import unittest
from unittest.mock import MagicMock, patch
import uuid
import json

from inbox.backend.services.inbox_service import sync_inbox_messages
from campaigns.backend.services.elein_executor import EleInNodeExecutor


class TestInboundMessageDeduplicationAndAIGuard(unittest.TestCase):
    """
    Step 13: Inbound Message Deduplication & AI Draft Double-Generation Guard
    Tests compliance with the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.workspace_id = "ws_test_123"
        self.account_id = "acc_test_456"

    # =========================================================================
    # Test 1: Deterministic UUID generation
    # =========================================================================
    def test_sync_inbox_messages_generates_deterministic_uuid(self):
        """
        Layer 1 Paranoia: Two parallel sync calls or extension instances syncing
        the exact same message attributes MUST generate the exact same deterministic UUID5.
        """
        msg = {
            "sender_name": "Alice Smith",
            "message_text": "Hello, let's connect!",
            "direction": "inbound",
            "thread_url": "https://www.linkedin.com/messaging/thread/2-YmNmNjQy/",
        }

        hash_seed = f"{self.workspace_id}:{self.account_id}:{msg['sender_name']}:{msg['message_text']}:{msg['direction']}:{msg['thread_url']}"
        expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, hash_seed))

        # First run
        mock_supabase1 = MagicMock()
        mock_supabase1.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        sync_inbox_messages(mock_supabase1, self.workspace_id, self.account_id, [msg])

        upsert_call1 = mock_supabase1.table("messages").upsert.call_args[0][0]
        self.assertEqual(len(upsert_call1), 1)
        gen_id_1 = upsert_call1[0]["id"]
        self.assertEqual(gen_id_1, expected_uuid)

        # Second run with another mock instance (simulating concurrent worker/tab)
        mock_supabase2 = MagicMock()
        mock_supabase2.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        sync_inbox_messages(mock_supabase2, self.workspace_id, self.account_id, [msg])

        upsert_call2 = mock_supabase2.table("messages").upsert.call_args[0][0]
        gen_id_2 = upsert_call2[0]["id"]
        self.assertEqual(gen_id_2, expected_uuid)
        self.assertEqual(gen_id_1, gen_id_2)

    # =========================================================================
    # Test 2: Persist thread_url in messages and approval_queue
    # =========================================================================
    def test_sync_inbox_messages_persists_thread_url(self):
        """
        Layer 0 & 1 Paranoia: Verifies thread_url is preserved in both messages
        upsert payload and approval_queue insert payload without dropping metadata.
        """
        thread_url = "https://www.linkedin.com/messaging/thread/thread-xyz-789/"
        msg = {
            "sender_name": "Bob Prospect",
            "message_text": "Sounds very interesting! Can you send pricing?",
            "direction": "inbound",
            "intent": "positive",
            "lead_id": "lead_999",
            "thread_url": thread_url,
        }

        mock_supabase = MagicMock()
        # No existing records in messages or approval_queue
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        sync_inbox_messages(mock_supabase, self.workspace_id, self.account_id, [msg])

        # Verify thread_url in messages upsert
        upsert_records = mock_supabase.table("messages").upsert.call_args[0][0]
        self.assertEqual(len(upsert_records), 1)
        self.assertEqual(upsert_records[0].get("thread_url"), thread_url)

        # Verify thread_url in approval_queue insert
        insert_records = mock_supabase.table("approval_queue").insert.call_args[0][0]
        self.assertEqual(len(insert_records), 1)
        self.assertEqual(insert_records[0].get("thread_url"), thread_url)

    # =========================================================================
    # Test 3: Prevents duplicate approval queue items
    # =========================================================================
    def test_sync_inbox_messages_prevents_duplicate_approval_queue_items(self):
        """
        Layer 1 & 2 Paranoia: If an approval is already pending for a sender/lead/thread,
        subsequent syncs or multiple messages in the same batch MUST NOT append duplicate queue items.
        """
        thread_url = "https://www.linkedin.com/messaging/thread/thread-101/"
        msg1 = {
            "sender_name": "Charlie Chief",
            "message_text": "Yes, I am interested in a demo.",
            "direction": "inbound",
            "intent": "positive",
            "lead_id": "lead_333",
            "thread_url": thread_url,
        }
        msg2 = {
            "sender_name": "Charlie Chief",
            "message_text": "Also let me know what times work on Thursday.",
            "direction": "inbound",
            "intent": "positive",
            "lead_id": "lead_333",
            "thread_url": thread_url,
        }

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(data=[])

        # Batch with two positive messages from the same sender/lead/thread
        res = sync_inbox_messages(mock_supabase, self.workspace_id, self.account_id, [msg1, msg2])
        self.assertEqual(res["queued"], 1)

        insert_records = mock_supabase.table("approval_queue").insert.call_args[0][0]
        self.assertEqual(len(insert_records), 1)
        self.assertEqual(insert_records[0]["sender_name"], "Charlie Chief")
        self.assertEqual(insert_records[0]["thread_url"], thread_url)

        # Now simulate a second sync where approval_queue already has pending entry in DB
        mock_supabase2 = MagicMock()
        mock_msg_select = MagicMock()
        mock_msg_select.execute.return_value = MagicMock(data=[])

        mock_q_select = MagicMock()
        mock_q_select.execute.return_value = MagicMock(data=[{
            "sender_name": "Charlie Chief",
            "lead_id": "lead_333",
            "thread_url": thread_url
        }])

        mock_approval_tbl = MagicMock()
        mock_approval_tbl.select.return_value.eq.return_value.eq.return_value.in_.return_value = mock_q_select

        mock_msg_tbl = MagicMock()
        mock_msg_tbl.select.return_value.eq.return_value.in_.return_value = mock_msg_select
        mock_msg_tbl.select.return_value.eq.return_value.in_.return_value.order.return_value = mock_msg_select

        def table_router(table_name):
            if table_name == "approval_queue":
                return mock_approval_tbl
            elif table_name == "messages":
                return mock_msg_tbl
            return MagicMock()

        mock_supabase2.table.side_effect = table_router

        res2 = sync_inbox_messages(mock_supabase2, self.workspace_id, self.account_id, [msg1])
        self.assertEqual(res2["queued"], 0)
        # Verify approval_queue.insert was NEVER called on mock_approval_tbl
        mock_approval_tbl.insert.assert_not_called()

    # =========================================================================
    # Test 4: AI Reply Approval skips when pending exists in executor
    # =========================================================================
    def test_executor_ai_reply_approval_skips_when_pending(self):
        """
        Layer 1 & 2 Paranoia: Verifies executor returns {"status": "awaiting_approval"}
        without re-inserting into ai_reply_approvals or sending duplicate email if
        a pending approval already exists for the execution state.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_777",
            "enrollment_id": "enr_888",
            "execution_state_id": "state_999",
            "_skip_limit_check": True,
        }

        # Mock table router
        mock_approvals_tbl = MagicMock()
        mock_approvals_select = MagicMock()
        # Pending approval exists!
        mock_approvals_select.execute.return_value = MagicMock(data=[{"id": "existing_appr_123"}])
        mock_approvals_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value = mock_approvals_select

        mock_messages_tbl = MagicMock()
        # 0 outbound messages in 24h for circuit breaker
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=[], count=0)
        # Inbound message
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "What is the turnaround time for your service?"}]
        )

        mock_workspaces_tbl = MagicMock()
        mock_workspaces_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"ai_reply_confidence_threshold": 0.7}])

        def table_router(table_name):
            if table_name == "ai_reply_approvals":
                return mock_approvals_tbl
            elif table_name == "messages":
                return mock_messages_tbl
            elif table_name == "workspaces":
                return mock_workspaces_tbl
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=[{"content": "Turnaround time is 48 hours.", "similarity": 0.5}]), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_synthesis", return_value={}), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value='{"reply": "Our turnaround time is typically 48 hours.", "confidence": 5, "grounded_in_knowledge": false}'), \
             patch.object(executor, "_get_unified_brain", return_value={}), \
             patch.object(executor, "_send_approval_email") as mock_send_email:

            res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/prospect")

        self.assertEqual(res["status"], "awaiting_approval")
        self.assertEqual(res["message"], "Already queued for review")

        # Verify no duplicate insert into ai_reply_approvals
        mock_approvals_tbl.insert.assert_not_called()
        # Verify no duplicate approval email sent
        mock_send_email.assert_not_called()

    # =========================================================================
    # Test 5: AI Reply Approval inserts when no pending exists
    # =========================================================================
    def test_executor_ai_reply_approval_inserts_when_no_pending_exists(self):
        """
        Layer 0 Paranoia: When no pending approval exists for the execution state,
        it successfully creates the approval record and queues email.
        """
        worker = MagicMock()
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=mock_supabase, workspace_id=self.workspace_id)

        data = {
            "workspace_id": self.workspace_id,
            "lead_id": "lead_777",
            "enrollment_id": "enr_888",
            "execution_state_id": "state_999",
            "_skip_limit_check": True,
        }

        mock_approvals_tbl = MagicMock()
        # No pending approval
        mock_approvals_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        mock_messages_tbl = MagicMock()
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_messages_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"message_text": "What is the turnaround time for your service?"}]
        )

        mock_workspaces_tbl = MagicMock()
        mock_workspaces_tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"ai_reply_confidence_threshold": 0.7}])

        def table_router(table_name):
            if table_name == "ai_reply_approvals":
                return mock_approvals_tbl
            elif table_name == "messages":
                return mock_messages_tbl
            elif table_name == "workspaces":
                return mock_workspaces_tbl
            elif table_name == "campaign_execution_states":
                return MagicMock()
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        with patch("knowledge.backend.services.vector_store.SemanticBrain.retrieve", return_value=[{"content": "Turnaround time is 48 hours.", "similarity": 0.5}]), \
             patch("knowledge.backend.services.knowledge_service.KnowledgeService.get_synthesis", return_value={}), \
             patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value='{"reply": "Our turnaround time is typically 48 hours.", "confidence": 5, "grounded_in_knowledge": false}'), \
             patch.object(executor, "_get_unified_brain", return_value={}), \
             patch.object(executor, "_send_approval_email") as mock_send_email:

            res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/prospect")

        self.assertEqual(res["status"], "awaiting_approval")
        self.assertIn("Queued for review", res["message"])
        # Verify insert into ai_reply_approvals was called
        mock_approvals_tbl.insert.assert_called_once()
        inserted_payload = mock_approvals_tbl.insert.call_args[0][0]
        self.assertEqual(inserted_payload["execution_state_id"], "state_999")
        self.assertEqual(inserted_payload["lead_id"], "lead_777")
        # Verify approval email was sent
        mock_send_email.assert_called_once()

    # =========================================================================
    # Test 6: Preserves explicit message ID and reuses existing DB message ID
    # =========================================================================
    def test_sync_inbox_messages_handles_existing_records_and_custom_id(self):
        """
        Layer 0 & 1 Paranoia: Explicit message IDs are preserved, and existing records
        in DB retain their original ID instead of generating new UUIDs.
        """
        custom_id = "custom-msg-id-12345"
        msg_explicit = {
            "id": custom_id,
            "sender_name": "Dave Developer",
            "message_text": "Custom ID message",
            "direction": "inbound",
        }
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        sync_inbox_messages(mock_supabase, self.workspace_id, self.account_id, [msg_explicit])
        records = mock_supabase.table("messages").upsert.call_args[0][0]
        self.assertEqual(records[0]["id"], custom_id)

        # Existing record in DB
        existing_db_id = "existing-db-id-67890"
        msg_existing = {
            "sender_name": "Dave Developer",
            "message_text": "Already saved message",
            "direction": "inbound",
            "thread_url": "https://linkedin.com/thread/1",
        }
        mock_supabase_existing = MagicMock()
        mock_supabase_existing.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[{
            "id": existing_db_id,
            "sender_name": "Dave Developer",
            "message_text": "Already saved message",
            "direction": "inbound",
            "thread_url": "https://linkedin.com/thread/1",
        }])

        res = sync_inbox_messages(mock_supabase_existing, self.workspace_id, self.account_id, [msg_existing])
        self.assertEqual(res["updated"], 1)
        records_existing = mock_supabase_existing.table("messages").upsert.call_args[0][0]
        self.assertEqual(records_existing[0]["id"], existing_db_id)

    # =========================================================================
    # Test 7: Handles None or missing thread_url without crashing
    # =========================================================================
    def test_sync_inbox_messages_handles_missing_or_none_thread_url(self):
        """
        Layer 2 Paranoia: Messages with missing, None, or empty thread_url
        must produce valid deterministic UUIDs and not crash on string interpolation.
        """
        msg_none = {
            "sender_name": "Eve Engineer",
            "message_text": "No thread url provided",
            "direction": "inbound",
            "thread_url": None,
        }
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        sync_inbox_messages(mock_supabase, self.workspace_id, self.account_id, [msg_none])
        records = mock_supabase.table("messages").upsert.call_args[0][0]
        self.assertTrue(bool(records[0]["id"]))
        self.assertNotIn("thread_url", records[0])  # None thread_url shouldn't be added or should be clean


if __name__ == "__main__":
    unittest.main()
