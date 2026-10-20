import unittest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from knowledge.backend.routers.assets import test_objection as assets_test_objection, TestObjectionRequest
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch, invalidate_brain_cache, _GLOBAL_BRAIN_CACHE
from knowledge.backend.services.knowledge_service import KnowledgeService

class TestStage3KnowledgeAndCampaignNodes(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Stage 3 Knowledge & Campaign Node integration:
    - Flaw 7: Consolidate test_objection with dual schema and full test-drive response
    - Flaw 8B: Tier 3 headless browser rendering fallback for dynamic SPAs
    - Item 10: Unified brain objection playbooks & buyer personas injected into handle_ai_generate_reply
    - Item 11: Resilient inbound reply resolution in handle_ai_query_brain
    """

    def setUp(self):
        self.workspace_id = "ws_stage3_test_888"
        invalidate_brain_cache()

    def tearDown(self):
        invalidate_brain_cache()

    # ─── FLAW 7: TEST OBJECTION ROUTER CONSOLIDATION ─────────────────────────

    async def test_test_objection_router_supports_dual_schema_and_keys(self):
        """
        Layer 0 & 2 Paranoia:
        assets.py's test_objection accepts either 'objection' or 'message' keys,
        delegates to generate_test_drive_response, and returns both 'reply' and 'response'.
        """
        mock_supabase = MagicMock()

        with patch("knowledge.backend.services.elein_ai_service.generate_test_drive_response", new_callable=AsyncMock) as mock_sim:
            mock_sim.return_value = "We understand budget constraints. Our ROI calculator shows payback in 45 days."

            # Test 1: Called with 'objection'
            req_1 = TestObjectionRequest(objection="Too expensive for our current budget")
            res_1 = await assets_test_objection(req=req_1, supabase=mock_supabase, workspace_id=self.workspace_id)

            self.assertEqual(res_1["reply"], "We understand budget constraints. Our ROI calculator shows payback in 45 days.")
            self.assertEqual(res_1["response"], res_1["reply"])
            mock_sim.assert_called_with(mock_supabase, self.workspace_id, message="Too expensive for our current budget")

            # Test 2: Called with 'message'
            req_2 = TestObjectionRequest(message="Can this integrate with HubSpot?")
            res_2 = await assets_test_objection(req=req_2, supabase=mock_supabase, workspace_id=self.workspace_id)
            self.assertIn("reply", res_2)
            self.assertIn("response", res_2)

    async def test_test_objection_handles_empty_input_gracefully(self):
        """
        Layer 2 Paranoia: If user submits empty or whitespace input, returns a friendly prompt
        instead of throwing a 500 LLM error.
        """
        mock_supabase = MagicMock()
        req = TestObjectionRequest(objection="   ")
        res = await assets_test_objection(req=req, supabase=mock_supabase, workspace_id=self.workspace_id)
        self.assertIn("Please provide", res["reply"])
        self.assertEqual(res["reply"], res["response"])

    # ─── FLAW 8B: TIER 3 SPA SCRAPER FALLBACK ────────────────────────────────

    async def test_scrape_url_resilient_falls_back_to_tier3_playwright(self):
        """
        Layer 0 & 1 Paranoia: When Tier 1 (Jina) and Tier 2 (Direct HTTP) return empty
        client-side mount shells (<div id="root"></div>), Tier 3 launches headless browser
        and extracts rendered DOM text.
        """
        url = "https://app.spa-example.com/pricing"

        mock_page = AsyncMock()
        mock_page.inner_text = AsyncMock(return_value="Our Enterprise Plan is $499/month with unlimited seats and dedicated IP.")
        mock_element = AsyncMock()
        mock_element.inner_text = AsyncMock(return_value="Our Enterprise Plan is $499/month with unlimited seats and dedicated IP.")
        mock_page.query_selector = AsyncMock(return_value=mock_element)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_playwright = MagicMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_async_pw = MagicMock()
        mock_async_pw.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_pw.return_value.__aexit__ = AsyncMock()

        # Force Tier 1 & Tier 2 to fail (return empty)
        with patch("httpx.AsyncClient.get", side_effect=Exception("HTTP connection failed")), \
             patch("playwright.async_api.async_playwright", mock_async_pw):

            text = await KnowledgeService._scrape_url_resilient(url)

        self.assertIn("Enterprise Plan is $499/month", text)

    # ─── ITEM 10: INJECT BRAIN OBJECTIONS & PERSONAS INTO AI REPLY NODE ──────

    def test_handle_ai_generate_reply_injects_objections_and_personas(self):
        """
        Layer 0 & 1 Paranoia:
        In handle_ai_generate_reply, the executor matches unified brain objections against
        the prospect's inquiry and matched personas against lead title, injecting both
        into the LLM context prompt for hyper-relevant responses.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_rev_100",
            "enrollment_id": "enr_100",
            "execution_state_id": "state_100",
            "lead_profile": {
                "title": "VP of Revenue Operations",
                "name": "Sarah Connor"
            },
            "_skip_limit_check": True,
        }

        # Mock messages table
        mock_messages_tbl = MagicMock()
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "We already use Apollo and it is too expensive to switch."}]
        )
        mock_workspaces_tbl = MagicMock()
        mock_workspaces_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"ai_reply_confidence_threshold": 0.65}]
        )

        def table_router(table_name):
            if table_name == "messages":
                return mock_messages_tbl
            elif table_name == "workspaces":
                return mock_workspaces_tbl
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        # Seed unified brain with objection and persona
        brain_payload = {
            "core_value_prop": "Autonomous B2B outbound revenue engine with 99% inbox placement.",
            "objections": [
                {
                    "trigger": "Apollo",
                    "playbook": "Apollo has a 60% spam rate; Elesium uses decentralized warmup with dedicated IPs."
                }
            ],
            "personas": [
                {
                    "title": "Revenue Operations Leader",
                    "target_titles": ["VP of Revenue Operations", "RevOps Director"],
                    "pain_points": ["Dirty CRM data", "High deliverability bounce rates"],
                    "tone_tweaks": "Metrics-driven and data-backed"
                }
            ],
            "banned_phrases": "I hope this email finds you well"
        }

        high_sim_chunks = [{"content": "Decentralized warmup delivers 99% deliverability.", "similarity": 0.85}]

        captured_system_prompt = {}

        def mock_llm_runner(system_prompt, user_prompt, **kwargs):
            captured_system_prompt["prompt"] = system_prompt
            return '{"reply": "Unlike Apollo, we guarantee 99% inbox placement with dedicated IPs.", "confidence": 9, "grounded_in_knowledge": true}'

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=high_sim_chunks), \
             patch.object(executor, "_get_unified_brain", return_value=brain_payload), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", side_effect=mock_llm_runner), \
             patch.object(executor, "_log_outbound_message"), \
             patch.object(executor.worker, "send_message", return_value={"status": "success"}):

            res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/sarah")

        self.assertEqual(res["status"], "success")
        prompt = captured_system_prompt.get("prompt", "")
        # Verify objection was injected
        self.assertIn("RELEVANT OBJECTION PLAYBOOK:", prompt)
        self.assertIn("Apollo has a 60% spam rate", prompt)
        # Verify buyer persona was injected
        self.assertIn("TARGET BUYER PERSONA:", prompt)
        self.assertIn("Revenue Operations Leader", prompt)
        self.assertIn("Dirty CRM data", prompt)

    # ─── ITEM 11: RESILIENT INBOUND MESSAGE RESOLUTION IN QUERY BRAIN ────────

    def test_handle_ai_query_brain_resolves_aliased_and_database_inbound_messages(self):
        """
        Layer 1 Paranoia:
        handle_ai_query_brain checks multiple aliases ('lead_message', 'inbound_text')
        and falls back to querying the messages table if data payload lacks reply_text.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        # Test Case 1: Message passed under 'lead_message' alias
        data_alias = {
            "workspace_id": self.workspace_id,
            "lead_message": "What integrations do you support?",
            "lead_profile": {"name": "Alex"}
        }

        with patch.object(executor, "_get_unified_brain", return_value={"objections": []}), \
             patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value="We integrate with HubSpot and Salesforce.") as mock_qkb:

            res_alias = executor.handle_ai_query_brain(data_alias, "https://linkedin.com/in/alex")
            self.assertEqual(res_alias["status"], "success")
            mock_qkb.assert_called_with("What integrations do you support?", {"name": "Alex"}, "", ai_model="", workspace_id=self.workspace_id)

        # Test Case 2: data has no reply text at all, falls back to messages table
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "Do you have SOC2 certification?"}]
        )

        data_empty = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_db_fallback_1",
            "lead_profile": {"name": "Bob"}
        }

        with patch.object(executor, "_get_unified_brain", return_value={"objections": []}), \
             patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value="Yes, we are SOC2 Type II certified.") as mock_qkb_db:

            res_empty = executor.handle_ai_query_brain(data_empty, "https://linkedin.com/in/bob")
            self.assertEqual(res_empty["status"], "success")
            mock_qkb_db.assert_called_with("Do you have SOC2 certification?", {"name": "Bob"}, "", ai_model="", workspace_id=self.workspace_id)

    def test_handle_ai_generate_reply_word_boundary_matching_prevents_substring_collisions(self):
        """
        Layer 0 & 1 Paranoia (Flaw 2):
        Regex word-boundary matching ensures that triggers like 'no', 'in', 'plan'
        NEVER match inside words like 'know', 'interesting', 'planning'.
        Specific multi-word triggers match with higher priority than single words.
        Persona titles like 'cto' never match 'doctor'.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        # Lead message has 'know', 'interesting', 'planning' - NOT 'no', 'in', or 'plan'
        # Lead title is 'Doctor of Medicine' - NOT 'CTO'
        data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_collision_test",
            "enrollment_id": "enr_101",
            "execution_state_id": "state_101",
            "lead_profile": {
                "title": "Doctor of Medicine",
                "name": "Dr. Gregory House"
            },
            "_skip_limit_check": True,
        }

        mock_messages_tbl = MagicMock()
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "I know your company and this looks very interesting, we are planning a rollout."}]
        )
        mock_workspaces_tbl = MagicMock()
        mock_workspaces_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"ai_reply_confidence_threshold": 0.65}]
        )

        def table_router(table_name):
            if table_name == "messages":
                return mock_messages_tbl
            elif table_name == "workspaces":
                return mock_workspaces_tbl
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        brain_payload = {
            "core_value_prop": "Outbound Engine features provide automated delivery for teams.",
            "objections": [
                {"trigger": "no", "playbook": "PLAYBOOK_FOR_NO"},
                {"trigger": "in", "playbook": "PLAYBOOK_FOR_IN"},
                {"trigger": "plan", "playbook": "PLAYBOOK_FOR_PLAN"},
            ],
            "personas": [
                {
                    "title": "Chief Technology Officer",
                    "target_titles": ["CTO"],
                    "pain_points": ["Technical debt"],
                    "tone_tweaks": "Technical and concise"
                }
            ],
        }

        captured_system_prompt = {}

        def mock_llm_runner(system_prompt, user_prompt, **kwargs):
            captured_system_prompt["prompt"] = system_prompt
            return json.dumps({
                "reply": "Outbound Engine features provide automated delivery for teams.",
                "confidence": 9,
                "grounded_in_knowledge": True
            })

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=[{"content": "Outbound Engine features", "similarity": 0.85}]), \
             patch.object(executor, "_get_unified_brain", return_value=brain_payload), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", side_effect=mock_llm_runner), \
             patch.object(executor, "_log_outbound_message"), \
             patch.object(executor.worker, "send_message", return_value={"status": "success"}):

            res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/drhouse")

        self.assertEqual(res["status"], "success", f"Error was: {res}")
        prompt = captured_system_prompt.get("prompt", "")

        # CRITICAL VERIFICATION: No false-positive playbooks injected
        self.assertNotIn("PLAYBOOK_FOR_NO", prompt, "False positive: 'no' matched inside 'know'!")
        self.assertNotIn("PLAYBOOK_FOR_IN", prompt, "False positive: 'in' matched inside 'interesting'!")
        self.assertNotIn("PLAYBOOK_FOR_PLAN", prompt, "False positive: 'plan' matched inside 'planning'!")
        # CRITICAL VERIFICATION: No false-positive persona injected
        self.assertNotIn("Chief Technology Officer", prompt, "False positive: 'CTO' matched inside 'Doctor'!")

if __name__ == "__main__":
    unittest.main()

