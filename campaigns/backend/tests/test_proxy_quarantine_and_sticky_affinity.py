import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, ANY

from core.backend.services.proxy_routing import (
    is_proxy_quarantined,
    quarantine_proxy,
    find_sticky_failover_proxy,
)
from core.backend.services.auto_cooling import probe_and_recover_degraded_proxies
from accounts.backend.services.account_auto_heal_service import probe_proxy_health


class TestProxyQuarantineAndStickyAffinity(unittest.TestCase):

    def test_quarantine_proxy_sets_quarantined_status_and_time(self):
        """Paranoia Layer 1: Quarantines proxy with 2-hour cooldown and reason."""
        mock_supabase = MagicMock()
        update_mock = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        ok = quarantine_proxy(mock_supabase, "proxy-123", reason="security_challenge", cooldown_hours=2)
        self.assertTrue(ok)

        mock_supabase.table.assert_called_with("proxies")
        update_args = mock_supabase.table().update.call_args[0][0]
        self.assertEqual(update_args["status"], "quarantined")
        self.assertFalse(update_args["is_active"])
        self.assertEqual(update_args["quarantine_reason"], "security_challenge")
        self.assertIn("quarantined_until", update_args)
        self.assertIn("last_checked_at", update_args)

        # Verify quarantined_until is ~2 hours in the future
        q_until = datetime.fromisoformat(update_args["quarantined_until"])
        now = datetime.now(timezone.utc)
        self.assertTrue(q_until > now + timedelta(hours=1, minutes=50))
        self.assertTrue(q_until <= now + timedelta(hours=2, minutes=5))

    def test_is_proxy_quarantined_detects_active_and_expired(self):
        """Paranoia Layer 1: Correctly identifies active vs expired quarantine."""
        now = datetime.now(timezone.utc)

        # 1. Future quarantine -> Active
        active_proxy = {
            "id": "p-1",
            "status": "quarantined",
            "quarantined_until": (now + timedelta(hours=1)).isoformat()
        }
        self.assertTrue(is_proxy_quarantined(active_proxy))

        # 2. ISO string ending in 'Z'
        active_proxy_z = {
            "id": "p-2",
            "status": "quarantined",
            "quarantined_until": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        }
        self.assertTrue(is_proxy_quarantined(active_proxy_z))

        # 3. Past quarantine -> Expired
        expired_proxy = {
            "id": "p-3",
            "status": "quarantined",
            "quarantined_until": (now - timedelta(hours=1)).isoformat()
        }
        self.assertFalse(is_proxy_quarantined(expired_proxy))

        # 4. Status quarantined with no timestamp -> Quarantined
        no_time_proxy = {
            "id": "p-4",
            "status": "quarantined",
            "quarantined_until": None
        }
        self.assertTrue(is_proxy_quarantined(no_time_proxy))

        # 5. Healthy proxy -> Not quarantined
        healthy_proxy = {
            "id": "p-5",
            "status": "healthy",
            "quarantined_until": None
        }
        self.assertFalse(is_proxy_quarantined(healthy_proxy))

        # 6. None / empty -> Not quarantined
        self.assertFalse(is_proxy_quarantined({}))
        self.assertFalse(is_proxy_quarantined(None))

    def test_find_sticky_failover_excludes_quarantined_proxies(self):
        """Paranoia Layer 1: Excludes degraded and quarantined proxies from failover."""
        now = datetime.now(timezone.utc)
        proxies_data = [
            {"id": "px-quarantined", "status": "quarantined", "is_active": True, "country_code": "US", "quarantined_until": (now + timedelta(hours=1)).isoformat()},
            {"id": "px-degraded", "status": "degraded", "is_active": True, "country_code": "US"},
            {"id": "px-healthy", "status": "healthy", "is_active": True, "country_code": "US", "latency_ms": 200, "host": "1.2.3.4"}
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

        chosen = find_sticky_failover_proxy(mock_supabase, "ws-1", current_proxy_id="px-old", target_country="US")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "px-healthy")

    def test_find_sticky_failover_preserves_country_affinity(self):
        """Paranoia Layer 0: Preserves matching country code for geo-consistency."""
        proxies_data = [
            {"id": "px-gb", "status": "healthy", "is_active": True, "country_code": "GB", "latency_ms": 150},
            {"id": "px-us", "status": "healthy", "is_active": True, "country_code": "US", "latency_ms": 250},
            {"id": "px-de", "status": "healthy", "is_active": True, "country_code": "DE", "latency_ms": 100}
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

        chosen = find_sticky_failover_proxy(mock_supabase, "ws-1", target_country="US")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "px-us")
        self.assertEqual(chosen["country_code"], "US")

    def test_find_sticky_failover_blocks_cross_country_drift_by_default(self):
        """Paranoia Layer 1: Blocks cross-country drift when matching country proxy unavailable."""
        proxies_data = [
            {"id": "px-gb", "status": "healthy", "is_active": True, "country_code": "GB", "latency_ms": 150},
            {"id": "px-de", "status": "healthy", "is_active": True, "country_code": "DE", "latency_ms": 100}
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

        # Target country US has no proxies, allow_cross_country_drift=False -> None
        chosen = find_sticky_failover_proxy(mock_supabase, "ws-1", target_country="US", allow_cross_country_drift=False)
        self.assertIsNone(chosen)

    def test_find_sticky_failover_allows_cross_country_when_flagged(self):
        """Paranoia Layer 1: Permits cross-country fallback only when explicitly flagged."""
        proxies_data = [
            {"id": "px-gb", "status": "healthy", "is_active": True, "country_code": "GB", "latency_ms": 150}
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

        chosen = find_sticky_failover_proxy(mock_supabase, "ws-1", target_country="US", allow_cross_country_drift=True)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "px-gb")

    def test_least_loaded_proxy_selection(self):
        """Paranoia Layer 0: Chooses proxy with lowest account load to avoid dogpiling."""
        proxies_data = [
            {"id": "px-heavy", "status": "healthy", "is_active": True, "country_code": "US", "latency_ms": 100},
            {"id": "px-light", "status": "healthy", "is_active": True, "country_code": "US", "latency_ms": 150}
        ]
        accounts_data = [
            {"proxy_id": "px-heavy"},
            {"proxy_id": "px-heavy"},
            {"proxy_id": "px-heavy"}
        ]

        mock_supabase = MagicMock()
        def mock_table(table_name):
            m = MagicMock()
            if table_name == "proxies":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=proxies_data)
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=proxies_data)
            elif table_name == "accounts":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=accounts_data)
            return m
        mock_supabase.table.side_effect = mock_table

        chosen = find_sticky_failover_proxy(mock_supabase, "ws-1", target_country="US")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["id"], "px-light")

    def test_auto_cooling_skips_unexpired_quarantine(self):
        """Paranoia Layer 1: Auto cooling does not un-quarantine proxies before their cooldown expires."""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        quarantined_proxy = {
            "id": "px-active-q",
            "status": "quarantined",
            "quarantined_until": future_time,
            "last_checked_at": datetime.utcnow().isoformat()
        }

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[quarantined_proxy]
        )

        recovered = probe_and_recover_degraded_proxies(mock_supabase, cooldown_hours=2)
        self.assertEqual(recovered, [])
        mock_supabase.table().update.assert_not_called()

    def test_auto_cooling_recovers_expired_quarantine(self):
        """Paranoia Layer 1: Auto cooling restores quarantined proxy after cooldown expires."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        expired_proxy = {
            "id": "px-expired-q",
            "status": "quarantined",
            "quarantined_until": past_time,
            "quarantine_reason": "security_challenge"
        }

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[expired_proxy]
        )
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        recovered = probe_and_recover_degraded_proxies(mock_supabase, cooldown_hours=2)
        self.assertIn("px-expired-q", recovered)
        mock_supabase.table.assert_called_with("proxies")
        update_args = mock_supabase.table().update.call_args[0][0]
        self.assertEqual(update_args["status"], "healthy")
        self.assertTrue(update_args["is_active"])
        self.assertIsNone(update_args["quarantined_until"])
        self.assertIsNone(update_args["quarantine_reason"])

    @patch("core.backend.services.proxy_routing.quarantine_proxy")
    def test_security_challenge_in_orchestrator_triggers_quarantine(self, mock_quarantine):
        """Paranoia Layer 1: security_challenge triggers immediate proxy quarantine."""
        from campaigns.backend.services.elein_orchestrator import EleInOrchestrator

        mock_supabase = MagicMock()
        def mock_table(table_name):
            m = MagicMock()
            if table_name == "campaigns":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "ACTIVE"}])
            elif table_name == "accounts":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"proxy_id": "proxy-tainted"}])
            return m
        mock_supabase.table.side_effect = mock_table

        orchestrator = EleInOrchestrator(supabase=mock_supabase)
        orchestrator.mark_error = MagicMock()
        orchestrator.execute_node_action = MagicMock(return_value={
            "status": "security_challenge",
            "error": "Checkpoint challenge detected"
        })

        state = {
            "id": "state-123",
            "campaign_id": "camp-123",
            "workspace_id": "ws-123",
            "nodes": [{"id": "node-1", "type": "custom_action", "data": {}}],
            "edges": [],
            "current_node_id": "node-1",
            "sender_id": "acc-1",
            "account_id": "acc-1",
            "opportunity_id": "opp-1",
            "attempts": 0,
            "max_attempts": 5,
            "variables": {}
        }

        orchestrator.process_lead(state, "lease-123")

        mock_quarantine.assert_called_once_with(
            mock_supabase,
            "proxy-tainted",
            reason="security_challenge",
            cooldown_hours=2
        )
        orchestrator.mark_error.assert_called_once()

    @patch("accounts.backend.services.account_auto_heal_service.time.perf_counter")
    @patch("accounts.backend.services.account_auto_heal_service.httpx.Client")
    def test_probe_proxy_health_flags_high_latency_as_degraded(self, mock_client_cls, mock_perf):
        """Paranoia Layer 2: High latency (> 2500ms) flags proxy as degraded."""
        # Simulate 2.7s elapsed time
        mock_perf.side_effect = [0.0, 2.7, 2.7, 2.7, 2.7, 2.7, 2.7]

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        proxy = {
            "id": "px-slow",
            "host": "192.168.1.50",
            "port": 8080,
            "protocol": "http",
            "country_code": "US"
        }

        res = probe_proxy_health(proxy)
        self.assertEqual(res["status"], "degraded")
        self.assertGreater(res["latency_ms"], 2500)
        self.assertIn("High latency detected", res["error"])


if __name__ == "__main__":
    unittest.main()
