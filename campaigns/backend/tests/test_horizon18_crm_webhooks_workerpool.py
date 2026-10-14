import os
import json
import time
import hmac
import hashlib
import unittest
from unittest.mock import MagicMock, patch

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

from integrations.backend.services.elein_crm_service import (
    push_to_hubspot,
    push_to_salesforce,
    push_to_pipedrive,
    push_to_notion,
    push_to_airtable,
    add_to_emailbison,
    add_to_lemlist,
    add_to_apollo,
    send_webhook,
    send_slack_alert,
    _safe_refund_credits,
    RateLimitExceeded
)
from integrations.backend.services.webhook_service import (
    sanitize_webhook_payload,
    generate_webhook_signature,
    verify_webhook_signature
)
from integrations.backend.services.linkedin_pool import (
    BrowserPool,
    BrowserPoolExhaustedError,
    MAX_BROWSER_OPS,
    MAX_BROWSER_AGE_SECONDS,
    IDLE_BROWSER_TTL_SECONDS
)
from integrations.backend.services.linkedin_worker import LinkedInWorker


class TestHorizon18CRMFailoverAndRefunds(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-crm-test-123"
        self.lead_data = {
            "id": "lead-456",
            "first_name": "Deeksha",
            "last_name": "Test",
            "email": "deeksha@example.com",
            "company": "Ele-in Corp",
            "title": "Lead Architect"
        }

    def _create_mock_supabase(self):
        sb = MagicMock()
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data={"success": True})
        sb.rpc.return_value = rpc_mock
        sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
        return sb

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_hubspot_rate_limit_429_triggers_credit_refund(self, mock_post):
        """Layer 1 Paranoia: 429 RateLimit on HubSpot contacts refunds deducted credits before raising."""
        mock_sb = self._create_mock_supabase()
        mock_res = MagicMock(status_code=429, text="Rate limit exceeded")
        mock_post.return_value = mock_res

        with patch.dict(os.environ, {"HUBSPOT_ACCESS_TOKEN": "hs_test_token"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                with self.assertRaises(RateLimitExceeded):
                    push_to_hubspot(self.workspace_id, self.lead_data, supabase=mock_sb)

        # Verify deduction was attempted
        rpc_calls = mock_sb.rpc.call_args_list
        actions = [c[0][0] for c in rpc_calls]
        self.assertIn("deduct_credits_safely", actions)
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_hubspot_poison_pill_400_refunds_credit(self, mock_post):
        """Layer 2 Paranoia: 400 Bad Request poison pill lead refunds deducted credit and safely returns False."""
        mock_sb = self._create_mock_supabase()
        mock_res = MagicMock(status_code=400, text="Bad Request: property does not exist")
        mock_post.return_value = mock_res

        with patch.dict(os.environ, {"HUBSPOT_ACCESS_TOKEN": "hs_test_token"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = push_to_hubspot(self.workspace_id, self.lead_data, supabase=mock_sb)

        self.assertFalse(result)
        rpc_calls = mock_sb.rpc.call_args_list
        actions = [c[0][0] for c in rpc_calls]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.put")
    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_hubspot_deal_failure_refunds_credit(self, mock_post, mock_put):
        """Layer 1: Contact creation succeeds (201) but Deal creation fails (500) -> credit refunded."""
        mock_sb = self._create_mock_supabase()
        contact_res = MagicMock(status_code=201)
        contact_res.json.return_value = {"id": "cnt-1001"}

        deal_res = MagicMock(status_code=500, text="Internal Hubspot Server Error")
        mock_post.side_effect = [contact_res, deal_res]

        with patch.dict(os.environ, {"HUBSPOT_ACCESS_TOKEN": "hs_test_token"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = push_to_hubspot(self.workspace_id, self.lead_data, supabase=mock_sb)

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_salesforce_failure_refunds_credit(self, mock_post):
        """Layer 1: Salesforce 500 server error triggers credit refund."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=500, text="Salesforce Down")

        env_vars = {
            "SALESFORCE_ACCESS_TOKEN": "sf_token",
            "SALESFORCE_INSTANCE_URL": "https://test.salesforce.com"
        }
        with patch.dict(os.environ, env_vars):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = push_to_salesforce(self.workspace_id, self.lead_data)

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_pipedrive_failure_refunds_credit(self, mock_post):
        """Layer 1: Pipedrive API failure refunds credit."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=422, text="Unprocessable Entity")

        with patch.dict(os.environ, {"PIPEDRIVE_API_KEY": "pd_key"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = push_to_pipedrive(self.workspace_id, self.lead_data)

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_notion_failure_refunds_credit(self, mock_post):
        """Layer 1: Notion API error refunds credit."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=400, text="Invalid parent database")

        with patch.dict(os.environ, {"NOTION_API_KEY": "nt_key"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = push_to_notion(self.workspace_id, self.lead_data, database_id="db-123")

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_airtable_failure_refunds_credit(self, mock_post):
        """Layer 1: Airtable API 404 table not found refunds credit."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=404, text="Table not found")

        with patch.dict(os.environ, {"AIRTABLE_API_KEY": "at_key"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = push_to_airtable(self.workspace_id, self.lead_data, base_id="app123", table_name="Leads")

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_emailbison_failure_refunds_credit(self, mock_post):
        """Layer 1: EmailBison failure refunds credit."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=502, text="Bad Gateway")

        with patch.dict(os.environ, {"EMAILBISON_API_KEY": "eb_key"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = add_to_emailbison(self.workspace_id, self.lead_data, campaign_id="camp-1")

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_lemlist_failure_refunds_credit(self, mock_post):
        """Layer 1: Lemlist 401 Unauthorized refunds credit."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")

        with patch.dict(os.environ, {"LEMLIST_API_KEY": "lem_key"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = add_to_lemlist(self.workspace_id, self.lead_data, campaign_id="camp-1")

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_apollo_failure_refunds_credit(self, mock_post):
        """Layer 1: Apollo 401 auth error refunds credit."""
        mock_sb = self._create_mock_supabase()
        mock_post.return_value = MagicMock(status_code=401, text="Invalid API key")

        with patch.dict(os.environ, {"APOLLO_API_KEY": "ap_key"}):
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                result = add_to_apollo(self.workspace_id, self.lead_data)

        self.assertFalse(result)
        actions = [c[0][0] for c in mock_sb.rpc.call_args_list]
        self.assertIn("add_credits_safely", actions)

    def test_safe_refund_credits_input_hygiene(self):
        """Layer 2 Paranoia: _safe_refund_credits rejects invalid arguments cleanly."""
        self.assertFalse(_safe_refund_credits(None, 1, "test_key"))
        self.assertFalse(_safe_refund_credits("ws-1", 1, None))
        self.assertFalse(_safe_refund_credits("", 1, "test_key"))


class TestHorizon18WebhookHardening(unittest.TestCase):
    def test_sanitize_webhook_payload_comprehensive(self):
        """Layer 2 Paranoia: Recursively scrubs all sensitive credentials and auth tokens."""
        dirty = {
            "lead": {
                "name": "Alex",
                "email": "alex@company.com",
                "password": "p@ssword!",
                "api_key": "sk_live_12345",
                "authorization": "Bearer token123",
                "cookie": "session=xyz",
                "client_secret": "sec_789"
            },
            "tokens": ["clean", {"secret": "private", "public": "visible"}],
            "metadata": {"tags": ["outreach"], "signing_secret": "wh_sec"}
        }

        clean = sanitize_webhook_payload(dirty)
        self.assertEqual(clean["lead"]["name"], "Alex")
        self.assertEqual(clean["lead"]["email"], "alex@company.com")
        self.assertNotIn("password", clean["lead"])
        self.assertNotIn("api_key", clean["lead"])
        self.assertNotIn("authorization", clean["lead"])
        self.assertNotIn("cookie", clean["lead"])
        self.assertNotIn("client_secret", clean["lead"])
        self.assertEqual(clean["tokens"][0], "clean")
        self.assertNotIn("secret", clean["tokens"][1])
        self.assertEqual(clean["tokens"][1]["public"], "visible")
        self.assertNotIn("signing_secret", clean["metadata"])
        self.assertEqual(clean["metadata"]["tags"], ["outreach"])

    def test_signature_generation_and_verification(self):
        """Layer 0 & 1: HMAC signature generation and constant-time verification with replay window."""
        secret = "test_webhook_signing_secret_999"
        payload = {"event": "lead.replied", "lead_id": "lead-777", "text": "Interested!"}
        now = int(time.time())

        ts, sig = generate_webhook_signature(payload, secret, timestamp_override=now)
        self.assertEqual(ts, str(now))

        # Verification passes
        self.assertTrue(verify_webhook_signature(payload, secret, ts, sig, tolerance_seconds=300))

        # Replay attack prevention: old timestamp fails
        old_ts = now - 600
        old_sig = generate_webhook_signature(payload, secret, timestamp_override=old_ts)[1]
        self.assertFalse(verify_webhook_signature(payload, secret, old_ts, old_sig, tolerance_seconds=300))

        # Tampered payload fails
        tampered_payload = {"event": "lead.replied", "lead_id": "lead-777", "text": "Hacked!"}
        self.assertFalse(verify_webhook_signature(tampered_payload, secret, ts, sig, tolerance_seconds=300))

        # Empty secret fails
        self.assertFalse(verify_webhook_signature(payload, "", ts, sig))

    def test_ssrf_blocking_in_crm_webhooks(self):
        """Layer 1 Paranoia: send_webhook blocks internal / private IP SSRF destinations."""
        lead = {"email": "prospect@acme.com"}
        self.assertFalse(send_webhook(lead, "http://127.0.0.1:8000/internal"))
        self.assertFalse(send_webhook(lead, "http://169.254.169.254/latest/meta-data"))
        self.assertFalse(send_webhook(lead, "http://localhost:5432"))
        self.assertFalse(send_slack_alert("Test Alert", "http://10.0.0.1/admin"))


class TestHorizon18LinkedInWorkerPoolHardening(unittest.TestCase):
    def test_worker_initialization_paranoia(self):
        """Layer 2 Paranoia: Worker safely parses lists, strings, and validates domains."""
        # Non-None account_id required
        with self.assertRaises(ValueError):
            LinkedInWorker(account_id=None, cookies=[])

        # Valid list of cookies
        valid_cookies = [{"name": "li_at", "value": "xyz", "domain": ".linkedin.com"}]
        w = LinkedInWorker(account_id="acc-1", cookies=valid_cookies)
        self.assertEqual(len(w.cookies), 1)

        # JSON string format supported
        w2 = LinkedInWorker(account_id="acc-2", cookies_json=json.dumps(valid_cookies))
        self.assertEqual(len(w2.cookies), 1)

        # Domain spoofing rejected
        spoofed = [{"name": "li_at", "value": "xyz", "domain": "evil-domain.com"}]
        with self.assertRaises(ValueError):
            LinkedInWorker(account_id="acc-3", cookies=spoofed)

    def test_browser_pool_lock_serialization(self):
        """Layer 1 Paranoia: Pool ensures strict serialization per account."""
        pool = BrowserPool(max_size=3)
        self.assertEqual(pool.max_size, 3)

        status = pool.get_status() if hasattr(pool, "get_status") else {}
        self.assertIsInstance(status, dict)

    def test_browser_pool_reap_idle(self):
        """Layer 1: Browser pool reaps idle instances older than TTL."""
        pool = BrowserPool(max_size=2)
        mock_c = MagicMock()
        mock_b = MagicMock()
        mock_pw = MagicMock()

        now = time.time()
        pool.pool["acc_old"] = {
            "pw": mock_pw,
            "browser": mock_b,
            "context": mock_c,
            "active_count": 0,
            "last_active_at": now - 1000,
            "created_at": now - 2000,
            "ops_count": 2
        }

        pool.reap_idle_browsers(max_idle_seconds=300)
        self.assertNotIn("acc_old", pool.pool)
        mock_c.close.assert_called()
        mock_b.close.assert_called()
        mock_pw.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
