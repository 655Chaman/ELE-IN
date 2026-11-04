"""
test_pillar6_unified_inbox_and_crm_sync.py — Comprehensive Test Suite for Pillar 6
Unified Omnichannel Inbox & CRM Sync Engine (Phases 6.1 – 6.4)
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import pytest
import uuid
import re
from datetime import datetime, date, time as dt_time, timedelta, timezone
from unittest.mock import MagicMock, patch

from inbox.backend.services.inbox_service import (
    stage_inbound_webhook_message,
    sanitize_ai_draft,
    sync_inbox_messages,
    _IN_MEMORY_INBOUND_BUFFER,
    _inbound_buffer_lock,
)
from inbox.backend.services.sentiment_classifier import (
    classify_inbound_sentiment_and_intent,
    extract_ooo_return_date,
    INTENT_MEETING_REQUESTED,
    INTENT_POSITIVE_INTEREST,
    INTENT_OBJECTION,
    INTENT_OUT_OF_OFFICE,
    INTENT_NOT_INTERESTED,
    INTENT_WRONG_CONTACT,
    INTENT_NEUTRAL_QUESTION,
)
from inbox.backend.services.battlecard_service import (
    generate_battlecard_responses,
    get_competitive_intel,
    generate_suggested_meeting_slots,
)
from inbox.backend.services.referral_and_snooze_service import (
    extract_referral_contact,
    detect_company_wide_opt_out,
    calculate_timezone_aware_ooo_snooze,
    process_advanced_inbound_reply,
)
from campaigns.backend.services.crm_attribution_service import (
    validate_crm_deal_properties,
    enqueue_crm_dead_letter,
    retry_failed_crm_sync_dead_letters,
    sync_deal_to_crm,
    list_crm_dead_letters,
    calculate_deal_attribution,
    process_inbound_crm_event,
    _IN_MEMORY_CRM_DLQ,
    _IN_MEMORY_SYNC_LOGS,
    _crm_sync_lock,
)


# =============================================================================
# PHASE 6.1: REAL-TIME INBOUND SYNC & WEBHOOK BUFFER TESTS
# =============================================================================

class TestPhase61InboundWebhookBuffer:
    @pytest.fixture(autouse=True)
    def clean_buffer(self):
        with _inbound_buffer_lock:
            _IN_MEMORY_INBOUND_BUFFER.clear()
        yield
        with _inbound_buffer_lock:
            _IN_MEMORY_INBOUND_BUFFER.clear()

    def test_stage_inbound_webhook_message_success(self):
        ws_id = f"ws-{uuid.uuid4().hex[:8]}"
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        payload = {
            "message_text": "Sounds very interesting! Can you send more details?",
            "sender_name": "Alice Smith",
            "thread_id": "thread-101",
            "account_id": "acc-101",
        }

        res = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_id,
            platform="linkedin",
            platform_message_id=msg_id,
            payload=payload,
            thread_id="thread-101",
            sender_name="Alice Smith",
            account_id="acc-101",
        )

        assert res["status"] == "processed"
        assert res["buffered"] is True
        assert res["platform_message_id"] == msg_id

    def test_stage_inbound_webhook_drops_duplicate(self):
        ws_id = f"ws-{uuid.uuid4().hex[:8]}"
        msg_id = f"msg-dup-{uuid.uuid4().hex[:8]}"
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        payload = {
            "message_text": "First delivery of inbound reply.",
            "sender_name": "Bob Jones",
            "thread_id": "thread-202",
        }

        first_res = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_id,
            platform="email",
            platform_message_id=msg_id,
            payload=payload,
        )
        assert first_res["status"] == "processed"

        # Second delivery (replay attack or ESP webhook retry)
        second_res = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_id,
            platform="email",
            platform_message_id=msg_id,
            payload=payload,
        )
        assert second_res["status"] == "duplicate"
        assert second_res["buffered"] is False
        assert second_res["action"] == "ignored"

    def test_missing_message_id_generates_deterministic_fingerprint(self):
        ws_id = f"ws-{uuid.uuid4().hex[:8]}"
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        payload = {
            "message_text": "Hey there, let's connect on Tuesday.",
            "sender_name": "Charlie Brown",
            "timestamp": "2026-10-24T12:00:00Z"
        }

        # First call with platform_message_id=None
        res1 = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_id,
            platform="linkedin",
            platform_message_id=None,
            payload=payload,
        )
        assert res1["status"] == "processed"
        generated_id = res1["platform_message_id"]
        assert len(generated_id) == 64  # SHA-256

        # Second call with identical payload must be recognized as duplicate
        res2 = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_id,
            platform="linkedin",
            platform_message_id=None,
            payload=payload,
        )
        assert res2["status"] == "duplicate"
        assert res2["platform_message_id"] == generated_id

    def test_multi_tenant_isolation_on_identical_message_ids(self):
        ws_a = "ws-tenant-alpha"
        ws_b = "ws-tenant-beta"
        msg_id = "universal-msg-999"

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_sb.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        payload = {"message_text": "Hello tenant", "sender_name": "David"}

        res_a = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_a,
            platform="linkedin",
            platform_message_id=msg_id,
            payload=payload
        )
        assert res_a["status"] == "processed"

        # Tenant B with same message_id must NOT be marked duplicate of Tenant A
        res_b = stage_inbound_webhook_message(
            supabase=mock_sb,
            workspace_id=ws_b,
            platform="linkedin",
            platform_message_id=msg_id,
            payload=payload
        )
        assert res_b["status"] == "processed"


# =============================================================================
# PHASE 6.2: AI SENTIMENT & OBJECTION BATTLECARDS TESTS
# =============================================================================

class TestPhase62SentimentAndBattlecards:
    @pytest.mark.parametrize("text, expected_sentiment, expected_intent", [
        ("Sounds great, let's book a call next Tuesday at 2pm", "POSITIVE", INTENT_MEETING_REQUESTED),
        ("Here is my calendar link: https://calendly.com/prospect/15min", "POSITIVE", INTENT_MEETING_REQUESTED),
        ("I'd love to learn more about your deliverability engine!", "POSITIVE", INTENT_POSITIVE_INTEREST),
        ("Please remove me from your list and unsubscribe immediately", "NEGATIVE", INTENT_NOT_INTERESTED),
        ("Stop emailing me, reported as spam!", "NEGATIVE", INTENT_NOT_INTERESTED),
        ("I am out of the office until November 15th with limited email access", "OOO", INTENT_OUT_OF_OFFICE),
        ("I don't handle this area, please contact Sarah at sarah@acme.com", "REFERRAL", INTENT_WRONG_CONTACT),
        ("We are currently locked into a contract with Apollo.io", "OBJECTION", INTENT_OBJECTION),
        ("Leadership placed a strict budget freeze on all new software tools", "OBJECTION", INTENT_OBJECTION),
        ("How does your proxy rotation work compared to standard residential proxies?", "QUESTION", INTENT_NEUTRAL_QUESTION),
    ])
    def test_benchmark_b2b_sentiment_classification_accuracy(self, text, expected_sentiment, expected_intent):
        res = classify_inbound_sentiment_and_intent(text)
        assert res["normalized_sentiment"] == expected_sentiment
        assert res["intent"] == expected_intent

    def test_objection_automatically_attaches_battlecard_recommendation(self):
        text = "We already use Apollo for our outbound prospecting."
        lead = {"first_name": "Marcus", "company_name": "Globex Corp", "timezone": "America/New_York"}
        
        res = classify_inbound_sentiment_and_intent(text, lead=lead)
        assert res["normalized_sentiment"] == "OBJECTION"
        assert res.get("battlecard_recommended") is True
        
        battlecard = res.get("suggested_battlecard")
        assert battlecard is not None
        assert "responses" in battlecard
        assert "challenger" in battlecard["responses"]
        assert "consultative" in battlecard["responses"]
        assert "casual" in battlecard["responses"]
        assert len(battlecard.get("kill_points", [])) > 0
        assert "Apollo" in battlecard.get("competitor_intel", {}).get("competitor", "")

    def test_sanitize_ai_draft_neutralizes_prompt_leaks_and_codeblocks(self):
        dirty_draft = '```AI: Here is a draft reply:\nAs an AI language model, I recommend you connect with us.```'
        cleaned = sanitize_ai_draft(dirty_draft, lead_name="Sarah Connor")
        assert "```" not in cleaned
        assert "as an ai language model" not in cleaned.lower()
        assert "here is a draft reply" not in cleaned.lower()
        assert len(cleaned) <= 2000

    def test_generate_suggested_meeting_slots_skips_weekends(self):
        slots = generate_suggested_meeting_slots(lead_tz="America/New_York", num_slots=3)
        assert len(slots) == 3
        for slot in slots:
            assert "formatted_label" in slot
            assert "iso_utc" in slot
            dt = datetime.fromisoformat(slot["iso_utc"].replace("Z", "+00:00"))
            assert dt.weekday() not in (5, 6)  # Not Saturday or Sunday


# =============================================================================
# PHASE 6.3: WORKING-HOURS OOO SNOOZE & REFERRAL INGESTION TESTS
# =============================================================================

class TestPhase63OOOSnoozeAndReferral:
    def test_extract_ooo_return_date_and_snooze_days(self):
        ref_dt = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
        text = "I am currently away on vacation, returning October 28th."
        ooo = extract_ooo_return_date(text, reference_date=ref_dt)
        assert ooo["has_return_date"] is True
        assert ooo["return_date"] == "2026-10-28"
        assert ooo["snooze_days"] == 8

    def test_weekend_rollover_friday_return_rolls_to_monday_morning(self):
        # 2026-10-23 is Friday. Next day is Saturday.
        ref_dt = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)
        lead = {"email": "lead@acme.com", "timezone": "America/New_York"}
        campaign = {"schedule": {"days": [1, 2, 3, 4, 5], "start_time": "09:00", "end_time": "17:00"}}

        snooze = calculate_timezone_aware_ooo_snooze(
            lead=lead,
            campaign=campaign,
            return_date_str="2026-10-23",
            reference_date=ref_dt,
        )
        next_dt = datetime.fromisoformat(snooze["snooze_until_iso"])
        assert next_dt.weekday() == 0  # Monday!
        assert snooze["is_weekend_rollover"] is True

    def test_extract_referral_contact_valid(self):
        text = "I am not the right person for this. Please reach out to Sarah Miller at sarah@acme.com."
        ref = extract_referral_contact(text, referring_email="john@acme.com")
        assert ref["has_referral"] is True
        assert ref["is_valid_referral"] is True
        assert ref["referral_email"] == "sarah@acme.com"
        assert ref["referral_first_name"] == "Sarah"
        assert ref["referral_last_name"] == "Miller"

    def test_self_referral_blocked(self):
        text = "Contact me at john@acme.com instead."
        ref = extract_referral_contact(text, referring_email="john@acme.com")
        assert ref["is_valid_referral"] is False
        assert ref["rejection_reason"] == "SELF_REFERRAL_DETECTED"

    def test_company_wide_opt_out_detection_and_freemail_exemption(self):
        # 1. Corporate domain should be flagged for company-wide suppression
        corp_text = "Please remove our entire company from your mailing list."
        opt_corp = detect_company_wide_opt_out(corp_text, email="alex@corpbrand.com")
        assert opt_corp["is_company_wide"] is True
        assert opt_corp["domain"] == "corpbrand.com"

        # 2. Consumer webmail (e.g. Gmail) must NEVER trigger company-wide suppression
        gmail_text = "Take our whole team off your list."
        opt_gmail = detect_company_wide_opt_out(gmail_text, email="alex@gmail.com")
        assert opt_gmail["is_company_wide"] is False
        assert opt_gmail["reason"] == "FREE_WEBMAIL_DOMAIN_CANNOT_BE_COMPANY_SUPPRESSED"


# =============================================================================
# PHASE 6.4: BI-DIRECTIONAL CRM DEAL SYNC & DEAD LETTER QUEUE TESTS
# =============================================================================

class TestPhase64CRMDealSyncAndDLQ:
    @pytest.fixture(autouse=True)
    def clean_dlq(self):
        with _crm_sync_lock:
            _IN_MEMORY_CRM_DLQ.clear()
            _IN_MEMORY_SYNC_LOGS.clear()
        yield
        with _crm_sync_lock:
            _IN_MEMORY_CRM_DLQ.clear()
            _IN_MEMORY_SYNC_LOGS.clear()

    def test_validate_crm_deal_properties_sanitizes_injection(self):
        malicious = {
            "deal_id": "deal-123",
            "dealname": "=HYPERLINK('http://evil.com', 'Malicious Deal')",
            "amount": "$45,000.50",
            "stage": "closed_won",
            "custom_formula": "+2+5"
        }
        clean = validate_crm_deal_properties(malicious)
        assert not clean["dealname"].startswith("=")
        assert clean["amount"] == 45000.50
        assert not clean["custom_formula"].startswith("+")

    def test_crm_sync_rate_limit_429_enqueues_to_dlq(self):
        ws_id = "ws-enterprise-01"
        deal_payload = {
            "deal_id": "deal-999",
            "dealname": "Acme Renewal",
            "amount": 25000.0,
            "stage": "closed_won"
        }

        res = sync_deal_to_crm(
            workspace_id=ws_id,
            deal_data=deal_payload,
            provider="hubspot",
            simulate_429=True
        )

        assert res["status"] == "queued_dlq"
        assert res["deal_id"] == "deal-999"

        # Verify item is in Dead Letter Queue
        dlq_items = list_crm_dead_letters(workspace_id=ws_id)
        assert len(dlq_items) == 1
        assert dlq_items[0]["entity_id"] == "deal-999"
        assert dlq_items[0]["status"] == "pending"
        assert dlq_items[0]["retry_count"] == 0

    def test_retry_failed_crm_sync_dead_letters_exponential_backoff(self):
        ws_id = "ws-enterprise-01"
        deal_payload = {"deal_id": "deal-backoff-1", "amount": 10000.0}

        # Enqueue item
        enqueue_crm_dead_letter(
            workspace_id=ws_id,
            provider="hubspot",
            entity_type="deal",
            entity_id="deal-backoff-1",
            payload=deal_payload,
            error_message="HTTP 429",
            status_code=429,
            base_backoff_seconds=10
        )

        # Force item's next_retry_at into the past so retry worker processes it
        with _crm_sync_lock:
            _IN_MEMORY_CRM_DLQ[0]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        # Run retry worker with simulate_fail_all=True
        retry_res = retry_failed_crm_sync_dead_letters(
            max_retries=3,
            base_backoff_seconds=10,
            simulate_fail_all=True
        )

        assert retry_res["processed_count"] == 1
        assert retry_res["failed_count"] == 1

        with _crm_sync_lock:
            item = _IN_MEMORY_CRM_DLQ[0]
            assert item["retry_count"] == 1
            # Next retry should have backed off: 10 * 2^1 = 20s
            next_dt = datetime.fromisoformat(item["next_retry_at"].replace("Z", "+00:00"))
            assert next_dt > datetime.now(timezone.utc)

    def test_retry_exhausted_marks_failed_permanent(self):
        ws_id = "ws-enterprise-01"
        deal_payload = {"deal_id": "deal-exhausted", "amount": 5000.0}

        enqueue_crm_dead_letter(
            workspace_id=ws_id,
            provider="salesforce",
            entity_type="deal",
            entity_id="deal-exhausted",
            payload=deal_payload,
            error_message="HTTP 429",
            status_code=429
        )

        # Pre-set retry_count to 4 with max_retries = 5
        with _crm_sync_lock:
            _IN_MEMORY_CRM_DLQ[0]["retry_count"] = 4
            _IN_MEMORY_CRM_DLQ[0]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

        retry_res = retry_failed_crm_sync_dead_letters(
            max_retries=5,
            simulate_fail_all=True
        )

        assert retry_res["exhausted_count"] == 1
        with _crm_sync_lock:
            item = _IN_MEMORY_CRM_DLQ[0]
            assert item["status"] == "failed_permanent"
            assert item["retry_count"] == 5

    def test_echo_loop_prevention_on_inbound_crm_webhooks(self):
        ws_id = "ws-default"
        payload = {
            "event": "deal.stage_change",
            "data": {
                "deal_id": "deal-echo-1",
                "company_name": "Echo Corp",
                "stage": "closed_won",
                "domain": "echocorp.io"
            }
        }

        # First inbound webhook from CRM
        first_res = process_inbound_crm_event("deal.stage_change", payload, workspace_id=ws_id)
        assert first_res["status"] == "success"

        # Echo bounceback with identical payload within debounce window
        echo_res = process_inbound_crm_event("deal.stage_change", payload, workspace_id=ws_id)
        assert echo_res["status"] == "skipped_echo"
        assert "Echo loop suppressed" in echo_res["message"]
