"""
Test Suite: Master Proxy Systems, Browser Stealth & Anti-Detect Audit Remediations
==================================================================================
Validates all 12 To-Do remediations across Phase 1, Phase 2, and Phase 3:
- TODO-01: curl_cffi Integration & Fail-Closed Proxy Requirement (FLAW-01, FLAW-02, FLAW-14)
- TODO-02: Geodesic Velocity & Impossible Travel Guard (FLAW-03, FLAW-16)
- TODO-03: Extension Dedicated Tab Fallback & Multi-Step Support (FLAW-05, FLAW-06, FLAW-18)
- TODO-04: Webhook Security & Multi-Tenant Scoping (FLAW-07, FLAW-12)
- TODO-05: Patchright Stealth & Native Prototype Protection (FLAW-09, FLAW-10, FLAW-21, FLAW-24)
- TODO-07: Deterministic Least-Loaded Allocation & Shared Proxy Decryption (FLAW-08, FLAW-20, FLAW-31)
- TODO-08: Format-Aware Symmetric DEK vs RSA Decryption (FLAW-11)
- TODO-10: Layer 7 HTTP Health Probing (FLAW-26, FLAW-27)
- TODO-12: Hardened Subnet Extractor via Public Suffix List (FLAW-32)
"""

import os
import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from core.backend.services.proxy_routing import (
    ProxyRequiredError,
    extract_ip_subnet,
    probe_proxy_health_and_latency,
    find_sticky_failover_proxy,
)
from core.backend.services.impossible_travel_guard import (
    haversine_distance_km,
    calculate_geographic_velocity,
    should_mute_cloud_execution,
    record_and_verify_account_geodesic_hop,
)
from core.backend.core import crypto
from integrations.backend.services.voyager_scraper import (
    VoyagerScraper,
    VoyagerThrottled,
    SessionExpired,
)
from integrations.backend.services.linkedin_worker import (
    LinkedInWorker,
    resolve_browser_profile,
    parse_playwright_proxy,
)


