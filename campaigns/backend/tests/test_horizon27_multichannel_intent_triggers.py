import unittest
from unittest.mock import MagicMock, patch
import json

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch, ACTION_TYPE_MAP
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestHorizon27MultichannelIntentTriggers(unittest.TestCase):
    """
    Test suite for Horizon 27: Multi-Channel Intent Triggers, Omnichannel Retargeting & Dynamic Step Forking.
    Implements Three-Layer Logic Architecture (Paranoia Framework):
      Layer 0: Foundational Layer (behavioral triggers, branch enum values, 4-tier channel cascade)
      Layer 1: Environmental Failure Analysis (database event lookups, suppression list blocks, fail-open timeout safety, orchestrator synonym matching)
      Layer 2: Human Paranoia (malformed email sanitization, IDOR tenant boundary, custom cascade priority, boolean normalization)
    """

    def setUp(self):
        self.workspace_id = "ws_test_horizon27"
        self.mock_supabase = MagicMock()
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        self.executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER TESTS
    # =========================================================================

    def test_layer0_action_type_map_and_branch_enum(self):
        """Verify fallback_to_inmail is mapped to inmail rate limits and all new branches exist."""
        self.assertIn("fallback_to_inmail", ACTION_TYPE_MAP)
        self.assertEqual(ACTION_TYPE_MAP["fallback_to_inmail"], "inmail")

        self.assertEqual(Branch.OPENED.value, "Opened")
        self.assertEqual(Branch.NOT_OPENED.value, "Not opened")
        self.assertEqual(Branch.CLICKED.value, "Clicked")
        self.assertEqual(Branch.NOT_CLICKED.value, "Not clicked")
        self.assertEqual(Branch.BOUNCED.value, "Bounced")
        self.assertEqual(Branch.DELIVERED.value, "Delivered")
        self.assertEqual(Branch.ACCEPTED.value, "Accepted")
        self.assertEqual(Branch.PENDING.value, "Pending")
        self.assertEqual(Branch.CHANNEL_LINKEDIN.value, "LinkedIn")
        self.assertEqual(Branch.CHANNEL_EMAIL.value, "Email")
        self.assertEqual(Branch.CHANNEL_INMAIL.value, "InMail")

    def test_layer0_if_email_opened_fast_path(self):
        """Layer 0: handle_if_email_opened returns Opened vs Not opened based on payload flags."""
        # True cases
        res1 = self.executor.handle_if_email_opened({"is_opened": True}, None)
        self.assertEqual(res1["branch"], Branch.OPENED.value)
        self.assertTrue(res1["opened"])
        self.assertTrue(res1["variables"]["email_opened"])

        res2 = self.executor.handle_if_email_opened({"opens_count": 3}, None)
        self.assertEqual(res2["branch"], Branch.OPENED.value)

        res3 = self.executor.handle_if_email_opened({"email_opened": "yes"}, None)
        self.assertEqual(res3["branch"], Branch.OPENED.value)

        # False cases
        res4 = self.executor.handle_if_email_opened({"is_opened": False}, None)
        self.assertEqual(res4["branch"], Branch.NOT_OPENED.value)
        self.assertFalse(res4["opened"])
        self.assertFalse(res4["variables"]["email_opened"])

        res5 = self.executor.handle_if_email_opened({}, None)
        self.assertEqual(res5["branch"], Branch.NOT_OPENED.value)

    def test_layer0_if_email_clicked_fast_path(self):
        """Layer 0: handle_if_email_clicked returns Clicked vs Not clicked based on payload flags."""
        res1 = self.executor.handle_if_email_clicked({"is_clicked": True, "clicked_url": "https://ele-in.com/demo"}, None)
        self.assertEqual(res1["branch"], Branch.CLICKED.value)
        self.assertTrue(res1["clicked"])
        self.assertEqual(res1["variables"]["clicked_url"], "https://ele-in.com/demo")

        res2 = self.executor.handle_if_email_clicked({"clicks_count": 1}, None)
        self.assertEqual(res2["branch"], Branch.CLICKED.value)

        res3 = self.executor.handle_if_email_clicked({"is_clicked": False}, None)
        self.assertEqual(res3["branch"], Branch.NOT_CLICKED.value)
        self.assertFalse(res3["clicked"])

    def test_layer0_if_email_bounced_fast_path(self):
        """Layer 0: handle_if_email_bounced returns Bounced vs Delivered."""
        res1 = self.executor.handle_if_email_bounced({"is_bounced": True, "error": "Mailbox not found"}, None)
        self.assertEqual(res1["branch"], Branch.BOUNCED.value)
        self.assertTrue(res1["bounced"])

        res2 = self.executor.handle_if_email_bounced({"delivery_status": "bounced"}, None)
        self.assertEqual(res2["branch"], Branch.BOUNCED.value)

        res3 = self.executor.handle_if_email_bounced({"delivery_status": "delivered"}, None)
        self.assertEqual(res3["branch"], Branch.DELIVERED.value)
        self.assertFalse(res3["bounced"])

    def test_layer0_if_connection_accepted_fast_path(self):
        """Layer 0: handle_if_connection_accepted returns Accepted vs Pending."""
        res1 = self.executor.handle_if_connection_accepted({"is_connected": True}, None)
        self.assertEqual(res1["branch"], Branch.ACCEPTED.value)
        self.assertTrue(res1["accepted"])

        res2 = self.executor.handle_if_connection_accepted({"accepted": "true"}, None)
        self.assertEqual(res2["branch"], Branch.ACCEPTED.value)

        res3 = self.executor.handle_if_connection_accepted({"is_connected": False}, None)
        self.assertEqual(res3["branch"], Branch.PENDING.value)
        self.assertFalse(res3["accepted"])

    def test_layer0_retarget_omnichannel_four_tier_cascade(self):
        """Layer 0: 4-Tier Omnichannel retargeting cascades properly across channel availability."""
        # Tier 1: 1st-Degree Connection -> LinkedIn
        lead_t1 = {
            "is_connected": True,
            "email": "sarah@acme.com",
            "inmail_eligible": True
        }
        res_t1 = self.executor.handle_retarget_omnichannel(lead_t1, "https://linkedin.com/in/sarah")
        self.assertEqual(res_t1["branch"], Branch.CHANNEL_LINKEDIN.value)
        self.assertEqual(res_t1["channel"], "linkedin")
        self.assertIn("1st-degree connection", res_t1["routing_reason"])

        # Tier 2: Not connected, but has valid deliverable email -> Email
        lead_t2 = {
            "is_connected": False,
            "email": "sarah@acme.com",
            "inmail_eligible": True
        }
        # Clear suppression check mock
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        res_t2 = self.executor.handle_retarget_omnichannel(lead_t2, "https://linkedin.com/in/sarah")
        self.assertEqual(res_t2["branch"], Branch.CHANNEL_EMAIL.value)
        self.assertEqual(res_t2["channel"], "email")
        self.assertIn("Deliverable email verified", res_t2["routing_reason"])

        # Tier 3: Not connected, no valid email, but InMail eligible -> InMail
        lead_t3 = {
            "is_connected": False,
            "email": "",
            "inmail_eligible": True
        }
        res_t3 = self.executor.handle_retarget_omnichannel(lead_t3, "https://linkedin.com/in/sarah")
        self.assertEqual(res_t3["branch"], Branch.CHANNEL_INMAIL.value)
        self.assertEqual(res_t3["channel"], "inmail")
        self.assertIn("Open profile / Sales Nav", res_t3["routing_reason"])

        # Tier 4: Fallback -> LinkedIn outreach
        lead_t4 = {
            "is_connected": False,
            "email": "",
            "inmail_eligible": False
        }
        res_t4 = self.executor.handle_retarget_omnichannel(lead_t4, "https://linkedin.com/in/sarah")
        self.assertEqual(res_t4["branch"], Branch.CHANNEL_LINKEDIN.value)
        self.assertEqual(res_t4["channel"], "linkedin")
        self.assertIn("Fallback", res_t4["routing_reason"])

    def test_layer0_fallback_to_inmail_execution(self):
        """Layer 0: handle_fallback_to_inmail dispatches InMail outreach with template variables."""
        payload = {
            "firstName": "Alex",
            "company": "TechCorp",
            "subject": "Regarding {{company}} growth",
            "message": "Hi {{firstName}}, checking in via InMail."
        }
        res = self.executor.handle_fallback_to_inmail(payload, "https://linkedin.com/in/alex")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.SENT.value)
        self.assertTrue(res["variables"]["fallback_inmail_sent"])
        self.assertEqual(res["variables"]["fallback_inmail_subject"], "Regarding TechCorp growth")
        self.assertEqual(res["variables"]["fallback_inmail_content"], "Hi Alex, checking in via InMail.")

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS TESTS
    # =========================================================================

    def test_layer1_email_events_and_leads_database_lookup(self):
        """Layer 1: When payload lacks flags, executor queries email_events and leads tables."""
        # 1. Email opened from email_events table
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"event_type": "open", "created_at": "2026-10-11T05:00:00Z"}
        ]
        res_open = self.executor.handle_if_email_opened({"_lead_id": "lead_123"}, None)
        self.assertEqual(res_open["branch"], Branch.OPENED.value)
        self.assertTrue(res_open["opened"])
        self.assertEqual(res_open["variables"]["email_opened_at"], "2026-10-11T05:00:00Z")

        # 2. Email clicked from email_events table
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"event_type": "click", "link_url": "https://ele-in.com/pricing"}
        ]
        res_click = self.executor.handle_if_email_clicked({"_lead_id": "lead_123"}, None)
        self.assertEqual(res_click["branch"], Branch.CLICKED.value)
        self.assertTrue(res_click["clicked"])
        self.assertEqual(res_click["variables"]["clicked_url"], "https://ele-in.com/pricing")

        # 3. Connection accepted from leads table
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"status": "1st", "is_connected": True}
        ]
        res_conn = self.executor.handle_if_connection_accepted({"_lead_id": "lead_123"}, None)
        self.assertEqual(res_conn["branch"], Branch.ACCEPTED.value)
        self.assertTrue(res_conn["accepted"])

    def test_layer1_database_exception_fails_open_safely(self):
        """Layer 1: Database timeout or missing table does not crash execution and returns safe defaults."""
        self.mock_supabase.table.side_effect = Exception("Database connection pool exhausted")

        res_open = self.executor.handle_if_email_opened({"_lead_id": "lead_err"}, None)
        self.assertEqual(res_open["branch"], Branch.NOT_OPENED.value)
        self.assertFalse(res_open["opened"])

        res_click = self.executor.handle_if_email_clicked({"_lead_id": "lead_err"}, None)
        self.assertEqual(res_click["branch"], Branch.NOT_CLICKED.value)
        self.assertFalse(res_click["clicked"])

        res_bounce = self.executor.handle_if_email_bounced({"_lead_id": "lead_err"}, None)
        self.assertEqual(res_bounce["branch"], Branch.DELIVERED.value)
        self.assertFalse(res_bounce["bounced"])

        res_conn = self.executor.handle_if_connection_accepted({"_lead_id": "lead_err"}, None)
        self.assertEqual(res_conn["branch"], Branch.PENDING.value)
        self.assertFalse(res_conn["accepted"])

    def test_layer1_suppression_list_blocks_email_channel(self):
        """Layer 1: If prospect email is in suppression list, omnichannel router disqualifies Email."""
        self.mock_supabase.table.side_effect = None

        def mock_table(table_name):
            t = MagicMock()
            if table_name == "suppression_list":
                def mock_select(fields):
                    s = MagicMock()
                    def mock_eq1(f1, v1):
                        e1 = MagicMock()
                        def mock_eq2(f2, v2):
                            e2 = MagicMock()
                            res = MagicMock()
                            if v2 == "unsubscribed@example.com":
                                res.data = [{"id": "suppressed_1"}]
                            else:
                                res.data = []
                            e2.limit.return_value.execute.return_value = res
                            return e2
                        e1.eq = mock_eq2
                        return e1
                    s.eq = mock_eq1
                    return s
                t.select = mock_select
            return t

        self.mock_supabase.table = mock_table

        lead_data = {
            "is_connected": False,
            "email": "unsubscribed@example.com",
            "inmail_eligible": True
        }
        res = self.executor.handle_retarget_omnichannel(lead_data, "https://linkedin.com/in/unsub")
        # Should NOT route to Email! Should cascade to InMail!
        self.assertEqual(res["branch"], Branch.CHANNEL_INMAIL.value)
        self.assertEqual(res["channel"], "inmail")

    def test_layer1_orchestrator_synonym_resolution_and_terminal_branches(self):
        """Layer 1: EleInOrchestrator properly resolves synonyms for Horizon 27 branches and handles terminal branches."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        edges = [
            {"source": "node_1", "target": "node_2", "source_handle": "email opened"},
            {"source": "node_1", "target": "node_3", "source_handle": "not opened"},
            {"source": "node_1", "target": "node_4", "source_handle": "link clicked"},
            {"source": "node_1", "target": "node_5", "source_handle": "channel_linkedin"},
            {"source": "node_1", "target": "node_6", "source_handle": "channel_email"},
            {"source": "node_1", "target": "node_7", "source_handle": "channel_inmail"},
        ]

        # 1. Opened matches 'email opened'
        edge1, is_term1 = orchestrator.resolve_branch_edge(edges, "Opened")
        self.assertIsNotNone(edge1)
        self.assertEqual(edge1["target"], "node_2")
        self.assertFalse(is_term1)

        # 2. Clicked matches 'link clicked'
        edge2, is_term2 = orchestrator.resolve_branch_edge(edges, "Clicked")
        self.assertIsNotNone(edge2)
        self.assertEqual(edge2["target"], "node_4")
        self.assertFalse(is_term2)

        # 3. Omnichannel channels match correctly
        edge_li, _ = orchestrator.resolve_branch_edge(edges, "LinkedIn")
        self.assertEqual(edge_li["target"], "node_5")

        edge_em, _ = orchestrator.resolve_branch_edge(edges, "Email")
        self.assertEqual(edge_em["target"], "node_6")

        edge_inm, _ = orchestrator.resolve_branch_edge(edges, "InMail")
        self.assertEqual(edge_inm["target"], "node_7")

        # 4. Terminal branches detection
        no_match_edge, is_term_bounced = orchestrator.resolve_branch_edge([], "Bounced")
        self.assertIsNone(no_match_edge)
        self.assertTrue(is_term_bounced)

        _, is_term_pending = orchestrator.resolve_branch_edge([], "Pending")
        self.assertTrue(is_term_pending)

        _, is_term_not_opened = orchestrator.resolve_branch_edge([], "Not opened")
        self.assertTrue(is_term_not_opened)

        _, is_term_not_clicked = orchestrator.resolve_branch_edge([], "Not clicked")
        self.assertTrue(is_term_not_clicked)

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA TESTS
    # =========================================================================

    def test_layer2_malformed_email_and_whitespace_sanitization(self):
        """Layer 2: Handles invalid emails (no @, missing TLD, spaces) gracefully without misrouting."""
        # Malformed email should NOT route to Email
        lead_malformed = {
            "is_connected": False,
            "email": "not-an-email",
            "inmail_eligible": False
        }
        res = self.executor.handle_retarget_omnichannel(lead_malformed, "https://linkedin.com/in/test")
        self.assertEqual(res["channel"], "linkedin")
        self.assertIsNone(res["variables"]["omnichannel_email"])

        # Whitespace padded email should be cleaned and routed if valid
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        lead_padded = {
            "is_connected": False,
            "email": "   valid.clean@domain.com   ",
            "inmail_eligible": False
        }
        res_clean = self.executor.handle_retarget_omnichannel(lead_padded, "https://linkedin.com/in/test")
        self.assertEqual(res_clean["channel"], "email")
        self.assertEqual(res_clean["variables"]["omnichannel_email"], "valid.clean@domain.com")

    def test_layer2_custom_cascade_order_preference(self):
        """Layer 2: Respects user-specified custom cascade order (e.g. Email before LinkedIn)."""
        lead_both = {
            "is_connected": True,
            "email": "ceo@growth.io",
            "inmail_eligible": True,
            "cascade_order": ["email", "linkedin_1st", "inmail"]
        }
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        res = self.executor.handle_retarget_omnichannel(lead_both, "https://linkedin.com/in/ceo")
        # Custom order requested email first!
        self.assertEqual(res["channel"], "email")
        self.assertEqual(res["branch"], Branch.CHANNEL_EMAIL.value)

    def test_layer2_evaluate_omnichannel_route_api_endpoint_and_idor(self):
        """Layer 2: API router endpoint enforces workspace isolation and returns candidate preview."""
        from fastapi import HTTPException
        from campaigns.backend.routers.elein import evaluate_omnichannel_route, EvaluateOmnichannelRouteRequest

        # 1. IDOR Defense: requesting a lead from another workspace raises 404
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        req_idor = EvaluateOmnichannelRouteRequest(lead_id="foreign_lead_999")
        with self.assertRaises(HTTPException) as cm:
            evaluate_omnichannel_route(req=req_idor, workspace_id="my_ws", supabase=mock_db)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertIn("Lead not found in current workspace", cm.exception.detail)

        # 2. Legitimate preview with ad-hoc attributes
        req_valid = EvaluateOmnichannelRouteRequest(
            email="lead@startup.com",
            is_connected=False,
            inmail_eligible=True
        )
        api_res = evaluate_omnichannel_route(req=req_valid, workspace_id="my_ws", supabase=mock_db)
        self.assertEqual(api_res["status"], "success")
        self.assertEqual(api_res["routed_channel"], "email")
        self.assertEqual(api_res["branch"], "Email")
        self.assertIn("variables", api_res)
        self.assertIn("evaluated_at", api_res)

    def test_tier_gating_free_workspace_raises_402_on_omnichannel_route(self):
        """Paranoia Layer 1: Asserts Free tier workspace receives HTTP 402 on omnichannel evaluation."""
        from fastapi import HTTPException
        from campaigns.backend.routers.elein import evaluate_omnichannel_route, EvaluateOmnichannelRouteRequest

        mock_db = MagicMock()
        mock_db.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        req = EvaluateOmnichannelRouteRequest(email="prospect@b2b.com", is_connected=False)

        with self.assertRaises(HTTPException) as ctx:
            evaluate_omnichannel_route(req=req, workspace_id="ws_real_free_tier", supabase=mock_db)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_pro_workspace_succeeds_on_omnichannel_route(self):
        """Paranoia Layer 1: Asserts Pro workspace passes tier check and evaluates route."""
        from campaigns.backend.routers.elein import evaluate_omnichannel_route, EvaluateOmnichannelRouteRequest

        mock_db = MagicMock()
        mock_db.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        req = EvaluateOmnichannelRouteRequest(email="prospect@b2b.com", is_connected=False)

        res = evaluate_omnichannel_route(req=req, workspace_id="ws_real_pro_tier", supabase=mock_db)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["routed_channel"], "email")


if __name__ == "__main__":
    unittest.main()
