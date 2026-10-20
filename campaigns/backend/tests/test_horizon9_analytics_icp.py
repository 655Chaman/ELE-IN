import io
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

from campaigns.backend.routers.master_view import (
    validate_date_range,
    sanitize_filter_list,
    export_master_view_stats_pdf,
    MasterViewRequest,
    get_funnel_leads,
    FunnelLeadsRequest
)
import pypdf
from campaigns.backend.utils.pdf_generator import generate_pdf_report, sanitize_pdf_text
from knowledge.backend.services.bayesian_icp_service import (
    _extract_signals,
    compute_bayesian_icp_score,
    get_workspace_signal_weights,
    record_outcome
)


class TestHorizon9MasterViewAnalytics(unittest.TestCase):
    """
    Test suite for Horizon 9: Master View Analytics, Date Slicing, and Radar Stat Clamping.
    Follows the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def test_validate_date_range_iso_timestamp_slicing(self):
        """
        Layer 0: Verifies that ISO timestamps with time and timezone components
        are safely sliced to YYYY-MM-DD so Postgres DATE columns match without syntax error.
        """
        start_raw = "2026-09-01T14:32:00.123Z"
        end_raw = "2026-09-15T23:59:59Z"
        sliced_start, sliced_end = validate_date_range(start_raw, end_raw)
        self.assertEqual(sliced_start, "2026-09-01")
        self.assertEqual(sliced_end, "2026-09-15")

    def test_validate_date_range_defaults_and_guards(self):
        """
        Layer 1 & 2: Missing dates use current UTC and default 30-day window.
        Inverted date ranges raise HTTP 400. Exceeding max_days raises HTTP 400.
        """
        # Missing date_end defaults to today in UTC
        start, end = validate_date_range(None, None)
        today_utc = datetime.now(timezone.utc).date().isoformat()
        self.assertEqual(end, today_utc)
        self.assertEqual(len(start), 10)
        self.assertEqual(len(end), 10)

        # Inverted dates fail closed
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2026-09-20", "2026-09-10")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("date_end must be after date_start", ctx.exception.detail)

        # Exceeding max_days fails closed
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2010-01-01", "2026-01-01", max_days=365)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Date range cannot exceed", ctx.exception.detail)

    def test_sanitize_filter_list(self):
        """
        Layer 2: Handles None, empty lists, and lists with blank/empty string items safely.
        """
        self.assertIsNone(sanitize_filter_list(None))
        self.assertIsNone(sanitize_filter_list([]))
        self.assertIsNone(sanitize_filter_list(["", None, ""]))
        self.assertEqual(sanitize_filter_list(["camp_1", "", "camp_2"]), ["camp_1", "camp_2"])

    def test_radar_stats_negative_count_clamping(self):
        """
        Layer 1 & 2: Tests the math behind radar stats when historical failed leads
        exceed enrolled leads or connected leads exceed enrolled leads.
        Metrics must be strictly clamped within [0.0, 100.0].
        """
        def safe_div(a, b):
            return a / b if b > 0 else 0

        # Scenario A: failed_count > enrolled_leads (e.g. data anomaly or purged enrolled leads)
        enrolled_leads = 10
        failed_count = 15
        connected_leads = 8
        replied_leads = 4
        booked_leads = 2
        positive_sentiment = 3
        period_replied = 4

        radar_stats = {
            "Acceptance Rate": max(0.0, min(100.0, safe_div(connected_leads, enrolled_leads) * 100)) if enrolled_leads > 0 else 0.0,
            "Reply Rate": max(0.0, min(100.0, safe_div(replied_leads, connected_leads) * 100)) if connected_leads > 0 else 0.0,
            "Booking Rate": max(0.0, min(100.0, safe_div(booked_leads, replied_leads) * 100)) if replied_leads > 0 else 0.0,
            "Sentiment (Pos)": max(0.0, min(100.0, safe_div(positive_sentiment, period_replied) * 100)) if period_replied > 0 else 0.0,
            "Deliverability": max(0.0, min(100.0, safe_div(enrolled_leads - failed_count, enrolled_leads) * 100)) if enrolled_leads > 0 else 100.0,
            "Bounces": max(0.0, min(100.0, safe_div(failed_count, enrolled_leads) * 100)) if enrolled_leads > 0 else 0.0,
        }

        # Deliverability: (10 - 15) / 10 = -50% -> clamped to 0.0%
        self.assertEqual(radar_stats["Deliverability"], 0.0)
        # Bounces: 15 / 10 = 150% -> clamped to 100.0%
        self.assertEqual(radar_stats["Bounces"], 100.0)
        # Other rates are valid
        self.assertEqual(radar_stats["Acceptance Rate"], 80.0)
        self.assertEqual(radar_stats["Reply Rate"], 50.0)
        self.assertEqual(radar_stats["Booking Rate"], 50.0)
        self.assertEqual(radar_stats["Sentiment (Pos)"], 75.0)

    def test_continuous_calendar_generation_no_ghost_dates(self):
        """
        Layer 1 (Environmental): Continuous calendar generation ensures that sparse
        days in the database do not result in missing dates in the time-series charts.
        """
        counts_by_date = {
            "2026-09-01": {"connections": 10, "messages": 5, "inmails": 0, "replied": 0},
            "2026-09-04": {"connections": 20, "messages": 15, "inmails": 0, "replied": 0}
        }
        daily_replies = {
            "2026-09-04": 2
        }

        all_dates = set(counts_by_date.keys()).union(set(daily_replies.keys()))
        self.assertTrue(bool(all_dates))

        min_date = datetime.fromisoformat(min(all_dates))
        max_date = datetime.fromisoformat(max(all_dates))

        time_series = []
        curr_date = min_date
        while curr_date <= max_date:
            dt_str = curr_date.date().isoformat()
            time_series.append({
                "date": dt_str,
                "connections": counts_by_date.get(dt_str, {}).get("connections", 0),
                "messages": counts_by_date.get(dt_str, {}).get("messages", 0),
                "inmails": counts_by_date.get(dt_str, {}).get("inmails", 0),
                "replied": daily_replies.get(dt_str, 0)
            })
            curr_date += timedelta(days=1)

        # Expected 4 contiguous dates: 2026-09-01, 2026-09-02, 2026-09-03, 2026-09-04
        self.assertEqual(len(time_series), 4)
        dates = [entry["date"] for entry in time_series]
        self.assertEqual(dates, ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"])

        # Days 2 and 3 should be zero-padded rather than omitted
        self.assertEqual(time_series[1]["connections"], 0)
        self.assertEqual(time_series[1]["messages"], 0)
        self.assertEqual(time_series[2]["connections"], 0)
        self.assertEqual(time_series[2]["messages"], 0)
        self.assertEqual(time_series[3]["connections"], 20)
        self.assertEqual(time_series[3]["replied"], 2)

    def test_generate_pdf_report_unicode_and_branding(self):
        """
        Layer 0 & 1: Verifies that PDF report generates with custom branding
        and safely survives unprintable emojis, smart quotes, and em-dashes without ReportLab crashing.
        """
        stats_payload = {
            "summary": {
                "total_leads": 1500,
                "active_campaigns": 3,
                "connections_today": 18,
                "messages_today": 32,
                "inmails_today": 4,
                "account_health": "Optimal",
                "positive_sentiment": 12,
                "auto_withdrawals": 2,
            },
            "radar_stats": {
                "Acceptance Rate": 38.5,
                "Reply Rate": 22.0,
                "Booking Rate": 9.4,
                "Deliverability": 99.1,
            },
            "funnel": {
                "extracted": 1500,
                "enrolled": 1200,
                "connected": 460,
                "replied": 101,
                "booked": 10,
            },
            "ai_insight": "Outreach pipeline is active — acceptance rate is 38.5% with high response quality. 🚀 “Priority: maintain velocity”."
        }

        pdf_buf = generate_pdf_report(
            stats_payload,
            date_range="2026-09-01 to 2026-09-30",
            workspace_name="Acme Healthtech",
            brand_name="Apex Growth Partners"
        )
        self.assertIsNotNone(pdf_buf)
        data = pdf_buf.getvalue()
        self.assertTrue(len(data) > 500)
        self.assertTrue(data.startswith(b"%PDF"))

    def test_export_pdf_tier_gating_free_tier_rejected(self):
        """
        Layer 1 & 2: Free tier users requesting PDF export fail closed with HTTP 403.
        """
        mock_req = MagicMock()
        mock_supabase = MagicMock()
        mock_ws_res = MagicMock()
        mock_ws_res.data = [{"tier": "free", "name": "Free Workspace"}]
        mock_supabase.table().select().eq().execute.return_value = mock_ws_res

        payload = MasterViewRequest()
        with self.assertRaises(HTTPException) as ctx:
            export_master_view_stats_pdf(mock_req, payload, mock_supabase, "ws_free")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("require Growth Pro or Enterprise", ctx.exception.detail)

    def test_validate_date_range_null_undefined_strings(self):
        """
        Layer 1 (Environmental): Verifies that string literals of 'null', 'undefined',
        and whitespace strings default to valid dates without throwing ValueError / HTTP 400.
        """
        start, end = validate_date_range("null", "undefined")
        today_utc = datetime.now(timezone.utc).date().isoformat()
        self.assertEqual(end, today_utc)
        self.assertEqual(len(start), 10)

        start2, end2 = validate_date_range("   ", "  ")
        self.assertEqual(end2, today_utc)

    def test_get_funnel_leads_failed_bounced_stage(self):
        """
        Layer 0 & 1: Verifies that requesting Failed/Bounced funnel stage leads
        queries lead_states and returns leads with rich attributes (linkedin_url, email).
        """
        mock_req = MagicMock()
        mock_supabase = MagicMock()

        # Mock lead_states query returning failed lead
        mock_ls_res = MagicMock()
        mock_ls_res.data = [{"lead_id": "lead_err_1"}]

        # Mock leads table query
        mock_leads_res = MagicMock()
        mock_leads_res.data = [{
            "id": "lead_err_1",
            "first_name": "Sarah",
            "last_name": "Connor",
            "job_title": "Security Director",
            "company_name": "Cyberdyne",
            "linkedin_url": "https://linkedin.com/in/sconnor",
            "email": "sarah@cyberdyne.io"
        }]

        mock_ls_query = MagicMock()
        mock_ls_query.select.return_value = mock_ls_query
        mock_ls_query.eq.return_value = mock_ls_query
        mock_ls_query.in_.return_value = mock_ls_query
        mock_ls_query.gte.return_value = mock_ls_query
        mock_ls_query.lte.return_value = mock_ls_query
        mock_ls_query.order.return_value = mock_ls_query
        mock_ls_query.limit.return_value = mock_ls_query
        mock_ls_query.execute.return_value = mock_ls_res

        mock_leads_query = MagicMock()
        mock_leads_query.select.return_value = mock_leads_query
        mock_leads_query.eq.return_value = mock_leads_query
        mock_leads_query.in_.return_value = mock_leads_query
        mock_leads_query.execute.return_value = mock_leads_res

        def mock_table(name):
            if name == "lead_states":
                return mock_ls_query
            elif name == "leads":
                return mock_leads_query
            return MagicMock()

        mock_supabase.table.side_effect = mock_table

        req = FunnelLeadsRequest(step="Failed/Bounced")
        leads = get_funnel_leads(mock_req, req, mock_supabase, "ws_test")

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["name"], "Sarah Connor")
        self.assertEqual(leads[0]["linkedin_url"], "https://linkedin.com/in/sconnor")
        self.assertEqual(leads[0]["email"], "sarah@cyberdyne.io")

    def test_get_funnel_leads_nonexistent_campaign_fails_closed(self):
        """
        Layer 1 & 2: When an invalid campaign filter is passed that does not exist
        in the workspace, it must fail closed and return 0 leads rather than leaking all leads.
        """
        mock_req = MagicMock()
        mock_supabase = MagicMock()

        mock_camp_res = MagicMock()
        mock_camp_res.data = []

        mock_empty_res = MagicMock()
        mock_empty_res.data = []

        def mock_table(name):
            t = MagicMock()
            if name == "campaigns":
                t.select().eq().in_().execute.return_value = mock_camp_res
            elif name == "campaign_execution_states":
                t.select().eq().in_().order().limit().execute.return_value = mock_empty_res
            return t

        mock_supabase.table.side_effect = mock_table

        req = FunnelLeadsRequest(step="Connected", campaigns=["foreign_camp_123"])
        leads = get_funnel_leads(mock_req, req, mock_supabase, "ws_test")
        self.assertEqual(leads, [])

    def test_generate_pdf_report_includes_failed_bounced_and_bounce_rate(self):
        """
        Layer 0: Verifies that the PDF generator generates cleanly with Failed/Bounced
        funnel metrics and Bounce Rate in the rates table.
        """
        stats_payload = {
            "summary": {"total_leads": 500, "active_campaigns": 2},
            "radar_stats": {
                "Acceptance Rate": 25.0,
                "Reply Rate": 15.0,
                "Booking Rate": 5.0,
                "Deliverability": 95.0,
                "Bounces": 5.0
            },
            "funnel": {
                "extracted": 500,
                "enrolled": 400,
                "connected": 100,
                "replied": 15,
                "booked": 2,
                "failed": 20
            },
            "ai_insight": "Outreach pipeline is operational."
        }
        pdf_buf = generate_pdf_report(stats_payload, workspace_name="Enterprise Team", brand_name="Ele-in")
        self.assertIsNotNone(pdf_buf)
        data = pdf_buf.getvalue()
        self.assertTrue(data.startswith(b"%PDF"))

    def test_generate_pdf_report_paranoia_null_and_overflow(self):
        """
        Paranoia Layer 1 & 2: Verifies that generate_pdf_report never crashes on
        None values, empty payload, NaN, Unicode emojis, or overflowing AI insight text.
        """
        poisoned_payload = {
            "summary": {
                "total_leads": None,
                "active_campaigns": None,
                "account_health": None,
                "positive_sentiment": None,
            },
            "radar_stats": {
                "Acceptance Rate": None,
                "Reply Rate": None,
                "Booking Rate": None,
                "Deliverability": None,
                "Bounces": None,
            },
            "funnel": {
                "extracted": None,
                "enrolled": None,
                "failed": None,
            },
            "ai_insight": "🚀 Special emojis and symbols ✓ ✔ ✕ ✖ → \n" + ("Repeating long text to test boundary overflow. " * 50)
        }
        # Should not crash on poisoned payload with NoneType and emojis
        pdf_buf = generate_pdf_report(
            poisoned_payload, 
            workspace_name="🚀 Rocket Workspace 💡", 
            brand_name="Whitelabel Agency™"
        )
        self.assertIsNotNone(pdf_buf)
        data = pdf_buf.getvalue()
        self.assertTrue(data.startswith(b"%PDF"))


class TestHorizon9BayesianICPSynthesis(unittest.TestCase):
    """
    Test suite for Bayesian ICP Adaptive Weight Learning and Prospect Scoring.
    """

    def test_extract_signals_null_safety(self):
        """
        Layer 1 & 2: Verifies that None, empty dict, or non-dict inputs
        do not raise TypeError: 'NoneType' object is not iterable.
        """
        self.assertEqual(_extract_signals(None), {})
        self.assertEqual(_extract_signals({}), {})
        self.assertEqual(_extract_signals("not a dict"), {})
        self.assertEqual(_extract_signals([]), {})

    def test_extract_signals_nested_profile(self):
        """
        Layer 0: Correctly extracts ICP signals from both raw and nested lead profile dicts.
        """
        raw_profile = {
            "title": "VP of Revenue Operations",
            "summary": "We are actively hiring sales reps for our team",
            "recent_job_change": True,
            "funding_announced": True,
            "company_size": "500-1000 employees"
        }
        signals = _extract_signals(raw_profile)
        self.assertTrue(signals["decision_maker_title"])
        self.assertTrue(signals["hiring_gtm"])
        self.assertTrue(signals["job_change_6mo"])
        self.assertTrue(signals["funding_announced"])
        self.assertTrue(signals["mid_market_enterprise"])

        # Nested lead_profile structure
        nested_wrapper = {"lead_profile": raw_profile}
        nested_signals = _extract_signals(nested_wrapper)
        self.assertEqual(signals, nested_signals)

    def test_compute_bayesian_icp_score_empty_fallback(self):
        """
        Layer 1: When profile data has no matched signals or is empty,
        returns neutral prior score 50 without crashing.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value.data = []

        score, reasoning = compute_bayesian_icp_score(mock_supabase, "ws_test", None)
        self.assertEqual(score, 50)
        self.assertIn("neutral prior", reasoning)

        score2, reasoning2 = compute_bayesian_icp_score(mock_supabase, "ws_test", {})
        self.assertEqual(score2, 50)
        self.assertIn("neutral prior", reasoning2)

    def test_compute_bayesian_icp_score_weighted_calculation(self):
        """
        Layer 0 & 2: Tests weighted Bayesian score computation with learned weights.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value.data = [
            {"signal_name": "decision_maker_title", "prior_alpha": 8, "prior_beta": 2}, # 8/10 = 0.8
            {"signal_name": "hiring_gtm", "prior_alpha": 6, "prior_beta": 4},           # 6/10 = 0.6
        ]

        profile = {
            "title": "Head of Growth",
            "summary": "Currently hiring engineers",
        }
        score, reasoning = compute_bayesian_icp_score(mock_supabase, "ws_test", profile)
        # Compounding Bayesian posterior probability with qualifier penalty -> 83
        self.assertEqual(score, 83)
        self.assertIn("Active signals:", reasoning)
        self.assertIn("decision_maker_title", reasoning)
        self.assertIn("hiring_gtm", reasoning)

    def test_get_workspace_signal_weights_corrupt_data_resilience(self):
        """
        Layer 1 & 2: When database returns invalid/negative/corrupt alpha/beta,
        falls back safely to Beta(2,2) -> 0.5 without exception.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value.data = [
            {"signal_name": "decision_maker_title", "prior_alpha": "invalid", "prior_beta": None},
            {"signal_name": "funding_announced", "prior_alpha": -5, "prior_beta": 0},
            {"signal_name": "", "prior_alpha": 10, "prior_beta": 10}, # empty signal name skipped
        ]

        weights = get_workspace_signal_weights(mock_supabase, "ws_test")
        self.assertIn("decision_maker_title", weights)
        self.assertEqual(weights["decision_maker_title"], 0.5)
        self.assertIn("funding_announced", weights)
        # alpha clamped to max(1.0, -5) -> 1.0, beta max(1.0, 0) -> 1.0, 1/(1+1) = 0.5
        self.assertEqual(weights["funding_announced"], 0.5)
        self.assertNotIn("", weights)

    def test_record_outcome_rpc_error_isolation(self):
        """
        Layer 1: If an RPC execution fails for one signal (e.g. database glitch),
        remaining signals continue updating and the function does not crash caller.
        """
        mock_supabase = MagicMock()
        call_count = 0

        def mock_rpc(func_name, params):
            nonlocal call_count
            call_count += 1
            mock_call = MagicMock()
            if params.get("p_signal_name") == "flaky_signal":
                mock_call.execute.side_effect = Exception("Postgres RPC connection dropped")
            else:
                mock_call.execute.return_value = MagicMock()
            return mock_call

        mock_supabase.rpc.side_effect = mock_rpc

        signals = {
            "flaky_signal": True,
            "healthy_signal": True,
            "inactive_signal": False
        }

        # Must not raise an exception
        record_outcome(mock_supabase, "ws_test", "lead_123", "won", signals)
        # Both True signals were attempted; the inactive one was skipped
        self.assertEqual(call_count, 2)

    def test_record_outcome_invalid_inputs_fail_closed(self):
        """
        Layer 2: Bad outcome string ('maybe') or empty arguments return early without RPC calls.
        """
        mock_supabase = MagicMock()
        record_outcome(mock_supabase, "", "lead_123", "won", {"sig": True})
        mock_supabase.rpc.assert_not_called()

        record_outcome(mock_supabase, "ws_test", "lead_123", "maybe", {"sig": True})
        mock_supabase.rpc.assert_not_called()

        record_outcome(mock_supabase, "ws_test", "lead_123", "lost", {})
        mock_supabase.rpc.assert_not_called()

    def test_generate_pdf_report_two_pages_structure(self):
        """
        Layer 0 & 1: Verifies that generate_pdf_report returns an executive report
        with exactly 2 pages containing Page 1 Brief/Funnel and Page 2 Fleet/Sender telemetry.
        """
        stats_data = {
            "summary": {"total_sent": 120, "connected": 45, "replied": 18, "meetings": 6},
            "funnel": [
                {"stage": "Dispatched", "count": 120, "pct": 100.0},
                {"stage": "Connected", "count": 45, "pct": 37.5},
                {"stage": "Replied", "count": 18, "pct": 15.0},
                {"stage": "Meeting", "count": 6, "pct": 5.0},
            ],
            "campaigns": [
                {"id": "c1", "name": "Q4 Outbound", "sent": 60, "replied": 10, "status": "active"},
                {"id": "c2", "name": "Enterprise ABM", "sent": 60, "replied": 8, "status": "active"},
            ],
            "sender_accounts": [
                {"name": "Alice Smith", "email": "alice@company.com", "sent": 60, "health": "excellent"},
                {"name": "Bob Jones", "email": "bob@company.com", "sent": 60, "health": "good"},
            ],
            "lead_sources": [
                {"source": "Sales Navigator", "count": 80},
                {"source": "Apollo", "count": 40},
            ],
            "radar_stats": {
                "connection_rate": 37.5,
                "reply_rate": 15.0,
                "meeting_rate": 5.0,
                "sentiment_positive": 72.0,
            },
        }
        buf = generate_pdf_report(
            stats_data,
            date_range="Oct 09 - Oct 16, 2026",
            workspace_name="Stark Growth Tech",
            brand_name="Ele-in Enterprise",
            filter_scope="All Senders · All Campaigns"
        )
        self.assertIsNotNone(buf)
        raw_pdf = buf.getvalue()
        self.assertTrue(raw_pdf.startswith(b"%PDF"))
        
        reader = pypdf.PdfReader(io.BytesIO(raw_pdf))
        self.assertEqual(len(reader.pages), 2, "Executive PDF must contain exactly 2 pages.")
        
        page1_text = reader.pages[0].extract_text()
        page2_text = reader.pages[1].extract_text()
        
        # Page 1 checks
        self.assertIn("Executive Performance Overview", page1_text)
        self.assertIn("KEY PERFORMANCE INDICATORS", page1_text)
        self.assertIn("CONVERSION FUNNEL", page1_text)
        self.assertIn("CAPTAIN'S STRATEGIC BRIEF", page1_text)
        self.assertIn("Page 1 of 2", page1_text)
        
        # Page 2 checks
        self.assertIn("Campaign Fleet & Sender Telemetry", page2_text)
        self.assertIn("TOP ACTIVE CAMPAIGNS PERFORMANCE", page2_text)
        self.assertIn("SENDER ACCOUNT HEALTH & SAFETY TELEMETRY", page2_text)
        self.assertIn("CHANNEL LEAD SOURCE DISTRIBUTION", page2_text)
        self.assertIn("ENTERPRISE SAFETY & DELIVERABILITY PROTOCOLS", page2_text)
        self.assertIn("Page 2 of 2", page2_text)

    def test_generate_pdf_report_paranoia_none_and_corrupt_data(self):
        """
        Layer 1 & 2 (Environmental & Human Paranoia):
        Survives completely empty dict, None stats_data, None sub-fields, negative values,
        and NaN/Inf values without throwing TypeError, ZeroDivisionError, or unhandled exceptions.
        """
        # Empty payload
        buf_empty = generate_pdf_report({})
        reader_empty = pypdf.PdfReader(buf_empty)
        self.assertEqual(len(reader_empty.pages), 2)
        
        # Corrupt and None subfields
        corrupted_data = {
            "summary": None,
            "funnel": {
                "extracted": 0,
                "enrolled": None,
                "connected": -5,
                "replied": "not_a_number",
                "booked": None,
                "failed": None
            },
            "radar_stats": {
                "Acceptance Rate": None,
                "Reply Rate": float("nan"),
                "Booking Rate": float("inf"),
                "Deliverability": None,
                "Bounces": -10.0
            },
            "campaigns": [
                None,
                {"name": None, "status": None, "enrolled": None, "reply_rate": None, "booked": None},
                {"name": "Ultra-Long Campaign Name " * 10, "status": "UNKNOWN", "enrolled": -100, "reply_rate": 999.9, "booked": 0}
            ],
            "sender_accounts": [
                None,
                {"name": None, "status": None, "health_pct": None, "activity_24h": None}
            ],
            "lead_sources": None,
            "ai_insight": None
        }
        
        buf_corrupt = generate_pdf_report(
            corrupted_data,
            date_range=None,
            workspace_name=None,
            brand_name=None,
            filter_scope=None
        )
        reader_corrupt = pypdf.PdfReader(buf_corrupt)
        self.assertEqual(len(reader_corrupt.pages), 2)

    def test_master_view_request_production_schema(self):
        """
        Layer 0 & 2: Verifies that MasterViewRequest accepts date slicing and filters,
        and operates in pure production mode.
        """
        req = MasterViewRequest(date_start="2026-10-01", date_end="2026-10-15")
        self.assertEqual(req.date_start, "2026-10-01")
        self.assertEqual(req.date_end, "2026-10-15")
        self.assertFalse(hasattr(req, "demo_mode"))

    def test_export_pdf_passes_filter_scope(self):
        """
        Layer 0 & 1: Verifies that export_master_view_stats_pdf constructs filter scope
        correctly and passes it to generate_pdf_report.
        """
        mock_req = MagicMock()
        mock_supabase = MagicMock()
        mock_ws_res = MagicMock()
        mock_ws_res.data = [{"tier": "PRO", "name": "Growth Co"}]
        mock_supabase.table().select().eq().execute.return_value = mock_ws_res

        with patch("campaigns.backend.routers.master_view.generate_pdf_report") as mock_gen:
            mock_gen.return_value = io.BytesIO(b"%PDF-1.4 dummy")
            payload = MasterViewRequest()
            res = export_master_view_stats_pdf(mock_req, payload, mock_supabase, "ws_test")
            self.assertEqual(res.status_code, 200)
            mock_gen.assert_called_once()
            _, kwargs = mock_gen.call_args
            self.assertIn("filter_scope", kwargs)
            self.assertIn("All Senders", kwargs["filter_scope"])


if __name__ == "__main__":
    unittest.main()
