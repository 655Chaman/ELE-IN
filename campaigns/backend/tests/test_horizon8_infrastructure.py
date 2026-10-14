import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from core.backend.api.routers.infrastructure import (
    get_system_health,
    get_worker_status,
    get_system_keys
)
from core.backend.services.job_queue import enqueue_job
from core.backend.api.rate_limit import rate_limit
from inbox.backend.services.outbox_worker import poll_outbox_once


class TestHorizon8InfrastructureAndWorkers(unittest.TestCase):
    """
    Horizon 8: System Infrastructure, Task Queues, Rate Limiters & Workers.
    Rigorous verification under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    # =========================================================================
    # Test 1: Health Probe & System Liveness
    # =========================================================================
    def test_system_health_liveness_probe(self):
        res = get_system_health()
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["service"], "ele-in-backend")
        self.assertIn("timestamp", res)

    # =========================================================================
    # Test 2: Worker Daemon Heartbeat Monitoring & Stale Classification
    # =========================================================================
    def test_worker_status_stale_and_alive_classification(self):
        mock_svc = MagicMock()
        now_utc = datetime.now(timezone.utc)
        recent_beat = (now_utc - timedelta(seconds=15)).isoformat()
        stale_beat = (now_utc - timedelta(seconds=300)).isoformat()

        mock_svc.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "worker_id": "elein-daemon",
                    "status": "alive",
                    "last_beat_at": recent_beat,
                    "last_tick_duration_ms": 120,
                    "last_tick_leads_processed": 5
                },
                {
                    "worker_id": "outbox-worker",
                    "status": "alive",
                    "last_beat_at": stale_beat,  # > 120s ago -> stale
                    "last_tick_duration_ms": 50,
                    "last_tick_leads_processed": 0
                }
            ]
        )

        with patch("core.backend.api.routers.infrastructure.get_service_client", return_value=mock_svc):
            report = get_worker_status()

        self.assertEqual(report["status"], "healthy")  # At least one alive
        self.assertEqual(len(report["workers"]), 2)

        w1 = next(w for w in report["workers"] if w["worker_id"] == "elein-daemon")
        self.assertTrue(w1["is_alive"])
        self.assertEqual(w1["status"], "alive")

        w2 = next(w for w in report["workers"] if w["worker_id"] == "outbox-worker")
        self.assertFalse(w2["is_alive"])
        self.assertEqual(w2["status"], "stale")

    # =========================================================================
    # Test 3: System Keys Placeholder Sanitization
    # =========================================================================
    def test_system_keys_placeholder_sanitization(self):
        # Case A: Placeholder is sanitized to empty string
        with patch.dict("os.environ", {"DEEPGRAM_API_KEY": "your_deepgram_api_key_here"}):
            res = get_system_keys()
            self.assertEqual(res["DEEPGRAM_API_KEY"], "")

        # Case B: Literal 'undefined' string is sanitized to empty string
        with patch.dict("os.environ", {"DEEPGRAM_API_KEY": "undefined"}):
            res = get_system_keys()
            self.assertEqual(res["DEEPGRAM_API_KEY"], "")

        # Case C: Valid key is returned cleanly
        with patch.dict("os.environ", {"DEEPGRAM_API_KEY": "dg_live_secret_key_999"}):
            res = get_system_keys()
            self.assertEqual(res["DEEPGRAM_API_KEY"], "dg_live_secret_key_999")

        # Case D: Suspended workspace is blocked with 403
        mock_svc = MagicMock()
        mock_svc.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "ws_banned", "status": "suspended"}]
        )
        with patch("core.backend.api.routers.infrastructure.get_service_client", return_value=mock_svc):
            with self.assertRaises(HTTPException) as ctx:
                get_system_keys(workspace_id="ws_banned")
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("Workspace is suspended", ctx.exception.detail)

    # =========================================================================
    # Test 4: Job Queue Enqueue Sanitization & Idempotency
    # =========================================================================
    def test_enqueue_job_sanitization_and_idempotency(self):
        mock_svc = MagicMock()
        mock_table = MagicMock()
        mock_table.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "job_001", "status": "pending"}]
        )
        mock_svc.table.return_value = mock_table

        # Case A: payload=None is safely sanitized to {}
        res = enqueue_job(
            supabase=mock_svc,
            job_type="pdf_extract",
            workspace_id="ws_1",
            asset_id="asset_1",
            payload=None,
            idempotency_key="idem_123"
        )
        self.assertEqual(res["id"], "job_001")
        upsert_call = mock_table.upsert.call_args[0][0]
        self.assertEqual(upsert_call["payload"], {})
        self.assertEqual(upsert_call["idempotency_key"], "idem_123")

    # =========================================================================
    # Test 5: Outbox Worker Polling Query for NULL deliver_at
    # =========================================================================
    def test_outbox_worker_polling_includes_null_deliver_at(self):
        mock_svc = MagicMock()
        mock_events_table = MagicMock()

        # Query returns no events
        mock_events_table.select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_svc.table.return_value = mock_events_table

        with patch("inbox.backend.services.outbox_worker.get_service_client", return_value=mock_svc):
            count = poll_outbox_once()

        self.assertEqual(count, 0)
        # Verify or_ filter was called to include deliver_at.is.null
        or_call = mock_events_table.select.return_value.eq.return_value.or_.call_args[0][0]
        self.assertIn("deliver_at.is.null", or_call)
        self.assertIn("deliver_at.lte.", or_call)

    # =========================================================================
    # Test 6: Rate Limiter Missing RPC Graceful Fallback & 429 Exhaustion
    # =========================================================================
    def test_rate_limiter_rpc_fallback_and_exhaustion(self):
        limiter = rate_limit(cost=1, capacity=10, refill_rate_per_second=1.0)
        mock_request = MagicMock()
        mock_request.state.api_key_id = "key_test_123"

        # Case A: Quota exhausted -> 429
        mock_supabase_exhausted = MagicMock()
        mock_supabase_exhausted.rpc.return_value.execute.return_value = MagicMock(data=False)
        with self.assertRaises(HTTPException) as cm:
            limiter(mock_request, supabase=mock_supabase_exhausted)
        self.assertEqual(cm.exception.status_code, 429)

        # Case B: RPC function missing in Postgres -> graceful transition fallback (permits request)
        mock_supabase_missing_rpc = MagicMock()
        mock_supabase_missing_rpc.rpc.side_effect = Exception("Could not find the function public.consume_api_quota in schema")
        res = limiter(mock_request, supabase=mock_supabase_missing_rpc)
        self.assertTrue(res)

        # Case C: Network drop / DB crash -> 503 Service Unavailable
        mock_supabase_down = MagicMock()
        mock_supabase_down.rpc.side_effect = ConnectionError("Could not connect to postgres port 5432")
        with self.assertRaises(HTTPException) as cm:
            limiter(mock_request, supabase=mock_supabase_down)
        self.assertEqual(cm.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
