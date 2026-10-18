"""
test_mx_and_catchall_guard.py — Comprehensive Unit & Integration Tests for Phase 38

Verifies:
  - Enums: MXProvider and CatchAllRisk definitions and aliases.
  - DNS MX record resolution and preference sorting.
  - RFC 7505 Null MX detection (returns status="NULL_MX_RFC7505", can_receive_mail=False).
  - RFC 5321 Section 5.1 implicit MX fallback (A / AAAA address records when no MX).
  - ESP Provider fingerprinting (Google Workspace, Microsoft 365, Proofpoint, Mimecast,
    Barracuda, Zoho, Proton, Self-Hosted, Unknown).
  - Catch-all / accept-all detection with free webmail defense (Gmail, Yahoo, Outlook).
  - Canary email generation and deterministic mock_is_catch_all handling.
  - SMTP 4xx deferral and greylisting regex pattern detection.
  - Suggested retry time extraction (seconds, minutes).
  - Exponential backoff calculation and bounds clamping [60, 3600].
  - MXAndCatchAllGuard facade class static methods.
"""

import unittest
from core.backend.services.mx_and_catchall_guard import (
    MXProvider,
    CatchAllRisk,
    MXAndCatchAllGuard,
    resolve_domain_mx_records,
    detect_catch_all_domain,
    detect_smtp_deferral_or_greylist,
    calculate_greylist_retry_delay,
    fingerprint_mx_provider,
    clear_catch_all_cache,
)


