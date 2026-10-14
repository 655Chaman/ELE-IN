import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException
from campaigns.backend.routers.elein import (
    run_campaign_preflight_audit,
    PreflightValidateRequest,
    post_campaign_preflight
)

class TestPreflightGate(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-test-123"
        self.client = MagicMock()

    def test_preflight_valid_campaign(self):
        """A complete, healthy campaign passes preflight with 100 clearance score."""
        nodes = [
            {"id": "n1", "type": "sequence_start", "data": {}},
            {"id": "n2", "type": "connection_request", "data": {"note": "Hi {{first_name|there}}, saw your work at {{company|your company}}."}},
            {"id": "n3", "type": "send_message", "data": {"delay": 2, "body": "Following up on my note!"}}
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"}
        ]
        sender_ids = ["acc-1"]

        # Mock accounts query
        acc_mock = MagicMock(data=[{
            "id": "acc-1",
            "name": "Alex Sender",
            "status": "ACTIVE",
            "is_active": True,
            "proxy_id": "proxy-1",
            "is_warmup": False,
            "daily_connection_limit": 25,
            "daily_message_limit": 50
        }])

        # Mock lead list query
        list_mock = MagicMock(data=[{
            "id": "list-1",
            "name": "Target Tech Leads",
            "row_count": 100
        }])

        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.in_.return_value.eq.return_value.execute.return_value = acc_mock
        table_mock.select.return_value.eq.return_value.execute.return_value = list_mock

        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Q4 SaaS Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=sender_ids,
            lead_list_id="list-1",
            stop_on_reply=True
        )

        self.assertTrue(res["can_launch"])
        self.assertTrue(res["passed"])
        self.assertEqual(res["score"], 100)
        self.assertEqual(len(res["critical_errors"]), 0)
        self.assertEqual(len(res["checks"]), 5)
        # Check sample previews were generated
        self.assertGreater(len(res["sample_previews"]), 0)

    def test_preflight_empty_sequence_blocked(self):
        """An empty sequence fails preflight and blocks launch."""
        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Empty Sequence",
            nodes_raw=[],
            edges_raw=[],
            sender_ids=["acc-1"],
            lead_list_id="list-1"
        )

        self.assertFalse(res["can_launch"])
        self.assertIn("Sequence contains 0 steps", res["critical_errors"][0])

    def test_preflight_cycle_detected_blocked(self):
        """A sequence with a loop is blocked from launching."""
        nodes = [
            {"id": "n1", "type": "send_message", "data": {"body": "Msg 1"}},
            {"id": "n2", "type": "send_message", "data": {"body": "Msg 2"}}
        ]
        edges = [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n1"}  # Loop
        ]

        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Looped Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=["acc-1"],
            lead_list_id="list-1"
        )

        self.assertFalse(res["can_launch"])
        self.assertTrue(any("cycle" in err.lower() for err in res["critical_errors"]))

    def test_preflight_invalid_variable_blocked(self):
        """A sequence with an illegal variable like {{bad_var}} is flagged as critical error."""
        nodes = [
            {"id": "n1", "type": "connection_request", "data": {"note": "Hi {{bad_var}}, check this out."}}
        ]
        edges = []

        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Bad Var Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=["acc-1"],
            lead_list_id="list-1"
        )

        self.assertFalse(res["can_launch"])
        self.assertTrue(any("Invalid template variables detected" in err for err in res["critical_errors"]))

    def test_preflight_unprotected_variable_warns(self):
        """A variable without fallback like {{first_name}} is flagged as a warning, not a hard launch block."""
        nodes = [
            {"id": "n1", "type": "connection_request", "data": {"note": "Hi {{first_name}}, let's connect."}}
        ]
        edges = []

        # Mock active account
        acc_mock = MagicMock(data=[{
            "id": "acc-1", "name": "Sender", "status": "ACTIVE", "is_active": True,
            "daily_connection_limit": 20, "daily_message_limit": 40
        }])
        list_mock = MagicMock(data=[{"id": "list-1", "row_count": 50}])

        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.in_.return_value.eq.return_value.execute.return_value = acc_mock
        table_mock.select.return_value.eq.return_value.execute.return_value = list_mock

        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Unprotected Var Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=["acc-1"],
            lead_list_id="list-1"
        )

        self.assertTrue(res["can_launch"])  # Allowed to launch with warning
        self.assertTrue(any("Variables without fallback" in w for w in res["warnings"]))

    def test_preflight_single_brace_typo_warns(self):
        """A single brace variable like {first_name} is detected and flagged as a typo warning."""
        nodes = [
            {"id": "n1", "type": "send_message", "data": {"body": "Hi {first_name}, how are you?"}}
        ]
        edges = []

        acc_mock = MagicMock(data=[{"id": "acc-1", "status": "ACTIVE", "is_active": True}])
        list_mock = MagicMock(data=[{"id": "list-1", "row_count": 50}])

        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.in_.return_value.eq.return_value.execute.return_value = acc_mock
        table_mock.select.return_value.eq.return_value.execute.return_value = list_mock

        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Single Brace Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=["acc-1"],
            lead_list_id="list-1"
        )

        self.assertTrue(any("Potential variable typo" in w for w in res["warnings"]))

    def test_preflight_no_senders_blocked(self):
        """A campaign with no senders assigned is hard-blocked."""
        nodes = [{"id": "n1", "type": "connection_request", "data": {"note": "Hi!"}}]
        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="No Senders",
            nodes_raw=nodes,
            edges_raw=[],
            sender_ids=[],
            lead_list_id="list-1"
        )

        self.assertFalse(res["can_launch"])
        self.assertTrue(any("No LinkedIn sender accounts assigned" in err for err in res["critical_errors"]))

    def test_preflight_warmup_pacing_calculation(self):
        """Accounts in warmup mode correctly calculate ramp pacing and estimated days."""
        nodes = [{"id": "n1", "type": "connection_request", "data": {"note": "Hi {{first_name|there}}!"}}]
        acc_mock = MagicMock(data=[{
            "id": "acc-1",
            "name": "New Account",
            "status": "ACTIVE",
            "is_active": True,
            "is_warmup": True,
            "warmup_start_date": "2026-10-01T00:00:00Z",
            "daily_connection_limit": 30,
            "daily_message_limit": 60
        }])
        list_mock = MagicMock(data=[{"id": "list-1", "row_count": 100}])

        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.in_.return_value.eq.return_value.execute.return_value = acc_mock
        table_mock.select.return_value.eq.return_value.execute.return_value = list_mock

        res = run_campaign_preflight_audit(
            supabase=self.client,
            workspace_id=self.workspace_id,
            campaign_name="Warmup Campaign",
            nodes_raw=nodes,
            edges_raw=[],
            sender_ids=["acc-1"],
            lead_list_id="list-1"
        )

        warmup_check = next(c for c in res["checks"] if c["id"] == "warmup")
        self.assertEqual(warmup_check["warmup_accounts_count"], 1)
        self.assertGreater(warmup_check["estimated_days"], 0)
        self.assertTrue(res["can_launch"])


if __name__ == "__main__":
    unittest.main()
