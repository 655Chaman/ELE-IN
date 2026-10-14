import pytest
import json
from unittest.mock import MagicMock
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.account_id = "acc-lifecycle-test"
    return worker

@pytest.fixture
def mock_supabase():
    sb = MagicMock()
    # Mock RPC for daily action limit
    sb.rpc.return_value.execute.return_value = MagicMock(data=True)

    # Dedicated table mocking to avoid cross-query contamination
    def mock_table(table_name):
        tbl = MagicMock()
        if table_name == "accounts":
            tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"is_warmup": False}])
        elif table_name == "messages":
            # Default empty messages
            tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "leads":
            tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "lead-1"}])
            tbl.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "lead-1"}])
        elif table_name == "campaign_enrollments":
            tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "enr-1"}])
        elif table_name == "suppression_list":
            tbl.upsert.return_value.execute.return_value = MagicMock(data=[{"value": "opted_out"}])
            tbl.insert.return_value.execute.return_value = MagicMock(data=[{"value": "opted_out"}])
        return tbl

    sb.table.side_effect = mock_table
    return sb

@pytest.fixture
def executor(mock_worker, mock_supabase):
    return EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id="ws-test")


class TestLifecycleAndConversionNodes:

    # ── 1. UPDATE LEAD STATUS ──────────────────────────────────────────────────
    def test_update_lead_status_interested(self, executor, mock_supabase):
        data = {
            "status": "Interested",
            "_lead_id": "lead-123",
            "tag": "warm_lead"
        }
        res = executor.execute("update_lead_status", data, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["terminal"] is False
        assert res["variables"]["lead_status"] == "Interested"
        assert res["variables"]["lifecycle_stage"] == "Interested"
        mock_supabase.table.assert_any_call("leads")

    def test_update_lead_status_by_linkedin_url(self, executor, mock_supabase):
        data = {
            "status": "SQL",
            "workspace_id": "ws-custom"
        }
        res = executor.execute("update_lead_status", data, "https://linkedin.com/in/sarah")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["variables"]["lead_status"] == "SQL"

    # ── 2. MARK SHORTCUT NODES (MQL, SQL, INTERESTED) ──────────────────────────
    def test_mark_interested_node(self, executor, mock_supabase):
        res = executor.execute("mark_interested", {"_lead_id": "lead-456"}, "https://linkedin.com/in/bob")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["variables"]["lead_status"] == "Interested"

    def test_mark_mql_node(self, executor, mock_supabase):
        res = executor.execute("mark_mql", {"_lead_id": "lead-789"}, "https://linkedin.com/in/clara")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["variables"]["lead_status"] == "MQL"

    def test_mark_sql_node(self, executor, mock_supabase):
        res = executor.execute("mark_sql", {"_lead_id": "lead-101"}, "https://linkedin.com/in/david")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["variables"]["lead_status"] == "SQL"

    # ── 3. TERMINAL CONVERSION & DISQUALIFICATION ─────────────────────────────
    def test_mark_converted_terminal_state(self, executor, mock_supabase):
        data = {
            "_lead_id": "lead-conv-1",
            "_enrollment_id": "enr-conv-1"
        }
        res = executor.execute("mark_converted", data, "https://linkedin.com/in/winner")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["terminal"] is True
        assert res["variables"]["lead_status"] == "Converted"
        mock_supabase.table.assert_any_call("campaign_enrollments")

    def test_mark_not_interested_terminal_state(self, executor, mock_supabase):
        data = {
            "_lead_id": "lead-ni-1",
            "_enrollment_id": "enr-ni-1",
            "reason": "Not a fit"
        }
        res = executor.execute("mark_not_interested", data, "https://linkedin.com/in/declined")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["terminal"] is True
        assert res["variables"]["lead_status"] == "Not Interested"
        mock_supabase.table.assert_any_call("campaign_enrollments")

    # ── 4. GDPR / CAN-SPAM SUPPRESSION LIST ENFORCEMENT ───────────────────────
    def test_mark_opted_out_gdpr_compliance(self, executor, mock_supabase):
        data = {
            "_lead_id": "lead-gdpr-1",
            "_enrollment_id": "enr-gdpr-1",
            "email": "optout@targetcorp.com",
            "workspace_id": "ws-compliance"
        }
        res = executor.execute("mark_opted_out", data, "https://linkedin.com/in/privacy-first")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["terminal"] is True
        assert res["variables"]["lead_status"] == "Opted Out (GDPR)"
        mock_supabase.table.assert_any_call("suppression_list")
        mock_supabase.table.assert_any_call("campaign_enrollments")

    # ── 5. INTRO CALL INVITE ──────────────────────────────────────────────────
    def test_send_intro_call_invite(self, executor, mock_worker):
        mock_worker.send_message.return_value = {"status": "success"}
        data = {
            "subject": "Platform Architecture Demo",
            "duration_minutes": 30,
            "body": "Hey Alex, would love to show you the engine."
        }
        res = executor.execute("send_intro_call_invite", data, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.SENT.value

        # Verify worker received duration and subject formatted into body
        sent_body = mock_worker.send_message.call_args[0][1]
        assert "[Platform Architecture Demo (30 mins)]" in sent_body
        assert "Hey Alex, would love to show you the engine." in sent_body

    # ── 6. WAIT FOR REPLY ─────────────────────────────────────────────────────
    def test_wait_for_reply_inbound_received(self, executor, mock_supabase):
        # Configure messages mock to return inbound reply
        msg_tbl = MagicMock()
        exec_mock = MagicMock(data=[{"id": "msg-1", "created_at": "2026-10-10T10:00:00Z"}])
        msg_tbl.select.return_value.eq.return_value.eq.return_value.gt.return_value.order.return_value.limit.return_value.execute.return_value = exec_mock
        msg_tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = exec_mock

        original_table = mock_supabase.table.side_effect
        mock_supabase.table.side_effect = lambda t: msg_tbl if t == "messages" else original_table(t)

        data = {
            "_lead_id": "lead-replied-1",
            "_enrollment_created_at": "2026-10-09T00:00:00Z"
        }
        res = executor.execute("wait_for_reply", data, "https://linkedin.com/in/chatter")
        assert res["status"] == "success"
        assert res["branch"] == "Replied"

    def test_wait_for_reply_timeout(self, executor, mock_supabase):
        # No reply received, but timeout flag is set in variables
        data = {
            "_lead_id": "lead-quiet-1",
            "variables": {"wait_reply_timed_out": True}
        }
        res = executor.execute("wait_for_reply", data, "https://linkedin.com/in/quiet")
        assert res["status"] == "success"
        assert res["branch"] == "Timeout"

    def test_wait_for_reply_waiting(self, executor, mock_supabase):
        # No reply, no timeout -> remains in waiting state
        data = {
            "_lead_id": "lead-pending-1",
            "variables": {}
        }
        res = executor.execute("wait_for_reply", data, "https://linkedin.com/in/pending")
        assert res["status"] == "waiting_for_reply"

    # ── 7. RETRY STEP ─────────────────────────────────────────────────────────
    def test_retry_step_first_attempt(self, executor):
        data = {
            "max_retries": 3,
            "_current_node_id": "node-retry-1",
            "variables": {}
        }
        res = executor.execute("retry_step", data, "https://linkedin.com/in/flaky")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["current_retry"] == 1
        assert res["max_retries"] == 3
        assert res["retries_exceeded"] is False
        assert res["variables"]["retry_count_node-retry-1"] == 1

    def test_retry_step_exhausted(self, executor):
        data = {
            "max_retries": 2,
            "_current_node_id": "node-retry-2",
            "variables": {"retry_count_node-retry-2": 2}
        }
        res = executor.execute("retry_step", data, "https://linkedin.com/in/flaky")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["current_retry"] == 3
        assert res["retries_exceeded"] is True
        assert "Max retries reached" in res["message"]

    def test_retry_step_invalid_inputs_resilient(self, executor):
        data = {
            "max_retries": "unlimited", # Invalid input
            "_current_node_id": "node-retry-3",
            "variables": "not-a-dict"
        }
        res = executor.execute("retry_step", data, "https://linkedin.com/in/flaky")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["max_retries"] == 3 # Safe default fallback
