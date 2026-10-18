"""
test_custom_tracking_cname_and_ssl_guard.py — Paranoia Test Automation Suite for Issue 6
(Custom Domain Tracking CNAME & Automated SSL Verification Guard).

Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - Valid CNAME and SSL handshake verification success.
    - Tracking link rewriting replaces URLs with signed/formatted track URLs.
    - Sentence trailing punctuation preservation (., !, ?, ;, ", ,).
    - Prevention of double-wrapping already tracked links.
    - Accurate certificate expiration and days_until_expiry calculation.
    - Subject Alternative Name (SAN), Common Name (CN), and Issuer extraction.
    - CNAME-only validation when check_live_ssl=False.
    - Integrated verify_domain_dns_health tracking domain verification.

  - Layer 1: Environmental Failure Analysis
    - CNAME valid but SSL pending provisioning fails safe (can_track_safely=False).
    - SSL pending bypasses link rewriting completely so recipients never hit red SSL warnings.
    - Expired SSL certificate detection and status="CERTIFICATE_EXPIRED".
    - CNAME pointing to wrong target or missing fails closed with CNAME_MISSING_OR_MISMATCH.
    - Socket timeout on TLS handshake handled gracefully without unhandled exception.
    - Port 443 connection refused handled cleanly with CONNECTION_REFUSED.
    - EleInExecutor.handle_send_email leaves links intact and emits ssl_tracking_bypassed=True.
    - EleInExecutor.handle_send_email with verified SSL rewrites links and records metrics.
    - TLS hostname verification failure (SSLCertVerificationError).
    - DNS resolution failure (socket.gaierror) during handshake.
    - SSL general handshake error (SSLError).
    - Inbox fallback tracking domain unverified SSL bypass in executor.

  - Layer 2: Human Paranoia & Security Defense
    - SSRF prevention: localhost, 127.0.0.1, 169.254.169.254, 10.0.0.1, ::1 blocked before socket.
    - SSRF prevention: internal TLDs (.local, .internal, .localhost, .lan, .arpa).
    - Malformed domain inputs (None, "", "://", "track..domain.com", protocol/path/query injection).
    - Cross-tenant IDOR defense in router endpoints (workspace scoping).
    - POST /deliverability/verify-tracking-domain verifies and updates matching sender inboxes.
    - POST /deliverability/verify-tracking-domain unverified SSL does not update sender inboxes.
    - GET /deliverability/tracking-domain-status cached inbox hit.
    - GET /deliverability/tracking-domain-status live check fallback.
    - Exclusion of non-HTTP schemes (mailto:, tel:) from link rewriting.
    - Fail-safe handling for None/empty email body.
"""

