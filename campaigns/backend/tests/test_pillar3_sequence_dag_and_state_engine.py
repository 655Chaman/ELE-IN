import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.services.sender_pod_service import (
    select_pod_sender,
    reassign_lead_sender,
    _is_account_quarantined
)


class TestPillar3SequenceDAGAndStateEngine(unittest.TestCase):
    """
    Comprehensive Three-Layer Paranoia Test Suite for Pillar 3:
    Campaign Sequence DAG & Multi-Channel State Engine (Phases 3.1 - 3.4).
    """

    def setUp(self):
        self.mock_worker = MagicMock()
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_pillar3_prod"
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.mock_worker,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

    # =========================================================================
    # Phase 3.1: Condition Node Branch Traversal Integrity
    # =========================================================================

    def test_handle_if_connected_fast_path_action_log_success(self):
        """Layer 1: Verifies action_log connection_accepted record returns Connected branch immediately."""
        data = {"_lead_id": "lead-456", "_current_node_id": "node-cond-1"}
        
        # Leads table returns false
        mock_leads_table = MagicMock()
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"is_connected": False, "status": "pending"}]
        )
        
        # Action log returns connection_accepted
        mock_action_log_table = MagicMock()
        mock_action_log_table.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "act-101", "action_type": "connection_accepted"}]
        )

        def mock_table(table_name):
            if table_name == "leads":
                return mock_leads_table
            elif table_name == "action_log":
                return mock_action_log_table
            return MagicMock()

        self.mock_supabase.table.side_effect = mock_table

        res = self.executor.handle_if_connected(data, "https://linkedin.com/in/accepted-user")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.CONNECTED.value)
        self.assertTrue(res.get("connected"))
        self.assertEqual(res["variables"].get("last_branch_taken"), Branch.CONNECTED.value)
        self.assertIn("condition_evaluated_at", res["variables"])
        self.mock_worker.check_if_connected.assert_not_called()

    def test_handle_if_connected_timeout_window_yields_waiting(self):
        """Layer 1 & 2: If prospect is not yet connected and within timeout window, returns waiting instead of failing."""
        data = {
            "_lead_id": "lead-wait-1",
            "_current_node_id": "node-cond-timeout",
            "timeout_days": 3
        }

        # No DB hit, no action_log hit
        mock_empty_table = MagicMock()
        mock_empty_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_empty_table.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value = mock_empty_table

        # Worker returns Not connected
        self.mock_worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}

        res = self.executor.handle_if_connected(data, "https://linkedin.com/in/pending-user")
        self.assertEqual(res.get("status"), "waiting")
        self.assertIn("resume_at", res)
        self.assertIn("condition_started_at_node-cond-timeout", res["variables"])
        self.assertEqual(res["variables"].get("last_branch_taken"), "waiting")

    def test_handle_if_connected_timeout_window_expired_routes_to_not_connected(self):
        """Layer 1: If timeout window has elapsed, cleanly routes to Not connected branch."""
        now_dt = datetime.now(timezone.utc)
        started_dt = now_dt - timedelta(days=4)  # Started 4 days ago
        
        data = {
            "_lead_id": "lead-expired-1",
            "_current_node_id": "node-cond-timeout",
            "timeout_days": 3,
            "variables": {
                "condition_started_at_node-cond-timeout": started_dt.isoformat()
            }
        }

        mock_empty_table = MagicMock()
        mock_empty_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_empty_table.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value = mock_empty_table
        self.mock_worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}

        res = self.executor.handle_if_connected(data, "https://linkedin.com/in/expired-user")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_CONNECTED.value)
        self.assertFalse(res.get("connected"))
        self.assertTrue(res.get("timed_out"))
        self.assertEqual(res["variables"].get("last_branch_taken"), Branch.NOT_CONNECTED.value)

    def test_handle_if_replied_timeout_window(self):
        """Layer 1: if_replied with timeout_hours yields waiting when pending and routes to No Reply when expired."""
        data_pending = {
            "_lead_id": "lead-reply-1",
            "_current_node_id": "node-reply-1",
            "timeout_hours": 48
        }
        mock_empty = MagicMock()
        mock_empty.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_empty.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value = mock_empty
        self.mock_worker.check_if_replied.return_value = {"status": "success", "branch": "No reply"}

        res_wait = self.executor.handle_if_replied(data_pending, "https://linkedin.com/in/prospect")
        self.assertEqual(res_wait.get("status"), "waiting")
        self.assertEqual(res_wait["variables"].get("last_branch_taken"), "waiting")

        # Now test expired
        data_expired = {
            "_lead_id": "lead-reply-1",
            "_current_node_id": "node-reply-1",
            "timeout_hours": 48,
            "variables": {
                "condition_started_at_node-reply-1": (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
            }
        }
        res_expired = self.executor.handle_if_replied(data_expired, "https://linkedin.com/in/prospect")
        self.assertEqual(res_expired.get("status"), "success")
        self.assertEqual(res_expired.get("branch"), Branch.NO_REPLY.value)
        self.assertEqual(res_expired["variables"].get("last_branch_taken"), Branch.NO_REPLY.value)

    # =========================================================================
    # Phase 3.2: Multi-Sender Pod Balancing & Thread Affinity
    # =========================================================================

    def test_select_pod_sender_respects_campaign_lead_sender_locks(self):
        """Layer 0: Verifies thread affinity lock binds conversation to original sender."""
        mock_sb = MagicMock()
        
        # Campaigns table check
        mock_camp = MagicMock()
        mock_camp.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": "ws-1", "pod_emergency_paused": False, "pod_dispatch_strategy": "ROUND_ROBIN"}]
        )
        
        # campaign_lead_sender_locks table returns lock
        mock_locks = MagicMock()
        mock_locks.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc-affinity-1"}]
        )

        # Accounts table returns active initiating sender
        mock_accounts = MagicMock()
        mock_accounts.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "acc-affinity-1",
                "status": "ACTIVE",
                "workspace_id": "ws-1",
                "daily_connection_limit": 50,
                "daily_message_limit": 100,
                "is_warmup": False
            }]
        )

        # Usage table for capacity
        mock_usage = MagicMock()
        mock_usage.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def table_dispatch(t):
            if t == "campaigns": return mock_camp
            if t == "campaign_lead_sender_locks": return mock_locks
            if t == "accounts": return mock_accounts
            if t == "account_daily_usage": return mock_usage
            return MagicMock()

        mock_sb.table.side_effect = table_dispatch

        res = select_pod_sender(
            campaign_id="camp-1",
            workspace_id="ws-1",
            action_type="message",
            supabase=mock_sb,
            lead_id="lead-bound-1"
        )
        self.assertEqual(res.get("status"), "THREAD_AFFINITY_LOCKED")
        self.assertEqual(res.get("account_id"), "acc-affinity-1")

    def test_select_pod_sender_thread_affinity_defers_on_rate_limited(self):
        """Layer 1: If initiating sender is RATE_LIMITED, defers outreach without switching senders."""
        mock_sb = MagicMock()
        mock_camp = MagicMock()
        mock_camp.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": "ws-1", "pod_emergency_paused": False}]
        )
        mock_locks = MagicMock()
        mock_locks.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc-limited-1"}]
        )
        mock_accounts = MagicMock()
        mock_accounts.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "acc-limited-1",
                "status": "RATE_LIMITED",
                "workspace_id": "ws-1"
            }]
        )

        mock_sb.table.side_effect = lambda t: {
            "campaigns": mock_camp,
            "campaign_lead_sender_locks": mock_locks,
            "accounts": mock_accounts
        }.get(t, MagicMock())

        res = select_pod_sender(
            campaign_id="camp-1",
            workspace_id="ws-1",
            action_type="message",
            supabase=mock_sb,
            lead_id="lead-bound-1"
        )
        self.assertEqual(res.get("status"), "THREAD_AFFINITY_RATE_LIMITED")
        self.assertIsNone(res.get("account_id"))
        self.assertEqual(res.get("initiating_account_id"), "acc-limited-1")

    def test_reassign_lead_sender_success_and_tenant_isolation(self):
        """Layer 0 & 2: reassign_lead_sender migrates lock to target account and rejects cross-tenant targets."""
        mock_sb = MagicMock()

        # Target account belongs to ws-1
        mock_acc = MagicMock()
        mock_acc.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc-target", "workspace_id": "ws-1", "status": "ACTIVE", "name": "Sarah Sales"}]
        )
        mock_sb.table.return_value = mock_acc

        res = reassign_lead_sender(
            supabase=mock_sb,
            workspace_id="ws-1",
            campaign_id="camp-1",
            lead_id="lead-100",
            new_account_id="acc-target",
            reason="Original sender left company"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("reassigned_account_id"), "acc-target")

        # Test cross-tenant isolation
        mock_acc_foreign = MagicMock()
        mock_acc_foreign.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc-foreign", "workspace_id": "ws-OTHER", "status": "ACTIVE"}]
        )
        mock_sb.table.return_value = mock_acc_foreign

        res_foreign = reassign_lead_sender(
            supabase=mock_sb,
            workspace_id="ws-1",
            campaign_id="camp-1",
            lead_id="lead-100",
            new_account_id="acc-foreign"
        )
        self.assertEqual(res_foreign.get("status"), "error")
        self.assertIn("another workspace", res_foreign.get("message", "").lower())

    # =========================================================================
    # Phase 3.3: Optimistic DAG Mutation Concurrency Guard
    # =========================================================================

    def test_orchestrator_orphaned_node_downstream_advance(self):
        """Layer 1: Orchestrator detects deleted node and advances lead to downstream surviving target."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        
        # Lead is currently on node-deleted
        state = {
            "id": "state-orphan-1",
            "opportunity_id": "opp-1",
            "campaign_id": "camp-mutated",
            "current_node_id": "node-deleted",
            "status": "pending",
            "workspace_id": "ws-1",
            "nodes": [
                {"id": "node-start", "type": "connection_request"},
                {"id": "node-survivor", "type": "send_message"}
            ],
            "edges": [
                {"source": "node-start", "target": "node-deleted"},
                {"source": "node-deleted", "target": "node-survivor"}
            ]
        }

        with patch.object(orchestrator, "update_state") as mock_update_state:
            orchestrator.process_lead(state, lease_token="lease-123")
            
            # Should have advanced to node-survivor rather than marking error!
            mock_update_state.assert_called_once()
            call_args = mock_update_state.call_args
            self.assertEqual(call_args[0][0], "state-orphan-1")
            self.assertEqual(call_args[0][1], "node-survivor")
            self.assertEqual(call_args[0][2], "pending")
            self.assertIn("Recovered from deleted node", call_args[1].get("error_reason", ""))

    def test_orchestrator_orphaned_terminal_node_clean_completion(self):
        """Layer 1: Orchestrator completes sequence cleanly if deleted node was terminal."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        state = {
            "id": "state-orphan-2",
            "opportunity_id": "opp-2",
            "campaign_id": "camp-mutated",
            "current_node_id": "node-deleted-terminal",
            "status": "pending",
            "workspace_id": "ws-1",
            "nodes": [{"id": "node-survivor", "type": "send_message"}],
            "edges": []
        }

        with patch.object(orchestrator, "update_state") as mock_update_state:
            orchestrator.process_lead(state, lease_token="lease-123")
            mock_update_state.assert_called_once()
            call_args = mock_update_state.call_args
            self.assertEqual(call_args[0][0], "state-orphan-2")
            self.assertIsNone(call_args[0][1])
            self.assertEqual(call_args[0][2], "completed")

    # =========================================================================
    # Phase 3.4: Stuck State Sweeper & Zombie Lease Recovery
    # =========================================================================

    def test_sweep_stale_leases_recovers_zombies_and_trips_poison_pill(self):
        """Layer 1 & 2: Stale leases are recovered, while repeated failures (>= max_attempts) are quarantined."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        mock_states_table = MagicMock()
        # Two stuck states:
        # 1. State A: attempts = 0 (should be recovered)
        # 2. State B: attempts = 2, max_attempts = 3 (attempts + 1 >= 3, should trip circuit breaker)
        mock_states_table.select.return_value.in_.return_value.or_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "state-recover-a",
                    "workspace_id": "ws-1",
                    "campaign_id": "c-1",
                    "opportunity_id": "opp-a",
                    "current_node_id": "node-1",
                    "attempts": 0,
                    "max_attempts": 3
                },
                {
                    "id": "state-poison-b",
                    "workspace_id": "ws-1",
                    "campaign_id": "c-1",
                    "opportunity_id": "opp-b",
                    "current_node_id": "node-1",
                    "attempts": 2,
                    "max_attempts": 3
                }
            ]
        )
        self.mock_supabase.table.return_value = mock_states_table

        stats = orchestrator.sweep_stale_leases(max_attempts=3, stale_minutes=5)
        self.assertEqual(stats["scanned"], 2)
        self.assertEqual(stats["recovered"], 1)
        self.assertEqual(stats["quarantined"], 1)


if __name__ == "__main__":
    unittest.main()
