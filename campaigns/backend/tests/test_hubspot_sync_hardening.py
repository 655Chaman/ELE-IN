import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from integrations.backend.services.hubspot_sync import sync_hubspot_deals_job, BATCH_DEAL_LIMIT
from integrations.backend.services.hubspot_worker import import_hubspot_list_bg


class TestHubSpotSyncHardening(unittest.IsolatedAsyncioTestCase):
    """
    Step 19: HubSpot CRM Bi-directional Sync Scalability, N+1 Elimination & Token Expiry Guard.
    Tests compliance with the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.workspace_id = "ws_test_hubspot_123"
        self.won_stage_id = "closedwon"
        self.token = "hs_pat_test_token"

    # =========================================================================
    # Helpers for mocking Supabase Async & Sync Clients
    # =========================================================================

    def _create_mock_async_supabase(self, workspaces=None, active_states=None, leads=None):
        """Creates an async supabase client mock supporting chained table queries."""
        mock_client = MagicMock()

        def table_side_effect(table_name):
            query = MagicMock()
            # Make chaining return query
            query.select.return_value = query
            query.eq.return_value = query
            query.neq.return_value = query
            query.in_.return_value = query

            if table_name == "workspaces":
                query.execute = AsyncMock(return_value=MagicMock(data=workspaces if workspaces is not None else []))
            elif table_name == "campaign_execution_states":
                query.execute = AsyncMock(return_value=MagicMock(data=active_states if active_states is not None else []))
            elif table_name == "leads":
                query.execute = AsyncMock(return_value=MagicMock(data=leads if leads is not None else []))
            else:
                query.execute = AsyncMock(return_value=MagicMock(data=[]))
            return query

        mock_client.table.side_effect = table_side_effect
        return mock_client

    def _create_mock_sync_supabase(self, workspace_token=None):
        """Creates a sync supabase client mock supporting tables and RPCs."""
        mock_client = MagicMock()

        tables = {}

        def table_side_effect(table_name):
            if table_name not in tables:
                t = MagicMock()
                t.select.return_value = t
                t.eq.return_value = t
                t.neq.return_value = t
                t.update.return_value = t
                t.insert.return_value = t
                if table_name == "workspaces" and workspace_token:
                    t.execute.return_value = MagicMock(data=[{"hubspot_token": workspace_token}])
                else:
                    t.execute.return_value = MagicMock(data=[])
                tables[table_name] = t
            return tables[table_name]

        mock_client.table.side_effect = table_side_effect
        mock_client._tables = tables

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data={"inserted_count": 1})
        mock_client.rpc.return_value = rpc_mock

        return mock_client

    # =========================================================================
    # Test 1: Batch deal read API is used (N+1 Elimination)
    # =========================================================================
    @patch("integrations.backend.services.hubspot_sync.async_external_request", new_callable=AsyncMock)
    async def test_sync_hubspot_deals_batch_read(self, mock_request):
        """
        Layer 0: Uses HubSpot CRM v3 Batch Read API (POST /crm/v3/objects/deals/batch/read)
        reducing HTTP calls by 99% (up to 100 deals per call).
        """
        workspaces = [{
            "id": self.workspace_id,
            "hubspot_token": self.token,
            "hubspot_won_stage_id": self.won_stage_id
        }]
        active_states = [
            {"opportunity_id": "lead-1"},
            {"opportunity_id": "lead-2"}
        ]
        leads = [
            {"id": "lead-1", "hubspot_deal_id": "deal-101"},
            {"id": "lead-2", "hubspot_deal_id": "deal-102"}
        ]

        async_sb = self._create_mock_async_supabase(workspaces, active_states, leads)
        sync_sb = self._create_mock_sync_supabase()

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "results": [
                {"id": "deal-101", "properties": {"dealstage": "appointmentscheduled"}},
                {"id": "deal-102", "properties": {"dealstage": "qualifiedtobuy"}}
            ]
        }
        mock_request.return_value = mock_resp

        await sync_hubspot_deals_job(async_sb, sync_sb)

        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        self.assertEqual(call_args[0], "POST")
        self.assertEqual(call_args[1], "https://api.hubapi.com/crm/v3/objects/deals/batch/read")
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], f"Bearer {self.token}")

        batch_inputs = call_kwargs["json_data"]["inputs"]
        self.assertEqual(len(batch_inputs), 2)
        input_ids = {item["id"] for item in batch_inputs}
        self.assertEqual(input_ids, {"deal-101", "deal-102"})

    # =========================================================================
    # Test 2: Halts outreach when deal reaches won stage
    # =========================================================================
    @patch("integrations.backend.services.hubspot_sync._pause_lead_execution_core")
    @patch("integrations.backend.services.hubspot_sync.async_external_request", new_callable=AsyncMock)
    async def test_sync_hubspot_deals_pauses_won_deals(self, mock_request, mock_pause):
        """
        Layer 0 & 1: Deal returns dealstage == won_stage_id -> _pause_lead_execution_core
        is invoked with status_override='exited' and error_reason_override='hubspot_deal_won'.
        """
        workspaces = [{
            "id": self.workspace_id,
            "hubspot_token": self.token,
            "hubspot_won_stage_id": self.won_stage_id
        }]
        active_states = [{"opportunity_id": "lead-1"}]
        leads = [{"id": "lead-1", "hubspot_deal_id": "deal-won-1"}]

        async_sb = self._create_mock_async_supabase(workspaces, active_states, leads)
        sync_sb = self._create_mock_sync_supabase()

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "results": [
                {"id": "deal-won-1", "properties": {"dealstage": self.won_stage_id}}
            ]
        }
        mock_request.return_value = mock_resp

        await sync_hubspot_deals_job(async_sb, sync_sb)

        mock_pause.assert_called_once_with(
            "lead-1",
            self.workspace_id,
            sync_sb,
            status_override="exited",
            error_reason_override="hubspot_deal_won"
        )

    # =========================================================================
    # Test 3: Skips HubSpot polling when no active execution states exist
    # =========================================================================
    @patch("integrations.backend.services.hubspot_sync.async_external_request", new_callable=AsyncMock)
    async def test_sync_hubspot_deals_skips_when_no_active_executions(self, mock_request):
        """
        Layer 1 Paranoia: Only polls deals for leads with ACTIVE in-flight execution states.
        If zero active executions exist, zero HTTP requests are fired.
        """
        workspaces = [{
            "id": self.workspace_id,
            "hubspot_token": self.token,
            "hubspot_won_stage_id": self.won_stage_id
        }]
        active_states = []  # No in-flight executions
        leads = [{"id": "lead-1", "hubspot_deal_id": "deal-101"}]

        async_sb = self._create_mock_async_supabase(workspaces, active_states, leads)
        sync_sb = self._create_mock_sync_supabase()

        await sync_hubspot_deals_job(async_sb, sync_sb)

        mock_request.assert_not_called()

    # =========================================================================
    # Test 4: Handles 401 token expiry and queues outbox in-app notification
    # =========================================================================
    @patch("integrations.backend.services.hubspot_sync.async_external_request", new_callable=AsyncMock)
    async def test_sync_hubspot_deals_handles_401_token_expiry(self, mock_request):
        """
        Layer 1 & 2 Paranoia: Handles 401/403 (token revoked/expired) by queuing an outbox in-app
        alert and breaking cleanly without hammering expired tokens.
        """
        workspaces = [{
            "id": self.workspace_id,
            "hubspot_token": self.token,
            "hubspot_won_stage_id": self.won_stage_id
        }]
        active_states = [{"opportunity_id": "lead-1"}]
        leads = [{"id": "lead-1", "hubspot_deal_id": "deal-101"}]

        async_sb = self._create_mock_async_supabase(workspaces, active_states, leads)
        sync_sb = self._create_mock_sync_supabase()

        mock_resp = MagicMock(status_code=401, text="Unauthorized: Token expired")
        mock_request.return_value = mock_resp

        await sync_hubspot_deals_job(async_sb, sync_sb)

        mock_request.assert_called_once()
        outbox_table = sync_sb._tables.get("outbox_events")
        self.assertIsNotNone(outbox_table)
        outbox_table.insert.assert_called_once()
        inserted_payload = outbox_table.insert.call_args[0][0]
        self.assertEqual(inserted_payload["workspace_id"], self.workspace_id)
        self.assertEqual(inserted_payload["event_type"], "notification.in_app")
        self.assertEqual(inserted_payload["payload"]["title"], "HubSpot Connection Expired")

    # =========================================================================
    # Test 5: Handles 429 rate limit backoff gracefully
    # =========================================================================
    @patch("integrations.backend.services.hubspot_sync.async_external_request", new_callable=AsyncMock)
    async def test_sync_hubspot_deals_handles_429_rate_limiting(self, mock_request):
        """
        Layer 1 Paranoia: Handles 429 rate limits without crashing the worker or loop.
        """
        workspaces = [{
            "id": self.workspace_id,
            "hubspot_token": self.token,
            "hubspot_won_stage_id": self.won_stage_id
        }]
        active_states = [{"opportunity_id": "lead-1"}]
        leads = [{"id": "lead-1", "hubspot_deal_id": "deal-101"}]

        async_sb = self._create_mock_async_supabase(workspaces, active_states, leads)
        sync_sb = self._create_mock_sync_supabase()

        mock_resp = MagicMock(status_code=429, text="Rate limit exceeded")
        mock_request.return_value = mock_resp

        # Must execute cleanly without unhandled exception
        await sync_hubspot_deals_job(async_sb, sync_sb)
        mock_request.assert_called_once()

    # =========================================================================
    # Test 6: Background list import chunks and sanitizes text & deduplicates URLs
    # =========================================================================
    @patch("integrations.backend.services.hubspot_worker.async_external_request", new_callable=AsyncMock)
    async def test_import_hubspot_list_bg_chunks_and_sanitizes(self, mock_request):
        """
        Layer 0 & 1: Imports via bulk_import_leads RPC, sanitizes control chars/NUL bytes,
        and deduplicates LinkedIn URLs within the batch.
        """
        sync_sb = self._create_mock_sync_supabase(workspace_token=self.token)

        dirty_contacts = [
            {
                "properties": {
                    "firstname": {"value": "Alice\x00Smith"},
                    "lastname": {"value": "Doe\t"},
                    "company": {"value": "Acme Corp\x1f"},
                    "linkedin": {"value": "https://linkedin.com/in/alice-doe"},
                    "city": {"value": "San Francisco"}
                }
            },
            # Duplicate linkedin profile
            {
                "properties": {
                    "firstname": {"value": "Alice Duplicate"},
                    "lastname": {"value": "Doe"},
                    "company": {"value": "Acme Corp"},
                    "linkedin": {"value": "https://linkedin.com/in/alice-doe"},
                    "city": {"value": "San Francisco"}
                }
            },
            # Unique profile
            {
                "properties": {
                    "firstname": {"value": "Bob"},
                    "lastname": {"value": "Jones"},
                    "company": {"value": "Beta LLC"},
                    "linkedin": {"value": "https://linkedin.com/in/bobjones"},
                    "city": {"value": "New York"}
                }
            }
        ]

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "contacts": dirty_contacts,
            "has-more": False,
            "vid-offset": 0
        }
        mock_request.return_value = mock_resp

        await import_hubspot_list_bg(sync_sb, self.workspace_id, 999, "lead-list-uuid-1")

        # Verify bulk_import_leads RPC called
        sync_sb.rpc.assert_called_once()
        rpc_call_args = sync_sb.rpc.call_args[0]
        self.assertEqual(rpc_call_args[0], "bulk_import_leads")
        payload = rpc_call_args[1]
        self.assertEqual(payload["p_list_id"], "lead-list-uuid-1")
        self.assertEqual(payload["p_workspace_id"], self.workspace_id)

        leads = payload["p_leads"]
        # Duplicate LinkedIn URL was deduplicated: 3 contacts -> 2 leads
        self.assertEqual(len(leads), 2)

        # Sanitization check: NUL bytes and control characters stripped
        first_lead = leads[0]
        self.assertNotIn("\x00", first_lead["first_name"])
        self.assertEqual(first_lead["first_name"], "AliceSmith")
        self.assertNotIn("\x1f", first_lead["company_name"])
        self.assertEqual(first_lead["company_name"], "Acme Corp")

        # Verify lead_lists marked completed
        lead_lists_table = sync_sb._tables.get("lead_lists")
        self.assertIsNotNone(lead_lists_table)
        update_calls = lead_lists_table.update.call_args_list
        completed_call = [c for c in update_calls if c[0][0].get("status") == "completed"]
        self.assertTrue(len(completed_call) > 0)

    # =========================================================================
    # Test 7: Enforces MAX_HUBSPOT_IMPORT_CONTACTS safety ceiling
    # =========================================================================
    @patch("integrations.backend.services.hubspot_worker.async_external_request", new_callable=AsyncMock)
    async def test_import_hubspot_list_bg_enforces_safety_ceiling(self, mock_request):
        """
        Layer 1 Paranoia: Enforces safety ceiling preventing OOM attacks or infinite pagination.
        """
        sync_sb = self._create_mock_sync_supabase(workspace_token=self.token)

        # Generate a page of 100 contacts
        page_contacts = [
            {
                "properties": {
                    "firstname": {"value": f"User{i}"},
                    "lastname": {"value": "Test"},
                    "company": {"value": "Corp"},
                    "linkedin": {"value": f"https://linkedin.com/in/user-{i}"},
                    "city": {"value": "City"}
                }
            }
            for i in range(100)
        ]

        def get_mock_page(*args, **kwargs):
            resp = MagicMock(status_code=200)
            resp.json.return_value = {
                "contacts": page_contacts,
                "has-more": True,
                "vid-offset": 100
            }
            return resp

        mock_request.side_effect = get_mock_page

        # Set ceiling to 150 contacts
        with patch.dict(os.environ, {"MAX_HUBSPOT_IMPORT_CONTACTS": "150"}):
            await import_hubspot_list_bg(sync_sb, self.workspace_id, 999, "lead-list-uuid-2")

        # After page 1 (100 contacts) < 150 -> fetches page 2 (total 200 contacts >= 150) -> breaks!
        # Should not fetch a 3rd page
        self.assertEqual(mock_request.call_count, 2)

    # =========================================================================
    # Test 8: Handles 401 token expiry on list import
    # =========================================================================
    @patch("integrations.backend.services.hubspot_worker.async_external_request", new_callable=AsyncMock)
    async def test_import_hubspot_list_bg_handles_401(self, mock_request):
        """
        Layer 2 Paranoia: On 401/403 token expiry, marks list 'failed' with actionable message
        and queues an outbox in-app notification.
        """
        sync_sb = self._create_mock_sync_supabase(workspace_token=self.token)

        mock_resp = MagicMock(status_code=401, text="Unauthorized: Revoked Token")
        mock_request.return_value = mock_resp

        with self.assertRaises(ValueError) as ctx:
            await import_hubspot_list_bg(sync_sb, self.workspace_id, 999, "lead-list-uuid-3")

        self.assertIn("HubSpot authorization expired or revoked", str(ctx.exception))

        # Check outbox notification queued
        outbox_table = sync_sb._tables.get("outbox_events")
        self.assertIsNotNone(outbox_table)
        outbox_table.insert.assert_called_once()
        inserted = outbox_table.insert.call_args[0][0]
        self.assertEqual(inserted["payload"]["title"], "HubSpot Import Failed")

        # Check lead_lists marked as failed
        lead_lists_table = sync_sb._tables.get("lead_lists")
        self.assertIsNotNone(lead_lists_table)
        update_calls = lead_lists_table.update.call_args_list
        failed_call = [c for c in update_calls if c[0][0].get("status") == "failed"]
        self.assertTrue(len(failed_call) > 0)
        self.assertEqual(failed_call[0][0][0]["row_count"], -2)


if __name__ == "__main__":
    unittest.main()
