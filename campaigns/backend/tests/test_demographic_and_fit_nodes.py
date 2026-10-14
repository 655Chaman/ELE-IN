import pytest
from unittest.mock import MagicMock
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

@pytest.fixture
def mock_worker():
    worker = MagicMock()
    worker.account_id = "acc-fit-test"
    return worker

@pytest.fixture
def mock_supabase():
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value = MagicMock(data=True)

    def mock_table(table_name):
        tbl = MagicMock()
        if table_name == "accounts":
            tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"is_warmup": False}])
        elif table_name == "leads":
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        return tbl

    sb.table.side_effect = mock_table
    return sb

@pytest.fixture
def executor(mock_worker, mock_supabase):
    return EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase, workspace_id="ws-fit-test")


class TestDemographicAndAccountFitNodes:

    # ── 1. IF COMPANY SIZE ─────────────────────────────────────────────────────
    def test_company_size_exact_integer_in_range(self, executor):
        data = {
            "min_size": 20,
            "max_size": 100,
            "lead": {"headcount": 50}
        }
        res = executor.execute("if_company_size", data, "https://linkedin.com/in/corp1")
        assert res["status"] == "success"
        assert res["branch"] == Branch.IN_RANGE.value
        assert res["in_range"] is True

    def test_company_size_linkedin_range_string_overlap(self, executor):
        # LinkedIn standard headcount band "51-200" overlapping min 100 max 500
        data = {
            "min_size": 100,
            "max_size": 500,
            "lead": {"headcount": "51-200"}
        }
        res = executor.execute("if_company_size", data, "https://linkedin.com/in/corp2")
        assert res["status"] == "success"
        assert res["branch"] == Branch.IN_RANGE.value
        assert res["in_range"] is True

    def test_company_size_formatted_plus_string(self, executor):
        data = {
            "min_size": 1000,
            "max_size": 0, # No limit
            "lead": {"headcount": "10,001+ employees"}
        }
        res = executor.execute("if_company_size", data, "https://linkedin.com/in/enterprise")
        assert res["status"] == "success"
        assert res["branch"] == Branch.IN_RANGE.value
        assert res["in_range"] is True

    def test_company_size_out_of_range(self, executor):
        data = {
            "min_size": 100,
            "max_size": 500,
            "lead": {"headcount": 15}
        }
        res = executor.execute("if_company_size", data, "https://linkedin.com/in/small")
        assert res["status"] == "success"
        assert res["branch"] == Branch.OUT_OF_RANGE.value
        assert res["in_range"] is False

    def test_company_size_inverted_bounds_auto_correction(self, executor):
        # Operator mistakenly sets min=500 and max=50
        data = {
            "min_size": 500,
            "max_size": 50,
            "lead": {"headcount": 150}
        }
        res = executor.execute("if_company_size", data, "https://linkedin.com/in/test")
        assert res["status"] == "success"
        assert res["branch"] == Branch.IN_RANGE.value

    def test_company_size_unknown_safe_fallback(self, executor):
        data = {
            "min_size": 10,
            "max_size": 100,
            "lead": {} # No headcount
        }
        res = executor.execute("if_company_size", data, "https://linkedin.com/in/unknown")
        assert res["status"] == "success"
        assert res["branch"] == Branch.OUT_OF_RANGE.value
        assert res["headcount"] is None

    # ── 2. IF COMPANY HIRING ───────────────────────────────────────────────────
    def test_company_hiring_cache_hit(self, executor, mock_worker):
        data = {"is_hiring": True}
        res = executor.execute("if_company_hiring", data, "https://linkedin.com/in/lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.HIRING.value
        assert res["source"] == "cache"
        mock_worker.check_company_hiring.assert_not_called()

    def test_company_hiring_worker_dispatch(self, executor, mock_worker):
        mock_worker.check_company_hiring.return_value = {"status": "success", "branch": "Hiring"}
        data = {"role_keywords": "Sales, Engineer"}
        res = executor.execute("if_company_hiring", data, "https://linkedin.com/in/hiring-lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.HIRING.value
        mock_worker.check_company_hiring.assert_called_once_with("https://linkedin.com/in/hiring-lead", role_filter="Sales, Engineer")

    def test_company_hiring_worker_unavailable_fallback(self, mock_supabase):
        exec_no_worker = EleInNodeExecutor(linkedin_worker=None, supabase=mock_supabase, workspace_id="ws-1")
        res = exec_no_worker.execute("if_company_hiring", {}, "https://linkedin.com/in/lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.NOT_HIRING.value

    # ── 3. IF PREMIUM MEMBER ───────────────────────────────────────────────────
    def test_premium_member_cache_hit(self, executor, mock_worker):
        data = {"is_premium": True}
        res = executor.execute("if_premium_member", data, "https://linkedin.com/in/vip")
        assert res["status"] == "success"
        assert res["branch"] == Branch.PREMIUM.value
        assert res["is_premium"] is True
        mock_worker.check_premium_badge.assert_not_called()

    def test_premium_member_worker_dispatch(self, executor, mock_worker):
        mock_worker.check_premium_badge.return_value = {"status": "success", "branch": "Premium", "is_premium": True}
        res = executor.execute("if_premium_member", {}, "https://linkedin.com/in/prospect")
        assert res["status"] == "success"
        assert res["branch"] == Branch.PREMIUM.value

    def test_premium_member_worker_unavailable_fallback(self, mock_supabase):
        exec_no_worker = EleInNodeExecutor(linkedin_worker=None, supabase=mock_supabase, workspace_id="ws-1")
        res = exec_no_worker.execute("if_premium_member", {}, "https://linkedin.com/in/prospect")
        assert res["status"] == "success"
        assert res["branch"] == Branch.FREE.value
        assert res["is_premium"] is False

    # ── 4. IF MUTUAL CONNECTIONS ───────────────────────────────────────────────
    def test_mutual_connections_cache_hit(self, executor, mock_worker):
        data = {"mutual_connections": 5, "min_mutuals": 3}
        res = executor.execute("if_mutual_connections", data, "https://linkedin.com/in/mutual")
        assert res["status"] == "success"
        assert res["branch"] == Branch.HAS_MUTUALS.value
        assert res["count"] == 5
        mock_worker.get_mutual_connection_count.assert_not_called()

    def test_mutual_connections_below_threshold(self, executor, mock_worker):
        mock_worker.get_mutual_connection_count.return_value = {"count": 1}
        data = {"min_mutuals": 3}
        res = executor.execute("if_mutual_connections", data, "https://linkedin.com/in/mutual-low")
        assert res["status"] == "success"
        assert res["branch"] == Branch.NO_MUTUALS.value

    # ── 5. IF RECENTLY ACTIVE ──────────────────────────────────────────────────
    def test_recently_active_cache_hit(self, executor, mock_worker):
        data = {"is_recently_active": True}
        res = executor.execute("if_recently_active", data, "https://linkedin.com/in/active-lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.ACTIVE.value
        mock_worker.check_recently_active.assert_not_called()

    def test_recently_active_worker_dispatch(self, executor, mock_worker):
        mock_worker.check_recently_active.return_value = {"status": "success", "branch": "Active"}
        data = {"days": 14}
        res = executor.execute("if_recently_active", data, "https://linkedin.com/in/active")
        assert res["status"] == "success"
        assert res["branch"] == Branch.ACTIVE.value
        mock_worker.check_recently_active.assert_called_once_with("https://linkedin.com/in/active", days=14)

    # ── 6. IF HAS RECENT POSTS ─────────────────────────────────────────────────
    def test_has_recent_posts_cache_hit(self, executor, mock_worker):
        data = {"has_recent_posts": True}
        res = executor.execute("if_has_recent_posts", data, "https://linkedin.com/in/poster")
        assert res["status"] == "success"
        assert res["branch"] == Branch.HAS_POSTS.value
        mock_worker.check_has_recent_posts.assert_not_called()

    # ── 7. IF LARGE FOLLOWING ──────────────────────────────────────────────────
    def test_large_following_formatted_string(self, executor):
        data = {
            "followers": "25k",
            "follower_threshold": 10000
        }
        res = executor.execute("if_large_following", data, "https://linkedin.com/in/influencer")
        assert res["status"] == "success"
        assert res["branch"] == Branch.HIGH_FOLLOWING.value
        assert res["followers"] == 25000

    def test_normal_following(self, executor):
        data = {
            "followers": 1500,
            "follower_threshold": 5000
        }
        res = executor.execute("if_large_following", data, "https://linkedin.com/in/standard")
        assert res["status"] == "success"
        assert res["branch"] == Branch.NORMAL_FOLLOWING.value

    # ── 8. KEYWORD MATCHING (TITLE, LOCATION, INDUSTRY) ───────────────────────
    def test_title_matches_multi_keyword(self, executor):
        data = {
            "keyword": "VP, Vice President, Head of",
            "lead": {"title": "Vice President of Engineering"}
        }
        res = executor.execute("if_title_matches", data, "https://linkedin.com/in/vp")
        assert res["status"] == "success"
        assert res["branch"] == Branch.MATCHES.value
        assert res["matched"] is True

    def test_location_matches(self, executor):
        data = {
            "keyword": "London, UK, United Kingdom",
            "lead": {"location": "Greater London, United Kingdom"}
        }
        res = executor.execute("if_location_matches", data, "https://linkedin.com/in/uk-lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.MATCHES.value

    def test_industry_matches(self, executor):
        data = {
            "keyword": "Software, SaaS",
            "lead": {"industry": "Software Development"}
        }
        res = executor.execute("if_industry_matches", data, "https://linkedin.com/in/saas-lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.MATCHES.value

    # ── 9. ICP SCORE GATE ──────────────────────────────────────────────────────
    def test_icp_score_gate_strong_fit(self, executor):
        data = {
            "score_threshold": 75,
            "variables": {"icp_score": 88}
        }
        res = executor.execute("icp_score_gate", data, "https://linkedin.com/in/ideal-lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.STRONG_FIT.value
        assert res["score"] == 88.0

    def test_icp_score_gate_weak_fit(self, executor):
        data = {
            "score_threshold": 75,
            "variables": {"icp_score": 42}
        }
        res = executor.execute("icp_score_gate", data, "https://linkedin.com/in/poor-lead")
        assert res["status"] == "success"
        assert res["branch"] == Branch.WEAK_FIT.value
        assert res["score"] == 42.0
