import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import re
import os

from knowledge.backend.services.ai_output_guard import (
    sanitize_outbound_ai_message,
    _clamp_text,
    PLACEHOLDER_PATTERN,
    REFUSAL_PATTERN,
    PREAMBLE_PATTERNS,
    AI_SLOP_PATTERNS
)
from knowledge.backend.services.copywriting_service import (
    get_llm_client,
    write_copy_for_pipeline,
    CopywritingResult
)
from knowledge.backend.services.llm_generator import LLMGenerator


class TestStage23EliteAIArchitecture(unittest.TestCase):
    """
    Stage 23: Elite Distributed AI Architecture Test Suite
    Tests strictly the AI side of the platform under the Three-Layer Logic Architecture (Paranoia Framework):
    - Outbound AI Message & Connection Note Output Guard
    - Markdown Link Preservation vs. Hallucinated Placeholder Rejection
    - Real-Time AI Slop and Conversational Preamble Neutralization
    - Multi-Tenant BYOK Key Resolution with NVIDIA Llama-3.3 Failover
    - Teleprompter Streaming Buffer Guard
    """

    # ─── 1. MARKDOWN LINK PRESERVATION VS PLACEHOLDER CIRCUIT-BREAKER ────────

    def test_markdown_links_preserved_without_false_placeholder_trigger(self):
        """
        Layer 0 & Layer 1 Paranoia:
        Valid markdown links containing words like [case study link](https://...) or [calendly](https://...)
        MUST NOT be falsely flagged as hallucinated placeholders.
        """
        raw_msg = (
            "Hi Sarah, loved your team's expansion! You can see our latest results in this "
            "[case study link](https://elesium.io/case-study) or grab 10 mins on my "
            "[calendar link](https://calendly.com/founder/10min)."
        )
        clean, valid, reason = sanitize_outbound_ai_message(raw_msg, context_type="message")
        self.assertTrue(valid, f"Expected valid message but rejected with reason: {reason}")
        self.assertEqual(reason, "OK")
        self.assertIn("[case study link](https://elesium.io/case-study)", clean)
        self.assertIn("[calendar link](https://calendly.com/founder/10min)", clean)

    def test_hallucinated_placeholders_rejected_comprehensively(self):
        """
        Layer 1 Paranoia:
        Bracketed placeholders hallucinated by LLMs must be rejected across all common variations.
        """
        bad_examples = [
            ("Hi [First Name], reaching out regarding your role.", "[First Name]"),
            ("Loved your work at [Target Company].", "[Target Company]"),
            ("We can help improve your [ROI].", "[ROI]"),
            ("Let's discuss your [Pain Point] next week.", "[Pain Point]"),
            ("Check out our [Booking Link] for a demo.", "[Booking Link]"),
            ("Here is the [Metric] you asked about.", "[Metric]"),
            ("Here is our [Call to action] for Q4.", "[Call to action]"),
            ("Hey {{first_name}}, saw your profile.", "{{first_name}}"),
        ]

        for text, placeholder in bad_examples:
            clean, valid, reason = sanitize_outbound_ai_message(
                text,
                fallback="I'd love to connect.",
                context_type="message"
            )
            self.assertFalse(valid, f"Expected rejection for: {placeholder}")
            self.assertEqual(clean, "I'd love to connect.")

    # ─── 2. AI REFUSAL & CONVERSATIONAL PREAMBLE STRIPPING ────────────────────

    def test_ai_refusal_circuit_breaker(self):
        """
        Layer 1 Paranoia:
        AI refusal phrases must be intercepted immediately, preventing embarrassing AI disclaimers from reaching leads.
        """
        refusals = [
            "As an AI language model, I cannot provide outreach advice for this prospect.",
            "As a helpful assistant, I am unable to write cold emails for unverified domains.",
            "I apologize, but my programming prevents me from generating outreach.",
            "This request violates our safety policies and cannot be completed.",
        ]
        for ref in refusals:
            clean, valid, reason = sanitize_outbound_ai_message(
                ref,
                fallback="I noticed your impressive background.",
                context_type="connection_note"
            )
            self.assertFalse(valid)
            self.assertEqual(reason, "AI refusal detected")
            self.assertEqual(clean, "I noticed your impressive background.")

    def test_conversational_preamble_and_zero_width_stripping(self):
        """
        Layer 0 & Layer 2 Paranoia:
        Conversational preambles, postamble commentary, and hidden zero-width / bidi characters
        must be stripped cleanly.
        """
        # Hidden zero-width space and conversational preamble
        raw = "Sure, here is your draft message:\n\u200bHey Alex, saw your keynote at SaaStr!\n\nHope this helps!"
        clean, valid, reason = sanitize_outbound_ai_message(raw, context_type="connection_note")
        self.assertTrue(valid)
        self.assertEqual(clean, "Hey Alex, saw your keynote at SaaStr!")
        self.assertNotIn("Sure, here is", clean)
        self.assertNotIn("Hope this helps", clean)
        self.assertNotIn("\u200b", clean)

    # ─── 3. FORMULA INJECTION & WORD-BOUNDARY CLAMPING ───────────────────────

    def test_formula_injection_sanitization(self):
        """
        Layer 2 Paranoia:
        Messages starting with '=', '+', '-', '@' must have dangerous formula prefixes removed.
        """
        raw = "=cmd|' /C calc'!A0 Hey Alex, loved your post on distributed systems."
        clean, valid, reason = sanitize_outbound_ai_message(raw, context_type="message")
        self.assertTrue(valid)
        self.assertFalse(clean.startswith("="))
        self.assertTrue(clean.startswith("cmd|") or clean.startswith("Hey Alex"))

    def test_word_boundary_aware_clamping(self):
        """
        Layer 2 Human Paranoia:
        Clamping must break on clean word boundaries rather than cutting words in half.
        """
        long_sentence = (
            "We help high-growth SaaS engineering teams streamline developer productivity, "
            "eliminate flaky tests, and deliver enterprise-grade software with zero regressions "
            "across all distributed customer deployments in North America and Western Europe."
        )
        clamped = _clamp_text(long_sentence, limit=120)
        self.assertLessEqual(len(clamped), 120)
        self.assertTrue(clamped.endswith("..."))
        # Ensure it didn't slice a word mid-letters (before ellipsis should be a complete word)
        before_ellipsis = clamped[:-3]
        self.assertFalse(before_ellipsis.endswith(" "))
        last_word = before_ellipsis.split()[-1]
        self.assertTrue(last_word.isalpha(), f"Expected whole word before ellipsis but got '{last_word}'")

    # ─── 4. AI SLOP PHRASE SCRUBBING & BANNED PHRASES ────────────────────────

    def test_ai_slop_and_banned_phrases_scrubbing(self):
        """
        Layer 1 & Layer 2 Paranoia:
        Common AI slop phrases and custom workspace banned keywords must be excised cleanly.
        """
        slop_msg = (
            "Hi David, I hope this email finds you well. In today's fast-paced world, "
            "we provide a game-changing platform to revolutionize your workflow."
        )
        clean, valid, reason = sanitize_outbound_ai_message(
            slop_msg,
            banned_phrases="revolutionize",
            strict_slop_mode=False
        )
        self.assertTrue(valid)
        self.assertNotIn("I hope this email finds you well", clean)
        self.assertNotIn("In today's fast-paced world", clean)
        self.assertNotIn("game-changing", clean)
        self.assertNotIn("revolutionize", clean)

    # ─── 5. MULTI-TENANT BYOK & NVIDIA KEY RESOLUTION ────────────────────────

    @patch("integrations.backend.services.credential_vault.vault.resolve_credential")
    @patch("knowledge.backend.services.copywriting_service.get_current_keys")
    def test_llm_client_nvidia_failover_routing(self, mock_get_keys, mock_resolve_cred):
        """
        Layer 0 & Layer 1 Paranoia:
        When an NVIDIA API key is configured (starts with nvapi-), get_llm_client
        must direct the client to https://integrate.api.nvidia.com/v1 with Llama-3.3.
        """
        mock_resolve_cred.return_value = None
        mock_get_keys.return_value = {
            "api_key_nvidia": "nvapi-test-secret-key-12345",
            "llm_provider": "nvidia",
            "llm_model": "meta/llama-3.3-70b-instruct"
        }

        client, model = get_llm_client(workspace_id="ws-test")
        self.assertIsNotNone(client)
        self.assertEqual(model, "meta/llama-3.3-70b-instruct")
        self.assertEqual(str(client.base_url).rstrip("/"), "https://integrate.api.nvidia.com/v1")

    # ─── 6. STRUCTURED OUTPUT FALLBACK & OUTPUT GUARD INTEGRATION ────────────

    @patch("knowledge.backend.services.copywriting_service.get_service_client")
    @patch("knowledge.backend.services.copywriting_service.get_llm_client")
    @patch("core.backend.services.credit_service.refund_credits")
    def test_copywriting_rejects_hallucinated_copy_and_refunds(self, mock_refund, mock_get_llm, mock_get_supabase):
        """
        Layer 1 & Layer 2 Paranoia:
        When the LLM returns copy with hallucinated bracketed placeholders,
        sanitize_outbound_ai_message rejects it and pro-rata credit refund is triggered.
        """
        mock_supabase = MagicMock()
        mock_client = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_get_llm.return_value = (mock_client, "gpt-4o-mini")

        mock_pipe_res = MagicMock(data=[{"workspace_id": "ws-stage23"}])
        mock_leads_res = MagicMock(data=[
            {"id": "lead-slop", "company_name": "Initech", "kdm_first": "Peter"}
        ])

        select_call_count = 0
        def fake_select(*args, **kwargs):
            nonlocal select_call_count
            select_call_count += 1
            ret = MagicMock()
            if select_call_count == 1:
                ret.eq.return_value.limit.return_value.execute.return_value = mock_pipe_res
            else:
                ret.eq.return_value.eq.return_value.execute.return_value = mock_leads_res
            return ret

        mock_supabase.table.return_value.select = fake_select
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True, "balance": 50})

        # Mock LLM returning copy with hallucinated placeholder
        mock_msg = MagicMock()
        mock_msg.parsed = CopywritingResult(
            subject_line="quick question for [Company Name]",
            email_body="Hey Peter, saw your work at [Company Name]. Would love to share our [Booking Link]."
        )
        mock_client.beta.chat.completions.parse.return_value = MagicMock(choices=[MagicMock(message=mock_msg)])

        write_copy_for_pipeline("pipe-test-slop")

        # Verify pro-rata refund was called for the rejected lead
        mock_refund.assert_called_once()
        refund_args = mock_refund.call_args[1]
        self.assertEqual(refund_args["workspace_id"], "ws-stage23")
        self.assertEqual(refund_args["amount"], 1)
        self.assertEqual(refund_args["reason"], "copywriting_partial_failure")

    # ─── 7. BYOK NVIDIA VALIDATION & CREDENTIAL VAULT SUPPORT ────────────────

    def test_byok_nvidia_validation_and_credential_vault_support(self):
        """
        Layer 0 & Layer 2 Paranoia:
        Verifies BYOK vault validates NVIDIA keys starting with 'nvapi-' and rejects invalid keys,
        and ensures CredentialVault includes 'nvidia' in its provider registry.
        """
        from knowledge.backend.services.byok_vault import validate_byok_key, InvalidKeyFormatError
        from integrations.backend.services.credential_vault import PROVIDER_KEY_MAP

        # 1. Valid NVIDIA key passes
        valid_nv = "nvapi-1234567890abcdef1234567890abcdef1234"
        clean = validate_byok_key("nvidia", valid_nv)
        self.assertEqual(clean, valid_nv)

        # 2. Invalid NVIDIA key format rejected
        with self.assertRaises(InvalidKeyFormatError):
            validate_byok_key("nvidia", "sk-invalid-nvidia-key")

        with self.assertRaises(InvalidKeyFormatError):
            validate_byok_key("nvidia", "nvapi-short")

        # 3. CredentialVault registry contains nvidia
        self.assertIn("nvidia", PROVIDER_KEY_MAP)
        self.assertEqual(PROVIDER_KEY_MAP["nvidia"]["column"], "api_key_nvidia")
        self.assertEqual(PROVIDER_KEY_MAP["nvidia"]["env_var"], "NVIDIA_API_KEY")


