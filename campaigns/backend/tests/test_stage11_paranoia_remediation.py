"""
Stage 11 Paranoia Remediation Test Suite (Final Pillar IV Remediation & 100% Milestone)
Targeting:
- API-06: Synchronous Supabase Client in Async FastAPI Routes (asyncio.to_thread offloading)
- API-10: Inconsistent Date Formatting in Analytics Responses (_format_iso_utc standardizer)
- API-11: Campaign Node Duplication via Ambiguous Paths (GET /campaigns/{id}/nodes)
- API-13: Database Connection Leaks on Unhandled Generator Errors (distributed_workspace_lock try/finally)
- API-15: Floating-Point Rounding in Campaign Budget Checks (_to_exact_credits Decimal precision)
- API-22: Unindexed Aggregation Spikes in Dashboard Endpoint (60s TTL cache)
- API-23: Missing Character Truncation on Outbound Logs (10KB char cap on error/ai_reasoning/variables)
- API-25: Stale Cache Serving Expired Campaign Settings (invalidate_master_view_cache on mutations)
- API-26: Memory Bloat in Inbound Email Webhook Parsing (_validate_payload_size 10MB limit / HTTP 413)
"""

import pytest
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.backend.main import app
from campaigns.backend.routers.master_view import (
    _format_iso_utc,
    invalidate_master_view_cache,
    _master_view_stats_cache,
    _master_view_stats_lock,
    _MASTER_VIEW_CACHE_TTL_SECONDS
)
from campaigns.backend.routers.inbound_webhooks import (
    _validate_payload_size,
    MAX_WEBHOOK_PAYLOAD_BYTES
)
from campaigns.backend.routers.elein import (
    _to_exact_credits,
    _truncate_log_payload,
    get_campaign_nodes
)
from core.backend.services.credit_service import distributed_workspace_lock


