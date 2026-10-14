import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import os
import time
import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException

from core.backend.api.routers.approvals import (
    approve_reply,
    reject_reply,
    magic_approval_handler,
    validate_approval_message,
    ApprovalActionRequest,
    _active_approvals,
    _approval_locks_mutex,
)


class TestApprovalQueueStaleLeadAndEditGuard(unittest.TestCase):
    """
    Step 35 Track A — AI Reply Approval Queue Stale-Lead & DNC Guard,
    Human-Edit Sanitization, Double-Approve Concurrency Lock & Magic-Link Dispatch Fix.
    """

    def setUp(self):
        with _approval_locks_mutex:
            _active_approvals.clear()

    def tearDown(self):
        with _approval_locks_mutex:
            _active_approvals.clear()

    def _setup_multi_table_mock(self):
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)

        def get_table(tbl_name):
            return tables[tbl_name]

        mock_svc.table.side_effect = get_table
        return mock_svc, tables

    # =========================================================================
    # 1. Human-Edit & Draft Message Sanitization (Layer 2)
    # =========================================================================

    def test_validate_approval_message_rejects_unresolved_template_tags(self):
        """Rejects human-edited messages containing raw {{variable}} tags with HTTP 422."""
        with self.assertRaises(HTTPException) as ctx:
            validate_approval_message("Hi {{first_name}}, would love to chat about {{company}}!")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("unresolved template", ctx.exception.detail.lower())

    def test_validate_approval_message_rejects_bracketed_placeholders(self):
        """Rejects human-edited messages containing [First Name] or [Insert Link] placeholders with HTTP 422."""
        with self.assertRaises(HTTPException) as ctx:
            validate_approval_message("Hey [First Name], check out [Insert Calendar Link] when free.")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("placeholder", ctx.exception.detail.lower())

    def test_validate_approval_message_rejects_over_2000_chars(self):
        """Rejects messages exceeding LinkedIn's 2,000-character limit with HTTP 422."""
        long_msg = "A" * 2005
        with self.assertRaises(HTTPException) as ctx:
            validate_approval_message(long_msg)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("2000", ctx.exception.detail)

    def test_approve_reply_blocks_edited_message_with_unresolved_tags(self):
        """End-to-end check that approve_reply refuses to enqueue a message with {{first_name}}."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_edit_1",
                "status": "pending",
                "ai_draft": "Clean draft",
                "account_id": "acc_1",
                "sender_name": "Alice"
            }]
        )

        payload = ApprovalActionRequest(edited_message="Hi {{first_name}}, let's talk!")
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_edit_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 422)

    # =========================================================================
    # 2. In-Flight Concurrency Lock (Layer 1)
    # =========================================================================

    def test_concurrent_approve_reply_locked_returns_409(self):
        """If an approval is currently being processed by another request/tab, returns HTTP 409."""
        mock_svc, tables = self._setup_multi_table_mock()
        with _approval_locks_mutex:
            _active_approvals["app_locked_1"] = time.time()

        payload = ApprovalActionRequest(edited_message="Hello there")
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_locked_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("already in progress", ctx.exception.detail.lower())

    # =========================================================================
    # 3. Stale Lead / Unsubscribed / DNC Suppression Pre-Send Guard (Layer 1)
    # =========================================================================

    @patch("core.backend.api.routers.approvals.enqueue_job")
    def test_approve_reply_aborts_and_skips_when_lead_unsubscribed(self, mock_enqueue):
        """If lead unsubscribed while AI draft sat in queue, skips draft, exits state, and does NOT enqueue job."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["ai_reply_approvals"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_stale_1",
                "status": "pending",
                "generated_reply": "Thanks for reaching out!",
                "lead_id": "lead_unsub_1",
                "enrollment_id": "enr_1",
                "execution_state_id": "exec_1"
            }]
        )
        tables["leads"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "lead_unsub_1",
                "first_name": "Bob",
                "last_name": "Smith",
                "linkedin_url": "https://www.linkedin.com/in/bobsmith",
                "status": "Unsubscribed",
                "is_unsubscribed": True,
                "metadata": {"unsubscribed": True}
            }]
        )

        payload = ApprovalActionRequest()
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_stale_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 409)
        mock_enqueue.assert_not_called()
        tables["ai_reply_approvals"].update.assert_called()
        tables["campaign_execution_states"].update.assert_called()

    @patch("leads.backend.services.suppression_service.check_lead_suppression")
    @patch("core.backend.api.routers.approvals.enqueue_job")
    def test_approve_reply_aborts_when_lead_on_dnc_suppression_list(self, mock_enqueue, mock_check_sup):
        """If lead is on workspace DNC suppression list, blocks approval with 409 and never dispatches."""
        mock_check_sup.return_value = {"is_suppressed": True, "reason": "domain:acme.com"}

        mock_svc, tables = self._setup_multi_table_mock()
        tables["approval_queue"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["ai_reply_approvals"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_dnc_1",
                "status": "pending",
                "generated_reply": "Following up with you!",
                "lead_id": "lead_dnc_1",
                "execution_state_id": "exec_dnc_1"
            }]
        )
        tables["leads"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "lead_dnc_1",
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane@acme.com",
                "linkedin_url": "https://www.linkedin.com/in/janedoe",
                "status": "Active",
                "is_unsubscribed": False,
                "metadata": {}
            }]
        )

        payload = ApprovalActionRequest()
        with self.assertRaises(HTTPException) as ctx:
            approve_reply("app_dnc_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("suppressed", ctx.exception.detail.lower())
        mock_enqueue.assert_not_called()

    # =========================================================================
    # 4. Magic-Link Dispatch & Tenant Isolation Fix (Layer 0 & Layer 1)
    # =========================================================================

    @patch("core.backend.api.routers.approvals.enqueue_job")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_enqueues_delivery_job_when_account_present(self, mock_svc_factory, mock_enqueue):
        """Magic link approval actually enqueues inbox_action job for delivery when account_id is resolved."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_magic_1",
                "workspace_id": "ws_magic",
                "account_id": "acc_magic_1",
                "sender_name": "Sarah Connor",
                "status": "pending",
                "generated_reply": "Sounds great, let's meet Tuesday!",
                "execution_state_id": "exec_m_1"
            }]
        )

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {
                    "approval_id": "app_magic_1",
                    "workspace_id": "ws_magic",
                    "action": "approve",
                    "exp": datetime.utcnow() + timedelta(hours=24)
                },
                secret,
                algorithm="HS256"
            )
            response = magic_approval_handler(token, confirm=True)
            self.assertEqual(response.status_code, 200)
            mock_enqueue.assert_called_once()

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_magic_approval_rejects_workspace_mismatch(self, mock_svc_factory):
        """Magic link token with mismatched workspace_id is rejected with HTTP 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_factory.return_value = mock_svc

        tables["ai_reply_approvals"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "app_magic_2",
                "workspace_id": "ws_actual_owner",
                "status": "pending",
                "generated_reply": "Hello!"
            }]
        )

        secret = "super_secure_jwt_secret_test_12345"
        with patch.dict(os.environ, {"SUPABASE_JWT_SECRET": secret}):
            token = jwt.encode(
                {
                    "approval_id": "app_magic_2",
                    "workspace_id": "ws_wrong_tenant",
                    "action": "approve",
                    "exp": datetime.utcnow() + timedelta(hours=24)
                },
                secret,
                algorithm="HS256"
            )
            response = magic_approval_handler(token)
            self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
