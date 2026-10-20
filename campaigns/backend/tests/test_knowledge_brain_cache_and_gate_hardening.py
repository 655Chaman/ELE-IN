import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import (
    EleInNodeExecutor,
    _GLOBAL_BRAIN_CACHE,
    invalidate_brain_cache,
    Branch
)

class TestKnowledgeBrainCacheAndGateHardening(unittest.TestCase):
    """
    Test suite for Flaw 3 (Brain Cache Invalidation) and Flaw 4 (Confidence Gate Reconnection)
    under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.workspace_id = "ws_test_brain_gate_999"
        invalidate_brain_cache()

    def tearDown(self):
        invalidate_brain_cache()

    # ─── FLAW 3: BRAIN CACHE INVALIDATION TESTS ──────────────────────────────

    def test_brain_cache_invalidation_evicts_specific_workspace(self):
        """
        Layer 1 Paranoia: When synthesis, personas, or objections are updated,
        invalidate_brain_cache(workspace_id) evicts that workspace's cached brain
        so subsequent node executions immediately read the latest intelligence.
        """
        global _GLOBAL_BRAIN_CACHE
        # Seed cache for two workspaces
        _GLOBAL_BRAIN_CACHE[self.workspace_id] = {"brain": {"core_value_prop": "Old Prop"}, "timestamp": 1000}
        _GLOBAL_BRAIN_CACHE["ws_other_111"] = {"brain": {"core_value_prop": "Other Prop"}, "timestamp": 1000}

        self.assertIn(self.workspace_id, _GLOBAL_BRAIN_CACHE)
        self.assertIn("ws_other_111", _GLOBAL_BRAIN_CACHE)

        # Evict specific workspace
        invalidate_brain_cache(self.workspace_id)

        self.assertNotIn(self.workspace_id, _GLOBAL_BRAIN_CACHE)
        self.assertIn("ws_other_111", _GLOBAL_BRAIN_CACHE)

    def test_executor_re_fetches_fresh_brain_after_invalidation(self):
        """
        Layer 0 Paranoia: After cache invalidation, _get_unified_brain queries Supabase
        for the latest synthesis rather than returning the stale in-memory cached copy.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        # First query returns initial synthesis
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"core_value_prop": "Initial Version", "workspace_id": self.workspace_id}]
        )

        brain_1 = executor._get_unified_brain(self.workspace_id)
        self.assertEqual(brain_1.get("core_value_prop"), "Initial Version")

        # Second query: even if DB has updated, without invalidation it would return cached copy
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"core_value_prop": "Updated After Document Ingestion", "workspace_id": self.workspace_id}]
        )

        # Before invalidation -> reads cached
        cached_brain = executor._get_unified_brain(self.workspace_id)
        self.assertEqual(cached_brain.get("core_value_prop"), "Initial Version")

        # Now invalidate
        invalidate_brain_cache(self.workspace_id)

        # After invalidation -> reads fresh from DB
        fresh_brain = executor._get_unified_brain(self.workspace_id)
        self.assertEqual(fresh_brain.get("core_value_prop"), "Updated After Document Ingestion")

    # ─── FLAW 4: CONFIDENCE GATE RECONNECTION TESTS ──────────────────────────

    def test_gate_rejects_autonomous_send_when_retrieval_similarity_below_threshold(self):
        """
        Layer 1 Paranoia: When vector search retrieves chunks with similarity 0.45,
        and workspace threshold is 0.65, the gate MUST block autonomous sending
        and route to ai_reply_approvals even if LLM claimed confidence=10.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_123",
            "enrollment_id": "enr_456",
            "execution_state_id": "state_789",
            "_skip_limit_check": True,
        }

        mock_approvals_tbl = MagicMock()
        mock_approvals_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_messages_tbl = MagicMock()
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "Can your software scale to 500 accounts?"}]
        )
        mock_workspaces_tbl = MagicMock()
        mock_workspaces_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"ai_reply_confidence_threshold": 0.65}]
        )

        def table_router(table_name):
            if table_name == "ai_reply_approvals":
                return mock_approvals_tbl
            elif table_name == "messages":
                return mock_messages_tbl
            elif table_name == "workspaces":
                return mock_workspaces_tbl
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        # Chunks similarity is only 0.45 (below threshold 0.65)
        low_sim_chunks = [{"content": "We support multiple accounts safely.", "similarity": 0.45}]

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=low_sim_chunks), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_synthesis", return_value={}), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value='{"reply": "Yes we can scale to 500 accounts without issues.", "confidence": 10, "grounded_in_knowledge": true}'), \
             patch.object(executor, "_get_unified_brain", return_value={}), \
             patch.object(executor, "_send_approval_email"):

            res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/prospect")

        # Gate blocked autonomous send because similarity 0.45 < 0.65
        self.assertEqual(res["status"], "awaiting_approval")
        self.assertIn("Queued for review", res["message"])
        mock_approvals_tbl.insert.assert_called_once()
        inserted_payload = mock_approvals_tbl.insert.call_args[0][0]
        self.assertEqual(inserted_payload["retrieval_score"], 0.45)

    def test_gate_approves_autonomous_send_when_similarity_and_confidence_pass(self):
        """
        Layer 0 Paranoia: When vector search similarity (0.85) >= threshold (0.65),
        LLM confidence (9) >= 8, grounded=True, and overlap passes,
        the gate approves autonomous sending.
        """
        worker = MagicMock()
        worker.send_message.return_value = {"status": "success"}
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_123",
            "enrollment_id": "enr_456",
            "execution_state_id": "state_789",
            "_skip_limit_check": True,
        }

        mock_messages_tbl = MagicMock()
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "Do you offer anti-spam domain protection?"}]
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

        high_sim_chunks = [{"content": "Our platform includes dedicated anti-spam domain protection algorithms.", "similarity": 0.88}]

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=high_sim_chunks), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_synthesis", return_value={}), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value='{"reply": "Yes, our platform includes dedicated anti-spam domain protection algorithms.", "confidence": 9, "grounded_in_knowledge": true}'), \
             patch.object(executor, "_get_unified_brain", return_value={}), \
             patch.object(executor, "_log_outbound_message"):

            res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/prospect")

        # Gate approved autonomous send
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        worker.send_message.assert_called_once_with(
            "https://linkedin.com/in/prospect",
            "Yes, our platform includes dedicated anti-spam domain protection algorithms."
        )
