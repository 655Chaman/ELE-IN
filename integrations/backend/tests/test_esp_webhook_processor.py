"""
test_esp_webhook_processor.py — Unit & Integration Test Suite for Unified ESP Webhook Feedback Loop,
FBL ARF Abuse Processor & Runaway Bounce Circuit Breaker (Phase 40 Core Service).
Hardened under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import time
import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch
import pytest

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

from integrations.backend.services.esp_webhook_processor import (
    ESPProvider,
    WebhookEventType,
    ESPWebhookProcessor,
    verify_sendgrid_signature,
    verify_mailgun_signature,
    verify_postmark_token,
    normalize_esp_event,
    process_esp_event,
    evaluate_campaign_circuit_breaker,
)


# ==============================================================================
# Layer 0: Foundational Layer — Enums & Normalization Tests
# ==============================================================================

def test_enums_completeness():
    """Verify all required ESP providers and canonical webhook event types exist."""
    assert ESPProvider.SENDGRID == "SENDGRID"
    assert ESPProvider.MAILGUN == "MAILGUN"
    assert ESPProvider.POSTMARK == "POSTMARK"
    assert ESPProvider.AMAZON_SES == "AMAZON_SES"
    assert ESPProvider.GENERIC_SMTP == "GENERIC_SMTP"

    assert WebhookEventType.DELIVERED == "delivered"
    assert WebhookEventType.OPEN == "open"
    assert WebhookEventType.CLICK == "click"
    assert WebhookEventType.BOUNCE_HARD == "bounce_hard"
    assert WebhookEventType.BOUNCE_SOFT == "bounce_soft"
    assert WebhookEventType.SPAM_COMPLAINT == "spam_complaint"
    assert WebhookEventType.UNSUBSCRIBE == "unsubscribe"
    assert WebhookEventType.UNKNOWN == "unknown"


def test_normalize_sendgrid_delivered_event():
    """Maps SendGrid event='delivered' to canonical WebhookEventType.DELIVERED."""
    raw = {
        "event": "delivered",
        "email": "lead1@prospect.com",
        "sg_message_id": "sg_msg_12345",
        "timestamp": 1729270000,
        "campaign_id": "camp_abc",
        "lead_id": "lead_111",
        "workspace_id": "ws_999",
    }
    normalized = normalize_esp_event(raw, ESPProvider.SENDGRID)
    assert normalized["event_type"] == WebhookEventType.DELIVERED
    assert normalized["clean_email"] == "lead1@prospect.com"
    assert normalized["campaign_id"] == "camp_abc"
    assert normalized["lead_id"] == "lead_111"
    assert normalized["workspace_id"] == "ws_999"
    assert normalized["provider"] == ESPProvider.SENDGRID


def test_normalize_sendgrid_hard_bounce():
    """Maps SendGrid event='bounce' (blocked / 5xx) to BOUNCE_HARD."""
    raw = {
        "event": "bounce",
        "type": "blocked",
        "status": "550 5.1.1 User unknown",
        "email": "bounced@invalid.org",
        "reason": "550 5.1.1 Recipient mailbox not found",
        "sg_message_id": "sg_bounce_1",
    }
    normalized = normalize_esp_event(raw, ESPProvider.SENDGRID)
    assert normalized["event_type"] == WebhookEventType.BOUNCE_HARD
    assert normalized["clean_email"] == "bounced@invalid.org"
    assert "User unknown" in normalized["smtp_code"]


def test_normalize_sendgrid_spam_report():
    """Maps SendGrid event='spamreport' to SPAM_COMPLAINT."""
    raw = {
        "event": "spamreport",
        "email": "complainer@victim.com",
        "sg_message_id": "sg_spam_99",
        "custom_args": {
            "campaign_id": "camp_spam",
            "workspace_id": "ws_spam",
            "lead_id": "lead_spam_1",
        },
    }
    normalized = normalize_esp_event(raw, ESPProvider.SENDGRID)
    assert normalized["event_type"] == WebhookEventType.SPAM_COMPLAINT
    assert normalized["clean_email"] == "complainer@victim.com"
    assert normalized["campaign_id"] == "camp_spam"
    assert normalized["lead_id"] == "lead_spam_1"


def test_normalize_mailgun_complained():
    """Maps Mailgun 'complained' event to SPAM_COMPLAINT."""
    raw = {
        "event-data": {
            "event": "complained",
            "recipient": "angry@target.io",
            "timestamp": 1729270000.5,
            "user-variables": {
                "campaign_id": "camp_mg",
                "lead_id": "lead_mg",
                "workspace_id": "ws_mg",
            },
        }
    }
    normalized = normalize_esp_event(raw, ESPProvider.MAILGUN)
    assert normalized["event_type"] == WebhookEventType.SPAM_COMPLAINT
    assert normalized["clean_email"] == "angry@target.io"
    assert normalized["campaign_id"] == "camp_mg"
    assert normalized["lead_id"] == "lead_mg"
    assert normalized["workspace_id"] == "ws_mg"


def test_normalize_postmark_hard_bounce():
    """Maps Postmark RecordType='Bounce', Type='HardBounce' to BOUNCE_HARD."""
    raw = {
        "RecordType": "Bounce",
        "Type": "HardBounce",
        "TypeCode": 1,
        "Recipient": "hardbounce@postmark.net",
        "Description": "The server was unable to deliver your message (invalid recipient).",
        "Metadata": {
            "campaign_id": "camp_pm",
            "lead_id": "lead_pm",
            "workspace_id": "ws_pm",
        },
    }
    normalized = normalize_esp_event(raw, ESPProvider.POSTMARK)
    assert normalized["event_type"] == WebhookEventType.BOUNCE_HARD
    assert normalized["clean_email"] == "hardbounce@postmark.net"
    assert normalized["campaign_id"] == "camp_pm"
    assert normalized["lead_id"] == "lead_pm"


def test_normalize_sendgrid_soft_bounce():
    """Maps SendGrid transient soft bounce to BOUNCE_SOFT."""
    raw = {
        "event": "bounce",
        "type": "soft_bounce",
        "bounce_classification": "transient",
        "email": "busy@mailbox.org",
    }
    normalized = normalize_esp_event(raw, ESPProvider.SENDGRID)
    assert normalized["event_type"] == WebhookEventType.BOUNCE_SOFT


def test_normalize_sendgrid_unsubscribe_event():
    """Maps SendGrid event='unsubscribe' to UNSUBSCRIBE."""
    raw = {
        "event": "unsubscribe",
        "email": "optout@company.com",
    }
    normalized = normalize_esp_event(raw, ESPProvider.SENDGRID)
    assert normalized["event_type"] == WebhookEventType.UNSUBSCRIBE


def test_normalize_mailgun_failed_permanent_vs_temporary():
    """Maps Mailgun severity permanent to BOUNCE_HARD and temporary to BOUNCE_SOFT."""
    perm_raw = {
        "event-data": {
            "event": "failed",
            "severity": "permanent",
            "recipient": "perm@bad.com",
        }
    }
    norm_perm = normalize_esp_event(perm_raw, ESPProvider.MAILGUN)
    assert norm_perm["event_type"] == WebhookEventType.BOUNCE_HARD

    temp_raw = {
        "event-data": {
            "event": "failed",
            "severity": "temporary",
            "recipient": "temp@busy.com",
        }
    }
    norm_temp = normalize_esp_event(temp_raw, ESPProvider.MAILGUN)
    assert norm_temp["event_type"] == WebhookEventType.BOUNCE_SOFT


def test_normalize_postmark_spam_complaint():
    """Maps Postmark SpamComplaint RecordType to SPAM_COMPLAINT."""
    raw = {
        "RecordType": "SpamComplaint",
        "Recipient": "fbl@complaint.org",
        "Description": "User clicked Report Spam in Yahoo Mail",
    }
    norm = normalize_esp_event(raw, ESPProvider.POSTMARK)
    assert norm["event_type"] == WebhookEventType.SPAM_COMPLAINT


def test_normalize_amazon_ses_events():
    """Maps Amazon SES bounce and complaint notifications."""
    ses_bounce = {
        "eventType": "bounce",
        "mail": {
            "destination": ["ses_bounce@domain.com"],
            "messageId": "ses_msg_1",
            "tags": {"campaign_id": ["camp_ses"], "workspace_id": ["ws_ses"]},
        },
        "bounce": {
            "bounceType": "Permanent",
            "bouncedRecipients": [{"diagnosticCode": "smtp; 550 User unknown"}],
        },
    }
    norm_ses = normalize_esp_event(ses_bounce, ESPProvider.AMAZON_SES)
    assert norm_ses["event_type"] == WebhookEventType.BOUNCE_HARD
    assert norm_ses["clean_email"] == "ses_bounce@domain.com"
    assert norm_ses["campaign_id"] == "camp_ses"


# ==============================================================================
# Layer 0: Feedback Loop & Abuse Processor Execution Tests
# ==============================================================================

def test_process_spam_complaint_quarantines_lead():
    """Lead status set to COMPLAINED, added to suppression_list, and active sequences purged."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])

    event = {
        "clean_email": "quarantine@prospect.com",
        "event_type": WebhookEventType.SPAM_COMPLAINT,
        "workspace_id": "ws_test_123",
        "lead_id": "lead_test_456",
        "campaign_id": "camp_test_789",
        "inbox_id": "inbox_test_001",
    }

    with patch("leads.backend.services.suppression_service.add_suppression_entries_bulk") as mock_suppress, \
         patch("campaigns.backend.services.unsubscribe_service.retroactive_purge") as mock_purge, \
         patch("integrations.backend.services.email_sender_service.record_inbox_delivery_outcome") as mock_inbox:

        outcome = process_esp_event(supabase=mock_supabase, event=event)

        assert outcome["status"] == "processed"
        assert outcome["action_taken"] == "LEAD_COMPLAINED_AND_SUPPRESSED"
        assert outcome["suppressed"] is True
        assert outcome["inbox_recorded"] is True

        mock_table.update.assert_called()
        update_args = mock_table.update.call_args[0][0]
        assert update_args["status"] == "COMPLAINED"
        assert update_args["is_unsubscribed"] is True
        assert "complaint_at" in update_args

        mock_suppress.assert_called_once()
        mock_purge.assert_called_once_with(
            workspace_id="ws_test_123",
            email="quarantine@prospect.com",
            supabase=mock_supabase,
        )
        mock_inbox.assert_called_once_with(
            supabase=mock_supabase,
            workspace_id="ws_test_123",
            inbox_id="inbox_test_001",
            event_type="spam_complaint",
        )


