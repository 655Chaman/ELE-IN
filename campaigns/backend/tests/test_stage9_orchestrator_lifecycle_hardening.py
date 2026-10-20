"""
Stage 9 Orchestrator Lifecycle & Concurrency Hardening Test Suite
Covers Flaws 32 - 35 under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestStage9OrchestratorLifecycleHardening(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        self.state_id = "state-st9-123"
        self.enrollment_id = "enr-st9-456"
        self.campaign_id = "camp-st9-789"
        self.lead_id = "lead-st9-999"
        self.lease_token = "lease-token-st9"

    # =========================================================================
    # FLAW 32: Deleted / Paused / Terminal Campaign Orphan Lead Execution Guard
    # =========================================================================

    def test_flaw32_deleted_campaign_exits_orphan_lead_immediately(self):
        """Layer 0 & 1: When a campaign was deleted, lead state exits immediately instead of re-entering pending."""
        state = {
            "id": self.state_id,
            "campaign_id": self.campaign_id,
            "opportunity_id": self.lead_id,
            "lead_id": self.lead_id,
            "enrollment_id": self.enrollment_id,
            "current_node_id": "node-1",
            "nodes": [
                {"id": "node-1", "node_type": "delay", "config": {"delay": 1, "delayUnit": "days"}},
                {"id": "node-2", "node_type": "send_message", "config": {}}
            ],
            "edges": [{"source": "node-1", "target": "node-2"}],
            "campaign_metadata": {}
        }

        # Mock campaign query returning empty list (campaign deleted)
        mock_camp_query = MagicMock()
        mock_camp_query.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value.select.return_value.eq.return_value = mock_camp_query

        with patch.object(self.orchestrator, "update_state") as mock_update:
            self.orchestrator.process_lead(state, lease_token=self.lease_token)

            mock_update.assert_called_once()
            called_args = mock_update.call_args[0]
            called_kwargs = mock_update.call_args[1]
            self.assertEqual(called_args[0], self.state_id)
            self.assertIsNone(called_args[1])  # node_id set to None
            self.assertEqual(called_args[2], "exited")  # status must be exited
            self.assertIsNone(called_args[3])  # next_run_at must be None
            self.assertEqual(called_kwargs.get("error_reason"), "Campaign deleted or not found")
            self.assertEqual(called_kwargs.get("enrollment_id"), self.enrollment_id)

    def test_flaw32_terminal_campaign_status_exits_lead_without_rescheduling(self):
        """Layer 1: Terminal statuses (ARCHIVED, DELETED, CANCELLED, STOPPED) exit lead states permanently."""
        for term_status in ["ARCHIVED", "DELETED", "CANCELLED", "STOPPED"]:
            state = {
                "id": self.state_id,
                "campaign_id": self.campaign_id,
                "opportunity_id": self.lead_id,
                "lead_id": self.lead_id,
                "enrollment_id": self.enrollment_id,
                "current_node_id": "node-1",
                "nodes": [
                    {"id": "node-1", "node_type": "delay", "config": {"delay": 1, "delayUnit": "days"}},
                    {"id": "node-2", "node_type": "send_message", "config": {}}
                ],
                "edges": [{"source": "node-1", "target": "node-2"}],
                "campaign_metadata": {}
            }

            mock_camp_query = MagicMock()
            mock_camp_query.execute.return_value = MagicMock(data=[{"status": term_status}])
            self.mock_supabase.table.return_value.select.return_value.eq.return_value = mock_camp_query

            with patch.object(self.orchestrator, "update_state") as mock_update:
                self.orchestrator.process_lead(state, lease_token=self.lease_token)

                mock_update.assert_called_once()
                called_args = mock_update.call_args[0]
                called_kwargs = mock_update.call_args[1]
                self.assertEqual(called_args[2], "exited")
                self.assertIsNone(called_args[3])
                self.assertEqual(called_kwargs.get("error_reason"), f"Campaign is {term_status}")
                self.assertEqual(called_kwargs.get("enrollment_id"), self.enrollment_id)

    def test_flaw32_process_pending_leads_cleans_orphaned_claimed_states(self):
        """Layer 0 & 2: process_pending_leads exits states missing enrollment or campaign rather than dropping them in 'running'."""
        claimed_states = [
            {"id": "st-orphan-enr", "enrollment_id": "enr-missing", "current_node_id": "n1", "lease_token": "lt-1", "status": "running"},
            {"id": "st-orphan-camp", "enrollment_id": "enr-valid", "current_node_id": "n1", "lease_token": "lt-2", "status": "running"}
        ]

        # dequeue_due_leads returns the 2 claimed states
        self.mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=claimed_states)

        # active campaigns query returns 1 campaign
        mock_camps_res = MagicMock(data=[{"id": "camp-active", "status": "ACTIVE", "workspace_id": "ws-1", "metadata": {}}])
        # enrollments query returns enr-valid pointing to missing campaign
        mock_enr_res = MagicMock(data=[{"id": "enr-valid", "campaign_id": "camp-deleted", "lead_id": "lead-1", "account_id": "acc-1", "workspace_id": "ws-1", "campaign_version_id": "v1"}])
        mock_ws_res = MagicMock(data=[{"id": "ws-1", "status": "active"}])

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "campaigns":
                m.select.return_value.eq.return_value.execute.return_value = mock_camps_res
            elif table_name == "workspaces":
                m.select.return_value.in_.return_value.execute.return_value = mock_ws_res
            elif table_name == "campaign_enrollments":
                m.select.return_value.in_.return_value.execute.return_value = mock_enr_res
            elif table_name == "campaign_execution_states":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                m.select.return_value.in_.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return m

        self.mock_supabase.table.side_effect = table_side_effect

        with patch.object(self.orchestrator, "update_state") as mock_update:
            self.orchestrator.process_pending_leads()

            # Both orphaned states must have been updated to 'exited'
            self.assertEqual(mock_update.call_count, 2)
            call1 = mock_update.call_args_list[0]
            self.assertEqual(call1[0][0], "st-orphan-enr")
            self.assertEqual(call1[0][2], "exited")
            self.assertEqual(call1[1].get("error_reason"), "Orphaned state: campaign enrollment not found")

            call2 = mock_update.call_args_list[1]
            self.assertEqual(call2[0][0], "st-orphan-camp")
            self.assertEqual(call2[0][2], "exited")
            self.assertEqual(call2[1].get("error_reason"), "Orphaned state: campaign not found or deleted")

    # =========================================================================
    # FLAW 33: Reply Detection & Stop-on-Reply State Synchronization
    # =========================================================================

    def test_flaw33_stop_on_reply_synchronizes_enrollment_and_lead_status(self):
        """Layer 0 & 1: When inbound reply is detected, lead state, enrollment, and leads table are synchronized."""
        state = {
            "id": self.state_id,
            "campaign_id": self.campaign_id,
            "opportunity_id": self.lead_id,
            "lead_id": self.lead_id,
            "enrollment_id": self.enrollment_id,
            "current_node_id": "node-msg",
            "nodes": [
                {"id": "node-msg", "node_type": "send_message", "config": {}}
            ],
            "edges": [],
            "campaign_metadata": {"stop_on_reply": True},
            "enrollment_created_at": "2026-10-10T10:00:00Z"
        }

        # Mock messages table query detecting inbound message
        mock_msg_res = MagicMock(data=[{"id": "msg-inbound-1"}])
        mock_lead_update = MagicMock()

        def table_side_effect(table_name):
            m = MagicMock()
            if table_name == "messages":
                m.select.return_value.eq.return_value.or_.return_value.gt.return_value.limit.return_value.execute.return_value = mock_msg_res
            elif table_name == "leads":
                m.update.return_value.eq.return_value = mock_lead_update
            return m

        self.mock_supabase.table.side_effect = table_side_effect

        with patch.object(self.orchestrator, "update_state") as mock_update:
            self.orchestrator.process_lead(state, lease_token=self.lease_token)

            mock_update.assert_called_once()
            called_args = mock_update.call_args[0]
            called_kwargs = mock_update.call_args[1]
            self.assertEqual(called_args[0], self.state_id)
            self.assertEqual(called_args[2], "completed")
            self.assertEqual(called_kwargs.get("enrollment_id"), self.enrollment_id)

            # Leads table must have been updated to 'replied'
            mock_lead_update.execute.assert_called_once()

    # =========================================================================
    # FLAW 34: Zombie Worker Lease Theft Prevention
    # =========================================================================

    def test_flaw34_zombie_worker_lease_theft_prevention_on_stale_claim(self):
        """Layer 0 & 1: If release_lead_claim RPC reports lease expired/stolen, update_state returns False without overwrite."""
        # Mock release_lead_claim returning False (lease expired or acquired by another worker)
        self.mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=False)

        res = self.orchestrator.update_state(
            state_id=self.state_id,
            node_id="node-2",
            status="completed",
            next_run_at=None,
            lease_token="expired-token",
            enrollment_id=self.enrollment_id
        )

        self.assertFalse(res)
        # Should not attempt to update campaign_enrollments
        self.mock_supabase.table.assert_not_called()

    def test_flaw34_table_fallback_zero_matched_rows_rejects_stale_worker(self):
        """Layer 1: When direct table fallback matches 0 rows (lease_token mismatch), returns False safely."""
        self.mock_supabase.rpc.side_effect = Exception("RPC unavailable")

        mock_upd_query = MagicMock()
        mock_upd_query.execute.return_value = MagicMock(data=[])  # 0 rows updated
        self.mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value = mock_upd_query

        res = self.orchestrator.update_state(
            state_id=self.state_id,
            node_id="node-2",
            status="completed",
            next_run_at=None,
            lease_token="stale-token",
            enrollment_id=self.enrollment_id
        )

        self.assertFalse(res)

    # =========================================================================
    # FLAW 35: Terminal Node & Branch Enrollment Synchronization
    # =========================================================================

    def test_flaw35_terminal_node_synchronizes_campaign_enrollment_to_completed(self):
        """Layer 0 & 1: When execution reaches a terminal node or terminal branch, campaign_enrollments is set to completed."""
        # Direct call to update_state with status='completed' and enrollment_id
        self.mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=True)

        mock_enr_update = MagicMock()
        mock_enr_table = MagicMock()
        mock_enr_table.update.return_value.eq.return_value = mock_enr_update

        def table_side_effect(table_name):
            if table_name == "campaign_enrollments":
                return mock_enr_table
            return MagicMock()

        self.mock_supabase.table.side_effect = table_side_effect

        res = self.orchestrator.update_state(
            state_id=self.state_id,
            node_id=None,
            status="completed",
            next_run_at=None,
            lease_token=self.lease_token,
            enrollment_id=self.enrollment_id
        )

        self.assertTrue(res)
        mock_enr_table.update.assert_called_once()
        payload = mock_enr_table.update.call_args[0][0]
        self.assertEqual(payload["status"], "completed")
        self.assertIn("completed_at", payload)
        self.assertIn("updated_at", payload)
        mock_enr_table.update.return_value.eq.assert_called_with("id", self.enrollment_id)


if __name__ == "__main__":
    unittest.main()
