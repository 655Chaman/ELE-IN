import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import time
from datetime import datetime, timezone
from fastapi import HTTPException

from integrations.backend.services.webhook_service import (
    SUPPORTED_WEBHOOK_EVENTS,
    generate_webhook_signature,
    verify_webhook_signature,
    emit_webhook_event,
    replay_webhook_delivery,
    debug_verify_signature,
    get_sample_webhook_payload,
)
from integrations.backend.routers.webhooks import (
    get_sample_event_payload,
    verify_signature_endpoint,
    replay_delivery_endpoint,
    VerifySignatureRequest,
)
from campaigns.backend.routers.inbound_webhooks import (
    stripe_inbound_webhook,
    hubspot_inbound_webhook,
    zapier_sample_endpoint,
)


class TestWebhookAutomationHub(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Automated Multi-Channel Inbound Webhook Listener &
    Zapier/Make Workflow Automation Hub (Blue Ocean Phase 9).
    Rigorously built under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.supabase = MagicMock()
        self.workspace_id = "ws_automation_101"
        self.lead_id = "lead_test_202"
        self.endpoint_id = "ep_subscriber_303"
        self.delivery_id = "del_record_404"
        self.signing_secret = "whsec_0123456789abcdef0123456789abcdef"

    # =========================================================================
    # 1. Event Catalog & Sample Payloads (Layer 0 Foundational)
    # =========================================================================

    def test_intent_hot_detected_registered_in_supported_events(self):
        """Layer 0: intent.hot_detected is registered in SUPPORTED_WEBHOOK_EVENTS."""
        self.assertIn("intent.hot_detected", SUPPORTED_WEBHOOK_EVENTS)
        self.assertIn("lead.replied", SUPPORTED_WEBHOOK_EVENTS)
        self.assertIn("lead.meeting_booked", SUPPORTED_WEBHOOK_EVENTS)

    def test_get_sample_webhook_payload_returns_structured_schema(self):
        """Layer 0: Generates realistic schema for Zapier / Make mapping."""
        sample = get_sample_webhook_payload("intent.hot_detected")
        self.assertEqual(sample["event"], "intent.hot_detected")
        self.assertIn("social_intent_score", sample["data"])
        self.assertIn("signals", sample["data"])

        sample_reply = get_sample_webhook_payload("lead.replied")
        self.assertEqual(sample_reply["event"], "lead.replied")
        self.assertIn("reply_text", sample_reply["data"])

    def test_sample_endpoint_returns_json(self):
        """Layer 0: Router GET /sample returns valid payload."""
        res = get_sample_event_payload(event="lead.replied")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["event"], "lead.replied")
        self.assertIn("sample", res)

    # =========================================================================
    # 2. HMAC Signature Verification & Debugger Tool (Layer 0, 1, 2)
    # =========================================================================

    def test_debug_verify_signature_valid_match(self):
        """Layer 0: Accurately validates genuine HMAC-SHA256 signature."""
        now_ts = int(time.time())
        payload = {"lead_id": "l_123", "event": "lead.replied"}
        _, sig = generate_webhook_signature(payload, self.signing_secret, timestamp_override=now_ts)

        res = debug_verify_signature(
            payload_str=json.dumps(payload),
            secret=self.signing_secret,
            signature=sig,
            timestamp=str(now_ts)
        )
        self.assertTrue(res["is_valid"])
        self.assertTrue(res["signature_match"])
        self.assertTrue(res["is_timestamp_valid"])
        self.assertEqual(res["expected_signature"], sig)

    def test_debug_verify_signature_detects_tampering_or_drift(self):
        """Layer 1: Detects payload tampering and timestamp drift (replay attack prevention)."""
        now_ts = int(time.time())
        payload = {"lead_id": "l_123"}
        _, sig = generate_webhook_signature(payload, self.signing_secret, timestamp_override=now_ts)

        # 1. Tampered payload
        tampered_res = debug_verify_signature(
            payload_str=json.dumps({"lead_id": "hacked"}),
            secret=self.signing_secret,
            signature=sig,
            timestamp=str(now_ts)
        )
        self.assertFalse(tampered_res["is_valid"])
        self.assertFalse(tampered_res["signature_match"])

        # 2. Expired timestamp drift (> 300s)
        old_ts = now_ts - 600
        _, old_sig = generate_webhook_signature(payload, self.signing_secret, timestamp_override=old_ts)
        drift_res = debug_verify_signature(
            payload_str=json.dumps(payload),
            secret=self.signing_secret,
            signature=old_sig,
            timestamp=str(old_ts),
            tolerance_seconds=300
        )
        self.assertFalse(drift_res["is_valid"])
        self.assertFalse(drift_res["is_timestamp_valid"])

    def test_verify_signature_endpoint_wrapper(self):
        """Layer 2: Router endpoint POST /verify-signature handles request."""
        now_ts = int(time.time())
        payload = {"test": 1}
        _, sig = generate_webhook_signature(payload, self.signing_secret, timestamp_override=now_ts)

        req = VerifySignatureRequest(
            payload=json.dumps(payload),
            secret=self.signing_secret,
            signature=sig,
            timestamp=str(now_ts)
        )
        res = verify_signature_endpoint(req)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["result"]["is_valid"])

    # =========================================================================
    # 3. Delivery Replay Harness (Layer 0, 1, 2)
    # =========================================================================

    @patch("integrations.backend.services.webhook_service.is_safe_ssrf_url", return_value=True)
    @patch("integrations.backend.services.webhook_service.requests.post")
    @patch("integrations.backend.services.webhook_service.decrypt_bytes")
    def test_replay_webhook_delivery_success(self, mock_decrypt, mock_post, mock_ssrf):
        """Layer 0: Successfully replays delivery and updates record."""
        mock_decrypt.return_value = self.signing_secret.encode('utf-8')
        mock_post.return_value = MagicMock(status_code=200, text="OK")

        # Mock delivery record and endpoint
        mock_delivery = {
            "id": self.delivery_id,
            "endpoint_id": self.endpoint_id,
            "workspace_id": self.workspace_id,
            "event_type": "lead.replied",
            "payload": {"lead_id": self.lead_id},
            "attempt_count": 1
        }
        mock_endpoint = {
            "id": self.endpoint_id,
            "workspace_id": self.workspace_id,
            "url": "https://hooks.zapier.com/hooks/catch/123/abc",
            "signing_secret": "abcdef123456"
        }

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "webhook_deliveries":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_delivery])
                t.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            elif tbl == "webhook_endpoints":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_endpoint])
            return t

        self.supabase.table.side_effect = table_side_effect

        res = replay_webhook_delivery(self.delivery_id, self.workspace_id, self.supabase)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["status_code"], 200)
        self.assertEqual(res["attempt_count"], 2)

    def test_replay_webhook_delivery_not_found(self):
        """Layer 2: Replaying missing delivery returns clean error."""
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        res = replay_webhook_delivery("non_existent_del", self.workspace_id, self.supabase)
        self.assertEqual(res["status"], "error")
        self.assertIn("not found", res["message"].lower())

    # =========================================================================
    # 4. Inbound Stripe Webhook (Layer 0, 1, 2)
    # =========================================================================

    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_stripe_inbound_webhook_checkout_completed(self, mock_get_client):
        """Layer 0: Handles checkout.session.completed, upgrades tier, and adds credits."""
        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb

        # Mock workspace
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.workspace_id, "tier": "FREE", "credits_balance": 100}]
        )
        # Mock idempotency check (not previously processed)
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": self.workspace_id, "tier": "FREE", "credits_balance": 100}]),
            MagicMock(data=[])  # No prior transaction with this order ID
        ]
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock()

        stripe_event = {
            "id": "evt_stripe_999",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_session_111",
                    "metadata": {
                        "workspace_id": self.workspace_id,
                        "package_id": "growth_tier"
                    }
                }
            }
        }

        mock_req = MagicMock()
        mock_req.body = AsyncMock(return_value=json.dumps(stripe_event).encode("utf-8"))
        mock_req.headers = {}

        res = await stripe_inbound_webhook(mock_req)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["event"], "checkout.session.completed")
        self.assertEqual(res["workspace_id"], self.workspace_id)

    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_stripe_inbound_webhook_idempotency_prevents_duplicate(self, mock_get_client):
        """Layer 1: Idempotency rejects duplicate Stripe event without double-crediting."""
        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb

        # Mock workspace exists and transaction already exists
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": self.workspace_id, "tier": "PRO"}]),
            MagicMock(data=[{"id": "tx_existing_123"}])  # Prior transaction found!
        ]

        stripe_event = {
            "id": "evt_stripe_duplicate",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_duplicate",
                    "metadata": {"workspace_id": self.workspace_id}
                }
            }
        }

        mock_req = MagicMock()
        mock_req.body = AsyncMock(return_value=json.dumps(stripe_event).encode("utf-8"))
        mock_req.headers = {}

        res = await stripe_inbound_webhook(mock_req)
        self.assertEqual(res["status"], "already_processed")

    # =========================================================================
    # 5. Inbound HubSpot Webhook (Layer 0, 1, 2)
    # =========================================================================

    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_hubspot_inbound_webhook_creates_lead(self, mock_get_client):
        """Layer 0: Ingests HubSpot contact payload and inserts lead."""
        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb

        # Mock active workspace
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": self.workspace_id, "status": "active"}]),
            MagicMock(data=[])  # Lead not existing yet
        ]
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new_lead"}])

        hubspot_payload = {
            "properties": {
                "email": "brian.halligan@hubspot.com",
                "firstname": "Brian",
                "lastname": "Halligan",
                "company": "HubSpot",
                "jobtitle": "Executive Chairman"
            }
        }

        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value=hubspot_payload)

        res = await hubspot_inbound_webhook(
            workspace_id=self.workspace_id,
            request=mock_req,
            campaign_id="camp_target_123"
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["processed_count"], 1)
        self.assertEqual(res["leads"][0]["email"], "brian.halligan@hubspot.com")

    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_hubspot_inbound_webhook_inactive_workspace_404(self, mock_get_client):
        """Layer 1: Non-existent workspace raises 404."""
        mock_sb = MagicMock()
        mock_get_client.return_value = mock_sb
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_req = MagicMock()
        with self.assertRaises(HTTPException) as cm:
            await hubspot_inbound_webhook(
                workspace_id="invalid_ws",
                request=mock_req
            )
        self.assertEqual(cm.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
