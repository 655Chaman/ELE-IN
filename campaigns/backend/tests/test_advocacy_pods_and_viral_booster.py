"""
test_advocacy_pods_and_viral_booster.py — Phase 21 Advocacy Pods & Viral LinkedIn Post Booster Test Suite.
Rigorously constructed under the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (Core math, models, URL normalization, contextual comment generation, and REST endpoints)
- Layer 1: Environmental Failure Analysis (Zero-Migration Supabase outages, in-memory fallback, self-boost exclusion, duplicate debouncing, inactive member skipping)
- Layer 2: Human Paranoia (Spreadsheet formula injection defense, anti-CFBR spam rejection, daily quota clamping, multi-tenant isolation, rapid replay defense)
"""

import copy
import re
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.advocacy_pod_service import (
    sanitize_text,
    normalize_linkedin_post_url,
    is_spam_comment,
    generate_contextual_comment,
    create_pod,
    list_pods,
    add_pod_member,
    list_pod_members,
    submit_post_for_boost,
    list_post_boosts,
    cancel_post_boost,
    get_advocacy_telemetry,
    _IN_MEMORY_PODS,
    _IN_MEMORY_MEMBERS,
    _IN_MEMORY_BOOSTS,
    _IN_MEMORY_ENGAGEMENTS,
)


# =============================================================================
# Paranoia Mocks & Fixtures
# =============================================================================

class FailingTableMock:
    """Simulates missing database relations or network partition (Zero-Migration resilience)."""
    def select(self, *args, **kwargs):
        return self

    def insert(self, *args, **kwargs):
        return self

    def update(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self, *args, **kwargs):
        raise RuntimeError("relation 'public.advocacy_pods' does not exist - simulating offline Supabase")


class FailingSupabaseMock:
    """Supabase client simulator when database is completely down or unmigrated."""
    def table(self, table_name: str):
        return FailingTableMock()


class WorkingTableMock:
    """Simulates a healthy database table chaining select, insert, update, and returning mock data."""
    def __init__(self, data: Optional[List[Dict[str, Any]]] = None):
        self._data = data if data is not None else []
        self._staged_data: Optional[List[Dict[str, Any]]] = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def insert(self, record, *args, **kwargs):
        self._staged_data = record if isinstance(record, list) else [record]
        return self

    def update(self, record, *args, **kwargs):
        self._staged_data = [record]
        return self

    def execute(self, *args, **kwargs):
        res = MagicMock()
        if self._staged_data is not None:
            res.data = self._staged_data
            self._staged_data = None
        else:
            res.data = self._data
        return res


