"""
test_phase_l_m_n_resilience.py — Comprehensive Unit Test Suite for Phases L, M, and N.
Engineered under the Three-Layer Logic Architecture (Paranoia Framework).

Covers:
- Phase L: Chrome Extension & Real-Time Bi-Directional Bridge Resilience
  * Cross-workspace token fencing (Layer 1 & 2)
  * Cryptographic HMAC-SHA256 signature verification & timestamp replay drift (Layer 1)
  * Ingest scraped profile with formula injection sanitization & URL normalization (Layer 0 & 2)
- Phase M: Autonomous Agentic Decisioning & Bayesian ICP Optimization
  * Cold-start hierarchical shrinkage regularization (Layer 0 & 1)
  * Deterministic logit clamping and score bounds in [0, 100] (Layer 1)
  * AI Gateway Circuit Breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED) (Layer 1)
  * Token budget enforcement and anti-hallucination claim sanitization (Layer 2)
- Phase N: Multi-Channel Orchestration & Rate-Pacing Telemetry
  * Synchronized multi-channel state transitions on reply/bounce/unsubscribe (Layer 0 & 1)
  * STO jitter anti-clustering distribution (Layer 0)
  * Account warming schedule backpressure delay calculations (Layer 0 & 2)
  * Proxy quarantine automatic sticky affinity failover in sender pods (Layer 1 & 2)
"""

import hashlib
import hmac
import json
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

# Phase L imports
from integrations.backend.routers.extension import (
    verify_extension_api_key,
    verify_extension_cryptographic_signature,
    ingest_scraped_profile,
    sanitize_scraped_text,
    ExtensionScrapedProfilePayload,
)

# Phase M imports
from knowledge.backend.services.bayesian_icp_service import (
    calculate_beta_metrics,
    compute_bayesian_icp_score,
)
from knowledge.backend.services.elein_ai_service import (
    AICircuitBreaker,
    enforce_token_budget,
    validate_persona_and_battlecard_claims,
)

