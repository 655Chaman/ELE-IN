import unittest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from collections import defaultdict

from core.backend.services.proxy_routing import (
    extract_ip_subnet,
    extract_ipv4_slash24,
    record_provider_failure,
    record_provider_success,
    is_provider_healthy,
    reset_provider_circuits,
    calculate_pool_subnet_diversity,
    find_sticky_failover_proxy,
    validate_and_normalize_proxy_host
)
from integrations.backend.services.webshare_sync import (
    handle_webshare_webhook_payload
)
from core.backend.services.auto_cooling import (
    calculate_backoff_cooldown,
    probe_and_recover_degraded_proxies,
    run_auto_cooling_daemon
)
from core.backend.api.routers.proxies import _verify_webshare_webhook_secret
from fastapi import HTTPException


class TestPillar1ProxyFleetHardening(unittest.TestCase):
    """
    Three-Layer Paranoia Framework: Pillar 1 Test Suite
    - Phase 1.1: Webshare Automated Sync & Webhook Ingestion
    - Phase 1.2: Multi-Provider Redundancy & Tiered Failover
    - Phase 1.3: Regional /24 & /64 Subnet Isolation Algorithm
    - Phase 1.4: Background Auto-Cooling Daemon & Jittered Probing
    """

    def setUp(self):
        reset_provider_circuits()

    # =========================================================================
    # PHASE 1.1: WEBSHARE AUTOMATED SYNC & WEBHOOK INGESTION
    # =========================================================================

    def test_webshare_webhook_replacement_rebinds_active_accounts(self):
        """
        Layer 1 (Environmental): When Webshare rotates a proxy, accounts bound to old proxy
        must be atomically migrated to the new proxy to prevent active campaign crashes.
        """
        mock_supabase = MagicMock()
        
        # 1. Old proxy exists with ID 'px-old-1'
        mock_old_proxy = MagicMock()
        mock_old_proxy.data = [{"id": "px-old-1", "host": "185.220.101.5", "port": 8000}]
        
        # 2. Account 'acc-vip' is assigned to 'px-old-1'
        mock_accounts = MagicMock()
        mock_accounts.data = [{"id": "acc-vip", "name": "Captain Sales Rep", "proxy_id": "px-old-1"}]
        
        # 3. New proxy insert/upsert returns 'px-new-1'
        mock_new_proxy = MagicMock()
        mock_new_proxy.data = [{"id": "px-new-1"}]

        def table_side_effect(table_name):
            t_mock = MagicMock()
            if table_name == "proxies":
                q_mock = MagicMock()
                q_mock.eq.return_value = q_mock
                q_mock.execute.return_value = mock_old_proxy
                t_mock.select.return_value = q_mock
                t_mock.upsert.return_value.execute.return_value = mock_new_proxy
                t_mock.insert.return_value.execute.return_value = mock_new_proxy
                t_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            elif table_name == "accounts":
                q_mock = MagicMock()
                q_mock.eq.return_value = q_mock
                q_mock.execute.return_value = mock_accounts
                t_mock.select.return_value = q_mock
                t_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            return t_mock

        mock_supabase.table.side_effect = table_side_effect
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data="vault-secret-dek-1")

        payload = {
            "event": "proxy_replaced",
            "workspace_id": "ws-alpha",
            "old_proxy": {"proxy_address": "185.220.101.5", "port": 8000},
            "new_proxy": {
                "proxy_address": "185.220.101.99",
                "port": 8080,
                "username": "webshare_user",
                "password": "secret_pass_123",
                "country_code": "US",
                "valid": True
            }
        }

        with patch("core.backend.core.crypto.encrypt_bytes", return_value=b"encrypted_cipher"):
            res = handle_webshare_webhook_payload(payload, mock_supabase, workspace_id="ws-alpha")

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["event"], "proxy_replaced")
        self.assertIn("acc-vip", res["migrated_accounts"])
        self.assertEqual(res["count_migrated"], 1)

    def test_webshare_webhook_ssrf_injection_rejected(self):
        """
        Layer 2 (Human & Attack Defense): Reject link-local / loopback addresses in webhook payloads.
        """
        mock_supabase = MagicMock()
        payload = {
            "event": "proxy_replaced",
            "new_proxy": {
                "proxy_address": "169.254.169.254", # AWS metadata SSRF attempt
                "port": 80
            }
        }

        with self.assertRaises(ValueError) as ctx:
            handle_webshare_webhook_payload(payload, mock_supabase, workspace_id="ws-alpha")
        self.assertIn("SSRF Guard", str(ctx.exception))

    def test_webshare_webhook_secret_verification(self):
        """
        Layer 2: Constant-time authentication verifies matching secret and rejects spoofed tokens.
        """
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"api_key": "super-secure-token-123"}]
        )

        # 1. Valid Bearer Token
        valid = _verify_webshare_webhook_secret(
            authorization="Bearer super-secure-token-123",
            x_webshare_signature=None,
            token=None,
            supabase=mock_supabase
        )
        self.assertTrue(valid)

        # 2. Invalid Token -> HTTP 401
        with self.assertRaises(HTTPException) as ctx:
            _verify_webshare_webhook_secret(
                authorization="Bearer wrong-hacker-token",
                x_webshare_signature=None,
                token=None,
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 401)

    # =========================================================================
    # PHASE 1.2: MULTI-PROVIDER REDUNDANCY & TIERED FAILOVER
    # =========================================================================

    def test_provider_circuit_breaker_trips_after_failures(self):
        """
        Layer 1: Provider circuit breaker trips after 3 consecutive failures.
        """
        provider = "webshare"
        self.assertTrue(is_provider_healthy(provider))

        record_provider_failure(provider, "Gateway Timeout 504")
        record_provider_failure(provider, "Connection Refused")
        self.assertTrue(is_provider_healthy(provider)) # 2 failures, still below threshold 3

        record_provider_failure(provider, "Proxy Auth 407 Exhaustion")
        self.assertFalse(is_provider_healthy(provider)) # Tripped!

        # Resetting or success clears circuit
        record_provider_success(provider)
        self.assertTrue(is_provider_healthy(provider))

    def test_tiered_provider_failover_same_country(self):
        """
        Layer 0 & 1: When preferred provider is circuit-tripped, failover routes to backup
        provider in the SAME country (US -> US), never cross-country drifting.
        """
        mock_supabase = MagicMock()
        
        # Webshare US proxy (tripped provider) and Oxylabs US proxy (healthy backup)
        proxies_data = [
            {
                "id": "px-webshare-us",
                "host": "198.51.100.10",
                "country_code": "US",
                "provider": "webshare",
                "is_active": True,
                "status": "healthy",
                "latency_ms": 100
            },
            {
                "id": "px-oxylabs-us",
                "host": "203.0.113.20",
                "country_code": "US",
                "provider": "oxylabs",
                "is_active": True,
                "status": "healthy",
                "latency_ms": 150
            }
        ]
        
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=proxies_data)
        mock_supabase.table().select().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        # Trip webshare circuit breaker
        for _ in range(3):
            record_provider_failure("webshare", "Provider outage")

        chosen = find_sticky_failover_proxy(
            mock_supabase,
            workspace_id="ws-prod",
            target_country="US",
            preferred_provider="webshare"
        )

        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "px-oxylabs-us")
        self.assertEqual(chosen["provider"], "oxylabs")
        self.assertEqual(chosen["country_code"], "US")

    def test_cross_country_drift_prevented_across_providers(self):
        """
        Layer 1 (The Drift Guard): When all proxies in target country (US) are exhausted,
        the system refuses to assign a UK or DE proxy unless allow_cross_country_drift=True.
        """
        mock_supabase = MagicMock()
        proxies_data = [
            {
                "id": "px-uk-1",
                "host": "185.220.101.5",
                "country_code": "GB",
                "provider": "oxylabs",
                "is_active": True,
                "status": "healthy"
            }
        ]
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=proxies_data)
        mock_supabase.table().select().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        chosen = find_sticky_failover_proxy(
            mock_supabase,
            workspace_id="ws-prod",
            target_country="US",
            allow_cross_country_drift=False
        )

        self.assertIsNone(chosen)

    # =========================================================================
    # PHASE 1.3: REGIONAL /24 & /64 SUBNET ISOLATION ALGORITHM
    # =========================================================================

    def test_extract_ip_subnet_ipv4_and_ipv6(self):
        """
        Layer 0 & 2: Subnet prefix extraction handles IPv4 /24 and IPv6 /64 correctly.
        """
        # IPv4
        self.assertEqual(extract_ip_subnet("198.51.100.42"), "198.51.100")
        self.assertEqual(extract_ipv4_slash24("203.0.113.199"), "203.0.113")
        
        # IPv6
        ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        self.assertEqual(extract_ip_subnet(ipv6), "2001:0db8:85a3:0000")

        # Hostname with port
        self.assertEqual(extract_ip_subnet("proxy.us-east.webshare.io:8080"), "webshare.io")

    def test_find_sticky_failover_avoids_workspace_subnet_collisions(self):
        """
        Layer 1 & 2: If Rep A is on subnet 198.51.100, Rep B must be assigned a proxy
        on a different subnet (e.g. 203.0.113) to avoid LinkedIn linked correlation bans.
        """
        mock_supabase = MagicMock()
        
        # Candidate 1: Shares subnet 198.51.100 with Rep A
        # Candidate 2: Fresh subnet 203.0.113
        proxies_data = [
            {
                "id": "px-crowded-subnet",
                "host": "198.51.100.99",
                "country_code": "US",
                "subnet": "198.51.100",
                "is_active": True,
                "status": "healthy",
                "latency_ms": 50
            },
            {
                "id": "px-clean-subnet",
                "host": "203.0.113.15",
                "country_code": "US",
                "subnet": "203.0.113",
                "is_active": True,
                "status": "healthy",
                "latency_ms": 120
            }
        ]

        def table_call(table_name):
            m = MagicMock()
            if table_name == "proxies":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=proxies_data)
            elif table_name == "accounts":
                # Active accounts in workspace: Account 1 is on proxy with subnet 198.51.100
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"proxy_id": "px-crowded-subnet"}]
                )
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_supabase.table.side_effect = table_call

        chosen = find_sticky_failover_proxy(
            mock_supabase,
            workspace_id="ws-team",
            target_country="US"
        )

        self.assertIsNotNone(chosen)
        # Must pick clean subnet even though candidate 1 had lower latency (50ms vs 120ms)
        self.assertEqual(chosen["id"], "px-clean-subnet")
        self.assertEqual(chosen["subnet"], "203.0.113")

    def test_calculate_pool_subnet_diversity(self):
        """
        Layer 2: Subnet diversity metric identifies duplicate subnets and calculates ratio.
        """
        pool = [
            {"host": "198.51.100.1"},
            {"host": "198.51.100.2"}, # Duplicate subnet
            {"host": "203.0.113.1"},
            {"host": "192.0.2.1"}
        ]
        res = calculate_pool_subnet_diversity(pool)
        self.assertEqual(res["total_proxies"], 4)
        self.assertEqual(res["unique_subnets"], 3)
        self.assertEqual(res["diversity_ratio"], 0.75)
        self.assertIn("198.51.100", res["colliding_subnets"])

    # =========================================================================
    # PHASE 1.4: BACKGROUND AUTO-COOLING DAEMON & JITTERED PROBING
    # =========================================================================

    def test_calculate_backoff_cooldown_exponential(self):
        """
        Layer 1: Backoff scales exponentially: 2h, 4h, 8h, capped at 24h.
        """
        p0 = {"failure_count": 0}
        self.assertEqual(calculate_backoff_cooldown(p0, base_hours=2), 2)

        p1 = {"failure_count": 1}
        self.assertEqual(calculate_backoff_cooldown(p1, base_hours=2), 4)

        p2 = {"failure_count": 2}
        self.assertEqual(calculate_backoff_cooldown(p2, base_hours=2), 8)

        p3 = {"failure_count": 3}
        self.assertEqual(calculate_backoff_cooldown(p3, base_hours=2), 16)

        p4 = {"failure_count": 10}
        self.assertEqual(calculate_backoff_cooldown(p4, base_hours=2), 24)

        # Quota exceeded min 6h
        p_quota = {"failure_count": 0, "status": "quota_exceeded"}
        self.assertEqual(calculate_backoff_cooldown(p_quota, base_hours=2), 6)

        # Auth failed min 12h
        p_auth = {"failure_count": 0, "status": "auth_failed"}
        self.assertEqual(calculate_backoff_cooldown(p_auth, base_hours=2), 12)

    def test_probe_and_recover_preserves_cooldown_with_backoff(self):
        """
        Layer 1: When a proxy with 2 failures (8h backoff) has only waited 3 hours,
        it must NOT be probed or recovered early.
        """
        mock_supabase = MagicMock()
        recent_check = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        
        mock_supabase.table().select().in_().execute.return_value = MagicMock(
            data=[
                {
                    "id": "px-repeat-failure",
                    "host": "198.51.100.5",
                    "port": 8080,
                    "status": "degraded",
                    "failure_count": 2, # Requires 8h backoff
                    "last_checked_at": recent_check
                }
            ]
        )

        recovered = probe_and_recover_degraded_proxies(mock_supabase, cooldown_hours=2)
        self.assertEqual(len(recovered), 0)

    def test_probe_and_recover_auth_failed_without_credentials_skips(self):
        """
        Layer 2 Paranoia: Never probe an auth_failed proxy if password ciphertext is missing.
        """
        mock_supabase = MagicMock()
        old_check = (datetime.utcnow() - timedelta(hours=20)).isoformat()
        
        mock_supabase.table().select().in_().execute.return_value = MagicMock(
            data=[
                {
                    "id": "px-no-creds",
                    "host": "198.51.100.5",
                    "port": 8080,
                    "status": "auth_failed",
                    "username": "user",
                    "password_encrypted": None,
                    "secret_ref": None,
                    "failure_count": 1,
                    "last_checked_at": old_check
                }
            ]
        )

        with patch("accounts.backend.services.account_auto_heal_service.probe_proxy_health") as mock_probe:
            recovered = probe_and_recover_degraded_proxies(mock_supabase, cooldown_hours=2)
            mock_probe.assert_not_called()
            self.assertEqual(len(recovered), 0)

    def test_auto_cooling_daemon_stops_cleanly_on_event(self):
        """
        Layer 0 & 1: Daemon completes iteration and stops cleanly when stop_event is set.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])
        mock_supabase.table().select().in_().execute.return_value = MagicMock(data=[])

        async def run_test():
            stop_event = asyncio.Event()
            stop_event.set() # Stop immediately after first check
            await run_auto_cooling_daemon(
                supabase_client=mock_supabase,
                interval_seconds=1,
                stop_event=stop_event,
                probe_jitter_seconds=0.01
            )
            return stop_event.is_set()

        completed = asyncio.run(run_test())
        # Reaching here means clean exit without hanging!
        self.assertTrue(completed)


if __name__ == "__main__":
    unittest.main()
