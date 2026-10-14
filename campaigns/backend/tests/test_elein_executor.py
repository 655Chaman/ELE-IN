import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor

class TestEleInExecutorLimits(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.worker.account_id = "acc_123"
        self.supabase = MagicMock()
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data=True)
        self.executor = EleInNodeExecutor(linkedin_worker=self.worker, supabase=self.supabase)

    @patch("campaigns.backend.services.elein_executor.get_effective_usage_date", return_value="2026-10-10")
    def test_limit_enforcement_normal(self, mock_get_date):
        """Normal case: under the limit, action is allowed."""
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data=True)
        self.supabase.rpc.return_value = rpc_mock
        
        self.worker.send_message.return_value = {"status": "success"}
        
        res = self.executor.execute("send_message", {"body": "hello"}, "url")
        
        self.supabase.rpc.assert_called_with("try_consume_daily_action", {
            "p_account_id": "acc_123",
            "p_action_type": "message",
            "p_usage_date": "2026-10-10"
        })
        self.assertNotEqual(res.get("status"), "rate_limited")
        self.worker.send_message.assert_called_once_with("url", "hello")

    def test_limit_enforcement_boundary(self):
        """Exact-boundary case: exact limit reached (last successful), next fails."""
        rpc_mock = MagicMock()
        rpc_mock.execute.side_effect = [MagicMock(data=True), MagicMock(data=False)]
        self.supabase.rpc.return_value = rpc_mock
        self.worker.send_message.return_value = {"status": "success"}
        
        res1 = self.executor.execute("send_message", {"body": "hello"}, "url")
        self.assertNotEqual(res1.get("status"), "rate_limited")
        self.worker.send_message.assert_called_once_with("url", "hello")
        
        # Reset mock to test the next call is blocked
        self.worker.send_message.reset_mock()
        
        res2 = self.executor.execute("send_message", {"body": "hello"}, "url")
        self.assertEqual(res2.get("status"), "rate_limited")
        self.assertIn("Daily limit reached", res2.get("error", ""))
        self.worker.send_message.assert_not_called()

    def test_limit_enforcement_over_limit(self):
        """Over-the-limit rejection: RPC denies the action immediately."""
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock(data=False)
        self.supabase.rpc.return_value = rpc_mock
        self.worker.send_message.return_value = {"status": "success"}
        
        res = self.executor.execute("send_message", {"body": "hello"}, "url")
        
        self.assertEqual(res.get("status"), "rate_limited")
        self.assertEqual(res.get("error"), "Daily limit reached for action: message")
        self.worker.send_message.assert_not_called()

    def test_limit_enforcement_fail_closed(self):
        """Fail-closed test: RPC raises an exception (e.g. DB down). Action must be BLOCKED."""
        rpc_mock = MagicMock()
        rpc_mock.execute.side_effect = Exception("Database connection lost")
        self.supabase.rpc.return_value = rpc_mock
        self.worker.send_message.return_value = {"status": "success"}
        
        res = self.executor.execute("send_message", {"body": "hello"}, "url")
        
        self.assertEqual(res.get("status"), "rate_limited")
        self.assertIn("Failed to verify rate limits", res.get("error", ""))
        self.worker.send_message.assert_not_called()
        
    def test_sequencer_unknown_provider(self):
        """Test the sequencer unknown provider path."""
        res = self.executor.execute("add_to_email_sequencer", {"provider": "unsupported_tool"}, "url")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Unknown sequencer provider", res.get("error"))

    def test_smartlead_missing_campaign_id(self):
        """Test Smartlead fails when campaign_id is missing."""
        res = self.executor.execute("add_to_smartlead", {}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("error"), "Smartlead campaign_id required")

    def test_instantly_missing_campaign_id(self):
        """Test Instantly fails when campaign_id is missing."""
        res = self.executor.execute("add_to_instantly", {}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("error"), "Instantly campaign_id required")

    @patch("integrations.backend.services.elein_crm_service.add_to_smartlead")
    def test_smartlead_success(self, mock_add):
        """Test Smartlead successful lead push."""
        mock_add.return_value = True
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"first_name": "Alice", "company_name": "Acme"}])
        res = self.executor.execute("add_to_smartlead", {"campaign_id": "sl_123"}, "https://linkedin.com/in/alice")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("message"), "Pushed lead to Smartlead")
        mock_add.assert_called_once()

    @patch("integrations.backend.services.elein_crm_service.add_to_instantly")
    def test_instantly_success(self, mock_add):
        """Test Instantly successful lead push."""
        mock_add.return_value = True
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"first_name": "Bob", "company_name": "Corp"}])
        res = self.executor.execute("add_to_instantly", {"sequencer_campaign_id": "inst_456"}, "https://linkedin.com/in/bob")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("message"), "Pushed lead to Instantly")
        mock_add.assert_called_once()

    def test_crm_not_implemented(self):
        """Test the CRM missing-handler path."""
        res = self.executor.execute("push_to_crm", {"provider": "Salesforce"}, "url")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Salesforce CRM integration is not yet implemented", res.get("error"))

    def test_send_voice_note_missing_url(self):
        """Test missing audio_url fails gracefully without calling worker."""
        res = self.executor.execute("send_voice_note", {"note": "Hi there"}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertIn("audio_url configured", res.get("error"))
        self.worker.send_voice_note.assert_not_called()

    def test_send_voice_note_success(self):
        """Test happy path: worker is called with url, audio_url, and companion note."""
        self.worker.send_voice_note.return_value = {"status": "success", "action": "send_voice_note"}
        res = self.executor.execute(
            "send_voice_note",
            {"audio_url": "https://example.com/audio.mp3", "note": "Hey check this voice memo"},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "success")
        self.worker.send_voice_note.assert_called_once_with(
            "https://linkedin.com/in/test",
            "https://example.com/audio.mp3",
            note="Hey check this voice memo"
        )

    def test_send_voice_note_worker_error(self):
        """Test error returned by worker is propagated safely."""
        self.worker.send_voice_note.return_value = {"status": "error", "error": "Message dialog not available on profile"}
        res = self.executor.execute(
            "send_voice_note",
            {"audio_url": "https://example.com/audio.mp3"},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "error")
        self.assertIn("Message dialog not available", res.get("error"))

    def test_view_profile_repeat(self):
        self.worker.view_profile.return_value = {"status": "success", "action": "view_profile"}
        res = self.executor.execute("view_profile_repeat", {}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "then")
        self.worker.view_profile.assert_called_once_with("https://linkedin.com/in/test")

    def test_like_top_3_posts(self):
        self.worker.like_top_3_posts.return_value = {"status": "success", "action": "like_top_3_posts", "count": 3}
        res = self.executor.execute(
            "like_top_3_posts",
            {"reaction_type": "Insightful", "max_posts": 3},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "then")
        self.worker.like_top_3_posts.assert_called_once_with("https://linkedin.com/in/test", reaction="EMPATHY", max_posts=3)

    def test_endorse_3_skills(self):
        self.worker.endorse_3_skills.return_value = {"status": "success", "action": "endorse_3_skills", "count": 3}
        res = self.executor.execute("endorse_3_skills", {"fallback": "Skip this step"}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "then")
        self.worker.endorse_3_skills.assert_called_once_with("https://linkedin.com/in/test", max_skills=3, fallback="Skip this step")

    def test_congratulate_new_job(self):
        self.worker.send_message.return_value = {"status": "success", "action": "send_message"}
        res = self.executor.execute(
            "congratulate_new_job",
            {
                "message": "Congrats on joining Acme, Alice!",
                "lead": {"first_name": "Alice", "company": "Acme"}
            },
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "then")
        self.worker.send_message.assert_called_once_with("https://linkedin.com/in/test", "Congrats on joining Acme, Alice!")

    def test_congratulate_anniversary(self):
        self.worker.send_message.return_value = {"status": "success", "action": "send_message"}
        res = self.executor.execute(
            "congratulate_anniversary",
            {
                "message": "Happy work anniversary, Bob!",
                "lead": {"first_name": "Bob", "company": "Acme"}
            },
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "then")
        self.worker.send_message.assert_called_once_with("https://linkedin.com/in/test", "Happy work anniversary, Bob!")

    def test_if_title_matches_success_and_fail(self):
        # Match case
        res_match = self.executor.execute(
            "if_title_matches",
            {"keyword": "VP, Head of, Director", "lead": {"title": "Vice President & Head of Sales"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res_match.get("branch"), "Matches")
        self.assertTrue(res_match.get("matched"))

        # No match case
        res_nomatch = self.executor.execute(
            "if_title_matches",
            {"keyword": "VP, Director", "lead": {"title": "Junior Software Engineer"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res_nomatch.get("branch"), "Does not match")
        self.assertFalse(res_nomatch.get("matched"))

    def test_if_location_matches(self):
        res = self.executor.execute(
            "if_location_matches",
            {"keyword": "San Francisco, London", "lead": {"location": "London Area, United Kingdom"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("branch"), "Matches")

        res_miss = self.executor.execute(
            "if_location_matches",
            {"keyword": "Tokyo", "lead": {"location": "New York, USA"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res_miss.get("branch"), "Does not match")

    def test_if_industry_matches(self):
        res = self.executor.execute(
            "if_industry_matches",
            {"keyword": "Software, SaaS, Technology", "lead": {"industry": "Enterprise Software"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("branch"), "Matches")

    def test_if_meeting_booked(self):
        res_booked = self.executor.execute(
            "if_meeting_booked",
            {"lead": {"status": "meeting_booked"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res_booked.get("branch"), "Booked")
        self.assertTrue(res_booked.get("booked"))

        res_not_booked = self.executor.execute(
            "if_meeting_booked",
            {"lead": {"status": "contacted"}},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res_not_booked.get("branch"), "Not booked")
        self.assertFalse(res_not_booked.get("booked"))

    def test_if_replied_sentiments(self):
        # Positive
        res_pos = self.executor.execute("if_replied_positive", {"variables": {"ai_sentiment": "positive"}}, "https://linkedin.com/in/test")
        self.assertEqual(res_pos.get("branch"), "Positive")

        res_pos_other = self.executor.execute("if_replied_positive", {"variables": {"ai_sentiment": "negative"}}, "https://linkedin.com/in/test")
        self.assertEqual(res_pos_other.get("branch"), "Other")

        # Negative
        res_neg = self.executor.execute("if_replied_negative", {"variables": {"ai_sentiment": "negative"}}, "https://linkedin.com/in/test")
        self.assertEqual(res_neg.get("branch"), "Negative")

        # Neutral
        res_neu = self.executor.execute("if_replied_neutral", {"variables": {"ai_sentiment": "neutral"}}, "https://linkedin.com/in/test")
        self.assertEqual(res_neu.get("branch"), "Neutral")

    def test_if_mutual_connections(self):
        self.worker.get_mutual_connection_count.return_value = {"status": "success", "count": 5}
        res = self.executor.execute("if_mutual_connections", {"min_mutuals": 3}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("branch"), "Has mutuals")
        self.assertEqual(res.get("count"), 5)

        self.worker.get_mutual_connection_count.return_value = {"status": "success", "count": 1}
        res2 = self.executor.execute("if_mutual_connections", {"min_mutuals": 5}, "https://linkedin.com/in/test")
        self.assertEqual(res2.get("branch"), "No mutuals")

    def test_if_recently_active_and_posts(self):
        self.worker.check_recently_active.return_value = {"status": "success", "branch": "Active"}
        res_act = self.executor.execute("if_recently_active", {"days": 7}, "https://linkedin.com/in/test")
        self.assertEqual(res_act.get("branch"), "Active")

        self.worker.check_has_recent_posts.return_value = {"status": "success", "branch": "Active"}
        res_post = self.executor.execute("if_has_recent_posts", {"days": 30}, "https://linkedin.com/in/test")
        self.assertEqual(res_post.get("branch"), "Has posts")

    def test_if_company_hiring(self):
        self.worker.check_company_hiring.return_value = {"status": "success", "branch": "Hiring"}
        res = self.executor.execute("if_company_hiring", {"role_keywords": "Engineers"}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("branch"), "Hiring")

    def test_send_message_variants(self):
        self.worker.send_message.return_value = {"status": "success", "action": "send_message"}
        
        for action in ["send_intro_message", "send_followup", "send_breakup_message", "send_reengage_message"]:
            res = self.executor.execute(action, {"body": "Test message body"}, "https://linkedin.com/in/test")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), "Sent")

    def test_send_message_with_image(self):
        self.worker.send_message_with_attachment.return_value = {"status": "success", "action": "send_image_message"}
        res = self.executor.execute(
            "send_message_with_image",
            {"body": "Check this screenshot", "image_url": "https://example.com/pic.png"},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Sent")
        self.worker.send_message_with_attachment.assert_called_once_with(
            "https://linkedin.com/in/test",
            "Check this screenshot",
            "https://example.com/pic.png",
            "image"
        )

    def test_send_message_ab(self):
        self.worker.send_message.return_value = {"status": "success", "action": "send_message"}
        res = self.executor.execute(
            "send_message_ab",
            {"body_a": "Variant A content", "body_b": "Variant B content"},
            "https://linkedin.com/in/test"
        )
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Sent")
        self.assertIn(res.get("variant"), ["A", "B"])

    def test_ai_buying_signal(self):
        self.worker.scrape_recent_post_text.return_value = {"status": "success", "post_text": "We are expanding our sales team and hiring SDRs urgently!"}
        res = self.executor.execute("ai_buying_signal", {"signal_keywords": "hiring SDRs, sales team, expansion"}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("branch"), "Signal detected")
        self.assertTrue(res.get("signal_detected"))

        res_nosig = self.executor.execute("ai_buying_signal", {"signal_keywords": "crypto, blockchain"}, "https://linkedin.com/in/test")
        self.assertEqual(res_nosig.get("branch"), "No signal")
        self.assertFalse(res_nosig.get("signal_detected"))


class TestEleInFlowControlNodes(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.supabase = MagicMock()
        self.executor = EleInNodeExecutor(linkedin_worker=self.worker, supabase=self.supabase, workspace_id="ws_123")

    def test_ab_split(self):
        res1 = self.executor.execute("ab_split", {"_lead_id": "lead_123", "_current_node_id": "node_ab"}, "https://linkedin.com/in/test")
        self.assertEqual(res1.get("status"), "success")
        self.assertIn(res1.get("branch"), ["Path A", "Path B"])
        
        # Verify determinism
        res2 = self.executor.execute("ab_split", {"_lead_id": "lead_123", "_current_node_id": "node_ab"}, "https://linkedin.com/in/test")
        self.assertEqual(res1.get("branch"), res2.get("branch"))

    def test_weighted_split(self):
        res_a = self.executor.execute("weighted_split", {"path_a_pct": 100, "_lead_id": "lead_123", "_current_node_id": "node_weighted"}, "https://linkedin.com/in/test")
        self.assertEqual(res_a.get("branch"), "Path A")

        res_b = self.executor.execute("weighted_split", {"path_a_pct": 0, "_lead_id": "lead_123", "_current_node_id": "node_weighted"}, "https://linkedin.com/in/test")
        self.assertEqual(res_b.get("branch"), "Path B")

    def test_if_email_found(self):
        res_has = self.executor.execute("if_email_found", {"email": "prospect@acme.com"}, "https://linkedin.com/in/test")
        self.assertEqual(res_has.get("branch"), "Has Email")

        # Mock DB returns no email
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        res_no = self.executor.execute("if_email_found", {"email": "", "_lead_id": "lead_missing"}, "https://linkedin.com/in/test")
        self.assertEqual(res_no.get("branch"), "No Email")

    def test_sequence_end(self):
        self.supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=True)
        res = self.executor.execute("sequence_end", {"exit_reason": "meeting_booked", "_enrollment_id": "enr_123"}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "success")

    def test_blacklist_check(self):
        # Mock supabase suppression_list returns matching record
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "sup_1"}])
        res_black = self.executor.execute("blacklist_check", {"email": "bad@acme.com"}, "https://linkedin.com/in/test")
        self.assertEqual(res_black.get("branch"), "Blacklisted → skip")

        # Mock supabase suppression_list returns empty
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        res_clean = self.executor.execute("blacklist_check", {"email": "good@acme.com"}, "https://linkedin.com/in/test")
        self.assertEqual(res_clean.get("branch"), "Not blacklisted")

    def test_add_tag(self):
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tags": ["existing"]}])
        self.supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=True)
        res = self.executor.execute("add_tag", {"tag": "high_intent", "_lead_id": "lead_123"}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "success")

    @patch("knowledge.backend.services.elein_ai_service.predict_best_send_time")
    def test_ai_best_send_time_alias(self, mock_predict):
        mock_predict.return_value = "Tuesday 9:00 AM"
        res = self.executor.execute("ai_best_send_time", {}, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("variables", {}).get("best_send_time"), "Tuesday 9:00 AM")


if __name__ == '__main__':
    unittest.main()
