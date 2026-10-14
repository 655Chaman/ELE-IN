"""
Horizon 35B: Social Pre-Warming & Autonomous Multi-Touch Engagement Cadence
Governance: Three-Layer Logic Architecture (Paranoia Framework)

Unit tests covering:
- Layer 0: The Foundational Layer (Prewarmed lead detection, unwarmed cadence scheduling, router endpoint resolution)
- Layer 1: Environmental Failure Analysis (Sensitive topic suppression, idempotent execution lock, lock expiration, DB fallback)
- Layer 2: Human Paranoia & Security Hardening (Dangerous URL scheme rejection, formula injection & AI slop neutralization, Cross-Tenant IDOR isolation)
"""

import unittest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

from campaigns.backend.services.prewarm_service import (
    resolve_prewarm_status_for_execution,
    get_lead_prewarm_status,
    list_prewarm_queue,
    schedule_prewarm_sequence,
    analyze_post_sentiment,
    generate_contextual_comment,
    sanitize_url,
    sanitize_input,
    _PREWARM_EXECUTION_LOCKS,
    _IN_MEMORY_PREWARM_EVENTS,
    _SEED_PREWARM_EVENTS,
    BANNED_SLOP_PHRASES,
)
from campaigns.backend.routers.social_prewarm import (
    resolve_prewarm_execution_status_endpoint,
    ResolvePrewarmExecutionPayload,
)


