import pytest
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.displacement_service import (
    calculate_migration_savings,
    calculate_displacement_opportunity,
    generate_displacement_battlecard_copy,
    list_competitor_displacements,
    create_competitor_displacement,
    get_vendor_battlecards,
    launch_displacement_sequence,
    unlock_displacement_sequence,
    resolve_displacement_battlecard_for_execution,
    normalize_vendor_name,
    _sanitize_displacement_text,
    _prune_displacement_in_memory_locked,
    reset_in_memory_displacement_state,
    _displacement_lock,
    _IN_MEMORY_DISPLACEMENTS,
    _IN_MEMORY_DISPLACEMENT_RUNS,
    _DISPLACEMENT_LOCKS,
    _MAX_IN_MEMORY_DISPLACEMENTS,
    _MAX_IN_MEMORY_DISPLACEMENT_RUNS,
)


class DummySupabaseMock:
    def table(self, name: str):
        mock_t = MagicMock()
        mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        mock_t.select.return_value.eq.return_value.execute.return_value.data = []
        mock_t.insert.return_value.execute.return_value.data = []
        return mock_t

    def rpc(self, name: str, params: dict):
        mock_r = MagicMock()
        mock_r.execute.return_value.data = {"tier": "ENTERPRISE", "credits": 500}
        return mock_r


@pytest.fixture(autouse=True)
def reset_displacement_state():
    reset_in_memory_displacement_state()
    yield
    reset_in_memory_displacement_state()


@pytest.fixture
def test_client():
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-displacement"
    app.dependency_overrides[get_service_client] = lambda: DummySupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =========================================================================
# LAYER 0: FOUNDATIONAL COMPETITIVE DISPLACEMENT AI
# =========================================================================
class TestStage29Layer0FoundationalDisplacementAI:
    def test_ai_displacement_synthesis_with_knowledge_brain(self):
        """Layer 0: AI competitive displacement copy infuses Knowledge Brain context and battlecard advantages."""
        mock_synthesis = {
            "core_value_prop": "Consolidated multichannel revenue engine with dedicated residential proxy pods.",
            "key_differentiators": ["3-provider waterfall data", "Thompson sampling genetic copy"],
            "proof_points": ["42% lower CAC", "Zero LinkedIn account bans across 2.4M touches"]
        }

        mock_ai_response = (
            "Hi Arthur — noticed NorthStar's reps actively prospecting with Outreach. "
            "With your renewal in ~60 days, many RevOps teams are migrating to Ele-in's residential proxy pods "
            "to eliminate shared IP bans while saving ~$19,600/year for 18 reps. "
            "We'll also credit your remaining 60 days on Outreach. Open to a 10-minute comparison this week?"
        )

        with patch("campaigns.backend.services.displacement_service._get_synthesis", return_value=mock_synthesis) as p_syn, \
             patch("campaigns.backend.services.displacement_service._run_llm_with_failover", return_value=mock_ai_response) as p_llm:

            res = generate_displacement_battlecard_copy(
                incumbent_vendor="outreach",
                target_company="NorthStar Logistics",
                target_contact_name="Arthur Pendelton",
                target_contact_title="VP of Revenue Operations",
                seat_count=18,
                renewal_days=60,
                annual_savings=19656.0,
                use_ai=True,
                workspace_id="ws-stage29-ai",
                ai_model="nvidia/meta/llama-3.1-70b-instruct"
            )

            assert p_llm.called
            call_kwargs = p_llm.call_args[1]
            assert "NorthStar Logistics" in call_kwargs["user_prompt"]
            assert "18 reps" in call_kwargs["user_prompt"]
            assert "Arthur" in call_kwargs["user_prompt"]
            assert "Outreach" in call_kwargs["system_prompt"]
            assert "LIBEL & BRAND SAFETY GUARD" in call_kwargs["system_prompt"]
            assert res["vendor_slug"] == "outreach"
            assert res["annual_savings"] == 19656.0
            assert "Arthur" in res["body"]

    def test_vendor_normalization_and_battlecard_advantages(self):
        """Layer 0: Normalizes competitor names and maps to vendor battlecards."""
        vendors = ["Apollo.io", "OUTREACH", "salesloft inc", "Expandi.io", "Lemlist", "HeyReach app", "unknown_vendor"]
        expected_slugs = ["apollo", "outreach", "salesloft", "expandi", "lemlist", "heyreach", "other"]

        for v_raw, expected_slug in zip(vendors, expected_slugs):
            slug = normalize_vendor_name(v_raw)
            assert slug == expected_slug
            cards = get_vendor_battlecards(workspace_id="ws-default", vendor_slug=slug)
            assert isinstance(cards, list)
            if slug != "other":
                assert len(cards) >= 1
                assert cards[0]["vendor_slug"] == slug
                assert "elein_killer_advantage" in cards[0]
                assert "contract_buyout_offer" in cards[0]

    def test_mathematical_migration_savings_calculation(self):
        """Layer 0: Accurately calculates annual incumbent spend vs Ele-in consolidated spend."""
        # 10 seats of Outreach ($140/seat/mo) vs Ele-in ($49/seat/mo)
        # Incumbent: 10 * 140 * 12 = 16,800. Ele-in: 10 * 49 * 12 = 5,880. Net savings: 10,920 (65.0%)
        res = calculate_migration_savings(vendor_slug="outreach", seat_count=10)
        assert res["annual_incumbent_spend"] == 16800.0
        assert res["annual_elein_spend"] == 5880.0
        assert res["annual_net_savings"] == 10920.0
        assert res["savings_percentage"] == 65.0

        # Custom seat pricing test: 20 seats at $200/mo
        # Incumbent: 20 * 200 * 12 = 48,000. Ele-in: 20 * 49 * 12 = 11,760. Net savings: 36,240 (75.5%)
        custom_res = calculate_migration_savings(
            vendor_slug="salesloft",
            seat_count=20,
            custom_monthly_cost_per_seat=200.0
        )
        assert custom_res["annual_incumbent_spend"] == 48000.0
        assert custom_res["annual_elein_spend"] == 11760.0
        assert custom_res["annual_net_savings"] == 36240.0
        assert custom_res["savings_percentage"] == 75.5

    def test_displacement_vulnerability_scoring_by_renewal_window(self):
        """Layer 0: Scores vulnerability accurately across renewal windows (peak, urgent, seeding, expired)."""
        # Peak window: 60 days
        peak = calculate_displacement_opportunity(incumbent_vendor="apollo", contract_renewal_days=60, seat_count=25)
        assert peak["window_status"] == "PEAK_EVALUATION"
        assert peak["displacement_vulnerability_score"] >= 90

        # Urgent window: 30 days
        urgent = calculate_displacement_opportunity(incumbent_vendor="apollo", contract_renewal_days=30, seat_count=10)
        assert urgent["window_status"] == "URGENT_RENEWAL"
        assert urgent["displacement_vulnerability_score"] >= 75

        # Seeding window: 120 days
        seeding = calculate_displacement_opportunity(incumbent_vendor="expandi", contract_renewal_days=120, seat_count=8)
        assert seeding["window_status"] == "STRATEGIC_SEEDING"

        # Expired window: 0 days
        expired = calculate_displacement_opportunity(incumbent_vendor="salesloft", contract_renewal_days=0, seat_count=5)
        assert expired["window_status"] == "EXPIRED"
        assert expired["contract_renewal_days"] == 0


