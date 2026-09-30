import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor

class TestEleInExecutorLimits(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_123"
        self.supabase = MagicMock()
        self.executor = EleInNodeExecutor(linkedin_worker=self.worker, supabase=self.supabase)

    def test_limit_enforcement_normal(self):
        """Normal case: under the limit, action is allowed."""
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data=True)
        self.supabase.rpc.return_value = rpc_mock
        
        self.worker.send_message.return_value = {"status": "success"}
        
        res = self.executor.execute("send_message", {"body": "hello"}, "url")
        
        self.supabase.rpc.assert_called_with("try_consume_daily_action", {
            "p_account_id": "acc_123",
            "p_action_type": "message"
        })
        self.assertNotEqual(res.get("status"), "rate_limited")
        self.worker.send_message.assert_called_once_with("url", "hello")

    def test_limit_enforcement_boundary(self):
        """Exact-boundary case: exact limit reached (last successful), next fails."""
        rpc_mock = MagicMock()
        rpc_mock.execute.side_effect = [MagicMock(data=True), MagicMock(data=False)]
        self.supabase.rpc.return_value = rpc_mock
        self.worker.send_message.return_value = {"status": "success"}
        
        res1 = self.executor.execute("send_message", {"body": "hello"}, "url")
        self.assertNotEqual(res1.get("status"), "rate_limited")
        self.worker.send_message.assert_called_once_with("url", "hello")
        
        # Reset mock to test the next call is blocked
        self.worker.send_message.reset_mock()
        
        res2 = self.executor.execute("send_message", {"body": "hello"}, "url")
        self.assertEqual(res2.get("status"), "rate_limited")
        self.assertIn("Daily limit reached", res2.get("error", ""))
        self.worker.send_message.assert_not_called()

    def test_limit_enforcement_over_limit(self):
        """Over-the-limit rejection: RPC denies the action immediately."""
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data=False)
        self.supabase.rpc.return_value = rpc_mock
        self.worker.send_message.return_value = {"status": "success"}
        
        res = self.executor.execute("send_message", {"body": "hello"}, "url")
        
        self.assertEqual(res.get("status"), "rate_limited")
        self.assertEqual(res.get("error"), "Daily limit reached for action: message")
        self.worker.send_message.assert_not_called()

    def test_limit_enforcement_fail_closed(self):
        """Fail-closed test: RPC raises an exception (e.g. DB down). Action must be BLOCKED."""
        rpc_mock = MagicMock()
        rpc_mock.execute.side_effect = Exception("Database connection lost")
        self.supabase.rpc.return_value = rpc_mock
        self.worker.send_message.return_value = {"status": "success"}
        
        res = self.executor.execute("send_message", {"body": "hello"}, "url")
        
        self.assertEqual(res.get("status"), "rate_limited")
        self.assertIn("Failed to verify rate limits", res.get("error", ""))
        self.worker.send_message.assert_not_called()
        
    def test_sequencer_not_implemented(self):
        """Test the sequencer not-implemented path."""
        res = self.executor.execute("add_to_email_sequencer", {"provider": "Smartlead"}, "url")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Smartlead sequencer integration is not yet implemented", res.get("error"))

    def test_crm_not_implemented(self):
        """Test the CRM missing-handler path."""
        res = self.executor.execute("push_to_crm", {"provider": "Salesforce"}, "url")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Salesforce CRM integration is not yet implemented", res.get("error"))

if __name__ == '__main__':
    unittest.main()