def test_process_hard_bounce_marks_lead_bounced():
    """Lead status set to BOUNCED and added to suppression_list."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])

    event = {
        "clean_email": "dead_mailbox@domain.com",
        "event_type": WebhookEventType.BOUNCE_HARD,
        "workspace_id": "ws_bounce",
        "lead_id": "lead_bounce",
        "campaign_id": "camp_bounce",
        "inbox_id": "inbox_bounce",
        "reason": "550 5.1.1 Mailbox does not exist",
    }

    with patch("leads.backend.services.suppression_service.add_suppression_entries_bulk") as mock_suppress, \
         patch("campaigns.backend.services.unsubscribe_service.retroactive_purge") as mock_purge, \
         patch("integrations.backend.services.email_sender_service.record_inbox_delivery_outcome") as mock_inbox:

        outcome = process_esp_event(supabase=mock_supabase, event=event)

        assert outcome["status"] == "processed"
        assert outcome["action_taken"] == "LEAD_BOUNCED_AND_SUPPRESSED"
        assert outcome["suppressed"] is True

        update_args = mock_table.update.call_args[0][0]
        assert update_args["status"] == "BOUNCED"
        assert update_args["bounce_reason"] == "550 5.1.1 Mailbox does not exist"
        mock_suppress.assert_called_once()


def test_process_unsubscribe_event():
    """Calls RFC 8058 compliant unsubscribe handler."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])

    event = {
        "clean_email": "unsub@enterprise.com",
        "event_type": WebhookEventType.UNSUBSCRIBE,
        "workspace_id": "ws_unsub",
        "lead_id": "lead_unsub",
    }

    with patch("campaigns.backend.services.unsubscribe_service.process_one_click_unsubscribe") as mock_unsub:
        outcome = process_esp_event(supabase=mock_supabase, event=event)
        assert outcome["status"] == "processed"
        assert outcome["action_taken"] == "LEAD_UNSUBSCRIBED"
        mock_unsub.assert_called_once_with(
            workspace_id="ws_unsub",
            lead_id="lead_unsub",
            email="unsub@enterprise.com",
            supabase=mock_supabase,
        )


