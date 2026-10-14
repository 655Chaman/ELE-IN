import unittest
from unittest.mock import MagicMock, patch
import uuid

from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.services.lead_ingestion_service import (
    split_full_name,
    execute_bulk_import_leads,
    _IN_MEMORY_LEADS,
    _IN_MEMORY_LEAD_LISTS
)
from campaigns.backend.routers.elein import (
    upload_urls,
    UploadUrlsRequest
)
from fastapi import HTTPException


class TestLeadIngestionNormalizationAndCollisionGuard(unittest.TestCase):
    """
    Step 31 Test Suite: Lead Ingestion Canonical Normalization & Cross-List Collision Prevention Guard.
    Evaluates Three-Layer Paranoia Framework:
    - Layer 0: Core mechanics, URL normalization, RFC email validation, batch ingestion.
    - Layer 1: Environmental Failure Analysis — subroute truncation, Sales Nav URN isolation,
               N+1 query eradication via chunked batch processing, zero-migration fallback.
    - Layer 2: Human Paranoia — rejection of dummy vanities/emails, cross-list collision policies
               ('skip_active_campaign', 'skip_existing', 'merge'), search URL interception.
    """

    def setUp(self):
        _IN_MEMORY_LEADS.clear()
        _IN_MEMORY_LEAD_LISTS.clear()

    # =========================================================================
    # Layer 0 & 1: URL Normalization, Sub-Route Truncation & Sales Nav Isolation
    # =========================================================================
    def test_canonical_linkedin_url_subroute_truncation(self):
        """Paranoia Layer 0 & 1: Sub-route truncation and vanity URL canonicalization."""
        # 1. Sub-route from activity tab
        raw_1 = "https://www.linkedin.com/in/alex-smith/recent-activity/all/"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(raw_1),
            "https://www.linkedin.com/in/alex-smith"
        )

        # 2. Sub-route from overlay or detail modal
        raw_2 = "https://linkedin.com/in/alex-smith/overlay/contact-info/"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(raw_2),
            "https://www.linkedin.com/in/alex-smith"
        )

        # 3. HTTP scheme upgraded to HTTPS, www subdomain normalized
        raw_3 = "http://linkedin.com/in/alex-smith/"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(raw_3),
            "https://www.linkedin.com/in/alex-smith"
        )

        # 4. Trailing punctuation and query params stripped
        raw_4 = "https://www.linkedin.com/in/alex-smith?trk=public_profile_browsemap"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(raw_4),
            "https://www.linkedin.com/in/alex-smith"
        )

        # 5. Enclosure quotes and angle brackets stripped
        raw_5 = "<https://www.linkedin.com/in/alex-smith>"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(raw_5),
            "https://www.linkedin.com/in/alex-smith"
        )

    def test_canonical_linkedin_sales_nav_urn_isolation(self):
        """Paranoia Layer 1: Isolates clean URNs from composite Sales Navigator URLs."""
        # Comma-separated identifier with query garbage
        nav_url_1 = "https://www.linkedin.com/sales/lead/ACwAABB1234,NAME,sample_ref?_sp=abc"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(nav_url_1),
            "https://www.linkedin.com/sales/lead/ACwAABB1234"
        )

        # Sales people path
        nav_url_2 = "https://www.linkedin.com/sales/people/ACwAACC5678,EXTRA"
        self.assertEqual(
            DataHygieneService.normalize_linkedin_url(nav_url_2),
            "https://www.linkedin.com/sales/people/ACwAACC5678"
        )

    def test_dummy_vanity_and_non_profile_url_rejection(self):
        """Paranoia Layer 2: Rejects placeholder vanities and company/job URLs."""
        # Dummy placeholder vanity usernames
        dummy_urls = [
            "https://www.linkedin.com/in/null",
            "https://www.linkedin.com/in/undefined",
            "https://www.linkedin.com/in/unknown",
            "https://www.linkedin.com/in/linkedin",
            "https://www.linkedin.com/in/profile",
            "https://www.linkedin.com/in/me",
            "https://www.linkedin.com/in/edit"
        ]
        for d in dummy_urls:
            self.assertEqual(DataHygieneService.normalize_linkedin_url(d), "")

        # Company, jobs, school sections should return empty (not personal profiles)
        non_profiles = [
            "https://www.linkedin.com/company/google",
            "https://www.linkedin.com/school/stanford-university",
            "https://www.linkedin.com/jobs/view/123456",
            "https://www.linkedin.com/feed/",
            "https://www.linkedin.com/groups/999"
        ]
        for np in non_profiles:
            self.assertEqual(DataHygieneService.normalize_linkedin_url(np), "")

    # =========================================================================
    # Layer 0 & 2: Email Hygiene & Dummy Catch-All Rejection
    # =========================================================================
    def test_rfc_email_cleaning_and_dummy_rejection(self):
        """Paranoia Layer 0 & 2: Cleans RFC emails and rejects dummy prefixes/domains."""
        # Standard email with mailto and angle brackets
        self.assertEqual(
            DataHygieneService.clean_email("mailto:<Alex.Smith@AcmeCorp.io>"),
            "alex.smith@acmecorp.io"
        )

        # Rejects dummy test emails
        self.assertEqual(DataHygieneService.clean_email("none@company.com"), "")
        self.assertEqual(DataHygieneService.clean_email("test@acme.com"), "")
        self.assertEqual(DataHygieneService.clean_email("fake@domain.com"), "")
        self.assertEqual(DataHygieneService.clean_email("null@company.com"), "")
        self.assertEqual(DataHygieneService.clean_email("no-reply@company.com"), "")
        self.assertEqual(DataHygieneService.clean_email("user@test.com"), "")
        self.assertEqual(DataHygieneService.clean_email("user@domain.com"), "")

        # Rejects malformed domains
        self.assertEqual(DataHygieneService.clean_email("user@domain..com"), "")
        self.assertEqual(DataHygieneService.clean_email("user@domain."), "")
        self.assertEqual(DataHygieneService.clean_email("not-an-email"), "")

    # =========================================================================
    # Layer 1 & 2: Cross-List Collision Prevention & Batch Processing
    # =========================================================================
    def test_collision_policy_skip_active_campaign(self):
        """Paranoia Layer 1 & 2: collision_policy='skip_active_campaign' skips leads in active outreach."""
        mock_supabase = MagicMock()
        # Fail RPC to test Layer 1 direct table engine
        mock_supabase.rpc.side_effect = Exception("RPC unmigrated")

        # Mock table calls
        lead_id = "lead-active-101"
        existing_lead = {
            "id": lead_id,
            "linkedin_url": "https://www.linkedin.com/in/activeuser",
            "email": "active@acme.com",
            "first_name": "Active",
            "last_name": "User"
        }

        # Setup select query mock
        select_mock = MagicMock()
        select_mock.eq.return_value = select_mock
        select_mock.or_.return_value = select_mock
        select_mock.in_.return_value = select_mock
        select_mock.execute.return_value = MagicMock(data=[existing_lead])

        # Setup table returns
        mock_supabase.table.return_value.select.return_value = select_mock

        leads = [
            {
                "linkedin_url": "https://www.linkedin.com/in/activeuser/recent-activity/",
                "email": "active@acme.com",
                "first_name": "Active",
                "last_name": "User"
            },
            {
                "linkedin_url": "https://www.linkedin.com/in/newuser",
                "email": "new@acme.com",
                "first_name": "New",
                "last_name": "User"
            }
        ]

        # Mock collision_guard to report lead_id as active in an outreach campaign
        with patch("campaigns.backend.services.collision_guard.get_conflicting_active_leads", return_value=[lead_id]):
            res = execute_bulk_import_leads(
                supabase=mock_supabase,
                list_id="list-123",
                workspace_id="ws-123",
                leads=leads,
                collision_policy="skip_active_campaign"
            )

        self.assertTrue(res["success"])
        # Active lead was skipped due to campaign collision
        self.assertEqual(res["colliding_count"], 1)
        # New lead was successfully processed
        self.assertEqual(res["inserted_count"], 1)

    def test_collision_policy_skip_existing(self):
        """Paranoia Layer 2: collision_policy='skip_existing' skips duplicate workspace leads."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("RPC unmigrated")

        existing_lead = {
            "id": "lead-exist-1",
            "linkedin_url": "https://www.linkedin.com/in/existinguser",
            "email": "existing@acme.com"
        }

        select_mock = MagicMock()
        select_mock.eq.return_value = select_mock
        select_mock.or_.return_value = select_mock
        select_mock.in_.return_value = select_mock
        select_mock.execute.return_value = MagicMock(data=[existing_lead])
        mock_supabase.table.return_value.select.return_value = select_mock

        leads = [
            {
                "linkedin_url": "https://www.linkedin.com/in/existinguser",
                "email": "existing@acme.com",
                "first_name": "Existing",
                "last_name": "User"
            }
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-123",
            workspace_id="ws-123",
            leads=leads,
            collision_policy="skip_existing"
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["duplicate_count"], 1)
        self.assertEqual(res["inserted_count"], 0)

    def test_batch_chunked_operations_eliminate_n_plus_one(self):
        """Paranoia Layer 1: Eradicates N+1 queries by executing batched table operations."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("RPC unmigrated")

        select_mock = MagicMock()
        select_mock.eq.return_value = select_mock
        select_mock.or_.return_value = select_mock
        select_mock.in_.return_value = select_mock
        select_mock.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value = select_mock

        insert_mock = MagicMock()
        insert_mock.execute.return_value = MagicMock(data=[{"id": f"lid-{i}"} for i in range(50)])
        mock_supabase.table.return_value.insert.return_value = insert_mock

        # Create 50 leads
        leads = [
            {
                "linkedin_url": f"https://www.linkedin.com/in/lead-{i}/",
                "first_name": f"Lead{i}",
                "last_name": "Test"
            }
            for i in range(50)
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-bulk",
            workspace_id="ws-bulk",
            leads=leads,
            collision_policy="merge"
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["inserted_count"], 50)
        self.assertEqual(res["source"], "direct_table")

        # Verify batch select was called once for the chunk, not 50 individual selects!
        self.assertEqual(mock_supabase.table.return_value.select.call_count, 1)

    # =========================================================================
    # Layer 2: API Endpoint Integration & Human Paranoia Guards
    # =========================================================================
    def test_upload_urls_rejects_search_queries_with_actionable_error(self):
        """Paranoia Layer 2: upload_urls rejects LinkedIn search / Sales Nav search queries."""
        mock_supabase = MagicMock()
        body = UploadUrlsRequest(
            name="Search Leads",
            urls=["https://www.linkedin.com/sales/search/people?query=(recentSearchParam)"],
            target_timezone="UTC",
            target_region_label="Global"
        )

        with self.assertRaises(HTTPException) as ctx:
            upload_urls(body, supabase=mock_supabase, workspace_id="ws-1", user_id="u-1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Search queries cannot be uploaded as raw profile URLs", ctx.exception.detail)

    def test_upload_urls_with_collision_policy_forwarding(self):
        """Paranoia Layer 2: upload_urls endpoint passes collision_policy and returns breakdown."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"inserted_count": 2, "duplicate_count": 1})
        mock_supabase.rpc.return_value = mock_rpc

        body = UploadUrlsRequest(
            name="URL List",
            urls=[
                "https://www.linkedin.com/in/sarah-connor/recent-activity/",
                "https://www.linkedin.com/in/john-connor/"
            ],
            target_timezone="UTC",
            target_region_label="US",
            collision_policy="skip_active_campaign"
        )

        res = upload_urls(body, supabase=mock_supabase, workspace_id="ws-1", user_id="u-1")
        self.assertIn("list_id", res)
        self.assertIn("row_count", res)
        self.assertIn("duplicate_count", res)
        self.assertIn("colliding_count", res)


class TestCSVHygieneCreditSecurity(unittest.TestCase):
    """Paranoia Layer 0, 1 & 2: Tests C-08 anti-credit-minting on failed hygiene imports."""

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_rpc_failure_never_mints_refund_on_empty_import(self, mock_get_client):
        """When deduct_credits_safely throws an error, no refund should ever be minted."""
        import tempfile
        import os
        from campaigns.backend.routers.elein import process_csv_background

        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        # Mock lead_lists status query
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "pending"}])

        # Simulate RPC failure / timeout on deduct_credits_safely
        def rpc_side_effect(rpc_name, params=None):
            if rpc_name == "deduct_credits_safely":
                raise RuntimeError("RPC deduct_credits_safely timed out")
            return MagicMock()

        mock_supabase.rpc.side_effect = rpc_side_effect

        # Create temporary empty CSV with only header
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tmp:
            tmp.write("first_name,last_name,email\n")
            tmp_path = tmp.name

        try:
            process_csv_background(
                list_id="list-rpc-fail",
                file_path=tmp_path,
                clean_data=True,
                workspace_id="ws-exploit-attempt"
            )

            # Assert add_credits_safely was NEVER called!
            for call in mock_supabase.rpc.call_args_list:
                rpc_name = call[0][0] if call[0] else call.kwargs.get("rpc_name")
                self.assertNotEqual(rpc_name, "add_credits_safely", "CRITICAL FLAW: add_credits_safely was called without deducting credits!")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_successful_deduction_refunds_once_on_empty_import(self, mock_get_client):
        """When deduct_credits_safely succeeds, a refund must be issued exactly once if 0 leads imported."""
        import tempfile
        import os
        from campaigns.backend.routers.elein import process_csv_background

        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "pending"}])

        def rpc_side_effect(rpc_name, params=None):
            if rpc_name == "deduct_credits_safely":
                return MagicMock(data={"success": True, "balance": 100})
            if rpc_name == "add_credits_safely":
                return MagicMock(data={"success": True})
            return MagicMock()

        mock_supabase.rpc.side_effect = rpc_side_effect

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tmp:
            tmp.write("first_name,last_name,email,linkedin_url\n")
            tmp.write("John,Doe,john@example.com,\n")
            tmp.write("Jane,Doe,jane@example.com,\n")
            tmp_path = tmp.name

        try:
            process_csv_background(
                list_id="list-legit-refund",
                file_path=tmp_path,
                clean_data=True,
                workspace_id="ws-legit-user"
            )

            # Assert add_credits_safely was called exactly once with system_refund
            refund_calls = [
                call for call in mock_supabase.rpc.call_args_list
                if (call[0][0] if call[0] else call.kwargs.get("rpc_name")) == "add_credits_safely"
            ]
            self.assertEqual(len(refund_calls), 1)
            self.assertEqual(refund_calls[0][0][1]["p_provider"], "system_refund")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
