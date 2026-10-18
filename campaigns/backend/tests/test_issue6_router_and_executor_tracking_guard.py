"""
test_issue6_router_and_executor_tracking_guard.py — Router, Probing, Cache & Executor SSL Guard Tests
Rigorous Three-Layer Logic Architecture tests for Issue 6:
  - Layer 0: POST verify-tracking-domain, GET tracking-domain-status, and EleInNodeExecutor link rewriting.
  - Layer 1: Environmental Failure Analysis (unverified SSL bypass, cache miss lightweight probe, non-fatal DB fallback).
  - Layer 2: Human Paranoia & Security Defense (SSRF protection, cross-tenant IDOR workspace boundaries).
"""

import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from campaigns.backend.routers.elein import VerifyTrackingDomainRequest
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestIssue6RouterAndExecutorTrackingGuard(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-issue6-router"
        self.mock_supabase = MagicMock()

    # =========================================================================
    # LAYER 0: FOUNDATIONAL TESTS
    # =========================================================================

    def test_layer0_verify_tracking_domain_request_model(self):
        """Layer 0: Pydantic model validates required fields and default values."""
        req = VerifyTrackingDomainRequest(tracking_domain="track.acmecorp.com")
        self.assertEqual(req.tracking_domain, "track.acmecorp.com")
        self.assertEqual(req.expected_cname, "track.elein.ai")
        self.assertTrue(req.check_live_ssl)

    @patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain")
    def test_layer0_post_verify_tracking_domain_endpoint_success_and_inbox_sync(self, mock_verify):
        """Layer 0: POST /deliverability/verify-tracking-domain verifies SSL and syncs matching inboxes."""
        mock_verify.return_value = {
            "valid": True,
            "status": "VERIFIED_ACTIVE",
            "cname_target": "track.elein.ai",
            "ssl_verified": True,
            "can_track_safely": True,
            "ssl_details": {
                "ssl_valid": True,
                "days_until_expiry": 85,
                "expires_at": "2026-12-31T00:00:00+00:00",
                "san_list": ["track.acmecorp.com"],
            },
        }

        # Mock supabase inboxes query and update
        mock_inboxes_data = [
            {
                "id": "inb-acme-1",
                "email": "sarah@acmecorp.com",
                "sender_domain": "acmecorp.com",
                "tracking_domain": None,
                "ssl_verified": False,
            },
            {
                "id": "inb-other-2",
                "email": "mark@anothercorp.com",
                "sender_domain": "anothercorp.com",
                "tracking_domain": None,
                "ssl_verified": False,
            },
        ]
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value.data = mock_inboxes_data
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/verify-tracking-domain",
                json={"tracking_domain": "track.acmecorp.com"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["tracking_domain"], "track.acmecorp.com")
            self.assertTrue(data["valid"])
            self.assertEqual(data["status"], "VERIFIED_ACTIVE")
            self.assertTrue(data["can_track_safely"])
            self.assertTrue(data["ssl_verified"])
            self.assertEqual(data["cname_target"], "track.elein.ai")
            self.assertEqual(data["inboxes_updated"], 1)

            # Assert matching inbox was updated with tracking domain and ssl_verified
            mock_table.update.assert_called_with({
                "tracking_domain": "track.acmecorp.com",
                "ssl_verified": True,
            })
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_layer0_get_tracking_domain_status_from_cache(self):
        """Layer 0: GET /deliverability/tracking-domain-status retrieves cached verified status."""
        mock_inboxes_data = [
            {
                "id": "inb-acme-1",
                "email": "alex@acmecorp.com",
                "sender_domain": "acmecorp.com",
                "tracking_domain": "track.acmecorp.com",
                "ssl_verified": True,
            }
        ]
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value.data = mock_inboxes_data
        self.mock_supabase.table.return_value = mock_table

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase
        try:
            client = TestClient(app)
            response = client.get(
                "/api/elein/deliverability/tracking-domain-status",
                params={"domain": "acmecorp.com"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["domain"], "acmecorp.com")
            self.assertEqual(data["tracking_domain"], "track.acmecorp.com")
            self.assertTrue(data["cached"])
            self.assertTrue(data["valid"])
            self.assertTrue(data["ssl_verified"])
            self.assertTrue(data["can_track_safely"])
            self.assertEqual(data["status"], "VERIFIED_ACTIVE")
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_layer0_executor_handle_send_email_ssl_verified_rewrites_links(self):
        """Layer 0: When ssl_verified=True, executor rewrites links and records tracking_rewritten."""
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}
        executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
        )
        node_data = {
            "_lead_id": "lead-ssl-1",
            "to": "cto@target.io",
            "subject": "Platform update",
            "body": "Read more at https://acmecorp.com/blog and schedule at https://cal.com/acme/demo.",
            "tracking_domain": "track.acmecorp.com",
            "ssl_verified": True,
        }
        res = executor.handle_send_email(node_data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res["tracking_rewritten"], 2)
        self.assertNotIn("ssl_tracking_bypassed", res)
        self.assertIn("https://track.acmecorp.com/t/c/", res["body"])

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS TESTS
    # =========================================================================

    def test_layer1_executor_ssl_unverified_bypasses_link_rewriting_and_emits_telemetry(self):
        """Layer 1: Unverified SSL logs warning, sets tracking_rewritten=0, and sets ssl_tracking_bypassed=True."""
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}
        executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
        )
        original_body = "Sign up now at https://acmecorp.com/join."
        node_data = {
            "_lead_id": "lead-ssl-unverified",
            "to": "vp@target.io",
            "subject": "Exclusive Beta",
            "body": original_body,
            "tracking_domain": "track.unverified-ssl.com",
            "ssl_verified": False,
        }
        with self.assertLogs("campaigns.backend.services.elein_executor", level="INFO") as log_capture:
            res = executor.handle_send_email(node_data, linkedin_url=None)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res["tracking_rewritten"], 0)
        self.assertTrue(res.get("ssl_tracking_bypassed"))
        # Body links MUST remain untouched
        self.assertEqual(res["body"], original_body)
        self.assertNotIn("track.unverified-ssl.com/t/c/", res["body"])

        # Check log message
        found_log = any("has unverified SSL. Bypassing tracking link rewrite" in msg for msg in log_capture.output)
        self.assertTrue(found_log, f"Expected warning log not found in: {log_capture.output}")

    @patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain")
    def test_layer1_post_verify_tracking_domain_ssl_pending_provisioning(self, mock_verify):
        """Layer 1: CNAME matches but SSL is pending returns valid=False and SSL_PENDING_PROVISIONING."""
        mock_verify.return_value = {
            "valid": False,
            "status": "SSL_PENDING_PROVISIONING",
            "cname_target": "track.elein.ai",
            "ssl_verified": False,
            "can_track_safely": False,
            "ssl_error": "Connection timed out",
            "action_required": "CNAME is configured, but SSL certificate is still provisioning or invalid.",
        }

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/verify-tracking-domain",
                json={"tracking_domain": "track.pending-acme.com"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["valid"])
            self.assertEqual(data["status"], "SSL_PENDING_PROVISIONING")
            self.assertFalse(data["can_track_safely"])
            self.assertFalse(data["ssl_verified"])
            self.assertEqual(data["inboxes_updated"], 0)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    @patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain")
    def test_layer1_get_tracking_domain_status_cache_miss_runs_live_check(self, mock_verify):
        """Layer 1: Cache miss triggers lightweight live DNS/SSL check."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value.data = []
        self.mock_supabase.table.return_value = mock_table

        mock_verify.return_value = {
            "valid": True,
            "status": "VERIFIED_ACTIVE",
            "cname_target": "track.elein.ai",
            "ssl_verified": True,
            "can_track_safely": True,
        }

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase
        try:
            client = TestClient(app)
            response = client.get(
                "/api/elein/deliverability/tracking-domain-status",
                params={"domain": "track.freshbrand.io"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data["cached"])
            self.assertTrue(data["valid"])
            self.assertEqual(data["status"], "VERIFIED_ACTIVE")
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & SECURITY DEFENSE TESTS
    # =========================================================================

    def test_layer2_ssrf_and_localhost_rejection_on_endpoints(self):
        """Layer 2: Reject localhost, 127.0.0.1, AWS metadata IP, and invalid schemes."""
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase
        try:
            client = TestClient(app)
            for malicious in ["http://127.0.0.1/admin", "169.254.169.254", "localhost", ":::1"]:
                res_post = client.post(
                    "/api/elein/deliverability/verify-tracking-domain",
                    json={"tracking_domain": malicious},
                )
                self.assertEqual(res_post.status_code, 200)
                data_post = res_post.json()
                self.assertFalse(data_post["valid"])
                self.assertEqual(data_post["status"], "FORBIDDEN_OR_INVALID_HOST")

                res_get = client.get(
                    "/api/elein/deliverability/tracking-domain-status",
                    params={"domain": malicious},
                )
                self.assertEqual(res_get.status_code, 200)
                data_get = res_get.json()
                self.assertFalse(data_get["valid"])
                self.assertEqual(data_get["status"], "FORBIDDEN_OR_INVALID_HOST")
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    @patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain")
    def test_layer2_cross_tenant_idor_inbox_update_protection(self, mock_verify):
        """Layer 2: Inbox updates strictly scoped to current workspace_id; other tenants cannot be updated."""
        mock_verify.return_value = {
            "valid": True,
            "status": "VERIFIED_ACTIVE",
            "cname_target": "track.elein.ai",
            "ssl_verified": True,
            "can_track_safely": True,
        }

        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "inb-tenant1-1",
                "email": "user@tenant1.com",
                "sender_domain": "tenant1.com",
            }
        ]
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        app.dependency_overrides[get_current_workspace] = lambda: "workspace-alpha"
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/elein/deliverability/verify-tracking-domain",
                json={"tracking_domain": "track.tenant1.com"},
            )
            self.assertEqual(resp.status_code, 200)
            # Verify update was scoped to workspace-alpha
            mock_table.update.return_value.eq.return_value.eq.assert_called_with("workspace_id", "workspace-alpha")
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)


if __name__ == "__main__":
    unittest.main()