# ==============================================================================
# Layer 0: Runaway Bounce & Spam Circuit Breaker Tests
# ==============================================================================

def test_circuit_breaker_trips_on_high_bounce_rate():
    """4 bounces out of 50 sends (8.0% > 3.0%) trips circuit breaker."""
    stats = {
        "sent_count": 50,
        "bounce_count": 4,
        "spam_complaint_count": 0,
    }
    decision = evaluate_campaign_circuit_breaker(stats)
    assert decision["should_trip"] is True
    assert decision["status"] == "TRIPPED"
    assert "CRITICAL_BOUNCE_SPIKE" in decision["tripwire"]
    assert decision["action"] == "AUTO_PAUSE_CAMPAIGN"
    assert decision["bounce_rate"] == 0.08
    assert len(decision["recommendations"]) > 0


def test_circuit_breaker_trips_on_spam_complaint():
    """2 spam complaints out of 100 sends (2.0% > 0.1%) trips circuit breaker."""
    stats = {
        "sent_count": 100,
        "bounce_count": 0,
        "spam_complaint_count": 2,
    }
    decision = evaluate_campaign_circuit_breaker(stats)
    assert decision["should_trip"] is True
    assert decision["status"] == "TRIPPED"
    assert "CRITICAL_SPAM_SPIKE" in decision["tripwire"]
    assert decision["spam_rate"] == 0.02


