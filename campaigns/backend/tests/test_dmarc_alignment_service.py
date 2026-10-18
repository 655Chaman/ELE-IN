"""
test_dmarc_alignment_service.py — Paranoia Test Automation Suite for Phase 36
(Live DMARC/DKIM/SPF Alignment Auditor, DNS Drift Tripwire & Auto-Quarantine).

Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - Full RFC 7489 parsing of tags: v, p, sp, aspf, adkim, pct, rua, ruf.
    - Strict vs relaxed alignment evaluation for SPF and DKIM.
    - RFC 7489 Section 6.6.3 Organization Domain fallback (subdomain inherits sp).
    - Deliverability risk mapping: SAFE, CRITICAL_REJECT_RISK, HIGH_SPAM_RISK, MODERATE_RISK, HIGH_RISK.
    - DMARCAlignmentService facade with static methods.

  - Layer 1: Environmental Failure Analysis
    - DNS lookup timeouts and NXDOMAIN handled without unhandled exception.
    - Authoritative mock_dns isolation for deterministic testing.
    - Supabase query and update failure resilience in scan_workspace_dns_drift.
    - Safe notification dispatch failure isolation.

  - Layer 2: Human Paranoia & Security Defense
    - SSRF prevention: blocks localhost, 127.0.0.1, internal TLDs.
    - Malformed DMARC syntax: quotes, whitespace around '=', duplicate tags, unknown tags.
    - RFC 7489 Section 6.6.1 enforcement: first tag MUST be v=DMARC1.
    - Clamped pct (0-100) and fallback on malformed integers.
    - Tripwires: SPF_MISSING_DRIFT, MULTIPLE_SPF_RFC7208_COLLISION, SPF_PERMISSIVE_PLUS_ALL,
      DKIM_MISSING_DRIFT, DKIM_REVOKED_KEY, DMARC_REJECT_UNALIGNED, DMARC_QUARANTINE_UNALIGNED.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.backend.services.dmarc_alignment_service import (
    DMARCAlignmentMode,
    DMARCPolicy,
    DMARCAlignmentService,
    parse_dmarc_record,
    evaluate_dmarc_alignment,
    audit_sender_inbox_dns_health,
    scan_workspace_dns_drift,
)


class TestDMARCAlignmentServiceParanoia(unittest.TestCase):

    # ========================================================================
    # Layer 0: RFC 7489 Parser Mechanics
    # ========================================================================

    def test_parse_dmarc_record_standard(self):
        raw = "v=DMARC1; p=reject; sp=quarantine; aspf=s; adkim=r; pct=100; rua=mailto:dmarc@example.com"
        res = parse_dmarc_record(raw)
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], "reject")
        self.assertEqual(res["subdomain_policy"], "quarantine")
        self.assertEqual(res["aspf"], "s")
        self.assertEqual(res["adkim"], "r")
        self.assertEqual(res["pct"], 100)
        self.assertEqual(res["rua"], "mailto:dmarc@example.com")
        self.assertEqual(len(res["errors"]), 0)

    def test_parse_dmarc_record_defaults(self):
        raw = "v=DMARC1; p=none"
        res = parse_dmarc_record(raw)
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], "none")
        self.assertEqual(res["subdomain_policy"], "none")  # Defaults to p
        self.assertEqual(res["aspf"], "r")  # Defaults to relaxed
        self.assertEqual(res["adkim"], "r")  # Defaults to relaxed
        self.assertEqual(res["pct"], 100)  # Defaults to 100%

    def test_parse_dmarc_record_quotes_and_whitespace(self):
        # Paranoia Layer 2: quotes and extra spaces around '='
        raw = '  v=DMARC1 ; p = "reject" ; aspf = \'s\' ; pct = "50" ; unknown_tag = "foo" ; '
        res = parse_dmarc_record(raw)
        self.assertTrue(res["valid"])
        self.assertEqual(res["policy"], "reject")
        self.assertEqual(res["aspf"], "s")
        self.assertEqual(res["pct"], 50)
        self.assertEqual(res["tags"].get("unknown_tag"), "foo")

    def test_parse_dmarc_record_pct_clamping(self):
        # Under 0 clamped to 0
        res1 = parse_dmarc_record("v=DMARC1; p=reject; pct=-20")
        self.assertEqual(res1["pct"], 0)

        # Over 100 clamped to 100
        res2 = parse_dmarc_record("v=DMARC1; p=reject; pct=250")
        self.assertEqual(res2["pct"], 100)

        # Malformed integer defaults to 100 with warning
        res3 = parse_dmarc_record("v=DMARC1; p=reject; pct=invalid")
        self.assertEqual(res3["pct"], 100)
        self.assertTrue(any("pct" in w for w in res3["warnings"]))

    def test_parse_dmarc_record_must_have_v_first(self):
        # RFC 7489 Section 6.6.1: v=DMARC1 must be first tag
        res = parse_dmarc_record("p=reject; v=DMARC1")
        self.assertFalse(res["valid"])
        self.assertEqual(res["policy"], "missing")
        self.assertTrue(any("First tag" in e for e in res["errors"]))

    def test_parse_dmarc_record_missing_p(self):
        res = parse_dmarc_record("v=DMARC1; rua=mailto:dmarc@example.com")
        self.assertFalse(res["valid"])
        self.assertEqual(res["policy"], "missing")
        self.assertTrue(any("Missing required 'p'" in e for e in res["errors"]))

    def test_parse_dmarc_record_invalid_policy(self):
        res = parse_dmarc_record("v=DMARC1; p=invalid_policy")
        self.assertFalse(res["valid"])
        self.assertEqual(res["policy"], "missing")
        self.assertTrue(any("Invalid policy" in e for e in res["errors"]))

    def test_parse_dmarc_record_empty_or_none(self):
        res1 = parse_dmarc_record(None)
        self.assertFalse(res1["valid"])
        self.assertEqual(res1["policy"], "missing")

        res2 = parse_dmarc_record("   ")
        self.assertFalse(res2["valid"])
        self.assertEqual(res2["policy"], "missing")

    # ========================================================================
    # Layer 0 & 1: Alignment Evaluation (Relaxed vs Strict)
    # ========================================================================

    def test_spf_alignment_relaxed_success(self):
        # Relaxed mode: Return-Path is mail.acme.com, From is acme.com -> root match
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=reject; aspf=r"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="mail.acme.com",
            dkim_domain=None,
            mock_dns=mock_dns,
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["spf_aligned"])
        self.assertFalse(res["dkim_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "SAFE")

    def test_spf_alignment_strict_failure_on_subdomain(self):
        # Strict mode: Return-Path mail.acme.com != From acme.com -> fails strict SPF
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=reject; aspf=s"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="mail.acme.com",
            dkim_domain=None,
            mock_dns=mock_dns,
        )
        self.assertFalse(res["spf_aligned"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "CRITICAL_REJECT_RISK")
        self.assertEqual(res["rejection_reason"], "DMARC_REJECT_UNALIGNED")

    def test_spf_alignment_strict_success_on_exact_match(self):
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=reject; aspf=s"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="acme.com",
            dkim_domain=None,
            mock_dns=mock_dns,
        )
        self.assertTrue(res["spf_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "SAFE")

    def test_dkim_alignment_relaxed_success(self):
        # Relaxed mode: dkim d=s1.acme.com, From is acme.com -> root match
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=reject; adkim=r"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="unrelated-esp.com",  # Unaligned SPF
            dkim_domain="s1.acme.com",               # Aligned DKIM
            mock_dns=mock_dns,
        )
        self.assertFalse(res["spf_aligned"])
        self.assertTrue(res["dkim_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "SAFE")

    def test_dkim_alignment_strict_failure(self):
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=quarantine; adkim=s"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain=None,
            dkim_domain="s1.acme.com",
            mock_dns=mock_dns,
        )
        self.assertFalse(res["dkim_aligned"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "HIGH_SPAM_RISK")
        self.assertEqual(res["rejection_reason"], "DMARC_QUARANTINE_UNALIGNED")

    # ========================================================================
    # Layer 0: RFC 7489 Section 6.6.3 Org Domain Fallback & Policy
    # ========================================================================

    def test_subdomain_fallback_inherits_sp(self):
        # From header: outbound.sales.acme.com
        # No DMARC at _dmarc.outbound.sales.acme.com
        # DMARC exists at _dmarc.acme.com with p=reject; sp=quarantine
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=reject; sp=quarantine"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="outbound.sales.acme.com",
            return_path_domain="bounces.other.com",
            dkim_domain="mailgun.org",
            mock_dns=mock_dns,
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["is_org_domain_fallback"])
        self.assertEqual(res["dmarc_record_location"], "_dmarc.acme.com")
        self.assertEqual(res["policy"], "quarantine")  # Uses sp!
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "HIGH_SPAM_RISK")
        self.assertEqual(res["rejection_reason"], "DMARC_QUARANTINE_UNALIGNED")

    def test_subdomain_fallback_defaults_sp_to_p_when_omitted(self):
        mock_dns = {
            "_dmarc.acme.com": "v=DMARC1; p=reject"
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="sub.acme.com",
            return_path_domain="other.com",
            dkim_domain=None,
            mock_dns=mock_dns,
        )
        self.assertEqual(res["policy"], "reject")  # sp defaults to p
        self.assertEqual(res["rejection_reason"], "DMARC_REJECT_UNALIGNED")

    def test_direct_subdomain_record_takes_precedence_over_org_domain(self):
        # DMARC at both _dmarc.sub.acme.com and _dmarc.acme.com
        mock_dns = {
            "_dmarc.sub.acme.com": "v=DMARC1; p=none",
            "_dmarc.acme.com": "v=DMARC1; p=reject; sp=reject",
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="sub.acme.com",
            return_path_domain="other.com",
            dkim_domain=None,
            mock_dns=mock_dns,
        )
        self.assertFalse(res["is_org_domain_fallback"])
        self.assertEqual(res["dmarc_record_location"], "_dmarc.sub.acme.com")
        self.assertEqual(res["policy"], "none")
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "MODERATE_RISK")

    def test_missing_dmarc_record_deliverability_risk(self):
        mock_dns = {}
        res = evaluate_dmarc_alignment(
            from_header_domain="unknown-domain.io",
            return_path_domain="unknown-domain.io",
            dkim_domain="unknown-domain.io",
            mock_dns=mock_dns,
        )
        self.assertEqual(res["policy"], "missing")
        self.assertEqual(res["deliverability_risk"], "HIGH_RISK")
        self.assertTrue(res["can_safely_send"])  # Legacy fallback allows sending with warning
        self.assertTrue(len(res["remediation_records"]) > 0)

    # ========================================================================
    # Layer 2: Mailbox Health Audit & Tripwires
    # ========================================================================

    def test_audit_inbox_healthy(self):
        mock_dns = {
            "acme.com": "v=spf1 include:_spf.google.com ~all",
            "elein._domainkey.acme.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.acme.com": "v=DMARC1; p=reject; rua=mailto:dmarc@acme.com",
        }
        inbox = {
            "id": "inb-1",
            "email": "sarah@acme.com",
            "domain": "acme.com",
            "return_path_domain": "acme.com",
            "dkim_domain": "acme.com",
            "dkim_selector": "elein",
        }
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertTrue(audit["healthy"])
        self.assertFalse(audit["should_quarantine"])
        self.assertIsNone(audit["quarantine_reason"])
        self.assertEqual(len(audit["tripwires_tripped"]), 0)
        self.assertEqual(audit["deliverability_score"], 100)

    def test_tripwire_spf_missing_drift(self):
        mock_dns = {
            # No SPF on acme.com!
            "elein._domainkey.acme.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.acme.com": "v=DMARC1; p=none",
        }
        inbox = {"id": "inb-2", "email": "alex@acme.com"}
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("SPF_MISSING_DRIFT", audit["tripwires_tripped"])
        self.assertEqual(audit["quarantine_reason"], "SPF_MISSING_DRIFT")

    def test_tripwire_multiple_spf_rfc7208_collision(self):
        mock_dns = {
            "acme.com": [
                "v=spf1 include:sendgrid.net ~all",
                "v=spf1 include:_spf.google.com ~all",
            ],
            "elein._domainkey.acme.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        inbox = {"id": "inb-3", "email": "alex@acme.com"}
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("MULTIPLE_SPF_RFC7208_COLLISION", audit["tripwires_tripped"])

    def test_tripwire_spf_permissive_plus_all(self):
        mock_dns = {
            "acme.com": "v=spf1 include:_spf.google.com +all",
            "elein._domainkey.acme.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        inbox = {"id": "inb-4", "email": "alex@acme.com"}
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("SPF_PERMISSIVE_PLUS_ALL", audit["tripwires_tripped"])

    def test_tripwire_dkim_missing_drift(self):
        mock_dns = {
            "acme.com": "v=spf1 include:_spf.google.com ~all",
            # Missing DKIM at elein._domainkey.acme.com
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        inbox = {"id": "inb-5", "email": "alex@acme.com"}
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("DKIM_MISSING_DRIFT", audit["tripwires_tripped"])

    def test_tripwire_dkim_revoked_key(self):
        mock_dns = {
            "acme.com": "v=spf1 include:_spf.google.com ~all",
            # p= empty means key revoked per RFC 6376
            "elein._domainkey.acme.com": "v=DKIM1; k=rsa; p=",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        inbox = {"id": "inb-6", "email": "alex@acme.com"}
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("DKIM_REVOKED_KEY", audit["tripwires_tripped"])

    def test_tripwire_dmarc_reject_unaligned(self):
        mock_dns = {
            "acme.com": "v=spf1 include:_spf.google.com ~all",
            "elein._domainkey.acme.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        # Inbox configured with completely unaligned Return-Path and DKIM
        inbox = {
            "id": "inb-7",
            "email": "alex@acme.com",
            "return_path_domain": "sendgrid.net",
            "dkim_domain": "sendgrid.net",
        }
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("DMARC_REJECT_UNALIGNED", audit["tripwires_tripped"])

    # ========================================================================
    # Layer 0 & 1: Workspace Scanner & Auto-Quarantine Pipeline
    # ========================================================================

    def test_scan_workspace_dns_drift_auto_quarantine(self):
        mock_dns = {
            "good.com": "v=spf1 include:_spf.google.com ~all",
            "elein._domainkey.good.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.good.com": "v=DMARC1; p=reject",
            # Bad domain: missing SPF
            "elein._domainkey.bad.com": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "_dmarc.bad.com": "v=DMARC1; p=reject",
        }

        mock_inboxes = [
            {"id": "inb-good", "email": "a@good.com", "status": "ACTIVE"},
            {"id": "inb-bad", "email": "b@bad.com", "status": "ACTIVE"},
        ]

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq1
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.execute.return_value = MagicMock(data=[])

        scan_res = scan_workspace_dns_drift(
            supabase=mock_supabase,
            workspace_id="ws-test-123",
            auto_quarantine=True,
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )

        self.assertEqual(scan_res["total_inboxes"], 2)
        self.assertEqual(scan_res["healthy_count"], 1)
        self.assertEqual(scan_res["quarantined_count"], 1)
        self.assertEqual(scan_res["drift_detected_count"], 1)

        # Verify Supabase update was called for the drifted inbox
        mock_table.update.assert_called()
        update_args = mock_table.update.call_args[0][0]
        self.assertEqual(update_args["status"], "QUARANTINED")
        self.assertEqual(update_args["quarantine_reason"], "SPF_MISSING_DRIFT")
        self.assertIn("quarantined_until", update_args)

    def test_scan_workspace_dns_drift_no_auto_quarantine(self):
        mock_dns = {
            # Bad domain
            "_dmarc.bad.com": "v=DMARC1; p=reject",
        }
        mock_inboxes = [
            {"id": "inb-bad", "email": "b@bad.com", "status": "ACTIVE"}
        ]
        mock_supabase = MagicMock()

        scan_res = scan_workspace_dns_drift(
            supabase=mock_supabase,
            workspace_id="ws-test-456",
            auto_quarantine=False,
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )

        self.assertEqual(scan_res["total_inboxes"], 1)
        self.assertEqual(scan_res["drift_detected_count"], 1)
        self.assertEqual(scan_res["quarantined_count"], 0)
        # Should not update Supabase
        mock_supabase.table.assert_not_called()

    # ========================================================================
    # Facade Class
    # ========================================================================

    def test_facade_class_methods(self):
        self.assertEqual(DMARCAlignmentService.DMARCAlignmentMode.STRICT, "s")
        self.assertEqual(DMARCAlignmentService.DMARCPolicy.REJECT, "reject")

        # parse_dmarc_record
        p = DMARCAlignmentService.parse_dmarc_record("v=DMARC1; p=reject")
        self.assertEqual(p["policy"], "reject")

        # evaluate_dmarc_alignment
        eval_res = DMARCAlignmentService.evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="acme.com",
            mock_dns={"_dmarc.acme.com": "v=DMARC1; p=none"},
        )
        self.assertTrue(eval_res["valid"])

        # audit_sender_inbox_dns_health
        audit_res = DMARCAlignmentService.audit_sender_inbox_dns_health(
            {"email": "test@acme.com"},
            mock_dns={},
        )
        self.assertIn("healthy", audit_res)

    # ========================================================================
    # Layer 1 & 2: Error Resilience, SSRF & Security Defense
    # ========================================================================

    def test_ssrf_domain_rejection(self):
        # Localhost, private IPs, AWS metadata endpoints must be rejected
        for bad_host in ["localhost", "127.0.0.1", "169.254.169.254", "server.local", "::1"]:
            res = evaluate_dmarc_alignment(
                from_header_domain=bad_host,
                mock_dns={},
            )
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_safely_send"])
            self.assertEqual(res["rejection_reason"], "INVALID_FROM_HEADER_DOMAIN")

    def test_inbox_with_invalid_domain_audit(self):
        audit = audit_sender_inbox_dns_health(
            {"id": "bad-inb", "email": "admin@localhost"},
            mock_dns={},
        )
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertEqual(audit["quarantine_reason"], "INVALID_OR_UNSAFE_DOMAIN")

    def test_supabase_db_outage_resilience_in_scan(self):
        # Database raises exception during update; scan must not crash
        mock_dns = {"_dmarc.bad.com": "v=DMARC1; p=reject"}
        mock_inboxes = [{"id": "inb-fail", "email": "a@bad.com", "status": "ACTIVE"}]

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("Supabase connection timeout / 502")

        # Scan should complete without raising
        scan_res = scan_workspace_dns_drift(
            supabase=mock_supabase,
            workspace_id="ws-outage",
            auto_quarantine=True,
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )
        self.assertEqual(scan_res["total_inboxes"], 1)
        self.assertEqual(scan_res["quarantined_count"], 1)

    def test_notification_failure_resilience_in_scan(self):
        mock_dns = {"_dmarc.bad.com": "v=DMARC1; p=reject"}
        mock_inboxes = [{"id": "inb-notif", "email": "a@bad.com", "status": "ACTIVE"}]

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq1 = MagicMock()
        mock_eq2 = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq1
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.execute.return_value = MagicMock(data=[])

        with patch("core.backend.services.dmarc_alignment_service.dispatch_notification", side_effect=Exception("Notification service failure")):
            scan_res = scan_workspace_dns_drift(
                supabase=mock_supabase,
                workspace_id="ws-notif",
                auto_quarantine=True,
                mock_inboxes=mock_inboxes,
                mock_dns=mock_dns,
            )
            self.assertEqual(scan_res["quarantined_count"], 1)

    def test_scan_workspace_dns_drift_empty_workspace_id(self):
        with self.assertRaises(ValueError):
            scan_workspace_dns_drift(supabase=None, workspace_id="")


if __name__ == "__main__":
    unittest.main()

