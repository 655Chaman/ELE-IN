import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from integrations.backend.routers.hubspot import (
    get_hubspot_status,
    authenticate_hubspot,
    HubspotAuth,
    get_hubspot_lists,
    import_hubspot_list
)


class TestStage18HubSpotCrmSyncAndLeadsLifecycle(unittest.IsolatedAsyncioTestCase):
    """
    Stage 18 Paranoia Test Suite:
    Validates HubSpot CRM Synchronization & Lead List Lifecycle Completion:
    - Layer 0: Authentication, status check, and contact lists discovery.
    - Layer 1: Asynchronous background worker dispatch for streaming imports.
    - Layer 2: Growth Pro tier gating and unauthorized/expired token defense.
    """

    async def test_layer0_get_hubspot_status_reports_connection_state(self):
        """
        Layer 0 Foundational:
        get_hubspot_status queries workspaces.hubspot_token and returns connected=True/False.
        """
        mock_supabase = MagicMock()
        mock_select = MagicMock()
        mock_select.execute = AsyncMock(return_value=MagicMock(data=[{"hubspot_token": "pat-na1-test-token-valid-99"}]))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_select

        res = await get_hubspot_status(workspace_id="ws-hubspot-active", supabase=mock_supabase)
        self.assertTrue(res["connected"])

        # Test disconnected state
        mock_select.execute = AsyncMock(return_value=MagicMock(data=[{"hubspot_token": None}]))
        res_empty = await get_hubspot_status(workspace_id="ws-hubspot-empty", supabase=mock_supabase)
        self.assertFalse(res_empty["connected"])

    async def test_layer1_authenticate_hubspot_validates_token_and_persists_for_pro_tier(self):
        """
        Layer 1 Paranoia:
        authenticate_hubspot verifies token format, validates token via external request,
        enforces Pro tier gating, and persists the token in workspaces table.
        """
        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(data=[{"tier": "PRO"}]))
        mock_ws_update = MagicMock()
        mock_ws_update.execute = AsyncMock(return_value=MagicMock(data=[{"id": "ws-pro-1"}]))

        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select
        mock_supabase.table.return_value.update.return_value.eq.return_value = mock_ws_update

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("core.backend.services.http_client.async_external_request", new_callable=AsyncMock, return_value=mock_resp):
            req = HubspotAuth(access_token="pat-na1-valid-secret-key-12345")
            res = await authenticate_hubspot(data=req, workspace_id="ws-pro-1", supabase=mock_supabase)

        self.assertEqual(res["status"], "ok")
        self.assertIn("Authenticated", res["message"])

    async def test_layer2_authenticate_hubspot_enforces_tier_gating(self):
        """
        Layer 2 Paranoia:
        Free tier workspaces cannot authenticate or use HubSpot CRM sync (HTTP 403 Forbidden).
        """
        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(data=[{"tier": "FREE"}]))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select

        req = HubspotAuth(access_token="pat-na1-valid-secret-key-12345")
        with self.assertRaises(HTTPException) as ctx:
            await authenticate_hubspot(data=req, workspace_id="ws-free", supabase=mock_supabase)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Growth Pro", ctx.exception.detail)

    async def test_layer0_get_hubspot_lists_retrieves_contact_lists(self):
        """
        Layer 0 Foundational:
        get_hubspot_lists queries HubSpot lists API and returns formatted contact lists.
        """
        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(
            data=[{"tier": "PRO", "hubspot_token": "pat-na1-token-123"}]
        ))
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select

        mock_hubspot_api_data = {
            "lists": [
                {"listId": 101, "name": "SaaS Leaders Q4", "metaData": {"size": 450}},
                {"listId": 102, "name": "Fintech VPs", "metaData": {"size": 80}}
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_hubspot_api_data

        with patch("core.backend.services.http_client.async_external_request", new_callable=AsyncMock, return_value=mock_resp):
            res = await get_hubspot_lists(workspace_id="ws-pro-lists", supabase=mock_supabase)

        self.assertEqual(len(res["lists"]), 2)
        self.assertEqual(res["lists"][0]["id"], 101)
        self.assertEqual(res["lists"][0]["name"], "SaaS Leaders Q4")
        self.assertEqual(res["lists"][0]["count"], 450)

    async def test_layer1_import_hubspot_list_initializes_and_enqueues_job(self):
        """
        Layer 1 & 2 Paranoia:
        import_hubspot_list validates list_id, checks tier, creates lead_lists record,
        and enqueues background worker job via enqueue_job.
        """
        mock_supabase = MagicMock()
        mock_ws_select = MagicMock()
        mock_ws_select.execute = AsyncMock(return_value=MagicMock(
            data=[{"tier": "PRO", "hubspot_token": "pat-na1-token-123"}]
        ))
        mock_list_insert = MagicMock()
        mock_list_insert.execute = AsyncMock(return_value=MagicMock(data=[{}]))

        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_ws_select
        mock_supabase.table.return_value.insert.return_value = mock_list_insert

        with patch("core.backend.services.job_queue.enqueue_job") as mock_enqueue:
            res = await import_hubspot_list(
                list_id=101,
                workspace_id="ws-pro-import",
                supabase=mock_supabase
            )

        self.assertEqual(res["status"], "sync_started")
        self.assertEqual(res["list_id"], 101)
        self.assertIsNotNone(res["internal_list_id"])
        mock_enqueue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
