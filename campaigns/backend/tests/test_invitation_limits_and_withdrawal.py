"""
Step 15 — LinkedIn Invitation Withdrawal & Pending Connect Queue Overflow Guard
Three-Layer Paranoia Framework Tests
"""
import unittest
import contextlib
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from integrations.backend.services.linkedin_worker import (
    LinkedInWorker,
    LinkedInActionOutcomeUnknown,
)


class TestExecutorConnectionSpecialStatusPassThrough(unittest.TestCase):
    """
    Layer 1 Environmental Failures:
    Ensures executor does not coerce special worker statuses (rate_limited,
    security_challenge, session_expired, pool_exhausted) into generic errors.
    """

    def setUp(self):
        self.mock_worker = MagicMock()
        self.mock_worker.account_id = "acc-test"
        self.mock_supabase = MagicMock()
        self.mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=True)
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"is_warmup": False}]
        )
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.mock_worker,
            supabase=self.mock_supabase,
            workspace_id="ws-test",
        )

    def test_connection_request_passes_rate_limited(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "rate_limited",
            "error": "Weekly invitation limit reached",
            "reason": "weekly_limit_reached",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "Fixed note", "note": "Hi there"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "rate_limited")
        self.assertEqual(res["reason"], "weekly_limit_reached")
        self.assertEqual(res["error"], "Weekly invitation limit reached")

    def test_connection_request_passes_security_challenge(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "security_challenge",
            "error": "CAPTCHA triggered",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "Fixed note", "note": "Hi there"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "security_challenge")

    def test_connection_request_passes_session_expired(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "session_expired",
            "error": "Cookies expired",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "Fixed note", "note": "Hi there"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "session_expired")

    def test_connection_request_passes_pool_exhausted(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "pool_exhausted",
            "error": "No browser slots",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "Fixed note", "note": "Hi there"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "pool_exhausted")

    def test_connection_no_note_passes_rate_limited_and_caps(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "rate_limited",
            "error": "Maximum pending invitations reached",
            "reason": "pending_invitation_limit",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "No note"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "rate_limited")
        self.assertEqual(res["reason"], "pending_invitation_limit")

    def test_connection_no_note_passes_security_challenge(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "security_challenge"
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "No note"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "security_challenge")

    @patch("knowledge.backend.services.elein_ai_service.write_connection_note")
    def test_connection_ai_note_passes_rate_limited(self, mock_ai):
        mock_ai.return_value = "AI personalized note"
        self.mock_worker.send_connection_request.return_value = {
            "status": "rate_limited",
            "error": "Weekly invitation limit reached",
            "reason": "weekly_limit_reached",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "AI-generated note"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "rate_limited")
        self.assertEqual(res["reason"], "weekly_limit_reached")

    @patch("knowledge.backend.services.elein_ai_service.write_connection_note")
    def test_connection_ai_note_passes_security_challenge(self, mock_ai):
        mock_ai.return_value = "AI personalized note"
        self.mock_worker.send_connection_request.return_value = {
            "status": "security_challenge"
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "AI-generated note"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "security_challenge")

    def test_connection_request_handles_already_pending_worker_success(self):
        # When worker detects pending button and returns success with note
        self.mock_worker.send_connection_request.return_value = {
            "status": "success",
            "action": "connection_request",
            "note": "Pending invitation already sent",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "No note"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.SENT.value)

    def test_connection_request_handles_already_connected(self):
        self.mock_worker.send_connection_request.return_value = {
            "status": "error",
            "error": "Connect button not found; already 1st degree connection",
        }
        res = self.executor.execute(
            "connection_request",
            {"note_strategy": "No note"},
            "https://linkedin.com/in/alex",
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.ALREADY_CONNECTED.value)


