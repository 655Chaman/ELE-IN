"""
Rigorous Automated Test Suite for Vulnerability M-05 Remediation:
Specialized Features Credit Metering & Anti-Leakage Hardening
(Competitive Displacement, Social Prewarm Feed Comments/Posts, Multimodal Voice Scripts & Video Prospecting Cards)

Enforces the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Metering
    * displacement_pitch costs 2 credits
    * social_prewarm_comment costs 1 credit
    * thought_leadership_post costs 2 credits
    * multimodal_voice_script costs 2 credits
    * multimodal_video_card costs 3 credits
    * Atomic credit deductions via deduct_credits
- Layer 1: Environmental Failure Analysis
    * Insufficient credits / overdraft limits enforce HTTP 402
    * LLM generation failures immediately trigger automated compensation refund_credits
    * Schema drift / mock database error isolation
- Layer 2: Human Paranoia
    * Empty strings, whitespace-only fields, and invalid payloads rejected with HTTP 400
    * Preflight rejection occurs before burning or locking tenant credits
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from campaigns.backend.routers.displacement_router import (
    generate_pitch_endpoint,
    GeneratePitchPayload
)
from campaigns.backend.routers.social_prewarm import (
    generate_comment_endpoint,
    generate_post_endpoint,
    GenerateCommentPayload,
    GeneratePostPayload
)
from campaigns.backend.routers.event_multimodal_router import (
    generate_voice_script_endpoint,
    generate_video_card_endpoint,
    GenerateVoiceScriptPayload,
    GenerateVideoCardPayload
)

# ==============================================================================
# LAYER 0: Foundational Metering & Deductions
# ==============================================================================

class TestLayer0FoundationalMetering:
    """Validates exact credit deduction amounts and success responses."""

    @patch("campaigns.backend.routers.displacement_router.deduct_credits")
    @patch("campaigns.backend.routers.displacement_router.check_overdraft_allowance")
    @patch("campaigns.backend.routers.displacement_router.generate_displacement_battlecard_copy")
    @patch("campaigns.backend.routers.displacement_router._check_workspace_tier_permission")
    def test_displacement_pitch_deducts_two_credits(self, mock_perm, mock_service, mock_allowance, mock_deduct):
        mock_allowance.return_value = (True, 100, "ok")
        mock_deduct.return_value = {"success": True, "balance": 98}
        mock_service.return_value = {"pitch": "Compelling displacement message"}

        payload = GeneratePitchPayload(
            incumbent_vendor="apollo",
            target_company="Acme Corp",
            target_contact_name="Alice Smith",
            target_contact_title="VP Sales"
        )
        mock_supabase = MagicMock()

        res = generate_pitch_endpoint(payload, workspace_id="ws-test-pro", supabase=mock_supabase)
        assert res["success"] is True
        assert res["credits_deducted"] == 2
        assert res["balance"] == 98
        mock_deduct.assert_called_once()
        call_kwargs = mock_deduct.call_args.kwargs
        assert call_kwargs["workspace_id"] == "ws-test-pro"
        assert call_kwargs["amount"] == 2
        assert call_kwargs["action_type"] == "displacement_pitch"

    @patch("campaigns.backend.routers.social_prewarm.deduct_credits")
    @patch("campaigns.backend.routers.social_prewarm.check_overdraft_allowance")
    @patch("campaigns.backend.services.prewarm_service.generate_contextual_comment")
    @patch("campaigns.backend.routers.social_prewarm._check_workspace_tier_permission")
    def test_social_prewarm_comment_deducts_one_credit(self, mock_perm, mock_service, mock_allowance, mock_deduct):
        mock_allowance.return_value = (True, 50, "ok")
        mock_deduct.return_value = {"success": True, "balance": 49}
        mock_service.return_value = {"comment": "Insightful social comment."}

        payload = GenerateCommentPayload(
            post_text="Excited to announce our new Q3 sales acceleration initiative!",
            tone="insightful_query",
            company_context="Ele-in"
        )
        res = generate_comment_endpoint(payload, workspace_id="ws-test-pro", supabase=MagicMock())
        assert res["status"] == "success"
        assert res["credits_deducted"] == 1
        assert res["balance"] == 49
        mock_deduct.assert_called_once()
        assert mock_deduct.call_args.kwargs["amount"] == 1
        assert mock_deduct.call_args.kwargs["action_type"] == "social_prewarm_comment"

    @patch("campaigns.backend.routers.social_prewarm.deduct_credits")
    @patch("campaigns.backend.routers.social_prewarm.check_overdraft_allowance")
    @patch("campaigns.backend.services.content_publisher_service.generate_thought_leadership_post")
    @patch("campaigns.backend.routers.social_prewarm._check_workspace_tier_permission")
    def test_social_prewarm_post_deducts_two_credits(self, mock_perm, mock_service, mock_allowance, mock_deduct):
        mock_allowance.return_value = (True, 50, "ok")
        mock_deduct.return_value = {"success": True, "balance": 48}
        mock_service.return_value = {"post": "Long-form thought leadership post content."}

        payload = GeneratePostPayload(
            topic="Outbound Sales Automation Trends",
            framework_id="CONTRARIAN_TRUTH",
            audience="revenue leaders"
        )
        res = generate_post_endpoint(payload, workspace_id="ws-test-pro", supabase=MagicMock())
        assert res["credits_deducted"] == 2
        assert res["balance"] == 48
        mock_deduct.assert_called_once()
        assert mock_deduct.call_args.kwargs["amount"] == 2
        assert mock_deduct.call_args.kwargs["action_type"] == "thought_leadership_post"

    @patch("campaigns.backend.routers.event_multimodal_router.deduct_credits")
    @patch("campaigns.backend.routers.event_multimodal_router.check_overdraft_allowance")
    @patch("campaigns.backend.routers.event_multimodal_router.generate_voice_script")
    @patch("campaigns.backend.routers.event_multimodal_router._check_workspace_tier_permission")
    def test_multimodal_voice_script_deducts_two_credits(self, mock_perm, mock_service, mock_allowance, mock_deduct):
        mock_allowance.return_value = (True, 50, "ok")
        mock_deduct.return_value = {"success": True, "balance": 48}
        mock_service.return_value = {"script": "Hey Sarah, noticed you're scaling SDRs..."}

        payload = GenerateVoiceScriptPayload(
            lead_name="Sarah Connor",
            company="Cyberdyne",
            tone="casual_peer"
        )
        mock_supabase = MagicMock()

        res = generate_voice_script_endpoint(payload, workspace_id="ws-test-pro", supabase=mock_supabase)
        assert res["credits_deducted"] == 2
        assert res["balance"] == 48
        mock_deduct.assert_called_once()
        assert mock_deduct.call_args.kwargs["amount"] == 2
        assert mock_deduct.call_args.kwargs["action_type"] == "multimodal_voice_script"

    @patch("campaigns.backend.routers.event_multimodal_router.deduct_credits")
    @patch("campaigns.backend.routers.event_multimodal_router.check_overdraft_allowance")
    @patch("campaigns.backend.routers.event_multimodal_router.generate_video_prospecting_card")
    @patch("campaigns.backend.routers.event_multimodal_router._check_workspace_tier_permission")
    def test_multimodal_video_card_deducts_three_credits(self, mock_perm, mock_service, mock_allowance, mock_deduct):
        mock_allowance.return_value = (True, 50, "ok")
        mock_deduct.return_value = {"success": True, "balance": 47}
        mock_service.return_value = {
            "headline": "Personalized Video Audit",
            "talking_points": ["Point 1", "Point 2"],
            "call_to_action": "Let's connect"
        }

        payload = GenerateVideoCardPayload(
            lead_name="John Connor",
            company="Tech Resistance",
            video_topic="Outbound Pipeline Teardown"
        )
        mock_supabase = MagicMock()

        res = generate_video_card_endpoint(payload, workspace_id="ws-test-pro", supabase=mock_supabase)
        assert res["credits_deducted"] == 3
        assert res["balance"] == 47
        mock_deduct.assert_called_once()
        assert mock_deduct.call_args.kwargs["amount"] == 3
        assert mock_deduct.call_args.kwargs["action_type"] == "multimodal_video_card"


# ==============================================================================
# LAYER 1: Environmental Failure Analysis & Automatic Refunds
# ==============================================================================

class TestLayer1EnvironmentalFailuresAndRefunds:
    """Validates preflight overdraft rejection (402) and automatic compensation refunding."""

    @patch("campaigns.backend.routers.displacement_router.check_overdraft_allowance")
    @patch("campaigns.backend.routers.displacement_router._check_workspace_tier_permission")
    def test_displacement_pitch_blocks_on_insufficient_credits(self, mock_perm, mock_allowance):
        mock_allowance.return_value = (False, 0, "insufficient_credits")
        payload = GeneratePitchPayload(
            incumbent_vendor="apollo",
            target_company="Acme Corp",
            target_contact_name="Alice Smith",
            target_contact_title="VP Sales"
        )
        mock_supabase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            generate_pitch_endpoint(payload, workspace_id="ws-test-zero-credits", supabase=mock_supabase)
        assert exc_info.value.status_code == 402
        assert "Insufficient credits" in exc_info.value.detail

    @patch("campaigns.backend.routers.displacement_router.refund_credits")
    @patch("campaigns.backend.routers.displacement_router.deduct_credits")
    @patch("campaigns.backend.routers.displacement_router.check_overdraft_allowance")
    @patch("campaigns.backend.routers.displacement_router.generate_displacement_battlecard_copy")
    @patch("campaigns.backend.routers.displacement_router._check_workspace_tier_permission")
    def test_displacement_pitch_compensating_refund_on_llm_crash(
        self, mock_perm, mock_service, mock_allowance, mock_deduct, mock_refund
    ):
        mock_allowance.return_value = (True, 10, "ok")
        mock_deduct.return_value = {"success": True, "balance": 8}
        mock_service.side_effect = RuntimeError("OpenAI 503 Service Unavailable")

        payload = GeneratePitchPayload(
            incumbent_vendor="apollo",
            target_company="Acme Corp",
            target_contact_name="Alice Smith",
            target_contact_title="VP Sales"
        )
        mock_supabase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            generate_pitch_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        assert exc_info.value.status_code == 500
        mock_refund.assert_called_once()
        assert mock_refund.call_args.kwargs["amount"] == 2
        assert mock_refund.call_args.kwargs["reason"] == "displacement_pitch_generation_failed"

    @patch("campaigns.backend.routers.social_prewarm.refund_credits")
    @patch("campaigns.backend.routers.social_prewarm.deduct_credits")
    @patch("campaigns.backend.routers.social_prewarm.check_overdraft_allowance")
    @patch("campaigns.backend.services.prewarm_service.generate_contextual_comment")
    @patch("campaigns.backend.routers.social_prewarm._check_workspace_tier_permission")
    def test_social_prewarm_comment_refunds_on_exception(
        self, mock_perm, mock_service, mock_allowance, mock_deduct, mock_refund
    ):
        mock_allowance.return_value = (True, 10, "ok")
        mock_deduct.return_value = {"success": True, "balance": 9}
        mock_service.side_effect = TimeoutError("LLM Gateway timeout")

        payload = GenerateCommentPayload(post_text="Big tech updates and sales developments.")

        with pytest.raises(HTTPException) as exc_info:
            generate_comment_endpoint(payload, workspace_id="ws-test", supabase=MagicMock())
        assert exc_info.value.status_code == 500
        mock_refund.assert_called_once()
        assert mock_refund.call_args.kwargs["amount"] == 1
        assert mock_refund.call_args.kwargs["reason"] == "social_comment_generation_failed"

    @patch("campaigns.backend.routers.event_multimodal_router.refund_credits")
    @patch("campaigns.backend.routers.event_multimodal_router.deduct_credits")
    @patch("campaigns.backend.routers.event_multimodal_router.check_overdraft_allowance")
    @patch("campaigns.backend.routers.event_multimodal_router.generate_voice_script")
    @patch("campaigns.backend.routers.event_multimodal_router._check_workspace_tier_permission")
    def test_multimodal_voice_script_refunds_on_llm_crash(
        self, mock_perm, mock_service, mock_allowance, mock_deduct, mock_refund
    ):
        mock_allowance.return_value = (True, 20, "ok")
        mock_deduct.return_value = {"success": True, "balance": 18}
        mock_service.side_effect = ValueError("Corrupted token stream")

        payload = GenerateVoiceScriptPayload(lead_name="Devin", company="Acme")
        mock_supabase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            generate_voice_script_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        assert exc_info.value.status_code == 500
        mock_refund.assert_called_once()
        assert mock_refund.call_args.kwargs["amount"] == 2
        assert mock_refund.call_args.kwargs["reason"] == "voice_script_generation_failed"


# ==============================================================================
# LAYER 2: Human Paranoia & Payload Validation Guardrails
# ==============================================================================

class TestLayer2HumanParanoiaInputValidation:
    """Validates that blank, empty, or whitespace-only inputs are rejected before deducting credits."""

    @patch("campaigns.backend.routers.displacement_router.deduct_credits")
    @patch("campaigns.backend.routers.displacement_router._check_workspace_tier_permission")
    def test_displacement_empty_target_company_rejected(self, mock_perm, mock_deduct):
        payload = GeneratePitchPayload(
            incumbent_vendor="apollo",
            target_company="   ",
            target_contact_name="Alice",
            target_contact_title="VP"
        )
        mock_supabase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            generate_pitch_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        assert exc_info.value.status_code == 400
        assert "target_company is required" in exc_info.value.detail
        mock_deduct.assert_not_called()

    @patch("campaigns.backend.routers.social_prewarm.deduct_credits")
    @patch("campaigns.backend.routers.social_prewarm._check_workspace_tier_permission")
    def test_social_prewarm_comment_empty_post_text_rejected(self, mock_perm, mock_deduct):
        payload = GenerateCommentPayload(post_text="")

        with pytest.raises(HTTPException) as exc_info:
            generate_comment_endpoint(payload, workspace_id="ws-test", supabase=MagicMock())
        assert exc_info.value.status_code == 400
        assert "at least 10 characters long" in exc_info.value.detail
        mock_deduct.assert_not_called()

    @patch("campaigns.backend.routers.social_prewarm.deduct_credits")
    @patch("campaigns.backend.routers.social_prewarm._check_workspace_tier_permission")
    def test_social_prewarm_post_empty_topic_rejected(self, mock_perm, mock_deduct):
        payload = GeneratePostPayload(topic="   ")

        with pytest.raises(HTTPException) as exc_info:
            generate_post_endpoint(payload, workspace_id="ws-test", supabase=MagicMock())
        assert exc_info.value.status_code == 400
        assert "at least 3 characters long" in exc_info.value.detail
        mock_deduct.assert_not_called()

    @patch("campaigns.backend.routers.event_multimodal_router.deduct_credits")
    @patch("campaigns.backend.routers.event_multimodal_router._check_workspace_tier_permission")
    def test_multimodal_voice_script_empty_lead_name_rejected(self, mock_perm, mock_deduct):
        payload = GenerateVoiceScriptPayload(lead_name=" \t\n ", company="HyperScale")
        mock_supabase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            generate_voice_script_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        assert exc_info.value.status_code == 400
        assert "lead_name is required" in exc_info.value.detail
        mock_deduct.assert_not_called()

    @patch("campaigns.backend.routers.event_multimodal_router.deduct_credits")
    @patch("campaigns.backend.routers.event_multimodal_router._check_workspace_tier_permission")
    def test_multimodal_video_card_empty_company_rejected(self, mock_perm, mock_deduct):
        payload = GenerateVideoCardPayload(lead_name="Devin", company="   ")
        mock_supabase = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            generate_video_card_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        assert exc_info.value.status_code == 400
        assert "company is required" in exc_info.value.detail
        mock_deduct.assert_not_called()
