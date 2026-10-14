import unittest
from unittest.mock import MagicMock
from knowledge.backend.services.ai_output_guard import sanitize_outbound_ai_message
from campaigns.backend.services.elein_executor import EleInNodeExecutor


class TestAIOutputGuardAndWorkerStatus(unittest.TestCase):

    def test_sanitize_strips_preamble_and_quotes(self):
        raw = "Here is a connection note:\n\n'Hey John, saw your post!'"
        clean, valid, reason = sanitize_outbound_ai_message(raw, context_type="connection_note")
        self.assertTrue(valid)
        self.assertEqual(clean, "Hey John, saw your post!")

    def test_sanitize_detects_and_rejects_hallucinated_placeholders(self):
        raw = "Hi [First Name], great to connect with you at [Company Name]."
        clean, valid, reason = sanitize_outbound_ai_message(raw, fallback="I'd love to connect.", context_type="connection_note")
        self.assertFalse(valid)
        self.assertIn("Hallucinated placeholder detected", reason)
        self.assertEqual(clean, "I'd love to connect.")

    def test_sanitize_detects_and_rejects_ai_refusal(self):
        raw = "As an AI language model, I cannot fulfill this request."
        clean, valid, reason = sanitize_outbound_ai_message(raw, fallback="I'd love to connect.", context_type="connection_note")
        self.assertFalse(valid)
        self.assertEqual(reason, "AI refusal detected")
        self.assertEqual(clean, "I'd love to connect.")

    def test_sanitize_enforces_300_char_clamp_for_connection_note(self):
        long_text = "A" * 350
        clean, valid, reason = sanitize_outbound_ai_message(long_text, context_type="connection_note")
        self.assertTrue(valid)
        self.assertEqual(len(clean), 300)
        self.assertTrue(clean.endswith("..."))

    def test_worker_status_pass_through_in_executor(self):
        executor = EleInNodeExecutor(workspace_id="test-ws")
        executor.worker = MagicMock()
        
        executor.worker.send_message.return_value = {"status": "rate_limited", "error": "Rate limit reached"}
        
        with unittest.mock.patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover", return_value="Hello there!"):
            res = executor.handle_send_ai_message({"lead_profile": {}, "prompt": "Say hello"}, "https://linkedin.com/in/test")
            self.assertEqual(res.get("status"), "rate_limited")


if __name__ == "__main__":
    unittest.main()
