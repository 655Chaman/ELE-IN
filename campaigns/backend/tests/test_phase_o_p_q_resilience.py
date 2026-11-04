import unittest
import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from integrations.backend.services.inbound_ingest_service import (
    stage_inbound_webhook,
    process_staged_inbound_webhooks,
    record_crm_dead_letter_event,
    replay_dead_letter_webhooks,
    get_crm_dlq_stats,
    clear_in_memory_buffers,
)
from campaigns.backend.routers.master_view import (
    get_workspace_rollup_summary,
    invalidate_master_view_cache,
    clear_master_view_cache,
)
from campaigns.backend.services.crm_attribution_service import (
    calculate_deal_attribution,
    stream_attribution_event,
)
from core.backend.services.proxy_routing import (
    probe_proxy_health_and_latency,
    check_and_auto_quarantine_proxy,
    assign_optimal_proxy_for_account,
    reset_proxy_failure_counts,
)
from integrations.backend.services.webshare_sync import (
    reconcile_and_probe_webshare_pool,
)


class TestPhaseOPQResilience(unittest.TestCase):

    def setUp(self):
        clear_in_memory_buffers()
        clear_master_view_cache()
        reset_proxy_failure_counts()

    # ── PHASE O TESTS: INBOUND WEBHOOK BUFFER & CRM DLQ ──────────────────────

    def test_stage_inbound_webhook_deduplication(self):
        """Paranoia Layer 1: Inbound buffer suppresses duplicate deliveries."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "buf-001"}]

        # First stage
        res1 = stage_inbound_webhook(
            supabase=mock_supabase,
            workspace_id="ws-test-o",
            platform="smartlead",
            platform_message_id="msg-101",
            payload={"event_type": "reply", "email": "lead@acme.com"}
        )
        self.assertEqual(res1["status"], "staged")

        # Second stage (in-memory deduplication)
        res2 = stage_inbound_webhook(
            supabase=mock_supabase,
            workspace_id="ws-test-o",
            platform="smartlead",
            platform_message_id="msg-101",
            payload={"event_type": "reply", "email": "lead@acme.com"}
        )
        self.assertEqual(res2["status"], "idempotent_duplicate")

    def test_stage_inbound_webhook_db_fallback_to_memory(self):
        """Paranoia Layer 1: Falls back safely to in-memory staging when DB fails."""
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("Database connection pool exhausted")

        res = stage_inbound_webhook(
            supabase=mock_supabase,
            workspace_id="ws-test-o",
            platform="sendgrid",
            platform_message_id="sg-999",
            payload={"event": "delivered", "email": "prospect@corp.com"}
        )
        self.assertEqual(res["status"], "staged")
        self.assertEqual(res["storage"], "memory_fallback")

    def test_process_staged_inbound_webhooks_dispatches_events(self):
        """Paranoia Layer 0: Staged webhooks drain asynchronously into target subsystems."""
        # Stage two items in memory
        stage_inbound_webhook(
            supabase=None,
            workspace_id="ws-test-o",
            platform="smartlead",
            platform_message_id="sl-1",
            payload={"event_type": "reply", "lead_email": "alice@startup.io", "campaign_id": "c-1"}
        )
        stage_inbound_webhook(
            supabase=None,
            workspace_id="ws-test-o",
            platform="sendgrid",
            platform_message_id="sg-1",
            payload={"event": "delivered", "email": "bob@startup.io"}
        )

        res = process_staged_inbound_webhooks(supabase=None, workspace_id="ws-test-o", limit=10)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["processed_count"], 2)
        self.assertEqual(res["success_count"], 2)
        self.assertEqual(res["failed_count"], 0)

    def test_crm_dead_letter_queue_exponential_backoff(self):
        """Paranoia Layer 1: Consecutive failures calculate exponential backoff."""
        # 1st attempt: 60 * 2^1 = 120s
        res1 = record_crm_dead_letter_event(
            supabase=None,
            workspace_id="ws-test-o",
            provider="hubspot",
            entity_type="deal",
            entity_id="deal-555",
            payload={"stage": "closed_won"},
            error_message="HubSpot API rate limit 429",
            status_code=429
        )
        self.assertEqual(res1["status"], "recorded")
        self.assertEqual(res1["retry_count"], 1)
        self.assertEqual(res1["dlq_status"], "pending")

        # 2nd attempt: 60 * 2^2 = 240s
        res2 = record_crm_dead_letter_event(
            supabase=None,
            workspace_id="ws-test-o",
            provider="hubspot",
            entity_type="deal",
            entity_id="deal-555",
            payload={"stage": "closed_won"},
            error_message="HubSpot API rate limit 429",
            status_code=429
        )
        self.assertEqual(res2["retry_count"], 2)

    def test_crm_dead_letter_queue_poison_pill_quarantine(self):
        """Paranoia Layer 1: 5th failure marks DLQ record as quarantined."""
        for _ in range(5):
            res = record_crm_dead_letter_event(
                supabase=None,
                workspace_id="ws-test-o",
                provider="salesforce",
                entity_type="lead",
                entity_id="sf-lead-888",
                payload={"bad_field": True},
                error_message="Malformed payload rejected by Salesforce",
                status_code=400
            )
        self.assertEqual(res["retry_count"], 5)
        self.assertEqual(res["dlq_status"], "quarantined")

    def test_replay_dead_letter_webhooks_and_stats(self):
        """Paranoia Layer 0 & 2: Replays pending items and queries telemetry stats."""
        # Record a pending DLQ item
        record_crm_dead_letter_event(
            supabase=None,
            workspace_id="ws-test-o",
            provider="hubspot",
            entity_type="deal.stage_change",
            entity_id="deal-999",
            payload={"data": {"deal_id": "deal-999", "stage": "closed_won", "amount": 10000.0}},
            error_message="Socket timeout"
        )

        stats_before = get_crm_dlq_stats(supabase=None, workspace_id="ws-test-o")
        self.assertEqual(stats_before["pending_count"], 1)

        # Replay with force=True
        replay_res = replay_dead_letter_webhooks(supabase=None, workspace_id="ws-test-o", limit=10, force=True)
        self.assertEqual(replay_res["status"], "success")
        self.assertEqual(replay_res["replayed_count"], 1)

        stats_after = get_crm_dlq_stats(supabase=None, workspace_id="ws-test-o")
        self.assertEqual(stats_after["replayed_count"], 1)

    # ── PHASE P TESTS: MASTER VIEW ANALYTICS & ATTRIBUTION RESILIENCE ────────

    def test_workspace_rollup_summary_single_pass_aggregation(self):
        """Paranoia Layer 0 & 2: Computes single-pass aggregation and safe conversion rates."""
        mock_supabase = MagicMock()
        # Mock campaigns
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "c1", "status": "ACTIVE"},
            {"id": "c2", "status": "DRAFT"},
            {"id": "c3", "status": "ACTIVE"}
        ]
        # Mock leads
        leads_mock = MagicMock()
        leads_mock.count = 250
        leads_mock.data = []

        # Mock daily_campaign_stats
        daily_mock = MagicMock()
        daily_mock.data = [
            {
                "connections_sent": 100,
                "messages_sent": 50,
                "leads_enrolled": 100,
                "connections_accepted": 30,
                "replied": 15,
                "meetings_booked": 5,
                "positive_sentiment": 10,
                "auto_withdrawals": 2
            }
        ]

        def table_router(table_name):
            t = MagicMock()
            if table_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": "c1", "status": "ACTIVE"},
                    {"id": "c2", "status": "DRAFT"},
                    {"id": "c3", "status": "ACTIVE"}
                ]
            elif table_name == "leads":
                t.select.return_value.eq.return_value.execute.return_value = leads_mock
            elif table_name == "daily_campaign_stats":
                t.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = daily_mock
            return t

        mock_supabase.table.side_effect = table_router

        summary = get_workspace_rollup_summary(
            workspace_id="ws-test-p",
            date_start="2026-10-01",
            date_end="2026-10-15",
            supabase=mock_supabase,
            bypass_cache=True
        )

        self.assertEqual(summary["overview"]["total_campaigns"], 3)
        self.assertEqual(summary["overview"]["active_campaigns"], 2)
        self.assertEqual(summary["volume"]["connections_sent"], 100)
        self.assertEqual(summary["volume"]["messages_sent"], 50)
        self.assertEqual(summary["volume"]["total_steps"], 150)
        self.assertEqual(summary["funnel"]["connected_leads"], 30)
        self.assertEqual(summary["funnel"]["replied_leads"], 15)
        self.assertEqual(summary["funnel"]["booked_leads"], 5)

        # 30 / 100 = 0.30
        self.assertAlmostEqual(summary["conversion_rates"]["connection_rate"], 0.30, places=2)
        # 15 / 30 = 0.50
        self.assertAlmostEqual(summary["conversion_rates"]["reply_rate"], 0.50, places=2)
        # 5 / 15 = 0.3333
        self.assertAlmostEqual(summary["conversion_rates"]["booking_rate"], 0.3333, places=2)

    def test_master_view_rollup_caching_and_invalidation(self):
        """Paranoia Layer 1: Verifies 60s cache hits and workspace-specific invalidation."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "c1", "status": "ACTIVE"}
        ]

        # Call 1: Populates cache
        res1 = get_workspace_rollup_summary(
            workspace_id="ws-test-cache",
            date_start="2026-10-01",
            date_end="2026-10-15",
            supabase=mock_supabase
        )
        self.assertEqual(res1["overview"]["total_campaigns"], 1)

        # Call 2: Hit cache without invoking DB again
        mock_supabase.table.reset_mock()
        res2 = get_workspace_rollup_summary(
            workspace_id="ws-test-cache",
            date_start="2026-10-01",
            date_end="2026-10-15",
            supabase=mock_supabase
        )
        mock_supabase.table.assert_not_called()

        # Invalidate cache for ws-test-cache
        invalidate_master_view_cache("ws-test-cache")

        # Call 3: Re-invokes DB after invalidation
        get_workspace_rollup_summary(
            workspace_id="ws-test-cache",
            date_start="2026-10-01",
            date_end="2026-10-15",
            supabase=mock_supabase
        )
        mock_supabase.table.assert_called()

    def test_multi_touch_attribution_100_percent_conservation(self):
        """Paranoia Layer 1: Strict 100.0% weight & exact cent conservation across models."""
        deal_amount = 10000.0
        touchpoints_odd = [
            {"channel": "linkedin", "campaign": "Inbound 1", "step": 1},
            {"channel": "email", "campaign": "Inbound 2", "step": 2},
            {"channel": "phone", "campaign": "Inbound 3", "step": 3},
            {"channel": "retargeting", "campaign": "Inbound 4", "step": 4},
            {"channel": "demo", "campaign": "Inbound 5", "step": 5},
        ]

        # Test Linear with 5 touchpoints (1/5 = 0.2 each)
        attr_linear = calculate_deal_attribution(
            deal_id="deal-odd-5",
            deal_name="Enterprise 5-Touch",
            deal_amount=deal_amount,
            touchpoints=touchpoints_odd,
            model="linear"
        )
        total_weight_lin = sum(tp["weight"] for tp in attr_linear["touchpoints"])
        total_amt_lin = sum(tp["attributed_amount"] for tp in attr_linear["touchpoints"])
        self.assertAlmostEqual(total_weight_lin, 1.0000, places=4)
        self.assertAlmostEqual(total_amt_lin, deal_amount, places=2)

        # Test W-Shaped with 3 touchpoints (40% first, 20% mid, 40% last)
        touchpoints_3 = touchpoints_odd[:3]
        attr_w = calculate_deal_attribution(
            deal_id="deal-w-3",
            deal_name="Enterprise 3-Touch",
            deal_amount=3333.33,
            touchpoints=touchpoints_3,
            model="w_shaped"
        )
        total_weight_w = sum(tp["weight"] for tp in attr_w["touchpoints"])
        total_amt_w = sum(tp["attributed_amount"] for tp in attr_w["touchpoints"])
        self.assertAlmostEqual(total_weight_w, 1.0000, places=4)
        self.assertAlmostEqual(total_amt_w, 3333.33, places=2)

        # Test stream_attribution_event
        stream_res = stream_attribution_event(
            deal_id="deal-stream",
            deal_name="Stream Test",
            deal_amount=50000.0,
            touchpoints=touchpoints_odd,
            model="w_shaped"
        )
        self.assertEqual(stream_res["status"], "success")
        self.assertEqual(stream_res["attributed_amount"], 50000.0)

    # ── PHASE Q TESTS: PROXY FLEET LATENCY & GEO-BALANCING ───────────────────

    def test_probe_proxy_health_and_latency_tcp_measurement(self):
        """Paranoia Layer 0 & 2: Probes TCP handshake latency and rejects SSRF private IPs."""
        # SSRF Private IP rejection
        private_proxy = {"host": "192.168.1.1", "port": 8080}
        res_ssrf = probe_proxy_health_and_latency(private_proxy)
        self.assertFalse(res_ssrf["is_healthy"])
        self.assertEqual(res_ssrf["status"], "ssrf_rejected")

        # Quarantined proxy rejection
        quarantined_proxy = {
            "host": "185.199.108.153",
            "port": 8080,
            "status": "quarantined",
            "quarantined_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
        res_q = probe_proxy_health_and_latency(quarantined_proxy)
        self.assertFalse(res_q["is_healthy"])
        self.assertEqual(res_q["status"], "quarantined")

        # Mock successful TCP connection
        valid_proxy = {"host": "185.199.108.153", "port": 8080, "country_code": "US"}
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value.__enter__.return_value = MagicMock()
            res_valid = probe_proxy_health_and_latency(valid_proxy)
            self.assertTrue(res_valid["is_healthy"])
            self.assertEqual(res_valid["status"], "healthy")
            self.assertEqual(res_valid["country_code"], "US")

    def test_check_and_auto_quarantine_proxy_consecutive_failures(self):
        """Paranoia Layer 1: Quarantines proxy after 3 consecutive failures."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        failing_proxy = {"id": "px-fail-1", "host": "185.199.108.153", "port": 8080}

        with patch("socket.create_connection", side_effect=socket.timeout("Timed out")):
            # 1st fail
            r1 = check_and_auto_quarantine_proxy(mock_supabase, failing_proxy)
            self.assertFalse(r1["quarantined"])

            # 2nd fail
            r2 = check_and_auto_quarantine_proxy(mock_supabase, failing_proxy)
            self.assertFalse(r2["quarantined"])

            # 3rd fail -> Auto-quarantined
            r3 = check_and_auto_quarantine_proxy(mock_supabase, failing_proxy)
            self.assertTrue(r3["quarantined"])
            self.assertEqual(r3["status"], "quarantined")

    def test_assign_optimal_proxy_for_account_preserves_sticky_affinity(self):
        """Paranoia Layer 0: Preserves sticky affinity when current proxy is healthy."""
        mock_supabase = MagicMock()
        mock_account = {
            "id": "acc-sticky-1",
            "workspace_id": "ws-proxy-test",
            "proxy_id": "px-healthy",
            "country_code": "US",
            "proxies": {
                "id": "px-healthy",
                "host": "185.199.108.153",
                "port": 8080,
                "country_code": "US",
                "status": "healthy",
                "is_active": True
            }
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_account]

        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value.__enter__.return_value = MagicMock()
            assigned = assign_optimal_proxy_for_account(
                account_id="acc-sticky-1",
                workspace_id="ws-proxy-test",
                supabase=mock_supabase,
                target_country="US"
            )
            self.assertIsNotNone(assigned)
            self.assertEqual(assigned["id"], "px-healthy")
            # Account table should NOT be updated because proxy did not change
            mock_supabase.table().update.assert_not_called()

    def test_reconcile_and_probe_webshare_pool(self):
        """Paranoia Layer 1 & 2: Probes Webshare pool and rebalances accounts from degraded proxies."""
        mock_supabase = MagicMock()
        webshare_proxies = [
            {"id": "px-ws-1", "host": "185.199.108.10", "port": 8080, "provider": "webshare", "country_code": "US"},
            {"id": "px-ws-2", "host": "185.199.108.20", "port": 8080, "provider": "webshare", "country_code": "US"}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = webshare_proxies

        # px-ws-1 succeeds, px-ws-2 fails with timeout
        def socket_side_effect(addr, timeout=None):
            if addr[0] == "185.199.108.20":
                raise socket.timeout("Timed out")
            m = MagicMock()
            m.__enter__.return_value = MagicMock()
            return m

        with patch("socket.create_connection", side_effect=socket_side_effect):
            reconcile_res = reconcile_and_probe_webshare_pool(
                workspace_id="ws-webshare-test",
                supabase=mock_supabase,
                auto_quarantine_slow=True
            )
            self.assertEqual(reconcile_res["status"], "success")
            self.assertEqual(reconcile_res["total_probed"], 2)
            self.assertEqual(reconcile_res["healthy_count"], 1)
            self.assertEqual(reconcile_res["quarantined_count"], 1)


if __name__ == "__main__":
    unittest.main()