# =========================================================================
# LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS & RESILIENCE
# =========================================================================
class TestStage29Layer1EnvironmentalResilience:
    def test_ai_fallback_on_llm_exception_or_timeout(self):
        """Layer 1: Gracefully falls back to deterministic battlecard template when LLM throws exception."""
        with patch("campaigns.backend.services.displacement_service._run_llm_with_failover", side_effect=RuntimeError("GPU cluster connection refused")):
            res = generate_displacement_battlecard_copy(
                incumbent_vendor="apollo",
                target_company="Stripe",
                target_contact_name="Patrick",
                target_contact_title="COO",
                seat_count=15,
                renewal_days=45,
                use_ai=True,
                workspace_id="ws-stage29-fallback"
            )

            assert "Patrick" in res["body"]
            assert "Apollo.io" in res["body"]
            assert "residential proxy pods" in res["body"]
            assert res["annual_savings"] > 0

    def test_concurrent_duplicate_sequence_lock(self):
        """Layer 1: Enforces concurrency locks to prevent sending duplicate displacement cadences to same company."""
        # First call acquires lock
        res1 = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-disp-lock",
            target_company="Snowflake Inc",
            target_contact_name="Frank",
            target_contact_title="CEO",
            incumbent_vendor="outreach",
            domain="snowflake.com",
            contract_renewal_days=50,
            seat_count=50
        )
        assert res1["lock_acquired"] is True
        assert res1["duplicate_prevented"] is False

        # Immediate second call is blocked by duplicate sequence lock
        res2 = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-disp-lock",
            target_company="Snowflake Inc",
            target_contact_name="Benoit",
            target_contact_title="CTO",
            incumbent_vendor="outreach",
            domain="snowflake.com",
            contract_renewal_days=50,
            seat_count=50
        )
        assert res2["lock_acquired"] is False
        assert res2["duplicate_prevented"] is True

    def test_displacement_sequence_unlock_and_ttl_expiration(self):
        """Layer 1: Manual unlock releases lock, and expired locks (past 3600s TTL) can be reacquired."""
        res1 = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-disp-unlock",
            target_company="Databricks",
            target_contact_name="Ali",
            target_contact_title="CEO",
            incumbent_vendor="salesloft",
            domain="databricks.com"
        )
        assert res1["lock_acquired"] is True

        # Unlock manually
        unlocked = unlock_displacement_sequence("ws-disp-unlock", "databricks.com")
        assert unlocked is True

        # Now can acquire again
        res2 = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-disp-unlock",
            target_company="Databricks",
            target_contact_name="Matei",
            target_contact_title="CTO",
            incumbent_vendor="salesloft",
            domain="databricks.com"
        )
        assert res2["lock_acquired"] is True
        assert res2["duplicate_prevented"] is False

        # Simulate TTL expiration by backdating locked_at
        lock_key = "ws-disp-unlock:databricks.com"
        with _displacement_lock:
            _DISPLACEMENT_LOCKS[lock_key]["locked_at"] = (datetime.now(timezone.utc) - timedelta(seconds=3605)).isoformat()

        # Reacquisition succeeds because old lock is expired
        res3 = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-disp-unlock",
            target_company="Databricks",
            target_contact_name="Reynold",
            target_contact_title="VP Eng",
            incumbent_vendor="salesloft",
            domain="databricks.com"
        )
        assert res3["lock_acquired"] is True
        assert res3["duplicate_prevented"] is False

    def test_in_memory_cache_pruning_under_thread_lock(self):
        """Layer 1: Caps in-memory caches to _MAX_IN_MEMORY_DISPLACEMENTS under high volume."""
        with _displacement_lock:
            # Populate 2050 displacement records
            for i in range(2050):
                _IN_MEMORY_DISPLACEMENTS.append({
                    "id": f"disp-bulk-{i}",
                    "workspace_id": "ws-bulk-test",
                    "target_company": f"Bulk Corp {i}",
                    "domain": f"bulk{i}.com",
                    "displacement_vulnerability_score": 75
                })
            assert len(_IN_MEMORY_DISPLACEMENTS) > _MAX_IN_MEMORY_DISPLACEMENTS

            _prune_displacement_in_memory_locked()
            assert len(_IN_MEMORY_DISPLACEMENTS) <= _MAX_IN_MEMORY_DISPLACEMENTS

            # Default seed records are preserved
            seed_ids = {d.get("id") for d in _IN_MEMORY_DISPLACEMENTS}
            assert "disp-101" in seed_ids
            assert "disp-102" in seed_ids

    def test_concurrency_race_condition_under_thread_stress(self):
        """Layer 1: Concurrently executing threads safely serialize under _displacement_lock."""
        results = []
        errors = []

        def worker(thread_idx):
            try:
                res = resolve_displacement_battlecard_for_execution(
                    workspace_id="ws-stress-test",
                    target_company=f"Target Company {thread_idx}",
                    target_contact_name=f"Lead {thread_idx}",
                    target_contact_title="VP of Sales",
                    incumbent_vendor="apollo",
                    domain=f"company{thread_idx}.com",
                    seat_count=10,
                    contract_renewal_days=45
                )
                results.append(res)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20
        assert all(r["lock_acquired"] is True for r in results)


