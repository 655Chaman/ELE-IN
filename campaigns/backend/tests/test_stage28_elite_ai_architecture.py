import pytest
import threading
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
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
    enroll_boomerang_or_revival,
    resolve_boomerang_hook_for_execution,
    _sanitize_boomerang_text,
    _prune_boomerang_in_memory_locked,
    _boomerang_lock,
    _IN_MEMORY_JOB_CHANGES,
    _IN_MEMORY_WARM_PATHS,
    _IN_MEMORY_REVIVALS,
    _ENROLLED_BOOMERANG_LOCKS,
    _MAX_IN_MEMORY_BOOMERANG_ITEMS,
)


class DummySupabaseMock:
    def table(self, name: str):
        mock_t = MagicMock()
        mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        mock_t.select.return_value.eq.return_value.execute.return_value.data = []
        mock_t.insert.return_value.execute.return_value.data = []
        return mock_t


@pytest.fixture(autouse=True)
def reset_in_memory_boomerang_state():
    with _boomerang_lock:
        _ENROLLED_BOOMERANG_LOCKS.clear()
    yield
    with _boomerang_lock:
        _ENROLLED_BOOMERANG_LOCKS.clear()


@pytest.fixture
def test_client():
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-boomerang"
    app.dependency_overrides[get_service_client] = lambda: DummySupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =========================================================================
# LAYER 0: FOUNDATIONAL AI REVIVAL ARCHITECTURE
# =========================================================================
class TestStage28Layer0FoundationalBoomerangAI:
    def test_ai_job_change_synthesis_with_knowledge_brain(self):
        """Layer 0: AI job-change copy synthesis infuses Knowledge Brain synthesis into playbook messages."""
        mock_synthesis = {
            "core_value_prop": "Autonomous multithreading across enterprise buying committees with residential proxy pods.",
            "key_differentiators": ["Zero IP bans", "3.4x reply lift"],
            "proof_points": ["Over 500k meetings booked", "42% CAC reduction"]
        }

        mock_ai_response = (
            "Hi Marcus — thrilled to see your move to VP of Growth at Ramp! Loved partnering with you at Plaid. "
            "As you audit Ramp's outbound motion, I'd love to share our new multithreading playbook. Open to a 10-min catch-up?"
        )

        with patch("campaigns.backend.services.boomerang_revival_service._get_synthesis", return_value=mock_synthesis) as p_syn, \
             patch("campaigns.backend.services.boomerang_revival_service._run_llm_with_failover", return_value=mock_ai_response) as p_llm:

            res = calculate_boomerang_buying_window(
                prospect_name="Marcus Vance",
                previous_company="Plaid",
                previous_title="Director of Sales Ops",
                new_company="Ramp",
                new_title="VP of Growth",
                days_in_new_role=25,
                relationship_type="former_champion",
                use_ai=True,
                workspace_id="ws-stage28-ai",
                ai_model="nvidia/meta/llama-3.1-70b-instruct",
            )

            assert res["buying_window_score"] >= 80
            assert res["window_tier"] == "PEAK_90_DAY"
            assert "Ramp" in res["playbook_message"]
            assert p_llm.called
            assert "Marcus Vance" in p_llm.call_args[1]["user_prompt"]

    def test_ai_warm_intro_bridge_dual_script_generation(self):
        """Layer 0: Synthesizes dual warm-introduction scripts (connector request vs direct bridge)."""
        mock_direct = (
            "Hi Natalie — David Kim and I were recently discussing Scale AI's Q4 push. "
            "We've helped fellow portfolio CROs cut outbound CAC by 42%. Open to a brief 10-minute exchange?"
        )
        mock_request = (
            "Hi David — hope all is great! Notice you're close with Natalie Port at Scale AI. "
            "Would you be open to introducing us? Happy to send a 2-line forwardable blurb."
        )

        with patch("campaigns.backend.services.boomerang_revival_service._run_llm_with_failover", side_effect=[mock_direct, mock_request]):
            bridge = generate_warm_intro_bridge(
                target_prospect_name="Natalie Port",
                target_company="Scale AI",
                target_title="Chief Revenue Officer",
                connector_name="David Kim",
                connector_role="General Partner at Index Ventures",
                bridge_type="shared_investor",
                overlap_context="Portfolio Board Advisor",
                use_ai=True,
                workspace_id="ws-stage28-ai",
            )

            assert bridge["warmth_score"] >= 90
            assert "David Kim" in bridge["direct_bridge_draft"]
            assert "Natalie Port" in bridge["intro_request_draft"]

    def test_ai_closed_lost_revival_generation(self):
        """Layer 0: Evaluates Closed-Lost deal resurrection readiness and generates no-guilt revival copy."""
        mock_ai_msg = (
            "Hi Rachel — when we spoke ~4 months ago at Airtable, budget was frozen. "
            "With the new fiscal half and our new Self-Funding ROI Guarantee, we're helping teams cut spend 42%. "
            "Open to a 10-minute look this week?"
        )

        with patch("campaigns.backend.services.boomerang_revival_service._run_llm_with_failover", return_value=mock_ai_msg):
            eval_res = evaluate_closed_lost_revival(
                prospect_name="Rachel Zane",
                company_name="Airtable",
                title="Chief Financial Officer",
                lost_reason="budget_freeze",
                days_since_lost=120,
                original_deal_value=65000.0,
                revival_trigger="New Fiscal Half Budget Reset",
                use_ai=True,
                workspace_id="ws-stage28-ai",
            )

            assert eval_res["revival_score"] >= 80
            assert "Airtable" in eval_res["resurrection_message"]
            assert eval_res["days_since_lost"] == 120

    def test_buying_window_scoring_decay_curve(self):
        """Layer 0: Validates mathematical buying window scoring peak in first 15-60 days and exponential decay post-90 days."""
        # 1. Peak window (30 days)
        peak = calculate_boomerang_buying_window(
            prospect_name="Elena",
            previous_company="Stripe",
            previous_title="Director",
            new_company="Vercel",
            new_title="VP of Revenue",
            days_in_new_role=30,
        )
        assert peak["buying_window_score"] >= 85
        assert peak["window_tier"] == "PEAK_90_DAY"

        # 2. Post-90 day decay (180 days)
        decayed = calculate_boomerang_buying_window(
            prospect_name="Elena",
            previous_company="Stripe",
            previous_title="Director",
            new_company="Vercel",
            new_title="VP of Revenue",
            days_in_new_role=180,
        )
        assert decayed["buying_window_score"] < peak["buying_window_score"]
        assert decayed["window_tier"] == "ESTABLISHED"


