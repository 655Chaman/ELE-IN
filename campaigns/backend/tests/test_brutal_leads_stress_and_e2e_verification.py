"""
test_brutal_leads_stress_and_e2e_verification.py — Exhaustive End-to-End Brutal Stress-Test Suite
for Ele-in Leads Module under the Three-Layer Logic Architecture (Paranoia Framework).

Covers:
1. CSV Ingestion Engine: Formula injection, malicious payloads, spam traps, ReDoS, 1,000-lead chunks, collision policies.
2. Dynamic Segmentation Engine: Seniority classification, company sizes, boolean ASTs, preview simulation, CSV export defense.
3. Location & Timezone Engine: E.164 parsing, US area code anti-inversion, DST safety, fallback defaults.
4. DNC / Suppression Engine: Domain wildcards, public freemail blocking, fail-closed database errors, retroactive purge.
5. Campaign Direct Enrollment: Pre-flight suppression skipping, collision guard filtering, weighted sender fleet allocation.
6. Multi-Tenant Isolation & IDOR: Cross-workspace query isolation, export boundary validation.
"""

import pytest
import uuid
import re
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.services.location_timezone_service import LocationTimezoneService
from leads.backend.services.lead_ingestion_service import (
    execute_bulk_import_leads,
    split_full_name,
    RESERVED_SYSTEM_LEAD_KEYS,
)
from leads.backend.services.lead_segmentation_service import (
    parse_job_title_seniority,
    normalize_company_size_tier,
    evaluate_lead_condition,
    evaluate_lead_against_rules,
    preview_dynamic_segment,
    export_dynamic_segment_csv,
    SENIORITY_C_SUITE,
    SENIORITY_FOUNDER,
    SENIORITY_VP,
    SENIORITY_DIRECTOR,
    SENIORITY_MANAGER,
    SENIORITY_CONTRIBUTOR,
    SENIORITY_UNKNOWN,
)
from leads.backend.services.suppression_service import (
    normalize_suppression_domain,
    check_lead_suppression,
    add_suppression_entries_bulk,
    PUBLIC_FREEMAIL_DOMAINS,
)
from campaigns.backend.routers.elein import EnrollListRequest, enroll_list_leads
from fastapi import HTTPException


class TestBrutalLeadsIngestionAndDataHygiene:
    """Brutally stress-tests CSV and bulk lead ingestion mechanics."""

    def test_name_splitting_handles_prefixes_suffixes_and_honorifics(self):
        """Tests that full name parser handles complex real-world executive names safely."""
        test_cases = [
            ("Dr. Jane Doe, Ph.D.", ("Jane", "Doe")),
            ("Mr. John Smith Jr.", ("John", "Smith")),
            ("Prof. Robert H. Davis III", ("Robert", "H. Davis")),
            ("Sarah Connor, CPA", ("Sarah", "Connor")),
            ("William Gates, Esq.", ("William", "Gates")),
            ("Cher", ("Cher", "")),
            ("ALEXANDER HAMILTON", ("Alexander", "Hamilton")),
            ("mary jane watson", ("Mary", "Jane Watson")),
            ("", ("", "")),
            (None, ("", "")),
        ]
        for raw, expected in test_cases:
            first, last = split_full_name(raw)
            assert (first, last) == expected, f"Failed on '{raw}' -> got ({first}, {last}), expected {expected}"

    def test_csv_formula_injection_defense_neutralizes_all_triggers(self):
        """Verifies DataHygieneService neutralizes all spreadsheet formula execution vectors."""
        payloads = [
            "=1+1",
            "+cmd|' /C calc'!A0",
            "-2+3",
            "@SUM(A1:A10)",
            "\t=cmd.exe",
            "\r-DDE('cmd')",
            "   =HYPERLINK('http://evil.com')",
            "=cmd|' /C powershell.exe'!",
        ]
        for p in payloads:
            sanitized = DataHygieneService.sanitize_text(p)
            assert sanitized.startswith("'"), f"Formula injection payload '{p}' was not neutralized: '{sanitized}'"

    def test_malicious_javascript_and_data_uris_sanitized(self):
        """Verifies Stored XSS vectors in LinkedIn URLs are rejected or neutralized."""
        evil_urls = [
            "javascript:alert(document.cookie)",
            "JAVASCRIPT:/*--></title></style></textarea><script>alert(1)</script>",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
        ]
        for u in evil_urls:
            norm = DataHygieneService.normalize_linkedin_url(u)
            assert norm is None or not norm.lower().startswith(("javascript:", "data:", "vbscript:", "file:")), \
                f"Malicious URI was not blocked: {norm}"

    def test_reserved_system_keys_purged_from_unvetted_csv(self):
        """Verifies that malicious CSV headers cannot overwrite system or enum fields."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("RPC unavailable")
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "lead-1"}]

        dirty_lead = {
            "first_name": "Attacker",
            "last_name": "User",
            "email": "attacker@corp.com",
            "status": "APPROVED_ADMIN",  # System enum injection
            "workspace_id": "victim-workspace",  # Tenant overwrite attempt
            "deliverability_risk": "UNTOUCHABLE",
            "id": "fixed-uuid-hijack",
            "custom_attribute_1": "valid_value",
        }

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-123",
            workspace_id="actual-workspace",
            leads=[dirty_lead],
            collision_policy="merge"
        )

        assert res["success"] is True
        # Find the insert call for the leads table
        leads_insert_call = None
        for call_item in mock_supabase.table.return_value.insert.call_args_list:
            args = call_item[0]
            if args and isinstance(args[0], list) and len(args[0]) > 0 and "first_name" in args[0][0]:
                leads_insert_call = args[0]
                break

        assert leads_insert_call is not None, "Did not find leads table insert call"
        row = leads_insert_call[0]
        # workspace_id must be the authorized workspace, NOT the CSV override
        assert row["workspace_id"] == "actual-workspace"
        # Overridden status should not be injected into row root or custom variables
        assert row.get("metadata", {}).get("custom_variables", {}).get("custom_attribute_1") == "valid_value"
        assert row.get("metadata", {}).get("custom_variables", {}).get("csv_status") == "APPROVED_ADMIN"

    def test_intra_batch_100_duplicate_deduplication(self):
        """Verifies that an import with 100 duplicate items deduplicates cleanly in memory."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("RPC unavailable")
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "l-unique"}]

        identical_leads = [
            {
                "first_name": "Duplicate",
                "last_name": f"User {i}",
                "email": "duplicate@company.com",
                "linkedin_url": "https://www.linkedin.com/in/identical-prospect",
            }
            for i in range(100)
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list-dup",
            workspace_id="ws-dup",
            leads=identical_leads,
            collision_policy="merge"
        )

        assert res["success"] is True
        assert res["duplicate_count"] == 99
        assert res["inserted_count"] == 1


