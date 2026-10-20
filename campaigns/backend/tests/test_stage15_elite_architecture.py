"""
test_stage15_elite_architecture.py

Stage 15 Elite Architecture & Resilience Suite:
- Dynamic Lead Segmentation Batch Idempotency (upsert on_conflict with fallback)
- CRM Client Shadowing & Credit Refund Fail-Safe (HubSpot, Salesforce, Pipedrive)
- Vault Credential Quarantine & 429 Backoff / RateLimitExceeded Propagation
- Apollo Rate-Limit Quota Guards (ApolloRateLimitException & safe credit refunds)
- Lead List Deletion Lockdown against RUNNING and SCHEDULED Campaigns

Adheres strictly to the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from leads.backend.services.lead_segmentation_service import sync_dynamic_segment_members
from integrations.backend.services.elein_crm_service import (
    push_to_hubspot,
    push_to_salesforce,
    push_to_pipedrive,
    add_to_apollo,
    enrich_with_apollo,
    RateLimitExceeded,
    ApolloRateLimitException,
)
from leads.backend.routers.leads import delete_lead_list_async
from campaigns.backend.routers.elein import delete_lead_list


class TestStage15EliteArchitecture(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.workspace_id = "ws-stage15-corp"
        self.list_id = "list-stage15-target"

    # =========================================================================
    # 1. Dynamic Lead Segmentation Batch Idempotency
    # =========================================================================
    def test_lead_segmentation_batch_idempotency_upsert(self):
        """Layer 1: sync_dynamic_segment_members performs conflict-tolerant upsert on list_members."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.update.return_value = mock_table

        # 1. lead_lists select
        # 2. leads select (1 qualifying lead)
        # 3. current list_members (currently empty)
        # 4. list_members upsert
        # 5. lead_lists update row_count
        mock_table.execute.side_effect = [
            MagicMock(data=[{
                "id": self.list_id,
                "name": "Stage 15 Dynamic Segment",
                "type": "dynamic",
                "metadata": {
                    "dynamic_rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "job_title", "operator": "equals", "value": "CTO"}]
                    }
                }
            }]),
            MagicMock(data=[
                {"id": "lead_stage15_cto", "job_title": "CTO", "workspace_id": self.workspace_id}
            ]),
            MagicMock(data=[]),
            MagicMock(data=[{"list_id": self.list_id, "opportunity_id": "lead_stage15_cto"}]),
            MagicMock(data=[])
        ]

        res = sync_dynamic_segment_members(
            list_id=self.list_id,
            workspace_id=self.workspace_id,
            supabase=mock_supabase,
            auto_enroll=False
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["qualified_leads_count"], 1)
        self.assertEqual(res["added_to_list"], 1)

        # Verify that upsert was called with on_conflict and ignore_duplicates
        mock_table.upsert.assert_called_once()
        upsert_kwargs = mock_table.upsert.call_args[1]
        self.assertEqual(upsert_kwargs.get("on_conflict"), "list_id,opportunity_id")
        self.assertTrue(upsert_kwargs.get("ignore_duplicates"))

    def test_lead_segmentation_upsert_fallback_to_insert(self):
        """Layer 1: If upsert raises an error, sync_dynamic_segment_members gracefully falls back to insert."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.update.return_value = mock_table

        mock_table.upsert.side_effect = RuntimeError("Upsert not supported on legacy schema")

        mock_table.execute.side_effect = [
            MagicMock(data=[{
                "id": self.list_id,
                "name": "Stage 15 Fallback Segment",
                "type": "dynamic",
                "metadata": {
                    "dynamic_rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "job_title", "operator": "equals", "value": "VP"}]
                    }
                }
            }]),
            MagicMock(data=[
                {"id": "lead_stage15_vp", "job_title": "VP", "workspace_id": self.workspace_id}
            ]),
            MagicMock(data=[]),
            # list_members insert execution
            MagicMock(data=[{"list_id": self.list_id, "opportunity_id": "lead_stage15_vp"}]),
            # lead_lists update row_count execution
            MagicMock(data=[])
        ]

        res = sync_dynamic_segment_members(
            list_id=self.list_id,
            workspace_id=self.workspace_id,
            supabase=mock_supabase,
            auto_enroll=False
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["added_to_list"], 1)
        mock_table.insert.assert_called_once()

    # =========================================================================
    # 2. HubSpot Client Preservation & Safe Credit Refund
    # =========================================================================
    @patch("integrations.backend.services.credential_vault.vault.resolve_credential", return_value="hubspot_token_abc")
    @patch("integrations.backend.services.credential_vault.vault.quarantine_credential")
    @patch("integrations.backend.services.elein_crm_service._safe_refund_credits")
    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_hubspot_push_client_preservation_and_refund_on_401(self, mock_post, mock_refund, mock_quarantine, mock_resolve):
        """Layer 1 & 2: HubSpot 401 quarantines vault credential and preserves supabase client for refund."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad token"
        mock_post.return_value = mock_response

        mock_supabase = MagicMock()
        mock_rpc_res = MagicMock()
        mock_rpc_res.data = {"success": True}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc_res

        lead_data = {"id": "lead_hs_101", "first_name": "Sarah", "email": "sarah@hubspot.io"}

        success = push_to_hubspot(
            workspace_id=self.workspace_id,
            lead_data=lead_data,
            api_key=None,
            supabase=mock_supabase
        )

        self.assertFalse(success)
        mock_quarantine.assert_called_once_with(self.workspace_id, "hubspot", "HTTP 401 Unauthorized")
        mock_refund.assert_called_once()
        # Verify that the preserved client passed into push_to_hubspot was supplied to _safe_refund_credits
        refund_args = mock_refund.call_args[0]
        self.assertEqual(refund_args[0], self.workspace_id)
        self.assertEqual(refund_args[1], 1)
        self.assertEqual(refund_args[3], mock_supabase)

    # =========================================================================
    # 3. Salesforce & Pipedrive Vault Quarantine and 429 Handling
    # =========================================================================
    @patch("integrations.backend.services.credential_vault.vault.resolve_credential")
    @patch("integrations.backend.services.credential_vault.vault.quarantine_credential")
    @patch("integrations.backend.services.elein_crm_service._safe_refund_credits")
    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_salesforce_vault_quarantine_and_rate_limit(self, mock_post, mock_refund, mock_quarantine, mock_resolve):
        """Layer 1: Salesforce 401 quarantines credential; 429 raises RateLimitExceeded with safe refund."""
        def resolve_side_effect(ws, provider, env_fallback=None, supabase_client=None):
            if provider == "salesforce": return "sf_access_token_123"
            if provider == "salesforce_instance": return "https://na101.salesforce.com"
            return None
        mock_resolve.side_effect = resolve_side_effect

        mock_supabase = MagicMock()
        mock_rpc_res = MagicMock()
        mock_rpc_res.data = {"success": True}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc_res

        lead_data = {"id": "lead_sf_1", "first_name": "Marc", "last_name": "Benioff", "email": "marc@salesforce.com"}

        # 1. 401 Unauthorized -> Quarantines credential and refunds credit
        mock_res_401 = MagicMock(status_code=401, text="Session expired or invalid")
        mock_post.return_value = mock_res_401

        success = push_to_salesforce(self.workspace_id, lead_data, supabase=mock_supabase)
        self.assertFalse(success)
        mock_quarantine.assert_called_once_with(self.workspace_id, "salesforce", "HTTP 401 Unauthorized")
        mock_refund.assert_called_once()

        mock_refund.reset_mock()
        mock_quarantine.reset_mock()

        # 2. 429 Too Many Requests -> Raises RateLimitExceeded and refunds credit
        mock_res_429 = MagicMock(status_code=429, text="Rate limit exceeded")
        mock_post.return_value = mock_res_429

        with self.assertRaises(RateLimitExceeded):
            push_to_salesforce(self.workspace_id, lead_data, supabase=mock_supabase)
        mock_refund.assert_called_once()

    @patch("integrations.backend.services.credential_vault.vault.resolve_credential", return_value="pipedrive_key_789")
    @patch("integrations.backend.services.credential_vault.vault.quarantine_credential")
    @patch("integrations.backend.services.elein_crm_service._safe_refund_credits")
    @patch("integrations.backend.services.elein_crm_service.requests.post")
    def test_pipedrive_vault_quarantine_and_rate_limit(self, mock_post, mock_refund, mock_quarantine, mock_resolve):
        """Layer 1: Pipedrive 401 quarantines credential; 429 raises RateLimitExceeded with safe refund."""
        mock_supabase = MagicMock()
        mock_rpc_res = MagicMock()
        mock_rpc_res.data = {"success": True}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc_res

        lead_data = {"id": "lead_pd_1", "first_name": "Timo", "email": "timo@pipedrive.com"}

        # 1. 401 Unauthorized -> Quarantines key
        mock_post.return_value = MagicMock(status_code=401, text="Invalid api_token")
        success = push_to_pipedrive(self.workspace_id, lead_data, supabase=mock_supabase)
        self.assertFalse(success)
        mock_quarantine.assert_called_once_with(self.workspace_id, "pipedrive", "HTTP 401 Unauthorized")
        mock_refund.assert_called_once()

        mock_refund.reset_mock()
        mock_quarantine.reset_mock()

        # 2. 429 Rate Limit -> Raises RateLimitExceeded
        mock_post.return_value = MagicMock(status_code=429, text="Usage limit reached")
        with self.assertRaises(RateLimitExceeded):
            push_to_pipedrive(self.workspace_id, lead_data, supabase=mock_supabase)
        mock_refund.assert_called_once()

    # =========================================================================
    # 4. Apollo Rate-Limit Quota Guard
    # =========================================================================
    @patch("integrations.backend.services.credential_vault.vault.resolve_credential", return_value="apollo_api_key_xyz")
    @patch("integrations.backend.services.elein_crm_service._safe_refund_credits")
    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    def test_add_to_apollo_rate_limit_quota_guard(self, mock_resilience, mock_refund, mock_resolve):
        """Layer 1: add_to_apollo raises ApolloRateLimitException and safely refunds deducted credits on 429."""
        mock_resilience.return_value = MagicMock(status_code=429, text="Apollo hourly rate limit reached")

        mock_supabase = MagicMock()
        mock_rpc_res = MagicMock()
        mock_rpc_res.data = {"success": True}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc_res

        lead_data = {"id": "lead_apollo_1", "first_name": "Tim", "email": "tim@apple.com"}

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            with self.assertRaises(ApolloRateLimitException):
                add_to_apollo(self.workspace_id, lead_data)

        mock_refund.assert_called_once()

    @patch("integrations.backend.services.credential_vault.vault.resolve_credential", return_value="apollo_api_key_xyz")
    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    def test_enrich_with_apollo_rate_limit_handling(self, mock_resilience, mock_resolve):
        """Layer 1: enrich_with_apollo returns None by default on 429, or raises ApolloRateLimitException when asked."""
        mock_resilience.return_value = MagicMock(status_code=429, text="Apollo quota exceeded")

        # Default caller invocation does not crash
        res = enrich_with_apollo(workspace_id=self.workspace_id, lead_data={"first_name": "Satya", "domain": "microsoft.com"})
        self.assertIsNone(res)

        # Explicit raise_on_rate_limit raises ApolloRateLimitException
        with self.assertRaises(ApolloRateLimitException):
            enrich_with_apollo(
                workspace_id=self.workspace_id,
                lead_data={"first_name": "Satya", "domain": "microsoft.com"},
                raise_on_rate_limit=True
            )

    # =========================================================================
    # 5. Lead List Deletion Lockdown against RUNNING and SCHEDULED Campaigns
    # =========================================================================
    def test_leads_deletion_blocked_by_running_and_scheduled_campaigns(self):
        """Layer 1 & 2: Both async and sync list deletion block lists assigned to RUNNING or SCHEDULED campaigns."""
        # 1. Test synchronous delete_lead_list (elein.py) with RUNNING campaign
        mock_sync_supabase = MagicMock()
        mock_sync_table = MagicMock()
        mock_sync_supabase.table.return_value = mock_sync_table
        mock_sync_table.select.return_value = mock_sync_table
        mock_sync_table.eq.return_value = mock_sync_table
        mock_sync_table.in_.return_value = mock_sync_table

        # 1. lead_lists select
        # 2. campaigns select (active query returns empty)
        # 3. campaigns select (scheduled/running query returns RUNNING campaign)
        mock_sync_table.execute.side_effect = [
            MagicMock(data=[{"id": self.list_id, "name": "Enterprise Accounts"}]),
            MagicMock(data=[]),
            MagicMock(data=[{"id": "camp_run_1", "name": "Scale Inbound", "status": "RUNNING"}])
        ]

        with self.assertRaises(HTTPException) as ctx:
            delete_lead_list(list_id=self.list_id, workspace_id=self.workspace_id, supabase=mock_sync_supabase)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Enterprise Accounts", ctx.exception.detail)
        self.assertIn("Scale Inbound", ctx.exception.detail)

    async def test_leads_async_deletion_blocked_by_scheduled_campaign(self):
        """Layer 1: Async delete_lead_list_async (leads.py) blocks deletion when campaign is SCHEDULED."""
        class MockAsyncQuery:
            def __init__(self, data=None):
                self._data = data or []
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def in_(self, *a, **k): return self
            def delete(self, *a, **k): return self
            async def execute(self):
                res = MagicMock()
                res.data = self._data
                return res

        mock_supabase = MagicMock()
        list_query = MockAsyncQuery(data=[{"id": self.list_id, "name": "EMEA Prospects"}])
        camp_query = MockAsyncQuery(data=[{"id": "camp_sched_1", "name": "Q4 EMEA Sequence", "status": "SCHEDULED"}])

        def table_router(t):
            if t == "lead_lists": return list_query
            return camp_query

        mock_supabase.table.side_effect = table_router

        with self.assertRaises(HTTPException) as ctx:
            await delete_lead_list_async(
                list_id=self.list_id,
                workspace_id=self.workspace_id,
                supabase=mock_supabase
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("EMEA Prospects", ctx.exception.detail)
        self.assertIn("Q4 EMEA Sequence", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
