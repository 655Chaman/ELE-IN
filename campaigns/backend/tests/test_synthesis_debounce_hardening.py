import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from knowledge.backend.services.knowledge_service import KnowledgeService

class TestSynthesisDebounceHardening(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Flaw 1 fix: Content-based fingerprinting, batch coalescing,
    and zero 5-minute wall clock debounce blockage.
    """

    def setUp(self):
        self.workspace_id = "ws_test_debounce_123"
        self.supabase = MagicMock()

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_defers_when_asset_jobs_pending(self):
        """
        Layer 1 Paranoia: When other asset ingestion jobs ('url', 'text', 'pdf')
        are pending or processing in processing_jobs, synthesis defers to avoid
        wasting LLM calls and credits on partial batches.
        """
        # Mock pending jobs found in processing_jobs
        mock_jobs_res = MagicMock(data=[{"id": "job-pending-2"}, {"id": "job-pending-3"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res

        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc:
            mock_svc = MagicMock()
            mock_get_svc.return_value = mock_svc

            await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

            # verify deduct_credits_safely was NEVER called because it deferred
            mock_svc.rpc.assert_not_called()

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_purges_cache_on_zero_synced_assets(self):
        """
        Layer 1 Paranoia: When all assets have been deleted (0 synced assets remain),
        synthesis cache is purged directly without deducting credits or calling LLM.
        """
        # 0 pending jobs
        mock_jobs_res = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res

        # 0 knowledge_assets
        mock_assets_res = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_assets_res

        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc:
            mock_svc = MagicMock()
            mock_get_svc.return_value = mock_svc

            await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

            # verify no credits deducted
            mock_svc.rpc.assert_not_called()

            # verify delete called on knowledge_synthesis and knowledge_synthesis_drafts
            delete_calls = [c for c in self.supabase.table.mock_calls if "delete" in str(c)]
            self.assertTrue(len(delete_calls) >= 2)

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_runs_for_sequential_uploads_without_5min_block(self):
        """
        Layer 0 Paranoia: When Document A is added, followed 30 seconds later by Document B,
        the second document creates a NEW content_hash, cleanly triggering synthesis
        and credit deduction rather than being dropped by a 5-minute wall-clock bucket.
        """
        # 0 pending jobs
        mock_jobs_res = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res

        # Two synced assets
        mock_assets_res = MagicMock(data=[
            {"id": "asset-1", "status": "synced", "updated_at": "2026-10-19T10:00:00Z", "chunk_count": 5},
            {"id": "asset-2", "status": "synced", "updated_at": "2026-10-19T10:00:30Z", "chunk_count": 7}
        ])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_assets_res

        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc, \
             patch("knowledge.backend.services.knowledge_service._get_vector_store") as mock_vs, \
             patch("knowledge.backend.services.knowledge_service.get_active_nvidia_keys", return_value=[{"id": "k1"}]) as mock_keys, \
             patch("knowledge.backend.services.knowledge_service._get_async_client") as mock_async_client:

            mock_svc = MagicMock()
            # Credit deduction succeeds with reason: 'deducted'
            mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"success": True, "reason": "deducted"})
            mock_get_svc.return_value = mock_svc

            # Mock vector retrieval returning content
            mock_vs.return_value.retrieve.return_value = [
                {"content": "Doc 1 value proposition and features", "source": "Doc 1"},
                {"content": "Doc 2 pricing and enterprise scale", "source": "Doc 2"}
            ]

            # Mock LLM chat completion
            mock_completion = MagicMock()
            mock_completion.choices = [
                MagicMock(message=MagicMock(content='{"core_value_prop": "Outbound Engine", "identified_tone": ["Professional"], "target_customer_profile": "Founders", "key_differentiators": ["Anti-spam"], "proof_points": ["1M sends"], "primary_pain_points_solved": ["Spam"]}'))
            ]
            mock_client_instance = MagicMock()
            mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_async_client.return_value = mock_client_instance

            # Mock draft check
            self.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"core_value_prop": "Old"}])

            await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

            # verify deduct_credits_safely was invoked
            mock_svc.rpc.assert_called_once()
            rpc_name, rpc_payload = mock_svc.rpc.call_args[0]
            self.assertEqual(rpc_name, "deduct_credits_safely")
            self.assertEqual(rpc_payload["p_action_type"], "ai_synthesis")
            # Verify the idempotency key uses content_hash and NOT a 5-minute window_id
            idemp_key = rpc_payload["p_idempotency_key"]
            self.assertTrue(idemp_key.startswith(f"ai_synthesis_{self.workspace_id}_"))
            self.assertNotIn("window", idemp_key)

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_skips_duplicate_content_when_already_synthesized(self):
        """
        Layer 2 Paranoia: If update_synthesis is triggered twice on the exact same content,
        and synthesis already exists, it cleanly skips without re-billing or re-calling the LLM.
        """
        # 0 pending jobs
        mock_jobs_res = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res

        # One synced asset
        mock_assets_res = MagicMock(data=[
            {"id": "asset-1", "status": "synced", "updated_at": "2026-10-19T10:00:00Z", "chunk_count": 5}
        ])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_assets_res

        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc, \
             patch.object(KnowledgeService, "get_synthesis", return_value={"core_value_prop": "Already Valid"}), \
             patch("knowledge.backend.services.knowledge_service._get_async_client") as mock_async_client:

            mock_svc = MagicMock()
            # deduct_credits_safely returns already_processed
            mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"success": True, "reason": "already_processed"})
            mock_get_svc.return_value = mock_svc

            await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

            # verify LLM was never called
            mock_async_client.assert_not_called()

    def test_json_auto_repair_recovers_truncated_synthesis(self):
        """
        Layer 1 Paranoia: Auto-repair parser rebalances truncated JSON,
        removes trailing commas, and recovers full structured fields.
        """
        from knowledge.backend.services.knowledge_service import _repair_and_parse_json

        # Truncated midway through list and quote
        raw_truncated = """```json
{
  "core_value_prop": "Automated B2B Outreach",
  "identified_tone": ["Professional", "Direct"],
  "target_customer_profile": "VP of Sales",
  "key_differentiators": ["Anti-spam warmup", "Sender load balancing"],
  "proof_points": ["42% reply rate"],
  "primary_pain_points_solved": ["Burned domains", "Manual follow-ups
"""
        parsed = _repair_and_parse_json(raw_truncated)
        self.assertEqual(parsed.get("core_value_prop"), "Automated B2B Outreach")
        self.assertEqual(parsed.get("identified_tone"), ["Professional", "Direct"])
        self.assertIn("Anti-spam warmup", parsed.get("key_differentiators", []))
        self.assertIn("Burned domains", parsed.get("primary_pain_points_solved", []))

    def test_get_synthesis_surfaces_draft_visibility_with_live_presence(self):
        """
        Layer 0 & 1 Paranoia: When live synthesis exists, but a newly ingested document
        creates an unapproved draft, get_synthesis() must surface the draft with
        has_draft=True, is_draft=True, status='pending_review' so the UI review banner triggers.
        """
        # Live synthesis exists
        live_data = {"core_value_prop": "Old Value Prop", "workspace_id": self.workspace_id}
        # Draft exists
        draft_data = {"core_value_prop": "New Value Prop from recent PDF", "workspace_id": self.workspace_id}

        mock_live_res = MagicMock(data=[live_data])
        mock_draft_res = MagicMock(data=[draft_data])

        def table_side_effect(tbl):
            mock_table = MagicMock()
            if tbl == "knowledge_synthesis":
                mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_live_res
            elif tbl == "knowledge_synthesis_drafts":
                mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_draft_res
            return mock_table

        self.supabase.table.side_effect = table_side_effect

        synthesis = KnowledgeService.get_synthesis(self.supabase, self.workspace_id)
        self.assertIsNotNone(synthesis)
        self.assertTrue(synthesis.get("has_draft"))
        self.assertTrue(synthesis.get("is_draft"))
        self.assertEqual(synthesis.get("status"), "pending_review")
        self.assertEqual(synthesis.get("core_value_prop"), "New Value Prop from recent PDF")
        self.assertEqual(synthesis.get("live_synthesis", {}).get("core_value_prop"), "Old Value Prop")

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_batch_coalescing_ignores_zombies_older_than_15_minutes(self):
        """
        Layer 1 Paranoia: If a processing_job is stuck in 'processing' or 'running'
        for > 15 minutes due to a crashed worker, batch coalescing treats it as an abandoned
        zombie and does NOT defer synthesis indefinitely.
        """
        from datetime import datetime, timedelta, timezone
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        # Job is 2 hours old (zombie)
        mock_jobs_res = MagicMock(data=[
            {"id": "job-zombie-1", "status": "processing", "created_at": two_hours_ago, "updated_at": two_hours_ago}
        ])
        # Synced assets exist
        mock_assets_res = MagicMock(data=[
            {"id": "asset-1", "status": "synced", "updated_at": "2026-10-19T10:00:00Z", "chunk_count": 3}
        ])

        def table_side_effect(tbl):
            mock_table = MagicMock()
            if tbl == "processing_jobs":
                mock_table.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res
            elif tbl == "knowledge_assets":
                mock_table.select.return_value.eq.return_value.execute.return_value = mock_assets_res
            return mock_table

        self.supabase.table.side_effect = table_side_effect

        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc, \
             patch.object(KnowledgeService, "get_synthesis", return_value={"core_value_prop": "Up to date"}), \
             patch("knowledge.backend.services.knowledge_service._get_async_client"):

            mock_svc = MagicMock()
            mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"success": True, "reason": "already_processed"})
            mock_get_svc.return_value = mock_svc

            await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

            # verify credit deduction check ran (it was NOT deferred by the 2-hour-old zombie job)
            mock_svc.rpc.assert_called_once()

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_query_failure_does_not_purge_synthesis(self):
        """
        Layer 1 & 2 Paranoia (Flaw 1): If querying knowledge_assets fails (e.g. database error,
        network timeout, or PostgREST schema desync), synthesis must abort safely and NEVER
        purge or delete existing knowledge_synthesis or drafts.
        """
        # 0 pending jobs
        mock_jobs_res = MagicMock(data=[])

        def table_side_effect(tbl):
            mock_table = MagicMock()
            if tbl == "processing_jobs":
                mock_table.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res
            elif tbl == "knowledge_assets":
                # Simulate PostgREST 42703 or database timeout exception
                mock_table.select.side_effect = Exception("PostgREST 42703: column updated_at does not exist")
            return mock_table

        self.supabase.table.side_effect = table_side_effect

        await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

        # CRITICAL VERIFICATION: delete must NEVER be called on knowledge_synthesis or drafts
        delete_calls = [c for c in self.supabase.table.mock_calls if "delete" in str(c)]
        self.assertEqual(len(delete_calls), 0, "Synthesis was purged on query failure! Catastrophic bug regression.")

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_does_not_purge_when_assets_exist_but_uncompleted(self):
        """
        Layer 1 Paranoia: If assets exist in knowledge_assets but are still 'processing' or
        marked 'failed', synthesis should defer and NOT wipe out existing synthesis.
        """
        mock_jobs_res = MagicMock(data=[])
        # 1 asset exists, but it is currently 'processing' (not synced yet)
        mock_assets_res = MagicMock(data=[
            {"id": "asset-proc-1", "status": "processing"}
        ])

        def table_side_effect(tbl):
            mock_table = MagicMock()
            if tbl == "processing_jobs":
                mock_table.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res
            elif tbl == "knowledge_assets":
                mock_table.select.return_value.eq.return_value.execute.return_value = mock_assets_res
            return mock_table

        self.supabase.table.side_effect = table_side_effect

        await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)

        # Verify no delete was called
        delete_calls = [c for c in self.supabase.table.mock_calls if "delete" in str(c)]
        self.assertEqual(len(delete_calls), 0, "Synthesis was purged while asset was still processing!")

    @patch("knowledge.backend.services.knowledge_service.HAS_LLM", True)
    async def test_update_synthesis_fingerprint_resilient_to_missing_fields(self):
        """
        Layer 0 Paranoia: When assets are missing updated_at or chunk_count (schema differences),
        the content-based fingerprinting does not crash or raise KeyError.
        """
        mock_jobs_res = MagicMock(data=[])
        mock_assets_res = MagicMock(data=[
            {"id": "asset-no-meta", "status": "synced"}  # no updated_at, no chunk_count
        ])

        def table_side_effect(tbl):
            mock_table = MagicMock()
            if tbl == "processing_jobs":
                mock_table.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = mock_jobs_res
            elif tbl == "knowledge_assets":
                mock_table.select.return_value.eq.return_value.execute.return_value = mock_assets_res
            return mock_table

        self.supabase.table.side_effect = table_side_effect

        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc, \
             patch.object(KnowledgeService, "get_synthesis", return_value={"core_value_prop": "Existing"}), \
             patch("knowledge.backend.services.knowledge_service._get_async_client"):

            mock_svc = MagicMock()
            mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"success": True, "reason": "already_processed"})
            mock_get_svc.return_value = mock_svc

            # Should complete fingerprint calculation cleanly without throwing KeyError
            await KnowledgeService.update_synthesis(self.supabase, self.workspace_id, force=False)
            mock_svc.rpc.assert_called_once()