class TestWorkerModalAndStateDetection(unittest.TestCase):
    """
    Layer 0 & Layer 1:
    Modal detection for 'Pending' state, Weekly Limit, Pending Invitations Cap,
    and Email Required dialogs inside LinkedInWorker.send_connection_request.
    """

    def setUp(self):
        self.worker = LinkedInWorker(
            cookies_json='[{"name": "li_at", "value": "test_token"}]',
            account_id="acc_test",
        )
        self.mock_page = MagicMock()
        self.worker._check_for_challenge = MagicMock()
        self.worker._human_delay = MagicMock()
        self.worker._safe_click = MagicMock(return_value=False)

    @contextlib.contextmanager
    def _mock_context(self):
        yield self.mock_page

    def test_profile_already_shows_pending_button(self):
        # Configure pending button visible
        mock_pending_btn = MagicMock()
        mock_pending_btn.is_visible.return_value = True

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_filter = MagicMock()
                mock_filter.first = mock_pending_btn
                mock_loc.filter.return_value = mock_filter
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.send_connection_request("https://linkedin.com/in/alex")

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["action"], "connection_request")
        self.assertEqual(res["note"], "Pending invitation already sent")

    def test_weekly_limit_modal_detected(self):
        # Configure pending button not visible, but weekly limit dialog visible
        mock_pending = MagicMock()
        mock_pending.is_visible.return_value = False

        mock_dialog = MagicMock()
        mock_dialog.is_visible.return_value = True

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_filter = MagicMock()
                mock_filter.first = mock_pending
                mock_loc.filter.return_value = mock_filter
            elif selector == "div[role='dialog']":
                mock_filter = MagicMock()
                mock_filter.first = mock_dialog
                mock_loc.filter.return_value = mock_filter
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.send_connection_request("https://linkedin.com/in/alex")

        self.assertEqual(res["status"], "rate_limited")
        self.assertEqual(res["reason"], "weekly_limit_reached")
        self.assertIn("Weekly invitation limit reached", res["error"])

    def test_pending_invitation_cap_modal_detected(self):
        mock_pending = MagicMock()
        mock_pending.is_visible.return_value = False

        mock_cap_dialog = MagicMock()
        mock_cap_dialog.is_visible.return_value = True

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_filter = MagicMock()
                mock_filter.first = mock_pending
                mock_loc.filter.return_value = mock_filter
            elif selector == "div[role='dialog']":
                def filter_func(has_text=None):
                    m = MagicMock()
                    if has_text in ("pending invitations", "maximum number of invitations", "too many pending"):
                        m.first = mock_cap_dialog
                    else:
                        m_invis = MagicMock()
                        m_invis.is_visible.return_value = False
                        m.first = m_invis
                    return m
                mock_loc.filter.side_effect = filter_func
            elif selector == "input[name='email']":
                mock_loc.first.is_visible.return_value = False
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.send_connection_request("https://linkedin.com/in/alex")

        self.assertEqual(res["status"], "rate_limited")
        self.assertEqual(res["reason"], "pending_invitation_limit")
        self.assertIn("Maximum pending invitations reached", res["error"])

    def test_email_required_input_detected(self):
        mock_pending = MagicMock()
        mock_pending.is_visible.return_value = False

        mock_email_input = MagicMock()
        mock_email_input.is_visible.return_value = True

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_filter = MagicMock()
                mock_filter.first = mock_pending
                mock_loc.filter.return_value = mock_filter
            elif selector == "div[role='dialog']":
                m = MagicMock()
                m_invis = MagicMock()
                m_invis.is_visible.return_value = False
                m.first = m_invis
                mock_loc.filter.return_value = m
            elif selector == "input[name='email']":
                mock_loc.first = mock_email_input
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.send_connection_request("https://linkedin.com/in/alex")

        self.assertEqual(res["status"], "error")
        self.assertEqual(res["reason"], "email_required")
        self.assertIn("Lead requires email to connect", res["error"])

    def test_email_required_dialog_text_detected(self):
        mock_pending = MagicMock()
        mock_pending.is_visible.return_value = False

        mock_email_dialog = MagicMock()
        mock_email_dialog.is_visible.return_value = True

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_filter = MagicMock()
                mock_filter.first = mock_pending
                mock_loc.filter.return_value = mock_filter
            elif selector == "div[role='dialog']":
                def filter_func(has_text=None):
                    m = MagicMock()
                    if has_text in ("enter their email", "requires an email"):
                        m.first = mock_email_dialog
                    else:
                        m_invis = MagicMock()
                        m_invis.is_visible.return_value = False
                        m.first = m_invis
                    return m
                mock_loc.filter.side_effect = filter_func
            elif selector == "input[name='email']":
                mock_loc.first.is_visible.return_value = False
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.send_connection_request("https://linkedin.com/in/alex")

        self.assertEqual(res["status"], "error")
        self.assertEqual(res["reason"], "email_required")
        self.assertIn("Lead requires email to connect", res["error"])


