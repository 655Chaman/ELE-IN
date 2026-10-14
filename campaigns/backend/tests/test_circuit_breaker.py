import unittest
from unittest.mock import patch, MagicMock
import time

from integrations.backend.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    get_circuit_breaker,
    reset_all_circuit_breakers,
    execute_with_resilience
)
from integrations.backend.services.elein_crm_service import add_to_smartlead

class TestCircuitBreakerAndResilience(unittest.TestCase):

    def setUp(self):
        reset_all_circuit_breakers()

    def tearDown(self):
        reset_all_circuit_breakers()

    def test_circuit_breaker_trips_to_open_after_threshold_failures(self):
        cb = CircuitBreaker("test_service", failure_threshold=3, recovery_timeout=10.0)
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitBreaker.CLOSED)

        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreaker.CLOSED)

        cb.record_failure() # 3rd failure reaches threshold
        self.assertEqual(cb.state, CircuitBreaker.OPEN)
        self.assertFalse(cb.can_execute())

    def test_circuit_breaker_half_open_recovery(self):
        cb = CircuitBreaker("test_service_recovery", failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreaker.OPEN)
        self.assertFalse(cb.can_execute())

        # Wait for recovery timeout
        time.sleep(0.15)
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitBreaker.HALF_OPEN)

        # Successful probe
        cb.record_success()
        self.assertEqual(cb.state, CircuitBreaker.CLOSED)
        self.assertTrue(cb.can_execute())

    def test_execute_with_resilience_retries_transient_500(self):
        cb = get_circuit_breaker("test_resilience_500", failure_threshold=3)
        
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 502

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200

        request_fn = MagicMock(side_effect=[mock_response_fail, mock_response_success])

        with patch("time.sleep", return_value=None):
            res = execute_with_resilience("test_resilience_500", request_fn, max_retries=3, base_backoff=0.01, circuit_breaker=cb)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(request_fn.call_count, 2)
        self.assertEqual(cb.state, CircuitBreaker.CLOSED)

    def test_execute_with_resilience_raises_when_breaker_open(self):
        cb = get_circuit_breaker("test_open_breaker", failure_threshold=1)
        cb.state = CircuitBreaker.OPEN
        cb.last_failure_time = time.time() # Still within recovery timeout

        request_fn = MagicMock()
        with self.assertRaises(CircuitBreakerOpenException):
            execute_with_resilience("test_open_breaker", request_fn, circuit_breaker=cb)

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    @patch("core.backend.api.auth_dep.get_service_client")
    @patch.dict("os.environ", {"SMARTLEAD_API_KEY": "fake_key"})
    def test_crm_service_refunds_credits_on_final_failure(self, mock_get_client, mock_post):
        mock_supabase = MagicMock()
        # Credit deduction success
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True, "balance": 10})
        mock_get_client.return_value = mock_supabase

        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_post.return_value = mock_response_fail

        leads = [{"id": "lead_1", "email": "test@example.com", "first_name": "Test", "last_name": "User", "company": "Acme"}]
        
        with patch("time.sleep", return_value=None):
            success = add_to_smartlead("workspace_123", leads, "camp_456")

        self.assertFalse(success)
        # Verify add_credits_safely (refund) was called
        refund_called = False
        for call_args in mock_supabase.rpc.call_args_list:
            if call_args[0][0] == 'add_credits_safely':
                refund_called = True
                self.assertEqual(call_args[0][1]['p_workspace_id'], "workspace_123")
                self.assertEqual(call_args[0][1]['p_credits'], 1)
                self.assertEqual(call_args[0][1]['p_provider'], 'system_refund')
        self.assertTrue(refund_called, "add_credits_safely (refund) RPC was not called on final failure")

if __name__ == "__main__":
    unittest.main()
