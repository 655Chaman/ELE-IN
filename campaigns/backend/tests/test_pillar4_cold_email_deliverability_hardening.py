"""
test_pillar4_cold_email_deliverability_hardening.py
===================================================
Production-grade test suite verifying Pillar 4:
Cold Email Engine & Sender Reputation Infrastructure
Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Phase 4.1: Live Multi-ESP Webhook Ingestion Engine (Resend & SES signature verification, normalization, dedupe)
- Phase 4.2: Peer Simulation Warmup Swarm (adaptive throttling, peer pairing, exchange generation)
- Phase 4.3: Automated CNAME & SSL Tracking Verification (fall-open link safety, TLS handshake check)
- Phase 4.4: Domain Burnout Circuit Breaker & RFC 8058 One-Click Unsubscribe (tripwire floors, retroactive purge)
"""

import os
import time
import json
import hmac
import base64
import hashlib
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from integrations.backend.services.esp_webhook_processor import (
    ESPProvider,
    WebhookEventType,
    ESPWebhookProcessor,
    verify_resend_signature,
    verify_ses_sns_signature,
    normalize_esp_event,
    process_esp_event,
)
from integrations.backend.services.mailbox_warmup_service import (
    calculate_inbox_warmup_health_score,
    simulate_peer_warmup_exchange,
    execute_warmup_swarm_batch,
    WarmupHealthStatus,
)
from core.backend.services.deliverability_guard import (
    verify_custom_tracking_domain,
    rewrite_tracking_links,
    evaluate_domain_burnout_tripwire,
)
from campaigns.backend.services.unsubscribe_service import (
    generate_unsubscribe_token,
    verify_unsubscribe_token,
    generate_rfc8058_headers,
    process_one_click_unsubscribe,
)


# ==============================================================================
# Phase 4.1: Live Multi-ESP Webhook Ingestion Engine
# ==============================================================================

