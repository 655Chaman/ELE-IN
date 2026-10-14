import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import Request, HTTPException
import json
import time

from core.backend.api.auth_dep import (
    get_current_workspace,
    get_current_user_id,
    get_current_user_id_with_2fa,
    get_workspace_role,
    require_workspace_role,
    verify_token_and_get_user_id,
    verify_jwt,
    get_supabase_client,
    get_async_supabase_client,
)


class TestHorizon7AuthAndRBAC(unittest.IsolatedAsyncioTestCase):
    """
    Horizon 7: Authentication, Session Security & Multi-Tenant RBAC.
    Rigorous verification under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.user_id = "user_alice_001"
        self.victim_user_id = "user_bob_002"
        self.workspace_id = "ws_alice_primary"
        self.victim_workspace_id = "ws_bob_private"

    def _create_mock_request(self, auth_header: str = None, headers: dict = None, method: str = "GET", path: str = "/api/campaigns"):
        req = MagicMock(spec=Request)
        req.method = method
        all_headers = {}
        if auth_header is not None:
            all_headers["authorization"] = auth_header
            all_headers["Authorization"] = auth_header
        if headers:
            for k, v in headers.items():
                all_headers[k.lower()] = v
                all_headers[k] = v

        req.headers = all_headers
        req.url = MagicMock()
        req.url.path = path
        req.path_params = {}
        return req

    # =========================================================================
    # Test 1: Authorization Header Parsing & Malformed Header Defense (Layer 2)
    # =========================================================================
    async def test_authorization_header_malformed_defense(self):
        # Case A: Missing header entirely -> 401
        req_missing = self._create_mock_request(auth_header=None)
        with self.assertRaises(HTTPException) as cm:
            await get_current_workspace(req_missing)
        self.assertEqual(cm.exception.status_code, 401)

        # Case B: Bad scheme (Basic) -> 401
        req_basic = self._create_mock_request(auth_header="Basic dXNlcjpwYXNz")
        with self.assertRaises(HTTPException) as cm:
            await get_current_workspace(req_basic)
        self.assertEqual(cm.exception.status_code, 401)

        # Case C: Bearer without token ("Bearer") -> 401 (no IndexError)
        req_bearer_empty = self._create_mock_request(auth_header="Bearer")
        with self.assertRaises(HTTPException) as cm:
            await get_current_workspace(req_bearer_empty)
        self.assertEqual(cm.exception.status_code, 401)

        # Case D: Bearer with whitespace only ("Bearer    ") -> 401
        req_bearer_spaces = self._create_mock_request(auth_header="Bearer   ")
        with self.assertRaises(HTTPException) as cm:
            await get_current_workspace(req_bearer_spaces)
        self.assertEqual(cm.exception.status_code, 401)

        # Case E: get_current_user_id handles malformed header safely
        with self.assertRaises(HTTPException) as cm:
            get_current_user_id(req_bearer_empty)
        self.assertEqual(cm.exception.status_code, 401)

    # =========================================================================
    # Test 2: Cross-Tenant IDOR Impersonation Defense (Layer 1)
    # =========================================================================
    async def test_cross_tenant_workspace_idor_defense(self):
        """
        User Alice attempts to pass User Bob's workspace ID in X-Workspace-Id.
        Must be strictly rejected with 403 Forbidden.
        """
        mock_supabase = MagicMock()
        # Mock auth.get_user returns Alice
        mock_user = MagicMock()
        mock_user.id = self.user_id
        mock_supabase.auth.get_user = AsyncMock(return_value=MagicMock(user=mock_user))

        # Bob's workspace exists, but owner is Bob
        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock(
            data=[{
                "id": self.victim_workspace_id,
                "status": "active",
                "require_2fa": False,
                "owner_id": self.victim_user_id  # Bob is owner
            }]
        ))

        # Query to workspace_members returns empty (Alice is NOT a member)
        mock_mem_table = MagicMock()
        mock_mem_table.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock(
            data=[]
        ))

        def table_router(t):
            if t == "workspaces":
                return mock_ws_table
            if t == "workspace_members":
                return mock_mem_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        req = self._create_mock_request(
            auth_header="Bearer valid_token_alice",
            headers={"X-Workspace-Id": self.victim_workspace_id}
        )

        with self.assertRaises(HTTPException) as cm:
            await get_current_workspace(req, supabase=mock_supabase)

        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Not a member of this workspace", cm.exception.detail)

    # =========================================================================
    # Test 3: Default Workspace Scoped Resolution (Layer 0 & Layer 1)
    # =========================================================================
    async def test_default_workspace_scoped_to_caller(self):
        """
        When X-Workspace-Id is omitted, get_current_workspace resolves the caller's
        membership rather than arbitrary global rows.
        """
        mock_supabase = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.user_id
        mock_supabase.auth.get_user = AsyncMock(return_value=MagicMock(user=mock_user))

        mock_mem_table = MagicMock()
        # User is a member of ws_alice_primary
        mock_mem_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"workspace_id": self.workspace_id}])
        )

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{
                "id": self.workspace_id,
                "status": "active",
                "require_2fa": False,
                "owner_id": self.user_id
            }])
        )

        def table_router(t):
            if t == "workspace_members":
                return mock_mem_table
            if t == "workspaces":
                return mock_ws_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        req = self._create_mock_request(auth_header="Bearer valid_token_alice")
        resolved_ws = await get_current_workspace(req, supabase=mock_supabase)
        self.assertEqual(resolved_ws, self.workspace_id)

    # =========================================================================
    # Test 4: Javascript State Normalization ("undefined" / "null") (Layer 2)
    # =========================================================================
    async def test_javascript_uninitialized_state_normalization(self):
        """
        Frontend uninitialized values ('undefined', 'null') in X-Workspace-Id
        are normalized to None and safely resolve default workspace without DB errors.
        """
        mock_supabase = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.user_id
        mock_supabase.auth.get_user = AsyncMock(return_value=MagicMock(user=mock_user))

        mock_mem_table = MagicMock()
        mock_mem_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"workspace_id": self.workspace_id}])
        )

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{
                "id": self.workspace_id,
                "status": "active",
                "require_2fa": False,
                "owner_id": self.user_id
            }])
        )

        def table_router(t):
            if t == "workspace_members":
                return mock_mem_table
            if t == "workspaces":
                return mock_ws_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        for uninit_val in ["undefined", "null", "None", "   "]:
            req = self._create_mock_request(
                auth_header="Bearer valid_token_alice",
                headers={"X-Workspace-Id": uninit_val}
            )
            resolved_ws = await get_current_workspace(req, supabase=mock_supabase)
            self.assertEqual(resolved_ws, self.workspace_id)

    # =========================================================================
    # Test 5: Workspace Pending Deletion Lock (Layer 1 & Layer 2)
    # =========================================================================
    async def test_pending_deletion_blocks_mutations(self):
        """
        Mutations (POST, PUT, DELETE, PATCH) on a workspace pending deletion
        are rejected with 423 Locked, while exempt lifecycle endpoints are permitted.
        """
        mock_supabase = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.user_id
        mock_supabase.auth.get_user = AsyncMock(return_value=MagicMock(user=mock_user))

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{
                "id": self.workspace_id,
                "status": "pending_deletion",
                "require_2fa": False,
                "owner_id": self.user_id
            }])
        )
        mock_supabase.table.return_value = mock_ws_table

        # Case A: Mutation to /api/campaigns is blocked
        req_post = self._create_mock_request(
            auth_header="Bearer valid_token_alice",
            headers={"X-Workspace-Id": self.workspace_id},
            method="POST",
            path="/api/campaigns"
        )
        with self.assertRaises(HTTPException) as cm:
            await get_current_workspace(req_post, supabase=mock_supabase)
        self.assertEqual(cm.exception.status_code, 423)

        # Case B: Read (GET) to /api/campaigns is allowed
        req_get = self._create_mock_request(
            auth_header="Bearer valid_token_alice",
            headers={"X-Workspace-Id": self.workspace_id},
            method="GET",
            path="/api/campaigns"
        )
        res = await get_current_workspace(req_get, supabase=mock_supabase)
        self.assertEqual(res, self.workspace_id)

        # Case C: Mutation to exempt path /cancel-deletion is allowed
        req_cancel = self._create_mock_request(
            auth_header="Bearer valid_token_alice",
            headers={"X-Workspace-Id": self.workspace_id},
            method="POST",
            path=f"/api/workspaces/{self.workspace_id}/cancel-deletion"
        )
        res_cancel = await get_current_workspace(req_cancel, supabase=mock_supabase)
        self.assertEqual(res_cancel, self.workspace_id)

    # =========================================================================
    # Test 6: 2FA / MFA Enforcement (Layer 1)
    # =========================================================================
    async def test_2fa_mfa_enforcement(self):
        mock_supabase = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.user_id
        mock_supabase.auth.get_user = AsyncMock(return_value=MagicMock(user=mock_user))

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{
                "id": self.workspace_id,
                "status": "active",
                "require_2fa": True,  # 2FA REQUIRED
                "owner_id": self.user_id
            }])
        )
        mock_supabase.table.return_value = mock_ws_table

        # Case A: AAL1 session rejected with 403 MFA_REQUIRED
        with patch("jwt.decode", return_value={"aal": "aal1"}):
            req_aal1 = self._create_mock_request(
                auth_header="Bearer token_aal1",
                headers={"X-Workspace-Id": self.workspace_id}
            )
            with self.assertRaises(HTTPException) as cm:
                await get_current_workspace(req_aal1, supabase=mock_supabase)
            self.assertEqual(cm.exception.status_code, 403)
            self.assertEqual(cm.exception.detail.get("code"), "MFA_REQUIRED")

        # Case B: AAL2 session passes
        with patch("jwt.decode", return_value={"aal": "aal2"}):
            req_aal2 = self._create_mock_request(
                auth_header="Bearer token_aal2",
                headers={"X-Workspace-Id": self.workspace_id}
            )
            res = await get_current_workspace(req_aal2, supabase=mock_supabase)
            self.assertEqual(res, self.workspace_id)

    # =========================================================================
    # Test 7: Multi-Tenant RBAC Role Verification (Layer 0 & Layer 1)
    # =========================================================================
    async def test_multi_tenant_rbac_roles(self):
        mock_async_client = MagicMock()
        mock_mem = MagicMock()
        mock_ws = MagicMock()

        # Case A: User has 'member' role
        mock_mem.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"role": "member"}])
        )
        mock_async_client.table.return_value = mock_mem

        role = await get_workspace_role(self.workspace_id, self.user_id, supabase=mock_async_client)
        self.assertEqual(role, "member")

        # Case B: require_workspace_role permits admin/owner but blocks member with 403
        role_checker = require_workspace_role(["owner", "admin"])
        with patch("core.backend.api.auth_dep.get_async_service_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_async_client
            with self.assertRaises(HTTPException) as cm:
                await role_checker(workspace_id=self.workspace_id, user_id=self.user_id)
            self.assertEqual(cm.exception.status_code, 403)
            self.assertIn("Action requires one of the following roles: owner, admin", cm.exception.detail)


if __name__ == "__main__":
    unittest.main()
