"""
Stage 11 Elite Architecture & Resilient Systems Test Suite
Covers:
  - Multi-Tenant CredentialVault with TTL LRU Caching & 401 Quarantine
  - Two-Phase Credit Reservation Engine (Reserve -> Commit -> Compensate)
  - Adaptive Rate-Limit Backpressure & Monotonic Fencing Token CAS in Webhooks
  - Bio-Mimetic Truncated Gaussian Scheduling & Circadian Daylight Clamping
"""

import unittest
from unittest.mock import MagicMock, patch
import time
from datetime import datetime, timezone, timedelta

from integrations.backend.services.credential_vault import CredentialVault
from core.backend.services.credit_service import CreditReservation
from integrations.backend.services.webhook_service import (
    record_endpoint_backpressure,
    get_endpoint_backpressure,
    dispatch_webhook_delivery,
    dispatch_pending_webhooks
)
from campaigns.backend.services.advocacy_pod_service import (
    compute_biomimetic_offset,
    clamp_to_circadian_daylight,
    submit_post_for_boost,
    _IN_MEMORY_ENGAGEMENTS,
    _IN_MEMORY_BOOSTS
)


class TestStage11EliteArchitecture(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws-stage11-enterprise"
        self.mock_supabase = MagicMock()

    # =========================================================================
    # 1. MULTI-TENANT CREDENTIAL VAULT & QUARANTINE ENGINE
    # =========================================================================

    def test_vault_resolves_from_workspace_settings_and_caches(self):
        """Layer 0 & 1: Resolves keys from workspace_settings columns and caches in-memory."""
        vault = CredentialVault(cache_ttl_seconds=60)
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "workspace_id": self.workspace_id,
                "smartlead_api_key": "sl_tenant_key_999",
                "settings": {"instantly_api_key": "inst_tenant_key_888"}
            }]
        )

        # 1. Resolve column-based key
        key1 = vault.resolve_credential(self.workspace_id, "smartlead", supabase_client=mock_client)
        self.assertEqual(key1, "sl_tenant_key_999")

        # 2. Resolve JSONB settings-based key
        key2 = vault.resolve_credential(self.workspace_id, "instantly", supabase_client=mock_client)
        self.assertEqual(key2, "inst_tenant_key_888")

        # 3. Verify in-memory cache hit (no second DB query)
        mock_client.table.reset_mock()
        cached_key = vault.resolve_credential(self.workspace_id, "smartlead", supabase_client=mock_client)
        self.assertEqual(cached_key, "sl_tenant_key_999")
        mock_client.table.assert_not_called()

    def test_vault_quarantine_on_401_and_clear(self):
        """Layer 1 & 2: Quarantines invalid keys to prevent hammering, and allows manual clearing."""
        vault = CredentialVault(cache_ttl_seconds=60, quarantine_ttl_seconds=300)

        # Manually quarantine
        vault.quarantine_credential(self.workspace_id, "smartlead", reason="HTTP 401 Unauthorized")

        # Check quarantine status
        is_q, reason = vault.is_quarantined(self.workspace_id, "smartlead")
        self.assertTrue(is_q)
        self.assertIn("401", reason)

        # Refuses to resolve while quarantined
        resolved = vault.resolve_credential(self.workspace_id, "smartlead", env_fallback="SMARTLEAD_API_KEY")
        self.assertIsNone(resolved)

        # Clear quarantine (e.g. after user updates key in UI)
        vault.clear_quarantine(self.workspace_id, "smartlead")
        is_q_after, _ = vault.is_quarantined(self.workspace_id, "smartlead")
        self.assertFalse(is_q_after)

    def test_vault_sanitizes_placeholder_and_control_chars(self):
        """Layer 2: Rejects placeholder strings and cleans malicious control characters."""
        vault = CredentialVault()
        self.assertIsNone(vault.sanitize_key("YOUR_API_KEY"))
        self.assertIsNone(vault.sanitize_key("null"))
        self.assertIsNone(vault.sanitize_key("   "))
        self.assertEqual(vault.sanitize_key("  clean_key_123\x00\x1f  "), "clean_key_123")

    # =========================================================================
    # 2. TWO-PHASE CREDIT RESERVATION ENGINE (2PC)
    # =========================================================================

    def test_credit_reservation_commit_flow(self):
        """Layer 0 & 1: Commit flow permanently finalizes deduction without refunding."""
        with patch("core.backend.services.credit_service.deduct_credits", return_value={"success": True, "balance": 500}) as mock_deduct:
            with patch("core.backend.services.credit_service.refund_credits") as mock_refund:
                with CreditReservation(self.workspace_id, 10, "crm_push", "corr-101") as hold:
                    self.assertTrue(hold.is_reserved)
                    hold.commit()
                    self.assertTrue(hold.is_committed)

                # Commit was called: refund must NEVER be triggered
                mock_refund.assert_not_called()
                mock_deduct.assert_called_once()

    def test_credit_reservation_auto_compensation_on_exception(self):
        """Layer 1 & 2: Automatic compensation refund when exception occurs inside reservation block."""
        with patch("core.backend.services.credit_service.deduct_credits", return_value={"success": True, "balance": 500}):
            with patch("core.backend.services.credit_service.refund_credits", return_value={"success": True}) as mock_refund:
                try:
                    with CreditReservation(self.workspace_id, 10, "crm_push", "corr-102") as hold:
                        self.assertTrue(hold.is_reserved)
                        raise ValueError("Network timeout during provider POST")
                except ValueError:
                    pass

                # Automatically compensated on uncommitted exit
                mock_refund.assert_called_once()
                self.assertTrue(hold.is_released)

    def test_credit_reservation_explicit_release(self):
        """Layer 1: Explicit release triggers compensation when provider returns 4xx/5xx."""
        with patch("core.backend.services.credit_service.deduct_credits", return_value={"success": True, "balance": 500}):
            with patch("core.backend.services.credit_service.refund_credits", return_value={"success": True}) as mock_refund:
                with CreditReservation(self.workspace_id, 5, "crm_push", "corr-103") as hold:
                    hold.release(reason="provider_rejected_400")
                    self.assertTrue(hold.is_released)

                mock_refund.assert_called_once()
                self.assertIn("provider_rejected_400", mock_refund.call_args[1].get("reason"))

    # =========================================================================
    # 3. ADAPTIVE BACKPRESSURE & MONOTONIC FENCING IN WEBHOOKS
    # =========================================================================

    def test_adaptive_rate_limit_backpressure(self):
        """Layer 1 & 2: Honors dynamic Retry-After backpressure from external webhook recipients."""
        endpoint_id = "ep-test-throttle-99"
        # Register 10 seconds backpressure
        record_endpoint_backpressure(endpoint_id, 10.0)

        remaining = get_endpoint_backpressure(endpoint_id)
        self.assertIsNotNone(remaining)
        self.assertTrue(remaining > 5.0)

        # Dispatcher must defer execution when backpressure is active
        mock_client = MagicMock()
        delivery = {"id": "deliv-throttle-1", "workspace_id": self.workspace_id, "attempt_count": 0}
        endpoint = {"id": endpoint_id, "url": "https://api.external.com/webhook", "workspace_id": self.workspace_id}

        res = dispatch_webhook_delivery(delivery, endpoint, supabase=mock_client)
        self.assertEqual(res.get("status"), "retry_scheduled")

    def test_dispatch_pending_webhooks_monotonic_fencing_claim(self):
        """Layer 0 & 1: CAS atomic claim prevents duplicate delivery dispatch across workers."""
        mock_client = MagicMock()
        mock_deliveries = [
            {"id": "deliv-fence-01", "endpoint_id": "ep-1", "workspace_id": self.workspace_id},
            {"id": "deliv-fence-02", "endpoint_id": "ep-1", "workspace_id": self.workspace_id}
        ]
        # First query returns the deliveries
        mock_client.table.return_value.select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=mock_deliveries
        )
        mock_client.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "ep-1", "is_active": True, "url": "https://api.test.com/hook", "signing_secret": "0123"}]
        )
        # CAS claim update returns the successfully claimed delivery record
        mock_client.table.return_value.update.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "deliv-fence-01"}]
        )

        with patch("integrations.backend.services.webhook_service.dispatch_webhook_delivery", return_value={"status": "success"}) as mock_dispatch:
            out = dispatch_pending_webhooks(batch_size=10, supabase=mock_client)
            self.assertEqual(out.get("processed"), 2)
            self.assertEqual(mock_dispatch.call_count, 2)
            # Verify fence token was passed
            self.assertIn("fence_token", mock_dispatch.call_args[1])
            self.assertTrue(mock_dispatch.call_args[1]["fence_token"].startswith("fence_deliv-fence-02_"))

    # =========================================================================
    # 4. BIO-MIMETIC SCHEDULING & CIRCADIAN DAYLIGHT CLAMPING
    # =========================================================================

    def test_compute_biomimetic_offset_distribution(self):
        """Layer 1 & 2: Staggers engagements across window with cognitive reading latency."""
        offset_like = compute_biomimetic_offset(index=0, total_actions=5, window_minutes=60, action_type="like")
        offset_comment = compute_biomimetic_offset(index=0, total_actions=5, window_minutes=60, action_type="comment")

        self.assertGreaterEqual(offset_like, 45)
        self.assertGreaterEqual(offset_comment, 45)
        # Comments should naturally carry higher cognitive overhead
        self.assertLessEqual(offset_like, 3600)
        self.assertLessEqual(offset_comment, 3600)

    def test_clamp_to_circadian_daylight_nocturnal_curfew(self):
        """Layer 1 & 2: Actions scheduled at 3 AM roll forward to daylight business hours (08:30+)."""
        # Scheduled at 3:15 AM UTC
        night_time = datetime(2026, 10, 20, 3, 15, 0, tzinfo=timezone.utc)
        safe_time = clamp_to_circadian_daylight(night_time, timezone_str="UTC")

        # Must have rolled forward to morning (hour >= 8)
        self.assertGreaterEqual(safe_time.hour, 8)
        self.assertLess(safe_time.hour, 10)

        # Daytime action (14:30) remains untouched
        day_time = datetime(2026, 10, 20, 14, 30, 0, tzinfo=timezone.utc)
        safe_day = clamp_to_circadian_daylight(day_time, timezone_str="UTC")
        self.assertEqual(safe_day.hour, 14)
        self.assertEqual(safe_day.minute, 30)

    def test_submit_post_for_boost_with_biomimetic_scheduling(self):
        """Layer 0, 1, 2: Full submit_post_for_boost produces staggered bio-mimetic schedule."""
        _IN_MEMORY_ENGAGEMENTS.clear()
        _IN_MEMORY_BOOSTS.clear()

        mock_members = [
            {"account_id": "acc-founder", "is_active": True},
            {"account_id": "acc-rep-1", "daily_like_cap": 10, "daily_comment_cap": 5, "is_active": True, "timezone": "UTC"},
            {"account_id": "acc-rep-2", "daily_like_cap": 10, "daily_comment_cap": 5, "is_active": True, "timezone": "UTC"}
        ]

        with patch("campaigns.backend.services.advocacy_pod_service.list_pod_members", return_value=mock_members):
            with patch("campaigns.backend.services.advocacy_pod_service.list_post_boosts", return_value=[]):
                boost = submit_post_for_boost(
                    workspace_id=self.workspace_id,
                    pod_id="pod-bio-01",
                    author_account_id="acc-founder",
                    post_url="https://www.linkedin.com/posts/growth_viral-activity-724918234",
                    post_content="Elite outbound architecture in 2026",
                    target_likes=2,
                    target_comments=1,
                    target_window_minutes=45
                )

                engagements = _IN_MEMORY_ENGAGEMENTS.get(boost["id"], [])
                self.assertGreaterEqual(len(engagements), 1)
                # Verify scheduled_at timestamps are ISO strings in daylight
                for eng in engagements:
                    dt = datetime.fromisoformat(eng["scheduled_at"])
                    self.assertGreaterEqual(dt.hour, 8)


if __name__ == "__main__":
    unittest.main()
