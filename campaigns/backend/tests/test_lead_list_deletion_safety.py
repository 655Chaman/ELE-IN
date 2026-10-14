import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from collections import defaultdict

class TestLeadListDeletionSafety(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Lead List Lifecycle, Active Campaign Safety & Deletion Hardening.
    Applies the Three-Layer Logic Architecture (Paranoia Framework).
    """

    @patch("campaigns.backend.routers.elein.get_supabase_client")
    @patch("campaigns.backend.routers.elein.get_current_workspace")
    def test_delete_lead_list_success(self, mock_get_ws, mock_get_supabase):
        from campaigns.backend.routers.elein import delete_lead_list
        mock_get_ws.return_value = "ws_test_123"
        supabase = MagicMock()

        def side_effect_table(name):
            t = MagicMock()
            if name == "lead_lists":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "list_1", "name": "VIP Leads"}])
            elif name == "campaigns":
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return t

        supabase.table.side_effect = side_effect_table

        res = delete_lead_list("list_1", workspace_id="ws_test_123", supabase=supabase)
        self.assertEqual(res["status"], "deleted")
        self.assertEqual(res["list_id"], "list_1")

    @patch("campaigns.backend.routers.elein.get_supabase_client")
    @patch("campaigns.backend.routers.elein.get_current_workspace")
    def test_delete_lead_list_blocks_active_campaign(self, mock_get_ws, mock_get_supabase):
        from campaigns.backend.routers.elein import delete_lead_list
        mock_get_ws.return_value = "ws_test_123"
        supabase = MagicMock()

        def side_effect_table(name):
            t = MagicMock()
            if name == "lead_lists":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "list_1", "name": "VIP Leads"}])
            elif name == "campaigns":
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "camp_1", "name": "Q4 Outreach"}])
            return t

        supabase.table.side_effect = side_effect_table

        with self.assertRaises(HTTPException) as ctx:
            delete_lead_list("list_1", workspace_id="ws_test_123", supabase=supabase)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Q4 Outreach", ctx.exception.detail)

    @patch("campaigns.backend.routers.elein.get_supabase_client")
    @patch("campaigns.backend.routers.elein.get_current_workspace")
    def test_delete_lead_list_allows_paused_campaign(self, mock_get_ws, mock_get_supabase):
        from campaigns.backend.routers.elein import delete_lead_list
        mock_get_ws.return_value = "ws_test_123"
        supabase = MagicMock()

        def side_effect_table(name):
            t = MagicMock()
            if name == "lead_lists":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "list_1", "name": "VIP Leads"}])
            elif name == "campaigns":
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return t

        supabase.table.side_effect = side_effect_table

        res = delete_lead_list("list_1", workspace_id="ws_test_123", supabase=supabase)
        self.assertEqual(res["status"], "deleted")

    @patch("campaigns.backend.routers.elein.get_supabase_client")
    @patch("campaigns.backend.routers.elein.get_current_workspace")
    def test_delete_lead_list_404_unauthorized(self, mock_get_ws, mock_get_supabase):
        from campaigns.backend.routers.elein import delete_lead_list
        mock_get_ws.return_value = "ws_test_123"
        supabase = MagicMock()

        supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            delete_lead_list("list_fake", workspace_id="ws_test_123", supabase=supabase)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_remove_lead_from_list_tenant_guard(self):
        from leads.backend.routers.leads import remove_lead_from_list
        supabase = MagicMock()
        query_mock = AsyncMock()
        query_mock.execute.return_value = MagicMock(data=[])
        supabase.table.return_value.select.return_value.eq.return_value.eq.return_value = query_mock

        with self.assertRaises(HTTPException) as ctx:
            await remove_lead_from_list("list_1", "lead_1", workspace_id="ws_other", supabase=supabase)
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("campaigns.backend.routers.elein._pause_lead_execution_core")
    @patch("core.backend.api.auth_dep.get_service_client")
    async def test_remove_lead_from_list_auto_pauses_in_flight_states(self, mock_get_service_client, mock_pause_core):
        from leads.backend.routers.leads import remove_lead_from_list
        supabase = MagicMock()
        query_mock = AsyncMock()
        query_mock.execute.return_value = MagicMock(data=[{"id": "list_1"}])
        supabase.table.return_value.select.return_value.eq.return_value.eq.return_value = query_mock
        
        del_mock = AsyncMock()
        del_mock.execute.return_value = MagicMock(data=[])
        supabase.table.return_value.delete.return_value.eq.return_value.eq.return_value = del_mock

        res = await remove_lead_from_list("list_1", "lead_1", workspace_id="ws_test_123", supabase=supabase)
        self.assertTrue(res["success"])
        mock_pause_core.assert_called_once()
