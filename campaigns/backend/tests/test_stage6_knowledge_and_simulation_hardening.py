import unittest
import json
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from campaigns.backend.services.elein_executor import (
    EleInNodeExecutor,
    _GLOBAL_BRAIN_CACHE,
    invalidate_brain_cache
)
from knowledge.backend.services.elein_ai_service import (
    generate_test_drive_response,
    invalidate_knowledge_context_cache
)
from admin.backend.services.persona_service import PersonaService
from knowledge.backend.services.knowledge_service import KnowledgeService
from knowledge.backend.services.vector_store import SemanticBrain

class TestStage6KnowledgeAndSimulationHardening(unittest.TestCase):
    """
    Test suite for Stage 6: Knowledge & Simulation Deep Edge-Case Hardening.
    Covers Flaws 15, 16, 17, 18, 19, and 20 under the Three-Layer Logic Architecture.
    """

    def setUp(self):
        self.workspace_id = "ws_test_stage6_999"
        invalidate_brain_cache()
        invalidate_knowledge_context_cache()

    def tearDown(self):
        invalidate_brain_cache()
        invalidate_knowledge_context_cache()

    # ─── FLAW 15: TEST-DRIVE OBJECTIONS MERGE & WORD BOUNDARIES ──────────────

    def test_generate_test_drive_response_objections_word_boundary(self):
        r"""
        Layer 0 & 1 Paranoia (Flaw 15):
        Ensures generate_test_drive_response:
        1. Calls PersonaService.get_objections to merge both tables.
        2. Uses regex word boundaries (?<!\w)...(?!\w) so trigger 'no' does not match 'know'.
        3. Prioritizes longer/specific triggers over short ones.
        """
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        objections = [
            {"id": "o1", "trigger": "no", "playbook": "Handle refusal"},
            {"id": "o2", "trigger": "too expensive", "playbook": "Deliver ROI case study"},
            {"id": "o3", "trigger": "expensive", "playbook": "Flexible pricing options"}
        ]

        with patch("admin.backend.services.persona_service.PersonaService.get_objections", return_value=objections) as mock_get_objs, \
             patch("admin.backend.services.persona_service.PersonaService.get_personas", return_value=[]), \
             patch("knowledge.backend.services.elein_ai_service._get_knowledge_context", return_value=""), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value="Handled reply") as mock_llm:

            # Test message contains "know" (should NOT trigger "no") and "too expensive" (should trigger "too expensive", not just "expensive")
            msg = "I know of your solution, but it is too expensive for our current budget."
            res = asyncio.run(generate_test_drive_response(mock_supabase, self.workspace_id, msg))

            mock_get_objs.assert_called_once_with(mock_supabase, self.workspace_id)
            self.assertIn("Handled reply", res)

            system_prompt = mock_llm.call_args.kwargs.get("system_prompt") or mock_llm.call_args[0][0]
            # Should have matched the more specific "too expensive" playbook
            self.assertIn("Deliver ROI case study", system_prompt)
            # Should NOT have matched "no"
            self.assertNotIn("Handle refusal", system_prompt)

    # ─── FLAW 16: TEST-DRIVE BUYER PERSONA INJECTION ─────────────────────────

    def test_generate_test_drive_response_buyer_persona_injection(self):
        """
        Layer 0 & 1 Paranoia (Flaw 16):
        Ensures generate_test_drive_response injects the 4th layer: Buyer Persona Directives.
        """
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        personas = [
            {
                "id": "p_cto",
                "title": "Chief Technology Officer",
                "target_titles": ["CTO", "Chief Technology Officer"],
                "pain_points": ["Cloud infrastructure costs", "Legacy architecture"],
                "tone_tweaks": "Technical, metrics-driven, no fluff"
            }
        ]

        with patch("admin.backend.services.persona_service.PersonaService.get_objections", return_value=[]), \
             patch("admin.backend.services.persona_service.PersonaService.get_personas", return_value=personas) as mock_get_personas, \
             patch("knowledge.backend.services.elein_ai_service._get_knowledge_context", return_value=""), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value="Technical response") as mock_llm:

            msg = "As the CTO of an enterprise fintech, I need scalable solutions."
            res = asyncio.run(generate_test_drive_response(mock_supabase, self.workspace_id, msg))

            mock_get_personas.assert_called_once_with(mock_supabase, self.workspace_id)
            self.assertIn("Technical response", res)

            system_prompt = mock_llm.call_args.kwargs.get("system_prompt") or mock_llm.call_args[0][0]
            self.assertIn("--- LAYER 4: TARGET PERSONA DIRECTIVES ---", system_prompt)
            self.assertIn("Chief Technology Officer", system_prompt)
            self.assertIn("Cloud infrastructure costs", system_prompt)
            self.assertIn("Technical, metrics-driven, no fluff", system_prompt)

    # ─── FLAW 17: CACHE INVALIDATION ON DUPLICATE TRIGGER UPDATE ─────────────

    def test_persona_service_invalidates_cache_on_duplicate_trigger_update(self):
        """
        Layer 1 & 2 Paranoia (Flaw 17):
        When PersonaService.create_objection detects an existing trigger, it updates the record
        and MUST call _invalidate_brain_cache so in-memory nodes don't serve stale playbooks.
        """
        mock_supabase = MagicMock()
        existing_row = {"id": "obj_dup_123", "trigger": "pricing", "playbook": "Old playbook"}
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=existing_row
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "obj_dup_123", "trigger": "pricing", "playbook": "New updated playbook"}]
        )

        with patch("admin.backend.services.persona_service.PersonaService._invalidate_brain_cache") as mock_inv:
            res = PersonaService.create_objection(mock_supabase, self.workspace_id, {
                "trigger": "pricing",
                "playbook": "New updated playbook"
            })
            mock_inv.assert_called_once_with(self.workspace_id)
            self.assertEqual(res["playbook"], "New updated playbook")

    # ─── FLAW 18: EMPTY CONTEXT ZERO-ASSET SYNTHESIS PURGE CACHE INVALIDATION 

    def test_update_synthesis_empty_context_purges_and_invalidates_cache(self):
        """
        Layer 1 Paranoia (Flaw 18):
        When update_synthesis encounters context < 100 chars and 0 remaining assets,
        it purges synthesis and drafts, and flushes the in-memory brain cache.
        """
        mock_supabase = MagicMock()
        # Mock pending jobs check -> 0 active jobs
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        # Mock assets query -> 1 synced asset initially so it passes the first check
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "a1", "status": "synced"}]
        )
        # Mock deduct_credits_safely RPC -> success
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

        # Mock vector store retrieve returning empty/sub-100-char context
        mock_vs = MagicMock()
        mock_vs.retrieve.return_value = []

        # Mock KnowledgeService.get_assets returning 0 assets on the secondary confirmation check
        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.knowledge_service._get_vector_store", return_value=mock_vs), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_assets", return_value=[]), \
             patch("campaigns.backend.services.elein_executor.invalidate_brain_cache") as mock_inv:

            asyncio.run(KnowledgeService.update_synthesis(mock_supabase, self.workspace_id, force=True))
            mock_inv.assert_called_once_with(self.workspace_id)

    # ─── FLAW 19: ADD_KNOWLEDGE_TEXT HASH DEDUPLICATION & ADD_KNOWLEDGE_URL GUARD 

    def test_add_knowledge_text_and_url_deduplication(self):
        """
        Layer 2 Paranoia (Flaw 19):
        1. add_knowledge_text enqueues job with hash and checks processing_jobs across
           ('text', 'text_process') in ('pending', 'processing').
        2. add_knowledge_url prevents duplicate clicks across ('queued', 'processing', 'pending', 'synced').
        """
        from knowledge.backend.routers.assets import add_knowledge_text, add_knowledge_url, TextUpload, UrlUpload
        import hashlib

        mock_supabase = MagicMock()
        # Mock workspace tier FREE
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )

        clean_text = "This is a comprehensive test text for knowledge ingestion."
        text_hash = hashlib.md5(clean_text.encode()).hexdigest()

        # Existing pending job with matching hash
        def mock_table(tbl):
            m = MagicMock()
            if tbl == "processing_jobs":
                m.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "job_123", "asset_id": "asset_dup_123", "payload": {"hash": text_hash}}]
                )
            elif tbl == "knowledge_assets":
                # Returns existing asset
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "asset_dup_123", "name": "Existing Text", "status": "queued"}]
                )
                m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
                    count=1, data=[{"id": "a1"}]
                )
                m.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "asset_url_123", "source_url": "https://example.com/about", "status": "queued"}]
                )
            elif tbl == "workspaces":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"tier": "FREE"}]
                )
            return m

        mock_supabase.table.side_effect = mock_table

        # Case A: Duplicate Text Upload is caught and returns existing asset without inserting
        text_payload = TextUpload(title="Test Snippet", text=clean_text)
        res_text = asyncio.run(add_knowledge_text(text_payload, mock_supabase, self.workspace_id))
        self.assertEqual(res_text["id"], "asset_dup_123")

        # Case B: Duplicate URL Upload is caught in 'queued' state and returns existing asset
        url_payload = UrlUpload(url="https://example.com/about")
        res_url = asyncio.run(add_knowledge_url(url_payload, mock_supabase, self.workspace_id))
        self.assertEqual(res_url["id"], "asset_url_123")

    # ─── FLAW 20: VECTOR STORE DELETE_BY_ASSET_ID MULTI-TENANT ISOLATION ─────

    def test_delete_by_asset_id_enforces_workspace_id(self):
        """
        Layer 1 Paranoia (Flaw 20):
        delete_by_asset_id enforces workspace_id on the deletion query when provided,
        maintaining strict tenant isolation boundaries.
        """
        mock_supabase = MagicMock()
        delete_chain = MagicMock()
        mock_supabase.table.return_value.delete.return_value = delete_chain
        delete_chain.eq.return_value = delete_chain
        delete_chain.execute.return_value = MagicMock()

        sb = SemanticBrain(mock_supabase)
        sb.delete_by_asset_id("asset_999", self.workspace_id)

        # Verify eq was called with both asset_id and workspace_id
        eq_calls = [c[0] for c in delete_chain.eq.call_args_list]
        self.assertIn(("asset_id", "asset_999"), eq_calls)
        self.assertIn(("workspace_id", self.workspace_id), eq_calls)

if __name__ == "__main__":
    unittest.main()
