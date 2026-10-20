import uuid
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from campaigns.backend.services.abm_multithreading_service import (
    _normalize_uuid,
    sanitize_text,
    sanitize_url,
    extract_domain,
    classify_committee_role,
    calculate_account_heat_score,
    generate_role_differentiated_copy,
    list_target_accounts,
    get_account_committee_members,
    create_or_map_target_account,
    add_committee_member,
    update_committee_member_status,
    launch_multithreaded_campaign,
    export_abm_accounts_csv,
    export_abm_committee_csv
)
from campaigns.backend.routers.abm_router import (
    get_target_accounts_endpoint,
    export_accounts_csv_endpoint,
    get_committee_members_endpoint,
    export_committee_csv_endpoint,
    add_committee_member_endpoint,
    update_committee_member_status_endpoint,
    create_account_endpoint,
    launch_multithread_endpoint,
    generate_copy_endpoint,
    get_copy_matrix_endpoint,
    CreateAccountPayload,
    AddCommitteeMemberPayload,
    UpdateCommitteeStatusPayload,
    LaunchMultithreadPayload,
    GenerateCopyPayload
)


class TestAbmDomainAndRoleClassification:
    def test_normalize_uuid_and_sanitization(self):
        norm = _normalize_uuid("acc-stripe", "target_account")
        parsed = uuid.UUID(norm)
        assert str(parsed) == norm

        assert sanitize_text("=CMD|' /C calc'!A0").startswith("'")
        assert sanitize_text("+SUM(A1:A5)").startswith("'")
        assert sanitize_url("javascript:alert(1)") is None
        assert sanitize_url("linkedin.com/in/cfo") == "https://linkedin.com/in/cfo"

    def test_extract_domain_from_various_inputs(self):
        # Email address
        assert extract_domain("alex@stripe.com") == "stripe.com"
        # Full URL with scheme and www and path
        assert extract_domain("https://www.datadoghq.com/pricing/enterprise") == "datadoghq.com"
        # URL with port and query params
        assert extract_domain("http://snowflake.com:8080/app?ref=123") == "snowflake.com"
        # Plain company name fallback
        assert extract_domain("Notion Labs") == "notionlabs.com"
        # None and invalid inputs
        assert extract_domain(None) == "unknown.com"
        assert extract_domain(12345) == "unknown.com"

    def test_classify_committee_role_economic_buyer(self):
        assert classify_committee_role("Chief Financial Officer") == "economic_buyer"
        assert classify_committee_role("Chief Revenue Officer") == "economic_buyer"
        assert classify_committee_role("CEO & Co-founder") == "economic_buyer"
        assert classify_committee_role("VP of Finance") == "economic_buyer"
        assert classify_committee_role("President") == "economic_buyer"

    def test_classify_committee_role_champion(self):
        assert classify_committee_role("VP of Sales") == "champion"
        assert classify_committee_role("Director of Sales") == "champion"
        assert classify_committee_role("Head of Outbound & Pipeline") == "champion"
        assert classify_committee_role("VP Growth") == "champion"
        assert classify_committee_role("Director of Business Development") == "champion"

    def test_classify_committee_role_technical_evaluator(self):
        assert classify_committee_role("Chief Information Security Officer (CISO)") == "technical_evaluator"
        assert classify_committee_role("VP Engineering") == "technical_evaluator"
        assert classify_committee_role("Head of IT & Security") == "technical_evaluator"
        assert classify_committee_role("Chief Technology Officer (CTO)") == "technical_evaluator"
        assert classify_committee_role("Enterprise Security Architect") == "technical_evaluator"

    def test_classify_committee_role_end_user(self):
        assert classify_committee_role("Senior Strategic Account Executive") == "end_user"
        assert classify_committee_role("Sales Development Representative (SDR)") == "end_user"
        assert classify_committee_role("BDR Specialist") == "end_user"
        assert classify_committee_role(None) == "champion"  # Safe default