class TestMultiESPWebhookIngestion:
    """Tests for Resend Svix HMAC-SHA256 and AWS SES SNS webhook processing."""

    def test_resend_svix_signature_verification_success(self):
        """Layer 0: Valid Resend/Svix HMAC-SHA256 signature passes verification."""
        secret = "whsec_dGVzdF9zZWNyZXRfa2V5XzEyMzQ1Njc4OTAxMjM0NTY="  # base64 encoded
        clean_secret = base64.b64decode("dGVzdF9zZWNyZXRfa2V5XzEyMzQ1Njc4OTAxMjM0NTY=")
        
        msg_id = "msg_resend_12345"
        timestamp = str(int(time.time()))
        payload = json.dumps({"type": "email.delivered", "data": {"email_id": "em_123"}}).encode("utf-8")
        
        to_sign = f"{msg_id}.{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
        expected_sig = base64.b64encode(hmac.new(clean_secret, to_sign, hashlib.sha256).digest()).decode("utf-8")
        svix_sig = f"v1,{expected_sig}"

        is_valid = verify_resend_signature(
            payload_bytes=payload,
            svix_id=msg_id,
            svix_timestamp=timestamp,
            svix_signature=svix_sig,
            secret=secret,
            tolerance_seconds=300,
        )
        assert is_valid is True

    def test_resend_svix_signature_clock_drift_rejection(self):
        """Layer 1: Timestamp older than tolerance (>300s) is rejected to prevent replay attacks."""
        secret = "whsec_dGVzdF9zZWNyZXRfa2V5XzEyMzQ1Njc4OTAxMjM0NTY="
        msg_id = "msg_resend_replay"
        stale_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        payload = b'{"type":"email.bounced"}'

        is_valid = verify_resend_signature(
            payload_bytes=payload,
            svix_id=msg_id,
            svix_timestamp=stale_timestamp,
            svix_signature="v1,fakesig",
            secret=secret,
            tolerance_seconds=300,
        )
        assert is_valid is False

    def test_resend_svix_tampered_payload_rejection(self):
        """Layer 2: Tampered payload body fails HMAC verification."""
        secret = "whsec_dGVzdF9zZWNyZXRfa2V5XzEyMzQ1Njc4OTAxMjM0NTY="
        clean_secret = base64.b64decode("dGVzdF9zZWNyZXRfa2V5XzEyMzQ1Njc4OTAxMjM0NTY=")
        
        msg_id = "msg_123"
        timestamp = str(int(time.time()))
        orig_payload = b'{"amount": 10}'
        tampered_payload = b'{"amount": 999}'

        to_sign = f"{msg_id}.{timestamp}.{orig_payload.decode('utf-8')}".encode("utf-8")
        expected_sig = base64.b64encode(hmac.new(clean_secret, to_sign, hashlib.sha256).digest()).decode("utf-8")

        is_valid = verify_resend_signature(
            payload_bytes=tampered_payload,
            svix_id=msg_id,
            svix_timestamp=timestamp,
            svix_signature=f"v1,{expected_sig}",
            secret=secret,
        )
        assert is_valid is False

    def test_resend_event_normalization(self):
        """Layer 0: Resend payload formats normalize to standard internal schema."""
        raw_resend = {
            "type": "email.bounced",
            "created_at": "2026-10-24T10:00:00.000Z",
            "data": {
                "email_id": "resend_em_789",
                "to": ["prospect@example.com"],
                "subject": "Quick question",
                "tags": {
                    "campaign_id": "camp_abc",
                    "lead_id": "lead_xyz",
                    "workspace_id": "ws_123",
                },
                "bounce": {
                    "message": "550 5.1.1 User unknown",
                    "type": "Permanent",
                }
            }
        }
        norm = normalize_esp_event(raw_resend, provider=ESPProvider.RESEND)
        assert norm["event_type"] == WebhookEventType.BOUNCE_HARD
        assert norm["email"] == "prospect@example.com"
        assert norm["campaign_id"] == "camp_abc"
        assert norm["lead_id"] == "lead_xyz"
        assert norm["workspace_id"] == "ws_123"

    def test_ses_sns_notification_normalization(self):
        """Layer 0: Amazon SES delivery via SNS payload unwraps and normalizes."""
        raw_ses_sns = {
            "Type": "Notification",
            "MessageId": "sns-msg-999",
            "Message": json.dumps({
                "notificationType": "Complaint",
                "complaint": {
                    "complainedRecipients": [{"emailAddress": "complainer@domain.com"}],
                    "complaintFeedbackType": "abuse",
                },
                "mail": {
                    "messageId": "ses-outbound-456",
                    "headers": [
                        {"name": "X-EleIn-Campaign-Id", "value": "camp_ses_1"},
                        {"name": "X-EleIn-Lead-Id", "value": "lead_ses_2"},
                        {"name": "X-EleIn-Workspace-Id", "value": "ws_ses_3"},
                    ]
                }
            })
        }
        norm = normalize_esp_event(raw_ses_sns, provider=ESPProvider.AMAZON_SES)
        assert norm["event_type"] == WebhookEventType.SPAM_COMPLAINT
        assert norm["email"] == "complainer@domain.com"
        assert norm["campaign_id"] == "camp_ses_1"
        assert norm["lead_id"] == "lead_ses_2"
        assert norm["workspace_id"] == "ws_ses_3"

    def test_esp_event_deduplication_idempotency(self):
        """Layer 1: Duplicate webhook delivery is identified and skipped idempotently."""
        mock_sb = MagicMock()
        mock_builder = MagicMock()
        mock_sb.table.return_value = mock_builder
        mock_builder.select.return_value = mock_builder
        mock_builder.eq.return_value = mock_builder
        mock_builder.limit.return_value = mock_builder
        # Simulate that this event already exists in esp_webhook_events
        mock_builder.execute.return_value = MagicMock(data=[{"id": "existing-event-uuid"}])

        event = {
            "provider": ESPProvider.RESEND,
            "event_id": "resend_evt_dup_123",
            "message_id": "msg_dup_123",
            "event_type": WebhookEventType.DELIVERED,
            "email": "lead@test.com",
            "workspace_id": "ws_123",
            "lead_id": "lead_123",
        }
        res = process_esp_event(mock_sb, event)
        assert res["status"] == "skipped_duplicate"
        assert res["deduplicated"] is True


# ==============================================================================
# Phase 4.2: Peer Simulation Warmup Swarm
# ==============================================================================