def test_circuit_breaker_healthy_campaign_does_not_trip():
    """0 bounces, 0 complaints out of 100 sends returns should_trip=False."""
    stats = {
        "sent_count": 100,
        "bounce_count": 0,
        "spam_complaint_count": 0,
    }
    decision = evaluate_campaign_circuit_breaker(stats)
    assert decision["should_trip"] is False
    assert decision["status"] == "HEALTHY"
    assert decision["bounce_rate"] == 0.0
    assert decision["spam_rate"] == 0.0


def test_circuit_breaker_insufficient_sample_size_guard():
    """1 bounce out of 5 sends (< 20 threshold) does not trip."""
    stats = {
        "sent_count": 5,
        "bounce_count": 1,
        "spam_complaint_count": 0,
    }
    decision = evaluate_campaign_circuit_breaker(stats)
    assert decision["should_trip"] is False
    assert decision["reason"] == "INSUFFICIENT_SAMPLE"
    assert decision["status"] == "HEALTHY"


def test_circuit_breaker_dual_spike():
    """Trips when both bounce rate and spam rate thresholds are exceeded."""
    stats = {
        "sent_count": 50,
        "bounce_count": 5,
        "spam_complaint_count": 3,
    }
    decision = evaluate_campaign_circuit_breaker(stats)
    assert decision["should_trip"] is True
    assert "CRITICAL_BOUNCE_SPIKE" in decision["tripwire"]
    assert "CRITICAL_SPAM_SPIKE" in decision["tripwire"]


# ==============================================================================
# Layer 1: Environmental Failure Analysis Tests
# ==============================================================================

def test_replay_attack_rejected_stale_timestamp():
    """Timestamp older than 600s is rejected by signature validators."""
    stale_ts = time.time() - 650
    future_ts = time.time() + 650

    # SendGrid
    assert verify_sendgrid_signature("pubkey", b"{}", "sig", stale_ts) is False
    assert verify_sendgrid_signature("pubkey", b"{}", "sig", future_ts) is False

    # Mailgun
    assert verify_mailgun_signature("key", "tok", stale_ts, "sig") is False
    assert verify_mailgun_signature("key", "tok", future_ts, "sig") is False


def test_malformed_json_and_missing_keys_handled_safely():
    """Handles corrupted or unexpected event payloads returning UNKNOWN without crashing."""
    corrupted_payloads = [
        {},
        {"random_key": "random_val"},
        {"event": None, "email": None},
        {"event": 12345, "email": {"nested": "not_str"}},
        {"RecordType": 9999},
        {"eventType": False},
    ]
    for raw in corrupted_payloads:
        res = normalize_esp_event(raw)
        assert res["event_type"] == WebhookEventType.UNKNOWN
        assert isinstance(res["clean_email"], str)


def test_missing_database_graceful_fallback():
    """Supabase connectivity drop does not crash event processing."""
    failing_supabase = MagicMock()
    failing_supabase.table.side_effect = ConnectionError("Supabase connection timeout")

    event = {
        "clean_email": "failover@lead.com",
        "event_type": WebhookEventType.BOUNCE_HARD,
        "workspace_id": "ws_failover",
        "lead_id": "lead_failover",
    }
    # Should not raise exception
    outcome = process_esp_event(supabase=failing_supabase, event=event)
    assert outcome["status"] == "processed"
    assert outcome["action_taken"] == "LEAD_BOUNCED_AND_SUPPRESSED"


