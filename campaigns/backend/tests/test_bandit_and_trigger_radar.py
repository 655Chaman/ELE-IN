import unittest
from unittest.mock import MagicMock, patch
import math

from campaigns.backend.services.bandit_service import (
    beta_sample,
    calculate_beta_credible_interval,
    compute_monte_carlo_win_probabilities,
    get_or_create_experiment,
    select_variant_thompson_sampling,
    record_variant_feedback,
    mutate_self_healing_variant,
    clamp_linkedin_note,
    resolve_bandit_arm_for_execution,
    validate_and_canonicalize_template
)
from campaigns.backend.services.trigger_radar_service import (
    generate_trigger_icebreaker,
    get_trigger_radar_events,
    enroll_lead_from_trigger,
    dismiss_trigger_event,
    register_in_memory_suppression,
    clear_in_memory_suppressions
)


class TestBanditOptimizerService(unittest.TestCase):
    """
    Tests for the Thompson Sampling Multi-Armed Bandit copy optimizer.
    """

    def setUp(self):
        from campaigns.backend.services.bandit_service import _IN_MEMORY_VARIANTS, _IN_MEMORY_EXPERIMENTS
        _IN_MEMORY_VARIANTS.clear()
        _IN_MEMORY_EXPERIMENTS.clear()

    def test_beta_sample_bounds(self):
        """Paranoia Layer 0: Beta samples must be bounded in [0.0, 1.0]."""
        for _ in range(50):
            sample = beta_sample(alpha=5.0, beta=15.0)
            self.assertGreaterEqual(sample, 0.0)
            self.assertLessEqual(sample, 1.0)

    def test_beta_sample_fallback_on_negative_or_zero(self):
        """Paranoia Layer 1: Zero or negative alpha/beta must be safely elevated to 1.0."""
        sample = beta_sample(alpha=0.0, beta=-5.0)
        self.assertGreaterEqual(sample, 0.0)
        self.assertLessEqual(sample, 1.0)

    def test_calculate_beta_credible_interval(self):
        """Paranoia Layer 0: Normal approximation of Beta credible interval."""
        lower, upper = calculate_beta_credible_interval(alpha=10.0, beta=30.0, confidence=0.95)
        # Mean = 10 / 40 = 0.25
        self.assertLess(lower, 0.25)
        self.assertGreater(upper, 0.25)
        self.assertGreaterEqual(lower, 0.0)
        self.assertLessEqual(upper, 1.0)

    def test_compute_monte_carlo_win_probabilities(self):
        """Paranoia Layer 0: Winning arm should have highest win probability."""
        variants = [
            {"id": "arm-strong", "alpha_param": 30.0, "beta_param": 10.0},  # ~75% CVR
            {"id": "arm-weak", "alpha_param": 5.0, "beta_param": 35.0}     # ~12.5% CVR
        ]
        win_probs = compute_monte_carlo_win_probabilities(variants, num_draws=500)
        self.assertIn("arm-strong", win_probs)
        self.assertIn("arm-weak", win_probs)
        self.assertGreater(win_probs["arm-strong"], 0.90)
        self.assertLess(win_probs["arm-weak"], 0.10)

    def test_select_variant_thompson_sampling_flow(self):
        """Paranoia Layer 0: Full Thompson Sampling selection flow."""
        res = select_variant_thompson_sampling(workspace_id="ws-test-bandit")
        self.assertEqual(res["status"], "success")
        self.assertIsNotNone(res["selected_variant_id"])
        self.assertIn("template_text", res)
        self.assertGreaterEqual(len(res["all_arms"]), 1)
        selected_arm = next(a for a in res["all_arms"] if a["is_selected"])
        self.assertEqual(selected_arm["id"], res["selected_variant_id"])

    def test_record_variant_feedback_positive_reply(self):
        """Paranoia Layer 0: Positive reply increments alpha."""
        res = record_variant_feedback(
            variant_id="var-challenger-1",
            outcome="positive_reply",
            workspace_id="ws-test-bandit"
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["outcome"], "positive_reply")
        self.assertGreaterEqual(res["alpha_param"], 6.0)

    def test_record_variant_feedback_objection_degradation(self):
        """Paranoia Layer 0 & 2: Consecutive objections increment beta."""
        res = record_variant_feedback(
            variant_id="var-direct-3",
            outcome="objection",
            workspace_id="ws-test-bandit"
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["arm_status"], "degraded")

    def test_mutate_self_healing_variant(self):
        """Paranoia Layer 0: Genetic mutation generates challenger arm."""
        res = mutate_self_healing_variant(
            parent_variant_id="var-direct-3",
            workspace_id="ws-test-bandit",
            mutation_theme="social_proof_metric"
        )
        self.assertEqual(res["status"], "success")
        challenger = res["challenger_variant"]
        self.assertEqual(challenger["generation"], 2)
        self.assertEqual(challenger["alpha_param"], 2.0)
        self.assertEqual(challenger["beta_param"], 2.0)
        self.assertEqual(challenger["parent_variant_id"], "var-direct-3")
        self.assertIn("Challenger", challenger["name"])

    def test_validate_and_canonicalize_template_single_brackets(self):
        """Paranoia Layer 0: Auto-fixes single brackets and aliases to canonical {{token}}."""
        raw = "Hi {first_name}, how is {company_name} solving pipeline? Talk to {title}."
        canon = validate_and_canonicalize_template(raw)
        self.assertEqual(canon, "Hi {{first_name}}, how is {{company}} solving pipeline? Talk to {{job_title}}.")

        # Test other aliases
        raw2 = "Hey {firstname} at {company name} - saw you are {role}."
        canon2 = validate_and_canonicalize_template(raw2)
        self.assertEqual(canon2, "Hey {{first_name}} at {{company}} - saw you are {{job_title}}.")

    def test_validate_and_canonicalize_template_formula_injection(self):
        """Paranoia Layer 2: Neutralizes leading spreadsheet formula injection characters."""
        malicious = "=HYPERLINK('http://evil.com') Hey {first_name}."
        canon = validate_and_canonicalize_template(malicious)
        self.assertFalse(canon.startswith("="))
        self.assertIn("{{first_name}}", canon)

    def test_mutate_self_healing_variant_themes(self):
        """Paranoia Layer 1: Supports all 4 framework themes for mutation."""
        themes = ["social_proof_metric", "provocative_question", "low_friction_benchmark", "brevity_direct"]
        for theme in themes:
            res = mutate_self_healing_variant(
                parent_variant_id="var-challenger-1",
                workspace_id="ws-test-bandit",
                mutation_theme=theme,
                retire_parent=False
            )
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["theme"], theme)
            self.assertIn("Challenger", res["challenger_variant"]["name"])

    def test_mutate_self_healing_variant_email_channel(self):
        """Paranoia Layer 0: Generates both subject and body for email channel steps."""
        res = mutate_self_healing_variant(
            parent_variant_id="var-challenger-1",
            workspace_id="ws-test-bandit",
            mutation_theme="social_proof_metric",
            channel="email",
            retire_parent=False
        )
        self.assertEqual(res["status"], "success")
        variant = res["challenger_variant"]
        self.assertEqual(variant["channel"], "email")
        self.assertTrue(len(variant["subject"]) > 5)
        self.assertIn("{{company}}", variant["subject"])
        self.assertTrue(len(variant["template_text"]) > 20)

    def test_mutate_self_healing_variant_non_destructive(self):
        """Paranoia Layer 2: retire_parent=False keeps the parent active while staging challenger."""
        res = mutate_self_healing_variant(
            parent_variant_id="var-consultative-2",
            workspace_id="ws-test-bandit",
            mutation_theme="low_friction_benchmark",
            retire_parent=False
        )
        self.assertEqual(res["status"], "success")
        self.assertIsNone(res["retired_parent_id"])
        parent = res["parent_variant"]
        self.assertEqual(parent["status"], "active")

    def test_mutate_self_healing_variant_generation_cap(self):
        """Paranoia Layer 1: Generational depth is bounded at 10 to prevent unbounded drift."""
        from campaigns.backend.services.bandit_service import _IN_MEMORY_VARIANTS
        # Seed an arm with generation 10
        _IN_MEMORY_VARIANTS["exp-capped"] = [{
            "id": "var-gen-10",
            "experiment_id": "exp-capped",
            "name": "Gen 10 Arm",
            "generation": 10,
            "status": "active",
            "template_text": "Old text",
            "workspace_id": "ws-test-cap"
        }]
        res = mutate_self_healing_variant(
            parent_variant_id="var-gen-10",
            workspace_id="ws-test-cap",
            retire_parent=False
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["challenger_variant"]["generation"], 10)

    def test_zero_migration_db_fallback_resilience(self):
        """Paranoia Layer 1: Database failure falls back gracefully to in-memory state."""
        mock_broken_supabase = MagicMock()
        mock_broken_supabase.table().select().eq().execute.side_effect = Exception("relation bandit_experiments does not exist")
        
        # Should not raise exception
        res = select_variant_thompson_sampling(workspace_id="ws-unmigrated", supabase=mock_broken_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIsNotNone(res["selected_variant_id"])

    def test_clamp_linkedin_note_hard_boundary(self):
        """Paranoia Layer 0 & 2: Clamp notes exceeding 295 chars at word boundary."""
        short_text = "Hey John, loved your post on B2B pipeline growth."
        self.assertEqual(clamp_linkedin_note(short_text), short_text)

        long_text = "Hey John " + ("very long title and detailed pitch " * 15)
        clamped = clamp_linkedin_note(long_text, max_chars=295)
        self.assertLessEqual(len(clamped), 295)
        self.assertTrue(clamped.endswith("..."))

    def test_min_burnin_floor_exploration(self):
        """Paranoia Layer 0: Arms under MIN_BURNIN_IMPRESSIONS (15) maintain exploration probability."""
        import random
        random.seed(42)
        # Over multiple draws, untested arm must get selected due to burn-in exploration floor
        selections = []
        for _ in range(50):
            res = select_variant_thompson_sampling(workspace_id="ws-burnin-test")
            selections.append(res["selected_variant_id"])
        self.assertIn("var-challenger-1", selections)

    def test_record_variant_feedback_toxic_sentiment(self):
        """Paranoia Layer 0 & 2: Toxic feedback types trigger immediate penalty and auto-degradation."""
        # Test spam complaint
        res_spam = record_variant_feedback(
            variant_id="var-challenger-1",
            outcome="spam_complaint",
            workspace_id="ws-toxic-test"
        )
        self.assertEqual(res_spam["status"], "success")
        self.assertEqual(res_spam["arm_status"], "degraded")

        # Test angry DNC
        res_dnc = record_variant_feedback(
            variant_id="var-consultative-2",
            outcome="angry_dnc",
            workspace_id="ws-toxic-test"
        )
        self.assertEqual(res_dnc["status"], "success")
        self.assertEqual(res_dnc["arm_status"], "degraded")

    def test_resolve_bandit_arm_deleted_fallback(self):
        """Paranoia Layer 2: Deleted arm id falls back gracefully to champion arm."""
        arm = resolve_bandit_arm_for_execution(
            variant_id="var-non-existent-or-deleted-arm",
            workspace_id="ws-fallback-test"
        )
        self.assertEqual(arm["status"], "success")
        self.assertIsNotNone(arm.get("selected_variant"))
        self.assertEqual(arm["selected_variant"].get("status"), "active")
        self.assertIn("template_text", arm)
        self.assertTrue(len(arm["template_text"]) > 0)



class TestTriggerRadarService(unittest.TestCase):
    """
    Tests for Career Move & Funding Trigger Radar.
    """

    def setUp(self):
        from campaigns.backend.services.trigger_radar_service import (
            _IN_MEMORY_TRIGGERS,
            _SEED_TRIGGER_EVENTS,
            _IN_MEMORY_SUPPRESSIONS
        )
        _IN_MEMORY_TRIGGERS.clear()
        _IN_MEMORY_TRIGGERS.extend([dict(t) for t in _SEED_TRIGGER_EVENTS])
        _IN_MEMORY_SUPPRESSIONS.clear()

    def test_generate_trigger_icebreaker_new_role(self):
        """Paranoia Layer 0: Personalized hook for new job title."""
        hook = generate_trigger_icebreaker(
            event_type="NEW_ROLE",
            prospect_name="Elena Rostova",
            company_name="Veloce Systems",
            event_data={"new_title": "VP of Revenue Operations"}
        )
        self.assertIn("Elena", hook)
        self.assertIn("VP of Revenue Operations", hook)
        self.assertIn("Veloce Systems", hook)
        self.assertLessEqual(len(hook), 280)

    def test_generate_trigger_icebreaker_funding_round(self):
        """Paranoia Layer 0: Personalized hook for funding round."""
        hook = generate_trigger_icebreaker(
            event_type="FUNDING_ROUND",
            prospect_name="Marcus Vance",
            company_name="Apex Cloud",
            event_data={"round_type": "Series B", "amount_raised": "$28M"}
        )
        self.assertIn("$28M Series B", hook)
        self.assertIn("Apex Cloud", hook)
        self.assertLessEqual(len(hook), 280)

    def test_generate_trigger_icebreaker_promotion(self):
        """Paranoia Layer 0: Personalized hook for promotion."""
        hook = generate_trigger_icebreaker(
            event_type="PROMOTION",
            prospect_name="Sarah Lin",
            company_name="Quantify Health",
            event_data={"new_title": "Chief Growth Officer"}
        )
        self.assertIn("Chief Growth Officer", hook)
        self.assertIn("Quantify Health", hook)
        self.assertLessEqual(len(hook), 280)

    def test_get_trigger_radar_events_filtering(self):
        """Paranoia Layer 0: Query radar events with event_type filter."""
        events = get_trigger_radar_events(workspace_id="ws-test", event_type_filter="NEW_ROLE")
        self.assertTrue(all(e["event_type"] == "NEW_ROLE" for e in events))

    def test_enroll_lead_from_trigger_lifecycle(self):
        """Paranoia Layer 0: Enrollment sets status to ENROLLED."""
        res = enroll_lead_from_trigger(
            trigger_event_id="trig-101",
            campaign_id="camp-q4-outbound",
            workspace_id="ws-test"
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["campaign_id"], "camp-q4-outbound")
        self.assertIsNotNone(res["icebreaker"])

        # Paranoia Layer 2: Reject duplicate enrollment
        dup_res = enroll_lead_from_trigger(
            trigger_event_id="trig-101",
            campaign_id="camp-q4-outbound",
            workspace_id="ws-test"
        )
        self.assertEqual(dup_res["status"], "ignored")
        self.assertIn("already enrolled", dup_res["message"])

    def test_dismiss_trigger_event(self):
        """Paranoia Layer 0: Dismissing trigger sets status to DISMISSED."""
        res = dismiss_trigger_event(trigger_event_id="trig-104", workspace_id="ws-test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["message"], "Trigger event dismissed.")

    def test_generate_trigger_icebreaker_null_safe_handling(self):
        """Paranoia Layer 0 & 1: Defend against None / null string interpolations."""
        # 1. Null prospect and null company
        hook_nulls = generate_trigger_icebreaker(
            event_type="NEW_ROLE",
            prospect_name=None,
            company_name="None",
            event_data={"new_title": "None"}
        )
        self.assertNotIn("None", hook_nulls)
        self.assertIn("there", hook_nulls)
        self.assertIn("your company", hook_nulls)
        self.assertIn("your new role", hook_nulls)

        # 2. Funding round with undisclosed or None amount
        hook_funding = generate_trigger_icebreaker(
            event_type="FUNDING_ROUND",
            prospect_name="Marcus Vance",
            company_name="Apex Cloud",
            event_data={"round_type": "Series B", "amount_raised": "None"}
        )
        self.assertNotIn("None Series B", hook_funding)
        self.assertIn("congrats on the Series B for Apex Cloud", hook_funding)

        hook_undisclosed = generate_trigger_icebreaker(
            event_type="FUNDING_ROUND",
            prospect_name="Marcus Vance",
            company_name="Apex Cloud",
            event_data={"round_type": "Series B", "amount_raised": "undisclosed"}
        )
        self.assertNotIn("undisclosed Series B", hook_undisclosed)
        self.assertIn("congrats on the Series B for Apex Cloud", hook_undisclosed)

    def test_generate_trigger_icebreaker_stale_trigger_defense(self):
        """Paranoia Layer 1: If tenure > 90 days, adapt copy away from 'first 90 days' ramp."""
        # Fresh trigger: 14 days
        hook_fresh = generate_trigger_icebreaker(
            event_type="NEW_ROLE",
            prospect_name="Elena Rostova",
            company_name="Veloce Systems",
            event_data={"new_title": "VP of Revenue Operations", "tenure_days": 14}
        )
        self.assertIn("initial ramp", hook_fresh)
        self.assertIn("congrats on taking the VP of Revenue Operations seat", hook_fresh)

        # Stale trigger: 180 days (6 months ago)
        hook_stale = generate_trigger_icebreaker(
            event_type="NEW_ROLE",
            prospect_name="Elena Rostova",
            company_name="Veloce Systems",
            event_data={"new_title": "VP of Revenue Operations", "tenure_days": 180}
        )
        self.assertNotIn("first 90 days", hook_stale)
        self.assertNotIn("initial ramp", hook_stale)
        self.assertIn("congrats on leading the VP of Revenue Operations team", hook_stale)

    def test_generate_trigger_icebreaker_word_boundary_length_clamping(self):
        """Paranoia Layer 2: Long copy is bounded to <= 280 characters without truncating mid-word."""
        long_title = "Executive Vice President of Global Enterprise Revenue Operations & Strategic Channel Partnerships"
        long_company = "International Consolidated Distributed Technologies & Cloud Infrastructure Solutions Inc"
        hook = generate_trigger_icebreaker(
            event_type="NEW_ROLE",
            prospect_name="Alexander Montgomery",
            company_name=long_company,
            event_data={"new_title": long_title}
        )
        self.assertLessEqual(len(hook), 280)
        self.assertTrue(hook.endswith("..."))
        # Must not end in trailing comma or punctuation right before ellipsis
        self.assertFalse(hook.endswith(",..."))

    def test_enroll_lead_from_trigger_suppression_list_blocks(self):
        """Paranoia Layer 2: Lead enrollment is strictly blocked if email is on the suppression list."""
        clear_in_memory_suppressions()
        # Suppress Elena Rostova's email
        register_in_memory_suppression(
            workspace_id="ws-suppress-test",
            email="elena@velocesystems.com",
            reason="GDPR DNC opt-out"
        )

        res = enroll_lead_from_trigger(
            trigger_event_id="trig-101",
            campaign_id="camp-test",
            workspace_id="ws-suppress-test"
        )
        self.assertEqual(res["status"], "blocked_suppressed")
        self.assertEqual(res["reason"], "SUPPRESSION_LIST_MATCH")
        self.assertEqual(res["matched_by"], "email")
        self.assertIn("prospect is on workspace suppression list", res["message"])

        clear_in_memory_suppressions()

    @patch("leads.backend.services.suppression_service.check_lead_suppression")
    def test_enroll_lead_from_trigger_supabase_suppression_blocks(self, mock_check_sup):
        """Paranoia Layer 1 & 2: Supabase suppression check triggers block on DNC match."""
        mock_check_sup.return_value = {
            "suppressed": True,
            "matched_by": "linkedin_url",
            "matched_value": "https://linkedin.com/in/marcusvance",
            "reason": "Competitor domain"
        }
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().limit().execute.return_value.data = []

        res = enroll_lead_from_trigger(
            trigger_event_id="trig-102",
            campaign_id="camp-test",
            workspace_id="ws-sup-mock",
            supabase=mock_supabase
        )
        self.assertEqual(res["status"], "blocked_suppressed")
        self.assertEqual(res["reason"], "SUPPRESSION_LIST_MATCH")
        self.assertEqual(res["matched_by"], "linkedin_url")



class TestBanditRouterEndpoints(unittest.TestCase):
    """
    Tests for router endpoint execution logic.
    """

    def test_select_variant_endpoint_logic(self):
        from campaigns.backend.routers.bandit_router import select_variant_endpoint, SelectVariantPayload
        payload = SelectVariantPayload(campaign_id="camp-123")
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value.data = []
        res = select_variant_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIn("selected_variant_id", res)
        self.assertIn("template_text", res)

    def test_record_feedback_endpoint_logic(self):
        from campaigns.backend.routers.bandit_router import record_feedback_endpoint, RecordFeedbackPayload
        payload = RecordFeedbackPayload(variant_id="var-challenger-1", outcome="positive_reply")
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().limit().execute.return_value.data = []
        res = record_feedback_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["outcome"], "positive_reply")

    def test_get_trigger_radar_endpoint_logic(self):
        from campaigns.backend.routers.bandit_router import get_trigger_radar_endpoint
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().order().limit().execute.return_value.data = []
        res = get_trigger_radar_endpoint(status="PENDING", workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["count"], 1)

    def test_tier_gating_free_workspace_raises_402_on_bandit(self):
        from fastapi import HTTPException
        from campaigns.backend.routers.bandit_router import select_variant_endpoint, SelectVariantPayload
        payload = SelectVariantPayload(campaign_id="camp-123")
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        with self.assertRaises(HTTPException) as ctx:
            select_variant_endpoint(payload, workspace_id="ws-real-free-workspace", supabase=mock_supabase)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_free_workspace_raises_402_on_trigger_radar(self):
        from fastapi import HTTPException
        from campaigns.backend.routers.bandit_router import enroll_trigger_endpoint, EnrollTriggerPayload
        payload = EnrollTriggerPayload(trigger_event_id="trig-1", campaign_id="camp-1")
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        with self.assertRaises(HTTPException) as ctx:
            enroll_trigger_endpoint(payload, workspace_id="ws-real-free-workspace", supabase=mock_supabase)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_pro_workspace_succeeds(self):
        from campaigns.backend.routers.bandit_router import select_variant_endpoint, SelectVariantPayload
        payload = SelectVariantPayload(campaign_id="camp-123")
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_supabase.table().select().eq().execute.return_value.data = []
        res = select_variant_endpoint(payload, workspace_id="ws-real-pro-workspace", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")

    def test_add_custom_variant_logic_and_formula_defense(self):
        """Paranoia Layer 0 & 2: Custom variant registration with formula neutralization."""
        from campaigns.backend.services.bandit_service import add_custom_variant
        res = add_custom_variant(
            workspace_id="ws-test-custom",
            campaign_id="camp-custom-1",
            name="=CMD|' /C calc'!A0 Custom Angle",
            template_text="+@HYPERLINK('http://evil.com') Hey {{first_name}}, testing our benchmark.",
            arm_type="full_message"
        )
        self.assertEqual(res["status"], "success")
        variant = res["variant"]
        # Formula characters must be stripped
        self.assertFalse(variant["name"].startswith("="))
        self.assertFalse(variant["template_text"].startswith(("+", "@")))
        self.assertEqual(variant["alpha_param"], 2.0)
        self.assertEqual(variant["beta_param"], 2.0)

    def test_export_bandit_telemetry_csv(self):
        """Paranoia Layer 0 & 2: Export bandit telemetry to CSV with safe headers."""
        from campaigns.backend.services.bandit_service import export_bandit_telemetry_csv
        csv_str = export_bandit_telemetry_csv(workspace_id="ws-test-csv")
        self.assertIn("Variant ID,Name,Arm Type,Status", csv_str)
        self.assertIn("Expected CVR", csv_str)
        self.assertIn("95% Credible Interval", csv_str)
        self.assertIn("Win Probability", csv_str)

    def test_export_trigger_radar_csv(self):
        """Paranoia Layer 0 & 2: Export trigger radar to CSV with formula escaping."""
        from campaigns.backend.services.trigger_radar_service import export_trigger_radar_csv
        csv_str = export_trigger_radar_csv(workspace_id="ws-test-csv")
        self.assertIn("Trigger ID,Prospect Name,Company Name,Event Type", csv_str)
        self.assertIn("Elena Rostova", csv_str)
        self.assertIn("Veloce Systems", csv_str)

    def test_add_custom_variant_endpoint_logic(self):
        """Paranoia Layer 0: Endpoint test for adding custom copy variant."""
        from campaigns.backend.routers.bandit_router import add_custom_variant_endpoint, AddVariantPayload
        payload = AddVariantPayload(
            campaign_id="camp-custom-endpoint",
            name="Founder-to-Founder Angle",
            template_text="Hey {{first_name}}, founder here—quick question."
        )
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value.data = []
        res = add_custom_variant_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIn("variant", res)

    def test_export_endpoints_response_headers(self):
        """Paranoia Layer 0: CSV export endpoints return valid CSV Content-Type and Disposition."""
        from campaigns.backend.routers.bandit_router import export_bandit_csv_endpoint, export_triggers_csv_endpoint
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value.data = []

        bandit_res = export_bandit_csv_endpoint(workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(bandit_res.media_type, "text/csv")
        self.assertIn("attachment; filename=bandit_arms_", bandit_res.headers["content-disposition"])

        trigger_res = export_triggers_csv_endpoint(workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(trigger_res.media_type, "text/csv")
        self.assertIn("attachment; filename=trigger_radar_", trigger_res.headers["content-disposition"])


    def test_mutate_variant_endpoint_with_channel_and_preview(self):
        """Paranoia Layer 0 & 2: Endpoint supports channel selection and non-destructive preview."""
        from campaigns.backend.routers.bandit_router import mutate_variant_endpoint, MutateVariantPayload
        payload = MutateVariantPayload(
            parent_variant_id="var-challenger-1",
            mutation_theme="social_proof_metric",
            channel="email",
            touchpoint_id="step_4_email",
            retire_parent=False
        )
        mock_supabase = MagicMock()
        mock_parent = {
            "id": "var-challenger-1",
            "workspace_id": "ws-test",
            "experiment_id": "exp-test",
            "name": "Challenger Arm",
            "generation": 1,
            "template_text": "Existing template"
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [mock_parent]
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = []
        res = mutate_variant_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIn("challenger_variant", res)
        challenger = res["challenger_variant"]
        self.assertEqual(challenger["channel"], "email")
        self.assertIsNone(res["retired_parent_id"])


if __name__ == "__main__":
    unittest.main()

