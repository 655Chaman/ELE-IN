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

if __name__ == "__main__":
    unittest.main()
