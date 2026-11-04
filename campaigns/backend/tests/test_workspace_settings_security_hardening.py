import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from pydantic import BaseModel

from admin.backend.routers.workspaces import remove_member, get_workspace_details, get_audit_log, verify_workspace_domain
from admin.backend.routers.settings import add_ai_key, APIKeyCreate
from integrations.backend.routers.api_keys import create_api_key, revoke_api_key, CreateApiKeyRequest
from core.backend.api.routers.billing import update_auto_recharge, AutoRechargeSettingsUpdate
from core.backend.api.auth_dep import get_supabase_client


class TestWorkspaceSettingsSecurityHardening(unittest.IsolatedAsyncioTestCase):

    def _setup_multi_table_mock(self):
        from collections import defaultdict
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    # --------------------------------------------------------------------------
    # 1. Privilege Inversion: Admin cannot remove Workspace Owner
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_admin_cannot_remove_workspace_owner(self, mock_svc_factory):
        """Paranoia Layer 2: An admin attempting to remove an owner must receive HTTP 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        # Distinguish actor query (admin) vs target query (owner)
        def mock_eq(col, val):
            m = MagicMock()
            if col == "user_id":
                role = "admin" if val == "user_admin" else "owner"
                m.eq.return_value.execute.return_value = MagicMock(data=[{"role": role}])
            return m

        tables["workspace_members"].select.return_value.eq.side_effect = mock_eq

        with self.assertRaises(HTTPException) as ctx:
            remove_member(
                workspace_id="ws_123",
                target_user_id="user_owner",
                user_id="user_admin"
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Workspace owners can only be removed by other owners", ctx.exception.detail)

    # --------------------------------------------------------------------------
    # 2. Workspace Details Endpoint: Returns Profile, Status, 2FA, Tier, Role
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_get_workspace_details_success(self, mock_svc_factory):
        """Paranoia Layer 0 & 2: GET /{workspace_id} returns full metadata and caller role."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "ws_123",
                "name": "Acme Outreach",
                "status": "active",
                "require_2fa": True,
                "created_at": "2026-01-01T00:00:00Z",
                "deletion_requested_at": None,
                "tier": "PRO",
                "owner_id": "user_owner"
            }]
        )

        # Member role lookup
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )

        res = get_workspace_details(
            workspace_id="ws_123",
            supabase=MagicMock(),
            user_id="user_admin"
        )
        self.assertEqual(res["id"], "ws_123")
        self.assertEqual(res["name"], "Acme Outreach")
        self.assertTrue(res["require_2fa"])
        self.assertEqual(res["tier"], "PRO")
        self.assertEqual(res["role"], "admin")
        self.assertFalse(res["is_owner"])

    # --------------------------------------------------------------------------
    # 3. AI Key Creation Masks Plaintext Secret
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.settings.get_service_client")
    def test_add_ai_key_masks_secret(self, mock_svc_factory):
        """Paranoia Layer 0 & 2: add_ai_key returns masked secret, never raw plaintext."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["system_api_keys"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        tables["system_api_keys"].insert.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "key_99",
                "provider": "openai",
                "api_key": "sk-proj-supersecretkey1234567890",
                "status": "active"
            }]
        )

        payload = APIKeyCreate(api_key="sk-proj-supersecretkey1234567890")
        res = add_ai_key(payload, _auth="superadmin")
        self.assertEqual(res["provider"], "openai")
        self.assertTrue(res["api_key"].startswith("sk-proj..."))
        self.assertNotIn("supersecretkey", res["api_key"])

    # --------------------------------------------------------------------------
    # 4. API Key Management RBAC: Non-admin Blocked
    # --------------------------------------------------------------------------
    def test_regular_member_cannot_create_api_key(self):
        """Paranoia Layer 2: Regular member cannot create integration API keys."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "member"}]
        )

        req = CreateApiKeyRequest(name="Test Key", scopes=["leads:read"])
        with self.assertRaises(HTTPException) as ctx:
            create_api_key(
                req=req,
                workspace_id="ws_123",
                user_id="user_member",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Only workspace owners and admins can create API keys", ctx.exception.detail)

    def test_regular_member_cannot_revoke_api_key(self):
        """Paranoia Layer 2: Regular member cannot revoke integration API keys."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "member"}]
        )

        with self.assertRaises(HTTPException) as ctx:
            revoke_api_key(
                key_id="key_1",
                workspace_id="ws_123",
                user_id="user_member",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Only workspace owners and admins can revoke API keys", ctx.exception.detail)

    # --------------------------------------------------------------------------
    # 5. Billing Auto-Recharge RBAC: Non-admin Blocked
    # --------------------------------------------------------------------------
    @patch("core.backend.api.routers.billing.get_service_client")
    async def test_regular_member_cannot_update_auto_recharge(self, mock_svc_factory):
        """Paranoia Layer 2: Regular member cannot configure auto-recharge settings."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "member"}]
        )

        req = AutoRechargeSettingsUpdate(
            enabled=True,
            threshold_credits=100,
            recharge_package_id="credits_1000",
            max_monthly_recharges=5
        )

        with self.assertRaises(HTTPException) as ctx:
            await update_auto_recharge(
                request=req,
                workspace_id="ws_123",
                user_id="user_member",
                supabase=MagicMock()
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Only workspace owners and admins can modify billing auto-recharge settings", ctx.exception.detail)

    # --------------------------------------------------------------------------
    # 6. Audit Log Filtering & Pagination
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_get_audit_log_filters_by_category_and_query(self, mock_svc_factory):
        """Paranoia Layer 0 & 2: Audit log accepts category and q parameters with exact count."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws_123", "tier": "ENTERPRISE"}]
        )
        tables["workspace_members"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )

        mock_query = MagicMock()
        mock_query.or_.return_value = mock_query
        mock_query.ilike.return_value = mock_query
        mock_query.order.return_value.range.return_value.execute.return_value = MagicMock(
            data=[{"id": "log_1", "action": "member.invited", "actor_id": "user_1"}],
            count=1
        )
        tables["audit_log"].select.return_value.eq.return_value = mock_query

        res = get_audit_log(
            workspace_id="ws_123",
            limit=20,
            offset=0,
            category="Team",
            q="invited",
            user_id="user_owner"
        )
        self.assertEqual(res["total"], 1)
        self.assertEqual(len(res["entries"]), 1)
        self.assertEqual(res["entries"][0]["action"], "member.invited")

    # --------------------------------------------------------------------------
    # 7. Retention 14-Day Workspace Deletion Sweep
    # --------------------------------------------------------------------------
    @patch("core.backend.services.gdpr_service.purge_workspace_data")
    def test_purge_expired_pending_deletion_workspaces(self, mock_purge):
        """Paranoia Layer 1: Purge worker automatically sweeps pending_deletion workspaces past 14 days."""
        from core.backend.services.retention_service import purge_expired_pending_deletion_workspaces
        mock_svc, tables = self._setup_multi_table_mock()

        tables["workspaces"].select.return_value.eq.return_value.lt.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws_expired_1", "name": "Dead Corp", "deletion_requested_at": "2026-01-01T00:00:00Z"}]
        )

        res = purge_expired_pending_deletion_workspaces(mock_svc, grace_period_days=14, dry_run=False)
        self.assertEqual(res["purged_workspaces"], 1)
        self.assertEqual(res["workspace_ids"], ["ws_expired_1"])
        mock_purge.assert_called_once()

    # --------------------------------------------------------------------------
    # 8. CNAME Verification Rejects Loopback / Malformed Domain
    # --------------------------------------------------------------------------
    @patch("admin.backend.routers.workspaces.get_service_client")
    def test_verify_workspace_domain_rejects_localhost(self, mock_svc_factory):
        """Paranoia Layer 2: Reject localhost and invalid domain formatting."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws_123", "custom_domain": "localhost", "tier": "AGENCY"}]
        )
        mock_supa = MagicMock()
        mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "owner"}]
        )

        with self.assertRaises(HTTPException) as ctx:
            verify_workspace_domain(
                workspace_id="ws_123",
                supabase=mock_supa,
                user_id="user_owner"
            )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