class TestStaleInvitationWithdrawal(unittest.TestCase):
    """
    Layer 1 & Layer 2:
    Bulk withdrawal of oldest sent unaccepted connection requests.
    """

    def setUp(self):
        self.worker = LinkedInWorker(
            cookies_json='[{"name": "li_at", "value": "test_token"}]',
            account_id="acc_test",
        )
        self.mock_page = MagicMock()
        self.worker._check_for_challenge = MagicMock()
        self.worker._human_delay = MagicMock()

    @contextlib.contextmanager
    def _mock_context(self):
        yield self.mock_page

    def test_withdraw_no_pending_invitations(self):
        mock_buttons = MagicMock()
        mock_buttons.count.return_value = 0

        mock_loc = MagicMock()
        mock_loc.filter.return_value = mock_buttons
        self.mock_page.locator.return_value = mock_loc

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.withdraw_oldest_pending_invitations(max_to_withdraw=15)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["withdrawn_count"], 0)
        self.assertEqual(res["message"], "No pending invitations found")

    def test_withdraw_oldest_success_up_to_max(self):
        mock_withdraw_btn = MagicMock()
        mock_withdraw_btn.is_visible.return_value = True

        mock_confirm_btn = MagicMock()
        mock_confirm_btn.is_visible.return_value = True

        mock_buttons = MagicMock()
        mock_buttons.count.return_value = 5
        mock_buttons.nth.return_value = mock_withdraw_btn

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_loc.filter.return_value = mock_buttons
            elif selector == "div[role='dialog'] button":
                mock_filter = MagicMock()
                mock_filter.first = mock_confirm_btn
                mock_loc.filter.return_value = mock_filter
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.withdraw_oldest_pending_invitations(max_to_withdraw=3)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["withdrawn_count"], 3)
        self.assertEqual(mock_confirm_btn.click.call_count, 3)

    def test_withdraw_stops_gracefully_on_item_failure(self):
        mock_withdraw_btn = MagicMock()
        mock_withdraw_btn.is_visible.return_value = True

        # First confirm succeeds, second raises error
        mock_confirm_btn = MagicMock()
        mock_confirm_btn.is_visible.side_effect = [True, False, False]

        mock_buttons = MagicMock()
        mock_buttons.count.return_value = 5
        mock_buttons.nth.return_value = mock_withdraw_btn

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_loc.filter.return_value = mock_buttons
            elif selector == "div[role='dialog'] button":
                mock_filter = MagicMock()
                mock_filter.first = mock_confirm_btn
                mock_loc.filter.return_value = mock_filter
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            res = self.worker.withdraw_oldest_pending_invitations(max_to_withdraw=5)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["withdrawn_count"], 1)

    def test_withdraw_reraises_action_outcome_unknown(self):
        mock_withdraw_btn = MagicMock()
        mock_withdraw_btn.is_visible.return_value = True

        mock_confirm_btn = MagicMock()
        mock_confirm_btn.is_visible.return_value = True
        mock_confirm_btn.click.side_effect = LinkedInActionOutcomeUnknown("Network drop during confirm")

        mock_buttons = MagicMock()
        mock_buttons.count.return_value = 2
        mock_buttons.nth.return_value = mock_withdraw_btn

        def locator_side_effect(selector):
            mock_loc = MagicMock()
            if selector == "button":
                mock_loc.filter.return_value = mock_buttons
            elif selector == "div[role='dialog'] button":
                mock_filter = MagicMock()
                mock_filter.first = mock_confirm_btn
                mock_loc.filter.return_value = mock_filter
            return mock_loc

        self.mock_page.locator.side_effect = locator_side_effect

        with patch.object(self.worker, "_get_or_create_context", side_effect=self._mock_context):
            with self.assertRaises(LinkedInActionOutcomeUnknown):
                self.worker.withdraw_oldest_pending_invitations(max_to_withdraw=2)


if __name__ == "__main__":
    unittest.main()
