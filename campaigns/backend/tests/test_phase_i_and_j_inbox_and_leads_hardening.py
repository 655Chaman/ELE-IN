"""
test_phase_i_and_j_inbox_and_leads_hardening.py - Phase I & J Comprehensive Hardening Tests.
Rigorous verification under the Three-Layer Logic Architecture (Paranoia Framework).

Covers:
Phase I:
  1. Optimistic Reply Concurrency & Lock Leases (inbox/backend/services/inbox_lock_service.py)
  2. Sentiment & Intent Heuristic Failover Pipeline (knowledge/backend/services/elein_ai_service.py)

Phase J:
  1. Apify Actor Execution Guard (leads/backend/services/apify_execution_guard.py)
  2. Domain Exclusivity Multi-Workspace Collision Shield (campaigns/backend/services/collision_guard.py)
"""

import time
import hmac
import hashlib
import pytest
from unittest.mock import MagicMock, patch

from inbox.backend.services.inbox_lock_service import (
    acquire_thread_reply_lease,
    release_thread_reply_lease,
    is_thread_reply_locked,
    clear_all_reply_leases,
)
from knowledge.backend.services.elein_ai_service import classify_intent
from leads.backend.services.apify_execution_guard import (
    acquire_apify_run_slot,
    release_apify_run_slot,
    verify_apify_webhook_signature,
    validate_apify_dataset_url,
    sanitize_scraped_lead_field,
    parse_and_sanitize_apify_item,
    MAX_CONCURRENT_APIFY_RUNS_PER_WORKSPACE,
)
from campaigns.backend.services.collision_guard import check_company_domain_exclusivity


# ==============================================================================
# Phase I: Inbox Lock Leases & Sentiment Failover Tests
# ==============================================================================

