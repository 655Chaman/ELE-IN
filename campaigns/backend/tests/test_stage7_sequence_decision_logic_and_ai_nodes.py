import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any
import json
import asyncio

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from knowledge.backend.services.elein_ai_service import (
    detect_competitor,
    score_icp_fit,
    write_connection_note,
    query_knowledge_base
)
from knowledge.backend.routers.assets import _mark_asset_failed_safe


class TestStage7SequenceDecisionLogicAndAiNodes(unittest.TestCase):
    """
    Stage 7 Deep Edge-Case Hardening:
    Verifies Flaws 21-26 under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.workspace_id = "ws_stage7_test_456"
        self.executor = EleInNodeExecutor()
        self.executor.workspace_id = self.workspace_id
        self.executor.supabase = MagicMock()

    # ─── FLAW 21: KNOWLEDGE_ASSETS SCHEMA DESYNC TOLERANCE ──────────────────

    def test_mark_asset_failed_safe_tolerates_missing_columns(self):
        """
        Layer 0 & 1 Paranoia (Flaw 21):
        _mark_asset_failed_safe attempts to write 'error_msg' (Migration 009),
        and if PostgREST reports PGRST204 column missing, gracefully falls back
        to 'error_message' or status update alone without throwing or swallowing failure.
        """
        mock_supabase = MagicMock()
        # Case 1: Normal execution (table has error_msg)
        _mark_asset_failed_safe(mock_supabase, "asset_123", "Processing timed out")
        mock_supabase.table.assert_called_with("knowledge_assets")
        mock_supabase.table.return_value.update.assert_called_with({
            "status": "failed",
            "error_msg": "Processing timed out"
        })

        # Case 2: PostgREST error stating error_msg column does not exist -> fall back to error_message
        mock_err_supabase = MagicMock()
        mock_err_supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = [
            Exception("PGRST204: Could not find the 'error_msg' column of 'knowledge_assets'"),
            MagicMock()
        ]
        _mark_asset_failed_safe(mock_err_supabase, "asset_legacy", "Storage error")
        # Second call should attempt error_message
        second_call = mock_err_supabase.table.return_value.update.call_args_list[1][0][0]
        self.assertEqual(second_call.get("status"), "failed")
        self.assertEqual(second_call.get("error_message"), "Storage error")

    # ─── FLAW 22: _MATCH_KEYWORDS WORD BOUNDARIES & PRECEDENCE ──────────────

    def test_match_keywords_word_boundary_and_length_descending(self):
        """
        Layer 0, 1 & 2 Paranoia (Flaw 22):
        _match_keywords uses regex word boundaries so short tokens do not match
        inside longer words. Multi-word phrases match with descending length precedence.
        """
        # "cto" should NOT match "Doctor of Philosophy"
        self.assertFalse(self.executor._match_keywords("Doctor of Philosophy", "cto"))
        self.assertTrue(self.executor._match_keywords("CTO & VP of Tech", "cto"))

        # "dev" should NOT match "Senior delivery manager"
        self.assertFalse(self.executor._match_keywords("Senior delivery manager", "dev"))
        self.assertTrue(self.executor._match_keywords("Senior dev at Stripe", "dev"))

        # "in" should NOT match "Beijing, China"
        self.assertFalse(self.executor._match_keywords("Beijing, China", "in"))
        self.assertTrue(self.executor._match_keywords("Bangalore, IN", "in"))

        # "fund" should NOT match "Company fundamentals are solid"
        self.assertFalse(self.executor._match_keywords("Company fundamentals are solid", "fund"))
        self.assertTrue(self.executor._match_keywords("Recently raised Series A fund round", "fund"))

        # "seed" should NOT match "We will proceed with expansion"
        self.assertFalse(self.executor._match_keywords("We will proceed with expansion", "seed"))
        self.assertTrue(self.executor._match_keywords("Announced seed funding", "seed"))

        # Multi-symbol / tech stack matching: "C++"
        self.assertTrue(self.executor._match_keywords("Experienced in C++ and Python", "c++"))
        self.assertFalse(self.executor._match_keywords("Experienced in Java and Python", "c++"))

        # Multi-word descending precedence: "VP of Sales" vs "VP"
        self.assertTrue(self.executor._match_keywords("Executive VP of Sales", "vp of sales, vp"))

    # ─── FLAW 23: DETECT_COMPETITOR EXTRACTS REAL BRAND NAME & BRAIN FALLBACK ─

    def test_detect_competitor_returns_competitor_name_and_auto_resolves(self):
        """
        Layer 0, 1 & 2 Paranoia (Flaw 23):
        1. detect_competitor returns (competitor_name, reasoning), NEVER literal 'Yes'.
        2. handle_ai_detect_competitor populates variables['detected_competitor'] with the brand.
        3. When competitors list is empty, it auto-resolves competitors from workspace brain differentiators.
        """
        profile = {
            "title": "VP of Revenue Operations",
            "company": "Enterprise Corp",
            "about": "We rely heavily on HubSpot and Apollo for our sales motions."
        }

        # Sub-test 1: detect_competitor returns competitor name, not "Yes"
        with patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover") as mock_llm:
            mock_llm.return_value = json.dumps({
                "detected": True,
                "competitor": "Apollo",
                "reasoning": "Profile mentions Apollo usage for sales motions."
            })
            comp_name, reason = detect_competitor(profile, ["HubSpot", "Apollo", "Lemlist"])
            self.assertEqual(comp_name, "Apollo")
            self.assertIn("Apollo", reason)

        # Sub-test 2: handle_ai_detect_competitor saves competitor brand into variables
        with patch("knowledge.backend.services.elein_ai_service.detect_competitor", return_value=("Apollo", "Uses Apollo")):
            res = self.executor.handle_ai_detect_competitor({
                "lead_profile": profile,
                "competitors": ["HubSpot", "Apollo"]
            }, "https://linkedin.com/in/prospect")

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["branch"], Branch.USING_COMPETITOR.value)
            self.assertTrue(res["competitor_detected"])
            self.assertEqual(res["variables"]["detected_competitor"], "Apollo")
            self.assertEqual(res["variables"]["competitor_name"], "Apollo")

        # Sub-test 3: Auto-resolves competitors from synthesis battlecards when node input is empty
        mock_brain = {
            "key_differentiators": ["Replaces Apollo and Outreach with unified waterfall enrichment"],
            "competitors": []
        }
        with patch.object(self.executor, "_get_unified_brain", return_value=mock_brain), \
             patch("knowledge.backend.services.elein_ai_service.detect_competitor") as mock_det:
            mock_det.return_value = ("Outreach", "Found Outreach")

            res = self.executor.handle_ai_detect_competitor({
                "lead_profile": profile,
                "competitors": [] # empty in node
            }, "https://linkedin.com/in/prospect")

            # Verify detect_competitor was called with auto-extracted ['Apollo', 'Outreach']
            called_comps = mock_det.call_args[0][1]
            self.assertIn("Apollo", called_comps)
            self.assertIn("Outreach", called_comps)
            self.assertEqual(res["variables"]["detected_competitor"], "Outreach")

    # ─── FLAW 24: HANDLE_IF_REPLIED WORD BOUNDARIES & EMPTY REPLY NEUTRAL ────

    def test_handle_if_replied_word_boundary_sentiment_and_empty_reply_neutral(self):
        """
        Layer 1 & 2 Paranoia (Flaw 24):
        1. 'no' does NOT trigger on 'now' or 'notice'.
        2. 'pass' does NOT trigger on 'passion' or 'compassionate'.
        3. Empty reply text defaults to Neutral (never assumes Positive).
        """
        mock_leads_tbl = MagicMock()

        # Case 1: "I will take a look now" (contains 'now', not 'no')
        mock_leads_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"has_replied": True, "last_message_received": "I will take a look now", "reply_sentiment": None}]
        )
        self.executor.supabase.table.return_value = mock_leads_tbl

        res = self.executor.handle_if_replied({"lead_id": "lead_1"}, "https://linkedin.com/in/lead1")
        # Should NOT be classified as negative
        self.assertNotEqual(res["branch"], Branch.NEGATIVE.value)

        # Case 2: "Our team has real passion for this space" (contains 'passion', not 'pass')
        mock_leads_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"has_replied": True, "last_message_received": "Our team has real passion for this space", "reply_sentiment": None}]
        )
        res = self.executor.handle_if_replied({"lead_id": "lead_2"}, "https://linkedin.com/in/lead2")
        self.assertNotEqual(res["branch"], Branch.NEGATIVE.value)

        # Case 3: Actual negative "Not interested, please pass on this"
        mock_leads_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"has_replied": True, "last_message_received": "Not interested, please pass on this", "reply_sentiment": None}]
        )
        res = self.executor.handle_if_replied({"lead_id": "lead_3"}, "https://linkedin.com/in/lead3")
        self.assertEqual(res["branch"], Branch.NEGATIVE.value)

        # Case 4: Empty reply body defaults to NEUTRAL, never POSITIVE
        mock_leads_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"has_replied": True, "last_message_received": "", "reply_sentiment": None}]
        )
        res = self.executor.handle_if_replied({"lead_id": "lead_4"}, "https://linkedin.com/in/lead4")
        self.assertEqual(res["branch"], Branch.NEUTRAL.value)

    # ─── FLAW 25: SCORE_ICP_FIT INGESTS SYNTHESIS TARGET CUSTOMER PROFILE ────

    def test_score_icp_fit_incorporates_synthesis_target_customer_profile(self):
        """
        Layer 0 & 1 Paranoia (Flaw 25):
        score_icp_fit extracts target_customer_profile and primary_pain_points_solved
        from _get_synthesis(workspace_id) and includes them in the LLM evaluation standard.
        """
        synth = {
            "target_customer_profile": "Mid-market B2B SaaS Founders with 10-50 sales reps",
            "primary_pain_points_solved": ["Burned domains", "High bounce rates", "Slow rep onboarding"],
            "core_value_prop": "Autonomous Multichannel Outreach Platform"
        }

        profile = {
            "title": "Co-Founder & CEO",
            "company": "GrowthApp",
            "company_size": "25-50"
        }

        with patch("knowledge.backend.services.elein_ai_service._get_synthesis", return_value=synth), \
             patch("knowledge.backend.services.elein_ai_service._get_knowledge_context", return_value=""), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover") as mock_llm:

            mock_llm.return_value = json.dumps({"result": 88, "reasoning": "Fits founder profile perfectly"})
            score = score_icp_fit(profile, icp_criteria="Series A+ preferred", workspace_id=self.workspace_id)

            self.assertEqual(score, 88)
            system_prompt = mock_llm.call_args[0][0]
            self.assertIn("Mid-market B2B SaaS Founders with 10-50 sales reps", system_prompt)
            self.assertIn("Burned domains", system_prompt)
            self.assertIn("Autonomous Multichannel Outreach Platform", system_prompt)

    # ─── FLAW 26: OUTREACH & Q&A INJECT CONSTITUTION AND BUYER PERSONAS ─────

    def test_write_connection_note_and_query_knowledge_base_inject_constitution_and_personas(self):
        """
        Layer 0 & 1 Paranoia (Flaw 26):
        write_connection_note and query_knowledge_base inject:
        - Layer 1 Workspace Constitution (core value prop, key differentiators, proof points)
        - Layer 4 Target Buyer Persona Directives (tone tweaks, persona pain points)
        """
        synth = {
            "core_value_prop": "Next-Gen LinkedIn Sequencing",
            "key_differentiators": ["Residential proxy rotation", "Realtime reply sentiment routing"],
            "proof_points": ["4.2x higher reply rate across 100k sends"]
        }

        personas = [
            {
                "id": "p_vp_sales",
                "title": "VP of Sales",
                "target_titles": ["VP of Sales", "Head of Sales"],
                "pain_points": ["Missed quota", "Stalled pipeline"],
                "tone_tweaks": "Focus on pipeline velocity and revenue metrics"
            }
        ]

        lead_profile = {
            "name": "David Miller",
            "title": "VP of Sales",
            "company": "Apex Cloud"
        }

        mock_supabase = MagicMock()

        with patch("knowledge.backend.services.elein_ai_service._get_synthesis", return_value=synth), \
             patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("admin.backend.services.persona_service.PersonaService.get_personas", return_value=personas), \
             patch("knowledge.backend.services.elein_ai_service._get_knowledge_context", return_value=""), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value="Great connection note") as mock_llm:

            # 1. Test write_connection_note
            note = write_connection_note(lead_profile, template="Short intro", workspace_id=self.workspace_id)
            self.assertIn("Great connection note", note)
            note_sys_prompt = mock_llm.call_args[0][0]
            self.assertIn("CORE VALUE PROP: Next-Gen LinkedIn Sequencing", note_sys_prompt)
            self.assertIn("TARGET PERSONA: VP of Sales", note_sys_prompt)
            self.assertIn("Focus on pipeline velocity and revenue metrics", note_sys_prompt)

            # 2. Test query_knowledge_base
            reply_resp = query_knowledge_base("How do you compare to Apollo?", lead_profile, "We offer better deliverability", workspace_id=self.workspace_id)
            q_sys_prompt = mock_llm.call_args[0][0]
            self.assertIn("--- LAYER 1: WORKSPACE CONSTITUTION ---", q_sys_prompt)
            self.assertIn("Next-Gen LinkedIn Sequencing", q_sys_prompt)
            self.assertIn("--- LAYER 4: TARGET PERSONA DIRECTIVES ---", q_sys_prompt)
            self.assertIn("Focus on pipeline velocity and revenue metrics", q_sys_prompt)


if __name__ == "__main__":
    unittest.main()
