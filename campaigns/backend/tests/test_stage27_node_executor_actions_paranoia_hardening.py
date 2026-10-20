"""
Stage 27: Campaign Node Execution & Executor Actions Paranoia Hardening Tests
==============================================================================
Rigorously evaluates the Three-Layer Logic Architecture across elein_executor.py:
- Layer 0: Foundational action execution, return normalization, and dispatch.
- Layer 1: Environmental failure analysis (quota release on failure/block/challenge,
           proxy quarantine triggers, custom account daily limits, custom_fields unpacking,
           and deliverability failure branch propagation).
- Layer 2: Human paranoia (Bandit variant C2 safety gate, assert_fully_interpolated,
           open profile arbitrage fallback, meeting invite newline formatting).
"""

import pytest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import (
    EleInNodeExecutor,
    Branch,
    UninterpolatedTemplateError,
    assert_fully_interpolated,
)


class MockQuery:
    def __init__(self, data=None):
        self._data = data if data is not None else []

    def select(self, *args, **kwargs):
        return self

    def insert(self, *args, **kwargs):
        return self

    def update(self, *args, **kwargs):
        return self

    def delete(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        res = MagicMock()
        res.data = self._data
        return res


class MockSupabase:
    def __init__(self):
        self.tables = {}
        self.rpcs = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = MockQuery([])
        return self.tables[name]

    def rpc(self, name, params=None):
        mock_call = MagicMock()
        mock_call.execute.return_value = MagicMock(data=self.rpcs.get(name, True))
        return mock_call


class MockWorker:
    def __init__(self, account_id="acc-123"):
        self.account_id = account_id
        self.workspace_id = "ws-test"
        self.timezone = "UTC"

    def send_message(self, linkedin_url, body):
        return {"status": "success", "message": "sent"}

    def send_connection_request(self, linkedin_url, note=None, fallback=None):
        return {"status": "success", "note": note}

    def send_inmail(self, linkedin_url, subject, body, is_open_profile=False, only_free=False):
        return {"status": "success", "is_free_inmail": is_open_profile}

    def send_voice_note(self, linkedin_url, audio_url, note=None):
        return {"status": "success"}

    def check_open_profile(self, linkedin_url):
        return {"status": "success", "branch": "Open", "open": True, "is_open_profile": True}


class TestStage27NodeExecutorActionsParanoiaHardening:
    """
    Test suite for Stage 27 Executor Hardening under the Three-Layer Paranoia Framework.
    """

    # =========================================================================
    # LAYER 0: Foundational Layer
    # =========================================================================

    def test_layer0_send_message_foundational_success(self):
        """Layer 0: Verifies basic message dispatch standardizes branch to 'Sent' and logs outbound message."""
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        data = {
            "message": "Hey {{first_name}}, loved your work at {{company}}!",
            "lead": {"first_name": "Alice", "company": "Acme Corp"},
            "_lead_id": "lead-1",
            "_skip_limit_check": True,
        }
        res = executor.execute("send_message", data, "https://linkedin.com/in/alice")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.SENT.value
        assert "Alice" in res.get("body_sent", "")

    def test_layer0_connection_request_foundational_success(self):
        """Layer 0: Verifies connection request with fixed note standardizes branch to 'Sent'."""
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        data = {
            "note_strategy": "Fixed note",
            "note": "Hi {{first_name}}, let's connect!",
            "lead": {"first_name": "Bob"},
            "_lead_id": "lead-2",
            "_skip_limit_check": True,
        }
        res = executor.execute("connection_request", data, "https://linkedin.com/in/bob")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.SENT.value
        assert "Bob" in res.get("note", "")

    # =========================================================================
    # LAYER 1: Environmental Failure Analysis
    # =========================================================================

    def test_layer1_quota_released_on_execution_failure(self):
        """
        Layer 1 (Paranoia Failure 1): If an action is pre-consumed but handler returns
        status='error', the consumed daily action limit must be immediately released.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        # Mock try_consume_daily_action RPC returning True
        supabase.rpcs["try_consume_daily_action"] = True

        released = False
        def mock_release(action_type, usage_date=None):
            nonlocal released
            released = True

        executor._release_limit = mock_release
        worker.send_message = MagicMock(return_value={"status": "error", "error": "Playwright dropped connection"})

        data = {
            "message": "Hello!",
            "_lead_id": "lead-fail",
        }
        res = executor.execute("send_message", data, "https://linkedin.com/in/fail")

        assert res.get("status") == "error"
        assert res.get("branch") == Branch.FAILED.value
        assert released is True, "Pre-consumed daily action quota was NOT released upon execution failure!"

    def test_layer1_playwright_security_challenge_interception_and_quota_release(self):
        """
        Layer 1 (Paranoia Failure 2): When Playwright worker returns status='security_challenge',
        handle_send_message must intercept it, return branch='Failed', and release daily action quota.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        supabase.rpcs["try_consume_daily_action"] = True
        worker.send_message = MagicMock(return_value={"status": "security_challenge", "error": "Checkpoint challenge"})

        released = False
        def mock_release(action_type, usage_date=None):
            nonlocal released
            released = True
        executor._release_limit = mock_release

        data = {"message": "Hello!", "_lead_id": "lead-challenge"}
        res = executor.execute("send_message", data, "https://linkedin.com/in/challenge")

        assert res.get("status") == "security_challenge"
        assert res.get("branch") == Branch.FAILED.value
        assert released is True, "Daily quota must be released when account hits security challenge"

    def test_layer1_broadened_security_challenge_exception_handling(self):
        """
        Layer 1 (Paranoia Failure 4): When an exception contains 'captcha', 'checkpoint', or 'pin verification',
        execute() must catch it as security_challenge rather than re-raising as an unhandled error.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        worker.send_message = MagicMock(side_effect=RuntimeError("LinkedIn Checkpoint page active: please complete captcha verification"))

        data = {"message": "Hello!", "_lead_id": "lead-captcha", "_skip_limit_check": True}
        res = executor.execute("send_message", data, "https://linkedin.com/in/captcha")

        assert res.get("status") == "security_challenge"
        assert res.get("branch") == Branch.FAILED.value

    def test_layer1_non_warmup_custom_daily_limits_enforced(self):
        """
        Layer 1 (Paranoia Failure 5): _check_limit must enforce daily_connection_limit even when
        is_warmup is False.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        # Account has custom daily_connection_limit = 10, is_warmup = False
        supabase.tables["accounts"] = MockQuery([{
            "is_warmup": False,
            "daily_connection_limit": 10,
            "daily_message_limit": 50,
        }])
        # Usage already at 10
        supabase.tables["account_daily_action_counts"] = MockQuery([{"count": 10}])

        limit_err, _ = executor._check_limit("connection_request")
        assert limit_err is not None
        assert "Daily account limit reached" in limit_err
        assert "10/10" in limit_err

    def test_layer1_custom_fields_unpacked_in_template_interpolation(self):
        """
        Layer 1 (Paranoia Failure 6): Custom fields stored in lead['custom_fields'] must be
        unpacked into raw_lookup, resolving {{conference}} and {{lead.custom_fields.conference}}.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        data = {
            "lead": {
                "first_name": "Charlie",
                "custom_fields": {"conference": "SaaStr 2026", "booth_number": "404"},
            }
        }
        res1 = executor._interpolate_template("Saw you at {{conference}}!", data)
        assert res1 == "Saw you at SaaStr 2026!"

        res2 = executor._interpolate_template("Visit booth {{lead.custom_fields.booth_number}}", data)
        assert res2 == "Visit booth 404"

    def test_layer1_email_deliverability_skipped_branches_fail_safely(self):
        """
        Layer 1 (Paranoia Failure 7): When send_email skips due to spam trap or disposable provider,
        the result dictionary must include branch='Failed' so orchestrator handles it cleanly.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        # Disposable email
        data = {
            "to_email": "prospect@mailinator.com",
            "subject": "Hello",
            "body": "Hi there",
            "_skip_limit_check": True,
        }
        res = executor.handle_send_email(data, linkedin_url=None)
        assert res.get("status") == "skipped"
        assert res.get("branch") == Branch.FAILED.value
        assert "disposable" in res.get("reason", "").lower() or "disposable" in res.get("error", "").lower()

    def test_layer1_paid_inmail_failure_releases_inmail_quota(self):
        """
        Layer 1 (Paranoia Failure 3): When a paid InMail fails on Playwright worker, the reserved
        'inmail' quota must be released.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        # Mock paid profile
        supabase.tables["leads"] = MockQuery([{"is_open_profile": False}])
        supabase.rpcs["try_consume_daily_action"] = True

        released_action = None
        def mock_release(action_type, usage_date=None):
            nonlocal released_action
            released_action = action_type
        executor._release_limit = mock_release

        worker.send_inmail = MagicMock(return_value={"status": "error", "error": "InMail box blocked"})

        data = {
            "subject": "Quick intro",
            "body": "Hi {{first_name}}, let's talk.",
            "lead": {"first_name": "Dan"},
            "_lead_id": "lead-inmail-fail",
            "only_send_free_inmails": False,
        }
        res = executor.handle_send_inmail(data, "https://linkedin.com/in/dan")
        assert res.get("status") == "error"
        assert res.get("branch") == Branch.FAILED.value
        assert released_action == "inmail", "Paid InMail quota was NOT released on send failure!"

    # =========================================================================
    # LAYER 2: Human Paranoia
    # =========================================================================

    def test_layer2_bandit_variants_checked_by_c2_safety_gate(self):
        """
        Layer 2 (Human Trap 1): If a user configures Bandit variants with unpopulated variables,
        the C2 safety net must inspect bandit_variants and raise requires_approval before sending.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        data = {
            "use_bandit": True,
            "bandit_variants": [
                {"template_text": "Hello {{first_name}}, saw your role at {{company}}."},
                {"template_text": "Hey {{nonexistent_variable_typo}}, check this out!"},
            ],
            "lead": {"first_name": "Eve", "company": "Initech"},
            "_lead_id": "lead-bandit-typo",
            "_skip_limit_check": True,
        }
        res = executor.execute("send_message", data, "https://linkedin.com/in/eve")

        assert res.get("status") == "error"
        assert res.get("requires_approval") is True
        assert res.get("branch") == Branch.FAILED.value
        assert "nonexistent_variable_typo" in res.get("error", "")

    def test_layer2_assert_fully_interpolated_blocks_raw_tags(self):
        """
        Layer 2 (Human Trap 2): assert_fully_interpolated strictly raises UninterpolatedTemplateError
        if any raw {{...}} tags remain in text.
        """
        with pytest.raises(UninterpolatedTemplateError) as exc_info:
            assert_fully_interpolated("Hello {{first_name}}, how are you?", lead_id="123", node_id="node_1")
        assert "unresolved variables" in str(exc_info.value)
        assert "{{first_name}}" in str(exc_info.value)

        # Fully interpolated text passes cleanly
        assert_fully_interpolated("Hello Alice, how are you?", lead_id="123", node_id="node_1")

    def test_layer2_meeting_invite_real_newlines(self):
        """
        Layer 2 (Human Trap 3): handle_send_meeting_invite must format calendly link with real
        newlines instead of literal escaped backslash-n ('\\n\\n').
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        captured_msg = None
        def mock_handle_send_msg(data_copy, url):
            nonlocal captured_msg
            captured_msg = data_copy.get("message")
            return {"status": "success", "branch": Branch.SENT.value}

        executor.handle_send_message = mock_handle_send_msg

        data = {
            "body": "Would love to chat.",
            "calendly_url": "https://calendly.com/elein/demo",
            "_skip_limit_check": True,
        }
        executor.handle_send_meeting_invite(data, "https://linkedin.com/in/frank")
        assert captured_msg is not None
        assert "\\n\\n" not in captured_msg, "Literal backslash-n detected in meeting invite message!"
        assert "\n\nBook a time here: https://calendly.com/elein/demo" in captured_msg

    def test_layer2_open_profile_arbitrage_fallback_to_connection_request(self):
        """
        Layer 2 (Human Trap 4): When only_send_free_inmails is requested and profile is closed,
        the node must automatically divert to free connection request with note truncated to 300 chars,
        marked arbitraged=True, and consuming no paid InMail quotas.
        """
        worker = MockWorker()
        supabase = MockSupabase()
        executor = EleInNodeExecutor(linkedin_worker=worker, supabase=supabase, workspace_id="ws-test")

        # Closed profile
        supabase.tables["leads"] = MockQuery([{"is_open_profile": False}])

        data = {
            "only_send_free_inmails": True,
            "fallback_to_connection_request": True,
            "subject": "Partnership opportunity",
            "body": "Hi {{first_name}}, " + ("A" * 350),  # Long body over 300 chars
            "lead": {"first_name": "Grace"},
            "_lead_id": "lead-grace",
            "_skip_limit_check": True,
        }
        res = executor.handle_send_inmail(data, "https://linkedin.com/in/grace")

        assert res.get("status") == "success"
        assert res.get("branch") == Branch.SENT.value
        assert res.get("arbitraged") is True
        assert res.get("diverted_from_paid_inmail") is True
        # Note should be truncated to 300 characters
        assert len(res.get("note") or "") <= 300
