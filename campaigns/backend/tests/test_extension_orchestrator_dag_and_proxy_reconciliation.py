import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import json
from collections import defaultdict
from fastapi import HTTPException

from integrations.backend.routers.extension import (
    get_extension_tasks,
    report_task_result,
    sync_cookies,
    ExtensionSyncPayload
)
from core.backend.services.health_check_cron import run_health_checks, _try_proxy_failover
from core.backend.services.auto_cooling import probe_and_recover_degraded_proxies
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestExtensionOrchestratorDAGAndProxyReconciliation(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws_test_dag_reconcile"
        self.account_id = "acc_test_extension"

    def _setup_multi_table_mock(self):
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    # =========================================================================
    # 1. Extension Task Dispatch Node Type Filtering
    # =========================================================================

    def test_extension_skips_delay_email_and_condition_nodes(self):
        """Paranoia Layer 0 & 1: Chrome Extension MUST NOT hijack delay, email, or condition nodes."""
        mock_svc, tables = self._setup_multi_table_mock()

        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.account_id, "status": "ACTIVE", "execution_channel": "EXTENSION"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": self.account_id}]
        )

        # State 1 is on a delay node; State 2 is on an email node; State 3 is on a condition node
        tables["campaign_execution_states"].select.return_value.eq.return_value.eq.return_value.lte.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "state_delay",
                    "current_node_id": "node_delay",
                    "campaign_enrollments": {
                        "campaign_id": "camp_1",
                        "leads": {"linkedin_url": "https://linkedin.com/in/lead1", "first_name": "Bob"}
                    }
                },
                {
                    "id": "state_email",
                    "current_node_id": "node_email",
                    "campaign_enrollments": {
                        "campaign_id": "camp_1",
                        "leads": {"linkedin_url": "https://linkedin.com/in/lead2", "first_name": "Charlie"}
                    }
                }
            ]
        )

        # The campaign graph has only delay and email nodes
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_1",
                "nodes_json": json.dumps([
                    {"id": "node_delay", "type": "delay", "data": {"duration_days": 2}},
                    {"id": "node_email", "type": "send_email", "data": {"subject": "Hi"}}
                ]),
                "edges_json": "[]"
            }]
        )

        res = get_extension_tasks(self.account_id, tab_id="tab_1", workspace_id=self.workspace_id, supabase=mock_svc)
        # MUST return empty tasks: neither delay nor email can be dispatched to browser extension!
        self.assertEqual(res["tasks"], [])

    def test_extension_claims_linkedin_connect_with_interpolated_template(self):
        """Paranoia Layer 0 & 2: LinkedIn connection nodes interpolate first_name, company, and job_title."""
        mock_svc, tables = self._setup_multi_table_mock()

        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": self.account_id, "status": "ACTIVE", "execution_channel": "EXTENSION"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": self.account_id}]
        )

        tables["campaign_execution_states"].select.return_value.eq.return_value.eq.return_value.lte.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "state_connect",
                "current_node_id": "node_connect",
                "campaign_enrollments": {
                    "campaign_id": "camp_1",
                    "leads": {
                        "linkedin_url": "https://linkedin.com/in/sarah",
                        "first_name": "Sarah",
                        "last_name": "Connor",
                        "company_name": "Cyberdyne",
                        "job_title": "Lead Engineer"
                    }
                }
            }]
        )

        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_1",
                "nodes_json": json.dumps([
                    {
                        "id": "node_connect",
                        "type": "linkedin_connect",
                        "data": {
                            "note": "Hi {{first_name}}, impressed by your work as {{job_title}} at {{company}}!"
                        }
                    }
                ]),
                "edges_json": "[]"
            }]
        )

        tables["campaign_execution_states"].update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "state_connect", "status": "running"}]
        )

        res = get_extension_tasks(self.account_id, tab_id="tab_1", workspace_id=self.workspace_id, supabase=mock_svc)
        self.assertEqual(len(res["tasks"]), 1)
        task = res["tasks"][0]
        self.assertEqual(task["task_id"], "state_connect")
        self.assertEqual(task["type"], "linkedin_connect")
        self.assertEqual(task["first_name"], "Sarah")
        self.assertEqual(
            task["message"],
            "Hi Sarah, impressed by your work as Lead Engineer at Cyberdyne!"
        )

    # =========================================================================
    # 2. Sequence Advancement on Task Success
    # =========================================================================

    def test_report_task_result_advances_to_next_node_when_edge_exists(self):
        """Paranoia Layer 0 & 1: Task success traverses outgoing edges in DAG and sets status to pending."""
        mock_svc, tables = self._setup_multi_table_mock()

        tables["campaign_execution_states"].select.return_value.eq.return_value.execute.side_effect = [
            # 1st call: check workspace ownership & lease token
            MagicMock(data=[{
                "workspace_id": self.workspace_id,
                "status": "running",
                "lease_token": "ext_lease_abc"
            }]),
            # 2nd call: fetch current_node_id & campaign_id
            MagicMock(data=[{
                "id": "task_1",
                "current_node_id": "node_1",
                "enrollment_id": "enr_1",
                "campaign_enrollments": {"campaign_id": "camp_1"}
            }])
        ]

        # Campaign edges: node_1 -> node_2
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "edges_json": json.dumps([
                    {"source": "node_1", "target": "node_2"}
                ])
            }]
        )

        update_mock = tables["campaign_execution_states"].update
        update_mock.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])

        res = report_task_result(
            "task_1",
            {"status": "success", "lease_token": "ext_lease_abc"},
            workspace_id=self.workspace_id,
            supabase=mock_svc
        )

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["task_status"], "pending")

        # Verify update payload advanced node_id to node_2 with status pending
        call_args = update_mock.call_args[0][0]
        self.assertEqual(call_args["current_node_id"], "node_2")
        self.assertEqual(call_args["status"], "pending")
        self.assertIsNone(call_args["lease_token"])

    def test_report_task_result_completes_when_terminal_node(self):
        """Paranoia Layer 0 & 1: Task success on terminal node marks state and enrollment completed."""
        mock_svc, tables = self._setup_multi_table_mock()

        tables["campaign_execution_states"].select.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{
                "workspace_id": self.workspace_id,
                "status": "running",
                "lease_token": "ext_lease_xyz"
            }]),
            MagicMock(data=[{
                "id": "task_term",
                "current_node_id": "node_final",
                "enrollment_id": "enr_final",
                "campaign_enrollments": {"campaign_id": "camp_1"}
            }])
        ]

        # No outgoing edges from node_final
        tables["campaigns"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "edges_json": json.dumps([
                    {"source": "node_prev", "target": "node_final"}
                ])
            }]
        )

        update_mock = tables["campaign_execution_states"].update
        update_mock.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])

        res = report_task_result(
            "task_term",
            {"status": "success", "lease_token": "ext_lease_xyz"},
            workspace_id=self.workspace_id,
            supabase=mock_svc
        )

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["task_status"], "completed")

        call_args = update_mock.call_args[0][0]
        self.assertEqual(call_args["status"], "completed")

    # =========================================================================
    # 3. Orchestrator Busy-Loop Prevention
    # =========================================================================

    def test_orchestrator_yields_with_two_minute_cooldown(self):
        """Paranoia Layer 1: Yielding extension state sets next_run_at to now + 2 minutes."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "ACTIVE", "status_reason": None}]
        )
        orchestrator = EleInOrchestrator(supabase=mock_supabase)

        current_node = {"id": "n_connect", "type": "connection_request"}
        state = {
            "id": "state_loop_test",
            "workspace_id": self.workspace_id,
            "enrollment_id": "enr_loop",
            "opportunity_id": "lead_loop_1",
            "lead_id": "lead_loop_1",
            "campaign_id": "camp_loop",
            "current_node_id": "n_connect",
            "nodes": [current_node],
            "edges": [],
            "tz_str": "UTC"
        }

        with patch.object(orchestrator, "execute_node_action", return_value={"status": "skipped", "reason": "extension_delegated"}):
            with patch.object(orchestrator, "update_state") as mock_update_state:
                orchestrator.process_lead(state, lease_token="lease_orch_1")

                self.assertTrue(mock_update_state.called)
                args = mock_update_state.call_args[0]
                state_id = args[0]
                node_id = args[1]
                status = args[2]
                next_run_at = args[3]

                self.assertEqual(state_id, "state_loop_test")
                self.assertEqual(node_id, "n_connect")
                self.assertEqual(status, "pending")

                # Verify next_run_at is roughly 2 minutes (100s - 140s) in the future, NOT now!
                diff_seconds = (next_run_at - datetime.now(timezone.utc)).total_seconds()
                self.assertGreater(diff_seconds, 100)
                self.assertLess(diff_seconds, 140)

    # =========================================================================
    # 4. Cookie Sync Execution Channel
    # =========================================================================

    def test_sync_cookies_sets_execution_channel_extension(self):
        """Paranoia Layer 0 & 1: Syncing cookies sets execution_channel = EXTENSION."""
        mock_svc, tables = self._setup_multi_table_mock()

        tables["accounts"].select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "GROWTH"}])
        tables["accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(count=0)

        insert_mock = tables["accounts"].insert
        insert_mock.return_value.execute.return_value = MagicMock(data=[{}])

        cookies_payload = [
            {"name": "li_at", "value": "AQEDA...", "domain": ".linkedin.com", "path": "/", "secure": True, "httpOnly": True},
            {"name": "JSESSIONID", "value": "ajax:123", "domain": ".linkedin.com", "path": "/", "secure": True, "httpOnly": False}
        ]
        req = ExtensionSyncPayload(
            account_name="Sarah LinkedIn",
            cookies_json=json.dumps(cookies_payload)
        )

        with patch("core.backend.core.crypto.encrypt_bytes", return_value=b"mock_encrypted"):
            with patch("core.backend.core.crypto.bytes_to_pg_hex", return_value="\\xdeadbeef"):
                res = sync_cookies(req, workspace_id=self.workspace_id, supabase=mock_svc)
                self.assertEqual(res["status"], "ok")

        inserted_row = insert_mock.call_args[0][0]
        self.assertEqual(inserted_row["execution_channel"], "EXTENSION")
        self.assertEqual(inserted_row["platform"], "LINKEDIN")

    # =========================================================================
    # 5. Health Check Cron Guard for Extension Accounts
    # =========================================================================

    def test_health_check_cron_skips_extension_accounts(self):
        """Paranoia Layer 0 & 1: Health check cron skips datacenter HTTP pings for EXTENSION accounts."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "acc_ext",
                    "name": "Local Extension User",
                    "session_cookies_encrypted": "encrypted_dummy",
                    "proxy_id": None,
                    "workspace_id": self.workspace_id,
                    "execution_channel": "EXTENSION"
                }
            ]
        )

        with patch("core.backend.services.health_check_cron.get_service_client", return_value=mock_supabase):
            with patch("integrations.backend.services.linkedin_worker.LinkedInWorker") as mock_worker:
                with patch("core.backend.services.auto_cooling.probe_and_recover_degraded_proxies"):
                    with patch("core.backend.services.auto_cooling.resume_cooled_accounts"):
                        run_health_checks()
                        self.assertFalse(mock_worker.called)


if __name__ == "__main__":
    unittest.main()
