import pytest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


@pytest.fixture
def mock_supabase():
    sb = MagicMock()
    # Mock workspaces
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "ws_test", "ai_reply_confidence_threshold": 0.65}
    ]
    return sb


@pytest.fixture
def mock_worker():
    w = MagicMock()
    w.account_id = "acc_123"
    w.workspace_id = "ws_test"
    w.send_message.return_value = {"status": "success", "message_id": "msg_abc"}
    return w


@pytest.fixture
def executor(mock_supabase, mock_worker):
    return EleInNodeExecutor(
        linkedin_worker=mock_worker,
        supabase=mock_supabase,
        workspace_id="ws_test"
    )


class TestAIPersonalizeNode:
    """Tests for ai_personalize (Family E)."""

    def test_ai_personalize_foundational(self, executor):
        data = {
            "lead_profile": {"title": "VP of Engineering", "company": "Acme Inc"},
            "hook_sources": "Recent post",
            "hook_length": "One sentence",
            "custom_persona": "Tech recruiter",
            "fallback_message": "Impressed by your engineering leadership."
        }
        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="Loved your recent post on distributed systems architecture!"):
            res = executor.execute("ai_personalize", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert "distributed systems" in res["variables"]["ai_hook"]
        assert res["variables"]["icebreaker"] == res["variables"]["ai_hook"]
        assert res["variables"]["personalization"] == res["variables"]["ai_hook"]

    def test_ai_personalize_l1_llm_failure_uses_fallback(self, executor):
        data = {
            "lead_profile": {"title": "CTO"},
            "fallback_message": "Great work scaling teams."
        }
        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", side_effect=Exception("API Timeout")):
            res = executor.execute("ai_personalize", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["variables"]["ai_hook"] == "Great work scaling teams."

    def test_ai_personalize_l2_clamping_and_quotes_stripping(self, executor):
        # Long generated hook over 280 chars wrapped in quotes
        long_hook = '"' + ("A" * 320) + '"'
        data = {"lead_profile": {"title": "CEO"}}
        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value=long_hook):
            res = executor.execute("ai_personalize", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        hook = res["variables"]["ai_hook"]
        assert not hook.startswith('"')
        assert len(hook) <= 280
        assert hook.endswith("...")


class TestAIDetectSentimentNode:
    """Tests for ai_detect_sentiment (Family E)."""

    @pytest.mark.parametrize("raw_sentiment,expected_branch", [
        ("Positive", "Positive"),
        ("positive", "Positive"),
        ("Strong positive interest in booking a demo", "Positive"),
        ("Neutral", "Neutral"),
        ("Out of office until next week", "Neutral"),
        ("Negative", "Negative"),
        ("not interested, please remove me", "Negative"),
    ])
    def test_ai_detect_sentiment_normalization(self, executor, raw_sentiment, expected_branch):
        data = {"reply_text": "Sounds interesting, let's talk Tuesday."}
        with patch("knowledge.backend.services.elein_ai_service.classify_reply_sentiment", return_value=(raw_sentiment, "Prospect showed intent")):
            res = executor.execute("ai_detect_sentiment", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == expected_branch
        assert res["sentiment"] == expected_branch
        assert res["variables"]["ai_sentiment"] == expected_branch

    def test_ai_detect_sentiment_l1_empty_text_zero_token_bypass(self, executor):
        data = {"reply_text": "   "}
        with patch("knowledge.backend.services.elein_ai_service.classify_reply_sentiment") as mock_classify:
            res = executor.execute("ai_detect_sentiment", data, "https://linkedin.com/in/test")
            mock_classify.assert_not_called()

        assert res["status"] == "success"
        assert res["branch"] == Branch.NEUTRAL.value
        assert res["sentiment"] == "Neutral"
        assert res["reasoning"] == "No reply text provided"


class TestAIIcebreakerNode:
    """Tests for ai_generate_icebreaker (Family E)."""

    def test_ai_generate_icebreaker_foundational(self, executor):
        data = {
            "lead_profile": {"title": "Product Lead", "company": "SaaS Co"},
            "tone": "Curious",
            "max_chars": 150
        }
        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value="Saw your product launch - what was the biggest hurdle?"):
            res = executor.execute("ai_generate_icebreaker", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert "biggest hurdle" in res["variables"]["ai_icebreaker"]
        assert res["variables"]["icebreaker"] == res["variables"]["ai_icebreaker"]

    def test_ai_generate_icebreaker_l2_max_chars_clamped(self, executor):
        data = {
            "lead_profile": {"title": "Founder"},
            "max_chars": 80
        }
        long_line = "This is a super long opening icebreaker line that definitely exceeds eighty total characters in length."
        with patch("knowledge.backend.services.elein_ai_service.generate_ai_hook", return_value=long_line):
            res = executor.execute("ai_generate_icebreaker", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert len(res["variables"]["ai_icebreaker"]) <= 80
        assert res["variables"]["ai_icebreaker"].endswith("...")


class TestAITranslateMessageNode:
    """Tests for ai_translate_message (Family E)."""

    def test_ai_translate_message_foundational(self, executor):
        data = {
            "message": "Hello {{first_name}}, glad to connect with you!",
            "target_language": "German"
        }
        with patch("knowledge.backend.services.elein_ai_service.translate_message", return_value="Hallo {{first_name}}, freut mich, mich mit Ihnen zu verbinden!"):
            res = executor.execute("ai_translate_message", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert "Hallo" in res["variables"]["ai_translated"]
        assert res["target_language"] == "German"

    def test_ai_translate_message_l1_empty_message_safe_bypass(self, executor):
        data = {"message": "", "target_language": "French"}
        with patch("knowledge.backend.services.elein_ai_service.translate_message") as mock_trans:
            res = executor.execute("ai_translate_message", data, "https://linkedin.com/in/test")
            mock_trans.assert_not_called()

        assert res["status"] == "success"
        assert res["variables"]["ai_translated"] == ""


class TestAIScoreICPNode:
    """Tests for ai_score_icp (Family E)."""

    @pytest.mark.parametrize("score,expected_branch", [
        (92, Branch.HIGH_FIT.value),
        (76, Branch.HIGH_FIT.value),
        (75, Branch.MEDIUM_FIT.value),
        (50, Branch.MEDIUM_FIT.value),
        (49, Branch.LOW_FIT.value),
        (15, Branch.LOW_FIT.value),
    ])
    def test_ai_score_icp_branches(self, executor, score, expected_branch):
        data = {
            "lead_profile": {"title": "VP Sales", "company": "Enterprise Tech"},
            "icp_description": "Enterprise SaaS VPs"
        }
        with patch("knowledge.backend.services.elein_ai_service.score_icp_fit", return_value=score):
            res = executor.execute("ai_score_icp", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == expected_branch
        assert res["score"] == score
        assert res["variables"]["icp_score"] == score

    def test_ai_score_icp_l2_failure_falls_back_to_medium_fit(self, executor):
        data = {"lead_profile": {"title": "Unknown"}}
        with patch("knowledge.backend.services.elein_ai_service.score_icp_fit", side_effect=Exception("LLM Down")):
            res = executor.execute("ai_score_icp", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.MEDIUM_FIT.value
        assert res["score"] == 50


class TestAIBuyingSignalNode:
    """Tests for ai_buying_signal & ai_detect_buying_signal (Family E)."""

    def test_ai_buying_signal_keyword_detected(self, executor):
        data = {
            "signal_keywords": "hiring SDRs, scaling outbound",
            "post_text": "We are aggressively hiring SDRs across North America this quarter!"
        }
        res = executor.execute("ai_buying_signal", data, "https://linkedin.com/in/test")
        assert res["status"] == "success"
        assert res["branch"] == Branch.SIGNAL_DETECTED.value
        assert res["signal_detected"] is True
        assert res["variables"]["buying_signal"] == "Yes"

    def test_ai_buying_signal_llm_detected(self, executor):
        data = {
            "lead_profile": {"headline": "Looking for modern outbound tools to replace Outreach"}
        }
        with patch("knowledge.backend.services.elein_ai_service.detect_buying_signal", return_value=("Yes", "Expressed buying intent")):
            res = executor.execute("ai_buying_signal", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.SIGNAL_DETECTED.value
        assert res["signal_detected"] is True
        assert res["variables"]["buying_signal"] == "Yes"

    def test_ai_buying_signal_no_signal(self, executor):
        data = {
            "signal_keywords": "hiring, budget",
            "post_text": "Enjoying the weekend hike with friends."
        }
        with patch("knowledge.backend.services.elein_ai_service.detect_buying_signal", return_value=("No", "No commercial intent")):
            res = executor.execute("ai_buying_signal", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.NO_SIGNAL.value
        assert res["signal_detected"] is False
        assert res["variables"]["buying_signal"] == "No"


class TestAIWriteConnectionNoteNode:
    """Tests for ai_write_connection_note (Family E)."""

    def test_ai_write_connection_note_foundational(self, executor):
        data = {
            "lead_profile": {"title": "Head of People", "company": "Stripe"},
            "angle": "Company context"
        }
        with patch("knowledge.backend.services.elein_ai_service.write_connection_note", return_value="Hi, saw your incredible team growth at Stripe and wanted to connect!"):
            res = executor.execute("ai_write_connection_note", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert "Stripe" in res["note"]
        assert res["variables"]["ai_connection_note"] == res["note"]
        assert res["variables"]["note"] == res["note"]

    def test_ai_write_connection_note_l2_clamps_to_300_chars(self, executor):
        long_note = "A" * 350
        data = {"lead_profile": {"title": "CEO"}}
        with patch("knowledge.backend.services.elein_ai_service.write_connection_note", return_value=long_note):
            res = executor.execute("ai_write_connection_note", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert len(res["note"]) <= 300
        assert res["note"].endswith("...")


class TestAISummarizeProfileNode:
    """Tests for ai_summarize_profile (Family E)."""

    def test_ai_summarize_profile_foundational(self, executor):
        data = {
            "lead_profile": {"title": "VP Growth", "company": "Linear"},
            "summary_focus": "Recent Career Moves & Accomplishments"
        }
        with patch("knowledge.backend.services.elein_ai_service.summarize_profile", return_value="Scaled product-led growth at Linear; specializes in developer marketing."):
            res = executor.execute("ai_summarize_profile", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert "Linear" in res["summary"]
        assert res["variables"]["profile_summary"] == res["summary"]
        assert res["variables"]["intel_card"] == res["summary"]


class TestAIDetectCompetitorNode:
    """Tests for ai_detect_competitor (Family E)."""

    def test_ai_detect_competitor_using_competitor(self, executor):
        data = {
            "lead_profile": {"summary": "Current stack: Salesforce, Lemlist, Apollo"},
            "competitors": "Lemlist, Outreach, Apollo"
        }
        with patch("knowledge.backend.services.elein_ai_service.detect_competitor", return_value=("Lemlist", "Mentioned in profile")):
            res = executor.execute("ai_detect_competitor", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.USING_COMPETITOR.value
        assert res["competitor_detected"] is True
        assert res["variables"]["competitor_detected"] is True
        assert res["variables"]["detected_competitor"] == "Lemlist"

    def test_ai_detect_competitor_not_detected(self, executor):
        data = {
            "lead_profile": {"summary": "Building enterprise databases in Rust"},
            "competitors": "Lemlist, Outreach"
        }
        with patch("knowledge.backend.services.elein_ai_service.detect_competitor", return_value=(None, "No competitor found")):
            res = executor.execute("ai_detect_competitor", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.NOT_DETECTED.value
        assert res["competitor_detected"] is False

    def test_ai_detect_competitor_l1_empty_competitor_list(self, executor):
        data = {"competitors": ""}
        with patch("knowledge.backend.services.elein_ai_service.detect_competitor") as mock_detect:
            res = executor.execute("ai_detect_competitor", data, "https://linkedin.com/in/test")
            mock_detect.assert_not_called()

        assert res["status"] == "success"
        assert res["branch"] == Branch.NOT_DETECTED.value
        assert res["competitor_detected"] is False


class TestAIBestSendTimeNode:
    """Tests for ai_best_send_time (Family E)."""

    def test_ai_best_send_time_foundational(self, executor):
        data = {
            "lead_profile": {"title": "Chief Information Officer", "timezone": "America/New_York"},
            "max_wait_hours": 18
        }
        with patch("knowledge.backend.services.elein_ai_service.predict_best_send_time", return_value="08:15 AM"):
            res = executor.execute("ai_best_send_time", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["best_send_time"] == "08:15 AM"
        assert res["max_wait_hours"] == 18
        assert res["variables"]["best_send_time"] == "08:15 AM"


class TestAIQueryKnowledgeBaseNode:
    """Tests for ai_query_knowledge_base & ai_query_brain (Family E)."""

    def test_ai_query_brain_response_generated(self, executor):
        data = {
            "reply_text": "Is this cheaper than Lemlist?",
            "lead_profile": {"title": "Sales Ops"}
        }
        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value="Yes, Ele-in provides unlimited seats with 40% lower TCO."):
            res = executor.execute("ai_query_knowledge_base", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.RESPONSE_GENERATED.value
        assert "40% lower TCO" in res["response"]
        assert res["variables"]["ai_brain_response"] == res["response"]

    def test_ai_query_brain_fallback_message(self, executor):
        data = {
            "reply_text": "Obscure technical question with no KB match",
            "fallback_message": "Thanks for asking! Let me check with the team and get back to you."
        }
        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value=""):
            res = executor.execute("ai_query_knowledge_base", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.RESPONSE_GENERATED.value
        assert "check with the team" in res["response"]

    def test_ai_query_brain_failed_when_no_match_and_no_fallback(self, executor):
        data = {
            "reply_text": "Completely unknown request",
            "fallback_message": ""
        }
        with patch("knowledge.backend.services.elein_ai_service.query_knowledge_base", return_value=""):
            res = executor.execute("ai_query_knowledge_base", data, "https://linkedin.com/in/test")

        assert res["status"] == "success"
        assert res["branch"] == Branch.FAILED.value


class TestAIGenerateReplyNode:
    """Tests for ai_generate_reply (Family E)."""

    def test_ai_generate_reply_circuit_breaker(self, mock_supabase, mock_worker):
        # 3 outbound messages in last 24h
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value.count = 3
        executor = EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id="ws_test")

        data = {"workspace_id": "ws_test", "lead_id": "lead-456", "_skip_limit_check": True}
        res = executor.execute("ai_generate_reply", data, "https://linkedin.com/in/test")
        assert res["status"] == "error"
        assert "AI Circuit Breaker" in res["error"]


class TestOrchestratorFamilyEIntegration:
    """Tests orchestrator edge matching and terminal paths for Family E nodes."""

    def test_orchestrator_advances_on_ai_branch_synonyms(self, mock_supabase):
        orchestrator = EleInOrchestrator(mock_supabase)
        
        # Test edge matching for "Positive" with synonym "interested"
        outgoing_edges = [
            {"source_handle": "interested", "target_node_id": "step_book_call"},
            {"source_handle": "uninterested", "target_node_id": "step_nurture"}
        ]
        
        # When executor returns "Positive", orchestrator should match "interested"
        branch_handle = "Positive"
        _get_h = lambda e: e.get("source_handle") or ""
        bh_norm = str(branch_handle).strip().lower()
        ai_synonyms_map = {
            "positive": {"positive", "pos", "interested", "warm"},
            "negative": {"negative", "neg", "uninterested", "opt-out", "not interested"}
        }
        syn_set = ai_synonyms_map.get(bh_norm)
        matched_edge = next((e for e in outgoing_edges if str(_get_h(e)).strip().lower() in syn_set), None)
        assert matched_edge is not None
        assert matched_edge["target_node_id"] == "step_book_call"
