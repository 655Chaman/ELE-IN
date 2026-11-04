"""
test_linkedin_community_messaging.py — Unit Tests for LinkedIn Group & Event Messaging Engine.

Phase 13: Shared Group & Event Direct Messaging Engine.
Verifies Three-Layer Logic Architecture:
  - Layer 0: Mutual group/event detection, community conversation payload formatting.
  - Layer 1: Rate limit 429/999 detection, 401 session expiry, 1,900 char clamping.
  - Layer 2: 30-day re-outreach cooldown, DNC suppression, Open Profile fallback.
"""

import pytest
from datetime import datetime, timezone, timedelta
from integrations.backend.services.linkedin_community_messaging import (
    LinkedInCommunityMessagingEngine,
    CommunityMessagingError,
    CommunityThrottledError,
    CommunitySessionExpiredError,
    MAX_COMMUNITY_MSGS_PER_DAY,
    MAX_MESSAGE_CHARACTERS
)


@pytest.fixture
def messaging_engine():
    return LinkedInCommunityMessagingEngine()


def test_generate_community_headers(messaging_engine):
    headers = messaging_engine.generate_community_headers(csrf_token="ajax:987654321")
    assert headers["csrf-token"] == "ajax:987654321"
    assert headers["X-RestLi-Protocol-Version"] == "2.0.0"
    assert "application/vnd.linkedin.normalized+json" in headers["Accept"]


def test_validate_outreach_candidate_mutual_group(messaging_engine):
    lead = {
        "profile_urn": "urn:li:fsd_profile:ACoAAABBB",
        "email": "sarah@acme.com",
        "group_ids": ["group_tech_execs", "group_ai_founders"]
    }
    sender_groups = {"group_ai_founders", "group_devops"}
    sender_events = set()

    eligible, reason, ctx_type, ctx_urn = messaging_engine.validate_outreach_candidate(
        lead=lead,
        sender_group_ids=sender_groups,
        sender_event_ids=sender_events
    )

    assert eligible is True
    assert reason is None
    assert ctx_type == "GROUP"
    assert ctx_urn == "urn:li:group:group_ai_founders"


def test_validate_outreach_candidate_mutual_event(messaging_engine):
    lead = {
        "profile_urn": "urn:li:fsd_profile:ACoAAACCC",
        "email": "mike@corp.com",
        "group_ids": [],
        "event_ids": ["event_saas_summit_2026"]
    }
    sender_groups = set()
    sender_events = {"event_saas_summit_2026"}

    eligible, reason, ctx_type, ctx_urn = messaging_engine.validate_outreach_candidate(
        lead=lead,
        sender_group_ids=sender_groups,
        sender_event_ids=sender_events
    )

    assert eligible is True
    assert ctx_type == "EVENT"
    assert ctx_urn == "urn:li:event:event_saas_summit_2026"


def test_validate_outreach_candidate_open_profile_fallback(messaging_engine):
    lead = {
        "profile_urn": "urn:li:fsd_profile:ACoAAADDD",
        "email": "david@open.io",
        "isOpenProfile": True,
        "group_ids": [],
        "event_ids": []
    }

    eligible, reason, ctx_type, ctx_urn = messaging_engine.validate_outreach_candidate(
        lead=lead,
        sender_group_ids=set(),
        sender_event_ids=set()
    )

    assert eligible is True
    assert ctx_type == "OPEN_PROFILE"
    assert ctx_urn == "FREE_INMAIL"


def test_validate_outreach_candidate_dnc_and_cooldown(messaging_engine):
    lead = {
        "profile_urn": "urn:li:fsd_profile:ACoAAALOCKED",
        "email": "blocked@target.com",
        "group_ids": ["shared_group"]
    }
    sender_groups = {"shared_group"}

    # 1. DNC Rejection
    eligible, reason, _, _ = messaging_engine.validate_outreach_candidate(
        lead=lead,
        sender_group_ids=sender_groups,
        sender_event_ids=set(),
        dnc_list={"blocked@target.com"}
    )
    assert eligible is False
    assert "Do-Not-Contact" in reason

    # 2. 30-day cooldown rejection
    now = datetime.now(timezone.utc)
    recent = {"urn:li:fsd_profile:ACoAAALOCKED": now - timedelta(days=5)}
    eligible, reason, _, _ = messaging_engine.validate_outreach_candidate(
        lead=lead,
        sender_group_ids=sender_groups,
        sender_event_ids=set(),
        recent_messaged_urns=recent
    )
    assert eligible is False
    assert "30-day community outreach cooldown" in reason

    # 3. Naive datetime resilience (Layer 1 Paranoia)
    naive_recent = {"urn:li:fsd_profile:ACoAAALOCKED": datetime.utcnow() - timedelta(days=5)}
    eligible, reason, _, _ = messaging_engine.validate_outreach_candidate(
        lead=lead,
        sender_group_ids=sender_groups,
        sender_event_ids=set(),
        recent_messaged_urns=naive_recent
    )
    assert eligible is False
    assert "30-day community outreach cooldown" in reason


def test_format_community_message_payload(messaging_engine):
    long_msg = "Hello! " * 400  # Exceeds 1900 chars
    payload = messaging_engine.format_community_message_payload(
        recipient_urn="ACoAAATEST123",
        message_body=long_msg,
        context_type="GROUP",
        context_urn="urn:li:group:tech_leaders"
    )

    assert payload["keyVersion"] == "LEGACY_INBOX"
    assert payload["conversationCreate"]["recipients"] == ["urn:li:fsd_profile:ACoAAATEST123"]
    assert payload["conversationCreate"]["context"]["groupUrn"] == "urn:li:group:tech_leaders"
    body_text = payload["conversationCreate"]["messages"][0]["body"]
    assert len(body_text) <= MAX_MESSAGE_CHARACTERS

    # Empty body check
    with pytest.raises(ValueError):
        messaging_engine.format_community_message_payload("ACoAAA123", "", "GROUP", "urn:li:group:1")


def test_parse_dispatch_response(messaging_engine):
    # 401 Session expired
    with pytest.raises(CommunitySessionExpiredError):
        messaging_engine.parse_dispatch_response(401, {"error": "unauthorized"})

    # 429 Throttle
    with pytest.raises(CommunityThrottledError):
        messaging_engine.parse_dispatch_response(429, {"error": "throttled"})

    # 200 Success
    resp = messaging_engine.parse_dispatch_response(200, {
        "value": {"conversationUrn": "urn:li:fsd_conversation:conv_789"}
    })
    assert resp["success"] is True
    assert resp["conversation_urn"] == "urn:li:fsd_conversation:conv_789"
