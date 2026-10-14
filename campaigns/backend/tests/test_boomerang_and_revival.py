import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from campaigns.backend.services.boomerang_revival_service import (
    calculate_boomerang_buying_window,
    generate_warm_intro_bridge,
    evaluate_closed_lost_revival,
    list_champion_job_changes,
    create_champion_job_change,
    list_warm_intro_paths,
    create_warm_intro_path,
    list_closed_lost_revivals,
    create_closed_lost_revival,
    enroll_boomerang_or_revival
)
from campaigns.backend.routers.boomerang_router import (
    get_job_changes_endpoint,
    create_job_change_endpoint,
    get_warm_intros_endpoint,
    create_warm_intro_endpoint,
    get_revivals_endpoint,
    create_revival_endpoint,
    enroll_item_endpoint,
    CreateJobChangePayload,
    CreateWarmIntroPayload,
    CreateRevivalPayload,
    EnrollItemPayload
)


class TestBoomerangBuyingWindow:
    def test_peak_buying_window_past_customer_vp(self):
        res = calculate_boomerang_buying_window(
            prospect_name="Sophia Reynolds",
            previous_company="Twilio",
            previous_title="Director of Sales",
            new_company="Vercel",
            new_title="VP of Global Revenue",
            days_in_new_role=30,
            relationship_type="past_customer"
        )
        assert res["buying_window_score"] >= 90
        assert res["is_internal_promotion"] is False
        assert res["window_tier"] == "PEAK_90_DAY"
        assert "Twilio" in res["playbook_message"]
        assert "Vercel" in res["playbook_message"]

    def test_internal_promotion_detection_paranoia_guard(self):
        # Layer 2 Human Paranoia: Same company name (case-insensitive) -> internal promotion
        res = calculate_boomerang_buying_window(
            prospect_name="David Kim",
            previous_company="Stripe",
            previous_title="Senior Sales Manager",
            new_company="  stripe ",
            new_title="VP of Sales",
            days_in_new_role=14,
            relationship_type="former_champion"
        )
        assert res["is_internal_promotion"] is True
        assert "internal promotion" in res["playbook_message"].lower()

    def test_closed_lost_contact_job_change_playbook(self):
        res = calculate_boomerang_buying_window(
            prospect_name="Alex Mercer",
            previous_company="LegacyCorp",
            previous_title="SDR Manager",
            new_company="NextGen AI",
            new_title="Head of Outbound",
            days_in_new_role=100,
            relationship_type="closed_lost_contact"
        )
        assert res["window_tier"] == "ESTABLISHED"
        assert "timing wasn't quite right" in res["playbook_message"]


class TestWarmIntroReferralGraph:
    def test_generate_warm_intro_bridge_dual_drafts(self):
        res = generate_warm_intro_bridge(
            target_prospect_name="Victor Krum",
            target_company="Anthropic",
            target_title="Head of Enterprise GTM",
            connector_name="Elena Rostova",
            connector_role="VP of RevOps at Stripe",
            bridge_type="shared_investor",
            overlap_context="Index Ventures GTM Board Network"
        )
        assert res["warmth_score"] == 93
        assert "Hi Elena" in res["intro_request_draft"]
        assert "Victor Krum" in res["intro_request_draft"]
        assert "Hi Victor" in res["direct_bridge_draft"]
        assert "Elena Rostova" in res["direct_bridge_draft"]


class TestClosedLostRevivalEngine:
    def test_anti_pestering_cooldown_guard_blocks_premature_revival(self):
        # Layer 2 Human Paranoia: <14 days since lost must raise ValueError
        with pytest.raises(ValueError, match="Anti-Pestering Guard"):
            evaluate_closed_lost_revival(
                prospect_name="Lucas Graham",
                company_name="Notion",
                title="VP Sales",
                lost_reason="budget_freeze",
                days_since_lost=5,
                force_override=False
            )

    def test_anti_pestering_guard_allows_force_override(self):
        res = evaluate_closed_lost_revival(
            prospect_name="Lucas Graham",
            company_name="Notion",
            title="VP Sales",
            lost_reason="budget_freeze",
            days_since_lost=5,
            force_override=True
        )
        assert res["days_since_lost"] == 5
        assert "Notion" in res["resurrection_message"]

    def test_revival_angles_by_lost_reason(self):
        r_feature = evaluate_closed_lost_revival(
            prospect_name="Sarah Connor",
            company_name="Cyberdyne",
            title="CTO",
            lost_reason="missing_feature",
            days_since_lost=120,
            revival_trigger="SOC2 Proxy Isolation Pod"
        )
        assert "SOC2 Proxy Isolation Pod" in r_feature["resurrection_message"]
        assert r_feature["revival_score"] >= 85

        r_comp = evaluate_closed_lost_revival(
            prospect_name="John Doe",
            company_name="Acme",
            title="VP Sales",
            lost_reason="competitor_chosen",
            days_since_lost=160
        )
        assert "renewal" in r_comp["resurrection_message"].lower()


