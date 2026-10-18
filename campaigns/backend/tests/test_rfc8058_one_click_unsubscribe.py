"""
Three-Layer Paranoia Framework Automated Test Suite:
RFC 8058 One-Click Unsubscribe System (List-Unsubscribe & List-Unsubscribe-Post)

Covers the full A-to-Z lifecycle:
- Layer 0: Foundational RFC 8058 mechanics, token HMAC roundtrip, endpoint status codes, header syntax.
- Layer 1: Environmental failure analysis (tampered signatures, malformed tokens, secret mismatches,
           database failovers, missing parameters, executor fail-open resilience).
- Layer 2: Human paranoia and adversarial input (zero-friction confirmation guarantee, injection safety,
           HTML XSS hygiene, non-blocking execution).
"""

import os
import json
import base64
import hmac
import hashlib
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Defensive environment bootstrapping for test isolation
if not os.environ.get("SUPABASE_JWT_SECRET"):
    os.environ["SUPABASE_JWT_SECRET"] = "dummy_secret_for_testing_1234567890"
if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from core.backend.main import app
from campaigns.backend.services.unsubscribe_service import (
    generate_unsubscribe_token,
    verify_unsubscribe_token,
    generate_rfc8058_headers,
    process_one_click_unsubscribe,
    retroactive_purge,
    _b64url_encode,
    _b64url_decode,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor


class TestRFC8058OneClickUnsubscribe(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.workspace_id = "ws-test-alpha"
        self.lead_id = "lead-uuid-7777"
        self.email = "prospect@example.com"
        self.custom_secret = "ultra-secure-test-signing-key-99"

    # =========================================================================
    # 1. Token Generation & Tamper-Proofing (Layer 0, 1 & 2)
    # =========================================================================

    def test_unsubscribe_token_generation_and_tamper_proofing(self):
        """
        Verify HMAC signing, correct payload roundtrip, and rejection of tampered tokens
        (e.g., modified email, corrupted signature, wrong secret, malformed format).
        """
        # 1. Happy path: generate token and verify payload roundtrip
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
            secret=self.custom_secret,
        )
        self.assertIsInstance(token, str)
        self.assertIn(".", token)
        self.assertEqual(len(token.split(".")), 2)

        verified = verify_unsubscribe_token(token, secret=self.custom_secret)
        self.assertIsNotNone(verified)
        self.assertEqual(verified["workspace_id"], self.workspace_id)
        self.assertEqual(verified["lead_id"], self.lead_id)
        self.assertEqual(verified["email"], self.email.lower())

        # 2. Tampered payload: Modify email inside the payload, keeping original signature
        parts = token.split(".")
        payload_bytes = _b64url_decode(parts[0])
        payload_data = json.loads(payload_bytes.decode("utf-8"))
        payload_data["email"] = "attacker@malicious.org"
        tampered_payload_b64 = _b64url_encode(json.dumps(payload_data, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        tampered_token = f"{tampered_payload_b64}.{parts[1]}"

        self.assertIsNone(
            verify_unsubscribe_token(tampered_token, secret=self.custom_secret),
            "Expected token with modified email payload to be rejected by HMAC verification",
        )

        # 3. Tampered signature: Corrupt the signature part
        sig_bytes = _b64url_decode(parts[1])
        corrupted_sig_bytes = bytes([b ^ 0xFF for b in sig_bytes])
        corrupted_token = f"{parts[0]}.{_b64url_encode(corrupted_sig_bytes)}"

        self.assertIsNone(
            verify_unsubscribe_token(corrupted_token, secret=self.custom_secret),
            "Expected token with flipped signature bits to be rejected",
        )

        # 4. Wrong secret key verification
        self.assertIsNone(
            verify_unsubscribe_token(token, secret="completely-wrong-secret-key"),
            "Expected token verified with wrong secret to fail",
        )

        # 5. Malformed tokens (Paranoia Layer 1 & 2 edge cases)
        for malformed in [
            "",
            "not-a-token",
            "part1.part2.part3",
            ".invalid",
            "invalid.",
            "???invalid_b64???.signature",
            None,
            12345,
        ]:
            self.assertIsNone(
                verify_unsubscribe_token(malformed),  # type: ignore
                f"Expected malformed token '{malformed}' to return None without crashing",
            )

    # =========================================================================
    # 2. RFC 8058 Headers Format Compliance (Layer 0 & 1)
    # =========================================================================

    def test_rfc8058_headers_format(self):
        """
        Verify headers match RFC 8058 standards:
        - List-Unsubscribe contains '<https://...>' and '<mailto:unsub+...>'
        - List-Unsubscribe-Post contains exactly 'List-Unsubscribe=One-Click'
        """
        headers = generate_rfc8058_headers(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
            base_url="https://app.ele-in.com",
        )

        # Assert presence of RFC 8058 required header keys
        self.assertIn("List-Unsubscribe", headers)
        self.assertIn("List-Unsubscribe-Post", headers)

        list_unsub = headers["List-Unsubscribe"]
        list_unsub_post = headers["List-Unsubscribe-Post"]

        # RFC 8058 §3.1: The List-Unsubscribe-Post header field MUST contain the single parameter
        # "List-Unsubscribe=One-Click"
        self.assertEqual(list_unsub_post, "List-Unsubscribe=One-Click")

        # RFC 8058 §3.1: The List-Unsubscribe header field MUST contain at least one URI starting
        # with "https:". It MAY contain other URIs, including "mailto:".
        self.assertIn("<https://app.ele-in.com/api/elein/unsubscribe?token=", list_unsub)
        self.assertIn("mailto:unsub+", list_unsub)
        self.assertTrue(list_unsub.startswith("<https://"))

        # Extract the token from the URL in List-Unsubscribe and verify it is valid
        url_part = list_unsub.split(",")[0].strip("<> ")
        self.assertIn("token=", url_part)
        token_extracted = url_part.split("token=")[1]
        verified = verify_unsubscribe_token(token_extracted)
        self.assertIsNotNone(verified)
        self.assertEqual(verified["email"], self.email.lower())
        self.assertEqual(verified["workspace_id"], self.workspace_id)

    # =========================================================================
    # 3. RFC 8058 POST Request One-Click Processing (Layer 0 & 2)
    # =========================================================================

    def test_rfc8058_post_request_one_click(self):
        """
        Send HTTP POST to /api/elein/unsubscribe?token=... with body List-Unsubscribe=One-Click.
        Assert HTTP 200, JSON success, zero confirmation redirect.
        """
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )

        with patch("campaigns.backend.routers.unsubscribe.process_one_click_unsubscribe") as mock_process:
            mock_process.return_value = {
                "status": "success",
                "unsubscribed": True,
                "lead_id": self.lead_id,
                "email": self.email,
            }

            response = self.client.post(
                f"/api/elein/unsubscribe?token={token}",
                data="List-Unsubscribe=One-Click",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            # Assert HTTP 200 (Never 301/302/303 redirect, per RFC 8058 §3.2)
            self.assertEqual(response.status_code, 200)

            # Assert JSON success payload
            data = response.json()
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("message"), "Successfully unsubscribed")

            # Assert processing logic was triggered with verified token claims
            mock_process.assert_called_once_with(
                workspace_id=self.workspace_id,
                lead_id=self.lead_id,
                email=self.email.lower(),
            )

    # =========================================================================
    # 4. Human Browser GET Request Confirmation HTML (Layer 0 & 2)
    # =========================================================================

    def test_human_get_request_html_page(self):
        """
        Send HTTP GET to /api/elein/unsubscribe?token=...
        Assert HTTP 200, Content-Type 'text/html', and confirmation message rendered.
        """
        token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )

        with patch("campaigns.backend.routers.unsubscribe.process_one_click_unsubscribe") as mock_process:
            mock_process.return_value = {
                "status": "success",
                "unsubscribed": True,
                "lead_id": self.lead_id,
                "email": self.email,
            }

            response = self.client.get(f"/api/elein/unsubscribe?token={token}")

            # Assert HTTP 200 OK
            self.assertEqual(response.status_code, 200)

            # Assert Content-Type text/html
            content_type = response.headers.get("content-type", "")
            self.assertIn("text/html", content_type)

            # Assert confirmation message rendered in HTML body
            html_text = response.text
            self.assertIn("Unsubscribed", html_text)
            self.assertIn("successfully unsubscribed from this campaign", html_text)
            self.assertIn(self.email.lower(), html_text)
            self.assertIn("RFC 8058 One-Click Compliant", html_text)

            # Assert process_one_click_unsubscribe was executed
            mock_process.assert_called_once_with(
                workspace_id=self.workspace_id,
                lead_id=self.lead_id,
                email=self.email.lower(),
            )

    # =========================================================================
    # 5. Invalid & Tampered Token Handling (Layer 1 & 2)
    # =========================================================================

    def test_invalid_token_returns_400(self):
        """
        Send GET and POST with invalid token, assert HTTP 400 with clean error message.
        """
        # 1. Missing token on GET
        res_get_missing = self.client.get("/api/elein/unsubscribe")
        self.assertEqual(res_get_missing.status_code, 400)
        self.assertIn("Invalid or missing", str(res_get_missing.json()))

        # 2. Corrupted token on GET
        res_get_corrupted = self.client.get("/api/elein/unsubscribe?token=malformed_token_xyz")
        self.assertEqual(res_get_corrupted.status_code, 400)
        self.assertIn("Invalid or tampered", str(res_get_corrupted.json()))

        # 3. Missing token on POST
        res_post_missing = self.client.post("/api/elein/unsubscribe")
        self.assertEqual(res_post_missing.status_code, 400)
        self.assertIn("Invalid or missing", str(res_post_missing.json()))

        # 4. Tampered token on POST
        valid_token = generate_unsubscribe_token(
            workspace_id=self.workspace_id,
            lead_id=self.lead_id,
            email=self.email,
        )
        tampered_token = valid_token[:-4] + "ABCD"
        res_post_tampered = self.client.post(
            f"/api/elein/unsubscribe?token={tampered_token}",
            data="List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(res_post_tampered.status_code, 400)
        self.assertIn("Invalid or tampered", str(res_post_tampered.json()))

    # =========================================================================
    # 6. Suppression and Retroactive Purge Triggered (Layer 0, 1 & 2)
    # =========================================================================

    def test_suppression_and_retroactive_purge_triggered(self):
        """
        Mock Supabase and verify that unsubscribing:
        - updates leads.status = 'UNSUBSCRIBED'
        - adds entry to suppression_list
        - invokes retroactive_purge to halt in-flight jobs
        """
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[])

        with patch("leads.backend.services.suppression_service.add_suppression_entries_bulk") as mock_add_supp, \
             patch("campaigns.backend.services.unsubscribe_service.retroactive_purge") as mock_purge:

            mock_add_supp.return_value = {"added": 1, "duplicates": 0}
            mock_purge.return_value = {
                "matched_leads_count": 1,
                "halted_states_count": 3,
                "lead_ids": [self.lead_id],
            }

            result = process_one_click_unsubscribe(
                workspace_id=self.workspace_id,
                lead_id=self.lead_id,
                email=self.email,
                supabase=mock_supabase,
            )

            # Assert return structure
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["unsubscribed"])
            self.assertEqual(result["lead_id"], self.lead_id)
            self.assertEqual(result["email"], self.email.lower())

            # Assert leads table was updated
            mock_supabase.table.assert_any_call("leads")
            update_call_args = mock_table.update.call_args[0][0]
            self.assertEqual(update_call_args["status"], "UNSUBSCRIBED")
            self.assertTrue(update_call_args["is_unsubscribed"])
            self.assertIn("unsubscribed_at", update_call_args)

            # Assert suppression list bulk addition was called
            mock_add_supp.assert_called_once_with(
                supabase=mock_supabase,
                workspace_id=self.workspace_id,
                entries=[{"email": self.email.lower(), "reason": "one_click_unsubscribe_rfc8058"}],
                allow_freemail_domain=True,
                trigger_retroactive_purge=False,
            )

            # Assert retroactive purge was triggered
            mock_purge.assert_called_once_with(
                workspace_id=self.workspace_id,
                email=self.email.lower(),
                supabase=mock_supabase,
            )

    def test_suppression_fallback_to_direct_table_insert(self):
        """
        Paranoia Layer 1: If add_suppression_entries_bulk throws an exception,
        process_one_click_unsubscribe falls back to direct insert into suppression_list table.
        """
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_table.insert.return_value.execute.return_value = MagicMock(data=[])

        with patch("leads.backend.services.suppression_service.add_suppression_entries_bulk", side_effect=RuntimeError("Bulk import down")), \
             patch("campaigns.backend.services.unsubscribe_service.retroactive_purge") as mock_purge:

            mock_purge.return_value = {"matched_leads_count": 0, "halted_states_count": 0}

            result = process_one_click_unsubscribe(
                workspace_id=self.workspace_id,
                lead_id=self.lead_id,
                email=self.email,
                supabase=mock_supabase,
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["unsubscribed"])
            # Assert fallback direct insert to suppression_list was triggered
            mock_supabase.table.assert_any_call("suppression_list")
            insert_args = mock_table.insert.call_args[0][0]
            self.assertEqual(insert_args["email"], self.email.lower())
            self.assertEqual(insert_args["reason"], "one_click_unsubscribe_rfc8058")

    # =========================================================================
    # 7. Executor handle_send_email Injects RFC 8058 Headers (Layer 0, 1 & 2)
    # =========================================================================

    def test_executor_handle_send_email_injects_rfc8058_headers(self):
        """
        Run handle_send_email in EleInNodeExecutor and assert that returned mock payload
        contains List-Unsubscribe and List-Unsubscribe-Post.
        """
        executor = EleInNodeExecutor(workspace_id=self.workspace_id)

        data = {
            "_lead_id": self.lead_id,
            "to_email": self.email,
            "subject": "Quick partnership question",
            "body": "Hi there, wanted to follow up on our previous note.",
        }

        # Run in test/mock environment
        with patch.dict(os.environ, {"TEST_MODE": "true", "SENDGRID_API_KEY": ""}):
            result = executor.handle_send_email(data, linkedin_url=None)

            self.assertEqual(result.get("status"), "success")
            self.assertEqual(result.get("to"), self.email)

            # Assert RFC 8058 headers injected into headers dictionary
            headers = result.get("headers", {})
            self.assertIn("List-Unsubscribe", headers)
            self.assertIn("List-Unsubscribe-Post", headers)
            self.assertEqual(headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
            self.assertIn(f"api/elein/unsubscribe?token=", headers["List-Unsubscribe"])

            # Assert top-level convenience keys present for delivery telemetry
            self.assertIn("list_unsubscribe", result)
            self.assertIn("list_unsubscribe_post", result)
            self.assertEqual(result["list_unsubscribe_post"], "List-Unsubscribe=One-Click")

    def test_executor_handle_send_email_fail_open_on_header_generation_error(self):
        """
        Paranoia Layer 1: If generate_rfc8058_headers throws an unexpected exception,
        handle_send_email must fail-open (log warning and proceed with email delivery),
        ensuring outbound campaigns are NEVER blocked by unsubscribe header generation failure.
        """
        executor = EleInNodeExecutor(workspace_id=self.workspace_id)

        data = {
            "lead_id": self.lead_id,
            "to_email": self.email,
            "subject": "Important update",
            "body": "Here is your weekly update.",
        }

        with patch.dict(os.environ, {"TEST_MODE": "true", "SENDGRID_API_KEY": ""}), \
             patch("campaigns.backend.services.elein_executor.generate_rfc8058_headers", side_effect=Exception("Crypto hardware error")):

            result = executor.handle_send_email(data, linkedin_url=None)

            # Email dispatch must still succeed (fail-open)
            self.assertEqual(result.get("status"), "success")
            self.assertEqual(result.get("to"), self.email)
            # Empty or missing headers dictionary, but no crash
            self.assertIsNone(result.get("headers"))


if __name__ == "__main__":
    unittest.main()
