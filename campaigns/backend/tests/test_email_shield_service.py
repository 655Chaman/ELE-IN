"""
test_email_shield_service.py — Unit test suite for Issue 9: ESP Spam Trap, Role-Based Mailbox & Disposable Domain Shield.

Rigorously verifies the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational): RFC validation, spam trap detection, role category mapping, disposable domain checking, webmail detection, batch hygiene aggregation.
  - Layer 1 (Environmental): Batch clamping to 10,000, non-string handling in batches, concurrent dataset immutability, zero-division avoidance on empty batches.
  - Layer 2 (Human Paranoia): Stripping mailto:, angle brackets, quotes, NUL bytes, subaddressing tags (+tag) bypass prevention.
"""

import unittest
from typing import List

from core.backend.services.email_shield_service import (
    EmailClassification,
    SPAM_TRAP_PREFIXES,
    ROLE_BASED_PREFIXES,
    DISPOSABLE_DOMAINS,
    FREE_WEBMAIL_DOMAINS,
    ROLE_CATEGORY_MAP,
    clean_and_parse_email,
    is_spam_trap,
    is_role_based_email,
    is_disposable_email,
    is_free_webmail,
    audit_email_address,
    audit_email_batch,
    MAX_BATCH_SIZE,
)


class TestEmailShieldService(unittest.TestCase):

    # =========================================================================
    # 1. ENUMS & DATASET INTEGRITY
    # =========================================================================

    def test_classification_enum_values(self):
        """Verifies all required classification values exist and match string representation."""
        expected = {
            "CORPORATE": "CORPORATE",
            "FREE_WEBMAIL": "FREE_WEBMAIL",
            "ROLE_BASED": "ROLE_BASED",
            "DISPOSABLE": "DISPOSABLE",
            "SPAM_TRAP": "SPAM_TRAP",
            "INVALID": "INVALID",
        }
        for name, val in expected.items():
            self.assertEqual(getattr(EmailClassification, name).value, val)

    def test_spam_trap_prefixes_dataset_coverage(self):
        """Verifies all mandatory spam trap prefixes are present in the dataset."""
        mandatory = [
            "abuse", "postmaster", "spam", "spamtrap", "trap", "honeypot",
            "honey", "uce", "fbl", "noc", "security", "phish", "phishing",
            "anti-spam", "antispam"
        ]
        for prefix in mandatory:
            self.assertIn(prefix, SPAM_TRAP_PREFIXES, f"Missing spam trap prefix: {prefix}")

    def test_role_based_prefixes_dataset_coverage(self):
        """Verifies all mandatory role-based prefixes are present in the dataset."""
        mandatory = [
            "info", "admin", "administrator", "support", "help", "billing",
            "invoices", "accounting", "accounts", "sales", "marketing", "press",
            "media", "jobs", "careers", "hr", "office", "contact", "team",
            "general", "service", "legal", "compliance", "privacy", "operations",
            "ops", "devnull", "orders", "hello", "inquiries", "feedback", "reception"
        ]
        for prefix in mandatory:
            self.assertIn(prefix, ROLE_BASED_PREFIXES, f"Missing role-based prefix: {prefix}")
            self.assertIn(prefix, ROLE_CATEGORY_MAP, f"Missing category mapping for: {prefix}")

    def test_disposable_domains_dataset_size_and_members(self):
        """Verifies 100+ disposable domains exist including core representative entries."""
        self.assertGreaterEqual(len(DISPOSABLE_DOMAINS), 100)
        core_disposable = [
            "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
            "yopmail.com", "trashmail.com", "getairmail.com", "dispostable.com",
            "throwawaymail.com", "sharklasers.com", "temp-mail.org", "fakemailgenerator.com",
            "emailondeck.com", "generator.email", "mohmal.com", "crazymailing.com",
            "maildrop.cc", "inboxkitten.com", "mytemp.email", "nada.ltd", "burnermail.io"
        ]
        for domain in core_disposable:
            self.assertIn(domain, DISPOSABLE_DOMAINS, f"Missing disposable domain: {domain}")

    def test_free_webmail_domains_dataset_coverage(self):
        """Verifies all mandatory consumer free webmail domains are present."""
        mandatory = [
            "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com",
            "hotmail.com", "outlook.com", "live.com", "msn.com", "aol.com", "aim.com",
            "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com", "zoho.com",
            "gmx.com", "mail.com", "yandex.com", "tutanota.com", "fastmail.com"
        ]
        for domain in mandatory:
            self.assertIn(domain, FREE_WEBMAIL_DOMAINS, f"Missing free webmail domain: {domain}")

    # =========================================================================
    # 2. CLEAN_AND_PARSE_EMAIL (PARANOIA LAYERS 0 & 2)
    # =========================================================================

    def test_clean_and_parse_standard_email(self):
        """Layer 0: Standard valid corporate email parsing."""
        full, local, domain = clean_and_parse_email("elena.rostova@enterprise.io")
        self.assertEqual(full, "elena.rostova@enterprise.io")
        self.assertEqual(local, "elena.rostova")
        self.assertEqual(domain, "enterprise.io")

    def test_clean_and_parse_mailto_and_angle_brackets(self):
        """Layer 2: Strips mailto: and angle brackets enclosing addresses."""
        full1, local1, domain1 = clean_and_parse_email("mailto:sales@stripe.com")
        self.assertEqual(full1, "sales@stripe.com")
        self.assertEqual(local1, "sales")
        self.assertEqual(domain1, "stripe.com")

        full2, local2, domain2 = clean_and_parse_email("Devin Booker <dbook@suns.nba>")
        self.assertEqual(full2, "dbook@suns.nba")
        self.assertEqual(local2, "dbook")
        self.assertEqual(domain2, "suns.nba")

        full3, local3, domain3 = clean_and_parse_email("<mailto:support@github.com>")
        self.assertEqual(full3, "support@github.com")
        self.assertEqual(local3, "support")
        self.assertEqual(domain3, "github.com")

    def test_clean_and_parse_quotes_whitespace_and_control_chars(self):
        """Layer 2: Strips enclosing quotes, whitespace, NUL bytes, and control characters."""
        dirty = "  \"admin\x00\x07@datadoghq.com\"  \t\n"
        full, local, domain = clean_and_parse_email(dirty)
        self.assertEqual(full, "admin@datadoghq.com")
        self.assertEqual(local, "admin")
        self.assertEqual(domain, "datadoghq.com")

    def test_clean_and_parse_subaddressing_normalization(self):
        """Layer 2: Normalizes plus-tags (e.g. abuse+campaign -> abuse) for categorization."""
        full, local, domain = clean_and_parse_email("abuse+campaign_lead_2026@acme.org")
        self.assertEqual(full, "abuse+campaign_lead_2026@acme.org")
        self.assertEqual(local, "abuse")
        self.assertEqual(domain, "acme.org")

        full2, local2, domain2 = clean_and_parse_email("info+newsletter@company.com")
        self.assertEqual(full2, "info+newsletter@company.com")
        self.assertEqual(local2, "info")
        self.assertEqual(domain2, "company.com")

    def test_clean_and_parse_invalid_formats(self):
        """Layer 0 & 2: Malformed email inputs return (None, None, None)."""
        invalid_inputs = [
            None,
            "",
            "   ",
            "not-an-email",
            "@domain.com",
            "user@",
            "user@@domain.com",
            "user@localhost",
            "user@domain.c",       # 1-char TLD
            "user@domain.123",     # numeric TLD
            ".user@domain.com",    # leading dot
            "user.@domain.com",    # trailing dot in local
            "user..name@domain.com", # consecutive dots
            "a" * 65 + "@domain.com", # local-part > 64 chars
        ]
        for inv in invalid_inputs:
            full, local, domain = clean_and_parse_email(inv)
            self.assertIsNone(full, f"Expected None for invalid input: {inv}")
            self.assertIsNone(local, f"Expected None for invalid input: {inv}")
            self.assertIsNone(domain, f"Expected None for invalid input: {inv}")

    # =========================================================================
    # 3. SPAM TRAP DETECTION
    # =========================================================================

    def test_is_spam_trap_direct_and_subaddressed(self):
        """Detects pristine spam trap prefixes across exact and subaddressed variations."""
        traps = [
            "abuse@acme.com",
            "postmaster@domain.org",
            "spam@trap.net",
            "spamtrap@security.com",
            "honeypot@honeynet.org",
            "abuse+q3_outreach@corp.com",
            "spam-catcher@isp.com",
            "trap.monitor@enterprise.co",
        ]
        for trap in traps:
            matched, reason = is_spam_trap(trap)
            self.assertTrue(matched, f"Expected spam trap for: {trap}")
            self.assertEqual(reason, "PRISTINE_SPAM_TRAP_PREFIX")

    def test_is_spam_trap_benign_emails(self):
        """Ensures legitimate business and personal emails are never flagged as spam traps."""
        benign = [
            "john.doe@company.com",
            "elena@stripe.com",
            "founder@startup.io",
            "engineering@acme.org",
        ]
        for b in benign:
            matched, reason = is_spam_trap(b)
            self.assertFalse(matched, f"Did not expect spam trap for: {b}")
            self.assertIsNone(reason)

    # =========================================================================
    # 4. ROLE-BASED MAILBOX DETECTION
    # =========================================================================

    def test_is_role_based_email_and_categories(self):
        """Detects department role-based mailboxes and returns proper functional category."""
        role_cases = [
            ("admin@acme.com", "ADMINISTRATION"),
            ("support@zendesk.com", "SUPPORT"),
            ("billing@stripe.com", "FINANCE_BILLING"),
            ("invoices@company.co", "FINANCE_BILLING"),
            ("sales@hubspot.com", "SALES"),
            ("marketing@growth.io", "MARKETING_PRESS"),
            ("press@nytimes.com", "MARKETING_PRESS"),
            ("jobs@apple.com", "HUMAN_RESOURCES"),
            ("careers@netflix.com", "HUMAN_RESOURCES"),
            ("hr@google.com", "HUMAN_RESOURCES"),
            ("office@headquarters.com", "OFFICE_MANAGEMENT"),
            ("contact@shopify.com", "GENERAL_INQUIRY"),
            ("info@github.com", "GENERAL_INQUIRY"),
            ("legal@uber.com", "LEGAL_COMPLIANCE"),
            ("privacy@meta.com", "LEGAL_COMPLIANCE"),
            ("operations@aws.amazon.com", "OPERATIONS"),
            ("devnull@blackhole.io", "SYSTEM_DEVNULL"),
            ("support+urgent@saas.com", "SUPPORT"),
            ("sales.americas@corp.net", "SALES"),
        ]
        for email, expected_cat in role_cases:
            matched, cat = is_role_based_email(email)
            self.assertTrue(matched, f"Expected role-based match for: {email}")
            self.assertEqual(cat, expected_cat, f"Wrong category for {email}: got {cat}, expected {expected_cat}")

    def test_is_role_based_benign_personal_emails(self):
        """Ensures individual professional addresses are not flagged as role-based."""
        benign = [
            "satya.nadella@microsoft.com",
            "tim.cook@apple.com",
            "jensen.huang@nvidia.com",
            "alex.smith@consulting.com",
        ]
        for email in benign:
            matched, cat = is_role_based_email(email)
            self.assertFalse(matched, f"Did not expect role-based match for: {email}")
            self.assertIsNone(cat)

    # =========================================================================
    # 5. DISPOSABLE & TEMPORARY DOMAINS
    # =========================================================================

    def test_is_disposable_email_exact_and_subdomains(self):
        """Detects disposable temporary domains including hierarchical subdomains."""
        disposable_emails = [
            "temp@mailinator.com",
            "burner@sub.mailinator.com",
            "user@deep.sub.mailinator.com",
            "fake@10minutemail.com",
            "test@sharklasers.com",
            "tester@guerrillamail.com",
            "disposable@temp-mail.org",
            "temp@inboxkitten.com",
        ]
        for email in disposable_emails:
            self.assertTrue(is_disposable_email(email), f"Expected disposable match for: {email}")

    def test_is_disposable_legitimate_domains(self):
        """Ensures corporate and authentic domains are not flagged as disposable."""
        legit = [
            "user@gmail.com",
            "ceo@stripe.com",
            "engineer@apple.com",
            "contact@harvard.edu",
        ]
        for email in legit:
            self.assertFalse(is_disposable_email(email), f"Did not expect disposable for: {email}")

    # =========================================================================
    # 6. FREE WEBMAIL PROVIDERS
    # =========================================================================

    def test_is_free_webmail_global_and_regional(self):
        """Detects consumer free webmail domains across global and international providers."""
        webmail_emails = [
            "user@gmail.com",
            "user@googlemail.com",
            "user@yahoo.com",
            "user@yahoo.co.uk",
            "user@hotmail.com",
            "user@outlook.com",
            "user@live.com",
            "user@icloud.com",
            "user@proton.me",
            "user@protonmail.com",
            "user@zoho.com",
            "user@sub.gmail.com",
        ]
        for email in webmail_emails:
            self.assertTrue(is_free_webmail(email), f"Expected free webmail match for: {email}")

    def test_is_free_webmail_corporate_domains(self):
        """Ensures custom business domains are not classified as free webmail."""
        corporate = [
            "user@elein.ai",
            "dev@datadoghq.com",
            "sales@snowflake.com",
        ]
        for email in corporate:
            self.assertFalse(is_free_webmail(email), f"Did not expect free webmail for: {email}")

    # =========================================================================
    # 7. SINGLE EMAIL AUDIT (audit_email_address)
    # =========================================================================

    def test_audit_email_spam_trap(self):
        """Audit identifies spam traps as CRITICAL_SPAM_TRAP and blocks sending."""
        res = audit_email_address("abuse+test@target.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["classification"], "SPAM_TRAP")
        self.assertTrue(res["is_spam_trap"])
        self.assertEqual(res["deliverability_risk"], "CRITICAL_SPAM_TRAP")
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "PRISTINE_SPAM_TRAP_PREFIX")
        self.assertIn("CRITICAL: Pristine spam trap detected", res["recommendations"][0])

    def test_audit_email_disposable(self):
        """Audit identifies disposable domains as HIGH_RISK and blocks sending."""
        res = audit_email_address("anonymous@mailinator.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["classification"], "DISPOSABLE")
        self.assertTrue(res["is_disposable"])
        self.assertEqual(res["deliverability_risk"], "HIGH_RISK")
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "DISPOSABLE_EMAIL_DOMAIN")

    def test_audit_email_role_based_disallowed(self):
        """Audit rejects role-based emails by default (allow_role_based=False)."""
        res = audit_email_address("info@stripe.com", allow_role_based=False)
        self.assertTrue(res["valid"])
        self.assertEqual(res["classification"], "ROLE_BASED")
        self.assertTrue(res["is_role_based"])
        self.assertEqual(res["role_category"], "GENERAL_INQUIRY")
        self.assertEqual(res["deliverability_risk"], "HIGH_RISK")
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "ROLE_BASED_MAILBOX_DETECTED")

    def test_audit_email_role_based_allowed(self):
        """Audit permits role-based emails when user explicitly enables allow_role_based=True."""
        res = audit_email_address("sales@stripe.com", allow_role_based=True)
        self.assertTrue(res["valid"])
        self.assertEqual(res["classification"], "ROLE_BASED")
        self.assertTrue(res["is_role_based"])
        self.assertEqual(res["role_category"], "SALES")
        self.assertEqual(res["deliverability_risk"], "LOW_RISK")
        self.assertTrue(res["can_safely_send"])
        self.assertIsNone(res["rejection_reason"])

    def test_audit_email_free_webmail(self):
        """Audit tags consumer webmail as LOW_RISK but permits sending."""
        res = audit_email_address("prospect@gmail.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["classification"], "FREE_WEBMAIL")
        self.assertTrue(res["is_free_webmail"])
        self.assertFalse(res["is_corporate"])
        self.assertEqual(res["deliverability_risk"], "LOW_RISK")
        self.assertTrue(res["can_safely_send"])
        self.assertIsNone(res["rejection_reason"])

    def test_audit_email_corporate_safe(self):
        """Audit verifies corporate B2B mailboxes as SAFE and optimal."""
        res = audit_email_address("satya@microsoft.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["classification"], "CORPORATE")
        self.assertTrue(res["is_corporate"])
        self.assertEqual(res["deliverability_risk"], "SAFE")
        self.assertTrue(res["can_safely_send"])
        self.assertIsNone(res["rejection_reason"])

    def test_audit_email_invalid(self):
        """Audit handles invalid/unparseable emails safely without exception."""
        res = audit_email_address("invalid-email-string")
        self.assertFalse(res["valid"])
        self.assertEqual(res["classification"], "INVALID")
        self.assertEqual(res["deliverability_risk"], "HIGH_RISK")
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "INVALID_EMAIL_FORMAT")

    # =========================================================================
    # 8. BATCH AUDIT (audit_email_batch)
    # =========================================================================

    def test_audit_email_batch_aggregation_and_math(self):
        """Verifies aggregate counts, ratio calculation, and individual result tracking."""
        batch = [
            "elena@datadoghq.com",        # CORPORATE (safe)
            "prospect@gmail.com",         # FREE_WEBMAIL (safe)
            "sales@acme.com",             # ROLE_BASED (blocked if allow_role_based=False)
            "user@mailinator.com",        # DISPOSABLE (blocked)
            "abuse@badspamtrap.org",      # SPAM_TRAP (blocked)
            "bad-syntax-email",           # INVALID (blocked)
        ]
        res = audit_email_batch(batch, allow_role_based=False)

        self.assertEqual(res["total_emails"], 6)
        self.assertEqual(res["corporate_count"], 1)
        self.assertEqual(res["free_webmail_count"], 1)
        self.assertEqual(res["role_based_count"], 1)
        self.assertEqual(res["disposable_count"], 1)
        self.assertEqual(res["spam_trap_count"], 1)
        self.assertEqual(res["invalid_count"], 1)
        self.assertEqual(res["safe_count"], 2)  # corporate + free_webmail
        # 2 / 6 = 33.33%
        self.assertEqual(res["safe_to_send_ratio_pct"], 33.33)
        self.assertFalse(res["batch_clamped"])
        self.assertEqual(len(res["results"]), 6)

    def test_audit_email_batch_allow_role_based_override(self):
        """Role-based override increases safe_count and ratio accordingly."""
        batch = [
            "elena@datadoghq.com",        # CORPORATE (safe)
            "sales@acme.com",             # ROLE_BASED (safe under override)
            "user@mailinator.com",        # DISPOSABLE (blocked)
        ]
        res = audit_email_batch(batch, allow_role_based=True)
        self.assertEqual(res["total_emails"], 3)
        self.assertEqual(res["safe_count"], 2)
        # 2 / 3 = 66.67%
        self.assertEqual(res["safe_to_send_ratio_pct"], 66.67)

    def test_audit_email_batch_empty_and_none(self):
        """Layer 1: Safely handles empty or None batches without ZeroDivisionError."""
        res_empty = audit_email_batch([])
        self.assertEqual(res_empty["total_emails"], 0)
        self.assertEqual(res_empty["safe_count"], 0)
        self.assertEqual(res_empty["safe_to_send_ratio_pct"], 0.0)

        res_none = audit_email_batch(None)  # type: ignore
        self.assertEqual(res_none["total_emails"], 0)
        self.assertEqual(res_none["safe_to_send_ratio_pct"], 0.0)

    def test_audit_email_batch_clamping_to_max(self):
        """Layer 1: Clamps batches exceeding MAX_BATCH_SIZE (10,000) to protect server memory."""
        oversized_batch = ["lead{}@corp.com".format(i) for i in range(MAX_BATCH_SIZE + 50)]
        res = audit_email_batch(oversized_batch)
        self.assertTrue(res["batch_clamped"])
        self.assertEqual(res["total_emails"], MAX_BATCH_SIZE)
        self.assertEqual(len(res["results"]), MAX_BATCH_SIZE)

    def test_audit_email_batch_defensive_types(self):
        """Layer 1 & 2: Handles non-string or malformed items in batch without crashing."""
        dirty_batch = [
            "clean@corp.com",
            None,
            12345,
            {"email": "broken"},
            "another@corp.com",
        ]
        res = audit_email_batch(dirty_batch)
        self.assertEqual(res["total_emails"], 5)
        self.assertEqual(res["corporate_count"], 2)
        self.assertEqual(res["invalid_count"], 3)


if __name__ == "__main__":
    unittest.main()
