import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import os
import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException

from core.backend.api.routers.approvals import (
    approve_reply,
    reject_reply,
    magic_approval_handler,
    magic_approval_get_endpoint,
    magic_approval_post_endpoint,
    ApprovalActionRequest,
)
from core.backend.api.routers.proxies import (
    create_proxy,
    delete_proxy,
    ProxyCreate,
)
from integrations.backend.routers.api_keys import (
    create_api_key,
    revoke_api_key,
    CreateApiKeyRequest,
)


class TestHorizon12ApprovalsProxiesApiKeys(unittest.TestCase):
    """
    Test suite for Horizon 12: Human-in-the-Loop AI Approvals, Magic Link Security,
    Residential Proxies & System Secret Auditing.
    Three-Layer Paranoia Architecture.
    """

    def _setup_multi_table_mock(self):
        """Helper to create isolated mock per table name to prevent chaining collisions."""
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)

        def get_table(tbl_name):
            return tables[tbl_name]

        mock_svc.table.side_effect = get_table
        return mock_svc, tables

    # =========================================================================
    # 1. AI Reply Approvals (Layer 0, 1, 2)
    # =========================================================================

    def test_approve_reply_404_if_not_found(self):
        """Layer 1: Non-existent approval item returns 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        tables["ai_reply_approvals"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = ApprovalActionRequest(edited_message="Looks great!")
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_ghost", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_approve_reply_400_if_already_resolved(self):
        """Layer 2: Cannot approve an item that is already approved or skipped (prevent double-sends)."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_1", "status": "approved", "ai_draft": "Hello!"}]
        )

        payload = ApprovalActionRequest()
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot approve item in status: approved", ctx.exception.detail)

    def test_approve_reply_400_if_message_body_empty(self):
        """Layer 2: Reject approval if message draft is empty and no edited text was provided."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_1", "status": "pending", "ai_draft": "   "}]
        )

        payload = ApprovalActionRequest(edited_message="   ")
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Message body cannot be empty", ctx.exception.detail)

    @patch("core.backend.api.routers.approvals.enqueue_job")
    def test_approve_reply_success_enqueues_worker_and_unblocks_state(self, mock_enqueue):
        """Layer 0: Approved reply queues delivery job and unblocks execution state."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_1",
                "status": "pending",
                "ai_draft": "Original Draft",
                "account_id": "acc_linkedin_1",
                "sender_name": "Sarah Connor",
                "execution_state_id": "exec_state_999"
            }]
        )

        payload = ApprovalActionRequest(edited_message="Custom Tailored Reply")
        res = approve_reply("app_1", payload, mock_svc, "ws_123")
        self.assertEqual(res["status"], "success")

        # Verify job queued with edited message
        mock_enqueue.assert_called_once()
        job_args = mock_enqueue.call_args[0]
        self.assertEqual(job_args[1], "inbox_action")
        self.assertEqual(job_args[4]["payload_data"]["message"], "Custom Tailored Reply")

        # Verify execution state advanced
        tables["campaign_execution_states"].update.assert_called()

    def test_reject_reply_success_marks_skipped_and_exits_state(self):
        """Layer 0: Rejected reply marks status as skipped and exits execution state."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_1",
                "status": "pending",
                "execution_state_id": "exec_state_999"
            }]
        )

        res = reject_reply("app_1", mock_svc, "ws_123")
        self.assertEqual(res["status"], "success")

        # Check queue status updated
        tables["approval_queue"].update.assert_called()
        # Check execution state marked exited with reason ai_reply_rejected
        tables["campaign_execution_states"].update.assert_called_with({
            "status": "exited",
            "error_reason": "ai_reply_rejected"
        })

    # =========================================================================
    # 2. Magic Link Approvals (Layer 1, 2)
    # =========================================================================

    def test_magic_approval_expired_token_returns_400_html(self):
        """Layer 1: Expired magic token returns clean 400 HTML response."""
        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            expired_token = jwt.encode(
                {"approval_id": "app_1", "action": "approve", "exp": datetime.utcnow() - timedelta(hours=1)},
                secret,
                algorithm="HS256"
            )
            response = magic_approval_handler(expired_token)
            self.assertEqual(response.status_code, 400)
            self.assertIn("link has expired", response.body.decode("utf-8"))

    def test_magic_approval_tampered_token_returns_400_html(self):
        """Layer 2: Tampered or invalid signature token returns 400 HTML response."""
        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            tampered_token = jwt.encode(
                {"approval_id": "app_1", "action": "approve"},
                "WRONG_SECRET_KEY",
                algorithm="HS256"
            )
            response = magic_approval_handler(tampered_token)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Invalid or tampered", response.body.decode("utf-8"))

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_scanner_get_shows_preview_without_mutating_db(self, mock_svc_factory):
        """Layer 1 Paranoia: Scanners issuing GET request only see preview form; NO database updates occur."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_ai_1", "status": "pending", "generated_reply": "AI response", "sender_name": "John Doe"}]
        )

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {"approval_id": "app_ai_1", "action": "approve", "exp": datetime.utcnow() + timedelta(hours=24)},
                secret,
                algorithm="HS256"
            )
            # Default GET / unconfirmed call
            response = magic_approval_handler(token, confirm=False)
            self.assertEqual(response.status_code, 200)
            body = response.body.decode("utf-8")
            self.assertIn("Review Proposed AI Outreach", body)
            self.assertIn("method=\"POST\"", body)
            self.assertIn("Protected by Ele-in Two-Step Gateway & Anti-Scanner Defense", body)
            # Database must NOT be updated on GET!
            tables["ai_reply_approvals"].update.assert_not_called()

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_confirmed_post_executes_mutation(self, mock_svc_factory):
        """Layer 0: Confirmed POST execution updates DB and queues delivery job."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_ai_1", "status": "pending", "generated_reply": "AI response", "execution_state_id": "exec_1"}]
        )

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {"approval_id": "app_ai_1", "action": "approve", "exp": datetime.utcnow() + timedelta(hours=24)},
                secret,
                algorithm="HS256"
            )
            # Confirmed execution
            response = magic_approval_handler(token, confirm=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn("AI Reply Approved", response.body.decode("utf-8"))
            tables["ai_reply_approvals"].update.assert_called()

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_confirmed_override_action_to_reject(self, mock_svc_factory):
        """Layer 2: Human manager can switch action to reject on confirmation screen."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_ai_1", "status": "pending", "generated_reply": "AI response", "execution_state_id": "exec_1"}]
        )

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {"approval_id": "app_ai_1", "action": "approve", "exp": datetime.utcnow() + timedelta(hours=24)},
                secret,
                algorithm="HS256"
            )
            response = magic_approval_handler(token, confirm=True, override_action="reject")
            self.assertEqual(response.status_code, 200)
            self.assertIn("AI Reply Rejected", response.body.decode("utf-8"))

    # =========================================================================
    # 3. Residential Proxies & Protocol Boundaries (Layer 1, 2)
    # =========================================================================

    def test_create_proxy_rejects_empty_host(self):
        """Layer 2: Empty proxy host is rejected with 400."""
        mock_supabase = MagicMock()
        payload = ProxyCreate(provider="custom", host="   ", port=8080)
        with self.assertRaises(HTTPException) as ctx:
            create_proxy(payload, mock_supabase, "ws_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", ctx.exception.detail)

    def test_create_proxy_rejects_out_of_range_port(self):
        """Layer 2: Port must be in valid TCP range 1-65535."""
        mock_supabase = MagicMock()
        payload_invalid_high = ProxyCreate(provider="custom", host="192.168.1.1", port=70000)
        with self.assertRaises(HTTPException) as ctx:
            create_proxy(payload_invalid_high, mock_supabase, "ws_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Port must be between 1 and 65535", ctx.exception.detail)

        payload_invalid_zero = ProxyCreate(provider="custom", host="192.168.1.1", port=0)
        with self.assertRaises(HTTPException) as ctx2:
            create_proxy(payload_invalid_zero, mock_supabase, "ws_1")
        self.assertEqual(ctx2.exception.status_code, 400)

    def test_create_proxy_rejects_unsupported_protocol(self):
        """Layer 2: Protocol outside http, https, socks4, socks5 is rejected with 400."""
        mock_supabase = MagicMock()
        payload = ProxyCreate(provider="custom", host="192.168.1.1", port=1080, protocol="ftp")
        with self.assertRaises(HTTPException) as ctx:
            create_proxy(payload, mock_supabase, "ws_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid protocol", ctx.exception.detail)

    def test_create_proxy_free_tier_rejected(self):
        """Layer 1: Free tier workspaces cannot configure custom proxies (requires Growth Pro)."""
        mock_supabase = MagicMock()
        mock_supabase.table("workspaces").select("tier").eq("id", "ws_free").execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )

        payload = ProxyCreate(provider="custom", host="192.168.1.1", port=8080)
        with self.assertRaises(HTTPException) as ctx:
            create_proxy(payload, mock_supabase, "ws_free")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Custom residential proxy pool configuration requires Growth Pro", ctx.exception.detail)

    def test_delete_proxy_404_if_not_found(self):
        """Layer 1: Deleting a non-existent proxy returns 404."""
        mock_supabase = MagicMock()
        mock_supabase.table("proxies").delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            delete_proxy("proxy_ghost", mock_supabase, "ws_1")
        self.assertEqual(ctx.exception.status_code, 404)

    # =========================================================================
    # 4. Public API Key Issuance, Scopes & Revocation (Layer 1, 2)
    # =========================================================================

    def test_create_api_key_rejects_empty_name(self):
        """Layer 2: Nameless API key requests return HTTP 400."""
        mock_supabase = MagicMock()
        req = CreateApiKeyRequest(name="   ", scopes=["campaigns:read"])
        with self.assertRaises(HTTPException) as ctx:
            create_api_key(req, "ws_1", "user_1", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", ctx.exception.detail)

    def test_create_api_key_rejects_empty_scopes(self):
        """Layer 2: API key requests with 0 scopes return HTTP 400."""
        mock_supabase = MagicMock()
        req = CreateApiKeyRequest(name="Cursor Agent", scopes=[])
        with self.assertRaises(HTTPException) as ctx:
            create_api_key(req, "ws_1", "user_1", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("At least one scope is required", ctx.exception.detail)

    def test_create_api_key_free_tier_rejected(self):
        """Layer 1: Free tier workspaces cannot generate external API keys."""
        mock_supabase = MagicMock()
        mock_supabase.table("workspaces").select("tier").eq("id", "ws_free").execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )

        req = CreateApiKeyRequest(name="Claude Code Pipeline", scopes=["leads:read"])
        with self.assertRaises(HTTPException) as ctx:
            create_api_key(req, "ws_free", "user_1", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("API key generation for external AI agents requires a Growth Pro", ctx.exception.detail)

    @patch("integrations.backend.routers.api_keys.issue_api_key")
    def test_create_api_key_pro_tier_succeeds(self, mock_issue):
        """Layer 0: Pro tier workspace successfully issues an API key."""
        mock_supabase = MagicMock()
        mock_supabase.table("workspaces").select("tier").eq("id", "ws_pro").execute.return_value = MagicMock(
            data=[{"tier": "PRO"}]
        )
        mock_issue.return_value = {"id": "key_1", "key": "ele_live_secret123", "prefix": "ele_live_"}

        req = CreateApiKeyRequest(name="Agent Key", scopes=["leads:read"])
        res = create_api_key(req, "ws_pro", "user_1", mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["prefix"], "ele_live_")

    def test_revoke_api_key_404_if_not_found(self):
        """Layer 1: Revoking a non-existent API key returns 404."""
        mock_supabase = MagicMock()
        mock_supabase.table("api_keys").update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            revoke_api_key("key_ghost", "ws_1", "user_1", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_revoke_api_key_success_writes_audit_log(self):
        """Layer 0: Revoking an API key sets is_active=False and records audit log."""
        mock_supabase, tables = self._setup_multi_table_mock()
        tables["api_keys"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "key_1", "is_active": False}]
        )

        res = revoke_api_key("key_1", "ws_1", "user_1", mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["message"], "API key revoked")
        tables["api_key_audit_logs"].insert.assert_called_with({
            "workspace_id": "ws_1",
            "api_key_id": "key_1",
            "actor": "user_1",
            "action": "revoked"
        })

    # =========================================================================
    # 4. Anti-Scanner Magic Approval Endpoint Integration Tests (H-03)
    # =========================================================================

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_get_endpoint_safe_preview(self, mock_svc_factory):
        """H-03: GET endpoint returns HTML preview form and never mutates DB."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_ai_1", "status": "pending", "generated_reply": "Safe AI reply", "sender_name": "Prospect X"}]
        )

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {"approval_id": "app_ai_1", "action": "approve", "exp": datetime.utcnow() + timedelta(hours=24)},
                secret,
                algorithm="HS256"
            )
            res = magic_approval_get_endpoint(token)
            self.assertEqual(res.status_code, 200)
            self.assertIn("Review Proposed AI Outreach", res.body.decode("utf-8"))
            tables["ai_reply_approvals"].update.assert_not_called()

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_post_endpoint_executes_mutation(self, mock_svc_factory):
        """H-03: POST endpoint accepts form submission and executes verified approval."""
        import asyncio
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "app_ai_1", "status": "pending", "generated_reply": "Safe AI reply", "execution_state_id": "exec_1"}]
        )

        mock_request = MagicMock()
        mock_request.query_params = {}

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {"approval_id": "app_ai_1", "action": "approve", "exp": datetime.utcnow() + timedelta(hours=24)},
                secret,
                algorithm="HS256"
            )
            res = asyncio.run(magic_approval_post_endpoint(
                request=mock_request,
                token=token,
                confirmed_action="approve"
            ))
            self.assertEqual(res.status_code, 200)
            self.assertIn("AI Reply Approved", res.body.decode("utf-8"))
            tables["ai_reply_approvals"].update.assert_called()


if __name__ == "__main__":
    unittest.main()
