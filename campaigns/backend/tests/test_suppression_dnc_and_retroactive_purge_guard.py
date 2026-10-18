"""
Three-Layer Paranoia Framework Unit Test Suite — Step 34 Track B:
Suppression List (DNC) Bulk Import Normalization, Wildcard Domain Blocking & Retroactive In-Flight Purge Guard
"""
import os
import unittest
from collections import defaultdict
from unittest.mock import MagicMock
from fastapi import HTTPException

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from leads.backend.services.suppression_service import (
    normalize_suppression_domain,
    normalize_suppression_entry,
    add_suppression_entries_bulk,
    retroactive_purge_suppressed_leads,
    check_lead_suppression,
)


class TestSuppressionDncAndRetroactivePurgeGuard(unittest.TestCase):
    def _setup_multi_table_mock(self):
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    # =========================================================================
    # 1. Canonical Domain & Entry Normalization (Layer 0 & 2)
    # =========================================================================

    def test_normalize_suppression_domain_canonicalizes_urls_and_wildcards(self):
        """Paranoia Layer 0 & 2: Strips *@, @, https://, www., paths, ports, and rejects linkedin.com."""
        self.assertEqual(normalize_suppression_domain("*@Competitor.com"), "competitor.com")
        self.assertEqual(normalize_suppression_domain("@acme-corp.io"), "acme-corp.io")
        self.assertEqual(
            normalize_suppression_domain("https://www.Competitor.com:8080/about-us?ref=123"),
            "competitor.com",
        )
        # Rejects linkedin.com itself from domain suppression
        self.assertIsNone(normalize_suppression_domain("https://www.linkedin.com/in/johndoe"))
        self.assertIsNone(normalize_suppression_domain("linkedin.com"))
        # Rejects full email with local part when passed directly to domain normalizer
        self.assertIsNone(normalize_suppression_domain("john@competitor.com"))

    def test_normalize_suppression_entry_blocks_freemail_wildcard_by_default(self):
        """Paranoia Layer 2: Blocks accidental wildcard domain suppression of gmail.com/yahoo.com/outlook.com."""
        for freemail in ("@gmail.com", "https://www.yahoo.com", "*@outlook.com", "icloud.com"):
            res = normalize_suppression_entry({"domain": freemail}, allow_freemail_domain=False)
            self.assertFalse(res["valid"], f"Expected freemail {freemail} to be blocked")
            self.assertIn("freemail", res["error"].lower())

        # Specific individual gmail address IS allowed!
        res_specific = normalize_suppression_entry({"email": "prospect@gmail.com"}, allow_freemail_domain=False)
        self.assertTrue(res_specific["valid"])
        self.assertEqual(res_specific["email"], "prospect@gmail.com")

        # Explicit override allows freemail domain if operator insists
        res_override = normalize_suppression_entry({"domain": "@gmail.com"}, allow_freemail_domain=True)
        self.assertTrue(res_override["valid"])
        self.assertEqual(res_override["domain"], "gmail.com")

    def test_normalize_suppression_entry_auto_detects_value_field(self):
        """Paranoia Layer 0: Generic 'value' string auto-classifies into LinkedIn URL, email, or domain."""
        li_entry = normalize_suppression_entry("https://uk.linkedin.com/in/Alice-Smith/recent-activity/")
        self.assertTrue(li_entry["valid"])
        self.assertEqual(li_entry["linkedin_url"], "https://www.linkedin.com/in/alice-smith")

        em_entry = normalize_suppression_entry("mailto:<Bob@Competitor.com>")
        self.assertTrue(em_entry["valid"])
        self.assertEqual(em_entry["email"], "bob@competitor.com")

        dom_entry = normalize_suppression_entry("*@rival-saas.io")
        self.assertTrue(dom_entry["valid"])
        self.assertEqual(dom_entry["domain"], "rival-saas.io")

    # =========================================================================
    # 2. Retroactive In-Flight Purge (Layer 1)
    # =========================================================================

    def test_retroactive_purge_halts_in_flight_leads_by_url_email_and_domain(self):
        """Paranoia Layer 1: Adding a domain or prospect to DNC immediately exits active execution states."""
        mock_svc, tables = self._setup_multi_table_mock()

        # Mock leads matching domain 'competitor.com'
        tables["leads"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "lead_comp_1", "email": "ceo@competitor.com"},
                {"id": "lead_comp_2", "email": "vp@competitor.com"},
                {"id": "lead_safe_3", "email": "vp@friendly.com"},
            ]
        )
        # Mock enrollments for matched leads
        tables["campaign_enrollments"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "enr_1"}, {"id": "enr_2"}]
        )
        # Mock execution states update
        tables["campaign_execution_states"].update.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "state_1", "status": "exited"}, {"id": "state_2", "status": "exited"}]
        )

        res = retroactive_purge_suppressed_leads(
            supabase=mock_svc,
            workspace_id="ws_dnc",
            domains=["competitor.com"],
        )
        self.assertEqual(res["matched_leads_count"], 2)
        self.assertEqual(res["halted_states_count"], 2)
        self.assertEqual(res["lead_ids"], ["lead_comp_1", "lead_comp_2"])

        state_upd = tables["campaign_execution_states"].update.call_args[0][0]
        self.assertEqual(state_upd["status"], "exited")
        self.assertIsNone(state_upd["lease_token"])
        self.assertIn("Suppression List", state_upd["error_reason"])

    # =========================================================================
    # 3. Bulk Import Deduplication & Wildcard Check (Layer 0, 1 & 2)
    # =========================================================================

    def test_add_suppression_entries_bulk_deduplicates_and_purges(self):
        """Paranoia Layer 1 & 2: Deduplicates intra-batch entries, blocks freemail wildcard, and runs purge."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["suppression_list"].insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "s1"}, {"id": "s2"}]
        )
        tables["leads"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        tables["leads"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        entries = [
            "https://www.linkedin.com/in/John-Doe/",
            "https://linkedin.com/in/john-doe/detail/recent-activity/",  # Duplicate after canonicalization!
            "*@competitor.io",
            "@gmail.com",  # Should be rejected as freemail wildcard
        ]
        res = add_suppression_entries_bulk(mock_svc, "ws_dnc", entries)
        self.assertEqual(res["inserted_count"], 2)
        self.assertEqual(res["duplicate_count"], 1)
        self.assertEqual(res["rejected_count"], 1)

    def test_check_lead_suppression_matches_wildcard_domain(self):
        """Paranoia Layer 0: Lead with 'alice@competitor.io' matches workspace domain suppression 'competitor.io'."""
        mock_svc, tables = self._setup_multi_table_mock()
        hit_resp = MagicMock(
            data=[
                {"id": "sup_1", "linkedin_url": None, "email": None, "domain": "competitor.io", "value": "competitor.io", "reason": "competitor"}
            ]
        )
        empty_resp = MagicMock(data=[])
        tables["suppression_list"].select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.side_effect = [
            hit_resp,
            empty_resp,
        ]

        check_hit = check_lead_suppression(mock_svc, "ws_dnc", email="Alice.VP@Competitor.io")
        self.assertTrue(check_hit["suppressed"])
        self.assertEqual(check_hit["matched_by"], "domain")
        self.assertEqual(check_hit["matched_value"], "competitor.io")

        check_safe = check_lead_suppression(mock_svc, "ws_dnc", email="alice@prospect.io")
        self.assertFalse(check_safe["suppressed"])


if __name__ == "__main__":
    unittest.main()
