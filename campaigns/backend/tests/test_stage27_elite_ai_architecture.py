import pytest
import threading
import json
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.bandit_service import (
    beta_sample,
    calculate_beta_credible_interval,
    compute_monte_carlo_win_probabilities,
    select_variant_thompson_sampling,
    resolve_bandit_arm_for_execution,
    record_variant_feedback,
    mutate_self_healing_variant,
    add_custom_variant,
    export_bandit_telemetry_csv,
    sanitize_text,
    validate_and_canonicalize_template,
    clamp_linkedin_note,
    _generate_ai_bandit_variant,
    _prune_in_memory_bandit_cache_locked,
    _bandit_lock,
    _IN_MEMORY_EXPERIMENTS,
    _IN_MEMORY_VARIANTS,
    _LEAD_ARM_LOCKS,
    _MAX_IN_MEMORY_EXPERIMENTS,
    _MAX_IN_MEMORY_VARIANTS_PER_EXP,
)


class DummySupabaseMock:
    def table(self, name: str):
        mock_t = MagicMock()
        mock_t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_t.insert.return_value.execute.return_value.data = []
        mock_t.update.return_value.eq.return_value.execute.return_value.data = []
        return mock_t


@pytest.fixture(autouse=True)
def reset_in_memory_bandit_state():
    with _bandit_lock:
        _IN_MEMORY_VARIANTS.clear()
        _IN_MEMORY_EXPERIMENTS.clear()
        _LEAD_ARM_LOCKS.clear()
    yield
    with _bandit_lock:
        _IN_MEMORY_VARIANTS.clear()
        _IN_MEMORY_EXPERIMENTS.clear()
        _LEAD_ARM_LOCKS.clear()


@pytest.fixture
def test_client():
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-bandit"
    app.dependency_overrides[get_service_client] = lambda: DummySupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =========================================================================
