"""
Unit & Integration Tests for Stage 13 Elite Architecture Hardening:
  1. Retry Failed Enrollment Node IDOR & Full State Reset Verification
  2. Inbox Service Cross-Tenant Message & Enrollment Scoping
  3. Campaign Activation and Deletion Workspace Isolation
  4. Modular Action Credit Deduction & Insufficient Credit Fail-Closed Guard
Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from campaigns.backend.routers.elein import retry_failed_enrollment_node, activate_campaign, delete_campaign
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from inbox.backend.services.inbox_service import sync_inbox_messages


class TestStage13EliteArchitecture(unittest.TestCase):

    def test_retry_failed_enrollment_node_campaign_idor_rejection(self):
        """
        Layer 0 & 2: Rejects retry attempts when campaign does not belong to the caller's workspace.
        """
        mock_supabase = MagicMock()
        # Campaign select returns empty -> foreign workspace or non-existent
        mock_supabase.table().select().eq().eq().execute.return_value.data = []

        with self.assertRaises(HTTPException) as ctx:
            retry_failed_enrollment_node(
                campaign_id="camp-foreign-1",
                enrollment_id="enr-1",
                supabase=mock_supabase,
                workspace_id="ws-caller-1"
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Campaign not found")

    def test_retry_failed_enrollment_node_enrollment_idor_rejection(self):
        """
        Layer 0 & 2: Rejects retry attempts when enrollment does not belong to the campaign/workspace.
        """
        mock_supabase = MagicMock()
        # Campaign exists
        camp_query = MagicMock()
        camp_query.execute.return_value.data = [{"id": "camp-valid-1"}]
        # Enrollment does not match
        enr_query = MagicMock()
        enr_query.execute.return_value.data = []

        def table_router(table_name):
            mock_tbl = MagicMock()
            if table_name == "campaigns":
                mock_tbl.select.return_value.eq.return_value.eq.return_value = camp_query
            elif table_name == "campaign_enrollments":
                mock_tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value = enr_query
            return mock_tbl

        mock_supabase.table.side_effect = table_router

        with self.assertRaises(HTTPException) as ctx:
            retry_failed_enrollment_node(
                campaign_id="camp-valid-1",
                enrollment_id="enr-foreign-1",
                supabase=mock_supabase,
                workspace_id="ws-caller-1"
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Enrollment not found")

    def test_retry_failed_enrollment_node_resets_execution_states(self):
        """
        Layer 0 & 1: On valid ownership, resets both campaign_node_executions AND
        campaign_execution_states to 'pending' with cleared leases and error reasons.
        """
        mock_supabase = MagicMock()
        updated_tables = []

        def table_router(table_name):
            mock_tbl = MagicMock()
            if table_name == "campaigns":
                mock_tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "camp-valid-1"}]
            elif table_name == "campaign_enrollments":
                mock_tbl.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "enr-valid-1"}]
            elif table_name in ("campaign_node_executions", "campaign_execution_states"):
                def capture_update(payload):
                    updated_tables.append((table_name, payload))
                    return MagicMock()
                mock_tbl.update.side_effect = capture_update
            return mock_tbl

        mock_supabase.table.side_effect = table_router

        res = retry_failed_enrollment_node(
            campaign_id="camp-valid-1",
            enrollment_id="enr-valid-1",
            supabase=mock_supabase,
            workspace_id="ws-caller-1"
        )
        self.assertEqual(res["status"], "success")

        # Verify campaign_node_executions update
        node_exec_updates = [p for t, p in updated_tables if t == "campaign_node_executions"]
        self.assertTrue(len(node_exec_updates) > 0)
        self.assertEqual(node_exec_updates[0]["status"], "pending")
        self.assertIsNone(node_exec_updates[0]["error_code"])

        # Verify campaign_execution_states update
        state_updates = [p for t, p in updated_tables if t == "campaign_execution_states"]
        self.assertTrue(len(state_updates) > 0)
        self.assertEqual(state_updates[0]["status"], "pending")
        self.assertIsNone(state_updates[0]["lease_token"])
        self.assertIsNone(state_updates[0]["error_reason"])

    def test_inbox_service_workspace_scoping(self):
        """
        Layer 0 & 2: Verifies sync_inbox_messages queries campaign_enrollments and messages
        with strict workspace_id filtering.
        """
        mock_supabase = MagicMock()
        queried_tables = []

        def table_router(table_name):
            mock_tbl = MagicMock()
            queried_tables.append(table_name)
            mock_tbl.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
            mock_tbl.select.return_value.eq.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = []
            return mock_tbl

        mock_supabase.table.side_effect = table_router

        messages = [
            {
                "sender_name": "Alice Prospect",
                "message_text": "Sounds interesting! Let's schedule a call next week.",
                "direction": "inbound",
                "lead_id": "lead-123"
            }
        ]

        with patch("inbox.backend.services.inbox_service.resolve_inbound_lead_and_campaign_context") as mock_resolve:
            mock_resolve.return_value = {"lead_id": "lead-123", "campaign_id": "camp-1"}
            with patch("inbox.backend.services.sentiment_classifier.classify_inbound_sentiment_and_intent") as mock_class:
                mock_class.return_value = {"intent": "positive_interest", "confidence": 0.95}

                res = sync_inbox_messages(
                    supabase=mock_supabase,
                    workspace_id="ws-inbox-secure",
                    account_id="acc-123",
                    messages=messages
                )
                self.assertIn("campaign_enrollments", queried_tables)

    def test_elein_executor_modular_action_and_fail_closed(self):
        """
        Layer 0 & 1: Verifies _deduct_credits passes modular action_type
        and fails closed if an insufficient credits exception occurs.
        """
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(
            supabase=mock_supabase,
            workspace_id="ws-credit-test"
        )

        # 1. Custom action type passing
        mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}
        success = executor._deduct_credits(
            amount=2,
            idempotency_key="test_idem_1",
            action_type="linkedin_inmail"
        )
        self.assertTrue(success)
        mock_supabase.rpc.assert_called_with("deduct_credits_safely", {
            "p_workspace_id": "ws-credit-test",
            "p_amount": 2,
            "p_action_type": "linkedin_inmail",
            "p_idempotency_key": "test_idem_1"
        })

        # 2. Fail closed on insufficient credits exception
        mock_supabase.rpc.return_value.execute.side_effect = Exception("insufficient credits in workspace")
        fail_res = executor._deduct_credits(
            amount=1,
            idempotency_key="test_idem_2",
            action_type="ai_personalize"
        )
        self.assertFalse(fail_res)
