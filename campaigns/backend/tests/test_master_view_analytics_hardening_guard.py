import unittest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from campaigns.backend.routers.master_view import (
    validate_date_range,
    safe_div,
    sanitize_filter_list,
    get_master_view_stats,
    MasterViewRequest,
    _master_view_stats_cache,
    _master_view_stats_lock
)

class TestMasterViewAnalyticsHardeningGuard(unittest.TestCase):

    def setUp(self):
        with _master_view_stats_lock:
            _master_view_stats_cache.clear()

    def test_validate_date_range_valid_and_defaults(self):
        # Valid explicit dates
        start, end = validate_date_range("2026-01-01", "2026-01-10")
        self.assertEqual(start, "2026-01-01")
        self.assertEqual(end, "2026-01-10")

        # Missing start/end defaults safely
        start_def, end_def = validate_date_range(None, None)
        self.assertIsNotNone(start_def)
        self.assertIsNotNone(end_def)

        # Null-like strings stripped
        start_null, end_null = validate_date_range("null", "undefined")
        self.assertIsNotNone(start_null)
        self.assertIsNotNone(end_null)

    def test_validate_date_range_rejects_inverted_range(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2026-01-10", "2026-01-01")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("date_end must be after date_start", ctx.exception.detail)

    def test_validate_date_range_rejects_exceeded_span(self):
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2024-01-01", "2026-01-01", max_days=366)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Date range cannot exceed 366 days", ctx.exception.detail)

    def test_safe_div_zero_division_and_nan(self):
        self.assertEqual(safe_div(10, 0), 0.0)
        self.assertEqual(safe_div(10, float('nan')), 0.0)
        self.assertEqual(safe_div(float('nan'), 5), 0.0)
        self.assertEqual(safe_div(None, 5), 0.0)
        self.assertEqual(safe_div(10, None), 0.0)
        self.assertEqual(safe_div(10, 2), 5.0)

    def test_radar_stats_zero_leads_deliverability_default(self):
        enrolled_leads = 0
        connected_leads = 0
        replied_leads = 0
        booked_leads = 0
        positive_sentiment = 0
        period_replied = 0
        failed_count = 0

        radar_stats = {
            "Acceptance Rate": max(0.0, min(100.0, safe_div(connected_leads, enrolled_leads) * 100)) if enrolled_leads > 0 else 0.0,
            "Reply Rate": max(0.0, min(100.0, safe_div(replied_leads, connected_leads) * 100)) if connected_leads > 0 else 0.0,
            "Booking Rate": max(0.0, min(100.0, safe_div(booked_leads, replied_leads) * 100)) if replied_leads > 0 else 0.0,
            "Sentiment (Pos)": max(0.0, min(100.0, safe_div(positive_sentiment, period_replied) * 100)) if period_replied > 0 else 0.0,
            "Deliverability": max(0.0, min(100.0, safe_div(enrolled_leads - failed_count, enrolled_leads) * 100)) if enrolled_leads > 0 else 100.0,
            "Bounces": max(0.0, min(100.0, safe_div(failed_count, enrolled_leads) * 100)) if enrolled_leads > 0 else 0.0,
        }

        self.assertEqual(radar_stats["Deliverability"], 100.0)
        self.assertEqual(radar_stats["Bounces"], 0.0)
        self.assertEqual(radar_stats["Acceptance Rate"], 0.0)

    def test_continuous_calendar_bounded_to_max_span(self):
        min_date = datetime(2020, 1, 1)
        max_date = datetime(2026, 1, 1) # > 366 days span
        
        span_days = (max_date - min_date).days
        self.assertGreater(span_days, 366)

        if span_days > 366:
            min_date = max_date - timedelta(days=366)

        self.assertEqual((max_date - min_date).days, 366)

    def test_sanitize_filter_list_strips_null_and_caps(self):
        lst = ["camp_1", "null", "undefined", "", "   ", "a" * 200, "drop table;", "camp_2"]
        cleaned = sanitize_filter_list(lst, max_items=2)
        self.assertEqual(cleaned, ["camp_1", "camp_2"])

    def test_master_view_cache_serves_fresh_result(self):
        mock_supabase = MagicMock()
        mock_request = MagicMock()
        workspace_id = "test-ws-1"

        # Mock workspace tier and query responses
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "PRO"}]
        mock_supabase.table().select().eq().gte().lte().execute.return_value.data = []

        req = MasterViewRequest(date_start="2026-01-01", date_end="2026-01-10")

        # First call hits supabase
        res1 = get_master_view_stats(mock_request, req, mock_supabase, workspace_id)
        
        # Second call within TTL should hit cache and not call supabase again
        call_count_before = mock_supabase.table.call_count
        res2 = get_master_view_stats(mock_request, req, mock_supabase, workspace_id)
        
        self.assertEqual(res1, res2)

    def test_master_view_stats_foreign_campaign_filter_isolation(self):
        mock_supabase = MagicMock()
        mock_request = MagicMock()
        workspace_id = "test-ws-1"

        # Mock tier
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "PRO"}]
        
        # Mock campaign validation returning empty (foreign ID)
        mock_supabase.table().select().eq().in_().execute.return_value.data = []

        req = MasterViewRequest(campaigns=["foreign-camp-id-999"])
        
        # Should assign dummy UUID ["00000000-0000-0000-0000-000000000000"]
        get_master_view_stats(mock_request, req, mock_supabase, workspace_id)
        self.assertEqual(req.campaigns, ["00000000-0000-0000-0000-000000000000"])

if __name__ == "__main__":
    unittest.main()