def test_circuit_breaker_auto_pauses_campaign_in_db():
    """Simulates updating campaign in db when circuit breaker trips."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "c1", "status": "paused"}])

    decision = evaluate_campaign_circuit_breaker({
        "sent_count": 100,
        "bounce_count": 10,
        "spam_complaint_count": 0,
    })
    assert decision["should_trip"] is True

    # Perform DB pause
    if decision["should_trip"]:
        mock_supabase.table("campaigns").update({
            "status": "paused",
            "status_reason": f"CIRCUIT_BREAKER_{decision['tripwire']}",
        }).eq("id", "c1").execute()

    mock_table.update.assert_called_once_with({
        "status": "paused",
        "status_reason": f"CIRCUIT_BREAKER_{decision['tripwire']}",
    })


# ==============================================================================
# Layer 2: Human Paranoia & Security Defense Tests
# ==============================================================================

def test_mailgun_invalid_signature_rejected():
    """Fake Mailgun signature fails HMAC-SHA256 verification."""
    signing_key = "key-secret-123"
    token = "random-token-xyz"
    ts = str(int(time.time()))

    assert verify_mailgun_signature(signing_key, token, ts, "invalid_hex_sig") is False
    assert verify_mailgun_signature(signing_key, token, ts, "deadbeef1234") is False


def test_mailgun_valid_signature_success():
    """Valid Mailgun HMAC-SHA256 signature passes verification."""
    signing_key = "key-secret-abc"
    token = "token-valid-99"
    ts = str(int(time.time()))
    data = f"{ts}{token}".encode("utf-8")
    expected_sig = hmac.new(signing_key.encode("utf-8"), data, hashlib.sha256).hexdigest()

    assert verify_mailgun_signature(signing_key, token, ts, expected_sig) is True


def test_sendgrid_timing_attack_defense():
    """SendGrid signature verification uses constant-time compare_digest."""
    secret_key = "test-hmac-secret-1234"
    payload = b'{"event":"delivered","email":"test@elein.io"}'
    ts = str(int(time.time()))
    signed_data = ts.encode("utf-8") + payload
    raw_mac = hmac.new(secret_key.encode("utf-8"), signed_data, hashlib.sha256).digest()
    b64_sig = base64.b64encode(raw_mac).decode("utf-8")

    with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
        res = verify_sendgrid_signature(secret_key, payload, b64_sig, ts)
        assert res is True
        mock_compare.assert_called()


def test_sendgrid_ecdsa_signature_verification():
    """SendGrid NIST P-256 ECDSA curve signature verification."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pem_str = pem_bytes.decode("utf-8")

    payload = b'[{"event":"delivered","email":"ecdsa@test.com"}]'
    ts = str(int(time.time()))
    signed_data = ts.encode("utf-8") + payload
    sig = private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
    sig_b64 = base64.b64encode(sig).decode("utf-8")

    # Valid signature
    assert verify_sendgrid_signature(pem_str, payload, sig_b64, ts) is True

    # Tampered payload
    assert verify_sendgrid_signature(pem_str, b'[{"event":"dropped"}]', sig_b64, ts) is False


def test_verify_postmark_token():
    """Postmark shared token verification."""
    expected = "pm_secret_token_12345"
    assert verify_postmark_token(expected, expected) is True
    assert verify_postmark_token(expected, "wrong_token") is False
    assert verify_postmark_token(expected, "") is False
    assert verify_postmark_token("", expected) is False


def test_facade_class_wrapper():
    """ESPWebhookProcessor facade class correctly proxies all static methods."""
    assert ESPWebhookProcessor.ESPProvider is ESPProvider
    assert ESPWebhookProcessor.WebhookEventType is WebhookEventType

    raw = {"event": "delivered", "email": "facade@test.com"}
    norm = ESPWebhookProcessor.normalize_esp_event(raw)
    assert norm["event_type"] == WebhookEventType.DELIVERED

    stats = {"sent_count": 100, "bounce_count": 0, "spam_complaint_count": 0}
    decision = ESPWebhookProcessor.evaluate_campaign_circuit_breaker(stats)
    assert decision["should_trip"] is False
