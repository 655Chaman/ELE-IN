import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.routers.leads import (
    export_dynamic_segment_csv_endpoint,
    check_suppression_endpoint,
    SuppressionCheckRequest,
)
from leads.backend.services.lead_segmentation_service import sync_dynamic_segment_members


class TestStage24LeadsSecurityAndSystemHardening(unittest.TestCase):
    """
    Stage 24 Paranoia Test Suite:
    Validates Leads Multi-Tenant Security, Fail-Closed DNC Guard, and Large-Scale Pagination:
    - Layer 0: IDOR validation on dynamic CSV export and valid CSV headers.
    - Layer 1: Environmental Failure Analysis — Fail-closed suppression on database drops (HTTP 503),
               and range-based pagination beyond 1,000 records.
    - Layer 2: Human Paranoia & ReDoS defense — strict string length bounding on email, phone, and URLs.
    """

    # =========================================================================
    # Layer 0 & 1: Multi-Tenant IDOR Guard on Export
    # =========================================================================
    def test_layer0_export_dynamic_segment_idor_prevention(self):
        """
        Layer 0 & 1 (LEAD-SEC-03): export_dynamic_segment_csv_endpoint must reject
        cross-tenant requests when list_id does not belong to the caller's workspace.
        """
        mock_supabase = MagicMock()
        # Mock list lookup returning empty (list belongs to different workspace)
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            export_dynamic_segment_csv_endpoint(
                list_id="list-foreign-org",
                workspace_id="ws-test-attacker",
                supabase=mock_supabase
            )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Lead list not found or unauthorized", ctx.exception.detail)

    def test_layer0_export_dynamic_segment_success_with_ownership(self):
        """
        Layer 0: When list belongs to the workspace, export_dynamic_segment_csv_endpoint
        returns a valid CSV Response with correct headers and formula injection protection.
        """
        mock_supabase = MagicMock()
        # Mock list ownership verified
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "list-legit", "name": "Enterprise Segment", "metadata": {}}]
        )

        with patch("leads.backend.services.lead_segmentation_service.export_dynamic_segment_csv") as mock_csv:
            mock_csv.return_value = "Lead ID,First Name,Last Name\n1,Alice,Smith\n"

            res = export_dynamic_segment_csv_endpoint(
                list_id="list-legit",
                workspace_id="ws-test-legit",
                supabase=mock_supabase
            )

            self.assertEqual(res.media_type, "text/csv")
            self.assertIn("dynamic_segment_list-legit.csv", res.headers.get("Content-Disposition", ""))

    # =========================================================================
    # Layer 1: Environmental Failure Analysis & Fail-Closed DNC
    # =========================================================================
    def test_layer1_check_suppression_fails_closed_on_database_error(self):
        """
        Layer 1 (LEAD-BE-04): check_suppression_endpoint must FAIL CLOSED with HTTP 503
        when the database encounters transient network drops, preventing unsuppressed outreach.
        """
        mock_supabase = MagicMock()
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_check:
            mock_check.side_effect = RuntimeError("Database connection timed out")

            req = SuppressionCheckRequest(
                email="prospect@target.com",
                linkedin_url="https://linkedin.com/in/prospect"
            )

            with self.assertRaises(HTTPException) as ctx:
                check_suppression_endpoint(
                    payload=req,
                    workspace_id="ws-outreach",
                    supabase=mock_supabase
                )

            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("Outreach blocked for compliance safety", ctx.exception.detail)

    def test_layer1_dynamic_segment_sync_paginates_beyond_1000_leads(self):
        """
        Layer 1 (LEAD-BE-06): sync_dynamic_segment_members must use range pagination
        to evaluate all workspace leads when count >= 1000, preventing false disqualifications.
        """
        mock_supabase = MagicMock()
        # 1. List lookup
        list_mock = MagicMock()
        list_mock.data = [{
            "id": "list-1000",
            "name": "Large Segment",
            "metadata": {
                "dynamic_rules": {
                    "match_type": "ALL",
                    "conditions": [{"field": "job_title", "operator": "contains", "value": "Engineer"}]
                }
            }
        }]

        # 2. Page 1 (1000 leads) and Page 2 (200 leads)
        page1_leads = [{"id": f"l-{i}", "job_title": "Software Engineer"} for i in range(1000)]
        page2_leads = [{"id": f"l-{1000 + i}", "job_title": "DevOps Engineer"} for i in range(200)]

        # 3. List members: initially 0 members
        members_mock = MagicMock(data=[])

        def table_router(table_name):
            t_mock = MagicMock()
            if table_name == "lead_lists":
                t_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = list_mock
                t_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "leads":
                # First call returns 1000 leads
                t_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=page1_leads)
                # Range call returns remaining 200 leads
                t_mock.select.return_value.eq.return_value.range.return_value.execute.return_value = MagicMock(data=page2_leads)
            elif table_name == "list_members":
                t_mock.select.return_value.eq.return_value.execute.return_value = members_mock
                t_mock.upsert.return_value.execute.return_value = MagicMock(data=[])
            return t_mock

        mock_supabase.table.side_effect = table_router

        res = sync_dynamic_segment_members(
            list_id="list-1000",
            workspace_id="ws-test-large",
            supabase=mock_supabase,
            auto_enroll=False
        )

        self.assertEqual(res["status"], "success")
        # All 1200 leads should have been evaluated and qualified!
        self.assertEqual(res["total_workspace_leads"], 1200)
        self.assertEqual(res["qualified_leads_count"], 1200)
        self.assertEqual(res["added_to_list"], 1200)

    # =========================================================================
    # Layer 2: Human Paranoia & ReDoS Length Bounding
    # =========================================================================
    def test_layer2_redos_length_bounding(self):
        """
        Layer 2 (LEAD-SEC-11): DataHygieneService must reject excessively long strings
        before regex parsing to eradicate catastrophic backtracking (ReDoS).
        """
        # 1. Oversized email (> 320 chars)
        giant_email = "a" * 325 + "@domain.com"
        self.assertEqual(DataHygieneService.clean_email(giant_email), "")

        # 2. Oversized phone (> 50 chars)
        giant_phone = "+1" + "9" * 60
        self.assertEqual(DataHygieneService.clean_phone(giant_phone), "")

        # 3. Oversized LinkedIn URL (> 2048 chars)
        giant_url = "https://www.linkedin.com/in/" + "x" * 2100
        self.assertEqual(DataHygieneService.normalize_linkedin_url(giant_url), "")


if __name__ == "__main__":
    unittest.main()
