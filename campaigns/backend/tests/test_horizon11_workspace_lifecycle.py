import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from admin.backend.routers.workspaces import (
    create_workspace,
    rename_workspace,
    update_sending_defaults,
    update_require_2fa,
    request_workspace_deletion,
    cancel_workspace_deletion,
    change_member_role,
    remove_member,
    get_audit_log,
    invite_member,
    revoke_invite,
    InviteCreate,
    WorkspaceCreate,
    WorkspaceRename,
    SendingDefaultsUpdate,
    Require2FAUpdate,
    DeletionRequest,
    RoleUpdate,
)
from admin.backend.routers.onboarding import (
    generate_preview,
    seed_demo_data,
    GeneratePreviewRequest,
)


from collections import defaultdict

class TestHorizon11WorkspaceLifecycle(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Horizon 11: Workspace Lifecycle, Onboarding Wizard,
    Account Deletion Grace Periods & Security Settings Audit.
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
    # 1. Workspace Creation & Renaming (Layer 0, 1, 2)
    # =========================================================================

    def test_create_workspace_rejects_empty_or_whitespace_name(self):
        """Layer 2: Prevent users from creating nameless workspaces."""
        with self.assertRaises(HTTPException) as ctx:
            create_workspace(WorkspaceCreate(name=""), user_id="user_123")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", ctx.exception.detail)

        with self.assertRaises(HTTPException) as ctx2:
            create_workspace(WorkspaceCreate(name="   \t\n  "), user_id="user_123")
        self.assertEqual(ctx2.exception.status_code, 400)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_create_workspace_trims_name_and_assigns_owner(self, mock_svc_factory):
        """Layer 0: Valid workspace creation inserts workspace and owner membership."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        res = create_workspace(WorkspaceCreate(name="  Acme Outbound  "), user_id="user_123")
        self.assertEqual(res["name"], "Acme Outbound")
        self.assertEqual(res["account_count"], 0)
        self.assertTrue(bool(res["id"]))

        # Verify calls to tables
        self.assertIn("workspaces", tables)
        self.assertIn("workspace_members", tables)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_rename_workspace_404_if_workspace_not_found(self, mock_svc_factory):
        """Layer 1: Renaming a ghost workspace returns 404, not 403 or 500."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        mock_supabase = MagicMock()

        # Workspace does not exist
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            rename_workspace("ws_ghost", WorkspaceRename(name="New Name"), mock_supabase, "user_123")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_rename_workspace_rejects_empty_name(self, mock_svc_factory):
        """Layer 2: Renaming to an empty or whitespace name is rejected with HTTP 400."""
        mock_svc, _ = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        mock_supabase = MagicMock()

        with self.assertRaises(HTTPException) as ctx:
            rename_workspace("ws_123", WorkspaceRename(name="   "), mock_supabase, "user_123")
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_rename_workspace_403_for_non_admin_member(self, mock_svc_factory):
        """Layer 1: Regular members cannot rename the workspace."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        mock_supabase = MagicMock()

        # Workspace exists
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_123"}])
        # Caller is regular member
        mock_supabase.table("workspace_members").select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "member"}])

        with self.assertRaises(HTTPException) as ctx:
            rename_workspace("ws_123", WorkspaceRename(name="New Brand"), mock_supabase, "user_mem")
        self.assertEqual(ctx.exception.status_code, 403)

    # =========================================================================
    # 2. Sending Defaults Configuration & Tier Gates (Layer 1, 2)
    # =========================================================================

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_sending_defaults_404_if_workspace_missing(self, mock_svc_factory):
        """Layer 1: Updating sending defaults for missing workspace returns 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = SendingDefaultsUpdate(daily_connection_limit=25)
        with self.assertRaises(HTTPException) as ctx:
            update_sending_defaults("ws_missing", payload, user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_sending_defaults_free_tier_cannot_override_schedule(self, mock_svc_factory):
        """Layer 1: Free tier cannot customize connection limits > 20 or enable weekend sending."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        # Workspace exists on FREE tier
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_free", "tier": "FREE"}])
        # Caller is owner
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        # Attempting 50 daily connections on Free tier (limit is 20)
        payload = SendingDefaultsUpdate(default_daily_connection_limit=50)
        with self.assertRaises(HTTPException) as ctx:
            update_sending_defaults("ws_free", payload, user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("require Growth Pro or Enterprise", ctx.exception.detail)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_sending_defaults_pro_tier_clamps_extreme_bounds(self, mock_svc_factory):
        """Layer 2: Outrageous values (e.g. 50,000 conns/day) are clamped to safe realistic limits."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        # Workspace is PRO
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_pro", "tier": "PRO"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
        tables["workspace_sending_defaults"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = SendingDefaultsUpdate(
            default_daily_connection_limit=99999,  # Should clamp to 500
            default_daily_message_limit=88888,     # Should clamp to 1000
            default_warmup_target_days=999,        # Should clamp to 90
            weekend_sending_enabled=True
        )

        res = update_sending_defaults("ws_pro", payload, user_id="user_owner")
        self.assertEqual(res["status"], "success")

        upsert_calls = tables["workspace_sending_defaults"].upsert.call_args[0][0]
        self.assertEqual(upsert_calls["default_daily_connection_limit"], 500)
        self.assertEqual(upsert_calls["default_daily_message_limit"], 1000)
        self.assertEqual(upsert_calls["default_warmup_target_days"], 90)

    # =========================================================================
    # 3. Mandatory 2FA Enforcement & Plan Gates (Layer 1, 2)
    # =========================================================================

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_require_2fa_free_tier_rejected(self, mock_svc_factory):
        """Layer 1: Free tier workspaces cannot enforce mandatory 2FA."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE", "require_2fa": False}])

        with self.assertRaises(HTTPException) as ctx:
            update_require_2fa("ws_free", Require2FAUpdate(require_2fa=True), user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Mandatory workspace-wide 2FA enforcement requires Growth Pro", ctx.exception.detail)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_update_require_2fa_rejected_if_owner_lacks_mfa(self, mock_svc_factory):
        """Layer 2: Owner cannot lock out everyone with mandatory 2FA if they haven't set up 2FA themselves."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO", "require_2fa": False}])

        # Owner has no verified factors
        mock_user = MagicMock()
        mock_user.factors = []
        mock_svc.auth.admin.get_user_by_id.return_value = MagicMock(user=mock_user)

        with self.assertRaises(HTTPException) as ctx:
            update_require_2fa("ws_pro", Require2FAUpdate(require_2fa=True), user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("You must enable 2FA on your own account before enforcing it", ctx.exception.detail)

    # =========================================================================
    # 4. Danger Zone: 14-Day Deletion Grace Period & Cancellation (Layer 0, 1, 2)
    # =========================================================================

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_request_workspace_deletion_requires_explicit_confirmation(self, mock_svc_factory):
        """Layer 2: Accidental clicks without confirm=True are rejected with 400."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_1", "status": "active"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        with self.assertRaises(HTTPException) as ctx:
            request_workspace_deletion("ws_1", DeletionRequest(confirm=False), user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Confirmation required")

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_request_workspace_deletion_pauses_campaigns_and_schedules_outbox(self, mock_svc_factory):
        """Layer 0 & 1: Deletion request marks pending_deletion, pauses campaigns, and inserts outbox event."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_1", "status": "active"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        res = request_workspace_deletion("ws_1", DeletionRequest(confirm=True), user_id="user_owner")
        self.assertEqual(res["status"], "success")
        self.assertIn("14-day grace period started", res["message"])

        # Check campaigns paused
        tables["campaigns"].update.assert_called_with({"status": "paused"})
        # Check outbox event inserted
        tables["outbox_events"].insert.assert_called()

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_request_workspace_deletion_duplicate_returns_409(self, mock_svc_factory):
        """Layer 1: Duplicate deletion requests while already pending return 409 Conflict."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_1", "status": "pending_deletion"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        with self.assertRaises(HTTPException) as ctx:
            request_workspace_deletion("ws_1", DeletionRequest(confirm=True), user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 409)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_cancel_workspace_deletion_restores_active_status(self, mock_svc_factory):
        """Layer 0: Cancellation restores status to 'active' and clears deletion_requested_at."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_1", "status": "pending_deletion"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        res = cancel_workspace_deletion("ws_1", user_id="user_owner")
        self.assertEqual(res["status"], "success")
        tables["workspaces"].update.assert_called_with({
            "status": "active",
            "deletion_requested_at": None
        })

    # =========================================================================
    # 5. Last Owner Protection & Member Role Management (Layer 1, 2)
    # =========================================================================

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_change_member_role_cannot_demote_sole_owner(self, mock_svc_factory):
        """Layer 1: Attempting to demote the only owner returns HTTP 400."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        # Plan tier allows role management
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO"}])

        def members_select_mock(fields, **kwargs):
            q = MagicMock()
            if fields == "role":
                q.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
            elif fields == "id":
                q.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "mem_1"}])
            return q

        tables["workspace_members"].select.side_effect = members_select_mock

        with self.assertRaises(HTTPException) as ctx:
            change_member_role("ws_1", "user_owner", RoleUpdate(role="admin"), user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot demote the last owner", ctx.exception.detail)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_remove_member_cannot_remove_sole_owner(self, mock_svc_factory):
        """Layer 1: Attempting to remove the last owner returns HTTP 400."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        def members_select_mock(fields, **kwargs):
            q = MagicMock()
            if fields == "role":
                q.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
            elif fields == "id":
                q.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "mem_1"}])
            return q

        tables["workspace_members"].select.side_effect = members_select_mock

        with self.assertRaises(HTTPException) as ctx:
            remove_member("ws_1", "user_owner", user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot remove the last owner", ctx.exception.detail)

    # =========================================================================
    # 6. Compliance Audit Log Pagination & Tier Gate (Layer 1, 2)
    # =========================================================================

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_get_audit_log_free_tier_blocked(self, mock_svc_factory):
        """Layer 1: Free tier workspaces cannot query audit logs."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_free", "tier": "FREE"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        with self.assertRaises(HTTPException) as ctx:
            get_audit_log("ws_free", limit=50, offset=0, user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("compliance audit trail and activity history require Growth Pro", ctx.exception.detail)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_get_audit_log_pro_tier_caps_limit_at_100(self, mock_svc_factory):
        """Layer 2: Huge limit requested (e.g. 5,000) is capped at 100 to protect server memory."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_pro", "tier": "PRO"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        mock_query = MagicMock()
        tables["audit_log"].select.return_value.eq.return_value.order.return_value.range.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=[{"id": "aud_1", "action": "member.invited"}])

        res = get_audit_log("ws_pro", limit=5000, offset=-10, user_id="user_owner")
        self.assertEqual(res["limit"], 100)
        self.assertEqual(res["offset"], 0)
        self.assertEqual(len(res["entries"]), 1)

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_get_audit_log_unmigrated_table_fallback(self, mock_svc_factory):
        """Layer 1: Missing/unmigrated audit_log table does not raise 503, returns unmigrated flag."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_pro", "tier": "PRO"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])

        mock_query = MagicMock()
        tables["audit_log"].select.return_value.eq.return_value.order.return_value.range.return_value = mock_query
        mock_query.execute.side_effect = Exception("PGRST205: relation 'audit_log' does not exist")

        res = get_audit_log("ws_pro", limit=50, offset=0, user_id="user_owner")
        self.assertEqual(res["entries"], [])
        self.assertTrue(res.get("unmigrated"))

    @patch("admin.backend.routers.workspaces.log_audit")
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_invite_member_success_returns_invite_url(self, mock_svc_factory, mock_log_audit):
        """Layer 0 & 2: Inviting a member creates token and returns 1-click shareable invite_url."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        # Actor is owner
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
        # Workspace is PRO (allows 5 seats)
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO"}])
        # Current members count = 1
        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value.count = 1
        # Pending invites count = 0
        tables["workspace_invites"].select.return_value.eq.return_value.eq.return_value.execute.return_value.count = 0

        # Upsert returns invite row
        tables["workspace_invites"].upsert.return_value.execute.return_value = MagicMock(data=[{"id": "inv_123", "email": "teammate@company.com"}])

        payload = InviteCreate(email="teammate@company.com", role="member")
        res = invite_member("ws_pro", payload=payload, supabase=MagicMock(), user_id="user_owner")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["invite_id"], "inv_123")
        self.assertIn("/accept-invite?token=", res["invite_url"])

    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_invite_member_unmigrated_table_raises_informative_503(self, mock_svc_factory):
        """Layer 1: Inviting a member when workspace_invites table is unmigrated returns clear 503."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "owner"}])
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO"}])
        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value.count = 1
        tables["workspace_invites"].select.side_effect = Exception("PGRST205: relation 'workspace_invites' does not exist")

        tables["workspace_invites"].upsert.side_effect = Exception("PGRST205: relation 'workspace_invites' does not exist")

        payload = InviteCreate(email="teammate@company.com", role="member")
        with self.assertRaises(HTTPException) as ctx:
            invite_member("ws_pro", payload=payload, supabase=MagicMock(), user_id="user_owner")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("pending database migrations", ctx.exception.detail)

    @patch("admin.backend.routers.workspaces.log_audit")
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_revoke_invite_success(self, mock_svc_factory, mock_log_audit):
        """Layer 0: Owners/admins can cleanly revoke pending invites."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "ws_1"}])
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"role": "admin"}])
        tables["workspace_invites"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "inv_1"}])

        res = revoke_invite("ws_1", "inv_1", user_id="user_admin")
        self.assertEqual(res["status"], "success")

    # =========================================================================
    # 7. Onboarding Wizard: LinkedIn Preview Generation (Layer 0, 1, 2)
    # =========================================================================

    async def test_generate_preview_guarantees_linkedin_length_constraints(self):
        """Layer 1: Algorithmic fallback guarantees connection note <= 300 characters across all tones."""
        tones = ["consultative", "direct", "curious"]
        for tone in tones:
            req = GeneratePreviewRequest(
                target_title="Chief Technology Officer",
                target_industry="Enterprise Financial Technology & Cybersecurity",
                company_name="Very Long Global Enterprise Corporation Inc",
                value_prop="revolutionize automated sovereign cold outbound email and linkedin lead generation at planetary scale",
                tone=tone
            )
            result = await generate_preview(req)
            self.assertEqual(result["status"], "success")
            self.assertLessEqual(len(result["connection_note"]), 300, f"Connection note exceeded 300 chars for tone {tone}")
            self.assertLessEqual(len(result["followup_message"]), 600, f"Followup exceeded 600 chars for tone {tone}")
            self.assertGreaterEqual(result["spam_safety_score"], 60.0)
            self.assertTrue(len(result["safety_badges"]) >= 3)

    async def test_generate_preview_penalizes_spam_triggers(self):
        """Layer 2: Aggressive sales trigger words reduce the calculated spam safety score."""
        req_clean = GeneratePreviewRequest(
            target_title="VP of Sales",
            target_industry="B2B SaaS",
            tone="direct"
        )
        res_clean = await generate_preview(req_clean)

        # Force a note with spam triggers
        with patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", side_effect=Exception("No LLM")):
            req_spam = GeneratePreviewRequest(
                target_title="VP of Sales",
                target_industry="B2B SaaS",
                value_prop="get 100% guaranteed free offer click here now",
                tone="direct"
            )
            res_spam = await generate_preview(req_spam)
            # res_spam contains triggers in the value prop
            self.assertLess(res_spam["spam_safety_score"], res_clean["spam_safety_score"])

    # =========================================================================
    # 8. Onboarding Wizard: IDOR Defense in Seed Demo Data (Layer 2)
    # =========================================================================

    @patch("admin.backend.routers.onboarding.verify_token_and_get_user_id")
    @patch("admin.backend.routers.onboarding.get_service_client")
    @patch("admin.backend.routers.onboarding.get_supabase_client")
    async def test_seed_demo_data_idor_defense_rejects_unauthorized_header(
        self, mock_get_supa, mock_get_svc, mock_verify_token
    ):
        """Layer 2 IDOR Defense: Passing X-Workspace-Id without membership ignores header and uses caller's workspace."""
        mock_verify_token.return_value = "user_attacker"
        mock_supabase = MagicMock()
        mock_get_supa.return_value = mock_supabase
        mock_svc = MagicMock()
        mock_get_svc.return_value = mock_svc

        # Attacker tries to inject victim's workspace
        victim_ws = "ws_victim_999"
        # workspace_members check returns empty (attacker is NOT a member of victim_ws)
        mock_supabase.table("workspace_members").select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        # But attacker has their own workspace
        own_ws = "ws_attacker_111"
        # Second call to workspace_members finds user's workspace
        mock_supabase.table("workspace_members").select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"workspace_id": own_ws}])

        # Campaigns check (already seeded)
        mock_supabase.table("campaigns").select.return_value.eq.return_value.execute.return_value = MagicMock(count=1)

        mock_request = MagicMock()
        mock_request.headers = {
            "Authorization": "Bearer mock_jwt_token",
            "X-Workspace-Id": victim_ws
        }
        mock_request.json = MagicMock(return_value={"force": False})

        res = await seed_demo_data(mock_request)
        # Verify it routed to attacker's own workspace, completely neutralizing IDOR injection
        self.assertEqual(res["workspace_id"], own_ws)
        self.assertEqual(res["status"], "already_seeded")


if __name__ == "__main__":
    unittest.main()
