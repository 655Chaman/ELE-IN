import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from campaigns.backend.services.unsubscribe_service import (
    generate_unsubscribe_token,
    verify_unsubscribe_token,
    generate_rfc8058_headers,
    retroactive_purge,
    process_one_click_unsubscribe,
)
from campaigns.backend.routers.unsubscribe import router
from core.backend.main import app, detect_route_collisions


class TestRFC8058Unsubscribe(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-test-8058"
        self.lead_id = "lead-test-8058"
        self.email = "prospect@enterprise.com"
        self.client = TestClient(app)

    def test_token_generation_and_verification_cycle(self):
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )
        self.assertIsInstance(token, str)
        self.assertIn(".", token)
        self.assertEqual(len(token.split(".")), 2)

        verified = verify_unsubscribe_token(token)
        self.assertIsNotNone(verified)
        self.assertEqual(verified["workspace_id"], self.workspace_id)
        self.assertEqual(verified["lead_id"], self.lead_id)
        self.assertEqual(verified["email"], self.email)

    def test_token_verification_rejects_tampered_token(self):
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )
        # Tamper signature part
        payload_b64, sig_b64 = token.split(".")
        tampered_sig = sig_b64[:-1] + ("x" if sig_b64[-1] != "x" else "y")
        tampered_token = f"{payload_b64}.{tampered_sig}"

        self.assertIsNone(verify_unsubscribe_token(tampered_token))
        self.assertIsNone(verify_unsubscribe_token("invalid-token-without-dot"))
        self.assertIsNone(verify_unsubscribe_token(""))
        self.assertIsNone(verify_unsubscribe_token(None))

    def test_token_verification_rejects_different_secret(self):
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
            secret="secret-key-alpha",
        )
        self.assertIsNone(verify_unsubscribe_token(token, secret="secret-key-beta"))
        verified = verify_unsubscribe_token(token, secret="secret-key-alpha")
        self.assertIsNotNone(verified)
        self.assertEqual(verified["email"], self.email)

    def test_rfc8058_headers_generation(self):
        headers = generate_rfc8058_headers(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
            base_url="https://app.ele-in.com",
        )
        self.assertIn("List-Unsubscribe", headers)
        self.assertIn("List-Unsubscribe-Post", headers)
        self.assertEqual(headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")

        list_unsub = headers["List-Unsubscribe"]
        self.assertTrue(list_unsub.startswith("<https://app.ele-in.com/api/elein/unsubscribe?token="))
        self.assertIn("mailto:unsub+", list_unsub)
        self.assertIn("@ele-in.com>", list_unsub)

    def test_retroactive_purge_invokes_suppression_service(self):
        mock_supabase = MagicMock()
        with patch("leads.backend.services.suppression_service.retroactive_purge_suppressed_leads") as mock_purge:
            mock_purge.return_value = {
                "matched_leads_count": 1,
                "halted_states_count": 1,
                "lead_ids": [self.lead_id],
            }
            res = retroactive_purge(
                workspace_id=self.workspace_id,
                email=self.email,
                supabase=mock_supabase,
            )
            self.assertEqual(res["matched_leads_count"], 1)
            self.assertEqual(res["halted_states_count"], 1)
            mock_purge.assert_called_once_with(
                supabase=mock_supabase,
                workspace_id=self.workspace_id,
                emails=[self.email],
            )

    def test_process_one_click_unsubscribe_database_flow(self):
        mock_supabase = MagicMock()
        mock_leads_table = MagicMock()
        mock_supabase.table.return_value = mock_leads_table

        with patch("leads.backend.services.suppression_service.add_suppression_entries_bulk") as mock_bulk, \
             patch("campaigns.backend.services.unsubscribe_service.retroactive_purge") as mock_purge:
            mock_bulk.return_value = {"status": "success", "inserted_count": 1}
            mock_purge.return_value = {"matched_leads_count": 1, "halted_states_count": 1, "lead_ids": [self.lead_id]}

            res = process_one_click_unsubscribe(
                workspace_id=self.workspace_id,
                lead_id=self.lead_id,
                email=self.email,
                supabase=mock_supabase,
            )

            self.assertEqual(res["status"], "success")
            self.assertTrue(res["unsubscribed"])
            self.assertEqual(res["lead_id"], self.lead_id)
            self.assertEqual(res["email"], self.email)

            # Check leads table update was called
            self.assertTrue(mock_supabase.table.called)
            mock_purge.assert_called_once_with(
                workspace_id=self.workspace_id,
                email=self.email,
                supabase=mock_supabase,
            )

    def test_post_rfc8058_unsubscribe_endpoint_success(self):
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )

        with patch("campaigns.backend.routers.unsubscribe.process_one_click_unsubscribe") as mock_process:
            mock_process.return_value = {"status": "success", "unsubscribed": True}

            # Test /api/elein/unsubscribe
            resp = self.client.post(
                f"/api/elein/unsubscribe?token={token}",
                data="List-Unsubscribe=One-Click",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"status": "success", "message": "Successfully unsubscribed"})
            self.assertEqual(mock_process.call_count, 1)

            # Test root /unsubscribe
            resp2 = self.client.post(
                f"/unsubscribe?token={token}",
                data="List-Unsubscribe=One-Click",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            self.assertEqual(resp2.status_code, 200)
            self.assertEqual(resp2.json(), {"status": "success", "message": "Successfully unsubscribed"})
            self.assertEqual(mock_process.call_count, 2)

    def test_post_rfc8058_unsubscribe_endpoint_rejects_bad_token(self):
        resp = self.client.post(
            "/api/elein/unsubscribe?token=malformed.token",
            data="List-Unsubscribe=One-Click",
        )
        self.assertEqual(resp.status_code, 400)

        resp2 = self.client.post(
            "/api/elein/unsubscribe",
            data="List-Unsubscribe=One-Click",
        )
        self.assertEqual(resp2.status_code, 400)

    def test_get_unsubscribe_endpoint_success(self):
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )

        with patch("campaigns.backend.routers.unsubscribe.process_one_click_unsubscribe") as mock_process:
            mock_process.return_value = {"status": "success", "unsubscribed": True}

            # Test /api/elein/unsubscribe
            resp = self.client.get(f"/api/elein/unsubscribe?token={token}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            self.assertIn("You have been successfully unsubscribed from this campaign.", resp.text)
            self.assertIn(self.email, resp.text)

            # Test root /unsubscribe
            resp2 = self.client.get(f"/unsubscribe?token={token}")
            self.assertEqual(resp2.status_code, 200)
            self.assertIn("text/html", resp2.headers["content-type"])
            self.assertIn("You have been successfully unsubscribed from this campaign.", resp2.text)

    def test_get_unsubscribe_endpoint_rejects_bad_token(self):
        resp = self.client.get("/api/elein/unsubscribe?token=tampered_or_invalid")
        self.assertEqual(resp.status_code, 400)

        resp2 = self.client.get("/unsubscribe")
        self.assertEqual(resp2.status_code, 400)

    def test_zero_route_collisions(self):
        # Must execute detect_route_collisions() without raising or exiting
        detect_route_collisions()


if __name__ == "__main__":
    unittest.main()