class TestPeerWarmupSwarm:
    """Tests for peer exchange generation, adaptive health throttling, and swarm batches."""

    def test_insufficient_mailboxes_rejected(self):
        """Layer 1: Swarm batch requires at least 2 mailboxes."""
        res = execute_warmup_swarm_batch(mailboxes=[{"id": "box_1"}], target_exchanges_per_box=3)
        assert res["success"] is False
        assert res["status"] == "INSUFFICIENT_MAILBOXES"
        assert res["total_exchanges"] == 0

    def test_adaptive_reputation_throttling(self):
        """Layer 0 & 1: Degraded health automatically throttles cold outreach."""
        # Box A: Pristine health (0% bounce, active 30 days) -> 100% capacity
        pristine_box = {
            "id": "box_pristine",
            "email": "pristine@domain.com",
            "current_ramp_day": 35,
            "total_sent": 200,
            "total_bounces": 0,
            "total_spam_complaints": 0,
            "peer_engagement_rate_pct": 50.0,
        }
        h_pristine = calculate_inbox_warmup_health_score(pristine_box)
        assert h_pristine["health_score"] >= 85
        assert h_pristine["throttle_cold_ratio"] == 1.0
        assert h_pristine["emergency_paused"] is False

        # Box B: Needs recovery (bounce rate 2.5%, score 50-69) -> 50% cold throttle
        recovery_box = {
            "id": "box_recovery",
            "email": "recovery@domain.com",
            "current_ramp_day": 10,
            "total_sent": 100,
            "total_bounces": 2,
            "aggregate_bounce_rate_pct": 2.0,
            "total_spam_complaints": 0,
            "peer_engagement_rate_pct": 10.0,
        }
        h_recovery = calculate_inbox_warmup_health_score(recovery_box)
        assert 50 <= h_recovery["health_score"] < 70
        assert h_recovery["throttle_cold_ratio"] == 0.5
        assert h_recovery["emergency_paused"] is False

        # Box C: Emergency paused (bounce rate >= 3.0%, high spam) -> 100% cold paused
        burned_box = {
            "id": "box_burned",
            "email": "burned@domain.com",
            "current_ramp_day": 5,
            "total_sent": 50,
            "total_bounces": 5,
            "aggregate_bounce_rate_pct": 10.0,
            "total_spam_complaints": 2,
            "aggregate_spam_rate_pct": 4.0,
            "peer_engagement_rate_pct": 0.0,
        }
        h_burned = calculate_inbox_warmup_health_score(burned_box)
        assert h_burned["health_score"] < 50
        assert h_burned["throttle_cold_ratio"] == 0.0
        assert h_burned["emergency_paused"] is True

    def test_swarm_batch_distinct_peer_pairing(self):
        """Layer 2: Swarm batch never pairs a mailbox with itself."""
        boxes = [
            {"id": "box_1", "email": "a@domain.com", "workspace_id": "ws_1"},
            {"id": "box_2", "email": "b@domain.com", "workspace_id": "ws_1"},
            {"id": "box_3", "email": "c@domain.com", "workspace_id": "ws_1"},
        ]
        res = execute_warmup_swarm_batch(mailboxes=boxes, target_exchanges_per_box=2)
        assert res["success"] is True
        assert res["total_exchanges"] > 0

        for ex in res["exchanges"]:
            assert ex["sender_inbox_id"] != ex["recipient_inbox_id"]
            assert ex["sender_email"] != ex["peer_email"]
            assert ex["landed_inbox"] is True
            assert ex["starred"] is True
            assert ex["replied"] is True


# ==============================================================================
# Phase 4.3: Automated CNAME & SSL Tracking Verification
# ==============================================================================

