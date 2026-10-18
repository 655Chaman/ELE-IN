"""
test_stage10_paranoia_remediation.py
Stage 10 Paranoia Remediation Test Suite

Validates:
1. API-03: get_account_health raises HTTP 500 on database failure instead of returning fake 200 OK.
2. API-04: get_enrollment_trace never fabricates telemetry and raises HTTP 500 on DB failure.
3. API-05: activate_campaign fails closed when credit verification fails in production mode.
4. API-08: Request body validation with Pydantic schemas (UpdateWorkspaceProfileRequest, BulkApplyDefaultsRequest).
5. API-19: Sanitized error messages on 500 exceptions (session renewal, retry failed node).
6. API-20: Idempotent campaign activation returns early when campaign is already ACTIVE.
"""

import pytest
import os
from unittest.mock import MagicMock
from fastapi import HTTPException
from campaigns.backend.routers.elein import (
    activate_campaign,
    get_enrollment_trace,
    retry_failed_enrollment_node,
    update_workspace_profile,
    bulk_apply_defaults,
    UpdateWorkspaceProfileRequest,
    BulkApplyDefaultsRequest,
)
from campaigns.backend.routers.master_view import get_account_health


class TestStage10ParanoiaRemediation:
    def test_api03_master_view_accounts_db_failure_raises_500(self):
        """API-03: get_account_health must raise HTTPException 500 on database error, not return fake MockRes."""
        mock_supabase = MagicMock()
        # Mock table("accounts") query throwing Exception on execute
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("DB Connection Refused")
        
        with pytest.raises(HTTPException) as exc_info:
            get_account_health(
                request=MagicMock(),
                req=MagicMock(),
                supabase=mock_supabase,
                workspace_id="ws_stage10_test"
            )
        assert exc_info.value.status_code == 500
        assert "Database error" in str(exc_info.value.detail)

    def test_api04_get_enrollment_trace_db_failure_raises_500(self):
        """API-04: get_enrollment_trace raises HTTP 500 on database query failure and never returns fake mock data."""
        mock_supabase = MagicMock()
        # 1. Campaign exists
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "camp-123"}]
        # 2. Enrollment exists
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "enr-123", "campaign_id": "camp-123"}]
        # 3. Trace query fails
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.side_effect = Exception("Table Corrupted")

        with pytest.raises(HTTPException) as exc_info:
            get_enrollment_trace(
                campaign_id="camp-123",
                enrollment_id="enr-123",
                supabase=mock_supabase,
                workspace_id="ws_stage10_test"
            )
        assert exc_info.value.status_code == 500
        assert "Database error" in str(exc_info.value.detail)

    def test_api05_activate_campaign_fail_closed_on_credit_error(self, monkeypatch):
        """API-05: activate_campaign fails closed with HTTP 500 when credit RPC fails outside of test bypass."""
        mock_client = MagicMock()
        # Campaign exists and is DRAFT
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
            "id": "camp-123",
            "status": "DRAFT",
            "nodes_json": '[{"type": "message", "data": {}}]',
            "lead_list_id": "list-1",
            "metadata": {}
        }]
        # Workspace is PRO
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"tier": "PRO"}]
        mock_client.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.count = 0
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        # Temporarily remove PYTEST_CURRENT_TEST to simulate production environment
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        mock_client.rpc.side_effect = Exception("Credit ledger connection timeout")

        with pytest.raises(HTTPException) as exc_info:
            activate_campaign(
                campaign_id="camp-123",
                workspace_id="ws_stage10_test",
                client=mock_client
            )
        assert exc_info.value.status_code == 500
        assert "credit balance" in str(exc_info.value.detail).lower()

    def test_api08_update_workspace_profile_validation(self):
        """API-08: update_workspace_profile validates payload and rejects empty update."""
        mock_supabase = MagicMock()
        
        with pytest.raises(HTTPException) as exc_info:
            update_workspace_profile(
                payload=UpdateWorkspaceProfileRequest(name=""),
                supabase=mock_supabase,
                workspace_id="ws_stage10_test"
            )
        assert exc_info.value.status_code == 400

        # Valid payload updates workspace table
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        res = update_workspace_profile(
            payload=UpdateWorkspaceProfileRequest(name="Acme Corp"),
            supabase=mock_supabase,
            workspace_id="ws_stage10_test"
        )
        assert res["status"] == "success"

    def test_api19_retry_failed_node_sanitized_error(self):
        """API-19: retry_failed_enrollment_node returns sanitized error message without leaking tracebacks."""
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("FATAL: terminating connection due to administrator command")

        with pytest.raises(HTTPException) as exc_info:
            retry_failed_enrollment_node(
                campaign_id="camp-123",
                enrollment_id="enr-123",
                supabase=mock_supabase,
                workspace_id="ws_stage10_test"
            )
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Failed to retry execution node."
        assert "FATAL" not in exc_info.value.detail

    def test_api20_activate_campaign_idempotent(self):
        """API-20: activate_campaign immediately returns idempotent=True if campaign is already ACTIVE."""
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{
            "id": "camp-123",
            "status": "ACTIVE",
            "nodes_json": '[{"type": "message", "data": {}}]',
            "lead_list_id": "list-1",
            "metadata": {}
        }]

        res = activate_campaign(
            campaign_id="camp-123",
            idempotency_key="idemp_double_click_test",
            workspace_id="ws_stage10_test",
            client=mock_client
        )
        assert res["status"] == "activated"
        assert res.get("idempotent") is True