class TestStage23TeleprompterBuffer(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Teleprompter streaming buffer guard in LLMGenerator.
    """

    async def test_teleprompter_stream_buffer_intercepts_preamble(self):
        """
        Layer 0 & Layer 1 Paranoia:
        Live teleprompter streaming buffer must intercept conversational preamble
        so the salesperson on a live call does not read AI commentary out loud.
        """
        generator = LLMGenerator()
        generator.client = MagicMock()
        generator.model_name = "gpt-4o-mini"

        # Mock streaming chunks
        async def mock_stream():
            tokens = [
                "Sure", ", here", " is what", " you should", " say:\n",
                "We understand", " timing", " is tight,", " but", " our platform", " delivers ROI", " in 30 days."
            ]
            for tok in tokens:
                chunk = MagicMock()
                chunk.choices = [MagicMock(delta=MagicMock(content=tok))]
                chunk.usage = None
                yield chunk

        generator.client.chat.completions.create = AsyncMock(return_value=mock_stream())

        # Mock credit deduction RPC to pass
        with patch("core.backend.api.auth_dep.get_service_client") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"success": True})
            mock_get_svc.return_value = mock_svc

            collected_tokens = []
            async for token in generator.generate_response(
                recent_transcript="We have competing priorities right now.",
                session_memory="Discussed budget in previous call.",
                workspace_id="ws-teleprompter"
            ):
                collected_tokens.append(token)

            full_spoken_text = "".join(collected_tokens)
            # The salesperson should NEVER see or say "Sure, here is what you should say:"
            self.assertNotIn("Sure, here is what you should say:", full_spoken_text)
            self.assertIn("We understand timing is tight", full_spoken_text)


if __name__ == "__main__":
    unittest.main()
