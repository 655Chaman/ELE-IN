"""
test_waitlist_service.py
========================
Automated Verification Suite for Ele-in Waitlist Engine.
Validates the Three-Layer Logic Architecture:
- Layer 0: Capture, queue position calculation, referral boosting, stats reporting.
- Layer 1: Environmental fallback resilience (zero dropped leads when Supabase offline).
- Layer 2: Human paranoia (double-submission idempotency, bot honeypots, input normalization).
"""

import os
import shutil
import pytest
from core.backend.services.waitlist_service import (
    WaitlistService,
    _LOCAL_WAITLIST_FILE,
    QUEUE_BASELINE_OFFSET,
    POINTS_PER_REFERRAL,
)


@pytest.fixture(autouse=True)
def clean_waitlist_test_env():
    """Isolates the local test waitlist file before and after each test."""
    backup_file = f"{_LOCAL_WAITLIST_FILE}.bak"
    if os.path.exists(_LOCAL_WAITLIST_FILE):
        shutil.copyfile(_LOCAL_WAITLIST_FILE, backup_file)
        os.remove(_LOCAL_WAITLIST_FILE)

    yield

    if os.path.exists(_LOCAL_WAITLIST_FILE):
        try:
            os.remove(_LOCAL_WAITLIST_FILE)
        except Exception:
            pass
    if os.path.exists(backup_file):
        shutil.move(backup_file, _LOCAL_WAITLIST_FILE)


def test_layer0_waitlist_submission_and_position():
    """Layer 0: Submitting a valid lead yields valid position and referral code."""
    service = WaitlistService()
    # Force fallback to verify pure local algorithmic correctness
    service._get_supabase_client = lambda: None

    res = service.submit_lead(
        email="sdr.leader@enterprise.co",
        full_name="Alex Mercer",
        company="Enterprise AI",
        role="VP Sales",
        team_size="21-50",
        monthly_outbound_volume="5,000 - 25,000",
        primary_channel="Multi-channel (LinkedIn + Email)"
    )

    assert res["status"] == "success"
    assert res["is_new"] is True
    assert res["email"] == "sdr.leader@enterprise.co"
    assert res["full_name"] == "Alex Mercer"
    assert res["referral_code"].startswith("ELE-")
    assert res["position"] >= QUEUE_BASELINE_OFFSET + 1
    assert res["referrals_count"] == 0


def test_layer0_referral_jump_and_queue_advancement():
    """Layer 0: When Alice refers Bob, Alice's referrals_count increments and priority increases."""
    service = WaitlistService()
    service._get_supabase_client = lambda: None

    # 1. Alice joins
    alice = service.submit_lead(
        email="alice@startup.io",
        full_name="Alice Founder",
        company="Startup.io"
    )
    alice_code = alice["referral_code"]
    initial_pos = alice["position"]

    # 2. Bob joins using Alice's referral code
    bob = service.submit_lead(
        email="bob@partner.org",
        full_name="Bob Partner",
        referred_by_code=alice_code
    )
    assert bob["status"] == "success"

    # 3. Verify Alice's updated status
    alice_updated = service.get_lead_status("alice@startup.io")
    assert alice_updated is not None
    assert alice_updated["referrals_count"] == 1
    assert alice_updated["priority_score"] == POINTS_PER_REFERRAL
    # Alice should have moved forward or maintained top rank relative to new entrants
    assert alice_updated["position"] <= initial_pos


def test_layer1_environmental_fallback_resilience():
    """Layer 1: When Supabase client throws an exception, fallback store transparently saves lead."""
    service = WaitlistService()

    class FailingSupabaseClient:
        def table(self, name):
            raise ConnectionError("Supabase cluster unreachable / Network timeout")

    service._get_supabase_client = lambda: FailingSupabaseClient()

    res = service.submit_lead(
        email="offline.lead@resilient.com",
        full_name="Offline Survivor"
    )

    assert res["status"] == "success"
    assert res["email"] == "offline.lead@resilient.com"

    # Ensure status lookup still succeeds from the local fallback store
    found = service.get_lead_status("offline.lead@resilient.com")
    assert found is not None
    assert found["email"] == "offline.lead@resilient.com"


