import unittest
import json
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from campaigns.backend.services.elein_executor import (
    EleInNodeExecutor,
    _GLOBAL_BRAIN_CACHE,
    invalidate_brain_cache,
    Branch
)
from knowledge.backend.services.elein_ai_service import (
    _knowledge_context_cache,
    invalidate_knowledge_context_cache
)
from core.backend.workers.job_processor import process_single_job

class TestStage5CampaignNodesAndWorkerHardening(unittest.TestCase):
    """
    Test suite for Stage 5: Campaign Node Execution & Background Worker Pipeline Hardening.
    Covers Flaws 9, 10, 11, 12, 13, and 14 under the Three-Layer Logic Architecture.
    """

    def setUp(self):
        self.workspace_id = "ws_test_stage5_999"
        invalidate_brain_cache()
        invalidate_knowledge_context_cache()

    def tearDown(self):
        invalidate_brain_cache()
        invalidate_knowledge_context_cache()

    # ─── FLAW 9: BUYER PERSONA WORD-BOUNDARY ANTI-COLLISION ──────────────────

    def test_match_buyer_persona_exact_and_word_boundaries(self):
        """
        Layer 0 & 1 Paranoia (Flaw 9):
        - Matches 'CTO' on 'Chief Technology Officer (CTO)'
        - Prevents false-positive substring collisions: 'cto' does NOT match 'Doctor'
        - 'vp' does NOT match 'Developer'
        - 'ceo' does NOT match 'Aceous'
        """
        personas = [
            {
                "id": "p1",
                "title": "Chief Technology Officer",
                "target_titles": ["CTO", "Chief Technology Officer", "VP of Engineering"],
                "pain_points": ["Legacy tech debt"],
                "value_prop": "Modern automated stack"
            },
            {
                "id": "p2",
                "title": "Doctor",
                "target_titles": ["Doctor", "Physician", "MD"],
                "pain_points": ["Patient scheduling"],
                "value_prop": "AI clinic concierge"
            }
        ]

        # Negative tests: Substring collision trap
        self.assertIsNone(EleInNodeExecutor._match_buyer_persona(personas, "Senior Software Developer"))
        match_doc = EleInNodeExecutor._match_buyer_persona(personas, "Medical Doctor at Memorial")
        self.assertIsNotNone(match_doc)
        self.assertEqual(match_doc["title"], "Doctor")

        # "Doctor" should NOT match the CTO persona even though "doctor" contains "cto"
        self.assertNotEqual(match_doc["title"], "Chief Technology Officer")

        # Positive test: Word-bounded CTO match
        match_cto = EleInNodeExecutor._match_buyer_persona(personas, "Interim CTO & VP of Engineering")
        self.assertIsNotNone(match_cto)
        self.assertEqual(match_cto["title"], "Chief Technology Officer")

    def test_match_buyer_persona_schema_tolerance(self):
        """
        Layer 2 Paranoia (Flaw 9):
        Tolerates target_titles stored as comma-separated string or list with messy spacing.
        """
        personas = [
            {
                "id": "p_csv",
                "title": "Head of Sales",
                "target_titles": "VP Sales, Head of Sales , Director of Sales",
                "pain_points": ["Quota attainment"]
            }
        ]
        match = EleInNodeExecutor._match_buyer_persona(personas, "VP Sales at HyperGrowth Inc")
        self.assertIsNotNone(match)
        self.assertEqual(match["title"], "Head of Sales")

    def test_handle_ai_personalize_and_score_icp_use_word_boundary_matching(self):
        """
        Layer 1 Paranoia (Flaw 9):
        Ensures handle_ai_personalize and handle_ai_score_icp leverage _match_buyer_persona
        and do not falsely trigger persona overrides on substring accidents.
        """
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id=self.workspace_id)

        # Mock brain with personas
        personas = [{
            "id": "p_cto",
            "title": "CTO",
            "target_titles": ["CTO"],
            "pain_points": ["Compute bills"],
            "value_prop": "Cloud savings"
        }]
        executor._get_unified_brain = MagicMock(return_value={"personas": personas})

        # Lead is a "Doctor" (contains "cto")
        node_data = {
            "workspace_id": self.workspace_id,
            "lead_profile": {"title": "Medical Doctor"},
            "custom_persona": "Base Persona"
        }

        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="Great medical practice!"):
            res = executor.handle_ai_personalize(node_data, "https://linkedin.com/in/doctor")
            self.assertEqual(res["status"], "success")

        with patch("knowledge.backend.services.elein_ai_service.score_icp_fit", return_value=85) as mock_score:
            res_icp = executor.handle_ai_score_icp(node_data, "https://linkedin.com/in/doctor")
            self.assertEqual(res_icp["branch"], Branch.HIGH_FIT.value)
            # The criteria string passed to score_icp_fit should NOT contain CTO directives
            criteria_arg = mock_score.call_args[0][1]
            self.assertNotIn("Strict Buyer Persona Match for this Lead:\nTitle: CTO", criteria_arg)

    # ─── FLAW 10: UNIFIED BRAIN OBJECTIONS DELEGATION ────────────────────────

    def test_get_unified_brain_calls_persona_service_get_objections(self):
        """
        Layer 0 & 1 Paranoia (Flaw 10):
        _get_unified_brain delegates to PersonaService.get_objections, merging both
        knowledge_objections and objections tables without historical data blindness.
        """
        mock_supabase = MagicMock()
        def mock_table(table_name):
            m = MagicMock()
            if table_name == "knowledge_synthesis":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"core_value_prop": "Val Prop", "workspace_id": self.workspace_id}]
                )
            elif table_name == "personas":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m
        mock_supabase.table.side_effect = mock_table
        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id=self.workspace_id)

        merged_objections = [
            {"id": "obj_mod_1", "trigger": "too expensive", "playbook": "Highlight ROI"},
            {"id": "obj_leg_2", "trigger": "not interested", "playbook": "Ask permission to nurture"}
        ]

        with patch("admin.backend.services.persona_service.PersonaService.get_objections", return_value=merged_objections) as mock_get_obj:
            brain = executor._get_unified_brain(self.workspace_id)
            mock_get_obj.assert_called_once_with(mock_supabase, self.workspace_id)
            self.assertEqual(len(brain.get("objections", [])), 2)
            self.assertEqual(brain["objections"][0]["trigger"], "too expensive")
            self.assertEqual(brain["objections"][1]["trigger"], "not interested")

    # ─── FLAW 11: MULTI-CACHE INVALIDATION SYNCHRONIZATION ───────────────────

    def test_invalidate_brain_cache_synchronizes_knowledge_context_cache(self):
        """
        Layer 1 Paranoia (Flaw 11):
        Calling invalidate_brain_cache(workspace_id) evicts both _GLOBAL_BRAIN_CACHE
        and _knowledge_context_cache for the targeted workspace.
        """
        from campaigns.backend.services.elein_executor import _GLOBAL_BRAIN_CACHE
        from knowledge.backend.services.elein_ai_service import _knowledge_context_cache

        # Populate both caches
        _GLOBAL_BRAIN_CACHE[self.workspace_id] = {"brain": {"core_value_prop": "Cached"}, "timestamp": 1000}
        _GLOBAL_BRAIN_CACHE["ws_other"] = {"brain": {"core_value_prop": "Other"}, "timestamp": 1000}

        _knowledge_context_cache[f"{self.workspace_id}::pricing::3"] = "cached pricing context"
        _knowledge_context_cache[f"{self.workspace_id}::general::3"] = "cached general context"
        _knowledge_context_cache["ws_other::pricing::3"] = "other workspace context"

        # Invalidate target workspace
        invalidate_brain_cache(self.workspace_id)

        # Check _GLOBAL_BRAIN_CACHE
        self.assertNotIn(self.workspace_id, _GLOBAL_BRAIN_CACHE)
        self.assertIn("ws_other", _GLOBAL_BRAIN_CACHE)

        # Check _knowledge_context_cache
        self.assertNotIn(f"{self.workspace_id}::pricing::3", _knowledge_context_cache)
        self.assertNotIn(f"{self.workspace_id}::general::3", _knowledge_context_cache)
        self.assertIn("ws_other::pricing::3", _knowledge_context_cache)

    # ─── FLAW 12: BACKGROUND WORKER FORWARDING FORCE TO SYNTHESIS ────────────

    def test_job_processor_forwards_force_flag_on_synthesis(self):
        """
        Layer 0 & 1 Paranoia (Flaw 12):
        The background worker inspects job payload (dict or JSON string) and forwards
        force=True to KnowledgeService.update_synthesis.
        """
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        calls = []
        async def fake_update_synthesis(sb, ws_id, force=False):
            calls.append((ws_id, force))

        # Case A: Dedicated synthesis job with dict payload
        job_synthesis = {
            "id": "job_syn_1",
            "job_type": "synthesis",
            "workspace_id": self.workspace_id,
            "asset_id": None,
            "payload": {"force": True}
        }

        with patch("knowledge.backend.services.knowledge_service.KnowledgeService.update_synthesis", side_effect=fake_update_synthesis):
            asyncio.run(process_single_job(job_synthesis, mock_supabase))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], (self.workspace_id, True))

        # Case B: Ingestion job with JSON-string payload containing force: True
        calls.clear()
        job_url_force = {
            "id": "job_url_1",
            "job_type": "url",
            "workspace_id": self.workspace_id,
            "asset_id": "asset_123",
            "payload": json.dumps({"url": "https://example.com", "force": True})
        }

        with patch("knowledge.backend.services.knowledge_service.KnowledgeService.process_url_bg", new_callable=AsyncMock), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.update_synthesis", side_effect=fake_update_synthesis):
            asyncio.run(process_single_job(job_url_force, mock_supabase))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], (self.workspace_id, True))

        # Case C: Standard follower ingestion job defaults to force=False
        calls.clear()
        job_url_default = {
            "id": "job_url_2",
            "job_type": "url",
            "workspace_id": self.workspace_id,
            "asset_id": "asset_456",
            "payload": {"url": "https://example.com"}
        }

        with patch("knowledge.backend.services.knowledge_service.KnowledgeService.process_url_bg", new_callable=AsyncMock), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.update_synthesis", side_effect=fake_update_synthesis):
            asyncio.run(process_single_job(job_url_default, mock_supabase))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0], (self.workspace_id, False))

    # ─── FLAW 13: HANDLE_AI_QUERY_BRAIN OBJECTION TRIGGER WORD BOUNDARIES ────

    def test_handle_ai_query_brain_objection_trigger_word_boundaries(self):
        """
        Layer 0 & 1 Paranoia (Flaw 13):
        Word boundaries prevent trigger collisions (e.g. trigger 'no' in 'know', 'in' in 'interactive').
        Exact matching gives priority to longer, specific triggers.
        """
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id=self.workspace_id)

        objections = [
            {"id": "o1", "trigger": "no", "playbook": "General objection handling"},
            {"id": "o2", "trigger": "not interested", "playbook": "Respectful disengagement"},
            {"id": "o3", "triggers": ["expensive", "too pricey"], "resolution": "Flexible terms"}
        ]
        executor._get_unified_brain = MagicMock(return_value={"objections": objections})

        # Lead reply contains "know" (should NOT trigger "no")
        node_data = {
            "workspace_id": self.workspace_id,
            "reply": "I know all about your product, but it is too pricey for us.",
            "lead_profile": {"title": "Director"}
        }

        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value="Here is our ROI breakdown") as mock_query:
            res = executor.handle_ai_query_brain(node_data, "https://linkedin.com/in/lead")
            self.assertEqual(res["status"], "success")

            # Check the playbook argument passed to query_knowledge_base
            playbook_arg = mock_query.call_args[0][2]
            # Should match "too pricey"
            self.assertIn("too pricey", playbook_arg)
            # Should NOT match "no"
            self.assertNotIn("Trigger 'no'", playbook_arg)

    # ─── FLAW 14: AI MODEL OVERRIDE PROPAGATION IN GENERATE REPLY ─────────────

    def test_handle_ai_generate_reply_passes_ai_model_and_preserves_data(self):
        """
        Layer 0 & 1 Paranoia (Flaw 14):
        Ensures handle_ai_generate_reply forwards node-level ai_model override to
        _run_llm_with_failover, and does not shadow input data with LLM JSON output.
        """
        mock_supabase = MagicMock()
        def mock_table(table_name):
            m = MagicMock()
            if table_name == "messages":
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"message_text": "What is your core value proposition?"}]
                )
                m.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(
                    count=0, data=[]
                )
            elif table_name == "workspaces":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"ai_reply_confidence_threshold": 0.65}]
                )
            return m
        mock_supabase.table.side_effect = mock_table

        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success"}

        executor = EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        executor._get_unified_brain = MagicMock(return_value={
            "core_value_prop": "Autonomous B2B outreach engine.",
            "personas": [],
            "objections": []
        })

        node_data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_stage5_123",
            "lead_message": "What is your core value proposition?",
            "ai_model": "deepseek-ai/deepseek-r1",
            "lead_profile": {"title": "VP of Sales"}
        }

        llm_json_response = json.dumps({
            "reply": "Our autonomous B2B outreach engine streamlines pipeline generation.",
            "confidence": 9,
            "grounded_in_knowledge": True
        })

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=[{"content": "Autonomous B2B outreach engine streamlines pipeline generation.", "similarity": 0.92}]), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value=llm_json_response) as mock_llm:
            res = executor.handle_ai_generate_reply(node_data, "https://linkedin.com/in/vpsales")
            self.assertEqual(res["status"], "success")

            # Verify ai_model was passed to _run_llm_with_failover
            self.assertEqual(mock_llm.call_args[1].get("ai_model"), "deepseek-ai/deepseek-r1")
            self.assertEqual(mock_llm.call_args[1].get("workspace_id"), self.workspace_id)

            # Verify input node_data was not mutated or shadowed
            self.assertEqual(node_data.get("ai_model"), "deepseek-ai/deepseek-r1")
            self.assertEqual(node_data.get("lead_message"), "What is your core value proposition?")

if __name__ == "__main__":
    unittest.main()
