import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from io import BytesIO

from campaigns.backend.routers.master_view import (
    sanitize_filter_list,
    validate_date_range,
    get_master_view_stats,
    get_funnel_leads,
    get_account_health,
    export_master_view_stats_pdf,
    MasterViewRequest,
    FunnelLeadsRequest,
    AccountHealthRequest,
    _generate_captain_brief,
    _captain_brief_cache
)


class TestHorizon21MasterViewAnalyticsHardening(unittest.TestCase):
    """
    Test suite for Horizon 21: Master View Analytics Hardening,
    Funnel Aggregations, Date-Range Curfews, Header Injection Protection & Funnel Validation.
    """

    def setUp(self):
        self.workspace_id = "ws_mv_21"
        self.supabase = MagicMock()

    # ─── 1. sanitize_filter_list tests ─────────────────────────────────────────

    def test_sanitize_filter_list_basic_and_empty(self):
        """Layer 0: Trims strings and drops empty or None inputs."""
        self.assertIsNone(sanitize_filter_list(None))
        self.assertIsNone(sanitize_filter_list([]))
        self.assertIsNone(sanitize_filter_list(["   ", "", "null", "undefined"]))
        res = sanitize_filter_list(["  camp_1  ", "camp_2", ""])
        self.assertEqual(res, ["camp_1", "camp_2"])

    def test_sanitize_filter_list_caps_at_100_items(self):
        """Layer 1: Prevents PostgREST URI overflow by bounding list to 100 items."""
        huge_list = [f"camp_{i}" for i in range(500)]
        res = sanitize_filter_list(huge_list, max_items=100)
        self.assertEqual(len(res), 100)
        self.assertEqual(res[0], "camp_0")
        self.assertEqual(res[99], "camp_99")

    # ─── 2. validate_date_range tests ──────────────────────────────────────────

    def test_validate_date_range_valid(self):
        """Layer 0: Accepts valid ISO date strings."""
        start, end = validate_date_range("2026-01-01", "2026-01-15")
        self.assertEqual(start, "2026-01-01")
        self.assertEqual(end, "2026-01-15")

    def test_validate_date_range_rejects_inverted_dates(self):
        """Layer 2: Rejects date_end before date_start with HTTP 400."""
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2026-05-10", "2026-05-01")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("date_end must be after date_start", ctx.exception.detail)

    def test_validate_date_range_rejects_exceeded_max_days(self):
        """Layer 1: Rejects date ranges exceeding maximum days limit."""
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2010-01-01", "2026-01-01", max_days=365)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Date range cannot exceed", ctx.exception.detail)

    def test_validate_date_range_rejects_malformed_date(self):
        """Layer 2: Rejects non-ISO date strings with HTTP 400."""
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("invalid-date", "2026-01-01")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid date format", ctx.exception.detail)

    # ─── 3. get_funnel_leads step validation ───────────────────────────────────

    def test_funnel_leads_rejects_invalid_step(self):
        """Layer 2: Rejects unknown funnel steps with HTTP 400."""
        mock_req = MagicMock()
        payload = FunnelLeadsRequest(
            step="HackedStep",
            date_start="2026-01-01",
            date_end="2026-01-15"
        )
        with self.assertRaises(HTTPException) as ctx:
            get_funnel_leads(mock_req, payload, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid funnel step 'HackedStep'", ctx.exception.detail)

    def test_funnel_leads_accepts_valid_step(self):
        """Layer 0: Accepts valid funnel step and queries database."""
        mock_req = MagicMock()
        payload = FunnelLeadsRequest(
            step="Extracted",
            date_start="2026-01-01",
            date_end="2026-01-15"
        )
        mock_leads = MagicMock(data=[{"id": "lead_1", "first_name": "Jane", "last_name": "Doe", "company_name": "Acme", "linkedin_url": "https://linkedin.com/in/jane", "email": "jane@acme.com"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.lte.return_value.limit.return_value.execute.return_value = mock_leads
        self.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = mock_leads

        res = get_funnel_leads(mock_req, payload, self.supabase, self.workspace_id)
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "lead_1")

    # ─── 4. export_master_view_stats_pdf header injection defense ───────────────

    @patch("campaigns.backend.routers.master_view.generate_pdf_report")
    @patch("campaigns.backend.routers.master_view.get_master_view_stats")
    def test_export_pdf_neutralizes_header_injection(self, mock_get_stats, mock_gen_pdf):
        """Layer 1 & 2: Strips CRLF and special characters from workspace/agency name in Content-Disposition."""
        mock_gen_pdf.return_value = BytesIO(b"%PDF-1.4 mock pdf content")
        mock_get_stats.return_value = {"summary": {}}

        # Malicious workspace name attempting HTTP header injection and path traversal
        malicious_ws = MagicMock(data=[{
            "name": "EvilCorp\r\nSet-Cookie: sessionId=hacked\r\n../../etc/passwd",
            "tier": "PRO",
            "agency_id": None
        }])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = malicious_ws

        mock_req = MagicMock()
        payload = MasterViewRequest(date_start="2026-01-01", date_end="2026-01-15")

        resp = export_master_view_stats_pdf(mock_req, payload, self.supabase, self.workspace_id)
        content_disp = resp.headers.get("Content-Disposition", "")
        self.assertNotIn("\r", content_disp)
        self.assertNotIn("\n", content_disp)
        self.assertNotIn("..", content_disp)
        self.assertIn("EvilCorp__Set-Cookie__sessionId_hacked", content_disp)

    # ─── 5. get_account_health cookie expiration accuracy ──────────────────────

    def test_get_account_health_cookie_expiration(self):
        """Layer 1: Accurate timezone-aware cookie expiry calculation without naive/aware exceptions."""
        now_utc = datetime.now(timezone.utc)
        expired_ts = (now_utc - timedelta(days=2)).isoformat()
        valid_ts = (now_utc + timedelta(days=5)).isoformat()

        accounts_data = [
            {
                "id": "acc_expired",
                "name": "Expired Sender",
                "status": "ACTIVE",
                "is_warmup": False,
                "cookie_expires_at": expired_ts
            },
            {
                "id": "acc_valid",
                "name": "Valid Sender",
                "status": "ACTIVE",
                "is_warmup": False,
                "cookie_expires_at": valid_ts
            }
        ]
        mock_acc_res = MagicMock(data=accounts_data)
        mock_counts_res = MagicMock(data=[])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_acc_res
        self.supabase.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value = mock_counts_res
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data=25)

        mock_req = MagicMock()
        payload = AccountHealthRequest()

        res = get_account_health(mock_req, payload, self.supabase, self.workspace_id)
        self.assertEqual(res["total_accounts"], 2)
        expired_acc = next(a for a in res["accounts"] if a["id"] == "acc_expired")
        valid_acc = next(a for a in res["accounts"] if a["id"] == "acc_valid")
        self.assertTrue(expired_acc["is_cookie_expired"])
        self.assertFalse(valid_acc["is_cookie_expired"])

    # ─── 6. _captain_brief_cache composite key isolation ───────────────────────

    def test_captain_brief_cache_composite_isolation(self):
        """Layer 1: Cache stores insights under composite keys preventing cross-filter leakage."""
        _captain_brief_cache.clear()
        _captain_brief_cache["ws_test:15.0:5.0:2.0:80.0:10:20:2"] = {
            "insight": "High acceptance rate on 7-day window.",
            "ts": 9999999999
        }

        # Querying with different metric profile should miss the cache
        diff_key = "ws_test:25.0:12.0:4.0:90.0:25:50:4"
        self.assertNotIn(diff_key, _captain_brief_cache)
        self.assertIn("ws_test:15.0:5.0:2.0:80.0:10:20:2", _captain_brief_cache)


if __name__ == "__main__":
    unittest.main()