# LAYER 0: FOUNDATIONAL AI BANDIT & CHALLENGER SYNTHESIS
# =========================================================================
class TestStage27Layer0FoundationalBanditAI:
    def test_ai_bandit_challenger_synthesis_with_knowledge_brain(self):
        """Layer 0: AI dynamic challenger variant generation infuses Knowledge Brain synthesis."""
        mock_synthesis = {
            "core_value_prop": "Autonomous outbound pipeline acceleration with residential proxy infrastructure.",
            "key_differentiators": ["42% lower cost per meeting", "Zero IP bans"],
            "proof_points": ["3.4x higher connection acceptance", "Over 500k meetings booked"]
        }

        mock_ai_json = (
            '{"body": "Hi {{first_name}}, rather than another generic pitch: we helped {{company}}\'s peers '
            'achieve a 3.4x lift in meeting conversions with zero IP bans. Open to a 2-min breakdown?"}'
        )

        with patch("campaigns.backend.services.bandit_service._get_synthesis", return_value=mock_synthesis) as p_syn, \
             patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value=mock_ai_json) as p_llm:

            res = mutate_self_healing_variant(
                parent_variant_id="var-challenger-1",
                workspace_id="ws-stage27-ai",
                mutation_theme="social_proof_metric",
                channel="linkedin",
                use_ai=True,
                ai_model="nvidia/meta/llama-3.1-70b-instruct",
            )

            assert res["status"] == "success"
            assert res["is_ai_generated"] is True
            assert res["ai_model"] == "nvidia/meta/llama-3.1-70b-instruct"
            challenger = res["challenger_variant"]
            assert challenger["channel"] == "linkedin"
            assert challenger["is_ai_generated"] is True
            assert "3.4x lift" in challenger["template_text"]
            assert len(challenger["template_text"]) <= 295
            assert p_llm.called
            assert "social_proof_metric" in p_llm.call_args[1]["user_prompt"]

    def test_ai_bandit_email_challenger_synthesis(self):
        """Layer 0: Cold email challenger variant generates subject and body parsed from JSON."""
        mock_ai_json = (
            '{"subject": "{{company}}\'s outbound deliverability shift", '
            '"body": "Hi {{first_name}},\\n\\nCurious how {{company}} is handling LinkedIn connection saturation '
            'and email spam filter shifts this quarter?\\n\\nMost revenue leaders we speak with report a 50% drop '
            'in cold replies without pre-warming.\\n\\nOpen to comparing notes?\\n\\nBest,\\nAlex"}'
        )

        with patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value=mock_ai_json):
            res = mutate_self_healing_variant(
                parent_variant_id="var-consultative-2",
                workspace_id="ws-stage27-ai",
                mutation_theme="provocative_question",
                channel="email",
                use_ai=True,
            )

            assert res["status"] == "success"
            challenger = res["challenger_variant"]
            assert challenger["channel"] == "email"
            assert challenger["subject"] == "{{company}}'s outbound deliverability shift"
            assert "Curious how {{company}}" in challenger["template_text"]

    def test_ai_bandit_custom_arm_generation(self):
        """Layer 0: Operator custom arm creation with AI synthesizes high-converting copy from intent."""
        mock_ai_json = (
            '{"body": "Quick question {{first_name}}: are you open to automated sequences that pre-warm '
            'prospects on LinkedIn before emailing them? Happy to send a 2-min demo if timing aligns."}'
        )

        with patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value=mock_ai_json):
            res = add_custom_variant(
                workspace_id="ws-stage27-ai",
                name="Executive Pre-warming Teardown",
                template_text="",
                use_ai=True,
                channel="linkedin",
            )

            assert res["status"] == "success"
            assert res["is_ai_generated"] is True
            variant = res["variant"]
            assert variant["name"] == "Executive Pre-warming Teardown"
            assert "pre-warm" in variant["template_text"]
            assert variant["alpha_param"] == 2.0
            assert variant["beta_param"] == 2.0

    def test_bayesian_math_stability_and_bounds(self):
        """Layer 0: Verifies mathematical stability of beta sampling, credible intervals, and win probabilities."""
        # 1. Beta sampling with extreme / degenerate inputs
        s1 = beta_sample(-10.0, -5.0)
        assert 0.0 <= s1 <= 1.0

        s2 = beta_sample(float("nan"), float("inf"))
        assert 0.0 <= s2 <= 1.0

        s3 = beta_sample(50.0, 50.0)
        assert 0.0 <= s3 <= 1.0

        # 2. Credible intervals
        ci_lower, ci_upper = calculate_beta_credible_interval(10.0, 20.0)
        assert 0.0 <= ci_lower <= ci_upper <= 1.0

        # 3. Monte Carlo win probabilities
        test_variants = [
            {"id": "arm-A", "alpha_param": 15.0, "beta_param": 5.0},
            {"id": "arm-B", "alpha_param": 5.0, "beta_param": 15.0},
        ]
        win_probs = compute_monte_carlo_win_probabilities(test_variants, num_draws=500)
        assert "arm-A" in win_probs
        assert "arm-B" in win_probs
        assert win_probs["arm-A"] > win_probs["arm-B"]
        assert 0.95 <= (win_probs["arm-A"] + win_probs["arm-B"]) <= 1.05


