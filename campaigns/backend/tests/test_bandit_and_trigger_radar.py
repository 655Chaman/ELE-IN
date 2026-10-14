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
    mutate_self_healing_variant
)
from campaigns.backend.services.trigger_radar_service import (
    generate_trigger_icebreaker,
    get_trigger_radar_events,
    enroll_lead_from_trigger,
    dismiss_trigger_event
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

    def test_zero_migration_db_fallback_resilience(self):
        """Paranoia Layer 1: Database failure falls back gracefully to in-memory state."""
        mock_broken_supabase = MagicMock()
        mock_broken_supabase.table().select().eq().execute.side_effect = Exception("relation bandit_experiments does not exist")
        
        # Should not raise exception
        res = select_variant_thompson_sampling(workspace_id="ws-unmigrated", supabase=mock_broken_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIsNotNone(res["selected_variant_id"])


class TestTriggerRadarService(unittest.TestCase):
    """
    Tests for Career Move & Funding Trigger Radar.
    """

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


if __name__ == "__main__":
    unittest.main()