class TestInboxLockLeasesAndSentimentFailover:
    @pytest.fixture(autouse=True)
    def clean_leases(self):
        clear_all_reply_leases()
        yield
        clear_all_reply_leases()

    def test_acquire_and_release_reply_lease(self):
        """Layer 0: Operator A acquires lease; Operator B is blocked; Operator A releases."""
        ws_id = "ws-inbox-01"
        thread_key = "lead-prospect-123"

        # Operator A acquires
        ok, owner, rem = acquire_thread_reply_lease(ws_id, thread_key, "operator_a", ttl_seconds=10)
        assert ok is True
        assert owner == "operator_a"
        assert rem == 10.0

        # Operator B attempts to acquire on same thread -> blocked
        ok2, owner2, rem2 = acquire_thread_reply_lease(ws_id, thread_key, "operator_b", ttl_seconds=10)
        assert ok2 is False
        assert owner2 == "operator_a"
        assert rem2 > 0

        # Operator A idempotent re-acquisition succeeds
        ok_re, owner_re, _ = acquire_thread_reply_lease(ws_id, thread_key, "operator_a", ttl_seconds=15)
        assert ok_re is True

        # Operator A releases lease
        assert release_thread_reply_lease(ws_id, thread_key, "operator_a") is True

        # Now Operator B can acquire
        ok3, owner3, _ = acquire_thread_reply_lease(ws_id, thread_key, "operator_b", ttl_seconds=10)
        assert ok3 is True
        assert owner3 == "operator_b"

    def test_reply_lease_auto_expiration(self):
        """Layer 1: Expired lease prunes automatically and allows another operator to acquire."""
        ws_id = "ws-inbox-02"
        thread_key = "lead-prospect-456"

        # Force a lease with negative remaining time
        from inbox.backend.services.inbox_lock_service import _REPLY_LEASES, _LEASES_LOCK, _normalize_key
        key = _normalize_key(ws_id, thread_key)
        with _LEASES_LOCK:
            _REPLY_LEASES[key] = {
                "operator_id": "crashed_operator",
                "expires_at": time.time() - 5,
                "acquired_at": time.time() - 20,
            }

        # Check lock status: should be unlocked
        is_locked, _, _ = is_thread_reply_locked(ws_id, thread_key)
        assert is_locked is False

        # Fresh operator acquires cleanly
        ok, owner, _ = acquire_thread_reply_lease(ws_id, thread_key, "fresh_operator", ttl_seconds=15)
        assert ok is True
        assert owner == "fresh_operator"

    def test_sentiment_intent_heuristic_fallback_on_zero_keys(self):
        """Layer 1 & 2: When LLM keys are missing, classify_intent falls back to heuristic rules."""
        import asyncio
        with patch("knowledge.backend.services.elein_ai_service.get_effective_keys_for_workspace", return_value=[]):
            # Test positive meeting request message
            res_positive = asyncio.run(classify_intent("Let's set up a quick 15 minute demo next Tuesday morning!"))
            assert res_positive["intent"] == "positive"
            assert res_positive.get("fallback_source") == "heuristic_zero_key"
            assert res_positive["confidence"] >= 0.6

            # Test explicit objection / opt-out
            res_optout = asyncio.run(classify_intent("Please unsubscribe me and remove me from your mailing list immediately."))
            assert res_optout["intent"] == "negative"
            assert res_optout.get("fallback_source") == "heuristic_zero_key"

    def test_sentiment_intent_heuristic_fallback_on_llm_exhaustion(self):
        """Layer 1: When LLM API throws errors across all attempts, heuristic failover classifies intent."""
        import asyncio
        mock_keys = [{"id": "key_1", "key": "test_key", "provider": "nvidia"}]
        with patch("knowledge.backend.services.elein_ai_service.get_effective_keys_for_workspace", return_value=mock_keys), \
             patch("knowledge.backend.services.elein_ai_service._get_async_client", side_effect=Exception("Connection to AI gateway timed out")):

            # Test general inquiry question
            res_q = asyncio.run(classify_intent("Could you please explain how your automation engine works?"))
            assert res_q["intent"] == "question"
            assert res_q.get("fallback_source") == "heuristic_exhaustion"

            # Test objection fallback
            res_obj = asyncio.run(classify_intent("We already use another platform and don't have budget for this right now."))
            assert res_obj["intent"] == "objection"
            assert res_obj.get("fallback_source") == "heuristic_exhaustion"


# ==============================================================================
# Phase J: Apify Execution Guard & Domain Exclusivity Tests
# ==============================================================================

