"""
test_esp_webhook_and_circuit_breaker.py — Comprehensive Integration & Paranoia Test Suite
for Phase 40 (Unified ESP Webhook Feedback Loop, FBL ARF Abuse Processor & Runaway Bounce Circuit Breaker).
Hardened under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import os
import time
import json
import base64
import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch, ANY

import pytest
from fastapi.testclient import TestClient

from core.backend.main import app
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.routers.elein import (
    webhook_esp_sendgrid,
    webhook_esp_mailgun,
    api_simulate_esp_event,
    api_evaluate_campaign_circuit_breaker,
    CircuitBreakerEvaluationRequest,
    ESPSimulateRequest,
)
from integrations.backend.services.esp_webhook_processor import (
    ESPProvider,
    WebhookEventType,
    ESPWebhookProcessor,
    evaluate_campaign_circuit_breaker,
)


class TestESPWebhookAndCircuitBreaker(unittest.TestCase):
    """
    Rigorously tests the Webhook Endpoints, Anti-Replay Guard, Tenant IDOR defenses,
    and Orchestrator Circuit Breaker integration across all three paranoia layers.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.workspace_id = "ws-test-esp-phase40"
        self.mock_supabase = MagicMock()
        self.mock_table = MagicMock()
        self.mock_supabase.table.return_value = self.mock_table
        self.mock_table.select.return_value = self.mock_table
        self.mock_table.update.return_value = self.mock_table
        self.mock_table.insert.return_value = self.mock_table
        self.mock_table.in_.return_value = self.mock_table
        self.mock_table.eq.return_value = self.mock_table
        self.mock_table.execute.return_value = MagicMock(data=[])

    # =========================================================================
    # LAYER 0: FOUNDATIONAL ROUTER & CIRCUIT BREAKER MECHANICS
    # =========================================================================

    def test_router_sendgrid_webhook_endpoint(self):
        """
        Layer 0: POST /api/elein/webhooks/esp/sendgrid ingests SendGrid events,
        calls feedback processor, and returns 200 with metrics.
        """
        payload = [
            {
                "event": "delivered",
                "email": "lead_delivered@acme.com",
                "sg_message_id": "sg_deliv_001",
                "campaign_id": "camp_test_1",
                "workspace_id": self.workspace_id,
            },
            {
                "event": "open",
                "email": "lead_delivered@acme.com",
                "sg_message_id": "sg_deliv_001",
            }
        ]
        res = self.client.post(
            "/api/elein/webhooks/esp/sendgrid",
            json=payload,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["events_processed"], 2)
        self.assertIsInstance(data["tripped_campaigns"], list)

    def test_router_mailgun_webhook_endpoint(self):
        """
        Layer 0: POST /api/elein/webhooks/esp/mailgun processes Mailgun payload
        and returns 200 status.
        """
        payload = {
            "event-data": {
                "event": "delivered",
                "recipient": "mg_lead@enterprise.com",
                "id": "mg_msg_100",
                "user-variables": {
                    "campaign_id": "camp_mg_1",
                    "workspace_id": self.workspace_id,
                }
            }
        }
        res = self.client.post(
            "/api/elein/webhooks/esp/mailgun",
            json=payload,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["events_processed"], 1)

    def test_router_circuit_breaker_endpoint(self):
        """
        Layer 0: POST /api/elein/deliverability/evaluate-campaign-circuit-breaker
        accurately checks campaign metrics and returns status.
        """
        # Create an authorized request using dependency injection or mock header
        req = CircuitBreakerEvaluationRequest(
            sent_count=100,
            bounce_count=1,
            spam_complaint_count=0,
            auto_pause=False,
        )
        res = api_evaluate_campaign_circuit_breaker(
            req=req,
            workspace_id=self.workspace_id,
            db=self.mock_supabase,
        )
        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertFalse(res["should_trip"])
        self.assertEqual(res["status"], "HEALTHY")
        self.assertEqual(res["bounce_rate"], 0.01)

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS & RESILIENCE
    # =========================================================================

    def test_replay_attack_rejected_stale_timestamp(self):
        """
        Layer 1: SendGrid webhook request with timestamp > 600s old is rejected (401).
        """
        stale_timestamp = str(int(time.time() - 700))
        secret_key = "test_signing_key_secret"
        payload = b'[{"event":"delivered","email":"stale@test.com"}]'
        signed_data = stale_timestamp.encode("utf-8") + payload
        sig = base64.b64encode(hmac.new(secret_key.encode("utf-8"), signed_data, hashlib.sha256).digest()).decode("utf-8")

        with patch.dict(os.environ, {"SENDGRID_WEBHOOK_VERIFICATION_KEY": secret_key}):
            res = self.client.post(
                "/api/elein/webhooks/esp/sendgrid",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Twilio-Email-Event-Webhook-Signature": sig,
                    "X-Twilio-Email-Event-Webhook-Timestamp": stale_timestamp,
                }
            )
            self.assertEqual(res.status_code, 401)
            self.assertIn("Invalid SendGrid", res.json()["detail"])

    def test_batch_events_sendgrid_array_processed(self):
        """
        Layer 1: Batch of 50 events in a JSON array handled cleanly without partial failures.
        """
        batch = [
            {
                "event": "delivered" if i % 2 == 0 else "open",
                "email": f"batch_lead_{i}@corp.com",
                "sg_message_id": f"msg_batch_{i}",
                "campaign_id": "camp_batch_test",
                "workspace_id": self.workspace_id,
            }
            for i in range(50)
        ]
        res = self.client.post(
            "/api/elein/webhooks/esp/sendgrid",
            json=batch,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["events_processed"], 50)

    def test_idempotent_event_deduplication(self):
        """
        Layer 1: Re-submitting the exact same webhook event is processed safely without crash.
        """
        payload = [{
            "event": "delivered",
            "email": "idempotent@corp.com",
            "sg_message_id": "msg_idem_1",
            "campaign_id": "camp_idem",
        }]
        # First send
        res1 = self.client.post("/api/elein/webhooks/esp/sendgrid", json=payload)
        self.assertEqual(res1.status_code, 200)

        # Immediate replay
        res2 = self.client.post("/api/elein/webhooks/esp/sendgrid", json=payload)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["events_processed"], 1)

    def test_malformed_json_and_missing_keys_handled_safely(self):
        """
        Layer 1: Corrupted or non-JSON payloads return 400 without crashing the server with 500.
        """
        res = self.client.post(
            "/api/elein/webhooks/esp/sendgrid",
            content=b"this is not valid json {{{[[",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(res.status_code, 400)

        # Empty array or object handled gracefully
        res_empty = self.client.post(
            "/api/elein/webhooks/esp/sendgrid",
            json=[],
        )
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(res_empty.json()["events_processed"], 0)

    def test_missing_database_graceful_fallback(self):
        """
        Layer 1: Database connectivity failure does not crash webhook endpoint.
        """
        failing_db = MagicMock()
        failing_db.table.side_effect = ConnectionError("Supabase connection pool exhausted")

        # Call endpoint directly with failing database
        mock_request = MagicMock()
        mock_request.body = MagicMock(return_value=b'[{"event":"delivered","email":"db_fail@test.com"}]')
        mock_request.headers = {}

        # The router catches per-event DB errors and still returns 200 with partial or safe status
        import asyncio
        loop = asyncio.get_event_loop()
        res = loop.run_until_complete(
            webhook_esp_sendgrid(
                request=mock_request,
                x_twilio_email_event_webhook_signature=None,
                x_twilio_email_event_webhook_timestamp=None,
                db=failing_db,
            )
        )
        self.assertEqual(res["status"], "ok")

    def test_circuit_breaker_auto_pauses_campaign_in_db(self):
        """
        Layer 1: Tripped circuit breaker updates campaign status to 'paused' in database.
        """
        mock_db = MagicMock()
        mock_tbl = MagicMock()
        mock_db.table.return_value = mock_tbl
        mock_tbl.select.return_value = mock_tbl
        mock_tbl.update.return_value = mock_tbl
        mock_tbl.eq.return_value = mock_tbl
        mock_tbl.execute.return_value = MagicMock(data=[{"id": "camp_runaway_1", "workspace_id": self.workspace_id}])

        req = CircuitBreakerEvaluationRequest(
            campaign_id="camp_runaway_1",
            sent_count=100,
            bounce_count=10,  # 10% bounce rate > 3% threshold
            spam_complaint_count=0,
            auto_pause=True,
        )

        res = api_evaluate_campaign_circuit_breaker(
            req=req,
            workspace_id=self.workspace_id,
            db=mock_db,
        )

        self.assertTrue(res["should_trip"])
        self.assertEqual(res["status"], "TRIPPED")
        self.assertIn("CRITICAL_BOUNCE_SPIKE", res["tripwire"])

        # Verify update was called on campaigns table
        mock_tbl.update.assert_called()
        update_args = mock_tbl.update.call_args[0][0]
        self.assertEqual(update_args["status"], "paused")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & SECURITY DEFENSES
    # =========================================================================

    def test_mailgun_invalid_signature_rejected(self):
        """
        Layer 2: Mailgun webhook rejects invalid or forged signatures with 401.
        """
        secret_key = "mailgun_test_secret"
        with patch.dict(os.environ, {"MAILGUN_WEBHOOK_SIGNING_KEY": secret_key}):
            payload = {
                "signature": {
                    "token": "fake_token_123",
                    "timestamp": str(int(time.time())),
                    "signature": "bad_hex_signature_deadbeef",
                },
                "event-data": {"event": "opened", "recipient": "user@test.com"}
            }
            res = self.client.post("/api/elein/webhooks/esp/mailgun", json=payload)
            self.assertEqual(res.status_code, 401)
            self.assertIn("Invalid Mailgun signature", res.json()["detail"])

    def test_sendgrid_timing_attack_defense(self):
        """
        Layer 2: SendGrid webhook signature verification uses constant-time compare_digest.
        """
        secret_key = "sendgrid_hmac_secret"
        ts = str(int(time.time()))
        payload = b'[{"event":"delivered","email":"safe@elein.io"}]'
        signed_data = ts.encode("utf-8") + payload
        sig = base64.b64encode(hmac.new(secret_key.encode("utf-8"), signed_data, hashlib.sha256).digest()).decode("utf-8")

        with patch.dict(os.environ, {"SENDGRID_WEBHOOK_VERIFICATION_KEY": secret_key}):
            with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
                res = self.client.post(
                    "/api/elein/webhooks/esp/sendgrid",
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Twilio-Email-Event-Webhook-Signature": sig,
                        "X-Twilio-Email-Event-Webhook-Timestamp": ts,
                    }
                )
                self.assertEqual(res.status_code, 200)
                mock_compare.assert_called()

    def test_cross_tenant_idor_simulation_endpoint(self):
        """
        Layer 2: Simulation endpoint requires valid workspace authentication
        and strictly rejects cross-tenant spoofing attempts (IDOR defense).
        """
        # 1. Unauthenticated request to /api/elein/webhooks/esp/simulate returns 401
        unauth_client = TestClient(app)
        res_unauth = unauth_client.post(
            "/api/elein/webhooks/esp/simulate",
            json={"email": "victim@domain.com", "event_type": "bounce_hard"}
        )
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Cross-tenant attempt (caller's authenticated workspace != payload workspace_id) returns 403
        req = ESPSimulateRequest(
            email="target@domain.com",
            event_type="bounce_hard",
            workspace_id="attacker_target_workspace_id",  # Mismatched!
        )
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            api_simulate_esp_event(
                req=req,
                workspace_id="victim_actual_workspace_id",
                db=self.mock_supabase,
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cross-tenant", ctx.exception.detail)

    def test_simulation_endpoint_executes_feedback_loop(self):
        """
        Layer 2: Authenticated simulation endpoint simulates bounce without external MTA.
        """
        req = ESPSimulateRequest(
            email="simulated_bounce@lead.com",
            event_type="bounce_hard",
            reason="Simulated 550 Mailbox not found",
            smtp_code=550,
            campaign_id="camp_sim_1",
        )
        res = api_simulate_esp_event(
            req=req,
            workspace_id=self.workspace_id,
            db=self.mock_supabase,
        )
        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["simulated"])
        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertEqual(res["result"]["action_taken"], "LEAD_BOUNCED_AND_SUPPRESSED")

    # =========================================================================
    # ORCHESTRATOR CIRCUIT BREAKER TRIPWIRE INTEGRATION TESTS
    # =========================================================================

    def test_orchestrator_skips_campaign_paused_by_circuit_breaker(self):
        """
        Layer 0, 1 & 2: Campaign paused by circuit breaker is not executed by orchestrator;
        lead state is updated to 'paused' and dispatch is halted.
        """
        mock_supabase = MagicMock()
        mock_camp_query = MagicMock()

        # Simulate campaign row returned with status="paused" and status_reason="CIRCUIT_BREAKER_CRITICAL_BOUNCE_SPIKE"
        mock_camp_query.execute.return_value = MagicMock(data=[{
            "id": "camp_tripped_101",
            "status": "paused",
            "status_reason": "CIRCUIT_BREAKER_CRITICAL_BOUNCE_SPIKE",
        }])
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_camp_query

        orchestrator = EleInOrchestrator(supabase=mock_supabase)
        orchestrator.update_state = MagicMock()
        orchestrator.execute_node_action = MagicMock()

        test_state = {
            "id": "state_lead_99",
            "campaign_id": "camp_tripped_101",
            "opportunity_id": "lead_prospect_42",
            "current_node_id": "node_send_email_1",
            "nodes": [{"id": "node_send_email_1", "node_type": "send_email", "config": {}}],
            "edges": [],
            "variables": {},
            "tz_str": "UTC",
        }

        # Call orchestrator.process_lead() with test state and lease token
        orchestrator.process_lead(test_state, "token_abc_123")

        # Verify update_state was called with status="paused" and circuit breaker reason
        orchestrator.update_state.assert_called_once()
        args, kwargs = orchestrator.update_state.call_args
        self.assertEqual(args[0], "state_lead_99")
        self.assertEqual(args[2], "paused")
        self.assertEqual(args[3], None)  # next_run is None
        self.assertIn("CIRCUIT_BREAKER", kwargs.get("error_reason", ""))
        orchestrator.execute_node_action.assert_not_called()

    def test_orchestrator_normal_active_campaign_proceeds(self):
        """
        Orchestrator proceeds with normal active campaign not paused by circuit breaker.
        """
        mock_supabase = MagicMock()
        mock_camp_query = MagicMock()
        mock_camp_query.execute.return_value = MagicMock(data=[{
            "id": "camp_active_normal",
            "status": "ACTIVE",
            "status_reason": None,
        }])
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_camp_query

        orchestrator = EleInOrchestrator(supabase=mock_supabase)
        orchestrator.update_state = MagicMock()
        orchestrator.execute_node_action = MagicMock(return_value={"status": "success"})

        test_state = {
            "id": "state_normal_1",
            "campaign_id": "camp_active_normal",
            "opportunity_id": "lead_ok_1",
            "current_node_id": "node_send_email_1",
            "nodes": [{"id": "node_send_email_1", "node_type": "send_email", "config": {}}],
            "edges": [],
            "variables": {},
            "tz_str": "UTC",
        }

        with patch("campaigns.backend.services.collision_guard.is_lead_active_in_other_campaign", return_value=False):
            orchestrator.process_lead(test_state, "token_normal_123")

        # execute_node_action should be called for active campaign
        orchestrator.execute_node_action.assert_called_once()


if __name__ == "__main__":
    unittest.main()