import socket
import ssl
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from core.backend.services.deliverability_guard import (
    sanitize_domain_input,
    verify_custom_tracking_domain,
    verify_domain_dns_health,
    verify_ssl_handshake,
    rewrite_tracking_links,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import (
    VerifyTrackingDomainRequest,
    verify_tracking_domain_endpoint,
    get_tracking_domain_status_endpoint,
)


class TestCustomTrackingCnameAndSslGuard(unittest.TestCase):
    """
    Automated test suite implementing the Paranoia Framework for Custom Tracking CNAME
    and Automated SSL Verification Guard.
    """

    def setUp(self):
        self.workspace_id = "ws_issue6_test"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER (CORE MECHANICS)
    # =========================================================================

    def test_valid_cname_and_valid_ssl_verifies_successfully(self):
        """Layer 0: Both CNAME and SSL handshake succeed -> returns can_track_safely=True, status='VERIFIED_ACTIVE'."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=True,
            mock_cname="track.elein.ai",
            mock_ssl_valid=True,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "VERIFIED_ACTIVE")
        self.assertEqual(res["cname_target"], "track.elein.ai")
        self.assertTrue(res["ssl_verified"])
        self.assertTrue(res["can_track_safely"])
        self.assertIn("ssl_details", res)
        self.assertEqual(res["ssl_details"]["status"], "ACTIVE_VALID")

    def test_rewrite_tracking_links_replaces_urls(self):
        """Layer 0: Plain URLs (https://acme.com/demo) in body become https://track.acme.com/t/c/..."""
        body = "Hi there, please review our demo at https://acme.com/demo and let us know!"
        res = rewrite_tracking_links(
            body=body,
            tracking_domain="track.acme.com",
            email_id="em_abc123",
            workspace_id=self.workspace_id,
            ssl_verified=True,
        )
        self.assertTrue(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 1)
        self.assertEqual(res["tracking_domain"], "track.acme.com")
        self.assertIn("https://track.acme.com/t/c/em_abc123?u=https%3A%2F%2Facme.com%2Fdemo&w=ws_issue6_test", res["body"])
        self.assertNotIn("https://acme.com/demo ", res["body"])

    def test_rewrite_tracking_links_preserves_trailing_punctuation(self):
        """Layer 0: https://acme.com. at end of sentence leaves trailing . outside the query parameter."""
        test_cases = [
            ("Visit https://acme.com.", "."),
            ("Check https://acme.com/pricing,", ","),
            ("Is this valid https://acme.com/faq?", "?"),
            ("Special offer https://acme.com/offer!", "!"),
            ('Read "https://acme.com/post"', '"'),
            ("Review https://acme.com/terms;", ";"),
        ]
        for body, punct in test_cases:
            res = rewrite_tracking_links(
                body=body,
                tracking_domain="track.acme.com",
                email_id="em_test",
                workspace_id=self.workspace_id,
                ssl_verified=True,
            )
            self.assertTrue(res["tracking_applied"], f"Failed for punct: {punct}")
            self.assertTrue(res["body"].endswith(punct), f"Body does not end with {punct}: {res['body']}")
            # Trailing punctuation must not be inside target URL param u
            self.assertIn("u=https%3A%2F%2Facme.com", res["body"])
            self.assertNotIn("acme.com" + punct + "&", res["body"])
            self.assertNotIn("acme.com%2E", res["body"])

    def test_rewrite_tracking_links_skips_already_tracked_links(self):
        """Layer 0: Links already pointing to track.acme.com or containing /t/c/ are not double-wrapped."""
        already_tracked = f"https://track.acme.com/t/c/em_prior?u=https%3A%2F%2Facme.com&w={self.workspace_id}"
        body = f"Already tracked: {already_tracked} and check another: {already_tracked}"
        res = rewrite_tracking_links(
            body=body,
            tracking_domain="track.acme.com",
            email_id="em_new",
            workspace_id=self.workspace_id,
            ssl_verified=True,
        )
        self.assertFalse(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 0)
        self.assertEqual(res["body"], body)

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_ssl_expiry_calculation_and_days_remaining(self, mock_connect, mock_ssl_ctx):
        """Layer 0: Verifies days_until_expiry is accurately computed from certificate notAfter."""
        future_dt = datetime.now(timezone.utc) + timedelta(days=60)
        not_after_str = future_dt.strftime("%b %d %H:%M:%S %Y GMT")

        fake_cert = {
            "subject": ((("commonName", "track.acme.com"),),),
            "issuer": ((("organizationName", "Let's Encrypt"),),),
            "subjectAltName": [("DNS", "track.acme.com"), ("DNS", "acme.com")],
            "notAfter": not_after_str,
        }

        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = fake_cert
        mock_connect.return_value.__enter__.return_value = mock_sock
        mock_ssl_ctx.return_value.wrap_socket.return_value.__enter__.return_value = mock_ssock

        res = verify_ssl_handshake("track.acme.com", timeout=2.0)
        self.assertTrue(res["ssl_valid"])
        self.assertEqual(res["status"], "ACTIVE_VALID")
        self.assertEqual(res["hostname"], "track.acme.com")
        self.assertTrue(58 <= res["days_until_expiry"] <= 61)
        self.assertIn("track.acme.com", res["san_list"])
        self.assertIn("acme.com", res["san_list"])

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_verify_ssl_handshake_extracts_san_and_issuer(self, mock_connect, mock_ssl_ctx):
        """Layer 0: Verifies SAN list, Common Name, and Issuer are properly parsed from certificate."""
        fake_cert = {
            "subject": ((("commonName", "track.mybrand.io"),),),
            "issuer": ((("organizationName", "DigiCert Global Root CA"),),),
            "subjectAltName": [("DNS", "track.mybrand.io"), ("DNS", "*.mybrand.io")],
            "notAfter": (datetime.now(timezone.utc) + timedelta(days=120)).strftime("%b %d %H:%M:%S %Y GMT"),
        }
        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = fake_cert
        mock_connect.return_value.__enter__.return_value = mock_sock
        mock_ssl_ctx.return_value.wrap_socket.return_value.__enter__.return_value = mock_ssock

        res = verify_ssl_handshake("track.mybrand.io")
        self.assertTrue(res["ssl_valid"])
        self.assertEqual(res["subject"], "track.mybrand.io")
        self.assertEqual(res["san_list"], ["track.mybrand.io", "*.mybrand.io"])
        self.assertEqual(res["issuer"], ((("organizationName", "DigiCert Global Root CA"),),))

    def test_verify_custom_tracking_domain_cname_only_check(self):
        """Layer 0: When check_live_ssl=False, verifies CNAME and returns status='CNAME_ONLY' without TLS handshake."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=False,
            mock_cname="track.elein.ai",
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "CNAME_ONLY")
        self.assertFalse(res["ssl_verified"])
        self.assertFalse(res["can_track_safely"])
        self.assertEqual(res["cname_target"], "track.elein.ai")

    def test_rewrite_tracking_links_multiple_unique_urls(self):
        """Layer 0: Multiple unique URLs in the body are each rewritten accurately."""
        body = "Check our site at https://acme.com/home and blog at https://blog.acme.com/post-1."
        res = rewrite_tracking_links(
            body=body,
            tracking_domain="track.acme.com",
            email_id="em_multi",
            workspace_id=self.workspace_id,
            ssl_verified=True,
        )
        self.assertTrue(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 2)
        self.assertIn("https://track.acme.com/t/c/em_multi?u=https%3A%2F%2Facme.com%2Fhome&w=ws_issue6_test", res["body"])
        self.assertIn("https://track.acme.com/t/c/em_multi?u=https%3A%2F%2Fblog.acme.com%2Fpost-1&w=ws_issue6_test", res["body"])

    @patch("core.backend.services.deliverability_guard._lookup_cname_record")
    @patch("core.backend.services.deliverability_guard._lookup_txt_records")
    def test_verify_domain_dns_health_integration_with_tracking_domain(self, mock_txt, mock_cname):
        """Layer 0: Integrated DNS health check passes mock_ssl_valid through to tracking domain evaluation."""
        mock_txt.side_effect = lambda qname, timeout=2.5: {
            "acme.com": ["v=spf1 include:_spf.google.com ~all"],
            "elein._domainkey.acme.com": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA123"],
            "_dmarc.acme.com": ["v=DMARC1; p=quarantine"],
        }.get(qname, [])
        mock_cname.return_value = "track.elein.ai"

        res = verify_domain_dns_health(
            domain="acme.com",
            tracking_subdomain="track",
            expected_cname_target="track.elein.ai",
            dkim_selector="elein",
            mock_records={"cname": "track.elein.ai", "ssl_valid": True},
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["health_status"], "HEALTHY")
        self.assertEqual(res["deliverability_score"], 100)
        self.assertTrue(res["ssl_tracking_ready"])
        self.assertEqual(res["records"]["tracking_cname"]["status"], "VERIFIED_ACTIVE")
        self.assertTrue(res["records"]["tracking_cname"]["can_track_safely"])

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # =========================================================================

    def test_cname_valid_but_ssl_pending_provisioning_fails_safe(self):
        """Layer 1: CNAME matches track.elein.ai, but TLS handshake fails -> returns can_track_safely=False, status='SSL_PENDING_PROVISIONING'."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=True,
            mock_cname="track.elein.ai",
            mock_ssl_valid=False,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "SSL_PENDING_PROVISIONING")
        self.assertFalse(res["ssl_verified"])
        self.assertFalse(res["can_track_safely"])
        self.assertEqual(res["cname_target"], "track.elein.ai")
        self.assertIn("action_required", res)
        self.assertIn("SSL certificate is still provisioning", res["action_required"])

    def test_ssl_pending_bypasses_link_rewriting_completely(self):
        """Layer 1: When ssl_verified=False, rewrite_tracking_links returns original body 100% untouched."""
        raw_body = "Hi there, see our live pricing at https://acme.com/pricing and case studies at https://acme.com/cases."
        res = rewrite_tracking_links(
            body=raw_body,
            tracking_domain="track.acme.com",
            email_id="em_pending_ssl",
            workspace_id=self.workspace_id,
            ssl_verified=False,
        )
        self.assertFalse(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 0)
        self.assertEqual(res["body"], raw_body)
        self.assertEqual(res["fallback_reason"], "SSL_UNVERIFIED_PREVENTED_BROWSER_WARNING")

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_expired_ssl_certificate_detected(self, mock_connect, mock_ssl_ctx):
        """Layer 1: Expired certificate returns status='CERTIFICATE_EXPIRED', can_track_safely=False."""
        past_dt = datetime.now(timezone.utc) - timedelta(days=10)
        not_after_str = past_dt.strftime("%b %d %H:%M:%S %Y GMT")

        fake_cert = {
            "subject": ((("commonName", "track.acme.com"),),),
            "issuer": ((("organizationName", "ZeroSSL"),),),
            "subjectAltName": [("DNS", "track.acme.com")],
            "notAfter": not_after_str,
        }
        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = fake_cert
        mock_connect.return_value.__enter__.return_value = mock_sock
        mock_ssl_ctx.return_value.wrap_socket.return_value.__enter__.return_value = mock_ssock

        res = verify_ssl_handshake("track.acme.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "CERTIFICATE_EXPIRED")
        self.assertTrue(res["days_until_expiry"] <= 0)
        self.assertIn("Certificate expired", res["error"])

    def test_cname_mismatch_fails_closed(self):
        """Layer 1: CNAME pointing to wrong target (e.g. other-service.com) fails with CNAME_MISSING_OR_MISMATCH."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            mock_cname="other-tracker.thirdparty.com",
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "CNAME_MISSING_OR_MISMATCH")
        self.assertEqual(res["cname_target"], "other-tracker.thirdparty.com")
        self.assertFalse(res["ssl_verified"])
        self.assertFalse(res["can_track_safely"])

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_tls_handshake_socket_timeout_resilience(self, mock_connect, mock_ssl_ctx):
        """Layer 1: Socket connection timeout on port 443 returns clean CONNECTION_TIMEOUT without unhandled exception."""
        mock_connect.side_effect = socket.timeout("Operation timed out")

        res = verify_ssl_handshake("track.slow-server.com", timeout=1.0)
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "CONNECTION_TIMEOUT")
        self.assertEqual(res["error"], "Connection timed out")
        self.assertEqual(res["hostname"], "track.slow-server.com")

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_connection_refused_port_443(self, mock_connect, mock_ssl_ctx):
        """Layer 1: Target with port 443 closed returns CONNECTION_REFUSED without crash."""
        mock_connect.side_effect = ConnectionRefusedError(61, "Connection refused")

        res = verify_ssl_handshake("track.noport443.com", timeout=1.0)
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "CONNECTION_REFUSED")
        self.assertEqual(res["error"], "Port 443 refused")
        self.assertEqual(res["hostname"], "track.noport443.com")

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_ssl_cert_verification_error_hostname_mismatch(self, mock_connect, mock_ssl_ctx):
        """Layer 1: Hostname mismatch or untrusted CA triggers SSL_CERT_VERIFICATION_FAILED."""
        mock_ssl_ctx.return_value.wrap_socket.side_effect = ssl.SSLCertVerificationError(
            "Hostname mismatch: certificate is for 'other.domain.com'"
        )

        res = verify_ssl_handshake("track.acme.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "SSL_CERT_VERIFICATION_FAILED")
        self.assertIn("Hostname mismatch", res["error"])

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_tls_dns_resolution_failure_gaierror(self, mock_connect, mock_ssl_ctx):
        """Layer 1: DNS failure to resolve tracking host returns SSL_CHECK_FAILED cleanly."""
        mock_connect.side_effect = socket.gaierror(-2, "Name or service not known")

        res = verify_ssl_handshake("track.nonexistent-nxdomain-target.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "SSL_CHECK_FAILED")
        self.assertIn("Name or service not known", res["error"])

    @patch("ssl.create_default_context")
    @patch("socket.create_connection")
    def test_ssl_general_sslerror_handled_gracefully(self, mock_connect, mock_ssl_ctx):
        """Layer 1: General SSL protocol failure returns SSL_HANDSHAKE_ERROR cleanly."""
        mock_ssl_ctx.return_value.wrap_socket.side_effect = ssl.SSLError(
            "TLS record version mismatch or invalid MAC"
        )

        res = verify_ssl_handshake("track.broken-tls.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "SSL_HANDSHAKE_ERROR")
        self.assertIn("TLS record version mismatch", res["error"])

    @patch("core.backend.services.deliverability_guard._lookup_cname_record")
    def test_cname_lookup_exception_fails_closed(self, mock_cname):
        """Layer 1: When DNS lookup fails with exception or returns None, verify_custom_tracking_domain fails closed."""
        mock_cname.return_value = None

        res = verify_custom_tracking_domain("track.missing-dns.com")
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "CNAME_MISSING_OR_MISMATCH")
        self.assertIsNone(res["cname_target"])
        self.assertFalse(res["ssl_verified"])
        self.assertFalse(res["can_track_safely"])

    def test_executor_handle_send_email_ssl_bypass_telemetry(self):
        """Layer 1: When SSL is unverified, handle_send_email leaves links intact and emits ssl_tracking_bypassed=True."""
        raw_body = "Schedule time here: https://acme.com/cal-link for a quick sync."
        data = {
            "to_email": "lead@target.com",
            "subject": "Quick demo",
            "body": raw_body,
            "tracking_domain": "track.acme.com",
            "ssl_verified": False,
            "lead_id": "lead_ssl_bypass",
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res["body"], raw_body)
        self.assertEqual(res["tracking_rewritten"], 0)
        self.assertTrue(res.get("ssl_tracking_bypassed"))

    def test_executor_handle_send_email_with_verified_ssl_rewrites_links(self):
        """Layer 1: When SSL is verified, handle_send_email rewrites links and records tracking_rewritten > 0."""
        raw_body = "Schedule time here: https://acme.com/cal-link for a quick sync."
        data = {
            "to_email": "lead@target.com",
            "subject": "Quick demo",
            "body": raw_body,
            "tracking_domain": "track.acme.com",
            "ssl_verified": True,
            "lead_id": "lead_ssl_verified",
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tracking_rewritten"], 1)
        self.assertIn("https://track.acme.com/t/c/", res["body"])
        self.assertFalse(res.get("ssl_tracking_bypassed", False))

    @patch("integrations.backend.services.email_sender_service.select_rotating_sender_inbox")
    def test_executor_inbox_fallback_tracking_domain_unverified_ssl(self, mock_select_inbox):
        """Layer 1: When node has no tracking domain, but selected inbox has unverified tracking domain, executor bypasses rewrite."""
        mock_select_inbox.return_value = {
            "selected": {
                "id": "inb_fallback_ssl",
                "email": "sender@brand.com",
                "tracking_domain": "track.brand.com",
                "ssl_verified": False,
                "domain_burnout_status": "HEALTHY",
            },
            "strategy_applied": "HEALTH_WEIGHTED",
            "selection_reason": "HEALTHY_SELECTION",
            "pool_summary": {},
        }
        raw_body = "Check our deck at https://brand.com/pitch.pdf now."
        data = {
            "to_email": "prospect@investor.com",
            "subject": "Intro Deck",
            "body": raw_body,
            "use_sender_pool": True,
            "lead_id": "lead_inbox_fallback",
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tracking_rewritten"], 0)
        self.assertEqual(res["body"], raw_body)
        self.assertTrue(res.get("ssl_tracking_bypassed"))

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & SECURITY DEFENSE
    # =========================================================================

    def test_ssrf_internal_ip_and_localhost_blocked(self):
        """Layer 2: Probing localhost, 127.0.0.1, 169.254.169.254, 10.0.0.1 immediately rejected without opening socket."""
        dangerous_hosts = [
            "localhost",
            "127.0.0.1",
            "169.254.169.254",
            "10.0.0.1",
            "192.168.1.1",
            "0.0.0.0",
            "::1",
        ]
        with patch("socket.create_connection") as mock_connect:
            for host in dangerous_hosts:
                # Test in verify_ssl_handshake
                ssl_res = verify_ssl_handshake(host)
                self.assertFalse(ssl_res["ssl_valid"], f"Host {host} was not blocked in verify_ssl_handshake")
                self.assertEqual(ssl_res["status"], "FORBIDDEN_OR_INVALID_HOST")

                # Test in verify_custom_tracking_domain
                cname_res = verify_custom_tracking_domain(host)
                self.assertFalse(cname_res["valid"], f"Host {host} was not blocked in verify_custom_tracking_domain")
                self.assertEqual(cname_res["status"], "CNAME_MISSING_OR_MISMATCH")

            # Socket connection must NEVER have been called for dangerous targets
            mock_connect.assert_not_called()

    def test_ssrf_internal_tlds_blocked(self):
        """Layer 2: Domains ending with .local, .internal, .localhost, .lan, .arpa rejected immediately."""
        internal_hosts = [
            "metadata.internal",
            "service.local",
            "kubernetes.default.svc.cluster.local",
            "router.lan",
            "host.localhost",
            "1.0.0.127.in-addr.arpa",
        ]
        with patch("socket.create_connection") as mock_connect:
            for host in internal_hosts:
                clean = sanitize_domain_input(host)
                self.assertIsNone(clean, f"Internal host {host} was not sanitized to None")

                res = verify_ssl_handshake(host)
                self.assertFalse(res["ssl_valid"])
                self.assertEqual(res["status"], "FORBIDDEN_OR_INVALID_HOST")

            mock_connect.assert_not_called()

    def test_malformed_tracking_domain_inputs(self):
        """Layer 2: Handles None, '', '://', 'track..domain.com' safely without uncaught exceptions."""
        malformed_inputs = [
            None,
            "",
            "   ",
            "://",
            "http://",
            "track..acme.com",
            "-track.acme.com",
            "track.acme.com-",
            "http://track.acme.com/path?query=1#frag",
            "track.acme.com:443",
            "sales@track.acme.com",
            "www.track.acme.com",
        ]
        for val in malformed_inputs:
            # None / invalid should never throw
            clean = sanitize_domain_input(val)
            if val in (None, "", "   ", "://", "http://", "track..acme.com", "-track.acme.com", "track.acme.com-"):
                self.assertIsNone(clean, f"Expected None for {val}, got {clean}")
            elif val in ("http://track.acme.com/path?query=1#frag", "track.acme.com:443", "sales@track.acme.com", "www.track.acme.com"):
                self.assertEqual(clean, "track.acme.com")

            # verify_ssl_handshake with bad inputs returns clean error dict
            ssl_res = verify_ssl_handshake(val)
            self.assertIsInstance(ssl_res, dict)
            if not clean:
                self.assertFalse(ssl_res["ssl_valid"])
                self.assertEqual(ssl_res["status"], "FORBIDDEN_OR_INVALID_HOST")

    def test_cross_tenant_idor_tracking_domain_endpoint(self):
        """Layer 2: Router endpoint verifies workspace ownership and scopes inbox queries strictly to caller's workspace."""
        req = VerifyTrackingDomainRequest(
            tracking_domain="track.acme.com",
            expected_cname="track.elein.ai",
            check_live_ssl=False,
        )

        inbox_query_mock = MagicMock()
        inbox_query_mock.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "inb_1", "email": "founder@acme.com", "sender_domain": "acme.com"}
        ]
        self.mock_supabase.table.return_value = inbox_query_mock

        with patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "status": "VERIFIED_ACTIVE",
                "cname_target": "track.elein.ai",
                "ssl_verified": True,
                "can_track_safely": True,
                "ssl_details": {"ssl_valid": True},
            }

            res = verify_tracking_domain_endpoint(
                req=req,
                workspace_id="ws_tenant_1",
                supabase=self.mock_supabase,
            )

            self.assertTrue(res["valid"])
            self.assertEqual(res["tracking_domain"], "track.acme.com")
            # Verify database query is strictly scoped to ws_tenant_1
            self.mock_supabase.table.assert_any_call("email_sender_inboxes")
            inbox_query_mock.select.return_value.eq.assert_called_with("workspace_id", "ws_tenant_1")

    def test_tracking_endpoint_verifies_and_updates_inboxes(self):
        """Layer 2: POST /api/elein/deliverability/verify-tracking-domain returns structured audit and updates matching sender inboxes."""
        req = VerifyTrackingDomainRequest(
            tracking_domain="track.acme.com",
            expected_cname="track.elein.ai",
            check_live_ssl=True,
        )

        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "inb_match", "email": "sales@acme.com", "sender_domain": "acme.com", "tracking_domain": None},
            {"id": "inb_nomatch", "email": "other@differentcorp.org", "sender_domain": "differentcorp.org", "tracking_domain": None},
        ]
        self.mock_supabase.table.return_value = table_mock

        with patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "status": "VERIFIED_ACTIVE",
                "cname_target": "track.elein.ai",
                "ssl_verified": True,
                "can_track_safely": True,
                "ssl_details": {"ssl_valid": True, "status": "ACTIVE_VALID", "days_until_expiry": 85},
            }

            res = verify_tracking_domain_endpoint(
                req=req,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase,
            )

            self.assertTrue(res["valid"])
            self.assertEqual(res["status"], "VERIFIED_ACTIVE")
            self.assertTrue(res["ssl_verified"])
            self.assertTrue(res["can_track_safely"])
            self.assertEqual(res["inboxes_updated"], 1)

            # Update must only be called for matching inbox
            table_mock.update.assert_called_once_with({"tracking_domain": "track.acme.com", "ssl_verified": True})

    def test_tracking_endpoint_unverified_ssl_does_not_update_inboxes(self):
        """Layer 2: If SSL is still provisioning, endpoint does NOT update inboxes to prevent breaking outgoing mail."""
        req = VerifyTrackingDomainRequest(
            tracking_domain="track.acme.com",
            check_live_ssl=True,
        )
        table_mock = MagicMock()
        self.mock_supabase.table.return_value = table_mock

        with patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain") as mock_verify:
            mock_verify.return_value = {
                "valid": False,
                "status": "SSL_PENDING_PROVISIONING",
                "cname_target": "track.elein.ai",
                "ssl_verified": False,
                "can_track_safely": False,
                "ssl_error": "Connection timed out",
            }

            res = verify_tracking_domain_endpoint(
                req=req,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase,
            )

            self.assertFalse(res["valid"])
            self.assertEqual(res["status"], "SSL_PENDING_PROVISIONING")
            self.assertFalse(res["ssl_verified"])
            self.assertEqual(res["inboxes_updated"], 0)
            table_mock.update.assert_not_called()

    def test_get_tracking_domain_status_endpoint_cached_hit(self):
        """Layer 2: GET /deliverability/tracking-domain-status returns cached inbox status when available."""
        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "id": "inb_cached",
                "email": "sarah@acme.com",
                "sender_domain": "acme.com",
                "tracking_domain": "track.acme.com",
                "ssl_verified": True,
            }
        ]
        self.mock_supabase.table.return_value = table_mock

        res = get_tracking_domain_status_endpoint(
            domain="acme.com",
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )
        self.assertTrue(res["cached"])
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "VERIFIED_ACTIVE")
        self.assertTrue(res["can_track_safely"])
        self.assertEqual(res["tracking_domain"], "track.acme.com")

    def test_get_tracking_domain_status_endpoint_live_check_fallback(self):
        """Layer 2: GET /deliverability/tracking-domain-status performs live check when domain is not cached in inboxes."""
        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.execute.return_value.data = []
        self.mock_supabase.table.return_value = table_mock

        with patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain") as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "status": "VERIFIED_ACTIVE",
                "cname_target": "track.elein.ai",
                "ssl_verified": True,
                "can_track_safely": True,
                "ssl_details": {"days_until_expiry": 75},
            }

            res = get_tracking_domain_status_endpoint(
                domain="track.newdomain.io",
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase,
            )
            self.assertFalse(res["cached"])
            self.assertTrue(res["valid"])
            self.assertEqual(res["status"], "VERIFIED_ACTIVE")
            self.assertTrue(res["can_track_safely"])
            mock_verify.assert_called()

    def test_rewrite_tracking_links_does_not_alter_mailto_or_tel(self):
        """Layer 2: mailto: and tel: links are strictly ignored and never rewritten to HTTP tracking links."""
        body = "Email us at mailto:support@acme.com or call tel:+18005550199 for help."
        res = rewrite_tracking_links(
            body=body,
            tracking_domain="track.acme.com",
            email_id="em_schemes",
            workspace_id=self.workspace_id,
            ssl_verified=True,
        )
        self.assertFalse(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 0)
        self.assertEqual(res["body"], body)

    def test_rewrite_tracking_links_empty_or_none_body(self):
        """Layer 2: Empty or None email bodies return empty/untouched dict without raising exceptions."""
        for empty_val in [None, "", "   "]:
            res = rewrite_tracking_links(
                body=empty_val,
                tracking_domain="track.acme.com",
                email_id="em_empty",
                workspace_id=self.workspace_id,
                ssl_verified=True,
            )
            self.assertFalse(res["tracking_applied"])
            self.assertEqual(res["rewritten_count"], 0)
            if empty_val is None or empty_val == "":
                self.assertEqual(res["body"], "")
            else:
                self.assertEqual(res["body"], empty_val)


if __name__ == "__main__":
    unittest.main()
