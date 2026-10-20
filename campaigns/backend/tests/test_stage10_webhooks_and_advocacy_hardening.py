"""
Stage 10 Inbound Webhook Security, Cross-Channel Cascade, & Advocacy Pods Hardening Test Suite
Covers Flaws 36 - 38 under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient

from integrations.backend.services.webhook_service import (
    verify_webhook_signature,
    generate_webhook_signature
)
from campaigns.backend.routers.inbound_webhooks import (
    _cascade_halt_lead_linkedin_outreach,
    calendar_booking_webhook,
    smartlead_inbound_webhook,
    instantly_inbound_webhook
)
from campaigns.backend.services.advocacy_pod_service import (
    normalize_linkedin_post_url,
    submit_post_for_boost,
    get_member_daily_engagements,
    _IN_MEMORY_ENGAGEMENTS,
    _IN_MEMORY_BOOSTS
)


class TestStage10WebhooksAndAdvocacyHardening(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws-stage10-testing"
        self.secret = "whsec_supersecretkey123456789"
        self.payload = {"event": "lead.replied", "lead_id": "lead-101", "email": "test@prospect.com"}
        self.ts = int(time.time())
        _, self.raw_signature = generate_webhook_signature(self.payload, self.secret, timestamp_override=self.ts)

    # =========================================================================
    # FLAW 36: Webhook Signature Header Decoupling & Prefix Rejection
    # =========================================================================

    def test_flaw36_verify_webhook_signature_prefixes(self):
        """Layer 1 & 2: Supports raw hex, sha256=, v1=, and Svix t=...,v1= prefixes."""
        # 1. Raw hex
        self.assertTrue(verify_webhook_signature(self.payload, self.secret, self.ts, self.raw_signature))

        # 2. sha256= prefix (GitHub / standard HMAC)
        prefixed_sha = f"sha256={self.raw_signature}"
        self.assertTrue(verify_webhook_signature(self.payload, self.secret, self.ts, prefixed_sha))

        # 3. v1= prefix (Stripe / modern webhooks)
        prefixed_v1 = f"v1={self.raw_signature}"
        self.assertTrue(verify_webhook_signature(self.payload, self.secret, self.ts, prefixed_v1))

        # 4. Multipart t=...,v1=... format
        multipart_sig = f"t={self.ts},v1={self.raw_signature}"
        self.assertTrue(verify_webhook_signature(self.payload, self.secret, self.ts, multipart_sig))

        # 5. Wrong secret fails
        self.assertFalse(verify_webhook_signature(self.payload, "wrong_secret_123", self.ts, self.raw_signature))

        # 6. Replay tolerance expiration (> 300s drift fails)
        old_ts = self.ts - 400
        _, old_sig = generate_webhook_signature(self.payload, self.secret, timestamp_override=old_ts)
        self.assertFalse(verify_webhook_signature(self.payload, self.secret, old_ts, old_sig, tolerance_seconds=300))

    def test_flaw36_booking_webhook_rejects_signature_without_timestamp(self):
        """Layer 1 & 2: When X-Webhook-Signature is sent without timestamp header, reject immediately."""
        mock_req = MagicMock()
        mock_req.headers.get.side_effect = lambda k, d=None: {
            "content-type": "application/json",
            "content-length": "100",
            "x-webhook-signature": self.raw_signature,
            "x-webhook-timestamp": None  # Intentionally omitted
        }.get(k.lower(), d)
        mock_req.query_params.get.return_value = None

        async def run_test():
            with patch("campaigns.backend.routers.inbound_webhooks.get_service_client") as mock_client:
                mock_db = MagicMock()
                mock_client.return_value = mock_db
                mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.workspace_id, "status": "active"}]
                )
                mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"booking_webhook_secret": self.secret}]
                )
                mock_req.json = AsyncMock(return_value=self.payload)

                with self.assertRaises(HTTPException) as ctx:
                    await calendar_booking_webhook(self.workspace_id, mock_req)
                self.assertEqual(ctx.exception.status_code, 401)
                self.assertIn("Missing webhook timestamp header", ctx.exception.detail)

        import asyncio
        asyncio.run(run_test())

    def test_flaw36_smartlead_and_instantly_reject_signature_without_timestamp(self):
        """Layer 1 & 2: Smartlead and Instantly webhooks reject decoupled signature headers without timestamp."""
        mock_req = MagicMock()
        mock_req.headers.get.side_effect = lambda k, d=None: {
            "content-type": "application/json",
            "content-length": "100",
            "x-webhook-signature": self.raw_signature,
            "x-webhook-timestamp": None
        }.get(k.lower(), d)
        mock_req.query_params.get.return_value = None

        async def run_test():
            with patch("campaigns.backend.routers.inbound_webhooks.get_service_client") as mock_client:
                mock_db = MagicMock()
                mock_client.return_value = mock_db
                mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.workspace_id, "status": "active", "smartlead_webhook_secret": self.secret, "instantly_webhook_secret": self.secret}]
                )
                mock_req.json = AsyncMock(return_value=self.payload)

                # Test Smartlead
                with self.assertRaises(HTTPException) as ctx_sl:
                    await smartlead_inbound_webhook(self.workspace_id, mock_req)
                self.assertEqual(ctx_sl.exception.status_code, 401)
                self.assertIn("Missing webhook timestamp header", ctx_sl.exception.detail)

                # Test Instantly
                with self.assertRaises(HTTPException) as ctx_inst:
                    await instantly_inbound_webhook(self.workspace_id, mock_req)
                self.assertEqual(ctx_inst.exception.status_code, 401)
                self.assertIn("Missing webhook timestamp header", ctx_inst.exception.detail)

        import asyncio
        asyncio.run(run_test())

    # =========================================================================
    # FLAW 37: ESP Webhook Outreach Cascade Desynchronization
    # =========================================================================

    def test_flaw37_cascade_halt_synchronizes_enrollments_to_completed_on_reply(self):
        """Layer 0 & 1: Cascade halt updates both execution states AND campaign_enrollments to completed."""
        mock_supabase = MagicMock()
        enr_data = [{"id": "enr-01"}, {"id": "enr-02"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=enr_data
        )

        _cascade_halt_lead_linkedin_outreach(mock_supabase, self.workspace_id, "lead-123", "Lead replied to email")

        # Verify table calls
        table_calls = [c[0][0] for c in mock_supabase.table.call_args_list]
        self.assertIn("campaign_execution_states", table_calls)
        self.assertIn("campaign_enrollments", table_calls)

        # Verify enrollment update payload contains status="completed"
        enr_update_calls = [
            call for call in mock_supabase.table.return_value.update.call_args_list
            if "status" in call[0][0] and call[0][0]["status"] == "completed"
        ]
        self.assertTrue(len(enr_update_calls) >= 1)

    def test_flaw37_cascade_halt_synchronizes_enrollments_to_exited_on_unsubscribe(self):
        """Layer 0 & 1: Cascade halt marks campaign_enrollments as exited on unsubscribe/bounce."""
        mock_supabase = MagicMock()
        enr_data = [{"id": "enr-03"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=enr_data
        )

        _cascade_halt_lead_linkedin_outreach(mock_supabase, self.workspace_id, "lead-456", "Lead unsubscribed from email")

        # Verify enrollment update payload contains status="exited"
        enr_update_calls = [
            call for call in mock_supabase.table.return_value.update.call_args_list
            if "status" in call[0][0] and call[0][0]["status"] == "exited"
        ]
        self.assertTrue(len(enr_update_calls) >= 1)

    # =========================================================================
    # FLAW 38: Advocacy Pods Member Daily Quota Enforcement and URL Validation
    # =========================================================================

    def test_flaw38_normalize_linkedin_post_url(self):
        """Layer 1 & 2: Validates proper LinkedIn URLs and rejects spoofed/dangerous domains."""
        # Valid URLs
        url1 = "https://www.linkedin.com/posts/sarahchen_growth-activity-724918234/?utm_source=share&utm_medium=member_desktop"
        self.assertEqual(
            normalize_linkedin_post_url(url1),
            "https://www.linkedin.com/posts/sarahchen_growth-activity-724918234"
        )

        url2 = "linkedin.com/feed/update/urn:li:activity:724912893"
        self.assertEqual(
            normalize_linkedin_post_url(url2),
            "https://linkedin.com/feed/update/urn:li:activity:724912893"
        )

        # Dangerous and spoofed URLs must return empty string
        self.assertEqual(normalize_linkedin_post_url("http://evil-domain.com?linkedin.com"), "")
        self.assertEqual(normalize_linkedin_post_url("javascript:alert(document.cookie)"), "")
        self.assertEqual(normalize_linkedin_post_url("https://fake-linkedin.com/posts/123"), "")
        self.assertEqual(normalize_linkedin_post_url(""), "")

    def test_flaw38_submit_post_for_boost_rejects_invalid_url(self):
        """Layer 2: submit_post_for_boost raises ValueError on invalid LinkedIn URL."""
        with self.assertRaises(ValueError) as ctx:
            submit_post_for_boost(
                workspace_id=self.workspace_id,
                pod_id="pod-01",
                author_account_id="acc-author-01",
                post_url="https://not-linkedin.com/test",
                target_likes=10,
                target_comments=5
            )
        self.assertIn("Invalid LinkedIn post URL", str(ctx.exception))

    def test_flaw38_advocacy_daily_quota_and_author_exclusion(self):
        """Layer 1: Enforces daily like/comment caps per member and excludes author."""
        _IN_MEMORY_ENGAGEMENTS.clear()
        _IN_MEMORY_BOOSTS.clear()

        # Members: acc-author-01 (author), acc-02 (cap reached), acc-03 (quota remaining)
        mock_members = [
            {
                "id": "mem-01",
                "workspace_id": self.workspace_id,
                "pod_id": "pod-01",
                "account_id": "acc-author-01",
                "account_name": "Author",
                "daily_like_cap": 20,
                "daily_comment_cap": 8,
                "is_active": True
            },
            {
                "id": "mem-02",
                "workspace_id": self.workspace_id,
                "pod_id": "pod-01",
                "account_id": "acc-sdr-maxed",
                "account_name": "Maxed SDR",
                "daily_like_cap": 2,
                "daily_comment_cap": 1,
                "is_active": True
            },
            {
                "id": "mem-03",
                "workspace_id": self.workspace_id,
                "pod_id": "pod-01",
                "account_id": "acc-ae-available",
                "account_name": "Available AE",
                "daily_like_cap": 15,
                "daily_comment_cap": 5,
                "is_active": True
            }
        ]

        # Simulate that acc-sdr-maxed has already used their 2 likes and 1 comment today
        now_iso = datetime.now(timezone.utc).isoformat()
        _IN_MEMORY_ENGAGEMENTS["prior-boost-1"] = [
            {"workspace_id": self.workspace_id, "account_id": "acc-sdr-maxed", "action_type": "like", "status": "completed", "created_at": now_iso},
            {"workspace_id": self.workspace_id, "account_id": "acc-sdr-maxed", "action_type": "like", "status": "completed", "created_at": now_iso},
            {"workspace_id": self.workspace_id, "account_id": "acc-sdr-maxed", "action_type": "comment", "status": "completed", "created_at": now_iso},
        ]

        with patch("campaigns.backend.services.advocacy_pod_service.list_pod_members", return_value=mock_members):
            with patch("campaigns.backend.services.advocacy_pod_service.list_post_boosts", return_value=[]):
                boost = submit_post_for_boost(
                    workspace_id=self.workspace_id,
                    pod_id="pod-01",
                    author_account_id="acc-author-01",
                    post_url="https://www.linkedin.com/posts/sarahchen_growth-activity-724918234",
                    post_content="Breakthrough on cold outbound deliverability",
                    target_likes=10,
                    target_comments=5,
                    supabase=None
                )

                # Retrieve generated engagements for this boost
                scheduled = _IN_MEMORY_ENGAGEMENTS.get(boost["id"], [])
                scheduled_account_ids = [eng["account_id"] for eng in scheduled]

                # Author must NEVER be scheduled
                self.assertNotIn("acc-author-01", scheduled_account_ids)

                # Maxed SDR must NOT be scheduled for likes or comments because cap was reached
                self.assertNotIn("acc-sdr-maxed", scheduled_account_ids)

                # Available AE should be scheduled
                self.assertIn("acc-ae-available", scheduled_account_ids)


if __name__ == "__main__":
    unittest.main()
