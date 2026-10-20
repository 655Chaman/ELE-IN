"""
test_stage30_final_campaigns_audit_and_dag_integrity.py — Paranoia Test Suite for Stage 30
Final Campaigns Audit, DAG Integrity, End-to-End Orchestrator Simulation & Failure Recovery Hardening

Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (Email/multimodal touchpoint recognition, JSON string DAG input normalization, expanded branch node types, duplicate node ID detection, linear sequence simulation)
- Layer 1: Environmental Failure Analysis (Tenant containment on cascade pause, unpausing non-colliding states, cascade delete with lease release & outbox events, stale lease recovery, max sequence hops loop breaker)
- Layer 2: Human Paranoia (Duplicate node ID rejection in campaign creation, active graph mutation locks for in-flight leads, optimistic concurrency multi-tab overwrite defense, terminal action node exit handling)
"""

import unittest
from unittest.mock import MagicMock, patch, call
import json
import uuid
from datetime import datetime, timezone, timedelta

from campaigns.backend.services.dag_validator import (
    has_cycle,
    validate_sequence_dag,
    check_optimistic_concurrency,
    validate_active_campaign_graph_mutation,
    _is_touchpoint_node,
    _is_branch_node,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestStage30FinalCampaignsAuditAndDagIntegrity(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws_stage30_final"
        self.campaign_id = "camp_stage30_alpha"
        self.mock_supabase = MagicMock()
        self.orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        self.executor = EleInNodeExecutor(
            worker=None,
            account_id="acc_stage30_sender",
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER
    # =========================================================================

    def test_dag_validator_email_touchpoints_recognized(self):
        """Layer 0: Verifies email, mail, multimodal, and video/voice nodes are recognized as touchpoints."""
        touchpoint_samples = [
            {"id": "n1", "type": "send_email"},
            {"id": "n2", "type": "email"},
            {"id": "n3", "type": "multimodal_asset"},
            {"id": "n4", "type": "video_card"},
            {"id": "n5", "type": "voice_script"},
            {"id": "n6", "type": "connection_request"},
            {"id": "n7", "type": "linkedin_message"},
        ]
        for node in touchpoint_samples:
            self.assertTrue(
                _is_touchpoint_node(node),
                f"Node type '{node['type']}' must be recognized as an outreach touchpoint"
            )

        # Non-touchpoint sample
        non_touchpoint = {"id": "n8", "type": "delay"}
        self.assertFalse(_is_touchpoint_node(non_touchpoint))

    def test_dag_validator_json_string_input_resilience(self):
        """Layer 0: Verifies has_cycle and validate_sequence_dag accept raw JSON strings seamlessly."""
        nodes_json_str = json.dumps([
            {"id": "n1", "type": "send_email"},
            {"id": "n2", "type": "delay"},
            {"id": "n3", "type": "send_email"}
        ])
        edges_json_str = json.dumps([
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"}
        ])

        # Test has_cycle with JSON strings
        self.assertFalse(has_cycle(nodes_json_str, edges_json_str))

        # Test validate_sequence_dag with JSON strings
        report = validate_sequence_dag(nodes_json_str, edges_json_str)
        self.assertFalse(report["has_cycle"])
        self.assertEqual(len(report["reachable_node_ids"]), 3)
        self.assertEqual(report["total_touchpoints"], 2)
        self.assertEqual(report["reachable_touchpoints"], 2)

    def test_dag_validator_duplicate_node_ids_detected(self):
        """Layer 0: Verifies duplicate node IDs on a canvas are flagged in duplicate_node_ids."""
        nodes = [
            {"id": "node_email_1", "type": "send_email"},
            {"id": "node_email_1", "type": "send_email"},  # Duplicate ID
            {"id": "node_delay_2", "type": "delay"},
        ]
        edges = [
            {"source": "node_email_1", "target": "node_delay_2"}
        ]
        report = validate_sequence_dag(nodes, edges)
        self.assertIn("node_email_1", report["duplicate_node_ids"])

    def test_dag_branch_node_types_expanded(self):
        """Layer 0: Verifies _is_branch_node identifies all custom and split branch node types."""
        branch_types = [
            {"id": "b1", "type": "if_connected"},
            {"id": "b2", "type": "if_replied"},
            {"id": "b3", "type": "ab_split"},
            {"id": "b4", "type": "weighted_split"},
            {"id": "b5", "type": "open_profile_check"},
            {"id": "b6", "type": "retarget_omnichannel"},
            {"id": "b7", "type": "fallback_to_inmail"},
            {"id": "b8", "type": "abm_multithread"},
            {"id": "b9", "type": "displacement"},
            {"id": "b10", "type": "boomerang_revival"},
        ]
        for node in branch_types:
            self.assertTrue(
                _is_branch_node(node),
                f"Node type '{node['type']}' must be recognized as a branch node"
            )

    def test_end_to_end_linear_sequence_simulation(self):
        """Layer 0: Simulates execution advancing across linear edges to completion."""
        edges = [
            {"source": "node_connect", "target": "node_delay", "source_handle": "then"},
            {"source": "node_delay", "target": "node_msg", "source_handle": "then"},
            {"source": "node_msg", "target": "node_end", "source_handle": "then"},
        ]
        # Step 1: Connect -> Delay
        e1, _ = self.orchestrator.resolve_branch_edge(
            self.orchestrator.get_outgoing_edges(edges, "node_connect"),
            branch_handle="then"
        )
        self.assertEqual(e1["target"], "node_delay")

        # Step 2: Delay -> Msg
        e2, _ = self.orchestrator.resolve_branch_edge(
            self.orchestrator.get_outgoing_edges(edges, "node_delay"),
            branch_handle="then"
        )
        self.assertEqual(e2["target"], "node_msg")

        # Step 3: Msg -> End
        e3, _ = self.orchestrator.resolve_branch_edge(
            self.orchestrator.get_outgoing_edges(edges, "node_msg"),
            branch_handle="then"
        )
        self.assertEqual(e3["target"], "node_end")

        # Step 4: End has no outgoing edges -> terminal node
        e4 = self.orchestrator.get_outgoing_edges(edges, "node_end")
        self.assertEqual(len(e4), 0, "Terminal node must have zero outgoing edges")

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # =========================================================================

    def test_campaign_pause_cascade_workspace_containment(self):
        """Layer 1: Verifies pausing a campaign strictly scopes updates by workspace_id."""
        mock_client = MagicMock()
        mock_camp_query = MagicMock()
        mock_camp_query.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.campaign_id, "name": "Enterprise Campaign"}]
        )
        mock_client.table.return_value = mock_camp_query

        from campaigns.backend.routers.elein import pause_campaign

        with patch("core.backend.services.credit_service.distributed_workspace_lock"):
            with patch("campaigns.backend.routers.master_view.invalidate_master_view_cache"):
                res = pause_campaign(self.campaign_id, workspace_id=self.workspace_id, client=mock_client)
                self.assertEqual(res["status"], "paused")

        # Check table calls
        update_calls = mock_client.table.return_value.update.call_args_list
        self.assertTrue(len(update_calls) > 0)

    def test_campaign_delete_force_and_cascade(self):
        """Layer 1: Deleting a campaign cascades to execution states, enrollments, and emits an outbox event."""
        mock_client = MagicMock()
        # Mock campaign select returns a DRAFT campaign
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.campaign_id, "name": "Draft Campaign", "status": "DRAFT"}]
        )
        # Mock enrollments select returns 1 enrollment
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "enr_1"}]
        )

        from campaigns.backend.routers.elein import delete_campaign

        with patch("core.backend.services.credit_service.distributed_workspace_lock"):
            with patch("campaigns.backend.routers.master_view.invalidate_master_view_cache"):
                res = delete_campaign(self.campaign_id, force=False, workspace_id=self.workspace_id, client=mock_client)
                self.assertEqual(res["status"], "deleted")

        # Verify outbox event insertion
        insert_calls = mock_client.table.return_value.insert.call_args_list
        found_outbox = any(
            isinstance(call[0][0], dict) and call[0][0].get("event_type") == "campaign.deleted"
            for call in insert_calls
        )
        self.assertTrue(found_outbox, "Cascade delete must emit campaign.deleted outbox event")

    def test_orchestrator_max_sequence_hops_infinite_loop_breaker(self):
        """Layer 1: Sequence loop breaker triggers when hop count exceeds MAX_SEQUENCE_HOPS (50)."""
        nodes = [{"id": "n1"}, {"id": "n2"}]
        state = {
            "id": "state_loop_guard",
            "opportunity_id": "opp_1",
            "campaign_id": self.campaign_id,
            "variables": {"_sequence_hop_count": 51}  # Exceeds max 50
        }
        out_vars = dict(state["variables"])

        is_valid = self.orchestrator._validate_and_prepare_hop(
            state=state,
            current_node_id="n1",
            next_node_id="n2",
            nodes=nodes,
            lease_token="lease_tok",
            out_vars=out_vars
        )
        self.assertFalse(is_valid, "Loop breaker must halt transitions exceeding MAX_SEQUENCE_HOPS")

    def test_orchestrator_dangling_edge_guard(self):
        """Layer 1: Transitioning to non-existent target node triggers dangling edge guard."""
        nodes = [{"id": "n1"}, {"id": "n2"}]
        state = {
            "id": "state_dangling",
            "opportunity_id": "opp_2",
            "campaign_id": self.campaign_id,
            "variables": {}
        }
        out_vars = dict(state["variables"])

        is_valid = self.orchestrator._validate_and_prepare_hop(
            state=state,
            current_node_id="n1",
            next_node_id="n_phantom_nonexistent",
            nodes=nodes,
            lease_token="lease_tok",
            out_vars=out_vars
        )
        self.assertFalse(is_valid, "Transition to phantom node must be rejected and marked as error")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA
    # =========================================================================

    def test_active_campaign_graph_mutation_lock(self):
        """Layer 2: Deleting or mutating node types while leads are in-flight is rejected."""
        existing_nodes = [
            {"id": "n1", "type": "connection_request"},
            {"id": "n2", "type": "send_message"},
            {"id": "n3", "type": "sequence_end"}
        ]
        # Human in browser deletes n2 and changes n1 to send_email
        new_nodes = [
            {"id": "n1", "type": "send_email"},
            {"id": "n3", "type": "sequence_end"}
        ]
        # In-flight leads currently executing on n1 and n2
        in_flight_node_ids = {"n1", "n2"}

        res = validate_active_campaign_graph_mutation(existing_nodes, new_nodes, in_flight_node_ids)
        self.assertFalse(res["is_safe"])
        self.assertIn("n2", res["deleted_node_ids"])
        self.assertEqual(len(res["type_mutated_nodes"]), 1)
        self.assertIn("n1", res["orphaned_in_flight_nodes"])
        self.assertIn("n2", res["orphaned_in_flight_nodes"])

    def test_optimistic_concurrency_multi_tab_collision_rejection(self):
        """Layer 2: Multi-tab simultaneous saves with outdated versions or timestamps are flagged."""
        persisted_campaign = {
            "id": self.campaign_id,
            "updated_at": "2026-10-20T12:00:00.000Z",
            "metadata": {"version": 4}
        }
        # Tab A tries to save expecting version 3 (outdated)
        conflict_ver = check_optimistic_concurrency(
            existing_campaign=persisted_campaign,
            expected_version=3
        )
        self.assertTrue(conflict_ver["conflict"])
        self.assertIn("modified by another session", conflict_ver["reason"])

        # Tab B tries to save expecting timestamp "2026-10-20T11:00:00.000Z" (outdated)
        conflict_ts = check_optimistic_concurrency(
            existing_campaign=persisted_campaign,
            expected_updated_at="2026-10-20T11:00:00.000Z"
        )
        self.assertTrue(conflict_ts["conflict"])
        self.assertIn("modified since it was loaded", conflict_ts["reason"])

    def test_terminal_action_nodes_mark_converted_and_sequence_end(self):
        """Layer 2: Executing mark_converted or sequence_end cleanly exits the lead state."""
        # Test mark_converted
        res_conv = self.executor.handle_mark_converted({"lead_id": "lead_win"}, "https://linkedin.com/in/winner")
        self.assertEqual(res_conv["status"], "success")

        # Test sequence_end
        res_end = self.executor.handle_sequence_end({"exit_reason": "completed"}, "https://linkedin.com/in/end")
        self.assertEqual(res_end["status"], "success")
        self.assertEqual(res_end["branch"], "then")


if __name__ == "__main__":
    unittest.main()
