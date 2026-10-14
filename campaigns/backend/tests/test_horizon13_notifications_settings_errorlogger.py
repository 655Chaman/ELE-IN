import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import time
from fastapi import HTTPException, Request

from inbox.backend.routers.notifications import (
    get_notifications,
    mark_notification_read,
    mark_all_notifications_read,
)
from admin.backend.routers.settings import (
    add_ai_key,
    delete_ai_key,
    reset_ai_key,
    APIKeyCreate,
)
from core.backend.api.routers.error_logger import (
    log_error,
    ErrorLog,
    _rate_limit_records,
)
import knowledge.backend.services.elein_ai_service as ai_svc


class TestHorizon13NotificationsSettingsErrorLogger(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Horizon 13: Notification Center, Admin Settings Key Pool &
    Frontend Error Logging Rate Limiting.
    Three-Layer Paranoia Architecture.
    """

    def _setup_multi_table_mock(self):
        """Helper to create isolated mock per table name to prevent chaining collisions."""
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)

        def get_table(tbl_name):
            return tables[tbl_name]

        mock_svc.table.side_effect = get_table
        return mock_svc, tables

    # =========================================================================
    # 1. Notification Center (Layer 0, 1, 2)
    # =========================================================================

    def test_get_notifications_pagination_and_bounds(self):
        """Layer 2: Sanitize pagination bounds to max 100 and min 0."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_query = MagicMock()
        tables["notifications"].select.return_value.eq.return_value.eq.return_value.order.return_value.range.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=[{"id": "notif_1"}])

        res = get_notifications(
            unread_only=False,
            limit=500,  # Should clamp to 100
            offset=-10,  # Should normalize to 0
            workspace_id="ws_1",
            user_id="user_1",
            supabase=mock_svc
        )
        self.assertEqual(len(res), 1)
        # Verify range was called with offset 0 and limit clamped
        tables["notifications"].select.return_value.eq.return_value.eq.return_value.order.return_value.range.assert_called_with(0, 99)

    def test_mark_notification_read_404_if_not_found(self):
        """Layer 1: Updating a non-existent or foreign notification returns 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["notifications"].update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            mark_notification_read("notif_ghost", "ws_1", "user_1", mock_svc)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_mark_all_notifications_read_success(self):
        """Layer 0: Bulk marks all unread notifications as read for current user."""
        mock_svc, tables = self._setup_multi_table_mock()
        res = mark_all_notifications_read("ws_1", "user_1", mock_svc)
        self.assertEqual(res["status"], "ok")
        self.assertIn("marked as read", res["message"])
        tables["notifications"].update.assert_called()

    # =========================================================================
    # 2. Admin Settings & AI Key Pool (Layer 1, 2)
    # =========================================================================

    @patch("admin.backend.routers.settings.get_service_client")
    def test_add_ai_key_auto_detects_providers_and_strips_quotes(self, mock_svc_factory):
        """Layer 2: Strips quotes and 'Bearer ' prefix, auto-detects provider."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        # No duplicate exists
        tables["system_api_keys"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        tables["system_api_keys"].insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "key_1", "provider": "nvidia", "status": "active"}]
        )

        ai_svc._last_fetch_time = 123456789

        # Test with quotes and Bearer prefix
        payload = APIKeyCreate(api_key="'Bearer nvapi-test-key-secret-1234'")
        res = add_ai_key(payload, _auth="superadmin")
        self.assertEqual(res["provider"], "nvidia")

        # Verify insert called with cleaned key
        insert_args = tables["system_api_keys"].insert.call_args[0][0]
        self.assertEqual(insert_args["api_key"], "nvapi-test-key-secret-1234")
        self.assertEqual(insert_args["provider"], "nvidia")

        # Verify module-level cache was invalidated
        self.assertEqual(ai_svc._last_fetch_time, 0)

    @patch("admin.backend.routers.settings.get_service_client")
    def test_add_ai_key_rejects_empty_or_unknown_format(self, mock_svc_factory):
        """Layer 2: Reject empty keys or unrecognized key formats."""
        mock_svc, _ = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        with self.assertRaises(HTTPException) as ctx:
            add_ai_key(APIKeyCreate(api_key="   "), _auth="superadmin")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", ctx.exception.detail)

        with self.assertRaises(HTTPException) as ctx2:
            add_ai_key(APIKeyCreate(api_key="gibberish_random_key_format"), _auth="superadmin")
        self.assertEqual(ctx2.exception.status_code, 400)
        self.assertIn("Could not auto-detect provider", ctx2.exception.detail)

    @patch("admin.backend.routers.settings.get_service_client")
    def test_delete_and_reset_ai_key_invalidates_cache(self, mock_svc_factory):
        """Layer 0: Deleting or resetting keys triggers module cache invalidation."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        ai_svc._last_fetch_time = 999999
        delete_ai_key("key_1", _auth="superadmin")
        self.assertEqual(ai_svc._last_fetch_time, 0)

        ai_svc._last_fetch_time = 888888
        reset_ai_key("key_1", _auth="superadmin")
        self.assertEqual(ai_svc._last_fetch_time, 0)

    # =========================================================================
    # 3. Frontend Error Logger & Rate Limiter (Layer 1, 2)
    # =========================================================================

    async def test_log_error_rate_limiting_exceeded_returns_429(self):
        """Layer 2: Flooding error logger (>10 requests/min) triggers HTTP 429."""
        _rate_limit_records.clear()
        mock_req = MagicMock(spec=Request)
        mock_req.client = MagicMock(host="192.168.1.100")

        payload = ErrorLog(message="Uncaught ReferenceError")

        # First 10 requests pass
        for _ in range(10):
            res = await log_error(mock_req, payload)
            self.assertEqual(res["status"], "ok")

        # 11th request triggers rate limit
        with self.assertRaises(HTTPException) as ctx:
            await log_error(mock_req, payload)
        self.assertEqual(ctx.exception.status_code, 429)

    async def test_log_error_stale_ip_eviction_bounds_memory(self):
        """Layer 1: When tracked IP records exceed 1000, stale records are evicted."""
        _rate_limit_records.clear()
        now = time.time()
        # Seed 1050 old IPs (>60s ago)
        for i in range(1050):
            _rate_limit_records[f"old_ip_{i}"] = [now - 120]

        mock_req = MagicMock(spec=Request)
        mock_req.client = MagicMock(host="new_active_ip")
        payload = ErrorLog(message="Frontend syntax warning")

        await log_error(mock_req, payload)

        # Stale IPs should have been evicted, shrinking memory footprint
        self.assertLessEqual(len(_rate_limit_records), 100)


if __name__ == "__main__":
    unittest.main()
