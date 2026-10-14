import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

class TestInboundWebhookReplayAndInboxSyncGuard(unittest.TestCase):
    
    def setUp(self):
        # Clear global idempotency ledger before each test
        from integrations.backend.services.inbound_ingest_service import get_inbound_idempotency_ledger
        get_inbound_idempotency_ledger().clear()

    def test_booking_webhook_idempotency_replay_blocked(self):
        """
        Test 1: calendar_booking_webhook blocks replay duplicates using InboundIdempotencyLedger.
        First call processes successfully, second call returns status: 'idempotent_duplicate'.
        """
        from campaigns.backend.routers.inbound_webhooks import calendar_booking_webhook
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "ws-1", "status": "active"}])
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "lead-1", "metadata": {}}])
        
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.json = AsyncMock(return_value={"email": "test@example.com", "event": "invitee.created"})

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):
            res1 = asyncio.run(calendar_booking_webhook(workspace_id="ws-1", request=mock_request))
            self.assertEqual(res1["status"], "success")

            res2 = asyncio.run(calendar_booking_webhook(workspace_id="ws-1", request=mock_request))
            self.assertEqual(res2["status"], "idempotent_duplicate")

    def test_smartlead_webhook_idempotency_replay_blocked(self):
        """
        Test 2: smartlead_inbound_webhook blocks duplicate webhooks.
        """
        from campaigns.backend.routers.inbound_webhooks import smartlead_inbound_webhook
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws-1", "status": "active"}])
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "lead-1", "metadata": {}}])
        
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.json = AsyncMock(return_value={"email": "lead@company.com", "event_type": "EMAIL_REPLY"})

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):
            res1 = asyncio.run(smartlead_inbound_webhook(workspace_id="ws-1", request=mock_request))
            self.assertEqual(res1["status"], "success")

            res2 = asyncio.run(smartlead_inbound_webhook(workspace_id="ws-1", request=mock_request))
            self.assertEqual(res2["status"], "idempotent_duplicate")

    def test_instantly_webhook_idempotency_replay_blocked(self):
        """
        Test 3: instantly_inbound_webhook blocks duplicate webhooks.
        """
        from campaigns.backend.routers.inbound_webhooks import instantly_inbound_webhook
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws-1", "status": "active"}])
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "lead-1", "metadata": {}}])
        
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.json = AsyncMock(return_value={"email": "lead@company.com", "event_type": "reply_received"})

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):
            res1 = asyncio.run(instantly_inbound_webhook(workspace_id="ws-1", request=mock_request))
            self.assertEqual(res1["status"], "success")

            res2 = asyncio.run(instantly_inbound_webhook(workspace_id="ws-1", request=mock_request))
            self.assertEqual(res2["status"], "idempotent_duplicate")

    def test_intent_webhook_idempotency_replay_blocked(self):
        """
        Test 4: intent_webhook blocks duplicate payloads.
        """
        from campaigns.backend.routers.inbound_webhooks import intent_webhook
        
        mock_supabase = MagicMock()
        
        def table_router(table_name):
            t = MagicMock()
            if table_name == "api_keys":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"workspace_id": "ws-1"}])
            elif table_name == "campaigns":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "camp-1"}])
            elif table_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"account_id": "acc-1", "accounts": {"id": "acc-1", "status": "ACTIVE"}}])
            elif table_name == "campaign_versions":
                t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "ver-1"}])
            elif table_name == "leads":
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                t.insert.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                t.insert.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "campaign_execution_states":
                t.select.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                t.insert.return_value.execute.return_value = MagicMock(data=[])
            return t

        mock_supabase.table.side_effect = table_router

        mock_request = MagicMock()
        mock_request.headers = {"x-api-key": "valid-token"}

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):
            res1 = intent_webhook("camp-1", {"email": "prospect@startup.com"}, api_key="valid-token", request=mock_request)
            self.assertEqual(res1["status"], "success")

            res2 = intent_webhook("camp-1", {"email": "prospect@startup.com"}, api_key="valid-token", request=mock_request)
            self.assertEqual(res2["status"], "idempotent_duplicate")

    def test_sync_inbox_messages_skips_sentiment_and_advance_for_existing(self):
        """
        Test 5: sync_inbox_messages skips sentiment analysis and state update for messages already present in existing_map.
        """
        from inbox.backend.services.inbox_service import sync_inbox_messages

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "acc-1", "imap_user": "test@domain.com"}])
        existing_record = {
            "id": "msg-existing",
            "sender_name": "lead@client.com",
            "message_text": "Sounds good!",
            "direction": "inbound",
            "thread_url": ""
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[existing_record])

        incoming_msg = {
            "id": "msg-existing",
            "sender_name": "lead@client.com",
            "message_text": "Sounds good!",
            "direction": "inbound",
            "thread_url": "",
            "lead_id": "lead-1"
        }

        with patch("inbox.backend.services.sentiment_classifier.apply_inbound_sentiment_actions") as mock_sentiment, \
             patch("inbox.backend.services.inbox_service.resolve_inbound_lead_and_campaign_context") as mock_resolve:

            res = sync_inbox_messages(mock_supabase, workspace_id="ws-1", account_id="acc-1", messages=[incoming_msg])
            self.assertEqual(res["updated"], 1)
            mock_sentiment.assert_not_called()

    def test_sync_inbox_messages_concurrency_lock(self):
        """
        Test 6: _get_account_sync_lock returns the same mutex lock for the same account, and a different lock for another account.
        """
        from inbox.backend.services.inbox_service import _get_account_sync_lock

        lock1_a = _get_account_sync_lock("ws-1", "acc-1")
        lock1_b = _get_account_sync_lock("ws-1", "acc-1")
        lock2 = _get_account_sync_lock("ws-1", "acc-2")

        self.assertIs(lock1_a, lock1_b)
        self.assertIsNot(lock1_a, lock2)

if __name__ == '__main__':
    unittest.main()
