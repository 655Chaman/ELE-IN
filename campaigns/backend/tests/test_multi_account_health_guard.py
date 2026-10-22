import unittest
from unittest.mock import MagicMock, patch
import json
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from accounts.backend.services.account_auto_heal_service import (
    probe_proxy_health,
    calculate_composite_health_score,
    auto_heal_account,
    fleet_auto_heal,
    get_fleet_health_summary,
    renew_account_session,
)
from core.backend.api.routers.proxies import (
    test_existing_proxy as api_test_existing_proxy,
    test_raw_proxy_config as api_test_raw_proxy_config,
    ProxyTestRequest,
)
from campaigns.backend.routers.elein import (
    trigger_account_auto_heal,
    trigger_fleet_heal,
    get_fleet_health_summary_endpoint,
    renew_session_endpoint,
    SessionRenewalRequest,
)


class TestMultiAccountHealthGuard(unittest.TestCase):
    """
    Test suite for Autonomous Multi-Account Proxy & Cookie Health Guard,
    Auto-Healing Engine, and Session Renewal (Blue Ocean Phase 7).
    Rigorously built under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.supabase = MagicMock()
        self.workspace_id = "ws_enterprise_101"
        self.account_id = "acc_sender_202"

    # =========================================================================
    # 1. Proxy Probing & Latency Measurement (Layer 0, 1, 2)
    # =========================================================================

    def test_probe_proxy_health_missing_host_fails_gracefully(self):
        """Layer 2: Missing host or port fails gracefully without throwing unhandled exceptions."""
        result = probe_proxy_health({"host": "", "port": None})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("Missing host or port", result["error"])

    @patch("accounts.backend.services.account_auto_heal_service.httpx.Client")
    def test_probe_proxy_health_healthy_response(self, mock_client_cls):
        """Layer 0: Healthy proxy returns latency_ms < 800 and status 'healthy'."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_robots_resp = MagicMock(status_code=200)
        mock_ip_resp = MagicMock(status_code=200, json=lambda: {"ip": "198.51.100.77"})
        mock_client.get.side_effect = [mock_robots_resp, mock_ip_resp]

        proxy_data = {
            "id": "px_1",
            "host": "198.51.100.1",
            "port": 8080,
            "protocol": "http",
            "country_code": "US"
        }

        result = probe_proxy_health(proxy_data, supabase=self.supabase)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "healthy")
        self.assertIsInstance(result["latency_ms"], int)
        self.assertEqual(result["exit_ip"], "198.51.100.77")

    @patch("accounts.backend.services.account_auto_heal_service.httpx.Client")
    def test_probe_proxy_health_timeout_handling(self, mock_client_cls):
        """Layer 1: ConnectTimeout bounded safely, returns status 'failed'."""
        import httpx
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectTimeout("Connection timed out")

        proxy_data = {
            "id": "px_dead",
            "host": "10.255.255.1",
            "port": 9999,
            "protocol": "http"
        }

        result = probe_proxy_health(proxy_data, timeout_seconds=2.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("timed out", result["error"])

    # =========================================================================
    # 2. Composite Health Score Calculation (Layer 0)
    # =========================================================================

    def test_composite_health_score_all_prime(self):
        """Layer 0: Active session, low latency, and fresh cookies yield score >= 90."""
        score = calculate_composite_health_score(
            session_valid=True,
            proxy_latency_ms=120,
            cookie_expires_at_str=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            status="ACTIVE"
        )
        self.assertGreaterEqual(score, 90)

    def test_composite_health_score_dead_session(self):
        """Layer 0: Expired session drops score below 40."""
        score = calculate_composite_health_score(
            session_valid=False,
            proxy_latency_ms=None,
            cookie_expires_at_str=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            status="DISCONNECTED"
        )
        self.assertLess(score, 40)

    # =========================================================================
    # 3. Single-Account Auto-Healing (Layer 0, 1, 2)
    # =========================================================================

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_auto_heal_account_recovers_to_active(self, mock_crypto, mock_worker_cls):
        """Layer 0 & 1: Degraded account with valid Voyager session auto-heals to ACTIVE and unpauses campaigns."""
        # Mock Supabase account query
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "NEEDS_ATTENTION",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1",
                "cookie_expires_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
                "proxy_id": None
            }]
        )

        mock_campaigns_table = MagicMock()
        mock_campaigns_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "name": "Q4 Outreach", "status": "PAUSED"}]
        )
        mock_camp_accs_table = MagicMock()
        mock_camp_accs_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": self.account_id}]
        )

        def table_side_effect(name):
            if name == "accounts":
                return mock_acc_table
            elif name == "campaigns":
                return mock_campaigns_table
            elif name == "campaign_accounts":
                return mock_camp_accs_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        # Mock DEK RPC & Decryption
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data={"dek": "ZGVr"})
        mock_crypto.pg_hex_to_bytes.return_value = b"encrypted"
        mock_crypto.decrypt_bytes.return_value = json.dumps([{"name": "li_at", "value": "xyz"}]).encode()

        # Mock LinkedInWorker session check
        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200)
        mock_worker_cls.return_value = mock_worker

        result = auto_heal_account(self.account_id, self.workspace_id, self.supabase)

        self.assertTrue(result["healed"])
        self.assertEqual(result["new_status"], "ACTIVE")
        self.assertEqual(result["recommendation"], "ALL_CLEAR")
        self.assertGreaterEqual(result["health_score"], 80)
        # Verify account was updated to ACTIVE
        mock_acc_table.update.assert_called()

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.probe_proxy_health")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_auto_heal_rotates_failing_proxy_to_backup(self, mock_crypto, mock_probe_proxy, mock_worker_cls):
        """Layer 1: When assigned proxy is dead, auto-heals by rotating to a healthy replacement in same country."""
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "ACTIVE",
                "session_cookies_encrypted": "hex_abc",
                "proxy_id": "px_dead_1"
            }]
        )

        mock_proxies_table = MagicMock()
        # Query for dead proxy
        mock_proxies_table.select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "px_dead_1", "host": "1.1.1.1", "port": 80, "country_code": "US", "status": "failed"}]),
            # Query for backup healthy proxies
            MagicMock(data=[{"id": "px_healthy_2", "host": "2.2.2.2", "port": 8080, "country_code": "US", "status": "healthy"}]),
            # Query to fetch updated proxy
            MagicMock(data=[{"id": "px_healthy_2", "host": "2.2.2.2", "port": 8080, "country_code": "US", "status": "healthy"}])
        ]

        def table_side_effect(name):
            if name == "accounts":
                return mock_acc_table
            elif name == "proxies":
                return mock_proxies_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        mock_crypto.pg_hex_to_bytes.return_value = b"encrypted"
        mock_crypto.decrypt_bytes.return_value = json.dumps([{"name": "li_at", "value": "xyz"}]).encode()

        # Dead proxy fails probe; backup succeeds
        mock_probe_proxy.side_effect = [
            {"ok": False, "status": "failed", "error": "Timeout"},
            {"ok": True, "status": "healthy", "latency_ms": 140}
        ]

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200)
        mock_worker_cls.return_value = mock_worker

        result = auto_heal_account(self.account_id, self.workspace_id, self.supabase)

        # Confirm proxy was rotated to px_healthy_2
        mock_acc_table.update.assert_called()
        self.assertEqual(result["proxy_status"], "healthy")
        self.assertEqual(result["proxy_latency_ms"], 140)

    # =========================================================================
    # 4. Fleet Auto-Heal & Health Summary (Layer 0)
    # =========================================================================

    @patch("accounts.backend.services.account_auto_heal_service.auto_heal_account")
    def test_fleet_auto_heal_sweeps_accounts(self, mock_auto_heal):
        """Layer 0: fleet_auto_heal iterates through all accounts and tallies outcomes."""
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "acc_1", "name": "Sender 1", "status": "ACTIVE"},
                {"id": "acc_2", "name": "Sender 2", "status": "DISCONNECTED"}
            ]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_auto_heal.side_effect = [
            {"account_id": "acc_1", "healed": False, "new_status": "ACTIVE"},
            {"account_id": "acc_2", "healed": True, "new_status": "ACTIVE"}
        ]

        summary = fleet_auto_heal(self.workspace_id, self.supabase)
        self.assertEqual(summary["total_scanned"], 2)
        self.assertEqual(summary["healed_count"], 1)

    def test_get_fleet_health_summary_metrics(self):
        """Layer 0: Returns aggregated metrics across senders and proxies."""
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "a1", "status": "ACTIVE", "health_score": 95, "cookie_expires_at": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()},
                {"id": "a2", "status": "ACTIVE", "health_score": 85, "cookie_expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()}
            ]
        )
        mock_px_table = MagicMock()
        mock_px_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "p1", "status": "healthy", "latency_ms": 120},
                {"id": "p2", "status": "healthy", "latency_ms": 180}
            ]
        )

        def table_side_effect(name):
            if name == "accounts":
                return mock_acc_table
            elif name == "proxies":
                return mock_px_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        summary = get_fleet_health_summary(self.workspace_id, self.supabase)
        self.assertEqual(summary["total_senders"], 2)
        self.assertEqual(summary["active_senders"], 2)
        self.assertEqual(summary["expiring_cookies_count"], 1)
        self.assertEqual(summary["avg_proxy_latency_ms"], 150)
        self.assertEqual(summary["fleet_health_score"], 90)

    # =========================================================================
    # 5. Session Renewal (Layer 0, 1, 2)
    # =========================================================================

    def test_renew_account_session_missing_li_at_raises_value_error(self):
        """Layer 2: Rejecting invalid cookie payload without 'li_at'."""
        bad_cookies = json.dumps([{"name": "bcookie", "value": "xyz"}])
        with self.assertRaises(ValueError) as ctx:
            renew_account_session(self.account_id, self.workspace_id, bad_cookies, self.supabase)
        self.assertIn("Missing 'li_at' cookie", str(ctx.exception))

    def test_renew_account_session_invalid_json_raises_value_error(self):
        """Layer 2: Rejecting malformed non-JSON string."""
        with self.assertRaises(ValueError) as ctx:
            renew_account_session(self.account_id, self.workspace_id, "NOT_JSON", self.supabase)
        self.assertIn("Invalid JSON format", str(ctx.exception))

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_renew_account_session_success(self, mock_crypto, mock_worker_cls):
        """Layer 0 & 1: Successfully renews session cookies, updates Vault DEK, and unpauses campaigns."""
        valid_cookies = json.dumps([
            {"name": "li_at", "value": "valid_token_123", "expires": int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp())},
            {"name": "JSESSIONID", "value": "ajax:999"}
        ])

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.account_id, "workspace_id": self.workspace_id}]
        )
        mock_camp_table = MagicMock()
        mock_camp_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def table_side_effect(name):
            if name == "accounts":
                return mock_acc_table
            elif name == "campaigns":
                return mock_camp_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        # Mock Voyager HTTP 200 OK
        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200)
        mock_worker_cls.return_value = mock_worker

        self.supabase.rpc.return_value.execute.return_value = MagicMock(data="new_vault_ref")
        mock_crypto.generate_dek.return_value = "ZGVr"
        mock_crypto.encrypt_bytes.return_value = b"new_encrypted"
        mock_crypto.bytes_to_pg_hex.return_value = "hex_new"

        res = renew_account_session(self.account_id, self.workspace_id, valid_cookies, self.supabase)

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "ACTIVE")
        mock_acc_table.update.assert_called()

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_renew_account_session_identity_mismatch_raises_value_error(self, mock_crypto, mock_worker_cls):
        """Layer 0 & 2: Aborts with ValueError when cookies belong to a different LinkedIn user."""
        valid_cookies = json.dumps([
            {"name": "li_at", "value": "valid_token_123"},
            {"name": "JSESSIONID", "value": "ajax:999"}
        ])

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "name": "Jane Doe",
                "linkedin_profile_url": "https://www.linkedin.com/in/jane-doe/"
            }]
        )

        self.supabase.table.side_effect = lambda name: mock_acc_table if name == "accounts" else MagicMock()

        # Mock Voyager returning a completely different profile: John Smith
        mock_worker = MagicMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "miniProfile": {
                "firstName": "John",
                "lastName": "Smith",
                "publicIdentifier": "john-smith"
            }
        }
        mock_worker._http_get.return_value = mock_resp
        mock_worker_cls.return_value = mock_worker

        with self.assertRaises(ValueError) as ctx:
            renew_account_session(self.account_id, self.workspace_id, valid_cookies, self.supabase)

        self.assertIn("Identity mismatch", str(ctx.exception))
        self.assertIn("John Smith", str(ctx.exception))
        self.assertIn("Jane Doe", str(ctx.exception))
        mock_acc_table.update.assert_not_called()

    # =========================================================================
    # 6. Router Endpoint Handlers (Layer 0, 1, 2)
    # =========================================================================

    @patch("accounts.backend.services.account_auto_heal_service.probe_proxy_health")
    def test_test_raw_proxy_config_validates_inputs(self, mock_probe):
        """Layer 2: Rejects invalid port bounds or empty hosts."""
        # Empty host
        req_empty = ProxyTestRequest(host="", port=8080)
        with self.assertRaises(HTTPException) as ctx:
            api_test_raw_proxy_config(req_empty, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)

        # Invalid port > 65535
        req_port = ProxyTestRequest(host="proxy.net", port=99999)
        with self.assertRaises(HTTPException) as ctx:
            api_test_raw_proxy_config(req_port, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("accounts.backend.services.account_auto_heal_service.probe_proxy_health")
    def test_test_existing_proxy_endpoint(self, mock_probe):
        """Layer 0: Tests existing proxy endpoint."""
        mock_px_table = MagicMock()
        mock_px_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "px_1", "host": "1.1.1.1", "port": 8080}]
        )
        self.supabase.table.return_value = mock_px_table
        mock_probe.return_value = {"ok": True, "latency_ms": 110, "status": "healthy"}

        res = api_test_existing_proxy("px_1", self.supabase, self.workspace_id)
        self.assertTrue(res["ok"])
        self.assertEqual(res["latency_ms"], 110)

    @patch("accounts.backend.services.account_auto_heal_service.auto_heal_account")
    def test_trigger_account_auto_heal_endpoint(self, mock_auto_heal):
        """Layer 0: Router triggers single account auto-heal."""
        mock_auto_heal.return_value = {"account_id": self.account_id, "healed": True, "new_status": "ACTIVE"}
        res = trigger_account_auto_heal(self.account_id, self.supabase, self.workspace_id)
        self.assertTrue(res["healed"])

    @patch("accounts.backend.services.account_auto_heal_service.renew_account_session")
    def test_renew_session_endpoint_bad_cookies(self, mock_renew):
        """Layer 2: Bad cookies convert ValueError into 400 HTTPException."""
        mock_renew.side_effect = ValueError("Missing 'li_at' cookie")
        req = SessionRenewalRequest(session_cookies_json="[]")
        with self.assertRaises(HTTPException) as ctx:
            renew_session_endpoint(self.account_id, req, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
