"""
test_horizon23_orchestrator_concurrency_heartbeat_recovery.py — Horizon 23 Test Suite
Hardening Campaign Orchestrator Concurrency Locks, Heartbeat Monitor & Stalled State Auto-Recovery.
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta

from campaigns.backend.services.elein_orchestrator import (
    try_acquire_session_lock,
    release_session_lock,
    renew_account_session_lock,
    EleInOrchestrator,
)
from campaigns.backend.services.collision_guard import (
    get_conflicting_active_leads,
    is_lead_active_in_other_campaign,
)


class TestHorizon23OrchestratorConcurrencyHeartbeatRecovery(unittest.TestCase):
    """
    Horizon 23 Verification Suite: Concurrency Session Locks, Heartbeat Monitor,
    Stalled State Recovery & Collision Guard Hardening.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_orch_23"
        self.account_id = "acc_sender_23"
        self.worker_id = "worker_daemon_23"
        self.state_id = "state_lead_23"
        self.lease_token = "lease_token_23"

    # =========================================================================
    # Layer 0: The Foundational Layer (RPC Success & Core Mechanics)
    # =========================================================================

    def test_try_acquire_session_lock_rpc_success(self):
        """Layer 0: Acquiring session lock via RPC returns True when free."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=True)
        self.mock_supabase.rpc.return_value = mock_rpc

        acquired = try_acquire_session_lock(
            self.mock_supabase,
            account_id=self.account_id,
            lock_duration_seconds=300,
            worker_id=self.worker_id
        )

        self.assertTrue(acquired)
        self.mock_supabase.rpc.assert_called_with(
            "try_acquire_account_lock",
            {
                "p_account_id": self.account_id,
                "p_duration_seconds": 300,
                "p_worker_id": self.worker_id
            }
        )

    def test_release_session_lock_rpc_success(self):
        """Layer 0: Releasing session lock via RPC returns True."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=True)
        self.mock_supabase.rpc.return_value = mock_rpc

        released = release_session_lock(
            self.mock_supabase,
            account_id=self.account_id,
            worker_id=self.worker_id
        )

        self.assertTrue(released)
        self.mock_supabase.rpc.assert_called_with(
            "release_account_lock",
            {
                "p_account_id": self.account_id,
                "p_worker_id": self.worker_id
            }
        )

    def test_renew_account_session_lock_rpc_success(self):
        """Layer 0: Heartbeat renewal via renew_account_lock RPC returns True."""
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=True)
        self.mock_supabase.rpc.return_value = mock_rpc

        renewed = renew_account_session_lock(
            self.mock_supabase,
            account_id=self.account_id,
            worker_id=self.worker_id,
            extra_seconds=300
        )

        self.assertTrue(renewed)
        self.mock_supabase.rpc.assert_called_with(
            "renew_account_lock",
            {
                "p_account_id": self.account_id,
                "p_worker_id": self.worker_id,
                "p_extra_seconds": 300
            }
        )

    def test_collision_guard_forwards_active_statuses(self):
        """Layer 0: CollisionGuard passes custom active_statuses filter to database queries."""
        from collections import defaultdict
        tables = defaultdict(MagicMock)
        self.mock_supabase.table.side_effect = lambda name: tables[name]

        # Mock enrollments query with chainable methods
        enr_query = MagicMock()
        enr_query.eq.return_value = enr_query
        enr_query.neq.return_value = enr_query
        enr_query.in_.return_value = enr_query
        enr_query.execute.return_value = MagicMock(
            data=[{"id": "enr_1", "campaign_id": "camp_a", "lead_id": "lead_1"}]
        )
        tables["campaign_enrollments"].select.return_value = enr_query

        # Mock campaigns query
        camp_query = MagicMock()
        camp_query.in_.return_value = camp_query
        camp_query.execute.return_value = MagicMock(
            data=[{"id": "camp_a", "status": "ACTIVE"}]
        )
        tables["campaigns"].select.return_value = camp_query

        # Mock states query
        state_query = MagicMock()
        state_query.in_.return_value = state_query
        state_query.execute.return_value = MagicMock(
            data=[{"enrollment_id": "enr_1", "status": "custom_in_flight"}]
        )
        tables["campaign_execution_states"].select.return_value = state_query

        conflicts = get_conflicting_active_leads(
            self.mock_supabase,
            workspace_id=self.workspace_id,
            lead_ids=["lead_1"],
            exclude_campaign_id="camp_b",
            active_statuses=["custom_in_flight"]
        )

        self.assertEqual(conflicts, {"lead_1"})
        state_query.in_.assert_called_with("status", ["custom_in_flight"])

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (RPC Outages, Stalls & Fallbacks)
    # =========================================================================

    def test_try_acquire_session_lock_table_fallback_when_rpc_fails(self):
        """Layer 1: When RPC throws (e.g. PostgREST 404), falls back to optimistic direct table lock."""
        # Make RPC fail
        self.mock_supabase.rpc.side_effect = Exception("PGRST202: Function not found")

        # Mock accounts query (account is currently free)
        mock_acc_query = MagicMock()
        mock_acc_query.execute.return_value = MagicMock(
            data=[{"id": self.account_id, "session_locked_until": None, "session_lock_worker_id": None}]
        )
        mock_upd_query = MagicMock()
        mock_upd_query.execute.return_value = MagicMock(data=[{"id": self.account_id}])

        def table_dispatch(name):
            t = MagicMock()
            if name == "accounts":
                t.select.return_value.eq.return_value = mock_acc_query
                t.update.return_value.eq.return_value = mock_upd_query
            return t

        self.mock_supabase.table.side_effect = table_dispatch

        acquired = try_acquire_session_lock(
            self.mock_supabase,
            account_id=self.account_id,
            lock_duration_seconds=300,
            worker_id=self.worker_id
        )

        self.assertTrue(acquired)
        mock_upd_query.execute.assert_called_once()

    def test_try_acquire_session_lock_fails_closed_when_another_worker_holds_lock(self):
        """Layer 1: Fails closed (False) when another worker holds an active unexpired lock."""
        self.mock_supabase.rpc.side_effect = Exception("PGRST202: Function not found")

        future_iso = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        mock_acc_query = MagicMock()
        mock_acc_query.execute.return_value = MagicMock(
            data=[{"id": self.account_id, "session_locked_until": future_iso, "session_lock_worker_id": "other_worker"}]
        )

        def table_dispatch(name):
            t = MagicMock()
            if name == "accounts":
                t.select.return_value.eq.return_value = mock_acc_query
            return t

        self.mock_supabase.table.side_effect = table_dispatch

        acquired = try_acquire_session_lock(
            self.mock_supabase,
            account_id=self.account_id,
            lock_duration_seconds=300,
            worker_id=self.worker_id
        )

        self.assertFalse(acquired)

    def test_release_session_lock_table_fallback(self):
        """Layer 1: When release RPC fails, falls back to direct table update matching worker ID."""
        self.mock_supabase.rpc.side_effect = Exception("RPC timeout")

        mock_upd = MagicMock()
        mock_upd.execute.return_value = MagicMock(data=[{"id": self.account_id}])
        self.mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value = mock_upd

        released = release_session_lock(
            self.mock_supabase,
            account_id=self.account_id,
            worker_id=self.worker_id
        )

        self.assertTrue(released)
        self.mock_supabase.table.assert_called_with("accounts")

    def test_stale_recovery_recovers_running_and_processing_and_clears_lease(self):
        """Layer 1: Stale recovery resets 'running' and 'processing' states to 'pending' and clears leases."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        # Mock RPC recover_stale_leases
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=2)
        self.mock_supabase.rpc.return_value = mock_rpc

        from collections import defaultdict
        tables = defaultdict(MagicMock)
        self.mock_supabase.table.side_effect = lambda name: tables[name]

        # Setup table returns with chainable mocks
        stale_upd_query = MagicMock()
        stale_upd_query.in_.return_value = stale_upd_query
        stale_upd_query.lt.return_value = stale_upd_query
        stale_upd_query.execute.return_value = MagicMock(data=[{"id": "s1"}])
        tables["campaign_execution_states"].update.return_value = stale_upd_query

        acc_upd_query = MagicMock()
        acc_upd_query.lt.return_value = acc_upd_query
        acc_upd_query.execute.return_value = MagicMock(data=[])
        tables["accounts"].update.return_value = acc_upd_query

        ai_query = MagicMock()
        ai_query.eq.return_value = ai_query
        ai_query.lt.return_value = ai_query
        ai_query.execute.return_value = MagicMock(data=[])
        tables["ai_reply_approvals"].select.return_value = ai_query

        paused_query = MagicMock()
        paused_query.eq.return_value = paused_query
        paused_query.limit.return_value = paused_query
        paused_query.execute.return_value = MagicMock(data=[])
        tables["campaign_execution_states"].select.return_value = paused_query

        camp_query = MagicMock()
        camp_query.eq.return_value = camp_query
        camp_query.execute.return_value = MagicMock(data=[])
        tables["campaigns"].select.return_value = camp_query

        # Run process_pending_leads (empty campaigns returns [])
        results = orchestrator.process_pending_leads()
        self.assertEqual(results, [])

        # Verify update was called with reset payload containing lease_token: None
        update_call_args = tables["campaign_execution_states"].update.call_args[0][0]
        self.assertEqual(update_call_args["status"], "pending")
        self.assertIsNone(update_call_args["lease_token"])
        self.assertIsNone(update_call_args["lease_expires_at"])

    def test_update_state_table_fallback_when_release_claim_rpc_fails(self):
        """Layer 1: update_state falls back to direct table update if release_lead_claim RPC throws."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        self.mock_supabase.rpc.side_effect = Exception("release_lead_claim RPC failed")

        mock_upd_query = MagicMock()
        mock_upd_query.execute.return_value = MagicMock(data=[{"id": self.state_id}])
        self.mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value = mock_upd_query

        orchestrator.update_state(
            state_id=self.state_id,
            node_id="node_next",
            status="completed",
            next_run_at=None,
            lease_token=self.lease_token,
            error_reason=None,
            tz_str="UTC",
            enforce_working_hours=False
        )

        # Fallback table update should have been called
        self.mock_supabase.table.assert_called_with("campaign_execution_states")
        upd_payload = self.mock_supabase.table.return_value.update.call_args[0][0]
        self.assertEqual(upd_payload["status"], "completed")
        self.assertEqual(upd_payload["current_node_id"], "node_next")
        self.assertIsNone(upd_payload["lease_token"])

    # =========================================================================
    # Layer 2: Human Paranoia (Input Hygiene, Malformed Calls & Lease Checks)
    # =========================================================================

    def test_session_lock_handles_empty_account_and_worker_ids(self):
        """Layer 2: Handles None or empty string account_id/worker_id safely without crashing."""
        self.assertFalse(try_acquire_session_lock(self.mock_supabase, account_id="", worker_id=None))
        self.assertFalse(try_acquire_session_lock(self.mock_supabase, account_id=None, worker_id="w1"))
        self.assertFalse(try_acquire_session_lock(None, account_id="acc_1", worker_id="w1"))

        self.assertFalse(release_session_lock(self.mock_supabase, account_id="", worker_id="w1"))
        self.assertFalse(release_session_lock(self.mock_supabase, account_id="acc_1", worker_id=""))
        self.assertFalse(release_session_lock(None, account_id="acc_1", worker_id="w1"))

        self.assertFalse(renew_account_session_lock(self.mock_supabase, account_id="", worker_id="w1"))
        self.assertFalse(renew_account_session_lock(self.mock_supabase, account_id="acc_1", worker_id=""))
        self.assertFalse(renew_account_session_lock(None, account_id="acc_1", worker_id="w1"))

    def test_collision_guard_lead_sanitization(self):
        """Layer 2: Sanitizes lead IDs with None, empty strings, whitespace, and duplicates."""
        from collections import defaultdict
        tables = defaultdict(MagicMock)
        self.mock_supabase.table.side_effect = lambda name: tables[name]

        enr_query = MagicMock()
        enr_query.eq.return_value = enr_query
        enr_query.neq.return_value = enr_query
        enr_query.in_.return_value = enr_query
        enr_query.execute.return_value = MagicMock(data=[])
        tables["campaign_enrollments"].select.return_value = enr_query

        conflicts = get_conflicting_active_leads(
            self.mock_supabase,
            workspace_id="  ws_clean  ",
            lead_ids=["lead_1", "", None, "  lead_1  ", "lead_2", 12345],
            exclude_campaign_id=" camp_x "
        )

        self.assertEqual(conflicts, set())
        # Verify in_ was called with sanitized list: ['lead_1', 'lead_2', '12345']
        enr_query.in_.assert_called_with("lead_id", ["lead_1", "lead_2", "12345"])


if __name__ == "__main__":
    unittest.main()
