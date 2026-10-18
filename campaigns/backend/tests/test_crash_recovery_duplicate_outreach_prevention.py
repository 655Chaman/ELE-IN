"""
Three-Layer Paranoia Framework Unit Test Suite — Audit Finding #6:
Mid-Send Worker Crash Recovery & Duplicate Outreach Prevention Guard
"""
import os
import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestCrashRecoveryDuplicateOutreachPrevention(unittest.TestCase):
    def setUp(self):
        self.mock_supabase = MagicMock()
        self.tables = defaultdict(MagicMock)
        self.mock_supabase.table.side_effect = lambda name: self.tables[name]
        self.orchestrator = EleInOrchestrator(self.mock_supabase)
        self.workspace_id = "ws_crash_test"
        self.enrollment_id = "enr_crash_123"
        self.node_id = "node_email_step_1"
        self.lead_id = "lead_456"
        self.account_id = "acc_sender_789"
        self.lease_token = "lease_tok_999"

        # Mock lead existence query
        self.tables["leads"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.lead_id,
                "first_name": "Sarah",
                "last_name": "Connor",
                "email": "sarah@cyberdyne.com",
                "company_name": "Cyberdyne",
                "job_title": "CEO"
            }]
        )

    def test_layer0_mid_send_crash_with_logged_message_fast_forwards(self):
        """
        Layer 0 (Foundational): When recovering a crashed 'running' execution state,
        if the outbound message was already recorded in `messages`, the orchestrator
        MUST fast-forward and NEVER re-dispatch the outreach touch.
        """
        action = "send_email"
        data = {"subject": "Follow up", "body": "Checking in"}
        state = {
            "id": "state_789",
            "workspace_id": self.workspace_id,
            "enrollment_id": self.enrollment_id,
            "lead_id": self.lead_id,
            "attempts": 0,
            "variables": {"prev_key": "val"}
        }

        # Simulate unique constraint violation on campaign_node_executions insert (collision)
        err = Exception("Unique violation duplicate key value violates unique constraint 23505")
        setattr(err, "code", "23505")
        self.tables["campaign_node_executions"].insert.return_value.execute.side_effect = err

        # Collision query returns 'running' (previous worker crashed mid-send)
        self.tables["campaign_node_executions"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "running", "output_payload": {"branch": "THEN"}}]
        )

        # Downstream check: messages table ALREADY has outbound message
        self.tables["messages"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "msg_already_sent_001", "direction": "outbound"}]
        )

        with patch("campaigns.backend.services.elein_executor.EleInNodeExecutor") as MockExecutor:
            res = self.orchestrator.execute_node_action(
                action=action,
                data=data,
                opportunity_id=self.lead_id,
                account_id=self.account_id,
                state=state,
                lease_token=self.lease_token,
                current_node_id=self.node_id
            )
            
            # The executor MUST NOT have been called (no duplicate email dispatched!)
            MockExecutor.assert_not_called()

        self.assertEqual(res.get("status"), "fast_forward")
        self.assertEqual(res.get("branch"), "THEN")

        # campaign_node_executions must be updated to 'success'
        self.tables["campaign_node_executions"].update.assert_called()
        update_args = self.tables["campaign_node_executions"].update.call_args[0][0]
        self.assertEqual(update_args.get("status"), "success")
        self.assertTrue(update_args.get("output_payload", {}).get("recovered_from_crash"))

    def test_layer1_mid_send_crash_with_action_log_success_fast_forwards(self):
        """
        Layer 1 (Environmental): If messages check misses but action_log confirms 'success',
        the orchestrator avoids re-executing external API.
        """
        action = "send_message"
        data = {"body": "Hello Sarah"}
        state = {
            "id": "state_789",
            "workspace_id": self.workspace_id,
            "enrollment_id": self.enrollment_id,
            "lead_id": self.lead_id,
            "attempts": 1
        }

        # LinkedIn account mock so it doesn't fail pre-check
        self.tables["accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.account_id, "status": "ACTIVE", "session_cookies_encrypted": None, "workspace_id": self.workspace_id}]
        )
        self.mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=True)

        err = Exception("23505 duplicate key")
        self.tables["campaign_node_executions"].insert.return_value.execute.side_effect = err
        self.tables["campaign_node_executions"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "running", "output_payload": {}}]
        )

        # messages table empty
        self.tables["messages"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        # action_log has success
        self.tables["action_log"].select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "act_log_002", "result": "success"}]
        )

        with patch("campaigns.backend.services.elein_executor.EleInNodeExecutor") as MockExecutor, \
             patch("campaigns.backend.services.elein_orchestrator.try_acquire_session_lock", return_value=True), \
             patch("campaigns.backend.services.elein_orchestrator.try_consume_action", return_value=True), \
             patch("campaigns.backend.services.elein_orchestrator.release_session_lock"):
            res = self.orchestrator.execute_node_action(
                action=action,
                data=data,
                opportunity_id=self.lead_id,
                account_id=self.account_id,
                state=state,
                lease_token=self.lease_token,
                current_node_id=self.node_id
            )
            MockExecutor.assert_not_called()

        self.assertEqual(res.get("status"), "fast_forward")

    def test_layer2_clean_retry_when_no_prior_send_verified(self):
        """
        Layer 2 (Human Paranoia): When crash happened BEFORE the external call,
        no message or action_log exists. The lock is cleanly reclaimed as 'running'
        and normal execution proceeds.
        """
        action = "custom_webhook"
        data = {"webhook_url": "https://example.com/hook"}
        state = {
            "id": "state_789",
            "workspace_id": self.workspace_id,
            "enrollment_id": self.enrollment_id,
            "lead_id": self.lead_id,
            "attempts": 0
        }

        err = Exception("23505 unique collision")
        self.tables["campaign_node_executions"].insert.return_value.execute.side_effect = err
        self.tables["campaign_node_executions"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "running", "output_payload": {}}]
        )

        # No messages, action_log, or outbox_events found
        self.tables["messages"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.tables["action_log"].select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.tables["outbox_events"].select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        # Atomic reclaim update succeeds
        self.tables["campaign_node_executions"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "cne_reclaimed"}]
        )

        with patch("campaigns.backend.services.elein_executor.EleInNodeExecutor") as MockExecutor:
            instance = MockExecutor.return_value
            instance.execute.return_value = {"status": "success", "branch": "THEN"}
            res = self.orchestrator.execute_node_action(
                action=action,
                data=data,
                opportunity_id=self.lead_id,
                account_id=self.account_id,
                state=state,
                lease_token=self.lease_token,
                current_node_id=self.node_id
            )
            instance.execute.assert_called_once()

        self.assertEqual(res.get("status"), "success")


if __name__ == "__main__":
    unittest.main()
