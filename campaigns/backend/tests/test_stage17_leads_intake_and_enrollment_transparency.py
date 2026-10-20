import io
import os
import unittest
from unittest.mock import MagicMock, patch

from leads.backend.services.data_hygiene import DataHygieneService
from campaigns.backend.routers.elein import (
    upload_urls,
    UploadUrlsRequest,
    enroll_list_leads,
    EnrollListRequest
)
from fastapi import BackgroundTasks


class TestStage17LeadsIntakeAndEnrollmentTransparency(unittest.TestCase):
    """
    Stage 17 Paranoia Test Suite:
    Validates Intake Pipeline Resilience, Formula Injection Sanitization on Tokens,
    Async URL Offloading, and Enrollment Breakdown Transparency:
    - Layer 0: Name and company cleaning strips quotes so formula defenses never leak into copy.
    - Layer 1: upload_urls offloads >100 URLs to BackgroundTasks to prevent HTTP 504 timeouts.
    - Layer 2: enroll_list_leads returns exact counts of enrolled, colliding, and suppressed leads.
    """

    def test_layer0_clean_name_and_company_strip_quotes_preventing_copy_leakage(self):
        """
        Layer 0 Foundational (B1-F09):
        Names and companies pre-processed by formula injection defense or wrapped in CSV quotes
        (e.g., "'=John", "'Sarah'", "\"-Acme Corp-\"") must have leading and trailing single/double
        quotes stripped cleanly so they never leak into outreach emails (e.g. "Hi 'John").
        """
        # Test names with quotes and formula triggers
        self.assertEqual(DataHygieneService.clean_name("'John"), "John")
        self.assertEqual(DataHygieneService.clean_name('"Sarah"'), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("'-Alexander'"), "Alexander")

        # Test first name extraction
        self.assertEqual(DataHygieneService.clean_first_name("'Ada Lovelace'"), "Ada")
        self.assertEqual(DataHygieneService.clean_first_name('"Grace Hopper"'), "Grace")

        # Test company cleaning
        self.assertEqual(DataHygieneService.clean_company("'-Apple, Inc.-'"), "Apple")
        self.assertEqual(DataHygieneService.clean_company('"Acme Corporation"'), "Acme")
        self.assertEqual(DataHygieneService.clean_company("'AWS'"), "AWS")

    def test_layer1_upload_urls_offloads_large_batches_to_background_tasks(self):
        """
        Layer 1 Paranoia (B1-F06):
        Uploading large batches of raw profile URLs (>100) must offload processing
        to FastAPI BackgroundTasks, returning status='processing' immediately
        to prevent HTTP 504 Gateway Timeouts.
        """
        mock_supabase = MagicMock()
        mock_bg_tasks = MagicMock()

        # Generate 150 unique profile URLs
        raw_urls = [f"https://www.linkedin.com/in/prospect-{i}" for i in range(150)]

        req = UploadUrlsRequest(
            name="Large Scale Outbound",
            urls=raw_urls,
            target_timezone="UTC",
            target_region_label="Auto-detect / Multi-region"
        )

        res = upload_urls(
            body=req,
            supabase=mock_supabase,
            workspace_id="ws-stage17-async",
            user_id="user-stage17",
            background_tasks=mock_bg_tasks
        )

        # Verified it returns processing state immediately
        self.assertEqual(res["status"], "processing")
        self.assertEqual(res["row_count"], 150)
        self.assertIsNotNone(res["list_id"])

        # Verified background_tasks.add_task was called with the async importer
        mock_bg_tasks.add_task.assert_called_once()

    def test_layer1_upload_urls_small_batch_executes_synchronously(self):
        """
        Layer 1 Paranoia:
        Small batches (<=100 URLs) execute synchronously so users get instant row counts
        and feedback without unnecessary async polling.
        """
        mock_supabase = MagicMock()
        mock_bg_tasks = MagicMock()

        raw_urls = [
            "https://www.linkedin.com/in/immediate-1",
            "https://www.linkedin.com/in/immediate-2"
        ]

        req = UploadUrlsRequest(
            name="Boutique High Priority",
            urls=raw_urls,
            target_timezone="America/New_York",
            target_region_label="US East"
        )

        with patch("leads.backend.services.lead_ingestion_service.execute_bulk_import_leads", return_value={
            "inserted_count": 2, "duplicate_count": 0, "colliding_count": 0
        }):
            res = upload_urls(
                body=req,
                supabase=mock_supabase,
                workspace_id="ws-stage17-sync",
                user_id="user-stage17",
                background_tasks=mock_bg_tasks
            )

        self.assertEqual(res["row_count"], 2)
        self.assertEqual(res["duplicate_count"], 0)
        self.assertNotIn("status", res)
        # Background task was NOT scheduled for small batches
        mock_bg_tasks.add_task.assert_not_called()

    def test_layer2_enroll_list_leads_transparent_collision_and_suppression_breakdown(self):
        """
        Layer 2 Paranoia (B3-F08):
        enroll_list_leads must return exact counts for:
        - enrolled: Leads cleanly added to campaign execution states
        - skipped: Leads skipped due to suppression / DNC
        - collisions: Leads skipped due to active enrollment in conflicting campaigns
        """
        mock_supabase = MagicMock()

        # Mock campaign lookup
        mock_camp_data = [{"id": "camp-test-1", "lead_list_id": "list-input-1"}]
        # Mock lead list lookup
        mock_list_data = [{"id": "list-input-1", "name": "Target List", "workspace_id": "ws-transparency"}]

        # Candidate leads: 3 leads total
        # lead-1: Valid, enrolls cleanly
        # lead-2: Colliding in another campaign
        # lead-3: Suppressed (DNC)
        candidate_opps = ["lead-1", "lead-2", "lead-3"]
        leads_db = [
            {"id": "lead-1", "linkedin_url": "https://linkedin.com/in/lead1", "email": "lead1@corp.com", "domain": "corp.com"},
            {"id": "lead-2", "linkedin_url": "https://linkedin.com/in/lead2", "email": "lead2@corp.com", "domain": "corp.com"},
            {"id": "lead-3", "linkedin_url": "https://linkedin.com/in/lead3", "email": "lead3@rival.com", "domain": "rival.com"},
        ]

        def router_table(name):
            m = MagicMock()
            if name == "campaigns":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=mock_camp_data)
                return m
            elif name == "lead_lists":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=mock_list_data)
                return m
            elif name == "list_members":
                m.select.return_value.eq.return_value.range.return_value.execute.return_value = MagicMock(
                    data=[{"lead_id": cid} for cid in candidate_opps]
                )
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"lead_id": cid} for cid in candidate_opps]
                )
                return m
            elif name == "leads":
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=leads_db)
                m.update.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                return m
            elif name == "suppression_list":
                # lead-3 is suppressed
                def mock_select(field):
                    s = MagicMock()
                    def mock_eq(w_field, w_val):
                        e = MagicMock()
                        def mock_in(f_name, chunk):
                            r = MagicMock()
                            if "rival.com" in chunk:
                                r.execute.return_value = MagicMock(data=[{"domain": "rival.com"}])
                            else:
                                r.execute.return_value = MagicMock(data=[])
                            return r
                        e.in_ = mock_in
                        return e
                    s.eq = mock_eq
                    return s
                m.select = mock_select
                return m
            elif name == "campaign_enrollments":
                # No leads enrolled in THIS campaign yet
                def mock_select(fields):
                    s = MagicMock()
                    s.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                    s.eq.return_value.neq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                    return s
                m.select = mock_select
                return m
            elif name == "campaign_accounts":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"account_id": "acc-1"}]
                )
                return m
            elif name == "action_log":
                m.insert.return_value.execute.return_value = MagicMock(data=[])
                return m
            return m

        mock_supabase.table.side_effect = router_table
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

        req = EnrollListRequest(
            list_id="list-input-1"
        )

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("campaigns.backend.routers.elein.get_conflicting_active_leads", return_value={"lead-2"}):
            res = enroll_list_leads(
                campaign_id="camp-test-1",
                body=req,
                supabase=mock_supabase,
                workspace_id="ws-transparency"
            )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["enrolled"], 1)
        self.assertEqual(res["collisions"], 1)
        self.assertEqual(res["skipped"], 2)


if __name__ == "__main__":
    unittest.main()