# =========================================================================
# LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS & CONCURRENCY
# =========================================================================
class TestStage28Layer1EnvironmentalResilience:
    def test_boomerang_concurrency_lock_and_thread_safety(self):
        """Layer 1: Concurrency re-entrant lock prevents race conditions during parallel job change registrations."""
        workspace = "ws-stage28-concurrency"
        exceptions = []

        def worker(thread_idx: int):
            try:
                for i in range(5):
                    create_champion_job_change(
                        workspace_id=workspace,
                        prospect_name=f"Executive {thread_idx}_{i}",
                        previous_company="PreviousCo",
                        previous_title="Manager",
                        new_company=f"NewCo_{thread_idx}",
                        new_title="Director",
                        days_in_new_role=20,
                    )
                    enroll_boomerang_or_revival(
                        workspace_id=workspace,
                        item_id=f"item-{thread_idx}-{i}",
                        campaign_id=f"camp-{thread_idx}",
                    )
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(exceptions) == 0, f"Concurrent execution produced exceptions: {exceptions}"

    def test_boomerang_idempotent_duplicate_enrollment_lock(self):
        """Layer 1: Duplicate-enrollment lock prevents enrolling the same item into the same campaign twice."""
        workspace = "ws-stage28-idempotency"
        item_id = "jc-idempotent-1"
        campaign_id = "camp-alpha-1"

        first = enroll_boomerang_or_revival(
            workspace_id=workspace,
            item_id=item_id,
            item_type="job_change",
            campaign_id=campaign_id,
        )
        assert first["duplicate_prevented"] is False
        assert first["status"] == "enrolled"

        # Second enrollment attempt for identical item + campaign
        second = enroll_boomerang_or_revival(
            workspace_id=workspace,
            item_id=item_id,
            item_type="job_change",
            campaign_id=campaign_id,
        )
        assert second["duplicate_prevented"] is True

    def test_boomerang_bounded_in_memory_pruning(self):
        """Layer 1: Pruning caps in-memory collections to prevent unbounded memory growth."""
        with _boomerang_lock:
            # Artificially populate excess items
            for i in range(50):
                _IN_MEMORY_JOB_CHANGES.append({"id": f"jc-excess-{i}", "workspace_id": "ws-overflow"})
                _IN_MEMORY_WARM_PATHS.append({"id": f"wp-excess-{i}", "workspace_id": "ws-overflow"})
                _IN_MEMORY_REVIVALS.append({"id": f"rev-excess-{i}", "workspace_id": "ws-overflow"})

            _prune_boomerang_in_memory_locked()

            assert len(_IN_MEMORY_JOB_CHANGES) <= _MAX_IN_MEMORY_BOOMERANG_ITEMS
            assert len(_IN_MEMORY_WARM_PATHS) <= _MAX_IN_MEMORY_BOOMERANG_ITEMS
            assert len(_IN_MEMORY_REVIVALS) <= _MAX_IN_MEMORY_BOOMERANG_ITEMS

    def test_boomerang_opt_out_suppression_guard(self):
        """Layer 1: Immediately suppresses boomerang outreach if prospect is opted out."""
        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-stage28-suppress",
            prospect_name="Opted Out Prospect",
            mode="job_change",
            is_opted_out=True,
        )
        assert res["status"] == "suppressed"
        assert res["suppressed"] is True
        assert res["hook_message"] == ""
        assert "opted out" in res["reason"].lower()


