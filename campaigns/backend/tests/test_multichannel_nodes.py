import unittest
from unittest.mock import MagicMock, patch
import json
import os

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestMultichannelNodes(unittest.TestCase):
    def setUp(self):
        self.supabase = MagicMock()
        self.worker = MagicMock()
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws-test-123"
        )
        self.executor.account_id = "acc-test-1"

    # ── InMail Nodes ─────────────────────────────────────────────────────────

    def test_send_inmail_success_standardizes_branch_then(self):
        self.worker.send_inmail.return_value = {"status": "success", "sent_at": "2026-10-10T12:00:00Z"}
        data = {
            "subject": "Quick question for {{first_name}}",
            "body": "Hi {{first_name}}, loved your work at {{company}}!",
            "first_name": "Sarah",
            "company": "Acme Corp"
        }
        res = self.executor.handle_send_inmail(data, "https://linkedin.com/in/sarah")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        self.worker.send_inmail.assert_called_once()
        args = self.worker.send_inmail.call_args[0]
        self.assertEqual(args[0], "https://linkedin.com/in/sarah")
        self.assertIn("Sarah", args[1])
        self.assertIn("Acme Corp", args[2])

    def test_send_inmail_clamps_long_subject_and_body(self):
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {
            "subject": "A" * 300,
            "body": "B" * 2500,
            "first_name": "John"
        }
        res = self.executor.handle_send_inmail(data, "https://linkedin.com/in/john")
        self.assertEqual(res.get("status"), "success")
        args = self.worker.send_inmail.call_args[0]
        self.assertLessEqual(len(args[1]), 200)
        self.assertLessEqual(len(args[2]), 1900)

    def test_send_inmail_empty_subject_auto_defaults(self):
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {
            "subject": "",
            "body": "Hello there!",
            "first_name": "Elena"
        }
        res = self.executor.handle_send_inmail(data, "https://linkedin.com/in/elena")
        self.assertEqual(res.get("status"), "success")
        args = self.worker.send_inmail.call_args[0]
        self.assertEqual(args[1], "Connecting with Elena")

    def test_send_inmail_credit_exhaustion_rate_limited(self):
        self.worker.send_inmail.return_value = {
            "status": "error",
            "reason": "inmail_exhausted",
            "error": "Out of InMail credits"
        }
        data = {"subject": "Hi", "body": "Hey", "fallback_to_connection_request": False}
        res = self.executor.handle_send_inmail(data, "https://linkedin.com/in/prospect")
        self.assertEqual(res.get("status"), "rate_limited")
        self.assertEqual(res.get("reason"), "inmail_exhausted")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)

    def test_send_inmail_credit_exhaustion_fallback_to_connection_request(self):
        self.worker.send_inmail.return_value = {
            "status": "error",
            "reason": "inmail_exhausted",
            "error": "Out of InMail credits"
        }
        self.worker.send_connection_request.return_value = {"status": "success"}
        data = {
            "subject": "Hi",
            "body": "Hey, let's connect!",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_send_inmail(data, "https://linkedin.com/in/prospect")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_connection_request.assert_called_once()

    def test_send_paid_inmail_delegates_to_inmail(self):
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {"subject": "Sponsored", "body": "Hello", "first_name": "Sam"}
        res = self.executor.handle_send_paid_inmail(data, "https://linkedin.com/in/sam")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)

    # ── Email Nodes ──────────────────────────────────────────────────────────

    def test_send_email_success_standardizes_branch_then(self):
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "SG.test-key", "ENV": "development"}):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 202
                mock_url.return_value.__enter__.return_value = mock_resp
                
                data = {
                    "email": "lead@company.com",
                    "subject": "Hello {{first_name}}",
                    "body": "Welcome to {{company}}",
                    "first_name": "David",
                    "company": "Stark Industries"
                }
                res = self.executor.handle_send_email(data, "https://linkedin.com/in/david")
                self.assertEqual(res.get("status"), "success")
                self.assertEqual(res.get("branch"), Branch.THEN.value)
                self.assertEqual(res.get("to"), "lead@company.com")
                self.assertIn("David", res.get("subject"))

    def test_send_email_missing_recipient_fails_gracefully(self):
        data = {"subject": "Hello", "body": "No email here"}
        self.supabase.table().select().eq().execute.return_value.data = []
        res = self.executor.handle_send_email(data, "https://linkedin.com/in/no-email")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.assertIn("Recipient email not found", res.get("error"))

    def test_send_email_invalid_syntax_rejected(self):
        data = {"to": "not-an-email-address", "subject": "Hello", "body": "World"}
        res = self.executor.handle_send_email(data, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.assertIn("Invalid recipient email syntax", res.get("error"))

    def test_send_email_dev_mock_fallback_when_api_key_unset(self):
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "", "ENV": "development", "TEST_MODE": "true"}):
            data = {"email": "test@demo.com", "subject": "Hi", "body": "There"}
            res = self.executor.handle_send_email(data, "https://linkedin.com/in/demo")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    # ── CRM Nodes ────────────────────────────────────────────────────────────

    def test_push_to_crm_hubspot_standardizes_branch_then(self):
        self.supabase.table().select().eq().eq().limit().execute.return_value.data = [{
            "id": "lead-1", "first_name": "Bob", "email": "bob@acme.com"
        }]
        self.supabase.table().select().eq().single().execute.return_value.data = {
            "hubspot_token": "hs-token-xyz"
        }
        with patch("campaigns.backend.services.elein_executor.push_to_hubspot", return_value=True):
            data = {"provider": "HubSpot", "pipeline_stage": "warm"}
            res = self.executor.handle_push_to_crm(data, "https://linkedin.com/in/bob")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_push_to_crm_alias_normalization(self):
        self.supabase.table().select().eq().eq().limit().execute.return_value.data = [{
            "id": "lead-2", "first_name": "Alice"
        }]
        self.supabase.table().select().eq().single().execute.return_value.data = {
            "hubspot_token": "hs-token-xyz"
        }
        with patch("campaigns.backend.services.elein_executor.push_to_hubspot", return_value=True):
            data = {"crm": "HubSpot"}
            res = self.executor.handle_push_to_crm(data, "https://linkedin.com/in/alice")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_push_to_crm_unknown_provider_returns_failed_branch(self):
        data = {"provider": "RandomCustomDB"}
        res = self.executor.handle_push_to_crm(data, "https://linkedin.com/in/user")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)

    # ── Email Sequencer Nodes ────────────────────────────────────────────────

    def test_add_to_email_sequencer_smartlead_success(self):
        self.supabase.table().select().eq().eq().limit().execute.return_value.data = [{
            "id": "lead-sl", "first_name": "Mark", "email": "mark@test.com"
        }]
        with patch("integrations.backend.services.elein_crm_service.add_to_smartlead", return_value=True):
            data = {"provider": "Smartlead", "campaign_id": "sl-campaign-123"}
            res = self.executor.handle_add_to_email_sequencer(data, "https://linkedin.com/in/mark")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_add_to_email_sequencer_instantly_success(self):
        self.supabase.table().select().eq().eq().limit().execute.return_value.data = [{
            "id": "lead-in", "first_name": "Anna", "email": "anna@test.com"
        }]
        with patch("integrations.backend.services.elein_crm_service.add_to_instantly", return_value=True):
            data = {"sequencer": "Instantly", "sequence_id": "instantly-seq-456"}
            res = self.executor.handle_add_to_email_sequencer(data, "https://linkedin.com/in/anna")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_add_to_smartlead_missing_campaign_id_fails_cleanly(self):
        self.supabase.table().select().eq().eq().limit().execute.return_value.data = [{
            "id": "lead-sl2", "email": "mark2@test.com"
        }]
        data = {"campaign_id": ""}
        res = self.executor.handle_add_to_smartlead(data, "https://linkedin.com/in/mark2")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.assertIn("campaign_id required", res.get("error"))

    # ── Slack & Webhook Nodes ────────────────────────────────────────────────

    def test_send_slack_alert_interpolates_template_and_returns_then(self):
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.return_value.__enter__.return_value = MagicMock()
            data = {
                "webhook_url": "https://hooks.slack.com/services/T00/B00/X00",
                "message": "🔥 {{first_name}} from {{company}} replied!",
                "first_name": "Jessica",
                "company": "Vercel"
            }
            res = self.executor.handle_send_slack_alert(data, "https://linkedin.com/in/jessica")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)
            mock_url.assert_called_once()
            req = mock_url.call_args[0][0]
            body_json = json.loads(req.data.decode("utf-8"))
            self.assertIn("Jessica", body_json["text"])
            self.assertIn("Vercel", body_json["text"])

    def test_send_slack_alert_no_webhook_skips_without_crashing(self):
        self.supabase.table().select().eq().limit().execute.return_value.data = []
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": ""}):
            data = {"message": "Test notification"}
            res = self.executor.handle_send_slack_alert(data, "https://linkedin.com/in/test")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)
            self.assertIn("skipped", res.get("message"))

    def test_send_webhook_custom_json_template_interpolated(self):
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.return_value.__enter__.return_value = MagicMock()
            data = {
                "url": "https://hooks.zapier.com/hooks/catch/123/abc/",
                "payload_template": '{"lead": "{{first_name}}", "org": "{{company}}"}',
                "first_name": "Tom",
                "company": "Linear"
            }
            res = self.executor.handle_send_webhook(data, "https://linkedin.com/in/tom")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)
            mock_url.assert_called_once()
            req = mock_url.call_args[0][0]
            sent_payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(sent_payload.get("lead"), "Tom")
            self.assertEqual(sent_payload.get("org"), "Linear")

    def test_send_webhook_invalid_url_fails_gracefully(self):
        data = {"url": "ftp://broken-schema.com"}
        res = self.executor.handle_send_webhook(data, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)


if __name__ == "__main__":
    unittest.main()
