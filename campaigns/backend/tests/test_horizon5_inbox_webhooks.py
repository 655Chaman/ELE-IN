import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta

from campaigns.backend.routers.inbound_webhooks import calendar_booking_webhook
from inbox.backend.routers.inbox import send_inbox_reply, SendReplyPayload
from inbox.backend.services.outbox_worker import poll_outbox_once, _process_webhook_notification


class TestHorizon5InboxAndWebhooks(unittest.IsolatedAsyncioTestCase):
    """
    Horizon 5: Inbox, Webhook Sync, CRM Integrations & Outbox Dispatch.
    Tests compliance with the Three-Layer Logic Architecture (Paranoia Framework).
    """

    # =========================================================================
    # Test 1: Calendar Booking Webhook Halts In-Flight Campaign States
    # =========================================================================
    async def test_calendar_booking_webhook_halts_all_in_flight_states(self):
        """
        PARANOIA TEST: When a prospect books via Calendly/Cal.com,
        the system MUST halt not just 'pending' states, but ALL in-flight states
        including 'waiting_for_reply' and 'running' so automated follow-ups are killed.
        """
        mock_supabase = MagicMock()
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "event": "invitee.created",
            "payload": {
                "email": "prospect@targetcorp.com"
            }
        })

        # Mock finding lead
        mock_lead_table = MagicMock()
        mock_lead_res = MagicMock(data=[{
            "id": "lead_book_123",
            "metadata": {"tags": ["outreach_active"]}
        }])
        mock_lead_table.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_lead_res

        # Mock enrollments
        mock_enr_table = MagicMock()
        mock_enr_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[
            {"id": "enr_1"}
        ])

        # Mock execution states update
        mock_state_table = MagicMock()

        def table_router(table_name):
            if table_name == "leads":
                return mock_lead_table
            elif table_name == "campaign_enrollments":
                return mock_enr_table
            elif table_name == "campaign_execution_states":
                return mock_state_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            res = await calendar_booking_webhook("ws_test", mock_request)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["lead_id"], "lead_book_123")

        # Verify execution states update halted all in-flight states
        update_call = mock_state_table.update.return_value.in_.return_value.in_.return_value.execute
        update_args = mock_state_table.update.call_args[0][0]
        self.assertEqual(update_args["status"], "completed")
        self.assertEqual(update_args["error_reason"], "meeting_booked")
        # Check that the in_ filter included in-flight states
        in_filter_args = mock_state_table.update.return_value.in_.return_value.in_.call_args
        self.assertEqual(in_filter_args[0][0], "status")
        self.assertIn("waiting_for_reply", in_filter_args[0][1])
        self.assertIn("running", in_filter_args[0][1])

    # =========================================================================
    # Test 2: Calendar Booking Webhook Handles Empty / Malformed Payload Gracefully
    # =========================================================================
    async def test_calendar_booking_webhook_ignores_missing_email(self):
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"unrelated": "payload"})

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client"):
            res = await calendar_booking_webhook("ws_test", mock_request)

        self.assertEqual(res["status"], "ignored")
        self.assertIn("No attendee email", res["reason"])

    # =========================================================================
    # Test 3: Inbox Reply Idempotency & Normalization
    # =========================================================================
    def test_send_inbox_reply_deduplication_and_normalization(self):
        mock_supabase = MagicMock()
        mock_msg_table = MagicMock()

        # Simulate existing message sent 2 seconds ago
        mock_msg_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[{"id": "msg_existing_123"}]
        )
        mock_supabase.table.return_value = mock_msg_table

        payload = SendReplyPayload(
            sender_name="John Prospect",
            message_text="Sounds great, let's connect tomorrow!"
        )

        res = send_inbox_reply(
            payload=payload,
            supabase=mock_supabase,
            workspace_id="ws_inbox_test"
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["message_id"], "msg_existing_123")
        self.assertTrue(res.get("deduplicated"))

    # =========================================================================
    # Test 4: Outbox Worker Webhook SSRF Rejection
    # =========================================================================
    def test_outbox_webhook_ssrf_protection(self):
        # Event targeting private localhost or AWS metadata endpoint
        unsafe_event = {
            "id": "outbox_evt_1",
            "payload": {
                "url": "http://169.254.169.254/latest/meta-data/"
            }
        }
        with patch("core.backend.core.validators.is_safe_ssrf_url", return_value=False):
            result = _process_webhook_notification(unsafe_event)
            self.assertFalse(result, "SSRF attempt must be rejected by outbox worker")


if __name__ == "__main__":
    unittest.main()