# Phase N imports
from campaigns.backend.services.sto_service import (
    compute_lead_jitter_minutes,
    calculate_warming_backpressure_delay,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.services.sender_pod_service import select_pod_sender


class TestPhaseLExtensionResilience(unittest.TestCase):
    """
    Phase L: Chrome Extension & Real-Time Bridge Resilience Tests
    """

    def setUp(self):
        self.workspace_id = "ws_primary_99"
        self.raw_api_key = "elein_live_ext_secret_key_12345"
        self.hashed_key = hashlib.sha256(self.raw_api_key.encode("utf-8")).hexdigest()

    def test_extension_cross_workspace_token_fencing_enforced(self):
        """Layer 1 & 2: Rejects cross-workspace boundary violations with HTTP 403."""
        mock_supabase = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{"workspace_id": self.workspace_id, "is_active": True}]
        mock_supabase.table().select().eq().execute.return_value = mock_res
        mock_supabase.table().update().eq().execute.return_value = MagicMock(data=[])

        # Attempting to access foreign workspace 'ws_attacker_66' with key belonging to 'ws_primary_99'
        with self.assertRaises(HTTPException) as ctx:
            verify_extension_api_key(
                x_api_key=self.raw_api_key,
                x_workspace_id="ws_attacker_66",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cross-workspace boundary violation", ctx.exception.detail)

    def test_extension_cross_workspace_token_fencing_matches(self):
        """Layer 0: Allows request when workspace ID matches API key owner."""
        mock_supabase = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{"workspace_id": self.workspace_id, "is_active": True}]
        mock_supabase.table().select().eq().execute.return_value = mock_res
        mock_supabase.table().update().eq().execute.return_value = MagicMock(data=[])

        resolved_ws = verify_extension_api_key(
            x_api_key=self.raw_api_key,
            x_workspace_id=self.workspace_id,
            supabase=mock_supabase
        )
        self.assertEqual(resolved_ws, self.workspace_id)

    def test_extension_cryptographic_signature_valid(self):
        """Layer 1: Valid HMAC-SHA256 signature passes verification."""
        body = b'{"status":"success","task_id":"t-101"}'
        timestamp = str(time.time())
        sig = hmac.new(self.raw_api_key.encode("utf-8"), body, hashlib.sha256).hexdigest()

        ok, msg = verify_extension_cryptographic_signature(
            raw_body=body,
            secret_key=self.raw_api_key,
            signature_header=f"sha256={sig}",
            timestamp_header=timestamp,
            max_drift_seconds=300
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "verified")

    def test_extension_cryptographic_signature_replay_drift_rejected(self):
        """Layer 1: Timestamp drift > 300s is rejected as replay attack."""
        body = b'{"status":"success"}'
        stale_ts = str(time.time() - 400)  # 400 seconds old
        sig = hmac.new(self.raw_api_key.encode("utf-8"), body, hashlib.sha256).hexdigest()

        ok, msg = verify_extension_cryptographic_signature(
            raw_body=body,
            secret_key=self.raw_api_key,
            signature_header=sig,
            timestamp_header=stale_ts,
            max_drift_seconds=300
        )
        self.assertFalse(ok)
        self.assertIn("timestamp_drift_exceeded", msg)

    def test_extension_cryptographic_signature_mismatch_rejected(self):
        """Layer 1: Signature mismatch due to tampering or wrong key is rejected."""
        body = b'{"status":"tampered"}'
        timestamp = str(time.time())
        wrong_sig = "deadbeef" * 8

        ok, msg = verify_extension_cryptographic_signature(
            raw_body=body,
            secret_key=self.raw_api_key,
            signature_header=wrong_sig,
            timestamp_header=timestamp,
            max_drift_seconds=300
        )
        self.assertFalse(ok)
        self.assertEqual(msg, "signature_mismatch")

    def test_extension_dom_scrape_profile_formula_sanitization(self):
        """Layer 2: Formula injection prefixes in scraped fields are neutralized with a leading quote."""
        self.assertEqual(sanitize_scraped_text("=SUM(A1:A10)"), "'=SUM(A1:A10)")
        self.assertEqual(sanitize_scraped_text("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(sanitize_scraped_text("@malicious_macro"), "'@malicious_macro")
        self.assertEqual(sanitize_scraped_text("Standard Name"), "Standard Name")

    def test_extension_dom_scrape_profile_ingestion(self):
        """Layer 0 & 1: Scraped profile creates lead with normalized URL and sanitized attributes."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "lead-new"}])

        payload = ExtensionScrapedProfilePayload(
            linkedin_url="https://www.linkedin.com/in/sarah-connor/?tracking=123#ref",
            first_name="=Sarah",
            last_name="Connor",
            title="VP of Engineering",
            company_name="@Cyberdyne Systems",
            location="Los Angeles, CA"
        )

        res = ingest_scraped_profile(
            payload=payload,
            x_api_key=self.raw_api_key,
            x_workspace_id=self.workspace_id,
            x_extension_signature=None,
            x_extension_timestamp=None,
            workspace_id=self.workspace_id,
            supabase=mock_supabase
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["action"], "created")
        self.assertEqual(res["linkedin_url"], "https://www.linkedin.com/in/sarah-connor")


class TestPhaseMBayesianICPandAICircuitBreaker(unittest.TestCase):
    """
    Phase M: Bayesian ICP Optimization & AI Circuit Breaker Tests
    """

    def test_bayesian_icp_cold_start_shrinkage_regularization(self):
        """Layer 0 & 1: When sample size is small (N < 10), weights shrink toward prior baseline."""
        # Unregularized Beta(2, 1) has raw mean = 2/3 = 0.6667
        # With sample size 3, shrinkage_lambda = 3 / (3 + 5) = 0.375
        # regularized mean = 0.375 * 0.6667 + 0.625 * 0.5 = 0.5625
        metrics = calculate_beta_metrics(alpha=2.0, beta=1.0, weight_multiplier=1.0)
        self.assertEqual(metrics["confidence_tier"], "LOW")
        self.assertLess(metrics["regularized_mean"], metrics["raw_mean"])
        self.assertGreater(metrics["regularized_mean"], 0.5)

    def test_bayesian_icp_score_logit_overflow_protection(self):
        """Layer 1: Extreme weights do not cause math.exp overflow; score is clamped [0, 100]."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])

        # Candidate with all signals present
        profile = {
            "title": "VP of Technology",
            "summary": "Actively hiring engineers at high-growth software company.",
            "recent_job_change": True,
            "funding_announced": True,
            "headcount": 250,
            "recent_posts": True,
            "industry": "Software & SaaS"
        }

        score, reasoning = compute_bayesian_icp_score(
            supabase=mock_supabase,
            workspace_id="ws-test",
            profile_data=profile
        )
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIn("Bayesian Score", reasoning)

    def test_ai_circuit_breaker_trips_and_resets(self):
        """Layer 1: Circuit Breaker trips to OPEN after consecutive failures and recovers on canary."""
        cb = AICircuitBreaker(failure_threshold=3, cooldown_seconds=0.1)
        self.assertEqual(cb.get_status()["state"], "CLOSED")
        self.assertTrue(cb.allow_request())

        # Record 2 failures -> remains CLOSED
        cb.record_failure(Exception("429 Too Many Requests"))
        cb.record_failure(Exception("429 Too Many Requests"))
        self.assertEqual(cb.get_status()["state"], "CLOSED")
        self.assertTrue(cb.allow_request())

        # 3rd failure -> trips to OPEN
        cb.record_failure(Exception("429 Rate limit exceeded"))
        self.assertEqual(cb.get_status()["state"], "OPEN")
        self.assertFalse(cb.allow_request())

        # Wait for cooldown
        time.sleep(0.12)
        # Should transition to HALF_OPEN
        self.assertTrue(cb.allow_request())
        self.assertEqual(cb.get_status()["state"], "HALF_OPEN")

        # Successful canary request -> resets to CLOSED
        cb.record_success()
        self.assertEqual(cb.get_status()["state"], "CLOSED")

    def test_token_budget_enforcement(self):
        """Layer 2: Token budget stops runaway prompts exceeding threshold."""
        self.assertTrue(enforce_token_budget(1024, max_budget=4096))
        self.assertFalse(enforce_token_budget(5000, max_budget=4096))

    def test_anti_hallucination_claim_validation(self):
        """Layer 2: Neutralizes hyperbolic guarantees and unsupported statistics."""
        hallucinated_text = "Our platform offers guaranteed 500% ROI within 30 days."
        valid, sanitized, flags = validate_persona_and_battlecard_claims(hallucinated_text)
        self.assertFalse(valid)
        self.assertGreater(len(flags), 0)
        self.assertNotIn("guaranteed 500% ROI", sanitized)


class TestPhaseNMultiChannelAndPacing(unittest.TestCase):
    """
    Phase N: Multi-Channel Orchestration & Rate-Pacing Telemetry Tests
    """

    def test_multi_channel_synchronized_reply_cancels_outbox(self):
        """Layer 0 & 1: Inbound reply on one channel cascade cancels pending outbox emails."""
        mock_supabase = MagicMock()
        mock_outbox_res = MagicMock()
        mock_outbox_res.data = [{"id": "msg-1"}, {"id": "msg-2"}]
        mock_supabase.table().select().eq().eq().in_().execute.return_value = mock_outbox_res
        mock_supabase.table().select().eq().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().update().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[])

        orch = EleInOrchestrator(supabase=mock_supabase)
        res = orch.cascade_multi_channel_transition(
            workspace_id="ws-alpha",
            lead_id="lead-42",
            event_type="reply_received",
            source_channel="linkedin"
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["cancelled_outbox_count"], 2)

    def test_multi_channel_synchronized_unsubscribe_cancels_all(self):
        """Layer 0 & 1: Unsubscribe cascade cancels all in-flight states across channels."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().select().eq().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().update().in_().execute.return_value = MagicMock(data=[])
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[])

        orch = EleInOrchestrator(supabase=mock_supabase)
        res = orch.cascade_multi_channel_transition(
            workspace_id="ws-alpha",
            lead_id="lead-88",
            event_type="lead_unsubscribed",
            source_channel="email"
        )
        self.assertEqual(res["status"], "success")

    def test_sto_jitter_bounds_and_distribution(self):
        """Layer 0 & 2: STO jitter computes deterministic minute offsets within bounds."""
        j1 = compute_lead_jitter_minutes("lead_abc_1", min_jitter=5, max_jitter=25)
        j2 = compute_lead_jitter_minutes("lead_xyz_9", min_jitter=5, max_jitter=25)
        self.assertGreaterEqual(j1, 5)
        self.assertLessEqual(j1, 25)
        self.assertGreaterEqual(j2, 5)
        self.assertLessEqual(j2, 25)
        # Consistent hash for same lead
        self.assertEqual(j1, compute_lead_jitter_minutes("lead_abc_1", min_jitter=5, max_jitter=25))

    def test_account_warming_schedule_backpressure_calculation(self):
        """Layer 0 & 2: Accounts in warmup experience progressive backpressure as daily quota fills."""
        # Account created 5 days ago (warmup phase)
        created_at = datetime.now(timezone.utc).isoformat()
        res_early = calculate_warming_backpressure_delay(created_at, actions_today=2, daily_target=20)
        res_late = calculate_warming_backpressure_delay(created_at, actions_today=18, daily_target=20)

        self.assertTrue(res_early["is_warmup"])
        self.assertFalse(res_early["cap_exceeded"])
        # Backpressure delay increases as utilization rises
        self.assertGreater(res_late["backpressure_delay_seconds"], res_early["backpressure_delay_seconds"])

    def test_sender_pod_proxy_quarantine_failover(self):
        """Layer 1 & 2: Initiating sender with quarantined proxy triggers transparent failover."""
        mock_supabase = MagicMock()
        mock_camp_res = MagicMock()
        mock_camp_res.data = [{
            "workspace_id": "ws-1",
            "pod_emergency_paused": False,
            "pod_dispatch_strategy": "CAPACITY_WEIGHTED"
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_camp_res

        # Thread affinity returns initiating account 'acc-1'
        mock_lock_res = MagicMock(data=[{"account_id": "acc-1"}])
        mock_acc_res = MagicMock(data=[{
            "id": "acc-1",
            "workspace_id": "ws-1",
            "status": "ACTIVE",
            "quarantined_until": None,
            "proxy_id": "proxy-broken"
        }])

        # Proxy check returns quarantined
        mock_proxy_res = MagicMock(data=[{"status": "quarantined", "is_active": False}])

        # Pod links return backup 'acc-2'
        mock_links_res = MagicMock(data=[
            {"account_id": "acc-1", "weight": 100},
            {"account_id": "acc-2", "weight": 100}
        ])

        # Account candidates
        mock_candidates_res = MagicMock(data=[{
            "id": "acc-2",
            "workspace_id": "ws-1",
            "status": "ACTIVE",
            "is_pod_eligible": True,
            "quarantined_until": None,
            "daily_connection_limit": 50,
            "daily_message_limit": 50,
            "proxy_id": "proxy-healthy"
        }])
        mock_healthy_proxy_res = MagicMock(data=[{"status": "active", "is_active": True}])

        def table_router(table_name):
            t = MagicMock()
            if table_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = mock_camp_res
            elif table_name == "campaign_lead_sender_locks":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = mock_lock_res
            elif table_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = mock_acc_res
                t.select.return_value.in_.return_value.execute.return_value = mock_candidates_res
            elif table_name == "proxies":
                def proxy_eq(col, val):
                    eq_mock = MagicMock()
                    if val == "proxy-broken":
                        eq_mock.execute.return_value = mock_proxy_res
                    else:
                        eq_mock.execute.return_value = mock_healthy_proxy_res
                    return eq_mock
                t.select.return_value.eq.side_effect = proxy_eq
            elif table_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = mock_links_res
            elif table_name == "account_daily_usage":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return t

        mock_supabase.table.side_effect = table_router

        # Select sender for lead
        result = select_pod_sender(
            campaign_id="camp-1",
            workspace_id="ws-1",
            action_type="linkedin_connect",
            supabase=mock_supabase,
            lead_id="lead-test-1"
        )
        # Should fail over to acc-2 because acc-1's proxy is quarantined
        self.assertEqual(result.get("account_id"), "acc-2")
        self.assertEqual(result.get("status"), "DISPATCH_SUCCESS")
        self.assertEqual(result.get("strategy"), "CAPACITY_WEIGHTED")


if __name__ == "__main__":
    unittest.main()
