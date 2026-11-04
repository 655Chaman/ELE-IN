"""
test_voyager_mobile_sync.py — Unit Tests for Voyager Mobile Contact Sync Engine.

Tests Phase 03: LinkedIn Mobile Protocol & Contact Synchronization Interoperability.
Verifies Three-Layer Logic Architecture:
  - Layer 0: Mobile headers generation, vCard batch compiling, Open Profile detection.
  - Layer 1: Clamping at 50 contacts, RFC 5322 regex validation, HTTP 401/429 exception handling.
  - Layer 2: 21-day anti-resend cooldown enforcement, DNC suppression, poison string rejection.
"""

import pytest
from datetime import datetime, timezone, timedelta
from integrations.backend.services.voyager_mobile_sync import (
    VoyagerMobileSyncEngine,
    VoyagerMobileSyncError,
    MobileSyncThrottledError,
    MobileSessionExpiredError
)


@pytest.fixture
def sync_engine():
    return VoyagerMobileSyncEngine(client_os="iOS", client_version="9.28.1")


def test_generate_mobile_headers(sync_engine):
    headers = sync_engine.generate_mobile_headers(csrf_token="ajax:123456789")
    assert headers["csrf-token"] == "ajax:123456789"
    assert "iPhone; iOS 17.4" in headers["User-Agent"]
    assert headers["X-RestLi-Protocol-Version"] == "2.0.0"
    assert "mobile_contact_sync_" in headers["X-Li-Page-Instance"]


def test_validate_lead_rfc5322_and_poison_rejection(sync_engine):
    # Valid lead
    ok, err = sync_engine.validate_lead_for_mobile_sync({"email": "alex.mercer@enterprise.io"})
    assert ok is True
    assert err is None

    # Poison strings
    for poison in ["None", "null", "undefined", "n/a", ""]:
        ok, err = sync_engine.validate_lead_for_mobile_sync({"email": poison})
        assert ok is False
        assert "missing" in err.lower() or "poison" in err.lower()

    # Invalid email syntax
    ok, err = sync_engine.validate_lead_for_mobile_sync({"email": "not-an-email"})
    assert ok is False
    assert "Invalid RFC 5322" in err

    # Disposable domain rejection
    ok, err = sync_engine.validate_lead_for_mobile_sync({"email": "hacker@mailinator.com"})
    assert ok is False
    assert "Disposable or test email" in err


def test_validate_lead_dnc_and_21_day_cooldown(sync_engine):
    dnc_list = {"ceo@forbidden-target.com"}
    ok, err = sync_engine.validate_lead_for_mobile_sync(
        {"email": "ceo@forbidden-target.com"},
        dnc_emails=dnc_list
    )
    assert ok is False
    assert "Do-Not-Contact" in err

    # 21-day cooldown check
    now = datetime.now(timezone.utc)
    withdrawn = {
        "https://linkedin.com/in/recent-lead": now - timedelta(days=10),
        "https://linkedin.com/in/old-lead": now - timedelta(days=25)
    }

    # Still in cooldown (10 days ago < 21 days)
    ok, err = sync_engine.validate_lead_for_mobile_sync(
        {"email": "recent@company.com", "linkedin_url": "https://linkedin.com/in/recent-lead"},
        withdrawn_recipients=withdrawn
    )
    assert ok is False
    assert "21-day cooldown active" in err

    # Expired cooldown (25 days ago > 21 days)
    ok, err = sync_engine.validate_lead_for_mobile_sync(
        {"email": "old@company.com", "linkedin_url": "https://linkedin.com/in/old-lead"},
        withdrawn_recipients=withdrawn
    )
    assert ok is True


def test_validate_lead_naive_datetime_cooldown_resilience(sync_engine):
    """Layer 1 Paranoia: Naive datetimes from DB strings must not cause TypeError."""
    naive_dt = datetime.utcnow() - timedelta(days=5)  # Naive datetime without tzinfo
    withdrawn = {"target_lead": naive_dt}
    ok, err = sync_engine.validate_lead_for_mobile_sync(
        {"email": "target@corp.com", "linkedin_url": "target_lead"},
        withdrawn_recipients=withdrawn
    )
    assert ok is False
    assert "21-day cooldown active" in err


def test_build_synthetic_vcard_batch_clamping(sync_engine):
    # Generate 65 sample leads
    sample_leads = [
        {
            "id": f"lead_{i}",
            "name": f"Lead Number {i}",
            "email": f"prospect{i}@enterprise.com",
            "company": "Acme Corp",
            "title": "VP Sales"
        }
        for i in range(65)
    ]

    batch = sync_engine.build_synthetic_vcard_batch(sample_leads)
    assert batch["total_submitted"] == 65
    assert batch["valid_count"] == 50  # Hard clamped at batch_max_size 50
    assert len(batch["contacts"]) == 50
    assert batch["contacts"][0]["emails"] == ["prospect0@enterprise.com"]
    assert batch["contacts"][0]["firstName"] == "Lead"


def test_evaluate_open_profile_arbitrage(sync_engine):
    # Free InMail target (Open Profile)
    open_profile = {
        "name": "Sarah Connor",
        "isOpenProfile": True,
        "isPremium": True
    }
    arb = sync_engine.evaluate_open_profile_arbitrage(open_profile)
    assert arb["is_open_profile"] is True
    assert arb["can_send_free_inmail"] is True
    assert arb["channel_recommendation"] == "FREE_INMAIL"
    assert arb["credits_consumed"] == 0

    # Standard closed profile
    closed_profile = {
        "name": "John Connor",
        "isOpenProfile": False,
        "isPremium": False
    }
    arb_closed = sync_engine.evaluate_open_profile_arbitrage(closed_profile)
    assert arb_closed["can_send_free_inmail"] is False
    assert arb_closed["channel_recommendation"] == "INVITE_BY_CONTACT_SYNC"
    assert arb_closed["credits_consumed"] == 1


def test_format_invite_by_email_payload(sync_engine):
    long_note = "A" * 350
    payload = sync_engine.format_invite_by_email_payload(
        email="ELON@X.COM",
        full_name="Elon Musk",
        custom_message=long_note
    )
    assert payload["email"] == "elon@x.com"
    assert len(payload["message"]) == 300  # Clamped to 300 chars


def test_parse_sync_response_statuses(sync_engine):
    # 401 Session expired
    with pytest.raises(MobileSessionExpiredError):
        sync_engine.parse_sync_response(401, {"message": "unauthorized"})

    # 429 Throttle
    with pytest.raises(MobileSyncThrottledError):
        sync_engine.parse_sync_response(429, {"message": "rate limit exceeded"})

    # 200 Success with matched profiles
    mock_payload = {
        "elements": [
            {
                "entityUrn": "urn:li:fsd_profile:ACoAAA12345",
                "email": "lead1@corp.com",
                "connected": False
            },
            {
                "entityUrn": "urn:li:fsd_profile:ACoAAA67890",
                "email": "lead2@corp.com",
                "connected": True  # Already connected
            }
        ]
    }
    res = sync_engine.parse_sync_response(200, mock_payload)
    assert res["success"] is True
    assert res["total_matched"] == 2
    assert res["eligible_for_invite"] == 1  # 1 eligible, 1 already connected
