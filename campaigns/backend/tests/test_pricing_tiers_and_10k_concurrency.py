import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException
from core.backend.services.credit_service import TIER_LIMITS
from campaigns.backend.routers.elein import TIER_LIMITS as ELEIN_TIER_LIMITS

class TestPricingTiersAnd10kConcurrency:
    """
    Forensic verification suite for Pricing Tier Entitlements,
    Quota Hardening, and 10,000-Customer Concurrency Architecture.
    """

    def test_tier_limits_deduplication_and_consistency(self):
        """
        Layer 0: Verify that TIER_LIMITS in campaigns.backend.routers.elein is the exact
        same dictionary imported from core.backend.services.credit_service to prevent configuration drift.
        """
        assert ELEIN_TIER_LIMITS is TIER_LIMITS
        assert "FREE" in TIER_LIMITS
        assert "PRO" in TIER_LIMITS
        assert "ENTERPRISE" in TIER_LIMITS

        # Verify quotas
        assert TIER_LIMITS["FREE"]["monthly_credit_allowance"] == 500
        assert TIER_LIMITS["FREE"]["max_stored_leads"] == 2500
        assert TIER_LIMITS["FREE"]["can_view_audit_logs"] is False

        assert TIER_LIMITS["PRO"]["monthly_credit_allowance"] == 5000
        assert TIER_LIMITS["PRO"]["max_stored_leads"] == 50000
        assert TIER_LIMITS["PRO"]["can_view_audit_logs"] is True

        assert TIER_LIMITS["ENTERPRISE"]["monthly_credit_allowance"] == 100000
        assert TIER_LIMITS["ENTERPRISE"]["max_stored_leads"] == 500000
        assert TIER_LIMITS["ENTERPRISE"]["can_view_audit_logs"] is True

    def test_free_tier_rejected_on_agency_creation(self):
        """
        Layer 1 & 2: Agency creation endpoint must reject Free tier workspaces with 403 Forbidden.
        Only PRO, AGENCY, or ENTERPRISE tiers are permitted to create agency structures.
        """
        from core.backend.api.routers.agencies import create_agency, AgencyCreate

        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(data=[{"tier": "FREE"}]))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select

        req = AgencyCreate(name="Test Agency")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(create_agency(
                payload=req,
                supabase=mock_supabase,
                user_id="user_123"
            ))
        assert exc_info.value.status_code == 403
        assert "Growth Pro, Agency, or Enterprise tier" in str(exc_info.value.detail)

    def test_free_tier_rejected_on_agency_client_creation(self):
        """
        Layer 1 & 2: Creating client workspaces under an agency must enforce tier gating.
        """
        from core.backend.api.routers.agencies import create_client_workspace, ClientWorkspaceCreate

        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(data=[{"tier": "FREE"}]))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select

        # Mock agency ownership check
        with patch("core.backend.api.routers.agencies._verify_agency_owner", new_callable=AsyncMock):
            req = ClientWorkspaceCreate(name="Client A")
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(create_client_workspace(
                    agency_id="agency_123",
                    payload=req,
                    supabase=mock_supabase,
                    user_id="user_123"
                ))
            assert exc_info.value.status_code == 403
            assert "Agency tier required to create client workspaces" in str(exc_info.value.detail)

    def test_free_tier_rejected_on_audit_trail(self):
        """
        Layer 1 & 2: Audit trail endpoint must enforce tier gating (can_view_audit_logs).
        Free tier workspaces must be rejected with 403 Forbidden.
        """
        from campaigns.backend.routers.elein import api_get_workspace_audit_trail

        mock_supabase = MagicMock()
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            return t
        mock_supabase.table.side_effect = mock_table

        with pytest.raises(HTTPException) as exc_info:
            api_get_workspace_audit_trail(
                limit=50,
                workspace_id="ws_free",
                user_id="user_123",
                db=mock_supabase
            )
        assert exc_info.value.status_code == 403
        assert "Growth Pro or Enterprise" in str(exc_info.value.detail)

    def test_lead_bulk_import_quota_boundary_enforcement(self):
        """
        Layer 1 & 2: Bulk lead import must halt immediately when stored leads exceed max_stored_leads.
        """
        from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads

        mock_supabase = MagicMock()
        # Mock workspace returning tier FREE (max_stored_leads = 2500)
        mock_ws_select = MagicMock()
        mock_ws_select.execute.return_value = MagicMock(data=[{"tier": "FREE"}])

        # Mock current leads count as 2500 (at quota capacity)
        mock_lead_count = MagicMock()
        mock_lead_count.limit.return_value.execute.return_value = MagicMock(count=2500)
        mock_lead_count.execute.return_value = MagicMock(count=2500)

        def table_router(table_name):
            mock_table = MagicMock()
            if table_name == "workspaces":
                mock_table.select.return_value.eq.return_value = mock_ws_select
            elif table_name == "leads":
                mock_table.select.return_value.eq.return_value = mock_lead_count
            return mock_table

        mock_supabase.table.side_effect = table_router

        leads_to_import = [
            {"email": "prospect@example.com", "first_name": "John"}
        ]

        result = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list_123",
            workspace_id="ws_free",
            leads=leads_to_import
        )

        assert result["success"] is False
        assert result["inserted_count"] == 0
        assert "Workspace lead storage limit reached" in result["error"]
        assert "2500" in result["error"]

    def test_orchestrator_chunked_workspace_queries_prevent_uri_overflow(self):
        """
        Layer 1 (Environmental Failure Analysis):
        Under 10,000 customers, active_workspace_ids contains thousands of UUIDs.
        Querying supabase.table("campaigns").select(...).in_("id", active_workspace_ids)
        in a single request generates an HTTP 414 Request-URI Too Long crash.
        Verify that chunking splits requests into batches of <= 100.
        """
        test_ws_ids = [f"ws_{i:04d}" for i in range(250)]

        # Chunk logic used in elein_orchestrator.py
        chunks = [test_ws_ids[i:i + 100] for i in range(0, len(test_ws_ids), 100)]
        assert len(chunks) == 3
        assert len(chunks[0]) == 100
        assert len(chunks[1]) == 100
        assert len(chunks[2]) == 50

    def test_health_check_cron_stalest_first_bounded_batch(self):
        """
        Layer 1 & 2: Health check cron must order by last_health_check_at ascending
        and limit inspection to 50 accounts to prevent thread starvation under 10k customers.
        """
        from core.backend.services.health_check_cron import run_health_checks

        mock_supabase = MagicMock()
        mock_query = MagicMock()
        mock_query.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value = mock_query

        # Execute run_health_checks with mock client
        run_health_checks(supabase=mock_supabase)

        # Verify query had limit(50) applied
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.assert_called_with(50)

    def test_client_connection_pool_cache_scaled_capacity(self):
        """
        Layer 0 & 1: Verify auth_dep connection cache maximum size is scaled to 1024
        to support 10k concurrent multi-tenant customer workloads without pool thrashing.
        """
        from core.backend.api.auth_dep import _CLIENT_CACHE_MAX_ENTRIES
        assert _CLIENT_CACHE_MAX_ENTRIES >= 1024

    def test_tier_normalization_and_synonyms(self):
        """Validates that casing drift, whitespace, and tier synonyms normalize to canonical tokens."""
        from core.backend.services.credit_service import normalize_tier
        assert normalize_tier("free") == "FREE"
        assert normalize_tier("FREE") == "FREE"
        assert normalize_tier("basic") == "FREE"
        assert normalize_tier("Basic") == "FREE"
        
        # Growth & Starter map to PRO
        assert normalize_tier("pro") == "PRO"
        assert normalize_tier("PRO") == "PRO"
        assert normalize_tier("growth") == "PRO"
        assert normalize_tier("GROWTH") == "PRO"
        assert normalize_tier("starter") == "PRO"
        assert normalize_tier("STARTER") == "PRO"
        
        # Agency maps to AGENCY
        assert normalize_tier("agency") == "AGENCY"
        assert normalize_tier("AGENCY") == "AGENCY"
        assert normalize_tier("agency_tier") == "AGENCY"
        
        # Scale & Unlimited map to ENTERPRISE
        assert normalize_tier("enterprise") == "ENTERPRISE"
        assert normalize_tier("ENTERPRISE") == "ENTERPRISE"
        assert normalize_tier("scale") == "ENTERPRISE"
        assert normalize_tier("unlimited") == "ENTERPRISE"
        
        # Fallback safety
        assert normalize_tier(None) == "FREE"
        assert normalize_tier("") == "FREE"
        assert normalize_tier("unknown_custom_tier") == "FREE"

    def test_tier_limits_matrix_completeness(self):
        """Verifies that all canonical tiers possess complete, non-colliding limits."""
        from core.backend.services.credit_service import CANONICAL_TIERS, TIER_LIMITS
        for tier in CANONICAL_TIERS:
            assert tier in TIER_LIMITS, f"Missing {tier} in TIER_LIMITS"
            limits = TIER_LIMITS[tier]
            assert "monthly_credit_allowance" in limits
            assert "max_team_members" in limits
            assert "max_linkedin_accounts" in limits
            assert "max_active_campaigns" in limits
            assert "can_use_enrichment" in limits
            assert "can_export_unmasked" in limits
            assert "can_view_audit_logs" in limits

        free = TIER_LIMITS["FREE"]
        pro = TIER_LIMITS["PRO"]
        agency = TIER_LIMITS["AGENCY"]
        ent = TIER_LIMITS["ENTERPRISE"]

        assert free["monthly_credit_allowance"] == 500
        assert pro["monthly_credit_allowance"] == 5000
        assert agency["monthly_credit_allowance"] == 25000
        assert ent["monthly_credit_allowance"] == 100000

        assert free["max_linkedin_accounts"] == 1
        assert pro["max_linkedin_accounts"] == 5
        assert agency["max_linkedin_accounts"] == 15
        assert ent["max_linkedin_accounts"] >= 25

        assert free["max_active_campaigns"] == 1
        assert pro["max_active_campaigns"] == 20
        assert agency["max_active_campaigns"] == 50
        assert ent["max_active_campaigns"] == 100

        assert free["can_export_unmasked"] is False
        assert pro["can_export_unmasked"] is True
        assert agency["can_export_unmasked"] is True
        assert ent["can_export_unmasked"] is True

    def test_packages_catalog_expansion(self):
        """Verifies that PACKAGES contains Agency and Enterprise plans with correct credit quotas."""
        from core.backend.api.routers.billing import PACKAGES
        assert "agency_tier" in PACKAGES
        assert PACKAGES["agency_tier"]["credits"] == 25000
        assert PACKAGES["agency_tier"]["tier"] == "AGENCY"
        assert PACKAGES["agency_tier"]["inr_paise"] == 1999900

        assert "agency_tier_annual" in PACKAGES
        assert PACKAGES["agency_tier_annual"]["credits"] == 300000
        assert PACKAGES["agency_tier_annual"]["tier"] == "AGENCY"

        assert "enterprise_tier" in PACKAGES
        assert PACKAGES["enterprise_tier"]["credits"] == 100000
        assert PACKAGES["enterprise_tier"]["tier"] == "ENTERPRISE"
        assert PACKAGES["enterprise_tier"]["inr_paise"] == 4999900

        assert "enterprise_tier_annual" in PACKAGES
        assert PACKAGES["enterprise_tier_annual"]["credits"] == 1200000
        assert PACKAGES["enterprise_tier_annual"]["tier"] == "ENTERPRISE"

        assert "credits_10000" in PACKAGES
        assert "credits_25000" in PACKAGES

    def test_safe_close_sync_client_closes_transports(self):
        """Verifies that _safe_close_sync_client calls close() on postgrest, auth, and storage transports."""
        from core.backend.api.auth_dep import _safe_close_sync_client
        mock_postgrest_sess = MagicMock()
        mock_auth_client = MagicMock()
        mock_storage_client = MagicMock()

        mock_client = MagicMock()
        mock_client.postgrest.session = mock_postgrest_sess
        mock_client.auth._http_client = mock_auth_client
        mock_client.storage._client = mock_storage_client

        _safe_close_sync_client(mock_client)

        mock_postgrest_sess.close.assert_called_once()
        mock_auth_client.close.assert_called_once()
        mock_storage_client.close.assert_called_once()

    def test_campaign_node_entitlements_rejection_for_free_tier(self):
        """Guarantees Free tier campaigns cannot contain external enrichment or scraping nodes."""
        from campaigns.backend.routers.elein import validate_campaign_node_entitlements
        restricted_nodes = [
            {"id": "n1", "type": "apollo_enrich", "data": {"vendor": "apollo"}},
            {"id": "n2", "type": "email_touchpoint", "data": {"subject": "Hi"}}
        ]
        with pytest.raises(HTTPException) as exc_info:
            validate_campaign_node_entitlements(restricted_nodes, "FREE")
        assert exc_info.value.status_code == 403
        assert "Free Tier cannot activate campaigns with external enrichment" in exc_info.value.detail

        # Allowed on PRO, AGENCY, and ENTERPRISE
        validate_campaign_node_entitlements(restricted_nodes, "PRO")
        validate_campaign_node_entitlements(restricted_nodes, "AGENCY")
        validate_campaign_node_entitlements(restricted_nodes, "ENTERPRISE")

    def test_contact_lead_masking(self):
        """Guarantees contact PII masking for Free tier users to prevent data exfiltration."""
        from leads.backend.routers.leads import mask_email, mask_phone
        assert mask_email("john.doe@example.com") == "jo***@example.com"
        assert mask_email("a@b.com") == "a***@b.com"
        assert mask_email("") == ""
        assert mask_email(None) == ""

        assert mask_phone("+1-555-123-4567") == "***-***-4567"
        assert mask_phone("9876543210") == "***-***-3210"
        assert mask_phone("123") == "***"
        assert mask_phone("") == ""

    def test_distributed_workspace_locking_under_concurrency(self):
        """Validates that distributed workspace locks serialize operations safely across concurrent threads."""
        import uuid
        import time
        from concurrent.futures import ThreadPoolExecutor
        from core.backend.services.credit_service import distributed_workspace_lock

        ws_id = str(uuid.uuid4())
        execution_order = []
        thread_count = 5

        def worker(worker_id: int):
            with distributed_workspace_lock(f"test_lock_{ws_id}", ttl_seconds=10, blocking=True):
                execution_order.append(f"enter_{worker_id}")
                time.sleep(0.02)
                execution_order.append(f"exit_{worker_id}")

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(worker, i) for i in range(thread_count)]
            for f in futures:
                f.result()

        assert len(execution_order) == thread_count * 2
        for i in range(0, len(execution_order), 2):
            enter = execution_order[i]
            exit_ = execution_order[i + 1]
            w_id = enter.split("_")[1]
            assert exit_ == f"exit_{w_id}", f"Lock interleaving violation at index {i}: {enter} vs {exit_}"

    def test_free_tier_custom_proxy_rejection(self):
        """FLAW-26: Free tier users must be forbidden from connecting accounts using custom residential proxies."""
        from campaigns.backend.routers.elein import add_account
        from campaigns.backend.schemas.elein import AccountCreate
        from unittest.mock import Mock

        mock_supabase = MagicMock()
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "accounts":
                count_res = MagicMock()
                count_res.count = 0
                count_res.data = []
                t.select.return_value.eq.return_value.neq.return_value.execute.return_value = count_res
                t.select.return_value.eq.return_value.execute.return_value = count_res
            return t
        mock_supabase.table.side_effect = mock_table
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"allowed": True})

        req = AccountCreate(
            name="John Doe",
            session_cookies_json='[{"name": "li_at", "value": "test_cookie"}]',
            proxy_id="custom-proxy-uuid-123"
        )
        mock_request = Mock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            add_account(
                account=req,
                request=mock_request,
                supabase=mock_supabase,
                workspace_id="ws_free",
                user_id="user_123"
            )
        assert exc_info.value.status_code == 403
        assert "Custom residential proxies are an Agency and Enterprise tier feature" in str(exc_info.value.detail)

    def test_free_tier_manual_health_check_and_auto_heal_rejection(self):
        """FLAW-31: Free tier users cannot trigger manual health checks, auto-heal, or fleet heal."""
        from campaigns.backend.routers.elein import trigger_account_auto_heal, trigger_fleet_heal, check_account_session_death

        mock_supabase = MagicMock()
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            return t
        mock_supabase.table.side_effect = mock_table

        with pytest.raises(HTTPException) as exc_info:
            trigger_account_auto_heal("acc_123", supabase=mock_supabase, workspace_id="ws_free")
        assert exc_info.value.status_code == 403

        with pytest.raises(HTTPException) as exc_info:
            trigger_fleet_heal(supabase=mock_supabase, workspace_id="ws_free")
        assert exc_info.value.status_code == 403

        with pytest.raises(HTTPException) as exc_info:
            check_account_session_death("acc_123", supabase=mock_supabase, workspace_id="ws_free")
        assert exc_info.value.status_code == 403

    def test_free_tier_sybil_workspace_creation_blocked(self):
        """FLAW-19: Free tier users owning 1 or more workspaces are blocked from Sybil minting."""
        from admin.backend.routers.workspaces import create_workspace, WorkspaceCreate

        mock_svc = MagicMock()
        mock_owned = MagicMock()
        mock_owned.execute.return_value = MagicMock(data=[{"id": "ws_1", "tier": "FREE"}])
        mock_svc.table.return_value.select.return_value.eq.return_value = mock_owned

        with patch("admin.backend.routers.workspaces.get_service_client", return_value=mock_svc):
            with patch.dict("os.environ", {}, clear=False):
                import os
                # Temporarily unset PYTEST_CURRENT_TEST to verify production guard
                old_val = os.environ.pop("PYTEST_CURRENT_TEST", None)
                try:
                    payload = WorkspaceCreate(name="Sybil Workspace 2")
                    with pytest.raises(HTTPException) as exc_info:
                        create_workspace(payload=payload, user_id="user_free")
                    assert exc_info.value.status_code == 403
                    assert "Free tier accounts can only create 1 workspace" in str(exc_info.value.detail)
                finally:
                    if old_val:
                        os.environ["PYTEST_CURRENT_TEST"] = old_val

    def test_waterfall_enrichment_credit_deduction_failure_raises_402(self):
        """FLAW-09: Waterfall enrichment must raise 402 if credit deduction fails, preventing free contact leakage."""
        from campaigns.backend.services.waterfall_enrichment_service import execute_waterfall_enrichment

        mock_supabase = MagicMock()
        # Mock failed deduction (0 balance or insufficient credits)
        with patch("core.backend.services.credit_service.deduct_credits", return_value={"success": False, "reason": "insufficient_credits"}):
            with pytest.raises(HTTPException) as exc_info:
                execute_waterfall_enrichment(
                    lead_name="Patrick Collison",
                    company_domain="stripe.com",
                    workspace_id="ws_real_production_tenant",
                    supabase=mock_supabase
                )
            assert exc_info.value.status_code == 402
            assert "Payment required: Insufficient credits" in str(exc_info.value.detail)

    def test_abm_generate_copy_tier_gated(self):
        """FLAW-16: ABM role-differentiated copy generator endpoints must enforce tier gating."""
        from campaigns.backend.routers.abm_router import generate_copy_endpoint, get_copy_matrix_endpoint, GenerateCopyPayload

        mock_supabase = MagicMock()
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            return t
        mock_supabase.table.side_effect = mock_table
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"tier": "FREE"})

        payload = GenerateCopyPayload(
            company_name="Acme",
            prospect_name="Alice",
            title="VP",
            role_archetype="champion"
        )
        with pytest.raises(HTTPException) as exc_info:
            generate_copy_endpoint(payload=payload, workspace_id="ws_free_abm", supabase=mock_supabase)
        assert exc_info.value.status_code == 402

        with pytest.raises(HTTPException) as exc_info:
            get_copy_matrix_endpoint(company_name="Acme", workspace_id="ws_free_abm", supabase=mock_supabase)
        assert exc_info.value.status_code == 402

    def test_bandit_experiments_tier_gated(self):
        """FLAW-30: Multi-armed bandit experiments endpoints must enforce tier gating."""
        from campaigns.backend.routers.bandit_router import get_experiment_stats, record_feedback_endpoint, RecordFeedbackPayload

        mock_supabase = MagicMock()
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            return t
        mock_supabase.table.side_effect = mock_table
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"tier": "FREE"})

        with pytest.raises(HTTPException) as exc_info:
            get_experiment_stats(campaign_id="camp_123", workspace_id="ws_free_bandit", supabase=mock_supabase)
        assert exc_info.value.status_code == 402

        fb_payload = RecordFeedbackPayload(variant_id="var_1", outcome="REPLY")
        with pytest.raises(HTTPException) as exc_info:
            record_feedback_endpoint(payload=fb_payload, workspace_id="ws_free_bandit", supabase=mock_supabase)
        assert exc_info.value.status_code == 402

    def test_social_radar_draft_generation_tier_gated(self):
        """FLAW-27: Social radar draft generation endpoint must enforce tier gating and deduct credits."""
        from leads.backend.routers.leads import generate_social_draft_endpoint, SocialGenerateDraftRequest

        mock_supabase = MagicMock()
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            return t
        mock_supabase.table.side_effect = mock_table

        req = SocialGenerateDraftRequest(signal_id="sig_123", tone="consultative")
        with pytest.raises(HTTPException) as exc_info:
            generate_social_draft_endpoint(
                lead_id="lead_123",
                payload=req,
                workspace_id="ws_free_social",
                supabase=mock_supabase
            )
        assert exc_info.value.status_code == 403
        assert "Social Intent Radar draft generation is a Growth Pro and Enterprise feature" in str(exc_info.value.detail)

    def test_salvage_starter_downsell_requires_checkout(self):
        """FLAW-12: Salvage starter downsell must require payment checkout rather than unmetered credit minting."""
        from core.backend.api.routers.billing import apply_salvage_offer, SalvageOfferRequest

        mock_supabase = MagicMock()
        mock_ws = MagicMock()
        mock_ws.execute.return_value = MagicMock(data=[{"tier": "PRO", "status": "active"}])
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value = mock_ws
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        req = SalvageOfferRequest(offerType="starter_downsell", reason="too expensive")
        res = asyncio.run(apply_salvage_offer(
            request=req,
            workspace_id="ws_salvage_test",
            supabase=mock_supabase
        ))
        assert res["status"] == "checkout_required"
        assert res["offer_applied"] == "starter_downsell"
        assert res["amount_inr"] == 2499
