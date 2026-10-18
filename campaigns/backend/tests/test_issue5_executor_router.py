import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import EvaluateDeliverabilityPoolRequest, get_sender_pool_domains_endpoint, evaluate_deliverability_pool_endpoint


class TestIssue5ExecutorRouterIntegration(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws_test_issue5"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

    @patch("integrations.backend.services.email_sender_service.select_rotating_sender_inbox")
    @patch("integrations.backend.services.email_sender_service.record_inbox_delivery_outcome")
    def test_executor_domain_balanced_selection_and_telemetry(self, mock_record_outcome, mock_select_inbox):
        """Verifies domain balancing strategy derivation, parameter propagation, telemetry injection, and outcome recording."""
        mock_select_inbox.return_value = {
            "selected": {
                "id": "inb_domain_1",
                "email": "sarah@outbound.sales.acme.com",
                "sender_domain": "acme.com",
                "domain_burnout_status": "HEALTHY",
            },
            "strategy_applied": "DOMAIN_BALANCED",
            "selection_reason": "DOMAIN_BALANCED_OPTIMAL",
            "pool_summary": {},
        }

        # Mock supabase RPC deduct credits and campaign_lead_sender_locks query
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value.data = {"success": True}
        self.mock_supabase.rpc.return_value = rpc_mock

        locks_query = MagicMock()
        locks_query.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        self.mock_supabase.table.return_value = locks_query

        res = self.executor.handle_send_email(
            data={
                "to_email": "prospect@target.com",
                "subject": "Hello {{first_name}}",
                "body": "Hi there",
                "use_domain_balancing": True,
                "domain_daily_cap": 120,
                "affinity_fallback_mode": "same_domain",
                "use_sender_pool": True,
                "lead_id": "lead_999",
            },
            linkedin_url="https://linkedin.com/in/prospect",
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["sender_inbox_id"], "inb_domain_1")
        self.assertEqual(res["sender_domain"], "acme.com")
        self.assertEqual(res["strategy_applied"], "DOMAIN_BALANCED")
        self.assertEqual(res["selection_reason"], "DOMAIN_BALANCED_OPTIMAL")
        self.assertFalse(res["thread_affinity_maintained"])
        self.assertEqual(res["domain_burnout_status"], "HEALTHY")

        # Verify select_rotating_sender_inbox was called with domain parameters
        mock_select_inbox.assert_called_once()
        kwargs = mock_select_inbox.call_args[1]
        self.assertEqual(kwargs["strategy"], "DOMAIN_BALANCED")
        self.assertEqual(kwargs["domain_daily_cap"], 120)
        self.assertEqual(kwargs["affinity_fallback_mode"], "same_domain")

        # Verify outcome recorded
        mock_record_outcome.assert_called_once_with(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            inbox_id="inb_domain_1",
            event_type="sent",
        )

        # Verify affinity lock insertion attempted
        self.mock_supabase.table.assert_any_call("campaign_lead_sender_locks")

    @patch("integrations.backend.services.email_sender_service.select_rotating_sender_inbox")
    @patch("integrations.backend.services.elein_crm_service._safe_refund_credits")
    def test_executor_postpone_when_affinity_inbox_capped(self, mock_refund, mock_select_inbox):
        """Verifies postponement when affinity inbox is capped without burning credits."""
        mock_select_inbox.return_value = {
            "selected": None,
            "postpone_required": True,
            "selection_reason": "AFFINITY_INBOX_CAPPED_POSTPONE",
            "pool_summary": {},
        }

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value.data = {"success": True}
        self.mock_supabase.rpc.return_value = rpc_mock

        res = self.executor.handle_send_email(
            data={
                "to_email": "prospect@target.com",
                "subject": "Quick follow-up",
                "body": "Checking in",
                "use_domain_balancing": True,
                "affinity_fallback_mode": "postpone",
                "use_sender_pool": True,
                "lead_id": "lead_123",
            },
            linkedin_url="https://linkedin.com/in/prospect",
        )

        self.assertEqual(res["status"], "postponed")
        self.assertEqual(res["reason"], "affinity_inbox_daily_cap_reached")
        self.assertEqual(res["branch"], Branch.FAILED.value)
        self.assertEqual(res["next_run_delta_hours"], 12)
        self.assertIn("deferred to next window", res["error"])

        # Credit should be refunded
        mock_refund.assert_called_once()

    def test_evaluate_deliverability_pool_request_schema(self):
        """Verifies request model includes domain balancing and daily cap fields with correct defaults."""
        req = EvaluateDeliverabilityPoolRequest()
        self.assertEqual(req.domain_daily_cap, 150)
        self.assertEqual(req.affinity_fallback_mode, "same_domain")
        self.assertFalse(req.use_domain_balancing)

        custom_req = EvaluateDeliverabilityPoolRequest(
            domain_daily_cap=80,
            affinity_fallback_mode="postpone",
            use_domain_balancing=True,
        )
        self.assertEqual(custom_req.domain_daily_cap, 80)
        self.assertEqual(custom_req.affinity_fallback_mode, "postpone")
        self.assertTrue(custom_req.use_domain_balancing)

    @patch("integrations.backend.services.email_sender_service.select_rotating_sender_inbox")
    def test_evaluate_deliverability_pool_endpoint_forwards_params(self, mock_select_inbox):
        """Verifies evaluate_deliverability_pool passes domain_daily_cap and affinity_fallback_mode."""
        mock_select_inbox.return_value = {"selected": {"id": "inb_1"}, "strategy_applied": "DOMAIN_BALANCED"}
        req = EvaluateDeliverabilityPoolRequest(
            domain_daily_cap=200,
            affinity_fallback_mode="same_domain",
            use_domain_balancing=True,
        )

        with patch("campaigns.backend.routers.elein._check_workspace_tier_permission"):
            res = evaluate_deliverability_pool_endpoint(
                req=req,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase,
            )

        self.assertEqual(res["strategy_applied"], "DOMAIN_BALANCED")
        mock_select_inbox.assert_called_once()
        kwargs = mock_select_inbox.call_args[1]
        self.assertEqual(kwargs["strategy"], "DOMAIN_BALANCED")
        self.assertEqual(kwargs["domain_daily_cap"], 200)
        self.assertEqual(kwargs["affinity_fallback_mode"], "same_domain")

    @patch("integrations.backend.services.email_sender_service.aggregate_domain_metrics")
    def test_get_sender_pool_domains_endpoint(self, mock_aggregate):
        """Verifies GET /sender-pool/domains queries inboxes for workspace and aggregates metrics."""
        mock_aggregate.return_value = {
            "acme.com": {
                "domain": "acme.com",
                "inbox_count": 2,
                "total_sent_today": 45,
                "domain_burnout_status": "HEALTHY",
            }
        }

        inboxes_table = MagicMock()
        inboxes_table.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "inb_1", "email": "a@acme.com", "workspace_id": self.workspace_id},
            {"id": "inb_2", "email": "b@acme.com", "workspace_id": self.workspace_id},
        ]
        self.mock_supabase.table.return_value = inboxes_table

        res = get_sender_pool_domains_endpoint(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertEqual(res["total_domains"], 1)
        self.assertIn("acme.com", res["domains"])
        mock_aggregate.assert_called_once()

    @patch("integrations.backend.services.email_sender_service.select_rotating_sender_inbox")
    @patch("integrations.backend.services.email_sender_service.record_inbox_delivery_outcome")
    def test_executor_thread_affinity_maintained_flag(self, mock_record_outcome, mock_select_inbox):
        """Verifies thread_affinity_maintained is True when AFFINITY is in selection_reason."""
        mock_select_inbox.return_value = {
            "selected": {
                "id": "inb_affinity_locked",
                "email": "dan@company.io",
                "domain_burnout_status": "HEALTHY",
            },
            "strategy_applied": "DOMAIN_BALANCED",
            "selection_reason": "THREAD_AFFINITY_LOCK",
            "pool_summary": {},
        }
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value.data = {"success": True}
        self.mock_supabase.rpc.return_value = rpc_mock

        locks_query = MagicMock()
        locks_query.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"inbox_id": "inb_affinity_locked"}
        ]
        self.mock_supabase.table.side_effect = lambda t: locks_query if t in ("thread_affinity_locks", "campaign_lead_sender_locks") else MagicMock()

        res = self.executor.handle_send_email(
            data={
                "to_email": "dan_lead@client.com",
                "subject": "Follow-up",
                "body": "Checking in",
                "use_domain_balancing": True,
                "use_sender_pool": True,
                "lead_id": "lead_locked_1",
            },
            linkedin_url="https://linkedin.com/in/dan",
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["thread_affinity_maintained"])
        self.assertEqual(res["sender_domain"], "company.io")
        # Since lock already existed, insert should not have been called
        locks_query.insert.assert_not_called()

    def test_get_sender_pool_domains_endpoint_handles_db_error(self):
        """Verifies GET /sender-pool/domains gracefully handles database failure without crashing."""
        inboxes_table = MagicMock()
        inboxes_table.select.return_value.eq.return_value.execute.side_effect = RuntimeError("Database timeout")
        self.mock_supabase.table.return_value = inboxes_table

        with patch("integrations.backend.services.email_sender_service.aggregate_domain_metrics", return_value={}):
            res = get_sender_pool_domains_endpoint(
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase,
            )

        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertEqual(res["total_domains"], 0)
        self.assertEqual(res["domains"], {})


if __name__ == "__main__":
    unittest.main()

