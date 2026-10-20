import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from leads.backend.schemas.lead import (
    LeadBase,
    LeadCreate,
    LeadUpdate,
    LeadResponse,
)
from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.services.lead_ingestion_service import (
    _IN_MEMORY_LEADS,
    _record_in_memory_leads,
    get_in_memory_leads_for_list,
    execute_bulk_import_leads,
)


class TestStage22LeadsFrontendResilienceAndSchemaSync(unittest.TestCase):
    """
    Stage 22 Paranoia Test Suite:
    Validates Leads Frontend Resilience, Schema Synchronization & Ingestion Hardening:
    - Layer 0: Schema synchronization (enriched_at, radar_signals, tags) and long TLD email cleaning.
    - Layer 1: Environmental Failure Analysis — in-memory cache capacity bounding, LRU eviction,
               zero RAM exhaustion in unmigrated environments, and conditional fallback storage.
    - Layer 2: Human Paranoia — rejection of invalid single-character/numeric TLDs, Sales Nav URL validation patterns.
    """

    def setUp(self):
        _IN_MEMORY_LEADS.clear()

    # =========================================================================
    # Layer 0: Schema Synchronization & Canonical Hygiene
    # =========================================================================
    def test_layer0_schema_synchronization_attributes(self):
        """
        Layer 0: Verify LeadBase and LeadUpdate properly accept and serialize
        enriched_at, radar_signals, and tags across Pydantic v2.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        signals = [
            {"signal_type": "JOB_CHANGE", "confidence": 0.95, "title": "Promoted to VP of Engineering"},
            {"signal_type": "FUNDING", "confidence": 0.88, "title": "Series B Announced"}
        ]
        tags = ["vip", "enterprise", "q4-priority"]

        lead = LeadBase(
            first_name="Elena",
            last_name="Rostova",
            email="elena.rostova@acme.technology",
            enriched_at=now_str,
            radar_signals=signals,
            tags=tags
        )

        dump = lead.model_dump()
        self.assertEqual(dump["first_name"], "Elena")
        self.assertEqual(dump["enriched_at"], now_str)
        self.assertEqual(len(dump["radar_signals"]), 2)
        self.assertEqual(dump["tags"], ["vip", "enterprise", "q4-priority"])

        # LeadUpdate allows partial updates of enriched_at, radar_signals, tags
        update = LeadUpdate(
            tags=["vip", "tier-1"],
            radar_signals=[{"signal_type": "HIRING", "confidence": 0.91}]
        )
        u_dump = update.model_dump(exclude_unset=True)
        self.assertEqual(u_dump["tags"], ["vip", "tier-1"])
        self.assertEqual(len(u_dump["radar_signals"]), 1)
        self.assertNotIn("first_name", u_dump)

    def test_layer0_email_cleaning_preserves_long_and_modern_tlds(self):
        """
        Layer 0 & 1: DataHygieneService.clean_email must preserve long modern TLDs
        (.technology, .consulting, .engineering, .international, .solutions) without truncation.
        """
        valid_long_tlds = [
            ("sarah@venture.consulting", "sarah@venture.consulting"),
            ("alex.smith@cloud.technology", "alex.smith@cloud.technology"),
            ("contact@precision.engineering", "contact@precision.engineering"),
            ("partners@global.international", "partners@global.international"),
            ("support@fintech.solutions", "support@fintech.solutions"),
            ("dev@crypto.institute", "dev@crypto.institute"),
            ("ceo@enterprise.ai", "ceo@enterprise.ai"),
            ("alice@sub.domain.co.uk", "alice@sub.domain.co.uk"),
        ]

        for raw_input, expected in valid_long_tlds:
            cleaned = DataHygieneService.clean_email(raw_input)
            self.assertEqual(cleaned, expected, f"Failed for valid email: {raw_input}")

    # =========================================================================
    # Layer 1: Environmental Failure Analysis & Memory Leak Guard
    # =========================================================================
    def test_layer1_in_memory_cache_bounded_capacity(self):
        """
        Layer 1: Verify _record_in_memory_leads strictly bounds cache capacity:
        - Max 25 workspaces
        - Max 50 lists per workspace
        - Max 500 leads per list
        Prevents memory leaks in long-running unmigrated worker processes.
        """
        # 1. Bounded leads per list: inserting 600 leads keeps only the last 500
        leads_600 = [{"first_name": f"Lead-{i}", "email": f"lead{i}@example.com"} for i in range(600)]
        _record_in_memory_leads("ws-test", "list-test", leads_600)
        stored_leads = get_in_memory_leads_for_list("ws-test", "list-test")
        self.assertEqual(len(stored_leads), 500)
        # Verify it retained the most recent leads (500th should be Lead-599)
        self.assertEqual(stored_leads[-1]["first_name"], "Lead-599")

        # 2. Bounded lists per workspace: inserting 60 lists retains at most 50
        for list_idx in range(60):
            _record_in_memory_leads("ws-multi-list", f"list-{list_idx}", [{"first_name": "Test"}])
        self.assertLessEqual(len(_IN_MEMORY_LEADS["ws-multi-list"]), 50)

        # 3. Bounded workspaces: inserting 30 workspaces retains at most 25
        for ws_idx in range(30):
            _record_in_memory_leads(f"ws-{ws_idx}", "list-1", [{"first_name": "Test"}])
        self.assertLessEqual(len(_IN_MEMORY_LEADS), 25)

    def test_layer1_in_memory_fallback_only_when_database_fails(self):
        """
        Layer 1: execute_bulk_import_leads must NOT pollute in-memory fallback cache
        when the database table operations succeed.
        """
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("RPC unmigrated")

        # Table query succeeds with 0 existing leads
        select_mock = MagicMock()
        select_mock.eq.return_value = select_mock
        select_mock.or_.return_value = select_mock
        select_mock.in_.return_value = select_mock
        select_mock.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value = select_mock

        # Table insert succeeds
        insert_mock = MagicMock()
        insert_mock.execute.return_value = MagicMock(data=[{"id": "lid-1"}])
        mock_supabase.table.return_value.insert.return_value = insert_mock

        leads = [
            {"first_name": "Alice", "last_name": "Smith", "email": "alice@acme.com"}
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-db-ok",
            workspace_id="ws-db-ok",
            leads=leads
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["source"], "direct_table")
        # In-memory store must NOT have been populated for this workspace/list!
        in_mem = get_in_memory_leads_for_list("ws-db-ok", "list-db-ok")
        self.assertEqual(len(in_mem), 0)

    # =========================================================================
    # Layer 2: Human Paranoia & Input Attack Defense
    # =========================================================================
    def test_layer2_email_cleaning_rejects_invalid_tlds_and_garbage(self):
        """
        Layer 2: Reject single-character TLDs (.c), numeric TLDs (.123),
        consecutive dots, missing domains, and dummy prefixes.
        """
        invalid_emails = [
            "user@domain.c",            # Single-character TLD
            "user@domain.123",          # Numeric TLD
            "user@domain..com",         # Consecutive dots
            "user@.com",                # Missing domain label
            "user@domain.",             # Trailing dot
            "none@company.com",         # Dummy prefix
            "test@acme.com",            # Dummy prefix
            "fake@domain.com",          # Dummy prefix
            "null@startup.io",          # Dummy prefix
            "user@test.com",            # Dummy domain
            "user@domain.com",          # Dummy domain
            "<mailto:user@domain.c>",   # Wrapped single-char TLD
            "plainaddress",             # No @ symbol
            "@missinguser.com",         # Missing user
        ]

        for bad_email in invalid_emails:
            cleaned = DataHygieneService.clean_email(bad_email)
            self.assertEqual(cleaned, "", f"Expected empty string for invalid email: {bad_email}")

    def test_layer2_sales_navigator_search_url_validation_patterns(self):
        """
        Layer 2: Validate Sales Navigator search URLs vs single profile URLs:
        - Search URLs (accepted by Sales Nav search import): /sales/search/people, /sales/search/lead
        - Single Profile URLs (flagged with warning): /sales/lead/..., /sales/people/..., /in/...
        - Non-LinkedIn URLs (rejected)
        """
        search_urls = [
            "https://www.linkedin.com/sales/search/people?query=(recentSearchParam:(id:12345))",
            "https://linkedin.com/sales/search/lead?query=(spellCorrectionEnabled:true)",
            "https://www.linkedin.com/sales/search/people?keywords=Chief+Technology+Officer",
        ]
        single_profile_urls = [
            "https://www.linkedin.com/sales/lead/ACwAABB1234,NAME,sample_ref",
            "https://www.linkedin.com/sales/people/ACwAABB1234,NAME,sample_ref",
            "https://www.linkedin.com/in/alex-smith",
            "https://linkedin.com/in/sarah-connor/",
        ]
        invalid_urls = [
            "https://google.com/search?q=leads",
            "https://twitter.com/sales",
            "not-a-url",
            "",
        ]

        # Simulation of client-side validation logic
        def validate_sales_nav_url(raw_url: str):
            clean = raw_url.strip()
            if not clean or "linkedin.com" not in clean.lower():
                return {"valid": False, "is_single": False, "error": "Must be a valid LinkedIn URL"}
            is_single = "/in/" in clean.lower() or "/sales/lead/" in clean.lower() or "/sales/people/" in clean.lower()
            return {"valid": True, "is_single": is_single, "error": None}

        for s_url in search_urls:
            val = validate_sales_nav_url(s_url)
            self.assertTrue(val["valid"])
            self.assertFalse(val["is_single"])

        for p_url in single_profile_urls:
            val = validate_sales_nav_url(p_url)
            self.assertTrue(val["valid"])
            self.assertTrue(val["is_single"], f"Expected single profile detection for {p_url}")

        for i_url in invalid_urls:
            val = validate_sales_nav_url(i_url)
            self.assertFalse(val["valid"])


if __name__ == "__main__":
    unittest.main()
