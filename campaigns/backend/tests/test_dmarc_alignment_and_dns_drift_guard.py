"""
test_dmarc_alignment_and_dns_drift_guard.py — Paranoia Automated Test Suite for Phase 36
(Live DMARC/DKIM/SPF Alignment Auditor, DNS Drift Tripwire & Auto-Quarantine).

Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - Full RFC 7489 DMARC record parsing (v, p, sp, aspf, adkim, pct, rua, ruf, fo, ri).
    - Authentic SPF & DKIM Alignment evaluation in Relaxed ('r') vs Strict ('s') modes.
    - RFC 7489 Section 6.6.3 Organization Domain fallback (subdomain -> root domain DMARC record).
    - SPF and DKIM standalone alignment permutations (either satisfies DMARC).
    - Monitoring mode (p=none) deliverability clearance vs enforcement (p=quarantine / p=reject).
    - Subdomain policy override tag (sp=) inheritance mechanics.
    - Missing DMARC record legacy fallback handling.

  - Layer 1: Environmental Failure Analysis
    - Executor pre-flight DMARC abort when mailbox domain fails alignment under p=reject.
    - Executor pre-flight DMARC abort when mailbox domain fails alignment under p=quarantine.
    - Executor allows send when SPF or DKIM is aligned, enriching telemetry with dmarc_aligned=True.
    - Executor permits outreach under monitoring mode (p=none) with unaligned telemetry.
    - Mailbox DNS drift tripwire: dropped SPF record triggers SPF_MISSING_DRIFT.
    - Mailbox DNS drift tripwire: RFC 7208 violation triggers MULTIPLE_SPF_RFC7208_COLLISION.
    - Mailbox DNS drift tripwire: permissive +all triggers SPF_PERMISSIVE_PLUS_ALL.
    - Mailbox DNS drift tripwire: revoked/empty DKIM public key triggers DKIM_REVOKED_KEY.
    - Mailbox DNS drift tripwire: missing DKIM selector record triggers DKIM_MISSING_DRIFT.
    - Workspace DNS drift scan automatically quarantines broken inboxes (status=QUARANTINED, quarantined_until).
    - Workspace DNS drift dry-run mode (auto_quarantine=False) inspects without mutating database.
    - Accurate copy-paste DNS remediation records generated for rapid resolution.
    - Supabase database network/outage resilience: failures fail safe without unhandled exceptions.
    - Notification dispatch failure isolation so alert errors never interrupt scan pipelines.
    - DNS query timeout and resolution failure defense with safe fallback.

  - Layer 2: Human Paranoia & Security Defense
    - Router endpoint POST /api/elein/deliverability/dmarc-alignment-audit returns structured audit.
    - Router endpoint POST /api/elein/deliverability/check-dns-drift executes workspace scan.
    - Cross-tenant IDOR defense: scanning workspace A never inspects or mutates workspace B inboxes.
    - Malformed domain inputs (None, "", "://", "localhost", "127.0.0.1", double dots).
    - Subaddressing, display names, and angle brackets stripped cleanly (<sales+campaign@acme.com>).
    - Corrupted and invalid DMARC syntax defense (missing v=DMARC1, non-numeric pct, invalid policy p=drop).
    - Percentage pct tag clamped safely between 0 and 100.
    - SSRF prevention: private IP literals and internal TLDs (.local, .internal, .arpa) rejected.
    - Case-insensitivity and arbitrary whitespace in DMARC tag tokens parsed reliably.
    - Duplicate DMARC tags handled with warnings without crashing.
    - Router validation: empty domain input returns HTTP 400.
    - Facade class DMARCAlignmentService methods parity with core functions.
"""

