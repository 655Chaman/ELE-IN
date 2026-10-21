import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, UploadFile

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import router, upload_campaign_audio

class TestVoiceNoteExecutor(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_voice_001"
        self.supabase = MagicMock()
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data=True)
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws_voice_123"
        )
        self.test_lead_url = "https://www.linkedin.com/in/prospect-test"

    def test_missing_or_invalid_audio_url(self):
        """Layer 2 (Human Paranoia): User launches sequence with missing or invalid audio URL."""
        res_empty = self.executor.handle_send_voice_note({}, self.test_lead_url)
        self.assertEqual(res_empty.get("status"), "error")
        self.assertTrue(res_empty.get("requires_approval"))
        self.assertEqual(res_empty.get("branch"), Branch.FAILED.value)

        res_malformed = self.executor.handle_send_voice_note({"audio_url": "ftp://files.com/voice.mp3"}, self.test_lead_url)
        self.assertEqual(res_malformed.get("status"), "error")
        self.assertTrue(res_malformed.get("requires_approval"))

    def test_send_voice_note_success(self):
        """Layer 0 (Foundational): 1st-degree connection prospect receives audio voice note."""
        self.worker.send_voice_note.return_value = {"status": "success"}
        data = {
            "audio_url": "https://cdn.example.com/audio/intro_pitch.mp3",
            "note": "Hey Alex, recorded a quick audio note for you!"
        }
        res = self.executor.handle_send_voice_note(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertIn(res.get("branch"), ["Sent", "No reply yet"])
        self.worker.send_voice_note.assert_called_once_with(
            self.test_lead_url,
            "https://cdn.example.com/audio/intro_pitch.mp3",
            note="Hey Alex, recorded a quick audio note for you!"
        )

    def test_send_voice_note_with_relative_api_url(self):
        """Layer 0: Accepts locally hosted upload URLs starting with /api/."""
        self.worker.send_voice_note.return_value = {"status": "success"}
        data = {
            "audio_url": "/api/elein/media/voice_notes/ws_voice_123_test.mp3",
            "note": "Check out this memo"
        }
        res = self.executor.handle_send_voice_note(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.worker.send_voice_note.assert_called_once()

    def test_environmental_failure_auto_fallback_enabled(self):
        """Layer 1 (Environmental Failure): Lead is not 1st-degree (message modal missing).
        Auto-fallback to connection request succeeds seamlessly!"""
        self.worker.send_voice_note.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile. Lead may not be a 1st degree connection."
        }
        self.worker.send_connection_request.return_value = {"status": "success"}

        data = {
            "audio_url": "https://cdn.example.com/audio/intro.mp3",
            "note": "Loved your keynote at SaaStr!",
            "fallback_to_connection_request": True
        }
        res = self.executor.handle_send_voice_note(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Connection request sent")
        self.assertTrue(res.get("fallback"))
        self.assertEqual(res.get("action"), "connection_request")
        self.worker.send_connection_request.assert_called_once_with(
            self.test_lead_url,
            note="Loved your keynote at SaaStr!"
        )

    def test_environmental_failure_auto_fallback_disabled(self):
        """Layer 1: Auto-fallback explicitly disabled. Returns clear actionable error message."""
        self.worker.send_voice_note.return_value = {
            "status": "error",
            "error": "Message dialog not available on profile"
        }
        data = {
            "audio_url": "https://cdn.example.com/audio/intro.mp3",
            "fallback_to_connection_request": False
        }
        res = self.executor.handle_send_voice_note(data, self.test_lead_url)

        self.assertEqual(res.get("status"), "error")
        self.assertIn("not a 1st-degree connection", res.get("error", ""))
        self.assertEqual(res.get("branch"), Branch.FAILED.value)
        self.worker.send_connection_request.assert_not_called()

    def test_missing_worker_guard(self):
        """Layer 1: Missing worker or missing lead URL handled safely without crash."""
        executor_no_worker = EleInNodeExecutor(linkedin_worker=None, supabase=self.supabase)
        res = executor_no_worker.handle_send_voice_note(
            {"audio_url": "https://cdn.example.com/audio.mp3"},
            self.test_lead_url
        )
        self.assertEqual(res.get("status"), "error")
        self.assertIn("No LinkedIn worker", res.get("error"))


class TestVoiceNoteAudioUploadEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_upload_valid_audio_file(self):
        """Layer 0: Uploads valid audio file and returns permanent URL."""
        mock_file = MagicMock()
        mock_file.filename = "memo_recording.mp3"
        mock_file.content_type = "audio/mpeg"
        mock_file.read = AsyncMock(return_value=b"fake-mp3-audio-bytes-header")

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.upload.return_value = True
        mock_supabase.storage.from_.return_value.get_public_url.return_value = "https://supabase.co/storage/v1/object/public/campaign-assets/ws_1/audio.mp3"

        res = await upload_campaign_audio(
            file=mock_file,
            supabase=mock_supabase,
            workspace_id="ws_123",
            user_id="user_abc"
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("audio.mp3", res["url"])
        self.assertEqual(res["filename"], "memo_recording.mp3")
        self.assertGreater(res["size"], 0)

    async def test_upload_invalid_file_extension(self):
        """Layer 2 (Paranoia): Rejects non-audio extensions (.sh, .exe, .pdf)."""
        from fastapi import HTTPException
        mock_file = MagicMock()
        mock_file.filename = "malicious_script.sh"
        mock_file.content_type = "text/x-shellscript"

        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            await upload_campaign_audio(
                file=mock_file,
                supabase=mock_supabase,
                workspace_id="ws_123",
                user_id="user_abc"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid audio format", ctx.exception.detail)

    async def test_upload_exceeds_size_limit(self):
        """Layer 1: Caps file size at 25MB (returns HTTP 413)."""
        from fastapi import HTTPException
        mock_file = MagicMock()
        mock_file.filename = "huge_audiobook.mp3"
        mock_file.content_type = "audio/mpeg"
        # 26MB dummy bytes
        huge_bytes = b"0" * (26 * 1024 * 1024)
        mock_file.read = AsyncMock(return_value=huge_bytes)

        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            await upload_campaign_audio(
                file=mock_file,
                supabase=mock_supabase,
                workspace_id="ws_123",
                user_id="user_abc"
            )
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("exceeds 25MB limit", ctx.exception.detail)


if __name__ == '__main__':
    unittest.main()
