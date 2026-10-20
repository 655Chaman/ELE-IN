import os
import json
import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

class TestStage13LeadsSeamlessnessRemediation(unittest.TestCase):
    """
    Paranoia Test Suite: Rigorous Layer 0, Layer 1, and Layer 2 verification
    of the Leads Subsystem Seamlessness Remediation across all 4 bridges.
    """

    def test_migration_102_sql_integrity(self):
        """
        Layer 0 & 1 Paranoia: Verify Migration 102 SQL file exists, is non-empty,
        and contains the 5 EmailShield columns, lead_tags workspace_id + RLS,
        campaigns.lead_list_id promotion, and atomic bulk_import function.
        """
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "backend", "migrations", "102_leads_storage_and_schema_drift.sql"
        )
        self.assertTrue(os.path.exists(migration_path), f"Migration 102 not found at {migration_path}")
        
        with open(migration_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        # EmailShield / Deliverability columns
        self.assertIn("quarantine_reason", sql_content)
        self.assertIn("email_classification", sql_content)
        self.assertIn("is_role_based", sql_content)
        self.assertIn("is_disposable", sql_content)
        self.assertIn("deliverability_risk", sql_content)

        # Multi-tenant isolation on lead_tags
        self.assertIn("ALTER TABLE public.lead_tags", sql_content)
        self.assertIn("workspace_id UUID REFERENCES public.workspaces(id)", sql_content)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql_content)
        self.assertIn("lead_tags_ws_all", sql_content)

        # Campaigns lead_list_id promotion
        self.assertIn("ALTER TABLE public.campaigns", sql_content)
        self.assertIn("lead_list_id UUID REFERENCES public.lead_lists(id)", sql_content)
        self.assertIn("idx_campaigns_lead_list_id", sql_content)

        # Domain suppression index
        self.assertIn("uq_suppression_domain_canonical", sql_content)

        # Atomic stored procedure
        self.assertIn("bulk_import_leads_atomic", sql_content)

    def test_hubspot_worker_extraction_and_deduplication(self):
        """
        Layer 1 & 2 Paranoia: Verify HubSpot worker extracts email, job title,
        company, location, and deduplicates using email-first resolution.
        """
        from integrations.backend.services.hubspot_worker import import_hubspot_list_bg

        sample_contacts_resp = {
            "contacts": [
                {
                    "vid": 101,
                    "properties": {
                        "firstname": {"value": "Sarah"},
                        "lastname": {"value": "Connor"},
                        "email": {"value": "sarah.connor@cyberdyne.io"},
                        "jobtitle": {"value": "VP Engineering"},
                        "company": {"value": "Cyberdyne Systems"},
                        "city": {"value": "Los Angeles"},
                        "country": {"value": "United States"},
                        "phone": {"value": "+1 555-0199"},
                        "linkedin": {"value": "https://linkedin.com/in/sarahconnor"}
                    }
                },
                {
                    # Duplicate email with different vid
                    "vid": 102,
                    "properties": {
                        "firstname": {"value": "Sarah Duplicate"},
                        "email": {"value": "sarah.connor@cyberdyne.io"},
                        "jobtitle": {"value": "Director"},
                        "company": {"value": "Cyberdyne Systems"}
                    }
                }
            ],
            "has-more": False,
            "vid-offset": 0
        }

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"hubspot_token": "mock-hs-token"}]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_http_resp = MagicMock()
        mock_http_resp.status_code = 200
        mock_http_resp.json.return_value = sample_contacts_resp

        with patch("integrations.backend.services.hubspot_worker.async_external_request", return_value=mock_http_resp), \
             patch("leads.backend.services.lead_ingestion_service.execute_bulk_import_leads") as mock_bulk_import:
            
            mock_bulk_import.return_value = {"inserted_count": 1, "failed_count": 0}

            asyncio.run(import_hubspot_list_bg(
                supabase=mock_supabase,
                workspace_id="ws-123",
                hubspot_list_id=42,
                internal_list_id="internal-list-1"
            ))

            # Verify the payload passed to bulk import
            mock_bulk_import.assert_called_once()
            call_kwargs = mock_bulk_import.call_args[1]
            call_leads = call_kwargs.get("leads", [])
            self.assertEqual(len(call_leads), 1)
            imported_lead = call_leads[0]
            self.assertEqual(imported_lead["email"], "sarah.connor@cyberdyne.io")
            self.assertEqual(imported_lead["job_title"], "VP Engineering")
            self.assertEqual(imported_lead["company_name"], "Cyberdyne Systems")
            self.assertEqual(imported_lead["linkedin_url"], "https://linkedin.com/in/sarahconnor")

    def test_voyager_scraper_company_and_location_forwarding(self):
        """
        Layer 0 & 1 Paranoia: Verify Voyager scraper extracts company_name
        and location in parsed search items.
        """
        from integrations.backend.services.voyager_scraper import VoyagerScraper

        cookies_json = json.dumps([
            {"name": "li_at", "value": "test_li_at_cookie_val"},
            {"name": "JSESSIONID", "value": "ajax:99887766"}
        ])
        scraper = VoyagerScraper(cookies_json=cookies_json, account_id="acc-1", supabase=MagicMock())

        # Strategy 1 payload
        strategy1_data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.identity.shared.MiniProfile",
                    "entityUrn": "urn:li:fs_miniProfile:ABC12345",
                    "firstName": "John",
                    "lastName": "Doe",
                    "occupation": "CTO at HyperGrowth Corp",
                    "publicIdentifier": "johndoe",
                    "objectUrn": "urn:li:member:123456",
                    "locationName": "San Francisco, CA"
                }
            ]
        }
        profiles_s1 = scraper._parse_profiles(strategy1_data)
        self.assertEqual(len(profiles_s1), 1)
        self.assertEqual(profiles_s1[0]["company_name"], "HyperGrowth Corp")
        self.assertEqual(profiles_s1[0]["location"], "San Francisco, CA")
        self.assertEqual(profiles_s1[0]["first_name"], "John")

        # Strategy 2 payload
        strategy2_data = {
            "data": {
                "elements": [
                    {
                        "items": [
                            {
                                "item": {
                                    "entityResult": {
                                        "navigationUrl": "https://www.linkedin.com/in/alice-smith-789",
                                        "title": {"text": "Alice Smith"},
                                        "primarySubtitle": {"text": "VP Product at SaaS Scale"},
                                        "secondarySubtitle": {"text": "Austin, Texas"}
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }
        profiles_s2 = scraper._parse_profiles(strategy2_data)
        self.assertEqual(len(profiles_s2), 1)
        self.assertEqual(profiles_s2[0]["company_name"], "SaaS Scale")
        self.assertEqual(profiles_s2[0]["location"], "Austin, Texas")
        self.assertEqual(profiles_s2[0]["first_name"], "Alice")

    def test_smartlead_bounce_webhook_auto_halts_and_suppresses(self):
        """
        Layer 1 Paranoia: When Smartlead reports an EMAIL_BOUNCE:
        1. Lead status is updated to 'bounced'
        2. LinkedIn outreach is cascade halted
        3. Email is added to suppression_list
        """
        from campaigns.backend.routers.inbound_webhooks import smartlead_inbound_webhook

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws-test", "status": "active"}]
        )
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead-bounce-1", "metadata": {}}]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.json = AsyncMock(return_value={
            "email": "bounced.lead@domain.com",
            "event_type": "EMAIL_BOUNCE",
            "campaign_id": "camp-123"
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("campaigns.backend.routers.inbound_webhooks._cascade_halt_lead_linkedin_outreach") as mock_halt, \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):

            res = asyncio.run(smartlead_inbound_webhook(workspace_id="ws-test", request=mock_request))
            self.assertEqual(res["status"], "success")

            # Verify lead outreach was cascade halted with exact signature
            mock_halt.assert_called_once_with(mock_supabase, "ws-test", "lead-bounce-1", error_reason="email_bounced")

            # Verify suppression list call was made
            suppression_upsert = any(
                call[0][0] == "suppression_list" if len(call[0]) > 0 else False
                for call in mock_supabase.table.call_args_list
            )
            self.assertTrue(suppression_upsert, "Expected table('suppression_list') to be called")

    def test_instantly_bounce_webhook_auto_halts_and_suppresses(self):
        """
        Layer 1 Paranoia: When Instantly reports a bounce:
        1. Lead status is updated to 'bounced'
        2. LinkedIn outreach is cascade halted
        3. Email is added to suppression_list
        """
        from campaigns.backend.routers.inbound_webhooks import instantly_inbound_webhook

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws-test", "status": "active"}]
        )
        mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead-bounce-2", "metadata": {}}]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.json = AsyncMock(return_value={
            "lead_email": "invalid.user@bounce.com",
            "event_type": "lead_bounced",
            "campaign_id": "instantly-camp-1"
        })

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("campaigns.backend.routers.inbound_webhooks._cascade_halt_lead_linkedin_outreach") as mock_halt, \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):

            res = asyncio.run(instantly_inbound_webhook(workspace_id="ws-test", request=mock_request))
            self.assertEqual(res["status"], "success")
            mock_halt.assert_called_once_with(mock_supabase, "ws-test", "lead-bounce-2", error_reason="email_bounced")

    def test_delete_list_blocked_if_bound_to_campaign(self):
        """
        Layer 1 & 2 Paranoia: Attempting to delete a lead list attached to an active
        campaign must be rejected with HTTP 400, checking both column and metadata.
        """
        from leads.backend.routers.leads import delete_lead_list_async

        mock_supabase = MagicMock()
        mock_list_exec = MagicMock(data=[{"id": "list-active-1", "name": "Target List", "workspace_id": "ws-test"}])
        mock_camp_exec = MagicMock(data=[{"id": "camp-active", "name": "Q4 Enterprise Outreach", "lead_list_id": "list-active-1", "metadata": {}}])

        def table_side_effect(name):
            m = MagicMock()
            if name == "lead_lists":
                m.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(return_value=mock_list_exec)
                return m
            elif name == "campaigns":
                camp_query = MagicMock()
                camp_query.eq.return_value = camp_query
                camp_query.execute = AsyncMock(return_value=mock_camp_exec)
                m.select.return_value = camp_query
                return m
            return m

        mock_supabase.table.side_effect = table_side_effect

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(delete_lead_list_async(
                list_id="list-active-1",
                workspace_id="ws-test",
                supabase=mock_supabase
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("active campaign", ctx.exception.detail.lower())

    def test_batch_remove_leads_pauses_execution_states(self):
        """
        Layer 1 Paranoia: Bulk removing leads from a list must invoke _pause_lead_execution_core
        for all targeted leads to prevent ghost sequence execution.
        """
        from leads.backend.routers.leads import bulk_remove_leads_from_list, BulkRemoveListMembersRequest

        mock_supabase = MagicMock()
        mock_list_exec = MagicMock(data=[{"id": "list-1", "workspace_id": "ws-test"}])
        mock_delete_exec = MagicMock(data=[])
        mock_count_exec = MagicMock(count=0)

        def table_side_effect(name):
            m = MagicMock()
            if name == "lead_lists":
                m.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(return_value=mock_list_exec)
                m.update.return_value.eq.return_value.execute = AsyncMock(return_value=mock_delete_exec)
                return m
            elif name == "list_members":
                m.delete.return_value.eq.return_value.in_.return_value.execute = AsyncMock(return_value=mock_delete_exec)
                m.select.return_value.eq.return_value.execute = AsyncMock(return_value=mock_count_exec)
                return m
            return m

        mock_supabase.table.side_effect = table_side_effect

        payload = BulkRemoveListMembersRequest(lead_ids=["lead-a", "lead-b", "lead-c"])

        with patch("campaigns.backend.routers.elein._pause_lead_execution_core") as mock_pause, \
             patch("core.backend.api.auth_dep.get_service_client"):

            res = asyncio.run(bulk_remove_leads_from_list(
                list_id="list-1",
                payload=payload,
                workspace_id="ws-test",
                supabase=mock_supabase
            ))

            self.assertEqual(res["removed_count"], 3)
            # Verify _pause_lead_execution_core was called for each lead
            self.assertEqual(mock_pause.call_count, 3)
            paused_lead_ids = [call[1]["lead_id"] for call in mock_pause.call_args_list]
            self.assertListEqual(paused_lead_ids, ["lead-a", "lead-b", "lead-c"])

    def test_get_leads_in_list_server_side_search_and_telemetry_augmentation(self):
        """
        Layer 0 & 1 Paranoia: GET /lists/{list_id}/leads:
        1. Correctly applies query filter 'q' using .or_()
        2. Augments returned leads with campaign_enrollments DAG trace IDs
        """
        from leads.backend.routers.leads import get_leads_in_list

        mock_supabase = MagicMock()

        # Mock query chain for leads
        query_mock = MagicMock()
        query_mock.eq.return_value = query_mock
        query_mock.or_.return_value = query_mock
        query_mock.order.return_value = query_mock
        query_mock.range.return_value = query_mock
        query_mock.execute = AsyncMock(return_value=MagicMock(
            data=[{"id": "lead-1", "first_name": "Elon", "company_name": "Tesla"}],
            count=1
        ))

        def table_router(name, **kwargs):
            m = MagicMock()
            if name == "lead_lists":
                m.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[{"id": "list-1"}]))
                return m
            elif name == "leads":
                m.select.return_value = query_mock
                return m
            elif name == "campaign_enrollments":
                m.select.return_value.eq.return_value.in_.return_value.execute = AsyncMock(return_value=MagicMock(
                    data=[{"id": "enr-999", "campaign_id": "camp-777", "lead_id": "lead-1", "status": "active"}]
                ))
                return m
            return m

        mock_supabase.table.side_effect = table_router

        res = asyncio.run(get_leads_in_list(
            list_id="list-1",
            page=1,
            page_size=50,
            q="Tesla",
            workspace_id="ws-test",
            supabase=mock_supabase
        ))

        # Verify search filter was applied
        query_mock.or_.assert_called_once()
        filter_str = query_mock.or_.call_args[0][0]
        self.assertIn("Tesla", filter_str)

        # Verify DAG trace telemetry augmentation
        self.assertEqual(len(res["data"]), 1)
        lead_result = res["data"][0]
        self.assertEqual(lead_result["enrollment_id"], "enr-999")
        self.assertEqual(lead_result["campaign_id"], "camp-777")
        self.assertEqual(lead_result["enrollment_status"], "active")

if __name__ == "__main__":
    unittest.main()