# =========================================================================
# LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS & CONCURRENCY
# =========================================================================
class TestStage27Layer1EnvironmentalResilience:
    def test_bandit_concurrency_lock_and_thread_safety(self):
        """Layer 1: Concurrency re-entrant lock prevents race conditions during parallel arm mutations."""
        workspace = "ws-stage27-concurrency"
        exceptions = []

        def worker(thread_idx: int):
            try:
                for i in range(5):
                    # Concurrent resolution
                    resolve_bandit_arm_for_execution(
                        workspace_id=workspace,
                        campaign_id="camp-parallel",
                        node_id=f"node-{thread_idx}",
                        lead_id=f"lead-{thread_idx}-{i}",
                    )
                    # Concurrent custom arm creation
                    add_custom_variant(
                        workspace_id=workspace,
                        campaign_id="camp-parallel",
                        name=f"Arm Thread {thread_idx} Step {i}",
                        template_text=f"Hello {{first_name}} from thread {thread_idx}",
                    )
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(exceptions) == 0, f"Concurrent execution produced exceptions: {exceptions}"

    def test_bandit_sticky_lead_idempotency(self):
        """Layer 1: Sticky lead-to-arm cache guarantees consistent copy across retries without double-impressions."""
        workspace = "ws-stage27-sticky"
        lead_id = "lead-sticky-999"
        node_id = "node-exec-1"

        res1 = resolve_bandit_arm_for_execution(
            workspace_id=workspace,
            campaign_id="camp-sticky",
            node_id=node_id,
            lead_id=lead_id,
            sticky=True,
        )
        assert res1["status"] == "success"
        assert res1["sticky_hit"] is False
        arm1_id = res1["selected_variant_id"]

        # Retry execution for same lead
        res2 = resolve_bandit_arm_for_execution(
            workspace_id=workspace,
            campaign_id="camp-sticky",
            node_id=node_id,
            lead_id=lead_id,
            sticky=True,
        )
        assert res2["status"] == "success"
        assert res2["sticky_hit"] is True
        assert res2["selected_variant_id"] == arm1_id

    def test_bandit_bounded_memory_pruning(self):
        """Layer 1: Memory bounds pruning prevents unbounded memory leaks in experiment/variant registries."""
        with _bandit_lock:
            # Artificially populate excess experiments
            for i in range(100):
                key = f"ws-overflow:camp-{i}"
                _IN_MEMORY_EXPERIMENTS[key] = {"id": f"exp-overflow-{i}"}
                _IN_MEMORY_VARIANTS[f"exp-overflow-{i}"] = [{"id": f"var-{j}"} for j in range(120)]

            # Call prune
            _prune_in_memory_bandit_cache_locked()

            # Verify variants per experiment pruned to <= _MAX_IN_MEMORY_VARIANTS_PER_EXP
            for exp_id in [f"exp-overflow-{i}" for i in range(10)]:
                if exp_id in _IN_MEMORY_VARIANTS:
                    assert len(_IN_MEMORY_VARIANTS[exp_id]) <= _MAX_IN_MEMORY_VARIANTS_PER_EXP

    def test_bandit_generation_count_clamping(self):
        """Layer 1: Generation counter is capped at <= 10 to prevent runaway genetic mutation loops."""
        workspace = "ws-stage27-gen"
        # Seed an arm with generation 10
        with _bandit_lock:
            _IN_MEMORY_VARIANTS["exp-gen-clamp"] = [{
                "id": "var-gen-10",
                "name": "Arm Gen 10",
                "workspace_id": workspace,
                "generation": 10,
                "status": "degraded",
                "template_text": "Old message"
            }]
            _IN_MEMORY_EXPERIMENTS[f"{workspace}:global"] = {"id": "exp-gen-clamp"}

        res = mutate_self_healing_variant(
            parent_variant_id="var-gen-10",
            workspace_id=workspace,
            mutation_theme="social_proof_metric",
            retire_parent=False,
        )
        assert res["generation"] <= 10


