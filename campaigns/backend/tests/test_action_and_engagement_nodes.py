import pytest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

class TestActionAndEngagementNodes:
    @pytest.fixture
    def mock_supabase(self):
        sb = MagicMock()
        sb.rpc.return_value.execute.return_value = MagicMock(data=True)
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return sb

    @pytest.fixture
    def mock_worker(self):
        worker = MagicMock()
        worker.account_id = "acc_worker_123"
        worker.view_profile.return_value = {"status": "success", "action": "view_profile"}
        worker.follow_profile.return_value = {"status": "success", "action": "follow_profile"}
        worker.like_post.return_value = {"status": "success", "action": "like_post"}
        worker.react_to_post.return_value = {"status": "success", "action": "react_to_post"}
        worker.like_top_3_posts.return_value = {"status": "success", "action": "like_top_3_posts", "count": 3}
        worker.comment_on_post.return_value = {"status": "success", "action": "comment_on_post"}
        worker.endorse_skill.return_value = {"status": "success", "action": "endorse_skill"}
        worker.endorse_3_skills.return_value = {"status": "success", "action": "endorse_3_skills", "count": 3}
        worker.follow_company.return_value = {"status": "success", "action": "follow_company"}
        return worker

    @pytest.fixture
    def executor(self, mock_worker, mock_supabase):
        return EleInNodeExecutor(
            linkedin_worker=mock_worker,
            supabase=mock_supabase,
            workspace_id="ws-c-1"
        )

    # 1. view_profile & view_profile_repeat
    def test_view_profile_success(self, executor, mock_worker):
        res = executor.execute("view_profile", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.view_profile.assert_called_once_with("https://linkedin.com/in/prospect")

    def test_view_profile_repeat_success(self, executor, mock_worker):
        res = executor.execute("view_profile_repeat", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("action") == "view_profile_repeat"

    # 2. follow_profile
    def test_follow_profile_success(self, executor, mock_worker):
        res = executor.execute("follow_profile", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value

    def test_follow_profile_already_following(self, executor, mock_worker):
        mock_worker.follow_profile.return_value = {"status": "error", "error": "Already following lead"}
        res = executor.execute("follow_profile", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert "already" in res.get("note", "").lower()

    def test_follow_profile_button_not_found_fallback(self, executor, mock_worker):
        mock_worker.follow_profile.return_value = {"status": "error", "error": "Follow button not found"}
        res = executor.execute("follow_profile", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
        mock_worker.view_profile.assert_called_once()

    # 3. like_post
    def test_like_post_default(self, executor, mock_worker):
        res = executor.execute("like_post", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.like_post.assert_called_once_with("https://linkedin.com/in/prospect")

    def test_like_post_specific_reaction(self, executor, mock_worker):
        res = executor.execute("like_post", {"reaction_type": "insightful"}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.react_to_post.assert_called_once_with("https://linkedin.com/in/prospect", "EMPATHY")

    def test_like_post_no_posts_fallback(self, executor, mock_worker):
        mock_worker.like_post.return_value = {"status": "error", "error": "No recent posts found to like"}
        res = executor.execute("like_post", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
        mock_worker.view_profile.assert_called_once()

    # 4. like_top_3_posts
    def test_like_top_3_posts_success(self, executor, mock_worker):
        res = executor.execute("like_top_3_posts", {"reaction_type": "celebrate", "max_posts": 3}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.like_top_3_posts.assert_called_once_with("https://linkedin.com/in/prospect", reaction="PRAISE", max_posts=3)

    def test_like_top_3_posts_no_posts_fallback(self, executor, mock_worker):
        mock_worker.like_top_3_posts.return_value = {"status": "error", "error": "No recent posts found to like"}
        res = executor.execute("like_top_3_posts", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True

    # 5. react_insightful & react_celebrate
    def test_react_insightful_success(self, executor, mock_worker):
        res = executor.execute("react_insightful", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.react_to_post.assert_called_once_with("https://linkedin.com/in/prospect", "EMPATHY")

    def test_react_insightful_no_posts_fallback(self, executor, mock_worker):
        mock_worker.react_to_post.return_value = {"status": "error", "error": "No posts found for reaction"}
        res = executor.execute("react_insightful", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
        mock_worker.view_profile.assert_called_once()

    def test_react_celebrate_success(self, executor, mock_worker):
        res = executor.execute("react_celebrate", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.react_to_post.assert_called_once_with("https://linkedin.com/in/prospect", "PRAISE")

    def test_react_celebrate_no_posts_fallback(self, executor, mock_worker):
        mock_worker.react_to_post.return_value = {"status": "error", "error": "No posts found for reaction"}
        res = executor.execute("react_celebrate", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
        mock_worker.view_profile.assert_called_once()

    # 6. comment_on_post
    def test_comment_on_post_fixed(self, executor, mock_worker):
        payload = {"comment_mode": "Fixed comment", "comment": "Great insight on this topic!"}
        res = executor.execute("comment_on_post", payload, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.comment_on_post.assert_called_once_with("https://linkedin.com/in/prospect", "Great insight on this topic!")

    def test_comment_on_post_template_interpolation(self, executor, mock_worker):
        payload = {
            "comment_mode": "Fixed comment",
            "comment": "Impressive work at {{company}}!",
            "company": "Acme Corp"
        }
        res = executor.execute("comment_on_post", payload, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        mock_worker.comment_on_post.assert_called_once_with("https://linkedin.com/in/prospect", "Impressive work at Acme Corp!")

    def test_comment_on_post_not_found_fallback(self, executor, mock_worker):
        mock_worker.comment_on_post.return_value = {"status": "error", "error": "Comment button not found"}
        res = executor.execute("comment_on_post", {"comment": "Hello"}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
        mock_worker.view_profile.assert_called_once()

    # 7. endorse_skill & endorse_3_skills
    def test_endorse_skill_success(self, executor, mock_worker):
        res = executor.execute("endorse_skill", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.endorse_skill.assert_called_once_with("https://linkedin.com/in/prospect")

    def test_endorse_skill_not_1st_degree_fallback(self, executor, mock_worker):
        mock_worker.endorse_skill.return_value = {"status": "error", "error": "Endorse button not found (requires 1st-degree)"}
        res = executor.execute("endorse_skill", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
        mock_worker.view_profile.assert_called_once()

    def test_endorse_3_skills_success(self, executor, mock_worker):
        res = executor.execute("endorse_3_skills", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.endorse_3_skills.assert_called_once_with("https://linkedin.com/in/prospect", max_skills=3, fallback="Endorse however many exist")

    def test_endorse_3_skills_fallback(self, executor, mock_worker):
        mock_worker.endorse_3_skills.return_value = {"status": "error", "error": "No skills section found on profile"}
        res = executor.execute("endorse_3_skills", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True

    # 8. follow_company
    def test_follow_company_success(self, executor, mock_worker):
        res = executor.execute("follow_company", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        mock_worker.follow_company.assert_called_once_with("https://linkedin.com/in/prospect")

    def test_follow_company_already_followed_or_not_found(self, executor, mock_worker):
        mock_worker.follow_company.return_value = {"status": "error", "error": "Company page already followed"}
        res = executor.execute("follow_company", {}, "https://linkedin.com/in/prospect")
        assert res.get("status") == "success"
        assert res.get("branch") == Branch.THEN.value
        assert res.get("fallback") is True
