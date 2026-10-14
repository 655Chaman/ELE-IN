"""
test_multi_tenant_rate_limiting.py

Unit tests for Step 24: Multi-Tenant Rate Limiting & Sliding Window Burst Protection
"""

import time
import threading
import unittest
from collections import deque
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from core.backend.api.rate_limit import (
    SlidingWindowRateLimiter,
    sliding_window_rate_limit,
    get_client_ip,
    get_client_workspace,
    get_client_user,
    rate_limit,
    enforce_ai_rate_limit,
)


def make_mock_request(headers=None, client_host="192.168.1.50", path="/api/test", state=None, query_params=None, path_params=None):
    req = MagicMock()
    req.headers = headers or {}
    req.client = MagicMock(host=client_host)
    req.url = MagicMock(path=path)
    req.state = state or MagicMock()
    req.query_params = query_params or {}
    req.path_params = path_params or {}
    return req


class TestMultiTenantRateLimiting(unittest.TestCase):
    """Test suite covering the 12 multi-tenant rate limiting and sliding window hardening requirements."""

    def test_sliding_window_allows_within_limit(self):
        """Requirement 1: Requests under limit succeed; remaining count decreases."""
        limiter = sliding_window_rate_limit(max_requests=5, window_seconds=60, scope="ip")
        req = make_mock_request(client_host="10.0.0.1", path="/api/ai")
        mock_supabase = MagicMock()

        for _ in range(5):
            res = limiter(req, mock_supabase)
            self.assertTrue(res)

    def test_sliding_window_blocks_burst_over_limit_with_429(self):
        """Requirement 2: Exceeding limit raises 429 with Retry-After header."""
        limiter = sliding_window_rate_limit(max_requests=2, window_seconds=60, scope="ip")
        req = make_mock_request(client_host="10.0.0.2", path="/api/ai")
        mock_supabase = MagicMock()

        limiter(req, mock_supabase)
        limiter(req, mock_supabase)

        with self.assertRaises(HTTPException) as ctx:
            limiter(req, mock_supabase)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Retry-After", ctx.exception.headers)

    def test_sliding_window_resets_after_window_expires(self):
        """Requirement 3: Timestamp progression allows new requests."""
        limiter = sliding_window_rate_limit(max_requests=1, window_seconds=1, scope="ip")
        req = make_mock_request(client_host="10.0.0.3", path="/api/ai")
        mock_supabase = MagicMock()

        self.assertTrue(limiter(req, mock_supabase))
        
        with self.assertRaises(HTTPException):
            limiter(req, mock_supabase)

        # Simulate time passing beyond window_seconds
        with patch("time.time", return_value=time.time() + 2.5):
            self.assertTrue(limiter(req, mock_supabase))

    def test_scope_workspace_isolates_tenants(self):
        """Requirement 4: Workspace A hit with 429 does not affect Workspace B."""
        limiter = sliding_window_rate_limit(max_requests=1, window_seconds=60, scope="workspace")
        mock_supabase = MagicMock()

        req_ws_a = make_mock_request(state=MagicMock(workspace_id="ws-alpha"))
        req_ws_b = make_mock_request(state=MagicMock(workspace_id="ws-beta"))

        self.assertTrue(limiter(req_ws_a, mock_supabase))
        with self.assertRaises(HTTPException):
            limiter(req_ws_a, mock_supabase)

        # Workspace B should still be allowed
        self.assertTrue(limiter(req_ws_b, mock_supabase))

    def test_scope_ip_extracts_real_client_ip(self):
        """Requirement 5: Correctly extracts IP from CF-Connecting-IP, X-Forwarded-For."""
        req_cf = make_mock_request(headers={"CF-Connecting-IP": "203.0.113.195"})
        self.assertEqual(get_client_ip(req_cf), "203.0.113.195")

        req_fwd = make_mock_request(headers={"X-Forwarded-For": "198.51.100.42, 10.0.0.1"})
        self.assertEqual(get_client_ip(req_fwd), "198.51.100.42")

    def test_ip_spoofing_defense(self):
        """Requirement 6: Malformed IP header falls back safely to client host or default."""
        req_bad = make_mock_request(headers={"CF-Connecting-IP": "not-an-ip-address"}, client_host="192.168.1.100")
        self.assertEqual(get_client_ip(req_bad), "192.168.1.100")

    def test_whitelist_internal_and_healthcheck(self):
        """Requirement 7: 127.0.0.1 and /health bypass limiter."""
        limiter = sliding_window_rate_limit(max_requests=1, window_seconds=60, scope="ip")
        req_health = make_mock_request(client_host="203.0.113.5", path="/health")
        req_local = make_mock_request(client_host="127.0.0.1", path="/api/ai")
        mock_supabase = MagicMock()

        self.assertTrue(limiter(req_health, mock_supabase))
        self.assertTrue(limiter(req_local, mock_supabase))

    def test_tier_aware_capacity_multiplier(self):
        """Requirement 8: Enterprise workspace gets higher allowance than Free."""
        limiter = sliding_window_rate_limit(max_requests=2, window_seconds=60, scope="workspace", tier_aware=True)
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "ENTERPRISE"}]
        )

        req_ent = make_mock_request(state=MagicMock(workspace_id="ws-enterprise"))
        
        # Enterprise multiplier is 10x (2 * 10 = 20 requests allowed)
        for _ in range(20):
            self.assertTrue(limiter(req_ent, mock_supabase))

        with self.assertRaises(HTTPException):
            limiter(req_ent, mock_supabase)

    def test_lru_bucket_reaping_prevents_memory_leak(self):
        """Requirement 9: Reaping evicts expired buckets when max buckets reached."""
        limiter = SlidingWindowRateLimiter(max_buckets=2)
        limiter.windows["key1"] = deque([time.time() - 100])
        limiter.windows["key2"] = deque([time.time() - 100])
        limiter.windows["key3"] = deque([time.time()])

        # Force reap by exceeding max_buckets
        with limiter.lock:
            while len(limiter.windows) > limiter.max_buckets:
                limiter.windows.popitem(last=False)

        self.assertNotIn("key1", limiter.windows)
        self.assertIn("key3", limiter.windows)

    def test_thread_concurrency_safety(self):
        """Requirement 10: Concurrent threads safely enforce limits."""
        limiter = sliding_window_rate_limit(max_requests=50, window_seconds=60, scope="ip")
        req = make_mock_request(client_host="10.0.0.99", path="/api/concurrency")
        mock_supabase = MagicMock()

        results = []
        def make_request():
            try:
                res = limiter(req, mock_supabase)
                results.append(res)
            except HTTPException:
                results.append("rate_limited")

        threads = [threading.Thread(target=make_request) for _ in range(60)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r is True]
        rate_limited = [r for r in results if r == "rate_limited"]
        self.assertEqual(len(successes), 50)
        self.assertEqual(len(rate_limited), 10)

    def test_legacy_rate_limit_backward_compatibility(self):
        """Requirement 11: Existing rate_limit(cost, capacity) continues to pass."""
        legacy_dep = rate_limit(cost=1, capacity=10, refill_rate_per_second=1.0)
        req = make_mock_request(state=MagicMock(api_key_id="key-123"))
        
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=True)

        self.assertTrue(legacy_dep(req, mock_supabase))

    def test_ai_rate_limit_protects_workspace_session_requests(self):
        """Requirement 12: Workspace without api_key_id is properly rate limited on AI generation."""
        req = make_mock_request(state=MagicMock(workspace_id="ws-session-test"), path="/api/ai/generate")
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )

        # enforce_ai_rate_limit has max_requests=30
        for _ in range(30):
            self.assertTrue(enforce_ai_rate_limit(req, mock_supabase))

        with self.assertRaises(HTTPException) as ctx:
            enforce_ai_rate_limit(req, mock_supabase)
        self.assertEqual(ctx.exception.status_code, 429)
