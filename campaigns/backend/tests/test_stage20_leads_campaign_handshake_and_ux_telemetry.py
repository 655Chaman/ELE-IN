"""
test_stage20_leads_campaign_handshake_and_ux_telemetry.py — Stage 20 Paranoia Test Suite.
Validates the Leads-to-Campaign Handshake, In-Campaign Presence & Telemetry Integration under
the Three-Layer Logic Architecture (Paranoia Framework).

- Layer 0: Foundational in-campaign list enrichment, campaign discovery via lead_list_id & metadata.
- Layer 1: Active campaign deletion block vs permitted deletion on draft/paused campaigns.
- Layer 2: Bulk lead removal execution pause, enrollment collision transparency, and zero data loss.
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from campaigns.backend.routers.elein import (
    get_lists,
    delete_lead_list
)
from leads.backend.routers.leads import (
    delete_lead_list_async,
    bulk_remove_leads_from_list,
    BulkRemoveListMembersRequest
)


class TestStage20LeadsCampaignHandshakeAndUXTelemetry(unittest.TestCase):
    """
    Stage 20 Paranoia Verification Suite:
    Tests bi-directional Leads-to-Campaign synchronization, active campaign list deletion guards,
    campaign metadata coalescence, and execution state safety upon lead removal.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_test_stage20"
        self.list_id = "list_camp_handshake_1"

    # =========================================================================
    # Layer 0: Foundational Layer (Campaign Join & Coalescence)
    # =========================================================================

    def test_layer0_get_lists_joins_campaign_data_for_in_campaign_filter(self):
        """
        Layer 0 Foundational (B3-F02):
        get_lists queries campaigns table and decorates list rows with
        associated campaign details (id, name, status) for 'In Campaign' filter.
        """
        # 1. lead_lists query result
        mock_lists_res = MagicMock(data=[
            {"id": "list_01", "name": "Enterprise CTOs", "type": "csv", "row_count": 150},
            {"id": "list_02", "name": "Unassigned Prospects", "type": "sales_nav", "row_count": 40}
        ])

        # 2. campaigns query result
        mock_camps_res = MagicMock(data=[
            {
                "id": "camp_active_01",
                "name": "Q4 Enterprise Scale",
                "status": "ACTIVE",
                "lead_list_id": "list_01",
                "metadata": {}
            }
        ])

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.range.return_value = mock_table

        mock_table.execute.side_effect = [mock_lists_res, mock_camps_res]

        results = get_lists(
            limit=50,
            offset=0,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

        self.assertEqual(len(results), 2)
        # First list is linked to camp_active_01
        self.assertIsNotNone(results[0].get("campaign"))
        self.assertEqual(results[0]["campaign"]["id"], "camp_active_01")
        self.assertEqual(results[0]["campaign"]["name"], "Q4 Enterprise Scale")
        self.assertEqual(results[0]["campaign"]["status"], "ACTIVE")

        # Second list has no campaign assigned
        self.assertIsNone(results[1].get("campaign"))

    def test_layer0_get_lists_coalesces_campaign_lead_list_id_and_metadata(self):
        """
        Layer 0 Foundational:
        Discovers campaigns where lead_list_id is stored inside metadata JSONB
        when the top-level lead_list_id column is null.
        """
        mock_lists_res = MagicMock(data=[
            {"id": "list_meta_01", "name": "Fintech Leads", "type": "hubspot", "row_count": 85}
        ])

        mock_camps_res = MagicMock(data=[
            {
                "id": "camp_meta_99",
                "name": "Fintech Inbound Sequence",
                "status": "ACTIVE",
                "lead_list_id": None,
                "metadata": {"lead_list_id": "list_meta_01"}
            }
        ])

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.range.return_value = mock_table

        mock_table.execute.side_effect = [mock_lists_res, mock_camps_res]

        results = get_lists(
            limit=50,
            offset=0,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

        self.assertIsNotNone(results[0].get("campaign"))
        self.assertEqual(results[0]["campaign"]["id"], "camp_meta_99")
        self.assertEqual(results[0]["campaign"]["name"], "Fintech Inbound Sequence")

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Active Deletion Protection)
    # =========================================================================

    def test_layer1_active_campaign_deletion_blocked_with_informative_error(self):
        """
        Layer 1 Environmental Safety (B3-F05):
        Prevents deleting a lead list when an ACTIVE campaign is using it,
        raising HTTP 400 with the active campaign's name.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # 1. list verification, 2. active campaigns query
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": self.list_id, "name": "Protected Active List"}]),
            MagicMock(data=[{"id": "camp_1", "name": "Live Outreach Alpha", "status": "ACTIVE"}])
        ]

        with self.assertRaises(HTTPException) as ctx:
            delete_lead_list(
                list_id=self.list_id,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Live Outreach Alpha", ctx.exception.detail)
        self.assertIn("Please pause the campaign", ctx.exception.detail)

    def test_layer1_draft_or_paused_campaign_list_can_be_deleted_safely(self):
        """
        Layer 1 Environmental Safety:
        Permits list deletion when associated campaign is in DRAFT, PAUSED, or ARCHIVED status.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.delete.return_value = mock_table

        # 1. list verification, 2. active campaigns query (empty because campaign is DRAFT),
        # 3. metadata active campaigns query (empty), 4. list_members delete, 5. lead_lists delete
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": self.list_id, "name": "Draft Campaign List"}]),
            MagicMock(data=[]),  # No ACTIVE campaigns by lead_list_id
            MagicMock(data=[]),  # No ACTIVE campaigns by metadata
            MagicMock(data=[]),  # list_members deleted
            MagicMock(data=[{"id": self.list_id}])  # lead_lists deleted
        ]

        res = delete_lead_list(
            list_id=self.list_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "deleted")
        self.assertEqual(res["list_id"], self.list_id)


