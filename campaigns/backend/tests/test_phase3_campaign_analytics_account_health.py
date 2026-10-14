import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient

from campaigns.backend.routers.master_view import (
    sanitize_filter_list,
    validate_date_range,
    get_master_view_stats,
    get_master_view_filters,
    get_funnel_leads,
    get_account_health,
    clear_master_view_cache,
    MasterViewRequest,
    FunnelLeadsRequest,
    AccountHealthRequest,
)
from campaigns.backend.routers.elein import (
    get_account_limits,
    get_warmup_status,
    get_all_warmup_statuses,
    get_account_warmup_roadmap,
    run_warmup_diagnostic,
)
from knowledge.backend.services.elein_ai_service import get_warmup_phase


class TestPhase3CampaignAnalyticsAndAccountHealth(unittest.TestCase):
    """
    Phase 3: Real-Time Campaign Analytics & Account Health Radar Test Suite.
    Rigorous verification across the Three-Layer Logic Architecture:
    - Layer 0: Foundational telemetry calculations, rollup metrics, warmup curves.
    - Layer 1: Environmental Failure Analysis — Zero-migration Supabase resilience
               (missing rollup tables, missing RPCs, missing columns, network drops).
    - Layer 2: Human Paranoia — Zero-division protection, metric clamping [0, 100],
               date inversion rejection, workspace isolation fail-closed.
    """

    def setUp(self):
        clear_master_view_cache()
        self.workspace_id = "ws_phase3_test"
        self.account_id = "acc_phase3_sender_1"
        self.mock_supabase = MagicMock()

    # =========================================================================
    # LAYER 0: Foundational Calculations & Warmup Mechanics
    # =========================================================================

    def test_warmup_phase_progression_curve(self):
        """Paranoia Layer 0: Verifies warmup progression across observation, seed, ramp, and cruise."""
        now = datetime.now(timezone.utc)
        
        # 14-day Balanced Curve:
        # Day 1 (days_active = 0): Observe phase
        d1 = now.isoformat()
        res_d1 = get_warmup_phase(d1, actions_today=5, is_warmup=True, target_days=14)
        self.assertEqual(res_d1["phase"], "observe")
        self.assertEqual(res_d1["day"], 1)
        self.assertEqual(res_d1["daily_limit"], 10)
        self.assertEqual(res_d1["actions_today"], 5)
        self.assertGreaterEqual(res_d1["safety_score"], 90)

        # Day 8 (days_active = 7): Seed phase
        d8 = (now - timedelta(days=7)).isoformat()
        res_d8 = get_warmup_phase(d8, actions_today=15, is_warmup=True, target_days=14)
        self.assertEqual(res_d8["phase"], "seed")
        self.assertEqual(res_d8["daily_limit"], 25)

        # 7-day Fast Curve:
        # Day 3 (days_active = 2): Seed phase
        d3_fast = (now - timedelta(days=2)).isoformat()
        res_fast = get_warmup_phase(d3_fast, actions_today=12, is_warmup=True, target_days=7)
        self.assertEqual(res_fast["phase"], "seed")
        self.assertEqual(res_fast["daily_limit"], 30)

        # Day 6 (days_active = 5): Ramp phase
        d6_fast = (now - timedelta(days=5)).isoformat()
        res_ramp = get_warmup_phase(d6_fast, actions_today=25, is_warmup=True, target_days=7)
        self.assertEqual(res_ramp["phase"], "ramp")
        self.assertEqual(res_ramp["daily_limit"], 45)

        # Warmup disabled -> instantly active
        res_disabled = get_warmup_phase(d1, actions_today=10, is_warmup=False, target_days=14)
        self.assertEqual(res_disabled["phase"], "active")

    def test_account_warmup_roadmap_and_vitals(self):
        """Paranoia Layer 0: Account warmup roadmap returns full 7-day milestones and vitals."""
        mock_acc_res = MagicMock()
        mock_acc_res.data = [{
            "id": self.account_id,
            "name": "Deeksha LinkedIn",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "actions_today": 12,
            "is_warmup": True,
            "is_active": True,
            "status": "active",
            "proxy_id": "proxy_1",
            "proxy_country": "US"
        }]
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res

        roadmap_res = get_account_warmup_roadmap(self.account_id, self.mock_supabase, self.workspace_id)
        self.assertEqual(roadmap_res["account_id"], self.account_id)
        self.assertEqual(roadmap_res["current_day"], 3)
        self.assertFalse(roadmap_res["is_graduated"])
        self.assertEqual(len(roadmap_res["roadmap"]), 7)
        self.assertIn("vitals", roadmap_res)
        self.assertGreaterEqual(roadmap_res["safety_score"], 75)

    def test_run_warmup_diagnostic_passes(self):
        """Paranoia Layer 0: Warmup diagnostic verifies proxy, jitter, and safety checks."""
        mock_acc_res = MagicMock()
        mock_acc_res.data = [{
            "id": self.account_id,
            "name": "Deeksha LinkedIn",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "actions_today": 2,
            "is_warmup": True,
            "is_active": True,
            "status": "active"
        }]
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res

        diag = run_warmup_diagnostic(self.account_id, self.mock_supabase, self.workspace_id)
        self.assertEqual(diag["status"], "passed")
        self.assertGreaterEqual(len(diag["checks"]), 4)
        for check in diag["checks"]:
            self.assertEqual(check["status"], "pass")

    # =========================================================================
    # LAYER 1: Environmental Failure Analysis — Zero-Migration Fallbacks
    # =========================================================================

    def test_master_view_stats_unmigrated_tables_returns_200_fallback(self):
        """
        Paranoia Layer 1: When daily_campaign_stats and daily_workspace_stats tables
        do not exist (unmigrated Supabase), endpoint cascades to base tables & in-memory stores.
        Must NEVER throw HTTP 500!
        """
        # Simulate missing rollup tables raising exceptions
        def table_router(table_name):
            mock_table = MagicMock()
            if table_name in ("daily_campaign_stats", "daily_workspace_stats"):
                mock_table.select.side_effect = Exception(f"relation '{table_name}' does not exist")
            elif table_name == "workspaces":
                mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO"}])
            elif table_name == "campaigns":
                mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "c1", "status": "ACTIVE", "enrolled_count": 50, "total_connected": 15, "total_replied": 5}]
                )
            elif table_name == "leads":
                mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(count=120, data=[])
            elif table_name == "messages":
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "action_log":
                mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "lead_states":
                mock_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(count=2, data=[])
            elif table_name == "accounts":
                mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "a1", "status": "active"}])
            elif table_name == "processing_jobs":
                mock_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            else:
                mock_table.select.return_value.execute.return_value = MagicMock(data=[])
            return mock_table

        self.mock_supabase.table.side_effect = table_router
        mock_request = MagicMock()

        req = MasterViewRequest(
            date_start="2026-03-01",
            date_end="2026-03-15",
            campaigns=None,
            senders=None,
            timezone="UTC"
        )

        with patch("campaigns.backend.routers.master_view._generate_captain_brief", new_callable=AsyncMock) as mock_brief:
            mock_brief.return_value = "Outreach operating on safe fallbacks."
            res = get_master_view_stats(mock_request, req, self.mock_supabase, self.workspace_id)

        self.assertIn("summary", res)
        self.assertIn("radar_stats", res)
        self.assertEqual(res["summary"]["total_leads"], 120)
        self.assertEqual(res["summary"]["active_campaigns"], 1)
        self.assertEqual(res["funnel"]["enrolled"], 50)
        self.assertEqual(res["funnel"]["connected"], 15)
        self.assertEqual(res["funnel"]["replied"], 5)
        self.assertAlmostEqual(res["radar_stats"]["Acceptance Rate"], 30.0, places=1)
        self.assertAlmostEqual(res["radar_stats"]["Reply Rate"], 33.3, places=1)

    def test_master_view_stats_complete_db_failure_returns_safe_zero_payload(self):
        """
        Paranoia Layer 1: If database drops connection entirely, endpoint returns safe
        zero-state telemetry (200 OK) so the executive dashboard never crashes with 500.
        """
        self.mock_supabase.table.side_effect = Exception("FATAL: Connection to PostgreSQL timed out")
        mock_request = MagicMock()

        req = MasterViewRequest(
            date_start="2026-03-01",
            date_end="2026-03-15",
            campaigns=None,
            senders=None
        )

        res = get_master_view_stats(mock_request, req, self.mock_supabase, self.workspace_id)

        self.assertIn("summary", res)
        self.assertEqual(res["summary"]["total_leads"], 0)
        self.assertEqual(res["summary"]["active_campaigns"], 0)
        self.assertEqual(res["summary"]["account_health"], "Healthy")
        self.assertEqual(res["funnel"]["extracted"], 0)
        self.assertEqual(res["time_series"], [])

    def test_get_account_limits_unmigrated_rpc_and_tables(self):
        """
        Paranoia Layer 1: In an unmigrated database where get_account_action_limit RPC
        and account_daily_action_counts table do not exist, dynamic warmup calculation
        provides safe daily limits without throwing HTTP 500.
        """
        def table_mock(table_name):
            mock_t = MagicMock()
            if table_name == "accounts":
                mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": self.account_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "is_warmup": True,
                        "warmup_target_days": 14
                    }]
                )
            elif table_name == "account_daily_action_counts":
                mock_t.select.side_effect = Exception("relation does not exist")
            elif table_name == "action_log":
                mock_t.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(count=4)
            elif table_name in ("action_type_limits", "account_action_limits"):
                mock_t.select.side_effect = Exception("table does not exist")
            return mock_t

        self.mock_supabase.table.side_effect = table_mock
        # RPC fails (unmigrated)
        self.mock_supabase.rpc.side_effect = Exception("function get_account_action_limit does not exist")

        res = get_account_limits(self.account_id, "connection_request", self.mock_supabase, self.workspace_id)

        self.assertEqual(res["action"], "connection_request")
        self.assertEqual(res["effective_limit"], 10) # Day 1 warmup ceiling
        self.assertEqual(res["used_today"], 4)
        self.assertTrue(res["is_clamped_by_warmup"])
        self.assertFalse(res["has_manual_override"])

    def test_get_account_health_missing_columns_fallback(self):
        """
        Paranoia Layer 1: When newer account columns (warmup_target_days, cookie_expires_at)
        are unmigrated, query gracefully cascades to base columns.
        """
        def table_mock(table_name):
            mock_t = MagicMock()
            if table_name == "accounts":
                # First select with advanced columns fails
                def select_mock(cols):
                    m = MagicMock()
                    if "cookie_expires_at" in cols:
                        m.eq.return_value.execute.side_effect = Exception("column cookie_expires_at does not exist")
                    else:
                        m.eq.return_value.execute.return_value = MagicMock(data=[
                            {"id": "a1", "name": "Sender 1", "status": "active", "is_warmup": True, "created_at": "2026-03-01T00:00:00Z"}
                        ])
                    return m
                mock_t.select.side_effect = select_mock
            elif table_name == "proxies":
                mock_t.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "account_daily_action_counts":
                mock_t.select.side_effect = Exception("relation does not exist")
            elif table_name == "action_log":
                mock_t.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])
            return mock_t

        self.mock_supabase.table.side_effect = table_mock
        mock_req = MagicMock()

        res = get_account_health(mock_req, AccountHealthRequest(), self.mock_supabase, self.workspace_id)
        self.assertIn("accounts", res)
        self.assertEqual(len(res["accounts"]), 1)
        self.assertEqual(res["accounts"][0]["id"], "a1")
        self.assertEqual(res["accounts"][0]["status"], "active")

    def test_get_master_view_filters_fallback_on_db_exception(self):
        """Paranoia Layer 1: Filters endpoint falls back to empty arrays on DB failure."""
        self.mock_supabase.table.side_effect = Exception("Database connection refused")
        mock_req = MagicMock()

        res = get_master_view_filters(mock_req, self.mock_supabase, self.workspace_id)
        self.assertEqual(res, {"workspaces": [], "senders": [], "campaigns": []})

    def test_workspace_boundary_isolation_fail_closed(self):
        """
        Paranoia Layer 1: If user passes campaign/sender IDs that do not belong to their
        workspace, the query fails closed using a zero UUID placeholder instead of querying all data.
        """
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value = mock_table

        req = MasterViewRequest(
            date_start="2026-03-01",
            date_end="2026-03-15",
            campaigns=["foreign-campaign-id"],
            senders=["foreign-sender-id"]
        )
        mock_request = MagicMock()

        # Execute get_master_view_stats
        res = get_master_view_stats(mock_request, req, self.mock_supabase, self.workspace_id)
        # Verify the requested filter was replaced with zero UUID to fail closed
        self.assertEqual(req.campaigns, ["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(req.senders, ["00000000-0000-0000-0000-000000000000"])

    # =========================================================================
    # LAYER 2: Human Paranoia — Input Validation, NaN & Clamping
    # =========================================================================

    def test_radar_stats_zero_division_and_nan_immunity(self):
        """
        Paranoia Layer 2: When all funnel counts are 0, radar stats must produce clean
        0.0 or 100.0 without ZeroDivisionError, NaN, or exceptions.
        """
        def table_router(table_name):
            mock_t = MagicMock()
            if table_name == "workspaces":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
            elif table_name == "campaigns":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "leads":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            elif table_name in ("daily_campaign_stats", "daily_workspace_stats", "messages", "action_log"):
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                mock_t.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "lead_states":
                mock_t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(count=0, data=[])
            elif table_name == "accounts":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "processing_jobs":
                mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            else:
                mock_t.select.return_value.execute.return_value = MagicMock(data=[])
            return mock_t

        self.mock_supabase.table.side_effect = table_router
        mock_request = MagicMock()

        req = MasterViewRequest(date_start="2026-03-01", date_end="2026-03-15")
        res = get_master_view_stats(mock_request, req, self.mock_supabase, self.workspace_id)

        radar = res["radar_stats"]
        self.assertEqual(radar["Acceptance Rate"], 0.0)
        self.assertEqual(radar["Reply Rate"], 0.0)
        self.assertEqual(radar["Booking Rate"], 0.0)
        self.assertEqual(radar["Sentiment (Pos)"], 0.0)
        self.assertEqual(radar["Deliverability"], 100.0)
        self.assertEqual(radar["Bounces"], 0.0)

    def test_radar_stats_clamped_strictly_between_0_and_100(self):
        """
        Paranoia Layer 2: Even with anomalous data (e.g. negative failed counts or
        outlier values), radar metrics are strictly clamped to [0.0, 100.0].
        """
        def table_router(table_name):
            mock_t = MagicMock()
            if table_name == "workspaces":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO"}])
            elif table_name == "campaigns":
                # Anomaly: 200 connected out of 50 enrolled
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "c1", "status": "ACTIVE", "enrolled_count": 50, "total_connected": 200, "total_replied": 500}]
                )
            elif table_name == "leads":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=50, data=[])
            elif table_name in ("daily_campaign_stats", "daily_workspace_stats", "messages", "action_log"):
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                mock_t.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "lead_states":
                # Anomaly: failed count exceeds enrolled count
                mock_t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(count=999, data=[])
            elif table_name == "accounts":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "processing_jobs":
                mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            else:
                mock_t.select.return_value.execute.return_value = MagicMock(data=[])
            return mock_t

        self.mock_supabase.table.side_effect = table_router
        mock_request = MagicMock()

        req = MasterViewRequest(date_start="2026-03-01", date_end="2026-03-15")
        res = get_master_view_stats(mock_request, req, self.mock_supabase, self.workspace_id)

        radar = res["radar_stats"]
        self.assertLessEqual(radar["Acceptance Rate"], 100.0)
        self.assertGreaterEqual(radar["Acceptance Rate"], 0.0)
        self.assertLessEqual(radar["Reply Rate"], 100.0)
        self.assertGreaterEqual(radar["Reply Rate"], 0.0)
        self.assertLessEqual(radar["Deliverability"], 100.0)
        self.assertGreaterEqual(radar["Deliverability"], 0.0)
        self.assertLessEqual(radar["Bounces"], 100.0)
        self.assertGreaterEqual(radar["Bounces"], 0.0)

    def test_validate_date_range_human_errors(self):
        """Paranoia Layer 2: Inverted dates, non-ISO strings, and excessive ranges rejected with 400."""
        # Inverted dates
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2026-03-20", "2026-03-10")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("date_end must be after date_start", ctx.exception.detail)

        # Malformed format
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("20-03-2026", "2026-03-25")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid date format", ctx.exception.detail)

        # Exceeded max days
        with self.assertRaises(HTTPException) as ctx:
            validate_date_range("2020-01-01", "2026-01-01", max_days=365)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Date range cannot exceed", ctx.exception.detail)

    def test_get_funnel_leads_rejects_arbitrary_step_injection(self):
        """Paranoia Layer 2: Reject arbitrary or malicious funnel steps with 400."""
        mock_req = MagicMock()
        payload = FunnelLeadsRequest(
            step="SELECT * FROM users",
            date_start="2026-03-01",
            date_end="2026-03-15"
        )
        with self.assertRaises(HTTPException) as ctx:
            get_funnel_leads(mock_req, payload, self.mock_supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid funnel step", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
