"""
Three-Layer Paranoia Framework Unit Test Suite — Step 33 Track B:
Extension Heartbeat Stale Session, Concurrent Tab Action Lock & Zombie Lease Guard
"""
import os
import unittest
from collections import defaultdict
from unittest.mock import MagicMock
from fastapi import HTTPException

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from integrations.backend.routers.extension import (
    extension_heartbeat,
    get_extension_tasks,
    report_task_result,
    clear_extension_tab_locks,
    MIN_SUPPORTED_EXTENSION_VERSION,
)


class TestExtensionConcurrencyAndLeaseGuard(unittest.TestCase):
    def setUp(self):
        clear_extension_tab_locks()
        self.workspace_id = "ws_ext_test"

    def tearDown(self):
        clear_extension_tab_locks()

    def _setup_multi_table_mock(self):
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    # =========================================================================
    # 1. Heartbeat Version Guard & Concurrent Tab Collision Detection
    # =========================================================================

    def test_heartbeat_outdated_extension_version_returns_upgrade_required(self):
        """Paranoia Layer 2: Outdated Chrome Extension (< 1.2.0) receives upgrade_required directive."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1"}]
        )

        res = extension_heartbeat(
            {"account_id": "acc_1", "extension_version": "1.0.4"},
            self.workspace_id,
            mock_svc,
        )
        self.assertEqual(res["status"], "upgrade_required")
        self.assertEqual(res["min_version"], MIN_SUPPORTED_EXTENSION_VERSION)

        # Supported version succeeds
        res_ok = extension_heartbeat(
            {"account_id": "acc_1", "extension_version": "1.2.5"},
            self.workspace_id,
            mock_svc,
        )
        self.assertEqual(res_ok["status"], "ok")

    def test_heartbeat_concurrent_browser_tabs_collision_and_force_takeover(self):
        """Paranoia Layer 1 & 2: Two browser tabs beating for the same account trigger conflict unless force_takeover=True."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1"}]
        )

        # Tab A acquires lock
        res_a = extension_heartbeat(
            {"account_id": "acc_1", "tab_id": "tab_chrome_profile_1"},
            self.workspace_id,
            mock_svc,
        )
        self.assertEqual(res_a["status"], "ok")

        # Tab B attempts heartbeat within lock TTL -> conflict
        res_b = extension_heartbeat(
            {"account_id": "acc_1", "tab_id": "tab_chrome_profile_2"},
            self.workspace_id,
            mock_svc,
        )
        self.assertEqual(res_b["status"], "conflict")
        self.assertTrue(res_b["concurrent_tab_detected"])
        self.assertEqual(res_b["active_tab_id"], "tab_chrome_profile_1")

        # Tab B explicitly passes force_takeover=True -> succeeds and takes over lock
        res_takeover = extension_heartbeat(
            {"account_id": "acc_1", "tab_id": "tab_chrome_profile_2", "force_takeover": True},
            self.workspace_id,
            mock_svc,
        )
        self.assertEqual(res_takeover["status"], "ok")

    # =========================================================================
    # 2. Task Polling Account Status Guard, Tab Lock & Atomic Lease Token
    # =========================================================================

    def test_get_extension_tasks_halts_on_challenged_or_disconnected_account(self):
        """Paranoia Layer 1: Polling tasks for a CHALLENGE_REQUIRED or DISCONNECTED account returns empty halted response."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1", "status": "CHALLENGE_REQUIRED"}]
        )

        res = get_extension_tasks("acc_1", workspace_id=self.workspace_id, supabase=mock_svc)
        self.assertEqual(res["tasks"], [])
        self.assertTrue(res["account_halted"])
        self.assertIn("CHALLENGE_REQUIRED", res["reason"])

    def test_get_extension_tasks_blocks_secondary_browser_tab(self):
        """Paranoia Layer 2: Secondary browser tab polling for tasks while primary tab holds lock is blocked."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1", "status": "ACTIVE"}]
        )

        # Primary tab registers via heartbeat
        extension_heartbeat({"account_id": "acc_1", "tab_id": "tab_primary"}, self.workspace_id, mock_svc)

        # Secondary tab tries to poll tasks
        res = get_extension_tasks(
            "acc_1", tab_id="tab_secondary", workspace_id=self.workspace_id, supabase=mock_svc
        )
        self.assertEqual(res["tasks"], [])
        self.assertTrue(res["concurrent_tab_blocked"])
        self.assertEqual(res["active_tab_id"], "tab_primary")

    def test_get_extension_tasks_issues_atomic_lease_token(self):
        """Paranoia Layer 0 & 1: Claiming a pending task issues a unique lease_token and lease_expires_at."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1", "status": "ACTIVE"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_1"}]
        )
        tables["campaign_execution_states"].select.return_value.eq.return_value.eq.return_value.lte.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "state_99",
                "current_node_id": "n1",
                "campaign_enrollments": {
                    "campaign_id": "camp_1",
                    "leads": {"linkedin_url": "https://www.linkedin.com/in/alice", "first_name": "Alice"}
                }
            }]
        )
        tables["campaign_execution_states"].update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "state_99", "status": "running"}]
        )

        res = get_extension_tasks("acc_1", tab_id="tab_primary", workspace_id=self.workspace_id, supabase=mock_svc)
        self.assertEqual(len(res["tasks"]), 1)
        task = res["tasks"][0]
        self.assertEqual(task["task_id"], "state_99")
        self.assertTrue(task["lease_token"].startswith("ext_"))
        self.assertIsNotNone(task["lease_expires_at"])

    # =========================================================================
    # 3. Task Result Reporting: Idempotency, Zombie Lease Guard & Challenge Halt
    # =========================================================================

    def test_report_task_result_idempotent_on_already_completed_task(self):
        """Paranoia Layer 1 & 2: Duplicate result reports for an already-completed task return idempotent success without duplicate logs."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaign_execution_states"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": self.workspace_id, "status": "completed", "lease_token": None}]
        )

        res = report_task_result("state_99", {"status": "success"}, self.workspace_id, mock_svc)
        self.assertEqual(res["status"], "already_completed")
        self.assertTrue(res["idempotent"])
        tables["action_log"].insert.assert_not_called()

    def test_report_task_result_ignores_zombie_report_on_paused_or_cancelled_task(self):
        """Paranoia Layer 2: Zombie extension tab reporting result after campaign was paused does not overwrite paused state."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaign_execution_states"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": self.workspace_id, "status": "paused", "lease_token": None}]
        )

        res = report_task_result("state_99", {"status": "success"}, self.workspace_id, mock_svc)
        self.assertEqual(res["status"], "ignored_terminal_state")
        self.assertEqual(res["current_status"], "paused")
        tables["campaign_execution_states"].update.assert_not_called()

    def test_report_task_result_rejects_mismatched_zombie_lease_token_409(self):
        """Paranoia Layer 1 & 2: Stale tab reporting with an outdated lease_token raises HTTP 409 Conflict."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaign_execution_states"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "workspace_id": self.workspace_id,
                "status": "running",
                "lease_token": "ext_current_owner_token",
            }]
        )

        with self.assertRaises(HTTPException) as ctx:
            report_task_result(
                "state_99",
                {"status": "success", "lease_token": "ext_stale_zombie_token"},
                self.workspace_id,
                mock_svc,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Stale or mismatched task lease token", ctx.exception.detail)

    def test_report_task_result_auto_pauses_and_alerts_on_security_challenge(self):
        """Paranoia Layer 1 & 2: Reporting a checkpoint/CAPTCHA error pauses execution state and queues an in-app outbox alert."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaign_execution_states"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "workspace_id": self.workspace_id,
                "status": "running",
                "lease_token": "ext_valid_token",
            }]
        )

        res = report_task_result(
            "state_challenge_1",
            {
                "status": "error",
                "lease_token": "ext_valid_token",
                "error_detail": "Redirected to /checkpoint/challenge CAPTCHA verification page",
            },
            self.workspace_id,
            mock_svc,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["task_status"], "paused")

        update_payload = tables["campaign_execution_states"].update.call_args[0][0]
        self.assertEqual(update_payload["status"], "paused")
        self.assertIn("Security challenge detected by extension", update_payload["error_reason"])
        self.assertIsNone(update_payload["lease_token"])

        tables["outbox_events"].insert.assert_called_once()
        outbox_payload = tables["outbox_events"].insert.call_args[0][0]
        self.assertEqual(outbox_payload["event_type"], "notification.in_app")
        self.assertIn("Security Challenge Detected", outbox_payload["payload"]["title"])


if __name__ == "__main__":
    unittest.main()
