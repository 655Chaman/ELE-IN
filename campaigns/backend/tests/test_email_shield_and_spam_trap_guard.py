"""
test_email_shield_and_spam_trap_guard.py — Paranoia Automated Test Suite for Issue 9
(ESP Spam Trap, Role-Based Mailbox & Disposable Domain Shield).

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - Pristine spam trap and honeypot detection (abuse@, postmaster@, spam@, trap@, honeypot@).
    - Subaddressed / plus-tag spam trap detection (abuse+marketing@, spam+inbound@).
    - Departmental role-based address detection (info@, admin@, support@, sales@, billing@, jobs@, careers@).
    - Explicit role-based policy overrides (allow_role_based=True -> LOW_RISK, can_safely_send=True).
    - 120+ disposable / ephemeral domain detection (mailinator.com, guerrillamail.com, 10minutemail.com, yopmail.com).
    - Consumer free webmail detection (gmail.com, yahoo.com, hotmail.com, outlook.com).
    - Corporate B2B email deliverability verification (alex@stripe.com, mark@notion.so -> SAFE).
    - Case-insensitivity, leading/trailing whitespace, and display format angle brackets parsing.
    - Department category mappings and regional consumer webmail domains.

  - Layer 1: Environmental Failure Analysis
    - Executor aborts outreach on spam traps (status="skipped", reason="spam_trap_detected", 0 dispatched).
    - Executor rejects disposable emails (status="skipped", reason="disposable_email_rejected").
    - Executor blocks role-based mailboxes by default (status="skipped", reason="role_based_email_blocked").
    - Executor permits role-based mailboxes when explicitly configured (allow_role_based=True / send_to_role_inboxes=True).
    - Executor enriches outcome telemetry with email_classification and deliverability_risk.
    - Lead ingestion quarantines spam traps (status="QUARANTINED", quarantine_reason="SPAM_TRAP_DETECTED").
    - Lead ingestion tags email_classification, is_role_based, is_disposable, and deliverability_risk.
    - Lead ingestion preserves clean corporate and consumer webmail leads without quarantine.
    - Disposable subdomain resolution (user@sub.mailinator.com, user@deep.nested.trashmail.com).
    - Batch audit aggregate deliverability statistics and safe_to_send_ratio_pct calculations.
    - Batch audit maximum ceiling clamp (clamped to 10,000 items to defend against memory exhaustion).
    - Batch audit defensive handling of empty and None inputs.

  - Layer 2: Human Paranoia & Security Defense
    - Router endpoint POST /api/elein/deliverability/audit-email returns structured audit.
    - Router endpoint POST /api/elein/deliverability/audit-batch returns aggregate batch metrics.
    - Malformed email inputs handled safely (None, "", "@missing.com", "user@", "user@.com", "://", "@@").
    - NUL byte and ASCII control character injection stripped cleanly (user\x00@acme.com, user\r\n@acme.com).
    - Cross-tenant IDOR defense in router endpoints (strict workspace dependency scoping).
    - Overlong email string buffer overflow defense (>254 chars total, >64 chars local).
    - Display name and mailto: protocol injection sanitization (mailto:sales@stripe.com -> sales@stripe.com).
    - Multiple plus-tag subaddressing normalization (abuse+promo+2026@domain.com).
    - Router role-based override verification via API.
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List

from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from core.backend.services.email_shield_service import (
    EmailShieldService,
    EmailClassification,
    SPAM_TRAP_PREFIXES,
    ROLE_BASED_PREFIXES,
    ROLE_CATEGORY_MAP,
    DISPOSABLE_DOMAINS,
    FREE_WEBMAIL_DOMAINS,
    MAX_BATCH_SIZE,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads
from campaigns.backend.routers.elein import (
    EmailAuditRequest,
    EmailBatchAuditRequest,
    audit_email_endpoint,
    audit_email_batch_endpoint,
)


class TestEmailShieldAndSpamTrapGuard(unittest.TestCase):
    """
    Comprehensive Three-Layer Paranoia Test Automation Suite for Issue 9:
    ESP Spam Trap, Role-Based Mailbox & Disposable Domain Shield.
    """

    def setUp(self):
        self.workspace_id = "ws-shield-paranoia-test"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER (CORE MECHANICS)
    # =========================================================================

    def test_pristine_spam_trap_detection(self):
        """
        Layer 0: Pristine spam traps and honeypots (abuse@, postmaster@, spam@, trap@, honeypot@)
        flagged as SPAM_TRAP and can_safely_send=False with deliverability_risk='CRITICAL_SPAM_TRAP'.
        """
        trap_emails = [
            "abuse@company.com",
            "postmaster@company.com",
            "spam@company.com",
            "trap@domain.com",
            "honeypot@domain.com",
            "spamtrap@security.org",
            "noc@backbone.net",
            "security@enterprise.com",
            "phish@bank.com",
        ]
        for em in trap_emails:
            audit = EmailShieldService.audit_email_address(em)
            self.assertTrue(audit["valid"], f"Expected valid syntax for {em}")
            self.assertEqual(audit["classification"], EmailClassification.SPAM_TRAP.value, f"Failed for {em}")
            self.assertTrue(audit["is_spam_trap"], f"Expected is_spam_trap=True for {em}")
            self.assertFalse(audit["can_safely_send"], f"Must not allow sending to spam trap {em}")
            self.assertEqual(audit["deliverability_risk"], "CRITICAL_SPAM_TRAP")
            self.assertEqual(audit["rejection_reason"], "PRISTINE_SPAM_TRAP_PREFIX")
            self.assertFalse(audit["is_corporate"])

    def test_subaddressed_spam_trap_detection(self):
        """
        Layer 0: Subaddressed spam traps with plus-tags (abuse+marketing@, spam+inbound@)
        correctly stripped to their root prefix and identified as SPAM_TRAP.
        """
        subaddressed_traps = [
            "abuse+marketing@company.com",
            "spam+inbound@acme.com",
            "postmaster+alerts@domain.io",
            "trap+coldoutreach@leadgen.co",
            "honeypot+tag123@enterprise.org",
        ]
        for em in subaddressed_traps:
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(audit["classification"], EmailClassification.SPAM_TRAP.value, f"Failed for {em}")
            self.assertTrue(audit["is_spam_trap"], f"Expected is_spam_trap=True for {em}")
            self.assertFalse(audit["can_safely_send"], f"Expected can_safely_send=False for {em}")
            self.assertEqual(audit["deliverability_risk"], "CRITICAL_SPAM_TRAP")

    def test_role_based_address_detection(self):
        """
        Layer 0: Departmental and generic role-based addresses (info@, admin@, support@, sales@, billing@, jobs@, careers@)
        flagged as ROLE_BASED and can_safely_send=False by default.
        """
        role_emails = [
            ("info@company.com", "GENERAL_INQUIRY"),
            ("admin@company.com", "ADMINISTRATION"),
            ("support@company.com", "SUPPORT"),
            ("sales@company.com", "SALES"),
            ("billing@company.com", "FINANCE_BILLING"),
            ("jobs@company.com", "HUMAN_RESOURCES"),
            ("careers@company.com", "HUMAN_RESOURCES"),
            ("legal@company.com", "LEGAL_COMPLIANCE"),
            ("office@company.com", "OFFICE_MANAGEMENT"),
            ("contact@company.com", "GENERAL_INQUIRY"),
        ]
        for em, expected_cat in role_emails:
            audit = EmailShieldService.audit_email_address(em, allow_role_based=False)
            self.assertEqual(audit["classification"], EmailClassification.ROLE_BASED.value, f"Failed for {em}")
            self.assertTrue(audit["is_role_based"], f"Expected is_role_based=True for {em}")
            self.assertEqual(audit["role_category"], expected_cat)
            self.assertFalse(audit["can_safely_send"], f"Expected default blocked send for {em}")
            self.assertEqual(audit["deliverability_risk"], "HIGH_RISK")
            self.assertEqual(audit["rejection_reason"], "ROLE_BASED_MAILBOX_DETECTED")
            self.assertFalse(audit["is_spam_trap"])

    def test_role_based_allowed_when_flag_enabled(self):
        """
        Layer 0: When allow_role_based=True, role-based mailboxes have can_safely_send=True
        and deliverability_risk='LOW_RISK'.
        """
        role_emails = ["info@company.com", "sales@company.com", "support@acme.io", "billing@saas.com"]
        for em in role_emails:
            audit = EmailShieldService.audit_email_address(em, allow_role_based=True)
            self.assertEqual(audit["classification"], EmailClassification.ROLE_BASED.value)
            self.assertTrue(audit["is_role_based"])
            self.assertTrue(audit["can_safely_send"], f"Should allow sending when allow_role_based=True for {em}")
            self.assertEqual(audit["deliverability_risk"], "LOW_RISK")
            self.assertIsNone(audit["rejection_reason"])

    def test_disposable_domain_detection(self):
        """
        Layer 0: Ephemeral and throwaway domains (mailinator.com, guerrillamail.com, 10minutemail.com, yopmail.com)
        flagged as DISPOSABLE with can_safely_send=False and deliverability_risk='HIGH_RISK'.
        """
        disposable_emails = [
            "user@mailinator.com",
            "test@guerrillamail.com",
            "temp@10minutemail.com",
            "alex@yopmail.com",
            "burner@trashmail.com",
            "temp@sharklasers.com",
            "throwaway@getairmail.com",
        ]
        for em in disposable_emails:
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(audit["classification"], EmailClassification.DISPOSABLE.value, f"Failed for {em}")
            self.assertTrue(audit["is_disposable"], f"Expected is_disposable=True for {em}")
            self.assertFalse(audit["can_safely_send"], f"Expected can_safely_send=False for {em}")
            self.assertEqual(audit["deliverability_risk"], "HIGH_RISK")
            self.assertEqual(audit["rejection_reason"], "DISPOSABLE_EMAIL_DOMAIN")

    def test_free_webmail_detection(self):
        """
        Layer 0: Major consumer free webmail addresses (gmail.com, yahoo.com, hotmail.com, outlook.com)
        flagged as FREE_WEBMAIL with can_safely_send=True and deliverability_risk='LOW_RISK'.
        """
        webmail_emails = [
            "john.doe@gmail.com",
            "sarah@yahoo.com",
            "test@hotmail.com",
            "dev@outlook.com",
            "founder@proton.me",
            "contractor@zoho.com",
            "freelancer@icloud.com",
        ]
        for em in webmail_emails:
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(audit["classification"], EmailClassification.FREE_WEBMAIL.value, f"Failed for {em}")
            self.assertTrue(audit["is_free_webmail"], f"Expected is_free_webmail=True for {em}")
            self.assertTrue(audit["can_safely_send"], f"Expected can_safely_send=True for {em}")
            self.assertEqual(audit["deliverability_risk"], "LOW_RISK")
            self.assertIsNone(audit["rejection_reason"])
            self.assertFalse(audit["is_corporate"])

    def test_corporate_b2b_email_verified(self):
        """
        Layer 0: Verified enterprise and B2B corporate domains (alex@stripe.com, sarah@apple.com, mark@notion.so)
        flagged as CORPORATE with can_safely_send=True and deliverability_risk='SAFE'.
        """
        corporate_emails = [
            "alex@stripe.com",
            "sarah@apple.com",
            "mark@notion.so",
            "elena@linear.app",
            "david@figma.com",
            "cto@retargeting.ai",
        ]
        for em in corporate_emails:
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(audit["classification"], EmailClassification.CORPORATE.value, f"Failed for {em}")
            self.assertTrue(audit["is_corporate"], f"Expected is_corporate=True for {em}")
            self.assertTrue(audit["can_safely_send"])
            self.assertEqual(audit["deliverability_risk"], "SAFE")
            self.assertIsNone(audit["rejection_reason"])
            self.assertFalse(audit["is_spam_trap"])
            self.assertFalse(audit["is_disposable"])
            self.assertFalse(audit["is_role_based"])
            self.assertFalse(audit["is_free_webmail"])

    def test_case_insensitivity_and_whitespace_trimming(self):
        """
        Layer 0: Email addresses with arbitrary casing and surrounding whitespace
        are normalized correctly before classification.
        """
        cases = [
            ("  ABUSE@COMPANY.COM  ", EmailClassification.SPAM_TRAP.value, False),
            ("  Info@Stripe.Com\t", EmailClassification.ROLE_BASED.value, False),
            (" USER@MAILINATOR.COM \n", EmailClassification.DISPOSABLE.value, False),
            (" John.Doe@GMAIL.com ", EmailClassification.FREE_WEBMAIL.value, True),
            ("  ALEX@NOTION.SO  ", EmailClassification.CORPORATE.value, True),
        ]
        for raw, expected_cls, expected_send in cases:
            audit = EmailShieldService.audit_email_address(raw)
            self.assertEqual(audit["classification"], expected_cls)
            self.assertEqual(audit["can_safely_send"], expected_send)

    def test_rfc_display_name_angle_bracket_extraction(self):
        """
        Layer 0: Extracts clean email from RFC 5322 display name formats ("First Last" <email@domain.com>).
        """
        formatted = '"Sarah Connor" <sarah@cyberdyne.systems>'
        audit = EmailShieldService.audit_email_address(formatted)
        self.assertEqual(audit["email"], "sarah@cyberdyne.systems")
        self.assertEqual(audit["classification"], EmailClassification.CORPORATE.value)
        self.assertTrue(audit["can_safely_send"])

        trap_formatted = '<abuse@honeypot-host.org>'
        audit_trap = EmailShieldService.audit_email_address(trap_formatted)
        self.assertEqual(audit_trap["email"], "abuse@honeypot-host.org")
        self.assertEqual(audit_trap["classification"], EmailClassification.SPAM_TRAP.value)

    def test_composite_spam_trap_prefixes(self):
        """
        Layer 0: Composite prefixes like spamtrap_marketing@ or honeypot123@ are detected as spam traps.
        """
        composite_traps = [
            "spamtrap_marketing@acme.com",
            "spamtrap12@domain.com",
            "honeypot_global@threat.intel",
            "honeypot99@corp.net",
        ]
        for em in composite_traps:
            is_trap, reason = EmailShieldService.is_spam_trap(em)
            self.assertTrue(is_trap, f"Expected trap detection for composite: {em}")
            self.assertEqual(reason, "PRISTINE_SPAM_TRAP_PREFIX")

    def test_department_category_mappings(self):
        """
        Layer 0: Specific role prefixes map to their expected organizational departments.
        """
        self.assertEqual(ROLE_CATEGORY_MAP.get("billing"), "FINANCE_BILLING")
        self.assertEqual(ROLE_CATEGORY_MAP.get("invoices"), "FINANCE_BILLING")
        self.assertEqual(ROLE_CATEGORY_MAP.get("accounting"), "FINANCE_BILLING")
        self.assertEqual(ROLE_CATEGORY_MAP.get("legal"), "LEGAL_COMPLIANCE")
        self.assertEqual(ROLE_CATEGORY_MAP.get("privacy"), "LEGAL_COMPLIANCE")
        self.assertEqual(ROLE_CATEGORY_MAP.get("compliance"), "LEGAL_COMPLIANCE")
        self.assertEqual(ROLE_CATEGORY_MAP.get("jobs"), "HUMAN_RESOURCES")
        self.assertEqual(ROLE_CATEGORY_MAP.get("careers"), "HUMAN_RESOURCES")
        self.assertEqual(ROLE_CATEGORY_MAP.get("hr"), "HUMAN_RESOURCES")
        self.assertEqual(ROLE_CATEGORY_MAP.get("admin"), "ADMINISTRATION")
        self.assertEqual(ROLE_CATEGORY_MAP.get("support"), "SUPPORT")
        self.assertEqual(ROLE_CATEGORY_MAP.get("sales"), "SALES")
        self.assertEqual(ROLE_CATEGORY_MAP.get("devnull"), "SYSTEM_DEVNULL")

    def test_regional_free_webmail_domains(self):
        """
        Layer 0: Regional and ccTLD variants of free webmail (yahoo.co.uk, hotmail.fr, gmx.de, yandex.ru)
        are categorized as FREE_WEBMAIL.
        """
        regional_emails = [
            "user@yahoo.co.uk",
            "test@yahoo.fr",
            "dev@hotmail.fr",
            "hans@gmx.de",
            "alex@yandex.ru",
        ]
        for em in regional_emails:
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(audit["classification"], EmailClassification.FREE_WEBMAIL.value, f"Failed for {em}")
            self.assertTrue(audit["is_free_webmail"])
            self.assertTrue(audit["can_safely_send"])

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS (INTEGRATION & RESILIENCE)
    # =========================================================================

    def test_executor_aborts_send_on_spam_trap(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email aborts immediately when to_email is a spam trap,
        returning status='skipped', reason='spam_trap_detected', and dispatching 0 emails.
        """
        data = {
            "to_email": "abuse@target.com",
            "subject": "Quick demo",
            "body": "Hi there, wanted to share our platform.",
            "lead_id": "lead-trap-1",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "spam_trap_detected")
        self.assertIn("spam trap or honeypot", res["error"])
        # Verify no database logging of outbound message took place
        self.mock_supabase.table.assert_not_called()

    def test_executor_aborts_send_on_disposable_email(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email aborts immediately on disposable emails,
        returning status='skipped' and reason='disposable_email_rejected'.
        """
        data = {
            "to_email": "fake@mailinator.com",
            "subject": "Platform introduction",
            "body": "Hello, check this out.",
            "lead_id": "lead-disp-1",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "disposable_email_rejected")
        self.assertIn("disposable/ephemeral", res["error"])

    def test_executor_blocks_role_based_by_default(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email blocks role-based mailboxes by default
        when no explicit override flag is present in node data.
        """
        data = {
            "to_email": "support@target.com",
            "subject": "Support inquiry follow up",
            "body": "Hello support team.",
            "lead_id": "lead-role-1",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "role_based_email_blocked")
        self.assertIn("blocked by deliverability policy", res["error"])

    def test_executor_allows_role_based_when_explicitly_configured(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email dispatches successfully when allow_role_based=True
        (or send_to_role_inboxes=True) is explicitly specified.
        """
        data = {
            "to_email": "sales@target.com",
            "subject": "Partnership inquiry",
            "body": "Hi Sales team, wanted to connect.",
            "lead_id": "lead-role-allowed-1",
            "allow_role_based": True,
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res.get("email_classification"), "ROLE_BASED")
        self.assertEqual(res.get("deliverability_risk"), "LOW_RISK")

    def test_executor_send_to_role_inboxes_alias_flag(self):
        """
        Layer 1: Alternative flag 'send_to_role_inboxes=True' is also honored by executor.
        """
        data = {
            "to_email": "info@prospectcorp.com",
            "subject": "General inquiry",
            "body": "Hi there.",
            "lead_id": "lead-alias-1",
            "send_to_role_inboxes": True,
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res.get("email_classification"), "ROLE_BASED")

    def test_executor_enriches_telemetry_on_corporate_send(self):
        """
        Layer 1: On successful corporate email send, executor outcome dictionary contains
        email_classification='CORPORATE' and deliverability_risk='SAFE'.
        """
        data = {
            "to_email": "alex@stripe.com",
            "subject": "Product feedback",
            "body": "Hi Alex, great work on Stripe Billing.",
            "lead_id": "lead-corp-1",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res.get("email_classification"), "CORPORATE")
        self.assertEqual(res.get("deliverability_risk"), "SAFE")

    def test_lead_ingestion_quarantines_spam_traps(self):
        """
        Layer 1: execute_bulk_import_leads automatically sets status='QUARANTINED' and
        quarantine_reason='SPAM_TRAP_DETECTED' for leads with spam trap addresses.
        """
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value.data = {"inserted_count": 2, "duplicate_count": 0}
        self.mock_supabase.rpc.return_value = mock_rpc

        leads = [
            {
                "first_name": "Trap",
                "last_name": "Account",
                "email": "abuse@malicious-domain.com",
                "company": "Spamhaus Test",
            },
            {
                "first_name": "Valid",
                "last_name": "Lead",
                "email": "contact@validcorp.com",
                "company": "Valid Corp",
            },
        ]

        res = execute_bulk_import_leads(
            supabase=self.mock_supabase,
            list_id="list-trap-quarantine",
            workspace_id=self.workspace_id,
            leads=leads,
        )
        self.assertTrue(res["success"])
        rpc_call = self.mock_supabase.rpc.call_args
        self.assertIsNotNone(rpc_call)
        p_leads = rpc_call[0][1]["p_leads"]
        self.assertEqual(len(p_leads), 2)

        # First lead (abuse@) must be quarantined
        trap_lead = p_leads[0]
        self.assertEqual(trap_lead["status"], "QUARANTINED")
        self.assertEqual(trap_lead["quarantine_reason"], "SPAM_TRAP_DETECTED")
        self.assertEqual(trap_lead["email_classification"], "SPAM_TRAP")
        self.assertEqual(trap_lead["deliverability_risk"], "CRITICAL_SPAM_TRAP")

        # Second lead (contact@) is role-based, not a spam trap
        clean_lead = p_leads[1]
        self.assertNotEqual(clean_lead.get("status"), "QUARANTINED")
        self.assertEqual(clean_lead["email_classification"], "ROLE_BASED")

    def test_lead_ingestion_tags_email_classification(self):
        """
        Layer 1: Ingested leads receive email_classification, is_role_based, is_disposable,
        and deliverability_risk metadata tags.
        """
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value.data = {"inserted_count": 3, "duplicate_count": 0}
        self.mock_supabase.rpc.return_value = mock_rpc

        leads = [
            {"email": "mark@notion.so", "first_name": "Mark"},
            {"email": "alex@yopmail.com", "first_name": "Alex"},
            {"email": "sarah@gmail.com", "first_name": "Sarah"},
        ]
        execute_bulk_import_leads(
            supabase=self.mock_supabase,
            list_id="list-tags-test",
            workspace_id=self.workspace_id,
            leads=leads,
        )
        rpc_call = self.mock_supabase.rpc.call_args
        p_leads = rpc_call[0][1]["p_leads"]

        # Corporate
        self.assertEqual(p_leads[0]["email_classification"], "CORPORATE")
        self.assertFalse(p_leads[0]["is_role_based"])
        self.assertFalse(p_leads[0]["is_disposable"])
        self.assertEqual(p_leads[0]["deliverability_risk"], "SAFE")

        # Disposable
        self.assertEqual(p_leads[1]["email_classification"], "DISPOSABLE")
        self.assertTrue(p_leads[1]["is_disposable"])
        self.assertEqual(p_leads[1]["deliverability_risk"], "HIGH_RISK")

        # Free Webmail
        self.assertEqual(p_leads[2]["email_classification"], "FREE_WEBMAIL")
        self.assertFalse(p_leads[2]["is_disposable"])
        self.assertEqual(p_leads[2]["deliverability_risk"], "LOW_RISK")

    def test_disposable_subdomain_handling(self):
        """
        Layer 1: Subdomains of disposable providers (user@sub.mailinator.com, user@mx1.trashmail.com)
        are resolved to their parent domain and identified as DISPOSABLE.
        """
        subdomain_cases = [
            "user@sub.mailinator.com",
            "prospect@inbound.guerrillamail.com",
            "tester@deep.nested.trashmail.com",
            "lead@temp.tempmail.com",
        ]
        for em in subdomain_cases:
            self.assertTrue(EmailShieldService.is_disposable_email(em), f"Failed for {em}")
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(audit["classification"], EmailClassification.DISPOSABLE.value)
            self.assertFalse(audit["can_safely_send"])

    def test_batch_audit_aggregate_statistics(self):
        """
        Layer 1: audit_email_batch accurately calculates total_emails, safe_count, corporate_count,
        free_webmail_count, role_based_count, disposable_count, spam_trap_count, invalid_count,
        and safe_to_send_ratio_pct.
        """
        batch = [
            "alex@stripe.com",            # Corporate (Safe)
            "elena@linear.app",           # Corporate (Safe)
            "john.doe@gmail.com",         # Free Webmail (Safe)
            "abuse@badcorp.com",          # Spam Trap (Unsafe)
            "fake@mailinator.com",        # Disposable (Unsafe)
            "support@acme.com",           # Role Based (Unsafe by default)
            "invalid-email-format",       # Invalid (Unsafe)
        ]
        # Total = 7, Safe = 3 (Corporate: 2, Free Webmail: 1), Unsafe = 4
        # Safe ratio = 3 / 7 * 100 = 42.86%
        stats = EmailShieldService.audit_email_batch(batch, allow_role_based=False)
        self.assertEqual(stats["total_emails"], 7)
        self.assertEqual(stats["safe_count"], 3)
        self.assertEqual(stats["corporate_count"], 2)
        self.assertEqual(stats["free_webmail_count"], 1)
        self.assertEqual(stats["role_based_count"], 1)
        self.assertEqual(stats["disposable_count"], 1)
        self.assertEqual(stats["spam_trap_count"], 1)
        self.assertEqual(stats["invalid_count"], 1)
        self.assertAlmostEqual(stats["safe_to_send_ratio_pct"], 42.86, places=2)
        self.assertEqual(len(stats["results"]), 7)

    def test_batch_audit_allow_role_based_increases_safe_ratio(self):
        """
        Layer 1: When allow_role_based=True, role-based mailboxes become safe,
        increasing safe_count and safe_to_send_ratio_pct.
        """
        batch = [
            "alex@stripe.com",    # Corporate (Safe)
            "sales@stripe.com",   # Role Based (Safe under allow_role_based=True)
            "abuse@stripe.com",   # Spam Trap (Still Unsafe)
        ]
        stats = EmailShieldService.audit_email_batch(batch, allow_role_based=True)
        self.assertEqual(stats["total_emails"], 3)
        self.assertEqual(stats["safe_count"], 2)
        self.assertEqual(stats["role_based_count"], 1)
        self.assertAlmostEqual(stats["safe_to_send_ratio_pct"], 66.67, places=2)

    def test_batch_audit_clamped_at_max_limit(self):
        """
        Layer 1: Batches exceeding MAX_BATCH_SIZE (10,000) are clamped safely
        to 10,000 without memory or CPU exhaustion.
        """
        oversized_batch = ["alex@stripe.com"] * (MAX_BATCH_SIZE + 50)
        stats = EmailShieldService.audit_email_batch(oversized_batch)
        self.assertEqual(stats["total_emails"], MAX_BATCH_SIZE)
        self.assertEqual(len(stats["results"]), MAX_BATCH_SIZE)
        self.assertTrue(stats.get("batch_clamped"))

    def test_batch_audit_empty_and_defensive_types(self):
        """
        Layer 1: Empty lists or invalid inputs return safe zero-count statistics.
        """
        self.assertEqual(EmailShieldService.audit_email_batch([])["total_emails"], 0)
        self.assertEqual(EmailShieldService.audit_email_batch(None)["total_emails"], 0)
        self.assertEqual(EmailShieldService.audit_email_batch("not_a_list")["total_emails"], 0)

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & SECURITY DEFENSE (ENDPOINTS & ATTACK VECTORS)
    # =========================================================================

    def test_router_audit_email_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/audit-email returns structured audit result
        bound to workspace_id.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/audit-email",
                json={"email": "alex@stripe.com", "allow_role_based": False},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["email"], "alex@stripe.com")
            self.assertEqual(data["classification"], "CORPORATE")
            self.assertTrue(data["can_safely_send"])
            self.assertEqual(data["workspace_id"], self.workspace_id)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_router_audit_batch_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/audit-batch returns aggregate statistics
        and itemized results bound to workspace_id.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/audit-batch",
                json={
                    "emails": [
                        "alex@stripe.com",
                        "abuse@company.com",
                        "info@company.com",
                    ],
                    "allow_role_based": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["total_emails"], 3)
            self.assertEqual(data["safe_count"], 2)  # alex + info (role allowed)
            self.assertEqual(data["spam_trap_count"], 1)
            self.assertEqual(data["workspace_id"], self.workspace_id)
            self.assertEqual(len(data["results"]), 3)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_malformed_email_inputs_handled_safely(self):
        """
        Layer 2: Malformed inputs (None, '', '@missing-user.com', 'user@', 'user@.com', '://', 'foo@@bar.com')
        are handled gracefully returning INVALID without uncaught exceptions or 500 errors.
        """
        malformed_inputs = [
            None,
            "",
            "   ",
            "@missing-user.com",
            "user@",
            "user@.com",
            "user@domain..com",
            "://",
            "foo@@bar.com",
            "plainaddress",
            "user @domain.com",
            "user@domain com",
        ]
        for bad in malformed_inputs:
            audit = EmailShieldService.audit_email_address(bad)
            self.assertFalse(audit["valid"])
            self.assertEqual(audit["classification"], EmailClassification.INVALID.value)
            self.assertFalse(audit["can_safely_send"])
            self.assertEqual(audit["deliverability_risk"], "HIGH_RISK")
            self.assertEqual(audit["rejection_reason"], "INVALID_EMAIL_FORMAT")

    def test_null_byte_and_control_char_injection_stripped(self):
        """
        Layer 2: NUL bytes, CR/LF, and ASCII escape codes injected into email strings
        are stripped cleanly without causing exceptions or breaking downstream parsing.
        """
        injected = "alex\x00@stripe.com"
        audit = EmailShieldService.audit_email_address(injected)
        self.assertEqual(audit["email"], "alex@stripe.com")
        self.assertEqual(audit["classification"], EmailClassification.CORPORATE.value)
        self.assertTrue(audit["can_safely_send"])

        newline_injected = "support\r\n@company.com"
        audit_nl = EmailShieldService.audit_email_address(newline_injected)
        self.assertEqual(audit_nl["email"], "support@company.com")
        self.assertEqual(audit_nl["classification"], EmailClassification.ROLE_BASED.value)

    def test_cross_tenant_idor_audit_endpoints(self):
        """
        Layer 2: Audit endpoints enforce workspace authentication scoping and reflect
        the authenticated tenant's workspace_id, preventing cross-tenant leakage.
        """
        tenant_a = "ws-tenant-alpha"
        tenant_b = "ws-tenant-bravo"

        app.dependency_overrides[get_current_workspace] = lambda: tenant_a
        try:
            client = TestClient(app)
            res_a = client.post(
                "/api/elein/deliverability/audit-email",
                json={"email": "lead@target.com"},
            )
            self.assertEqual(res_a.json()["workspace_id"], tenant_a)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

        app.dependency_overrides[get_current_workspace] = lambda: tenant_b
        try:
            client = TestClient(app)
            res_b = client.post(
                "/api/elein/deliverability/audit-email",
                json={"email": "lead@target.com"},
            )
            self.assertEqual(res_b.json()["workspace_id"], tenant_b)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_overlong_email_buffer_overflow_defense(self):
        """
        Layer 2: Strings exceeding maximum RFC lengths (254 chars total or 64 chars local part)
        are cleanly rejected as INVALID without catastrophic regex backtracking.
        """
        huge_local = "a" * 70 + "@stripe.com"
        audit = EmailShieldService.audit_email_address(huge_local)
        self.assertFalse(audit["valid"])
        self.assertEqual(audit["classification"], EmailClassification.INVALID.value)

        huge_total = "user@" + ("sub." * 60) + "company.com"
        audit_total = EmailShieldService.audit_email_address(huge_total)
        self.assertFalse(audit_total["valid"])
        self.assertEqual(audit_total["classification"], EmailClassification.INVALID.value)

    def test_mailto_protocol_stripping(self):
        """
        Layer 2: 'mailto:' prefix accidentally included by scraping or copy-paste
        is stripped cleanly.
        """
        audit = EmailShieldService.audit_email_address("mailto:alex@stripe.com")
        self.assertEqual(audit["email"], "alex@stripe.com")
        self.assertEqual(audit["classification"], EmailClassification.CORPORATE.value)
        self.assertTrue(audit["can_safely_send"])

        trap_audit = EmailShieldService.audit_email_address("mailto:abuse@target.com")
        self.assertEqual(trap_audit["email"], "abuse@target.com")
        self.assertEqual(trap_audit["classification"], EmailClassification.SPAM_TRAP.value)

    def test_multiple_plus_subaddressing_spam_trap(self):
        """
        Layer 2: Multiple plus segments (e.g. abuse+marketing+promo@company.com)
        are stripped back to the root prefix ('abuse') and flagged as SPAM_TRAP.
        """
        em = "abuse+marketing+promo+2026@acme.com"
        audit = EmailShieldService.audit_email_address(em)
        self.assertEqual(audit["classification"], EmailClassification.SPAM_TRAP.value)
        self.assertTrue(audit["is_spam_trap"])
        self.assertFalse(audit["can_safely_send"])

    def test_subaddressed_role_based_address_detection(self):
        """
        Layer 0 & 2: Subaddressed/plus-tagged role-based mailboxes (e.g. info+marketing@company.com,
        support+urgent@acme.com, billing+invoices@target.com) are normalized to the base role
        prefix, identified as ROLE_BASED, and assigned the correct department category.
        """
        cases = [
            ("info+marketing@company.com", "GENERAL_INQUIRY"),
            ("support+urgent@acme.com", "SUPPORT"),
            ("billing+invoices@target.com", "FINANCE_BILLING"),
            ("legal+contracts@enterprise.org", "LEGAL_COMPLIANCE"),
            ("sales+outbound@saas.io", "SALES"),
        ]
        for email, expected_category in cases:
            is_role, cat = EmailShieldService.is_role_based_email(email)
            self.assertTrue(is_role, f"Failed for {email}")
            self.assertEqual(cat, expected_category, f"Wrong category for {email}")

            audit = EmailShieldService.audit_email_address(email, allow_role_based=False)
            self.assertEqual(audit["classification"], EmailClassification.ROLE_BASED.value)
            self.assertFalse(audit["can_safely_send"])
            self.assertEqual(audit["role_category"], expected_category)

            # When allow_role_based=True, can_safely_send becomes True
            audit_allowed = EmailShieldService.audit_email_address(email, allow_role_based=True)
            self.assertTrue(audit_allowed["can_safely_send"])

    def test_disposable_domain_trailing_dot_and_mailto(self):
        """
        Layer 1 & 2: Disposable emails formatted with trailing FQDN dot (user@mailinator.com.),
        mailto: protocol (mailto:burner@guerrillamail.com), or angle brackets (<temp@10minutemail.com>)
        are all correctly identified as DISPOSABLE and blocked.
        """
        disposable_variations = [
            "user@mailinator.com.",
            "mailto:burner@guerrillamail.com",
            "<temp@10minutemail.com>",
            "\"ephemeral\" <trash@yopmail.com>",
        ]
        for em in disposable_variations:
            audit = EmailShieldService.audit_email_address(em)
            self.assertEqual(
                audit["classification"],
                EmailClassification.DISPOSABLE.value,
                f"Failed classification for {em}",
            )
            self.assertTrue(audit["is_disposable"])
            self.assertFalse(audit["can_safely_send"])
            self.assertEqual(audit["rejection_reason"], "DISPOSABLE_EMAIL_DOMAIN")

    def test_batch_audit_all_invalid_emails_ratio_zero(self):
        """
        Layer 1 & 2: A batch containing exclusively invalid or malformed email inputs
        computes safe_to_send_ratio_pct = 0.0 without divide-by-zero errors.
        """
        invalid_batch = [
            "not-an-email",
            "@missinguser.com",
            "user@",
            "user@domain..com",
            "",
        ]
        stats = EmailShieldService.audit_email_batch(invalid_batch)
        self.assertEqual(stats["total_emails"], 5)
        self.assertEqual(stats["safe_count"], 0)
        self.assertEqual(stats["invalid_count"], 5)
        self.assertEqual(stats["corporate_count"], 0)
        self.assertEqual(stats["free_webmail_count"], 0)
        self.assertEqual(stats["safe_to_send_ratio_pct"], 0.0)

    def test_executor_preserves_spintax_and_tracking_with_shield(self):
        """
        Layer 1: Email node containing spintax template in body and valid corporate email
        passes deliverability check, resolves spintax, records deliverability telemetry,
        and dispatches successfully.
        """
        data = {
            "to_email": "alex@stripe.com",
            "subject": "Platform introduction",
            "body": "{Hi|Hello} Alex, hope you are doing well.",
            "lead_id": "lead-spintax-1",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res.get("email_classification"), "CORPORATE")
        self.assertEqual(res.get("deliverability_risk"), "SAFE")
        self.assertTrue(res.get("spintax_resolved"))
        # Verify outbound message was logged to messages table
        table_calls = [c[1][0] for c in self.mock_supabase.table.mock_calls if c[1]]
        self.assertIn("messages", table_calls)

    def test_executor_double_dot_email_returns_skipped_invalid_format(self):
        """
        Layer 1 & 2: Recipient email with double dot in domain (user@domain..com)
        passes initial simple regex but fails EmailShieldService RFC validation,
        gracefully returning status='skipped' and reason='INVALID_EMAIL_FORMAT'.
        """
        data = {
            "to_email": "user@domain..com",
            "subject": "Inquiry",
            "body": "Hello",
            "lead_id": "lead-bad-rfc",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "INVALID_EMAIL_FORMAT")


if __name__ == "__main__":
    unittest.main()

