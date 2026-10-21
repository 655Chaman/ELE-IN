"""
Unit tests for inbox outbound email service: live Resend/SendGrid and graceful test mode.
"""
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

from inbox.backend.services.email_service import send_outbound_email


class TestInboxOutboundEmailService(unittest.TestCase):
    def setUp(self):
        self.mock_supabase = MagicMock()

    @patch("inbox.backend.services.email_service.get_service_client")
    @patch("inbox.backend.services.email_service.RESEND_API_KEY", "re_test_key_123")
    @patch("urllib.request.urlopen")
    def test_send_outbound_email_via_resend(self, mock_urlopen, mock_get_client):
        mock_get_client.return_value = self.mock_supabase
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"id": "resend_msg_abc123"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = send_outbound_email(
            match_id="match-1",
            to_email="prospect@company.com",
            subject="Demo follow up",
            html_body="<p>Great chatting today!</p>",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["message_id"], "resend_msg_abc123")
        self.mock_supabase.table.return_value.insert.assert_called_once()
        inserted = self.mock_supabase.table.return_value.insert.call_args[0][0]
        self.assertEqual(inserted["status"], "sent")
        self.assertEqual(inserted["message_id"], "resend_msg_abc123")

    @patch("inbox.backend.services.email_service.get_service_client")
    @patch("inbox.backend.services.email_service.RESEND_API_KEY", None)
    @patch("inbox.backend.services.email_service.SENDGRID_API_KEY", "SG.test_key_456")
    @patch("urllib.request.urlopen")
    def test_send_outbound_email_via_sendgrid(self, mock_urlopen, mock_get_client):
        mock_get_client.return_value = self.mock_supabase
        mock_resp = MagicMock()
        mock_resp.status = 202
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = send_outbound_email(
            match_id="match-2",
            to_email="lead@startup.io",
            subject="Pricing info",
            html_body="<p>Attached is the pricing matrix.</p>",
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["message_id"].startswith("sg_"))
        self.mock_supabase.table.return_value.insert.assert_called_once()
        inserted = self.mock_supabase.table.return_value.insert.call_args[0][0]
        self.assertEqual(inserted["status"], "sent")

    @patch("inbox.backend.services.email_service.get_service_client")
    @patch("inbox.backend.services.email_service.RESEND_API_KEY", None)
    @patch("inbox.backend.services.email_service.SENDGRID_API_KEY", None)
    def test_send_outbound_email_sandbox_fallback(self, mock_get_client):
        mock_get_client.return_value = self.mock_supabase

        res = send_outbound_email(
            match_id="match-3",
            to_email="sandbox@test.local",
            subject="Test mode message",
            html_body="<p>Hello sandbox</p>",
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["message_id"].startswith("msg_"))
        self.mock_supabase.table.return_value.insert.assert_called_once()
        inserted = self.mock_supabase.table.return_value.insert.call_args[0][0]
        self.assertEqual(inserted["status"], "sent")


if __name__ == "__main__":
    unittest.main()