import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from core.backend.services.dmarc_alignment_service import (
    DMARCAlignmentMode,
    DMARCPolicy,
    DMARCAlignmentService,
    parse_dmarc_record,
    evaluate_dmarc_alignment,
    audit_sender_inbox_dns_health,
    scan_workspace_dns_drift,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import (
    DMARCAlignmentAuditRequest,
    DNSDriftScanRequest,
    api_dmarc_alignment_audit,
    api_check_dns_drift,
)


class TestDMARCAlignmentAndDNSDriftGuard(unittest.TestCase):
    """
    Comprehensive 3-Layer Paranoia Test Automation Suite for Phase 36:
    Live DMARC/DKIM/SPF Alignment Auditor, DNS Drift Tripwire & Auto-Quarantine.
    """

    def setUp(self):
        self.workspace_id = "ws-dmarc-paranoia-test"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER (CORE MECHANICS)
    # =========================================================================

    def test_relaxed_spf_alignment_subdomain_matches_root(self):
        """
        Layer 0: From: sales@acme.com, Return-Path: bounces@mail.acme.com with aspf=r (relaxed)
        passes SPF alignment because both share the effective root domain acme.com.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="mail.acme.com",
            dkim_domain=None,
            dmarc_record="v=DMARC1; p=reject; aspf=r",
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["spf_aligned"])
        self.assertFalse(res["dkim_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "SAFE")
        self.assertIsNone(res["rejection_reason"])

    def test_strict_spf_alignment_subdomain_rejected(self):
        """
        Layer 0: From: sales@acme.com, Return-Path: bounces@mail.acme.com with aspf=s (strict)
        fails SPF alignment because mail.acme.com does not exactly equal acme.com.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="mail.acme.com",
            dkim_domain=None,
            dmarc_record="v=DMARC1; p=reject; aspf=s",
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["spf_aligned"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "DMARC_REJECT_UNALIGNED")
        self.assertEqual(res["deliverability_risk"], "CRITICAL_REJECT_RISK")

    def test_relaxed_dkim_alignment_subdomain_matches_root(self):
        """
        Layer 0: From: sales@acme.com, d=outbound.acme.com with adkim=r (relaxed)
        passes DKIM alignment because both share the effective root domain acme.com.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain=None,
            dkim_domain="outbound.acme.com",
            dmarc_record="v=DMARC1; p=reject; adkim=r",
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["dkim_aligned"])
        self.assertFalse(res["spf_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["deliverability_risk"], "SAFE")

    def test_strict_dkim_alignment_subdomain_rejected(self):
        """
        Layer 0: From: sales@acme.com, d=outbound.acme.com with adkim=s (strict)
        fails DKIM alignment because outbound.acme.com does not exactly equal acme.com.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain=None,
            dkim_domain="outbound.acme.com",
            dmarc_record="v=DMARC1; p=reject; adkim=s",
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["dkim_aligned"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "DMARC_REJECT_UNALIGNED")

    def test_dmarc_aligned_if_either_spf_or_dkim_aligns(self):
        """
        Layer 0: RFC 7489 specifies DMARC passes if EITHER SPF OR DKIM achieves identifier alignment.
        """
        # Case A: SPF unaligned, DKIM aligned
        res_a = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="bounces.sendgrid.net",  # Unaligned third-party
            dkim_domain="acme.com",                     # Aligned
            dmarc_record="v=DMARC1; p=reject; aspf=r; adkim=r",
        )
        self.assertFalse(res_a["spf_aligned"])
        self.assertTrue(res_a["dkim_aligned"])
        self.assertTrue(res_a["dmarc_aligned"])
        self.assertTrue(res_a["can_safely_send"])
        self.assertEqual(res_a["deliverability_risk"], "SAFE")

        # Case B: DKIM unaligned, SPF aligned
        res_b = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="mail.acme.com",         # Aligned relaxed
            dkim_domain="shared.esp.net",              # Unaligned third-party
            dmarc_record="v=DMARC1; p=reject; aspf=r; adkim=r",
        )
        self.assertTrue(res_b["spf_aligned"])
        self.assertFalse(res_b["dkim_aligned"])
        self.assertTrue(res_b["dmarc_aligned"])
        self.assertTrue(res_b["can_safely_send"])
        self.assertEqual(res_b["deliverability_risk"], "SAFE")

    def test_dmarc_parse_tags_pct_sp_rua(self):
        """
        Layer 0: Full tag parsing for RFC 7489 attributes (v, p, sp, pct, aspf, adkim, rua, ruf).
        """
        raw = "v=DMARC1; p=reject; sp=quarantine; pct=100; aspf=s; adkim=r; rua=mailto:dmarc@acme.com; ruf=mailto:forensics@acme.com"
        parsed = parse_dmarc_record(raw)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["policy"], "reject")
        self.assertEqual(parsed["subdomain_policy"], "quarantine")
        self.assertEqual(parsed["pct"], 100)
        self.assertEqual(parsed["aspf"], "s")
        self.assertEqual(parsed["adkim"], "r")
        self.assertEqual(parsed["rua"], "mailto:dmarc@acme.com")
        self.assertEqual(parsed["ruf"], "mailto:forensics@acme.com")

    def test_dmarc_fallback_to_root_domain_for_subdomains(self):
        """
        Layer 0: Subdomain mail.acme.com without its own DMARC record falls back to the
        Organization Domain _dmarc.acme.com per RFC 7489 Section 6.6.3.
        """
        mock_dns = {
            "_dmarc.mail.acme.com": [],  # No record on subdomain
            "_dmarc.acme.com": ["v=DMARC1; p=reject; sp=quarantine; aspf=r; adkim=r"],
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="mail.acme.com",
            return_path_domain="mail.acme.com",
            dkim_domain="mail.acme.com",
            mock_dns=mock_dns,
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["is_org_domain_fallback"])
        self.assertEqual(res["dmarc_record_location"], "_dmarc.acme.com")
        # Under org domain fallback, subdomain policy 'sp' governs
        self.assertEqual(res["policy"], "quarantine")
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])

    def test_dmarc_none_policy_monitoring_mode(self):
        """
        Layer 0: Unaligned email with p=none emits deliverability_risk='MODERATE_RISK'
        and can_safely_send=True because p=none is an observation/monitoring policy.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="unaligned.com",
            dkim_domain="unaligned.com",
            dmarc_record="v=DMARC1; p=none",
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertEqual(res["policy"], "none")
        self.assertEqual(res["deliverability_risk"], "MODERATE_RISK")
        self.assertTrue(res["can_safely_send"])
        self.assertIsNone(res["rejection_reason"])
        self.assertTrue(any("monitoring mode" in w.lower() for w in res["warnings"]))

    def test_dmarc_reject_policy_blocks_unaligned(self):
        """
        Layer 0: Unaligned email under p=reject emits can_safely_send=False and
        rejection_reason='DMARC_REJECT_UNALIGNED' to prevent ESP hard bounces.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="unaligned.com",
            dkim_domain="unaligned.com",
            dmarc_record="v=DMARC1; p=reject",
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "DMARC_REJECT_UNALIGNED")
        self.assertEqual(res["deliverability_risk"], "CRITICAL_REJECT_RISK")

    def test_dmarc_quarantine_policy_blocks_unaligned(self):
        """
        Layer 0: Unaligned email under p=quarantine emits can_safely_send=False and
        rejection_reason='DMARC_QUARANTINE_UNALIGNED'.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="unaligned.com",
            dkim_domain="unaligned.com",
            dmarc_record="v=DMARC1; p=quarantine",
        )
        self.assertTrue(res["valid"])
        self.assertFalse(res["dmarc_aligned"])
        self.assertFalse(res["can_safely_send"])
        self.assertEqual(res["rejection_reason"], "DMARC_QUARANTINE_UNALIGNED")
        self.assertEqual(res["deliverability_risk"], "HIGH_SPAM_RISK")

    def test_strict_spf_alignment_exact_match_passes(self):
        """
        Layer 0: Strict SPF alignment passes when Return-Path exactly matches From domain.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            return_path_domain="acme.com",
            dmarc_record="v=DMARC1; p=reject; aspf=s",
        )
        self.assertTrue(res["spf_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])

    def test_strict_dkim_alignment_exact_match_passes(self):
        """
        Layer 0: Strict DKIM alignment passes when d= exactly matches From domain.
        """
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            dkim_domain="acme.com",
            dmarc_record="v=DMARC1; p=reject; adkim=s",
        )
        self.assertTrue(res["dkim_aligned"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])

    def test_dmarc_sp_tag_overrides_subdomain_policy(self):
        """
        Layer 0: When root has p=reject and sp=none, subdomains evaluate under sp=none.
        """
        mock_dns = {
            "_dmarc.sales.acme.com": [],
            "_dmarc.acme.com": ["v=DMARC1; p=reject; sp=none"],
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="sales.acme.com",
            return_path_domain="other.com",
            dkim_domain="other.com",
            mock_dns=mock_dns,
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["is_org_domain_fallback"])
        self.assertEqual(res["policy"], "none")
        self.assertTrue(res["can_safely_send"])

    def test_missing_dmarc_record_returns_policy_missing(self):
        """
        Layer 0: If neither subdomain nor root domain has a DMARC record,
        returns policy='missing', valid=False, and deliverability_risk='HIGH_RISK'.
        """
        mock_dns = {
            "_dmarc.acme.com": [],
        }
        res = evaluate_dmarc_alignment(
            from_header_domain="acme.com",
            mock_dns=mock_dns,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["policy"], "missing")
        self.assertEqual(res["deliverability_risk"], "HIGH_RISK")
        self.assertTrue(res["can_safely_send"])  # Legacy fallback allows send with warning

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS (INTEGRATION & DRIFT TRIPWIRES)
    # =========================================================================

    def test_executor_aborts_send_when_dmarc_reject_unaligned(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email aborts outreach with
        reason='dmarc_alignment_failure' when mailbox fails alignment under p=reject.
        """
        data = {
            "to_email": "prospect@targetcorp.com",
            "subject": "Platform introduction",
            "body": "Hi there, wanted to connect.",
            "lead_id": "lead-dmarc-1",
            "selected_inbox": {
                "id": "inb-reject-1",
                "email": "sales@unaligned-corp.com",
                "sender_domain": "unaligned-corp.com",
                "return_path_domain": "external-esp.com",
                "dkim_domain": "external-esp.com",
                "spf_record": "v=spf1 include:_spf.elein.ai ~all",
                "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
                "dmarc_record": "v=DMARC1; p=reject; aspf=s; adkim=s",
            },
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "dmarc_alignment_failure")
        self.assertEqual(res["branch"], Branch.FAILED.value)
        self.assertIn("fails DMARC identifier alignment", res["error"])
        # Ensure outbound message was not persisted
        self.mock_supabase.table.assert_not_called()

    def test_executor_aborts_send_when_dmarc_quarantine_unaligned(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email aborts outreach with
        reason='dmarc_alignment_failure' when mailbox fails alignment under p=quarantine.
        """
        data = {
            "to_email": "prospect@targetcorp.com",
            "subject": "Platform introduction",
            "body": "Hi there.",
            "lead_id": "lead-dmarc-2",
            "selected_inbox": {
                "id": "inb-quarantine-1",
                "email": "outreach@quarantine-corp.com",
                "sender_domain": "quarantine-corp.com",
                "return_path_domain": "thirdparty.org",
                "dkim_domain": "thirdparty.org",
                "spf_record": "v=spf1 include:_spf.elein.ai ~all",
                "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
                "dmarc_record": "v=DMARC1; p=quarantine",
            },
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "dmarc_alignment_failure")
        self.assertEqual(res["branch"], Branch.FAILED.value)

    def test_executor_allows_send_when_dmarc_aligned(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email permits send when DKIM/SPF aligns,
        enriching outcome telemetry with dmarc_aligned=True, dmarc_policy, and dmarc_score.
        """
        data = {
            "to_email": "prospect@targetcorp.com",
            "subject": "Introductory note",
            "body": "Hi Alex, hope you are well.",
            "lead_id": "lead-dmarc-3",
            "selected_inbox": {
                "id": "inb-aligned-1",
                "email": "alex@stripe.com",
                "sender_domain": "stripe.com",
                "return_path_domain": "stripe.com",
                "dkim_domain": "stripe.com",
                "spf_record": "v=spf1 include:_spf.elein.ai ~all",
                "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
                "dmarc_record": "v=DMARC1; p=reject; aspf=r; adkim=r",
            },
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertTrue(res.get("dmarc_aligned"))
        self.assertEqual(res.get("dmarc_policy"), "reject")
        self.assertGreaterEqual(res.get("dmarc_score", 0), 80)

    def test_executor_allows_send_under_none_policy_monitoring_mode(self):
        """
        Layer 1: Unaligned sender under p=none monitoring mode is allowed through
        with telemetry reflecting dmarc_aligned=False and dmarc_policy='none'.
        """
        data = {
            "to_email": "prospect@targetcorp.com",
            "subject": "Platform demo",
            "body": "Hello there.",
            "lead_id": "lead-dmarc-4",
            "selected_inbox": {
                "id": "inb-none-1",
                "email": "alex@testing-monitoring.com",
                "sender_domain": "testing-monitoring.com",
                "return_path_domain": "other.com",
                "dkim_domain": "other.com",
                "spf_record": "v=spf1 include:_spf.elein.ai ~all",
                "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
                "dmarc_record": "v=DMARC1; p=none",
            },
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertFalse(res.get("dmarc_aligned"))
        self.assertEqual(res.get("dmarc_policy"), "none")

    def test_dns_drift_missing_spf_triggers_tripwire(self):
        """
        Layer 1: Mailbox with dropped SPF record is flagged as SPF_MISSING_DRIFT,
        should_quarantine=True, and healthy=False.
        """
        inbox = {
            "id": "inb-drift-spf",
            "email": "sales@acme.com",
            "domain": "acme.com",
            "spf_record": None,  # Dropped record
        }
        mock_dns = {
            "acme.com": [],  # No SPF record found
            "elein._domainkey.acme.com": ["v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ..."],
            "_dmarc.acme.com": ["v=DMARC1; p=reject"],
        }
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("SPF_MISSING_DRIFT", audit["tripwires_tripped"])
        self.assertEqual(audit["quarantine_reason"], "SPF_MISSING_DRIFT")

    def test_dns_drift_multiple_spf_rfc7208_collision(self):
        """
        Layer 1: Domain publishing more than 1 SPF record violates RFC 7208 Section 3.2,
        triggering MULTIPLE_SPF_RFC7208_COLLISION and should_quarantine=True.
        """
        inbox = {
            "id": "inb-drift-multispf",
            "email": "sales@acme.com",
            "domain": "acme.com",
        }
        mock_dns = {
            "acme.com": [
                "v=spf1 include:_spf.google.com ~all",
                "v=spf1 include:sendgrid.net ~all",  # RFC 7208 collision!
            ],
            "elein._domainkey.acme.com": ["v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ..."],
            "_dmarc.acme.com": ["v=DMARC1; p=reject"],
        }
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("MULTIPLE_SPF_RFC7208_COLLISION", audit["tripwires_tripped"])

    def test_dns_drift_spf_all_pass_vulnerability(self):
        """
        Layer 1: Permissive '+all' directive allows any IP to spoof domain,
        tripping SPF_PERMISSIVE_PLUS_ALL tripwire.
        """
        inbox = {
            "id": "inb-drift-plusall",
            "email": "sales@acme.com",
            "domain": "acme.com",
            "spf_record": "v=spf1 +all",
            "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ...",
            "dmarc_record": "v=DMARC1; p=none",
        }
        audit = audit_sender_inbox_dns_health(inbox)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("SPF_PERMISSIVE_PLUS_ALL", audit["tripwires_tripped"])

    def test_dns_drift_revoked_dkim_key(self):
        """
        Layer 1: DKIM record with empty or missing 'p=' attribute indicates a revoked key
        per RFC 6376, tripping DKIM_REVOKED_KEY.
        """
        inbox = {
            "id": "inb-drift-revoked",
            "email": "sales@acme.com",
            "domain": "acme.com",
            "spf_record": "v=spf1 include:_spf.elein.ai ~all",
            "dkim_record": "v=DKIM1; k=rsa; p=",  # Revoked key!
            "dmarc_record": "v=DMARC1; p=reject",
        }
        audit = audit_sender_inbox_dns_health(inbox)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("DKIM_REVOKED_KEY", audit["tripwires_tripped"])

    def test_dns_drift_missing_dkim_record(self):
        """
        Layer 1: Mailbox missing DKIM record entirely triggers DKIM_MISSING_DRIFT.
        """
        inbox = {
            "id": "inb-drift-nodkim",
            "email": "sales@acme.com",
            "domain": "acme.com",
        }
        mock_dns = {
            "acme.com": ["v=spf1 include:_spf.elein.ai ~all"],
            "elein._domainkey.acme.com": [],  # Missing DKIM
            "_dmarc.acme.com": ["v=DMARC1; p=none"],
        }
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        self.assertFalse(audit["healthy"])
        self.assertTrue(audit["should_quarantine"])
        self.assertIn("DKIM_MISSING_DRIFT", audit["tripwires_tripped"])

    def test_scan_workspace_dns_drift_auto_quarantines_broken_inboxes(self):
        """
        Layer 1: scan_workspace_dns_drift detects drift, updates Supabase with
        status='QUARANTINED', and populates quarantined_until.
        """
        mock_inboxes = [
            {
                "id": "inb-good",
                "email": "good@acme.com",
                "status": "ACTIVE",
                "spf_record": "v=spf1 include:_spf.elein.ai ~all",
                "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ...",
                "dmarc_record": "v=DMARC1; p=reject; aspf=r; adkim=r",
            },
            {
                "id": "inb-broken",
                "email": "broken@acme.com",
                "status": "ACTIVE",
                "spf_record": None,  # Will trip SPF_MISSING_DRIFT
            },
        ]
        mock_dns = {
            "acme.com": [],  # For inb-broken
            "elein._domainkey.acme.com": [],
            "_dmarc.acme.com": [],
        }

        # Mock Supabase table update chain
        table_mock = MagicMock()
        self.mock_supabase.table.return_value = table_mock

        res = scan_workspace_dns_drift(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            auto_quarantine=True,
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )

        self.assertEqual(res["total_inboxes"], 2)
        self.assertEqual(res["healthy_count"], 1)
        self.assertEqual(res["quarantined_count"], 1)
        self.assertEqual(res["drift_detected_count"], 1)

        # Verify broken inbox received QUARANTINED update
        update_calls = table_mock.update.call_args_list
        self.assertGreaterEqual(len(update_calls), 1)
        update_payload = update_calls[0][0][0]
        self.assertEqual(update_payload["status"], "QUARANTINED")
        self.assertIn("quarantined_until", update_payload)
        self.assertIn("SPF_MISSING_DRIFT", update_payload["quarantine_reason"])

    def test_scan_workspace_dns_drift_dry_run_no_quarantine(self):
        """
        Layer 1: When auto_quarantine=False (dry-run), returns drift report without mutating database.
        """
        mock_inboxes = [
            {
                "id": "inb-broken-dry",
                "email": "dryrun@acme.com",
                "status": "ACTIVE",
                "spf_record": None,
            }
        ]
        mock_dns = {"acme.com": []}
        table_mock = MagicMock()
        self.mock_supabase.table.return_value = table_mock

        res = scan_workspace_dns_drift(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            auto_quarantine=False,
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )

        self.assertEqual(res["total_inboxes"], 1)
        self.assertEqual(res["quarantined_count"], 0)
        self.assertEqual(res["drift_detected_count"], 1)
        # Database should NOT have been updated in dry-run
        table_mock.update.assert_not_called()

    def test_dns_drift_remediation_records_generated(self):
        """
        Layer 1: Provides exact DNS copy-paste records (v=spf1 ..., v=DMARC1 ...) to resolve issues.
        """
        inbox = {
            "id": "inb-remedy",
            "email": "fixme@outreachcorp.com",
            "domain": "outreachcorp.com",
        }
        mock_dns = {
            "outreachcorp.com": [],
            "elein._domainkey.outreachcorp.com": [],
            "_dmarc.outreachcorp.com": [],
        }
        audit = audit_sender_inbox_dns_health(inbox, mock_dns=mock_dns)
        remediation = audit.get("remediation_records", [])
        self.assertGreaterEqual(len(remediation), 2)
        # Should have SPF and DMARC copy-paste records
        spf_recs = [r for r in remediation if "v=spf1" in r.get("value", "")]
        dmarc_recs = [r for r in remediation if "v=DMARC1" in r.get("value", "")]
        self.assertTrue(len(spf_recs) >= 1)
        self.assertTrue(len(dmarc_recs) >= 1)

    def test_scan_workspace_dns_drift_handles_supabase_exception(self):
        """
        Layer 1: If Supabase fails or throws an exception during inbox query or update,
        scan_workspace_dns_drift fails safe and does not crash the server.
        """
        broken_supabase = MagicMock()
        broken_supabase.table.side_effect = RuntimeError("Database unreachable")

        res = scan_workspace_dns_drift(
            supabase=broken_supabase,
            workspace_id=self.workspace_id,
            auto_quarantine=True,
        )
        self.assertEqual(res["total_inboxes"], 0)
        self.assertEqual(res["healthy_count"], 0)
        self.assertEqual(res["quarantined_count"], 0)

    def test_inbox_dns_health_empty_mailboxes_list(self):
        """
        Layer 1: Scanning an empty workspace returns a clean report with zero counts.
        """
        res = scan_workspace_dns_drift(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            mock_inboxes=[],
        )
        self.assertEqual(res["total_inboxes"], 0)
        self.assertEqual(res["healthy_count"], 0)
        self.assertEqual(res["quarantined_count"], 0)
        self.assertEqual(res["drift_detected_count"], 0)

    def test_dns_timeout_and_resolution_failure_defense(self):
        """
        Layer 1: Live DNS lookup timeout or network failure fails safe to empty list
        without unhandled socket/resolver exceptions.
        """
        with patch("core.backend.services.dmarc_alignment_service.HAS_DNS_RESOLVER", True):
            with patch("core.backend.services.dmarc_alignment_service.dns") as mock_dns_mod:
                mock_resolver = MagicMock()
                mock_resolver.resolve.side_effect = Exception("DNS query timed out (2.5s)")
                mock_dns_mod.resolver.Resolver.return_value = mock_resolver

                res = evaluate_dmarc_alignment(
                    from_header_domain="timeout-domain.com",
                    mock_dns=None,
                )
                self.assertFalse(res["valid"])
                self.assertEqual(res["policy"], "missing")
                self.assertTrue(res["can_safely_send"])

    def test_notification_dispatch_failure_resilience(self):
        """
        Layer 1: Failure in notification_service during auto-quarantine is isolated
        and does not interrupt or fail the scan pipeline.
        """
        mock_inboxes = [{
            "id": "inb-broken-notif",
            "email": "notif@broken.com",
            "spf_record": None,
        }]
        mock_dns = {"broken.com": []}

        with patch("core.backend.services.dmarc_alignment_service.HAS_NOTIFICATION_SERVICE", True):
            with patch("core.backend.services.dmarc_alignment_service.dispatch_notification") as mock_dispatch:
                mock_dispatch.side_effect = RuntimeError("Push notification server down")

                res = scan_workspace_dns_drift(
                    supabase=self.mock_supabase,
                    workspace_id=self.workspace_id,
                    auto_quarantine=True,
                    mock_inboxes=mock_inboxes,
                    mock_dns=mock_dns,
                )
                self.assertEqual(res["quarantined_count"], 1)

    def test_scan_workspace_dns_drift_healthy_mailboxes_preserved(self):
        """
        Layer 1: Mailbox with valid SPF, DKIM, and aligned DMARC remains ACTIVE
        and deliverability score is in peak health tier (>=80).
        """
        mock_inboxes = [{
            "id": "inb-healthy-1",
            "email": "founder@stellarcorp.io",
            "status": "ACTIVE",
            "spf_record": "v=spf1 include:_spf.elein.ai ~all",
            "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3...",
            "dmarc_record": "v=DMARC1; p=reject; aspf=r; adkim=r",
        }]
        res = scan_workspace_dns_drift(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            auto_quarantine=True,
            mock_inboxes=mock_inboxes,
        )
        self.assertEqual(res["healthy_count"], 1)
        self.assertEqual(res["quarantined_count"], 0)
        audit = res["inboxes_audit"][0]
        self.assertTrue(audit["healthy"])
        self.assertFalse(audit["should_quarantine"])
        self.assertEqual(audit["status_applied"], "ACTIVE")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & SECURITY DEFENSE (IDOR, MALFORMED & SYNTAX)
    # =========================================================================

    def test_router_dmarc_alignment_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/dmarc-alignment-audit returns structured report.
        """
        req = DMARCAlignmentAuditRequest(
            from_domain="acme.com",
            return_path_domain="mail.acme.com",
            dkim_domain="acme.com",
            dmarc_record="v=DMARC1; p=reject; aspf=r; adkim=r",
        )
        res = api_dmarc_alignment_audit(
            req=req,
            workspace_id=self.workspace_id,
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["dmarc_aligned"])
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["policy"], "reject")

    def test_router_dns_drift_scan_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/check-dns-drift executes workspace scan.
        """
        req = DNSDriftScanRequest(
            auto_quarantine=False,
            mock_inboxes=[{
                "id": "inb-api-test",
                "email": "api@testcorp.com",
                "spf_record": "v=spf1 include:_spf.elein.ai ~all",
                "dkim_record": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ...",
                "dmarc_record": "v=DMARC1; p=none",
            }],
        )
        res = api_check_dns_drift(
            req=req,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )
        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertEqual(res["total_inboxes"], 1)
        self.assertEqual(res["healthy_count"], 1)

    def test_cross_tenant_idor_dns_drift_scoping(self):
        """
        Layer 2: Scanning workspace ws_tenant_alpha strictly filters Supabase queries
        by workspace_id='ws_tenant_alpha', preventing cross-tenant inbox leakage or mutation.
        """
        table_mock = MagicMock()
        self.mock_supabase.table.return_value = table_mock

        scan_workspace_dns_drift(
            supabase=self.mock_supabase,
            workspace_id="ws_tenant_alpha",
            auto_quarantine=True,
        )
        self.mock_supabase.table.assert_called_with("email_sender_inboxes")
        table_mock.select.return_value.eq.assert_called_with("workspace_id", "ws_tenant_alpha")

    def test_malformed_domain_and_email_inputs(self):
        """
        Layer 2: Handles None, "", "://", "127.0.0.1", "localhost", "bad..domain"
        safely with can_safely_send=False and rejection_reason='INVALID_FROM_HEADER_DOMAIN'.
        """
        malformed_inputs = [
            None,
            "",
            "   ",
            "://",
            "localhost",
            "127.0.0.1",
            "169.254.169.254",
            "host.local",
            "bad..domain.com",
            "http://",
        ]
        for bad in malformed_inputs:
            res = evaluate_dmarc_alignment(from_header_domain=bad)
            self.assertFalse(res["valid"], f"Expected valid=False for: {bad}")
            self.assertFalse(res["can_safely_send"])
            self.assertEqual(res["rejection_reason"], "INVALID_FROM_HEADER_DOMAIN")
            self.assertEqual(res["deliverability_risk"], "CRITICAL_REJECT_RISK")

    def test_subaddress_and_angle_brackets_stripped(self):
        """
        Layer 2: Jane Doe <sales+campaign@acme.com> correctly extracts acme.com.
        """
        from_display = "Jane Doe <sales+campaign@acme.com>"
        res = evaluate_dmarc_alignment(
            from_header_domain=from_display,
            return_path_domain="acme.com",
            dmarc_record="v=DMARC1; p=reject",
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["from_header_domain"], "acme.com")
        self.assertEqual(res["from_header_root"], "acme.com")

    def test_corrupted_dmarc_tags_handled_safely(self):
        """
        Layer 2: Missing v=DMARC1, non-integer pct, invalid policy p=drop handled gracefully.
        """
        # Missing v=DMARC1 as first tag
        res_no_v = parse_dmarc_record("p=reject; aspf=r")
        self.assertFalse(res_no_v["valid"])
        self.assertIn("v=DMARC1", res_no_v["errors"][0])

        # Wrong version
        res_bad_v = parse_dmarc_record("v=SPF1; p=reject")
        self.assertFalse(res_bad_v["valid"])

        # Invalid policy
        res_bad_p = parse_dmarc_record("v=DMARC1; p=drop")
        self.assertFalse(res_bad_p["valid"])
        self.assertTrue(any("invalid policy" in e.lower() for e in res_bad_p["errors"]))

        # Non-numeric pct defaults safely to 100
        res_bad_pct = parse_dmarc_record("v=DMARC1; p=reject; pct=fifty")
        self.assertTrue(res_bad_pct["valid"])
        self.assertEqual(res_bad_pct["pct"], 100)

    def test_percentage_pct_clamped(self):
        """
        Layer 2: pct=200 clamped to 100, pct=-10 clamped to 0.
        """
        res_over = parse_dmarc_record("v=DMARC1; p=reject; pct=200")
        self.assertEqual(res_over["pct"], 100)

        res_under = parse_dmarc_record("v=DMARC1; p=reject; pct=-10")
        self.assertEqual(res_under["pct"], 0)

        res_valid = parse_dmarc_record("v=DMARC1; p=reject; pct=50")
        self.assertEqual(res_valid["pct"], 50)

    def test_ssrf_ip_literal_and_internal_domain_rejection(self):
        """
        Layer 2: SSRF defense blocks IP literals and internal network TLDs.
        """
        ssrf_targets = [
            "10.0.0.1",
            "192.168.1.1",
            "172.16.0.1",
            "cluster.internal",
            "kube.local",
            "router.lan",
        ]
        for target in ssrf_targets:
            res = evaluate_dmarc_alignment(from_header_domain=target)
            self.assertFalse(res["valid"])
            self.assertEqual(res["rejection_reason"], "INVALID_FROM_HEADER_DOMAIN")

    def test_case_insensitivity_and_whitespace_in_dmarc_tags(self):
        """
        Layer 2: Arbitrary spaces and uppercase tag names/values parsed reliably.
        """
        raw = "  V = DMARC1 ;  P = ReJeCt ;  ASPF = S ; ADKIM = R ;  PCT = 75 "
        parsed = parse_dmarc_record(raw)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["policy"], "reject")
        self.assertEqual(parsed["aspf"], "s")
        self.assertEqual(parsed["adkim"], "r")
        self.assertEqual(parsed["pct"], 75)

    def test_duplicate_dmarc_tags_handled_safely(self):
        """
        Layer 2: Duplicate tags in DMARC record overwrite with warning without throwing exceptions.
        """
        raw = "v=DMARC1; p=none; p=reject; aspf=r"
        parsed = parse_dmarc_record(raw)
        self.assertTrue(parsed["valid"])
        self.assertEqual(parsed["policy"], "reject")
        self.assertTrue(len(parsed["warnings"]) >= 1)

    def test_router_empty_domain_rejected_400(self):
        """
        Layer 2: POST /deliverability/dmarc-alignment-audit with empty domain raises HTTP 400.
        """
        req = DMARCAlignmentAuditRequest(from_domain="")
        with self.assertRaises(HTTPException) as ctx:
            api_dmarc_alignment_audit(req=req, workspace_id=self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_dmarc_facade_methods_parity(self):
        """
        Layer 2: Confirms static methods on DMARCAlignmentService facade match underlying functions.
        """
        dmarc_raw = "v=DMARC1; p=reject; aspf=s"
        parsed_func = parse_dmarc_record(dmarc_raw)
        parsed_facade = DMARCAlignmentService.parse_dmarc_record(dmarc_raw)
        self.assertEqual(parsed_func, parsed_facade)

        eval_func = evaluate_dmarc_alignment("acme.com", dmarc_record=dmarc_raw)
        eval_facade = DMARCAlignmentService.evaluate_dmarc_alignment("acme.com", dmarc_record=dmarc_raw)
        self.assertEqual(eval_func, eval_facade)


if __name__ == "__main__":
    unittest.main()
