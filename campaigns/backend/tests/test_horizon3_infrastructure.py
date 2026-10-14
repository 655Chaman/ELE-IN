import unittest
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from integrations.backend.services.linkedin_pool import BrowserPool, BrowserPoolExhaustedError
from knowledge.backend.services.elein_ai_service import get_warmup_phase
from campaigns.backend.routers.elein import _build_proxy_url


class TestHorizon3Infrastructure(unittest.TestCase):
    def test_browser_pool_serialization_and_release(self):
        """Verifies BrowserPool releases account mutex so sequential tasks don't deadlock."""
        pool = BrowserPool(max_size=3)
        acc_id = "test_acc_sender_1"

        # Mock setup function and playwright driver
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_setup = MagicMock(return_value=(mock_browser, mock_context))

        mock_pw = MagicMock()
        mock_pw_inst = MagicMock()
        mock_pw.return_value.start.return_value = mock_pw_inst

        with patch("integrations.backend.services.linkedin_pool.sync_playwright", mock_pw):
            # First acquire
            ctx1 = pool.acquire(acc_id, mock_setup)
            self.assertIsNotNone(ctx1)
            self.assertTrue(pool.account_locks[acc_id].locked())

            # Release first task
            pool.release(acc_id)
            self.assertFalse(pool.account_locks[acc_id].locked(), "Account lock should be released after pool.release()")

            # Second acquire for same account must succeed immediately without timeout
            ctx2 = pool.acquire(acc_id, mock_setup)
            self.assertIsNotNone(ctx2)
            self.assertTrue(pool.account_locks[acc_id].locked())

            # Release second task
            pool.release(acc_id)
            self.assertFalse(pool.account_locks[acc_id].locked())

    def test_warmup_phase_calculations(self):
        """Verifies get_warmup_phase computes phases without datetime.utcnow argument TypeError."""
        # Active account (not warmup)
        res_active = get_warmup_phase("2026-09-01T00:00:00Z", 15, is_warmup=False)
        self.assertEqual(res_active["phase"], "active")
        self.assertEqual(res_active["safety_score"], 100)

        # Warmup account created 3 days ago -> observe
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        res_observe = get_warmup_phase(three_days_ago, 5, is_warmup=True)
        self.assertEqual(res_observe["phase"], "observe")
        self.assertEqual(res_observe["daily_limit"], 10)

        # Warmup account created 10 days ago -> seed
        ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        res_seed = get_warmup_phase(ten_days_ago, 20, is_warmup=True)
        self.assertEqual(res_seed["phase"], "seed")
        self.assertEqual(res_seed["daily_limit"], 25)

        # Warmup account created 18 days ago -> ramp
        eighteen_days_ago = (datetime.now(timezone.utc) - timedelta(days=18)).isoformat()
        res_ramp = get_warmup_phase(eighteen_days_ago, 35, is_warmup=True)
        self.assertEqual(res_ramp["phase"], "ramp")
        self.assertEqual(res_ramp["daily_limit"], 50)

        # Warmup account created 30 days ago -> cruise
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        res_cruise = get_warmup_phase(thirty_days_ago, 40, is_warmup=True)
        self.assertEqual(res_cruise["phase"], "cruise")
        self.assertEqual(res_cruise["daily_limit"], 80)

        # Corrupted / invalid timestamp string fallback
        res_fallback = get_warmup_phase("invalid_timestamp", 0, is_warmup=True)
        self.assertIn("phase", res_fallback)

    def test_build_proxy_url_with_and_without_auth(self):
        """Verifies _build_proxy_url formats HTTP proxy strings properly with credentials."""
        # Case A: Proxy with username & decrypted password
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        # Mock decrypted payload RPC response
        mock_rpc.execute.return_value = MagicMock(data=None)
        mock_supabase.rpc.return_value = mock_rpc

        account_row_auth = {
            "proxy_id": "px_1",
            "proxies": {
                "id": "px_1",
                "protocol": "http",
                "host": "198.51.100.1",
                "port": 8080,
                "username": "proxy_user",
            }
        }
        url_auth = _build_proxy_url(account_row_auth, mock_supabase)
        self.assertIn("http://proxy_user@", url_auth)
        self.assertIn("198.51.100.1:8080", url_auth)

        # Case B: Proxy without username
        account_row_no_auth = {
            "proxies": {
                "protocol": "http",
                "host": "198.51.100.2",
                "port": 3128,
            }
        }
        url_no_auth = _build_proxy_url(account_row_no_auth)
        self.assertEqual(url_no_auth, "http://198.51.100.2:3128")

        # Case C: No proxy assigned
        self.assertIsNone(_build_proxy_url({}))


if __name__ == "__main__":
    unittest.main()
