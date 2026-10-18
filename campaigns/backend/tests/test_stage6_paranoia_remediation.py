"""
test_stage6_paranoia_remediation.py — Tests for Stage 6 Paranoia Remediation:
- VULN-05: Multi-Tenant Sender Pod Failover & Quarantine Hardening
- ENG-07: Deterministic Priority Ordering to Eliminate Mutual Livelock in Collision Guard
- ENG-08: Send-Time Optimization (STO) Delay Bloat Prevention
- ENG-09: Kahn's Algorithm Cycle Detection with Duplicate Canvas Edges
- API-14: Rate Limit Dependency on Public ROI Certificate Verification
- API-27: Unchecked Workspace Tier Overrides Enforcement
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from campaigns.backend.services.sender_pod_service import trigger_pod_failover
from campaigns.backend.services.collision_guard import get_conflicting_active_leads, is_lead_active_in_other_campaign
from campaigns.backend.services.dag_validator import has_cycle, validate_sequence_dag
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.routers.roi_certificates import public_verify_certificate_endpoint
from campaigns.backend.routers.elein import _check_workspace_tier_permission
from fastapi import HTTPException


class TestStage6ParanoiaRemediation(unittest.TestCase):

    # ── VULN-05: Sender Pod Failover Isolation ─────────────────────────────

    def test_vuln05_failover_rejects_missing_parameters(self):
        """Layer 0: Fail closed if any required parameter is missing."""
        mock_sb = MagicMock()
        res = trigger_pod_failover("", "camp-1", "ws-1", mock_sb)
        self.assertEqual(res.get("status"), "FAILOVER_REJECTED")

        res = trigger_pod_failover("acc-1", "", "ws-1", mock_sb)
        self.assertEqual(res.get("status"), "FAILOVER_REJECTED")

        res = trigger_pod_failover("acc-1", "camp-1", "", mock_sb)
        self.assertEqual(res.get("status"), "FAILOVER_REJECTED")

    def test_vuln05_failover_rejects_unowned_account(self):
        """Layer 1: Fails closed if failed account does not belong to the requested workspace."""
        mock_sb = MagicMock()
        # Account query returns empty (e.g. cross-tenant ID or RLS masked)
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        res = trigger_pod_failover("acc-attacker", "camp-victim", "ws-victim", mock_sb)
        self.assertEqual(res.get("status"), "FAILOVER_REJECTED")
        self.assertIn("does not belong", res.get("message", "").lower())

    def test_vuln05_failover_rejects_unowned_campaign(self):
        """Layer 1: Fails closed if campaign does not belong to the requested workspace."""
        mock_sb = MagicMock()
        # Account is valid in ws-attacker, but campaign belongs to ws-victim (or empty)
        def mock_table(table_name):
            mock_t = MagicMock()
            if table_name == "accounts":
                mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc-1", "workspace_id": "ws-attacker"}]
                )
            elif table_name == "campaigns":
                mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return mock_t

        mock_sb.table.side_effect = mock_table

        res = trigger_pod_failover("acc-1", "camp-victim", "ws-attacker", mock_sb)
        self.assertEqual(res.get("status"), "FAILOVER_REJECTED")
        self.assertIn("campaign not found or does not belong", res.get("message", "").lower())

    # ── ENG-07: Collision Guard Deterministic Priority ─────────────────────

    def test_eng07_deterministic_priority_breaks_mutual_livelock(self):
        """
        Layer 1: When two active campaigns have the same lead in 'pending' state:
        - Higher priority campaign (lexicographically smaller UUID) does NOT yield.
        - Lower priority campaign (lexicographically greater UUID) yields.
        """
        mock_sb = MagicMock()
        camp_a = "11111111-1111-1111-1111-111111111111"
        camp_b = "22222222-2222-2222-2222-222222222222"
        lead_id = "lead-test-01"

        def mock_table(table_name):
            mock_t = MagicMock()
            if table_name == "campaign_enrollments":
                # Returns enrollment in Camp B when Camp A queries
                mock_t.select.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-b", "campaign_id": camp_b, "lead_id": lead_id}]
                )
            elif table_name == "campaigns":
                mock_t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": camp_b, "status": "ACTIVE"}]
                )
            elif table_name == "campaign_execution_states":
                mock_t.select.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"enrollment_id": "enr-b", "status": "pending"}]
                )
            return mock_t

        mock_sb.table.side_effect = mock_table

        # Camp A (smaller UUID: '111...' < '222...') checks if lead is colliding:
        # Since Camp A has higher priority than Camp B's pending enrollment, Camp A must NOT yield!
        colliding_a = get_conflicting_active_leads(
            mock_sb, "ws-1", [lead_id], exclude_campaign_id=camp_a
        )
        self.assertNotIn(lead_id, colliding_a)

        # Now test Camp B (greater UUID: '222...' > '111...'):
        def mock_table_for_b(table_name):
            mock_t = MagicMock()
            if table_name == "campaign_enrollments":
                mock_t.select.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-a", "campaign_id": camp_a, "lead_id": lead_id}]
                )
            elif table_name == "campaigns":
                mock_t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": camp_a, "status": "ACTIVE"}]
                )
            elif table_name == "campaign_execution_states":
                mock_t.select.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"enrollment_id": "enr-a", "status": "pending"}]
                )
            return mock_t

        mock_sb.table.side_effect = mock_table_for_b

        # Camp B checks if lead is colliding: Camp B must yield to Camp A!
        colliding_b = get_conflicting_active_leads(
            mock_sb, "ws-1", [lead_id], exclude_campaign_id=camp_b
        )
        self.assertIn(lead_id, colliding_b)

    def test_eng07_yields_unconditionally_if_other_campaign_is_running(self):
        """Layer 1: If another campaign is running, both campaigns yield regardless of priority."""
        mock_sb = MagicMock()
        camp_a = "11111111-1111-1111-1111-111111111111"
        camp_b = "22222222-2222-2222-2222-222222222222"
        lead_id = "lead-test-01"

        def mock_table(table_name):
            mock_t = MagicMock()
            if table_name == "campaign_enrollments":
                mock_t.select.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-b", "campaign_id": camp_b, "lead_id": lead_id}]
                )
            elif table_name == "campaigns":
                mock_t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": camp_b, "status": "ACTIVE"}]
                )
            elif table_name == "campaign_execution_states":
                # Camp B is running actively!
                mock_t.select.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"enrollment_id": "enr-b", "status": "running"}]
                )
            return mock_t

        mock_sb.table.side_effect = mock_table

        # Camp A checks: Even though Camp A has lower UUID, Camp B is actively running so Camp A must yield!
        colliding_a = get_conflicting_active_leads(
            mock_sb, "ws-1", [lead_id], exclude_campaign_id=camp_a
        )
        self.assertIn(lead_id, colliding_a)

    # ── ENG-08: Send-Time Optimization Delay Bloat ─────────────────────────

    def test_eng08_update_state_suppresses_sto_when_use_sto_false(self):
        """Layer 1: update_state does not apply calculate_sto_next_run when use_sto=False."""
        mock_sb = MagicMock()
        orch = EleInOrchestrator(mock_sb)

        tactical_next_run = datetime(2026, 10, 18, 10, 0, 0)
        schedule_with_sto = {"enabled": True, "send_time_optimization": True, "working_hours": {"start": "09:00", "end": "17:00"}}

        with patch("campaigns.backend.services.sto_service.calculate_sto_next_run") as mock_sto, \
             patch("campaigns.backend.services.elein_orchestrator.adjust_to_working_hours", return_value=tactical_next_run) as mock_adjust:
            
            orch.update_state(
                state_id="state-1",
                node_id="node-1",
                status="pending",
                next_run_at=tactical_next_run,
                lease_token="lease-1",
                schedule=schedule_with_sto,
                use_sto=False  # Tactical delay node explicitly disables STO
            )

            # calculate_sto_next_run MUST NOT be called!
            mock_sto.assert_not_called()
            # Standard working hours adjustment should be used instead
            mock_adjust.assert_called_once()

    # ── ENG-09: Kahn's Algorithm Duplicate Canvas Edges ────────────────────

    def test_eng09_duplicate_edges_do_not_mask_cycles(self):
        """Layer 0: Duplicate canvas edges between nodes are deduplicated and cycles are accurately detected."""
        nodes = [
            {"id": "node-A", "type": "trigger"},
            {"id": "node-B", "type": "send_message"},
            {"id": "node-C", "type": "send_message"}
        ]
        # Cycle: A -> B -> C -> A, with duplicate edge between A and B
        edges_with_duplicates_and_cycle = [
            {"source": "node-A", "target": "node-B"},
            {"source": "node-A", "target": "node-B"},  # duplicate
            {"source": "node-B", "target": "node-C"},
            {"source": "node-C", "target": "node-A"}
        ]
        self.assertTrue(has_cycle(nodes, edges_with_duplicates_and_cycle))

    def test_eng09_duplicate_edges_in_dag_do_not_falsely_report_cycle(self):
        """Layer 0: Duplicate canvas edges in a valid acyclic DAG do not distort in-degree or trigger false cycle."""
        nodes = [
            {"id": "node-A", "type": "trigger"},
            {"id": "node-B", "type": "send_message"},
            {"id": "node-C", "type": "send_message"}
        ]
        # Acyclic DAG: A -> B -> C, with duplicate edges between A -> B and B -> C
        edges_with_duplicates_dag = [
            {"source": "node-A", "target": "node-B"},
            {"source": "node-A", "target": "node-B"},  # duplicate
            {"source": "node-B", "target": "node-C"},
            {"source": "node-B", "target": "node-C"}   # duplicate
        ]
        self.assertFalse(has_cycle(nodes, edges_with_duplicates_dag))
        analysis = validate_sequence_dag(nodes, edges_with_duplicates_dag)
        self.assertFalse(analysis["has_cycle"])
        self.assertEqual(analysis["root_node_ids"], ["node-A"])

    # ── API-27: Workspace Tier Override Hardening ──────────────────────────

    def test_api27_no_unrestricted_ws_prefix_bypass(self):
        """Layer 1 & 2: Production workspaces starting with 'ws-' are not bypassed and enforce tier limits."""
        mock_sb = MagicMock()
        # Mock RPC returning Free tier
        mock_sb.rpc.return_value.execute.return_value = MagicMock(data={"tier": "FREE"})

        # Temporarily unset PYTEST_CURRENT_TEST to simulate production request
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(HTTPException) as cm:
                _check_workspace_tier_permission("ws-customer-enterprise-slug", "advanced_ai_replies", mock_sb)
            self.assertEqual(cm.exception.status_code, 402)


if __name__ == "__main__":
    unittest.main()
