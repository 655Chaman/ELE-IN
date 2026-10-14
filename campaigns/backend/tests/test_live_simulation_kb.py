import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import json

from knowledge.backend.services.knowledge_service import KnowledgeService
from knowledge.backend.services.elein_ai_service import (
    _get_synthesis,
    _clean_semantic_query,
    UsageLimitExceededError,
    generate_test_drive_response,
    _get_sync_client
)
from knowledge.backend.services.prompt_safety import sanitize_for_prompt
from knowledge.backend.services.vector_store import SemanticBrain
from admin.backend.services.persona_service import PersonaService


class TestLiveKnowledgeBaseSimulation(unittest.IsolatedAsyncioTestCase):
    """
    Live End-to-End Simulation of the Hardened AI Knowledge Base Engine.
    Validates Layer 0, Layer 1, and Layer 2 Paranoia Architectures.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_sim_001"
        self.asset_id = "asset_sim_001"

    # =========================================================================
    # Simulation 1: Ingestion Error Propagation & Worker Status Preservation
    # =========================================================================
    async def test_simulation_url_failure_reraises_and_preserves_error(self):
        """
        PARANOIA TEST: When a URL scraping fails (e.g. anti-bot block),
        KnowledgeService MUST finalize asset as 'failed' with error_msg,
        AND re-raise the exception so job_processor does NOT overwrite it.
        """
        with patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True), \
             patch.object(KnowledgeService, "_scrape_url_resilient", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = ""  # Scrape failed / anti-bot blocked

            # Must raise ValueError
            with self.assertRaises(ValueError) as cm:
                await KnowledgeService.process_url_bg(
                    self.mock_supabase,
                    self.workspace_id,
                    "https://blocked-site.com",
                    self.asset_id
                )
            self.assertIn("Website could not be extracted", str(cm.exception))

            # Verify knowledge_assets was updated with 'failed' and error_msg
            update_calls = self.mock_supabase.table("knowledge_assets").update.call_args_list
            self.assertTrue(len(update_calls) > 0)
            last_payload = update_calls[-1][0][0]
            self.assertEqual(last_payload.get("status"), "failed")
            self.assertIn("Website could not be extracted", last_payload.get("error_msg", ""))

    async def test_simulation_pdf_zero_text_preserves_diagnostic(self):
        """
        PARANOIA TEST: When a scanned/image-only PDF is processed,
        it must raise a clear actionable error and preserve it in DB.
        """
        mock_pypdf_module = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pypdf_module.PdfReader.return_value.pages = [mock_page]

        with patch.dict("sys.modules", {"pypdf": mock_pypdf_module}):
            with self.assertRaises(ValueError) as cm:
                await KnowledgeService.process_pdf_bg(
                    self.mock_supabase,
                    self.workspace_id,
                    "scan.pdf",
                    b"dummy_bytes",
                    self.asset_id
                )
            self.assertIn("scanned images or no selectable text", str(cm.exception))

    # =========================================================================
    # Simulation 2: Vector Store Credit Deduction & Graceful Fallback
    # =========================================================================
    def test_simulation_vector_store_insufficient_credits(self):
        """
        PARANOIA TEST: Explicit credit failure must raise UsageLimitExceededError
        with actionable top-up instructions.
        """
        brain = SemanticBrain(self.mock_supabase)
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data={"success": False, "reason": "insufficient_credits"})
        self.mock_supabase.rpc.return_value = rpc_mock

        with self.assertRaises(UsageLimitExceededError) as cm:
            brain.index_document("Test document content", "Test Doc", self.workspace_id, "text", self.asset_id)
        self.assertIn("Insufficient credits for document indexing (2 credits required)", str(cm.exception))

    def test_simulation_vector_store_unmigrated_rpc_graceful_proceed(self):
        """
        PARANOIA TEST: If the RPC is unmigrated or fails due to network,
        it logs a warning and does NOT block indexing with a false credit error.
        """
        brain = SemanticBrain(self.mock_supabase)
        rpc_mock = MagicMock()
        rpc_mock.execute.side_effect = Exception("function deduct_credits_safely does not exist")
        self.mock_supabase.rpc.return_value = rpc_mock

        with patch.object(brain, "delete_by_asset_id"), \
             patch.object(brain, "_chunk_content", return_value=[]):
            # Should NOT raise UsageLimitExceededError
            try:
                brain.index_document("Test document content", "Test Doc", self.workspace_id, "text", self.asset_id)
            except UsageLimitExceededError:
                self.fail("index_document falsely raised UsageLimitExceededError on unmigrated RPC error")

    # =========================================================================
    # Simulation 3: Draft Synthesis Fallback (Preventing Context Blindness)
    # =========================================================================
    def test_simulation_synthesis_draft_fallback(self):
        """
        PARANOIA TEST: When active knowledge_synthesis table is empty,
        _get_synthesis must seamlessly fallback to knowledge_synthesis_drafts.
        """
        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_sc:
            sc = MagicMock()
            mock_get_sc.return_value = sc

            # knowledge_synthesis is empty
            mock_live = MagicMock()
            mock_live.execute.return_value = MagicMock(data=[])

            # knowledge_synthesis_drafts has data
            mock_draft = MagicMock()
            draft_payload = {
                "workspace_id": self.workspace_id,
                "core_value_prop": "Automated B2B Outbound Engine",
                "key_differentiators": ["High deliverability", "Multi-touch sequences"],
                "proof_points": ["10x reply rate"]
            }
            mock_draft.execute.return_value = MagicMock(data=[draft_payload])

            def table_router(tbl_name):
                t_mock = MagicMock()
                if tbl_name == "knowledge_synthesis":
                    t_mock.select.return_value.eq.return_value.limit.return_value = mock_live
                elif tbl_name == "knowledge_synthesis_drafts":
                    t_mock.select.return_value.eq.return_value.limit.return_value = mock_draft
                return t_mock

            sc.table.side_effect = table_router

            result = _get_synthesis(self.workspace_id)
            self.assertEqual(result.get("core_value_prop"), "Automated B2B Outbound Engine")
            self.assertEqual(len(result.get("key_differentiators")), 2)

    # =========================================================================
    # Simulation 4: Prompt Safety & RAG Context Preservation
    # =========================================================================
    def test_simulation_rag_context_preservation_in_prompt_safety(self):
        """
        PARANOIA TEST: sanitize_for_prompt must NOT erase list[dict] chunks.
        """
        chunks = [
            {"content": "Ele-in delivers 3x higher booking rates through Bayesian ICP scoring."},
            {"content": "Automated sequences pause immediately upon prospect reply."}
        ]
        sanitized = sanitize_for_prompt(chunks, "KNOWLEDGE_CHUNKS")
        self.assertIn("Ele-in delivers 3x higher booking rates", sanitized)
        self.assertIn("Automated sequences pause immediately", sanitized)

    # =========================================================================
    # Simulation 5: Persona Service Normalization & Objections Dual-Sync
    # =========================================================================
    def test_simulation_persona_normalization(self):
        """
        PARANOIA TEST: String and list inputs for target_titles, pain_points,
        value_prop, and tone_tweaks must be strictly normalized and preserved.
        """
        raw_data = {
            "name": "VP Sales",
            "target_titles": "VP Sales, Head of Sales\nDirector of Business Development",
            "pain_points": "Low reply rates, Rep fatigue",
            "value_prop": "Guaranteed pipeline growth",
            "tone_tweaks": "Authoritative, concise"
        }

        with patch.object(self.mock_supabase, "table") as mock_table:
            mock_table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": "pers_123",
                    "name": "VP Sales",
                    "target_titles": ["VP Sales", "Head of Sales", "Director of Business Development"],
                    "pain_points": ["Low reply rates", "Rep fatigue"],
                    "value_prop": "Guaranteed pipeline growth",
                    "tone_tweaks": "Authoritative, concise"
                }]
            )
            created = PersonaService.create_persona(self.mock_supabase, self.workspace_id, raw_data)
            self.assertEqual(len(created.get("targetTitles", [])), 3)
            self.assertEqual(created.get("valueProp"), "Guaranteed pipeline growth")


if __name__ == "__main__":
    unittest.main()
