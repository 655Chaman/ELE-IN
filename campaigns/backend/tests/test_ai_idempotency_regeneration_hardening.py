import unittest
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from knowledge.backend.services.elein_ai_service import stream_reply_draft
from knowledge.backend.routers.ai_routes import ai_suggest_reply
from inbox.backend.schemas.inbox import AISuggestRequest


class TestAIIdempotencyRegenerationHardening(unittest.IsolatedAsyncioTestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests M-01 Static Idempotency Key & AI Regeneration Hardening.
    
    Guarantees:
    - Layer 0 (Foundational): Two consecutive generations for the same thread messages without an explicit
      key generate distinct nonced idempotency keys and trigger separate 5-credit deductions (no free regenerations).
    - Layer 1 (Environmental): 
        * Replay attempts where RPC returns 'already_processed' immediately abort without LLM invocation.
        * RPC exceptions fail closed with 'AI Error: credit_check_failed'.
        * Phantom refunds are prevented: refund RPC is only invoked if credits were actually deducted.
    - Layer 2 (Human Paranoia): Malicious clients reusing a static idempotency key across requests are blocked.
    """

    async def test_consecutive_regenerations_generate_unique_keys_and_deduct_credits(self):
        """Layer 0: Consecutive calls for the identical thread generate distinct nonces and deduct twice."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True, "reason": "ok"})

        thread = [{"message_text": "Could you share details on pricing?"}]
        mock_keys = [{"key": "nvapi-test-key", "id": "key-1"}]

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=mock_keys), \
             patch.dict("os.environ", {"ALLOW_MOCK_BILLING": "true"}):

            # Call 1: First generation
            gen1 = stream_reply_draft(
                sender_name="Alice",
                thread_messages=thread,
                workspace_id="ws-test-tenant",
                intent="pricing"
            )
            tokens1 = [t async for t in gen1]
            self.assertTrue(len(tokens1) > 0)

            # Call 2: User clicks 'Regenerate' with identical thread messages
            gen2 = stream_reply_draft(
                sender_name="Alice",
                thread_messages=thread,
                workspace_id="ws-test-tenant",
                intent="pricing"
            )
            tokens2 = [t async for t in gen2]
            self.assertTrue(len(tokens2) > 0)

            # Verify that deduct_credits_safely was called for ai_reply_draft TWICE
            deduct_reply_calls = [
                c for c in mock_supabase.rpc.call_args_list 
                if len(c[0]) > 0 and c[0][0] == 'deduct_credits_safely' and c[0][1].get('p_action_type') == 'ai_reply_draft'
            ]
            self.assertEqual(len(deduct_reply_calls), 2)
            call1_args = deduct_reply_calls[0][0][1]
            call2_args = deduct_reply_calls[1][0][1]

            self.assertEqual(call1_args["p_amount"], 5)
            self.assertEqual(call2_args["p_amount"], 5)
            self.assertEqual(call1_args["p_workspace_id"], "ws-test-tenant")
            self.assertEqual(call2_args["p_workspace_id"], "ws-test-tenant")

            # Crucial Layer 0 check: The idempotency keys MUST be distinct despite identical thread messages
            key1 = call1_args["p_idempotency_key"]
            key2 = call2_args["p_idempotency_key"]
            self.assertNotEqual(key1, key2)
            self.assertTrue(key1.startswith("reply_ws-test-tenant_"))
            self.assertTrue(key2.startswith("reply_ws-test-tenant_"))

    async def test_replay_key_already_processed_aborts_without_llm_call(self):
        """Layer 1 & 2: Replay of an existing idempotency key yields duplicate_generation_request without calling LLM."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        # RPC returns already_processed (deduction skipped in DB)
        mock_rpc.execute.return_value = MagicMock(data={"success": True, "reason": "already_processed"})

        mock_keys = [{"key": "nvapi-test-key", "id": "key-1"}]

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=mock_keys) as mock_get_keys:

            gen = stream_reply_draft(
                sender_name="Alice",
                thread_messages=[{"message_text": "Hi"}],
                workspace_id="ws-test-tenant",
                idempotency_key="replayed_key_123"
            )
            tokens = [t async for t in gen]

            self.assertEqual(tokens, ["AI Error: duplicate_generation_request"])
            # Active keys / LLM must NEVER be queried or invoked on duplicate key replay
            mock_get_keys.assert_not_called()

    async def test_credit_deduction_exception_fails_closed(self):
        """Layer 1: RPC network error or database crash fails closed with credit_check_failed."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = RuntimeError("Postgres connection dropped")

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys") as mock_get_keys:

            gen = stream_reply_draft(
                sender_name="Alice",
                thread_messages=[{"message_text": "Hi"}],
                workspace_id="ws-test-tenant"
            )
            tokens = [t async for t in gen]

            self.assertEqual(tokens, ["AI Error: credit_check_failed"])
            mock_get_keys.assert_not_called()

    async def test_no_phantom_refund_when_credits_were_not_deducted(self):
        """Layer 1: If credit deduction was rejected or duplicate, downstream errors do not trigger refunds."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        # Deduction failed due to insufficient credits
        mock_rpc.execute.return_value = MagicMock(data={"success": False, "reason": "insufficient_credits"})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            gen = stream_reply_draft(
                sender_name="Alice",
                thread_messages=[{"message_text": "Hi"}],
                workspace_id="ws-test-tenant"
            )
            tokens = [t async for t in gen]

            self.assertEqual(tokens, ["AI Error: insufficient_credits"])
            # Exactly 1 RPC call was made (deduct_credits_safely). ZERO add_credits_safely calls made!
            self.assertEqual(mock_supabase.rpc.call_count, 1)
            self.assertEqual(mock_supabase.rpc.call_args_list[0][0][0], "deduct_credits_safely")

    async def test_ai_suggest_route_forwards_idempotency_key(self):
        """Layer 0 & 2: ai_suggest_reply route correctly forwards request idempotency_key to stream_reply_draft."""
        req = AISuggestRequest(
            sender_name="Alice",
            thread_messages=[{"message_text": "Hello"}],
            idempotency_key="client-custom-key-777",
            is_simulation=False
        )

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO", "plan": "pro"}]
        )

        with patch("knowledge.backend.routers.ai_routes.get_credit_balance", return_value=100), \
             patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.stream_reply_draft") as mock_stream:

            async def dummy_gen():
                yield "Draft content"
            mock_stream.return_value = dummy_gen()

            response = await ai_suggest_reply(req, workspace_id="ws-pro-user")
            self.assertEqual(response.media_type, "text/plain")

            # Consume the StreamingResponse body iterator to trigger generate()
            chunks = [c async for c in response.body_iterator]
            self.assertTrue(len(chunks) > 0)

            # Verify idempotency_key was passed to stream_reply_draft
            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args[1]
            self.assertEqual(call_kwargs.get("idempotency_key"), "client-custom-key-777")


if __name__ == "__main__":
    unittest.main()
