import pytest
import json
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from knowledge.backend.services.elein_ai_service import (
    generate_ai_hook,
    generate_inbound_comment,
    UsageLimitExceededError
)


@pytest.fixture
def mock_supabase():
    sb = MagicMock()
    # Default deduct_credits_safely success
    sb.rpc.return_value.execute.return_value.data = {"success": True, "balance": 99}
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "ws_test_credit", "ai_reply_confidence_threshold": 0.65}
    ]
    sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
    return sb


@pytest.fixture
def mock_worker():
    w = MagicMock()
    w.account_id = "acc_123"
    w.workspace_id = "ws_test_credit"
    w.send_message.return_value = {"status": "success", "message_id": "msg_abc"}
    w.comment_on_post.return_value = {"status": "success"}
    w.scrape_recent_post_text.return_value = {"status": "success", "post_text": "Excited about our scalable distributed storage engine launch!"}
    return w


@pytest.fixture
def executor(mock_supabase, mock_worker):
    return EleInNodeExecutor(
        linkedin_worker=mock_worker,
        supabase=mock_supabase,
        workspace_id="ws_test_credit"
    )


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 0: FOUNDATIONAL CREDIT DEDUCTION
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer0FoundationalCreditDeductions:
    """Verifies that AI nodes perform atomic credit deductions."""

    @patch("core.backend.api.auth_dep.get_service_client")
    @patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys")
    @patch("knowledge.backend.services.elein_ai_service._get_sync_client")
    def test_generate_ai_hook_deducts_one_credit(self, mock_client_factory, mock_keys, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase
        mock_keys.return_value = [{"id": "key1", "key": "nvapi-test"}]

        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Great work on cloud architectures!"))]
        mock_completion.usage.total_tokens = 45
        mock_client.chat.completions.create.return_value = mock_completion
        mock_client_factory.return_value = mock_client

        profile = {"title": "VP of Engineering", "company": "Acme Cloud"}
        hook = generate_ai_hook(profile, workspace_id="ws_test_credit")

        assert hook == "Great work on cloud architectures!"
        # Verify deduct_credits_safely was called for workspace
        deduct_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "deduct_credits_safely"]
        assert len(deduct_calls) >= 1
        call_args = deduct_calls[0][0][1]
        assert call_args["p_workspace_id"] == "ws_test_credit"
        assert call_args["p_amount"] == 1
        assert call_args["p_action_type"] == "ai_scoring"

    @patch("core.backend.api.auth_dep.get_service_client")
    @patch("knowledge.backend.services.elein_ai_service._get_sync_client")
    def test_generate_inbound_comment_deducts_one_credit(self, mock_client_factory, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Fascinating approach to distributed database sharding!"))]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_client_factory.return_value = mock_client

        comment = generate_inbound_comment(
            workspace_id="ws_test_credit",
            post_text="Here is a deep technical breakdown of distributed sharding in PostgreSQL.",
            k_obj={"id": "key1", "key": "nvapi-test", "model": "meta/llama-3.1-70b-instruct"}
        )

        assert comment == "Fascinating approach to distributed database sharding!"
        deduct_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "deduct_credits_safely"]
        assert len(deduct_calls) >= 1
        call_args = deduct_calls[0][0][1]
        assert call_args["p_workspace_id"] == "ws_test_credit"
        assert call_args["p_amount"] == 1

    @patch("knowledge.backend.services.elein_ai_service._run_llm_with_failover")
    def test_translate_message_resolves_workspace_from_self(self, mock_llm, executor):
        mock_llm.return_value = "Hola, vi tu perfil profesional."
        data = {
            "message": "Hello, saw your profile.",
            "target_language": "Spanish"
            # workspace_id omitted from data payload!
        }
        res = executor.execute("ai_translate_message", data, "https://linkedin.com/in/test")
        assert res["status"] == "success"
        # Check that workspace_id was passed to translate_message / _run_llm_with_failover
        mock_llm.assert_called_once()
        assert mock_llm.call_args[1]["workspace_id"] == "ws_test_credit"


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: ENVIRONMENTAL FAILURE & REFUND SAFETY
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer1EnvironmentalFailureAndRefunds:
    """Verifies atomic refunds on model/network failures and zero-credit hard stops."""

    @patch("core.backend.api.auth_dep.get_service_client")
    @patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys")
    def test_generate_ai_hook_insufficient_credits_raises(self, mock_keys, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase
        mock_keys.return_value = [{"id": "key1", "key": "nvapi-test"}]
        # Credit deduction fails
        mock_supabase.rpc.return_value.execute.return_value.data = {"success": False, "reason": "insufficient_credits"}

        profile = {"title": "CTO", "company": "Enterprise AI"}
        with pytest.raises(UsageLimitExceededError):
            generate_ai_hook(profile, workspace_id="ws_test_credit")

    @patch("core.backend.api.auth_dep.get_service_client")
    @patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys")
    @patch("knowledge.backend.services.elein_ai_service._get_sync_client")
    def test_generate_ai_hook_refunds_on_all_models_failed(self, mock_client_factory, mock_keys, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase
        mock_keys.return_value = [{"id": "key1", "key": "nvapi-test"}]
        # Deduction succeeds
        mock_supabase.rpc.return_value.execute.return_value.data = {"success": True, "balance": 10}

        # Model throws 500 error
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("500 Internal Server Error")
        mock_client_factory.return_value = mock_client

        profile = {"title": "CTO", "company": "Enterprise AI"}
        result = generate_ai_hook(profile, workspace_id="ws_test_credit")
        assert result == ""

        # Verify refund was issued via add_credits_safely
        refund_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "add_credits_safely"]
        assert len(refund_calls) >= 1
        assert refund_calls[0][0][1]["p_credits"] == 1
        assert refund_calls[0][0][1]["p_workspace_id"] == "ws_test_credit"

    @patch("core.backend.api.auth_dep.get_service_client")
    @patch("knowledge.backend.services.elein_ai_service._get_sync_client")
    def test_generate_inbound_comment_refunds_on_abort_ghostwriting(self, mock_client_factory, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase
        mock_supabase.rpc.return_value.execute.return_value.data = {"success": True, "balance": 20}

        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="ABORT_GHOSTWRITING"))]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_client_factory.return_value = mock_client

        comment = generate_inbound_comment(
            workspace_id="ws_test_credit",
            post_text="Deeply saddened to share that our team has been impacted by massive layoffs today.",
            k_obj={"id": "key1", "key": "nvapi-test"}
        )

        assert comment == "ABORT_GHOSTWRITING"
        # Should refund the credit for safety abort
        refund_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "add_credits_safely"]
        assert len(refund_calls) >= 1
        assert refund_calls[0][0][1]["p_credits"] == 1

    @patch("knowledge.backend.services.elein_ai_service.generate_ai_hook")
    def test_handle_ai_personalize_fails_closed_on_insufficient_credits(self, mock_hook, executor):
        mock_hook.side_effect = UsageLimitExceededError("insufficient_credits")
        data = {
            "lead_profile": {"title": "VP Engineering", "company": "Acme"},
            "fallback_message": "Impressive background!"
        }
        res = executor.handle_ai_personalize(data, "https://linkedin.com/in/test")
        assert res["status"] == "error"
        assert res["error"] == "insufficient_credits"
        assert res["branch"] == Branch.FAILED.value

    @patch("knowledge.backend.services.elein_ai_service.generate_ai_hook")
    def test_handle_ai_generate_icebreaker_fails_closed_on_insufficient_credits(self, mock_hook, executor):
        mock_hook.side_effect = UsageLimitExceededError("insufficient_credits")
        data = {
            "lead_profile": {"title": "VP Engineering", "company": "Acme"},
            "fallback_message": "Loved your post!"
        }
        res = executor.handle_ai_generate_icebreaker(data, "https://linkedin.com/in/test")
        assert res["status"] == "error"
        assert res["error"] == "insufficient_credits"
        assert res["branch"] == Branch.FAILED.value

    @patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=["nvapi-mock-key"])
    @patch("knowledge.backend.services.elein_ai_service.generate_inbound_comment")
    def test_handle_inbound_ghostwriting_fails_closed_on_insufficient_credits(self, mock_gen, mock_keys, executor, mock_worker):
        mock_gen.side_effect = UsageLimitExceededError("insufficient_credits")
        res = executor.handle_inbound_ghostwriting({}, "https://linkedin.com/in/test")
        assert res["status"] == "error"
        assert res["error"] == "insufficient_credits"
        assert res["branch"] == Branch.FAILED.value


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: HUMAN PARANOIA (EMPTY INPUTS & CONTEXT RESOLUTION)
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer2HumanParanoiaEdgeCases:
    """Verifies that human errors like empty profiles or short text don't waste credits."""

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_generate_ai_hook_empty_profile_skips_deduction(self, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase

        # User provided empty title and empty company
        profile = {"title": "", "company": "", "name": "Anonymous"}
        hook = generate_ai_hook(profile, workspace_id="ws_test_credit")

        assert hook == ""
        # Should NOT have called deduct_credits_safely
        deduct_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "deduct_credits_safely"]
        assert len(deduct_calls) == 0

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_generate_inbound_comment_short_text_skips_deduction(self, mock_get_svc, mock_supabase):
        mock_get_svc.return_value = mock_supabase

        # Prospect posted a tiny 5-character string
        comment = generate_inbound_comment(
            workspace_id="ws_test_credit",
            post_text="Hi!!",
            k_obj={"id": "key1", "key": "nvapi-test"}
        )

        assert comment == ""
        # Should NOT have called deduct_credits_safely
        deduct_calls = [c for c in mock_supabase.rpc.call_args_list if c[0][0] == "deduct_credits_safely"]
        assert len(deduct_calls) == 0

    @patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="Great talk on systems!")
    def test_workspace_id_resolution_precedence(self, mock_hook, executor):
        # 1. Test data._workspace_id overrides
        data1 = {"_workspace_id": "ws_override_1", "lead_profile": {"title": "Dev"}}
        executor.handle_ai_personalize(data1, "https://linkedin.com/in/test")
        assert mock_hook.call_args[0][1] == "ws_override_1"

        # 2. Test data.workspace_id overrides
        data2 = {"workspace_id": "ws_override_2", "lead_profile": {"title": "Dev"}}
        executor.handle_ai_personalize(data2, "https://linkedin.com/in/test")
        assert mock_hook.call_args[0][1] == "ws_override_2"

        # 3. Test fallback to executor.workspace_id
        data3 = {"lead_profile": {"title": "Dev"}}
        executor.handle_ai_personalize(data3, "https://linkedin.com/in/test")
        assert mock_hook.call_args[0][1] == "ws_test_credit"
