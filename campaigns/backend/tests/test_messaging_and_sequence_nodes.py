import unittest
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestMessagingAndSequenceNodes(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_msg_seq_001"
        self.supabase = MagicMock()
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data=True)
        # Mock table calls to avoid PostgREST MagicMock cache false-positives
        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.supabase.table.return_value = table_mock

        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws_msg_seq_123"
        )
        self.test_lead_url = "https://www.linkedin.com/in/direct-outreach-prospect"

    # ══════════════════════════════════════════════════════════════════════════
    # 1. send_message
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_message_foundational_success(self):
        """Layer 0: Standard direct message delivers and returns Branch.SENT.value."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "body": "Hi {{first_name}}, loved your recent insights on {{company}}!",
            "first_name": "Elena",
            "company": "ScaleTech"
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message.assert_called_once_with(
            self.test_lead_url,
            "Hi Elena, loved your recent insights on ScaleTech!"
        )

    def test_send_message_dialog_unavailable_fallback_to_connection(self):
        """Layer 1: Message dialog unavailable triggers auto-fallback to connection request."""
        self.worker.send_message.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile. Lead may not be a 1st degree connection."
        }
        self.worker.send_connection_request.return_value = {"status": "success"}
        data = {
            "body": "Great chatting at the event!",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Connection request sent")
        self.assertTrue(res.get("fallback"))
        self.assertEqual(res.get("action"), "connection_request")

    def test_send_message_empty_body_and_fallback_fails_closed(self):
        """Layer 2 (Human Paranoia): Empty message and empty fallback fails closed with requires_approval."""
        data = {"body": "   ", "fallback": ""}
        res = self.executor.handle_send_message(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.worker.send_message.assert_not_called()

    # ══════════════════════════════════════════════════════════════════════════
    # 2. send_message_ab
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_message_ab_deterministic_split(self):
        """Layer 0: Assigns A or B deterministically and attaches variant telemetry."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "body_a": "Hey {{first_name}}, Variant A pitch",
            "body_b": "Hey {{first_name}}, Variant B value hook",
            "first_name": "Marcus",
            "_lead_id": "lead_hash_456"
        }
        res = self.executor.handle_send_message_ab(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.assertIn(res.get("variant"), ["A", "B"])
        self.assertIn("ab_variant_sent", res.get("variables", {}))
        self.assertEqual(res["variables"]["ab_variant_sent"], res["variant"])

    def test_send_message_ab_empty_variant_falls_back_to_alternate(self):
        """Layer 2: If operator configured Variant A but left Variant B empty, falls back to Variant A."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "body_a": "Hi {{first_name}}, this is the robust pitch",
            "body_b": "",
            "first_name": "Chloe"
        }
        res = self.executor.handle_send_message_ab(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.assertIn("Chloe", self.worker.send_message.call_args[0][1])

    def test_send_message_ab_both_variants_empty_fails_closed(self):
        """Layer 2: If both variant A and variant B are empty, fails closed."""
        data = {"body_a": "", "body_b": "", "fallback": ""}
        res = self.executor.handle_send_message_ab(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)

    # ══════════════════════════════════════════════════════════════════════════
    # 3. send_message_with_doc
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_message_with_doc_valid_dispatch(self):
        """Layer 0: Dispatches with document attachment when doc_url is valid."""
        self.worker.send_message_with_attachment.return_value = {"status": "success"}
        data = {
            "body": "Here is our quarterly benchmark study",
            "doc_url": "https://cdn.example.com/reports/benchmark_2026.pdf"
        }
        res = self.executor.handle_send_message_with_doc(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message_with_attachment.assert_called_once_with(
            self.test_lead_url,
            "Here is our quarterly benchmark study",
            "https://cdn.example.com/reports/benchmark_2026.pdf",
            "document"
        )

    def test_send_message_with_doc_missing_url_fails_closed(self):
        """Layer 1/2: Refuses to send empty attachment promise without valid doc_url."""
        data = {
            "body": "Check out this document attached",
            "doc_url": ""
        }
        res = self.executor.handle_send_message_with_doc(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.assertIn("no valid doc_url configured", res.get("error", ""))

    # ══════════════════════════════════════════════════════════════════════════
    # 4. send_message_with_image
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_message_with_image_valid_dispatch(self):
        """Layer 0: Dispatches with image attachment when image_url is valid."""
        self.worker.send_message_with_attachment.return_value = {"status": "success"}
        data = {
            "body": "Check out this architecture diagram",
            "image_url": "https://cdn.example.com/images/architecture.png"
        }
        res = self.executor.handle_send_message_with_image(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message_with_attachment.assert_called_once_with(
            self.test_lead_url,
            "Check out this architecture diagram",
            "https://cdn.example.com/images/architecture.png",
            "image"
        )

    def test_send_message_with_image_missing_url_fails_closed(self):
        """Layer 1/2: Refuses to send image message when image_url is missing."""
        data = {
            "body": "Here is the screenshot",
            "image_url": ""
        }
        res = self.executor.handle_send_message_with_image(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.assertIn("no valid image_url configured", res.get("error", ""))

    # ══════════════════════════════════════════════════════════════════════════
    # 5. Sequence Touches: intro, followup, breakup, reengage
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_intro_message_smart_default_when_body_omitted(self):
        """Layer 2: Intro message automatically uses warm connection fallback if body omitted."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {"first_name": "Liam"}
        res = self.executor.handle_send_intro_message(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        sent_body = self.worker.send_message.call_args[0][1]
        self.assertIn("Liam", sent_body)
        self.assertIn("thanks for connecting", sent_body.lower())

    def test_send_followup_smart_default_when_body_omitted(self):
        """Layer 2: Followup message automatically uses value bump fallback if body omitted."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {"first_name": "Sophia"}
        res = self.executor.handle_send_followup(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        sent_body = self.worker.send_message.call_args[0][1]
        self.assertIn("Sophia", sent_body)
        self.assertIn("following up", sent_body.lower())

    def test_send_breakup_message_smart_default_when_body_omitted(self):
        """Layer 2: Breakup message automatically uses polite closing fallback if body omitted."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {"first_name": "Daniel"}
        res = self.executor.handle_send_breakup_message(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        sent_body = self.worker.send_message.call_args[0][1]
        self.assertIn("Daniel", sent_body)
        self.assertIn("pause reaching out", sent_body.lower())

    def test_send_reengage_message_smart_default_when_body_omitted(self):
        """Layer 2: Re-engagement message automatically uses fresh context fallback if body omitted."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {"first_name": "Aria", "company": "NextGen"}
        res = self.executor.handle_send_reengage_message(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        sent_body = self.worker.send_message.call_args[0][1]
        self.assertIn("Aria", sent_body)
        self.assertIn("circling back", sent_body.lower())

    # ══════════════════════════════════════════════════════════════════════════
    # 6. InMail: send_inmail & send_paid_inmail
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_inmail_foundational_success(self):
        """Layer 0: Dispatches InMail with subject and body, advancing to Branch.THEN.value."""
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {
            "subject": "Question about {{company}}'s outbound tech",
            "body": "Hey {{first_name}}, noticing your expansion.",
            "first_name": "Maya",
            "company": "CloudPeak"
        }
        res = self.executor.handle_send_inmail(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        args = self.worker.send_inmail.call_args[0]
        self.assertIn("CloudPeak", args[1])
        self.assertIn("Maya", args[2])

    def test_send_inmail_empty_body_fails_closed(self):
        """Layer 2: InMail with empty body and no fallback fails closed."""
        data = {"subject": "Valid Subject", "body": "   ", "fallback": ""}
        res = self.executor.handle_send_inmail(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)

    def test_send_paid_inmail_delegation(self):
        """Layer 0: Paid InMail delegates to InMail handler with Branch.THEN.value."""
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {
            "subject": "Sponsored Executive Briefing",
            "body": "Executive briefing for {{first_name}}",
            "first_name": "David"
        }
        res = self.executor.handle_send_paid_inmail(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)

    # ══════════════════════════════════════════════════════════════════════════
    # 7. send_voice_note
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_voice_note_foundational_success(self):
        """Layer 0: Valid voice note audio URL dispatches successfully."""
        self.worker.send_voice_note.return_value = {"status": "success"}
        data = {
            "audio_url": "https://storage.example.com/audio/voice_greeting.mp3",
            "note": "Quick voice note for you!"
        }
        res = self.executor.handle_send_voice_note(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.worker.send_voice_note.assert_called_once_with(
            self.test_lead_url,
            "https://storage.example.com/audio/voice_greeting.mp3",
            note="Quick voice note for you!"
        )

    def test_send_voice_note_invalid_url_fails_closed(self):
        """Layer 2: Malformed or missing audio URL fails closed."""
        data = {"audio_url": "ftp://badhost/memo.mp3"}
        res = self.executor.handle_send_voice_note(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)

    # ══════════════════════════════════════════════════════════════════════════
    # 8. congratulate_new_job & congratulate_anniversary
    # ══════════════════════════════════════════════════════════════════════════

    def test_congratulate_new_job_foundational_success(self):
        """Layer 0: Congratulates on new role and returns Branch.THEN.value."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "first_name": "Rachel",
            "company": "Apex Global"
        }
        res = self.executor.handle_congratulate_new_job(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        sent_body = self.worker.send_message.call_args[0][1]
        self.assertIn("Rachel", sent_body)
        self.assertIn("Apex Global", sent_body)

    def test_congratulate_new_job_not_connected_fallback_to_connection(self):
        """Layer 1: When prospect is not 1st degree, falls back to connection request note."""
        self.worker.send_message.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile. Lead may not be a 1st degree connection."
        }
        self.worker.send_connection_request.return_value = {"status": "success"}
        data = {
            "first_name": "Devin",
            "company": "Vanguard Labs",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_congratulate_new_job(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Connection request sent")
        self.assertTrue(res.get("fallback"))
        self.assertEqual(res.get("action"), "connection_request")

    def test_congratulate_anniversary_foundational_success(self):
        """Layer 0: Congratulates on work anniversary and returns Branch.THEN.value."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "first_name": "Nathan",
            "company": "Stripe"
        }
        res = self.executor.handle_congratulate_anniversary(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        sent_body = self.worker.send_message.call_args[0][1]
        self.assertIn("Nathan", sent_body)
        self.assertIn("Stripe", sent_body)
        self.assertIn("work anniversary", sent_body.lower())

    def test_congratulate_anniversary_not_connected_fallback_to_connection(self):
        """Layer 1: When prospect is not 1st degree, falls back to connection request note."""
        self.worker.send_message.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile"
        }
        self.worker.send_connection_request.return_value = {"status": "success"}
        data = {
            "first_name": "Jessica",
            "company": "Figma",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_congratulate_anniversary(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Connection request sent")
        self.assertTrue(res.get("fallback"))
        self.assertEqual(res.get("action"), "connection_request")


if __name__ == "__main__":
    unittest.main()
