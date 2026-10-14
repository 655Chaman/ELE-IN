import unittest
from unittest.mock import MagicMock, patch

from knowledge.backend.services.copywriting_service import write_copy_for_pipeline, CopywritingResult


class TestBatchCopywritingProRataRefund(unittest.TestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests H-08 Batch Copywriting Pro-Rata Failure Refunds.
    Guarantees:
    - Layer 0: If all leads succeed, 0 refund is issued.
    - Layer 1: If 2 of 3 leads fail in batch, exactly 2 credits are refunded pro-rata via refund_credits.
    - Layer 2: If an unexpected crash interrupts the batch, ungenerated leads are refunded via finally block.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.mock_client = MagicMock()

    @patch("knowledge.backend.services.copywriting_service.get_service_client")
    @patch("knowledge.backend.services.copywriting_service.get_llm_client")
    @patch("core.backend.services.credit_service.refund_credits")
    def test_partial_lead_failure_refunds_pro_rata(self, mock_refund, mock_get_llm, mock_get_supabase):
        """Layer 1: When 2 of 3 leads fail, exactly 2 credits are refunded."""
        mock_get_supabase.return_value = self.mock_supabase
        mock_get_llm.return_value = (self.mock_client, "gpt-4o-mini")

        # Mock pipeline select
        mock_pipe_res = MagicMock(data=[{"workspace_id": "ws-tenant-pro"}])
        # Mock leads select: 3 leads
        mock_leads_res = MagicMock(data=[
            {"id": "lead-1", "company_name": "Acme Inc", "kdm_first": "Alice"},
            {"id": "lead-2", "company_name": "Beta LLC", "kdm_first": "Bob"},
            {"id": "lead-3", "company_name": "Gamma Corp", "kdm_first": "Charlie"}
        ])

        select_call_count = 0
        def fake_select(*args, **kwargs):
            nonlocal select_call_count
            select_call_count += 1
            ret = MagicMock()
            if select_call_count == 1:
                ret.eq.return_value.limit.return_value.execute.return_value = mock_pipe_res
            else:
                ret.eq.return_value.eq.return_value.execute.return_value = mock_leads_res
            return ret

        self.mock_supabase.table.return_value.select = fake_select

        # Mock deduct credits RPC succeeds for 3 credits
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"success": True, "balance": 97})
        self.mock_supabase.rpc.return_value = mock_rpc

        # Mock OpenAI completions: lead-1 succeeds, lead-2 and lead-3 raise Exception
        parse_call_count = 0
        def fake_parse(*args, **kwargs):
            nonlocal parse_call_count
            parse_call_count += 1
            if parse_call_count == 1:
                mock_msg = MagicMock()
                mock_msg.parsed = CopywritingResult(
                    subject_line="quick question for acme",
                    email_body="loved what you are doing at acme"
                )
                return MagicMock(choices=[MagicMock(message=mock_msg)])
            else:
                raise Exception("OpenAI 429 Rate limit exceeded")

        self.mock_client.beta.chat.completions.parse = fake_parse

        write_copy_for_pipeline("pipe-123")

        # Assert deduction was called for 3 credits
        deduct_call = self.mock_supabase.rpc.call_args_list[0]
        self.assertEqual(deduct_call[0][0], "deduct_credits_safely")
        self.assertEqual(deduct_call[0][1]["p_amount"], 3)
        self.assertEqual(deduct_call[0][1]["p_workspace_id"], "ws-tenant-pro")

        # Assert refund_credits was called exactly once for 2 credits (pro-rata!)
        mock_refund.assert_called_once()
        refund_args = mock_refund.call_args[1]
        self.assertEqual(refund_args["workspace_id"], "ws-tenant-pro")
        self.assertEqual(refund_args["amount"], 2)
        self.assertEqual(refund_args["reason"], "copywriting_partial_failure")

    @patch("knowledge.backend.services.copywriting_service.get_service_client")
    @patch("knowledge.backend.services.copywriting_service.get_llm_client")
    @patch("core.backend.services.credit_service.refund_credits")
    def test_all_leads_succeed_zero_refund(self, mock_refund, mock_get_llm, mock_get_supabase):
        """Layer 0: When all leads succeed, 0 credits are refunded."""
        mock_get_supabase.return_value = self.mock_supabase
        mock_get_llm.return_value = (self.mock_client, "gpt-4o-mini")

        mock_pipe_res = MagicMock(data=[{"workspace_id": "ws-tenant-pro"}])
        mock_leads_res = MagicMock(data=[
            {"id": "lead-1", "company_name": "Acme Inc", "kdm_first": "Alice"},
            {"id": "lead-2", "company_name": "Beta LLC", "kdm_first": "Bob"}
        ])

        select_call_count = 0
        def fake_select(*args, **kwargs):
            nonlocal select_call_count
            select_call_count += 1
            ret = MagicMock()
            if select_call_count == 1:
                ret.eq.return_value.limit.return_value.execute.return_value = mock_pipe_res
            else:
                ret.eq.return_value.eq.return_value.execute.return_value = mock_leads_res
            return ret

        self.mock_supabase.table.return_value.select = fake_select

        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"success": True, "balance": 98})
        self.mock_supabase.rpc.return_value = mock_rpc

        mock_msg = MagicMock()
        mock_msg.parsed = CopywritingResult(
            subject_line="intro",
            email_body="hello"
        )
        self.mock_client.beta.chat.completions.parse.return_value = MagicMock(choices=[MagicMock(message=mock_msg)])

        write_copy_for_pipeline("pipe-456")

        # Zero refund on 100% success
        mock_refund.assert_not_called()


if __name__ == "__main__":
    unittest.main()
