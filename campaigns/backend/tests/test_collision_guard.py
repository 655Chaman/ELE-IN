import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.collision_guard import get_conflicting_active_leads, is_lead_active_in_other_campaign

class TestCollisionGuard(unittest.TestCase):
    def setUp(self):
        self.mock_supabase = MagicMock()

    def test_get_conflicting_active_leads_detects_in_flight_states(self):
        mock_enrollment_query = MagicMock()
        mock_enrollment_query.eq.return_value = mock_enrollment_query
        mock_enrollment_query.neq.return_value = mock_enrollment_query
        mock_enrollment_query.in_.return_value = mock_enrollment_query
        mock_enrollment_query.execute.return_value = MagicMock(data=[
            {"id": "e1", "campaign_id": "camp_other", "lead_id": "lead_1"}
        ])

        mock_camp_query = MagicMock()
        mock_camp_query.in_.return_value = mock_camp_query
        mock_camp_query.execute.return_value = MagicMock(data=[
            {"id": "camp_other", "status": "ACTIVE"}
        ])

        mock_state_query = MagicMock()
        mock_state_query.in_.return_value = mock_state_query
        mock_state_query.execute.return_value = MagicMock(data=[
            {"enrollment_id": "e1", "status": "running"}
        ])

        def table_side_effect(table_name):
            t_mock = MagicMock()
            if table_name == "campaign_enrollments":
                t_mock.select.return_value = mock_enrollment_query
            elif table_name == "campaigns":
                t_mock.select.return_value = mock_camp_query
            elif table_name == "campaign_execution_states":
                t_mock.select.return_value = mock_state_query
            return t_mock

        self.mock_supabase.table.side_effect = table_side_effect

        colliding = get_conflicting_active_leads(
            self.mock_supabase, "ws_123", ["lead_1", "lead_2"], exclude_campaign_id="camp_current"
        )
        self.assertEqual(colliding, {"lead_1"})

    def test_get_conflicting_active_leads_ignores_completed_or_exited_states(self):
        mock_enrollment_query = MagicMock()
        mock_enrollment_query.eq.return_value = mock_enrollment_query
        mock_enrollment_query.neq.return_value = mock_enrollment_query
        mock_enrollment_query.in_.return_value = mock_enrollment_query
        mock_enrollment_query.execute.return_value = MagicMock(data=[
            {"id": "e1", "campaign_id": "camp_other", "lead_id": "lead_1"}
        ])

        mock_camp_query = MagicMock()
        mock_camp_query.in_.return_value = mock_camp_query
        mock_camp_query.execute.return_value = MagicMock(data=[
            {"id": "camp_other", "status": "ACTIVE"}
        ])

        # Execution state is completed, so query with in_ for in-flight statuses returns empty data
        mock_state_query = MagicMock()
        mock_state_query.in_.return_value = mock_state_query
        mock_state_query.execute.return_value = MagicMock(data=[])

        def table_side_effect(table_name):
            t_mock = MagicMock()
            if table_name == "campaign_enrollments":
                t_mock.select.return_value = mock_enrollment_query
            elif table_name == "campaigns":
                t_mock.select.return_value = mock_camp_query
            elif table_name == "campaign_execution_states":
                t_mock.select.return_value = mock_state_query
            return t_mock

        self.mock_supabase.table.side_effect = table_side_effect

        colliding = get_conflicting_active_leads(
            self.mock_supabase, "ws_123", ["lead_1"]
        )
        self.assertEqual(colliding, set())

    def test_get_conflicting_active_leads_ignores_paused_or_draft_campaigns(self):
        mock_enrollment_query = MagicMock()
        mock_enrollment_query.eq.return_value = mock_enrollment_query
        mock_enrollment_query.neq.return_value = mock_enrollment_query
        mock_enrollment_query.in_.return_value = mock_enrollment_query
        mock_enrollment_query.execute.return_value = MagicMock(data=[
            {"id": "e1", "campaign_id": "camp_other", "lead_id": "lead_1"}
        ])

        mock_camp_query = MagicMock()
        mock_camp_query.in_.return_value = mock_camp_query
        mock_camp_query.execute.return_value = MagicMock(data=[
            {"id": "camp_other", "status": "PAUSED"}
        ])

        def table_side_effect(table_name):
            t_mock = MagicMock()
            if table_name == "campaign_enrollments":
                t_mock.select.return_value = mock_enrollment_query
            elif table_name == "campaigns":
                t_mock.select.return_value = mock_camp_query
            return t_mock

        self.mock_supabase.table.side_effect = table_side_effect

        colliding = get_conflicting_active_leads(
            self.mock_supabase, "ws_123", ["lead_1"]
        )
        self.assertEqual(colliding, set())

    def test_is_lead_active_in_other_campaign(self):
        with patch("campaigns.backend.services.collision_guard.get_conflicting_active_leads", return_value={"lead_1"}):
            self.assertTrue(is_lead_active_in_other_campaign(self.mock_supabase, "ws_123", "lead_1", "camp_1"))
            self.assertFalse(is_lead_active_in_other_campaign(self.mock_supabase, "ws_123", "lead_2", "camp_1"))

    def test_preflight_collision_check_endpoint_empty_inputs(self):
        from campaigns.backend.routers.elein import preflight_collision_check, PreflightCollisionCheckRequest
        req = PreflightCollisionCheckRequest(linkedin_urls=[], emails=[])
        res = preflight_collision_check(req, supabase=self.mock_supabase, workspace_id="ws_123", user_id="u_1")
        self.assertEqual(res["total_checked"], 0)
        self.assertEqual(res["colliding_active_count"], 0)

    def test_preflight_collision_check_detects_active_collisions(self):
        from campaigns.backend.routers.elein import preflight_collision_check, PreflightCollisionCheckRequest

        mock_leads_query = MagicMock()
        mock_leads_query.eq.return_value = mock_leads_query
        mock_leads_query.in_.return_value = mock_leads_query
        mock_leads_query.execute.return_value = MagicMock(data=[
            {
                "id": "lead_1",
                "linkedin_url": "https://linkedin.com/in/alex",
                "email": "alex@example.com",
                "first_name": "Alex",
                "last_name": "Smith",
                "company_name": "Acme Corp"
            }
        ])

        mock_enrollments = MagicMock()
        mock_enrollments.eq.return_value = mock_enrollments
        mock_enrollments.in_.return_value = mock_enrollments
        mock_enrollments.execute.return_value = MagicMock(data=[
            {"id": "enr_1", "campaign_id": "camp_active", "lead_id": "lead_1"}
        ])

        mock_camp = MagicMock()
        mock_camp.in_.return_value = mock_camp
        mock_camp.execute.return_value = MagicMock(data=[
            {"id": "camp_active", "name": "Q4 Outreach", "status": "ACTIVE"}
        ])

        def table_side_effect(name):
            m = MagicMock()
            if name == "leads":
                m.select.return_value = mock_leads_query
            elif name == "campaign_enrollments":
                m.select.return_value = mock_enrollments
            elif name == "campaigns":
                m.select.return_value = mock_camp
            return m

        self.mock_supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.collision_guard.get_conflicting_active_leads", return_value={"lead_1"}):
            req = PreflightCollisionCheckRequest(
                linkedin_urls=["https://www.linkedin.com/in/alex/"],
                emails=["alex@example.com"]
            )
            res = preflight_collision_check(req, supabase=self.mock_supabase, workspace_id="ws_123", user_id="u_1")
            self.assertEqual(res["total_checked"], 2)
            self.assertEqual(res["workspace_matches_count"], 1)
            self.assertEqual(res["colliding_active_count"], 1)
            self.assertIn("Q4 Outreach", res["active_campaign_names"])
            self.assertEqual(len(res["colliding_samples"]), 1)
            self.assertEqual(res["colliding_samples"][0]["name"], "Alex Smith")
            self.assertEqual(res["colliding_samples"][0]["campaign_name"], "Q4 Outreach")

if __name__ == "__main__":
    unittest.main()