# =========================================================================
# LAYER 2: HUMAN PARANOIA & SECURITY
# =========================================================================
class TestStage27Layer2HumanParanoiaAndSecurity:
    def test_bandit_formula_injection_defense(self):
        """Layer 2: Spreadsheet formula injection prefixes (=, +, -, @) are neutralized in templates and CSV exports."""
        raw_text = "=CMD|' /C calc'!A0 {{first_name}} check this out"
        cleaned = validate_and_canonicalize_template(raw_text)
        assert not cleaned.startswith("=")
        assert "{{first_name}}" in cleaned

        # In CSV export
        workspace = "ws-stage27-csv"
        add_custom_variant(
            workspace_id=workspace,
            name="@HYPERLINK('http://malicious.com','Click')",
            template_text="+SUM(1+1) {{first_name}}",
        )
        csv_data = export_bandit_telemetry_csv(workspace_id=workspace)
        assert not any(line.startswith("=") or line.startswith("@") or line.startswith("+") for line in csv_data.splitlines())

    def test_bandit_banned_phrases_scrubbing(self):
        """Layer 2: Banned competitor and high-risk spam phrases are stripped from variant text."""
        with patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value='{"body": "We offer guaranteed revenue and 100% free leads for {{company}}"}'):
            res = mutate_self_healing_variant(
                parent_variant_id="var-challenger-1",
                workspace_id="ws-stage27-bp",
                banned_phrases="guaranteed revenue, 100% free",
                use_ai=True,
            )
            challenger = res["challenger_variant"]
            assert "guaranteed revenue" not in challenger["template_text"].lower()
            assert "100% free" not in challenger["template_text"].lower()

    def test_bandit_ai_slop_and_buzzword_fallback(self):
        """Layer 2: AI output guard rejects buzzword slop and safely reverts to high-integrity template."""
        slop_response = '{"body": "I hope this email finds you well! Let me revolutionize your business with our cutting-edge AI."}'
        with patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value=slop_response):
            res = mutate_self_healing_variant(
                parent_variant_id="var-challenger-1",
                workspace_id="ws-stage27-slop",
                channel="linkedin",
                use_ai=True,
            )
            challenger = res["challenger_variant"]
            # Output guard catches "I hope this email finds you well" and falls back safely
            assert "I hope this email finds you well" not in challenger["template_text"]

    def test_bandit_cross_tenant_idor_isolation(self):
        """Layer 2: Cross-tenant access is rejected with PermissionError when attempting to mutate foreign variant."""
        foreign_ws = "ws-foreign-tenant"
        attacker_ws = "ws-stage27-attacker"

        # Create arm in foreign workspace
        res = add_custom_variant(
            workspace_id=foreign_ws,
            name="Confidential Executive Offer",
            template_text="Secret pricing for {{company}}",
        )
        foreign_var_id = res["variant"]["id"]

        # Attacker tries to mutate foreign arm
        with pytest.raises(PermissionError):
            mutate_self_healing_variant(
                parent_variant_id=foreign_var_id,
                workspace_id=attacker_ws,
            )

        # Attacker tries to record feedback on foreign arm
        with pytest.raises(PermissionError):
            record_variant_feedback(
                variant_id=foreign_var_id,
                outcome="positive_reply",
                workspace_id=attacker_ws,
            )


# =========================================================================
# ROUTER INTEGRATION & FASTAPI ENDPOINTS
# =========================================================================
class TestStage27RouterEndpoints:
    def test_router_mutate_variant_ai_endpoint(self, test_client):
        """Router: /api/elein/bandit/mutate-variant executes AI-powered mutation with tier permissions."""
        mock_ai_json = '{"body": "Hi {{first_name}}, benchmark teardown for {{company}}: 42% reply rate lift. Worth a look?"}'
        with patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value=mock_ai_json):
            resp = test_client.post(
                "/api/elein/bandit/mutate-variant",
                json={
                    "parent_variant_id": "var-challenger-1",
                    "mutation_theme": "social_proof_metric",
                    "channel": "linkedin",
                    "use_ai": True,
                    "ai_model": "nvidia/meta/llama-3.1-70b-instruct",
                }
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["is_ai_generated"] is True
            assert "challenger_variant" in data

    def test_router_add_custom_variant_ai_endpoint(self, test_client):
        """Router: /api/elein/bandit/variants registers custom AI-synthesized arm into the MAB pool."""
        mock_ai_json = '{"body": "Quick note {{first_name}}: we compiled an outbound benchmark for {{company}}."}'
        with patch("campaigns.backend.services.bandit_service._run_llm_with_failover", return_value=mock_ai_json):
            resp = test_client.post(
                "/api/elein/bandit/variants",
                json={
                    "name": "Autonomous Pre-Warming Challenger",
                    "template_text": "",
                    "use_ai": True,
                    "channel": "linkedin",
                }
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["is_ai_generated"] is True
            assert "variant" in data

    def test_router_select_variant_endpoint(self, test_client):
        """Router: /api/elein/bandit/select-variant draws variant arm via Thompson Sampling."""
        resp = test_client.post(
            "/api/elein/bandit/select-variant",
            json={
                "campaign_id": "camp-stage27",
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "selected_variant_id" in data
        assert "all_arms" in data

    def test_router_export_csv_endpoint(self, test_client):
        """Router: /api/elein/bandit/experiments/export-csv returns sanitized CSV telemetry."""
        resp = test_client.get("/api/elein/bandit/experiments/export-csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "Variant ID,Name,Arm Type" in resp.text
