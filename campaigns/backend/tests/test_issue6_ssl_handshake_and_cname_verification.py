"""
test_issue6_ssl_handshake_and_cname_verification.py
Unit test suite for Issue 6: Custom Domain Tracking CNAME & Automated SSL Verification Guard.
Implements the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (TLS handshake, certificate extraction, SAN list, DNS CNAME resolution, link rewriting)
  - Layer 1: Environmental Failure Analysis (SSL cert verification failures, handshake errors, timeouts, connection refused, DNS/gaierror, pending provisioning)
  - Layer 2: Human Paranoia (SSRF rejection for localhost/internal/private IPs, trailing punctuation preservation, double-wrap avoidance)
"""

import socket
import ssl
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from core.backend.services.deliverability_guard import (
    sanitize_domain_input,
    verify_ssl_handshake,
    verify_custom_tracking_domain,
    verify_domain_dns_health,
    rewrite_tracking_links,
)


class TestIssue6SSLHandshakeAndCNAMEVerification(unittest.TestCase):

    # =========================================================================
    # 1. VERIFY_SSL_HANDSHAKE TESTS
    # =========================================================================

    def test_layer2_verify_ssl_handshake_ssrf_and_invalid_inputs(self):
        """Paranoia Layer 2: Sanitizes domain and blocks localhost, 127.0.0.1, private IPs, and malformed strings."""
        forbidden_inputs = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "169.254.169.254",
            "10.0.0.1",
            "192.168.1.1",
            "internal.corp.local",
            "server.internal",
            "",
            "   ",
            None,
            "https://localhost/path",
            "http://127.0.0.1:8000",
        ]
        for host in forbidden_inputs:
            res = verify_ssl_handshake(host)
            self.assertFalse(res["ssl_valid"])
            self.assertEqual(res["error"], "FORBIDDEN_OR_INVALID_HOST")

    @patch("core.backend.services.deliverability_guard.socket.create_connection")
    @patch("core.backend.services.deliverability_guard.ssl.create_default_context")
    def test_layer0_verify_ssl_handshake_active_valid(self, mock_ctx, mock_create_conn):
        """Paranoia Layer 0: Successful TLS handshake extracts SANs, issuer, subject CN, and computes days until expiry."""
        future_dt = datetime.now(timezone.utc) + timedelta(days=75)
        # OpenSSL standard time format: "May 15 23:59:59 2026 GMT"
        not_after_str = future_dt.strftime("%b %d %H:%M:%S %Y GMT")

        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_context_inst = MagicMock()
        mock_ctx.return_value = mock_context_inst
        mock_context_inst.wrap_socket.return_value.__enter__.return_value = mock_ssock

        mock_ssock.getpeercert.return_value = {
            "subject": ((("commonName", "track.acme.com"),),),
            "issuer": ((("organizationName", "Let's Encrypt"),), (("commonName", "R3"),)),
            "subjectAltName": [
                ("DNS", "track.acme.com"),
                ("DNS", "click.acme.com"),
            ],
            "notAfter": not_after_str,
        }

        res = verify_ssl_handshake("track.acme.com")
        self.assertTrue(res["ssl_valid"])
        self.assertEqual(res["status"], "ACTIVE_VALID")
        self.assertEqual(res["hostname"], "track.acme.com")
        self.assertGreaterEqual(res["days_until_expiry"], 74)
        self.assertIn("track.acme.com", res["san_list"])
        self.assertIn("click.acme.com", res["san_list"])
        self.assertEqual(res["subject"], "track.acme.com")
        self.assertIsNotNone(res["expires_at"])

    @patch("core.backend.services.deliverability_guard.socket.create_connection")
    @patch("core.backend.services.deliverability_guard.ssl.create_default_context")
    def test_layer1_verify_ssl_handshake_expired_cert(self, mock_ctx, mock_create_conn):
        """Paranoia Layer 1: Detects expired certificate (days_until_expiry <= 0) and marks invalid."""
        past_dt = datetime.now(timezone.utc) - timedelta(days=10)
        not_after_str = past_dt.strftime("%b %d %H:%M:%S %Y GMT")

        mock_sock = MagicMock()
        mock_ssock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_context_inst = MagicMock()
        mock_ctx.return_value = mock_context_inst
        mock_context_inst.wrap_socket.return_value.__enter__.return_value = mock_ssock

        mock_ssock.getpeercert.return_value = {
            "subject": ((("commonName", "track.expired.com"),),),
            "issuer": ((("commonName", "ZeroSSL"),),),
            "subjectAltName": [("DNS", "track.expired.com")],
            "notAfter": not_after_str,
        }

        res = verify_ssl_handshake("track.expired.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "CERTIFICATE_EXPIRED")
        self.assertLessEqual(res["days_until_expiry"], 0)
        self.assertIn("expired", res["error"].lower())

    @patch("core.backend.services.deliverability_guard.socket.create_connection")
    @patch("core.backend.services.deliverability_guard.ssl.create_default_context")
    def test_layer1_verify_ssl_handshake_cert_verification_error(self, mock_ctx, mock_create_conn):
        """Paranoia Layer 1: Catches ssl.SSLCertVerificationError (e.g. self-signed or untrusted CA)."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__.return_value = mock_sock
        mock_context_inst = MagicMock()
        mock_ctx.return_value = mock_context_inst
        mock_context_inst.wrap_socket.side_effect = ssl.SSLCertVerificationError("certificate verify failed: self-signed certificate")

        res = verify_ssl_handshake("track.selfsigned.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "SSL_CERT_VERIFICATION_FAILED")
        self.assertIn("self-signed", res["error"])

    @patch("core.backend.services.deliverability_guard.socket.create_connection")
    @patch("core.backend.services.deliverability_guard.ssl.create_default_context")
    def test_layer1_verify_ssl_handshake_socket_timeout(self, mock_ctx, mock_create_conn):
        """Paranoia Layer 1: Catches socket.timeout and TimeoutError gracefully."""
        mock_create_conn.side_effect = socket.timeout("timed out")

        res = verify_ssl_handshake("slow-host.acme.com", timeout=1.0)
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "CONNECTION_TIMEOUT")
        self.assertEqual(res["error"], "Connection timed out")

    @patch("core.backend.services.deliverability_guard.socket.create_connection")
    def test_layer1_verify_ssl_handshake_connection_refused(self, mock_create_conn):
        """Paranoia Layer 1: Catches ConnectionRefusedError when port 443 is closed."""
        mock_create_conn.side_effect = ConnectionRefusedError("Connection refused")

        res = verify_ssl_handshake("no-ssl-server.acme.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "CONNECTION_REFUSED")
        self.assertEqual(res["error"], "Port 443 refused")

    @patch("core.backend.services.deliverability_guard.socket.create_connection")
    def test_layer1_verify_ssl_handshake_gaierror_dns_failure(self, mock_create_conn):
        """Paranoia Layer 1: Catches socket.gaierror (DNS resolution failure)."""
        mock_create_conn.side_effect = socket.gaierror(-2, "Name or service not known")

        res = verify_ssl_handshake("nonexistent-domain-xyz12345.com")
        self.assertFalse(res["ssl_valid"])
        self.assertEqual(res["status"], "SSL_CHECK_FAILED")
        self.assertIn("Name or service not known", res["error"])

    # =========================================================================
    # 2. VERIFY_CUSTOM_TRACKING_DOMAIN TESTS
    # =========================================================================

    def test_layer0_verify_custom_tracking_domain_cname_missing_or_mismatch(self):
        """Paranoia Layer 0: Fails verification when CNAME record is missing or points to the wrong target."""
        # Missing CNAME
        res_missing = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            mock_cname=None,
        )
        self.assertFalse(res_missing["valid"])
        self.assertEqual(res_missing["status"], "CNAME_MISSING_OR_MISMATCH")
        self.assertFalse(res_missing["ssl_verified"])
        self.assertFalse(res_missing["can_track_safely"])

        # Mismatched CNAME
        res_mismatch = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            mock_cname="other-provider.sendgrid.net",
        )
        self.assertFalse(res_mismatch["valid"])
        self.assertEqual(res_mismatch["status"], "CNAME_MISSING_OR_MISMATCH")
        self.assertEqual(res_mismatch["cname_target"], "other-provider.sendgrid.net")
        self.assertFalse(res_mismatch["can_track_safely"])

    def test_layer0_verify_custom_tracking_domain_active_verified(self):
        """Paranoia Layer 0: Returns VERIFIED_ACTIVE when CNAME matches and SSL certificate is valid."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=True,
            mock_cname="track.elein.ai",
            mock_ssl_valid=True,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["status"], "VERIFIED_ACTIVE")
        self.assertTrue(res["ssl_verified"])
        self.assertTrue(res["can_track_safely"])
        self.assertEqual(res["cname_target"], "track.elein.ai")
        self.assertIsNotNone(res.get("ssl_details"))

    def test_layer1_verify_custom_tracking_domain_ssl_pending_provisioning(self):
        """Paranoia Layer 1: Returns SSL_PENDING_PROVISIONING when CNAME matches but SSL is not yet active."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.acme.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=True,
            mock_cname="track.elein.ai",
            mock_ssl_valid=False,
        )
        self.assertFalse(res["valid"])
        self.assertEqual(res["status"], "SSL_PENDING_PROVISIONING")
        self.assertEqual(res["cname_target"], "track.elein.ai")
        self.assertFalse(res["ssl_verified"])
        self.assertFalse(res["can_track_safely"])
        self.assertIn("SSL certificate is still provisioning", res["action_required"])

    def test_layer0_verify_custom_tracking_domain_cname_only_no_ssl_check(self):
        """Paranoia Layer 0: Returns CNAME_ONLY when check_live_ssl is False."""
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

    # =========================================================================
    # 3. VERIFY_DOMAIN_DNS_HEALTH INTEGRATION TESTS
    # =========================================================================

    @patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain")
    @patch("core.backend.services.deliverability_guard._lookup_txt_records")
    def test_layer0_verify_domain_dns_health_with_active_ssl(self, mock_txt, mock_tracking):
        """Paranoia Layer 0: Full health check with active tracking SSL marks ssl_tracking_ready=True."""
        def txt_side_effect(qname, timeout=2.5):
            if qname == "acme.com":
                return ["v=spf1 include:_spf.google.com ~all"]
            elif qname == "elein._domainkey.acme.com":
                return ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"]
            elif qname == "_dmarc.acme.com":
                return ["v=DMARC1; p=reject; rua=mailto:dmarc@acme.com"]
            return []

        mock_txt.side_effect = txt_side_effect
        mock_tracking.return_value = {
            "valid": True,
            "status": "VERIFIED_ACTIVE",
            "cname_target": "track.elein.ai",
            "ssl_verified": True,
            "can_track_safely": True,
            "ssl_details": {"ssl_valid": True, "status": "ACTIVE_VALID"},
        }

        res = verify_domain_dns_health("acme.com")
        self.assertTrue(res["valid"])
        self.assertEqual(res["deliverability_score"], 100)
        self.assertTrue(res["ssl_tracking_ready"])
        self.assertEqual(res["records"]["tracking_cname"]["status"], "VERIFIED_ACTIVE")
        self.assertTrue(res["records"]["tracking_cname"]["ssl_verified"])

    @patch("core.backend.services.deliverability_guard.verify_custom_tracking_domain")
    @patch("core.backend.services.deliverability_guard._lookup_txt_records")
    def test_layer1_verify_domain_dns_health_cname_set_ssl_pending_logs_warning(self, mock_txt, mock_tracking):
        """Paranoia Layer 1: When CNAME is set but SSL is pending, logs explicit warning and marks ssl_tracking_ready=False."""
        def txt_side_effect(qname, timeout=2.5):
            if qname == "acme.com":
                return ["v=spf1 include:_spf.google.com ~all"]
            elif qname == "elein._domainkey.acme.com":
                return ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"]
            elif qname == "_dmarc.acme.com":
                return ["v=DMARC1; p=reject; rua=mailto:dmarc@acme.com"]
            return []

        mock_txt.side_effect = txt_side_effect
        mock_tracking.return_value = {
            "valid": False,
            "status": "SSL_PENDING_PROVISIONING",
            "cname_target": "track.elein.ai",
            "ssl_verified": False,
            "can_track_safely": False,
            "ssl_error": "SSL handshake timeout",
            "action_required": "CNAME is configured, but SSL certificate is still provisioning or invalid. Tracking links will remain plain until SSL is active.",
        }

        with patch("core.backend.services.deliverability_guard.logger.warning") as mock_log_warn:
            res = verify_domain_dns_health("acme.com")
            self.assertTrue(res["valid"])
            self.assertFalse(res["ssl_tracking_ready"])
            mock_log_warn.assert_called()
            self.assertTrue(any("still provisioning" in w for w in res["warnings"]))
            self.assertEqual(res["records"]["tracking_cname"]["status"], "SSL_PENDING_PROVISIONING")
            self.assertFalse(res["records"]["tracking_cname"]["ssl_verified"])

    # =========================================================================
    # 4. REWRITE_TRACKING_LINKS TESTS
    # =========================================================================

    def test_layer1_rewrite_tracking_links_ssl_unverified_fallback(self):
        """Paranoia Layer 1: When ssl_verified is False, always leaves body untouched with SSL_UNVERIFIED_PREVENTED_BROWSER_WARNING."""
        body = "Hello! Check out https://acme.com/demo and read https://acme.com/docs."
        res = rewrite_tracking_links(
            body=body,
            tracking_domain="track.acme.com",
            email_id="email_123",
            workspace_id="ws_456",
            ssl_verified=False,
        )
        self.assertFalse(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 0)
        self.assertEqual(res["body"], body)
        self.assertEqual(res["fallback_reason"], "SSL_UNVERIFIED_PREVENTED_BROWSER_WARNING")

    def test_layer2_rewrite_tracking_links_preserves_trailing_punctuation(self):
        """Paranoia Layer 2: Preserves trailing punctuation (., ,, !, ?, ;, \") at the end of prose URLs."""
        test_cases = [
            ("Visit https://acme.com/pricing.", "."),
            ("Check https://acme.com/pricing,", ","),
            ("Click https://acme.com/pricing!", "!"),
            ("Is this it https://acme.com/pricing?", "?"),
            ("Options include https://acme.com/pricing;", ";"),
            ('See "https://acme.com/pricing"', '"'),
        ]

        for text, punct in test_cases:
            res = rewrite_tracking_links(
                body=text,
                tracking_domain="track.acme.com",
                email_id="em_1",
                workspace_id="ws_1",
                ssl_verified=True,
            )
            self.assertTrue(res["tracking_applied"])
            self.assertEqual(res["rewritten_count"], 1)
            self.assertTrue(res["body"].endswith(punct), f"Failed for trailing punct: {punct}")
            self.assertIn("https://track.acme.com/t/c/em_1?u=https%3A%2F%2Facme.com%2Fpricing", res["body"])

    def test_layer2_rewrite_tracking_links_no_double_wrapping(self):
        """Paranoia Layer 2: Does not double-wrap URLs that already point to the custom tracking domain or have /t/c/."""
        already_tracked = "Already tracked: https://track.acme.com/t/c/em_1?u=https%3A%2F%2Facme.com and https://click.track.acme.com/t/c/em_2"
        res = rewrite_tracking_links(
            body=already_tracked,
            tracking_domain="track.acme.com",
            email_id="em_new",
            workspace_id="ws_new",
            ssl_verified=True,
        )
        self.assertFalse(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 0)
        self.assertEqual(res["body"], already_tracked)


if __name__ == "__main__":
    unittest.main()
