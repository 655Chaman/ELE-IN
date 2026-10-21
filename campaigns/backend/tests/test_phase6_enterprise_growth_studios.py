"""
Phase 6: Enterprise Growth Studios, Multithread ABM, Bandit Optimization,
Boomerang Revival & Omnichannel Frontend-Backend Unification Test Suite.

Governance: Three-Layer Logic Architecture (Paranoia Framework)
- Layer 0 (Foundational): Full API & service verification across all 5 Enterprise Growth Studios.
- Layer 1 (Environmental): Zero-SQL-migration resilience (verifying in-memory fallbacks when Supabase tables do not exist).
- Layer 2 (Human Paranoia): Formula injection defense, anti-pestering cooldown guards, URL sanitization, and boundary clamping.
"""

import os
import pytest
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_current_user_id, get_supabase_client, get_service_client


class FailingTableMock:
    """Simulates unmigrated Supabase environment where new tables raise PostgREST errors."""
    def select(self, *args, **kwargs):
        return self
    def insert(self, *args, **kwargs):
        return self
    def update(self, *args, **kwargs):
        return self
    def delete(self, *args, **kwargs):
        return self
    def upsert(self, *args, **kwargs):
        return self
    def eq(self, *args, **kwargs):
        return self
    def neq(self, *args, **kwargs):
        return self
    def in_(self, *args, **kwargs):
        return self
    def order(self, *args, **kwargs):
        return self
    def limit(self, *args, **kwargs):
        return self
    def execute(self):
        raise RuntimeError("PGRST205: Could not find the table in the schema cache (Zero-Migration Simulation)")


class ZeroMigrationSupabaseMock:
    """Mock Supabase client simulating a workspace where ZERO SQL migrations have been run."""
    def table(self, name: str):
        return FailingTableMock()

    def rpc(self, fn_name: str, params: dict = None):
        return FailingTableMock()


@pytest.fixture
def zero_migration_client():
    """FastAPI TestClient authenticated as test-workspace with a Zero-Migration Supabase mock."""
    mock_db = ZeroMigrationSupabaseMock()
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
    app.dependency_overrides[get_current_user_id] = lambda: "user-test-phase6"
    app.dependency_overrides[get_supabase_client] = lambda: mock_db
    app.dependency_overrides[get_service_client] = lambda: mock_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ==============================================================================
# 1. ABM BUYING COMMITTEES & MULTITHREADING STUDIO
# ==============================================================================

def test_abm_studio_zero_migration_accounts_and_committees(zero_migration_client: TestClient):
    """
    Layer 0 & Layer 1: Verifies ABM target accounts and committee members load seamlessly
    from in-memory fallback stores when Supabase tables do not exist yet.
    """
    res = zero_migration_client.get("/api/elein/abm/accounts")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert len(body["accounts"]) >= 3

    stripe_acc = next((a for a in body["accounts"] if "stripe" in a["domain"]), body["accounts"][0])
    comm_res = zero_migration_client.get(f"/api/elein/abm/accounts/{stripe_acc['id']}/committee")
    assert comm_res.status_code == 200
    comm_body = comm_res.json()
    assert comm_body["success"] is True
    assert len(comm_body["members"]) >= 2


def test_abm_create_account_role_classification_and_heat_progression(zero_migration_client: TestClient):
    """
    Layer 0 & Layer 2: Verifies domain extraction, automatic buying committee role archetype
    classification, status progression, and composite heat score clamping [0, 100].
    """
    create_res = zero_migration_client.post(
        "/api/elein/abm/accounts/create-or-map",
        json={
            "company_name": "OpenAI Enterprise",
            "domain": "https://www.openai.com/enterprise?utm_source=linkedin",
            "tier": "tier_1",
            "employee_count": 1500,
            "industry": "Artificial Intelligence",
            "leads": [
                {"name": "Sarah Friar", "title": "Chief Financial Officer", "email": "sarah@openai.com"},
                {"name": "Brad Lightcap", "title": "VP of Global Sales & Operations", "email": "brad@openai.com"},
                {"name": "Matt Knight", "title": "Chief Information Security Officer", "email": "matt@openai.com"},
                {"name": "Alex Rivera", "title": "Account Executive", "email": "alex@openai.com"},
            ],
        },
    )
    assert create_res.status_code == 200
    data = create_res.json()["data"]
    account = data["account"]
    assert account["domain"] == "openai.com"

    archetypes = {m["prospect_name"]: m["role_archetype"] for m in data["committee_members"]}
    assert archetypes["Sarah Friar"] == "economic_buyer"
    assert archetypes["Brad Lightcap"] == "champion"
    assert archetypes["Matt Knight"] == "technical_evaluator"
    assert archetypes["Alex Rivera"] == "end_user"

    # Update member status to 'meeting_booked' and verify heat score & stage upgrade
    member_id = data["committee_members"][0]["id"]
    patch_res = zero_migration_client.patch(
        f"/api/elein/abm/committee/{member_id}/status",
        json={"status": "meeting_booked"},
    )
    assert patch_res.status_code == 200
    patch_data = patch_res.json()["data"]
    assert 0 <= patch_data["heat_summary"]["heat_score"] <= 100
    assert patch_data["heat_summary"]["stage"] == "opportunity"


