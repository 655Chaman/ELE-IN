import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.routers.elein import get_lists

class TestStage15LeadsFrontendStateAndSeamlessOverlays(unittest.TestCase):
    """
    Stage 15 Paranoia Test Suite:
    Validates Bridge 4 & Bridge 3 Seamlessness:
    - Layer 0: get_lists returns paginated lists with campaign association.
    - Layer 1: get_lists handles missing campaigns, schema drift, and empty metadata gracefully.
    - Layer 2: In-memory fallback and unassigned list isolation.
    """

    def test_layer0_get_lists_enriches_campaign_associations(self):
        """
        Layer 0 Foundational (B3-F02):
        get_lists must join active campaigns matching list_id, populating list['campaign']
        so the frontend 'In Campaign' and 'Unassigned' filter chips function correctly.
        """
        mock_supabase = MagicMock()
        mock_lists_data = [
            {"id": "list-1", "name": "SaaS Founders", "row_count": 150, "type": "csv"},
            {"id": "list-2", "name": "Fintech VPs", "row_count": 80, "type": "sales_nav"}
        ]
        mock_camps_data = [
            {"id": "camp-100", "name": "Q4 Outbound Campaign", "status": "ACTIVE", "lead_list_id": "list-1", "metadata": {}}
        ]

        def table_router(name):
            m = MagicMock()
            if name == "lead_lists":
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=mock_lists_data)
                return m
            elif name == "campaigns":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=mock_camps_data)
                return m
            return m

        mock_supabase.table.side_effect = table_router

        result = get_lists(
            limit=50,
            offset=0,
            supabase=mock_supabase,
            workspace_id="ws-stage15"
        )

        self.assertEqual(len(result), 2)
        # list-1 should have its campaign joined
        self.assertIsNotNone(result[0].get("campaign"))
        self.assertEqual(result[0]["campaign"]["id"], "camp-100")
        self.assertEqual(result[0]["campaign"]["name"], "Q4 Outbound Campaign")
        self.assertEqual(result[0]["campaign"]["status"], "ACTIVE")

        # list-2 is unassigned and should have campaign: None
        self.assertIsNone(result[1].get("campaign"))

    def test_layer1_get_lists_matches_nested_metadata_campaign_references(self):
        """
        Layer 1 Paranoia (B3-F05):
        Campaigns that store lead_list_id inside campaign.metadata['lead_list_id']
        must still be joined onto the corresponding lead_list.
        """
        mock_supabase = MagicMock()
        mock_lists_data = [
            {"id": "list-meta-1", "name": "AI Engineers", "row_count": 220, "type": "search"}
        ]
        mock_camps_data = [
            {"id": "camp-meta-9", "name": "AI Outreach Sprint", "status": "PAUSED", "lead_list_id": None, "metadata": {"lead_list_id": "list-meta-1"}}
        ]

        def table_router(name):
            m = MagicMock()
            if name == "lead_lists":
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=mock_lists_data)
                return m
            elif name == "campaigns":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=mock_camps_data)
                return m
            return m

        mock_supabase.table.side_effect = table_router

        result = get_lists(
            limit=50,
            offset=0,
            supabase=mock_supabase,
            workspace_id="ws-meta-test"
        )

        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0]["campaign"])
        self.assertEqual(result[0]["campaign"]["id"], "camp-meta-9")
        self.assertEqual(result[0]["campaign"]["name"], "AI Outreach Sprint")

    def test_layer1_get_lists_campaign_join_failure_is_non_fatal(self):
        """
        Layer 1 Paranoia: If campaigns table query throws an exception,
        get_lists must not crash; it logs a debug warning and returns lists with campaign: None.
        """
        mock_supabase = MagicMock()
        mock_lists_data = [
            {"id": "list-safe-1", "name": "Resilience List", "row_count": 10, "type": "csv"}
        ]

        def table_router(name):
            m = MagicMock()
            if name == "lead_lists":
                m.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=mock_lists_data)
                return m
            elif name == "campaigns":
                m.select.return_value.eq.return_value.execute.side_effect = RuntimeError("PostgREST transient error")
                return m
            return m

        mock_supabase.table.side_effect = table_router

        result = get_lists(
            limit=50,
            offset=0,
            supabase=mock_supabase,
            workspace_id="ws-fail-safe"
        )

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].get("campaign"))

    def test_layer2_get_lists_zero_migration_in_memory_fallback(self):
        """
        Layer 2 Paranoia: If lead_lists query fails entirely, fallback to in-memory store
        without crashing the request.
        """
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = RuntimeError("Database unreachable")

        with patch("leads.backend.services.lead_ingestion_service.get_in_memory_lead_lists", return_value=[
            {"id": "mem-list-1", "name": "Sandbox Memory List", "row_count": 5}
        ]):
            result = get_lists(
                limit=50,
                offset=0,
                supabase=mock_supabase,
                workspace_id="ws-mem-test"
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "mem-list-1")


if __name__ == "__main__":
    unittest.main()
