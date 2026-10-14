import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor

class TestDailyActionRelease(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "test-account-id"
        self.supabase = MagicMock()
        self.executor = EleInNodeExecutor(linkedin_worker=self.worker, supabase=self.supabase, workspace_id="test-ws")

    @patch("campaigns.backend.services.elein_executor.get_effective_usage_date", return_value="2026-10-10")
    def test_release_limit_rpc(self, mock_get_date):
        self.executor._release_limit("message")
        self.supabase.rpc.assert_called_with("release_consumed_daily_action", {
            "p_account_id": "test-account-id",
            "p_action_type": "message",
            "p_usage_date": "2026-10-10"
        })

    def test_enrichment_refund_on_not_found(self):
        # Mock deduct credits success
        mock_deduct = MagicMock()
        mock_deduct.data = {"success": True}
        self.supabase.rpc.return_value.execute.return_value = mock_deduct
        
        # Test enrichment when email not found
        with patch("core.backend.services.credit_service.check_tier_access", return_value=True), \
             patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email", return_value=None):
            res = self.executor._handle_enrichment({"_lead_id": "lead-1"}, "https://linkedin.com/in/test")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["branch"], "Not found")

class TestDataHygieneSanitize(unittest.TestCase):
    def test_sanitize_text(self):
        from leads.backend.services.data_hygiene import DataHygieneService
        dirty = "Hello\x00World\x0bTest"
        cleaned = DataHygieneService.sanitize_text(dirty)
        self.assertEqual(cleaned, "HelloWorldTest")

if __name__ == "__main__":
    unittest.main()
