import unittest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from core.backend.services.credit_service import (
    distributed_workspace_lock,
    trigger_auto_recharge_if_needed,
    reconcile_workspace_credit_ledger,
    _FALLBACK_AUTO_RECHARGE_SETTINGS
)


class TestDistributedWorkspaceLockHardening(unittest.TestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests M-02 Distributed Workspace Lock Hardening.
    
    Guarantees:
    - Layer 0 (Foundational): Database-level distributed lock acquires and releases via Postgres RPC.
      Blocks second worker/pod from entering critical section concurrently.
    - Layer 1 (Environmental): 
        * Database RPC failures failover safely to in-process mutex without crashing.
        * Workspace isolation: locking workspace A does not block workspace B.
        * TTL expiration prevents permanent deadlocks.
    - Layer 2 (Human Paranoia): Rapid concurrent auto-recharge or ledger reconciliation
      across multiple Uvicorn workers skips duplicate charges/repairs cleanly with 'lock_active'.
    """

    def setUp(self):
        self.workspace_a = "ws-tenant-lock-aaa"
        self.workspace_b = "ws-tenant-lock-bbb"
        _FALLBACK_AUTO_RECHARGE_SETTINGS.clear()

    def test_distributed_lock_acquire_and_release_success(self):
        """Layer 0: try_acquire_distributed_lock succeeds, executes block, and calls release_distributed_lock."""
        mock_client = MagicMock()
        mock_rpc_acquire = MagicMock()
        mock_rpc_acquire.execute.return_value = MagicMock(data=True)
        
        mock_rpc_release = MagicMock()
        mock_rpc_release.execute.return_value = MagicMock(data=None)

        def rpc_router(fn_name, params):
            if fn_name == 'try_acquire_distributed_lock':
                return mock_rpc_acquire
            elif fn_name == 'release_distributed_lock':
                return mock_rpc_release
            return MagicMock()

        mock_client.rpc.side_effect = rpc_router

        lock_name = f"auto_recharge:{self.workspace_a}"
        with distributed_workspace_lock(lock_name, ttl_seconds=60, supabase=mock_client) as acquired:
            self.assertTrue(acquired)
            # Verify acquire RPC call parameters
            mock_rpc_acquire.execute.assert_called_once()
            call_params = mock_client.rpc.call_args_list[0][0][1]
            self.assertEqual(call_params['p_lock_name'], lock_name)
            self.assertEqual(call_params['p_ttl_seconds'], 60)

        # Verify release RPC was called on context exit
        mock_rpc_release.execute.assert_called_once()
        release_params = mock_client.rpc.call_args_list[1][0][1]
        self.assertEqual(release_params['p_lock_name'], lock_name)

    def test_concurrent_worker_blocked_when_db_lock_held(self):
        """Layer 0 & 2: When another worker/pod holds the DB lock (RPC returns False), block is not entered."""
        mock_client = MagicMock()
        mock_rpc = MagicMock()
        # Another pod holds the lock: RPC returns False
        mock_rpc.execute.return_value = MagicMock(data=False)
        mock_client.rpc.return_value = mock_rpc

        lock_name = f"auto_recharge:{self.workspace_a}"
        executed = False
        with distributed_workspace_lock(lock_name, ttl_seconds=60, supabase=mock_client) as acquired:
            if acquired:
                executed = True

        self.assertFalse(executed)
        # Release RPC should NOT be called since lock was not acquired
        release_calls = [c for c in mock_client.rpc.call_args_list if c[0][0] == 'release_distributed_lock']
        self.assertEqual(len(release_calls), 0)

    def test_db_rpc_exception_falls_back_to_in_memory_mutex(self):
        """Layer 1: If database RPC fails or is unavailable, lock falls back safely to in-memory mutex."""
        mock_client = MagicMock()
        mock_client.rpc.side_effect = RuntimeError("Postgres connection dropped")

        lock_name = f"test_fallback_lock_{self.workspace_a}"
        executed = False
        with distributed_workspace_lock(lock_name, ttl_seconds=60, supabase=mock_client) as acquired:
            if acquired:
                executed = True

        # In-memory lock acquired, operation proceeds without raising exception
        self.assertTrue(executed)

    def test_different_workspaces_do_not_block_each_other(self):
        """Layer 1: Lock for workspace A does not block independent lock for workspace B."""
        mock_client = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=True)
        mock_client.rpc.return_value = mock_rpc

        lock_a = f"auto_recharge:{self.workspace_a}"
        lock_b = f"auto_recharge:{self.workspace_b}"

        with distributed_workspace_lock(lock_a, ttl_seconds=60, supabase=mock_client) as acq_a:
            self.assertTrue(acq_a)
            # Workspace B can acquire concurrently
            with distributed_workspace_lock(lock_b, ttl_seconds=60, supabase=mock_client) as acq_b:
                self.assertTrue(acq_b)

    def test_auto_recharge_skips_when_lock_active_on_another_worker(self):
        """Layer 2: trigger_auto_recharge_if_needed skips cleanly with 'lock_active' when locked on another pod."""
        mock_lock_client = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=False)  # Lock already held
        mock_lock_client.rpc.return_value = mock_rpc

        with patch("core.backend.services.credit_service.get_lock_client", return_value=mock_lock_client):
            res = trigger_auto_recharge_if_needed(self.workspace_a, current_balance=50)
            self.assertFalse(res["triggered"])
            self.assertEqual(res["reason"], "lock_active")
            self.assertIn("already in progress", res["detail"])

    def test_reconcile_workspace_credit_ledger_skips_when_lock_active(self):
        """Layer 2: reconcile_workspace_credit_ledger returns in_progress when another worker holds lock."""
        mock_client = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=False)  # Lock already held
        mock_client.rpc.return_value = mock_rpc

        res = reconcile_workspace_credit_ledger(self.workspace_a, auto_repair=True, supabase=mock_client)
        self.assertEqual(res["status"], "in_progress")
        self.assertEqual(res["reason"], "lock_active")
        self.assertEqual(res["workspace_id"], self.workspace_a)


if __name__ == "__main__":
    unittest.main()
