import unittest
from unittest.mock import MagicMock, patch
import os
from core.backend.services.storage_service import (
    sanitize_filename,
    ensure_bucket_exists,
    upload_media_file,
)

class TestStorageService(unittest.TestCase):

    def test_sanitize_filename_blocks_traversal(self):
        dirty = "../../etc/passwd"
        clean = sanitize_filename(dirty)
        self.assertNotIn("..", clean)
        self.assertNotIn("/", clean)
        self.assertEqual(clean, "passwd")

        special = "file@name#with$special%chars*.mp3"
        clean_special = sanitize_filename(special)
        self.assertEqual(clean_special, "file_name_with_special_chars_.mp3")

    @patch("core.backend.services.storage_service.get_service_client")
    def test_ensure_bucket_exists_creates_bucket(self, mock_get_client):
        mock_supabase = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.name = "other-bucket"
        mock_supabase.storage.list_buckets.return_value = [mock_bucket]
        mock_get_client.return_value = mock_supabase

        import core.backend.services.storage_service as ss
        ss._verified_buckets.clear()

        res = ensure_bucket_exists("campaign-assets")
        self.assertTrue(res)
        mock_supabase.storage.create_bucket.assert_called_once_with(
            "campaign-assets", options={"public": True}
        )

    @patch("core.backend.services.storage_service.get_service_client")
    @patch("core.backend.services.storage_service.ensure_bucket_exists")
    def test_upload_media_file_cloud_success(self, mock_ensure, mock_get_client):
        mock_ensure.return_value = True
        mock_supabase = MagicMock()
        mock_supabase.storage.from_().get_public_url.return_value = "https://cdn.example.com/file.mp3"
        mock_get_client.return_value = mock_supabase

        content = b"fake audio content"
        result = upload_media_file(
            workspace_id="ws_123",
            content=content,
            original_filename="audio.mp3",
            folder="voice_notes",
            content_type="audio/mpeg"
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["url"], "https://cdn.example.com/file.mp3")
        self.assertEqual(result["size"], len(content))
        self.assertIn("hash", result)

    @patch("core.backend.services.storage_service.get_service_client")
    @patch("core.backend.services.storage_service.ensure_bucket_exists")
    def test_upload_media_file_fallback_to_local_on_error(self, mock_ensure, mock_get_client):
        mock_ensure.return_value = True
        mock_get_client.side_effect = Exception("Supabase connection failed")

        content = b"fallback content"
        result = upload_media_file(
            workspace_id="ws_123",
            content=content,
            original_filename="doc.pdf",
            folder="attachments",
            content_type="application/pdf"
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["url"].startswith("/api/elein/media/attachments/"))
        self.assertEqual(result["size"], len(content))

    @patch("core.backend.services.storage_service.get_service_client")
    @patch("core.backend.services.storage_service.ensure_bucket_exists")
    def test_upload_media_file_deduplication_hash(self, mock_ensure, mock_get_client):
        mock_ensure.return_value = True
        mock_supabase = MagicMock()
        mock_supabase.storage.from_().get_public_url.side_effect = lambda path: f"https://cdn.example.com/{path}"
        mock_get_client.return_value = mock_supabase

        content = b"identical content"
        res1 = upload_media_file("ws_1", content, "test.mp3", "voice_notes")
        res2 = upload_media_file("ws_1", content, "test.mp3", "voice_notes")

        self.assertEqual(res1["hash"], res2["hash"])
        self.assertIn(res1["hash"][:16], res1["url"])
        self.assertIn(res2["hash"][:16], res2["url"])

if __name__ == "__main__":
    unittest.main()