class TestZeroMigrationResilienceAndEndpoints:
    def test_zero_migration_supabase_fallback(self):
        broken_db = MagicMock()
        broken_db.table.side_effect = Exception("relation does not exist")

        jcs = list_champion_job_changes("ws-prod", supabase=broken_db)
        assert len(jcs) >= 3

        wps = list_warm_intro_paths("ws-prod", supabase=broken_db)
        assert len(wps) >= 2

        revs = list_closed_lost_revivals("ws-prod", supabase=broken_db)
        assert len(revs) >= 3

    def test_router_job_changes_crud(self):
        get_res = get_job_changes_endpoint(relationship=None, workspace_id="ws-test", supabase=None)
        assert get_res["success"] is True
        assert get_res["total"] >= 3

        payload = CreateJobChangePayload(
            prospect_name="Claire Underwood",
            previous_company="Snowflake",
            previous_title="VP Sales",
            new_company="Databricks",
            new_title="Chief Revenue Officer",
            relationship_type="past_customer",
            days_in_new_role=25
        )
        post_res = create_job_change_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert post_res["success"] is True
        assert post_res["data"]["new_company"] == "Databricks"
        assert post_res["data"]["buying_window_score"] >= 90

    def test_router_warm_intros_crud(self):
        get_res = get_warm_intros_endpoint(workspace_id="ws-test", supabase=None)
        assert get_res["success"] is True
        assert get_res["total"] >= 2

        payload = CreateWarmIntroPayload(
            target_prospect_name="Sam Altman",
            target_company="OpenAI",
            target_title="CEO",
            connector_name="Reid Hoffman",
            connector_role="Board Partner",
            bridge_type="board_member",
            overlap_context="Early Board Advisory"
        )
        post_res = create_warm_intro_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert post_res["success"] is True
        assert post_res["data"]["warmth_score"] == 96

    def test_router_revivals_and_anti_pestering_http_400(self):
        get_res = get_revivals_endpoint(reason=None, workspace_id="ws-test", supabase=None)
        assert get_res["success"] is True
        assert get_res["total"] >= 3

        # Premature revival (<14 days) should return HTTP 400
        bad_payload = CreateRevivalPayload(
            prospect_name="Too Soon Prospect",
            company_name="FastCo",
            title="VP Sales",
            lost_reason="bad_timing",
            days_since_lost=3
        )
        with pytest.raises(HTTPException) as exc_info:
            create_revival_endpoint(bad_payload, workspace_id="ws-test", supabase=None)
        assert exc_info.value.status_code == 400

        # Valid revival (120 days) succeeds
        good_payload = CreateRevivalPayload(
            prospect_name="Ready Prospect",
            company_name="ScaleCo",
            title="CRO",
            lost_reason="budget_freeze",
            days_since_lost=120,
            original_deal_value=55000
        )
        post_res = create_revival_endpoint(good_payload, workspace_id="ws-test", supabase=None)
        assert post_res["success"] is True
        assert post_res["data"]["original_deal_value"] == 55000

    def test_router_enroll_endpoint(self):
        payload = EnrollItemPayload(item_id="jc-101", item_type="job_change")
        res = enroll_item_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert res["data"]["status"] == "enrolled"

    def test_free_tier_rejection_http_402_on_endpoints(self):
        """Layer 2 Paranoia: Endpoints return HTTP 402 FEATURE_TIER_GATED when workspace is on Free tier."""
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}

        # Test job-changes endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_job_changes_endpoint(relationship=None, workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["error"] == "FEATURE_TIER_GATED"

        # Test warm-intros endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_warm_intros_endpoint(workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # Test revivals endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_revivals_endpoint(reason=None, workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # Test enroll endpoint
        payload = EnrollItemPayload(item_id="jc-101", item_type="job_change")
        with pytest.raises(HTTPException) as exc_info:
            enroll_item_endpoint(payload, workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402

    def test_pro_tier_allowed_on_endpoints(self):
        """Growth Pro and Enterprise workspaces have full access to boomerang endpoints."""
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_sb.table.side_effect = Exception("table not migrated yet")

        # Fallbacks engage smoothly without 402 or 500
        res = get_job_changes_endpoint(relationship=None, workspace_id="00000000-0000-0000-0000-000000000002", supabase=mock_sb)
        assert res["success"] is True
        assert res["total"] >= 3

    def test_free_tier_campaign_activation_blocked_for_boomerang_nodes(self):
        """Layer 2: Free tier campaign activation is rejected with 403 when boomerang revival is enabled."""
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace
        from campaigns.backend.routers.elein import get_supabase_client

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        mock_data = [
            {
                "id": "camp-boom-free",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "metadata": {"boomerang_revival_enabled": True},
            }
        ]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = mock_data
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = mock_data

        free_ws_id = "00000000-0000-0000-0000-000000000001"
        app.dependency_overrides[get_current_workspace] = lambda: free_ws_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            resp = client.patch("/api/elein/campaigns/camp-boom-free/activate")
            assert resp.status_code == 403
            assert "Champion Job-Change Tracker" in str(resp.json())
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)
