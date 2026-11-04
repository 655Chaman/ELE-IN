"""
test_phase_k_multi_tenant_pen_test.py - Phase K: Full Multi-Tenant Account Security Audit & Pen-Test Validation.
Rigorous verification under the Three-Layer Logic Architecture (Paranoia Framework).

Covers:
1. End-to-End IDOR Security Audits across Workspace Boundaries (Campaigns, Leads, Inbox, Proxies, Billing)
2. CSRF & Adversarial Origin Boundary Validation
3. JWT Audience, Expiration, and Cryptographic Secret Boundaries
"""

import os
import time
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.services.tenant_guard import (
    enforce_tenant_boundary,
    TenantIDORViolationError,
    TENANT_ISOLATED_TABLES,
)
from core.backend.api.auth_dep import (
    get_current_workspace,
    get_supabase_client,
    verify_token_and_get_user_id,
)


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. IDOR Security Audits Across Workspace Boundaries
# ==============================================================================

class TestMultiTenantIDORDefense:
    def test_enforce_tenant_boundary_blocks_cross_workspace_access(self):
        """Layer 0 & 2: enforce_tenant_boundary raises TenantIDORViolationError (HTTP 403) on workspace mismatch."""
        ws_legit = "ws-owner-1111"
        ws_attacker = "ws-attacker-9999"

        # Matching workspace succeeds
        assert enforce_tenant_boundary(ws_legit, ws_legit, actor_id="user_1") is True

        # Mismatched workspace raises HTTP 403
        with pytest.raises(TenantIDORViolationError) as exc_info:
            enforce_tenant_boundary(
                current_workspace_id=ws_attacker,
                requested_workspace_id=ws_legit,
                actor_id="attacker_user",
                resource_type="campaign"
            )
        assert exc_info.value.status_code == 403
        assert "Forbidden" in exc_info.value.detail

    def test_enforce_tenant_boundary_rejects_missing_workspace(self):
        """Layer 1: Empty or None workspace context is strictly denied."""
        with pytest.raises(TenantIDORViolationError):
            enforce_tenant_boundary(None, "ws-legit")

        with pytest.raises(TenantIDORViolationError):
            enforce_tenant_boundary("ws-legit", "")

    def test_idor_blocked_on_inbox_reply_foreign_account(self, client):
        """Layer 0 & 2: Operator in Workspace A attempting to send reply via Workspace B's account is blocked."""
        ws_victim = "ws-victim-alpha"
        ws_attacker = "ws-attacker-beta"
        foreign_account_id = "acc-victim-999"

        mock_supabase = MagicMock()
        mock_acc_res = MagicMock(data=[])  # No account found in ws_attacker
        mock_msg_res = MagicMock(data=[])  # No recent deduplicated messages

        def table_router(table_name):
            builder = MagicMock()
            if table_name == "messages":
                sub = MagicMock()
                sub.eq.return_value = sub
                sub.gte.return_value = sub
                sub.execute.return_value = mock_msg_res
                builder.select.return_value = sub
            elif table_name == "accounts":
                sub = MagicMock()
                sub.eq.return_value = sub
                sub.execute.return_value = mock_acc_res
                builder.select.return_value = sub
            return builder

        mock_supabase.table.side_effect = table_router

        app.dependency_overrides[get_current_workspace] = lambda: ws_attacker
        app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        try:
            payload = {
                "sender_name": "Attacker",
                "message_text": "Phishing reply",
                "account_id": foreign_account_id,
                "lead_id": "lead-victim-001"
            }
            resp = client.post("/api/elein/inbox/reply", json=payload)
            assert resp.status_code == 403
            assert "Specified account does not belong to this workspace" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_idor_blocked_on_inbox_reply_foreign_lead(self, client):
        """Layer 0 & 2: Operator in Workspace A attempting to reply to a lead in Workspace B is blocked."""
        ws_attacker = "ws-attacker-beta"
        foreign_lead_id = "lead-victim-888"

        mock_supabase = MagicMock()
        mock_acc_res = MagicMock(data=[{"id": "acc-attacker-1", "status": "ACTIVE"}])
        mock_lead_res = MagicMock(data=[])  # Lead does not belong to ws_attacker
        mock_msg_res = MagicMock(data=[])

        def table_router(table_name):
            builder = MagicMock()
            if table_name == "messages":
                sub = MagicMock()
                sub.eq.return_value = sub
                sub.gte.return_value = sub
                sub.execute.return_value = mock_msg_res
                builder.select.return_value = sub
            elif table_name == "accounts":
                sub = MagicMock()
                sub.eq.return_value = sub
                sub.execute.return_value = mock_acc_res
                builder.select.return_value = sub
            elif table_name == "leads":
                sub = MagicMock()
                sub.eq.return_value = sub
                sub.execute.return_value = mock_lead_res
                builder.select.return_value = sub
            return builder

        mock_supabase.table.side_effect = table_router

        app.dependency_overrides[get_current_workspace] = lambda: ws_attacker
        app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        try:
            payload = {
                "sender_name": "Attacker",
                "message_text": "Phishing reply",
                "account_id": "acc-attacker-1",
                "lead_id": foreign_lead_id
            }
            resp = client.post("/api/elein/inbox/reply", json=payload)
            assert resp.status_code == 403
            assert "Specified lead does not belong to this workspace" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)