# =========================================================================
# LAYER 2: HUMAN PARANOIA & SECURITY
# =========================================================================
class TestStage28Layer2HumanParanoiaAndSecurity:
    def test_boomerang_formula_injection_defense(self):
        """Layer 2: Strips leading spreadsheet formula injection characters (=, +, -, @) to prevent CRM/CSV execution."""
        assert _sanitize_boomerang_text("=CMD|' /C calc'!A0") == "CMD|' /C calc'!A0"
        assert _sanitize_boomerang_text("+@=-jected Company") == "jected Company"
        assert _sanitize_boomerang_text("@HYPERLINK('evil.com','click')") == "HYPERLINK('evil.com','click')"

    def test_boomerang_internal_promotion_detection(self):
        """Layer 2: Internal promotion guard detects previous_company == new_company and prevents 'Congrats on leaving X' slop."""
        res = calculate_boomerang_buying_window(
            prospect_name="Hannah Abbott",
            previous_company="Stripe",
            previous_title="Director of Operations",
            new_company="Stripe",
            new_title="VP of Operations",
            days_in_new_role=14,
        )
        assert res["is_internal_promotion"] is True
        assert "internal promotion" in res["playbook_message"].lower()
        assert "leaving stripe" not in res["playbook_message"].lower()

    def test_boomerang_anti_pestering_14_day_guard(self):
        """Layer 2: Anti-Pestering Guard blocks reviving deals lost fewer than 14 days ago unless force_override=True."""
        # 7 days since lost -> must raise ValueError
        with pytest.raises(ValueError, match="Anti-Pestering Guard"):
            evaluate_closed_lost_revival(
                prospect_name="Trevor Philips",
                company_name="Miro",
                title="Director",
                lost_reason="bad_timing",
                days_since_lost=7,
                force_override=False,
            )

        # When force_override=True -> permitted
        res = evaluate_closed_lost_revival(
            prospect_name="Trevor Philips",
            company_name="Miro",
            title="Director",
            lost_reason="bad_timing",
            days_since_lost=7,
            force_override=True,
        )
        assert res["days_since_lost"] == 7

    def test_boomerang_ai_slop_and_banned_phrases_scrubbing(self):
        """Layer 2: AI output guard rejects buzzword slop and strips banned competitor phrases."""
        slop_response = "I hope this email finds you well! Let me revolutionize your business at Ramp with 100% free guaranteed leads."
        with patch("campaigns.backend.services.boomerang_revival_service._run_llm_with_failover", return_value=slop_response):
            res = calculate_boomerang_buying_window(
                prospect_name="Sophia Reynolds",
                previous_company="Twilio",
                previous_title="Director",
                new_company="Ramp",
                new_title="VP",
                use_ai=True,
                banned_phrases="100% free, guaranteed leads",
            )
            # Output guard catches "I hope this email finds you well" and falls back safely
            assert "I hope this email finds you well" not in res["playbook_message"]
            assert "100% free" not in res["playbook_message"]

    def test_boomerang_cross_tenant_idor_isolation(self):
        """Layer 2: Enforces Cross-Tenant IDOR boundary preventing Tenant B from enrolling Tenant A's private boomerang records."""
        with _boomerang_lock:
            _IN_MEMORY_JOB_CHANGES.append({
                "id": "jc-private-tenant-a",
                "workspace_id": "ws-tenant-a",
                "prospect_name": "Private Lead",
                "status": "detected"
            })

        # Tenant B tries to enroll Tenant A's item
        with pytest.raises(PermissionError, match="Cross-workspace access denied"):
            enroll_boomerang_or_revival(
                workspace_id="ws-tenant-b",
                item_id="jc-private-tenant-a",
                item_type="job_change",
            )


