import unittest
from unittest.mock import MagicMock, patch
import io
import csv

from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.services.lead_ingestion_service import (
    split_full_name,
    execute_bulk_import_leads,
    _IN_MEMORY_LEADS,
    _IN_MEMORY_LEAD_LISTS,
    register_in_memory_lead_list,
    get_in_memory_lead_lists,
    get_in_memory_leads_for_list
)
from campaigns.backend.routers.elein import (
    upload_urls,
    UploadUrlsRequest,
    get_lists
)


class TestPhase2LeadIngestionEngine(unittest.TestCase):
    """
    Phase 2: Lead Sourcing & CSV Ingestion Engine Test Suite.
    Rigorously verifies compliance across all Three Paranoia Layers:
    - Layer 0: Core parsing, full name auto-splitting, and deduplication.
    - Layer 1: Environmental Failure Analysis — Zero-migration Supabase resilience (missing RPCs & tables).
    - Layer 2: Human Paranoia — Input mistakes, single column full names, and search URL interception.
    """

    def setUp(self):
        _IN_MEMORY_LEADS.clear()
        _IN_MEMORY_LEAD_LISTS.clear()

    # =========================================================================
    # Layer 0: Foundational Mechanics — Full Name Splitting
    # =========================================================================
    def test_split_full_name_standard_and_single_word(self):
        """Paranoia Layer 0: Standard first/last names and single-word names."""
        first, last = split_full_name("Sarah Lin")
        self.assertEqual(first, "Sarah")
        self.assertEqual(last, "Lin")

        first, last = split_full_name("Cher")
        self.assertEqual(first, "Cher")
        self.assertEqual(last, "")

        first, last = split_full_name("   ")
        self.assertEqual(first, "")
        self.assertEqual(last, "")

        first, last = split_full_name(None)
        self.assertEqual(first, "")
        self.assertEqual(last, "")

    def test_split_full_name_honorifics_and_suffixes(self):
        """Paranoia Layer 0 & 2: Strips honorifics and professional suffixes."""
        first, last = split_full_name("Dr. Gregory House, M.D.")
        self.assertEqual(first, "Gregory")
        self.assertEqual(last, "House")

        first, last = split_full_name("Prof. John von Neumann, Ph.D.")
        self.assertEqual(first, "John")
        self.assertEqual(last, "von Neumann")

        first, last = split_full_name("Martin Luther King Jr.")
        self.assertEqual(first, "Martin")
        self.assertEqual(last, "Luther King")

        first, last = split_full_name("Ms. Jane Doe Esq.")
        self.assertEqual(first, "Jane")
        self.assertEqual(last, "Doe")

    # =========================================================================
    # Layer 1: Environmental Failure Analysis — Zero-Migration DB Fallbacks
    # =========================================================================
    def test_execute_bulk_import_leads_rpc_success(self):
        """Paranoia Layer 0: When Supabase RPC exists, uses atomic RPC successfully."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"inserted_count": 3})
        mock_supabase.rpc.return_value = mock_rpc

        leads = [
            {"linkedin_url": "https://www.linkedin.com/in/lead1", "first_name": "A", "last_name": "B"},
            {"linkedin_url": "https://www.linkedin.com/in/lead2", "first_name": "C", "last_name": "D"},
            {"linkedin_url": "https://www.linkedin.com/in/lead3", "first_name": "E", "last_name": "F"},
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-123",
            workspace_id="ws-test",
            leads=leads,
            timezone="America/New_York"
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["inserted_count"], 3)
        self.assertEqual(res["source"], "rpc")
        mock_supabase.rpc.assert_called_once()

    def test_execute_bulk_import_leads_zero_migration_rpc_fallback(self):
        """
        Paranoia Layer 1: When 0 migrations have been run in Supabase and bulk_import_leads RPC
        throws PGRST202 (not found), falls back to direct table upserts and in-memory store.
        """
        mock_supabase = MagicMock()
        # RPC raises exception simulating missing RPC in unmigrated database
        mock_supabase.rpc.side_effect = Exception("PGRST202: Could not find the function public.bulk_import_leads")

        # Mock direct table operations
        mock_select = MagicMock()
        mock_select.execute.return_value = MagicMock(data=[])
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "lead-new"}])

        leads = [
            {"linkedin_url": "https://www.linkedin.com/in/lead-unmigrated", "first_name": "Elena", "last_name": "Rostova"}
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-fallback-1",
            workspace_id="ws-unmigrated",
            leads=leads
        )

        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["inserted_count"], 1)
        self.assertIn(res["source"], ["direct_table", "in_memory"])

        # Verify leads are recorded in in-memory fallback store
        in_mem = get_in_memory_leads_for_list("ws-unmigrated", "list-fallback-1")
        self.assertEqual(len(in_mem), 1)
        self.assertEqual(in_mem[0]["first_name"], "Elena")

    def test_execute_bulk_import_leads_total_db_failure_in_memory_resilience(self):
        """
        Paranoia Layer 1: When both RPC AND database tables throw (e.g. unmigrated Supabase instance),
        leads are safely recorded in-memory without raising an unhandled exception or crashing.
        """
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("PGRST202 function missing")
        mock_supabase.table.side_effect = Exception("42P01 table does not exist")

        leads = [
            {"linkedin_url": "https://www.linkedin.com/in/marcus", "first_name": "Marcus", "last_name": "Vance"}
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-crash-resilient",
            workspace_id="ws-resilient",
            leads=leads
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["inserted_count"], 1)
        self.assertEqual(res["source"], "in_memory")
        in_mem = get_in_memory_leads_for_list("ws-resilient", "list-crash-resilient")
        self.assertEqual(len(in_mem), 1)

    def test_get_lists_zero_migration_fallback(self):
        """
        Paranoia Layer 1: When lead_lists table is unmigrated, GET /api/elein/leads/lists
        returns in-memory registered lists instead of 500 internal server error.
        """
        register_in_memory_lead_list("ws-mem-test", {
            "id": "list-mem-1",
            "name": "Q3 Target Outbound",
            "type": "csv",
            "row_count": 50,
            "workspace_id": "ws-mem-test",
            "status": "completed"
        })

        mock_supabase = MagicMock()
        # Simulating unmigrated table
        mock_supabase.table.side_effect = Exception("relation 'lead_lists' does not exist")

        res = get_lists(supabase=mock_supabase, workspace_id="ws-mem-test")
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Q3 Target Outbound")

    # =========================================================================
    # Layer 2: Human Paranoia — Input Mistakes & Search URL Interception
    # =========================================================================
    def test_upload_urls_rejects_sales_nav_search_query(self):
        """
        Paranoia Layer 2: When user mistakenly pastes Sales Navigator or LinkedIn Search URLs
        into Raw Profiles import, immediately returns helpful 400 instructing them to use Sales Nav tab.
        """
        from fastapi import HTTPException
        mock_supabase = MagicMock()

        req = UploadUrlsRequest(
            name="Accidental Search Query",
            urls=["https://www.linkedin.com/sales/search/people?query=(recentSearchParam:(id:123))"],
            target_timezone="UTC",
            target_region_label="Global"
        )

        with self.assertRaises(HTTPException) as ctx:
            upload_urls(body=req, supabase=mock_supabase, workspace_id="ws-test", user_id="u-1")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Detected Sales Navigator or LinkedIn Search URL", ctx.exception.detail)

    def test_data_hygiene_formula_injection_defense(self):
        """
        Paranoia Layer 0 & 2: Prevents CSV formula injection (CWE-1236) while preserving
        legitimate numbers.
        """
        # Formula injection triggers must be escaped with single quote
        self.assertEqual(DataHygieneService.sanitize_text("=CMD|' /C calc'!A0"), "'=CMD|' /C calc'!A0")
        self.assertEqual(DataHygieneService.sanitize_text("@SUM(1+1)"), "'@SUM(1+1)")
        self.assertEqual(DataHygieneService.sanitize_text("+MALICIOUS_CALL()"), "'+MALICIOUS_CALL()")

        # Legitimate signed numbers preserved
        self.assertEqual(DataHygieneService.sanitize_text("-42"), "-42")
        self.assertEqual(DataHygieneService.sanitize_text("+3.14"), "+3.14")


if __name__ == "__main__":
    unittest.main()