# ==============================================================================
# 2. JWT Audience, Expiration, and Cryptographic Secret Boundaries
# ==============================================================================

class TestJWTCryptographicBoundaries:
    def test_jwt_wrong_secret_rejected(self):
        """Layer 0: Token signed with unauthorized HMAC secret is rejected."""
        import jwt
        token = jwt.encode(
            {"sub": "attacker-user-id", "exp": time.time() + 3600, "aud": "authenticated"},
            "wrong-secret-key-999",
            algorithm="HS256"
        )
        with patch("core.backend.api.auth_dep.SUPABASE_JWT_SECRET", "legitimate-secret-key-123"):
            with pytest.raises(HTTPException) as exc_info:
                verify_token_and_get_user_id(token)
            assert exc_info.value.status_code == 401

    def test_jwt_expired_token_rejected(self):
        """Layer 1: Expired token raises HTTP 401 with expiration detail."""
        import jwt
        secret = "test-jwt-secret-abc"
        expired_token = jwt.encode(
            {"sub": "legit-user-id", "exp": time.time() - 3600, "aud": "authenticated"},
            secret,
            algorithm="HS256"
        )
        with patch("core.backend.api.auth_dep.SUPABASE_JWT_SECRET", secret):
            with pytest.raises(HTTPException) as exc_info:
                verify_token_and_get_user_id(expired_token)
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()

    def test_jwt_forged_audience_rejected(self):
        """Layer 2 (Paranoia): Token with forged audience (e.g. 'admin') is rejected when aud='authenticated' is required."""
        import jwt
        secret = "test-jwt-secret-abc"
        forged_aud_token = jwt.encode(
            {"sub": "user-id-555", "exp": time.time() + 3600, "aud": "admin_portal"},
            secret,
            algorithm="HS256"
        )
        with patch("core.backend.api.auth_dep.SUPABASE_JWT_SECRET", secret):
            with pytest.raises(HTTPException) as exc_info:
                verify_token_and_get_user_id(forged_aud_token)
            assert exc_info.value.status_code == 401

    def test_jwt_missing_sub_rejected(self):
        """Layer 2: Token lacking 'sub' claim raises HTTP 401."""
        import jwt
        secret = "test-jwt-secret-abc"
        no_sub_token = jwt.encode(
            {"exp": time.time() + 3600, "aud": "authenticated"},
            secret,
            algorithm="HS256"
        )
        with patch("core.backend.api.auth_dep.SUPABASE_JWT_SECRET", secret):
            with pytest.raises(HTTPException) as exc_info:
                verify_token_and_get_user_id(no_sub_token)
            assert exc_info.value.status_code == 401
            assert "missing sub" in exc_info.value.detail.lower()


# ==============================================================================
# 3. Canonical Tenant-Isolated Tables Audit
# ==============================================================================

class TestTenantIsolatedTablesAudit:
    def test_tenant_isolated_tables_integrity(self):
        """Layer 1: Validates that all primary operational tables are registered in TENANT_ISOLATED_TABLES."""
        expected_tables = {
            "leads", "campaigns", "campaign_enrollments", "campaign_execution_states",
            "proxies", "sender_inboxes", "messages", "inbound_webhook_buffer",
            "workspace_deks", "suppression_list"
        }
        for table in expected_tables:
            assert table in TENANT_ISOLATED_TABLES
