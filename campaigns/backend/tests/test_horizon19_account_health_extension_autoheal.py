import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import base64
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from accounts.backend.services.account_health_service import (
    check_session_validity,
    check_cookie_freshness,
    check_profile_reachable,
    check_for_restriction_signals,
    run_health_check,
    compute_safety_indicator,
    get_next_check_interval
)
from accounts.backend.services.account_auto_heal_service import (
    auto_heal_account,
    fleet_auto_heal,
    get_fleet_health_summary,
    renew_account_session,
    calculate_composite_health_score,
    probe_proxy_health
)
from integrations.backend.routers.hubspot import (
    get_hubspot_lists,
    import_hubspot_list,
    get_hubspot_pipelines,
    set_hubspot_won_stage,
    disconnect_hubspot,
    HubspotWonStage
)
from integrations.backend.routers.extension import (
    sync_cookies,
    extension_heartbeat,
    get_extension_tasks,
    report_task_result,
    ExtensionSyncPayload
)
from core.backend.services.credit_service import TIER_LIMITS


class TestHorizon19AccountHealthDiagnostics(unittest.TestCase):
    """
    Test suite for Horizon 19: Account Health Diagnostics,
    Worker Instantiation, and Resilience under the Three-Layer Architecture.
    """

    def setUp(self):
        self.account_id = "acc_diag_101"
        self.workspace_id = "ws_diag_202"
        self.cookies_json = json.dumps([{"name": "li_at", "value": "AQED_TEST_COOKIE_VAL"}])

    @patch("accounts.backend.services.account_health_service.LinkedInWorker")
    def test_check_session_validity_instantiates_worker_with_account_id(self, mock_worker_cls):
        """Layer 0: Passes account_id to LinkedInWorker and parses 200/401/999 status codes correctly."""
        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200)
        mock_worker_cls.return_value = mock_worker

        res_200 = check_session_validity(self.account_id, self.cookies_json)
        self.assertEqual(res_200["result"], "pass")
        self.assertEqual(res_200["check_type"], "session_valid")
        mock_worker_cls.assert_called_with(cookies_json=self.cookies_json, account_id=self.account_id)

        # 401 Session expired
        mock_worker._http_get.return_value = MagicMock(status_code=401)
        res_401 = check_session_validity(self.account_id, self.cookies_json)
        self.assertEqual(res_401["result"], "fail")
        self.assertIn("expired", res_401["detail"]["message"].lower())

        # 999 Bot detection
        mock_worker._http_get.return_value = MagicMock(status_code=999)
        res_999 = check_session_validity(self.account_id, self.cookies_json)
        self.assertEqual(res_999["result"], "fail")
        self.assertIn("999", res_999["detail"]["message"])

    @patch("accounts.backend.services.account_health_service.LinkedInWorker")
    def test_check_profile_reachable_passes_account_id_and_detects_restriction(self, mock_worker_cls):
        """Layer 0 & 1: Profile reachability passes account_id and catches challenge interstitial."""
        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(
            status_code=200,
            text="<html><body>checkpoint/challenge detected</body></html>"
        )
        mock_worker_cls.return_value = mock_worker

        res = check_profile_reachable(
            self.cookies_json,
            "https://www.linkedin.com/in/test-prospect",
            account_id=self.account_id
        )
        self.assertEqual(res["result"], "fail")
        self.assertIn("Restriction", res["detail"]["message"])
        mock_worker_cls.assert_called_with(cookies_json=self.cookies_json, account_id=self.account_id)

    @patch("accounts.backend.services.account_health_service.LinkedInWorker")
    def test_check_for_restriction_signals_passes_account_id(self, mock_worker_cls):
        """Layer 0: Feed restriction detection passes account_id to worker."""
        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200, text="<html><body>Normal feed</body></html>")
        mock_worker_cls.return_value = mock_worker

        res = check_for_restriction_signals(self.cookies_json, account_id=self.account_id)
        self.assertEqual(res["result"], "pass")
        mock_worker_cls.assert_called_with(cookies_json=self.cookies_json, account_id=self.account_id)

    def test_check_cookie_freshness_boundary_conditions(self):
        """Layer 2: Cookie freshness handles missing expiry, imminent expiry (<7 days), and expired cookies."""
        now = datetime.now(timezone.utc)

        # Missing expiry
        res_none = check_cookie_freshness({})
        self.assertEqual(res_none["result"], "warn")

        # Expired
        expired_iso = (now - timedelta(days=1)).isoformat()
        res_exp = check_cookie_freshness({"cookie_expires_at": expired_iso})
        self.assertEqual(res_exp["result"], "fail")

        # Imminent (<7 days)
        soon_iso = (now + timedelta(days=3)).isoformat()
        res_soon = check_cookie_freshness({"cookie_expires_at": soon_iso})
        self.assertEqual(res_soon["result"], "warn")

        # Fresh (>7 days)
        fresh_iso = (now + timedelta(days=30)).isoformat()
        res_fresh = check_cookie_freshness({"cookie_expires_at": fresh_iso})
        self.assertEqual(res_fresh["result"], "pass")

    @patch("accounts.backend.services.account_health_service.crypto")
    @patch("accounts.backend.services.account_health_service.check_session_validity")
    @patch("accounts.backend.services.account_health_service.check_profile_reachable")
    @patch("accounts.backend.services.account_health_service.check_for_restriction_signals")
    def test_run_health_check_full_pipeline_success(
        self,
        mock_restr,
        mock_reach,
        mock_valid,
        mock_crypto
    ):
        """Layer 0: Full health check executes without crashing, passing account_id everywhere."""
        mock_supabase = MagicMock()
        mock_acc_res = MagicMock()
        mock_acc_res.data = [{
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "status": "ACTIVE",
            "session_cookies_encrypted": "deadbeef",
            "cookie_secret_ref": "vault-ref-1",
            "linkedin_profile_url": "https://www.linkedin.com/in/me"
        }]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res

        # Mock DEK RPC
        mock_rpc = MagicMock()
        mock_rpc.data = {"dek": base64.b64encode(b"0" * 32).decode("utf-8")}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc

        mock_crypto.pg_hex_to_bytes.return_value = b"decrypted_raw"
        mock_crypto.decrypt_bytes.return_value = self.cookies_json.encode("utf-8")

        mock_valid.return_value = {"check_type": "session_valid", "result": "pass"}
        mock_reach.return_value = {"check_type": "profile_reachable", "result": "pass"}
        mock_restr.return_value = {"check_type": "restriction_signals", "result": "pass"}

        result = run_health_check(mock_supabase, self.account_id, self.workspace_id)
        self.assertEqual(result["account_id"], self.account_id)
        self.assertEqual(result["new_status"], "ACTIVE")
        mock_valid.assert_called_with(self.account_id, self.cookies_json)
        mock_reach.assert_called_with(self.cookies_json, "https://www.linkedin.com/in/me", account_id=self.account_id)
        mock_restr.assert_called_with(self.cookies_json, account_id=self.account_id)

    def test_compute_safety_indicator_logic(self):
        """Layer 2: Evaluates risk level indicator dynamically from status and history."""
        self.assertEqual(compute_safety_indicator({"manual_send_suspected": True}, []), "critical")
        self.assertEqual(compute_safety_indicator({"status": "SUSPENDED"}, []), "critical")
        self.assertEqual(compute_safety_indicator({"status": "NEEDS_ATTENTION"}, []), "warning")
        self.assertEqual(compute_safety_indicator({"status": "ACTIVE"}, [{"result": "fail"}]), "warning")
        self.assertEqual(compute_safety_indicator({"status": "ACTIVE"}, [{"result": "pass"}]), "healthy")


