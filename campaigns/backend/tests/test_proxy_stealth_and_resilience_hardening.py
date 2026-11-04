import unittest
import json
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from core.backend.services.proxy_routing import (
    format_proxy_url,
    build_authenticated_proxy_url,
    find_sticky_failover_proxy
)
from integrations.backend.services.linkedin_worker import (
    parse_playwright_proxy,
    COUNTRY_BROWSER_PROFILES
)
from core.backend.services.health_check_cron import run_health_checks, _try_proxy_failover


class TestProxyStealthAndResilienceHardening(unittest.TestCase):
    """
    Paranoia Framework Layer 0, 1 & 2 tests for Proxy Stealth, URL formatting,
    Decoupled Health Checks, Geo-affinity drift prevention, and Extension channel exclusivity.
    """

    def test_format_proxy_url_percent_encodes_all_special_chars(self):
        """Layer 1: Passwords containing @, :, #, /, ?, &, %, + are strictly encoded."""
        raw_password = "p@ss:w/o?r#d&100%+!"
        raw_username = "user@domain.com"
        
        formatted = format_proxy_url("http", "185.220.101.5", 8080, raw_username, raw_password)
        
        self.assertIn("user%40domain.com", formatted)
        self.assertIn("p%40ss%3Aw%2Fo%3Fr%23d%26100%25%2B%21", formatted)
        self.assertTrue(formatted.startswith("http://user%40domain.com:p%40ss%3Aw%2Fo%3Fr%23d%26100%25%2B%21@185.220.101.5:8080"))

    def test_format_proxy_url_without_credentials(self):
        """Layer 0: Handles unauthenticated proxies without dangling colons or @ symbols."""
        formatted = format_proxy_url("socks5", "10.0.0.1", 1080)
        self.assertEqual(formatted, "socks5://10.0.0.1:1080")

    def test_parse_playwright_proxy_splits_credentials_from_server(self):
        """
        Layer 0 & 1: Chromium CLI parser strips embedded user:pass@host:port.
        parse_playwright_proxy must separate them into discrete dictionary keys.
        """
        proxy_url = "http://myuser:p%40ssword@192.168.1.100:3128"
        parsed = parse_playwright_proxy(proxy_url)
        
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["server"], "http://192.168.1.100:3128")
        self.assertEqual(parsed["username"], "myuser")
        self.assertEqual(parsed["password"], "p@ssword")

    def test_parse_playwright_proxy_unauthenticated_url(self):
        """Layer 0: Unauthenticated URLs do not include username/password keys."""
        proxy_url = "http://192.168.1.100:3128"
        parsed = parse_playwright_proxy(proxy_url)
        
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["server"], "http://192.168.1.100:3128")
        self.assertNotIn("username", parsed)
        self.assertNotIn("password", parsed)

    def test_country_browser_profiles_exist_for_core_regions(self):
        """Layer 1: India, UAE/Dubai, US, and UK profiles match local timezones and coordinates."""
        in_profile = COUNTRY_BROWSER_PROFILES.get("IN")
        self.assertIsNotNone(in_profile)
        self.assertEqual(in_profile["timezone_id"], "Asia/Kolkata")
        self.assertEqual(in_profile["locale"], "en-IN")
        self.assertAlmostEqual(in_profile["geo"]["latitude"], 19.0760, places=2)

        ae_profile = COUNTRY_BROWSER_PROFILES.get("AE")
        self.assertIsNotNone(ae_profile)
        self.assertEqual(ae_profile["timezone_id"], "Asia/Dubai")
        self.assertEqual(ae_profile["locale"], "en-AE")
        self.assertAlmostEqual(ae_profile["geo"]["latitude"], 25.2048, places=2)

        us_profile = COUNTRY_BROWSER_PROFILES.get("US")
        self.assertIsNotNone(us_profile)
        self.assertEqual(us_profile["timezone_id"], "America/New_York")

    def test_health_check_cron_401_does_not_quarantine_proxy(self):
        """
        Layer 1 (The Proxy Murder Loop Fix):
        When an account gets HTTP 401 (expired session), the account status is disconnected,
        but the proxy is NEVER degraded or quarantined.
        """
        mock_supabase = MagicMock()
        mock_accounts_res = MagicMock()
        mock_accounts_res.data = [{
            "id": "acc-401",
            "name": "Expired Account",
            "proxy_id": "px-healthy-1",
            "status": "ACTIVE",
            "workspace_id": "ws-1",
            "session_cookies_encrypted": "hexdata"
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_accounts_res
        
        mock_proxies_res = MagicMock()
        mock_proxies_res.data = [{
            "id": "px-healthy-1",
            "host": "1.2.3.4",
            "port": 8080,
            "status": "healthy",
            "country_code": "US"
        }]
        mock_supabase.table().select().in_().execute.return_value = mock_proxies_res

        mock_supabase.rpc().execute.return_value.data = None
        with patch("core.backend.services.health_check_cron.get_service_client", return_value=mock_supabase), \
             patch("core.backend.services.auto_cooling.resume_cooled_accounts", return_value=[]), \
             patch("core.backend.services.auto_cooling.probe_and_recover_degraded_proxies", return_value=[]), \
             patch("core.backend.services.health_check_cron.quarantine_proxy") as mock_quarantine, \
             patch("core.backend.services.health_check_cron._disconnect_account") as mock_disconnect, \
             patch("core.backend.core.crypto.pg_hex_to_bytes", return_value=b"raw"), \
             patch("core.backend.core.crypto.decrypt_bytes", return_value=b'[{"name": "li_at", "value": "xyz"}]'), \
             patch("integrations.backend.services.linkedin_worker.LinkedInWorker._http_get") as mock_http_get:
            
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_http_get.return_value = mock_resp

            run_health_checks()
            
            # Account disconnect called
            mock_disconnect.assert_called_once()
            # Proxy was NEVER quarantined
            mock_quarantine.assert_not_called()

    def test_health_check_cron_403_or_999_quarantines_proxy(self):
        """
        Layer 1: When LinkedIn explicitly responds with 403 or 999 (IP ban/challenge),
        quarantine_proxy is called for the proxy.
        """
        mock_supabase = MagicMock()
        mock_accounts_res = MagicMock()
        mock_accounts_res.data = [{
            "id": "acc-blocked",
            "name": "Blocked Account",
            "proxy_id": "px-burned-1",
            "status": "ACTIVE",
            "workspace_id": "ws-1",
            "session_cookies_encrypted": "hexdata"
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_accounts_res
        
        mock_proxies_res = MagicMock()
        mock_proxies_res.data = [{
            "id": "px-burned-1",
            "host": "1.2.3.4",
            "port": 8080,
            "status": "healthy",
            "country_code": "US"
        }]
        mock_supabase.table().select().in_().execute.return_value = mock_proxies_res

        mock_supabase.rpc().execute.return_value.data = None
        with patch("core.backend.services.health_check_cron.get_service_client", return_value=mock_supabase), \
             patch("core.backend.services.auto_cooling.resume_cooled_accounts", return_value=[]), \
             patch("core.backend.services.auto_cooling.probe_and_recover_degraded_proxies", return_value=[]), \
             patch("core.backend.services.health_check_cron.quarantine_proxy") as mock_quarantine, \
             patch("core.backend.core.crypto.pg_hex_to_bytes", return_value=b"raw"), \
             patch("core.backend.core.crypto.decrypt_bytes", return_value=b'[{"name": "li_at", "value": "xyz"}]'), \
             patch("integrations.backend.services.linkedin_worker.LinkedInWorker._http_get") as mock_http_get:
            
            mock_resp = MagicMock()
            mock_resp.status_code = 999
            mock_http_get.return_value = mock_resp

            run_health_checks()
            
            mock_quarantine.assert_called_once()
            args, kwargs = mock_quarantine.call_args
            self.assertEqual(args[1], "px-burned-1")
            self.assertEqual(kwargs.get("reason"), "linkedin_challenge_999")

    def test_geo_routing_drift_guard_blocks_cross_country_fallback(self):
        """
        Layer 1 & 2: When an Indian sender connects an account and no IN proxies exist
        (only US proxies), find_sticky_failover_proxy with allow_cross_country_drift=False
        returns None rather than blindsiding LinkedIn with impossible travel.
        """
        mock_supabase = MagicMock()
        mock_proxies = [
            {"id": "px-us-1", "country_code": "US", "status": "healthy", "is_active": True},
            {"id": "px-us-2", "country_code": "US", "status": "healthy", "is_active": True}
        ]
        mock_supabase.table().select().eq().eq().execute.return_value.data = mock_proxies
        mock_supabase.table().select().in_().execute.return_value.data = []

        # Target country IN with drift forbidden
        chosen = find_sticky_failover_proxy(
            mock_supabase,
            workspace_id="ws-123",
            target_country="IN",
            allow_cross_country_drift=False
        )
        self.assertIsNone(chosen)

        # When matching IN proxy exists, it assigns it cleanly
        mock_proxies_with_in = [
            {"id": "px-us-1", "country_code": "US", "status": "healthy", "is_active": True},
            {"id": "px-in-1", "country_code": "IN", "status": "healthy", "is_active": True}
        ]
        mock_supabase.table().select().eq().eq().execute.return_value.data = mock_proxies_with_in
        chosen_in = find_sticky_failover_proxy(
            mock_supabase,
            workspace_id="ws-123",
            target_country="IN",
            allow_cross_country_drift=False
        )
        self.assertIsNotNone(chosen_in)
        self.assertEqual(chosen_in["id"], "px-in-1")

    def test_extension_dispatch_blocked_for_cloud_proxied_account(self):
        """
        Layer 1 & 2: Prevent concurrent IP collisions. If account is configured
        with a cloud residential proxy and execution_channel != 'EXTENSION',
        extension task dispatch is safely paused.
        """
        from integrations.backend.routers.extension import get_extension_tasks

        mock_supabase = MagicMock()
        mock_acc_res = MagicMock()
        mock_acc_res.data = [{
            "id": "acc-cloud-1",
            "workspace_id": "ws-123",
            "proxy_id": "px-cloud-res-1",
            "execution_channel": "CLOUD",
            "status": "ACTIVE"
        }]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_acc_res

        res = get_extension_tasks(
            account_id="acc-cloud-1",
            tab_id=None,
            workspace_id="ws-123",
            supabase=mock_supabase
        )
        self.assertTrue(res.get("proxy_exclusive"))
        self.assertEqual(res.get("tasks"), [])
        self.assertIn("Local extension outreach dispatch paused", res.get("message", ""))

    def test_webshare_sync_encrypts_password_with_vault_dek(self):
        """
        Layer 0 & 1: Webshare proxy sync must encrypt password using per-record DEK
        and store reference in secret_ref so workers can decrypt without shared static keys.
        """
        from integrations.backend.services.webshare_sync import sync_webshare_proxies

        mock_supabase = MagicMock()
        mock_supabase.rpc().execute.return_value.data = "vault-ref-webshare-1"
        mock_supabase.table().upsert().execute.return_value = MagicMock()

        mock_api_response = {
            "results": [{
                "proxy_address": "185.100.50.1",
                "port": 8000,
                "username": "user123",
                "password": "secret_password",
                "country_code": "US",
                "valid": True
            }],
            "next": None
        }

        with patch.dict("os.environ", {"WEBSHARE_API_KEY": "mock_webshare_key"}), \
             patch("integrations.backend.services.webshare_sync.requests.get") as mock_get, \
             patch("core.backend.core.crypto.generate_dek", return_value="bW9jay1kZWstYnl0ZXM="), \
             patch("core.backend.core.crypto.encrypt_bytes", return_value=b"encrypted_pass_bytes"):
            
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_api_response
            mock_get.return_value = mock_resp

            summary = sync_webshare_proxies(
                workspace_id="ws-123",
                supabase=mock_supabase
            )

            self.assertEqual(summary["synced"], 1)
            self.assertEqual(summary["errors"], 0)
            mock_supabase.rpc.assert_called_with("store_account_secret", {"p_secret": "bW9jay1kZWstYnl0ZXM="})
            upsert_args = mock_supabase.table().upsert.call_args[0][0]
            self.assertEqual(upsert_args["secret_ref"], "vault-ref-webshare-1")
            self.assertIn("password_encrypted", upsert_args)

    def test_webrtc_ip_leak_protection_flags_and_init_script(self):
        """
        Layer 1: WebRTC STUN/TURN can leak the host server's real IP address.
        Verify Chromium flags and init script enforce strict proxy routing for WebRTC.
        """
        from integrations.backend.services.linkedin_worker import LinkedInWorker

        worker = LinkedInWorker(
            cookies_json=json.dumps([{"name": "li_at", "value": "val"}]),
            proxy_url="http://185.1.2.3:8080",
            account_id="acc-webrtc-test",
            country_code="IN"
        )

        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context

        worker._setup_browser_headless(mock_playwright)

        # Check launch args passed to Chromium
        launch_kwargs = mock_playwright.chromium.launch.call_args[1]
        args = launch_kwargs.get("args", [])
        self.assertIn("--force-webrtc-ip-handling-policy=disable_non_proxied_udp", args)
        self.assertIn("--enforce-webrtc-ip-permission-check", args)

        # Check init script injected into context
        mock_context.add_init_script.assert_called_once()
        injected_script = mock_context.add_init_script.call_args[0][0]
        self.assertIn("iceTransportPolicy = 'relay'", injected_script)
        self.assertIn("languages", injected_script)
        self.assertIn("en-IN", injected_script)

    def test_http_get_aligns_headers_with_country_code(self):
        """
        Layer 1 & 2: HTTP requests must align language headers with proxy location.
        """
        from integrations.backend.services.linkedin_worker import LinkedInWorker
        import httpx

        worker = LinkedInWorker(
            cookies_json=json.dumps([
                {"name": "li_at", "value": "li_at_val"},
                {"name": "JSESSIONID", "value": '"ajax:csrf_val"'}
            ]),
            proxy_url="http://185.1.2.3:8080",
            account_id="acc-headers-test",
            country_code="IN"
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
            self.assertEqual(resp.status_code, 200)

            call_kwargs = mock_client_cls.call_args[1]
            headers = call_kwargs.get("headers", {})
            self.assertEqual(headers.get("x-li-lang"), "en_IN")
            self.assertIn("en-IN", headers.get("Accept-Language", ""))

    def test_http_get_retries_transient_proxy_transport_error(self):
        """
        Layer 1: Transient proxy network blips retry cleanly before failing.
        """
        from integrations.backend.services.linkedin_worker import LinkedInWorker
        import httpx

        worker = LinkedInWorker(
            cookies_json=json.dumps([
                {"name": "li_at", "value": "li_at_val"},
                {"name": "JSESSIONID", "value": '"ajax:csrf_val"'}
            ]),
            proxy_url="http://185.1.2.3:8080",
            account_id="acc-retry-test"
        )

        with patch("httpx.Client") as mock_client_cls, \
             patch("time.sleep"):
            mock_client_1 = MagicMock()
            mock_client_1.get.side_effect = httpx.ConnectTimeout("Proxy gateway timeout")
            
            mock_client_2 = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client_2.get.return_value = mock_resp

            mock_client_cls.side_effect = [mock_client_1, mock_client_2]

            resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(mock_client_cls.call_count, 2)

    def test_get_proxies_endpoint_aggregates_workspace_and_system_pool(self):
        """
        Layer 0 & 2: /api/proxies endpoint returns both dedicated workspace proxies
        and shared system proxies, including assigned account counts.
        """
        from core.backend.api.routers.proxies import get_proxies

        mock_supabase = MagicMock()
        
        # Workspace proxies
        ws_proxies = [{
            "id": "px-ws-1",
            "provider": "custom",
            "host": "185.10.10.1",
            "port": 8080,
            "protocol": "http",
            "status": "healthy",
            "country_code": "US",
            "workspace_id": "ws-123"
        }]
        # System proxies
        sys_proxies = [{
            "id": "px-sys-1",
            "provider": "webshare",
            "host": "194.20.20.1",
            "port": 8080,
            "protocol": "http",
            "status": "healthy",
            "country_code": "IN",
            "workspace_id": None
        }]

        # Mock calls
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.order.return_value.execute.return_value.data = ws_proxies
        table_mock.select.return_value.is_.return_value.order.return_value.execute.return_value.data = sys_proxies
        table_mock.select.return_value.in_.return_value.execute.return_value.data = [
            {"proxy_id": "px-ws-1"},
            {"proxy_id": "px-ws-1"}
        ]

        proxies = get_proxies(supabase=mock_supabase, workspace_id="ws-123")
        
        self.assertEqual(len(proxies), 2)
        px_ws = next(p for p in proxies if p["id"] == "px-ws-1")
        px_sys = next(p for p in proxies if p["id"] == "px-sys-1")

        self.assertFalse(px_ws["is_system"])
        self.assertEqual(px_ws["assigned_accounts_count"], 2)
        self.assertTrue(px_sys["is_system"])
        self.assertEqual(px_sys["assigned_accounts_count"], 0)

    def test_browser_pool_purges_stale_context_on_proxy_rotation(self):
        """
        Layer 1 Non-Generic Discrepancy Fix:
        When an account's proxy is rotated, BrowserPool must NOT reuse the old
        browser context still connected to the dead proxy. It must purge and recreate.
        """
        from integrations.backend.services.linkedin_pool import BrowserPool

        pool = BrowserPool(max_size=2)
        mock_pw_1 = MagicMock()
        mock_browser_1 = MagicMock()
        mock_context_1 = MagicMock()
        mock_page_1 = MagicMock()
        mock_context_1.new_page.return_value = mock_page_1

        mock_pw_2 = MagicMock()
        mock_browser_2 = MagicMock()
        mock_context_2 = MagicMock()
        mock_page_2 = MagicMock()
        mock_context_2.new_page.return_value = mock_page_2

        setup_calls = []
        def mock_setup(pw):
            if len(setup_calls) == 0:
                setup_calls.append("call-1")
                return mock_browser_1, mock_context_1
            else:
                setup_calls.append("call-2")
                return mock_browser_2, mock_context_2

        with patch("integrations.backend.services.linkedin_pool.sync_playwright") as mock_sync_pw:
            mock_sync_pw.return_value.start.side_effect = [mock_pw_1, mock_pw_2]

            # 1. First acquire with Proxy A
            ctx1 = pool.acquire("acc-rotate-test", mock_setup, proxy_url="http://proxy-a:8080")
            self.assertEqual(ctx1, mock_context_1)
            self.assertEqual(len(setup_calls), 1)
            pool.release("acc-rotate-test")

            # 2. Second acquire with SAME proxy A -> Reuses existing context
            ctx1_reuse = pool.acquire("acc-rotate-test", mock_setup, proxy_url="http://proxy-a:8080")
            self.assertEqual(ctx1_reuse, mock_context_1)
            self.assertEqual(len(setup_calls), 1)  # No new browser created!
            pool.release("acc-rotate-test")

            # 3. Third acquire with NEW Proxy B -> Detects rotation, purges old context, launches new browser
            ctx2 = pool.acquire("acc-rotate-test", mock_setup, proxy_url="http://proxy-b:8080")
            self.assertEqual(ctx2, mock_context_2)
            self.assertEqual(len(setup_calls), 2)  # New browser created!
            pool.release("acc-rotate-test")

    def test_browser_pool_evict_removes_entry(self):
        """
        Layer 1: Explicit evict terminates browser and removes from active pool.
        """
        from integrations.backend.services.linkedin_pool import BrowserPool

        pool = BrowserPool(max_size=2)
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_context.new_page.return_value = MagicMock()

        with patch("integrations.backend.services.linkedin_pool.sync_playwright") as mock_sync_pw:
            mock_sync_pw.return_value.start.return_value = MagicMock()
            pool.acquire("acc-evict-test", lambda pw: (mock_browser, mock_context), proxy_url="http://p:8080")
            self.assertIn("acc-evict-test", pool.pool)

            pool.evict("acc-evict-test")
            self.assertNotIn("acc-evict-test", pool.pool)
            mock_context.close.assert_called_once()
            mock_browser.close.assert_called_once()

    def test_parse_playwright_proxy_normalizes_socks5h_to_socks5(self):
        """
        Layer 0 & 1: socks5h (remote DNS) normalizes to socks5 for Playwright Chromium.
        """
        parsed = parse_playwright_proxy("socks5h://user:pass@185.1.2.3:1080")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["server"], "socks5://185.1.2.3:1080")
        self.assertEqual(parsed["username"], "user")
        self.assertEqual(parsed["password"], "pass")

    # =========================================================================
    # 4 Hardened Architectural Vectors: Extension Guard, Rotating Flapping,
    # HTTP/2 + Regional Timezone Matching, and Gateway Error Classification
    # =========================================================================

    def test_orchestrator_yields_for_extension_channel(self):
        """
        Vector 1: When an account's execution_channel == 'EXTENSION', the cloud orchestrator
        must NOT run Playwright; it must yield the state back to the Chrome Extension dispatcher.
        """
        from campaigns.backend.services.elein_orchestrator import EleInOrchestrator

        mock_supabase = MagicMock()
        mock_acc_res = MagicMock()
        mock_acc_res.data = [{
            "id": "acc-ext-1",
            "workspace_id": "ws-1",
            "status": "ACTIVE",
            "execution_channel": "EXTENSION",
            "proxy_id": None,
            "session_cookies_encrypted": None
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_acc_res
        mock_supabase.rpc().execute.return_value = MagicMock(data=True)

        orch = EleInOrchestrator(supabase=mock_supabase)
        mock_state = {
            "id": "state-ext-1",
            "workspace_id": "ws-1",
            "opportunity_id": "opp-1",
            "campaign_id": "camp-1"
        }

        with patch("campaigns.backend.services.elein_orchestrator.try_acquire_session_lock", return_value=True), \
             patch("campaigns.backend.services.elein_orchestrator.release_session_lock"):
            res = orch.execute_node_action(
                action="send_message",
                data={"body": "Hello {{first_name}}"},
                opportunity_id="opp-1",
                account_id="acc-ext-1",
                state=mock_state,
                lease_token="lease-123",
                current_node_id="node-1"
            )
            self.assertEqual(res.get("status"), "skipped")
            self.assertEqual(res.get("reason"), "extension_delegated")

    def test_probe_proxy_health_detects_rotating_flapping_proxy(self):
        """
        Vector 2: Two-ping drift detection. If exit IP mutates between two pings
        200ms apart, the proxy is classified as 'rotating_flapping' and rejected.
        """
        from accounts.backend.services.account_auto_heal_service import probe_proxy_health
        import httpx

        mock_robots = MagicMock(status_code=200)
        mock_ip_1 = MagicMock(status_code=200, json=lambda: {"ip": "185.10.10.1"})
        mock_ip_2 = MagicMock(status_code=200, json=lambda: {"ip": "185.10.10.2"})  # Mutated IP!

        proxy = {"host": "rotating-proxy.io", "port": 8080, "protocol": "http"}

        with patch("accounts.backend.services.account_auto_heal_service.httpx.Client") as mock_client_cls, \
             patch("accounts.backend.services.account_auto_heal_service.time.sleep"):
            mock_client = MagicMock()
            mock_client.get.side_effect = [mock_robots, mock_ip_1, mock_ip_2]
            mock_client_cls.return_value.__enter__.return_value = mock_client

            res = probe_proxy_health(proxy)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "rotating_flapping")
            self.assertIn("Rotating proxy detected", res["error"])
            self.assertIn("185.10.10.1 to 185.10.10.2", res["error"])

    def test_probe_proxy_health_stable_static_ip_passes(self):
        """
        Vector 2: If exit IP remains identical across both pings, proxy passes as healthy.
        """
        from accounts.backend.services.account_auto_heal_service import probe_proxy_health

        mock_robots = MagicMock(status_code=200)
        mock_ip_1 = MagicMock(status_code=200, json=lambda: {"ip": "185.10.10.1"})
        mock_ip_2 = MagicMock(status_code=200, json=lambda: {"ip": "185.10.10.1"})  # Stable IP

        proxy = {"host": "static-proxy.io", "port": 8080, "protocol": "http"}

        with patch("accounts.backend.services.account_auto_heal_service.httpx.Client") as mock_client_cls, \
             patch("accounts.backend.services.account_auto_heal_service.time.sleep"):
            mock_client = MagicMock()
            mock_client.get.side_effect = [mock_robots, mock_ip_1, mock_ip_2]
            mock_client_cls.return_value.__enter__.return_value = mock_client

            res = probe_proxy_health(proxy)
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "healthy")
            self.assertEqual(res["exit_ip"], "185.10.10.1")

    def test_http_get_enables_http2_negotiation(self):
        """
        Vector 3: _http_get must pass http2=True to httpx.Client to prevent Akamai JA3 mismatch.
        """
        from integrations.backend.services.linkedin_worker import LinkedInWorker

        worker = LinkedInWorker(
            cookies_json=json.dumps([
                {"name": "li_at", "value": "val1"},
                {"name": "JSESSIONID", "value": '"val2"'}
            ]),
            proxy_url="http://185.1.2.3:8080",
            account_id="acc-h2-test"
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MagicMock(status_code=200)
            mock_client_cls.return_value = mock_client

            worker._http_get("https://www.linkedin.com/voyager/api/me")
            self.assertTrue(mock_client_cls.call_args[1].get("http2"))

    def test_resolve_browser_profile_subnational_and_regional_mapping(self):
        """
        Vector 3: Regional sub-national codes (US-CA, CA-BC, AU-VIC) resolve to accurate
        regional timezones and geolocations, preventing regional timezone-IP drift.
        """
        from integrations.backend.services.linkedin_worker import resolve_browser_profile

        # California
        ca_profile = resolve_browser_profile("US-CA")
        self.assertEqual(ca_profile["timezone_id"], "America/Los_Angeles")
        self.assertAlmostEqual(ca_profile["geo"]["latitude"], 34.0522, places=2)

        # New York (with underscore normalization)
        ny_profile = resolve_browser_profile("US_NY")
        self.assertEqual(ny_profile["timezone_id"], "America/New_York")
        self.assertAlmostEqual(ny_profile["geo"]["latitude"], 40.7128, places=2)

        # British Columbia
        bc_profile = resolve_browser_profile("CA-BC")
        self.assertEqual(bc_profile["timezone_id"], "America/Vancouver")

        # Victoria, Australia
        vic_profile = resolve_browser_profile("AU-VIC")
        self.assertEqual(vic_profile["timezone_id"], "Australia/Melbourne")

        # Explicit custom timezone override
        custom_profile = resolve_browser_profile("US", timezone="America/Chicago")
        self.assertEqual(custom_profile["timezone_id"], "America/Chicago")
        self.assertAlmostEqual(custom_profile["geo"]["latitude"], 41.8781, places=2)

    def test_probe_proxy_health_classifies_407_auth_failed(self):
        """
        Vector 4: Proxy gateway HTTP 407 (Proxy Authentication Required) is classified
        distinctly as 'auth_failed' instead of a generic failure or LinkedIn ban.
        """
        from accounts.backend.services.account_auto_heal_service import probe_proxy_health
        import httpx

        proxy = {"host": "bad-auth.io", "port": 8080, "protocol": "http"}

        # Case A: Status code 407 returned
        mock_resp_407 = MagicMock(status_code=407)
        with patch("accounts.backend.services.account_auto_heal_service.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp_407
            mock_client_cls.return_value.__enter__.return_value = mock_client

            res = probe_proxy_health(proxy)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "auth_failed")
            self.assertIn("407", res["error"])

        # Case B: ProxyError with 407 raised
        with patch("accounts.backend.services.account_auto_heal_service.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ProxyError("407 Proxy Authentication Required")
            mock_client_cls.return_value.__enter__.return_value = mock_client

            res = probe_proxy_health(proxy)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "auth_failed")
            self.assertIn("Proxy Authentication Required", res["error"])

    def test_probe_proxy_health_classifies_402_and_429_quota_exceeded(self):
        """
        Vector 4: Proxy provider quota exhaustion (HTTP 402) or concurrency limits (HTTP 429)
        are classified as 'quota_exceeded' to alert operators to top up bandwidth.
        """
        from accounts.backend.services.account_auto_heal_service import probe_proxy_health
        import httpx

        proxy = {"host": "depleted-provider.io", "port": 8080, "protocol": "http"}

        # HTTP 402 Payment Required
        mock_resp_402 = MagicMock(status_code=402)
        with patch("accounts.backend.services.account_auto_heal_service.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp_402
            mock_client_cls.return_value.__enter__.return_value = mock_client

            res = probe_proxy_health(proxy)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "quota_exceeded")
            self.assertIn("quota depleted", res["error"])

        # HTTP 429 Too Many Requests (Concurrency cap)
        mock_resp_429 = MagicMock(status_code=429)
        with patch("accounts.backend.services.account_auto_heal_service.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp_429
            mock_client_cls.return_value.__enter__.return_value = mock_client

            res = probe_proxy_health(proxy)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "quota_exceeded")
            self.assertIn("rate limited", res["error"])


if __name__ == "__main__":
    unittest.main()
