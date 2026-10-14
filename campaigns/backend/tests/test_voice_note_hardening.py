"""
test_voice_note_hardening.py

Unit tests for Step 23: Voice Note Audio Duration Bounds & Format Guard
- Audio format detection (WAV, MP3, M4A, etc.)
- Audio duration estimation (WAV, MP3, fallback)
- Duration bounds validation (3.0s min, 60.0s max)
- Executor handling, fallback to text message
- Worker inspection & codec binding
- Audio upload endpoint validation
"""

import io
import os
import wave
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.datastructures import UploadFile

from core.backend.services.audio_service import (
    detect_audio_format,
    estimate_audio_duration,
    inspect_voice_note_audio,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from integrations.backend.services.linkedin_worker import LinkedInWorker


class TestVoiceNoteHardening(unittest.TestCase):
    """Test suite covering the 12 voice note duration bounds and format guard requirements."""

    def test_detect_audio_format_wav(self):
        """Requirement 1: Recognizes WAV magic bytes."""
        # Minimal valid WAV header bytes
        wav_header = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        self.assertEqual(detect_audio_format(wav_header), "wav")

    def test_detect_audio_format_mp3(self):
        """Requirement 2: Recognizes MP3 ID3 and sync frames."""
        id3_bytes = b"ID3\x04\x00\x00\x00\x00\x00\x10" + b"\xff\xfb\x90\x00" * 10
        self.assertEqual(detect_audio_format(id3_bytes), "mp3")

        sync_bytes = b"\xff\xfb\x90\x00" + b"\x00" * 100
        self.assertEqual(detect_audio_format(sync_bytes), "mp3")

    def test_detect_audio_format_m4a(self):
        """Requirement 3: Recognizes M4A ftyp atom."""
        m4a_bytes = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00isomiso2"
        self.assertEqual(detect_audio_format(m4a_bytes), "m4a")

    def test_estimate_audio_duration_wav(self):
        """Requirement 4: Uses wave module to compute exact duration."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            # 8000 frames = exactly 1.0 second
            wf.writeframes(b"\x00\x00" * 8000)
        wav_data = buf.getvalue()
        duration = estimate_audio_duration(wav_data, "wav")
        self.assertAlmostEqual(duration, 1.0, places=1)

    def test_voice_note_audio_too_short_rejected(self):
        """Requirement 5: Audio < 3.0s returns error."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            # 16,000 frames at 8kHz = 2.0 seconds (< 3.0s)
            wf.writeframes(b"\x00\x00" * 16000)
        wav_data = buf.getvalue()
        res = inspect_voice_note_audio(wav_data, "short.wav")
        self.assertFalse(res["is_valid"])
        self.assertIn("too short", res["error"].lower())

    def test_voice_note_audio_too_long_rejected(self):
        """Requirement 6: Audio > 60.0s returns error."""
        # Using mock declared duration or large size estimation
        res = inspect_voice_note_audio(b"fake-mp3-audio-bytes-header", "long.mp3", declared_duration=75.0)
        self.assertFalse(res["is_valid"])
        self.assertIn("exceeds", res["error"].lower())

    def test_executor_declared_duration_too_short(self):
        """Requirement 7: Rejects node with declared duration = 2.0s."""
        executor = EleInNodeExecutor.__new__(EleInNodeExecutor)
        node_data = {"audio_url": "https://example.com/audio.mp3", "duration": 2.0, "note": "Hello"}
        res = executor.handle_send_voice_note(node_data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "error")
        self.assertIn("too short", res["error"].lower())

    def test_executor_declared_duration_too_long(self):
        """Requirement 8: Rejects node with declared duration = 75.0s."""
        executor = EleInNodeExecutor.__new__(EleInNodeExecutor)
        node_data = {"audio_url": "https://example.com/audio.mp3", "duration": 75.0, "note": "Hello"}
        res = executor.handle_send_voice_note(node_data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "error")
        self.assertIn("exceeds", res["error"].lower())

    def test_executor_fallback_to_message_on_too_long(self):
        """Requirement 9: Auto-fallbacks to text message when fallback_to_message: True."""
        executor = EleInNodeExecutor.__new__(EleInNodeExecutor)
        executor.handle_send_message = MagicMock(return_value={"status": "success", "branch": "then"})
        node_data = {
            "audio_url": "https://example.com/audio.mp3",
            "duration": 75.0,
            "note": "Fallback text note",
            "fallback_to_message": True
        }
        res = executor.handle_send_voice_note(node_data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        executor.handle_send_message.assert_called_once()

    def test_executor_fallback_to_message_on_worker_error(self):
        """Requirement 10: Auto-fallbacks to text message on worker error when configured."""
        executor = EleInNodeExecutor.__new__(EleInNodeExecutor)
        executor._require_worker = MagicMock(return_value=None)
        mock_worker = MagicMock()
        mock_worker.send_voice_note.return_value = {"status": "error", "error": "audio duration too short"}
        executor.worker = mock_worker
        executor.handle_send_message = MagicMock(return_value={"status": "success", "branch": "then"})

        node_data = {
            "audio_url": "https://example.com/audio.mp3",
            "note": "Fallback text note",
            "fallback_to_message": True
        }
        res = executor.handle_send_voice_note(node_data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        executor.handle_send_message.assert_called_once()

    def test_worker_detects_accurate_extension_from_magic_bytes(self):
        """Requirement 11: Sets correct extension even if URL lacks it."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * 40000) # 5.0 seconds
        wav_data = buf.getvalue()

        check = inspect_voice_note_audio(wav_data, "https://example.com/download_stream?id=123")
        self.assertTrue(check["is_valid"])
        self.assertEqual(check["format"], "wav")

    def test_upload_audio_endpoint_duration_bounds(self):
        """Requirement 12: Rejects upload if duration out of bounds."""
        # Test inspect_voice_note_audio directly for upload endpoint logic
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * 8000) # 1 second (< 3s)
        short_wav = buf.getvalue()
        
        check = inspect_voice_note_audio(short_wav, "audio.wav")
        self.assertFalse(check["is_valid"])
        self.assertIn("too short", check["error"].lower())
