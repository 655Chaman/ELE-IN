"""
Unit tests for Campaign Sequence DAG Cycle Detection, Validation, and Runtime Loop Guards.
"""
import unittest
from campaigns.backend.services.dag_validator import has_cycle, validate_sequence_dag
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class DummyOrchestrator(EleInOrchestrator):
    def __init__(self):
        # Override init to avoid DB initialization requirements during unit tests
        self.updates = []

    def update_state(self, state_id, current_node_id, status, next_node_id, lease_token, error_reason=None, variables=None, tz_str="UTC"):
        self.updates.append({
            "state_id": state_id,
            "current_node_id": current_node_id,
            "status": status,
            "next_node_id": next_node_id,
            "error_reason": error_reason,
            "variables": variables
        })

    def mark_error(self, state_id, error_reason, lease_token=None):
        self.updates.append({
            "state_id": state_id,
            "status": "error",
            "error_reason": error_reason
        })


class TestSequenceDAGAndLoopGuard(unittest.TestCase):

    def test_has_cycle_direct_self_loop_and_multi_hop(self):
        # Direct self-loop
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        edges = [{"source": "A", "target": "A"}]
        self.assertTrue(has_cycle(nodes, edges))

        # Multi-hop cycle: A -> B -> C -> A
        edges_cycle = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
            {"source": "C", "target": "A"}
        ]
        self.assertTrue(has_cycle(nodes, edges_cycle))

        # Valid DAG: A -> B -> C
        edges_dag = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"}
        ]
        self.assertFalse(has_cycle(nodes, edges_dag))

    def test_has_cycle_supports_db_edge_keys(self):
        nodes = [{"id": "n1"}, {"id": "n2"}]
        edges = [{"source_node_id": "n1", "target_node_id": "n2"}, {"source_node_id": "n2", "target_node_id": "n1"}]
        self.assertTrue(has_cycle(nodes, edges))

    def test_has_cycle_deep_graph_no_recursion_error(self):
        # 1,500 node linear chain
        num_nodes = 1500
        nodes = [{"id": f"node_{i}"} for i in range(num_nodes)]
        edges = [{"source": f"node_{i}", "target": f"node_{i+1}"} for i in range(num_nodes - 1)]
        self.assertFalse(has_cycle(nodes, edges))

        # Add a back-edge to create a cycle at the end
        edges.append({"source": f"node_{num_nodes-1}", "target": "node_0"})
        self.assertTrue(has_cycle(nodes, edges))

    def test_has_cycle_malformed_nodes_and_dangling_edges(self):
        nodes = [{"id": "A"}, None, {"not_an_id": 123}, {"id": "B"}]
        edges = [{"source": "A", "target": "B"}, {"source": "B", "target": "non_existent"}]
        self.assertFalse(has_cycle(nodes, edges))

    def test_validate_sequence_dag_detects_orphaned_nodes(self):
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "ORPHAN"}]
        edges = [{"source": "A", "target": "B"}]
        report = validate_sequence_dag(nodes, edges)
        self.assertIn("ORPHAN", report["orphaned_node_ids"])

    def test_validate_sequence_dag_detects_dangling_edges(self):
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"source": "A", "target": "missing_node"}]
        report = validate_sequence_dag(nodes, edges)
        self.assertEqual(len(report["dangling_edges"]), 1)
        self.assertEqual(report["dangling_edges"][0]["target"], "missing_node")

    def test_validate_sequence_dag_detects_dead_end_branch_nodes(self):
        nodes = [{"id": "A", "type": "if_connected"}, {"id": "B"}]
        edges = [{"source": "B", "target": "A"}]  # A is branch node with out_degree == 0
        report = validate_sequence_dag(nodes, edges)
        self.assertIn("A", report["dead_end_branch_nodes"])

    def test_orchestrator_runtime_self_loop_breaker(self):
        orch = DummyOrchestrator()
        state = {"id": "state_1", "tz_str": "UTC"}
        nodes = [{"id": "A"}, {"id": "B"}]
        out_vars = {}
        res = orch._validate_and_prepare_hop(state, current_node_id="A", next_node_id="A", nodes=nodes, lease_token="token", out_vars=out_vars)
        self.assertFalse(res)
        self.assertTrue(any("self-loop" in str(u.get("error_reason")) for u in orch.updates))

    def test_orchestrator_runtime_max_hops_loop_breaker(self):
        orch = DummyOrchestrator()
        state = {"id": "state_1", "tz_str": "UTC"}
        nodes = [{"id": "A"}, {"id": "B"}]
        out_vars = {"_sequence_hop_count": 50}
        res = orch._validate_and_prepare_hop(state, current_node_id="A", next_node_id="B", nodes=nodes, lease_token="token", out_vars=out_vars)
        self.assertFalse(res)
        self.assertTrue(any("exceeded maximum sequence hops" in str(u.get("error_reason")) for u in orch.updates))

    def test_orchestrator_runtime_dangling_target_edge_guard(self):
        orch = DummyOrchestrator()
        state = {"id": "state_1", "tz_str": "UTC"}
        nodes = [{"id": "A"}, {"id": "B"}]
        out_vars = {}
        res = orch._validate_and_prepare_hop(state, current_node_id="A", next_node_id="Z_DELETED", nodes=nodes, lease_token="token", out_vars=out_vars)
        self.assertFalse(res)
        self.assertTrue(any("Dangling sequence edge" in str(u.get("error_reason")) for u in orch.updates))

    def test_preflight_audit_flags_dangling_edges_and_dead_end_branches(self):
        from campaigns.backend.routers.elein import run_campaign_preflight_audit
        nodes = [
            {"id": "A", "type": "send_message"},
            {"id": "B", "type": "if_connected"}
        ]
        edges = [
            {"source": "A", "target": "missing_node"},
            {"source": "A", "target": "B"}
        ]
        # Mock supabase or pass None if unused in preflight audit
        # run_campaign_preflight_audit(supabase, tier, nodes_raw, edges_raw, stop_on_reply, ...)
        # Let's check signature of run_campaign_preflight_audit in elein.py
        audit = run_campaign_preflight_audit(
            supabase=None,
            workspace_id="ws_1",
            campaign_name="Test Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=["acc_1"],
            timezone="UTC",
            stop_on_reply=True
        )
        self.assertFalse(audit["passed"])
        self.assertTrue(any("dangling edge" in err.lower() or "dead-end" in err.lower() for err in audit.get("critical_errors", [])))



if __name__ == "__main__":
    unittest.main()
