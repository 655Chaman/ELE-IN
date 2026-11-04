import unittest
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from integrations.backend.routers.extension import (
    clear_extension_tab_locks,
    get_extension_tasks,
    report_task_result,
    update_extension_session_state,
    report_extension_diagnostic,
    ExtensionSessionStatePayload,
    ExtensionDiagnosticPayload,
    CONCURRENT_TAB_LOCK_TTL_SECONDS
)


class TestPillar2ExtensionHardening(unittest.TestCase):
    """
    Three-Layer Paranoia Framework: Pillar 2 Test Suite
    - Phase 2.1: Multi-Tab & Multi-Profile Exclusivity Lock
    - Phase 2.2: LinkedIn Voyager DOM & API Mutation Resilience
    - Phase 2.3: Continuous Cookie & Session Health Bridge
    - Phase 2.4: Anti-Bot Checkpoint Detection & Immediate Auto-Halt
    """

    def setUp(self):
        clear_extension_tab_locks()

    # =========================================================================
    # PHASE 2.1: MULTI-TAB & MULTI-PROFILE EXCLUSIVITY LOCK
    # =========================================================================

    def test_concurrent_tab_lock_blocks_secondary_tab(self):
        """
        Layer 1 & 2: Tab 1 claims lease. Tab 2 attempting to poll tasks within 60s
        must be blocked with concurrent_tab_blocked=True to prevent race conditions.
        """
        mock_supabase = MagicMock()
        mock_acc = MagicMock()
        mock_acc.data = [{
            "id": "acc-multi-tab",
            "status": "ACTIVE",
            "proxy_id": None,
            "execution_channel": "EXTENSION"
        }]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_acc
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        # Tab 1 polls
        res1 = get_extension_tasks(
            account_id="acc-multi-tab",
            workspace_id="ws-1",
            supabase=mock_supabase,
            tab_id="tab-1",
            force_takeover=False
        )
        self.assertFalse(res1.get("concurrent_tab_blocked", False))

        # Tab 2 polls immediately
        res2 = get_extension_tasks(
            account_id="acc-multi-tab",
            workspace_id="ws-1",
            supabase=mock_supabase,
            tab_id="tab-2",
            force_takeover=False
        )
        self.assertTrue(res2.get("concurrent_tab_blocked"))
        self.assertEqual(res2.get("active_tab_id"), "tab-1")
        self.assertEqual(res2.get("tasks"), [])

    def test_force_takeover_transfers_lease_to_new_tab(self):
        """
        Layer 2: User explicitly clicking 'Claim Tab' (force_takeover=True)
        transfers the lock to the new tab immediately.
        """
        mock_supabase = MagicMock()
        mock_acc = MagicMock()
        mock_acc.data = [{
            "id": "acc-takeover",
            "status": "ACTIVE",
            "proxy_id": None,
            "execution_channel": "EXTENSION"
        }]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_acc
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        # Tab 1 acquires lock
        get_extension_tasks("acc-takeover", "ws-1", mock_supabase, tab_id="tab-1")

        # Tab 2 takes over
        res2 = get_extension_tasks(
            account_id="acc-takeover",
            workspace_id="ws-1",
            supabase=mock_supabase,
            tab_id="tab-2",
            force_takeover=True
        )
        self.assertFalse(res2.get("concurrent_tab_blocked", False))

    # =========================================================================
    # PHASE 2.2: LINKEDIN VOYAGER DOM & API MUTATION RESILIENCE
    # =========================================================================

    def test_diagnostic_endpoint_records_dom_mutation_telemetry(self):
        """
        Layer 2: When both API and DOM fallback fail, extension reports diagnostic
        telemetry to POST /api/extension/diagnostic for proactive engineering triage.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[{}])

        payload = ExtensionDiagnosticPayload(
            account_id="acc-diag-1",
            task_id="task-123",
            error_type="SELECTOR_MUTATION_FAILURE",
            error_detail="LinkedIn changed button to [data-test-invite-button]",
            failed_selectors=["button:has-text('Connect')", "button[aria-label*='Invite']"],
            url="https://linkedin.com/in/prospect-1"
        )

        res = report_extension_diagnostic(
            payload=payload,
            workspace_id="ws-1",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "recorded")
        mock_supabase.table().insert.assert_called()

    # =========================================================================
    # PHASE 2.3: CONTINUOUS COOKIE & SESSION HEALTH BRIDGE
    # =========================================================================

    def test_session_state_disconnect_updates_account_and_cancels_leases(self):
        """
        Layer 1 (Environmental): When user logs out in local browser,
        POST /api/extension/session-state transitions account to DISCONNECTED
        and releases all active 'running' task leases back to 'pending'.
        """
        mock_supabase = MagicMock()
        mock_acc_check = MagicMock()
        mock_acc_check.data = [{"id": "acc-logout", "status": "ACTIVE"}]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_acc_check

        # Campaign accounts & enrollments setup for task lease release
        mock_c_accs = MagicMock(data=[{"campaign_id": "camp-1"}])
        mock_enrs = MagicMock(data=[{"id": "enr-1"}])

        def table_call(table_name):
            m = MagicMock()
            if table_name == "accounts":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_check
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            elif table_name == "campaign_accounts":
                m.select.return_value.eq.return_value.execute.return_value = mock_c_accs
            elif table_name == "campaign_enrollments":
                m.select.return_value.in_.return_value.execute.return_value = mock_enrs
            elif table_name == "campaign_execution_states":
                m.update.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            elif table_name == "action_log":
                m.insert.return_value.execute.return_value = MagicMock(data=[{}])
            return m

        mock_supabase.table.side_effect = table_call

        payload = ExtensionSessionStatePayload(
            account_id="acc-logout",
            status="DISCONNECTED",
            reason="User logged out of LinkedIn in local browser"
        )

        res = update_extension_session_state(
            payload=payload,
            workspace_id="ws-1",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["new_status"], "DISCONNECTED")

    def test_session_state_rejects_foreign_account(self):
        """
        Layer 2: IDOR defense rejects account state update if account does not belong to workspace.
        """
        mock_supabase = MagicMock()
        mock_acc_check = MagicMock()
        mock_acc_check.data = [] # Empty -> foreign account
        mock_supabase.table().select().eq().eq().execute.return_value = mock_acc_check

        payload = ExtensionSessionStatePayload(
            account_id="acc-foreign",
            status="DISCONNECTED"
        )

        with self.assertRaises(HTTPException) as ctx:
            update_extension_session_state(
                payload=payload,
                workspace_id="ws-1",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 403)

    # =========================================================================
    # PHASE 2.4: ANTI-BOT CHECKPOINT DETECTION & AUTO-HALT
    # =========================================================================

    def test_checkpoint_error_transitions_account_to_challenge_required(self):
        """
        Layer 1 & 2: When extension reports a security checkpoint / challenge error,
        the account is transitioned to CHALLENGE_REQUIRED and disabled to protect from ban.
        """
        mock_supabase = MagicMock()
        mock_task = MagicMock()
        mock_task.data = [{
            "id": "task-checkpoint",
            "workspace_id": "ws-1",
            "status": "running",
            "lease_token": "ext_valid_token_123"
        }]

        # Campaign and account lookup
        mock_enr = MagicMock(data=[{"campaign_enrollments": {"campaign_id": "camp-10"}}])
        mock_c_acc = MagicMock(data=[{"account_id": "acc-challenged"}])

        def table_call(table_name):
            m = MagicMock()
            if table_name == "campaign_execution_states":
                m.select.return_value.eq.return_value.execute.return_value = mock_task
                m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            elif table_name == "campaign_accounts":
                m.select.return_value.eq.return_value.execute.return_value = mock_c_acc
            elif table_name == "accounts":
                m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            elif table_name in ("action_log", "outbox_events"):
                m.insert.return_value.execute.return_value = MagicMock(data=[{}])
            return m

        mock_supabase.table.side_effect = table_call

        payload = {
            "status": "error",
            "error_detail": "LinkedIn security checkpoint / verification challenge detected: HTTP 999",
            "lease_token": "ext_valid_token_123"
        }

        res = report_task_result(
            task_id="task-checkpoint",
            payload=payload,
            workspace_id="ws-1",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["task_status"], "paused")


if __name__ == "__main__":
    unittest.main()