# =========================================================================
# LAYER 2: HUMAN PARANOIA, LIBEL GUARD, SAFETY & IDOR
# =========================================================================
class TestStage29Layer2HumanParanoiaAndSafety:
    def test_formula_injection_sanitization(self):
        """Layer 2: Strips leading spreadsheet injection triggers (=, +, -, @, tab, newline)."""
        malicious_company = "=cmd|'/C calc'!A0"
        malicious_name = "@DDE(\"cmd\";\"/C calc\";\"__PROMPT__\")"
        malicious_domain = "+https://evil.com"

        clean_c = _sanitize_displacement_text(malicious_company)
        clean_n = _sanitize_displacement_text(malicious_name)
        clean_d = _sanitize_displacement_text(malicious_domain)

        assert not clean_c.startswith("=")
        assert not clean_n.startswith("@")
        assert not clean_d.startswith("+")

    def test_numerical_bounds_clamping(self):
        """Layer 2: Clamps out-of-bounds seats (1-5000), renewal days (0-365), and custom costs."""
        # Extreme negative and overflow seats
        res_neg = calculate_migration_savings("apollo", seat_count=-999)
        assert res_neg["seat_count"] == 1

        res_over = calculate_migration_savings("apollo", seat_count=999999)
        assert res_over["seat_count"] == 5000

        # Custom cost clamping ($10 - $5000)
        res_cheap = calculate_migration_savings("outreach", seat_count=10, custom_monthly_cost_per_seat=1.0)
        assert res_cheap["incumbent_monthly_seat_cost"] == 10.0

        res_expensive = calculate_migration_savings("outreach", seat_count=10, custom_monthly_cost_per_seat=999999.0)
        assert res_expensive["incumbent_monthly_seat_cost"] == 5000.0

        # Renewal days clamping (0 - 365)
        opp_neg = calculate_displacement_opportunity("apollo", contract_renewal_days=-50)
        assert opp_neg["contract_renewal_days"] == 0
        assert opp_neg["window_status"] == "EXPIRED"

        opp_over = calculate_displacement_opportunity("apollo", contract_renewal_days=9999)
        assert opp_over["contract_renewal_days"] == 365

    def test_comparative_libel_guard_and_ai_slop_rejection(self):
        """Layer 2: Strict slop mode rejects AI clichés and unreplaced brackets, safely falling back."""
        # 1. Output containing AI slop phrases like 'I hope this email finds you well' and 'game-changing platform'
        slop_response = (
            "Hi Arthur — I hope this email finds you well. Ele-in is a game-changing platform to revolutionize your workflow."
        )

        with patch("campaigns.backend.services.displacement_service._run_llm_with_failover", return_value=slop_response):
            res = generate_displacement_battlecard_copy(
                incumbent_vendor="outreach",
                target_company="NorthStar Logistics",
                target_contact_name="Arthur Pendelton",
                target_contact_title="VP of Sales",
                use_ai=True,
                workspace_id="ws-slop-test"
            )

            # Strict slop mode caught 'I hope this email finds you well' / 'game-changing platform' and fell back to deterministic template
            assert "hope this email finds you well" not in res["body"].lower()
            assert "game-changing platform" not in res["body"].lower()
            assert "Arthur" in res["body"]

        # 2. Output containing unreplaced template placeholder like [Insert Company]
        placeholder_response = (
            "Hi [Contact Name] — noticed [Insert Company] is using Outreach. "
            "Switch to Ele-in to save budget."
        )

        with patch("campaigns.backend.services.displacement_service._run_llm_with_failover", return_value=placeholder_response):
            res_ph = generate_displacement_battlecard_copy(
                incumbent_vendor="outreach",
                target_company="NorthStar Logistics",
                target_contact_name="Arthur Pendelton",
                target_contact_title="VP of Sales",
                use_ai=True,
                workspace_id="ws-ph-test"
            )

            # Placeholder was caught and triggered fallback
            assert "[Contact Name]" not in res_ph["body"]
            assert "[Insert Company]" not in res_ph["body"]
            assert "Arthur" in res_ph["body"]

    def test_banned_phrases_scrubbing_across_ai_and_fallback(self):
        """Layer 2: Banned phrases are scrubbed from displacement copy in both AI and fallback modes."""
        res = generate_displacement_battlecard_copy(
            incumbent_vendor="apollo",
            target_company="Acme Corp",
            target_contact_name="Alice",
            target_contact_title="VP Sales",
            banned_phrases="deliverability,residential",
            use_ai=False
        )

        assert "deliverability" not in res["body"].lower()
        assert "residential" not in res["body"].lower()

    def test_cross_tenant_idor_isolation(self):
        """Layer 2: Prevents cross-workspace IDOR updates or sequence launches."""
        # Create displacement belonging to Workspace A
        item_a = create_competitor_displacement(
            workspace_id="ws-tenant-alpha",
            target_company="Confidential Corp",
            target_contact_name="John Doe",
            target_contact_title="CRO",
            incumbent_vendor="salesloft",
            domain="confidentialcorp.com"
        )
        assert item_a["workspace_id"] == "ws-tenant-alpha"

        # Workspace B attempts to launch sequence on Workspace A's displacement record
        with pytest.raises(PermissionError, match="Cross-workspace access denied"):
            launch_displacement_sequence(
                workspace_id="ws-tenant-beta",
                displacement_id=item_a["id"]
            )

        # Workspace B attempts to resolve execution context targeting Workspace A's private company
        with pytest.raises(PermissionError, match="Cross-workspace access denied"):
            resolve_displacement_battlecard_for_execution(
                workspace_id="ws-tenant-beta",
                target_company="Confidential Corp",
                target_contact_name="Sneaky Hacker",
                target_contact_title="Attacker",
                domain="confidentialcorp.com"
            )