class WorkingSupabaseMock:
    """Healthy Supabase client simulator with preloaded table datasets."""
    def __init__(self, data_by_table: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self.data_by_table = data_by_table or {}

    def table(self, table_name: str):
        return WorkingTableMock(self.data_by_table.get(table_name, []))


@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    """Isolates state mutations across tests by capturing and restoring in-memory store copies."""
    orig_pods = copy.deepcopy(_IN_MEMORY_PODS)
    orig_members = copy.deepcopy(_IN_MEMORY_MEMBERS)
    orig_boosts = copy.deepcopy(_IN_MEMORY_BOOSTS)
    orig_engagements = copy.deepcopy(_IN_MEMORY_ENGAGEMENTS)
    yield
    _IN_MEMORY_PODS.clear()
    _IN_MEMORY_PODS.update(orig_pods)
    _IN_MEMORY_MEMBERS.clear()
    _IN_MEMORY_MEMBERS.update(orig_members)
    _IN_MEMORY_BOOSTS.clear()
    _IN_MEMORY_BOOSTS.update(orig_boosts)
    _IN_MEMORY_ENGAGEMENTS.clear()
    _IN_MEMORY_ENGAGEMENTS.update(orig_engagements)


@pytest.fixture
def auth_client():
    """Client configured with FailingSupabaseMock to guarantee zero-migration resilience by default."""
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-advocacy"
    app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def healthy_client():
    """Client configured with WorkingSupabaseMock for operational DB verification."""
    mock_db = WorkingSupabaseMock({
        "advocacy_pods": [
            {
                "id": "pod-db-001",
                "workspace_id": "ws-test-advocacy",
                "name": "DB Enterprise Advocacy Swarm",
                "description": "Live production database pod",
                "settings": {"auto_boost": True, "golden_hour_minutes": 60},
                "is_active": True,
                "created_at": "2026-10-11T12:00:00Z",
                "updated_at": "2026-10-11T12:00:00Z"
            }
        ],
        "advocacy_pod_members": [
            {
                "id": "mem-db-001",
                "workspace_id": "ws-test-advocacy",
                "pod_id": "pod-db-001",
                "account_id": "acc-db-rep1",
                "account_name": "DB Rep 1",
                "daily_like_cap": 15,
                "daily_comment_cap": 5,
                "role": "member",
                "is_active": True
            }
        ],
        "advocacy_post_boosts": [
            {
                "id": "boost-db-001",
                "workspace_id": "ws-test-advocacy",
                "pod_id": "pod-db-001",
                "author_account_id": "acc-db-founder",
                "post_url": "https://www.linkedin.com/posts/db-post-activity-987",
                "post_content": "DB post content",
                "target_likes": 10,
                "target_comments": 5,
                "target_window_minutes": 60,
                "status": "boosting",
                "likes_count": 4,
                "comments_count": 2,
                "golden_hour_deadline": "2026-10-11T13:00:00Z"
            }
        ]
    })
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-advocacy"
    app.dependency_overrides[get_service_client] = lambda: mock_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# Layer 0: Foundational Layer Tests
# =============================================================================

class TestLayer0SanitizationAndURLNormalization:
    """Verifies baseline text sanitization and LinkedIn URL normalization mechanics."""

    def test_sanitize_text_clean(self):
        assert sanitize_text("Growth Swarm Pod") == "Growth Swarm Pod"

    def test_sanitize_text_none_and_empty(self):
        assert sanitize_text(None) == ""
        assert sanitize_text("") == ""
        assert sanitize_text("   ") == ""

    def test_sanitize_text_formula_injection_defense(self):
        assert sanitize_text("=SUM(A1:B1)") == "'=SUM(A1:B1)"
        assert sanitize_text("+1234567") == "'+1234567"
        assert sanitize_text("-CMD|' /C calc'!A0") == "'-CMD|' /C calc'!A0"
        assert sanitize_text("@IMPORTDATA('https://evil.com')") == "'@IMPORTDATA('https://evil.com')"
        # Leading whitespace is cleanly stripped before formula check
        assert sanitize_text("  =SUM(A1:B1)  ") == "'=SUM(A1:B1)"
        assert sanitize_text("\tTABBED") == "TABBED"

    def test_sanitize_text_control_characters_scrubbed(self):
        raw = "\x00Hello\x08 \x0BWorld\x1F\x7F"
        assert sanitize_text(raw) == "Hello World"

    def test_normalize_linkedin_url_clean(self):
        url = "https://www.linkedin.com/posts/sarahchen_growth-activity-724912893-xyz"
        assert normalize_linkedin_post_url(url) == url

    def test_normalize_linkedin_url_tracking_parameters_stripped(self):
        raw = "https://www.linkedin.com/posts/sarahchen_growth-activity-724912893-xyz?utm_source=share&utm_medium=member_desktop&rcm=ACoAA"
        expected = "https://www.linkedin.com/posts/sarahchen_growth-activity-724912893-xyz"
        assert normalize_linkedin_post_url(raw) == expected

    def test_normalize_linkedin_url_hash_fragment_and_trailing_slash(self):
        raw = "https://www.linkedin.com/posts/sarahchen_growth-activity-724912893-xyz/#comments"
        expected = "https://www.linkedin.com/posts/sarahchen_growth-activity-724912893-xyz"
        assert normalize_linkedin_post_url(raw) == expected

    def test_normalize_linkedin_url_non_linkedin_fallback(self):
        assert normalize_linkedin_post_url("https://twitter.com/example/status/123") == "https://twitter.com/example/status/123"

    def test_normalize_linkedin_url_none_and_empty(self):
        assert normalize_linkedin_post_url(None) == ""
        assert normalize_linkedin_post_url("") == ""
        assert normalize_linkedin_post_url("   ") == ""


class TestLayer0CommentGenerationAndAntiSpam:
    """Verifies contextual business comment generation and anti-CFBR spam filtering."""

    def test_is_spam_comment_short_string(self):
        assert is_spam_comment("great") is True
        assert is_spam_comment("nice post") is True
        assert is_spam_comment("hello") is True
        assert is_spam_comment("") is True
        assert is_spam_comment(None) is True

    def test_is_spam_comment_exact_low_effort_triggers(self):
        assert is_spam_comment("cfbr") is True
        assert is_spam_comment("CFBR") is True
        assert is_spam_comment("commenting for better reach") is True
        assert is_spam_comment("congratulations") is True
        assert is_spam_comment("following") is True
        assert is_spam_comment("+1") is True

    def test_is_spam_comment_prefix_suffix_triggers(self):
        assert is_spam_comment("cfbr to the moon and stars") is True
        assert is_spam_comment("really great work congrats") is True
        assert is_spam_comment("congratulations to the team on this") is True

    def test_is_spam_comment_passes_substantive_comment(self):
        substantive = "Spot-on perspective here. The biggest bottleneck we see teams facing when executing this is balancing automation volume with account reputation safety."
        assert is_spam_comment(substantive) is False

    def test_generate_contextual_comment_default(self):
        comment = generate_contextual_comment("Excited to announce our new product rollout today!")
        assert isinstance(comment, str)
        assert len(comment) > 25
        assert is_spam_comment(comment) is False

    def test_generate_contextual_comment_email_deliverability_keywords(self):
        post = "Why cold email deliverability is dropping across Google and Microsoft in 2026."
        comment = generate_contextual_comment(post)
        assert "deliverability" in comment.lower() or "reputation" in comment.lower()
        assert is_spam_comment(comment) is False

    def test_generate_contextual_comment_ai_agent_keywords(self):
        post = "How autonomous AI agents are transforming revenue operations."
        comment = generate_contextual_comment(post)
        assert "agent" in comment.lower() or "autonomous" in comment.lower() or "ai" in comment.lower()
        assert is_spam_comment(comment) is False


class TestLayer0ServiceCoreLogic:
    """Verifies baseline CRUD, scheduling, cancellation, and telemetry in the advocacy service."""

    def test_create_pod_default_settings(self):
        ws_id = "ws-core-01"
        pod = create_pod(workspace_id=ws_id, name="Founders Pod")
        assert pod["workspace_id"] == ws_id
        assert pod["name"] == "Founders Pod"
        assert pod["is_active"] is True
        assert pod["settings"]["golden_hour_minutes"] == 60
        assert pod["settings"]["auto_boost"] is True

    def test_create_pod_custom_settings(self):
        ws_id = "ws-core-02"
        custom_settings = {"golden_hour_minutes": 45, "auto_boost": False, "custom_rule": "strict"}
        pod = create_pod(workspace_id=ws_id, name="SDR Pod", description="SDR team only", settings=custom_settings)
        assert pod["name"] == "SDR Pod"
        assert pod["description"] == "SDR team only"
        assert pod["settings"]["golden_hour_minutes"] == 45
        assert pod["settings"]["auto_boost"] is False
        assert pod["settings"]["custom_rule"] == "strict"

    def test_list_pods_in_memory_default(self):
        ws_id = "ws-empty-01"
        pods = list_pods(workspace_id=ws_id)
        assert len(pods) >= 1
        assert pods[0]["workspace_id"] == ws_id

    def test_add_pod_member_and_list(self):
        ws_id = "ws-mem-01"
        pod = create_pod(workspace_id=ws_id, name="Alpha Pod")
        member = add_pod_member(
            workspace_id=ws_id,
            pod_id=pod["id"],
            account_id="acc-rep-100",
            account_name="Alice Smith",
            daily_like_cap=12,
            daily_comment_cap=4,
            role="admin"
        )
        assert member["account_id"] == "acc-rep-100"
        assert member["role"] == "admin"
        assert member["daily_like_cap"] == 12
        assert member["daily_comment_cap"] == 4

        members = list_pod_members(workspace_id=ws_id, pod_id=pod["id"])
        assert len(members) == 1
        assert members[0]["account_id"] == "acc-rep-100"

    def test_add_pod_member_update_existing_account(self):
        ws_id = "ws-mem-02"
        pod_id = "pod-test-dup"
        m1 = add_pod_member(ws_id, pod_id, account_id="acc-rep-101", account_name="Bob Original", daily_like_cap=10)
        assert m1["daily_like_cap"] == 10

        m2 = add_pod_member(ws_id, pod_id, account_id="acc-rep-101", account_name="Bob Updated", daily_like_cap=20)
        assert m2["account_name"] == "Bob Updated"
        assert m2["daily_like_cap"] == 20

        members = list_pod_members(ws_id, pod_id)
        assert len(members) == 1

    def test_submit_post_for_boost_staggered_schedule(self):
        ws_id = "ws-boost-01"
        pod_id = "pod-boost-01"
        # Seed 3 pod members
        add_pod_member(ws_id, pod_id, "acc-author", "Post Author", role="admin")
        add_pod_member(ws_id, pod_id, "acc-member-1", "Member One", role="member")
        add_pod_member(ws_id, pod_id, "acc-member-2", "Member Two", role="member")

        boost = submit_post_for_boost(
            workspace_id=ws_id,
            pod_id=pod_id,
            author_account_id="acc-author",
            post_url="https://www.linkedin.com/posts/test-author_post-1",
            post_content="Breakthrough insights on AI outbound workflows",
            target_likes=2,
            target_comments=1,
            target_window_minutes=60
        )
        assert boost["id"] is not None
        assert boost["status"] == "boosting"
        assert boost["post_url"] == "https://www.linkedin.com/posts/test-author_post-1"
        assert boost["scheduled_engagements_count"] > 0

        # Retrieve scheduled engagements from in-memory store
        engagements = _IN_MEMORY_ENGAGEMENTS.get(boost["id"], [])
        assert len(engagements) > 0
        for eng in engagements:
            assert eng["post_boost_id"] == boost["id"]
            assert eng["status"] == "queued"
            assert eng["account_id"] != "acc-author"  # Strict self-boost exclusion

    def test_list_post_boosts_filtered(self):
        ws_id = "ws-boost-filter"
        pod_a = "pod-a"
        pod_b = "pod-b"
        submit_post_for_boost(ws_id, pod_a, "acc-1", "https://www.linkedin.com/posts/url-a")
        submit_post_for_boost(ws_id, pod_b, "acc-2", "https://www.linkedin.com/posts/url-b")

        all_boosts = list_post_boosts(ws_id)
        assert len(all_boosts) == 2

        pod_a_boosts = list_post_boosts(ws_id, pod_id=pod_a)
        assert len(pod_a_boosts) == 1
        assert pod_a_boosts[0]["pod_id"] == pod_a

    def test_cancel_post_boost(self):
        ws_id = "ws-cancel-01"
        boost = submit_post_for_boost(ws_id, "pod-cancel", "acc-1", "https://www.linkedin.com/posts/url-cancel")
        boost_id = boost["id"]

        res = cancel_post_boost(ws_id, boost_id)
        assert res["success"] is True
        assert res["boost"]["status"] == "cancelled"

        updated_boosts = list_post_boosts(ws_id)
        cancelled = [b for b in updated_boosts if b["id"] == boost_id][0]
        assert cancelled["status"] == "cancelled"

    def test_get_advocacy_telemetry_aggregation(self):
        ws_id = "ws-telemetry-01"
        create_pod(ws_id, "Pod Telemetry")
        submit_post_for_boost(ws_id, "pod-1", "acc-1", "https://www.linkedin.com/posts/url-telemetry")

        telemetry = get_advocacy_telemetry(ws_id)
        assert telemetry["active_pods_count"] >= 1
        assert telemetry["total_boosted_posts"] >= 1
        assert telemetry["currently_boosting"] >= 1
        assert telemetry["golden_hour_success_rate_pct"] > 90.0
        assert telemetry["anti_cfbr_compliance_pct"] == 100.0


class TestLayer0RouterEndpoints:
    """Verifies all 8 REST endpoints exposed by advocacy_pod_router via TestClient."""

    def test_get_pods_endpoint(self, auth_client):
        res = auth_client.get("/api/elein/advocacy/pods")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_post_pods_endpoint(self, auth_client):
        payload = {
            "name": "Executive Viral Pod",
            "description": "Leadership team advocacy pod",
            "settings": {"golden_hour_minutes": 50, "auto_boost": True}
        }
        res = auth_client.post("/api/elein/advocacy/pods", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["pod"]["name"] == "Executive Viral Pod"
        assert data["pod"]["settings"]["golden_hour_minutes"] == 50

    def test_post_and_get_pod_members_endpoints(self, auth_client):
        pod_res = auth_client.post("/api/elein/advocacy/pods", json={"name": "SDR Swarm"})
        pod_id = pod_res.json()["pod"]["id"]

        member_payload = {
            "account_id": "acc-sdr-99",
            "account_name": "Dave Growth",
            "daily_like_cap": 14,
            "daily_comment_cap": 4,
            "role": "member"
        }
        res = auth_client.post(f"/api/elein/advocacy/pods/{pod_id}/members", json=member_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["member"]["account_id"] == "acc-sdr-99"

        list_res = auth_client.get(f"/api/elein/advocacy/pods/{pod_id}/members")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["success"] is True
        assert len(list_data["data"]) >= 1

    def test_post_boost_post_endpoint(self, auth_client):
        boost_payload = {
            "pod_id": "pod-router-01",
            "author_account_id": "acc-founder-01",
            "post_url": "https://www.linkedin.com/posts/sarahchen_router-boost-activity-9999",
            "post_content": "Deep thoughts on outbound sales infrastructure",
            "target_likes": 8,
            "target_comments": 4,
            "target_window_minutes": 45
        }
        res = auth_client.post("/api/elein/advocacy/boost-post", json=boost_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["boost"]["status"] == "boosting"
        assert data["boost"]["target_likes"] == 8

    def test_get_boosts_endpoint(self, auth_client):
        res = auth_client.get("/api/elein/advocacy/boosts")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "data" in data

    def test_post_cancel_boost_endpoint(self, auth_client):
        boost_res = auth_client.post("/api/elein/advocacy/boost-post", json={
            "pod_id": "pod-c1",
            "author_account_id": "acc-c1",
            "post_url": "https://www.linkedin.com/posts/cancel-me-1234"
        })
        boost_id = boost_res.json()["boost"]["id"]

        cancel_res = auth_client.post(f"/api/elein/advocacy/boosts/{boost_id}/cancel")
        assert cancel_res.status_code == 200
        cancel_data = cancel_res.json()
        assert cancel_data["success"] is True

    def test_get_telemetry_endpoint(self, auth_client):
        res = auth_client.get("/api/elein/advocacy/telemetry")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "telemetry" in data
        assert "golden_hour_success_rate_pct" in data["telemetry"]
        assert "anti_cfbr_compliance_pct" in data["telemetry"]


# =============================================================================
# Layer 1: Environmental Failure Analysis Tests
# =============================================================================

class TestLayer1ZeroMigrationSupabaseOutages:
    """Verifies that Zero-Migration DB outages and network drops trigger graceful in-memory fallbacks."""

    def test_service_functions_survive_failing_supabase(self):
        failing_db = FailingSupabaseMock()
        ws_id = "ws-failing-db"

        # 1. create_pod
        pod = create_pod(ws_id, "Offline Pod", supabase=failing_db)
        assert pod["id"] is not None
        assert pod["name"] == "Offline Pod"

        # 2. list_pods
        pods = list_pods(ws_id, supabase=failing_db)
        assert len(pods) >= 1

        # 3. add_pod_member
        member = add_pod_member(ws_id, pod["id"], "acc-offline-1", "Offline Member", supabase=failing_db)
        assert member["account_id"] == "acc-offline-1"

        # 4. list_pod_members
        members = list_pod_members(ws_id, pod["id"], supabase=failing_db)
        assert len(members) == 1

        # 5. submit_post_for_boost
        boost = submit_post_for_boost(
            ws_id, pod["id"], "acc-offline-author",
            "https://www.linkedin.com/posts/offline-post-123",
            supabase=failing_db
        )
        assert boost["status"] == "boosting"

        # 6. list_post_boosts
        boosts = list_post_boosts(ws_id, supabase=failing_db)
        assert len(boosts) >= 1

        # 7. cancel_post_boost
        cancelled = cancel_post_boost(ws_id, boost["id"], supabase=failing_db)
        assert cancelled["success"] is True

        # 8. get_advocacy_telemetry
        telemetry = get_advocacy_telemetry(ws_id, supabase=failing_db)
        assert telemetry["active_pods_count"] >= 1

    def test_all_router_endpoints_survive_failing_supabase(self, auth_client):
        """Verifies full router surface under complete database outage returns HTTP 200."""
        # 1. Get pods
        r1 = auth_client.get("/api/elein/advocacy/pods")
        assert r1.status_code == 200

        # 2. Post pods
        r2 = auth_client.post("/api/elein/advocacy/pods", json={"name": "Fallback Pod"})
        assert r2.status_code == 200
        pod_id = r2.json()["pod"]["id"]

        # 3. Post pod members
        r3 = auth_client.post(f"/api/elein/advocacy/pods/{pod_id}/members", json={"account_id": "acc-fb-1"})
        assert r3.status_code == 200

        # 4. Get pod members
        r4 = auth_client.get(f"/api/elein/advocacy/pods/{pod_id}/members")
        assert r4.status_code == 200

        # 5. Post boost
        r5 = auth_client.post("/api/elein/advocacy/boost-post", json={
            "pod_id": pod_id,
            "author_account_id": "acc-author-fb",
            "post_url": "https://www.linkedin.com/posts/fallback-url-55"
        })
        assert r5.status_code == 200
        boost_id = r5.json()["boost"]["id"]

        # 6. Get boosts
        r6 = auth_client.get("/api/elein/advocacy/boosts")
        assert r6.status_code == 200

        # 7. Cancel boost
        r7 = auth_client.post(f"/api/elein/advocacy/boosts/{boost_id}/cancel")
        assert r7.status_code == 200

        # 8. Get telemetry
        r8 = auth_client.get("/api/elein/advocacy/telemetry")
        assert r8.status_code == 200


class TestLayer1WorkingSupabaseDBVerification:
    """Verifies operational Supabase interactions when database is completely healthy."""

    def test_service_with_healthy_supabase(self):
        mock_db = WorkingSupabaseMock({
            "advocacy_pods": [{"id": "pod-1", "name": "DB Swarm", "workspace_id": "ws-ok"}],
            "advocacy_pod_members": [{"id": "mem-1", "account_id": "acc-1", "workspace_id": "ws-ok", "pod_id": "pod-1"}],
            "advocacy_post_boosts": [{"id": "b-1", "post_url": "https://linkedin.com/posts/db", "workspace_id": "ws-ok"}],
        })

        pod = create_pod("ws-ok", "New DB Pod", supabase=mock_db)
        assert pod["name"] == "New DB Pod"

        pods = list_pods("ws-ok", supabase=mock_db)
        assert len(pods) == 1
        assert pods[0]["id"] == "pod-1"

    def test_router_with_healthy_supabase(self, healthy_client):
        res = healthy_client.get("/api/elein/advocacy/pods")
        assert res.status_code == 200
        data = res.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "DB Enterprise Advocacy Swarm"


class TestLayer1SelfBoostExclusion:
    """Verifies that authors are strictly excluded from participating in their own boosts."""

    def test_author_account_is_never_assigned_to_engagements(self):
        ws_id = "ws-self-boost"
        pod_id = "pod-sb-1"

        # Register author and two peers
        add_pod_member(ws_id, pod_id, "author-rep", "Author Rep")
        add_pod_member(ws_id, pod_id, "peer-rep-1", "Peer Rep One")
        add_pod_member(ws_id, pod_id, "peer-rep-2", "Peer Rep Two")

        boost = submit_post_for_boost(
            workspace_id=ws_id,
            pod_id=pod_id,
            author_account_id="author-rep",
            post_url="https://www.linkedin.com/posts/author-post-exclusive",
            target_likes=10,
            target_comments=5
        )

        engagements = _IN_MEMORY_ENGAGEMENTS.get(boost["id"], [])
        assigned_accounts = [e["account_id"] for e in engagements]

        assert "author-rep" not in assigned_accounts
        assert len(assigned_accounts) > 0
        for acc in assigned_accounts:
            assert acc in ("peer-rep-1", "peer-rep-2")

    def test_sole_member_author_creates_boost_without_engagements(self):
        ws_id = "ws-lone-author"
        pod_id = "pod-lone-1"
        add_pod_member(ws_id, pod_id, "lone-author", "Lone Author")

        boost = submit_post_for_boost(
            workspace_id=ws_id,
            pod_id=pod_id,
            author_account_id="lone-author",
            post_url="https://www.linkedin.com/posts/lone-author-post"
        )

        assert boost["status"] == "boosting"
        assert boost["scheduled_engagements_count"] == 0
        assert len(_IN_MEMORY_ENGAGEMENTS.get(boost["id"], [])) == 0


class TestLayer1DuplicateSubmissionDebounce:
    """Verifies duplicate submission detection and debouncing within active golden hour windows."""

    def test_duplicate_submission_returns_existing_boost(self):
        ws_id = "ws-dedup"
        pod_id = "pod-dedup-1"
        url = "https://www.linkedin.com/posts/dedup-test-post-001"

        b1 = submit_post_for_boost(ws_id, pod_id, "acc-1", url, target_likes=5)
        b2 = submit_post_for_boost(ws_id, pod_id, "acc-1", url, target_likes=15)

        assert b1["id"] == b2["id"]
        # Ensure we didn't duplicate in-memory boosts
        all_boosts = list_post_boosts(ws_id)
        matching = [b for b in all_boosts if b["post_url"] == url]
        assert len(matching) == 1

    def test_duplicate_submission_with_tracking_params_debounced(self):
        ws_id = "ws-dedup-params"
        pod_id = "pod-dedup-2"
        base_url = "https://www.linkedin.com/posts/clean-activity-555"
        dirty_url = "https://www.linkedin.com/posts/clean-activity-555?utm_source=share&utm_medium=android_app#comments"

        b1 = submit_post_for_boost(ws_id, pod_id, "acc-1", base_url)
        b2 = submit_post_for_boost(ws_id, pod_id, "acc-1", dirty_url)

        assert b1["id"] == b2["id"]


class TestLayer1InactiveMembersSkipping:
    """Verifies that inactive or disconnected members are excluded from engagement scheduling."""

    def test_inactive_members_never_scheduled(self):
        ws_id = "ws-inactive-check"
        pod_id = "pod-inact-1"

        # Member 1 is active, Member 2 is inactive
        m1 = add_pod_member(ws_id, pod_id, "acc-active", "Active Rep")
        m2 = add_pod_member(ws_id, pod_id, "acc-inactive", "Inactive Rep")
        m2["is_active"] = False

        boost = submit_post_for_boost(
            ws_id, pod_id, "acc-author",
            "https://www.linkedin.com/posts/inactive-test-post",
            target_likes=5,
            target_comments=2
        )

        engagements = _IN_MEMORY_ENGAGEMENTS.get(boost["id"], [])
        assigned = [e["account_id"] for e in engagements]
        assert "acc-inactive" not in assigned
        assert "acc-active" in assigned


# =============================================================================
# Layer 2: Human Paranoia & Extreme Input Guardrails Tests
# =============================================================================

class TestLayer2FormulaInjectionAndDirtyInputs:
    """Verifies defense against spreadsheet formula injection, malicious tokens, and malformed data."""

    def test_formula_injection_in_pod_name_and_description(self):
        ws_id = "ws-injection"
        malicious_name = "=cmd|'/c calc'!A0"
        malicious_desc = "@SUM(1+1)*cmd"

        pod = create_pod(ws_id, name=malicious_name, description=malicious_desc)
        assert pod["name"].startswith("'")
        assert pod["description"].startswith("'")

    def test_formula_injection_in_member_name(self):
        ws_id = "ws-inj-member"
        member = add_pod_member(ws_id, "pod-1", "acc-inj", account_name="+123456789=HYPERLINK()")
        assert member["account_name"].startswith("'")

    def test_formula_injection_in_post_content(self):
        ws_id = "ws-inj-content"
        boost = submit_post_for_boost(
            ws_id, "pod-1", "acc-1",
            "https://www.linkedin.com/posts/valid-url-123",
            post_content="-2+5+cmd|' /C calc'!A0"
        )
        assert boost["post_content"].startswith("'")

    def test_control_character_scrubbing_across_all_fields(self):
        ws_id = "ws-ctrl-chars"
        dirty_name = "Pod\x00\x08Name\x1F"
        pod = create_pod(ws_id, dirty_name)
        assert pod["name"] == "PodName"


class TestLayer2QuotaAndWindowClamping:
    """Verifies that human error in setting daily caps or time windows is physically clamped to safety limits."""

    def test_daily_like_cap_clamped_to_safety_ceiling(self):
        ws_id = "ws-clamp"
        # Overzealous admin enters 500 likes
        member = add_pod_member(ws_id, "pod-c", "acc-c1", daily_like_cap=500)
        assert member["daily_like_cap"] == 30  # Clamped to 30

    def test_daily_like_cap_clamped_to_safety_floor(self):
        ws_id = "ws-clamp"
        # Accidental negative or zero input
        member = add_pod_member(ws_id, "pod-c", "acc-c2", daily_like_cap=-50)
        assert member["daily_like_cap"] == 1  # Clamped to 1

    def test_daily_comment_cap_clamped_to_safety_ceiling(self):
        ws_id = "ws-clamp"
        member = add_pod_member(ws_id, "pod-c", "acc-c3", daily_comment_cap=250)
        assert member["daily_comment_cap"] == 15  # Clamped to 15

    def test_daily_comment_cap_clamped_to_safety_floor(self):
        ws_id = "ws-clamp"
        member = add_pod_member(ws_id, "pod-c", "acc-c4", daily_comment_cap=0)
        assert member["daily_comment_cap"] == 1  # Clamped to 1

    def test_target_window_minutes_clamped(self):
        ws_id = "ws-clamp"
        # Window too small (<15 mins)
        b1 = submit_post_for_boost(ws_id, "pod-c", "acc-1", "https://www.linkedin.com/posts/window-1", target_window_minutes=5)
        assert b1["target_window_minutes"] == 15

        # Window too large (>180 mins)
        b2 = submit_post_for_boost(ws_id, "pod-c", "acc-1", "https://www.linkedin.com/posts/window-2", target_window_minutes=999)
        assert b2["target_window_minutes"] == 180


class TestLayer2ValidationAndEndpointGuards:
    """Verifies that missing or malformed inputs return proper HTTP status codes."""

    def test_boost_missing_post_url_returns_400(self, auth_client):
        payload = {
            "pod_id": "pod-test",
            "author_account_id": "acc-1",
            "post_url": ""  # Missing URL
        }
        res = auth_client.post("/api/elein/advocacy/boost-post", json=payload)
        assert res.status_code == 400
        data = res.json()
        error_msg = data.get("error", {}).get("message") or data.get("detail", "")
        assert "post_url and author_account_id are required" in error_msg

    def test_boost_missing_author_account_id_returns_400(self, auth_client):
        payload = {
            "pod_id": "pod-test",
            "author_account_id": "",  # Missing author
            "post_url": "https://www.linkedin.com/posts/valid-post-url"
        }
        res = auth_client.post("/api/elein/advocacy/boost-post", json=payload)
        assert res.status_code == 400
        data = res.json()
        error_msg = data.get("error", {}).get("message") or data.get("detail", "")
        assert "post_url and author_account_id are required" in error_msg


class TestLayer2TenantIsolation:
    """Verifies that multi-tenant workspace data boundaries are strictly respected."""

    def test_pods_isolated_between_tenants(self):
        create_pod("tenant-A", "Tenant A Pod")
        create_pod("tenant-B", "Tenant B Pod")

        pods_a = list_pods("tenant-A")
        pods_b = list_pods("tenant-B")

        names_a = [p["name"] for p in pods_a]
        names_b = [p["name"] for p in pods_b]

        assert "Tenant A Pod" in names_a
        assert "Tenant B Pod" not in names_a
        assert "Tenant B Pod" in names_b
        assert "Tenant A Pod" not in names_b

    def test_boosts_isolated_between_tenants(self):
        submit_post_for_boost("tenant-A", "pod-a", "acc-a", "https://www.linkedin.com/posts/tenant-a-post")
        submit_post_for_boost("tenant-B", "pod-b", "acc-b", "https://www.linkedin.com/posts/tenant-b-post")

        boosts_a = list_post_boosts("tenant-A")
        boosts_b = list_post_boosts("tenant-B")

        urls_a = [b["post_url"] for b in boosts_a]
        urls_b = [b["post_url"] for b in boosts_b]

        assert "https://www.linkedin.com/posts/tenant-a-post" in urls_a
        assert "https://www.linkedin.com/posts/tenant-b-post" not in urls_a
        assert "https://www.linkedin.com/posts/tenant-b-post" in urls_b
        assert "https://www.linkedin.com/posts/tenant-a-post" not in urls_b


class TestLayer2RapidReplayDefense:
    """Verifies system stability and debounce consistency during rapid double-click submissions."""

    def test_rapid_back_to_back_submissions_produce_single_job(self, auth_client):
        payload = {
            "pod_id": "pod-replay-01",
            "author_account_id": "acc-replay-author",
            "post_url": "https://www.linkedin.com/posts/rapid-replay-test-activity-7788",
            "target_likes": 10,
            "target_comments": 5
        }

        # Simulate user frantically clicking "Boost Post" twice within 10 milliseconds
        res1 = auth_client.post("/api/elein/advocacy/boost-post", json=payload)
        res2 = auth_client.post("/api/elein/advocacy/boost-post", json=payload)

        assert res1.status_code == 200
        assert res2.status_code == 200

        data1 = res1.json()["boost"]
        data2 = res2.json()["boost"]

        # Debounced safely to identical boost ID
        assert data1["id"] == data2["id"]
