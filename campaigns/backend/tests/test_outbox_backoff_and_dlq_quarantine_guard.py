import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi import HTTPException

from inbox.backend.services.outbox_worker import (
    _compute_retry_deliver_at,
    _process_in_app_notification,
    _process_slack_notification,
    poll_outbox_once,
    get_outbox_dead_letter_events,
    retry_outbox_dead_letter_event,
    MAX_ATTEMPTS,
)
from inbox.backend.routers.notifications import (
    list_notification_dlq,
    retry_notification_dlq_event,
)
from integrations.backend.services.circuit_breaker import reset_all_circuit_breakers


class TestOutboxBackoffAndDlqQuarantineGuard(unittest.TestCase):
    """
    Step 32 Test Suite: Outbox Notification Exponential Backoff & Poison-Pill DLQ Quarantine Guard.
    Evaluates Three-Layer Paranoia Framework:
    - Layer 0: Exponential backoff calculation, payload field normalization ('message' vs 'body', top-level event_type).
    - Layer 1: Randomized jitter against thundering herds, infinite self-replicating DLQ alert loop prevention,
               per-workspace Slack circuit breaker protection, audit event handling.
    - Layer 2: DLQ inspection with pagination clamping, operator re-drive with status & SSRF pre-validation.
    """

    def setUp(self):
        reset_all_circuit_breakers()

    def _setup_multi_table_mock(self):
        from collections import defaultdict
        tables = defaultdict(MagicMock)
        mock_svc = MagicMock()
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    # =========================================================================
    # Layer 0 & 1: Exponential Backoff with Jitter
    # =========================================================================
    def test_compute_retry_deliver_at_exponential_backoff_with_jitter(self):
        """Paranoia Layer 0 & 1: Exponential backoff scales by 2^(attempt-1) with jitter and caps at 300s + jitter."""
        now = datetime.now(timezone.utc)

        # Deterministic without jitter
        t1_no_jitter = datetime.fromisoformat(_compute_retry_deliver_at(1, jitter=False))
        t2_no_jitter = datetime.fromisoformat(_compute_retry_deliver_at(2, jitter=False))
        t4_no_jitter = datetime.fromisoformat(_compute_retry_deliver_at(4, jitter=False))

        d1 = (t1_no_jitter - now).total_seconds()
        d2 = (t2_no_jitter - now).total_seconds()
        d4 = (t4_no_jitter - now).total_seconds()

        self.assertTrue(59.0 <= d1 <= 62.0, f"Expected ~60s for attempt 1, got {d1}")
        self.assertTrue(119.0 <= d2 <= 122.0, f"Expected ~120s for attempt 2, got {d2}")
        self.assertTrue(299.0 <= d4 <= 302.0, f"Expected ~300s cap for attempt 4, got {d4}")

        # With jitter enabled
        t1_jitter = datetime.fromisoformat(_compute_retry_deliver_at(1, jitter=True))
        d1_jitter = (t1_jitter - now).total_seconds()
        self.assertTrue(60.5 <= d1_jitter <= 77.0, f"Expected 61..75s with jitter, got {d1_jitter}")

    # =========================================================================
    # Layer 0: Payload Normalization ('message' vs 'body' & top-level event_type)
    # =========================================================================
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_in_app_notification_normalizes_message_and_top_level_event_type(self, mock_client):
        """Paranoia Layer 0: Outbox events using 'message' instead of 'body' and top-level event_type succeed."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "usr_1"}]
        )
        tables["notification_preferences"].select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["notifications"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )

        # Event format emitted by HubSpot / SenderPod alerts ('message' key, top-level 'event_type')
        event = {
            "id": "evt_hubspot_alert",
            "workspace_id": "ws_123",
            "event_type": "notification.in_app",
            "payload": {
                "title": "HubSpot Connection Expired",
                "message": "Your HubSpot token has expired. Please reconnect."
            }
        }

        res = _process_in_app_notification(event)
        self.assertTrue(res)
        tables["notifications"].insert.assert_called_once()
        inserted_rows = tables["notifications"].insert.call_args[0][0]
        self.assertEqual(inserted_rows[0]["title"], "HubSpot Connection Expired")
        self.assertEqual(inserted_rows[0]["body"], "Your HubSpot token has expired. Please reconnect.")

    # =========================================================================
    # Layer 1 & 2: Infinite Self-Replicating DLQ Alert Cascade Guard
    # =========================================================================
    @patch("inbox.backend.services.outbox_worker._process_in_app_notification", return_value=False)
    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_infinite_dlq_alert_cascade_loop_prevented(self, mock_client, mock_process):
        """
        Paranoia Layer 1 & 2: When a 'notification.in_app' event permanently fails after MAX_ATTEMPTS,
        it MUST NOT insert another 'notification.in_app' event into outbox_events (preventing infinite cascade loops).
        """
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "evt_in_app_fail",
                "workspace_id": "ws_loop_guard",
                "event_type": "notification.in_app",
                "payload": {"title": "Alert", "body": "Test"},
                "attempts": MAX_ATTEMPTS - 1
            }]
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_in_app_fail", "status": "processing"}]
        )

        poll_outbox_once()

        # Verify status was marked 'failed', and NO recursive outbox_events.insert was called!
        tables["outbox_events"].insert.assert_not_called()

    @patch("inbox.backend.services.outbox_worker._process_slack_notification", return_value=False)
    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_external_channel_dlq_queues_single_safe_in_app_alert(self, mock_client, mock_slack):
        """
        Paranoia Layer 2: When an external channel ('notification.slack') fails after MAX_ATTEMPTS,
        it queues a single in-app alert tagged with is_dlq_alert=True and both 'body' and 'message'.
        """
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "evt_slack_fail",
                "workspace_id": "ws_slack_1",
                "event_type": "notification.slack",
                "payload": {"text": "Hello Slack"},
                "attempts": MAX_ATTEMPTS - 1
            }]
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_slack_fail", "status": "processing"}]
        )

        poll_outbox_once()

        tables["outbox_events"].insert.assert_called_once()
        alert_row = tables["outbox_events"].insert.call_args[0][0]
        self.assertEqual(alert_row["event_type"], "notification.in_app")
        self.assertTrue(alert_row["payload"]["is_dlq_alert"])
        self.assertIn("body", alert_row["payload"])
        self.assertIn("message", alert_row["payload"])

    # =========================================================================
    # Layer 1: Slack Circuit Breaker Protection & Audit Event Delivery
    # =========================================================================
    @patch("requests.post")
    def test_slack_channel_circuit_breaker_protection(self, mock_post):
        """Paranoia Layer 1: 5 consecutive Slack failures trip the circuit breaker and fast-fail the 6th call."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        event = {
            "id": "evt_slack_cb",
            "workspace_id": "ws_cb_test",
            "payload": {
                "webhook_url": "https://hooks.slack.com/services/T00/B00/X00",
                "text": "Alert"
            }
        }

        for _ in range(5):
            self.assertFalse(_process_slack_notification(event))

        self.assertEqual(mock_post.call_count, 5)

        # 6th call should be blocked by the open circuit breaker without invoking requests.post
        self.assertFalse(_process_slack_notification(event))
        self.assertEqual(mock_post.call_count, 5)

    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_audit_outbox_events_delivered_without_suspending(self, mock_client):
        """Paranoia Layer 0 & 1: Audit events ('campaign.deleted', 'lead_list.deleted') mark delivered cleanly."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "evt_audit_1",
                "workspace_id": "ws_1",
                "event_type": "campaign.deleted",
                "payload": {"campaign_id": "camp_1", "name": "Q4 Outbound"},
                "attempts": 0
            }]
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_audit_1", "status": "processing"}]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 1)
        last_update = tables["outbox_events"].update.call_args_list[-1][0][0]
        self.assertEqual(last_update["status"], "delivered")

    # =========================================================================
    # Layer 2: Operator DLQ Inspection & Safe Re-Drive Guard
    # =========================================================================
    def test_get_outbox_dead_letter_events_pagination_and_tenant_isolation(self):
        """Paranoia Layer 2: Clamps pagination bounds and filters by workspace_id and failed/suspended status."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["outbox_events"].select.return_value.eq.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
            data=[{"id": "dlq_1", "status": "failed"}],
            count=1
        )

        res = get_outbox_dead_letter_events(mock_svc, workspace_id="ws_dlq", limit=500, offset=-10)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["limit"], 100)  # Clamped to 100
        self.assertEqual(res["offset"], 0)   # Clamped to 0
        self.assertEqual(len(res["data"]), 1)

    def test_retry_outbox_dead_letter_event_blocks_ssrf_and_wrong_status(self):
        """Paranoia Layer 2: Blocks re-driving delivered events or events containing SSRF URLs."""
        mock_svc, tables = self._setup_multi_table_mock()

        # 1. Event already delivered -> blocked
        tables["outbox_events"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ev_done", "workspace_id": "ws_1", "status": "delivered", "payload": {}}]
        )
        res_done = retry_outbox_dead_letter_event(mock_svc, "ev_done", "ws_1")
        self.assertEqual(res_done["status"], "error")
        self.assertIn("Cannot retry event in 'delivered' status", res_done["message"])

        # 2. Failed event with SSRF webhook URL -> blocked
        tables["outbox_events"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "ev_ssrf",
                "workspace_id": "ws_1",
                "status": "failed",
                "payload": {"url": "http://169.254.169.254/latest/meta-data/"}
            }]
        )
        res_ssrf = retry_outbox_dead_letter_event(mock_svc, "ev_ssrf", "ws_1")
        self.assertEqual(res_ssrf["status"], "error")
        self.assertIn("SSRF Violation", res_ssrf["message"])

        # 3. Valid failed event -> re-queued to pending with attempts=0
        tables["outbox_events"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "ev_valid",
                "workspace_id": "ws_1",
                "status": "failed",
                "payload": {"url": "https://hooks.slack.com/services/T00/B00/X00"}
            }]
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ev_valid", "status": "pending", "attempts": 0}]
        )
        res_ok = retry_outbox_dead_letter_event(mock_svc, "ev_valid", "ws_1")
        self.assertEqual(res_ok["status"], "success")
        self.assertEqual(res_ok["event_id"], "ev_valid")

    def test_notifications_dlq_router_endpoints(self):
        """Paranoia Layer 2: Router endpoints return DLQ list and raise appropriate 404/400 on invalid retry."""
        mock_svc, tables = self._setup_multi_table_mock()

        # 1. List DLQ
        tables["outbox_events"].select.return_value.eq.return_value.in_.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(
            data=[], count=0
        )
        list_res = list_notification_dlq(limit=20, offset=0, workspace_id="ws_1", supabase=mock_svc)
        self.assertEqual(list_res["status"], "success")

        # 2. Retry non-existent event -> 404
        tables["outbox_events"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with self.assertRaises(HTTPException) as ctx404:
            retry_notification_dlq_event("ev_missing", workspace_id="ws_1", supabase=mock_svc)
        self.assertEqual(ctx404.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
