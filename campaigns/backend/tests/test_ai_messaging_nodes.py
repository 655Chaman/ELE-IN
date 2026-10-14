import pytest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    return mock

@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.account_id = "acc_123"
    worker.workspace_id = "ws_test"
    worker.send_message.return_value = {"status": "success", "message_id": "msg_abc"}
    return worker

@pytest.fixture
def executor(mock_supabase, mock_worker):
    exec_inst = EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id="ws_test")
    return exec_inst


# ─── 1. AI PERSONALIZE TESTS ─────────────────────────────────────────────────

def test_ai_personalize_success(executor):
    data = {
        "workspace_id": "ws_test",
        "lead_profile": {"title": "VP of Engineering", "company": "Acme Inc"},
        "ai_model": "Auto-Route (Recommended)",
        "fallback_message": "Loved your background."
    }
    with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="Saw your work scaling engineering teams."):
        res = executor.handle_ai_personalize(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["variables"]["ai_hook"] == "Saw your work scaling engineering teams."
    assert res["variables"]["icebreaker"] == "Saw your work scaling engineering teams."
    assert res["variables"]["personalization"] == "Saw your work scaling engineering teams."


def test_ai_personalize_fallback_on_empty(executor):
    data = {
        "workspace_id": "ws_test",
        "lead_profile": {"title": "Founder"},
        "fallback_message": "Impressive company trajectory."
    }
    with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="   "):
        res = executor.handle_ai_personalize(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["variables"]["ai_hook"] == "Impressive company trajectory."


def test_ai_personalize_empty_string_fallback_trap(executor):
    # Layer 2 Paranoia: Empty string fallback should not result in empty hook
    data = {
        "workspace_id": "ws_test",
        "lead_profile": {"title": "CTO"},
        "fallback_message": ""
    }
    with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value=None):
        res = executor.handle_ai_personalize(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert len(res["variables"]["ai_hook"].strip()) > 0


def test_ai_personalize_persona_injection(executor):
    with patch.object(executor, "_get_unified_brain", return_value={
        "personas": [
            {
                "title": "Engineering Leader",
                "target_titles": ["vp of engineering", "cto"],
                "pain_points": ["hiring delays", "tech debt"],
                "value_prop": "automate pipeline",
                "tone_tweaks": "direct and technical"
            }
        ]
    }):
        data = {
            "workspace_id": "ws_test",
            "lead_profile": {"title": "VP of Engineering at FinTech Corp"}
        }
        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook") as mock_gen:
            mock_gen.return_value = "Custom hook"
            res = executor.handle_ai_personalize(data, "https://linkedin.com/in/test")
            # Verify custom persona was injected into the call
            args, _ = mock_gen.call_args
            custom_persona_arg = args[2]
            assert "Engineering Leader" in custom_persona_arg
            assert "hiring delays" in custom_persona_arg


# ─── 2. AI DETECT SENTIMENT TESTS ────────────────────────────────────────────

def test_ai_detect_sentiment_positive(executor):
    data = {
        "reply_text": "Yes, I am very interested! Let's schedule a call this Thursday.",
        "workspace_id": "ws_test"
    }
    with patch("knowledge.backend.services.elein_ai_service.classify_reply_sentiment", return_value=("Positive", "High intent with time window")):
        res = executor.handle_ai_detect_sentiment(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == "Positive"
    assert res["sentiment"] == "Positive"
    assert res["reasoning"] == "High intent with time window"
    assert res["variables"]["ai_sentiment"] == "Positive"


def test_ai_detect_sentiment_negative(executor):
    data = {
        "reply_text": "Please remove me from your list. Not interested.",
        "workspace_id": "ws_test"
    }
    with patch("knowledge.backend.services.elein_ai_service.classify_reply_sentiment", return_value=("Negative", "Explicit opt-out")):
        res = executor.handle_ai_detect_sentiment(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == "Negative"
    assert res["sentiment"] == "Negative"
    assert res["variables"]["ai_sentiment"] == "Negative"


def test_ai_detect_sentiment_neutral_tuple_unpacking(executor):
    data = {
        "reply_text": "What is the pricing model?",
        "workspace_id": "ws_test"
    }
    with patch("knowledge.backend.services.elein_ai_service.classify_reply_sentiment", return_value=("Neutral", "Inquiry without commitment")):
        res = executor.handle_ai_detect_sentiment(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == "Neutral"
    assert res["sentiment"] == "Neutral"


def test_ai_detect_sentiment_string_normalization(executor):
    data = {
        "reply_text": "Sounds good!",
        "workspace_id": "ws_test"
    }
    with patch("knowledge.backend.services.elein_ai_service.classify_reply_sentiment", return_value="positive"):
        res = executor.handle_ai_detect_sentiment(data, "https://linkedin.com/in/test")

    assert res["branch"] == "Positive"
    assert res["variables"]["ai_sentiment"] == "Positive"


# ─── 3. AI GENERATE ICEBREAKER TESTS ─────────────────────────────────────────

def test_ai_generate_icebreaker_success(executor):
    data = {
        "lead_profile": {"name": "Alice", "title": "Head of Product"},
        "tone": "Curious",
        "max_chars": 150
    }
    with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="Loved your perspective on product-led growth!"):
        res = executor.handle_ai_generate_icebreaker(data, "https://linkedin.com/in/alice")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["variables"]["ai_icebreaker"] == "Loved your perspective on product-led growth!"
    assert res["variables"]["icebreaker"] == "Loved your perspective on product-led growth!"


def test_ai_generate_icebreaker_fallback_on_failure(executor):
    data = {
        "lead_profile": {},
        "fallback_message": "Awesome updates on LinkedIn recently."
    }
    with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value=""):
        res = executor.handle_ai_generate_icebreaker(data, "https://linkedin.com/in/alice")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["variables"]["ai_icebreaker"] == "Awesome updates on LinkedIn recently."


# ─── 4. AI TRANSLATE MESSAGE TESTS ───────────────────────────────────────────

def test_ai_translate_message_success(executor):
    data = {
        "message": "Hello {{first_name}}, I wanted to reach out regarding your tech stack.",
        "target_language": "German"
    }
    with patch("knowledge.backend.services.elein_ai_service.translate_message", return_value="Hallo {{first_name}}, ich wollte mich bezüglich Ihres Tech-Stacks melden."):
        res = executor.handle_ai_translate_message(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert "Hallo {{first_name}}" in res["translated_message"]
    assert res["variables"]["ai_translated"] == res["translated_message"]
    assert res["target_language"] == "German"


def test_ai_translate_message_multi_key_fallback(executor):
    # Test fallback keys: body -> message, fallback_language -> target_language
    data = {
        "body": "Bonjour, comment allez-vous?",
        "fallback_language": "French"
    }
    with patch("knowledge.backend.services.elein_ai_service.translate_message", return_value="Bonjour, comment allez-vous?"):
        res = executor.handle_ai_translate_message(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["translated_message"] == "Bonjour, comment allez-vous?"


def test_ai_translate_message_failure_preserves_original(executor):
    data = {
        "message": "Original English message",
        "target_language": "Japanese"
    }
    with patch("knowledge.backend.services.elein_ai_service.translate_message", return_value=""):
        res = executor.handle_ai_translate_message(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["translated_message"] == "Original English message"


# ─── 5. AI WRITE CONNECTION NOTE TESTS ───────────────────────────────────────

def test_ai_write_connection_note_success(executor):
    data = {
        "lead_profile": {"name": "Bob", "title": "VP Sales"},
        "angle": "Relevant experience"
    }
    with patch("knowledge.backend.services.elein_ai_service.write_connection_note", return_value="Saw your work scaling sales at Enterprise Co. Would love to connect!"):
        res = executor.handle_ai_write_connection_note(data, "https://linkedin.com/in/bob")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["action"] == "ai_write_connection_note"
    assert "Saw your work scaling sales" in res["note"]
    assert res["variables"]["ai_connection_note"] == res["note"]
    assert res["variables"]["note"] == res["note"]


def test_ai_write_connection_note_strict_300_char_clamp(executor):
    long_note = "A" * 350
    data = {
        "lead_profile": {"name": "Bob"},
        "angle": "Direct value offer"
    }
    with patch("knowledge.backend.services.elein_ai_service.write_connection_note", return_value=long_note):
        res = executor.handle_ai_write_connection_note(data, "https://linkedin.com/in/bob")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert len(res["note"]) <= 300
    assert res["note"].endswith("...")


def test_ai_write_connection_note_exception_fallback(executor):
    data = {
        "lead_profile": {},
        "fallback_message": "Hi, I would love to connect."
    }
    with patch("knowledge.backend.services.elein_ai_service.write_connection_note", side_effect=RuntimeError("LLM API Timeout")):
        res = executor.handle_ai_write_connection_note(data, "https://linkedin.com/in/bob")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    assert res["note"] == "Hi, I would love to connect."


# ─── 6. AI GENERATE REPLY TESTS ──────────────────────────────────────────────

def test_ai_generate_reply_approved_path(executor):
    data = {
        "_workspace_id": "ws_test",
        "_lead_id": "lead_123",
        "approved_ai_reply": "Thanks for getting back! Let's connect on Tuesday."
    }
    with patch.object(executor, "_log_outbound_message"):
        res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/lead123")

    assert res["status"] == "success"
    assert res["branch"] == Branch.THEN.value
    executor.worker.send_message.assert_called_once_with(
        "https://linkedin.com/in/lead123",
        "Thanks for getting back! Let's connect on Tuesday."
    )


def test_ai_generate_reply_circuit_breaker(executor):
    # Simulate 3 outbound messages already sent in last 24h
    executor.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value.count = 3
    
    # Inbound message exists
    msg_mock = MagicMock()
    msg_mock.data = [{"message_text": "Hey, tell me more"}]
    executor.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = msg_mock

    data = {
        "_workspace_id": "ws_test",
        "_lead_id": "lead_123"
    }
    res = executor.handle_ai_generate_reply(data, "https://linkedin.com/in/lead123")
    assert res["status"] == "error"
    assert "Circuit Breaker" in res["error"]


# ─── 7. AI QUERY KNOWLEDGE BASE / BRAIN TESTS ─────────────────────────────────

def test_ai_query_brain_response_generated(executor):
    data = {
        "reply_text": "Do you support HIPAA compliance?",
        "workspace_id": "ws_test"
    }
    with patch.object(executor, "_get_unified_brain", return_value={"objections": []}):
        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value="Yes, we are fully HIPAA compliant and provide signed BAAs."):
            res = executor.handle_ai_query_brain(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.RESPONSE_GENERATED.value
    assert "HIPAA compliant" in res["response"]
    assert res["variables"]["ai_objection_handler"] == res["response"]
    assert res["variables"]["ai_brain_response"] == res["response"]


def test_ai_query_brain_failed_branch_when_no_answer(executor):
    data = {
        "reply_text": "Random gibberish that cannot be answered",
        "workspace_id": "ws_test"
    }
    with patch.object(executor, "_get_unified_brain", return_value={"objections": []}):
        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value=""):
            res = executor.handle_ai_query_brain(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.FAILED.value


def test_ai_query_brain_fallback_message_routes_to_response_generated(executor):
    data = {
        "reply_text": "Unknown topic",
        "workspace_id": "ws_test",
        "fallback_message": "Thanks for your question! Let me check with our technical team."
    }
    with patch.object(executor, "_get_unified_brain", return_value={"objections": []}):
        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value=""):
            res = executor.handle_ai_query_brain(data, "https://linkedin.com/in/test")

    assert res["status"] == "success"
    assert res["branch"] == Branch.RESPONSE_GENERATED.value
    assert "technical team" in res["response"]
    assert res["variables"]["ai_objection_handler"] == res["response"]


def test_ai_query_knowledge_base_alias(executor):
    data = {
        "reply_text": "Pricing question",
        "workspace_id": "ws_test"
    }
    with patch.object(executor, "handle_ai_query_brain", return_value={"status": "success", "branch": Branch.RESPONSE_GENERATED.value}) as mock_brain:
        res = executor.handle_ai_query_knowledge_base(data, "https://linkedin.com/in/test")
        mock_brain.assert_called_once_with(data, "https://linkedin.com/in/test")
        assert res["branch"] == Branch.RESPONSE_GENERATED.value
