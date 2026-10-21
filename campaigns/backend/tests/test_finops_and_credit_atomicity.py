import os
import json
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from core.backend.api.routers.billing import (
    add_credits_safely_fallback,
    verify_payment,
    VerifyPaymentRequest,
    webhook_razorpay,
    PACKAGES
)
from knowledge.backend.services.elein_ai_service import (
    _get_knowledge_context,
    ROUTING_CONFIG,
    UsageLimitExceededError,
    generate_ai_hook,
    generate_inbound_comment
)


class TestFinOpsAndCreditAtomicity(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-finops-test"
        self.supabase = MagicMock()

    def test_routing_config_cost_effective_models(self):
        """
        Layer 0 & 1 FinOps: Ensure drafting and personalization route to cost-effective models
        (< $0.35/M tokens) rather than high-cost models (Nemotron-340B or Nemotron-120B at $3.50-$4.20/M).
        """
        drafting_models = ROUTING_CONFIG.get("drafting", [])
        self.assertTrue(len(drafting_models) > 0)
        # Verify no 120B or 340B model is the primary default drafting model
        primary_drafting = drafting_models[0]
        self.assertNotIn("340b", primary_drafting.lower())
        self.assertNotIn("super-120b", primary_drafting.lower())

        personalize_models = ROUTING_CONFIG.get("personalize", [])
        self.assertTrue(len(personalize_models) > 0)
        primary_personalize = personalize_models[0]
        self.assertNotIn("340b", primary_personalize.lower())

    def test_knowledge_context_hard_token_ceiling(self):
        """
        Layer 1 & 2 Paranoia: Unbounded vector chunks (e.g. 10,000 words from scraped PDFs)
        are clamped to safe token limits (<= 1,000 tokens) to prevent negative gross margins.
        """
        huge_chunk = "Word " * 5000  # ~5,000 words (~6,500 tokens)
        mock_chunks = [
            {"source": "massive_doc.pdf", "content": huge_chunk},
            {"source": "massive_doc2.pdf", "content": huge_chunk}
        ]

        with patch("knowledge.backend.services.vector_store.vector_store") as mock_vs:
            mock_vs.retrieve.return_value = mock_chunks
            with patch("knowledge.backend.services.elein_ai_service._knowledge_context_cache", {}):
                context = _get_knowledge_context(
                    workspace_id=self.workspace_id,
                    query="product pricing",
                    top_k=5,
                    max_tokens=600
                )
                words = context.split()
                # 600 tokens is ~450 words. Ensure word count is strictly bounded
                self.assertLessEqual(len(words), 500)
                self.assertGreater(len(words), 50)

    def test_add_credits_safely_fallback_unique_collision_prevents_double_credit(self):
        """
        Layer 1 Paranoia: When another worker inserts the event into processed_webhook_events
        concurrently, a unique constraint collision must return immediately without incrementing balance.
        """
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock

        # Step 1: select returns empty (not yet seen)
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        # Step 2: insert throws a unique constraint error (collision with concurrent worker)
        table_mock.insert.return_value.execute.side_effect = RuntimeError("duplicate key value violates unique constraint 'processed_webhook_events_pkey'")

        # Mock rpc to fail so it uses fallback
        self.supabase.rpc.return_value.execute.side_effect = RuntimeError("RPC missing")

        add_credits_safely_fallback(
            supabase=self.supabase,
            workspace_id=self.workspace_id,
            credits=1000,
            event_id="evt_collision_123",
            provider="razorpay"
        )

        # Step 3: workspaces.update must NOT have been called!
        table_mock.update.assert_not_called()

    def test_ai_credit_deduction_fail_closed_on_insufficient_credits(self):
        """
        Layer 0 & 1 Paranoia: When credit balance is depleted or deduction fails,
        AI generation must fail closed by raising UsageLimitExceededError instead of generating for free.
        """
        with patch("core.backend.services.credit_service.deduct_credits", return_value={"success": False, "balance": 0, "reason": "insufficient_credits"}), \
             patch("core.backend.api.auth_dep.get_service_client", return_value=self.supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_effective_keys_for_workspace", return_value=[{"id": "k1", "key": "nvapi-test"}]):

            profile_data = {"name": "Alex", "title": "VP Sales", "company": "Acme Corp"}
            with self.assertRaises(UsageLimitExceededError):
                generate_ai_hook(profile_data, workspace_id="ws-debt-insufficient")

            with self.assertRaises(UsageLimitExceededError):
                generate_inbound_comment(
                    workspace_id="ws-debt-insufficient",
                    post_text="Excited to announce our new funding!",
                    k_obj={"id": "k1", "key": "nvapi-test"}
                )

    def test_verify_payment_already_paid_returns_instantly(self):
        """
        Layer 1 & 2 Paranoia: If Razorpay webhook already processed and paid the session,
        subsequent verify calls return already_verified idempotently without duplicate crediting.
        """
        import asyncio
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        # Session is already marked paid
        table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": self.workspace_id, "package_id": "growth_tier", "status": "paid"}]
        )

        req = VerifyPaymentRequest(
            razorpay_payment_id="pay_already_processed",
            razorpay_order_id="order_123",
            razorpay_signature="sig_123",
            session_id="sess-already-paid"
        )

        res = asyncio.run(verify_payment(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(res["status"], "already_verified")
        self.assertEqual(res["tier"], "PRO")
        # Ensure no credits were added
        self.supabase.rpc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