# =========================================================================
# ROUTER INTEGRATION & CREDIT FINANCIAL SAFETY
# =========================================================================
class TestStage29RouterIntegrationAndCreditSafety:
    def test_get_opportunities_and_battlecards_endpoints(self, test_client):
        """Router: Verifies opportunities and battlecards listing endpoints."""
        # Opportunities
        resp_opp = test_client.get("/api/elein/displacement/opportunities")
        assert resp_opp.status_code == 200
        data_opp = resp_opp.json()
        assert data_opp["success"] is True
        assert data_opp["total"] >= 1

        # Battlecards
        resp_bc = test_client.get("/api/elein/displacement/battlecards")
        assert resp_bc.status_code == 200
        data_bc = resp_bc.json()
        assert data_bc["success"] is True
        assert data_bc["total"] >= 6

    def test_savings_calculator_endpoint(self, test_client):
        """Router: Calculates migration savings via API."""
        payload = {
            "incumbent_vendor": "outreach",
            "seat_count": 15,
            "custom_monthly_cost_per_seat": 150.0
        }
        resp = test_client.post("/api/elein/displacement/savings-calculator", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["seat_count"] == 15
        assert data["annual_incumbent_spend"] == 27000.0
        assert data["annual_elein_spend"] == 8820.0
        assert data["annual_net_savings"] == 18180.0

    def test_generate_pitch_endpoint_credit_lifecycle_and_refund_on_failure(self, test_client):
        """Router: Deducts 2 credits on pitch generation, rejects empty inputs before burning credits, and refunds on failure."""
        # 1. Empty company validation (HTTP 400 before deducting credits)
        empty_payload = {
            "incumbent_vendor": "apollo",
            "target_company": "   ",
            "target_contact_name": "Bob",
            "target_contact_title": "VP Sales"
        }
        resp_empty = test_client.post("/api/elein/displacement/generate-pitch", json=empty_payload)
        assert resp_empty.status_code == 400
        assert "target_company is required" in resp_empty.text

        # 2. Successful generation with credit deduction
        valid_payload = {
            "incumbent_vendor": "apollo",
            "target_company": "Acme Inc",
            "target_contact_name": "Bob Smith",
            "target_contact_title": "VP of Revenue",
            "seat_count": 10,
            "renewal_days": 60
        }
        with patch("campaigns.backend.routers.displacement_router.check_overdraft_allowance", return_value=(True, 50, "ok")), \
             patch("campaigns.backend.routers.displacement_router.deduct_credits", return_value={"success": True, "balance": 48}):

            resp_success = test_client.post("/api/elein/displacement/generate-pitch", json=valid_payload)
            assert resp_success.status_code == 200
            assert resp_success.json()["credits_deducted"] == 2
            assert "Acme Inc" in resp_success.json()["data"]["subject"]

        # 3. Generation failure triggers automatic credit refund
        with patch("campaigns.backend.routers.displacement_router.check_overdraft_allowance", return_value=(True, 50, "ok")), \
             patch("campaigns.backend.routers.displacement_router.deduct_credits", return_value={"success": True, "balance": 48}), \
             patch("campaigns.backend.routers.displacement_router.generate_displacement_battlecard_copy", side_effect=RuntimeError("Fatal error")), \
             patch("campaigns.backend.routers.displacement_router.refund_credits") as p_refund:

            resp_fail = test_client.post("/api/elein/displacement/generate-pitch", json=valid_payload)
            assert resp_fail.status_code == 500
            assert p_refund.called
            assert p_refund.call_args[1]["amount"] == 2
            assert p_refund.call_args[1]["reason"] == "displacement_pitch_generation_failed"

    def test_resolve_battlecard_execution_endpoint(self, test_client):
        """Router: Resolves displacement execution context with concurrency and renewal checks."""
        payload = {
            "target_company": "Vercel",
            "target_contact_name": "Guillermo Rauch",
            "target_contact_title": "CEO",
            "incumbent_vendor": "outreach",
            "seat_count": 25,
            "contract_renewal_days": 60,
            "domain": "vercel.com"
        }
        resp = test_client.post("/api/elein/displacement/resolve-battlecard-execution", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "ready"
        assert data["vendor_slug"] == "outreach"
        assert data["lock_acquired"] is True
        assert data["duplicate_prevented"] is False
        assert "residential proxy pods" in data["displacement_wedge"]
