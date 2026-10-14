import time
import json
import hmac
import hashlib
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from inbox.backend.services.outbox_worker import _process_webhook_notification
from campaigns.backend.routers.inbound_webhooks import (
    calendar_booking_webhook,
    intent_webhook,
    MAX_INTENT_BATCH_SIZE
)
from integrations.backend.services.webhook_service import (
    generate_webhook_signature,
    verify_webhook_signature,
    sanitize_webhook_payload
)


class TestOutboundWebhookSecurity(unittest.TestCase):
    """
    Paranoia Layer 0, 1 & 2: Outbound Webhook Security, Payload Sanitization & Signing.
    """

    @patch("requests.post")
    @patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True)
    def test_outbound_webhook_sanitizes_sensitive_secrets(self, mock_ssrf, mock_post):
        """Paranoia Layer 1 & 2: Internal tokens, passwords, and secrets are purged before dispatch."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        event = {
            "id": "evt_outbound_1",
            "workspace_id": "ws-sec-1",
            "payload": {
                "url": "https://api.partner.com/webhook",
                "lead_id": "lead-456",
                "email": "prospect@enterprise.com",
                "password": "internal_password_never_leak",
                "api_key": "sk_live_999999",
                "token": "jwt_token_secret",
                "secret": "signing_key_12345",
                "nested": {
                    "access_token": "oauth_token_val",
                    "campaign_id": "camp-99"
                }
            }
        }

        success = _process_webhook_notification(event)
        self.assertTrue(success)
        mock_post.assert_called_once()

        call_args, call_kwargs = mock_post.call_args
        self.assertEqual(call_args[0], "https://api.partner.com/webhook")
        dispatched_body = call_kwargs["json"]

        # Ensure credentials stripped
        self.assertNotIn("password", dispatched_body)
        self.assertNotIn("api_key", dispatched_body)
        self.assertNotIn("token", dispatched_body)
        self.assertNotIn("secret", dispatched_body)
        self.assertNotIn("access_token", dispatched_body.get("nested", {}))
        self.assertEqual(dispatched_body["lead_id"], "lead-456")
        self.assertEqual(dispatched_body["email"], "prospect@enterprise.com")
        self.assertEqual(dispatched_body["nested"]["campaign_id"], "camp-99")

    @patch("requests.post")
    @patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True)
    def test_outbound_webhook_signs_with_payload_secret(self, mock_ssrf, mock_post):
        """Paranoia Layer 0 & 1: HMAC-SHA256 signature generated when secret is in payload."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        signing_secret = "whsec_super_secret_key_888"
        event = {
            "id": "evt_outbound_2",
            "payload": {
                "url": "https://hooks.client.io/inbound",
                "event": "lead.replied",
                "data": {"reply_text": "Sounds great!"},
                "secret": signing_secret
            }
        }

        success = _process_webhook_notification(event)
        self.assertTrue(success)
        mock_post.assert_called_once()

        call_args, call_kwargs = mock_post.call_args
        headers = call_kwargs["headers"]
        dispatched_body = call_kwargs["json"]

        self.assertIn("EleIn-Signature", headers)
        self.assertIn("EleIn-Timestamp", headers)
        self.assertIn("X-Webhook-Signature", headers)
        self.assertIn("X-Webhook-Timestamp", headers)

        sig = headers["EleIn-Signature"]
        ts = headers["EleIn-Timestamp"]

        # Validate signature authenticity against dispatched clean payload
        valid = verify_webhook_signature(
            payload=dispatched_body,
            secret=signing_secret,
            timestamp=ts,
            signature=sig,
            tolerance_seconds=300
        )
        self.assertTrue(valid, "Outbound HMAC signature must match dispatched sanitized payload")

    @patch("requests.post")
    @patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True)
    def test_outbound_webhook_signs_with_workspace_settings_secret(self, mock_ssrf, mock_post):
        """Paranoia Layer 1: Falls back to database workspace_settings webhook_signing_secret."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        db_secret = "whsec_workspace_level_secret_999"
        mock_svc = MagicMock()
        mock_svc.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"webhook_signing_secret": db_secret}]
        )

        event = {
            "id": "evt_outbound_3",
            "workspace_id": "ws-custom-tenant",
            "payload": {
                "url": "https://webhook.site/receiver",
                "event": "lead.meeting_booked",
                "lead_id": "lead-321"
            }
        }

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_svc):
            success = _process_webhook_notification(event)

        self.assertTrue(success)
        call_args, call_kwargs = mock_post.call_args
        headers = call_kwargs["headers"]
        dispatched_body = call_kwargs["json"]

        self.assertIn("EleIn-Signature", headers)
        self.assertTrue(verify_webhook_signature(
            payload=dispatched_body,
            secret=db_secret,
            timestamp=headers["EleIn-Timestamp"],
            signature=headers["EleIn-Signature"]
        ))

    @patch("requests.post")
    @patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True)
    def test_outbound_webhook_unsigned_when_no_secret_configured(self, mock_ssrf, mock_post):
        """Paranoia Layer 2: Gracefully sends unsigned webhook when workspace has no signing secret."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        mock_svc = MagicMock()
        mock_svc.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        event = {
            "id": "evt_outbound_4",
            "workspace_id": "ws-no-secret",
            "payload": {
                "url": "https://webhook.site/receiver",
                "event": "lead.connected",
                "lead_id": "lead-111"
            }
        }

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_svc):
            success = _process_webhook_notification(event)

        self.assertTrue(success)
        call_args, call_kwargs = mock_post.call_args
        headers = call_kwargs["headers"]
        self.assertNotIn("EleIn-Signature", headers)
        self.assertNotIn("X-Webhook-Signature", headers)

    @patch("core.backend.core.validators.is_safe_ssrf_url", return_value=False)
    def test_outbound_webhook_ssrf_violation_blocked(self, mock_ssrf):
        """Paranoia Layer 1: Block SSRF payloads targeting internal IPs."""
        event = {
            "id": "evt_outbound_ssrf",
            "payload": {
                "url": "http://169.254.169.254/latest/meta-data/",
                "event": "ping"
            }
        }
        self.assertFalse(_process_webhook_notification(event))


