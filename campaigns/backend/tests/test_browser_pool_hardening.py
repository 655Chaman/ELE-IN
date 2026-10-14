import unittest
import time as _t
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from integrations.backend.services.linkedin_pool import (
    BrowserPool,
    MAX_BROWSER_OPS,
    MAX_BROWSER_AGE_SECONDS,
    IDLE_BROWSER_TTL_SECONDS,
    BrowserPoolExhaustedError
)
from integrations.backend.services.linkedin_worker import LinkedInWorker
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestBrowserPoolHardening(unittest.TestCase):
    def setUp(self):
        self.supabase = MagicMock()
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data={"success": True})
        self.supabase.rpc.return_value = rpc_mock
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "ACTIVE"}]
        )
        self.orchestrator = EleInOrchestrator(supabase=self.supabase)

    @patch("integrations.backend.services.linkedin_pool.sync_playwright")
    def test_browser_recycles_after_max_ops(self, mock_playwright):
        mock_pw = MagicMock()
        mock_playwright.return_value.start.return_value = mock_pw

        setup_calls = []

        def setup_func(pw):
            b = MagicMock()
            b.is_connected.return_value = True
            c = MagicMock()
            p = MagicMock()
            c.new_page.return_value = p
            setup_calls.append((b, c))
            return b, c

        pool = BrowserPool(max_size=3)

        # 1. First acquire: creates new browser
        ctx1 = pool.acquire("acc1", setup_func)
        self.assertEqual(len(setup_calls), 1)
        first_b, first_c = setup_calls[0]
        self.assertEqual(ctx1, first_c)
        pool.release("acc1")
        self.assertEqual(pool.pool["acc1"]["ops_count"], 1)

        # 2. Simulate operations reaching MAX_BROWSER_OPS threshold
        pool.pool["acc1"]["ops_count"] = MAX_BROWSER_OPS

        # 3. Next acquire: should detect ops >= MAX_BROWSER_OPS, close old and recreate
        ctx2 = pool.acquire("acc1", setup_func)
        self.assertEqual(len(setup_calls), 2)
        second_b, second_c = setup_calls[1]
        self.assertEqual(ctx2, second_c)
        self.assertNotEqual(first_c, second_c)

        # Ensure old entry was cleanly closed
        first_c.close.assert_called()
        first_b.close.assert_called()

        pool.release("acc1")
        self.assertEqual(pool.pool["acc1"]["ops_count"], 1)

    @patch("integrations.backend.services.linkedin_pool.sync_playwright")
    def test_browser_recycles_after_max_age(self, mock_playwright):
        mock_pw = MagicMock()
        mock_playwright.return_value.start.return_value = mock_pw

        setup_calls = []

        def setup_func(pw):
            b = MagicMock()
            b.is_connected.return_value = True
            c = MagicMock()
            p = MagicMock()
            c.new_page.return_value = p
            setup_calls.append((b, c))
            return b, c

        pool = BrowserPool(max_size=3)

        # 1. First acquire
        ctx1 = pool.acquire("acc1", setup_func)
        self.assertEqual(len(setup_calls), 1)
        first_b, first_c = setup_calls[0]
        pool.release("acc1")

        # 2. Artificially age the entry past MAX_BROWSER_AGE_SECONDS
        pool.pool["acc1"]["created_at"] = _t.time() - (MAX_BROWSER_AGE_SECONDS + 60)

        # 3. Next acquire: age exceeded -> evicts and recreates
        ctx2 = pool.acquire("acc1", setup_func)
        self.assertEqual(len(setup_calls), 2)
        second_b, second_c = setup_calls[1]
        self.assertEqual(ctx2, second_c)

        # Verify old was closed
        first_c.close.assert_called()
        first_b.close.assert_called()

        pool.release("acc1")

    @patch("integrations.backend.services.linkedin_pool.sync_playwright")
    def test_browser_reconnect_check_fails_triggers_recreation(self, mock_playwright):
        mock_pw = MagicMock()
        mock_playwright.return_value.start.return_value = mock_pw

        setup_calls = []

        def setup_func(pw):
            b = MagicMock()
            b.is_connected.return_value = True
            c = MagicMock()
            p = MagicMock()
            c.new_page.return_value = p
            setup_calls.append((b, c))
            return b, c

        pool = BrowserPool(max_size=3)

        # 1. First acquire
        ctx1 = pool.acquire("acc1", setup_func)
        self.assertEqual(len(setup_calls), 1)
        first_b, first_c = setup_calls[0]
        pool.release("acc1")

        # 2. Simulate browser crash / disconnect
        first_b.is_connected.return_value = False

        # 3. Next acquire: is_connected() is False -> recreates
        ctx2 = pool.acquire("acc1", setup_func)
        self.assertEqual(len(setup_calls), 2)
        second_b, second_c = setup_calls[1]
        self.assertEqual(ctx2, second_c)

        # Verify old was closed
        first_c.close.assert_called()
        first_b.close.assert_called()

        pool.release("acc1")

    def test_reap_idle_browsers_cleans_aged_idle_entries(self):
        pool = BrowserPool(max_size=3)

        mock_pw1 = MagicMock()
        mock_b1 = MagicMock()
        mock_c1 = MagicMock()

        mock_pw2 = MagicMock()
        mock_b2 = MagicMock()
        mock_c2 = MagicMock()

        mock_pw3 = MagicMock()
        mock_b3 = MagicMock()
        mock_c3 = MagicMock()

        now = _t.time()
        # Aged and idle
        pool.pool["acc_aged_idle"] = {
            "pw": mock_pw1,
            "browser": mock_b1,
            "context": mock_c1,
            "active_count": 0,
            "last_active_at": now - (IDLE_BROWSER_TTL_SECONDS + 100),
            "created_at": now - 2000,
            "ops_count": 5
        }
        # Fresh and idle
        pool.pool["acc_fresh_idle"] = {
            "pw": mock_pw2,
            "browser": mock_b2,
            "context": mock_c2,
            "active_count": 0,
            "last_active_at": now - 10,
            "created_at": now - 50,
            "ops_count": 1
        }
        # Aged but active (in-use)
        pool.pool["acc_aged_active"] = {
            "pw": mock_pw3,
            "browser": mock_b3,
            "context": mock_c3,
            "active_count": 1,
            "last_active_at": now - (IDLE_BROWSER_TTL_SECONDS + 100),
            "created_at": now - 2000,
            "ops_count": 10
        }

        pool.reap_idle_browsers(max_idle_seconds=IDLE_BROWSER_TTL_SECONDS)

        # acc_aged_idle should be reaped
        self.assertNotIn("acc_aged_idle", pool.pool)
        mock_c1.close.assert_called_once()
        mock_b1.close.assert_called_once()
        mock_pw1.stop.assert_called_once()

        # acc_fresh_idle should remain
        self.assertIn("acc_fresh_idle", pool.pool)
        mock_c2.close.assert_not_called()

        # acc_aged_active should remain (active_count > 0)
        self.assertIn("acc_aged_active", pool.pool)
        mock_c3.close.assert_not_called()

    def test_evict_idle_triggers_reap_idle_browsers(self):
        pool = BrowserPool(max_size=3)
        with patch.object(pool, "reap_idle_browsers") as mock_reap:
            pool._evict_idle_if_needed()
            mock_reap.assert_called_once()

    def test_worker_context_sets_page_timeouts(self):
        worker = LinkedInWorker(cookies_json="[]", account_id="acc_timeout_test")
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        with patch("integrations.backend.services.linkedin_worker.global_browser_pool.acquire", return_value=mock_context), \
             patch("integrations.backend.services.linkedin_worker.global_browser_pool.release"):
            with worker._get_or_create_context() as page:
                mock_page.set_default_timeout.assert_called_with(30000)
                mock_page.set_default_navigation_timeout.assert_called_with(30000)
                self.assertEqual(page, mock_page)

    def test_orchestrator_reschedules_on_pool_exhausted(self):
        state = {
            "id": "state_exhaustion_test",
            "current_node_id": "node_step_1",
            "nodes": [{"id": "node_step_1", "node_type": "send_message", "config": {}}],
            "edges": [],
            "account_id": "acc_100",
            "campaign_id": "camp_100",
            "enrollment_id": "enroll_100",
            "workspace_id": "ws_100",
            "opportunity_id": "opp_100",
            "variables": {"test_var": "val1"}
        }

        camp_mock = MagicMock()
        camp_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "ACTIVE"}])
        self.supabase.table.return_value = camp_mock

        with patch("campaigns.backend.services.elein_orchestrator.is_lead_active_in_other_campaign", return_value=False), \
             patch.object(self.orchestrator, "execute_node_action", return_value={"status": "pool_exhausted"}), \
             patch.object(self.orchestrator, "update_state") as mock_update_state, \
             patch.object(self.orchestrator, "mark_error") as mock_mark_error:
            self.orchestrator.process_lead(state, lease_token="lease_token_123")

            mock_mark_error.assert_not_called()
            mock_update_state.assert_called_once()

            args, kwargs = mock_update_state.call_args
            self.assertEqual(args[0], "state_exhaustion_test")
            self.assertEqual(args[1], "node_step_1")
            self.assertEqual(args[2], "pending")

            next_retry = args[3]
            self.assertIsNotNone(next_retry)
            delay = (next_retry - datetime.utcnow()).total_seconds()
            self.assertTrue(25 <= delay <= 65)

            self.assertEqual(kwargs.get("lease_token"), "lease_token_123")
            self.assertEqual(kwargs.get("variables"), {"test_var": "val1"})


if __name__ == "__main__":
    unittest.main()
