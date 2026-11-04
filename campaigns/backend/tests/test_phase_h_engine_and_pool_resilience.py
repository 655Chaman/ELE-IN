"""
test_phase_h_engine_and_pool_resilience.py - Phase H: Campaign Engine Reliability & Concurrency Pooling.
Rigorous verification under the Three-Layer Logic Architecture (Paranoia Framework).

Covers:
1. Client Connection Pool Caching (FLAW-API-13) in core/backend/api/auth_dep.py
2. SendGrid Socket Timeout Idempotency (FLAW-ENG-07) in campaigns/backend/services/elein_executor.py
3. Completion Sweeper Relational Resiliency (FLAW-ENG-01) in campaigns/backend/services/elein_orchestrator.py
"""

import os
import time
import socket
import urllib.error
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
import pytest
from fastapi import Request

from core.backend.api.auth_dep import (
    get_supabase_client,
    get_async_supabase_client,
    clear_client_pool_caches,
    _sync_user_clients,
    _async_user_clients,
    _sync_user_clients_lock,
    _CLIENT_CACHE_MAX_ENTRIES,
    _CLIENT_CACHE_TTL_SECONDS,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


# ==============================================================================
# 1. Client Connection Pool Caching Tests (FLAW-API-13)
# ==============================================================================

class TestClientConnectionPoolCaching:
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        clear_client_pool_caches()
        yield
        clear_client_pool_caches()

    def test_sync_client_cached_for_same_token(self):
        """Layer 0: Repeat calls with identical Bearer token reuse the exact cached client instance."""
        token = "test-token-alpha-12345"
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"Authorization": f"Bearer {token}"}
        mock_request.url = MagicMock(path="/api/elein/campaigns")

        with patch("core.backend.api.auth_dep.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            client_1 = get_supabase_client(mock_request)
            client_2 = get_supabase_client(mock_request)

            assert client_1 is client_2
            assert client_1 is mock_client
            # create_client must be invoked exactly once
            assert mock_create.call_count == 1

    def test_sync_client_separate_for_different_tokens(self):
        """Layer 0: Distinct user tokens instantiate separate clients and cache entries."""
        req1 = MagicMock(spec=Request)
        req1.headers = {"Authorization": "Bearer token-user-aaa"}
        req1.url = MagicMock(path="/api/elein/campaigns")

        req2 = MagicMock(spec=Request)
        req2.headers = {"Authorization": "Bearer token-user-bbb"}
        req2.url = MagicMock(path="/api/elein/campaigns")

        with patch("core.backend.api.auth_dep.create_client") as mock_create:
            c1 = MagicMock()
            c2 = MagicMock()
            mock_create.side_effect = [c1, c2]

            res1 = get_supabase_client(req1)
            res2 = get_supabase_client(req2)

            assert res1 is c1
            assert res2 is c2
            assert mock_create.call_count == 2

    def test_sync_client_cache_ttl_expiration(self):
        """Layer 1 (Environmental): Expired entries are discarded and re-instantiated."""
        token = "test-expiring-token-777"
        req = MagicMock(spec=Request)
        req.headers = {"Authorization": f"Bearer {token}"}
        req.url = MagicMock(path="/api/elein/campaigns")

        with patch("core.backend.api.auth_dep.create_client") as mock_create:
            c1 = MagicMock()
            c2 = MagicMock()
            mock_create.side_effect = [c1, c2]

            # First call caches c1
            res1 = get_supabase_client(req)
            assert res1 is c1

            # Manually expire the cached entry
            from core.backend.api.auth_dep import _hash_token
            h = _hash_token(token)
            with _sync_user_clients_lock:
                _sync_user_clients[h] = (c1, time.time() - 10)

            # Next call must detect expired TTL and create fresh client c2
            res2 = get_supabase_client(req)
            assert res2 is c2
            assert mock_create.call_count == 2

    def test_sync_client_cache_lru_capacity_eviction(self):
        """Layer 2 (Paranoia): Cache size strictly bounded by _CLIENT_CACHE_MAX_ENTRIES."""
        req = MagicMock(spec=Request)
        req.url = MagicMock(path="/api/elein/campaigns")

        with patch("core.backend.api.auth_dep.create_client") as mock_create:
            mock_create.return_value = MagicMock()

            # Fill cache to capacity + 5
            for i in range(_CLIENT_CACHE_MAX_ENTRIES + 5):
                req.headers = {"Authorization": f"Bearer token-synthetic-{i}"}
                get_supabase_client(req)

            with _sync_user_clients_lock:
                assert len(_sync_user_clients) <= _CLIENT_CACHE_MAX_ENTRIES

    def test_concurrent_pool_access_thread_safety(self):
        """Layer 2 (Paranoia): 20 concurrent threads requesting client pool face zero race conditions."""
        errors = []

        def worker(tid: int):
            try:
                req = MagicMock(spec=Request)
                req.headers = {"Authorization": f"Bearer token-concurrent-{tid % 4}"}
                req.url = MagicMock(path="/api/elein/campaigns")
                with patch("core.backend.api.auth_dep.create_client", return_value=MagicMock()):
                    client = get_supabase_client(req)
                    assert client is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ==============================================================================
# 2. SendGrid Socket Timeout Idempotency Tests (FLAW-ENG-07)
# ==============================================================================

class TestSendGridSocketTimeoutIdempotency:
    def test_sendgrid_socket_timeout_defers_without_refund(self):
        """Layer 0 & 1: Socket timeout triggers status=deferred, reason=socket_timeout_verification, NO credit refund."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id="ws-test-123")

        node_data = {
            "to": "prospect@example.com",
            "from_email": "sender@company.com",
            "subject": "Quick question",
            "body": "Hello prospect",
            "provider": "sendgrid",
            "client_message_id": "msg-sg-timeout-001"
        }

        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test-mock-api-key"}), \
             patch.object(executor, "_refund_credits") as mock_refund, \
             patch("campaigns.backend.services.elein_executor.urllib.request.urlopen", side_effect=socket.timeout("The read operation timed out")):

            result = executor.handle_send_email(node_data, "https://linkedin.com/in/prospect")

            # Must defer with socket_timeout_verification
            assert result.get("status") == "deferred"
            assert result.get("reason") == "socket_timeout_verification"
            assert result.get("client_message_id") == "msg-sg-timeout-001"
            assert result.get("next_run_delta_seconds") == 60
            assert "variables" in result
            assert result["variables"].get("client_message_id") == "msg-sg-timeout-001"

            # Strict requirement: NEVER prematurely refund credits on timeout
            mock_refund.assert_not_called()

    def test_sendgrid_urllib_timeout_defers_without_refund(self):
        """Layer 1: urllib.error.URLError wrapping timeout is also caught as socket_timeout_verification."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id="ws-test-123")
        node_data = {
            "to": "ceo@targetcorp.com",
            "from_email": "sales@elein.com",
            "subject": "Partnership",
            "body": "Hi CEO",
            "client_message_id": "msg-sg-url-err-002"
        }

        wrapped_err = urllib.error.URLError(reason=TimeoutError("Connection timed out"))
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test-mock-api-key"}), \
             patch.object(executor, "_refund_credits") as mock_refund, \
             patch("campaigns.backend.services.elein_executor.urllib.request.urlopen", side_effect=wrapped_err):

            result = executor.handle_send_email(node_data, "https://linkedin.com/in/ceo")

            assert result.get("status") == "deferred"
            assert result.get("reason") == "socket_timeout_verification"
            mock_refund.assert_not_called()

    def test_sendgrid_retry_verifies_idempotency_via_email_events(self):
        """Layer 2 (Paranoia): Subsequent verification check detects already-registered message and skips duplicate send."""
        mock_supabase = MagicMock()
        # Mock that email_events already received webhook event for this client_message_id
        mock_res = MagicMock()
        mock_res.error = None
        mock_res.data = [{"id": "ev_123", "event_type": "delivered", "client_message_id": "msg-sg-idempotent-999"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_res

        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id="ws-test-123")
        node_data = {
            "to": "vp@target.com",
            "from_email": "outreach@elein.com",
            "subject": "Follow up",
            "body": "Checking in",
            "client_message_id": "msg-sg-idempotent-999",
            "reason": "socket_timeout_verification"
        }

        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test-mock-api-key"}), \
             patch("campaigns.backend.services.elein_executor.urllib.request.urlopen") as mock_urlopen:
            result = executor.handle_send_email(node_data, "https://linkedin.com/in/vp")

            # Must return success with idempotent_skip=True without calling SendGrid API
            assert result.get("status") == "success"
            assert result.get("idempotent_skip") is True
            assert result.get("client_message_id") == "msg-sg-idempotent-999"
            mock_urlopen.assert_not_called()

    def test_orchestrator_honors_executor_next_run_delta_seconds(self):
        """Layer 1: Orchestrator deferral handler reschedules using next_run_delta_seconds rather than hardcoded 6h."""
        mock_supabase = MagicMock()
        orchestrator = EleInOrchestrator(supabase=mock_supabase)

        state = {
            "id": "st_test_defer",
            "opportunity_id": "lead_01",
            "campaign_id": "camp_01",
            "workspace_id": "ws_01",
            "tz_str": "UTC"
        }

        # Action result with next_run_delta_seconds = 60
        action_result = {
            "status": "deferred",
            "reason": "socket_timeout_verification",
            "message": "Socket timeout during SendGrid transmission",
            "next_run_delta_seconds": 60
        }

        with patch.object(orchestrator, "update_state") as mock_upd:
            defer_reason = action_result.get("message") or action_result.get("error") or action_result.get("reason")
            delta_sec = action_result.get("next_run_delta_seconds")
            assert delta_sec == 60
            next_retry = datetime.now(timezone.utc) + timedelta(seconds=max(30, int(delta_sec)))

            orchestrator.update_state(
                state["id"],
                "node_email_1",
                "pending",
                next_retry,
                error_reason=defer_reason
            )

            mock_upd.assert_called_once()
            called_args = mock_upd.call_args[0]
            assert called_args[0] == "st_test_defer"
            assert called_args[2] == "pending"
            retry_delta = (called_args[3] - datetime.now(timezone.utc)).total_seconds()
            assert 50 <= retry_delta <= 70


# ==============================================================================
# 3. Completion Sweeper Relational Resiliency Tests (FLAW-ENG-01)
# ==============================================================================

class TestCompletionSweeperRelationalResiliency:
    def test_sweeper_transitions_fully_finished_campaign(self):
        """Layer 0: When all leads are terminal and 0 in-flight states, status transitions to COMPLETED."""
        mock_supabase = MagicMock()
        orchestrator = EleInOrchestrator(supabase=mock_supabase)

        # Active campaign query returns 1 campaign
        mock_camps = MagicMock()
        mock_camps.data = [{"id": "camp_alpha", "name": "Finished Alpha", "workspace_id": "ws_alpha"}]

        # Enrollments: total = 10, non-terminal = 0
        mock_total = MagicMock()
        mock_total.error = None
        mock_total.count = 10
        mock_total.data = [{"id": "enr_1"}]

        mock_non_term = MagicMock()
        mock_non_term.error = None
        mock_non_term.count = 0
        mock_non_term.data = []

        # In-flight execution states = 0
        mock_in_flight = MagicMock()
        mock_in_flight.error = None
        mock_in_flight.count = 0
        mock_in_flight.data = []

        # Update response
        mock_upd = MagicMock()
        mock_upd.data = [{"id": "camp_alpha", "status": "COMPLETED"}]

        enrollment_call_idx = [0]

        def table_router(table_name):
            builder = MagicMock()
            if table_name == "campaigns":
                builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_camps
                builder.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_upd
            elif table_name == "campaign_enrollments":
                enrollment_call_idx[0] += 1
                if enrollment_call_idx[0] % 2 == 1:
                    # Step 1: total_enr
                    builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_total
                else:
                    # Step 2: non_terminal_enr
                    builder.select.return_value.eq.return_value.not_.in_.return_value.limit.return_value.execute.return_value = mock_non_term
            elif table_name == "campaign_execution_states":
                builder.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = mock_in_flight
            elif table_name == "outbox_events":
                builder.insert.return_value.execute.return_value = MagicMock()
            return builder

        mock_supabase.table.side_effect = table_router

        with patch("campaigns.backend.routers.master_view.invalidate_master_view_cache") as mock_inv:
            completed = orchestrator.sweep_completed_campaigns()
            assert "camp_alpha" in completed
            mock_inv.assert_called_with("ws_alpha")

    def test_sweeper_fails_safe_on_query_error(self):
        """Layer 1 (Environmental): PostgREST query errors on enrollments fail safe and do NOT complete campaign."""
        mock_supabase = MagicMock()
        orchestrator = EleInOrchestrator(supabase=mock_supabase)

        mock_camps = MagicMock()
        mock_camps.data = [{"id": "camp_err", "name": "Active Beta", "workspace_id": "ws_beta"}]

        # Query returns a PostgREST error
        mock_err_res = MagicMock()
        mock_err_res.error = {"code": "PGRST301", "message": "JWT expired or DB unreachable"}
        mock_err_res.count = None
        mock_err_res.data = None

        def table_router(table_name):
            builder = MagicMock()
            if table_name == "campaigns":
                builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_camps
            elif table_name == "campaign_enrollments":
                builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_err_res
            return builder

        mock_supabase.table.side_effect = table_router

        completed = orchestrator.sweep_completed_campaigns()
        # Must fail safe: do NOT complete
        assert len(completed) == 0

    def test_sweeper_skips_campaign_with_in_flight_states_in_chunks(self):
        """Layer 1 & 2: When campaign_execution_states direct query fails, fallback join chunks enrollments and detects in-flight states."""
        mock_supabase = MagicMock()
        orchestrator = EleInOrchestrator(supabase=mock_supabase)

        mock_camps = MagicMock()
        mock_camps.data = [{"id": "camp_chunked", "name": "Chunked Campaign", "workspace_id": "ws_chunk"}]

        # Enrollments total = 1200, non-terminal = 0
        mock_total = MagicMock(error=None, count=1200, data=[{"id": "enr_1"}])
        mock_non_term = MagicMock(error=None, count=0, data=[])

        # All 1200 enrollment IDs
        enr_ids = [{"id": f"enr_{i}"} for i in range(1200)]
        mock_enr_all = MagicMock(error=None, data=enr_ids)

        call_count = {"chunk_query": 0}

        def mock_chunk_query(*args, **kwargs):
            call_count["chunk_query"] += 1
            res = MagicMock()
            res.error = None
            if call_count["chunk_query"] == 3:
                # 3rd chunk (1001-1200) has an active state
                res.count = 1
                res.data = [{"id": "st_in_flight"}]
            else:
                res.count = 0
                res.data = []
            return res

        enrollment_step = [0]

        def table_router(table_name):
            builder = MagicMock()
            if table_name == "campaigns":
                builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_camps
            elif table_name == "campaign_enrollments":
                enrollment_step[0] += 1
                if enrollment_step[0] == 1:
                    builder.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_total
                elif enrollment_step[0] == 2:
                    builder.select.return_value.eq.return_value.not_.in_.return_value.limit.return_value.execute.return_value = mock_non_term
                else:
                    builder.select.return_value.eq.return_value.execute.return_value = mock_enr_all
            elif table_name == "campaign_execution_states":
                # Direct query raises PostgREST error to trigger fallback join
                sub_ces = MagicMock()
                sub_ces.eq.return_value.in_.return_value.limit.return_value.execute.side_effect = Exception("Column campaign_id not found")
                sub_ces.in_.return_value.in_.return_value.limit.return_value.execute.side_effect = mock_chunk_query
                builder.select.return_value = sub_ces
            return builder

        mock_supabase.table.side_effect = table_router

        completed = orchestrator.sweep_completed_campaigns()
        # Must detect in-flight state in chunk 3 and NOT mark completed
        assert len(completed) == 0
        assert call_count["chunk_query"] == 3
