"""
Advanced AI Engineer Upgrades Test Suite
========================================
Comprehensive verification for:
1. Cross-Encoder & Reciprocal Rank Fusion (RRF) Reranker Engine
2. Semantic Prompt & Completion Cache with Tenant Isolation
3. Constrained Pydantic Structured Output Extraction with JSON Repair
4. Server-Sent Events (SSE) Token Streaming
5. Empirical Bayes CRM Prior Bootstrapper
6. Automated Copywriting Quality & Regression Evals Engine
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from knowledge.backend.services.reranker_service import (
    rerank_documents,
    compute_bm25_lexical_score,
    compute_cross_attention_heuristic
)
from knowledge.backend.services.semantic_cache import (
    get_cached_completion,
    cache_completion,
    get_cache_stats,
    clear_semantic_cache,
    compute_prompt_cache_key
)
from knowledge.backend.services.structured_output_service import (
    extract_structured_output,
    repair_and_parse_json,
    EmailDraftOutput,
    ProspectClassificationOutput
)
from knowledge.backend.services.streaming_service import (
    format_sse_chunk,
    stream_llm_tokens
)
from knowledge.backend.services.empirical_bayes_bootstrapper import (
    compute_empirical_beta_prior,
    bootstrap_priors_from_crm_deals
)
from knowledge.backend.services.ai_evals_engine import evaluate_copywriting_quality
from knowledge.backend.services.vector_store import SemanticBrain


class TestAdvancedAIEngineerUpgrades(unittest.TestCase):

    def setUp(self):
        clear_semantic_cache()

    def tearDown(self):
        clear_semantic_cache()

    # ─── 1. CROSS-ENCODER & RECIPROCAL RANK FUSION RERANKER ──────────────────

    def test_reranker_prioritizes_exact_answer_chunk(self):
        """Cross-encoder promotes exact semantic matches over broad topical distractors."""
        query = "What is the refund policy for enterprise plans?"
        candidates = [
            {
                "id": "c1",
                "content": "Enterprise plans include dedicated IP pools, custom rate limits, and 24/7 Slack support.",
                "similarity": 0.85
            },
            {
                "id": "c2",
                "content": "Our refund policy for enterprise plans allows a 100% money-back guarantee within 30 days.",
                "similarity": 0.78
            },
            {
                "id": "c3",
                "content": "We support Stripe, wire transfers, and ACH invoicing for annual subscriptions.",
                "similarity": 0.72
            }
        ]
        reranked = rerank_documents(query, candidates, top_k=2)
        self.assertEqual(len(reranked), 2)
        # c2 must be promoted to rank 1 because it contains exact phrase matches
        self.assertEqual(reranked[0]["id"], "c2")
        self.assertIn("rerank_metadata", reranked[0])
        self.assertGreater(reranked[0]["rerank_metadata"]["cross_encoder_score"], 0)

    def test_reranker_handles_empty_inputs_gracefully(self):
        """Handles empty queries and empty lists without crashing."""
        self.assertEqual(rerank_documents("", []), [])
        self.assertEqual(rerank_documents("query", []), [])
        self.assertEqual(rerank_documents("", [{"id": "1", "content": "test"}]), [{"id": "1", "content": "test"}])

    def test_vector_store_integration_with_rerank_flag(self):
        """SemanticBrain.retrieve passes candidates through reranker when rerank=True."""
        brain = SemanticBrain(None)
        # Test in-memory query with rerank=True
        results = brain.retrieve("pricing", "test-ws", rerank=True)
        self.assertIsInstance(results, list)

    # ─── 2. SEMANTIC PROMPT CACHE WITH TENANT ISOLATION ──────────────────────

    def test_semantic_cache_hit_and_miss(self):
        """Validates cache hits, misses, and stats."""
        ws = "ws-tenant-100"
        prompt = "Write an email to a CRO about sales engagement tools"
        
        # Miss
        self.assertIsNone(get_cached_completion(ws, prompt))
        
        # Cache
        expected_output = "Hi there, noticed your revenue growth..."
        cache_completion(ws, prompt, expected_output, ttl_seconds=60)
        
        # Hit
        hit = get_cached_completion(ws, prompt)
        self.assertEqual(hit, expected_output)
        
        stats = get_cache_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertGreater(stats["total_cached_entries"], 0)

    def test_semantic_cache_tenant_isolation(self):
        """Tenant A cannot access Tenant B's cached prompts."""
        prompt = "Confidential business intelligence prompt"
        cache_completion("workspace-A", prompt, "Secret response A")
        
        # Workspace B querying identical prompt must get a cache MISS
        self.assertIsNone(get_cached_completion("workspace-B", prompt))

    # ─── 3. CONSTRAINED STRUCTURED PYDANTIC OUTPUT ───────────────────────────

    def test_extract_structured_output_from_markdown_fence(self):
        """Extracts JSON wrapped in markdown fences into Pydantic EmailDraftOutput."""
        raw_llm = """
        Here is the requested email draft:
        ```json
        {
            "subject": "Quick question on Q4 pipeline",
            "body": "Hi Sarah, loved your latest post on LinkedIn.",
            "call_to_action": "Open to a brief 10-minute catch up next Tuesday?",
            "word_count": 16
        }
        ```
        Let me know if you want any revisions!
        """
        output = extract_structured_output(raw_llm, EmailDraftOutput)
        self.assertIsInstance(output, EmailDraftOutput)
        self.assertEqual(output.subject, "Quick question on Q4 pipeline")
        self.assertEqual(output.word_count, 16)

    def test_extract_structured_output_repairs_unclosed_json(self):
        """Auto-repairs unclosed brackets and trailing commas."""
        broken_json = '{"is_icp": true, "icp_score": 88, "detected_signals": ["is_decision_maker", "has_funding"],'
        output = extract_structured_output(broken_json, ProspectClassificationOutput)
        self.assertIsInstance(output, ProspectClassificationOutput)
        self.assertTrue(output.is_icp)
        self.assertEqual(output.icp_score, 88)
        self.assertEqual(len(output.detected_signals), 2)

    # ─── 4. SERVER-SENT EVENTS (SSE) STREAMING ───────────────────────────────

    def test_format_sse_chunk(self):
        """Generates standard SSE data payloads."""
        chunk = format_sse_chunk("Hello", done=False)
        self.assertTrue(chunk.startswith("data: "))
        self.assertTrue(chunk.endswith("\n\n"))
        self.assertIn('"token": "Hello"', chunk)
        self.assertIn('"done": false', chunk)

    def test_stream_llm_tokens_from_cache(self):
        """Streams cached completion via async generator."""
        ws = "ws-stream-test"
        prompt = "Hello AI"
        cache_completion(ws, f"\n\n{prompt}", "This is a cached stream")

        async def run_stream():
            chunks = []
            async for packet in stream_llm_tokens("", prompt, workspace_id=ws):
                chunks.append(packet)
            return chunks

        packets = asyncio.run(run_stream())
        self.assertGreater(len(packets), 0)
        self.assertTrue(any('"done": true' in p for p in packets))

    # ─── 5. EMPIRICAL BAYES CRM PRIOR BOOTSTRAPPER ───────────────────────────

    def test_bootstrap_priors_from_crm_deals(self):
        """Calculates accurate empirical Beta priors from historical CRM won/lost deals."""
        deals = [
            {"outcome": "closed_won", "signals": {"is_decision_maker": True, "has_funding": True}},
            {"outcome": "closed_won", "signals": {"is_decision_maker": True, "is_target_industry": True}},
            {"outcome": "closed_won", "signals": {"is_decision_maker": True}},
            {"outcome": "closed_lost", "signals": {"is_decision_maker": False, "has_funding": True}},
            {"outcome": "closed_lost", "signals": {"is_decision_maker": False}},
        ]
        priors = bootstrap_priors_from_crm_deals(deals, prior_strength=10.0)
        
        self.assertIn("is_decision_maker", priors)
        dm_stats = priors["is_decision_maker"]
        self.assertEqual(dm_stats["historical_wins"], 3)
        self.assertEqual(dm_stats["historical_losses"], 0)
        # With 3 wins and 0 losses, empirical win rate is high (~0.80) -> prior_alpha > prior_beta
        self.assertGreater(dm_stats["prior_alpha"], dm_stats["prior_beta"])

    # ─── 6. AUTOMATED COPYWRITING QUALITY & EVALS HARNESS ────────────────────

    def test_copywriting_evals_scores_high_quality_email(self):
        """Scores a concise, personalized email with high composite quality."""
        copy = (
            "Hi David — loved seeing Ramp's recent Series D expansion announcement.\n\n"
            "As VP of Sales, scaling outbound reply rates without burning sender domains is critical. "
            "Ele-in uses Bayesian bandits and dedicated residential IPs to cut CAC by 35%.\n\n"
            "Open to a brief 10-minute look this Thursday?"
        )
        context = {
            "first_name": "David",
            "company": "Ramp",
            "title": "VP of Sales",
            "industry": "FinTech"
        }
        res = evaluate_copywriting_quality(copy, context, channel="email")
        self.assertGreaterEqual(res["composite_score"], 80)
        self.assertEqual(res["flags"]["missing_cta_question"], False)
        self.assertEqual(res["flags"]["is_too_long"], False)

    def test_copywriting_evals_penalizes_slop_and_missing_cta(self):
        """Penalizes generic boilerplate without call to action."""
        bad_copy = (
            "I hope this email finds you well. Allow me to introduce myself. We have a cutting-edge, "
            "game-changing platform that will revolutionize your sales team."
        )
        context = {"first_name": "Alex", "company": "Stripe"}
        res = evaluate_copywriting_quality(bad_copy, context, channel="email")
        self.assertLess(res["composite_score"], 60)
        self.assertTrue(res["flags"]["has_ai_slop"])
        self.assertTrue(res["flags"]["missing_cta_question"])


if __name__ == "__main__":
    unittest.main()
