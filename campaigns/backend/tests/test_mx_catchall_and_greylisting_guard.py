"""
test_mx_catchall_and_greylisting_guard.py — Comprehensive Paranoia Test Automation Suite
for Phase 38 (Recipient MX Record Validator, Catch-All / Accept-All Probe & Greylisting Deferral Engine).

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - DNS MX record resolution and priority ordering (preference 10 before preference 20).
    - ESP fingerprinting (Google Workspace, Microsoft 365, Proofpoint, Mimecast, Barracuda, Zoho, Proton, Self-Hosted, Unknown).
    - RFC 5321 Section 5.1 implicit MX fallback (A / AAAA address records when no MX).
    - Missing MX and A record rejection (NO_MAIL_EXCHANGER, can_receive_mail=False).
    - Corporate catch-all / accept-all detection flagged (is_catch_all=True, CATCH_ALL_ACCEPT_ALL).
    - Non-catch-all specific domain verification (is_catch_all=False, VERIFIED_SPECIFIC).
    - SMTP deferral and greylisting pattern detection for code 451.
    - Truncated exponential backoff calculation (Attempt 1: 300s, Attempt 2: 600s, Attempt 3: 1200s, clamped at 3600s).
    - Suggested retry wait time extraction (seconds, minutes).
    - Non-deferral permanent 5xx rejection (fail_permanent).

  - Layer 1: Environmental Failure Analysis
    - RFC 7505 Null MX record rejection (preference=0, host="." and host="").
    - Consumer free webmail protection: bypasses network probe, never flagged as catch-all.
    - All major free webmail providers (Gmail, Yahoo, Outlook, Hotmail, iCloud, Proton) protected.
    - Executor aborts outreach on missing mail exchanger (reason="no_mail_exchanger", 0 credits burned).
    - Executor handles SMTP greylisting deferral (status="deferred", reason="smtp_greylisted", next_run_delta_seconds).
    - Executor enriches telemetry with recipient ESP, catch-all status, and MX record count.
    - Executor permits dispatch when implicit MX (A record) is present.
    - DNS resolver failure isolation (timeout, NXDOMAIN, NoAnswer fallback).
    - Catch-all live probe timeout/connection refused fails safe to UNKNOWN_UNPROBED.
    - In-memory cache TTL and cache clearing.

  - Layer 2: Human Paranoia & Security Defense
    - SSRF and private IP literal rejection (localhost, 127.0.0.1, 169.254.169.254, 10.0.0.1, ::1).
    - Subaddressing and display name format cleansing ("Jane Doe <prospect+marketing@acme.com>" -> acme.com).
    - Router endpoint POST /api/elein/deliverability/verify-mx verified via TestClient.
    - Router endpoint POST /api/elein/deliverability/check-catch-all verified via TestClient.
    - Router endpoint POST /api/elein/deliverability/evaluate-smtp-deferral verified via TestClient.
    - Malformed email inputs handled safely (None, "", "://", bad@@domain).
    - Router validation on missing domain (HTTP 400).
    - Missing request payload validation (HTTP 422).
    - Overlong email inputs handled safely.
    - URL protocol, path, and query parameter stripping.
    - Internal and private TLD rejection (.local, .internal, .lan, .corp).
    - Facade class static methods parity.
    - Enum definitions and alias integrity (BARRACODA / BARRACUDA).
"""

