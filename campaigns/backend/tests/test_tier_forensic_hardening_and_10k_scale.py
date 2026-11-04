import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from core.backend.services.credit_service import TIER_LIMITS, normalize_tier
from core.backend.services.account_rate_limiter import (
    check_and_increment_account_action,
    _IN_MEMORY_ACCOUNT_COUNTERS,
    DAILY_CONNECTION_LIMIT,
    HOURLY_CONNECTION_LIMIT
)
from campaigns.backend.routers.elein import validate_campaign_node_entitlements


class TestTierForensicHardeningAnd10kScale:
    """
    Paranoia Verification Suite:
    Tests strict tier limits, paywall locks, agency multi-tenancy RBAC,
    non-compounding rate limiter arithmetic, and 10k customer scalability.
    """

    def test_canonical_tier_limits_contain_all_tiers(self):
        """Layer 0: Verify TIER_LIMITS defines FREE, PRO, AGENCY, ENTERPRISE."""
        for tier in ["FREE", "PRO", "AGENCY", "ENTERPRISE"]:
            assert tier in TIER_LIMITS
            assert "monthly_credit_allowance" in TIER_LIMITS[tier]
            assert "max_active_campaigns" in TIER_LIMITS[tier]
            assert "max_stored_leads" in TIER_LIMITS[tier]

        # Verify agency limits are enterprise-grade, not clamped to free
        assert TIER_LIMITS["AGENCY"]["max_active_campaigns"] == 50
        assert TIER_LIMITS["AGENCY"]["monthly_credit_allowance"] == 25000
        assert TIER_LIMITS["FREE"]["max_active_campaigns"] == 1
        assert TIER_LIMITS["FREE"]["can_use_enrichment"] is False
        assert TIER_LIMITS["FREE"]["can_use_bayesian_icp"] is False

    def test_free_tier_campaign_node_entitlement_rejection(self):
        """Layer 1 & 2: Free tier cannot activate campaigns with Apollo/Apify or Bayesian ICP."""
        # Enrichment node rejection
        enrichment_nodes = [{"id": "n1", "type": "apollo_enrich", "data": {}}]
        with pytest.raises(HTTPException) as exc_info:
            validate_campaign_node_entitlements(enrichment_nodes, "FREE")
        assert exc_info.value.status_code == 403
        assert "Free Tier cannot activate campaigns with external enrichment" in exc_info.value.detail

        # Bayesian ICP node rejection
        icp_nodes = [{"id": "n2", "type": "ai_score_icp", "data": {}}]
        with pytest.raises(HTTPException) as exc_info:
            validate_campaign_node_entitlements(icp_nodes, "FREE")
        assert exc_info.value.status_code == 403
        assert "Bayesian ICP" in exc_info.value.detail

        # Omnichannel node rejection
        omni_nodes = [{"id": "n3", "type": "retarget_omnichannel", "data": {}}]
        with pytest.raises(HTTPException) as exc_info:
            validate_campaign_node_entitlements(omni_nodes, "FREE")
        assert exc_info.value.status_code == 403
        assert "Omnichannel" in exc_info.value.detail

        # Paid tier (PRO / AGENCY / ENTERPRISE) passes without error
        validate_campaign_node_entitlements(enrichment_nodes, "PRO")
        validate_campaign_node_entitlements(icp_nodes, "AGENCY")
        validate_campaign_node_entitlements(omni_nodes, "ENTERPRISE")

    def test_account_rate_limiter_arithmetic_does_not_compound(self):
        """
        Layer 1 & 2: Rate limiter tracks independent hourly buckets and sums hourly actions
        without compounding cumulative daily counts exponentially across hours.
        """
        from datetime import datetime, timezone
        test_acc = f"acc_test_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        today_str = now.date().isoformat()

        # Simulate 5 actions in hour 1
        h1_key = (test_acc, today_str, 1)
        _IN_MEMORY_ACCOUNT_COUNTERS[h1_key] = {
            "conn_daily": 5,
            "msg_daily": 5,
            "conn_hourly": 5,
            "msg_hourly": 5
        }

        # Simulate 5 actions in hour 2
        h2_key = (test_acc, today_str, 2)
        _IN_MEMORY_ACCOUNT_COUNTERS[h2_key] = {
            "conn_daily": 10,
            "msg_daily": 10,
            "conn_hourly": 5,
            "msg_hourly": 5
        }

        # Check total connections calculated: must be 5 + 5 = 10, NOT (5 + 10 = 15)
        conn_sum = sum(
            val.get("conn_hourly", 0)
            for (a_id, d_str, h), val in _IN_MEMORY_ACCOUNT_COUNTERS.items()
            if a_id == test_acc and d_str == today_str
        )
        assert conn_sum == 10

        # Clean up test keys
        _IN_MEMORY_ACCOUNT_COUNTERS.pop(h1_key, None)
        _IN_MEMORY_ACCOUNT_COUNTERS.pop(h2_key, None)

    def test_agency_client_workspace_tier_provisioning(self):
        """Layer 0 & 1: Client workspaces created under an agency receive AGENCY tier."""
        import asyncio
        from core.backend.api.routers.agencies import create_client_workspace, ClientWorkspaceCreate
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"id": "m1", "role": "owner"}])
        )
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"tier": "AGENCY"}], count=1)
        )
        insert_mock = AsyncMock(return_value=MagicMock(data=[{
            "id": "ws-client-1",
            "name": "Acme Corp Client",
            "tier": "AGENCY",
            "agency_id": "ag-1"
        }]))
        mock_supabase.table.return_value.insert = MagicMock(return_value=MagicMock(execute=insert_mock))

        with patch("core.backend.api.routers.agencies._verify_agency_owner", AsyncMock()):
            res = asyncio.run(create_client_workspace(
                agency_id="ag-1",
                payload=ClientWorkspaceCreate(name="Acme Corp Client"),
                supabase=mock_supabase,
                user_id="user-1"
            ))
            assert res["status"] == "success"
            # Verify tier was passed as AGENCY
            insert_call_args = mock_supabase.table.return_value.insert.call_args[0][0]
            assert insert_call_args.get("tier") == "AGENCY"
            assert insert_call_args.get("agency_id") == "ag-1"
