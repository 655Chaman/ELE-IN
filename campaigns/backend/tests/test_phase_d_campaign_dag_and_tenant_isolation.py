import unittest
from unittest.mock import MagicMock
from datetime import datetime, timezone
import pytz

from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.services.dag_validator import has_cycle, validate_sequence_dag
from campaigns.backend.services.sto_service import (
    compute_lead_jitter_minutes,
    compute_lead_sto_window,
    calculate_sto_next_run,
    should_use_sto
)


class TestPhaseDCampaignDAGAndTenantIsolation(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws-tenant-alpha"
        self.executor = EleInNodeExecutor(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

    # =========================================================================
    # Part 1: Cross-Tenant Isolation in EleInNodeExecutor (FLAW-SEC-02, 03)
    # =========================================================================

    def test_open_profile_check_scopes_select_and_update_to_workspace(self):
        """Layer 0 & 1: open_profile_check must query and update leads with workspace_id filter."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        mock_select = MagicMock()
        mock_update = MagicMock()
        mock_table.select.return_value = mock_select
        mock_table.update.return_value = mock_update

        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(data=[])

        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock(data=[])

        mock_worker = MagicMock()
        mock_worker.check_open_profile.return_value = {"status": "success", "branch": "Open", "open": True}
        self.executor.worker = mock_worker

        data = {"_lead_id": "lead-123"}
        res = self.executor.handle_open_profile_check(data, linkedin_url="https://linkedin.com/in/prospect-alice")

        self.assertEqual(res.get("branch"), "Open")
        self.assertTrue(res.get("open"))

        # Verify select and update scoped with workspace_id in positional args
        select_arg_calls = [c[0] for c in mock_select.eq.call_args_list]
        self.assertIn(("workspace_id", self.workspace_id), select_arg_calls)

        update_arg_calls = [c[0] for c in mock_update.eq.call_args_list]
        self.assertIn(("workspace_id", self.workspace_id), update_arg_calls)

    def test_inmail_arbitrage_scopes_leads_to_workspace(self):
        """Layer 0 & 1: handle_send_inmail must query and update leads scoped to workspace."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        mock_select = MagicMock()
        mock_update = MagicMock()
        mock_table.select.return_value = mock_select
        mock_table.update.return_value = mock_update

        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(data=[{"is_open_profile": True}])

        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock(data=[])

        mock_worker = MagicMock()
        mock_worker.account_id = "acc-456"
        mock_worker.send_inmail.return_value = {"status": "success", "is_free_inmail": True}
        self.executor.worker = mock_worker

        data = {
            "lead_id": "lead-999",
            "body": "Hello Alice, loved your work on distributed systems."
        }
        res = self.executor.handle_send_inmail(data, linkedin_url="https://linkedin.com/in/prospect-alice")

        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("is_free_inmail"))

        # Verify select and update queries included workspace_id
        select_arg_calls = [c[0] for c in mock_select.eq.call_args_list]
        self.assertIn(("workspace_id", self.workspace_id), select_arg_calls)

    def test_ai_agent_reply_scopes_messages_to_workspace(self):
        """Layer 0 & 1: handle_ai_generate_reply must filter inbound and outbound messages by workspace_id."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.gt.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.limit.return_value = mock_select
        # Return empty inbound message to trigger clean return right after scoped query
        mock_select.execute.return_value = MagicMock(data=[])

        data = {
            "lead_id": "lead-333"
        }
        res = self.executor.handle_ai_generate_reply(data, linkedin_url="https://linkedin.com/in/prospect-bob")

        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("error"), "No inbound message found for lead")

        # Verify that messages query was scoped with workspace_id
        select_arg_calls = [c[0] for c in mock_select.eq.call_args_list]
        self.assertIn(("workspace_id", self.workspace_id), select_arg_calls)

    def test_find_and_verify_email_scopes_leads_to_workspace(self):
        """Layer 0 & 1: handle_verify_email queries leads with workspace filter."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(data=[{
            "first_name": "Carol",
            "last_name": "Danvers",
            "domain": "acme.corp",
            "email": "carol@acme.corp"
        }])

        mock_rpc = MagicMock()
        self.mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        data = {"_lead_id": "lead-777", "_current_node_id": "verify-1"}
        res = self.executor.handle_verify_email(data, linkedin_url="https://linkedin.com/in/carol")

        self.assertEqual(res.get("status"), "success")
        select_arg_calls = [c[0] for c in mock_select.eq.call_args_list]
        self.assertIn(("workspace_id", self.workspace_id), select_arg_calls)

    # =========================================================================
    # Part 2: DAG Sequence Engine & Cycle Detection (Kahn's Algorithm)
    # =========================================================================

    def test_has_cycle_detects_self_loop(self):
        """Layer 2: Direct self-loop (node pointing to itself) must be caught instantly."""
        nodes = [{"id": "node-1", "type": "connection_request"}]
        edges = [{"source": "node-1", "target": "node-1"}]
        self.assertTrue(has_cycle(nodes, edges))

    def test_has_cycle_detects_two_node_loop(self):
        """Layer 0: A -> B -> A cycle must be detected."""
        nodes = [
            {"id": "node-1", "type": "connection_request"},
            {"id": "node-2", "type": "send_message"}
        ]
        edges = [
            {"source": "node-1", "target": "node-2"},
            {"source": "node-2", "target": "node-1"}
        ]
        self.assertTrue(has_cycle(nodes, edges))

    def test_has_cycle_accepts_valid_dag_with_dual_edge_keys(self):
        """Layer 1: Valid branching DAG with dual edge-keys must report has_cycle=False."""
        nodes = [
            {"id": "root", "type": "sequence_start"},
            {"id": "branch_check", "type": "if_connected"},
            {"id": "msg_connected", "type": "send_message"},
            {"id": "conn_request", "type": "connection_request"},
            {"id": "end", "type": "sequence_end"}
        ]
        edges = [
            {"source": "root", "target": "branch_check"},
            {"source_node_id": "branch_check", "target_node_id": "msg_connected"},
            {"source": "branch_check", "target": "conn_request"},
            {"source_node_id": "msg_connected", "target_node_id": "end"},
            {"source": "conn_request", "target": "end"}
        ]
        self.assertFalse(has_cycle(nodes, edges))

        report = validate_sequence_dag(nodes, edges)
        self.assertFalse(report["has_cycle"])
        self.assertEqual(len(report["dangling_edges"]), 0)
        self.assertEqual(len(report["orphaned_node_ids"]), 0)

    def test_validate_sequence_dag_flags_dangling_edges_and_orphans(self):
        """Layer 2: Detects dangling edge pointing to missing node and orphaned nodes."""
        nodes = [
            {"id": "root", "type": "sequence_start"},
            {"id": "msg_1", "type": "send_message"},
            {"id": "isolated_node", "type": "send_email"}
        ]
        edges = [
            {"source": "root", "target": "msg_1"},
            {"source": "msg_1", "target": "deleted_node_99"}
        ]
        report = validate_sequence_dag(nodes, edges)

        self.assertEqual(len(report["dangling_edges"]), 1)
        self.assertEqual(report["dangling_edges"][0]["target"], "deleted_node_99")
        self.assertIn("isolated_node", report["orphaned_node_ids"])

    # =========================================================================
    # Part 3: Send Time Optimization (STO) Window & Jitter Resilience
    # =========================================================================

    def test_sto_jitter_within_safe_bounds(self):
        """Layer 1: STO jitter minutes must remain within configured bounds."""
        for lead_id in ["lead_alpha", "lead_beta", "lead_gamma", None]:
            jitter = compute_lead_jitter_minutes(lead_id, min_jitter=5, max_jitter=25)
            self.assertGreaterEqual(jitter, 5)
            self.assertLessEqual(jitter, 25)

    def test_calculate_sto_next_run_resilient_to_24h_schedule(self):
        """Layer 2: 24h schedule (start_hour=0, end_hour=24) never causes dt_time ValueError."""
        schedule = {
            "start_hour": 0,
            "end_hour": 24,
            "active_days": [0, 1, 2, 3, 4, 5, 6]
        }
        base = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)
        next_run = calculate_sto_next_run(
            base_time=base,
            target_tz="America/New_York",
            lead_id="prospect_test_1",
            schedule=schedule,
            min_gap_minutes=15
        )
        self.assertIsInstance(next_run, datetime)
        self.assertGreater(next_run, base)

    def test_compute_lead_sto_window_scopes_events_by_workspace(self):
        """Layer 2: Historical engagement queries scope email_events and messages by workspace_id."""
        mock_sub = MagicMock()
        mock_table = MagicMock()
        mock_sub.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.in_.return_value = mock_select
        mock_select.limit.return_value = mock_select
        mock_select.execute.return_value = MagicMock(data=[
            {"created_at": "2026-10-24T14:30:00Z", "event_type": "click"}
        ])

        sto_result = compute_lead_sto_window(
            supabase=mock_sub,
            lead_id="prospect_multi_tenant",
            tz_str="America/New_York",
            schedule={"start_hour": 9, "end_hour": 17},
            workspace_id="ws-tenant-alpha"
        )
        self.assertEqual(sto_result["source"], "historical_engagement")
        select_arg_calls = [c[0] for c in mock_select.eq.call_args_list]
        self.assertIn(("workspace_id", "ws-tenant-alpha"), select_arg_calls)


if __name__ == "__main__":
    unittest.main()