class TestAbmHeatScoreAndCopyGeneration:
    def test_calculate_account_heat_score_empty(self):
        calc = calculate_account_heat_score([])
        assert calc["heat_score"] == 0
        assert calc["stage"] == "discovery"
        assert calc["engaged_count"] == 0

    def test_calculate_account_heat_score_stages(self):
        # 1 engaged (10 pts) -> discovery/multithreaded boundary
        calc1 = calculate_account_heat_score([{"status": "engaged"}])
        assert calc1["heat_score"] == 10
        assert calc1["stage"] == "discovery"

        # 3 engaged (30 pts) -> multithreaded
        calc2 = calculate_account_heat_score([
            {"status": "engaged"},
            {"status": "engaged"},
            {"status": "engaged"}
        ])
        assert calc2["heat_score"] == 30
        assert calc2["stage"] == "multithreaded"

        # 1 replied (25) + 1 engaged (10) + 1 replied (25) = 60 pts -> consensus_building
        calc3 = calculate_account_heat_score([
            {"status": "replied"},
            {"status": "engaged"},
            {"status": "replied"}
        ])
        assert calc3["heat_score"] == 60
        assert calc3["stage"] == "consensus_building"

        # 1 meeting_booked (40) -> opportunity
        calc4 = calculate_account_heat_score([
            {"status": "meeting_booked"},
            {"status": "replied"}
        ])
        assert calc4["heat_score"] == 65
        assert calc4["stage"] == "opportunity"

    def test_generate_role_differentiated_copy_angles(self):
        # Economic Buyer
        cfo_copy = generate_role_differentiated_copy(
            company_name="Acme Corp",
            prospect_name="Sarah Jenkins",
            title="CFO",
            role_archetype="economic_buyer"
        )
        assert "ROI" in cfo_copy["subject"] or "CAC" in cfo_copy["subject"]
        assert "Sarah" in cfo_copy["body"]
        assert cfo_copy["role_archetype"] == "economic_buyer"
        assert not cfo_copy["cross_thread_aware"]

        # Champion with cross-thread peer
        vps_copy = generate_role_differentiated_copy(
            company_name="Acme Corp",
            prospect_name="David Miller",
            title="VP Sales",
            role_archetype="champion",
            cross_thread_peer="Sarah Jenkins"
        )
        assert "Pipeline Velocity" in cfo_copy["angle"] or "Pipeline Velocity" in vps_copy["angle"]
        assert "Sarah Jenkins" in vps_copy["body"]
        assert vps_copy["cross_thread_aware"] is True

        # Technical Evaluator
        ciso_copy = generate_role_differentiated_copy(
            company_name="Acme Corp",
            prospect_name="Alex Chen",
            title="CISO",
            role_archetype="technical_evaluator"
        )
        assert "SOC2" in ciso_copy["subject"] or "Security" in ciso_copy["subject"]
        assert "residential proxy" in ciso_copy["body"].lower()

        # End User
        ae_copy = generate_role_differentiated_copy(
            company_name="Acme Corp",
            prospect_name="Lisa Wong",
            title="Account Executive",
            role_archetype="end_user"
        )
        assert "prospecting" in ae_copy["subject"].lower()


class TestAbmServiceAndZeroMigrationResilience:
    def test_list_target_accounts_fallback(self):
        # Mock supabase that throws table does not exist
        failing_supabase = MagicMock()
        failing_supabase.table.side_effect = Exception("relation 'target_accounts' does not exist")
        accounts = list_target_accounts("ws-default", supabase=failing_supabase)
        assert len(accounts) >= 3
        # Should include Stripe, Datadog, Snowflake
        names = [a["company_name"] for a in accounts]
        assert any("Stripe" in n for n in names)
        assert all("account_heat_score" in a for a in accounts)

    def test_create_or_map_target_account_with_leads_and_deduplication(self):
        leads = [
            {"name": "Alice Morgan", "title": "CFO", "email": "alice@cloudscale.io"},
            {"name": "Bob Vance", "title": "VP Sales", "email": "bob@cloudscale.io"},
            {"name": "Alice Morgan (Duplicate)", "title": "CFO", "email": "alice@cloudscale.io"}  # Duplicate email
        ]
        res = create_or_map_target_account(
            workspace_id="ws-test",
            company_name="CloudScale Technologies",
            domain="cloudscale.io",
            tier="tier_1",
            leads=leads
        )
        assert res["account"]["company_name"] == "CloudScale Technologies"
        assert res["account"]["domain"] == "cloudscale.io"
        # Deduplication check: 3 input leads with 1 duplicate -> 2 committee members created
        assert res["members_count"] == 2
        roles = [m["role_archetype"] for m in res["committee_members"]]
        assert "economic_buyer" in roles
        assert "champion" in roles

    def test_add_and_update_committee_member_and_csv_exports(self):
        add_res = add_committee_member(
            workspace_id="ws-test",
            account_id="acc-snowflake",
            prospect_name="Claire Sterling",
            title="Chief Information Security Officer",
            email="claire@snowflake.com",
            linkedin_url="linkedin.com/in/claire-sterling"
        )
        assert add_res["deduplicated"] is False
        assert add_res["member"]["role_archetype"] == "technical_evaluator"
        member_id = add_res["member"]["id"]

        # Duplicate check
        dup_res = add_committee_member(
            workspace_id="ws-test",
            account_id="acc-snowflake",
            prospect_name="Claire Sterling",
            title="Chief Information Security Officer",
            email="claire@snowflake.com"
        )
        assert dup_res["deduplicated"] is True

        # Update status to meeting_booked and verify heat score jumps
        upd_res = update_committee_member_status(
            workspace_id="ws-test",
            member_id=member_id,
            status="meeting_booked"
        )
        assert upd_res["member"]["status"] == "meeting_booked"
        assert upd_res["heat_summary"]["heat_score"] >= 40
        assert upd_res["heat_summary"]["stage"] == "opportunity"

        # Invalid status raises ValueError
        with pytest.raises(ValueError):
            update_committee_member_status(workspace_id="ws-test", member_id=member_id, status="invalid_status")

        # Export CSVs
        acc_csv = export_abm_accounts_csv(workspace_id="ws-test")
        assert "Company Name,Domain,Tier" in acc_csv
        assert "Snowflake" in acc_csv

        comm_csv = export_abm_committee_csv(workspace_id="ws-test", account_id="acc-snowflake")
        assert "Prospect Name,Title,Role Archetype" in comm_csv
        assert "Claire Sterling" in comm_csv

    def test_launch_multithreaded_campaign_staggered(self):
        # Launch for Stripe
        res = launch_multithreaded_campaign(
            workspace_id="ws-default",
            account_id="acc-stripe",
            campaign_id="camp-test",
            staggered_interval_hours=4
        )
        assert res["status"] == "active"
        assert res["staggered_interval_hours"] == 4
        assert len(res["schedule"]) > 0
        # Verify staggered schedule offsets
        offsets = [s["stagger_offset_hours"] for s in res["schedule"]]
        assert offsets[0] == 0
        if len(offsets) > 1:
            assert offsets[1] == 4

    def test_launch_multithreaded_campaign_invalid_account(self):
        with pytest.raises(ValueError):
            launch_multithreaded_campaign(
                workspace_id="ws-default",
                account_id="acc-non-existent-999"
            )


