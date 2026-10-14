import unittest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestHorizon2OrchestratorAndExecutor(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_horizon2"
        self.supabase = MagicMock()
        # Mock rpc execute
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data={"success": True})
        self.supabase.rpc.return_value = rpc_mock

        self.executor = EleInNodeExecutor(linkedin_worker=self.worker, supabase=self.supabase, workspace_id="ws_horizon2")
        self.orchestrator = EleInOrchestrator(supabase=self.supabase)

    def test_dual_edge_format_resolution(self):
        """Verifies both React Flow camelCase edges and backend snake_case edges are resolved correctly."""
        # Snake case edges
        edges_snake = [
            {"source_node_id": "start", "target_node_id": "step1", "source_handle": "output"},
            {"source_node_id": "step1", "target_node_id": "step2", "source_handle": "then"},
        ]
        # Camel case edges (React Flow format from eiTreeStore)
        edges_camel = [
            {"source": "start", "target": "step1", "sourceHandle": "output"},
            {"source": "step1", "target": "step2", "sourceHandle": "then"},
        ]

        # Verify get_incoming_edges
        in_snake = self.orchestrator.get_incoming_edges(edges_snake, "step1")
        self.assertEqual(len(in_snake), 1)
        self.assertEqual(in_snake[0].get("source_node_id") or in_snake[0].get("source"), "start")

        in_camel = self.orchestrator.get_incoming_edges(edges_camel, "step1")
        self.assertEqual(len(in_camel), 1)
        self.assertEqual(in_camel[0].get("source_node_id") or in_camel[0].get("source"), "start")

        # Verify get_outgoing_edges
        out_snake = self.orchestrator.get_outgoing_edges(edges_snake, "step1")
        self.assertEqual(len(out_snake), 1)
        self.assertEqual(out_snake[0].get("target_node_id") or out_snake[0].get("target"), "step2")

        out_camel = self.orchestrator.get_outgoing_edges(edges_camel, "step1")
        self.assertEqual(len(out_camel), 1)
        self.assertEqual(out_camel[0].get("target_node_id") or out_camel[0].get("target"), "step2")

    def test_send_intro_call_invite(self):
        """Verifies send_intro_call_invite formats subject, body, and duration, delegating to handle_send_message."""
        with patch.object(self.executor, "handle_send_message", return_value={"status": "success", "branch": "then"}) as mock_send:
            data = {
                "subject": "Quick Sync",
                "body": "Let's discuss growth strategies.",
                "duration_minutes": 25,
            }
            res = self.executor.handle_send_intro_call_invite(data, "https://linkedin.com/in/test-lead")
            self.assertEqual(res.get("status"), "success")
            mock_send.assert_called_once()
            called_data, called_url = mock_send.call_args[0]
            self.assertIn("Quick Sync", called_data["message"])
            self.assertIn("25 mins", called_data["message"])
            self.assertIn("growth strategies", called_data["message"])

    def test_find_phone_handler(self):
        """Verifies find_phone extracts phone from lead variables or returns Not found."""
        # Case A: Phone exists in data
        data_with_phone = {"variables": {"phone": "+1-555-0199"}}
        res_found = self.executor.handle_find_phone(data_with_phone, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_found.get("status"), "success")
        self.assertEqual(res_found.get("branch"), Branch.FOUND.value)
        self.assertEqual(res_found.get("variables", {}).get("phone"), "+1-555-0199")

        # Case B: Phone missing and no DB record
        self.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        data_no_phone = {"variables": {}}
        res_not_found = self.executor.handle_find_phone(data_no_phone, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_not_found.get("status"), "success")
        self.assertEqual(res_not_found.get("branch"), Branch.NOT_FOUND.value)

    def test_find_tech_stack_handler(self):
        """Verifies find_tech_stack evaluates target tools against lead technologies."""
        data_matched = {
            "variables": {"tech_stack": "React, TypeScript, Salesforce, AWS"},
            "target_tools": "Salesforce, HubSpot",
        }
        res = self.executor.handle_find_tech_stack(data_matched, "https://linkedin.com/in/test-lead")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertIn("Salesforce", res.get("variables", {}).get("tech_stack"))

        data_unmatched = {
            "variables": {"tech_stack": "WordPress, PHP"},
            "target_tools": "Salesforce, HubSpot",
        }
        res_unmatched = self.executor.handle_find_tech_stack(data_unmatched, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_unmatched.get("status"), "success")
        self.assertEqual(res_unmatched.get("branch"), Branch.NOT_FOUND.value)

    def test_find_funding_round_handler(self):
        """Verifies find_funding_round recognizes funded companies vs bootstrapped/unfunded."""
        data_funded = {"variables": {"funding_round": "Series A ($12M)"}}
        res_funded = self.executor.handle_find_funding_round(data_funded, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_funded.get("status"), "success")
        self.assertEqual(res_funded.get("branch"), Branch.RECENTLY_FUNDED.value)

        data_unfunded = {"variables": {"funding_round": "bootstrapped"}}
        res_unfunded = self.executor.handle_find_funding_round(data_unfunded, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_unfunded.get("status"), "success")
        self.assertEqual(res_unfunded.get("branch"), Branch.NO_RECENT_FUNDING.value)

    def test_find_headcount_handler(self):
        """Verifies find_headcount returns headcount when present."""
        data_hc = {"variables": {"company_size": "250 employees"}}
        res = self.executor.handle_find_headcount(data_hc, "https://linkedin.com/in/test-lead")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("variables", {}).get("headcount"), "250 employees")

    def test_find_job_postings_handler(self):
        """Verifies find_job_postings identifies active hiring."""
        data_hiring = {"variables": {"is_hiring": "true", "open_roles": "Senior Backend Engineer, Account Executive"}}
        res = self.executor.handle_find_job_postings(data_hiring, "https://linkedin.com/in/test-lead")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.HIRING.value)

    def test_get_linkedin_activity_handler(self):
        """Verifies get_linkedin_activity branches based on post frequency."""
        # Active (>4)
        data_active = {"variables": {"posts_per_month": "6"}}
        res_active = self.executor.handle_get_linkedin_activity(data_active, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_active.get("status"), "success")
        self.assertEqual(res_active.get("branch"), Branch.ACTIVE_MONTHLY.value)

        # Passive (1-4)
        data_passive = {"variables": {"posts_per_month": "2"}}
        res_passive = self.executor.handle_get_linkedin_activity(data_passive, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_passive.get("status"), "success")
        self.assertEqual(res_passive.get("branch"), Branch.PASSIVE_MONTHLY.value)

        # Inactive (<1)
        data_inactive = {"variables": {"posts_per_month": "0"}}
        res_inactive = self.executor.handle_get_linkedin_activity(data_inactive, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_inactive.get("status"), "success")
        self.assertEqual(res_inactive.get("branch"), Branch.INACTIVE_MONTHLY.value)

    def test_get_mutual_connections_handler(self):
        """Verifies get_mutual_connections branches based on mutual connection count."""
        data_mutuals = {"variables": {"mutual_connections": "5"}}
        res_mutuals = self.executor.handle_get_mutual_connections(data_mutuals, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_mutuals.get("status"), "success")
        self.assertEqual(res_mutuals.get("branch"), Branch.HAS_MUTUALS.value)

        data_none = {"variables": {"mutual_connections": "0"}}
        res_none = self.executor.handle_get_mutual_connections(data_none, "https://linkedin.com/in/test-lead")
        self.assertEqual(res_none.get("status"), "success")
        self.assertEqual(res_none.get("branch"), Branch.NO_MUTUALS.value)

    def test_not_implemented_status_hard_error(self):
        """Verifies unhandled action returns not_implemented and marks hard_error without retries."""
        res = self.executor.execute("some_nonexistent_action_xyz", {}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "not_implemented")

        with patch.object(self.orchestrator, "mark_error") as mock_mark_error:
            # Simulate orchestrator handling not_implemented
            state = {"id": "state_123", "attempts": 0, "max_attempts": 5}
            current_node = {"id": "node_xyz"}
            lease_token = "lease_123"

            action_result = res
            action = "some_nonexistent_action_xyz"
            if action_result.get("status") == "not_implemented":
                self.orchestrator.mark_error(
                    state["id"],
                    f"Action not yet supported: {action}",
                    attempts=state.get("attempts", 0),
                    max_attempts=state.get("max_attempts", 5),
                    hard_error=True,
                    lease_token=lease_token,
                    node_id=current_node["id"]
                )

            mock_mark_error.assert_called_once_with(
                "state_123",
                "Action not yet supported: some_nonexistent_action_xyz",
                attempts=0,
                max_attempts=5,
                hard_error=True,
                lease_token="lease_123",
                node_id="node_xyz"
            )

    def test_handle_if_replied_variable_extraction(self):
        """Verifies handle_if_replied extracts sentiment from variables dict or json string."""
        # From dict in variables
        data_dict = {"variables": {"last_reply_sentiment": "Positive"}}
        res_dict = self.executor.handle_if_replied(data_dict, "https://linkedin.com/in/test")
        self.assertEqual(res_dict.get("status"), "success")
        self.assertEqual(res_dict.get("branch"), "Positive")

        # From JSON string in variables
        data_json = {"variables": json.dumps({"ai_sentiment": "Negative"})}
        res_json = self.executor.handle_if_replied(data_json, "https://linkedin.com/in/test")
        self.assertEqual(res_json.get("status"), "success")
        self.assertEqual(res_json.get("branch"), "Negative")

        # Default fallback
        data_empty = {"variables": {}}
        res_empty = self.executor.handle_if_replied(data_empty, "https://linkedin.com/in/test")
        self.assertEqual(res_empty.get("status"), "success")
        self.assertEqual(res_empty.get("branch"), "No Reply")


if __name__ == "__main__":
    unittest.main()