class TestHorizon19AutoHealingSecurity(unittest.TestCase):
    """
    Test suite for Autonomous Multi-Account Proxy & Cookie Auto-Healing Engine.
    """

    def setUp(self):
        self.account_id = "acc_heal_101"
        self.workspace_id = "ws_heal_202"
        self.supabase = MagicMock()

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_auto_heal_account_passes_account_id_and_restores_active(self, mock_crypto, mock_worker_cls):
        """Layer 0: auto_heal_account passes account_id to LinkedInWorker and restores ACTIVE status."""
        mock_acc_res = MagicMock(data=[{
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "status": "DISCONNECTED",
            "session_cookies_encrypted": "deadbeef",
            "proxy_id": None
        }])
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res

        mock_crypto.pg_hex_to_bytes.return_value = b"raw"
        mock_crypto.decrypt_bytes.return_value = json.dumps([{"name": "li_at", "value": "xyz"}]).encode("utf-8")

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200)
        mock_worker_cls.return_value = mock_worker

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertTrue(res["healed"])
        self.assertEqual(res["new_status"], "ACTIVE")
        mock_worker_cls.assert_called_with(
            cookies_json=json.dumps([{"name": "li_at", "value": "xyz"}]),
            proxy_url=None,
            account_id=self.account_id
        )

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_renew_account_session_passes_account_id_and_stores_dek(self, mock_crypto, mock_worker_cls):
        """Layer 0 & 2: renew_account_session validates against Voyager with account_id and generates Vault DEK."""
        mock_acc_res = MagicMock(data=[{"id": self.account_id, "workspace_id": self.workspace_id, "proxy_id": None}])
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200)
        mock_worker_cls.return_value = mock_worker

        mock_crypto.generate_dek.return_value = base64.b64encode(b"1" * 32).decode("utf-8")
        mock_crypto.encrypt_bytes.return_value = b"encrypted_cookie_data"
        mock_crypto.bytes_to_pg_hex.return_value = "hex_cookies"

        self.supabase.rpc.return_value.execute.return_value = MagicMock(data="secret_ref_xyz")

        raw_json = json.dumps([{"name": "li_at", "value": "new_secret_val", "expires": 1893456000}])
        res = renew_account_session(self.account_id, self.workspace_id, raw_json, self.supabase)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "ACTIVE")
        mock_worker_cls.assert_called_with(cookies_json=raw_json, account_id=self.account_id)

    def test_calculate_composite_health_score(self):
        """Layer 1: Calculates deterministic composite score from session, proxy, cookies, and status."""
        # Perfect health: session=True(40), proxy < 250ms(30), cookie > 14 days(20), ACTIVE(10) -> 100
        future_iso = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        score_100 = calculate_composite_health_score(
            session_valid=True,
            proxy_latency_ms=120,
            cookie_expires_at_str=future_iso,
            status="ACTIVE"
        )
        self.assertEqual(score_100, 100)

        # Degraded health: session=False(0), direct connection(15), expired cookie(3), DISCONNECTED(0) -> 18
        past_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        score_low = calculate_composite_health_score(
            session_valid=False,
            proxy_latency_ms=None,
            cookie_expires_at_str=past_iso,
            status="DISCONNECTED"
        )
        self.assertTrue(0 <= score_low <= 25)


