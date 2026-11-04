"""
test_pillar5_lead_ingestion_and_hygiene.py
==========================================
Production-grade test suite verifying Pillar 5:
Lead Ingestion, Data Hygiene & Recipient Safety Engine
Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Phase 5.1: Streaming Bulk Ingestion (chunked parsing, BOM decode, formula sanitization)
- Phase 5.2: Real-Time Spam Trap & Role-Based Shield (abuse/postmaster traps, disposable domains, quarantine)
- Phase 5.3: Recipient Working Hours & Timezone Guard (local time windows, Friday->Monday rollover, jitter)
- Phase 5.4: Cross-Campaign Friendly Fire & Domain Exclusivity (single lead & account-level exclusivity)
"""

import io
import time
import pytz
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from core.backend.services.email_shield_service import (
    EmailShieldService,
    EmailClassification,
    SPAM_TRAP_PREFIXES,
    ROLE_BASED_PREFIXES,
)
from leads.backend.services.lead_ingestion_service import (
    stream_parse_csv_leads,
    execute_streaming_bulk_import_leads,
    execute_bulk_import_leads,
    _canonicalize_header,
    _sanitize_csv_cell,
    split_full_name,
)
from campaigns.backend.services.timezone_utils import (
    is_working_hours,
    calculate_next_run_at,
    calculate_next_run_with_jitter,
    parse_schedule_config,
)
from campaigns.backend.services.collision_guard import (
    get_conflicting_active_leads,
    is_lead_active_in_other_campaign,
    check_company_domain_exclusivity,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


# ==============================================================================
# Phase 5.1: Streaming Bulk Ingestion & Sanitization
# ==============================================================================

class TestStreamingCSVIngestion:
    """Tests for memory-bounded CSV streaming, encoding resilience, and formula injection defense."""

    def test_canonicalize_header_fuzzy_mapping(self):
        """Layer 2: Maps varying user-submitted CSV headers to canonical field names."""
        assert _canonicalize_header("First Name") == "first_name"
        assert _canonicalize_header("work_email") == "email"
        assert _canonicalize_header("E-Mail") == "email"
        assert _canonicalize_header("Company Name") == "company_name"
        assert _canonicalize_header("Organization") == "company_name"
        assert _canonicalize_header("Job Title") == "job_title"
        assert _canonicalize_header("LinkedIn Profile") == "linkedin_url"
        assert _canonicalize_header("custom_variable_1") == "custom_variable_1"

    def test_formula_injection_stripping(self):
        """Layer 2: Strips spreadsheet command execution characters (=, +, -, @, \\t, \\r)."""
        assert _sanitize_csv_cell("=cmd|'/C calc'!A0") == "cmd|'/C calc'!A0"
        assert _sanitize_csv_cell("+1234567890") == "1234567890"
        assert _sanitize_csv_cell("-DANGEROUS_PAYLOAD") == "DANGEROUS_PAYLOAD"
        assert _sanitize_csv_cell("@SUM(1,2)") == "SUM(1,2)"
        assert _sanitize_csv_cell("Normal Text") == "Normal Text"

    def test_stream_parse_csv_leads_utf8_with_bom(self):
        """Layer 1: Automatically detects and strips UTF-8 BOM (\\ufeff) without corrupting first header."""
        csv_bytes = b"\xef\xbb\xbfFirst Name,Last Name,Email,Company\nAlice,Smith,alice@corp.com,Acme Corp\nBob,Jones,bob@corp.com,Beta Inc"
        batches = list(stream_parse_csv_leads(csv_bytes, batch_size=10))
        assert len(batches) == 1
        leads = batches[0]
        assert len(leads) == 2
        assert leads[0]["first_name"] == "Alice"
        assert leads[0]["email"] == "alice@corp.com"
        assert leads[1]["first_name"] == "Bob"

    def test_stream_parse_csv_leads_bounded_chunks(self):
        """Layer 0: Yields bounded batches without loading all rows into RAM simultaneously."""
        # Generate 25 CSV rows
        header = "First Name,Email,Company\n"
        rows = [f"Lead_{i},lead_{i}@domain.com,Company_{i}\n" for i in range(25)]
        csv_content = header + "".join(rows)

        batches = list(stream_parse_csv_leads(csv_content, batch_size=10))
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5

    def test_execute_streaming_bulk_import_leads(self):
        """Layer 0 & 1: Streams CSV into execute_bulk_import_leads and aggregates telemetry."""
        csv_content = "First Name,Last Name,Email,Company\nSarah,Connor,sarah@skynet.com,Cyberdyne\nJohn,Connor,john@resistance.org,Resistance"
        
        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        mock_table.insert.return_value = mock_table

        summary = execute_streaming_bulk_import_leads(
            supabase=mock_sb,
            list_id="list_stream_1",
            workspace_id="ws_stream_1",
            stream_or_content=csv_content,
            batch_size=500,
        )
        assert summary["success"] is True
        assert summary["total_read"] == 2
        assert summary["batches_processed"] == 1


# ==============================================================================
# Phase 5.2: Real-Time Spam Trap & Role-Based Shield
# ==============================================================================

class TestSpamTrapAndRoleBasedShield:
    """Tests for honeypot detection, plus-tag normalization, and pre-campaign quarantining."""

    def test_spam_trap_detection_and_quarantine(self):
        """Layer 0 & 1: Honeypot prefixes are identified as SPAM_TRAP and quarantined."""
        audit_abuse = EmailShieldService.audit_email_address("abuse@targetdomain.com")
        assert audit_abuse["is_spam_trap"] is True
        assert audit_abuse["classification"] == EmailClassification.SPAM_TRAP.value
        assert "CRITICAL" in audit_abuse["deliverability_risk"]

        audit_postmaster = EmailShieldService.audit_email_address("postmaster@targetdomain.com")
        assert audit_postmaster["is_spam_trap"] is True

        audit_spamtrap = EmailShieldService.audit_email_address("spamtrap@security.net")
        assert audit_spamtrap["is_spam_trap"] is True

    def test_plus_tag_subaddressing_normalization(self):
        """Layer 2: Subaddress evasion (abuse+test@domain.com) is normalized and flagged."""
        audit = EmailShieldService.audit_email_address("abuse+campaign_outreach@corp.com")
        assert audit["is_spam_trap"] is True
        assert audit["classification"] == EmailClassification.SPAM_TRAP.value

    def test_role_based_address_flagging(self):
        """Layer 0: Departmental role addresses (billing, support, sales) are categorized."""
        audit_billing = EmailShieldService.audit_email_address("billing@saas.com")
        assert audit_billing["is_role_based"] is True
        assert audit_billing["classification"] == EmailClassification.ROLE_BASED.value

        audit_support = EmailShieldService.audit_email_address("support@saas.com")
        assert audit_support["is_role_based"] is True

    def test_disposable_domain_detection(self):
        """Layer 0: Ephemeral throwaway domains are categorized as DISPOSABLE."""
        audit = EmailShieldService.audit_email_address("tempuser@mailinator.com")
        assert audit["is_disposable"] is True
        assert audit["classification"] == EmailClassification.DISPOSABLE.value

    def test_bulk_importer_quarantines_spam_traps(self):
        """Layer 1: execute_bulk_import_leads automatically sets status='QUARANTINED' for spam traps."""
        leads = [
            {"first_name": "Trap", "email": "abuse@honeypot.org", "company": "Honey Corp"},
            {"first_name": "Valid", "email": "valid.ceo@enterprise.com", "company": "Enterprise Inc"},
        ]
        mock_sb = MagicMock()
        mock_sb.rpc.side_effect = Exception("RPC function not available in mock")
        mock_table = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        mock_table.insert.return_value = mock_table

        # Intercept the processed leads passed to direct insert
        captured_inserts = []
        def capture_insert(payload):
            captured_inserts.extend(payload if isinstance(payload, list) else [payload])
            return MagicMock(data=payload if isinstance(payload, list) else [payload])
        mock_table.insert.side_effect = capture_insert

        res = execute_bulk_import_leads(
            supabase=mock_sb,
            list_id="list_shield_1",
            workspace_id="ws_shield_1",
            leads=leads,
        )
        assert res["success"] is True

        # Find the abuse lead in captured leads
        abuse_lead = next((l for l in captured_inserts if l.get("email") == "abuse@honeypot.org"), None)
        assert abuse_lead is not None
        assert abuse_lead["status"] == "QUARANTINED"
        assert abuse_lead["quarantine_reason"] == "SPAM_TRAP_DETECTED"


# ==============================================================================
# Phase 5.3: Recipient Working Hours & Timezone Guard
# ==============================================================================

class TestRecipientWorkingHoursAndTimezoneGuard:
    """Tests for recipient working hours, weekend rollover, and thunder-herd jitter."""

    def test_is_working_hours_daytime_vs_night(self):
        """Layer 0: Correctly evaluates whether recipient local time is inside working hours."""
        tz_ny = pytz.timezone("America/New_York")
        # Wednesday 10:30 AM EDT -> Inside window (9:00 - 17:00)
        wed_10am = tz_ny.localize(datetime(2026, 10, 21, 10, 30, 0))
        assert is_working_hours("America/New_York", schedule={"start_hour": 9, "end_hour": 17}, now_dt=wed_10am) is True

        # Wednesday 2:30 AM EDT -> Outside window
        wed_2am = tz_ny.localize(datetime(2026, 10, 21, 2, 30, 0))
        assert is_working_hours("America/New_York", schedule={"start_hour": 9, "end_hour": 17}, now_dt=wed_2am) is False

    def test_friday_evening_rollover_to_monday_morning(self):
        """Layer 0 & 1: Friday after 17:00 local time rolls over to Monday 09:00 AM local time."""
        tz_ny = pytz.timezone("America/New_York")
        # Friday October 23, 2026 at 6:30 PM EDT (18:30)
        fri_evening = tz_ny.localize(datetime(2026, 10, 23, 18, 30, 0))

        # Schedule: Standard Mon-Fri (active_days: 0-4), start 9, end 17
        schedule = {"start_hour": 9, "end_hour": 17, "weekend_sending": False}
        next_run_utc = calculate_next_run_at(base_time=fri_evening, target_tz="America/New_York", schedule=schedule)
        
        # Convert next run back to America/New_York
        next_run_ny = next_run_utc.astimezone(tz_ny)
        # Expected: Monday October 26, 2026 at 09:00 AM
        assert next_run_ny.weekday() == 0  # Monday
        assert next_run_ny.hour == 9
        assert next_run_ny.minute == 0

    def test_calculate_next_run_with_jitter_prevents_burst(self):
        """Layer 1: Adds pseudo-random jitter (5-25 min) when rolling over to a new window."""
        tz_ny = pytz.timezone("America/New_York")
        fri_evening = tz_ny.localize(datetime(2026, 10, 23, 19, 0, 0))
        schedule = {"start_hour": 9, "end_hour": 17, "weekend_sending": False}

        next_run_jitter = calculate_next_run_with_jitter(
            base_time=fri_evening,
            target_tz="America/New_York",
            schedule=schedule,
            jitter_range=(5, 25),
            lead_id="lead_jitter_test_123",
        )
        local_jitter = next_run_jitter.astimezone(tz_ny)
        assert local_jitter.weekday() == 0  # Monday
        assert local_jitter.hour == 9
        assert 5 <= local_jitter.minute <= 25


# ==============================================================================
# Phase 5.4: Cross-Campaign Friendly Fire & Company Domain Exclusivity
# ==============================================================================

class TestCrossCampaignFriendlyFireAndDomainExclusivity:
    """Tests for single-lead friendly fire deferral and account-level exclusivity."""

    def test_single_lead_friendly_fire_detected(self):
        """Layer 0: Detects when lead has active in-flight states in another campaign."""
        mock_sb = MagicMock()
        mock_enr = MagicMock()
        mock_sb.table.side_effect = lambda t: mock_enr

        # Return enrollment in campaign_B
        mock_enr.select.return_value = mock_enr
        mock_enr.eq.return_value = mock_enr
        mock_enr.neq.return_value = mock_enr
        mock_enr.in_.return_value = mock_enr

        # Mock enrollment in another campaign
        mock_enr.execute.side_effect = [
            MagicMock(data=[{"id": "enr_b", "campaign_id": "camp_B", "lead_id": "lead_123"}]),  # enrollments
            MagicMock(data=[{"id": "camp_B", "status": "ACTIVE"}]),                                 # active campaigns
            MagicMock(data=[{"enrollment_id": "enr_b", "status": "running"}]),                      # in-flight state
        ]

        is_colliding = is_lead_active_in_other_campaign(
            mock_sb,
            workspace_id="ws_1",
            lead_id="lead_123",
            exclude_campaign_id="camp_A",
        )
        assert is_colliding is True

    def test_company_domain_exclusivity_freemail_bypass(self):
        """Layer 1: Consumer freemail domains (gmail.com, yahoo.com) are exempt from corporate account collision."""
        res = check_company_domain_exclusivity(
            supabase_client=MagicMock(),
            workspace_id="ws_1",
            company_domain="gmail.com",
            exclude_campaign_id="camp_A",
            strict_account_exclusivity=True,
        )
        assert res["collision_detected"] is False
        assert res["reason"] == "FREEMAIL_DOMAIN_EXEMPT"

    def test_company_domain_exclusivity_blocks_simultaneous_account_outreach(self):
        """Layer 0: Sibling leads at the same corporate domain cannot be contacted simultaneously across campaigns."""
        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_sb.table.side_effect = lambda t: mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.neq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.limit.return_value = mock_table

        # Mock leads table query returning 2 leads for domain 'acme-corp.com'
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": "lead_vp_eng"}, {"id": "lead_cto"}]),                          # domain sibling leads
            MagicMock(data=[{"id": "enr_rep_b", "campaign_id": "camp_B", "lead_id": "lead_cto"}]), # enrollments
            MagicMock(data=[{"id": "camp_B", "status": "ACTIVE"}]),                                 # active campaigns
            MagicMock(data=[{"enrollment_id": "enr_rep_b", "status": "waiting_for_reply"}]),       # in-flight state
        ]

        collision_res = check_company_domain_exclusivity(
            supabase_client=mock_sb,
            workspace_id="ws_1",
            company_domain="acme-corp.com",
            exclude_campaign_id="camp_A",
            strict_account_exclusivity=True,
        )
        assert collision_res["collision_detected"] is True
        assert collision_res["company_domain"] == "acme-corp.com"
        assert collision_res["reason"] == "ACCOUNT_EXCLUSIVITY_COLLISION"
        assert collision_res["conflicting_lead_id"] == "lead_cto"