class TestStage20AsyncLeadsOperations(unittest.IsolatedAsyncioTestCase):
    """
    Stage 20 Async Operations Suite:
    Tests async list deletion and bulk lead removal with automated campaign pause.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_test_stage20_async"
        self.list_id = "list_async_01"

    async def test_layer1_async_delete_lead_list_blocks_active_campaign(self):
        """
        Layer 1 Environmental Safety:
        delete_lead_list_async in leads router enforces identical active campaign protection.
        """
        mock_list_select = MagicMock()
        mock_list_select.execute = AsyncMock(return_value=MagicMock(data=[{"id": self.list_id, "name": "Async Active List"}]))
        
        mock_camp_select = MagicMock()
        mock_camp_select.execute = AsyncMock(return_value=MagicMock(data=[{"id": "camp_2", "name": "Live Outreach Beta"}]))

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # execute mock dispatch
        mock_table.execute = AsyncMock(side_effect=[
            MagicMock(data=[{"id": self.list_id, "name": "Async Active List"}]),
            MagicMock(data=[{"id": "camp_2", "name": "Live Outreach Beta"}])
        ])

        with self.assertRaises(HTTPException) as ctx:
            await delete_lead_list_async(
                list_id=self.list_id,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Live Outreach Beta", ctx.exception.detail)

    async def test_layer2_bulk_remove_leads_pauses_campaign_execution_states(self):
        """
        Layer 2 Human Paranoia (B3-F04):
        bulk_remove_leads_from_list verifies list ownership, deletes list_members records,
        and atomically pauses in-flight campaign execution states for all removed leads.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.delete.return_value = mock_table

        # 1. list verification, 2. list_members deletion
        mock_table.execute = AsyncMock(side_effect=[
            MagicMock(data=[{"id": self.list_id}]),
            MagicMock(data=[])
        ])

        payload = BulkRemoveListMembersRequest(lead_ids=["lead_01", "lead_02"])

        with patch("campaigns.backend.routers.elein._pause_lead_execution_core") as mock_pause, \
             patch("core.backend.api.auth_dep.get_service_client", return_value=MagicMock()):
            res = await bulk_remove_leads_from_list(
                list_id=self.list_id,
                payload=payload,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["removed_count"], 2)
        # Verify _pause_lead_execution_core was called for removed leads
        self.assertEqual(mock_pause.call_count, 2)


if __name__ == "__main__":
    unittest.main()
