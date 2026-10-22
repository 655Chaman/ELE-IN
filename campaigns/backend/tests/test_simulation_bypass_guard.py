import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from knowledge.backend.services.elein_ai_service import stream_reply_draft
from knowledge.backend.routers.ai_routes import ai_suggest_reply
from inbox.backend.schemas.inbox import AISuggestRequest


class TestSimulationBypassGuard(unittest.IsolatedAsyncioTestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests H-05 Simulation Isolation and Tier-Aware Credit Enforcement.
    Guarantees:
    - Layer 0: Simulation returns synthetic preview tokens with 0 external LLM calls and 0 credit deduction.
    - Layer 1: Overdraft limits are tier-aware (Free requires >= 5, Paid allows down to -495).
    - Layer 2: Live API keys are never leaked or used when is_simulation=True, preventing free-tier exploit.
    """

    async def test_simulation_mode_never_calls_llm_or_deducts_credits(self):
        """Layer 0 & 2: is_simulation=True returns canned tokens, never queries keys or deducts credits."""
        mock_supabase = MagicMock()
        mock_keys = [{"key": "nvapi-live-secret-key-123", "id": "key-1"}]

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=mock_keys) as mock_get_keys:

            gen = stream_reply_draft(
                sender_name="Bob Smith",
                thread_messages=[{"message_text": "What is your pricing?"}],
                workspace_id="ws-enterprise-victim",
                is_simulation=True
            )
            tokens = [t async for t in gen]
            result_text = "".join(tokens)

            # Assert preview draft was generated synthetically
            self.assertIn("pricing is tailored to team scale", result_text)
            self.assertIn("Bob", result_text)

            # Assert zero credit RPC calls were made
            mock_supabase.rpc.assert_not_called()

            # Assert active API keys function was NEVER even queried
            mock_get_keys.assert_not_called()

    async def test_ai_suggest_route_simulation_skips_preflight(self):
        """Layer 0: In simulation mode, ai_suggest_reply does not block even with zero credits."""
        req = AISuggestRequest(
            sender_name="Alice",
            thread_messages=[{"message_text": "Hello"}],
            is_simulation=True
        )

        with patch("knowledge.backend.services.elein_ai_service.stream_reply_draft") as mock_stream:
            async def dummy_gen():
                yield "Simulated"
                yield " draft"
            mock_stream.return_value = dummy_gen()

            response = await ai_suggest_reply(req, workspace_id="ws-zero-credits")
            self.assertEqual(response.media_type, "text/plain")

    async def test_ai_suggest_route_free_tier_insufficient_credits_blocks(self):
        """Layer 1: Free tier workspace with < 5 credits is rejected with HTTP 402."""
        req = AISuggestRequest(
            sender_name="Alice",
            thread_messages=[{"message_text": "Can we talk?"}],
            is_simulation=False
        )

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE", "plan": "free"}]
        )

        with patch("knowledge.backend.routers.ai_routes.get_credit_balance", return_value=4), \
             patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                await ai_suggest_reply(req, workspace_id="ws-free-user")
            self.assertEqual(ctx.exception.status_code, 402)
            self.assertIn("Insufficient credits", ctx.exception.detail)

    async def test_ai_suggest_route_paid_tier_within_overdraft_passes(self):
        """Layer 1: Paid tier workspace at -400 (within -500 overdraft buffer) passes preflight."""
        req = AISuggestRequest(
            sender_name="Alice",
            thread_messages=[{"message_text": "Can we talk?"}],
            is_simulation=False
        )

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO", "plan": "pro"}]
        )

        with patch("knowledge.backend.routers.ai_routes.get_credit_balance", return_value=-400), \
             patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.stream_reply_draft") as mock_stream:
            async def dummy_gen():
                yield "Ready"
            mock_stream.return_value = dummy_gen()

            response = await ai_suggest_reply(req, workspace_id="ws-pro-user")
            self.assertEqual(response.media_type, "text/plain")

    async def test_ai_suggest_route_paid_tier_exceeding_overdraft_blocks(self):
        """Layer 1: Paid tier workspace at -496 (exceeding -495 threshold) is rejected with HTTP 402."""
        req = AISuggestRequest(
            sender_name="Alice",
            thread_messages=[{"message_text": "Can we talk?"}],
            is_simulation=False
        )

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO", "plan": "pro"}]
        )

        with patch("knowledge.backend.routers.ai_routes.get_credit_balance", return_value=-496), \
             patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                await ai_suggest_reply(req, workspace_id="ws-pro-user")
            self.assertEqual(ctx.exception.status_code, 402)
            self.assertIn("Insufficient credits", ctx.exception.detail)

    async def test_non_simulation_mode_deducts_credits_and_refunds_on_no_keys(self):
        """Layer 1 & 2: Non-simulation mode deducts 5 credits and triggers tenant-isolated refund when no keys."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=[]), \
             patch.dict("os.environ", {"ALLOW_MOCK_BILLING": "false"}):

            gen = stream_reply_draft(
                sender_name="Charlie",
                thread_messages=[{"message_text": "Hello"}],
                workspace_id="ws-tenant-omega",
                idempotency_key="msg_reply_999",
                is_simulation=False
            )
            tokens = [t async for t in gen]
            self.assertEqual(tokens, ["No AI keys configured. Please add NVIDIA API keys to continue."])

            # Check deduct call
            deduct_call = mock_supabase.rpc.call_args_list[0]
            self.assertEqual(deduct_call[0][0], "deduct_credits_safely")
            self.assertEqual(deduct_call[0][1]["p_amount"], 5)
            self.assertEqual(deduct_call[0][1]["p_workspace_id"], "ws-tenant-omega")

            # Check refund call has tenant-isolated event ID
            refund_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "add_credits_safely"]
            self.assertTrue(len(refund_calls) > 0, "Expected add_credits_safely RPC call")
            refund_call = refund_calls[0]
            self.assertEqual(refund_call[0][0], "add_credits_safely")
            self.assertEqual(refund_call[0][1]["p_credits"], 5)
            self.assertEqual(refund_call[0][1]["p_workspace_id"], "ws-tenant-omega")
            self.assertEqual(refund_call[0][1]["p_event_id"], "refund_ws-tenant-omega_msg_reply_999")


if __name__ == "__main__":
    unittest.main()