class TestHorizon35bSocialPrewarmOrchestration(unittest.TestCase):

    def setUp(self):
        _PREWARM_EXECUTION_LOCKS.clear()
        _IN_MEMORY_PREWARM_EVENTS.clear()
        _IN_MEMORY_PREWARM_EVENTS.extend([dict(e) for e in _SEED_PREWARM_EVENTS])

    # -------------------------------------------------------------------------
    # LAYER 0: THE FOUNDATIONAL LAYER
    # -------------------------------------------------------------------------

    def test_layer0_prewarmed_lead_returns_ready_status(self):
        """
        Layer 0: If lead has completed_events >= required_touches, returns status='ready',
        is_prewarmed=True, branch='Prewarmed', and empty prewarm_comment.
        """
        # Inject 2 completed prewarm events for this lead
        _IN_MEMORY_PREWARM_EVENTS.extend([
            {
                "id": "evt-c1",
                "workspace_id": "ws-test",
                "lead_id": "lead-already-warm",
                "action_type": "profile_view",
                "status": "completed",
                "scheduled_for": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            },
            {
                "id": "evt-c2",
                "workspace_id": "ws-test",
                "lead_id": "lead-already-warm",
                "action_type": "post_like",
                "status": "completed",
                "scheduled_for": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            }
        ])

        res = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-already-warm",
            required_touches=2,
            supabase=None
        )

        self.assertEqual(res["status"], "ready")
        self.assertTrue(res["is_prewarmed"])
        self.assertEqual(res["completed_touches"], 2)
        self.assertEqual(res["branch"], "Prewarmed")
        self.assertTrue(res["is_safe_to_engage"])
        self.assertEqual(res["prewarm_comment"], "")
        self.assertEqual(res["prewarm_theme"], "general_b2b")

    def test_layer0_unwarmed_lead_schedules_cadence_and_generates_comment(self):
        """
        Layer 0: An unwarmed lead with safe post snippet triggers comment generation,
        automatically schedules the 3-touch cadence, and returns branch='Warming'.
        """
        post_snippet = "Deploying an autonomous AI agent cluster for high-volume sales prospecting."
        res = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-fresh-prospect",
            lead_url="https://linkedin.com/in/fresh-prospect",
            post_snippet=post_snippet,
            tone="insightful_query",
            supabase=None
        )

        self.assertEqual(res["status"], "in_progress")
        self.assertFalse(res["is_prewarmed"])
        self.assertEqual(res["completed_touches"], 0)
        self.assertEqual(res["branch"], "Warming")
        self.assertTrue(res["is_safe_to_engage"])
        self.assertTrue(res["scheduled"])
        self.assertFalse(res["duplicate_prevented"])
        self.assertEqual(res["prewarm_theme"], "ai_automation")
        self.assertGreater(len(res["prewarm_comment"]), 20)

    def test_layer0_router_resolve_execution_status_success(self):
        """
        Layer 0: Router endpoint POST /prewarm/resolve-execution-status returns HTTP 200
        with structured status data for valid payloads.
        """
        payload = ResolvePrewarmExecutionPayload(
            lead_id="lead-router-test-01",
            lead_url="https://linkedin.com/in/router-test",
            post_snippet="Growing our SDR pod and outbound pipeline efficiency this quarter.",
            tone="benchmark_data"
        )

        res = resolve_prewarm_execution_status_endpoint(
            payload=payload,
            workspace_id="ws-test",
            supabase=None
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["branch"], "Warming")
        self.assertTrue(data["is_safe_to_engage"])
        self.assertEqual(data["prewarm_theme"], "outbound_pipeline")
        self.assertIn("data", data["prewarm_comment"].lower())

    # -------------------------------------------------------------------------
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # -------------------------------------------------------------------------

    def test_layer1_sensitive_topics_suppressed_as_unsafe(self):
        """
        Layer 1 Environmental Paranoia: If post sentiment detects sensitive/grief/layoff/controversial
        topics, returns status='unsafe', branch='Unsafe', and suppresses outbound cadence.
        """
        sensitive_post = "Devastated to share our company announced a massive layoff today affecting 40% of staff."
        res = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-sensitive-prospect",
            post_snippet=sensitive_post,
            supabase=None
        )

        self.assertEqual(res["status"], "unsafe")
        self.assertFalse(res["is_prewarmed"])
        self.assertEqual(res["branch"], "Unsafe")
        self.assertFalse(res["is_safe_to_engage"])
        self.assertEqual(res["prewarm_theme"], "sensitive")
        self.assertEqual(res["prewarm_comment"], "")
        self.assertIn("layoff", res["safety_reason"])
        self.assertFalse(res.get("scheduled", False))

    def test_layer1_idempotent_execution_lock_prevents_duplicate_within_hour(self):
        """
        Layer 1 Environmental Paranoia: Repeated execution triggers within 1 hour for the same
        workspace and lead are intercepted by _PREWARM_EXECUTION_LOCKS, preventing duplicate spam.
        """
        # First call acquires lock and schedules prewarm
        res1 = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-double-trigger",
            post_snippet="Reaching out to new partners this quarter.",
            supabase=None
        )
        self.assertEqual(res1["status"], "in_progress")
        self.assertTrue(res1.get("scheduled"))
        self.assertFalse(res1.get("duplicate_prevented"))

        # Verify lock is in memory
        lock_key = "ws-test:lead-double-trigger"
        self.assertIn(lock_key, _PREWARM_EXECUTION_LOCKS)

        # Second call within seconds triggers duplicate prevention
        res2 = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-double-trigger",
            post_snippet="Reaching out to new partners this quarter.",
            supabase=None
        )
        self.assertTrue(res2["duplicate_prevented"])
        self.assertEqual(res2["branch"], "Warming")
        self.assertFalse(res2.get("scheduled", False))

    def test_layer1_execution_lock_expires_after_one_hour(self):
        """
        Layer 1 Environmental Paranoia: Execution lock expires after 3600 seconds, permitting
        fresh execution cycles after the cooldown window.
        """
        lock_key = "ws-test:lead-expired-lock"
        # Seed an expired lock from 2 hours ago
        _PREWARM_EXECUTION_LOCKS[lock_key] = {
            "locked_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "lead_id": "lead-expired-lock",
            "workspace_id": "ws-test"
        }

        res = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-expired-lock",
            post_snippet="Great conference keynote today on revenue architecture.",
            supabase=None
        )

        self.assertFalse(res["duplicate_prevented"])
        self.assertEqual(res["status"], "in_progress")
        self.assertTrue(res["scheduled"])

    def test_layer1_database_failure_resilient_in_memory_fallback(self):
        """
        Layer 1 Environmental Paranoia: If Supabase throws unexpected connection/query exceptions,
        the service seamlessly falls back to defensive in-memory operation without crashing.
        """
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("503 Service Unavailable: database connection pool exhausted")

        res = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-db-fallback",
            post_snippet="Scaling our SDR outreach with zero technical debt.",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "in_progress")
        self.assertEqual(res["branch"], "Warming")
        self.assertTrue(res["is_safe_to_engage"])
        self.assertTrue(res["scheduled"])

    # -------------------------------------------------------------------------
    # LAYER 2: HUMAN PARANOIA & SECURITY HARDENING
    # -------------------------------------------------------------------------

    def test_layer2_dangerous_url_schemes_rejected_with_value_error_and_400(self):
        """
        Layer 2 Human Paranoia: Rejects dangerous URI schemes (javascript:, data:, file:)
        with ValueError in service and HTTP 400 in router endpoint.
        """
        # Service level rejection
        with self.assertRaises(ValueError) as ctx:
            resolve_prewarm_status_for_execution(
                workspace_id="ws-test",
                lead_id="lead-malicious-url",
                lead_url="javascript:alert('pwned')",
                supabase=None
            )
        self.assertIn("Dangerous URL scheme", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx2:
            resolve_prewarm_status_for_execution(
                workspace_id="ws-test",
                lead_id="lead-malicious-url-2",
                post_url="data:text/html,<script>steal()</script>",
                supabase=None
            )
        self.assertIn("Dangerous URL scheme", str(ctx2.exception))

        # Router level HTTP 400 mapping
        payload = ResolvePrewarmExecutionPayload(
            lead_id="lead-malicious-router",
            lead_url="file:///etc/passwd"
        )
        with self.assertRaises(HTTPException) as http_ctx:
            resolve_prewarm_execution_status_endpoint(
                payload=payload,
                workspace_id="ws-test",
                supabase=None
            )
        self.assertEqual(http_ctx.exception.status_code, 400)

    def test_layer2_formula_injection_stripped_and_slop_neutralized(self):
        """
        Layer 2 Human Paranoia: Strips spreadsheet formula injection characters (=, +, -, @)
        from prospect snippet and verifies comments contain no banned AI slop openers.
        """
        malicious_snippet = "=cmd|' /C calc'!A0 Scaling SDR team headcount and commission structure."
        res = resolve_prewarm_status_for_execution(
            workspace_id="ws-test",
            lead_id="lead-formula-injection",
            post_snippet=malicious_snippet,
            tone="insightful_query",
            supabase=None
        )

        self.assertEqual(res["status"], "in_progress")
        comment = res["prewarm_comment"]
        # Verify no banned slop opener exists
        for slop in BANNED_SLOP_PHRASES:
            self.assertFalse(comment.lower().startswith(slop))

        # Verify scheduled in-memory event does not start with '='
        matching = [
            e for e in _IN_MEMORY_PREWARM_EVENTS
            if e.get("metadata", {}).get("raw_lead_id") == "lead-formula-injection"
        ]
        self.assertTrue(len(matching) > 0)
        for ev in matching:
            snip = ev.get("post_snippet") or ""
            if snip:
                self.assertFalse(snip.startswith("="))

    def test_layer2_cross_tenant_idor_isolation_enforced(self):
        """
        Layer 2 Human Paranoia: Enforces Cross-Tenant IDOR Isolation:
        1. get_lead_prewarm_status does not leak events belonging to another non-default workspace.
        2. list_prewarm_queue filters out events belonging to other workspaces.
        3. resolve_prewarm_status_for_execution raises PermissionError on cross-tenant lead,
           which maps to HTTP 403 in router.
        """
        # Inject foreign tenant events into in-memory store
        _IN_MEMORY_PREWARM_EVENTS.extend([
            {
                "id": "foreign-evt-1",
                "workspace_id": "ws-victim-tenant",
                "lead_id": "lead-victim-01",
                "action_type": "profile_view",
                "status": "completed",
                "scheduled_for": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "foreign-evt-2",
                "workspace_id": "ws-victim-tenant",
                "lead_id": "lead-victim-01",
                "action_type": "post_like",
                "status": "completed",
                "scheduled_for": datetime.now(timezone.utc).isoformat(),
            }
        ])

        # 1. Attacker queries victim's lead status -> 0 events leaked
        status_res = get_lead_prewarm_status(
            supabase=None,
            workspace_id="ws-attacker-tenant",
            lead_id="lead-victim-01"
        )
        self.assertEqual(status_res["total_events"], 0)
        self.assertEqual(len(status_res["events"]), 0)

        # 2. Attacker lists prewarm queue -> victim events filtered out
        queue_res = list_prewarm_queue(
            supabase=None,
            workspace_id="ws-attacker-tenant"
        )
        for evt in queue_res["events"]:
            self.assertNotEqual(evt.get("workspace_id"), "ws-victim-tenant")

        # 3. Attacker tries to resolve execution on victim's lead -> PermissionError
        with self.assertRaises(PermissionError):
            resolve_prewarm_status_for_execution(
                workspace_id="ws-attacker-tenant",
                lead_id="lead-victim-01",
                supabase=None
            )

        # 4. Router maps PermissionError to HTTP 403 Forbidden
        payload = ResolvePrewarmExecutionPayload(
            lead_id="lead-victim-01"
        )
        with self.assertRaises(HTTPException) as ctx:
            resolve_prewarm_execution_status_endpoint(
                payload=payload,
                workspace_id="ws-attacker-tenant",
                supabase=None
            )
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
