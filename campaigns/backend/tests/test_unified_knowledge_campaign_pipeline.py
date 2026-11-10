"""
test_unified_knowledge_campaign_pipeline.py — Comprehensive EPF Test Battery.

Validates the Unified Knowledge Base -> Campaign Sequence DAG Pipeline:
  - Layer 0: Full 4-layer Knowledge Base context injection in handle_send_ai_message
  - Layer 1: Outbound & Inbound query handling in handle_ai_query_brain without empty-context crashes
  - Layer 2: Variable propagation (ai_brain_response, ai_hook) to downstream sequence nodes
"""

import unittest
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor


class TestUnifiedKnowledgeCampaignPipeline(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws_test_pipeline_001"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(self.mock_supabase, workspace_id=self.workspace_id)
        # Mock worker
        self.executor.worker = MagicMock()
        self.executor.worker.send_message.return_value = {"status": "success"}

    @patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover")
    @patch("knowledge.backend.services.elein_ai_service._get_knowledge_context")
    @patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_synthesis")
    def test_send_ai_message_injects_full_knowledge_base_context(
        self,
        mock_get_synthesis,
        mock_get_kb_context,
        mock_run_llm
    ):
        """
        Layer 0 & 1: Verifies that handle_send_ai_message retrieves the company synthesis,
        queries SemanticBrain for RAG vector chunks, and injects them into the system prompt.
        """
        mock_get_synthesis.return_value = {
            "core_value_prop": "Ele-in delivers 4x outbound pipeline via WebAssembly client execution.",
            "key_differentiators": ["Zero DOM injection", "Kinematic jerk smoothing"],
            "proof_points": ["14 meetings booked in 3 weeks for Linear"]
        }
        mock_get_kb_context.return_value = "[Doc: Security_Whitepaper.pdf] Ele-in runs isolated WebAssembly sandboxes."
        mock_run_llm.return_value = "Hey Alex, saw your role leading engineering at Acme. Wanted to share how we run WebAssembly outreach."

        node_data = {
            "prompt": "Pitch our WebAssembly anti-bot architecture to engineering leadership",
            "lead_profile": {
                "title": "VP of Engineering",
                "company": "Acme Technologies",
                "about": "Scaling distributed cloud infrastructure"
            },
            "workspace_id": self.workspace_id
        }

        # Mock safety guards
        self.executor._check_message_safety_guards = MagicMock(return_value=None)
        self.executor._require_worker = MagicMock(return_value=None)

        res = self.executor.handle_send_ai_message(node_data, "https://linkedin.com/in/alex-test")

        self.assertEqual(res.get("status"), "success")
        mock_run_llm.assert_called_once()
        call_kwargs = mock_run_llm.call_args[1]

        system_prompt = call_kwargs["system_prompt"]
        self.assertIn("--- LAYER 1: WORKSPACE CONSTITUTION & VALUE PROPOSITION ---", system_prompt)
        self.assertIn("Ele-in delivers 4x outbound pipeline", system_prompt)
        self.assertIn("Zero DOM injection", system_prompt)
        self.assertIn("--- LAYER 2: RELEVANT KNOWLEDGE CONTEXT & TECHNICAL PROOF POINTS ---", system_prompt)
        self.assertIn("Security_Whitepaper.pdf", system_prompt)
        self.assertIn("WebAssembly sandboxes", system_prompt)

    @patch("knowledge.backend.services.elein_ai_service.query_knowledge_base")
    def test_handle_ai_query_brain_outbound_sequence_support(self, mock_query_kb):
        """
        Layer 0 & 1: Verifies that handle_ai_query_brain supports outbound sequences
        where no inbound prospect reply exists yet, using custom directives or profile context.
        """
        mock_query_kb.return_value = "Ele-in scales outbound without triggering LinkedIn canvas checks."

        node_data = {
            "custom_query": "Extract our best enterprise case study for {{company}}",
            "lead_profile": {
                "title": "Head of Growth",
                "company": "ScaleUp AI"
            },
            "workspace_id": self.workspace_id
        }

        res = self.executor.handle_ai_query_brain(node_data, "https://linkedin.com/in/growth-lead")

        self.assertEqual(res.get("status"), "success")
        self.assertIn("variables", res)
        # Check that both canonical and alias variables are populated
        self.assertEqual(res["variables"]["ai_brain_response"], "Ele-in scales outbound without triggering LinkedIn canvas checks.")
        self.assertEqual(res["variables"]["brain_response"], "Ele-in scales outbound without triggering LinkedIn canvas checks.")
        self.assertEqual(res["variables"]["ai_objection_handler"], "Ele-in scales outbound without triggering LinkedIn canvas checks.")

        # Verify query_knowledge_base was invoked with resolved query mentioning ScaleUp AI
        mock_query_kb.assert_called_once()
        first_arg = mock_query_kb.call_args[0][0]
        self.assertIn("ScaleUp AI", first_arg)

    def test_downstream_message_interpolates_ai_brain_variables(self):
        """
        Layer 2: Verifies that downstream message nodes resolve {{ai_brain_response}}
        and {{ai_hook}} cleanly without dropping variables.
        """
        data = {
            "lead": {
                "first_name": "Alex",
                "company": "Acme"
            },
            "variables": {
                "ai_brain_response": "We eliminate DOM injection via native Wasm execution.",
                "ai_hook": "Congrats on Acme's Series B announcement!"
            }
        }

        template = "Hi {{first_name}},\n\n{{ai_hook}}\n\nQuick note: {{ai_brain_response}}\n\nBest,\nTeam"
        resolved = self.executor._interpolate_template(template, data, "https://linkedin.com/in/alex")

        self.assertIn("Hi Alex,", resolved)
        self.assertIn("Congrats on Acme's Series B announcement!", resolved)
        self.assertIn("We eliminate DOM injection via native Wasm execution.", resolved)
        self.assertNotIn("{{ai_brain_response}}", resolved)
        self.assertNotIn("{{ai_hook}}", resolved)

    @patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover")
    @patch("knowledge.backend.services.elein_ai_service._get_knowledge_context")
    @patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_synthesis")
    def test_node_sample_endpoint_generates_grounded_preview(
        self,
        mock_get_synthesis,
        mock_get_kb_context,
        mock_run_llm
    ):
        """
        Layer 0 & 1: Verifies that POST /api/assets/knowledge/test-node-sample
        generates an on-canvas simulation preview against company knowledge for sample leads.
        """
        import asyncio
        from knowledge.backend.routers.assets import test_node_sample, TestNodeSampleRequest

        mock_get_synthesis.return_value = {
            "core_value_prop": "Ele-in automates outreach with WebAssembly sandboxing."
        }
        mock_get_kb_context.return_value = "Chunk from Enterprise_Security.pdf"
        mock_run_llm.return_value = "Hi Alex, noticed your engineering leadership at Acme Cloud Technologies. Wanted to share our WebAssembly sandbox."

        req = TestNodeSampleRequest(
            node_type="send_ai_message",
            prompt="Pitch our WebAssembly sandbox",
            tone="Professional & Direct"
        )

        mock_supabase = MagicMock()
        res = asyncio.run(test_node_sample(req, supabase=mock_supabase, workspace_id=self.workspace_id))

        self.assertEqual(res.get("status"), "success")
        self.assertIn("WebAssembly sandbox", res.get("generated_text", ""))
        self.assertEqual(res.get("lead", {}).get("first_name"), "Alex")
        self.assertGreater(res.get("word_count", 0), 0)


if __name__ == "__main__":
    unittest.main()
