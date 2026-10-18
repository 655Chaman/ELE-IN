"""
Comprehensive Automated Test Suite: Issue 4 - Open Profile InMail Arbitrage & Free Credit Discovery.

Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (Core InMail sending, open profile checks, tagging, credits_saved)
- Layer 1: Environmental Failure Analysis (Only free inmail policy, credit exhaustion, diversions, worker aborts, DB persistence)
- Layer 2: Human Paranoia & Extreme Edge Cases (Corrupted types, payload clamping, worker absence, concurrent race safety)
"""

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from integrations.backend.services.linkedin_worker import LinkedInWorker
from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads, get_in_memory_leads_for_list


class TestInMailOpenProfileArbitrage(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_arbitrage_test"
        self.supabase = MagicMock()
        self.workspace_id = "ws_arbitrage_101"
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id=self.workspace_id
        )
        self.test_lead_url = "https://www.linkedin.com/in/prospect-open"
        self.worker.send_inmail.return_value = {"status": "success", "action": "send_inmail"}
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Open", "open": True}
        self.worker.send_connection_request.return_value = {"status": "success", "action": "connection_request"}

    # =========================================================================
    # LAYER 0: Foundational Layer (Core Mechanics)
    # =========================================================================

    def test_free_inmail_to_open_profile_success(self):
        """Layer 0: Lead with is_open_profile=True dispatches InMail successfully, tagged with free tier and credits_saved=1."""
        data = {
            "is_open_profile": True,
            "subject": "Collaboration Opportunity",
            "body": "Hi there, would love to connect and share some insights.",
            "first_name": "Jordan"
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("inmail_tier"), "free")
        self.assertEqual(res.get("credits_saved"), 1)
        self.worker.send_inmail.assert_called_once()

    def test_paid_inmail_to_closed_profile_success(self):
        """Layer 0: Lead with is_open_profile=False dispatches paid InMail, tagged with inmail_tier='paid'."""
        data = {
            "is_open_profile": False,
            "subject": "Enterprise Solutions",
            "body": "Hi Taylor, sharing enterprise platform details with you.",
            "first_name": "Taylor"
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        self.assertFalse(res.get("is_free_inmail"))
        self.assertEqual(res.get("inmail_tier"), "paid")
        self.worker.send_inmail.assert_called_once()

    def test_open_profile_check_node(self):
        """Layer 0: Evaluates open_profile_check node and transitions to 'Open' or 'Not open' branch."""
        # Sub-case A: Direct payload fast-path
        data_open = {"is_open_profile": True}
        res_open = self.executor.handle_open_profile_check(data_open, self.test_lead_url)
        self.assertEqual(res_open.get("status"), "success")
        self.assertEqual(res_open.get("branch"), "Open")
        self.assertTrue(res_open.get("open"))

        # Sub-case B: Worker returns Not open
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Not open", "open": False}
        data_closed = {"_lead_id": "lead_closed_1"}
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        res_closed = self.executor.handle_open_profile_check(data_closed, self.test_lead_url)
        self.assertEqual(res_closed.get("status"), "success")
        self.assertEqual(res_closed.get("branch"), "Not open")
        self.assertFalse(res_closed.get("open"))

    def test_open_profile_check_db_cached(self):
        """Layer 0: When database confirms lead is Open Profile, resolves without Playwright worker overhead."""
        data = {"_lead_id": "lead_db_cached_99"}
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead_db_cached_99", "is_open_profile": True}]
        )

        res = self.executor.handle_open_profile_check(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Open")
        self.assertTrue(res.get("open"))
        self.worker.check_open_profile.assert_not_called()

    def test_handle_send_paid_inmail_delegation(self):
        """Layer 0: handle_send_paid_inmail delegates to handle_send_inmail maintaining tier tagging."""
        data = {
            "is_open_profile": False,
            "subject": "Sponsored Message",
            "body": "Discover how our product scales your team.",
            "first_name": "Marcus"
        }
        res = self.executor.handle_send_paid_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        self.assertEqual(res.get("inmail_tier"), "paid")
        self.assertFalse(res.get("is_free_inmail"))

    def test_inmail_variable_interpolation(self):
        """Layer 0: Variables {{first_name}} and {{company}} in subject and body are properly replaced."""
        data = {
            "is_open_profile": True,
            "subject": "Hello {{first_name}} at {{company}}",
            "body": "Hi {{first_name}}, we saw {{company}}'s recent product launch!",
            "variables": {
                "first_name": "Elena",
                "company": "Stripe"
            }
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.worker.send_inmail.assert_called_once()
        args = self.worker.send_inmail.call_args[0]
        self.assertIn("Elena", args[1])
        self.assertIn("Stripe", args[1])
        self.assertIn("Elena", args[2])
        self.assertIn("Stripe", args[2])

    def test_inmail_default_subject_when_omitted(self):
        """Layer 0: When subject is omitted or whitespace, generates 'Connecting with {first_name}'."""
        data = {
            "is_open_profile": True,
            "subject": "   ",
            "body": "Hey Alex, saw your recent post.",
            "first_name": "Alex"
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        args = self.worker.send_inmail.call_args[0]
        self.assertEqual(args[1], "Connecting with Alex")

    # =========================================================================
    # LAYER 1: Environmental Failure Analysis
    # =========================================================================

    def test_only_free_inmails_with_open_profile(self):
        """Layer 1: When only_send_free_inmails=True and lead is Open Profile, sends free InMail with 0 credit waste."""
        data = {
            "only_send_free_inmails": True,
            "is_open_profile": True,
            "subject": "Free Outreach",
            "body": "Reaching out via zero-cost Open Profile channel."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("inmail_tier"), "free")
        self.assertEqual(res.get("credits_saved"), 1)
        self.worker.send_inmail.assert_called_once()

    def test_only_free_inmails_with_closed_profile_diverts_to_connection_request(self):
        """Layer 1: When only_send_free_inmails=True and lead is closed profile, automatically diverts to connection request with body converted to note."""
        data = {
            "only_send_free_inmails": True,
            "is_open_profile": False,
            "fallback_to_connection_request": True,
            "body": "Hi Sam, impressed with your growth engineering work. Let's connect!"
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertIn(res.get("branch"), (Branch.SENT.value, "Connection request sent", "Sent"))
        self.assertTrue(res.get("diverted_from_paid_inmail") or res.get("fallback"))
        self.worker.send_connection_request.assert_called_once()
        conn_args = self.worker.send_connection_request.call_args
        sent_note = conn_args[0][1] if len(conn_args[0]) > 1 else conn_args[1].get("note", "")
        self.assertIn("Let's connect!", sent_note)
        self.worker.send_inmail.assert_not_called()

    def test_only_free_inmails_with_closed_profile_diverts_to_email(self):
        """Layer 1: When only_send_free_inmails=True, closed profile, and fallback_to_email=True, diverts to email send."""
        data = {
            "only_send_free_inmails": True,
            "is_open_profile": False,
            "fallback_to_connection_request": False,
            "fallback_to_email": True,
            "email": "lead@enterprise.com",
            "subject": "Quick Partnership Note",
            "body": "Hi Jamie, reaching out regarding our mutual tech integrations."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("diverted_from_paid_inmail") or res.get("arbitraged"))
        self.worker.send_inmail.assert_not_called()

    def test_only_free_inmails_no_fallback_skips_cleanly(self):
        """Layer 1: When only_send_free_inmails=True, closed profile, and no fallback configured, returns status='skipped', branch='not_open_profile' without error or penalty."""
        data = {
            "only_send_free_inmails": True,
            "is_open_profile": False,
            "fallback_to_connection_request": False,
            "fallback_to_email": False,
            "subject": "Exclusive Webinar",
            "body": "Join our upcoming session on distributed systems."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "skipped")
        self.assertEqual(res.get("branch"), "not_open_profile")
        self.assertEqual(res.get("reason"), "not_open_profile")
        self.worker.send_inmail.assert_not_called()
        self.worker.send_connection_request.assert_not_called()

    def test_paid_inmail_exhaustion_allows_free_inmail(self):
        """Layer 1: When account is out of paid InMail credits, sending to an Open Profile STILL succeeds because Free InMails do not consume paid quotas!"""
        # Simulate paid InMail credit limit error from rate limit checker
        with patch.object(self.executor, "_check_limit", return_value=("Paid InMail daily limit reached (0 credits remaining)", "2026-10-18")):
            data = {
                "is_open_profile": True,
                "subject": "Zero Cost Pitch",
                "body": "This InMail is 100% free because prospect has Open Profile."
            }
            res = self.executor.handle_send_inmail(data, self.test_lead_url)

            # Must succeed despite paid credit exhaustion
            self.assertEqual(res.get("status"), "success")
            self.assertTrue(res.get("is_free_inmail"))
            self.assertEqual(res.get("credits_saved"), 1)
            self.worker.send_inmail.assert_called_once()

    def test_paid_inmail_exhaustion_blocks_closed_profile(self):
        """Layer 1: When account is out of paid InMail credits, sending to a closed profile fails with rate_limited status."""
        with patch.object(self.executor, "_check_limit", return_value=("Paid InMail daily limit reached (0 credits remaining)", "2026-10-18")):
            data = {
                "is_open_profile": False,
                "fallback_to_connection_request": False,
                "subject": "Paid Outreach",
                "body": "Attempting paid outreach while credits are zero."
            }
            res = self.executor.handle_send_inmail(data, self.test_lead_url)

            self.assertEqual(res.get("status"), "rate_limited")
            self.assertEqual(res.get("reason"), "inmail_exhausted")
            self.worker.send_inmail.assert_not_called()

    def test_paid_inmail_exhaustion_fallback_to_connection_request(self):
        """Layer 1: When paid InMail credits are exhausted during worker dispatch, diverts to connection request if configured."""
        self.worker.send_inmail.return_value = {
            "status": "error",
            "reason": "inmail_exhausted",
            "error": "Out of InMail credits (0 remaining)"
        }
        data = {
            "is_open_profile": False,
            "subject": "Networking",
            "body": "Would love to add you to my professional network.",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertIn(res.get("branch"), (Branch.SENT.value, "Connection request sent", "Sent"))
        self.worker.send_connection_request.assert_called_once()

    def test_paid_inmail_exhaustion_fallback_to_email(self):
        """Layer 1: When paid InMail credits are exhausted during worker dispatch, diverts to email if fallback_to_email=True."""
        self.worker.send_inmail.return_value = {
            "status": "error",
            "reason": "inmail_exhausted",
            "error": "Out of InMail credits (0 remaining)"
        }
        data = {
            "is_open_profile": False,
            "fallback_to_connection_request": False,
            "fallback_to_email": True,
            "email": "lead@enterprise.com",
            "subject": "Connecting with Sarah",
            "body": "Following up via email since InMail is exhausted."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.worker.send_inmail.assert_called_once()

    def test_worker_send_inmail_only_free_aborts_on_paid_prompt(self):
        """Layer 1: When worker detects paid credit prompt in composer and only_free=True, worker aborts before sending."""
        # Using real LinkedInWorker in mock/test mode
        worker = LinkedInWorker(account_id="acc_unit_test")
        worker.mock_mode = True
        # Calling send_inmail with only_free=True on a closed profile returns skipped/aborted
        res = worker.send_inmail(
            profile_url=self.test_lead_url,
            subject="Test Subject",
            body="Test Body",
            is_open_profile=False,
            only_free=True
        )
        self.assertEqual(res.get("status"), "skipped")
        self.assertEqual(res.get("reason"), "not_open_profile")
        self.assertTrue(res.get("requires_paid_credit"))

    def test_lead_ingestion_normalizes_open_profile_flag(self):
        """Layer 1: Verifies execute_bulk_import_leads extracts and normalizes is_open_profile from 'true', True, '1', 1, 'yes', 'open'."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.side_effect = Exception("RPC unavailable for test")
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        test_leads = [
            {"email": "lead1@corp.com", "linkedin_url": "https://linkedin.com/in/lead1", "is_open_profile": "true"},
            {"email": "lead2@corp.com", "linkedin_url": "https://linkedin.com/in/lead2", "is_open_profile": True},
            {"email": "lead3@corp.com", "linkedin_url": "https://linkedin.com/in/lead3", "is_open_profile": "1"},
            {"email": "lead4@corp.com", "linkedin_url": "https://linkedin.com/in/lead4", "open_profile": 1},
            {"email": "lead5@corp.com", "linkedin_url": "https://linkedin.com/in/lead5", "open_profile": "yes"},
            {"email": "lead6@corp.com", "linkedin_url": "https://linkedin.com/in/lead6", "open_link": "open"},
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list_open_test",
            workspace_id="ws_open_test",
            leads=test_leads
        )
        self.assertTrue(res.get("success"))

        stored_leads = get_in_memory_leads_for_list("ws_open_test", "list_open_test")
        self.assertGreaterEqual(len(stored_leads), 6)
        for lead_record in stored_leads:
            self.assertIs(lead_record.get("is_open_profile"), True, f"Lead {lead_record.get('email')} failed boolean normalization")

    def test_lead_ingestion_normalizes_closed_profile_flag(self):
        """Layer 1: Verifies execute_bulk_import_leads normalizes 'false', False, '0', 0, 'no', 'closed' to False."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.side_effect = Exception("RPC unavailable for test")
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        test_leads = [
            {"email": "closed1@corp.com", "linkedin_url": "https://linkedin.com/in/closed1", "is_open_profile": "false"},
            {"email": "closed2@corp.com", "linkedin_url": "https://linkedin.com/in/closed2", "is_open_profile": False},
            {"email": "closed3@corp.com", "linkedin_url": "https://linkedin.com/in/closed3", "is_open_profile": "0"},
            {"email": "closed4@corp.com", "linkedin_url": "https://linkedin.com/in/closed4", "open_profile": 0},
            {"email": "closed5@corp.com", "linkedin_url": "https://linkedin.com/in/closed5", "open_profile": "no"},
            {"email": "closed6@corp.com", "linkedin_url": "https://linkedin.com/in/closed6", "is_open_profile": "closed"},
        ]

        res = execute_bulk_import_leads(
            supabase=mock_supabase,
            list_id="list_closed_test",
            workspace_id="ws_closed_test",
            leads=test_leads
        )
        self.assertTrue(res.get("success"))

        stored_leads = get_in_memory_leads_for_list("ws_closed_test", "list_closed_test")
        self.assertGreaterEqual(len(stored_leads), 6)
        for lead_record in stored_leads:
            self.assertIs(lead_record.get("is_open_profile"), False, f"Lead {lead_record.get('email')} failed closed boolean normalization")

    def test_open_profile_persisted_to_db_after_discovery(self):
        """Layer 1: When Open Profile is confirmed during send, updates leads.is_open_profile=True in database for future zero-cost reuse."""
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table

        data = {
            "lead_id": "lead_discovered_123",
            "is_open_profile": True,
            "subject": "Discovery Note",
            "body": "Checking in with you."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertIn(unittest.mock.call("leads"), self.supabase.table.call_args_list)
        mock_leads_table.update.assert_called_with({"is_open_profile": True})
        mock_leads_table.update.return_value.eq.assert_called_with("id", "lead_discovered_123")

    def test_open_profile_discovery_during_open_profile_check_persisted(self):
        """Layer 1: When open_profile_check node queries worker and finds Open Profile, persists leads.is_open_profile=True in database."""
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table
        # Database query initially returns empty (unknown status)
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Open", "open": True}

        data = {"lead_id": "lead_check_discovery_456"}
        res = self.executor.handle_open_profile_check(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Open")
        self.assertTrue(res.get("open"))
        mock_leads_table.update.assert_called_with({"is_open_profile": True})

    def test_worker_network_timeout_in_open_profile_check(self):
        """Layer 1: When worker throws exception or times out during check_open_profile, safely falls back to 'Not open'."""
        self.worker.check_open_profile.side_effect = Exception("Playwright browser timeout: Target page crashed")
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        data = {"_lead_id": "lead_timeout_001"}
        res = self.executor.handle_open_profile_check(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Not open")
        self.assertFalse(res.get("open"))

    # =========================================================================
    # LAYER 2: Human Paranoia & Extreme Edge Cases
    # =========================================================================

    def test_corrupted_boolean_types(self):
        """Layer 2: Corrupted boolean types ('invalid', None, {}, [], 'maybe') are safely handled without raising exceptions."""
        corrupted_values = ["invalid", None, {}, [], "maybe", 999, "unknown"]
        for bad_val in corrupted_values:
            data = {
                "is_open_profile": bad_val,
                "subject": "Resilience Test",
                "body": "Testing corrupted boolean resilience."
            }
            # Should safely execute without raising TypeError or ValueError
            res = self.executor.handle_send_inmail(data, self.test_lead_url)
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_empty_subject_and_body_clamping(self):
        """Layer 2: Subject clamped to 200 chars (197 + '...'), body clamped to 1900 chars (1897 + '...')."""
        long_subject = "X" * 350
        long_body = "Y" * 3000
        data = {
            "is_open_profile": True,
            "subject": long_subject,
            "body": long_body
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        args = self.worker.send_inmail.call_args[0]
        sent_subject = args[1]
        sent_body = args[2]

        self.assertLessEqual(len(sent_subject), 200)
        self.assertTrue(sent_subject.endswith("..."))
        self.assertLessEqual(len(sent_body), 1900)
        self.assertTrue(sent_body.endswith("..."))

    def test_connection_request_note_clamping_on_diversion(self):
        """Layer 2: When long InMail body (>300 chars) is diverted to connection request note, clamped to 300 chars without exceeding LinkedIn limits."""
        long_body = "We would love to connect with your team! " * 15  # > 600 characters
        data = {
            "only_send_free_inmails": True,
            "is_open_profile": False,
            "fallback_to_connection_request": True,
            "body": long_body
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.worker.send_connection_request.assert_called_once()
        conn_args = self.worker.send_connection_request.call_args
        sent_note = conn_args[0][1] if len(conn_args[0]) > 1 else conn_args[1].get("note", "")
        self.assertLessEqual(len(sent_note), 300)
        self.assertTrue(sent_note.endswith("..."))

    def test_missing_worker_error_handling(self):
        """Layer 2: Gracefully returns error dictionary without unhandled exception when worker is None or uninitialized."""
        executor_no_worker = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.supabase,
            workspace_id=self.workspace_id
        )
        data = {
            "is_open_profile": True,
            "subject": "Missing Worker Test",
            "body": "Should fail gracefully."
        }
        res = executor_no_worker.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.assertIn("worker", res.get("error", "").lower())

    def test_empty_body_with_fallback_template(self):
        """Layer 2: When InMail body is whitespace but fallback is provided, interpolates fallback cleanly."""
        data = {
            "is_open_profile": True,
            "body": "   ",
            "fallback": "Hello {{first_name}}, following up regarding {{company}}.",
            "variables": {"first_name": "Dave", "company": "GitHub"}
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        args = self.worker.send_inmail.call_args[0]
        self.assertEqual(args[2], "Hello Dave, following up regarding GitHub.")

    def test_empty_body_and_no_fallback_fails_closed(self):
        """Layer 2: Empty body and empty fallback fails closed with requires_approval=True and FAILED branch."""
        data = {
            "is_open_profile": True,
            "subject": "Valid Subject",
            "body": "",
            "fallback": ""
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.worker.send_inmail.assert_not_called()

    def test_concurrent_open_profile_arbitrage_race_protection(self):
        """Layer 2: Ensures idempotency and data consistency across repeated or concurrent executions."""
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table

        data = {
            "lead_id": "lead_race_condition_77",
            "is_open_profile": True,
            "subject": "Concurrent Test",
            "body": "Ensuring multiple dispatches execute cleanly."
        }

        # Simulate 3 sequential or concurrent worker attempts
        results = [self.executor.handle_send_inmail(data, self.test_lead_url) for _ in range(3)]

        for r in results:
            self.assertEqual(r.get("status"), "success")
            self.assertTrue(r.get("is_free_inmail"))
            self.assertEqual(r.get("credits_saved"), 1)

        # Database update should be idempotent (calling update with is_open_profile=True repeatedly causes zero corruption)
        self.assertEqual(mock_leads_table.update.call_count, 3)

    def test_database_failure_during_open_profile_check_does_not_crash(self):
        """Layer 2: If Supabase query throws exception in handle_open_profile_check, worker is queried gracefully."""
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table
        mock_leads_table.select.return_value.eq.return_value.execute.side_effect = Exception("PGRST connection dropped")
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Open", "open": True}

        data = {"_lead_id": "lead_db_crash_1"}
        res = self.executor.handle_open_profile_check(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Open")
        self.worker.check_open_profile.assert_called_once()

    def test_database_failure_during_discovery_persistence_does_not_fail_send(self):
        """Layer 2: If Supabase update throws exception when caching open profile, InMail send outcome remains successful."""
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table
        mock_leads_table.update.side_effect = Exception("Database disk full / read-only replica")

        data = {
            "lead_id": "lead_db_fail_graceful",
            "is_open_profile": True,
            "subject": "Resilience Verification",
            "body": "Send must succeed even if DB caching fails."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        # Outbound InMail was sent, so business action is successful
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("credits_saved"), 1)

    def test_only_free_inmails_with_dynamic_open_profile_discovery(self):
        """Layer 2: When lead has no pre-existing flag, but only_send_free_inmails=True, worker dynamic check discovers open profile and dispatches free InMail."""
        mock_leads_table = MagicMock()
        self.supabase.table.return_value = mock_leads_table
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Open", "open": True}

        data = {
            "lead_id": "lead_dynamic_999",
            "only_send_free_inmails": True,
            "subject": "Dynamic Discovery",
            "body": "Checking dynamically before sending InMail."
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("credits_saved"), 1)
        self.worker.check_open_profile.assert_called_once()
        self.worker.send_inmail.assert_called_once()


if __name__ == "__main__":
    unittest.main()