class TestApifyExecutionGuardAndDomainExclusivity:
    def test_apify_concurrency_ceiling(self):
        """Layer 2: Max 5 concurrent Apify actor runs enforced per workspace."""
        ws_id = "ws-apify-test"

        # Acquire 5 slots
        for _ in range(MAX_CONCURRENT_APIFY_RUNS_PER_WORKSPACE):
            assert acquire_apify_run_slot(ws_id) is True

        # 6th attempt is blocked
        assert acquire_apify_run_slot(ws_id) is False

        # Release 1 slot
        release_apify_run_slot(ws_id)

        # Now acquire succeeds
        assert acquire_apify_run_slot(ws_id) is True

    def test_apify_webhook_signature_and_drift_verification(self):
        """Layer 1: HMAC-SHA256 signature and 300s clock-drift verification."""
        secret = "secret-token-apify-999"
        payload = b'{"eventType": "ACTOR.RUN.SUCCEEDED", "actorId": "crawler_1"}'

        # Valid signature
        valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        now_ts = str(time.time())

        ok, msg = verify_apify_webhook_signature(
            raw_body=payload,
            secret=secret,
            signature_header=f"sha256={valid_sig}",
            timestamp_header=now_ts
        )
        assert ok is True
        assert msg == "verified"

        # Replay attack with expired timestamp (drift > 300s)
        stale_ts = str(time.time() - 400)
        ok_stale, msg_stale = verify_apify_webhook_signature(
            raw_body=payload,
            secret=secret,
            signature_header=valid_sig,
            timestamp_header=stale_ts
        )
        assert ok_stale is False
        assert "timestamp_drift_exceeded" in msg_stale

        # Invalid signature
        ok_bad, msg_bad = verify_apify_webhook_signature(
            raw_body=payload,
            secret=secret,
            signature_header="bad_signature",
            timestamp_header=now_ts
        )
        assert ok_bad is False
        assert msg_bad == "signature_mismatch"

    def test_apify_dataset_url_ssrf_validation(self):
        """Layer 1: Validates that dataset download URLs only point to https://api.apify.com."""
        # Legitimate URL
        ok, _ = validate_apify_dataset_url("https://api.apify.com/v2/datasets/xyz123/items?format=json")
        assert ok is True

        # SSRF attempts
        bad_urls = [
            "http://api.apify.com/v2/datasets/xyz",  # non-https
            "https://169.254.169.254/latest/meta-data",  # AWS metadata
            "https://localhost:8000/api/internal",  # Localhost
            "https://evil-apify.com/v2/items",  # Attacker domain
            "ftp://api.apify.com/files",  # FTP protocol
        ]
        for url in bad_urls:
            valid, reason = validate_apify_dataset_url(url)
            assert valid is False

    def test_apify_formula_injection_sanitization(self):
        """Layer 2: Neutralizes spreadsheet formula injection prefixes (=, +, -, @)."""
        assert sanitize_scraped_lead_field("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
        assert sanitize_scraped_lead_field("+123456") == "'+123456"
        assert sanitize_scraped_lead_field("-DDE(\"server\")") == "'-DDE(\"server\")"
        assert sanitize_scraped_lead_field("@SUM(A1:A10)") == "'@SUM(A1:A10)"
        assert sanitize_scraped_lead_field("Acme Corporation") == "Acme Corporation"

        raw_item = {
            "name": "=HYPERLINK(\"http://attacker.com\")",
            "company": "Normal Corp",
            "linkedinUrl": "https://linkedin.com/in/prospect?trk=share",
        }
        sanitized = parse_and_sanitize_apify_item(raw_item)
        assert sanitized["name"].startswith("'=")
        assert sanitized["company"] == "Normal Corp"
        assert sanitized["linkedin_url"] == "https://linkedin.com/in/prospect"

    def test_domain_exclusivity_multi_workspace_shield(self):
        """Layer 0 & 1: Detects collisions across sister enterprise workspaces and un-normalized email domains."""
        mock_supabase = MagicMock()
        primary_ws = "ws_amer"
        sister_ws = "ws_emea"

        # Mock that sister workspace has a lead for stripe.com actively in a campaign
        def table_router(table_name):
            builder = MagicMock()
            if table_name == "leads":
                # Returns 1 lead in sister workspace
                def select_handler(*args, **kwargs):
                    sub = MagicMock()
                    def eq_handler(col, val):
                        sub_eq = MagicMock()
                        if col == "workspace_id" and val == sister_ws:
                            sub_eq.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "lead_sister_1"}])
                        else:
                            sub_eq.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                        sub_eq.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                        return sub_eq
                    sub.eq = eq_handler
                    return sub
                builder.select = select_handler
            return builder

        mock_supabase.table.side_effect = table_router

        # Patch get_conflicting_active_leads to return conflict for sister workspace
        def mock_conflicts(supabase_client, workspace_id, lead_ids, **kwargs):
            if workspace_id == sister_ws and "lead_sister_1" in lead_ids:
                return {"lead_sister_1"}
            return set()

        with patch("campaigns.backend.services.collision_guard.get_conflicting_active_leads", side_effect=mock_conflicts):
            # Check with enterprise_workspace_ids including sister_ws
            res = check_company_domain_exclusivity(
                supabase_client=mock_supabase,
                workspace_id=primary_ws,
                company_domain="stripe.com",
                enterprise_workspace_ids=[sister_ws]
            )

            assert res["collision_detected"] is True
            assert res["conflicting_lead_id"] == "lead_sister_1"
            assert res["colliding_workspace_id"] == sister_ws
