import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, ANY

from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestAccountFailover(unittest.TestCase):
    def setUp(self):
        self.supabase = MagicMock()
        # Default mock rpc
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data={"success": True})
        self.supabase.rpc.return_value = rpc_mock
        self.orchestrator = EleInOrchestrator(supabase=self.supabase)

    def test_account_disconnected_with_healthy_backup(self):
        """When an account disconnects mid-flight and a healthy backup exists:
        - Account marked DISCONNECTED with status_changed_at.
        - Enrollment account_id reassigned to backup account.
        - State rescheduled with pending + 30s jitter.
        - No in-app alert queued.
        """
        table_mock = MagicMock()
        self.supabase.table = table_mock

        # Setup table mocks
        accounts_table = MagicMock()
        enrollments_table = MagicMock()
        camp_accounts_table = MagicMock()
        events_table = MagicMock()
        outbox_table = MagicMock()

        def table_side_effect(tbl_name):
            if tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "campaign_enrollments":
                return enrollments_table
            elif tbl_name == "campaign_accounts":
                return camp_accounts_table
            elif tbl_name == "campaign_events":
                return events_table
            elif tbl_name == "outbox_events":
                return outbox_table
            elif tbl_name == "campaigns":
                camp_mock = MagicMock()
                camp_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "ACTIVE"}])
                return camp_mock
            return MagicMock()

        table_mock.side_effect = table_side_effect

        # Backup account query returns an active account
        camp_accounts_table.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_backup_123"}]
        )

        state = {
            "id": "state_101",
            "current_node_id": "node_send_1",
            "nodes": [{"id": "node_send_1", "node_type": "send_message", "config": {}}],
            "edges": [],
            "account_id": "acc_primary",
            "campaign_id": "camp_1",
            "enrollment_id": "enroll_1",
            "workspace_id": "ws_1",
            "opportunity_id": "opp_1",
        }

        with patch.object(self.orchestrator, "execute_node_action", return_value={"status": "account_disconnected"}), \
             patch.object(self.orchestrator, "update_state") as mock_update_state:
            self.orchestrator.process_lead(state, lease_token="lease_abc")

            # 1. Accounts table updated with DISCONNECTED and status_changed_at
            accounts_table.update.assert_called()
            update_arg = accounts_table.update.call_args[0][0]
            self.assertEqual(update_arg["status"], "DISCONNECTED")
            self.assertIn("status_changed_at", update_arg)

            # 2. Campaign enrollment updated with new backup account
            enrollments_table.update.assert_called_with({"account_id": "acc_backup_123"})

            # 3. State rescheduled to pending with ~30s jitter
            mock_update_state.assert_called_once()
            call_args = mock_update_state.call_args
            self.assertEqual(call_args[0][0], "state_101")
            self.assertEqual(call_args[0][1], "node_send_1")
            self.assertEqual(call_args[0][2], "pending")
            next_run = call_args[0][3]
            self.assertIsNotNone(next_run)
            now_utc = datetime.now(timezone.utc)
            if next_run.tzinfo is None:
                diff_sec = (next_run - datetime.utcnow()).total_seconds()
            else:
                diff_sec = (next_run - now_utc).total_seconds()
            self.assertAlmostEqual(diff_sec, 30, delta=5)

            # 4. Outbox events should NOT have been queued since failover succeeded
            outbox_table.insert.assert_not_called()

    def test_account_disconnected_without_backup(self):
        """When an account disconnects mid-flight and NO backup exists:
        - Account marked DISCONNECTED with status_changed_at.
        - State updated to paused (next_run_at=None).
        - In-app notification queued in outbox_events.
        """
        table_mock = MagicMock()
        self.supabase.table = table_mock

        accounts_table = MagicMock()
        enrollments_table = MagicMock()
        camp_accounts_table = MagicMock()
        events_table = MagicMock()
        outbox_table = MagicMock()

        def table_side_effect(tbl_name):
            if tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "campaign_enrollments":
                return enrollments_table
            elif tbl_name == "campaign_accounts":
                return camp_accounts_table
            elif tbl_name == "campaign_events":
                return events_table
            elif tbl_name == "outbox_events":
                return outbox_table
            elif tbl_name == "campaigns":
                camp_mock = MagicMock()
                camp_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "ACTIVE"}])
                return camp_mock
            return MagicMock()

        table_mock.side_effect = table_side_effect

        # Accounts table select returns account name
        accounts_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"name": "Alice LinkedIn"}]
        )

        # No backup accounts available
        camp_accounts_table.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        state = {
            "id": "state_202",
            "current_node_id": "node_send_2",
            "nodes": [{"id": "node_send_2", "node_type": "send_message", "config": {}}],
            "edges": [],
            "account_id": "acc_broken",
            "campaign_id": "camp_2",
            "enrollment_id": "enroll_2",
            "workspace_id": "ws_test_2",
            "opportunity_id": "opp_2",
        }

        with patch.object(self.orchestrator, "execute_node_action", return_value={"status": "account_disconnected"}), \
             patch.object(self.orchestrator, "update_state") as mock_update_state:
            self.orchestrator.process_lead(state, lease_token="lease_xyz")

            # 1. Accounts table updated to DISCONNECTED
            accounts_table.update.assert_called()
            update_arg = accounts_table.update.call_args[0][0]
            self.assertEqual(update_arg["status"], "DISCONNECTED")
            self.assertIn("status_changed_at", update_arg)

            # 2. State paused with next_run_at=None (no spin loop!)
            mock_update_state.assert_called_once()
            call_args = mock_update_state.call_args
            self.assertEqual(call_args[0][0], "state_202")
            self.assertEqual(call_args[0][1], "node_send_2")
            self.assertEqual(call_args[0][2], "paused")
            self.assertIsNone(call_args[0][3])

            # 3. In-app alert queued via outbox_events
            outbox_table.insert.assert_called_once()
            insert_arg = outbox_table.insert.call_args[0][0]
            self.assertEqual(insert_arg["workspace_id"], "ws_test_2")
            self.assertEqual(insert_arg["event_type"], "notification.in_app")
            self.assertIn("Disconnected", insert_arg["payload"]["title"])
            self.assertIn("Alice LinkedIn", insert_arg["payload"]["message"])

    def test_execute_node_action_instant_failover_disconnected(self):
        """In execute_node_action, DISCONNECTED accounts immediately fail over without waiting 48h."""
        table_mock = MagicMock()
        self.supabase.table = table_mock

        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "opp_1", "first_name": "Bob", "linkedin_url": "https://linkedin.com/in/bob"}]
        )

        accounts_table = MagicMock()
        # Account was disconnected just 5 minutes ago (now - 5 min)
        recent_disconnect = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        accounts_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "acc_disc",
                "workspace_id": "ws_1",
                "status": "DISCONNECTED",
                "status_changed_at": recent_disconnect,
                "proxy_id": None,
                "proxies": None,
                "session_cookies_encrypted": None,
                "is_warmup": False,
                "warmup_max_connections": 20,
                "warmup_max_messages": 20
            }]
        )

        camp_accounts_table = MagicMock()
        camp_accounts_table.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_healthy_backup"}]
        )

        enrollments_table = MagicMock()

        def table_side_effect(tbl_name):
            if tbl_name == "leads":
                return leads_table
            elif tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "campaign_accounts":
                return camp_accounts_table
            elif tbl_name == "campaign_enrollments":
                return enrollments_table
            return MagicMock()

        table_mock.side_effect = table_side_effect

        state = {
            "id": "state_1",
            "campaign_id": "camp_1",
            "enrollment_id": "enroll_1",
            "workspace_id": "ws_1",
            "opportunity_id": "opp_1"
        }

        with patch("campaigns.backend.services.elein_orchestrator.try_acquire_session_lock", return_value=True), \
             patch("campaigns.backend.services.sender_pod_service.select_pod_sender", return_value={"account_id": "acc_disc"}):
            res = self.orchestrator.execute_node_action(
                action="send_message",
                data={"body": "Hello"},
                opportunity_id="opp_1",
                account_id="acc_disc",
                state=state,
                lease_token="lease_1",
                current_node_id="node_1"
            )

            # Reassignment happens immediately without waiting 48 hours
            self.assertEqual(res.get("status"), "skipped")
            enrollments_table.update.assert_called_with({"account_id": "acc_healthy_backup"})
            self.assertEqual(state["account_id"], "acc_healthy_backup")

    def test_execute_node_action_disconnected_without_backup_returns_account_disconnected(self):
        """In execute_node_action, when DISCONNECTED and no backup exists, returns account_disconnected."""
        table_mock = MagicMock()
        self.supabase.table = table_mock

        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "opp_1", "first_name": "Bob", "linkedin_url": "https://linkedin.com/in/bob"}]
        )

        accounts_table = MagicMock()
        accounts_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "acc_disc",
                "workspace_id": "ws_1",
                "status": "DISCONNECTED",
                "status_changed_at": datetime.utcnow().isoformat(),
                "proxy_id": None,
                "proxies": None,
                "session_cookies_encrypted": None,
                "is_warmup": False,
                "warmup_max_connections": 20,
                "warmup_max_messages": 20
            }]
        )

        camp_accounts_table = MagicMock()
        camp_accounts_table.select.return_value.eq.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        def table_side_effect(tbl_name):
            if tbl_name == "leads":
                return leads_table
            elif tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "campaign_accounts":
                return camp_accounts_table
            return MagicMock()

        table_mock.side_effect = table_side_effect

        state = {
            "id": "state_1",
            "campaign_id": "camp_1",
            "enrollment_id": "enroll_1",
            "workspace_id": "ws_1",
            "opportunity_id": "opp_1"
        }

        with patch("campaigns.backend.services.elein_orchestrator.try_acquire_session_lock", return_value=True), \
             patch("campaigns.backend.services.sender_pod_service.select_pod_sender", return_value={"account_id": "acc_disc"}):
            res = self.orchestrator.execute_node_action(
                action="send_message",
                data={"body": "Hello"},
                opportunity_id="opp_1",
                account_id="acc_disc",
                state=state,
                lease_token="lease_1",
                current_node_id="node_1"
            )

            # Returns account_disconnected so process_lead pauses and alerts via outbox
            self.assertEqual(res.get("status"), "account_disconnected")

    @patch("campaigns.backend.services.elein_orchestrator.LinkedInWorker")
    @patch("core.backend.core.crypto.decrypt_bytes")
    def test_execute_node_action_configured_proxy_unavailable_halts_safely(self, mock_decrypt_bytes, mock_worker_cls):
        """Paranoia Layer 1: When account has proxy_id configured but _build_proxy_url is None, halts outreach without launching worker."""
        table_mock = MagicMock()
        self.supabase.table = table_mock

        leads_table = MagicMock()
        leads_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "opp_1", "first_name": "Bob", "linkedin_url": "https://linkedin.com/in/bob"}]
        )

        accounts_table = MagicMock()
        accounts_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "acc_with_dead_proxy",
                "workspace_id": "ws_1",
                "status": "ACTIVE",
                "proxy_id": "proxy_dead",
                "proxies": {"id": "proxy_dead", "status": "quarantined", "is_active": False},
                "session_cookies_encrypted": "hex_cookies",
                "is_warmup": False,
                "warmup_max_connections": 20,
                "warmup_max_messages": 20
            }]
        )

        def table_side_effect(tbl_name):
            if tbl_name == "leads":
                return leads_table
            elif tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "account_health_checks":
                return MagicMock()
            return MagicMock()

        table_mock.side_effect = table_side_effect
        mock_decrypt_bytes.return_value = b'[{"name": "li_at", "value": "xyz"}]'

        state = {
            "id": "state_1",
            "campaign_id": "camp_1",
            "enrollment_id": "enroll_1",
            "workspace_id": "ws_1",
            "opportunity_id": "opp_1"
        }

        with patch("campaigns.backend.services.elein_orchestrator.try_acquire_session_lock", return_value=True), \
             patch("campaigns.backend.services.elein_orchestrator._build_proxy_url", return_value=None), \
             patch("campaigns.backend.services.sender_pod_service.select_pod_sender", return_value={"account_id": "acc_with_dead_proxy"}):
            res = self.orchestrator.execute_node_action(
                action="send_message",
                data={"body": "Hello"},
                opportunity_id="opp_1",
                account_id="acc_with_dead_proxy",
                state=state,
                lease_token="lease_1",
                current_node_id="node_1"
            )

            # Execution halts cleanly with account_disconnected / PROXY_UNAVAILABLE
            self.assertEqual(res.get("status"), "account_disconnected")
            self.assertEqual(res.get("reason"), "PROXY_UNAVAILABLE")
            # LinkedInWorker is NEVER instantiated on bare datacenter IP
            mock_worker_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
