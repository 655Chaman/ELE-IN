import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from inbox.backend.routers.inbox import get_inbox_threads, get_thread_messages, get_threads_with_intent
from inbox.backend.schemas.inbox import AISuggestRequest
from knowledge.backend.routers.ai_routes import ai_suggest_reply


class TestPhaseCInboxConsolidationAndCopilot(unittest.IsolatedAsyncioTestCase):
    """
    Phase C Verification:
    - Layer 0: Multi-sender thread message consolidation and transparent account attribution.
    - Layer 1: Resilience against fragmented sender IDs, ensuring all prospect hops unify under one lead history.
    - Layer 2: Automatic objection battlecard and competitive intel injection into AI Copilot drafts.
    """

    def setUp(self):
        self.workspace_id = "ws-phase-c"
        self.supabase = MagicMock()

    def test_multi_sender_messages_consolidated_in_thread_history(self):
        """Layer 0 & 1: Verifies get_thread_messages consolidates multi-sender messages by lead_id and attaches sender account names."""
        lead_id = "lead-prospect-1"
        sender_name = "Alex Prospect"
        
        # Prospect interacted with Account 1 (Sarah) and Account 2 (John)
        messages_db = [
            {
                "id": "msg-1",
                "message_text": "Hey Alex, saw your work on deliverability!",
                "direction": "outbound",
                "created_at": "2026-06-01T10:00:00Z",
                "lead_id": lead_id,
                "account_id": "acc-sarah",
                "sender_name": sender_name
            },
            {
                "id": "msg-2",
                "message_text": "Thanks Sarah! What does your team do?",
                "direction": "inbound",
                "created_at": "2026-06-01T11:00:00Z",
                "lead_id": lead_id,
                "account_id": "acc-sarah",
                "sender_name": sender_name
            },
            {
                "id": "msg-3",
                "message_text": "Following up with our technical docs — John here from the same team.",
                "direction": "outbound",
                "created_at": "2026-06-02T14:00:00Z",
                "lead_id": lead_id,
                "account_id": "acc-john",
                "sender_name": sender_name
            }
        ]

        accounts_db = [
            {"id": "acc-sarah", "name": "Sarah Miller"},
            {"id": "acc-john", "name": "John Doe"}
        ]

        def mock_table(table_name):
            m = MagicMock()
            if table_name == "messages":
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=messages_db)
            elif table_name == "accounts":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=accounts_db)
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=accounts_db)
            elif table_name == "action_log":
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return m

        self.supabase.table.side_effect = mock_table

        res = get_thread_messages(
            sender_name=sender_name,
            lead_id=lead_id,
            supabase=self.supabase,
            workspace_id=self.workspace_id
        )

        self.assertEqual(len(res), 3)
        self.assertEqual(res[0]["sender_account_name"], "Sarah Miller")
        self.assertEqual(res[1]["sender_account_name"], "Sarah Miller")
        self.assertEqual(res[2]["sender_account_name"], "John Doe")
        self.assertEqual(res[2]["direction"], "outbound")

    def test_threads_enriched_with_all_account_names(self):
        """Layer 0: Verifies get_inbox_threads attaches all_account_names across multi-sender conversations."""
        messages_db = [
            {
                "sender_name": "Elena Smith",
                "message_text": "Sounds good!",
                "direction": "inbound",
                "created_at": "2026-06-05T12:00:00Z",
                "lead_id": "lead-elena",
                "account_id": "acc-1"
            },
            {
                "sender_name": "Elena Smith",
                "message_text": "Checking back in",
                "direction": "outbound",
                "created_at": "2026-06-04T12:00:00Z",
                "lead_id": "lead-elena",
                "account_id": "acc-2"
            }
        ]

        accounts_db = [
            {"id": "acc-1", "name": "Primary Sender"},
            {"id": "acc-2", "name": "Secondary Sender"}
        ]

        def mock_table(table_name):
            m = MagicMock()
            if table_name == "messages":
                m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=messages_db)
            elif table_name == "accounts":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=accounts_db)
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=accounts_db)
            elif table_name == "leads":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "action_log":
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return m

        self.supabase.table.side_effect = mock_table

        threads = get_inbox_threads(limit=10, offset=0, supabase=self.supabase, workspace_id=self.workspace_id)
        self.assertEqual(len(threads), 1)
        elena_thread = threads[0]
        self.assertEqual(elena_thread["sender_name"], "Elena Smith")
        self.assertIn("Primary Sender", elena_thread["all_account_names"])
        self.assertIn("Secondary Sender", elena_thread["all_account_names"])

    async def test_ai_suggest_route_injects_objection_and_competitor_battlecard(self):
        """Layer 2: ai_suggest_reply route synthesizes competitor kill points into objection playbook when competitor detected."""
        req = AISuggestRequest(
            sender_name="David Miller",
            thread_messages=[
                {"direction": "inbound", "message_text": "We currently use Apollo.io and are locked in."}
            ],
            intent="objection",
            objection_type="COMPETITOR",
            detected_competitor="Apollo.io",
            is_simulation=True
        )

        with patch("knowledge.backend.services.elein_ai_service.stream_reply_draft") as mock_stream:
            async def mock_gen(*args, **kwargs):
                yield "Draft response countering Apollo"

            mock_stream.side_effect = mock_gen

            response = await ai_suggest_reply(req, workspace_id="ws-test")
            # Consume the generator to trigger stream_reply_draft
            tokens = [t async for t in response.body_iterator]
            
            # Verify stream_reply_draft was called with objection playbook containing Apollo intel
            mock_stream.assert_called_once()
            kwargs = mock_stream.call_args[1]
            playbook = kwargs.get("objection_playbook", "")
            self.assertIn("OBJECTION TYPE: COMPETITOR", playbook)
            self.assertIn("Apollo.io", playbook)
            self.assertIn("KILL POINTS", playbook)


if __name__ == "__main__":
    unittest.main()