class TestHorizon19HubSpotCRMTierEnforcement(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for HubSpot CRM Router Tier Enforcement & Security Hardening.
    """

    def setUp(self):
        self.workspace_id = "ws_hubspot_test"
        self.supabase = MagicMock()

    async def test_import_hubspot_list_free_tier_rejected(self):
        """Layer 1: Free tier workspaces cannot trigger HubSpot list imports (HTTP 403)."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws

        with self.assertRaises(HTTPException) as ctx:
            await import_hubspot_list(101, self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Growth Pro", ctx.exception.detail)

    async def test_import_hubspot_list_invalid_list_id_rejected(self):
        """Layer 2: Negative or zero list_id is rejected with HTTP 400 before DB queries."""
        with self.assertRaises(HTTPException) as ctx:
            await import_hubspot_list(-5, self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("positive integer", ctx.exception.detail)

    async def test_get_hubspot_pipelines_free_tier_rejected(self):
        """Layer 1: Free tier workspaces cannot fetch CRM pipelines (HTTP 403)."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws

        with self.assertRaises(HTTPException) as ctx:
            await get_hubspot_pipelines(self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Growth Pro", ctx.exception.detail)

    async def test_set_hubspot_won_stage_free_tier_rejected(self):
        """Layer 1: Free tier workspaces cannot configure CRM won-stage (HTTP 403)."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws

        data = HubspotWonStage(stage_id="closedwon")
        with self.assertRaises(HTTPException) as ctx:
            await set_hubspot_won_stage(data, self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Growth Pro", ctx.exception.detail)

    async def test_get_hubspot_lists_uses_stored_token_only(self):
        """Layer 2: get_hubspot_lists loads token strictly from DB, rejecting if not connected."""
        # Tier allows sync (PRO), but no token in DB
        mock_ws_tier = MagicMock(data=[{"tier": "PRO"}])
        mock_ws_token = MagicMock(data=[{"hubspot_token": None}])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws_tier,
            mock_ws_token
        ]

        with self.assertRaises(HTTPException) as ctx:
            await get_hubspot_lists(self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("not connected", ctx.exception.detail.lower())

    async def test_disconnect_hubspot_clears_tokens(self):
        """Layer 0: disconnect_hubspot zeroes out hubspot_token and hubspot_won_stage_id."""
        mock_upd = MagicMock(data=[{"id": self.workspace_id}])
        self.supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_upd

        res = await disconnect_hubspot(self.workspace_id, self.supabase)
        self.assertEqual(res["status"], "ok")
        self.supabase.table("workspaces").update.assert_called_with({
            "hubspot_token": None,
            "hubspot_won_stage_id": None
        })


class TestHorizon19ExtensionBridgeHardening(unittest.TestCase):
    """
    Test suite for Chrome Extension Cookie Sync Tier Limits and Task Isolation.
    """

    def setUp(self):
        self.workspace_id = "ws_ext_test"
        self.supabase = MagicMock()
        self.valid_cookies = json.dumps([
            {"name": "li_at", "value": "AQED_TEST", "expires": 1893456000}
        ])

    @patch("integrations.backend.routers.extension.crypto")
    def test_sync_cookies_enforces_tier_limit_on_new_account(self, mock_crypto):
        """Layer 1: FREE tier workspace cannot exceed max_linkedin_accounts (1 account)."""
        mock_crypto.encrypt_bytes.return_value = b"enc"
        mock_crypto.bytes_to_pg_hex.return_value = "hex"

        def mock_table(table_name):
            tbl = MagicMock()
            if table_name == "accounts":
                # For disconnected check
                disc_mock = MagicMock(data=[])
                tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = disc_mock
                # For count check
                count_mock = MagicMock(count=1)
                tbl.select.return_value.eq.return_value.execute.return_value = count_mock
            elif table_name == "workspaces":
                ws_mock = MagicMock(data=[{"tier": "FREE"}])
                tbl.select.return_value.eq.return_value.execute.return_value = ws_mock
            return tbl

        self.supabase.table.side_effect = mock_table

        payload = ExtensionSyncPayload(
            account_id=None,
            account_name="Second Account",
            cookies_json=self.valid_cookies
        )

        with self.assertRaises(HTTPException) as ctx:
            sync_cookies(payload, self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("limit reached", ctx.exception.detail.lower())

    def test_extension_heartbeat_rejects_foreign_account_id(self):
        """Layer 2: Rejects heartbeat for account belonging to another workspace (HTTP 403)."""
        # Account not found in this workspace
        mock_acc = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc

        with self.assertRaises(HTTPException) as ctx:
            extension_heartbeat({"account_id": "foreign_acc"}, self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("does not belong to your workspace", ctx.exception.detail)

    def test_get_extension_tasks_rejects_foreign_account_id(self):
        """Layer 2: Rejects task polling for account belonging to another workspace (HTTP 403)."""
        mock_acc = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc

        with self.assertRaises(HTTPException) as ctx:
            get_extension_tasks("foreign_acc", self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("does not belong to your workspace", ctx.exception.detail)

    def test_report_task_result_rejects_foreign_task_id(self):
        """Layer 2: Rejects task result reporting for task belonging to another workspace (HTTP 403)."""
        mock_task = MagicMock(data=[{"workspace_id": "other_workspace"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_task

        with self.assertRaises(HTTPException) as ctx:
            report_task_result("task_123", {"status": "success"}, self.workspace_id, self.supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("does not belong to your workspace", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