import io
import re
import socket
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from core.backend.services.mx_and_catchall_guard import (
    MXProvider,
    CatchAllRisk,
    MXAndCatchAllGuard,
    resolve_domain_mx_records,
    detect_catch_all_domain,
    detect_smtp_deferral_or_greylist,
    calculate_greylist_retry_delay,
    fingerprint_mx_provider,
    extract_wait_time_seconds,
    clear_catch_all_cache,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import (
    MXVerifyRequest,
    CatchAllCheckRequest,
    SMTPDeferralEvaluateRequest,
    api_verify_mx,
    api_check_catch_all,
    api_evaluate_smtp_deferral,
)


class TestMXCatchallAndGreylistingGuard(unittest.TestCase):
    """
    Comprehensive Three-Layer Paranoia Test Automation Suite for Phase 38:
    Recipient MX Record Validator, Catch-All / Accept-All Probe & Greylisting Deferral Engine.
    """

    def setUp(self):
        self.workspace_id = "ws-mx-paranoia-test"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )
        clear_catch_all_cache()

    def tearDown(self):
        clear_catch_all_cache()

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER (CORE MECHANICS)
    # =========================================================================

    def test_resolve_domain_mx_records_ordered_by_priority(self):
        """
        Layer 0: Priority 10 sorted before priority 20. Primary MX points to lowest preference host.
        """
        mock_dns = {
            "acme.com": {
                "MX": [
                    {"priority": 20, "host": "alt1.aspmx.l.google.com"},
                    {"priority": 10, "host": "aspmx.l.google.com"},
                    {"priority": 30, "host": "alt2.aspmx.l.google.com"},
                ]
            }
        }
        res = resolve_domain_mx_records("acme.com", mock_dns=mock_dns)
        self.assertTrue(res["valid"])
        self.assertTrue(res["can_receive_mail"])
        self.assertEqual(res["status"], "VALID_MX")
        self.assertEqual(len(res["mx_records"]), 3)
        self.assertEqual(res["mx_records"][0]["priority"], 10)
        self.assertEqual(res["mx_records"][0]["host"], "aspmx.l.google.com")
        self.assertEqual(res["mx_records"][1]["priority"], 20)
        self.assertEqual(res["mx_records"][2]["priority"], 30)
        self.assertEqual(res["primary_mx"], "aspmx.l.google.com")
        self.assertEqual(res["esp_provider"], MXProvider.GOOGLE_WORKSPACE.value)
        self.assertFalse(res["has_implicit_mx"])

    def test_esp_fingerprinting_google_workspace(self):
        """
        Layer 0: 'aspmx.l.google.com' identified as GOOGLE_WORKSPACE.
        """
        provider = fingerprint_mx_provider("aspmx.l.google.com", "target.com")
        self.assertEqual(provider, MXProvider.GOOGLE_WORKSPACE)

        provider_alt = fingerprint_mx_provider("alt1.aspmx.l.google.com", "target.com")
        self.assertEqual(provider_alt, MXProvider.GOOGLE_WORKSPACE)

        provider_smtp = fingerprint_mx_provider("smtp.google.com", "target.com")
        self.assertEqual(provider_smtp, MXProvider.GOOGLE_WORKSPACE)

    def test_esp_fingerprinting_microsoft_365(self):
        """
        Layer 0: 'acme-com.mail.protection.outlook.com' identified as MICROSOFT_365.
        """
        provider = fingerprint_mx_provider("acme-com.mail.protection.outlook.com", "acme.com")
        self.assertEqual(provider, MXProvider.MICROSOFT_365)

        provider_ms = fingerprint_mx_provider("mail.office365.com", "target.com")
        self.assertEqual(provider_ms, MXProvider.MICROSOFT_365)

    def test_esp_fingerprinting_proofpoint(self):
        """
        Layer 0: 'mx1-us1.pphosted.com' identified as PROOFPOINT.
        """
        provider = fingerprint_mx_provider("mx1-us1.pphosted.com", "enterprise.com")
        self.assertEqual(provider, MXProvider.PROOFPOINT)

        provider_direct = fingerprint_mx_provider("mx.proofpoint.com", "enterprise.com")
        self.assertEqual(provider_direct, MXProvider.PROOFPOINT)

    def test_esp_fingerprinting_mimecast(self):
        """
        Layer 0: 'us-smtp-inbound-1.mimecast.com' identified as MIMECAST.
        """
        provider = fingerprint_mx_provider("us-smtp-inbound-1.mimecast.com", "corp.com")
        self.assertEqual(provider, MXProvider.MIMECAST)

        provider_uk = fingerprint_mx_provider("eu-smtp-inbound-2.mimecast.co.uk", "corp.co.uk")
        self.assertEqual(provider_uk, MXProvider.MIMECAST)

    def test_rfc5321_fallback_to_implicit_mx_a_record(self):
        """
        Layer 0: No MX records but valid A record passes per RFC 5321 with has_implicit_mx=True.
        """
        mock_dns = {
            "legacy-box.com": {
                "MX": [],
                "A": ["198.51.100.25"],
            }
        }
        res = resolve_domain_mx_records("legacy-box.com", mock_dns=mock_dns)
        self.assertTrue(res["valid"])
        self.assertTrue(res["can_receive_mail"])
        self.assertTrue(res["has_implicit_mx"])
        self.assertEqual(res["status"], "IMPLICIT_MX_RFC5321")
        self.assertEqual(res["primary_mx"], "legacy-box.com")
        self.assertEqual(len(res["mx_records"]), 1)
        self.assertTrue(res["mx_records"][0].get("implicit"))

    def test_missing_mx_and_a_record_rejected(self):
        """
        Layer 0: No MX and no A record flags NO_MAIL_EXCHANGER, can_receive_mail=False.
        """
        mock_dns = {
            "dead-domain-xyz.com": {
                "MX": [],
                "A": [],
                "AAAA": [],
            }
        }
        res = resolve_domain_mx_records("dead-domain-xyz.com", mock_dns=mock_dns)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])
        self.assertEqual(res["status"], "NO_MAIL_EXCHANGER")
        self.assertIn("No MX or address", res["error"])
        self.assertIsNone(res["primary_mx"])

    def test_detect_catch_all_domain_flagged(self):
        """
        Layer 0: Catch-all corporate domain returns is_catch_all=True, catch_all_risk='CATCH_ALL_ACCEPT_ALL'.
        """
        res = detect_catch_all_domain("enterprise.com", mock_is_catch_all=True)
        self.assertEqual(res["domain"], "enterprise.com")
        self.assertTrue(res["is_catch_all"])
        self.assertEqual(res["catch_all_risk"], CatchAllRisk.CATCH_ALL_ACCEPT_ALL.value)
        self.assertIn("elein_canary_", res["canary_tested"])
        self.assertGreaterEqual(res["confidence"], 0.9)
        self.assertIn("Domain accepts all addresses", res["recommendation"])

    def test_detect_specific_non_catch_all_domain(self):
        """
        Layer 0: Non-catch-all returns is_catch_all=False, catch_all_risk='VERIFIED_SPECIFIC'.
        """
        res = detect_catch_all_domain("specific-corp.com", mock_is_catch_all=False)
        self.assertEqual(res["domain"], "specific-corp.com")
        self.assertFalse(res["is_catch_all"])
        self.assertEqual(res["catch_all_risk"], CatchAllRisk.VERIFIED_SPECIFIC.value)
        self.assertIn("elein_canary_", res["canary_tested"])
        self.assertGreaterEqual(res["confidence"], 0.9)
        self.assertIn("rejects non-existent addresses", res["recommendation"])

    def test_detect_smtp_deferral_greylisting_code_451(self):
        """
        Layer 0: '451 4.7.1 Greylisted, please try again later' flags is_greylisted=True, retry_recommended=True.
        """
        res = detect_smtp_deferral_or_greylist(451, "451 4.7.1 Greylisted, please try again later")
        self.assertTrue(res["is_deferred"])
        self.assertTrue(res["is_greylisted"])
        self.assertTrue(res["retry_recommended"])
        self.assertEqual(res["action"], "defer_and_retry")
        self.assertEqual(res["retry_delay_seconds"], 300)

    def test_calculate_greylist_retry_delay_exponential_backoff(self):
        """
        Layer 0: Attempt 1 = 300s, Attempt 2 = 600s, Attempt 3 = 1200s, Attempt 4 = 2400s, clamped at 3600s.
        """
        delay_1 = calculate_greylist_retry_delay(attempt_count=1)
        delay_2 = calculate_greylist_retry_delay(attempt_count=2)
        delay_3 = calculate_greylist_retry_delay(attempt_count=3)
        delay_4 = calculate_greylist_retry_delay(attempt_count=4)
        delay_5 = calculate_greylist_retry_delay(attempt_count=5)
        delay_10 = calculate_greylist_retry_delay(attempt_count=10)

        self.assertEqual(delay_1, 300)
        self.assertEqual(delay_2, 600)
        self.assertEqual(delay_3, 1200)
        self.assertEqual(delay_4, 2400)
        self.assertEqual(delay_5, 3600)
        self.assertEqual(delay_10, 3600)

    def test_esp_fingerprinting_barracuda(self):
        """
        Layer 0: 'd1234.ess.barracudanetworks.com' identified as BARRACUDA.
        """
        provider = fingerprint_mx_provider("d1234.ess.barracudanetworks.com", "target.com")
        self.assertEqual(provider.value, "BARRACUDA")
        self.assertEqual(provider, MXProvider.BARRACUDA)

    def test_esp_fingerprinting_zoho(self):
        """
        Layer 0: 'mx.zoho.com' identified as ZOHO.
        """
        provider = fingerprint_mx_provider("mx.zoho.com", "smallbiz.com")
        self.assertEqual(provider, MXProvider.ZOHO)

    def test_esp_fingerprinting_proton(self):
        """
        Layer 0: 'mail.protonmail.ch' identified as PROTON.
        """
        provider = fingerprint_mx_provider("mail.protonmail.ch", "privacycorp.org")
        self.assertEqual(provider, MXProvider.PROTON)

        provider_me = fingerprint_mx_provider("mailsec.proton.me", "target.me")
        self.assertEqual(provider_me, MXProvider.PROTON)

    def test_esp_fingerprinting_self_hosted(self):
        """
        Layer 0: Host matching target domain (e.g. mail.acmecorp.com for acmecorp.com) -> SELF_HOSTED.
        """
        provider = fingerprint_mx_provider("mail.acmecorp.com", "acmecorp.com")
        self.assertEqual(provider, MXProvider.SELF_HOSTED)

        provider_exact = fingerprint_mx_provider("acmecorp.com", "acmecorp.com")
        self.assertEqual(provider_exact, MXProvider.SELF_HOSTED)

    def test_esp_fingerprinting_unknown(self):
        """
        Layer 0: Arbitrary unknown host without domain match -> UNKNOWN.
        """
        provider = fingerprint_mx_provider("mx1.some-niche-custom-relay-99.net", "different-corp.com")
        self.assertEqual(provider, MXProvider.UNKNOWN)

    def test_calculate_greylist_retry_delay_suggested_wait_time(self):
        """
        Layer 0: Explicit suggested_seconds respected, clamped to [60, 3600].
        """
        self.assertEqual(calculate_greylist_retry_delay(suggested_seconds=180), 180)
        self.assertEqual(calculate_greylist_retry_delay(suggested_seconds=15), 60)
        self.assertEqual(calculate_greylist_retry_delay(suggested_seconds=7200), 3600)

    def test_detect_smtp_deferral_codes_421_450_452(self):
        """
        Layer 0: SMTP codes 421, 450, 452 flagged as deferred with defer_and_retry action.
        """
        c421 = detect_smtp_deferral_or_greylist(421, "421 Service not available, closing transmission channel")
        self.assertTrue(c421["is_deferred"])
        self.assertEqual(c421["action"], "defer_and_retry")

        c450 = detect_smtp_deferral_or_greylist(450, "450 4.2.0 Mailbox temporarily unavailable")
        self.assertTrue(c450["is_deferred"])
        self.assertEqual(c450["action"], "defer_and_retry")

        c452 = detect_smtp_deferral_or_greylist(452, "452 4.5.3 Too many recipients, try again in 120 seconds")
        self.assertTrue(c452["is_deferred"])
        self.assertEqual(c452["retry_delay_seconds"], 120)

    def test_smtp_permanent_error_550_not_deferred(self):
        """
        Layer 0: SMTP code 550 permanent error is marked is_deferred=False, fail_permanent.
        """
        res = detect_smtp_deferral_or_greylist(550, "550 5.1.1 User unknown")
        self.assertFalse(res["is_deferred"])
        self.assertFalse(res["is_greylisted"])
        self.assertFalse(res["retry_recommended"])
        self.assertEqual(res["action"], "fail_permanent")
        self.assertEqual(res["retry_delay_seconds"], 0)

    def test_extract_wait_time_seconds_minutes_and_seconds(self):
        """
        Layer 0: Parses wait times: 'try again in 5 minutes' -> 300, 'wait 120 seconds' -> 120.
        """
        self.assertEqual(extract_wait_time_seconds("try again in 5 minutes"), 300)
        self.assertEqual(extract_wait_time_seconds("retry after 120 seconds"), 120)
        self.assertEqual(extract_wait_time_seconds("waiting for 60s please"), 60)
        self.assertIsNone(extract_wait_time_seconds("no wait time specified"))

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS (INTEGRATION & RESILIENCE)
    # =========================================================================

    def test_rfc7505_null_mx_record_rejected(self):
        """
        Layer 1: Domain with preference=0, host='.' rejected as NULL_MX_RFC7505.
        """
        mock_dns = {
            "discards-email.com": {
                "MX": [{"priority": 0, "host": "."}]
            }
        }
        res = resolve_domain_mx_records("discards-email.com", mock_dns=mock_dns)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])
        self.assertEqual(res["status"], "NULL_MX_RFC7505")
        self.assertIn("RFC 7505 Null MX", res["error"])
        self.assertIsNone(res["primary_mx"])

    def test_rfc7505_null_mx_empty_string_host(self):
        """
        Layer 1: Domain with preference=0 and host='' also rejected as NULL_MX_RFC7505.
        """
        mock_dns = {
            "null-target.org": {
                "MX": [{"priority": 0, "host": ""}]
            }
        }
        res = resolve_domain_mx_records("null-target.org", mock_dns=mock_dns)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])
        self.assertEqual(res["status"], "NULL_MX_RFC7505")

    def test_free_webmail_never_probed_for_catch_all(self):
        """
        Layer 1: 'user@gmail.com' immediately returns is_catch_all=False without network probe.
        """
        res = detect_catch_all_domain("user@gmail.com")
        self.assertEqual(res["domain"], "gmail.com")
        self.assertFalse(res["is_catch_all"])
        self.assertEqual(res["catch_all_risk"], CatchAllRisk.VERIFIED_SPECIFIC.value)
        self.assertIsNone(res["canary_tested"])
        self.assertEqual(res["confidence"], 1.0)
        self.assertIn("Free webmail provider", res["recommendation"])

    def test_free_webmail_providers_all_bypass_catchall_probe(self):
        """
        Layer 1: Yahoo, Outlook, Hotmail, iCloud, Proton all return is_catch_all=False, VERIFIED_SPECIFIC.
        """
        providers = [
            "lead@yahoo.com",
            "sales@outlook.com",
            "contact@hotmail.com",
            "ceo@icloud.com",
            "sec@proton.me",
        ]
        for em in providers:
            res = detect_catch_all_domain(em)
            self.assertFalse(res["is_catch_all"], f"Failed for {em}")
            self.assertEqual(res["catch_all_risk"], CatchAllRisk.VERIFIED_SPECIFIC.value)
            self.assertEqual(res["confidence"], 1.0)
            self.assertIsNone(res["canary_tested"])

    def test_executor_aborts_send_when_no_mail_exchanger(self):
        """
        Layer 1: EleInNodeExecutor.handle_send_email aborts with reason='no_mail_exchanger'
        when domain lacks MX and A records, burning 0 credits.
        """
        data = {
            "to_email": "prospect@nonexistent-mx-domain-404.com",
            "subject": "Platform introduction",
            "body": "Hi there.",
            "lead_id": "lead-mx-fail-1",
            "mock_dns": {
                "nonexistent-mx-domain-404.com": {
                    "MX": [],
                    "A": [],
                }
            },
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "no_mail_exchanger")
        self.assertEqual(res["branch"], Branch.FAILED.value)
        self.assertIn("no valid mail exchanger", res["error"])
        # Verify no database logging of outbound message took place
        self.mock_supabase.table.assert_not_called()

    def test_executor_handles_smtp_greylisting_deferral(self):
        """
        Layer 1: Greylisted send transitions to status='deferred', reason='smtp_greylisted' with next_run_delta_seconds.
        """
        data = {
            "to_email": "prospect@greylisted-corp.com",
            "subject": "Platform introduction",
            "body": "Hi there.",
            "lead_id": "lead-grey-1",
            "mock_dns": {
                "greylisted-corp.com": {
                    "MX": [{"priority": 10, "host": "mail.greylisted-corp.com"}]
                }
            },
        }

        # Mock urllib.request.urlopen to simulate SendGrid returning HTTP 451 Greylisted
        http_error = urllib.error.HTTPError(
            url="https://api.sendgrid.com/v3/mail/send",
            code=451,
            msg="451 4.7.1 Greylisted, please try again in 600 seconds",
            hdrs={},
            fp=io.BytesIO(b"451 4.7.1 Greylisted, please try again in 600 seconds"),
        )

        with patch.dict("os.environ", {"SENDGRID_API_KEY": "SG.test_key_valid_123"}):
            with patch("urllib.request.urlopen", side_effect=http_error):
                res = self.executor.handle_send_email(data, linkedin_url=None)

        self.assertEqual(res["status"], "deferred")
        self.assertEqual(res["reason"], "smtp_greylisted")
        self.assertEqual(res["next_run_delta_seconds"], 600)
        self.assertEqual(res["branch"], Branch.FAILED.value)
        self.assertIn("SMTP temporary deferral", res["error"])

    def test_executor_enriches_telemetry_with_mx_provider(self):
        """
        Layer 1: Successful send includes recipient_esp='GOOGLE_WORKSPACE', is_catch_all_domain=False.
        """
        data = {
            "to_email": "alex@google-hosted-corp.com",
            "subject": "Introductory note",
            "body": "Hi Alex, hope you are well.",
            "lead_id": "lead-mx-telemetry-1",
            "mock_dns": {
                "google-hosted-corp.com": {
                    "MX": [{"priority": 10, "host": "aspmx.l.google.com"}]
                }
            },
            "mock_is_catch_all": False,
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res.get("recipient_esp"), "GOOGLE_WORKSPACE")
        self.assertFalse(res.get("is_catch_all_domain"))
        self.assertEqual(res.get("mx_record_count"), 1)

    def test_executor_proceeds_with_implicit_mx(self):
        """
        Layer 1: Domain without MX but with valid A record is permitted to send with implicit MX.
        """
        data = {
            "to_email": "alex@legacy-box-server.org",
            "subject": "System notice",
            "body": "Hello alex.",
            "lead_id": "lead-implicit-1",
            "mock_dns": {
                "legacy-box-server.org": {
                    "MX": [],
                    "A": ["203.0.113.195"],
                }
            },
            "mock_is_catch_all": False,
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res.get("mx_record_count"), 1)

    def test_dns_timeout_resilience_fallback(self):
        """
        Layer 1: Socket/DNS timeout during MX resolution fails safe with error dictionary without uncaught exception.
        """
        with patch("dns.resolver.Resolver.resolve", side_effect=socket.timeout("DNS lookup timed out")):
            res = resolve_domain_mx_records("timeout-test-domain.com")
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_receive_mail"])
            self.assertEqual(res["status"], "NO_MAIL_EXCHANGER")
            self.assertIn("No MX or address", res["error"])

    def test_dns_nxdomain_resilience_fallback(self):
        """
        Layer 1: NXDOMAIN exception returns clean dictionary can_receive_mail=False.
        """
        try:
            import dns.resolver
            nx_exc = dns.resolver.NXDOMAIN()
        except Exception:
            nx_exc = Exception("NXDOMAIN")

        with patch("dns.resolver.Resolver.resolve", side_effect=nx_exc):
            res = resolve_domain_mx_records("nxdomain-test.com")
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_receive_mail"])
            self.assertEqual(res["status"], "NO_MAIL_EXCHANGER")

    def test_dns_no_answer_resilience_fallback(self):
        """
        Layer 1: NoAnswer exception returns clean dictionary can_receive_mail=False.
        """
        try:
            import dns.resolver
            no_ans_exc = dns.resolver.NoAnswer()
        except Exception:
            no_ans_exc = Exception("NoAnswer")

        with patch("dns.resolver.Resolver.resolve", side_effect=no_ans_exc):
            res = resolve_domain_mx_records("noanswer-test.com")
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_receive_mail"])
            self.assertEqual(res["status"], "NO_MAIL_EXCHANGER")

    def test_catch_all_live_probe_timeout_fails_safe(self):
        """
        Layer 1: Live SMTP probe timeout or connection failure returns UNKNOWN_UNPROBED safely.
        """
        mock_dns = {
            "unreachable-server.com": {
                "MX": [{"priority": 10, "host": "mail.unreachable-server.com"}]
            }
        }
        with patch("smtplib.SMTP", side_effect=socket.timeout("Connection timed out on port 25")):
            with patch("core.backend.services.mx_and_catchall_guard.resolve_domain_mx_records") as mock_res:
                mock_res.return_value = {
                    "can_receive_mail": True,
                    "primary_mx": "mail.unreachable-server.com",
                }
                res = detect_catch_all_domain("unreachable-server.com")
                self.assertFalse(res["is_catch_all"])
                self.assertEqual(res["catch_all_risk"], CatchAllRisk.UNKNOWN_UNPROBED.value)
                self.assertIn("could not complete", res["recommendation"])

    def test_catch_all_cache_ttl_and_invalidation(self):
        """
        Layer 1: Cached catch-all probe result reused within 24h, cleared by clear_catch_all_cache.
        """
        res1 = detect_catch_all_domain("cached-corp.com", mock_is_catch_all=True)
        self.assertTrue(res1["is_catch_all"])

        # Subsequent call without mock uses cache
        res2 = detect_catch_all_domain("cached-corp.com")
        self.assertTrue(res2["is_catch_all"])

        # Cache clear forces re-evaluation
        clear_catch_all_cache()
        res3 = detect_catch_all_domain("cached-corp.com", mock_is_catch_all=False)
        self.assertFalse(res3["is_catch_all"])

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & SECURITY DEFENSE
    # =========================================================================

    def test_ssrf_localhost_and_private_ip_mx_rejected(self):
        """
        Layer 2: Rejects localhost, 127.0.0.1, 169.254.169.254, 10.0.0.1, ::1 as invalid/prohibited.
        """
        prohibited_inputs = [
            "localhost",
            "127.0.0.1",
            "169.254.169.254",
            "10.0.0.1",
            "::1",
            "0.0.0.0",
        ]
        for target in prohibited_inputs:
            res = resolve_domain_mx_records(target)
            self.assertFalse(res["valid"], f"Should reject {target}")
            self.assertFalse(res["can_receive_mail"])
            self.assertIn(res["status"], ["INVALID_DOMAIN", "PROHIBITED_SSRF_DOMAIN"])

    def test_subaddressing_and_display_format_cleansed(self):
        """
        Layer 2: 'Jane Doe <prospect+marketing@acme.com>' correctly resolves acme.com.
        """
        mock_dns = {
            "acme.com": {
                "MX": [{"priority": 10, "host": "aspmx.l.google.com"}]
            }
        }
        raw_email = "Jane Doe <prospect+marketing@acme.com>"
        res = resolve_domain_mx_records(raw_email, mock_dns=mock_dns)
        self.assertEqual(res["domain"], "acme.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["primary_mx"], "aspmx.l.google.com")

    def test_router_verify_mx_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/verify-mx returns structured MX resolution.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/verify-mx",
                json={
                    "domain": "google.com",
                    "mock_dns": {
                        "google.com": {
                            "MX": [{"priority": 10, "host": "aspmx.l.google.com"}]
                        }
                    },
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["domain"], "google.com")
            self.assertTrue(data["valid"])
            self.assertTrue(data["can_receive_mail"])
            self.assertEqual(data["esp_provider"], "GOOGLE_WORKSPACE")
            self.assertEqual(data["workspace_id"], self.workspace_id)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_router_check_catch_all_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/check-catch-all returns catch-all assessment.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/check-catch-all",
                json={
                    "domain": "acme-corp.com",
                    "mock_is_catch_all": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["domain"], "acme-corp.com")
            self.assertTrue(data["is_catch_all"])
            self.assertEqual(data["catch_all_risk"], "CATCH_ALL_ACCEPT_ALL")
            self.assertEqual(data["workspace_id"], self.workspace_id)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_router_evaluate_smtp_deferral_endpoint(self):
        """
        Layer 2: POST /api/elein/deliverability/evaluate-smtp-deferral returns deferral timing.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/evaluate-smtp-deferral",
                json={
                    "smtp_code": 451,
                    "smtp_message": "451 4.7.1 Greylisted, please try again later",
                    "attempt_count": 2,
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["is_deferred"])
            self.assertTrue(data["is_greylisted"])
            self.assertTrue(data["retry_recommended"])
            self.assertEqual(data["retry_delay_seconds"], 600)
            self.assertEqual(data["action"], "defer_and_retry")
            self.assertEqual(data["workspace_id"], self.workspace_id)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_malformed_email_inputs_handled_safely(self):
        """
        Layer 2: Handles None, '', '://', 'bad@@domain' returning invalid status safely without exceptions.
        """
        malformed = [None, "", "://", "bad@@domain", "   ", "@nodomain.com", "user@"]
        for item in malformed:
            res = resolve_domain_mx_records(item)
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_receive_mail"])
            self.assertEqual(res["status"], "INVALID_DOMAIN")

            ca_res = detect_catch_all_domain(item)
            self.assertFalse(ca_res["is_catch_all"])
            self.assertEqual(ca_res["catch_all_risk"], CatchAllRisk.UNKNOWN_UNPROBED.value)

    def test_router_verify_mx_missing_domain_400(self):
        """
        Layer 2: Empty or blank domain in request body triggers HTTP 400.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/verify-mx",
                json={"domain": ""},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("required", str(response.json()))
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_router_check_catch_all_missing_domain_400(self):
        """
        Layer 2: Empty or blank domain in catch-all request triggers HTTP 400.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/check-catch-all",
                json={"domain": "   "},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("required", str(response.json()))
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_router_verify_mx_missing_payload_422(self):
        """
        Layer 2: Missing payload fields triggers FastAPI 422 Unprocessable Entity.
        """
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        try:
            client = TestClient(app)
            response = client.post(
                "/api/elein/deliverability/verify-mx",
                json={},
            )
            self.assertEqual(response.status_code, 422)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)

    def test_overlong_email_input_handled_safely(self):
        """
        Layer 2: Overlong domain or email string (>255 chars) fails safe without buffer overflow.
        """
        overlong = "a" * 300 + "@example.com"
        res = resolve_domain_mx_records(overlong)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])

    def test_url_protocol_and_query_stripped_safely(self):
        """
        Layer 2: URL 'https://www.targetcompany.com/path?query=1#sec' cleanly stripped to 'targetcompany.com'.
        """
        raw_url = "https://www.targetcompany.com/about/team?source=linkedin#contact"
        mock_dns = {
            "targetcompany.com": {
                "MX": [{"priority": 10, "host": "aspmx.l.google.com"}]
            }
        }
        res = resolve_domain_mx_records(raw_url, mock_dns=mock_dns)
        self.assertEqual(res["domain"], "targetcompany.com")
        self.assertTrue(res["valid"])

    def test_internal_tld_ssrf_rejected(self):
        """
        Layer 2: Domains ending with internal TLDs (.local, .internal, .lan, .corp) rejected.
        """
        internal_targets = [
            "k8s-master.internal",
            "gateway.local",
            "corp-infra.lan",
            "internal-dc.corp",
            "database.test",
        ]
        for it in internal_targets:
            res = resolve_domain_mx_records(it)
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_receive_mail"])

    def test_facade_class_methods_parity(self):
        """
        Layer 2: MXAndCatchAllGuard static methods match standalone functional implementations.
        """
        mock_dns = {
            "facade-test.com": {
                "MX": [{"priority": 10, "host": "aspmx.l.google.com"}]
            }
        }
        res_facade = MXAndCatchAllGuard.resolve_domain_mx_records("facade-test.com", mock_dns=mock_dns)
        res_direct = resolve_domain_mx_records("facade-test.com", mock_dns=mock_dns)
        self.assertEqual(res_facade, res_direct)

        ca_facade = MXAndCatchAllGuard.detect_catch_all_domain("facade-test.com", mock_is_catch_all=True)
        ca_direct = detect_catch_all_domain("facade-test.com", mock_is_catch_all=True)
        self.assertEqual(ca_facade["is_catch_all"], ca_direct["is_catch_all"])
        self.assertEqual(ca_facade["catch_all_risk"], ca_direct["catch_all_risk"])
        self.assertEqual(ca_facade["domain"], ca_direct["domain"])

        def_facade = MXAndCatchAllGuard.detect_smtp_deferral_or_greylist(451, "Greylisted")
        def_direct = detect_smtp_deferral_or_greylist(451, "Greylisted")
        self.assertEqual(def_facade, def_direct)

        del_facade = MXAndCatchAllGuard.calculate_greylist_retry_delay(2)
        del_direct = calculate_greylist_retry_delay(2)
        self.assertEqual(del_facade, del_direct)

    def test_enum_values_and_aliases(self):
        """
        Layer 2: Enum members, values, and aliases (BARRACODA / BARRACUDA) resolve consistently.
        """
        self.assertEqual(MXProvider.GOOGLE_WORKSPACE.value, "GOOGLE_WORKSPACE")
        self.assertEqual(MXProvider.MICROSOFT_365.value, "MICROSOFT_365")
        self.assertEqual(MXProvider.PROOFPOINT.value, "PROOFPOINT")
        self.assertEqual(MXProvider.MIMECAST.value, "MIMECAST")
        self.assertEqual(MXProvider.BARRACODA.value, "BARRACUDA")
        self.assertEqual(MXProvider.BARRACUDA.value, "BARRACUDA")
        self.assertEqual(MXProvider.ZOHO.value, "ZOHO")
        self.assertEqual(MXProvider.PROTON.value, "PROTON")
        self.assertEqual(MXProvider.SELF_HOSTED.value, "SELF_HOSTED")
        self.assertEqual(MXProvider.UNKNOWN.value, "UNKNOWN")

        self.assertEqual(CatchAllRisk.VERIFIED_SPECIFIC.value, "VERIFIED_SPECIFIC")
        self.assertEqual(CatchAllRisk.CATCH_ALL_ACCEPT_ALL.value, "CATCH_ALL_ACCEPT_ALL")
        self.assertEqual(CatchAllRisk.UNKNOWN_UNPROBED.value, "UNKNOWN_UNPROBED")


if __name__ == "__main__":
    unittest.main()
