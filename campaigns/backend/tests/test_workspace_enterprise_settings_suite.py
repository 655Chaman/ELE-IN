import unittest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from starlette.requests import Request

from admin.backend.routers.workspaces import (
    list_workspace_sessions,
    revoke_workspace_session,
    revoke_all_other_sessions,
    list_workspace_api_keys,
    create_workspace_api_key,
    revoke_workspace_api_key,
    get_workspace_ip_allowlist,
    update_workspace_ip_allowlist,
    update_member_permissions,
    resend_workspace_invite,
    test_notification_webhook as execute_test_notification_webhook,
    export_workspace_data_archive,
    get_workspace_legal_profile,
    update_workspace_legal_profile,
    get_workspace_webhooks,
    update_workspace_webhooks,
    get_session_timeout,
    update_session_timeout,
    bulk_invite_workspace_members,
    WorkspaceApiKeyCreate,
    IpAllowlistUpdate,
    MemberPermissionsUpdate,
    NotificationTestPayload,
    LegalProfileUpdate,
    WorkspaceWebhooksUpdate,
    SessionTimeoutUpdate,
    BulkInviteRequest,
)


class TestWorkspaceEnterpriseSettingsSuite(unittest.IsolatedAsyncioTestCase):

    def _setup_multi_table_mock(self):
        from collections import defaultdict
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    def _make_dummy_request(self, client_ip: str = "203.0.113.195"):
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"user-agent", b"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")],
            "client": (client_ip, 54321),
        }
        return Request(scope)

    # --------------------------------------------------------------------------
    # 1. Active Sessions Management
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_list_workspace_sessions_returns_current(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {"active_sessions": [
                {"id": "sess_1", "user_id": "u1", "browser": "Chrome", "is_current": True}
            ]}}]
        )

        req = self._make_dummy_request()
        res = list_workspace_sessions("ws_1", req, user_id="u1")
        self.assertIn("sessions", res)
        self.assertGreaterEqual(len(res["sessions"]), 1)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_revoke_session_success(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {"active_sessions": [
                {"id": "sess_1", "user_id": "u1"},
                {"id": "sess_2", "user_id": "u1"}
            ]}}]
        )

        res = revoke_workspace_session("ws_1", "sess_2", user_id="u1")
        self.assertEqual(res["status"], "revoked")
        self.assertEqual(res["session_id"], "sess_2")

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_revoke_all_other_sessions_success(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {}}]
        )

        res = revoke_all_other_sessions("ws_1", user_id="u1")
        self.assertEqual(res["status"], "all_revoked")

    # --------------------------------------------------------------------------
    # 2. Developer API Keys Management
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_create_and_revoke_api_key(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {}}]
        )

        req_body = WorkspaceApiKeyCreate(name="Zapier Prod", scopes=["campaigns:read", "leads:write"])
        created = create_workspace_api_key("ws_1", req_body, user_id="u1")
        self.assertIn("raw_secret", created)
        self.assertTrue(created["raw_secret"].startswith("sk_live_"))
        self.assertEqual(created["api_key"]["name"], "Zapier Prod")

        key_id = created["api_key"]["id"]
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {"developer_api_keys": [{"id": key_id, "name": "Zapier Prod"}]}}]
        )
        revoked = revoke_workspace_api_key("ws_1", key_id, user_id="u1")
        self.assertEqual(revoked["status"], "revoked")

    # --------------------------------------------------------------------------
    # 3. Enterprise IP Allowlisting (CIDR Validation & Self-Lockout Defense)
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_ip_allowlist_blocks_self_lockout(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {}}]
        )

        import os
        old_val = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            req = self._make_dummy_request(client_ip="203.0.113.195")
            body = IpAllowlistUpdate(enforce_ip_allowlist=True, allowed_cidrs=["10.0.0.0/8"])
            with self.assertRaises(HTTPException) as ctx:
                update_workspace_ip_allowlist("ws_1", body, req, user_id="u1")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Self-Lockout Prevented", ctx.exception.detail)
        finally:
            if old_val:
                os.environ["PYTEST_CURRENT_TEST"] = old_val

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_ip_allowlist_success_when_client_included(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {}}]
        )

        req = self._make_dummy_request(client_ip="203.0.113.195")
        body = IpAllowlistUpdate(enforce_ip_allowlist=True, allowed_cidrs=["203.0.113.0/24"])
        res = update_workspace_ip_allowlist("ws_1", body, req, user_id="u1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["ip_allowlist"]["allowed_cidrs"], ["203.0.113.0/24"])

    # --------------------------------------------------------------------------
    # 4. Granular Permissions Update
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_member_permissions_success(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        def mock_user_query(col, val):
            m = MagicMock()
            role = "owner" if val == "u1" else "member"
            m.eq.return_value.execute.return_value = MagicMock(data=[{"user_id": val, "role": role}])
            return m

        tables["workspace_members"].select.return_value.eq.side_effect = mock_user_query
        tables["workspace_members"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "target_user_1", "role": "member"}]
        )

        body = MemberPermissionsUpdate(permissions={"can_export_leads": False, "can_delete_campaigns": False})
        res = update_member_permissions("ws_1", "target_user_1", body, user_id="u1")
        self.assertEqual(res["status"], "success")
        self.assertFalse(res["permissions"]["can_export_leads"])

    # --------------------------------------------------------------------------
    # 5. Invite Resend with Cooldown
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_resend_workspace_invite_success(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )
        tables["workspace_invites"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "inv_1", "email": "test@domain.com", "status": "pending", "updated_at": "2020-01-01T00:00:00Z"}]
        )

        res = resend_workspace_invite("ws_1", "inv_1", user_id="u1")
        self.assertEqual(res["status"], "success")
        self.assertIn("test@domain.com", res["message"])

    # --------------------------------------------------------------------------
    # 6. Webhook Delivery Testing
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    @patch("httpx.AsyncClient.post")
    async def test_notification_webhook_test_success(self, mock_http_post, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "ok"
        mock_http_post.return_value = mock_resp

        body = NotificationTestPayload(webhook_url="https://hooks.slack.com/services/test/endpoint")
        res = await execute_test_notification_webhook("ws_1", body, user_id="u1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["status_code"], 200)

    # --------------------------------------------------------------------------
    # 7. Complete Workspace Archive Export
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_export_workspace_data_archive_success(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "u1", "role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws_1", "name": "Acme Corp", "metadata": {}}]
        )
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "title": "Outreach Alpha", "status": "active"}]
        )
        mock_leads_query = MagicMock()
        mock_leads_query.count = 150
        tables["leads"].select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_leads_query

        res = export_workspace_data_archive("ws_1", user_id="u1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.media_type, "application/json")
        bundle = json.loads(res.body.decode())
        self.assertEqual(bundle["workspace"]["name"], "Acme Corp")
        self.assertEqual(bundle["total_stored_leads"], 150)

    # --------------------------------------------------------------------------
    # 8. Legal Profile & CAN-SPAM Compliance
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_legal_profile_update_and_get(self, mock_svc_factory):
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {"legal_profile": {"company_legal_name": "Acme Global Inc"}}}]
        )

        get_res = get_workspace_legal_profile("ws_1", user_id="u1")
        self.assertEqual(get_res["company_legal_name"], "Acme Global Inc")

        update_body = LegalProfileUpdate(
            company_legal_name="Acme Enterprise Inc",
            address_line1="100 Enterprise Way",
            city="San Francisco",
            country="United States"
        )
        update_res = update_workspace_legal_profile("ws_1", update_body, user_id="u1")
        self.assertEqual(update_res["status"], "success")
        self.assertEqual(update_res["legal_profile"]["company_legal_name"], "Acme Enterprise Inc")

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_webhooks_persistence_and_ssrf_defense(self, mock_svc_factory):
        """Layer 1 & 2: Validates HTTPS webhook persistence and blocks private network SSRF targets."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {"webhooks": {"slack_webhook_url": "https://hooks.slack.com/services/T00/B00/X00"}}}]
        )

        # GET
        wh_data = get_workspace_webhooks("ws_1", user_id="u1")
        self.assertEqual(wh_data["slack_webhook_url"], "https://hooks.slack.com/services/T00/B00/X00")
        self.assertIn("channel_routing", wh_data)

        # SSRF attempt on localhost
        with self.assertRaises(HTTPException) as ctx:
            update_workspace_webhooks(
                "ws_1",
                WorkspaceWebhooksUpdate(slack_webhook_url="http://localhost:8080/hook"),
                user_id="u1"
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # Valid HTTPS update
        valid_update = WorkspaceWebhooksUpdate(
            slack_webhook_url="https://hooks.slack.com/services/T01/B01/VALID",
            discord_webhook_url="https://discord.com/api/webhooks/123/ABC"
        )
        res = update_workspace_webhooks("ws_1", valid_update, user_id="u1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["webhooks"]["slack_webhook_url"], "https://hooks.slack.com/services/T01/B01/VALID")

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_session_inactivity_timeout_policy(self, mock_svc_factory):
        """Layer 1 & 2: Configures session inactivity timeout and enforces allowed duration intervals."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"metadata": {"security_policies": {"session_inactivity_timeout_minutes": 60}}}]
        )

        res = get_session_timeout("ws_1", user_id="u1")
        self.assertEqual(res["session_inactivity_timeout_minutes"], 60)

        # Invalid duration
        with self.assertRaises(HTTPException) as ctx:
            update_session_timeout("ws_1", SessionTimeoutUpdate(timeout_minutes=42), user_id="u1")
        self.assertEqual(ctx.exception.status_code, 400)

        # Valid duration (15 min high security)
        res_update = update_session_timeout("ws_1", SessionTimeoutUpdate(timeout_minutes=15, enforce_device_fingerprint=True), user_id="u1")
        self.assertEqual(res_update["status"], "success")
        self.assertEqual(res_update["session_inactivity_timeout_minutes"], 15)
        self.assertTrue(res_update["enforce_device_fingerprint"])

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_bulk_invite_members_with_dedupe_and_validation(self, mock_svc_factory):
        """Layer 0 & 2: Bulk invitation deduplicates, validates email format, and checks seat limits."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "ENTERPRISE"}]
        )
        # Existing 1 member, 0 pending invites
        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "u1"}]
        )
        tables["workspace_invites"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["workspace_invites"].insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "inv_new"}]
        )

        req = BulkInviteRequest(
            emails=["alice@acme.com", "bob@acme.com", "invalid-syntax", "alice@acme.com"],
            role="member"
        )
        res = bulk_invite_workspace_members("ws_1", req, user_id="u1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_created"], 2)  # alice and bob (deduped, invalid skipped)
        self.assertEqual(len(res["skipped"]), 1)
        self.assertEqual(res["skipped"][0]["reason"], "Invalid email format")


if __name__ == "__main__":
    unittest.main()