def test_layer2_human_paranoia_duplicate_submission_amnesia():
    """Layer 2: User forgets they joined and re-submits with different casing and whitespace."""
    service = WaitlistService()
    service._get_supabase_client = lambda: None

    # First submission
    res1 = service.submit_lead(
        email="founder@unicorn.com",
        full_name="Jane Doe"
    )
    code1 = res1["referral_code"]

    # Re-submission with uppercase and spaces
    res2 = service.submit_lead(
        email="  FOUNDER@UNICORN.COM  ",
        full_name="Jane Doe"
    )

    assert res2["status"] == "already_registered"
    assert res2["is_new"] is False
    assert res2["referral_code"] == code1
    assert "already on the priority waitlist" in res2["message"]


def test_layer2_human_paranoia_honeypot_bot_neutralization():
    """Layer 2: Bot fills in hidden honeypot field; lead is silently dropped without polluting database."""
    service = WaitlistService()
    service._get_supabase_client = lambda: None

    res = service.submit_lead(
        email="spambot@scraping-farm.xyz",
        full_name="Spam Bot",
        honeypot_value="http://buy-viagra-now.ru"
    )

    assert res["status"] == "success"
    assert res["referral_code"] == "ELE-B0TTRAP"

    # Verify spambot was NOT written to store
    assert service.get_by_email("spambot@scraping-farm.xyz") is None


def test_layer2_human_paranoia_invalid_email_rejection():
    """Layer 2: Malformed email strings fail early before hitting persistence."""
    service = WaitlistService()

    with pytest.raises(ValueError, match="valid email"):
        service.submit_lead(email="not-an-email", full_name="Broken")

    with pytest.raises(ValueError, match="Full name"):
        service.submit_lead(email="valid@domain.com", full_name="   ")


def test_router_join_and_status_endpoints():
    """Validates FastAPI router integration for waitlist endpoints."""
    from fastapi.testclient import TestClient
    from core.backend.main import app

    client = TestClient(app)

    # 1. Join Waitlist
    resp = client.post("/api/waitlist", json={
        "email": "test.api.user@growth.com",
        "full_name": "Growth Lead",
        "company": "Fast Scaler",
        "role": "Head of Growth",
        "primary_channel": "Multi-channel (LinkedIn + Email)",
        "team_size": "6-20",
        "monthly_outbound_volume": "1,000 - 5,000"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "referral_code" in data
    assert data["position"] > 0
    ref_code = data["referral_code"]

    # 2. Check Status
    status_resp = client.get(f"/api/waitlist/status?q={ref_code}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["email"] == "test.api.user@growth.com"
    assert status_data["referral_code"] == ref_code

    # 3. Check Public Stats
    stats_resp = client.get("/api/waitlist/stats")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert stats_data["total_waitlist_count"] > 0


def test_layer0_waitlist_early30_discount_attached():
    """Layer 0: Every waitlist lead receives the EARLY30 30% off first year discount perk."""
    service = WaitlistService()
    service._get_supabase_client = lambda: None

    res = service.submit_lead(
        email="vip.founder@saas.com",
        full_name="VIP Founder"
    )

    assert "discount" in res
    assert res["discount"]["code"] == "EARLY30"
    assert res["discount"]["percent"] == 30
    assert "1st Year" in res["discount"]["duration_label"]


def test_billing_coupon_validation_endpoint():
    """Validates the /api/elein/billing/coupons/validate endpoint for 30% discount."""
    from fastapi.testclient import TestClient
    from core.backend.main import app

    client = TestClient(app)

    # Valid coupon EARLY30
    resp = client.post("/api/elein/billing/coupons/validate", json={
        "coupon_code": "EARLY30",
        "package_id": "growth_tier"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["discount_percent"] == 30
    # Growth tier normal $99 (9900 cents) -> 30% off is $69.30 (6930 cents)
    assert data["pricing"]["original_usd_cents"] == 9900
    assert data["pricing"]["discounted_usd_cents"] == 6930

    # Invalid coupon
    bad_resp = client.post("/api/elein/billing/coupons/validate", json={
        "coupon_code": "INVALID_CODE"
    })
    assert bad_resp.status_code == 404
