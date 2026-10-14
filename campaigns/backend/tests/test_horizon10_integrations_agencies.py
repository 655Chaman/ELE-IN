import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import hashlib
from fastapi import HTTPException

from integrations.backend.routers.hubspot import (
    require_workspace_admin,
    authenticate_hubspot,
    get_hubspot_lists,
    set_hubspot_won_stage,
    HubspotAuth,
    HubspotWonStage
)
from integrations.backend.routers.extension import (
    verify_extension_api_key,
    sync_cookies,
    extension_heartbeat,
    get_extension_tasks,
    ExtensionSyncPayload
)
from core.backend.api.routers.agencies import (
    create_agency,
    create_client_workspace,
    invite_member,
    grant_client_access,
    get_agency_whitelabel,
    update_agency_whitelabel,
    list_agency_clients,
    AgencyCreate,
    ClientWorkspaceCreate,
    AgencyMemberInvite,
    AgencyAccessGrant,
    AgencyWhitelabelUpdate
)


class TestHorizon10HubSpotIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Horizon 10: HubSpot CRM Sync & Tier Enforcement.
    Three-Layer Paranoia Architecture.
    """

    @patch("core.backend.api.auth_dep.get_workspace_role")
    async def test_require_workspace_admin_owner_and_admin_permitted(self, mock_role):
        """Layer 0: Owners and admins pass permission check."""
        mock_supabase = MagicMock()
        mock_role.return_value = "owner"
        ws_id = await require_workspace_admin("ws_alpha", "user_owner", mock_supabase)
        self.assertEqual(ws_id, "ws_alpha")

        mock_role.return_value = "admin"
        ws_id2 = await require_workspace_admin("ws_alpha", "user_admin", mock_supabase)
        self.assertEqual(ws_id2, "ws_alpha")

    @patch("core.backend.api.auth_dep.get_workspace_role")
    async def test_require_workspace_admin_member_or_none_rejected(self, mock_role):
        """Layer 1: Regular members or non-members fail closed with HTTP 403."""
        mock_supabase = MagicMock()
        mock_role.return_value = "member"
        with self.assertRaises(HTTPException) as ctx:
            await require_workspace_admin("ws_alpha", "user_member", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 403)

        mock_role.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            await require_workspace_admin("ws_alpha", "user_stranger", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_authenticate_hubspot_free_tier_blocked(self):
        """Layer 1: Free tier workspaces cannot sync CRM contacts; requires Growth Pro."""
        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(data=[{"tier": "FREE"}]))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select

        data = HubspotAuth(access_token="pat-na1-12345")
        with self.assertRaises(HTTPException) as ctx:
            await authenticate_hubspot(data, "ws_free", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Growth Pro", ctx.exception.detail)

    @patch("core.backend.services.http_client.async_external_request")
    async def test_authenticate_hubspot_network_error_containment(self, mock_req):
        """Layer 1: External HTTP network failure raises HTTP 502 instead of 500 traceback."""
        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(data=[{"tier": "PRO"}]))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select

        mock_req.side_effect = Exception("HubSpot gateway timeout connection dropped")

        data = HubspotAuth(access_token="pat-na1-12345")
        with self.assertRaises(HTTPException) as ctx:
            await authenticate_hubspot(data, "ws_pro", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Failed to communicate with HubSpot API", ctx.exception.detail)

    async def test_set_hubspot_won_stage_empty_stage_id_rejected(self):
        """Layer 2: Blank or whitespace stage ID fails validation with HTTP 400."""
        mock_supabase = MagicMock()
        data = HubspotWonStage(stage_id="   ")
        with self.assertRaises(HTTPException) as ctx:
            await set_hubspot_won_stage(data, "ws_alpha", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("stage_id cannot be empty", ctx.exception.detail)


class TestHorizon10ExtensionBridge(unittest.TestCase):
    """
    Test suite for Chrome Extension Bridge: API Key Validation, CAS Dequeuing, and Cookie Ingestion.
    """

    def test_verify_extension_api_key_empty_or_whitespace_fails(self):
        """Layer 2: Blank or whitespace-only API keys are rejected with HTTP 401."""
        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            verify_extension_api_key("", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 401)

        with self.assertRaises(HTTPException) as ctx:
            verify_extension_api_key("   ", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_sync_cookies_rejects_non_list_json(self):
        """Layer 1: Cookie payload formatted as JSON dict or primitive fails safely with HTTP 400."""
        mock_supabase = MagicMock()
        payload = ExtensionSyncPayload(
            account_name="Sender",
            cookies_json=json.dumps({"name": "li_at", "value": "AQED..."}) # Dict instead of list
        )
        with self.assertRaises(HTTPException) as ctx:
            sync_cookies(payload, "ws_alpha", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("must be a non-empty JSON list of cookies", ctx.exception.detail)

    def test_extension_heartbeat_db_resilience(self):
        """Layer 1: Heartbeat database hiccup or missing table fails silently without breaking extension."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.upsert.return_value.execute.side_effect = Exception("DB timeout")

        res = extension_heartbeat({"account_id": None}, "ws_alpha", mock_supabase)
        self.assertEqual(res, {"status": "ok"})

    def test_get_extension_tasks_atomic_cas_race_defense(self):
        """
        Layer 1 & Concurrency: When two extension workers poll the same pending state,
        the second worker whose update returns 0 rows yields empty tasks cleanly.
        """
        mock_supabase = MagicMock()

        # 1. Account check passes
        mock_acc = MagicMock()
        mock_acc.data = [{"id": "acc_1"}]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_acc

        # 2. Campaign check
        mock_camp = MagicMock()
        mock_camp.data = [{"id": "camp_1"}]
        mock_supabase.table().select().eq().execute.return_value = mock_camp

        # 3. Campaign accounts
        mock_ca = MagicMock()
        mock_ca.data = [{"account_id": "acc_1"}]
        mock_supabase.table().select().eq().execute.return_value = mock_ca

        # 4. Pending execution state found
        mock_state = {
            "id": "state_123",
            "current_node_id": "node_1",
            "campaign_enrollments": {
                "campaign_id": "camp_1",
                "leads": {"linkedin_url": "https://linkedin.com/in/john", "first_name": "John"}
            }
        }
        mock_states = MagicMock()
        mock_states.data = [mock_state]
        mock_supabase.table().select().eq().eq().lte().limit().execute.return_value = mock_states

        # 5. CAS update to 'running' returns EMPTY (simulating another worker claimed it first)
        mock_upd = MagicMock()
        mock_upd.data = []
        mock_supabase.table().update().eq().eq().eq().execute.return_value = mock_upd

        res = get_extension_tasks("acc_1", "ws_alpha", mock_supabase)
        # Yields empty tasks without double-claiming or crashing
        self.assertEqual(res, {"tasks": []})


