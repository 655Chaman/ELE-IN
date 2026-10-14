import os
import unittest
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor


class TestSendGridFailureRefundGuard(unittest.TestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests H-07 SendGrid Automatic Refund Guarantees.
    Guarantees:
    - Layer 0: If SendGrid API fails (HTTP 4xx/5xx or network drop), the deducted credit is refunded.
    - Layer 1: If no sender inboxes are available or API key is missing, credit is refunded immediately.
    - Layer 2: Deducted flag prevents duplicate refunds even on cascaded exception handlers.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            supabase=self.mock_supabase,
            workspace_id="ws-tenant-alpha"
        )

    def test_sendgrid_network_error_triggers_refund(self):
        """Layer 0 & 1: SendGrid network timeout/failure refunds 1 credit to workspace."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"success": True})
        self.mock_supabase.rpc.return_value = mock_rpc

        node_data = {
            "to_email": "prospect@example.com",
            "from_email": "sender@elein.ai",
            "subject": "Quick question",
            "body": "Hi there!",
            "_lead_id": "lead-123",
            "_current_node_id": "node-email-1"
        }

        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test_key_123", "ENV": "production", "MOCK_EXTERNAL_SERVICES": "false"}), \
             patch("urllib.request.urlopen", side_effect=Exception("Connection timed out to api.sendgrid.com")), \
             patch("integrations.backend.services.elein_crm_service._safe_refund_credits") as mock_refund:

            res = self.executor.handle_send_email(node_data, linkedin_url=None)
            self.assertEqual(res["status"], "error")
            self.assertIn("Connection timed out", res["error"])

            # Verify deduct call
            deduct_call = self.mock_supabase.rpc.call_args_list[0]
            self.assertEqual(deduct_call[0][0], "deduct_credits_safely")
            self.assertEqual(deduct_call[0][1]["p_amount"], 1)

            # Verify refund call was made exactly once with reason sendgrid_api_error
            mock_refund.assert_called_once_with(
                "ws-tenant-alpha",
                1,
                "sendgrid_ws-tenant-alpha_lead-123_node-email-1",
                self.mock_supabase,
                reason="sendgrid_api_error"
            )

    def test_sendgrid_no_healthy_inboxes_triggers_refund(self):
        """Layer 1: If sender pool has no healthy inboxes, credit is refunded immediately."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"success": True})
        self.mock_supabase.rpc.return_value = mock_rpc

        node_data = {
            "to_email": "prospect@example.com",
            "subject": "Hello",
            "body": "World",
            "use_sender_pool": True,
            "sender_pool_inboxes": ["inbox-1"],
            "_lead_id": "lead-456",
            "_current_node_id": "node-email-2"
        }

        mock_pool_res = {
            "selected": None,
            "selection_reason": "ALL_INBOXES_WARMING_UP"
        }

        with patch("integrations.backend.services.email_sender_service.select_rotating_sender_inbox", return_value=mock_pool_res), \
             patch("integrations.backend.services.elein_crm_service._safe_refund_credits") as mock_refund:

            res = self.executor.handle_send_email(node_data, linkedin_url=None)
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["error"], "ALL_INBOXES_WARMING_UP")

            mock_refund.assert_called_once_with(
                "ws-tenant-alpha",
                1,
                "sendgrid_ws-tenant-alpha_lead-456_node-email-2",
                self.mock_supabase,
                reason="no_healthy_inboxes"
            )

    def test_sendgrid_missing_api_key_production_triggers_refund(self):
        """Layer 1: If SENDGRID_API_KEY is missing in production, credit is refunded."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"success": True})
        self.mock_supabase.rpc.return_value = mock_rpc

        node_data = {
            "to_email": "prospect@example.com",
            "subject": "Hello",
            "body": "World",
            "_lead_id": "lead-789",
            "_current_node_id": "node-email-3"
        }

        with patch.dict(os.environ, {"SENDGRID_API_KEY": "", "ENV": "production", "MOCK_EXTERNAL_SERVICES": "false", "TEST_MODE": ""}), \
             patch("integrations.backend.services.elein_crm_service._safe_refund_credits") as mock_refund:

            res = self.executor.handle_send_email(node_data, linkedin_url=None)
            self.assertEqual(res["status"], "error")
            self.assertIn("SENDGRID_API_KEY is not configured", res["error"])

            mock_refund.assert_called_once_with(
                "ws-tenant-alpha",
                1,
                "sendgrid_ws-tenant-alpha_lead-789_node-email-3",
                self.mock_supabase,
                reason="missing_sendgrid_api_key"
            )

    def test_sendgrid_success_retains_deduction_no_refund(self):
        """Layer 0: Successful delivery keeps credit deduction and does NOT call refund."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"success": True})
        self.mock_supabase.rpc.return_value = mock_rpc

        node_data = {
            "to_email": "prospect@example.com",
            "from_email": "sender@elein.ai",
            "subject": "Great news",
            "body": "Here is the proposal",
            "_lead_id": "lead-win-1",
            "_current_node_id": "node-email-4"
        }

        mock_resp = MagicMock()
        mock_resp.status = 202

        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.valid_key", "ENV": "production", "MOCK_EXTERNAL_SERVICES": "false"}), \
             patch("urllib.request.urlopen") as mock_urlopen, \
             patch("integrations.backend.services.elein_crm_service._safe_refund_credits") as mock_refund:

            mock_urlopen.return_value.__enter__.return_value = mock_resp

            res = self.executor.handle_send_email(node_data, linkedin_url=None)
            self.assertEqual(res["status"], "success")

            # Refund must NOT be called on success!
            mock_refund.assert_not_called()


if __name__ == "__main__":
    unittest.main()