class TestInboundBookingWebhookSecurity(unittest.IsolatedAsyncioTestCase):
    """
    Paranoia Layer 0, 1 & 2: Inbound Booking Webhook Replay Protection & HMAC Signatures.
    """

    def setUp(self):
        self.workspace_id = "ws-booking-test"
        self.mock_supabase = MagicMock()
        # Active workspace
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": self.workspace_id, "status": "active"}]
        )

    async def test_booking_webhook_rejects_expired_timestamp_replay_attack(self):
        """Paranoia Layer 1: Rejects replay payloads older than 300 seconds."""
        mock_req = MagicMock()
        old_timestamp = int(time.time()) - 301  # 5m 1s ago
        mock_req.headers = {"X-Webhook-Timestamp": str(old_timestamp)}
        mock_req.query_params = {}

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                await calendar_booking_webhook(self.workspace_id, mock_req)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("replay defense", ctx.exception.detail)

    async def test_booking_webhook_rejects_future_timestamp_drift(self):
        """Paranoia Layer 1: Rejects future timestamps beyond 300s drift."""
        mock_req = MagicMock()
        future_timestamp = int(time.time()) + 350
        mock_req.headers = {"EleIn-Timestamp": str(future_timestamp)}
        mock_req.query_params = {}

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                await calendar_booking_webhook(self.workspace_id, mock_req)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("replay defense", ctx.exception.detail)

    async def test_booking_webhook_rejects_malformed_timestamp_header(self):
        """Paranoia Layer 2: Gracefully rejects non-integer timestamp headers."""
        mock_req = MagicMock()
        mock_req.headers = {"Calendly-Webhook-Timestamp": "not_a_valid_unix_ts"}
        mock_req.query_params = {}

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                await calendar_booking_webhook(self.workspace_id, mock_req)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Invalid webhook timestamp header format", ctx.exception.detail)

    async def test_booking_webhook_valid_hmac_signature_succeeds(self):
        """Paranoia Layer 0 & 1: Successfully authenticates payload with valid HMAC-SHA256 signature."""
        secret = "booking_secret_abc123"
        payload = {"email": "sarah@clientcorp.com", "event": "invitee.created"}
        now_ts = int(time.time())
        ts, sig = generate_webhook_signature(payload, secret, timestamp_override=now_ts)

        mock_req = MagicMock()
        mock_req.headers = {
            "X-Webhook-Signature": sig,
            "X-Webhook-Timestamp": ts,
            "user-agent": "Calendly-Hook/1.0"
        }
        mock_req.query_params = {}
        mock_req.json = AsyncMock(return_value=payload)

        # Mock workspace settings with secret
        def table_mock(tbl):
            m = MagicMock()
            if tbl == "workspaces":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.workspace_id, "status": "active"}]
                )
            elif tbl == "workspace_settings":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"booking_webhook_secret": secret}]
                )
            elif tbl == "leads":
                m.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": "lead-999", "metadata": {}}]
                )
            elif tbl == "campaign_enrollments":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-1"}]
                )
            return m

        self.mock_supabase.table.side_effect = table_mock

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
            res = await calendar_booking_webhook(self.workspace_id, mock_req)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["lead_id"], "lead-999")

    async def test_booking_webhook_forged_signature_rejected_with_401(self):
        """Paranoia Layer 0 & 1: Forged or altered signature fails verification with 401."""
        secret = "booking_secret_abc123"
        payload = {"email": "attacker@fake.com", "event": "invitee.created"}
        now_ts = int(time.time())

        mock_req = MagicMock()
        mock_req.headers = {
            "EleIn-Signature": "forged_hex_signature_deadbeef0000",
            "EleIn-Timestamp": str(now_ts)
        }
        mock_req.query_params = {}
        mock_req.json = AsyncMock(return_value=payload)

        def table_mock(tbl):
            m = MagicMock()
            if tbl == "workspaces":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.workspace_id, "status": "active"}]
                )
            elif tbl == "workspace_settings":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"booking_webhook_secret": secret}]
                )
            return m

        self.mock_supabase.table.side_effect = table_mock

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                await calendar_booking_webhook(self.workspace_id, mock_req)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Invalid webhook signature", ctx.exception.detail)


