"""
test_horizon24_webhook_dispatcher_dlq_circuit_breaker.py — Horizon 24 Test Suite
Real-Time Webhook Dispatcher Worker, Dead-Letter Queue & Exponential Retry Circuit Breaker.
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch, call
import time
from datetime import datetime, timezone, timedelta

from integrations.backend.services.circuit_breaker import CircuitBreaker, get_circuit_breaker
from integrations.backend.services.webhook_service import (
    calculate_retry_backoff,
    route_to_dead_letter,
    retry_dead_letter_delivery,
    get_dead_letter_queue,
    dispatch_webhook_delivery,
    dispatch_pending_webhooks,
    sanitize_webhook_payload,
    generate_webhook_signature,
    verify_webhook_signature,
)
from core.backend.workers.webhook_worker import process_delivery
from core.backend.core.crypto import encrypt_bytes


class TestHorizon24WebhookDispatcherDLQCircuitBreaker(unittest.TestCase):
    """
    Horizon 24 Verification Suite: Outbound Webhook Delivery, Dead-Letter Queue (DLQ),
    Circuit Breakers, Exponential Backoff with Jitter, and Tenant Isolation.
    """

    def setUp(self):
        from integrations.backend.services.webhook_service import _ENDPOINT_BACKPRESSURE, _BACKPRESSURE_LOCK
        with _BACKPRESSURE_LOCK:
            _ENDPOINT_BACKPRESSURE.clear()
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_test_horizon24"
        self.endpoint_id = "ep_test_24"
        self.delivery_id = "del_test_24"
        self.raw_secret = "whsec_0123456789abcdef0123456789abcdef"
        self.encrypted_secret_hex = "deadbeef12345678deadbeef12345678"

        self.endpoint = {
            "id": self.endpoint_id,
            "workspace_id": self.workspace_id,
            "url": "https://api.external-crm.com/webhooks/elein",
            "signing_secret": self.encrypted_secret_hex,
            "is_active": True,
            "event_types": ["lead.replied", "intent.hot_detected"]
        }

        self.delivery = {
            "id": self.delivery_id,
            "workspace_id": self.workspace_id,
            "endpoint_id": self.endpoint_id,
            "event_type": "lead.replied",
            "payload": {
                "id": "evt_123",
                "event": "lead.replied",
                "workspace_id": self.workspace_id,
                "data": {"lead_id": "lead_999", "reply": "Interested!"}
            },
            "delivery_status": "pending",
            "attempt_count": 0
        }

        self.decrypt_patcher = patch("integrations.backend.services.webhook_service.decrypt_bytes", return_value=self.raw_secret.encode('utf-8'))
        self.mock_decrypt = self.decrypt_patcher.start()
        self.addCleanup(self.decrypt_patcher.stop)

        def mock_getaddrinfo(host, port, *args, **kwargs):
            if host in ("169.254.169.254", "127.0.0.1", "localhost", "10.0.0.1"):
                return [(2, 1, 6, '', (host, port or 80))]
            return [(2, 1, 6, '', ('93.184.216.34', port or 443))]

        self.dns_patcher = patch("socket.getaddrinfo", side_effect=mock_getaddrinfo)
        self.dns_patcher.start()
        self.addCleanup(self.dns_patcher.stop)

    # =========================================================================
    # Layer 0: The Foundational Layer (Core Dispatch, DLQ & Retries)
    # =========================================================================

    @patch("requests.post")
    def test_dispatch_webhook_delivery_success(self, mock_post):
        """Layer 0: Successful delivery (200 OK) records status 'success' and clears retry."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"received": true}'
        mock_post.return_value = mock_resp

        # Mock supabase table update
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id}])

        # Clear any existing breaker
        cb = get_circuit_breaker(f"webhook_ep_{self.endpoint_id}")
        cb.state = "CLOSED"
        cb.failure_count = 0

        res = dispatch_webhook_delivery(
            delivery=self.delivery,
            endpoint=self.endpoint,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["status_code"], 200)

        # Verify requests.post was called with signature headers
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        headers = kwargs.get("headers", {})
        self.assertIn("EleIn-Signature", headers)
        self.assertIn("EleIn-Timestamp", headers)
        self.assertEqual(headers["EleIn-Event"], "lead.replied")

        # Verify DB update recorded success
        mock_table.update.assert_called()
        update_args = mock_table.update.call_args[0][0]
        self.assertEqual(update_args["delivery_status"], "success")
        self.assertIsNone(update_args["next_retry_at"])

    def test_route_to_dead_letter(self):
        """Layer 0: Isolates failing deliveries into Dead-Letter Queue with metadata."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        
        # Select returns current delivery
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": self.delivery_id, "payload": {"foo": "bar"}, "response_body": "Err"}]),
            MagicMock(data=[{"id": self.delivery_id, "delivery_status": "dead_letter"}])
        ]

        routed = route_to_dead_letter(
            delivery_id=self.delivery_id,
            workspace_id=self.workspace_id,
            reason="UNRECOVERABLE_PAYLOAD_ERROR",
            metadata={"detail": "Bad format"},
            supabase=self.mock_supabase
        )

        self.assertTrue(routed)
        update_args = mock_table.update.call_args[0][0]
        self.assertEqual(update_args["delivery_status"], "dead_letter")
        self.assertIsNone(update_args["next_retry_at"])
        self.assertIn("dlq_info", update_args["payload"])
        self.assertEqual(update_args["payload"]["dlq_info"]["reason"], "UNRECOVERABLE_PAYLOAD_ERROR")

    def test_retry_dead_letter_delivery_success(self):
        """Layer 0: Re-enqueues a dead-letter delivery, resets attempts, and archives dlq_info."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table

        dlq_delivery = {
            "id": self.delivery_id,
            "workspace_id": self.workspace_id,
            "delivery_status": "dead_letter",
            "attempt_count": 5,
            "payload": {
                "id": "evt_123",
                "dlq_info": {"reason": "TIMEOUT", "routed_at": "2026-10-10T12:00:00Z"}
            }
        }
        mock_table.execute.side_effect = [
            MagicMock(data=[dlq_delivery]),
            MagicMock(data=[{"id": self.delivery_id, "delivery_status": "pending"}])
        ]

        res = retry_dead_letter_delivery(
            delivery_id=self.delivery_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        update_args = mock_table.update.call_args[0][0]
        self.assertEqual(update_args["delivery_status"], "pending")
        self.assertEqual(update_args["attempt_count"], 0)
        # dlq_info was popped and moved to dlq_history
        self.assertNotIn("dlq_info", update_args["payload"])
        self.assertEqual(len(update_args["payload"]["dlq_history"]), 1)

    def test_get_dead_letter_queue_pagination(self):
        """Layer 0: Paginated retrieval of DLQ deliveries within tenant bounds."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.range.return_value = mock_table

        mock_exec = MagicMock()
        mock_exec.data = [{"id": "del_1", "delivery_status": "dead_letter"}]
        mock_exec.count = 42
        mock_table.execute.return_value = mock_exec

        res = get_dead_letter_queue(
            workspace_id=self.workspace_id,
            limit=10,
            offset=20,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_count"], 42)
        self.assertEqual(res["limit"], 10)
        self.assertEqual(res["offset"], 20)
        mock_table.range.assert_called_with(20, 29)

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Outages, SSRF, Circuit Breakers)
    # =========================================================================

    @patch("requests.post")
    def test_circuit_breaker_open_defers_delivery(self, mock_post):
        """Layer 1: If circuit breaker is OPEN, outgoing requests are aborted and retried later."""
        cb = get_circuit_breaker(f"webhook_ep_{self.endpoint_id}")
        cb.state = "OPEN"
        cb.last_failure_time = time.time()  # Recent failure
        cb.recovery_timeout = 60.0

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id}])

        res = dispatch_webhook_delivery(
            delivery=self.delivery,
            endpoint=self.endpoint,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "circuit_open")
        self.assertIn("next_retry_at", res)
        # requests.post MUST NOT be called!
        mock_post.assert_not_called()

        # Reset breaker
        cb.state = "CLOSED"
        cb.failure_count = 0

    @patch("requests.post")
    def test_ssrf_prohibited_target_routes_directly_to_dlq(self, mock_post):
        """Layer 1: Endpoints targeting loopback/cloud metadata fail immediately to DLQ."""
        bad_endpoint = dict(self.endpoint)
        bad_endpoint["url"] = "http://169.254.169.254/latest/meta-data/"

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id, "payload": {}}])

        res = dispatch_webhook_delivery(
            delivery=self.delivery,
            endpoint=bad_endpoint,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "dead_letter")
        self.assertEqual(res["reason"], "SSRF_VIOLATION")
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_permanent_client_errors_route_directly_to_dlq(self, mock_post):
        """Layer 1: HTTP 400, 404, 410 responses are routed to DLQ without wasteful retries."""
        cb = get_circuit_breaker(f"webhook_ep_{self.endpoint_id}")
        cb.state = "CLOSED"
        cb.failure_count = 0

        mock_resp = MagicMock()
        mock_resp.status_code = 410  # Gone
        mock_resp.text = '{"error": "Endpoint retired"}'
        mock_post.return_value = mock_resp

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id, "payload": {}}])

        res = dispatch_webhook_delivery(
            delivery=self.delivery,
            endpoint=self.endpoint,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "dead_letter")
        self.assertEqual(res["reason"], "PERMANENT_CLIENT_ERROR_410")
        self.assertEqual(res["status_code"], 410)

    @patch("requests.post")
    def test_transient_failure_schedules_retry_with_jitter(self, mock_post):
        """Layer 1: HTTP 503 triggers exponential retry with jitter for attempts < 5."""
        cb = get_circuit_breaker(f"webhook_ep_{self.endpoint_id}")
        cb.state = "CLOSED"
        cb.failure_count = 0

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_post.return_value = mock_resp

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id}])

        # First attempt
        first_delivery = dict(self.delivery)
        first_delivery["attempt_count"] = 0

        res = dispatch_webhook_delivery(
            delivery=first_delivery,
            endpoint=self.endpoint,
            supabase=self.mock_supabase,
            max_retries=5
        )

        self.assertEqual(res["status"], "retry_scheduled")
        self.assertEqual(res["attempt_count"], 1)
        self.assertIn("next_retry_at", res)

    @patch("requests.post")
    def test_transient_failure_exhaustion_routes_to_dlq(self, mock_post):
        """Layer 1: After max_retries (5 attempts), transient failure is routed to DLQ."""
        cb = get_circuit_breaker(f"webhook_ep_{self.endpoint_id}")
        cb.state = "CLOSED"
        cb.failure_count = 0

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id, "payload": {}}])

        exhausted_delivery = dict(self.delivery)
        exhausted_delivery["attempt_count"] = 4  # Next will be 5

        res = dispatch_webhook_delivery(
            delivery=exhausted_delivery,
            endpoint=self.endpoint,
            supabase=self.mock_supabase,
            max_retries=5
        )

        self.assertEqual(res["status"], "dead_letter")
        self.assertEqual(res["reason"], "MAX_RETRIES_EXHAUSTED")

    def test_calculate_retry_backoff_formula_and_jitter(self):
        """Layer 1: Backoff calculates exponential intervals with bounded jitter."""
        # Attempt 1: 30 * 2^0 = 30s + [1..5] jitter -> 31..35s
        b1 = calculate_retry_backoff(1, base_seconds=30.0, jitter=True)
        self.assertTrue(31 <= b1 <= 35)

        # Attempt 2: 30 * 2^1 = 60s + [1..5] jitter -> 61..65s
        b2 = calculate_retry_backoff(2, base_seconds=30.0, jitter=True)
        self.assertTrue(61 <= b2 <= 65)

        # Attempt 3: 30 * 2^2 = 120s + [1..5] jitter -> 121..125s
        b3 = calculate_retry_backoff(3, base_seconds=30.0, jitter=True)
        self.assertTrue(121 <= b3 <= 125)

        # Max cap enforced
        b_cap = calculate_retry_backoff(20, base_seconds=30.0, max_seconds=300.0, jitter=False)
        self.assertEqual(b_cap, 300)

    @patch("requests.post")
    def test_corrupt_signing_secret_routes_to_dlq(self, mock_post):
        """Layer 1: Malformed signing secret hex routes to DLQ immediately."""
        corrupt_endpoint = dict(self.endpoint)
        corrupt_endpoint["signing_secret"] = "not_valid_hex_string"

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.delivery_id, "payload": {}}])

        res = dispatch_webhook_delivery(
            delivery=self.delivery,
            endpoint=corrupt_endpoint,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "dead_letter")
        self.assertEqual(res["reason"], "CORRUPT_SIGNING_SECRET")
        mock_post.assert_not_called()

    # =========================================================================
    # Layer 2: Human Paranoia & Security Hardening (IDOR, Secrets, Sanitization)
    # =========================================================================

    def test_dlq_retry_idor_cross_tenant_isolation(self):
        """Layer 2: Re-enqueue attempt on foreign workspace delivery is rejected."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        # Returns empty list because .eq("workspace_id", "ws_attacker") finds nothing
        mock_table.execute.return_value = MagicMock(data=[])

        res = retry_dead_letter_delivery(
            delivery_id=self.delivery_id,
            workspace_id="ws_attacker",
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "error")
        self.assertIn("not found or foreign workspace", res["message"].lower())

    def test_dlq_retry_invalid_status_rejection(self):
        """Layer 2: Cannot re-enqueue a delivery that is already 'success' or 'pending'."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{
            "id": self.delivery_id,
            "workspace_id": self.workspace_id,
            "delivery_status": "success"
        }])

        res = retry_dead_letter_delivery(
            delivery_id=self.delivery_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "error")
        self.assertIn("cannot retry from dlq", res["message"].lower())

    def test_sanitize_webhook_payload_removes_secrets(self):
        """Layer 2: Strips passwords, auth tokens, cookies, and api keys recursively."""
        dirty_payload = {
            "lead_id": "lead_123",
            "name": "Jane Doe",
            "auth_token": "secret_token_abc",
            "password": "super_secret_password",
            "api_key": "nvapi-12345",
            "nested": {
                "safe_field": "visible",
                "client_secret": "forbidden",
                "session_cookie": "sess_xyz"
            },
            "array_data": [
                {"token": "tok_1", "email": "jane@example.com"},
                {"private_key": "pk_rsa"}
            ]
        }

        clean = sanitize_webhook_payload(dirty_payload)

        self.assertEqual(clean["lead_id"], "lead_123")
        self.assertEqual(clean["name"], "Jane Doe")
        self.assertNotIn("auth_token", clean)
        self.assertNotIn("password", clean)
        self.assertNotIn("api_key", clean)
        self.assertEqual(clean["nested"]["safe_field"], "visible")
        self.assertNotIn("client_secret", clean["nested"])
        self.assertNotIn("session_cookie", clean["nested"])
        self.assertEqual(clean["array_data"][0]["email"], "jane@example.com")
        self.assertNotIn("token", clean["array_data"][0])
        self.assertNotIn("private_key", clean["array_data"][1])

    @patch("integrations.backend.services.webhook_service.dispatch_webhook_delivery")
    def test_webhook_worker_process_delivery_delegation(self, mock_dispatch):
        """Layer 2: Verifies core webhook worker process_delivery delegates seamlessly."""
        mock_dispatch.return_value = {"status": "success", "status_code": 200}

        res = process_delivery(
            delivery=self.delivery,
            endpoint=self.endpoint,
            client=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        mock_dispatch.assert_called_once_with(
            delivery=self.delivery,
            endpoint=self.endpoint,
            supabase=self.mock_supabase
        )

    def test_api_get_dead_letter_queue_success(self):
        """Layer 2: Router endpoint GET /dead-letter-queue returns paginated DLQ items."""
        from integrations.backend.routers.webhooks import get_dead_letter_queue_endpoint
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.range.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "del_dlq_1"}], count=1)

        res = get_dead_letter_queue_endpoint(
            limit=25,
            offset=0,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["data"]), 1)

    def test_api_retry_dlq_delivery_success(self):
        """Layer 2: Router endpoint POST /deliveries/{delivery_id}/retry-dlq re-enqueues."""
        from integrations.backend.routers.webhooks import retry_dlq_delivery_endpoint
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": self.delivery_id, "workspace_id": self.workspace_id, "delivery_status": "dead_letter"}]),
            MagicMock(data=[{"id": self.delivery_id, "delivery_status": "pending"}])
        ]

        res = retry_dlq_delivery_endpoint(
            delivery_id=self.delivery_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")

    def test_api_retry_dlq_delivery_idor_404(self):
        """Layer 2: Router endpoint POST /deliveries/{delivery_id}/retry-dlq raises 404 on IDOR."""
        from fastapi import HTTPException
        from integrations.backend.routers.webhooks import retry_dlq_delivery_endpoint
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            retry_dlq_delivery_endpoint(
                delivery_id=self.delivery_id,
                workspace_id="ws_foreign",
                supabase=self.mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_api_retry_dlq_delivery_invalid_status_400(self):
        """Layer 2: Router endpoint POST /deliveries/{delivery_id}/retry-dlq raises 400 on non-DLQ status."""
        from fastapi import HTTPException
        from integrations.backend.routers.webhooks import retry_dlq_delivery_endpoint
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{
            "id": self.delivery_id,
            "workspace_id": self.workspace_id,
            "delivery_status": "success"
        }])

        with self.assertRaises(HTTPException) as ctx:
            retry_dlq_delivery_endpoint(
                delivery_id=self.delivery_id,
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

