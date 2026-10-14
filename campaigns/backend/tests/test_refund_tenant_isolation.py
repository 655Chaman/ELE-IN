import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from core.backend.services.credit_service import refund_credits
from knowledge.backend.services.llm_generator import LLMGenerator
from integrations.backend.services.elein_crm_service import _safe_refund_credits

class TestRefundMultiTenantIsolation(unittest.TestCase):
    def test_refund_credits_scopes_event_id_by_workspace(self):
        """Layer 0 & 1: Two workspaces using the same bare idempotency key get distinct event IDs."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            # Workspace A refunds with key "lead_error_123"
            res_a = refund_credits(
                workspace_id="ws_tenant_alpha",
                amount=5,
                idempotency_key="lead_error_123"
            )
            # Workspace B refunds with identical key "lead_error_123"
            res_b = refund_credits(
                workspace_id="ws_tenant_beta",
                amount=5,
                idempotency_key="lead_error_123"
            )

        self.assertTrue(res_a.get("success"))
        self.assertTrue(res_b.get("success"))

        calls = mock_supabase.rpc.call_args_list
        self.assertEqual(len(calls), 2)

        # Verify event_id in call 1 contains ws_tenant_alpha
        call_a_args = calls[0][0][1]
        self.assertEqual(call_a_args["p_workspace_id"], "ws_tenant_alpha")
        self.assertEqual(call_a_args["p_event_id"], "refund_ws_tenant_alpha_lead_error_123")

        # Verify event_id in call 2 contains ws_tenant_beta
        call_b_args = calls[1][0][1]
        self.assertEqual(call_b_args["p_workspace_id"], "ws_tenant_beta")
        self.assertEqual(call_b_args["p_event_id"], "refund_ws_tenant_beta_lead_error_123")

        # Zero collision between Tenant Alpha and Tenant Beta!
        self.assertNotEqual(call_a_args["p_event_id"], call_b_args["p_event_id"])

    def test_refund_credits_already_scoped_key_preserved(self):
        """Layer 2: If key already has workspace_id and refund_ prefix, it's not double-prefixed."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            refund_credits(
                workspace_id="ws_alpha",
                amount=10,
                idempotency_key="refund_ws_alpha_custom_key"
            )

        call_args = mock_supabase.rpc.call_args[0][1]
        self.assertEqual(call_args["p_event_id"], "refund_ws_alpha_custom_key")

    def test_crm_safe_refund_credits_multi_tenant_isolation(self):
        """Layer 1: elein_crm_service._safe_refund_credits isolates bare keys per tenant."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

        _safe_refund_credits(
            workspace_id="ws_corp_1",
            amount=2,
            idempotency_key="hubspot_sync_fail_001",
            supabase_client=mock_supabase
        )
        _safe_refund_credits(
            workspace_id="ws_corp_2",
            amount=2,
            idempotency_key="hubspot_sync_fail_001",
            supabase_client=mock_supabase
        )

        calls = mock_supabase.rpc.call_args_list
        self.assertEqual(len(calls), 2)
        event_id_1 = calls[0][0][1]["p_event_id"]
        event_id_2 = calls[1][0][1]["p_event_id"]

        self.assertEqual(event_id_1, "refund_ws_corp_1_hubspot_sync_fail_001")
        self.assertEqual(event_id_2, "refund_ws_corp_2_hubspot_sync_fail_001")
        self.assertNotEqual(event_id_1, event_id_2)

    def test_llm_generator_coaching_refund_isolation(self):
        """Layer 0 & 1: Two workspaces failing on identical transcript text receive isolated refund event IDs."""
        generator = LLMGenerator()
        generator.client = MagicMock()

        # Simulate exception during OpenAI completion creation
        generator.client.chat.completions.create = AsyncMock(side_effect=RuntimeError("GPU cluster capacity exceeded"))

        mock_supabase = MagicMock()
        # Mock successful deduction
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

        identical_transcript = "Hello, I am interested in scheduling a demonstration of your sales software."

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            with patch("knowledge.backend.services.llm_generator.vector_store", MagicMock()):
                async def run_gen_a():
                    chunks = []
                    async for chunk in generator.generate_response(identical_transcript, "", "ws_customer_a"):
                        chunks.append(chunk)
                    return chunks

                async def run_gen_b():
                    chunks = []
                    async for chunk in generator.generate_response(identical_transcript, "", "ws_customer_b"):
                        chunks.append(chunk)
                    return chunks

                asyncio.run(run_gen_a())
                asyncio.run(run_gen_b())

        # Inspect add_credits_safely refund calls
        refund_calls = [
            call for call in mock_supabase.rpc.call_args_list
            if call[0][0] == "add_credits_safely"
        ]
        self.assertEqual(len(refund_calls), 2)

        call_a = refund_calls[0][0][1]
        call_b = refund_calls[1][0][1]

        self.assertEqual(call_a["p_workspace_id"], "ws_customer_a")
        self.assertEqual(call_b["p_workspace_id"], "ws_customer_b")

        self.assertIn("ws_customer_a", call_a["p_event_id"])
        self.assertIn("ws_customer_b", call_b["p_event_id"])
        self.assertTrue(call_a["p_event_id"].startswith("refund_coach_ws_customer_a_"))
        self.assertTrue(call_b["p_event_id"].startswith("refund_coach_ws_customer_b_"))

        # Zero collision!
        self.assertNotEqual(call_a["p_event_id"], call_b["p_event_id"])


if __name__ == "__main__":
    unittest.main()
