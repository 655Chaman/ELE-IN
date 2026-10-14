"""
test_horizon25_inbound_webhook_buffer_replay_defense.py — Horizon 25 Test Suite
Inbound Webhook Ingestion Buffer, Replay Attack Clock Drift Defense & High-Throughput Batch Commits.
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from integrations.backend.services.inbound_ingest_service import (
    validate_inbound_timestamp,
    sanitize_lead_field,
    is_valid_email,
    InboundIdempotencyLedger,
    get_inbound_idempotency_ledger,
    generate_inbound_idempotency_key,
    batch_ingest_inbound_leads,
)
from campaigns.backend.routers.inbound_webhooks import hubspot_inbound_webhook


class TestHorizon25InboundWebhookBufferReplayDefense(unittest.IsolatedAsyncioTestCase):
    """
    Horizon 25 Verification Suite: Inbound Webhook Buffer, Anti-Replay Clock Drift Defense,
    Idempotency Ledgers, and High-Throughput N+1 Query Eradication.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_test_horizon25"
        self.campaign_id = "camp_test_25"
        self.ledger = InboundIdempotencyLedger(capacity=100)
        self.ledger.clear()

    # =========================================================================
    # Layer 0: The Foundational Layer (Batch Ingestion & Idempotency Mechanics)
    # =========================================================================

    @patch("integrations.backend.services.webhook_service.emit_webhook_event")
    def test_batch_ingest_inbound_leads_success_partitioning(self, mock_emit):
        """Layer 0: Partitions batch into bulk-inserts (new) and updates (existing) in single queries."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.upsert.return_value = mock_table

        # Existing query finds alice@example.com, but bob@example.com and charlie@example.com are new
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": "lead_existing_alice", "email": "alice@example.com"}]),  # select existing
            MagicMock(data=[{"id": "lead_existing_alice"}]),                                 # update alice
            MagicMock(data=[{"id": "lead_new_1"}, {"id": "lead_new_2"}]),                   # bulk insert 2 new
            MagicMock(data=[{"id": "state_1"}, {"id": "state_2"}, {"id": "state_3"}])       # bulk upsert states
        ]

        batch = [
            {"email": "alice@example.com", "firstname": "Alice", "company": "Acme Inc"},
            {"email": "bob@example.com", "firstname": "Bob", "company": "Beta Corp"},
            {"email": "charlie@example.com", "firstname": "Charlie", "company": "Charlie LLC"},
        ]

        res = batch_ingest_inbound_leads(
            workspace_id=self.workspace_id,
            items=batch,
            campaign_id=self.campaign_id,
            source="hubspot_webhook",
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["processed_count"], 3)
        self.assertEqual(res["created_count"], 2)
        self.assertEqual(res["updated_count"], 1)
        self.assertEqual(res["enrolled_count"], 3)
        self.assertEqual(len(res["errors"]), 0)

        # Verify bulk insert was called with Bob and Charlie
        mock_table.insert.assert_called_once()
        inserted_items = mock_table.insert.call_args[0][0]
        self.assertEqual(len(inserted_items), 2)
        inserted_emails = [item["email"] for item in inserted_items]
        self.assertIn("bob@example.com", inserted_emails)
        self.assertIn("charlie@example.com", inserted_emails)

    def test_inbound_idempotency_ledger_prevents_duplicate_processing(self):
        """Layer 0: Idempotency ledger intercepts duplicate payloads and returns cached result."""
        idem_key = "hubspot:ws_test_25:sha256:abcd1234efgh5678"
        initial_result = {"status": "success", "processed_count": 5}

        # First check: not duplicate, records key
        is_dup1, cached1 = self.ledger.check_and_set(idem_key, ttl_seconds=300, result_data=initial_result)
        self.assertFalse(is_dup1)
        self.assertIsNone(cached1)

        # Second check: duplicate detected, returns cached result
        is_dup2, cached2 = self.ledger.check_and_set(idem_key, ttl_seconds=300)
        self.assertTrue(is_dup2)
        self.assertEqual(cached2, initial_result)

    def test_validate_inbound_timestamp_fresh(self):
        """Layer 0: Fresh timestamp within 300s tolerance passes validation."""
        now_ts = int(time.time())
        is_valid, err = validate_inbound_timestamp(now_ts, max_drift_seconds=300)
        self.assertTrue(is_valid)
        self.assertIsNone(err)

        # Millisecond timestamp normalization
        ms_ts = now_ts * 1000
        is_valid_ms, err_ms = validate_inbound_timestamp(ms_ts, max_drift_seconds=300)
        self.assertTrue(is_valid_ms)
        self.assertIsNone(err_ms)

    @patch("integrations.backend.services.webhook_service.emit_webhook_event")
    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_hubspot_webhook_successful_ingestion_and_enrollment(self, mock_get_client, mock_emit):
        """Layer 0: Full hubspot_inbound_webhook handler ingests and enrolls lead."""
        mock_get_client.return_value = self.mock_supabase

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.upsert.return_value = mock_table

        # Return workspace then empty existing leads
        mock_table.execute.side_effect = [
            MagicMock(data=[{"id": self.workspace_id, "status": "active"}]),  # workspace
            MagicMock(data=[]),                                                # existing leads
            MagicMock(data=[{"id": "new_lead_id"}]),                          # lead insert
            MagicMock(data=[{"id": "new_state_id"}])                           # execution state upsert
        ]

        payload = {
            "properties": {
                "email": "dharmesh@hubspot.com",
                "firstname": "Dharmesh",
                "lastname": "Shah",
                "company": "HubSpot"
            }
        }

        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value=payload)
        mock_req.headers.get.return_value = None

        res = await hubspot_inbound_webhook(
            workspace_id=self.workspace_id,
            request=mock_req,
            campaign_id=self.campaign_id
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["processed_count"], 1)
        self.assertEqual(res["created_count"], 1)
        self.assertEqual(res["leads"][0]["email"], "dharmesh@hubspot.com")

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Clock Drift, Floods, Replays)
    # =========================================================================

    def test_validate_inbound_timestamp_expired_and_future_clock_drift(self):
        """Layer 1: Stale timestamps (>300s old) or excessive future skew are rejected."""
        now_ts = int(time.time())

        # 301 seconds old -> rejected
        is_valid_old, err_old = validate_inbound_timestamp(now_ts - 301, max_drift_seconds=300)
        self.assertFalse(is_valid_old)
        self.assertIn("drift exceeds 300s window", err_old)

        # 305 seconds in future -> rejected
        is_valid_future, err_future = validate_inbound_timestamp(now_ts + 305, max_drift_seconds=300)
        self.assertFalse(is_valid_future)
        self.assertIn("drift exceeds 300s window", err_future)

        # Malformed format -> rejected
        is_valid_bad, err_bad = validate_inbound_timestamp("not_a_valid_number")
        self.assertFalse(is_valid_bad)
        self.assertIn("Invalid timestamp format", err_bad)

    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_hubspot_webhook_rejects_expired_timestamp_401(self, mock_get_client):
        """Layer 1: Incoming webhook with expired timestamp header raises HTTP 401."""
        mock_get_client.return_value = self.mock_supabase
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.workspace_id, "status": "active"}])

        expired_ts = str(int(time.time()) - 400)
        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value={"email": "lead@test.com"})
        mock_req.headers.get.side_effect = lambda h: expired_ts if "timestamp" in h.lower() else None

        with self.assertRaises(HTTPException) as cm:
            await hubspot_inbound_webhook(
                workspace_id=self.workspace_id,
                request=mock_req
            )
        self.assertEqual(cm.exception.status_code, 401)
        self.assertIn("Webhook timestamp rejected", cm.exception.detail)

    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_batch_size_flooding_ceiling(self, mock_get_client):
        """Layer 1: Reject batches exceeding MAX_BATCH_SIZE (500) with HTTP 400."""
        mock_get_client.return_value = self.mock_supabase
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.workspace_id, "status": "active"}])

        oversized_batch = [{"email": f"user{i}@example.com"} for i in range(501)]
        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value=oversized_batch)

        with self.assertRaises(HTTPException) as cm:
            await hubspot_inbound_webhook(
                workspace_id=self.workspace_id,
                request=mock_req
            )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Batch size exceeds maximum limit", cm.exception.detail)

    def test_chunked_batch_inserts_for_large_batches(self):
        """Layer 1: Batches of 250 leads are inserted in chunks of 100 max (3 bulk calls)."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        batch = [{"email": f"prospect_{i}@domain.com", "firstname": f"Prospect {i}"} for i in range(250)]

        res = batch_ingest_inbound_leads(
            workspace_id=self.workspace_id,
            items=batch,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["created_count"], 250)

        # 250 leads / 100 chunk size = 3 insert calls (100, 100, 50)
        self.assertEqual(mock_table.insert.call_count, 3)
        chunk1 = mock_table.insert.call_args_list[0][0][0]
        chunk2 = mock_table.insert.call_args_list[1][0][0]
        chunk3 = mock_table.insert.call_args_list[2][0][0]
        self.assertEqual(len(chunk1), 100)
        self.assertEqual(len(chunk2), 100)
        self.assertEqual(len(chunk3), 50)

    @patch("integrations.backend.services.webhook_service.emit_webhook_event")
    @patch("campaigns.backend.routers.inbound_webhooks.get_service_client")
    async def test_hubspot_webhook_replay_returns_cached_duplicate(self, mock_get_client, mock_emit):
        """Layer 1: Replayed webhook payload returns duplicate_idempotent without re-inserting."""
        mock_get_client.return_value = self.mock_supabase

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": self.workspace_id, "status": "active"}, {"id": "new_lead_id"}])

        payload = {"properties": {"email": "unique_replay_test@hubspot.com", "firstname": "Replay"}}
        mock_req = MagicMock()
        mock_req.json = AsyncMock(return_value=payload)
        mock_req.headers.get.side_effect = lambda h: "idemp_token_unique_999" if "idempotency" in h.lower() else None

        # Call 1: Processed
        res1 = await hubspot_inbound_webhook(workspace_id=self.workspace_id, request=mock_req)
        self.assertEqual(res1["status"], "success")
        self.assertEqual(res1["created_count"], 1)

        # Call 2: Replay intercepted by ledger!
        res2 = await hubspot_inbound_webhook(workspace_id=self.workspace_id, request=mock_req)
        self.assertEqual(res2["status"], "duplicate_idempotent")
        self.assertTrue(res2["cached"])

    # =========================================================================
    # Layer 2: Human Paranoia & Security Hardening (Sanitization & IDOR)
    # =========================================================================

    def test_null_byte_and_control_character_stripping(self):
        """Layer 2: Strips dangerous null bytes and carriage returns from inputs."""
        dirty_name = "Satya\x00\x00Nadella\r\n"
        clean_name = sanitize_lead_field(dirty_name, max_len=100)
        self.assertEqual(clean_name, "SatyaNadella")
        self.assertNotIn("\x00", clean_name)
        self.assertNotIn("\r", clean_name)

    def test_field_length_clamping(self):
        """Layer 2: Clamps oversized strings to prevent Postgres schema errors."""
        long_company = "A" * 500
        clean_company = sanitize_lead_field(long_company, max_len=150)
        self.assertEqual(len(clean_company), 150)

    def test_invalid_and_corrupt_emails_filtered_without_dropping_batch(self):
        """Layer 2: Filters bad emails while successfully processing remaining valid leads."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        mixed_batch = [
            {"email": "valid_user@company.com", "firstname": "Valid"},
            {"email": "not_an_email", "firstname": "Broken"},
            {"email": None, "firstname": "Empty"},
            "this_is_not_even_a_dictionary",
            {"email": "another_valid@company.com", "firstname": "Another"}
        ]

        res = batch_ingest_inbound_leads(
            workspace_id=self.workspace_id,
            items=mixed_batch,
            supabase=self.mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["processed_count"], 2)
        self.assertEqual(res["created_count"], 2)
        self.assertEqual(len(res["errors"]), 3)

    def test_explicit_idempotency_key_override(self):
        """Layer 2: Explicit headers take precedence over body hashes."""
        payload = {"email": "test@example.com"}
        k1 = generate_inbound_idempotency_key("hubspot", "ws_123", payload, explicit_key="evt_hubspot_456")
        self.assertEqual(k1, "hubspot:ws_123:evt_hubspot_456")

        k2 = generate_inbound_idempotency_key("hubspot", "ws_123", payload)
        self.assertTrue(k2.startswith("hubspot:ws_123:sha256:"))


if __name__ == "__main__":
    unittest.main()
