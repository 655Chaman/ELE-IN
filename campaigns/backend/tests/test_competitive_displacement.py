import pytest
from unittest.mock import MagicMock

from campaigns.backend.services.displacement_service import (
    normalize_vendor_name,
    calculate_migration_savings,
    calculate_displacement_opportunity,
    generate_displacement_battlecard_copy,
    list_competitor_displacements,
    create_competitor_displacement,
    get_vendor_battlecards,
    launch_displacement_sequence
)
from campaigns.backend.routers.displacement_router import (
    get_displacements_endpoint,
    create_displacement_endpoint,
    get_battlecards_endpoint,
    calculate_savings_endpoint,
    generate_pitch_endpoint,
    launch_displacement_endpoint,
    CreateDisplacementPayload,
    SavingsCalculatorPayload,
    GeneratePitchPayload,
    LaunchDisplacementPayload
)


class TestVendorNormalizationAndSavings:
    def test_normalize_vendor_name_variations(self):
        assert normalize_vendor_name("Apollo.io") == "apollo"
        assert normalize_vendor_name("  out-reach  ") == "outreach"
        assert normalize_vendor_name("Sales Loft") == "salesloft"
        assert normalize_vendor_name("LemList") == "lemlist"
        assert normalize_vendor_name("Expandi.co") == "expandi"
        assert normalize_vendor_name("Hey Reach") == "heyreach"
        assert normalize_vendor_name("RandomToolXYZ") == "other"
        assert normalize_vendor_name(None) == "apollo"  # Default fallback

    def test_calculate_migration_savings_outreach(self):
        # 10 seats of Outreach ($140/seat/mo) vs Ele-in ($49/seat/mo)
        # Annual Outreach = 10 * 140 * 12 = $16,800
        # Annual Ele-in = 10 * 49 * 12 = $5,880
        # Annual Net Savings = $10,920 (65.0%)
        res = calculate_migration_savings(vendor_slug="outreach", seat_count=10)
        assert res["annual_incumbent_spend"] == 16800.0
        assert res["annual_elein_spend"] == 5880.0
        assert res["annual_net_savings"] == 10920.0
        assert res["savings_percentage"] == 65.0

    def test_calculate_migration_savings_bounds_clamping(self):
        # Layer 2 Human Paranoia: seat counts clamped between 1 and 5000
        res_min = calculate_migration_savings("apollo", seat_count=-5)
        assert res_min["seat_count"] == 1

        res_max = calculate_migration_savings("apollo", seat_count=99999)
        assert res_max["seat_count"] == 5000


class TestDisplacementScoringAndCopy:
    def test_calculate_displacement_opportunity_peak_window(self):
        # 60 days to renewal = PEAK_EVALUATION window (45-90d)
        res = calculate_displacement_opportunity(
            incumbent_vendor="apollo",
            contract_renewal_days=60,
            seat_count=20,
            target_company="Acme Corp"
        )
        assert res["window_status"] == "PEAK_EVALUATION"
        assert res["displacement_vulnerability_score"] >= 90
        assert res["annual_potential_savings"] > 0

    def test_calculate_displacement_opportunity_early_contract(self):
        # 250 days to renewal = EARLY_CONTRACT window
        res = calculate_displacement_opportunity(
            incumbent_vendor="lemlist",
            contract_renewal_days=250,
            seat_count=5,
            target_company="Acme Corp"
        )
        assert res["window_status"] == "EARLY_CONTRACT"
        assert res["displacement_vulnerability_score"] < 80

    def test_generate_displacement_copy_diplomacy_and_buyout(self):
        copy_res = generate_displacement_battlecard_copy(
            incumbent_vendor="outreach",
            target_company="Datadog",
            target_contact_name="Arthur Pendelton",
            target_contact_title="VP RevOps",
            seat_count=15,
            renewal_days=60,
            annual_savings=16380.0
        )
        assert "Outreach" in copy_res["subject"]
        assert "Arthur" in copy_res["body"]
        assert "credit" in copy_res["body"].lower()
        assert "60 days" in copy_res["body"]
        assert "$16,380" in copy_res["body"]
        assert "contract buyout credit" in copy_res["body"].lower()


