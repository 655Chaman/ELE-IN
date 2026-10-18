import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestInMailArbitrage(unittest.TestCase):
    def setUp(self):
        self.supabase = MagicMock()
        self.worker = MagicMock()
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws-test-arbitrage"
        )
        self.test_url = "https://linkedin.com/in/prospect-ceo"

    def test_arbitrage_discovery_payload_open_profile(self):
        """Pre-Flight: Detects is_open_profile=True from payload, marks Free InMail, saves 1 credit."""
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {
            "subject": "Quick chat {{first_name}}",
            "body": "Hi {{first_name}}, let's connect!",
            "first_name": "Alice",
            "is_open_profile": True,
            "only_send_free_inmails": True,
            "lead_id": "lead-101"
        }
        res = self.executor.handle_send_inmail(data, self.test_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("inmail_tier"), "free")
        self.assertEqual(res.get("credits_saved"), 1)
        self.worker.send_inmail.assert_called_once()
        kwargs = self.worker.send_inmail.call_args[1]
        self.assertTrue(kwargs.get("is_open_profile"))
        self.assertTrue(kwargs.get("only_free"))

    def test_arbitrage_discovery_db_open_profile(self):
        """Pre-Flight: Queries Supabase leads table when is_open_profile is not in payload."""
        self.worker.send_inmail.return_value = {"status": "success"}
        mock_res = MagicMock()
        mock_res.data = [{"is_open_profile": True}]
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_res

        data = {
            "subject": "Hello {{first_name}}",
            "body": "Testing InMail delivery",
            "first_name": "Bob",
            "lead_id": "lead-202"
        }
        res = self.executor.handle_send_inmail(data, self.test_url)
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("inmail_tier"), "free")
        self.assertEqual(res.get("credits_saved"), 1)

    def test_arbitrage_gate_diverts_to_connection_request(self):
        """Arbitrage Gate: only_free=True & is_open_profile=False diverts to free connection request."""
        self.worker.send_connection_request.return_value = {"status": "success"}
        data = {
            "subject": "Partnership idea",
            "body": "Hey Charlie, would love to connect about growth at your company.",
            "first_name": "Charlie",
            "is_open_profile": False,
            "only_send_free_inmails": True,
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_send_inmail(data, self.test_url)
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("arbitraged"))
        self.assertTrue(res.get("diverted_from_paid_inmail"))
        self.worker.send_connection_request.assert_called_once()
        self.worker.send_inmail.assert_not_called()

    def test_arbitrage_gate_diverts_to_email(self):
        """Arbitrage Gate: only_free=True & is_open_profile=False diverts to email when connection fallback is False."""
        data = {
            "subject": "Introductory inquiry",
            "body": "Hello Dana, saw your team's launch.",
            "first_name": "Dana",
            "email": "dana@example.com",
            "is_open_profile": False,
            "only_send_free_inmails": True,
            "fallback_to_connection_request": False,
            "fallback_to_email": True
        }
        with patch.object(self.executor, "handle_send_email") as mock_send_email:
            mock_send_email.return_value = {"status": "success", "branch": Branch.THEN.value}
            res = self.executor.handle_send_inmail(data, self.test_url)
            self.assertEqual(res.get("status"), "success")
            self.assertTrue(res.get("arbitraged"))
            self.assertTrue(res.get("diverted_from_paid_inmail"))
            mock_send_email.assert_called_once()
            email_payload = mock_send_email.call_args[0][0]
            self.assertEqual(email_payload["email"], "dana@example.com")
            self.assertEqual(email_payload["subject"], "Introductory inquiry")

    def test_arbitrage_gate_skips_when_no_fallback_configured(self):
        """Arbitrage Gate: only_free=True & is_open_profile=False returns skipped when no fallback is active."""
        data = {
            "subject": "Direct outreach",
            "body": "Hi Evan",
            "is_open_profile": False,
            "only_send_free_inmails": True,
            "fallback_to_connection_request": False,
            "fallback_to_email": False
        }
        res = self.executor.handle_send_inmail(data, self.test_url)
        self.assertEqual(res.get("status"), "skipped")
        self.assertEqual(res.get("reason"), "not_open_profile")
        self.assertEqual(res.get("branch"), "not_open_profile")
        self.assertIn("Prospect does not have an Open Profile", res.get("error", ""))
        self.worker.send_inmail.assert_not_called()

    def test_limit_check_exception_for_free_inmails(self):
        """Limit Exception: Free InMails (is_open_profile=True) do NOT block when paid inmail limit is exhausted."""
        self.worker.send_inmail.return_value = {"status": "success"}
        with patch.object(self.executor, "_check_limit") as mock_limit:
            mock_limit.return_value = ("Daily limit reached for action: inmail", "2026-10-18")
            data = {
                "subject": "Greetings {{first_name}}",
                "body": "Hello Fiona",
                "first_name": "Fiona",
                "is_open_profile": True,
                "only_send_free_inmails": False
            }
            res = self.executor.handle_send_inmail(data, self.test_url)
            self.assertEqual(res.get("status"), "success")
            self.assertTrue(res.get("is_free_inmail"))
            self.assertEqual(res.get("inmail_tier"), "free")
            mock_limit.assert_not_called()
            self.worker.send_inmail.assert_called_once()

    def test_limit_check_enforced_for_paid_inmails(self):
        """Limit Enforcement: Standard paid InMails (is_open_profile=False) check limits and halt on exhaustion."""
        with patch.object(self.executor, "_check_limit") as mock_limit:
            mock_limit.return_value = ("Daily limit reached for action: inmail", "2026-10-18")
            data = {
                "subject": "Executive Pitch",
                "body": "Hello George",
                "is_open_profile": False,
                "fallback_to_connection_request": False
            }
            res = self.executor.handle_send_inmail(data, self.test_url)
            self.assertEqual(res.get("status"), "rate_limited")
            self.assertEqual(res.get("reason"), "inmail_exhausted")
            mock_limit.assert_called_once_with("inmail")
            self.worker.send_inmail.assert_not_called()

    def test_worker_free_inmail_discovery_updates_leads_table(self):
        """Telemetry: If worker discovers Free InMail on send, updates leads table and credits_saved=1."""
        self.worker.send_inmail.return_value = {"status": "success", "is_free_inmail": True}
        data = {
            "subject": "Quick Hello",
            "body": "Hey Helen!",
            "lead_id": "lead-helen-88"
        }
        res = self.executor.handle_send_inmail(data, self.test_url)
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(res.get("is_free_inmail"))
        self.assertEqual(res.get("credits_saved"), 1)
        self.supabase.table.assert_any_call("leads")
        self.supabase.table.return_value.update.assert_any_call({"is_open_profile": True})

    def test_handle_send_paid_inmail_delegation(self):
        """handle_send_paid_inmail delegates directly to handle_send_inmail."""
        self.worker.send_inmail.return_value = {"status": "success"}
        data = {
            "subject": "Paid Note",
            "body": "Content here",
            "first_name": "Ian"
        }
        res = self.executor.handle_send_paid_inmail(data, self.test_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_handle_open_profile_check_persists_to_leads_table(self):
        """handle_open_profile_check updates Supabase leads table when worker detects Open Profile."""
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Open"}
        data = {"lead_id": "lead-303"}
        res = self.executor.handle_open_profile_check(data, self.test_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Open")
        self.assertTrue(res.get("open"))
        self.supabase.table.assert_called_with("leads")
        self.supabase.table.return_value.update.assert_called_with({"is_open_profile": True})


if __name__ == "__main__":
    unittest.main()
