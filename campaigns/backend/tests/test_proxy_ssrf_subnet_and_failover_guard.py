import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
from fastapi import HTTPException

from core.backend.services.proxy_routing import (
    validate_and_normalize_proxy_host,
    extract_ipv4_slash24,
    find_sticky_failover_proxy,
)
from core.backend.api.routers.proxies import (
    create_proxy,
    delete_proxy,
    test_raw_proxy_config as api_test_raw_proxy_config,
    ProxyCreate,
    ProxyTestRequest,
)


class TestProxySSRFSubnetAndFailoverGuard(unittest.TestCase):
    """
    Step 35 Track B — Residential Proxy Pool SSRF/Private-IP Guard,
    /24 Subnet Collision Avoidance, Max-Load Cap & Active-Account Deletion Failover.
    """

    # =========================================================================
    # 1. SSRF, Private IP & Cloud Metadata Guard (Layer 1 & Layer 2)
    # =========================================================================

    def test_validate_proxy_host_blocks_loopback_and_localhost(self):
        """Blocks 127.0.0.1, ::1, and localhost to prevent SSRF against local services."""
        for bad_host in ("127.0.0.1", "127.0.1.1", "::1", "localhost", "api.localhost", "redis.internal"):
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {bad_host}"):
                validate_and_normalize_proxy_host(bad_host)

    def test_validate_proxy_host_blocks_cloud_metadata_and_private_ranges(self):
        """Blocks AWS/GCP metadata IP (169.254.169.254) and RFC1918 private IPs."""
        for bad_ip in ("169.254.169.254", "10.0.0.1", "172.16.0.5", "192.168.1.100", "0.0.0.0"):
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {bad_ip}"):
                validate_and_normalize_proxy_host(bad_ip)

    def test_validate_proxy_host_normalizes_pasted_url_and_valid_public_host(self):
        """Strips accidental protocol/port when operator pastes http://proxy.isp.com:8080 into host field."""
        self.assertEqual(
            validate_and_normalize_proxy_host("  http://Gate.SmartProxy.com:7000/  "),
            "gate.smartproxy.com"
        )
        self.assertEqual(
            validate_and_normalize_proxy_host("185.199.108.153"),
            "185.199.108.153"
        )

    def test_test_raw_proxy_config_rejects_ssrf_metadata_ip(self):
        """/proxies/test-config blocks probing 169.254.169.254 with HTTP 400."""
        mock_supabase = MagicMock()
        req = ProxyTestRequest(host="169.254.169.254", port=80, protocol="http")
        with self.assertRaises(HTTPException) as ctx:
            api_test_raw_proxy_config(req, mock_supabase, "ws_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("SSRF", ctx.exception.detail)

    def test_create_proxy_rejects_duplicate_host_and_port_with_409(self):
        """Prevents registering duplicate (workspace_id, host, port) proxy entries with HTTP 409."""
        mock_supabase = MagicMock()
        tables = defaultdict(MagicMock)
        mock_supabase.table.side_effect = lambda name: tables[name]

        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO"}]
        )
        tables["proxies"].select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "px_existing", "host": "185.199.108.10", "port": 8080}]
        )

        payload = ProxyCreate(provider="webshare", host="185.199.108.10", port=8080, protocol="http")
        with self.assertRaises(HTTPException) as ctx:
            create_proxy(payload, mock_supabase, "ws_pro")
        self.assertEqual(ctx.exception.status_code, 409)

    # =========================================================================
    # 2. /24 Subnet Collision Avoidance & Max-Accounts Cap (Layer 1)
    # =========================================================================

    def test_extract_ipv4_slash24(self):
        self.assertEqual(extract_ipv4_slash24("185.199.108.42"), "185.199.108")
        self.assertIsNone(extract_ipv4_slash24("gate.smartproxy.com"))

    def test_find_sticky_failover_avoids_same_slash24_subnet_as_tainted_proxy(self):
        """When failing over from 185.199.108.10, prefers a proxy in a different /24 subnet even if same-subnet has lower latency."""
        proxies_data = [
            {"id": "px-tainted", "status": "quarantined", "is_active": True, "country_code": "US", "host": "185.199.108.10"},
            {"id": "px-same-subnet", "status": "healthy", "is_active": True, "country_code": "US", "host": "185.199.108.25", "latency_ms": 80},
            {"id": "px-diff-subnet", "status": "healthy", "is_active": True, "country_code": "US", "host": "104.244.42.19", "latency_ms": 180},
        ]

        mock_supabase = MagicMock()
        def mock_table(table_name):
            m = MagicMock()
            if table_name == "proxies":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=proxies_data)
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=proxies_data)
            elif table_name == "accounts":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            return m
        mock_supabase.table.side_effect = mock_table

        chosen = find_sticky_failover_proxy(mock_supabase, "ws-1", current_proxy_id="px-tainted", target_country="US")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "px-diff-subnet")

    # =========================================================================
    # 3. Active-Account Deletion Protection & Sticky Auto-Migration (Layer 2)
    # =========================================================================

    def test_delete_proxy_blocks_with_409_when_bound_to_active_account_and_no_failover(self):
        """Blocks deleting a proxy assigned to an active LinkedIn account when no replacement proxy exists."""
        mock_supabase = MagicMock()
        tables = defaultdict(MagicMock)
        mock_supabase.table.side_effect = lambda name: tables[name]

        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_active_1", "proxy_id": "px_in_use", "proxy_country": "US"}]
        )
        # No replacement proxies available
        tables["proxies"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        tables["proxies"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            delete_proxy("px_in_use", mock_supabase, "ws_1", force=False)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("active LinkedIn account", ctx.exception.detail)

    def test_delete_proxy_auto_migrates_bound_accounts_when_healthy_failover_exists(self):
        """Automatically migrates bound LinkedIn accounts to a healthy sticky failover proxy upon deletion."""
        mock_supabase = MagicMock()
        tables = defaultdict(MagicMock)
        mock_supabase.table.side_effect = lambda name: tables[name]

        tables["accounts"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_active_1", "proxy_id": "px_old", "proxy_country": "US"}]
        )
        tables["accounts"].select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        proxies_pool = [
            {"id": "px_replacement_us", "status": "healthy", "is_active": True, "country_code": "US", "host": "104.244.42.10", "latency_ms": 120}
        ]
        tables["proxies"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=proxies_pool)
        tables["proxies"].delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "px_old"}]
        )

        res = delete_proxy("px_old", mock_supabase, "ws_1", force=False)
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res.get("migrated_accounts", [])), 1)
        self.assertEqual(res["migrated_accounts"][0]["new_proxy_id"], "px_replacement_us")
        tables["accounts"].update.assert_called_with({"proxy_id": "px_replacement_us"})


if __name__ == "__main__":
    unittest.main()