# =========================================================================
# ROUTER INTEGRATION & FASTAPI ENDPOINTS
# =========================================================================
class TestStage28RouterEndpoints:
    def test_router_job_changes_endpoints(self, test_client):
        """Router: /api/elein/boomerang/job-changes lists and creates tracked champion job changes."""
        # 1. GET list
        resp = test_client.get("/api/elein/boomerang/job-changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "job_changes" in data

        # 2. POST create
        resp_post = test_client.post(
            "/api/elein/boomerang/job-changes",
            json={
                "prospect_name": "Marcus Chen",
                "previous_company": "Plaid",
                "previous_title": "Head of SDRs",
                "new_company": "Ramp",
                "new_title": "VP of Growth",
                "relationship_type": "former_champion",
                "days_in_new_role": 25,
            }
        )
        assert resp_post.status_code == 200
        post_data = resp_post.json()
        assert post_data["success"] is True
        assert post_data["data"]["prospect_name"] == "Marcus Chen"

    def test_router_warm_intros_endpoints(self, test_client):
        """Router: /api/elein/boomerang/warm-intros lists and creates warm intro paths."""
        resp = test_client.get("/api/elein/boomerang/warm-intros")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "warm_intros" in data

        resp_post = test_client.post(
            "/api/elein/boomerang/warm-intros",
            json={
                "target_prospect_name": "Victor Krum",
                "target_company": "Anthropic",
                "target_title": "Head of GTM",
                "connector_name": "Elena Rostova",
                "connector_role": "VP RevOps",
                "bridge_type": "shared_alumni",
            }
        )
        assert resp_post.status_code == 200
        post_data = resp_post.json()
        assert post_data["success"] is True
        assert post_data["data"]["target_prospect_name"] == "Victor Krum"

    def test_router_revivals_endpoints(self, test_client):
        """Router: /api/elein/boomerang/revivals lists and creates closed-lost deal revivals."""
        resp = test_client.get("/api/elein/boomerang/revivals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "revivals" in data

        resp_post = test_client.post(
            "/api/elein/boomerang/revivals",
            json={
                "prospect_name": "Lucas Graham",
                "company_name": "Notion",
                "title": "VP of Sales",
                "lost_reason": "missing_feature",
                "days_since_lost": 115,
                "revival_trigger": "Shipped Phase 14 ABM Multithreading",
            }
        )
        assert resp_post.status_code == 200
        post_data = resp_post.json()
        assert post_data["success"] is True
        assert post_data["data"]["prospect_name"] == "Lucas Graham"

    def test_router_resolve_execution_hook_endpoint(self, test_client):
        """Router: /api/elein/boomerang/resolve-execution-hook resolves runtime hook for sequence nodes."""
        resp = test_client.post(
            "/api/elein/boomerang/resolve-execution-hook",
            json={
                "prospect_name": "Hannah Abbott",
                "mode": "job_change",
                "previous_company": "Figma",
                "previous_title": "Senior Sales Manager",
                "new_company": "Linear",
                "new_title": "Head of Commercial Sales",
                "days_in_new_role": 19,
                "relationship_type": "power_user",
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "ready"
        assert "Linear" in data["data"]["hook_message"]
