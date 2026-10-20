import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
import os

from campaigns.backend.routers.inbound_webhooks import (
    smartlead_inbound_webhook,
    instantly_inbound_webhook,
    calendar_booking_webhook,
    _cascade_halt_lead_linkedin_outreach
)
from integrations.backend.services.elein_crm_service import (
    unsubscribe_from_smartlead,
    pause_lead_in_smartlead,
    unsubscribe_from_instantly
)
from inbox.backend.services.inbox_service import sync_inbox_messages


def _make_mock_request(json_data, headers=None, query_params=None):
    req = MagicMock()
    req.headers = headers or {}
    req.query_params = query_params or {}
    async def get_json():
        return json_data
    req.json = get_json
    return req


class TestCrossChannelSyncAndUnsubscribe(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws-test-100"
        self.lead_id = "lead-test-200"
        self.email = "prospect@company.com"

    def _build_mock_supabase(self, lead_meta=None, lead_status="Active", states_status="pending", secret=None):
        supabase = MagicMock()
        lead_meta = lead_meta or {}
        tables = {}

        def table_mock(tbl):
            if tbl in tables:
                return tables[tbl]
            m = MagicMock()
            if tbl == "workspaces":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.workspace_id, "status": "active"}]
                )
            elif tbl == "workspace_settings":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"smartlead_webhook_secret": secret, "instantly_webhook_secret": secret, "booking_webhook_secret": secret}] if secret else []
                )
            elif tbl == "leads":
                lead_data = [{"id": self.lead_id, "status": lead_status, "metadata": dict(lead_meta), "email": self.email}]
                m.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=lead_data)
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=lead_data)
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "campaign_enrollments":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-101"}]
                )
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-101"}]
                )
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-101"}]
                )
            elif tbl == "campaign_execution_states":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"status": states_status}]
                )
                m.update.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                m.update.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                m.update.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "outbox_events":
                m.insert.return_value.execute.return_value = MagicMock(data=[])
            elif tbl == "messages":
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                m.upsert.return_value.execute.return_value = MagicMock(data=[])
            tables[tbl] = m
            return m

        supabase.table.side_effect = table_mock
        return supabase

    # 1. test_smartlead_reply_halts_linkedin_outreach
    def test_smartlead_reply_halts_linkedin_outreach(self):
        """Layer 0 & 1: Inbound Smartlead reply updates lead status, metadata, halts pending/running states, queues outbox notification."""
        mock_supabase = self._build_mock_supabase()
        req = _make_mock_request({
            "event_type": "EMAIL_REPLY",
            "email": self.email,
            "reply_text": "Sounds great, let's schedule a demo."
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
            res = asyncio.run(smartlead_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["lead_id"], self.lead_id)

            # Verify leads table update
            leads_table = mock_supabase.table("leads")
            leads_table.update.assert_called()
            update_call = leads_table.update.call_args[0][0]
            self.assertIn(update_call["status"].lower(), ["replied", "replied (email)"])
            self.assertTrue(update_call["metadata"].get("email_replied"))
            self.assertIn("email_replied", update_call["metadata"].get("tags", []))
            self.assertEqual(update_call["metadata"].get("email_reply_text"), "Sounds great, let's schedule a demo.")

            # Verify campaign_execution_states halted
            exec_table = mock_supabase.table("campaign_execution_states")
            exec_table.update.assert_called()
            halt_call = exec_table.update.call_args[0][0]
            self.assertEqual(halt_call["status"], "completed")
            self.assertEqual(halt_call["error_reason"], "email_replied")

            # Verify in-app notification in outbox_events
            outbox_table = mock_supabase.table("outbox_events")
            outbox_table.insert.assert_called()
            outbox_call = outbox_table.insert.call_args[0][0]
            self.assertEqual(outbox_call["event_type"], "notification.in_app")
            self.assertIn("Lead Replied via Email", outbox_call["payload"]["title"])

            # Verify webhook event emission
            mock_emit.assert_called_once()
            self.assertEqual(mock_emit.call_args[1]["event_type"], "lead.email_replied")
            self.assertEqual(mock_emit.call_args[1]["payload"]["channel"], "smartlead")

    # 2. test_smartlead_unsubscribe_halts_linkedin_outreach
    def test_smartlead_unsubscribe_halts_linkedin_outreach(self):
        """Layer 0 & 1: Inbound Smartlead unsubscribe sets lead status to Unsubscribed, halts states."""
        mock_supabase = self._build_mock_supabase()
        req = _make_mock_request({
            "event_type": "LEAD_UNSUBSCRIBED",
            "email": self.email
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
            res = asyncio.run(smartlead_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "success")

            leads_table = mock_supabase.table("leads")
            update_call = leads_table.update.call_args[0][0]
            self.assertEqual(update_call["status"], "Unsubscribed")
            self.assertTrue(update_call["metadata"].get("unsubscribed"))
            self.assertEqual(update_call["metadata"].get("unsubscribed_channel"), "smartlead")

            exec_table = mock_supabase.table("campaign_execution_states")
            halt_call = exec_table.update.call_args[0][0]
            self.assertEqual(halt_call["status"], "completed")
            self.assertEqual(halt_call["error_reason"], "email_unsubscribed")

            mock_emit.assert_called_once()
            self.assertEqual(mock_emit.call_args[1]["event_type"], "lead.unsubscribed")

    # 3. test_instantly_reply_halts_linkedin_outreach
    def test_instantly_reply_halts_linkedin_outreach(self):
        """Layer 0 & 1: Instantly reply halts states and sets lead status to Replied (Email)."""
        mock_supabase = self._build_mock_supabase()
        req = _make_mock_request({
            "event_type": "reply_received",
            "email": self.email,
            "reply_text": "Let's touch base next month."
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
            res = asyncio.run(instantly_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "success")

            leads_table = mock_supabase.table("leads")
            update_call = leads_table.update.call_args[0][0]
            self.assertIn(update_call["status"].lower(), ["replied", "replied (email)"])
            self.assertTrue(update_call["metadata"].get("email_replied"))

            exec_table = mock_supabase.table("campaign_execution_states")
            halt_call = exec_table.update.call_args[0][0]
            self.assertEqual(halt_call["status"], "completed")
            self.assertEqual(halt_call["error_reason"], "email_replied")

            mock_emit.assert_called_once()
            self.assertEqual(mock_emit.call_args[1]["event_type"], "lead.email_replied")
            self.assertEqual(mock_emit.call_args[1]["payload"]["channel"], "instantly")

    # 4. test_instantly_unsubscribe_halts_linkedin_outreach
    def test_instantly_unsubscribe_halts_linkedin_outreach(self):
        """Layer 0 & 1: Instantly unsubscribe halts states and sets status to Unsubscribed."""
        mock_supabase = self._build_mock_supabase()
        req = _make_mock_request({
            "event_type": "lead_unsubscribed",
            "email": self.email
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
            res = asyncio.run(instantly_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "success")

            leads_table = mock_supabase.table("leads")
            update_call = leads_table.update.call_args[0][0]
            self.assertEqual(update_call["status"], "Unsubscribed")
            self.assertEqual(update_call["metadata"].get("unsubscribed_channel"), "instantly")

            exec_table = mock_supabase.table("campaign_execution_states")
            halt_call = exec_table.update.call_args[0][0]
            self.assertEqual(halt_call["status"], "completed")
            self.assertEqual(halt_call["error_reason"], "email_unsubscribed")

            mock_emit.assert_called_once()
            self.assertEqual(mock_emit.call_args[1]["event_type"], "lead.unsubscribed")

    # 5. test_inbound_webhook_tenant_isolation_404
    def test_inbound_webhook_tenant_isolation_404(self):
        """Layer 1: Non-existent or inactive workspace returns 404."""
        mock_supabase = MagicMock()
        # Non-existent workspace
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        req = _make_mock_request({"email": self.email, "event_type": "REPLY"})

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(smartlead_inbound_webhook("ws-non-existent", req))
            self.assertEqual(ctx.exception.status_code, 404)

        # Inactive workspace
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws-inactive", "status": "suspended"}]
        )
        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(smartlead_inbound_webhook("ws-inactive", req))
            self.assertEqual(ctx.exception.status_code, 404)

    # 6. test_inbound_webhook_secret_authentication
    def test_inbound_webhook_secret_authentication(self):
        """Layer 1: When workspace has a configured secret, wrong secret returns 401, correct secret succeeds."""
        mock_supabase = self._build_mock_supabase(secret="super-secret-key-123")
        
        # Wrong secret
        bad_req = _make_mock_request(
            {"email": self.email, "event_type": "REPLY"},
            headers={"x-webhook-secret": "wrong-secret"}
        )
        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(smartlead_inbound_webhook(self.workspace_id, bad_req))
            self.assertEqual(ctx.exception.status_code, 401)

        # Correct secret
        good_req = _make_mock_request(
            {"email": self.email, "event_type": "REPLY"},
            headers={"x-webhook-secret": "super-secret-key-123"}
        )
        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            res = asyncio.run(smartlead_inbound_webhook(self.workspace_id, good_req))
            self.assertEqual(res["status"], "success")

    # 7. test_inbound_webhook_idempotency_defense
    def test_inbound_webhook_idempotency_defense(self):
        """Layer 2: Second identical webhook on already processed lead returns already_processed."""
        mock_supabase = self._build_mock_supabase(
            lead_meta={"email_replied": True},
            lead_status="Replied (Email)",
            states_status="completed"
        )
        req = _make_mock_request({
            "event_type": "EMAIL_REPLY",
            "email": self.email
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            res = asyncio.run(smartlead_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "already_processed")
            # Verify update was NOT called redundantly
            mock_supabase.table("leads").update.assert_not_called()

    # 8. test_inbound_webhook_malformed_email
    def test_inbound_webhook_malformed_email(self):
        """Layer 2: Malformed or invalid email format returns ignored."""
        mock_supabase = self._build_mock_supabase()
        req = _make_mock_request({
            "event_type": "EMAIL_REPLY",
            "email": "not-a-valid-email-format"
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            res = asyncio.run(smartlead_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "ignored")
            self.assertIn("Invalid or malformed email", res["reason"])

    # 9. test_inbound_webhook_lead_not_found
    def test_inbound_webhook_lead_not_found(self):
        """Layer 2: Unknown lead email returns ignored."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.workspace_id, "status": "active"}]
        )
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        req = _make_mock_request({
            "event_type": "EMAIL_REPLY",
            "email": "unknown@company.com"
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
            res = asyncio.run(smartlead_inbound_webhook(self.workspace_id, req))
            self.assertEqual(res["status"], "ignored")
            self.assertIn("No lead matching", res["reason"])

    # 10. test_outbound_unsubscribe_smartlead
    def test_outbound_unsubscribe_smartlead(self):
        """Layer 0 & 1: Verifies unsubscribe_from_smartlead sends request with API key."""
        with patch.dict(os.environ, {"SMARTLEAD_API_KEY": "sl_test_key_123"}), \
             patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)

            # Campaign-specific unsubscribe
            res = unsubscribe_from_smartlead("ws-1", "prospect@target.com", campaign_id="camp-777")
            self.assertTrue(res)
            mock_post.assert_called_with(
                "https://server.smartlead.ai/api/v1/campaigns/camp-777/leads/unsubscribe",
                headers={"Content-Type": "application/json"},
                json={"api_key": "sl_test_key_123", "email": "prospect@target.com"},
                timeout=12
            )

            # Global unsubscribe
            mock_post.reset_mock()
            res_global = unsubscribe_from_smartlead("ws-1", "prospect@target.com")
            self.assertTrue(res_global)
            mock_post.assert_called_with(
                "https://server.smartlead.ai/api/v1/leads/unsubscribe",
                headers={"Content-Type": "application/json"},
                json={"api_key": "sl_test_key_123", "email": "prospect@target.com"},
                timeout=12
            )

    # 11. test_outbound_unsubscribe_instantly
    def test_outbound_unsubscribe_instantly(self):
        """Layer 0 & 1: Verifies unsubscribe_from_instantly sends request with API key."""
        with patch.dict(os.environ, {"INSTANTLY_API_KEY": "inst_test_key_456"}), \
             patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)

            res = unsubscribe_from_instantly("ws-1", "prospect@target.com")
            self.assertTrue(res)
            mock_post.assert_called_with(
                "https://api.instantly.ai/api/v1/lead/update",
                headers={"Content-Type": "application/json"},
                json={"api_key": "inst_test_key_456", "email": "prospect@target.com", "status": "unsubscribed"},
                timeout=12
            )

    # 12. test_booking_webhook_cascades_email_unsubscribe
    def test_booking_webhook_cascades_email_unsubscribe(self):
        """Layer 0 & 1: Confirmed booking triggers email unsubscribe cascade across Smartlead and Instantly."""
        mock_supabase = self._build_mock_supabase()
        booking_payload = {
            "email": "sarah@client.com",
            "event": "invitee.created"
        }
        req = _make_mock_request(booking_payload, headers={"user-agent": "Calendly-Hook/1.0"})

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("integrations.backend.services.elein_crm_service.unsubscribe_from_smartlead") as mock_unsub_sl, \
             patch("integrations.backend.services.elein_crm_service.unsubscribe_from_instantly") as mock_unsub_inst:
            res = asyncio.run(calendar_booking_webhook(workspace_id=self.workspace_id, request=req))
            self.assertEqual(res["status"], "success")
            mock_unsub_sl.assert_called_once_with(self.workspace_id, "sarah@client.com")
            mock_unsub_inst.assert_called_once_with(self.workspace_id, "sarah@client.com")

    # 13. test_inbound_linkedin_reply_cascades_email_unsubscribe
    def test_inbound_linkedin_reply_cascades_email_unsubscribe(self):
        """Layer 0 & 1: Inbound LinkedIn reply advances lead and triggers email unsubscribe cascade."""
        mock_supabase = self._build_mock_supabase()
        inbound_messages = [{
            "sender_name": "John Doe",
            "message_text": "Hey, I am open to a chat next Monday.",
            "direction": "inbound",
            "thread_url": "https://linkedin.com/messaging/thread/123",
            "intent": "positive"
        }]

        with patch("inbox.backend.services.inbox_service.resolve_inbound_lead_and_campaign_context", return_value={"lead_id": self.lead_id}), \
             patch("integrations.backend.services.elein_crm_service.unsubscribe_from_smartlead") as mock_unsub_sl, \
             patch("integrations.backend.services.elein_crm_service.unsubscribe_from_instantly") as mock_unsub_inst:
            res = sync_inbox_messages(mock_supabase, self.workspace_id, "acc-101", inbound_messages)
            self.assertGreater(res["new_saved"] + res["updated"], 0)
            mock_unsub_sl.assert_called_once_with(self.workspace_id, self.email)
            mock_unsub_inst.assert_called_once_with(self.workspace_id, self.email)


if __name__ == "__main__":
    unittest.main()