class TestAbmEndpoints:
    def test_get_target_accounts_endpoint(self):
        res = get_target_accounts_endpoint(tier=None, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert res["total"] >= 3

    def test_get_committee_members_endpoint(self):
        res = get_committee_members_endpoint("acc-stripe", workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert len(res["members"]) >= 3

    def test_add_and_update_committee_endpoints_and_exports(self):
        add_payload = AddCommitteeMemberPayload(
            prospect_name="Nathan Drake",
            title="VP of Revenue",
            email="nathan@datadoghq.com"
        )
        add_res = add_committee_member_endpoint("acc-datadog", add_payload, workspace_id="ws-test", supabase=None)
        assert add_res["success"] is True
        mem_id = add_res["data"]["member"]["id"]

        upd_payload = UpdateCommitteeStatusPayload(status="replied")
        upd_res = update_committee_member_status_endpoint(mem_id, upd_payload, workspace_id="ws-test", supabase=None)
        assert upd_res["success"] is True
        assert upd_res["data"]["member"]["status"] == "replied"

        acc_csv_resp = export_accounts_csv_endpoint(tier="all", workspace_id="ws-test", supabase=None)
        assert acc_csv_resp.media_type == "text/csv"
        assert "Stripe" in acc_csv_resp.body.decode("utf-8")

        comm_csv_resp = export_committee_csv_endpoint("acc-datadog", workspace_id="ws-test", supabase=None)
        assert comm_csv_resp.media_type == "text/csv"
        assert "Nathan Drake" in comm_csv_resp.body.decode("utf-8")

    def test_free_tier_gated_with_402(self):
        mock_sb = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"tier": "FREE", "balance": 100})
        mock_sb.rpc.return_value = mock_rpc

        with pytest.raises(HTTPException) as exc_info:
            get_target_accounts_endpoint(tier=None, workspace_id="ws-free-prod", supabase=mock_sb)
        assert exc_info.value.status_code == 402

    def test_create_account_endpoint(self):
        payload = CreateAccountPayload(
            company_name="FinOps Systems",
            domain="finops.io",
            tier="tier_2",
            employee_count=450
        )
        res = create_account_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert res["data"]["account"]["company_name"] == "FinOps Systems"

    def test_launch_multithread_endpoint(self):
        payload = LaunchMultithreadPayload(
            account_id="acc-datadog",
            staggered_interval_hours=3
        )
        res = launch_multithread_endpoint(payload, workspace_id="ws-test", supabase=None)
        assert res["success"] is True
        assert res["data"]["staggered_interval_hours"] == 3

    def test_generate_copy_endpoint(self):
        payload = GenerateCopyPayload(
            company_name="Datadog",
            prospect_name="Liam Thorne",
            title="Chief Revenue Officer",
            role_archetype="economic_buyer"
        )
        res = generate_copy_endpoint(payload, workspace_id="ws-test")
        assert res["success"] is True
        assert "ROI" in res["data"]["subject"] or "CAC" in res["data"]["subject"]

    def test_get_copy_matrix_endpoint(self):
        res = get_copy_matrix_endpoint(company_name="Snowflake", workspace_id="ws-test")
        assert res["success"] is True
        assert res["company_name"] == "Snowflake"
        assert len(res["matrix"]) == 4

    def test_free_tier_campaign_activation_blocked_for_abm_nodes(self):
        """Layer 2: Free tier campaign activation is rejected with 403 when abm_multithread_enabled is enabled."""
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace
        from campaigns.backend.routers.elein import get_supabase_client

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        mock_data = [
            {
                "id": "camp-abm-free",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "metadata": {"abm_multithread_enabled": True},
                "nodes_json": [{"type": "message", "data": {"text": "hello"}}],
            }
        ]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = mock_data
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = mock_data

        free_ws_id = "00000000-0000-0000-0000-000000000001"
        app.dependency_overrides[get_current_workspace] = lambda: free_ws_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            resp = client.patch("/api/elein/campaigns/camp-abm-free/activate")
            assert resp.status_code == 403
            assert "ABM Buying Committees" in str(resp.json())
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)


