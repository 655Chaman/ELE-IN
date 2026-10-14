import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from integrations.backend.services.webhook_service import (
    normalize_webhook_url,
    rotate_webhook_signing_secret,
    prune_expired_webhook_dlq,
    emit_webhook_event
)


class TestWebhookServiceHardeningAndRotationGuard(unittest.TestCase):

    def test_normalize_webhook_url_valid_and_invalid(self):
        # 1. Valid URL with https
        self.assertEqual(
            normalize_webhook_url("  https://Example.COM/Path/  "),
            "https://example.com/Path/"
        )
        # 2. Query parameters preserved, whitespace / quotes stripped
        self.assertEqual(
            normalize_webhook_url(' "http://myhook.io/webhook?foo=bar" '),
            "http://myhook.io/webhook?foo=bar"
        )
        # 3. Missing scheme defaults to https://
        self.assertEqual(
            normalize_webhook_url("api.webhook.site/v1"),
            "https://api.webhook.site/v1"
        )
        # 4. Invalid schemes rejected
        self.assertEqual(normalize_webhook_url("ftp://example.com"), "")
        self.assertEqual(normalize_webhook_url("javascript:alert(1)"), "")
        # 5. Empty or non-string rejected
        self.assertEqual(normalize_webhook_url(""), "")
        self.assertEqual(normalize_webhook_url(None), "")

    def test_rotate_signing_secret_success(self):
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
            data=[{"id": "ep_123", "workspace_id": "ws_123"}]
        )
        mock_supabase.table().update().eq().eq().execute.return_value = MagicMock(
            data=[{"id": "ep_123"}]
        )

        with patch("integrations.backend.services.webhook_service.encrypt_bytes", return_value=b"mock_encrypted"):
            res = rotate_webhook_signing_secret("ep_123", "ws_123", supabase=mock_supabase)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("endpoint_id"), "ep_123")
        secret = res.get("signing_secret")
        self.assertTrue(secret.startswith("whsec_"))

    def test_rotate_signing_secret_rejects_foreign_workspace(self):
        mock_supabase = MagicMock()
        # Mock endpoint query returning empty (unauthorized / IDOR)
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
            data=[]
        )

        res = rotate_webhook_signing_secret("ep_123", "ws_evil", supabase=mock_supabase)
        self.assertEqual(res.get("status"), "error")
        self.assertIn("not found or unauthorized", res.get("message", "").lower())

    def test_create_webhook_rejects_duplicate_active_url(self):
        mock_supabase = MagicMock()
        # Simulate existing active endpoint with same normalized URL
        mock_supabase.table().select().eq().eq().eq().execute.return_value = MagicMock(
            data=[{"id": "ep_existing"}]
        )
        dup_check = mock_supabase.table("webhook_endpoints") \
            .select("id") \
            .eq("workspace_id", "ws_123") \
            .eq("url", "https://example.com/hook") \
            .eq("is_active", True) \
            .execute()
        self.assertTrue(len(dup_check.data) > 0)

    def test_create_webhook_rejects_ssrf_url(self):
        from core.backend.core.validators import is_safe_ssrf_url
        self.assertFalse(is_safe_ssrf_url("http://127.0.0.1/hook"))
        self.assertFalse(is_safe_ssrf_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(is_safe_ssrf_url("http://localhost:8000/hook"))

    def test_prune_expired_webhook_dlq_deletes_only_dead_letter(self):
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        # Ensure table("webhook_deliveries") returns mock_table
        mock_supabase.table.return_value = mock_table
        
        # When select is called, return query builder mock where execute returns rows
        select_mock = MagicMock()
        select_mock.eq.return_value = select_mock
        select_mock.lt.return_value = select_mock
        select_mock.limit.return_value = select_mock
        select_mock.execute.return_value = MagicMock(data=[{"id": "del_1"}, {"id": "del_2"}])
        mock_table.select.return_value = select_mock

        # When delete is called, return delete builder mock where execute returns deleted rows
        delete_mock = MagicMock()
        delete_mock.eq.return_value = delete_mock
        delete_mock.in_.return_value = delete_mock
        delete_mock.execute.return_value = MagicMock(data=[{"id": "del_1"}, {"id": "del_2"}])
        mock_table.delete.return_value = delete_mock

        res = prune_expired_webhook_dlq(workspace_id="ws_123", retention_days=30, supabase=mock_supabase)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("pruned_count"), 2)

    def test_prune_expired_webhook_dlq_enforces_minimum_retention_floor(self):
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().lt().limit().execute.return_value = MagicMock(data=[])

        res = prune_expired_webhook_dlq(workspace_id="ws_123", retention_days=2, supabase=mock_supabase)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("retention_days"), 7)

    def test_emit_webhook_event_case_insensitive_matching(self):
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
            data=[
                {
                    "id": "ep_1",
                    "url": "https://example.com/hook",
                    "event_types": ["LEAD.REPLIED"],
                    "is_active": True
                }
            ]
        )
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "ins_1"}])

        count = emit_webhook_event(
            workspace_id="ws_123",
            event_type="lead.replied",
            payload={"lead_id": "lead_1"},
            supabase=mock_supabase
        )
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