class TestCustomTrackingDomainAndSSLGuard:
    """Tests for CNAME DNS check, TLS handshake, and fall-open link rewriting."""

    def test_custom_tracking_domain_active_verified(self):
        """Layer 0: Active verified status returned when CNAME and SSL pass."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.clientdomain.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=True,
            mock_cname="track.elein.ai",
            mock_ssl_valid=True,
        )
        assert res["valid"] is True
        assert res["status"] == "VERIFIED_ACTIVE"
        assert res["ssl_verified"] is True
        assert res["can_track_safely"] is True

    def test_custom_tracking_domain_ssl_pending_provisioning(self):
        """Layer 1: When CNAME matches but SSL handshake fails, reports SSL_PENDING_PROVISIONING."""
        res = verify_custom_tracking_domain(
            tracking_fqdn="track.clientdomain.com",
            expected_cname_target="track.elein.ai",
            check_live_ssl=True,
            mock_cname="track.elein.ai",
            mock_ssl_valid=False,
        )
        assert res["valid"] is False
        assert res["status"] == "SSL_PENDING_PROVISIONING"
        assert res["ssl_verified"] is False
        assert res["can_track_safely"] is False

    def test_rewrite_tracking_links_fall_open_on_unverified_ssl(self):
        """Layer 1 Fall-open Protection: If SSL is not verified, links remain untouched to prevent browser warnings."""
        body = "Hello! Check our website at https://clientdomain.com/demo and read docs at https://docs.clientdomain.com."
        
        result = rewrite_tracking_links(
            body=body,
            tracking_domain="track.clientdomain.com",
            email_id="em_abc123",
            workspace_id="ws_789",
            ssl_verified=False,  # Unverified SSL!
        )
        # Invariant: body must NOT be altered
        assert result["body"] == body
        assert result["rewritten_count"] == 0
        assert result["tracking_applied"] is False
        assert result["fallback_reason"] == "SSL_UNVERIFIED_PREVENTED_BROWSER_WARNING"

    def test_rewrite_tracking_links_rewrites_when_ssl_verified(self):
        """Layer 0: When SSL is verified, links are safely wrapped through custom tracking domain."""
        body = "Check our platform: https://clientdomain.com/demo."
        result = rewrite_tracking_links(
            body=body,
            tracking_domain="track.clientdomain.com",
            email_id="em_abc123",
            workspace_id="ws_789",
            ssl_verified=True,
        )
        assert result["tracking_applied"] is True
        assert result["rewritten_count"] == 1
        assert "https://track.clientdomain.com/t/c/em_abc123" in result["body"]
        # Preserves trailing period
        assert result["body"].endswith(".")


# ==============================================================================
# Phase 4.4: Domain Burnout Circuit Breaker & RFC 8058 One-Click Unsubscribe
# ==============================================================================

class TestDomainBurnoutAndRFC8058Unsubscribe:
    """Tests for domain burnout tripwires and RFC 8058 cryptographic unsubscribe."""

    def test_domain_burnout_small_sample_false_positive_guard(self):
        """Layer 1: Small sample (under 15 sends) does not trip percentage-based burnout."""
        small_sample = {
            "total_sent": 8,
            "total_bounces": 1,  # 12.5% rate, but below sample size and below 5 bounce floor
            "total_spam_complaints": 0,
            "inbox_count": 2,
            "active_inbox_count": 2,
        }
        res = evaluate_domain_burnout_tripwire(small_sample, min_sample_size=15)
        assert res["should_quarantine"] is False
        assert res["status"] == "HEALTHY"

    def test_domain_burnout_absolute_bounce_floor_tripwire(self):
        """Layer 0: Absolute bounce ceiling of >= 5 bounces trips burnout regardless of sample size."""
        absolute_spike = {
            "total_sent": 10,
            "total_bounces": 5,
            "total_spam_complaints": 0,
            "inbox_count": 2,
            "active_inbox_count": 2,
        }
        res = evaluate_domain_burnout_tripwire(absolute_spike, min_sample_size=15)
        assert res["should_quarantine"] is True
        assert res["status"] == "BURNOUT_QUARANTINED"
        assert "DOMAIN_ABSOLUTE_BOUNCE_CEILING_EXCEEDED" in res["quarantine_reason"]

    def test_domain_burnout_percentage_tripwire_with_sufficient_sample(self):
        """Layer 0: With >= 15 sends, aggregate bounce rate >= 3.0% triggers 24h burnout cooldown."""
        burned_sample = {
            "total_sent": 100,
            "total_bounces": 4,  # 4.0% >= 3.0%
            "total_spam_complaints": 0,
            "inbox_count": 4,
            "active_inbox_count": 4,
        }
        res = evaluate_domain_burnout_tripwire(burned_sample, min_sample_size=15, bounce_threshold_pct=3.0)
        assert res["should_quarantine"] is True
        assert res["status"] == "BURNOUT_QUARANTINED"
        assert "DOMAIN_BOUNCE_RATE_EXCEEDED" in res["quarantine_reason"]
        assert res["quarantined_until"] is not None

    def test_rfc8058_headers_generation_and_verification(self):
        """Layer 0 & 1: Compliant RFC 8058 headers generated with constant-time HMAC token."""
        headers = generate_rfc8058_headers(
            workspace_id="ws_unsub_1",
            lead_id="lead_unsub_2",
            email="recipient@test.com",
            base_url="https://app.ele-in.com",
        )
        assert "List-Unsubscribe" in headers
        assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert "https://app.ele-in.com/api/elein/unsubscribe?token=" in headers["List-Unsubscribe"]

        # Extract token and verify
        unsub_link = headers["List-Unsubscribe"].split(",")[0].strip("<>")
        token = unsub_link.split("token=")[1]
        verified = verify_unsubscribe_token(token)
        assert verified is not None
        assert verified["workspace_id"] == "ws_unsub_1"
        assert verified["lead_id"] == "lead_unsub_2"
        assert verified["email"] == "recipient@test.com"

    def test_rfc8058_tampered_token_rejection(self):
        """Layer 2: Malformed or forged tokens are safely rejected without crashing."""
        assert verify_unsubscribe_token("invalid.token") is None
        assert verify_unsubscribe_token("") is None
        assert verify_unsubscribe_token("not-a-token") is None

    def test_one_click_unsubscribe_updates_lead_and_retroactive_purge(self):
        """Layer 0: One-click unsubscribe transitions lead status and triggers retroactive purge."""
        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        with patch("campaigns.backend.services.unsubscribe_service.retroactive_purge") as mock_purge:
            mock_purge.return_value = {"matched_leads_count": 1, "halted_states_count": 2, "lead_ids": ["lead_100"]}
            
            res = process_one_click_unsubscribe(
                workspace_id="ws_test",
                lead_id="lead_100",
                email="lead100@target.com",
                supabase=mock_sb,
            )
            assert res["status"] == "success"
            assert res["unsubscribed"] is True
            assert res["email"] == "lead100@target.com"
            mock_purge.assert_called_once_with(workspace_id="ws_test", email="lead100@target.com", supabase=mock_sb)
