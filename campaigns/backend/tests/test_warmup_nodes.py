import pytest
from unittest.mock import MagicMock
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.account_id = "acc-warmup-test"
    return worker

@pytest.fixture
def mock_supabase():
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value = MagicMock(data=True)
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"is_warmup": False}])
    return sb

@pytest.fixture
def executor(mock_worker, mock_supabase):
    return EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id="ws-test")


class TestWarmupNodes:

    # ── 1. LIKE POST ──────────────────────────────────────────────────────────
    def test_like_post_success(self, executor, mock_worker):
        mock_worker.like_post.return_value = {"status": "success"}
        res = executor.execute("like_post", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        mock_worker.like_post.assert_called_once_with("https://linkedin.com/in/alex")

    def test_like_post_custom_reaction(self, executor, mock_worker):
        mock_worker.react_to_post.return_value = {"status": "success"}
        res = executor.execute("like_post", {"reaction_type": "insightful"}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        mock_worker.react_to_post.assert_called_once_with("https://linkedin.com/in/alex", "EMPATHY")

    def test_like_post_no_posts_fallback_to_view_profile(self, executor, mock_worker):
        mock_worker.like_post.return_value = {"status": "error", "error": "No recent posts found to like"}
        mock_worker.view_profile.return_value = {"status": "success"}
        
        res = executor.execute("like_post", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/alex")

    def test_like_top_3_posts_fallback(self, executor, mock_worker):
        mock_worker.like_top_3_posts.return_value = {"status": "error", "error": "Posts not found"}
        mock_worker.view_profile.return_value = {"status": "success"}
        
        res = executor.execute("like_top_3_posts", {"max_posts": 2}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/alex")

    # ── 2. COMMENT ON POST ────────────────────────────────────────────────────
    def test_comment_on_post_interpolation(self, executor, mock_worker):
        mock_worker.comment_on_post.return_value = {"status": "success"}
        data = {
            "comment": "Awesome post {{first_name}} at {{company}}!",
            "first_name": "Sarah",
            "company": "ScaleUp AI",
            "comment_mode": "Fixed comment"
        }
        res = executor.execute("comment_on_post", data, "https://linkedin.com/in/sarah")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        mock_worker.comment_on_post.assert_called_once_with(
            "https://linkedin.com/in/sarah",
            "Awesome post Sarah at ScaleUp AI!"
        )

    def test_comment_on_post_fallback_to_view_profile(self, executor, mock_worker):
        mock_worker.comment_on_post.return_value = {"status": "error", "error": "No recent posts or commenting is disabled"}
        mock_worker.view_profile.return_value = {"status": "success"}
        
        data = {"comment": "Great insight!", "comment_mode": "Fixed comment"}
        res = executor.execute("comment_on_post", data, "https://linkedin.com/in/sarah")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/sarah")

    def test_comment_on_post_fallback_comment_used_when_empty(self, executor, mock_worker):
        mock_worker.scrape_recent_post_text.return_value = {"status": "error"}
        mock_worker.comment_on_post.return_value = {"status": "success"}
        
        data = {
            "comment": "",
            "comment_mode": "Fixed comment",
            "fallback_comment": "Super insightful share, thanks for posting!"
        }
        res = executor.execute("comment_on_post", data, "https://linkedin.com/in/sarah")
        assert res["status"] == "success"
        mock_worker.comment_on_post.assert_called_once_with(
            "https://linkedin.com/in/sarah",
            "Super insightful share, thanks for posting!"
        )

    # ── 3. ENDORSE SKILL ──────────────────────────────────────────────────────
    def test_endorse_skill_success(self, executor, mock_worker):
        mock_worker.endorse_skill.return_value = {"status": "success"}
        res = executor.execute("endorse_skill", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value

    def test_endorse_skill_non_connection_fallback_to_view_profile(self, executor, mock_worker):
        # 2nd or 3rd degree connections don't have endorse button
        mock_worker.endorse_skill.return_value = {"status": "error", "error": "Endorse button not found on non-connection"}
        mock_worker.view_profile.return_value = {"status": "success"}
        
        res = executor.execute("endorse_skill", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/alex")

    def test_endorse_3_skills_fallback(self, executor, mock_worker):
        mock_worker.endorse_3_skills.return_value = {"status": "error", "error": "Skills not found"}
        mock_worker.view_profile.return_value = {"status": "success"}
        
        res = executor.execute("endorse_3_skills", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/alex")

    # ── 4. FOLLOW COMPANY ─────────────────────────────────────────────────────
    def test_follow_company_success(self, executor, mock_worker):
        mock_worker.follow_company.return_value = {"status": "success"}
        res = executor.execute("follow_company", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value

    def test_follow_company_already_followed_or_not_found(self, executor, mock_worker):
        mock_worker.follow_company.return_value = {"status": "error", "error": "Company page already followed"}
        res = executor.execute("follow_company", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True

    # ── 5. SHARE POST ─────────────────────────────────────────────────────────
    def test_share_post_success(self, executor, mock_worker):
        mock_worker.repost.return_value = {"status": "success"}
        data = {
            "share_comment": "Loved this insight by {{first_name}}!",
            "first_name": "Dave"
        }
        res = executor.execute("share_post", data, "https://linkedin.com/in/dave")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        mock_worker.repost.assert_called_once_with("https://linkedin.com/in/dave", "Loved this insight by Dave!")

    def test_share_post_no_posts_fallback(self, executor, mock_worker):
        mock_worker.repost.return_value = {"status": "error", "error": "No recent posts found to repost"}
        mock_worker.view_profile.return_value = {"status": "success"}
        
        res = executor.execute("share_post", {}, "https://linkedin.com/in/dave")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/dave")

    # ── 6. INVITE TO EVENT ────────────────────────────────────────────────────
    def test_invite_to_event_success(self, executor, mock_worker):
        mock_worker.invite_to_event.return_value = {"status": "success"}
        data = {
            "event_url": "https://linkedin.com/events/saas-summit-2026",
            "invite_note": "Hey {{first_name}}, check out our upcoming session!",
            "first_name": "Dave"
        }
        res = executor.execute("invite_to_event", data, "https://linkedin.com/in/dave")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        mock_worker.invite_to_event.assert_called_once_with(
            "https://linkedin.com/in/dave",
            "https://linkedin.com/events/saas-summit-2026",
            "Hey Dave, check out our upcoming session!"
        )

    def test_invite_to_event_missing_url_safely_falls_back(self, executor, mock_worker):
        mock_worker.view_profile.return_value = {"status": "success"}
        data = {"event_url": ""}
        res = executor.execute("invite_to_event", data, "https://linkedin.com/in/dave")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/dave")

    def test_invite_to_event_error_fallback(self, executor, mock_worker):
        mock_worker.invite_to_event.return_value = {"status": "error", "error": "Event not found or closed"}
        mock_worker.view_profile.return_value = {"status": "success"}
        data = {"event_url": "https://linkedin.com/events/old-event"}
        res = executor.execute("invite_to_event", data, "https://linkedin.com/in/dave")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
        assert res["fallback"] is True

    # ── 7. VIEW PROFILE & REPEAT ──────────────────────────────────────────────
    def test_view_profile_success(self, executor, mock_worker):
        mock_worker.view_profile.return_value = {"status": "success"}
        res = executor.execute("view_profile", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value

    def test_view_profile_repeat_success(self, executor, mock_worker):
        mock_worker.view_profile.return_value = {"status": "success"}
        res = executor.execute("view_profile_repeat", {}, "https://linkedin.com/in/alex")
        assert res["status"] == "success"
        assert res["branch"] == Branch.THEN.value