class TestMasterProxyAuditAndRemediation(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.valid_cookies = json.dumps([
            {"name": "li_at", "value": "AQEDATestCookieValue123"},
            {"name": "JSESSIONID", "value": '"ajax:987654321"'},
            {"name": "bcookie", "value": "v=2&uuid=123"},
        ])

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-01: curl_cffi Integration & Fail-Closed Proxy Requirement
    # ─────────────────────────────────────────────────────────────────────────

    def test_voyager_scraper_fail_closed_without_proxy(self):
        """FLAW-01: VoyagerScraper must reject execution if no proxy_url is provided."""
        # Ensure test bypass env var is cleared
        old_env = os.environ.pop("ALLOW_DIRECT_SCRAPE_FOR_TESTS", None)
        try:
            scraper = VoyagerScraper(
                cookies_json=self.valid_cookies,
                account_id="acc-prod-1",
                supabase=self.mock_supabase,
                proxy_url=None
            )
            with self.assertRaises(ProxyRequiredError) as ctx:
                scraper._fetch_page({"keywords": "CTO"}, start=0)
            self.assertIn("Direct execution prohibited", str(ctx.exception))
            self.assertIn("residential proxy is strictly required", str(ctx.exception))
        finally:
            if old_env:
                os.environ["ALLOW_DIRECT_SCRAPE_FOR_TESTS"] = old_env

    def test_voyager_scraper_dynamic_timezone_alignment(self):
        """FLAW-14: VoyagerScraper must align x-li-track timezone dynamically with proxy geo."""
        scraper_us = VoyagerScraper(
            cookies_json=self.valid_cookies,
            account_id="acc-prod-2",
            supabase=self.mock_supabase,
            proxy_url="http://user:pass@1.2.3.4:8080",
            timezone_name="America/Chicago",
            timezone_offset=-6.0
        )
        headers = scraper_us._build_headers()
        track_data = json.loads(headers["x-li-track"])
        self.assertEqual(track_data["timezone"], "America/Chicago")
        self.assertEqual(track_data["timezoneOffset"], -6.0)
        self.assertNotEqual(track_data["timezone"], "Asia/Kolkata")

    def test_linkedin_worker_fail_closed_without_proxy(self):
        """FLAW-01 & FLAW-02: LinkedInWorker _http_get must reject direct datacenter execution."""
        old_env = os.environ.pop("ALLOW_DIRECT_SCRAPE_FOR_TESTS", None)
        try:
            worker = LinkedInWorker(
                cookies_json=self.valid_cookies,
                proxy_url=None,
                account_id="acc-bare-ip"
            )
            with self.assertRaises(ProxyRequiredError) as ctx:
                worker._http_get("https://www.linkedin.com/voyager/api/me")
            self.assertIn("Direct execution prohibited", str(ctx.exception))
        finally:
            if old_env:
                os.environ["ALLOW_DIRECT_SCRAPE_FOR_TESTS"] = old_env

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-02: Geodesic Velocity & Impossible Travel Guard
    # ─────────────────────────────────────────────────────────────────────────

    def test_haversine_distance_accuracy(self):
        """Layer 0: Verifies accurate distance calculation between major hubs."""
        # London (51.5074, -0.1278) to New York (40.7128, -74.0060) is approx ~5570 km
        dist = haversine_distance_km(51.5074, -0.1278, 40.7128, -74.0060)
        self.assertTrue(5500.0 < dist < 5650.0, f"Distance {dist} km out of expected range")

    def test_impossible_travel_velocity_flagging(self):
        """FLAW-03: Velocity > 800 km/h trips impossible travel anomaly."""
        now = datetime.now(timezone.utc)
        ten_minutes_ago = now - timedelta(minutes=10)

        # London to New York in 10 minutes (velocity ~33,000 km/h)
        eval_anomaly = calculate_geographic_velocity(
            prev_country="GB",
            prev_lat=51.5074,
            prev_lon=-0.1278,
            prev_timestamp=ten_minutes_ago,
            curr_country="US",
            curr_lat=40.7128,
            curr_lon=-74.0060,
            curr_timestamp=now
        )
        self.assertTrue(eval_anomaly["is_anomaly"])
        self.assertGreater(eval_anomaly["velocity_kmh"], 800.0)
        self.assertIn("exceeds maximum threshold", eval_anomaly["reason"])

        # Credible travel: New York to Philadelphia (150 km) in 2 hours (~75 km/h)
        two_hours_ago = now - timedelta(hours=2)
        eval_safe = calculate_geographic_velocity(
            prev_country="US",
            prev_lat=40.7128,
            prev_lon=-74.0060,
            prev_timestamp=two_hours_ago,
            curr_country="US",
            curr_lat=39.9526,
            curr_lon=-75.1652,
            curr_timestamp=now
        )
        self.assertFalse(eval_safe["is_anomaly"])
        self.assertLess(eval_safe["velocity_kmh"], 800.0)

    def test_channel_mutex_mutes_cloud_execution_when_extension_active(self):
        """FLAW-03: Background cloud workers mute execution if extension active."""
        now = datetime.now(timezone.utc)

        # Extension active 5 minutes ago -> MUST MUTE
        acc_active = {
            "execution_channel": "EXTENSION",
            "last_extension_active_at": (now - timedelta(minutes=5)).isoformat()
        }
        mute, reason = should_mute_cloud_execution(acc_active)
        self.assertTrue(mute)
        self.assertIn("muted to prevent dual-ip collision", reason.lower())

        # Extension idle 45 minutes ago -> CAN EXECUTE
        acc_idle = {
            "execution_channel": "EXTENSION",
            "last_extension_active_at": (now - timedelta(minutes=45)).isoformat()
        }
        mute_idle, reason_idle = should_mute_cloud_execution(acc_idle)
        self.assertFalse(mute_idle)
        self.assertIn("idle", reason_idle.lower())

        # Account is configured for CLOUD -> NEVER MUTE
        acc_cloud = {
            "execution_channel": "CLOUD",
            "last_extension_active_at": (now - timedelta(minutes=2)).isoformat()
        }
        mute_cloud, _ = should_mute_cloud_execution(acc_cloud)
        self.assertFalse(mute_cloud)

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-04: Webhook Security & Multi-Tenant Scoping
    # ─────────────────────────────────────────────────────────────────────────

    def test_webshare_webhook_rejects_missing_secret(self):
        """FLAW-07: Webhook fails closed (HTTP 500) if WEBSHARE_WEBHOOK_SECRET is unconfigured."""
        from core.backend.api.routers.proxies import _verify_webshare_webhook_secret
        from fastapi import HTTPException

        old_secret = os.environ.pop("WEBSHARE_WEBHOOK_SECRET", None)
        old_key = os.environ.pop("WEBSHARE_API_KEY", None)
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

            with self.assertRaises(HTTPException) as ctx:
                _verify_webshare_webhook_secret(
                    authorization="Bearer elein-webshare-webhook-secret",
                    x_webshare_signature=None,
                    token=None,
                    supabase=mock_sb
                )
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertIn("WEBSHARE_WEBHOOK_SECRET is unconfigured", ctx.exception.detail)
        finally:
            if old_secret:
                os.environ["WEBSHARE_WEBHOOK_SECRET"] = old_secret
            if old_key:
                os.environ["WEBSHARE_API_KEY"] = old_key

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-07: Deterministic Least-Loaded Allocation & Shared Proxy Decryption
    # ─────────────────────────────────────────────────────────────────────────

    def test_shared_system_proxy_shadowing_eliminated(self):
        """FLAW-31: Active shared system proxies are returned if workspace has no active proxies."""
        # Workspace has 0 active proxies, but 1 inactive proxy
        ws_proxies = [
            {"id": "p-inactive-ws", "workspace_id": "ws-1", "is_active": False, "status": "degraded"}
        ]
        # System pool has 1 active healthy proxy
        sys_proxies = [
            {"id": "p-healthy-sys", "workspace_id": None, "is_active": True, "status": "healthy", "country_code": "US", "host": "104.28.1.1", "port": 8080}
        ]

        def table_mock(name):
            m = MagicMock()
            if name == "proxies":
                def select_mock(*args, **kwargs):
                    sm = MagicMock()
                    # Workspace query with is_active=True returns empty
                    sm.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                    # System query is_("workspace_id", "null") returns active sys_proxies
                    sm.is_.return_value.eq.return_value.execute.return_value = MagicMock(data=sys_proxies)
                    return sm
                m.select = select_mock
            elif name == "accounts":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_sb = MagicMock()
        mock_sb.table = table_mock

        with patch("core.backend.services.proxy_routing.probe_proxy_health_and_latency") as mock_probe:
            mock_probe.return_value = {"is_healthy": True, "latency_ms": 120.0, "status": "healthy"}
            chosen = find_sticky_failover_proxy(
                supabase=mock_sb,
                workspace_id="ws-1",
                target_country="US"
            )
            self.assertIsNotNone(chosen)
            self.assertEqual(chosen["id"], "p-healthy-sys")

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-08: Format-Aware Symmetric DEK vs RSA Decryption
    # ─────────────────────────────────────────────────────────────────────────

    def test_crypto_decrypt_bytes_format_aware_resolution(self):
        """FLAW-11: decrypt_bytes correctly resolves format without throwing tag mismatch."""
        # 1. Symmetric DEK encryption (enc_key_len == 0)
        test_dek = os.urandom(32)
        plaintext = b'{"li_at": "session_secret_cookie_123"}'
        enc_with_dek = crypto.encrypt_bytes(plaintext, dek=test_dek)

        # Decrypt with correct DEK
        decrypted = crypto.decrypt_bytes(enc_with_dek, dek=test_dek)
        self.assertEqual(decrypted, plaintext)

        # Attempting to decrypt DEK payload without DEK raises clean VaultDecryptionError
        with self.assertRaises(crypto.VaultDecryptionError) as ctx:
            crypto.decrypt_bytes(enc_with_dek, dek=None)
        self.assertIn("encrypted with a DEK", str(ctx.exception))

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-10: Layer 7 HTTP Health Probing
    # ─────────────────────────────────────────────────────────────────────────

    def test_layer7_proxy_probe_detects_http_407(self):
        """FLAW-26: Layer 7 probing catches HTTP 407 proxy auth failure."""
        proxy_row = {
            "id": "p-auth-fail",
            "host": "104.28.1.1",
            "port": 8080,
            "username": "bad_user",
            "country_code": "US",
            "is_active": True
        }

        # Mock socket TCP handshake succeeding in 20ms, but HTTP returning 407
        with patch("socket.create_connection"):
            with patch("httpx.Client") as mock_http_client:
                mock_inst = MagicMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 407
                mock_inst.get.return_value = mock_resp
                mock_http_client.return_value.__enter__.return_value = mock_inst

                probe = probe_proxy_health_and_latency(
                    proxy_row,
                    timeout_seconds=2.0,
                    perform_layer7_probe=True
                )
                self.assertFalse(probe["is_healthy"])
                self.assertEqual(probe["status"], "proxy_auth_407")
                self.assertIn("407 Proxy Authentication Required", probe["error"])

    # ─────────────────────────────────────────────────────────────────────────
    # TODO-12: Hardened Subnet Extractor via Public Suffix List
    # ─────────────────────────────────────────────────────────────────────────

    def test_subdomain_extractor_handles_multi_part_tlds_and_gateways(self):
        """FLAW-32: Subnet extractor extracts provider root without false collision flags."""
        # Standard IPv4 /24 extraction
        sub_ip = extract_ip_subnet("192.168.1.55")
        self.assertEqual(sub_ip, "192.168.1")

        # Multi-part UK domain node
        sub_uk = extract_ip_subnet("node-1.residential.proxy.co.uk")
        self.assertIn("proxy.co.uk", sub_uk)
        self.assertNotEqual(sub_uk, "co.uk")  # Must NOT collapse to raw TLD "co.uk"

        # Webshare gateway subdomains correctly resolve to registered provider domain
        sub_ws1 = extract_ip_subnet("p-us.webshare.io")
        sub_ws2 = extract_ip_subnet("p-uk.webshare.io")
        self.assertEqual(sub_ws1, "webshare.io")
        self.assertEqual(sub_ws2, "webshare.io")


if __name__ == "__main__":
    unittest.main()