class TestMXAndCatchAllGuard(unittest.TestCase):

    def setUp(self):
        clear_catch_all_cache()

    def tearDown(self):
        clear_catch_all_cache()

    # =========================================================================
    # Enum Tests
    # =========================================================================

    def test_enums_defined_correctly(self):
        """Verifies MXProvider and CatchAllRisk enum members and values."""
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

    # =========================================================================
    # ESP Fingerprinting Tests
    # =========================================================================

    def test_fingerprint_mx_providers(self):
        """Verifies ESP fingerprinting patterns for major providers."""
        self.assertEqual(
            fingerprint_mx_provider("aspmx.l.google.com"),
            MXProvider.GOOGLE_WORKSPACE,
        )
        self.assertEqual(
            fingerprint_mx_provider("alt1.aspmx.l.google.com"),
            MXProvider.GOOGLE_WORKSPACE,
        )
        self.assertEqual(
            fingerprint_mx_provider("aspmx2.googlemail.com"),
            MXProvider.GOOGLE_WORKSPACE,
        )
        self.assertEqual(
            fingerprint_mx_provider("smtp.google.com"),
            MXProvider.GOOGLE_WORKSPACE,
        )
        self.assertEqual(
            fingerprint_mx_provider("acme-com.mail.protection.outlook.com"),
            MXProvider.MICROSOFT_365,
        )
        self.assertEqual(
            fingerprint_mx_provider("mx1-us1.pphosted.com"),
            MXProvider.PROOFPOINT,
        )
        self.assertEqual(
            fingerprint_mx_provider("us-smtp-inbound-1.mimecast.com"),
            MXProvider.MIMECAST,
        )
        self.assertEqual(
            fingerprint_mx_provider("d12345.ess.barracuda.com"),
            MXProvider.BARRACODA,
        )
        self.assertEqual(
            fingerprint_mx_provider("mx.zoho.com"),
            MXProvider.ZOHO,
        )
        self.assertEqual(
            fingerprint_mx_provider("mail.protonmail.ch"),
            MXProvider.PROTON,
        )
        self.assertEqual(
            fingerprint_mx_provider("mail.proton.me"),
            MXProvider.PROTON,
        )

    def test_fingerprint_self_hosted_and_unknown(self):
        """Verifies SELF_HOSTED matches domain while unrecognized hosts return UNKNOWN."""
        self.assertEqual(
            fingerprint_mx_provider("mail.acmecorp.com", "acmecorp.com"),
            MXProvider.SELF_HOSTED,
        )
        self.assertEqual(
            fingerprint_mx_provider("smtp.sub.acmecorp.com", "acmecorp.com"),
            MXProvider.SELF_HOSTED,
        )
        self.assertEqual(
            fingerprint_mx_provider("mx.obscurehoster.net", "acmecorp.com"),
            MXProvider.UNKNOWN,
        )

    # =========================================================================
    # MX Resolution & Priority Sorting Tests
    # =========================================================================

    def test_resolve_mx_records_sorted_by_priority(self):
        """Verifies MX records are sorted ascending by preference with primary_mx identified."""
        mock_dns = {
            "example.com": [
                {"preference": 30, "exchange": "alt2.aspmx.l.google.com"},
                {"preference": 10, "exchange": "aspmx.l.google.com"},
                {"preference": 20, "exchange": "alt1.aspmx.l.google.com"},
            ]
        }
        res = resolve_domain_mx_records("example.com", mock_dns=mock_dns)
        self.assertTrue(res["valid"])
        self.assertTrue(res["can_receive_mail"])
        self.assertEqual(res["status"], "VALID_MX")
        self.assertEqual(res["primary_mx"], "aspmx.l.google.com")
        self.assertEqual(res["esp_provider"], MXProvider.GOOGLE_WORKSPACE.value)
        self.assertFalse(res["has_implicit_mx"])
        # Check sort order
        priorities = [r["priority"] for r in res["mx_records"]]
        self.assertEqual(priorities, [10, 20, 30])

    def test_resolve_mx_from_email_address_input(self):
        """Verifies input sanitization extracts domain from full email address."""
        mock_dns = {
            "acme.com": [
                {"priority": 10, "host": "acme-com.mail.protection.outlook.com"}
            ]
        }
        res = resolve_domain_mx_records("sarah.connor@acme.com", mock_dns=mock_dns)
        self.assertEqual(res["domain"], "acme.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["esp_provider"], MXProvider.MICROSOFT_365.value)

    # =========================================================================
    # RFC 7505 Null MX Tests
    # =========================================================================

    def test_rfc7505_null_mx_record_detected(self):
        """Verifies RFC 7505 Null MX (preference 0, host '.') returns valid=False and can_receive_mail=False."""
        mock_dns = {
            "nomail.org": [
                {"preference": 0, "exchange": "."}
            ]
        }
        res = resolve_domain_mx_records("nomail.org", mock_dns=mock_dns)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])
        self.assertEqual(res["status"], "NULL_MX_RFC7505")
        self.assertIn("explicitly rejects all email", res["error"])
        self.assertIsNone(res["primary_mx"])

    def test_rfc7505_null_mx_empty_host_detected(self):
        """Verifies RFC 7505 Null MX with empty string host is also caught."""
        mock_dns = {
            "rejectall.com": [(0, "")]
        }
        res = resolve_domain_mx_records("rejectall.com", mock_dns=mock_dns)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])
        self.assertEqual(res["status"], "NULL_MX_RFC7505")

    # =========================================================================
    # RFC 5321 Implicit MX Fallback Tests
    # =========================================================================

    def test_rfc5321_implicit_mx_fallback_a_record(self):
        """Verifies RFC 5321 fallback to A record when no MX records are published."""
        mock_dns = {
            "legacy-box.com": {
                "MX": [],
                "A": ["198.51.100.1"],
            }
        }
        res = resolve_domain_mx_records("legacy-box.com", mock_dns=mock_dns)
        self.assertTrue(res["valid"])
        self.assertTrue(res["can_receive_mail"])
        self.assertEqual(res["status"], "IMPLICIT_MX_RFC5321")
        self.assertTrue(res["has_implicit_mx"])
        self.assertEqual(res["primary_mx"], "legacy-box.com")
        self.assertEqual(res["mx_records"][0]["implicit"], True)

    def test_no_mail_exchanger_when_neither_mx_nor_address(self):
        """Verifies domain without MX or A/AAAA records is rejected as NO_MAIL_EXCHANGER."""
        mock_dns = {
            "dead-domain.xyz": {
                "MX": [],
                "A": [],
                "AAAA": [],
            }
        }
        res = resolve_domain_mx_records("dead-domain.xyz", mock_dns=mock_dns)
        self.assertFalse(res["valid"])
        self.assertFalse(res["can_receive_mail"])
        self.assertEqual(res["status"], "NO_MAIL_EXCHANGER")
        self.assertIsNone(res["primary_mx"])
        self.assertFalse(res["has_implicit_mx"])

    # =========================================================================
    # SSRF & Invalid Input Tests (Layer 2 Paranoia)
    # =========================================================================

    def test_invalid_domain_input(self):
        """Verifies invalid or empty domain inputs are safely handled."""
        for invalid in ["", None, "   ", "http://", "not a domain"]:
            res = resolve_domain_mx_records(invalid)
            self.assertFalse(res["valid"])
            self.assertFalse(res["can_receive_mail"])
            self.assertEqual(res["status"], "INVALID_DOMAIN")

    def test_ssrf_prohibited_domains(self):
        """Verifies private network and internal TLD targets are blocked."""
        for ssrf in ["internal.local", "db.corp", "gateway.lan"]:
            res = resolve_domain_mx_records(ssrf)
            self.assertFalse(res["valid"])
            self.assertEqual(res["status"], "PROHIBITED_SSRF_DOMAIN")

    # =========================================================================
    # Catch-All Domain Detection Tests
    # =========================================================================

    def test_detect_catch_all_free_webmail_bypasses_probe(self):
        """Verifies consumer webmail domains bypass live probe and return VERIFIED_SPECIFIC."""
        for free_email in [
            "prospect@gmail.com",
            "alex@yahoo.com",
            "founder@outlook.com",
            "john@hotmail.com",
            "user@icloud.com",
        ]:
            res = detect_catch_all_domain(free_email)
            self.assertFalse(res["is_catch_all"])
            self.assertEqual(res["catch_all_risk"], CatchAllRisk.VERIFIED_SPECIFIC.value)
            self.assertIsNone(res["canary_tested"])
            self.assertEqual(res["confidence"], 1.0)
            self.assertIn("Free webmail provider", res["recommendation"])

    def test_detect_catch_all_mocked_true(self):
        """Verifies corporate domain with mock_is_catch_all=True returns CATCH_ALL_ACCEPT_ALL."""
        res = detect_catch_all_domain("acme-sales.com", mock_is_catch_all=True)
        self.assertTrue(res["is_catch_all"])
        self.assertEqual(res["catch_all_risk"], CatchAllRisk.CATCH_ALL_ACCEPT_ALL.value)
        self.assertTrue(res["canary_tested"].startswith("elein_canary_"))
        self.assertTrue(res["canary_tested"].endswith("@acme-sales.com"))
        self.assertEqual(res["confidence"], 0.95)

    def test_detect_catch_all_mocked_false(self):
        """Verifies corporate domain with mock_is_catch_all=False returns VERIFIED_SPECIFIC."""
        res = detect_catch_all_domain("enterprise.co", mock_is_catch_all=False)
        self.assertFalse(res["is_catch_all"])
        self.assertEqual(res["catch_all_risk"], CatchAllRisk.VERIFIED_SPECIFIC.value)
        self.assertTrue(res["canary_tested"].startswith("elein_canary_"))
        self.assertEqual(res["confidence"], 0.95)

    def test_detect_catch_all_unprobed_on_network_failure(self):
        """Verifies live probe safely falls back to UNKNOWN_UNPROBED when port 25 is unreachable."""
        res = detect_catch_all_domain("test-corp.com", mock_is_catch_all=None, timeout=0.01)
        self.assertFalse(res["is_catch_all"])
        self.assertEqual(res["catch_all_risk"], CatchAllRisk.UNKNOWN_UNPROBED.value)

    # =========================================================================
    # SMTP Deferral & Greylisting Detection Tests
    # =========================================================================

    def test_detect_smtp_deferral_greylisted(self):
        """Verifies 451 greylisting message triggers defer_and_retry with extracted delay."""
        msg = "451 4.7.1 Greylisted, please try again in 300 seconds"
        res = detect_smtp_deferral_or_greylist(451, msg, attempt_count=1)
        self.assertTrue(res["is_deferred"])
        self.assertTrue(res["is_greylisted"])
        self.assertTrue(res["retry_recommended"])
        self.assertEqual(res["retry_delay_seconds"], 300)
        self.assertEqual(res["action"], "defer_and_retry")

    def test_detect_smtp_deferral_rate_limit(self):
        """Verifies 421 rate limit message triggers defer_and_retry with extracted delay."""
        msg = "421 4.7.0 Rate limit exceeded for your IP, please retry after 120s"
        res = detect_smtp_deferral_or_greylist(421, msg, attempt_count=1)
        self.assertTrue(res["is_deferred"])
        self.assertTrue(res["is_greylisted"])
        self.assertEqual(res["retry_delay_seconds"], 120)
        self.assertEqual(res["action"], "defer_and_retry")

    def test_detect_smtp_deferral_in_minutes(self):
        """Verifies wait time specified in minutes is correctly converted to seconds."""
        msg = "450 4.2.1 Mailbox temporarily deferred, try again in 5 minutes"
        res = detect_smtp_deferral_or_greylist(450, msg, attempt_count=1)
        self.assertTrue(res["is_deferred"])
        self.assertTrue(res["is_greylisted"])
        self.assertEqual(res["retry_delay_seconds"], 300)

    def test_detect_smtp_permanent_failure(self):
        """Verifies 5xx errors return fail_permanent with retry_recommended=False."""
        msg = "550 5.1.1 User unknown or mailbox does not exist"
        res = detect_smtp_deferral_or_greylist(550, msg)
        self.assertFalse(res["is_deferred"])
        self.assertFalse(res["is_greylisted"])
        self.assertFalse(res["retry_recommended"])
        self.assertEqual(res["retry_delay_seconds"], 0)
        self.assertEqual(res["action"], "fail_permanent")

    # =========================================================================
    # Exponential Backoff & Retry Delay Tests
    # =========================================================================

    def test_calculate_greylist_retry_delay_exponential(self):
        """Verifies exponential backoff progression clamped to [300, 3600]."""
        self.assertEqual(calculate_greylist_retry_delay(1), 300)
        self.assertEqual(calculate_greylist_retry_delay(2), 600)
        self.assertEqual(calculate_greylist_retry_delay(3), 1200)
        self.assertEqual(calculate_greylist_retry_delay(4), 2400)
        self.assertEqual(calculate_greylist_retry_delay(5), 3600)
        self.assertEqual(calculate_greylist_retry_delay(10), 3600)

    def test_calculate_greylist_retry_delay_suggested_clamping(self):
        """Verifies suggested seconds are clamped between 60 and 3600."""
        self.assertEqual(calculate_greylist_retry_delay(1, suggested_seconds=30), 60)
        self.assertEqual(calculate_greylist_retry_delay(1, suggested_seconds=500), 500)
        self.assertEqual(calculate_greylist_retry_delay(1, suggested_seconds=7200), 3600)

    # =========================================================================
    # Facade Class Tests
    # =========================================================================

    def test_facade_static_methods(self):
        """Verifies MXAndCatchAllGuard facade class delegates properly."""
        mock_dns = {"test.com": [{"priority": 10, "host": "aspmx.l.google.com"}]}
        res_mx = MXAndCatchAllGuard.resolve_domain_mx_records("test.com", mock_dns=mock_dns)
        self.assertTrue(res_mx["valid"])

        res_ca = MXAndCatchAllGuard.detect_catch_all_domain("test.com", mock_is_catch_all=False)
        self.assertFalse(res_ca["is_catch_all"])

        res_def = MXAndCatchAllGuard.detect_smtp_deferral_or_greylist(451, "Greylisted")
        self.assertTrue(res_def["is_deferred"])

        delay = MXAndCatchAllGuard.calculate_greylist_retry_delay(2)
        self.assertEqual(delay, 600)

    # =========================================================================
    # Additional Paranoia & Edge Case Tests
    # =========================================================================

    def test_mx_resolution_for_all_esp_providers(self):
        """Verifies resolve_domain_mx_records correctly fingerprints all known ESP providers."""
        provider_mocks = [
            ("google.com", "aspmx.l.google.com", MXProvider.GOOGLE_WORKSPACE.value),
            ("office.com", "outlook-com.mail.protection.outlook.com", MXProvider.MICROSOFT_365.value),
            ("secure-corp.com", "mx1-us1.pphosted.com", MXProvider.PROOFPOINT.value),
            ("corp-gateway.com", "us-smtp-inbound-1.mimecast.com", MXProvider.MIMECAST.value),
            ("barracuda-protected.com", "d1234.ess.barracuda.com", MXProvider.BARRACODA.value),
            ("zoho-mail.com", "mx.zoho.com", MXProvider.ZOHO.value),
            ("proton-privacy.com", "mail.protonmail.ch", MXProvider.PROTON.value),
            ("my-own-server.com", "mail.my-own-server.com", MXProvider.SELF_HOSTED.value),
            ("custom-linux.net", "mx.unrecognized-relay.org", MXProvider.UNKNOWN.value),
        ]
        for domain, mx_host, expected_provider in provider_mocks:
            mock_dns = {domain: [{"priority": 10, "host": mx_host}]}
            res = resolve_domain_mx_records(domain, mock_dns=mock_dns)
            self.assertTrue(res["valid"], f"Failed for {domain}")
            self.assertEqual(res["esp_provider"], expected_provider, f"Failed for {domain}")

    def test_smtp_deferral_malformed_code_and_messages(self):
        """Verifies malformed status codes and edge-case error strings fail safely."""
        # Non-integer string code
        res1 = detect_smtp_deferral_or_greylist("invalid", "error")
        self.assertFalse(res1["is_deferred"])
        self.assertEqual(res1["action"], "fail_permanent")

        # None code
        res2 = detect_smtp_deferral_or_greylist(None, None)
        self.assertFalse(res2["is_deferred"])
        self.assertEqual(res2["action"], "fail_permanent")

        # 421 without message
        res3 = detect_smtp_deferral_or_greylist(421, "")
        self.assertTrue(res3["is_deferred"])
        self.assertFalse(res3["is_greylisted"])
        self.assertEqual(res3["retry_delay_seconds"], 300)

        # 452 with too many connections pattern
        res4 = detect_smtp_deferral_or_greylist(452, "452 4.3.2 Too many connections, please try again later")
        self.assertTrue(res4["is_deferred"])
        self.assertTrue(res4["is_greylisted"])

    def test_calculate_greylist_retry_delay_with_jitter(self):
        """Verifies jitter stays within [base_delay, base_delay + 30] and <= 3600."""
        delay1 = calculate_greylist_retry_delay(1, jitter=True)
        self.assertTrue(300 <= delay1 <= 330)

        delay_max = calculate_greylist_retry_delay(10, jitter=True)
        self.assertEqual(delay_max, 3600)  # Clamped at 3600

    def test_catch_all_in_memory_caching(self):
        """Verifies catch-all results are stored and returned from in-memory cache."""
        clear_catch_all_cache()
        # Seed cache manually or via mock
        res1 = detect_catch_all_domain("cached-domain.com", mock_is_catch_all=True)
        self.assertTrue(res1["is_catch_all"])

        # Subsequent call with mock_is_catch_all=None should read from cache instead of failing
        from core.backend.services.mx_and_catchall_guard import _CATCH_ALL_CACHE
        from datetime import datetime, timezone
        _CATCH_ALL_CACHE["cached-domain.com"] = (datetime.now(timezone.utc), res1)

        res2 = detect_catch_all_domain("cached-domain.com", mock_is_catch_all=None)
        self.assertTrue(res2["is_catch_all"])
        self.assertEqual(res2["catch_all_risk"], CatchAllRisk.CATCH_ALL_ACCEPT_ALL.value)



if __name__ == "__main__":
    unittest.main()
