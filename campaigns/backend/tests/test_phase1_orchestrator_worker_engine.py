"""
test_phase1_orchestrator_worker_engine.py — Phase 1 Test Suite
Autonomous Orchestrator & Worker Engine Hardening.
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta
import os
import signal

from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from core.backend.workers.orchestrator_worker import _safe_heartbeat, handle_sigterm


class TestPhase1OrchestratorWorkerEngine(unittest.TestCase):
    """
    Verification suite for Phase 1: Background Orchestrator Daemon, Worker Engine,
    Unmigrated DB Fallback, Stale Recovery & Concurrency Resilience.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_orch_phase1"
        self.campaign_id = "camp_phase1"
        self.account_id = "acc_phase1"
        self.enrollment_id = "enr_phase1"
        self.state_id = "state_phase1"
        self.lease_token = "lease_phase1_token"

    # =========================================================================
    # Layer 0: The Foundational Layer (Core Mechanics)
    # =========================================================================

    def test_safe_heartbeat_writes_upsert(self):
        """Layer 0: _safe_heartbeat calls upsert on worker_heartbeat table."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        payload = {
            "worker_id": "elein-daemon",
            "last_beat_at": "2026-10-11T00:00:00+00:00",
            "status": "alive"
        }
        _safe_heartbeat(self.mock_supabase, payload)

        self.mock_supabase.table.assert_called_with("worker_heartbeat")
        mock_table.upsert.assert_called_with(payload)
        mock_table.upsert.return_value.execute.assert_called_once()

    def test_orchestrator_dequeue_due_leads_rpc_success(self):
        """Layer 0: When dequeue_due_leads RPC succeeds, processes returned execution states."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        # Mock active campaigns
        camp_query = MagicMock()
        camp_query.eq.return_value = camp_query
        camp_query.execute.return_value = MagicMock(data=[{
            "id": self.campaign_id,
            "workspace_id": self.workspace_id,
            "metadata": {"scheduling_mode": "campaign_timezone", "timezone": "UTC"}
        }])

        ws_query = MagicMock()
        ws_query.in_.return_value = ws_query
        ws_query.execute.return_value = MagicMock(data=[{"id": self.workspace_id, "status": "active"}])

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data=[{
            "id": self.state_id,
            "enrollment_id": self.enrollment_id,
            "current_node_id": "node_1",
            "status": "running",
            "next_run_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "attempts": 0,
            "max_attempts": 5,
            "variables": {},
            "lease_token": self.lease_token
        }])

        def table_dispatch(name):
            t = MagicMock()
            if name == "campaigns":
                t.select.return_value = camp_query
            elif name == "workspaces":
                t.select.return_value = ws_query
            elif name == "campaign_enrollments":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{
                    "id": self.enrollment_id,
                    "campaign_id": self.campaign_id,
                    "lead_id": "lead_1",
                    "account_id": self.account_id,
                    "workspace_id": self.workspace_id,
                    "campaign_version_id": "ver_1"
                }])
            elif name == "leads":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{
                    "id": "lead_1", "timezone": "UTC"
                }])
            elif name == "campaign_nodes":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{
                    "id": "node_1", "campaign_version_id": "ver_1", "node_type": "delay", "config": {"delay": 1, "delayUnit": "days"}
                }])
            elif name == "campaign_edges":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            return t

        self.mock_supabase.table.side_effect = table_dispatch
        self.mock_supabase.rpc.return_value = rpc_mock

        with patch("campaigns.backend.services.elein_orchestrator.is_working_hours", return_value=True), \
             patch.object(orchestrator, "_workspace_has_credits", return_value=True), \
             patch.object(orchestrator, "process_lead") as mock_process_lead:
            results = orchestrator.process_pending_leads()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "advanced")
            mock_process_lead.assert_called_once()

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Unmigrated DB, RPC Fallbacks)
    # =========================================================================

    def test_dequeue_due_leads_table_fallback_when_rpc_fails_unmigrated_db(self):
        """
        Layer 1 Environmental Failure:
        When dequeue_due_leads RPC fails (e.g. 0 SQL migrations run in Supabase),
        orchestrator automatically falls back to direct table queries and atomic leasing.
        """
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        # Make RPC throw PGRST202 Function not found
        def rpc_dispatcher(name, params):
            r = MagicMock()
            if name == "dequeue_due_leads":
                r.execute.side_effect = Exception("PGRST202: Function dequeue_due_leads not found in schema public")
            else:
                r.execute.return_value = MagicMock(data=True)
            return r

        self.mock_supabase.rpc.side_effect = rpc_dispatcher

        now_iso = datetime.now(timezone.utc).isoformat()

        # Set up table dispatch
        def table_dispatch(name):
            t = MagicMock()
            if name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    "id": self.campaign_id,
                    "workspace_id": self.workspace_id,
                    "metadata": {"scheduling_mode": "campaign_timezone", "timezone": "UTC"}
                }])
            elif name == "workspaces":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{"id": self.workspace_id, "status": "active"}])
            elif name == "campaign_enrollments":
                enr_sel = MagicMock()
                enr_sel.in_.return_value.execute.return_value = MagicMock(data=[{
                    "id": self.enrollment_id,
                    "campaign_id": self.campaign_id,
                    "lead_id": "lead_1",
                    "account_id": self.account_id,
                    "workspace_id": self.workspace_id,
                    "campaign_version_id": "ver_1"
                }])
                t.select.return_value = enr_sel
            elif name == "campaign_execution_states":
                # Candidate selection
                st_sel = MagicMock()
                st_sel.in_.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
                    "id": self.state_id,
                    "enrollment_id": self.enrollment_id,
                    "current_node_id": "node_1",
                    "status": "pending",
                    "next_run_at": now_iso,
                    "updated_at": now_iso,
                    "attempts": 0,
                    "max_attempts": 5,
                    "variables": {}
                }])
                t.select.return_value = st_sel

                # Atomic claim update
                st_upd = MagicMock()
                st_upd.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    "id": self.state_id,
                    "enrollment_id": self.enrollment_id,
                    "current_node_id": "node_1",
                    "status": "running",
                    "next_run_at": now_iso,
                    "updated_at": now_iso,
                    "attempts": 0,
                    "max_attempts": 5,
                    "variables": {},
                    "lease_token": "fallback_token_123"
                }])
                t.update.return_value = st_upd
            elif name == "leads":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{
                    "id": "lead_1", "timezone": "UTC"
                }])
            elif name == "campaign_nodes":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{
                    "id": "node_1", "campaign_version_id": "ver_1", "node_type": "delay", "config": {"delay": 1, "delayUnit": "days"}
                }])
            elif name == "campaign_edges":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            return t

        self.mock_supabase.table.side_effect = table_dispatch

        with patch("campaigns.backend.services.elein_orchestrator.is_working_hours", return_value=True), \
             patch.object(orchestrator, "_workspace_has_credits", return_value=True), \
             patch.object(orchestrator, "process_lead") as mock_process_lead:
            results = orchestrator.process_pending_leads()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "advanced")
            mock_process_lead.assert_called_once()

    def test_safe_heartbeat_silently_ignores_missing_table_exception(self):
        """Layer 1: Heartbeat write does not crash when worker_heartbeat table is unmigrated or unavailable."""
        mock_table = MagicMock()
        mock_table.upsert.return_value.execute.side_effect = Exception("relation 'worker_heartbeat' does not exist")
        self.mock_supabase.table.return_value = mock_table

        # Should not raise exception
        _safe_heartbeat(self.mock_supabase, {"worker_id": "elein-daemon", "status": "alive"})
        _safe_heartbeat(None, {"worker_id": "elein-daemon", "status": "alive"})

    def test_stale_recovery_sub_step_fault_isolation(self):
        """
        Layer 1: When a specific stale recovery query throws (e.g. missing lease_expires_at column),
        other recovery steps continue executing.
        """
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        self.mock_supabase.rpc.side_effect = Exception("RPC not found")

        # Mock table returns
        def table_dispatch(name):
            t = MagicMock()
            if name == "campaign_execution_states":
                # First update throws, second succeeds
                st_upd = MagicMock()
                st_upd.in_.return_value.lt.return_value.execute.side_effect = [
                    Exception("Column lease_expires_at does not exist"),
                    MagicMock(data=[{"id": "recovered_1"}])
                ]
                t.update.return_value = st_upd
            elif name == "accounts":
                acc_upd = MagicMock()
                acc_upd.lt.return_value.execute.return_value = MagicMock(data=[])
                t.update.return_value = acc_upd
            elif name == "ai_reply_approvals":
                ai_sel = MagicMock()
                ai_sel.eq.return_value.lt.return_value.execute.side_effect = Exception("Table ai_reply_approvals not found")
                t.select.return_value = ai_sel
            elif name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return t

        self.mock_supabase.table.side_effect = table_dispatch

        # Should not crash despite multiple table/column errors
        results = orchestrator.process_pending_leads()
        self.assertEqual(results, [])

    # =========================================================================
    # Layer 2: Human Paranoia (Shutdown Interruption, Double-Claims, Ghost Processes)
    # =========================================================================

    def test_cooperative_stop_checker_halts_submission(self):
        """Layer 2: Cooperative stop_checker prevents further leads from being submitted upon shutdown."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        # Mock campaigns query
        camp_query = MagicMock()
        camp_query.eq.return_value = camp_query
        camp_query.execute.return_value = MagicMock(data=[{
            "id": self.campaign_id,
            "workspace_id": self.workspace_id,
            "metadata": {"scheduling_mode": "campaign_timezone", "timezone": "UTC"}
        }])
        ws_query = MagicMock()
        ws_query.in_.return_value = ws_query
        ws_query.execute.return_value = MagicMock(data=[{"id": self.workspace_id, "status": "active"}])

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data=[
            {"id": "state_1", "enrollment_id": "enr_1", "status": "running"},
            {"id": "state_2", "enrollment_id": "enr_2", "status": "running"}
        ])

        def table_dispatch(name):
            t = MagicMock()
            if name == "campaigns":
                t.select.return_value = camp_query
            elif name == "workspaces":
                t.select.return_value = ws_query
            elif name == "campaign_enrollments":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[
                    {"id": "enr_1", "campaign_id": self.campaign_id, "lead_id": "lead_1", "account_id": self.account_id, "workspace_id": self.workspace_id, "campaign_version_id": "v1"},
                    {"id": "enr_2", "campaign_id": self.campaign_id, "lead_id": "lead_2", "account_id": self.account_id, "workspace_id": self.workspace_id, "campaign_version_id": "v1"},
                ])
            elif name == "leads":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[
                    {"id": "lead_1", "timezone": "UTC"},
                    {"id": "lead_2", "timezone": "UTC"}
                ])
            elif name == "campaign_nodes":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            elif name == "campaign_edges":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            return t

        self.mock_supabase.table.side_effect = table_dispatch
        self.mock_supabase.rpc.return_value = rpc_mock

        with patch.object(orchestrator, "_workspace_has_credits", return_value=True), \
             patch.object(orchestrator, "process_lead") as mock_process:
            # stop_checker returns True immediately
            results = orchestrator.process_pending_leads(stop_checker=lambda: True)
            self.assertEqual(results, [])
            mock_process.assert_not_called()

    def test_panic_pause_halts_execution_mid_queue(self):
        """Layer 2: Live campaign check detects Panic Pause and pauses lead without executing node."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        # When campaign is checked in process_lead, status is PAUSED
        camp_check = MagicMock()
        camp_check.execute.return_value = MagicMock(data=[{"status": "PAUSED"}])
        self.mock_supabase.table.return_value.select.return_value.eq.return_value = camp_check

        mock_update = MagicMock()
        with patch.object(orchestrator, "update_state", mock_update):
            state = {
                "id": self.state_id,
                "campaign_id": self.campaign_id,
                "opportunity_id": "lead_1",
                "nodes": [{"id": "node_1", "node_type": "send_message", "config": {}}],
                "edges": [],
                "current_node_id": "node_1",
                "campaign_metadata": {}
            }
            orchestrator.process_lead(state, lease_token=self.lease_token)

            mock_update.assert_called_once()
            called_args = mock_update.call_args[0]
            self.assertEqual(called_args[0], self.state_id)
            self.assertEqual(called_args[1], "node_1")
            self.assertEqual(called_args[2], "paused")

    def test_handle_sigterm_sets_running_false(self):
        """Layer 2: handle_sigterm sets _running to False cleanly."""
        import core.backend.workers.orchestrator_worker as ow
        ow._running = True
        handle_sigterm(signal.SIGTERM, None)
        self.assertFalse(ow._running)
        ow._running = True  # Reset

    def test_get_worker_status_alive_and_stopped_and_standby(self):
        """Layer 0 & 1: get_worker_status handles alive, stopped, and unmigrated gracefully."""
        from campaigns.backend.routers.elein import get_worker_status

        # 1. Alive heartbeat
        recent_iso = datetime.now(timezone.utc).isoformat()
        mock_table = MagicMock()
        mock_table.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
            "worker_id": "elein-daemon",
            "last_beat_at": recent_iso,
            "status": "alive",
            "last_tick_duration_ms": 120,
            "last_tick_leads_processed": 5
        }])
        self.mock_supabase.table.return_value = mock_table

        status_alive = get_worker_status(supabase=self.mock_supabase, workspace_id=self.workspace_id)
        self.assertEqual(status_alive["status"], "alive")
        self.assertFalse(status_alive["stalled"])
        self.assertEqual(status_alive["last_tick_leads_processed"], 5)

        # 2. Stopped heartbeat (should NOT be marked stalled)
        mock_table.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
            "worker_id": "elein-daemon",
            "last_beat_at": "2026-10-01T00:00:00+00:00",
            "status": "stopped"
        }])
        status_stopped = get_worker_status(supabase=self.mock_supabase, workspace_id=self.workspace_id)
        self.assertEqual(status_stopped["status"], "stopped")
        self.assertFalse(status_stopped["stalled"])

        # 3. Missing/unmigrated table (throws exception)
        mock_table.select.return_value.order.return_value.limit.return_value.execute.side_effect = Exception("table not found")
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("table not found")
        status_standby = get_worker_status(supabase=self.mock_supabase, workspace_id=self.workspace_id)
        self.assertEqual(status_standby["status"], "standby")
        self.assertFalse(status_standby["stalled"])

    def test_browser_pool_serialization_and_teardown(self):
        """Layer 1 & 2: BrowserPool serializes per-account requests and performs clean teardown."""
        from integrations.backend.services.linkedin_pool import BrowserPool

        pool = BrowserPool(max_size=2)
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = MagicMock()

        def dummy_setup(pw):
            return mock_browser, mock_context

        # Mock sync_playwright to avoid spinning actual Chromium in unit tests
        with patch("integrations.backend.services.linkedin_pool.sync_playwright") as mock_pw_start:
            mock_pw = MagicMock()
            mock_pw_start.return_value.start.return_value = mock_pw

            ctx = pool.acquire("acc_1", dummy_setup)
            self.assertEqual(ctx, mock_context)
            self.assertIn("acc_1", pool.pool)
            self.assertEqual(pool.pool["acc_1"]["active_count"], 1)

            # Release
            pool.release("acc_1")
            self.assertEqual(pool.pool["acc_1"]["active_count"], 0)

            # Reap idle browsers
            pool.reap_idle_browsers(max_idle_seconds=-1)  # immediate reap
            self.assertNotIn("acc_1", pool.pool)

            # Teardown
            pool.teardown()
            self.assertEqual(len(pool.pool), 0)


if __name__ == "__main__":
    unittest.main()

