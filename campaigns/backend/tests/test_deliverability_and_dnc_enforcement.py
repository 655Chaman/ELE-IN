"""
Three-Layer Paranoia Framework Unit Test Suite:
Issue 4 — Deliverability Collapse, Mailbox Blacklisting, RFC 8058, & Anti-Spam Compliance
Tests Universal Pre-Flight Suppression, Cross-Channel Opt-Out Gates, Mailbox Burnout Protection,
and Retroactive Purge.
"""
import os
import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from campaigns.backend.services.elein_executor import EleInNodeExecutor, LeadSuppressedError
from leads.backend.services.suppression_service import retroactive_purge_suppressed_leads, check_lead_suppression


class TestDeliverabilityAndDNCEnforcement(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-deliverability-test"
        self.mock_supabase = MagicMock()
        self.mock_worker = MagicMock()
        self.executor = EleInNodeExecutor(
            worker=self.mock_worker,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

    # =========================================================================
    # Layer 0: The Foundational Layer (Core Mechanics)
    # =========================================================================

    def test_handle_send_email_aborts_when_prospect_unsubscribed_in_payload(self):
        """Layer 0: handle_send_email aborts immediately if lead is marked unsubscribed in payload."""
        data = {
            "to_email": "prospect@acmecorp.com",
            "subject": "Quick question",
            "body": "Hi there, wanted to connect.",
            "is_unsubscribed": True,
            "status": "UNSUBSCRIBED",
        }
        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "prospect_unsubscribed")
        self.assertIn("unsubscribed or opted out", res["error"])
        self.mock_worker.send_message.assert_not_called()

    def test_handle_send_email_aborts_when_exact_email_in_suppression_list(self):
        """Layer 0: handle_send_email aborts when email is in workspace suppression list."""
        data = {
            "to_email": "blocked@rivalsaas.io",
            "subject": "Hello",
            "body": "Checking in.",
            "lead_id": "lead-blocked-1",
        }
        # Mock suppression check hit
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_check:
            mock_check.return_value = {
                "suppressed": True,
                "matched_by": "email",
                "matched_value": "blocked@rivalsaas.io",
                "reason": "customer_request_dnc",
            }
            res = self.executor.handle_send_email(data, linkedin_url=None)
            self.assertEqual(res["status"], "skipped")
            self.assertEqual(res["reason"], "prospect_suppressed")
            self.assertEqual(res["matched_by"], "email")
            self.assertIn("blocked@rivalsaas.io", res["error"])

    def test_handle_send_email_aborts_when_email_domain_wildcard_suppressed(self):
        """Layer 0: handle_send_email aborts when company domain is wildcard-suppressed (e.g. @competitor.com)."""
        data = {
            "to_email": "vp_sales@competitor.com",
            "subject": "Partnership",
            "body": "Let's explore synergies.",
        }
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_check:
            mock_check.return_value = {
                "suppressed": True,
                "matched_by": "domain",
                "matched_value": "competitor.com",
                "reason": "competitor_exclusion_list",
            }
            res = self.executor.handle_send_email(data, linkedin_url=None)
            self.assertEqual(res["status"], "skipped")
            self.assertEqual(res["reason"], "prospect_suppressed")
            self.assertEqual(res["matched_by"], "domain")
            self.assertIn("competitor.com", res["error"])

    def test_handle_send_message_aborts_when_linkedin_url_suppressed(self):
        """Layer 0: LinkedIn send_message aborts immediately when prospect is on DNC list."""
        data = {
            "message": "Hey John, saw your post on AI.",
            "linkedin_url": "https://www.linkedin.com/in/john-doe",
        }
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_check:
            mock_check.return_value = {
                "suppressed": True,
                "matched_by": "linkedin_url",
                "matched_value": "https://www.linkedin.com/in/john-doe",
                "reason": "manual_dnc_request",
            }
            res = self.executor.handle_send_message(data, linkedin_url="https://www.linkedin.com/in/john-doe")
            self.assertEqual(res["status"], "skipped")
            self.assertEqual(res["reason"], "prospect_suppressed")
            self.mock_worker.send_message.assert_not_called()

    def test_handle_connection_request_aborts_when_lead_suppressed(self):
        """Layer 0: LinkedIn connection request aborts before sending when lead is suppressed."""
        data = {
            "note": "Let's connect!",
            "note_strategy": "Fixed note",
            "linkedin_url": "https://www.linkedin.com/in/prospect-optout",
        }
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_check:
            mock_check.return_value = {
                "suppressed": True,
                "matched_by": "linkedin_url",
                "matched_value": "https://www.linkedin.com/in/prospect-optout",
                "reason": "unsubscribed_via_rfc8058",
            }
            res = self.executor.handle_connection_request(data, linkedin_url="https://www.linkedin.com/in/prospect-optout")
            self.assertEqual(res["status"], "skipped")
            self.assertEqual(res["reason"], "prospect_suppressed")
            self.mock_worker.send_connection_request.assert_not_called()

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Outages, Burnout, Race Conditions)
    # =========================================================================

    def test_handle_send_email_blocks_burned_or_quarantined_sender_inbox(self):
        """Layer 1: handle_send_email aborts and refunds credit if the selected sender inbox is in burnout or quarantine."""
        data = {
            "to_email": "prospect@healthy-target.com",
            "subject": "Intro",
            "body": "Hello world",
            "selected_inbox": {
                "email": "outreach@burned-domain.com",
                "domain_burnout_status": "BURNOUT_QUARANTINED",
                "status": "QUARANTINED",
            },
        }
        with patch.object(self.executor, "_deduct_credits", return_value=True), \
             patch.object(self.executor, "_refund_credits") as mock_refund:
            res = self.executor.handle_send_email(data, linkedin_url=None)
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["reason"], "sender_inbox_burned_or_quarantined")
            self.assertIn("burned or quarantined", res["error"])
            # Credit must be safely refunded
            mock_refund.assert_called_once()
            self.assertEqual(mock_refund.call_args[1]["reason"], "inbox_burned_or_quarantined")

    def test_handle_send_email_blocks_emergency_paused_mailbox(self):
        """Layer 1: handle_send_email aborts if mailbox is marked EMERGENCY_PAUSED due to warmup tripwire."""
        data = {
            "to_email": "prospect@healthy-target.com",
            "subject": "Intro",
            "body": "Hello world",
            "selected_inbox": {
                "email": "sender@recovering-domain.com",
                "domain_burnout_status": "EMERGENCY_PAUSED",
                "emergency_paused": True,
            },
        }
        with patch.object(self.executor, "_deduct_credits", return_value=True), \
             patch.object(self.executor, "_refund_credits") as mock_refund:
            res = self.executor.handle_send_email(data, linkedin_url=None)
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["reason"], "sender_inbox_burned_or_quarantined")
            mock_refund.assert_called_once()

    def test_retroactive_purge_cancels_pending_outbox_events_for_suppressed_leads(self):
        """Layer 1: Retroactive DNC purge halts execution states and cancels pending outbox_events to stop race-condition dispatches."""
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]

        # Leads matching domain
        tables["leads"].select.return_value.eq.return_value.range.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead-dnc-1", "email": "ceo@blocked-firm.com", "domain": "blocked-firm.com"}]
        )
        # Mock enrollments
        tables["campaign_enrollments"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "enr-1"}]
        )
        # Mock execution states
        tables["campaign_execution_states"].update.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "state-1"}]
        )
        # Mock outbox events
        tables["outbox_events"].update.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "ob-1", "status": "cancelled"}]
        )

        res = retroactive_purge_suppressed_leads(
            supabase=mock_svc,
            workspace_id="ws-dnc-test",
            domains=["blocked-firm.com"],
        )
        self.assertEqual(res["matched_leads_count"], 1)
        self.assertIn("lead-dnc-1", res["lead_ids"])

        # Verify outbox_events cancel call
        outbox_update_args = tables["outbox_events"].update.call_args[0][0]
        self.assertEqual(outbox_update_args["status"], "cancelled")
        self.assertIn("Suppressed prospect", outbox_update_args["error_message"])

    # =========================================================================
    # Layer 2: Human Paranoia (Cross-Channel Stalking & Dirty Inputs)
    # =========================================================================

    def test_cross_channel_opt_out_blocks_linkedin_after_email_unsubscribe(self):
        """
        Layer 2: When a prospect unsubscribes from email outreach (status='UNSUBSCRIBED'),
        subsequent sequence steps attempting LinkedIn outreach (InMail, Message) are blocked immediately.
        """
        data = {
            "_lead_id": "lead-unsub-999",
            "body": "Hey, circling back on LinkedIn since you didn't reply to my email!",
            "linkedin_url": "https://www.linkedin.com/in/unsub-lead",
        }
        # Supabase returns that this lead has status='UNSUBSCRIBED' and is_unsubscribed=True
        mock_lead_row = {
            "id": "lead-unsub-999",
            "email": "unsub@company.com",
            "linkedin_url": "https://www.linkedin.com/in/unsub-lead",
            "status": "UNSUBSCRIBED",
            "is_unsubscribed": True,
        }
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[mock_lead_row]
        )

        res = self.executor.handle_send_message(data, linkedin_url="https://www.linkedin.com/in/unsub-lead")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "prospect_unsubscribed")
        self.assertIn("unsubscribed", res["error"].lower())
        self.mock_worker.send_message.assert_not_called()

    def test_handle_blacklist_check_node_identifies_suppressed_lead_and_wildcard_domains(self):
        """Layer 2: handle_blacklist_check visual node returns 'Blacklisted → skip' for wildcard domains and opted-out leads."""
        data = {
            "email": "employee@competitor-saas.com",
            "linkedin_url": "https://www.linkedin.com/in/competitor-rep",
        }
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_check:
            mock_check.return_value = {
                "suppressed": True,
                "matched_by": "domain",
                "matched_value": "competitor-saas.com",
                "reason": "rival_saas_exclusion",
            }
            res = self.executor.handle_blacklist_check(data, linkedin_url="https://www.linkedin.com/in/competitor-rep")
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["branch"], "Blacklisted → skip")

    def test_handle_send_inmail_aborts_for_complained_or_bounced_prospect(self):
        """Layer 2: handle_send_inmail aborts when lead status is COMPLAINED or BOUNCED in database."""
        data = {
            "_lead_id": "lead-complained-42",
            "subject": "Quick demo",
            "body": "Check this out",
            "is_open_profile": True,
        }
        mock_lead_row = {
            "id": "lead-complained-42",
            "status": "COMPLAINED",
            "is_unsubscribed": True,
            "email": "angry_prospect@corp.com",
            "linkedin_url": "https://www.linkedin.com/in/angry-prospect",
        }
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[mock_lead_row]
        )

        res = self.executor.handle_send_inmail(data, linkedin_url="https://www.linkedin.com/in/angry-prospect")
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "prospect_unsubscribed")
        self.assertIn("unsubscribed", res["error"].lower())
        self.mock_worker.send_inmail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
