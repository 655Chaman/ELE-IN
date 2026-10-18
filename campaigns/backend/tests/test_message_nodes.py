import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import upload_campaign_attachment

class TestMessageNodesExecutor(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_msg_001"
        self.supabase = MagicMock()
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data=True)
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws_msg_123"
        )
        self.test_lead_url = "https://www.linkedin.com/in/prospect-active"

    def test_variable_interpolation_in_send_message(self):
        """Layer 0 (Foundational): Variables {{first_name}} and {{company}} are interpolated correctly."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "body": "Hi {{first_name}}, big fan of your team at {{company}}!",
            "variables": {
                "first_name": "Sarah",
                "company": "Acme Corp"
            }
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message.assert_called_once_with(
            self.test_lead_url,
            "Hi Sarah, big fan of your team at Acme!"
        )

    def test_empty_body_fallback_resolution(self):
        """Layer 1: Empty primary body seamlessly falls back to human fallback message."""
        self.worker.send_message.return_value = {"status": "success"}
        data = {
            "body": "   ",
            "fallback": "Hello {{first_name}}, following up on our sync.",
            "variables": {"first_name": "Jordan"}
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message.assert_called_once_with(
            self.test_lead_url,
            "Hello Jordan, following up on our sync."
        )

    def test_empty_body_and_empty_fallback_fails_closed(self):
        """Layer 2 (Paranoia): Blank message with no fallback fails closed before reaching worker."""
        data = {"body": "", "fallback": ""}
        res = self.executor.handle_send_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("requires_approval"))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.worker.send_message.assert_not_called()

    def test_send_message_with_attachment_dispatch(self):
        """Layer 0: Dispatches with attachment when attachment_url is provided."""
        self.worker.send_message_with_attachment.return_value = {"status": "success"}
        data = {
            "body": "Here is our latest deck",
            "attachment_url": "/api/elein/media/attachments/ws_deck.pdf",
            "attachment_type": "Document"
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message_with_attachment.assert_called_once_with(
            self.test_lead_url,
            "Here is our latest deck",
            "/api/elein/media/attachments/ws_deck.pdf",
            "Document"
        )

    def test_environmental_failure_auto_fallback_to_connection(self):
        """Layer 1: Message dialog unavailable on profile triggers auto-fallback to connection request."""
        self.worker.send_message.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile. Lead may not be a 1st degree connection."
        }
        self.worker.send_connection_request.return_value = {"status": "success"}

        data = {
            "body": "Loved your keynote at the conference!",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Connection request sent")
        self.assertTrue(res.get("fallback"))
        self.assertEqual(res.get("action"), "connection_request")
        self.worker.send_connection_request.assert_called_once_with(
            self.test_lead_url,
            note="Loved your keynote at the conference!"
        )

    def test_environmental_failure_auto_fallback_disabled(self):
        """Layer 1: Auto-fallback explicitly disabled produces clear error."""
        self.worker.send_message.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile"
        }
        data = {
            "body": "Check this out",
            "fallback_to_connection_request": False
        }
        res = self.executor.handle_send_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "error")
        self.assertIn("not a 1st-degree connection", res.get("error", ""))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.worker.send_connection_request.assert_not_called()

    def test_message_variants_delegation(self):
        """Layer 0: All message variants (doc, image, followup, intro) advance with Branch.SENT."""
        self.worker.send_message.return_value = {"status": "success"}
        self.worker.send_message_with_attachment.return_value = {"status": "success"}

        res_doc = self.executor.handle_send_message_with_doc(
            {"body": "Doc memo", "doc_url": "https://cdn.com/one-pager.pdf"},
            self.test_lead_url
        )
        self.assertEqual(res_doc.get("branch"), Branch.SENT.value)

        res_img = self.executor.handle_send_message_with_image(
            {"body": "Infographic", "image_url": "https://cdn.com/chart.png"},
            self.test_lead_url
        )
        self.assertEqual(res_img.get("branch"), Branch.SENT.value)

        res_followup = self.executor.handle_send_followup(
            {"body": "Following up"},
            self.test_lead_url
        )
        self.assertEqual(res_followup.get("branch"), Branch.SENT.value)

    @patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover")
    def test_send_ai_message_fallback_when_llm_empty(self, mock_llm):
        """Layer 1: AI message generation failure uses human fallback message."""
        mock_llm.return_value = ""  # LLM failure or timeout
        self.worker.send_message.return_value = {"status": "success"}

        data = {
            "pitch": "Pitch our analytics tool",
            "fallback": "Quick note regarding analytics at {{company}}",
            "variables": {"company": "DataCorp"}
        }
        res = self.executor.handle_send_ai_message(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.SENT.value)
        self.worker.send_message.assert_called_once_with(
            self.test_lead_url,
            "Quick note regarding analytics at DataCorp"
        )


class TestAttachmentUploadEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_upload_valid_document(self):
        """Layer 0: Uploads PDF document and returns durable media URL."""
        mock_file = MagicMock()
        mock_file.filename = "pitch_deck.pdf"
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=b"%PDF-1.4 sample content")

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.upload.return_value = True
        mock_supabase.storage.from_.return_value.get_public_url.return_value = "https://supabase.co/storage/v1/object/public/campaign-assets/ws_1/deck.pdf"

        res = await upload_campaign_attachment(
            file=mock_file,
            supabase=mock_supabase,
            workspace_id="ws_attach_123",
            user_id="user_attach"
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("deck.pdf", res["url"])
        self.assertEqual(res["attachment_type"], "document")
        self.assertEqual(res["filename"], "pitch_deck.pdf")

    async def test_upload_valid_image(self):
        """Layer 0: Uploads image and sets attachment_type='image'."""
        mock_file = MagicMock()
        mock_file.filename = "architecture.png"
        mock_file.content_type = "image/png"
        mock_file.read = AsyncMock(return_value=b"\x89PNG sample bytes")

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.upload.return_value = True
        mock_supabase.storage.from_.return_value.get_public_url.return_value = ""

        res = await upload_campaign_attachment(
            file=mock_file,
            supabase=mock_supabase,
            workspace_id="ws_attach_123",
            user_id="user_attach"
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("/api/elein/media/attachments/", res["url"])
        self.assertEqual(res["attachment_type"], "image")

    async def test_upload_invalid_extension_rejected(self):
        """Layer 2 (Paranoia): Disallowed extension (.exe) rejected with HTTP 400."""
        mock_file = MagicMock()
        mock_file.filename = "trojan.exe"
        mock_file.content_type = "application/x-msdownload"

        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            await upload_campaign_attachment(
                file=mock_file,
                supabase=mock_supabase,
                workspace_id="ws_1",
                user_id="user_1"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid attachment format", ctx.exception.detail)

    async def test_upload_exceeds_size_cap(self):
        """Layer 1: Rejects attachment exceeding 25MB with HTTP 413."""
        mock_file = MagicMock()
        mock_file.filename = "heavy_video.pdf"
        mock_file.content_type = "application/pdf"
        huge_bytes = b"X" * (26 * 1024 * 1024)
        mock_file.read = AsyncMock(return_value=huge_bytes)

        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            await upload_campaign_attachment(
                file=mock_file,
                supabase=mock_supabase,
                workspace_id="ws_1",
                user_id="user_1"
            )
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("exceeds 25MB limit", ctx.exception.detail)


if __name__ == '__main__':
    unittest.main()