class TestInboundIntentWebhookSecurity(unittest.TestCase):
    """
    Paranoia Layer 0, 1 & 2: Inbound Intent Webhook Batch Flooding & Replay Defense.
    """

    def setUp(self):
        self.campaign_id = "camp-intent-1"
        self.token = "test_token_valid_123"

        self.mock_supabase = MagicMock()
        # Valid API key
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": "ws-intent"}]
        )

    def test_intent_webhook_rejects_batch_exceeding_ceiling(self):
        """Paranoia Layer 1 & 2: Rejects payloads exceeding 500 leads with HTTP 400."""
        oversized_batch = [{"email": f"user{i}@bigcorp.com"} for i in range(MAX_INTENT_BATCH_SIZE + 1)]

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                intent_webhook(self.campaign_id, body=oversized_batch, token=self.token)

            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Batch size exceeds maximum limit of 500 leads", ctx.exception.detail)

    def test_intent_webhook_catastrophic_oom_bomb_blocked(self):
        """Paranoia Layer 2 (Human Paranoia): 50,000-lead payload bomb is rejected immediately."""
        bomb_batch = [{"email": f"victim{i}@bomb.com"} for i in range(50000)]

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                intent_webhook(self.campaign_id, body=bomb_batch, token=self.token)

            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Batch size exceeds maximum limit of 500 leads", ctx.exception.detail)

    def test_intent_webhook_rejects_expired_timestamp_replay_attack(self):
        """Paranoia Layer 1: Rejects replayed intent payloads when timestamp > 300s old."""
        mock_req = MagicMock()
        old_ts = int(time.time()) - 301
        mock_req.headers = {"X-Webhook-Timestamp": str(old_ts)}

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                intent_webhook(
                    self.campaign_id,
                    body={"email": "lead@target.com"},
                    token=self.token,
                    request=mock_req
                )
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("replay defense", ctx.exception.detail)

    def test_intent_webhook_rejects_malformed_timestamp(self):
        """Paranoia Layer 2: Rejects invalid timestamp string with 401."""
        mock_req = MagicMock()
        mock_req.headers = {"EleIn-Timestamp": "invalid_epoch_string"}

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=self.mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                intent_webhook(
                    self.campaign_id,
                    body={"email": "lead@target.com"},
                    token=self.token,
                    request=mock_req
                )
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Invalid webhook timestamp header format", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
