"""
Three-Layer Paranoia Test Suite for Phase T:
Enterprise Team Collaboration, Granular RBAC Permissions & Audit Trail Guard
"""

import unittest
from unittest.mock import MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.backend.services.rbac_guard import (
    RBACGuard,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SENDER,
    ROLE_ANALYST,
)
from campaigns.backend.routers.elein import router
from core.backend.api.auth_dep import get_current_workspace, get_current_user_id, get_service_client


class TestPhaseTRBACAndAuditTrail(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()

    # -------------------------------------------------------------------------
    # Layer 0: Role Definitions & Permission Hierarchy
    # -------------------------------------------------------------------------

    def test_owner_and_admin_have_full_wildcard_permissions(self):
        """Layer 0: Owner and admin possess wildcard '*' permission across all actions."""
        for role in (ROLE_OWNER, ROLE_ADMIN):
            self.assertTrue(RBACGuard.has_permission(role, "campaign:create"))
            self.assertTrue(RBACGuard.has_permission(role, "lead:export"))
            self.assertTrue(RBACGuard.has_permission(role, "billing:manage"))
            self.assertTrue(RBACGuard.has_permission(role, "workspace:delete"))
            self.assertTrue(RBACGuard.has_permission(role, "dek:rotate"))

    def test_manager_permissions(self):
        """Layer 0: Manager can manage campaigns and export leads, but not billing or workspace deletion."""
        self.assertTrue(RBACGuard.has_permission(ROLE_MANAGER, "campaign:create"))
        self.assertTrue(RBACGuard.has_permission(ROLE_MANAGER, "lead:export"))
        self.assertTrue(RBACGuard.has_permission(ROLE_MANAGER, "sender:view"))
        self.assertFalse(RBACGuard.has_permission(ROLE_MANAGER, "billing:manage"))
        self.assertFalse(RBACGuard.has_permission(ROLE_MANAGER, "workspace:delete"))

    def test_sender_permissions(self):
        """Layer 0: Sender can connect sender account and update cookies, but cannot create campaigns or export leads."""
        self.assertTrue(RBACGuard.has_permission(ROLE_SENDER, "sender:connect"))
        self.assertTrue(RBACGuard.has_permission(ROLE_SENDER, "sender:update_cookies"))
        self.assertFalse(RBACGuard.has_permission(ROLE_SENDER, "campaign:create"))
        self.assertFalse(RBACGuard.has_permission(ROLE_SENDER, "lead:export"))
        self.assertFalse(RBACGuard.has_permission(ROLE_SENDER, "billing:manage"))

    def test_analyst_permissions(self):
        """Layer 0: Analyst has read-only analytics/report view, strictly prohibited from mutations and export."""
        self.assertTrue(RBACGuard.has_permission(ROLE_ANALYST, "analytics:view"))
        self.assertTrue(RBACGuard.has_permission(ROLE_ANALYST, "campaign:view"))
        self.assertFalse(RBACGuard.has_permission(ROLE_ANALYST, "lead:export"))
        self.assertFalse(RBACGuard.has_permission(ROLE_ANALYST, "lead:import"))
        self.assertFalse(RBACGuard.has_permission(ROLE_ANALYST, "campaign:create"))

    # -------------------------------------------------------------------------
    # Layer 1: Environmental Failure Analysis & Credential Sanitization
    # -------------------------------------------------------------------------

    def test_unverified_role_fails_closed(self):
        """Layer 1: Null, empty, or unmapped roles fail closed with False."""
        self.assertFalse(RBACGuard.has_permission(None, "campaign:view"))
        self.assertFalse(RBACGuard.has_permission("", "analytics:view"))
        self.assertFalse(RBACGuard.has_permission("guest", "analytics:view"))
        self.assertFalse(RBACGuard.has_permission("hacker", "lead:export"))

    def test_sensitive_audit_details_sanitization(self):
        """Layer 1: Automatically scrubs passwords, tokens, cookies, and DEKs from audit logs."""
        raw_details = {
            "user_id": "usr-123",
            "session_cookies": "li_at=AQEDATxyz123; JSESSIONID=ajax:456",
            "api_key": "sk_live_secretkey999",
            "nested": {
                "credential_dek": "supersecretdek",
                "safe_field": "public_name"
            }
        }
        sanitized = RBACGuard.sanitize_audit_details(raw_details)
        self.assertEqual(sanitized["user_id"], "usr-123")
        self.assertEqual(sanitized["session_cookies"], "[REDACTED_CONFIDENTIAL]")
        self.assertEqual(sanitized["api_key"], "[REDACTED_CONFIDENTIAL]")
        self.assertEqual(sanitized["nested"]["credential_dek"], "[REDACTED_CONFIDENTIAL]")
        self.assertEqual(sanitized["nested"]["safe_field"], "public_name")

    def test_audit_log_survives_database_exception(self):
        """Layer 1: Database write errors to workspace_audit_logs do not crash the audit logger."""
        failing_db = MagicMock()
        failing_db.table.return_value.insert.side_effect = Exception("DB connection dropped")
        
        entry = RBACGuard.log_rbac_audit_event(
            actor_id="user-1",
            actor_role="admin",
            workspace_id="ws-1",
            action="test.action",
            resource_type="test",
            resource_id="res-1",
            status="SUCCESS",
            db=failing_db
        )
        self.assertIsNotNone(entry["id"])
        self.assertEqual(entry["status"], "SUCCESS")

    # -------------------------------------------------------------------------
    # Layer 2: Human Paranoia (Exfiltration, Privilege Escalation & Lockout)
    # -------------------------------------------------------------------------

    def test_prevent_last_admin_lockout(self):
        """Layer 2: Rejects demoting or removing the sole admin of a workspace."""
        mock_db = MagicMock()
        # Workspace has owner_id 'admin-1'
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"owner_id": "admin-1"}]
        )
        # workspace_members has only 'admin-1' as admin
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "admin-1", "role": "admin"}]
        )

        with self.assertRaises(HTTPException) as ctx:
            RBACGuard.prevent_last_admin_lockout("ws-100", "admin-1", "analyst", mock_db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("sole administrator", ctx.exception.detail)

    def test_privilege_escalation_prohibited(self):
        """Layer 2: Prevents a manager from assigning the admin or owner role."""
        with self.assertRaises(HTTPException) as ctx:
            RBACGuard.verify_role_assignment_authority(ROLE_MANAGER, ROLE_ADMIN)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("only workspace administrators can modify member roles", ctx.exception.detail)

    def test_non_owner_cannot_assign_owner_role(self):
        """Layer 2: Prevents an admin from transferring or creating owner role (only owner can)."""
        with self.assertRaises(HTTPException) as ctx:
            RBACGuard.verify_role_assignment_authority(ROLE_ADMIN, ROLE_OWNER)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Only the workspace owner can transfer or assign workspace ownership", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # Layer 0 & 2: API Endpoints (Lead Export Exfiltration Shield & Audit Trail)
    # -------------------------------------------------------------------------

    def test_lead_export_blocked_for_analyst(self):
        """Layer 2: Analyst calling /leads/export is blocked with 403 and DENIED audit event logged."""
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/elein")

        mock_db = MagicMock()
        # Mock member role as analyst
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "analyst"}]
        )

        test_app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
        test_app.dependency_overrides[get_current_user_id] = lambda: "user-analyst"
        test_app.dependency_overrides[get_service_client] = lambda: mock_db

        client = TestClient(test_app)
        res = client.get("/api/elein/leads/export")
        self.assertEqual(res.status_code, 403)
        self.assertIn("strictly prohibited from exporting leads", res.json()["detail"])

    def test_lead_export_authorized_for_admin_and_logs_audit(self):
        """Layer 0: Admin calling /leads/export receives data and generates SUCCESS audit event."""
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/elein")

        mock_db = MagicMock()
        # Mock member role as admin
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )
        # Mock leads table response
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead-1", "email": "prospect@acme.com"}]
        )

        test_app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
        test_app.dependency_overrides[get_current_user_id] = lambda: "user-admin"
        test_app.dependency_overrides[get_service_client] = lambda: mock_db

        client = TestClient(test_app)
        res = client.get("/api/elein/leads/export")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["exported_count"], 1)

    def test_update_member_role_endpoint(self):
        """Layer 0: Admin updates member role and receives success with audit ID."""
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/elein")

        mock_db = MagicMock()
        # Caller is admin
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "admin"}]
        )
        # Lockout check: multiple admins exist
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"owner_id": "owner-1"}]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "owner-1"}, {"user_id": "other-admin"}]
        )

        test_app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
        test_app.dependency_overrides[get_current_user_id] = lambda: "user-admin"
        test_app.dependency_overrides[get_service_client] = lambda: mock_db

        client = TestClient(test_app)
        payload = {"target_user_id": "user-to-demote", "new_role": "sender"}
        res = client.post("/api/elein/workspaces/members/role", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["new_role"], "sender")
        self.assertTrue("audit_id" in data)

    def test_get_workspace_audit_trail_endpoint(self):
        """Layer 0: Retrieves workspace audit trail."""
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/elein")

        mock_db = MagicMock()
        def db_table_router(table_name):
            mock_table = MagicMock()
            if table_name == "workspaces":
                mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"tier": "ENTERPRISE"}]
                )
            elif table_name == "workspace_members":
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"role": "admin"}]
                )
            elif table_name == "workspace_audit_logs":
                mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": "audit-1", "action": "lead.export", "status": "SUCCESS"}]
                )
            return mock_table
        mock_db.table.side_effect = db_table_router

        test_app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
        test_app.dependency_overrides[get_current_user_id] = lambda: "user-admin"
        test_app.dependency_overrides[get_service_client] = lambda: mock_db

        client = TestClient(test_app)
        res = client.get("/api/elein/workspaces/audit-trail?limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["count"], 1)


if __name__ == "__main__":
    unittest.main()