class TestDisplacementZeroMigrationAndEndpoints:
    def test_zero_migration_supabase_fallback(self):
        failing_db = MagicMock()
        failing_db.table.side_effect = Exception("table does not exist")

        disps = list_competitor_displacements("ws-test", supabase=failing_db)
        assert len(disps) >= 3

        cards = get_vendor_battlecards("ws-test", supabase=failing_db)
        assert len(cards) >= 5

    def test_router_displacements_crud(self):
        get_res = get_displacements_endpoint(vendor=None, workspace_id="ws-test", supabase=None)
        assert get_res["success"] is True
        assert get_res["total"] >= 3

        payload = CreateDisplacementPayload(
            target_company="Brex",
            target_contact_name="Elena Vance",
            target_contact_title="CRO",
            incumbent_vendor="salesloft",
            seat_count=20,
            contract_renewal_days=50
        )
        post_res = create_displacement_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert post_res["success"] is True
        assert post_res["data"]["incumbent_vendor"] == "salesloft"
        assert post_res["data"]["displacement_vulnerability_score"] >= 85

    def test_router_battlecards_endpoint(self):
        res = get_battlecards_endpoint(vendor="apollo", workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert len(res["battlecards"]) >= 1
        assert res["battlecards"][0]["vendor_slug"] == "apollo"

    def test_router_savings_calculator_endpoint(self):
        payload = SavingsCalculatorPayload(
            incumbent_vendor="outreach",
            seat_count=12,
            custom_monthly_cost_per_seat=150.0
        )
        res = calculate_savings_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert res["data"]["annual_net_savings"] > 14000.0

    def test_router_generate_pitch_endpoint(self):
        payload = GeneratePitchPayload(
            incumbent_vendor="apollo",
            target_company="Ramp",
            target_contact_name="Samantha Wu",
            target_contact_title="Head of SDRs",
            seat_count=10,
            renewal_days=45
        )
        res = generate_pitch_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert "Apollo.io" in res["data"]["subject"]
        assert "waterfall" in res["data"]["displacement_hook"].lower()

    def test_router_launch_endpoint(self):
        payload = LaunchDisplacementPayload(displacement_id="disp-101")
        res = launch_displacement_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert res["data"]["status"] == "launched"

    def test_free_tier_rejection_http_402_on_displacement_endpoints(self):
        """Layer 2 Paranoia: Endpoints return HTTP 402 FEATURE_TIER_GATED when workspace is on Free tier."""
        from fastapi import HTTPException
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}

        # Test opportunities GET endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_displacements_endpoint(vendor=None, workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["error"] == "FEATURE_TIER_GATED"

        # Test battlecards endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_battlecards_endpoint(vendor="apollo", workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # Test savings calculator endpoint
        calc_payload = SavingsCalculatorPayload(incumbent_vendor="outreach", seat_count=10)
        with pytest.raises(HTTPException) as exc_info:
            calculate_savings_endpoint(calc_payload, workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # Test launch endpoint
        launch_payload = LaunchDisplacementPayload(displacement_id="disp-101")
        with pytest.raises(HTTPException) as exc_info:
            launch_displacement_endpoint(launch_payload, workspace_id="00000000-0000-0000-0000-000000000001", supabase=mock_sb)
        assert exc_info.value.status_code == 402

    def test_pro_tier_allowed_on_displacement_endpoints(self):
        """Growth Pro and Enterprise workspaces have full access to displacement endpoints."""
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_sb.table.side_effect = Exception("table not migrated yet")

        res = get_displacements_endpoint(vendor=None, workspace_id="00000000-0000-0000-0000-000000000002", supabase=mock_sb)
        assert res["success"] is True
        assert res["total"] >= 3

    def test_free_tier_campaign_activation_blocked_for_displacement_nodes(self):
        """Layer 2: Free tier campaign activation is rejected with 403 when competitive displacement is enabled."""
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace
        from campaigns.backend.routers.elein import get_supabase_client

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        mock_data = [
            {
                "id": "camp-disp-free",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "nodes_json": [{"type": "message", "data": {"text": "hello"}}],
                "metadata": {"competitive_displacement_enabled": True},
            }
        ]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = mock_data
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = mock_data

        free_ws_id = "00000000-0000-0000-0000-000000000001"
        app.dependency_overrides[get_current_workspace] = lambda: free_ws_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            resp = client.patch("/api/elein/campaigns/camp-disp-free/activate")
            assert resp.status_code == 403
            assert "Autonomous Competitive Displacement" in str(resp.json())
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)