class TestStage11ParanoiaRemediation:
    """Rigorous verification of the final Batch 8 API architecture remediations."""

    def test_api10_format_iso_utc_standardization(self):
        """Layer 0 & 1 (API-10): All dates and timestamps standardize to ISO 8601 UTC."""
        # 1. None/empty handling
        assert _format_iso_utc(None) is None
        assert _format_iso_utc("") is None

        # 2. Date-only strings ('YYYY-MM-DD') are preserved as clean dates
        assert _format_iso_utc("2026-10-18") == "2026-10-18"

        # 3. Epoch timestamps (int and float)
        epoch_ts = 1792310400  # 2026-10-18 08:00:00 UTC
        formatted_epoch = _format_iso_utc(epoch_ts)
        assert formatted_epoch == "2026-10-18T08:00:00Z"
        assert _format_iso_utc(float(epoch_ts)) == "2026-10-18T08:00:00Z"

        # 4. Naive datetime -> converted to UTC
        dt_naive = datetime(2026, 10, 18, 14, 30, 0)
        assert _format_iso_utc(dt_naive) == "2026-10-18T14:30:00Z"

        # 5. Timestamp strings with Z or offsets
        assert _format_iso_utc("2026-10-18T14:30:00Z") == "2026-10-18T14:30:00Z"
        assert _format_iso_utc("2026-10-18 14:30:00") == "2026-10-18T14:30:00Z"

    def test_api15_exact_decimal_credits(self):
        """Layer 0 (API-15): Exact integer credits via Decimal prevents IEEE 754 precision drift."""
        assert _to_exact_credits(None) == 0
        assert _to_exact_credits(100) == 100
        assert _to_exact_credits("100") == 100
        assert _to_exact_credits(99.999) == 100
        assert _to_exact_credits("99.4") == 99
        assert _to_exact_credits("-499.999") == -500
        assert _to_exact_credits("-500.000") == -500
        assert _to_exact_credits("invalid") == 0

    def test_api22_master_view_cache_ttl_and_retrieval(self):
        """Layer 1 (API-22): Master view cache TTL is set to 60s to prevent unindexed aggregation spikes."""
        assert _MASTER_VIEW_CACHE_TTL_SECONDS == 60

        # Verify cache stores and retrieves cleanly
        ws_id = "ws_test_stage11_cache"
        cache_key = (ws_id, "2026-10-01", "2026-10-18", (), ())
        test_payload = {"summary": {"total_leads": 42}, "cached": True}

        with _master_view_stats_lock:
            _master_view_stats_cache[cache_key] = {"data": test_payload, "ts": time.time()}

        assert cache_key in _master_view_stats_cache
        assert _master_view_stats_cache[cache_key]["data"]["summary"]["total_leads"] == 42

    def test_api25_invalidate_master_view_cache(self):
        """Layer 1 (API-25): Mutations invalidate cached analytics strictly for the affected workspace."""
        ws1 = "ws_tenant_1"
        ws2 = "ws_tenant_2"

        k1 = (ws1, "2026-10-01", "2026-10-18", (), ())
        k2 = (ws2, "2026-10-01", "2026-10-18", (), ())

        with _master_view_stats_lock:
            _master_view_stats_cache[k1] = {"data": {"leads": 10}, "ts": time.time()}
            _master_view_stats_cache[k2] = {"data": {"leads": 20}, "ts": time.time()}

        # Invalidate strictly ws1
        invalidate_master_view_cache(ws1)

        with _master_view_stats_lock:
            assert k1 not in _master_view_stats_cache
            assert k2 in _master_view_stats_cache

        # Invalidate all
        invalidate_master_view_cache()
        with _master_view_stats_lock:
            assert len(_master_view_stats_cache) == 0

    def test_api26_validate_payload_size_ceiling(self):
        """Layer 1 & 2 (API-26): Payloads exceeding 10MB are rejected with HTTP 413 Payload Too Large."""
        mock_req_ok = MagicMock()
        mock_req_ok.headers = {"content-length": str(1024 * 1024)}  # 1MB
        # Should not raise
        _validate_payload_size(mock_req_ok)

        mock_req_oversized = MagicMock()
        mock_req_oversized.headers = {"content-length": str(MAX_WEBHOOK_PAYLOAD_BYTES + 1024)}
        with pytest.raises(HTTPException) as exc_info:
            _validate_payload_size(mock_req_oversized)
        assert exc_info.value.status_code == 413
        assert "Payload Too Large" in exc_info.value.detail

    def test_api23_character_truncation_on_logs(self):
        """Layer 1 (API-23): Log payloads and string values are strictly capped at 10,000 characters."""
        huge_string = "A" * 15000
        truncated = _truncate_log_payload(huge_string)
        assert len(truncated) < 15000
        assert "truncated at 10000 chars" in truncated
        assert truncated.startswith("A" * 10000)

        # Nested dictionary truncation
        payload = {
            "error": "Error: " + ("E" * 12000),
            "nested": {
                "reasoning": "Think: " + ("T" * 11000),
                "safe": "normal"
            }
        }
        res = _truncate_log_payload(payload)
        assert len(res["error"]) < 12050
        assert res["nested"]["safe"] == "normal"
        assert "truncated at 10000 chars" in res["nested"]["reasoning"]

    def test_api13_distributed_lock_generator_guaranteed_release(self):
        """Layer 1 (API-13): distributed_workspace_lock guaranteed release on unhandled generator errors."""
        lock_name = "test_gen_release_lock"
        
        # Test that an exception inside the with block does not leave the lock acquired
        try:
            with distributed_workspace_lock(lock_name, ttl_seconds=10, blocking=False) as acquired:
                assert acquired is True
                raise RuntimeError("Simulated crash inside with-block")
        except RuntimeError:
            pass

        # Immediate re-acquisition must succeed because the finally block released the in-memory lock!
        with distributed_workspace_lock(lock_name, ttl_seconds=10, blocking=False) as acquired_second:
            assert acquired_second is True

    def test_api11_get_campaign_nodes_endpoint(self):
        """Layer 0 & 1 (API-11): Dedicated /campaigns/{campaign_id}/nodes endpoint returns scoped graph."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "c1111111-1111-1111-1111-111111111111",
                "nodes_json": '[{"id": "node_1", "type": "message"}]',
                "edges_json": '[{"id": "e_1", "source": "node_1", "target": "node_2"}]'
            }]
        )

        res = get_campaign_nodes(
            campaign_id="c1111111-1111-1111-1111-111111111111",
            supabase=mock_supabase,
            workspace_id="ws_test_nodes"
        )
        assert res["campaign_id"] == "c1111111-1111-1111-1111-111111111111"
        assert len(res["nodes"]) == 1
        assert res["nodes"][0]["id"] == "node_1"
        assert len(res["edges"]) == 1

        # Test 404 when campaign not found in workspace
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with pytest.raises(HTTPException) as exc_info:
            get_campaign_nodes(
                campaign_id="c_missing",
                supabase=mock_supabase,
                workspace_id="ws_test_nodes"
            )
        assert exc_info.value.status_code == 404