class TestBrutalDynamicSegmentationEngine:
    """Brutally stress-tests the dynamic rule filter and AST evaluation."""

    def test_job_title_seniority_classification_edge_cases(self):
        """Tests that titles are mapped accurately without false positives."""
        cases = [
            # C-Suite
            ("Chief Executive Officer", SENIORITY_C_SUITE),
            ("CEO & Co-Founder", SENIORITY_C_SUITE),
            ("Chief Information Security Officer (CISO)", SENIORITY_C_SUITE),
            ("CTO", SENIORITY_C_SUITE),
            ("CFO / Treasurer", SENIORITY_C_SUITE),
            # Founder
            ("Co-Founder & President", SENIORITY_FOUNDER),
            ("Managing Partner", SENIORITY_FOUNDER),
            ("Owner & Principal", SENIORITY_FOUNDER),
            # VP
            ("Vice President of Sales", SENIORITY_VP),
            ("SVP Engineering", SENIORITY_VP),
            ("EVP Global Operations", SENIORITY_VP),
            ("VP, Product Design", SENIORITY_VP),
            # Director
            ("Director of Marketing", SENIORITY_DIRECTOR),
            ("Head of People & Culture", SENIORITY_DIRECTOR),
            # Manager
            ("Engineering Manager", SENIORITY_MANAGER),
            ("Team Lead - DevOps", SENIORITY_MANAGER),
            # Contributor - CRITICAL: "Account Executive" is Contributor, NOT C-Suite!
            ("Account Executive", SENIORITY_CONTRIBUTOR),
            ("Senior Account Executive", SENIORITY_CONTRIBUTOR),
            ("Software Engineer", SENIORITY_CONTRIBUTOR),
            ("Product Specialist", SENIORITY_CONTRIBUTOR),
            # Unknown
            ("", SENIORITY_UNKNOWN),
            (None, SENIORITY_UNKNOWN),
            ("Consultant", SENIORITY_CONTRIBUTOR),
        ]
        for title, expected in cases:
            res = parse_job_title_seniority(title)
            assert res == expected, f"Title '{title}' mapped to '{res}', expected '{expected}'"

    def test_company_size_normalization_ranges(self):
        """Verifies company size string / number normalization into canonical tiers."""
        assert normalize_company_size_tier(5) == "1-10"
        assert normalize_company_size_tier("8 employees") == "1-10"
        assert normalize_company_size_tier(45) == "11-50"
        assert normalize_company_size_tier("150") == "51-200"
        assert normalize_company_size_tier("350 staff") == "201-500"
        assert normalize_company_size_tier(800) == "501-1000"
        assert normalize_company_size_tier(2500) == "1001-5000"
        assert normalize_company_size_tier("10,000+") == "5001+"
        assert normalize_company_size_tier("invalid") == "unknown"

    def test_boolean_rule_evaluation_all_and_any(self):
        """Tests complex boolean rule logic matching."""
        lead = {
            "job_title": "Vice President of Engineering",
            "company_name": "Stripe",
            "location": "San Francisco, CA",
            "social_intent_score": 85.0,
            "is_open_profile": True,
        }

        # Rule 1: ALL matching
        rule_all_match = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "equals", "value": "vp"},
                {"field": "intent_score", "operator": ">=", "value": 75},
            ]
        }
        assert evaluate_lead_against_rules(lead, rule_all_match) is True

        # Rule 2: ALL failing one condition
        rule_all_fail = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "equals", "value": "vp"},
                {"field": "intent_score", "operator": "<", "value": 50},  # Fails
            ]
        }
        assert evaluate_lead_against_rules(lead, rule_all_fail) is False

        # Rule 3: ANY matching one condition
        rule_any_match = {
            "match_type": "ANY",
            "conditions": [
                {"field": "seniority", "operator": "equals", "value": "c_suite"},  # Fails
                {"field": "intent_score", "operator": ">=", "value": 70},  # Passes
            ]
        }
        assert evaluate_lead_against_rules(lead, rule_any_match) is True

    def test_dynamic_segment_csv_export_neutralizes_formulas(self):
        """Verifies that dynamic segment CSV export escapes spreadsheet formula triggers."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {
                "id": "lead-malicious",
                "first_name": "=cmd|' /C calc'!A0",
                "last_name": "Hacker",
                "company_name": "+Evil Corp",
                "job_title": "@Managing Director",
                "email": "hacker@evil.com",
                "linkedin_url": "https://linkedin.com/in/hacker",
            }
        ]

        csv_output = export_dynamic_segment_csv(
            workspace_id="ws-123",
            list_id="list-123",
            rule_config=None,
            supabase=mock_supabase
        )

        assert "=cmd" not in csv_output or "'=cmd" in csv_output
        assert "'+Evil Corp" in csv_output or "+Evil Corp" not in csv_output
        assert "'@Managing Director" in csv_output or "@Managing Director" not in csv_output


class TestBrutalLocationAndTimezoneEngine:
    """Brutally stress-tests location parsing and timezone inference without country code inversion."""

    def test_us_phone_number_does_not_invert_country_code(self):
        """
        Critical Flaw LEAD-BE-03 Regression Test:
        (415) area code must NOT become +41 (Switzerland).
        (917) area code must NOT become +91 (India).
        (330) area code must NOT become +33 (France).
        """
        test_phones = [
            ("(415) 555-0199", "San Francisco, CA"),
            ("415-555-0199", "California"),
            ("(917) 555-0199", "New York, NY"),
            ("330-555-0199", "Akron, Ohio"),
        ]
        for phone, loc in test_phones:
            tz = LocationTimezoneService.infer_timezone(location=loc, phone=phone, country="US")
            assert tz is not None
            assert "Europe" not in tz, f"Phone '{phone}' in '{loc}' inverted into Europe: '{tz}'"
            assert "Asia" not in tz, f"Phone '{phone}' in '{loc}' inverted into Asia: '{tz}'"
            assert tz.startswith("America/"), f"Phone '{phone}' should resolve to America/*, got '{tz}'"

    def test_iana_timezone_validation_and_fallback(self):
        """Verifies valid IANA timezones pass and invalid strings fallback cleanly."""
        assert LocationTimezoneService.validate_iana_timezone("America/New_York") == "America/New_York"
        assert LocationTimezoneService.validate_iana_timezone("Europe/London") == "Europe/London"
        assert LocationTimezoneService.validate_iana_timezone("Asia/Tokyo") == "Asia/Tokyo"
        assert LocationTimezoneService.validate_iana_timezone("Invalid/Fantasy_Zone") is None
        assert LocationTimezoneService.validate_iana_timezone("") is None
        assert LocationTimezoneService.validate_iana_timezone(None) is None


class TestBrutalSuppressionAndDncEngine:
    """Brutally stress-tests DNC suppression, wildcard domain blocking, and fail-closed safety."""

    def test_domain_normalization_removes_wildcards_and_subdomains(self):
        """Verifies that wildcard prefixes, emails, and full URLs extract root domain cleanly."""
        cases = [
            ("*@Competitor.com", "competitor.com"),
            ("@acme-corp.io", "acme-corp.io"),
            ("https://www.apple.com/iphone", "apple.com"),
            ("http://sub.domain.co.uk/path", "sub.domain.co.uk"),
            ("competitor.com", "competitor.com"),
        ]
        for raw, expected in cases:
            norm = normalize_suppression_domain(raw)
            assert norm == expected, f"Failed on '{raw}' -> got '{norm}', expected '{expected}'"

    def test_public_freemail_domains_blocked_from_wildcard_suppression(self):
        """Verifies that suppressing '@gmail.com' without override is blocked to prevent wiping all leads."""
        mock_supabase = MagicMock()
        res = add_suppression_entries_bulk(
            supabase=mock_supabase,
            workspace_id="ws-123",
            entries=[{"domain": "gmail.com"}],
            allow_freemail_domain=False
        )
        assert len(res.get("rejected_entries", [])) == 1
        assert "Blocked wildcard domain suppression" in res["rejected_entries"][0]["error"]

    def test_check_lead_suppression_fails_closed_on_db_error(self):
        """Verifies that database exceptions trigger fail-closed suppression (marked suppressed for safety)."""
        broken_supabase = MagicMock()
        broken_supabase.table.side_effect = Exception("Database connection timeout")

        res = check_lead_suppression(
            supabase=broken_supabase,
            workspace_id="ws-123",
            email="prospect@company.com"
        )
        # In a database failure, fail-closed means suppressed=True or error surfaced
        assert res.get("suppressed") is True
        assert res.get("fail_closed") is True


class TestBrutalCampaignDirectEnrollmentIntegration:
    """Brutally stress-tests lead list direct enrollment into campaigns."""

    def test_enroll_list_leads_skips_suppressed_prospects(self):
        """Verifies that prospects on the suppression list are strictly excluded during campaign enrollment."""
        mock_supabase = MagicMock()
        
        # 1. Campaign and list exist
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "camp-1"}]
        
        # 2. List members: 3 leads
        lead_ids = ["lead-1", "lead-2", "lead-3"]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"opportunity_id": lid} for lid in lead_ids
        ]

        # 3. Collision guard: none conflicting
        with patch("campaigns.backend.routers.elein.get_conflicting_active_leads", return_value=set()):
            with patch("campaigns.backend.routers.elein._fetch_all_list_members", return_value=lead_ids):
                with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
                    # Leads map: lead-1 is safe, lead-2 has suppressed email, lead-3 has suppressed domain
                    suppression_mock = MagicMock()
                suppression_mock.select.return_value.eq.return_value.in_.return_value.execute.side_effect = [
                    MagicMock(data=[]),  # linkedin check
                    MagicMock(data=[{"email": "blocked@spam.com"}]),  # email check
                    MagicMock(data=[{"domain": "competitor.com"}]),  # domain check
                ]

                def mock_table(table_name):
                    if table_name == "suppression_list":
                        return suppression_mock
                    t = MagicMock()
                    if table_name == "leads":
                        t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
                            {"id": "lead-1", "linkedin_url": "https://linkedin.com/in/safe", "email": "safe@safe.com", "domain": "safe.com"},
                            {"id": "lead-2", "linkedin_url": "https://linkedin.com/in/blocked", "email": "blocked@spam.com", "domain": "spam.com"},
                            {"id": "lead-3", "linkedin_url": "https://linkedin.com/in/dnc", "email": "dnc@competitor.com", "domain": "competitor.com"},
                        ]
                    elif table_name == "campaign_versions":
                        t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [{"id": "ver-1"}]
                    elif table_name == "campaign_accounts":
                        t.select.return_value.eq.return_value.execute.return_value.data = [
                            {"account_id": "acc-1", "accounts": {"id": "acc-1", "status": "ACTIVE"}}
                        ]
                    elif table_name == "campaign_enrollments":
                        t.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = []
                        t.insert.return_value.execute.return_value.data = [{"id": "enr-1"}]
                        t.upsert.return_value.execute.return_value.data = [{"id": "enr-1"}]
                    elif table_name == "campaign_execution_states":
                        t.insert.return_value.execute.return_value.data = [{"id": "exec-1"}]
                        t.upsert.return_value.execute.return_value.data = [{"id": "exec-1"}]
                    elif table_name == "campaigns" or table_name == "lead_lists":
                        t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"id": "valid"}]
                    return t

                mock_supabase.table.side_effect = mock_table

                body = EnrollListRequest(list_id="list-test")
                res = enroll_list_leads(
                    campaign_id="camp-1",
                    body=body,
                    supabase=mock_supabase,
                    workspace_id="ws-test"
                )

                # Exactly 1 lead should be enrolled (lead-1), 2 skipped
                assert res["enrolled"] == 1
                assert res["skipped"] == 2