def test_abm_multithread_launch_staggering_and_csv_formula_defense(zero_migration_client: TestClient):
    """
    Layer 0 & Layer 2: Verifies synchronized multithread launch with staggered interval clamping
    and CSV export formula injection defense.
    """
    # Inject a member with a malicious formula payload in name
    add_res = zero_migration_client.post(
        "/api/elein/abm/accounts/acc-stripe/committee/add",
        json={
            "prospect_name": "=CMD|' /C calc'!A0 Evil CFO",
            "title": "SVP Finance",
            "email": "evil@stripe.com",
            "linkedin_url": "javascript:alert(1)",
        },
    )
    assert add_res.status_code == 200
    member = add_res.json()["data"]["member"]
    assert member["prospect_name"].startswith("'=CMD")
    assert member["linkedin_url"] is None  # javascript: URI stripped by Layer 2 sanitizer

    # Launch multithreaded campaign with extreme interval (should clamp to 24h max)
    launch_res = zero_migration_client.post(
        "/api/elein/abm/launch-multithread",
        json={
            "account_id": "acc-stripe",
            "staggered_interval_hours": 999,
        },
    )
    assert launch_res.status_code == 200
    launch_data = launch_res.json()["data"]
    assert launch_data["staggered_interval_hours"] == 24
    assert launch_data["committee_size"] >= 2

    # Verify Copy Matrix & CSV Export
    matrix_res = zero_migration_client.get("/api/elein/abm/copy-matrix?company_name=Stripe")
    assert matrix_res.status_code == 200
    assert len(matrix_res.json()["matrix"]) == 4

    csv_res = zero_migration_client.get("/api/elein/abm/accounts/acc-stripe/committee/export-csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "'=CMD" in csv_res.text


# ==============================================================================
# 2. BANDIT COPY OPTIMIZER & TRIGGER RADAR STUDIO
# ==============================================================================

def test_bandit_thompson_sampling_feedback_and_self_healing_mutation(zero_migration_client: TestClient):
    """
    Layer 0, 1 & 2: Verifies Thompson Sampling Beta posteriors, feedback updates,
    and self-healing variant mutation under zero-migration fallback.
    """
    exp_res = zero_migration_client.get("/api/elein/bandit/experiments")
    assert exp_res.status_code == 200
    exp_data = exp_res.json()["data"]
    assert "selected_variant_id" in exp_data
    assert len(exp_data["all_arms"]) >= 3

    target_arm_id = exp_data["selected_variant_id"]

    # Record positive feedback
    fb_res = zero_migration_client.post(
        "/api/elein/bandit/feedback",
        json={"variant_id": target_arm_id, "outcome": "meeting_booked"},
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["status"] == "success"

    # Spawn a self-healing mutated challenger variant
    mut_res = zero_migration_client.post(
        "/api/elein/bandit/mutate-variant",
        json={"parent_variant_id": target_arm_id, "mutation_theme": "contrarian_question"},
    )
    assert mut_res.status_code == 200
    assert mut_res.json()["status"] == "success"
    assert "challenger_variant" in mut_res.json()


def test_trigger_radar_feed_and_enrollment(zero_migration_client: TestClient):
    """
    Layer 0 & 1: Verifies Trigger Radar live signal feed and 1-click campaign enrollment.
    """
    radar_res = zero_migration_client.get("/api/elein/bandit/triggers/radar")
    assert radar_res.status_code == 200
    events = radar_res.json()["events"]
    assert len(events) >= 1

    # Pick an event that is not yet enrolled, or reset status to PENDING
    target_ev = next((e for e in events if e.get("status") != "ENROLLED"), None)
    if not target_ev:
        from campaigns.backend.services.trigger_radar_service import _IN_MEMORY_TRIGGERS
        _IN_MEMORY_TRIGGERS[0]["status"] = "PENDING"
        target_ev = _IN_MEMORY_TRIGGERS[0]

    trigger_id = target_ev["id"]
    enroll_res = zero_migration_client.post(
        "/api/elein/bandit/triggers/enroll",
        json={"trigger_event_id": trigger_id, "campaign_id": "camp-enterprise-1"},
    )
    assert enroll_res.status_code == 200
    assert enroll_res.json()["status"] in ("success", "ignored", "blocked_suppressed")


# ==============================================================================
# 3. EVENT HARVESTER & MULTIMODAL VOICE/VIDEO STUDIO
# ==============================================================================

def test_event_harvester_and_multimodal_voice_video_studio(zero_migration_client: TestClient):
    """
    Layer 0, 1 & 2: Verifies LinkedIn Event harvesting, URL validation guard,
    batch attendee enrollment, conversational voice script synthesis, and video cards.
    """
    # Layer 2: Invalid non-LinkedIn URL should be rejected with 400
    bad_res = zero_migration_client.post(
        "/api/elein/events-multimodal/events/harvest",
        json={"event_url": "https://evil.example.com/phishing"},
    )
    assert bad_res.status_code == 400

    # Valid LinkedIn Event URL harvest
    harvest_res = zero_migration_client.post(
        "/api/elein/events-multimodal/events/harvest",
        json={
            "event_url": "https://www.linkedin.com/events/saasstrannual2026-719283746/",
            "event_name": "SaaStr Annual 2026 Executive Summit",
        },
    )
    assert harvest_res.status_code == 200
    harvest_data = harvest_res.json()
    assert harvest_data["status"] == "success"
    attendees = harvest_data["attendees"]
    assert len(attendees) >= 3

    # Batch enroll harvested attendees
    enroll_res = zero_migration_client.post(
        "/api/elein/events-multimodal/events/enroll-attendees",
        json={
            "attendee_ids": [a["id"] for a in attendees[:2]],
            "campaign_id": "camp-saastr-2026",
        },
    )
    assert enroll_res.status_code == 200
    assert enroll_res.json()["enrolled_count"] == 2

    # Generate conversational voice script
    voice_res = zero_migration_client.post(
        "/api/elein/events-multimodal/multimodal/generate-voice-script",
        json={
            "lead_name": "Elena Rostova",
            "company": "Stripe",
            "title": "VP Revenue Operations",
            "tone": "casual_peer",
        },
    )
    assert voice_res.status_code == 200
    voice_data = voice_res.json()
    assert voice_data["status"] == "success"
    assert voice_data["estimated_duration_sec"] > 0

    # Generate personalized video prospecting card
    video_res = zero_migration_client.post(
        "/api/elein/events-multimodal/multimodal/generate-video-card",
        json={
            "lead_name": "Elena Rostova",
            "company": "Stripe",
            "video_topic": "ABM Buying Committee Audit",
        },
    )
    assert video_res.status_code == 200
    assert video_res.json()["status"] == "success"


# ==============================================================================
# 4. CHAMPION BOOMERANG, WARM INTRO GRAPH & CLOSED-LOST REVIVAL STUDIO
# ==============================================================================

def test_boomerang_job_changes_warm_intros_and_anti_pestering_guard(zero_migration_client: TestClient):
    """
    Layer 0, 1 & 2: Verifies Champion Job-Change Boomerang scoring, internal promotion detection,
    warm intro dual-script generation, and the 14-day Closed-Lost Anti-Pestering Guard.
    """
    # 1. List and create job change
    jc_list = zero_migration_client.get("/api/elein/boomerang/job-changes")
    assert jc_list.status_code == 200
    assert len(jc_list.json()["job_changes"]) >= 3

    jc_create = zero_migration_client.post(
        "/api/elein/boomerang/job-changes",
        json={
            "prospect_name": "Claire Underwood",
            "previous_company": "Figma",
            "previous_title": "Director of Growth",
            "new_company": "Figma",  # Same company -> should detect internal promotion!
            "new_title": "VP of Global Growth",
            "relationship_type": "past_customer",
            "days_in_new_role": 14,
        },
    )
    assert jc_create.status_code == 200
    jc_record = jc_create.json()["data"]
    assert jc_record["is_internal_promotion"] is True
    assert 0 <= jc_record["buying_window_score"] <= 100

    # 2. Warm intro path creation
    wp_create = zero_migration_client.post(
        "/api/elein/boomerang/warm-intros",
        json={
            "target_prospect_name": "Dario Amodei",
            "target_company": "Anthropic",
            "target_title": "CEO",
            "connector_name": "Elena Rostova",
            "connector_role": "VP RevOps at Stripe",
            "bridge_type": "shared_investor",
            "overlap_context": "Shared Series C board network",
        },
    )
    assert wp_create.status_code == 200
    wp_record = wp_create.json()["data"]
    assert "intro_request_draft" in wp_record
    assert "direct_bridge_draft" in wp_record

    # 3. Layer 2 Paranoia: 14-day Anti-Pestering Guard on Closed-Lost Revival
    premature_revival = zero_migration_client.post(
        "/api/elein/boomerang/revivals",
        json={
            "prospect_name": "Too Soon Prospect",
            "company_name": "Acme Corp",
            "title": "CRO",
            "lost_reason": "budget_freeze",
            "days_since_lost": 5,  # < 14 days cooldown!
            "force_override": False,
        },
    )
    assert premature_revival.status_code == 400
    err_text = str(premature_revival.json())
    assert "Anti-Pestering" in err_text or "14" in err_text

    # Valid Closed-Lost Revival (120 days elapsed)
    valid_revival = zero_migration_client.post(
        "/api/elein/boomerang/revivals",
        json={
            "prospect_name": "Ready Prospect",
            "company_name": "Acme Corp",
            "title": "CRO",
            "lost_reason": "missing_feature",
            "days_since_lost": 120,
            "original_deal_value": 48000,
            "revival_trigger": "Launched ABM Buying Committee Multithreading",
        },
    )
    assert valid_revival.status_code == 200
    rev_record = valid_revival.json()["data"]
    assert rev_record["revival_score"] >= 70


# ==============================================================================
# 5. OMNICHANNEL RETARGETING CASCADE & SOCIAL PRE-WARM STUDIO
# ==============================================================================

def test_omnichannel_retargeting_4tier_cascade_and_prewarm_safety(zero_migration_client: TestClient):
    """
    Layer 0, 1 & 2: Verifies the 4-tier Omnichannel Retargeting Cascade simulator
    (/api/elein/campaigns/evaluate-omnichannel-route) and Social Pre-Warm sentiment safety guard.
    """
    # Tier 1: 1st-degree connected on LinkedIn -> routes to 'linkedin_dm'
    t1_res = zero_migration_client.post(
        "/api/elein/campaigns/evaluate-omnichannel-route",
        json={
            "email": "alex@techscale.io",
            "linkedin_url": "https://linkedin.com/in/alex-vance",
            "is_connected": True,
            "inmail_eligible": True,
            "cascade_order": ["linkedin", "email", "inmail"],
        },
    )
    assert t1_res.status_code == 200
    assert t1_res.json()["routed_channel"] in ("linkedin_dm", "linkedin")

    # Tier 2: Not connected on LinkedIn, but deliverable email present -> routes to 'email'
    t2_res = zero_migration_client.post(
        "/api/elein/campaigns/evaluate-omnichannel-route",
        json={
            "email": "alex@techscale.io",
            "linkedin_url": "https://linkedin.com/in/alex-vance",
            "is_connected": False,
            "inmail_eligible": True,
            "cascade_order": ["linkedin", "email", "inmail"],
        },
    )
    assert t2_res.status_code == 200
    assert t2_res.json()["routed_channel"] == "email"
    assert t2_res.json()["branch"] == "Email"

    # Social Pre-Warm Sentiment Safety Guard (Layer 2: block grief/layoff posts)
    unsafe_post_res = zero_migration_client.post(
        "/api/elein/prewarm/analyze-post",
        json={"post_text": "Heartbroken to share that we had to lay off 30% of our engineering team today after a tragic week."},
    )
    assert unsafe_post_res.status_code == 200
    sentiment_data = unsafe_post_res.json()["data"]
    assert sentiment_data["is_safe_to_engage"] is False
