import pytest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.account_id = "acc-conn-test"
    return worker

@pytest.fixture
def mock_supabase():
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value = MagicMock(data=True)
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"is_warmup": False}])
    return sb

@pytest.fixture
def executor(mock_worker, mock_supabase):
    return EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id="ws-test")


class TestConnectionAndControlNodes:

    # ── 1. CONNECTION REQUEST ─────────────────────────────────────────────────
    def test_connection_request_no_note(self, executor, mock_worker):
        mock_worker.send_connection_request.return_value = {"status": "success"}
        res = executor.execute("connection_request", {"note_strategy": "No note"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.SENT.value
        mock_worker.send_connection_request.assert_called_once_with("https://linkedin.com/in/alex", None, None)

    def test_connection_request_fixed_note_interpolation_and_clamp(self, executor, mock_worker):
        mock_worker.send_connection_request.return_value = {"status": "success"}
        long_tail = "x" * 350
        data = {
            "note_strategy": "Fixed note",
            "note": "Hi {{first_name}}! " + long_tail,
            "first_name": "Sarah"
        }
        res = executor.execute("connection_request", data, "https://linkedin.com/in/sarah")
        assert res["status"] == "success"
        assert res["branch"] == Branch.SENT.value
        
        # Verify clamped note <= 300 chars
        sent_note = mock_worker.send_connection_request.call_args[0][1]
        assert len(sent_note) <= 300
        assert sent_note.startswith("Hi Sarah! ")
        assert sent_note.endswith("...")

    def test_connection_request_already_connected(self, executor, mock_worker):
        mock_worker.send_connection_request.return_value = {
            "status": "error",
            "error": "Connect button not found; user is already connected"
        }
        res = executor.execute("connection_request", {"note_strategy": "No note"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.ALREADY_CONNECTED.value

    def test_connection_request_already_pending(self, executor, mock_worker):
        mock_worker.send_connection_request.return_value = {
            "status": "error",
            "error": "Pending invitation already sent"
        }
        res = executor.execute("connection_request", {"note_strategy": "No note"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.SENT.value

    # ── 2. WITHDRAW REQUEST ───────────────────────────────────────────────────
    def test_withdraw_request_success(self, executor, mock_worker):
        mock_worker.withdraw_connection_request.return_value = {"status": "success"}
        res = executor.execute("withdraw_request", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value

    def test_withdraw_request_fallback_when_already_withdrawn(self, executor, mock_worker):
        mock_worker.withdraw_connection_request.return_value = {
            "status": "error",
            "error": "No pending invitation found to withdraw"
        }
        res = executor.execute("withdraw_request", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True

    # ── 3. REMOVE CONNECTION ──────────────────────────────────────────────────
    def test_remove_connection_success(self, executor, mock_worker):
        mock_worker.remove_connection.return_value = {"status": "success"}
        res = executor.execute("remove_connection", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value

    def test_remove_connection_fallback_when_not_connected(self, executor, mock_worker):
        mock_worker.remove_connection.return_value = {
            "status": "error",
            "error": "Remove button not found; lead is not connected"
        }
        res = executor.execute("remove_connection", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True

    # ── 4. A/B SPLIT ──────────────────────────────────────────────────────────
    def test_ab_split_deterministic(self, executor):
        data = {"_lead_id": "lead-42", "_current_node_id": "ab_1"}
        res1 = executor.execute("ab_split", data, "https://linkedin.com/in/alex")
        res2 = executor.execute("ab_split", data, "https://linkedin.com/in/alex")
        assert res1["status"] == "success"
        assert res1["branch"] in ["Path A", "Path B"]
        assert res1["branch"] == res2["branch"]

    # ── 5. WEIGHTED SPLIT ─────────────────────────────────────────────────────
    def test_weighted_split_100_percent_path_a(self, executor):
        data = {"_lead_id": "lead-99", "path_a_pct": 100}
        res = executor.execute("weighted_split", data, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Path A"

    def test_weighted_split_0_percent_path_a(self, executor):
        data = {"_lead_id": "lead-99", "path_a_pct": 0}
        res = executor.execute("weighted_split", data, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Path B"

    # ── 6. DAILY LIMIT CHECK ──────────────────────────────────────────────────
    def test_daily_limit_check_under_limit(self, executor, mock_supabase):
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=True)
        res = executor.execute("daily_limit_check", {"action_type": "message"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Under limit"

    def test_daily_limit_check_limit_reached(self, executor, mock_supabase):
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=False)
        res = executor.execute("daily_limit_check", {"action_type": "message"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Limit reached"

    # ── 7. BLACKLIST CHECK ────────────────────────────────────────────────────
    def test_blacklist_check_not_blacklisted(self, executor, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        res = executor.execute("blacklist_check", {"email": "clean@acme.com"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Not blacklisted"

    def test_blacklist_check_blacklisted(self, executor, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "supp_1"}])
        res = executor.execute("blacklist_check", {"email": "blocked@spam.com"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Blacklisted → skip"

    # ── 8. BLANK CONNECTION REQUEST (connection_no_note) ───────────────────────
    def test_connection_no_note_success(self, executor, mock_worker):
        mock_worker.send_connection_request.return_value = {"status": "success"}
        res = executor.execute("connection_no_note", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.SENT.value
        mock_worker.send_connection_request.assert_called_once_with("https://linkedin.com/in/alex", None, None)

    def test_connection_no_note_already_connected(self, executor, mock_worker):
        mock_worker.send_connection_request.return_value = {
            "status": "error",
            "error": "Connect button not found; user is already connected"
        }
        res = executor.execute("connection_no_note", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.ALREADY_CONNECTED.value

    # ── 9. WAIT FOR REPLY (wait_for_reply) ────────────────────────────────────
    def test_wait_for_reply_received(self, executor, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "msg-1", "created_at": "2026-10-10T05:00:00Z"}]
        )
        data = {
            "_lead_id": "lead-1",
            "_enrollment_created_at": "2026-10-09T00:00:00Z"
        }
        res = executor.execute("wait_for_reply", data, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Replied"

    def test_wait_for_reply_timed_out(self, executor, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        data = {
            "_lead_id": "lead-1",
            "_enrollment_created_at": "2026-10-01T00:00:00Z",
            "variables": {"wait_reply_timed_out": True}
        }
        res = executor.execute("wait_for_reply", data, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == "Timeout"

    # ── 10. INBOUND GHOSTWRITING (inbound_ghostwriting) ───────────────────────
    @patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=["nvapi-mock-key"])
    @patch("knowledge.backend.services.elein_ai_service.generate_inbound_comment", return_value="Great post on AI systems!")
    def test_inbound_ghostwriting_success(self, mock_gen, mock_keys, executor, mock_worker):
        mock_worker.scrape_recent_post_text.return_value = {"status": "success", "post_text": "Excited to announce our new product launch!"}
        mock_worker.comment_on_post.return_value = {"status": "success"}
        mock_worker.like_top_3_posts.return_value = {"status": "success"}

        res = executor.execute("inbound_ghostwriting", {"_workspace_id": "ws-test"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["comment_posted"] == "Great post on AI systems!"
        mock_worker.comment_on_post.assert_called_once_with("https://linkedin.com/in/alex", "Great post on AI systems!")

    def test_inbound_ghostwriting_skipped_when_no_posts(self, executor, mock_worker):
        mock_worker.scrape_recent_post_text.return_value = {"status": "error", "error": "No posts found"}
        res = executor.execute("inbound_ghostwriting", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "skipped"
        assert "No recent posts found" in res["reason"]

    # ── 11. LIFECYCLE STATUS NODES ───────────────────────────────────────────
    def test_mark_lifecycle_nodes(self, executor, mock_supabase):
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        res_interested = executor.execute("mark_interested", {"_lead_id": "lead-1"}, "https://linkedin.com/in/alex")
        assert res_interested["status"] == "success"
        assert res_interested["variables"]["lead_status"] == "Interested"

        res_sql = executor.execute("mark_sql", {"_lead_id": "lead-1"}, "https://linkedin.com/in/alex")
        assert res_sql["status"] == "success"
        assert res_sql["variables"]["lead_status"] == "SQL"

        res_converted = executor.execute("mark_converted", {"_lead_id": "lead-1"}, "https://linkedin.com/in/alex")
        assert res_converted["status"] == "success"
        assert res_converted["variables"]["lead_status"] == "Converted"

    # ── 12. SEND MESSAGE WITH DOC ─────────────────────────────────────────────
    def test_send_message_with_doc(self, executor, mock_worker):
        mock_worker.send_message_with_attachment.return_value = {"status": "success"}
        data = {
            "body": "Hi {{first_name}}, check out our doc!",
            "first_name": "Jordan",
            "doc_url": "https://elein.ai/whitepaper.pdf"
        }
        res = executor.execute("send_message_with_doc", data, "https://linkedin.com/in/jordan")
        assert res["status"] == "success"
        mock_worker.send_message_with_attachment.assert_called_once()