class TestHorizon10AgencyArchitecture(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Agency Multi-Workspace Architecture, Member Roles, and Client Delegation.
    """

    async def test_create_agency_empty_name_fails(self):
        """Layer 2: Blank or whitespace agency name rejected with HTTP 400."""
        mock_supabase = MagicMock()
        payload = AgencyCreate(name="   ")
        with self.assertRaises(HTTPException) as ctx:
            await create_agency(payload, mock_supabase, "user_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Agency name cannot be empty", ctx.exception.detail)

    async def test_create_client_workspace_empty_name_fails(self):
        """Layer 2: Blank client workspace name rejected with HTTP 400."""
        mock_supabase = MagicMock()
        mock_owner_check = MagicMock()
        mock_owner_check.data = [{"id": "agency_mem_1"}]
        mock_supabase.table().select().eq().eq().eq().limit().execute = AsyncMock(return_value=mock_owner_check)

        payload = ClientWorkspaceCreate(name="  ")
        with self.assertRaises(HTTPException) as ctx:
            await create_client_workspace("agency_1", payload, mock_supabase, "user_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Client workspace name cannot be empty", ctx.exception.detail)

    async def test_invite_member_role_and_email_validation(self):
        """Layer 2: Invalid agency roles (e.g. 'superadmin') or malformed emails fail with HTTP 400."""
        mock_supabase = MagicMock()
        mock_owner_check = MagicMock()
        mock_owner_check.data = [{"id": "agency_mem_1"}]
        mock_supabase.table().select().eq().eq().eq().limit().execute = AsyncMock(return_value=mock_owner_check)

        # Bad email
        payload_bad_email = AgencyMemberInvite(email="notanemail", role="member")
        with self.assertRaises(HTTPException) as ctx:
            await invite_member("agency_1", payload_bad_email, mock_supabase, "user_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Valid email address required", ctx.exception.detail)

        # Illegal role
        payload_bad_role = AgencyMemberInvite(email="rep@client.com", role="superadmin")
        with self.assertRaises(HTTPException) as ctx:
            await invite_member("agency_1", payload_bad_role, mock_supabase, "user_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid agency role", ctx.exception.detail)

    async def test_grant_client_access_duplicate_tolerance(self):
        """Layer 1: Duplicate access grant gracefully returns existing access instead of 500 crash."""
        mock_supabase = MagicMock()

        # 1. Verify agency owner
        mock_owner = MagicMock()
        mock_owner.data = [{"id": "mem_owner"}]
        mock_supabase.table().select().eq().eq().eq().limit().execute = AsyncMock(return_value=mock_owner)

        # 2. Workspace check
        mock_ws = MagicMock()
        mock_ws.data = [{"id": "ws_client"}]
        mock_supabase.table().select().eq().eq().limit().execute = AsyncMock(return_value=mock_ws)

        # 3. Member check
        mock_mem = MagicMock()
        mock_mem.data = [{"id": "mem_target"}]
        mock_supabase.table().select().eq().eq().limit().execute = AsyncMock(return_value=mock_mem)

        # 4. Insert throws duplicate constraint exception
        mock_insert = MagicMock()
        mock_insert.execute = AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))
        mock_supabase.table().insert.return_value = mock_insert

        # 5. Fallback select finds existing grant
        mock_existing = MagicMock()
        mock_existing.data = [{"id": "access_existing", "workspace_id": "ws_client"}]
        mock_supabase.table().select().eq().eq().execute = AsyncMock(return_value=mock_existing)

        payload = AgencyAccessGrant(workspace_id="ws_client")
        res = await grant_client_access("agency_1", "mem_target", payload, mock_supabase, "user_1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["access"]["id"], "access_existing")

    async def test_whitelabel_update_validation_and_sanitization(self):
        """Layer 2: Whitelabel update sanitizes protocols and validates hex colors and brand title."""
        mock_supabase = MagicMock()
        mock_admin = MagicMock()
        mock_admin.data = [{"id": "mem_admin", "role": "admin"}]
        mock_supabase.table().select().eq().eq().in_().limit().execute = AsyncMock(return_value=mock_admin)

        mock_update = MagicMock()
        mock_update.data = [{"id": "agency_1"}]
        mock_supabase.table().update().eq().execute = AsyncMock(return_value=mock_update)

        # 1. Successful update strips https:// and trailing slashes
        payload = AgencyWhitelabelUpdate(
            brand_name="  Nexus Growth Agency  ",
            custom_domain="https://portal.nexusgrowth.com/",
            accent_color="#4f46e5"
        )
        res = await update_agency_whitelabel("agency_1", payload, mock_supabase, "user_admin")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["whitelabel"]["brand_name"], "Nexus Growth Agency")
        self.assertEqual(res["whitelabel"]["custom_domain"], "portal.nexusgrowth.com")
        self.assertEqual(res["whitelabel"]["accent_color"], "#4f46e5")

        # 2. Empty brand fails with 400
        bad_payload = AgencyWhitelabelUpdate(brand_name="   ")
        with self.assertRaises(HTTPException) as ctx:
            await update_agency_whitelabel("agency_1", bad_payload, mock_supabase, "user_admin")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", ctx.exception.detail)

    async def test_list_agency_clients_rpc_success(self):
        """Layer 0: list_agency_clients returns data from get_agency_clients_overview RPC."""
        mock_supabase = MagicMock()
        mock_member = MagicMock()
        mock_member.data = [{"id": "mem_1"}]
        mock_supabase.table().select().eq().eq().limit().execute = AsyncMock(return_value=mock_member)

        mock_rpc = MagicMock()
        mock_rpc.data = [
            {
                "id": "ws_1",
                "name": "Client Alpha",
                "campaigns_count": 5,
                "active_campaigns_count": 2,
                "leads_count": 1200,
                "senders_count": 3
            }
        ]
        mock_supabase.rpc().execute = AsyncMock(return_value=mock_rpc)

        clients = await list_agency_clients("agency_1", mock_supabase, "user_1")
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["name"], "Client Alpha")
        self.assertEqual(clients[0]["campaigns_count"], 5)
        self.assertEqual(clients[0]["senders_count"], 3)


if __name__ == "__main__":
    unittest.main()
