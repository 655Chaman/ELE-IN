import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pytz

from campaigns.backend.services.sto_service import (
    compute_lead_jitter_minutes,
    compute_lead_sto_window,
    calculate_sto_next_run,
    should_use_sto,
    DEFAULT_B2B_PEAK_HOURS,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestHorizon28SendTimeOptimization(unittest.TestCase):
    """
    Test suite for Horizon 28: Dynamic Send-Time Optimization (AI STO) & Prospect Activity-Aware Pacing.
    Implements Three-Layer Logic Architecture (Paranoia Framework):
      Layer 0: Foundational Layer (engagement clustering, peak hour scoring, anti-bot jitter, dynamic run calculation)
      Layer 1: Environmental Failure Analysis (database timeout resilience, non-IANA timezone fallback, DST safety, working days curfews)
      Layer 2: Human Paranoia (malformed schedule inputs, deterministic hash distribution, IDOR defense)
    """

    def setUp(self):
        self.workspace_id = "ws_test_horizon28"
        self.mock_supabase = MagicMock()
        # Default mock supabase returns empty lists for queries
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = []
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER TESTS
    # =========================================================================

    def test_layer0_sto_window_with_historical_engagement(self):
        """Layer 0: Clusters historical email opens and inbound replies into local timezone hours."""
        # Simulate events in UTC:
        # 14:00 UTC for Europe/London is 14:00 local time.
        # 15:00 UTC for Europe/London is 15:00 local time.
        mock_events = [
            {"event_type": "open", "created_at": "2026-10-01T14:10:00Z"},
            {"event_type": "open", "created_at": "2026-10-02T14:25:00Z"},
            {"event_type": "click", "created_at": "2026-10-03T15:05:00Z"},  # click weight = 2.0
            {"event_type": "open", "created_at": "2026-10-04T15:30:00Z"},  # open weight = 1.0 (total for 15:00 = 3.0)
        ]
        mock_messages = [
            {"created_at": "2026-10-05T15:40:00Z"}  # reply weight = 3.0 (total for 15:00 = 6.0)
        ]

        def mock_table(name):
            t = MagicMock()
            if name == "email_events":
                t.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value.data = mock_events
            elif name == "messages":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = mock_messages
            return t

        mock_db = MagicMock()
        mock_db.table = mock_table

        res = compute_lead_sto_window(
            supabase=mock_db,
            lead_id="lead_engaged_123",
            tz_str="Europe/London",
            schedule={"start_hour": 9, "end_hour": 18}
        )

        # In October, Europe/London is in BST (UTC+1).
        # 15:00 UTC corresponds to 16:00 BST local time, which had the highest weighted score (6.0)
        self.assertEqual(res["best_hour"], 16)
        self.assertEqual(res["source"], "historical_engagement")
        self.assertGreater(res["confidence"], 0.7)
        self.assertEqual(res["data_points"], 5)

    def test_layer0_sto_window_cold_lead_industry_priors(self):
        """Layer 0: Cold leads fall back to deterministic B2B peak hours (10:00 AM or 14:00 PM)."""
        res = compute_lead_sto_window(
            supabase=self.mock_supabase,
            lead_id="lead_cold_456",
            tz_str="America/New_York",
            schedule={"start_hour": 9, "end_hour": 17}
        )

        self.assertIn(res["best_hour"], DEFAULT_B2B_PEAK_HOURS)
        self.assertEqual(res["source"], "industry_prior")
        self.assertEqual(res["data_points"], 0)
        self.assertEqual(res["confidence"], 0.35)

    def test_layer0_anti_bot_jitter_determinism_and_spread(self):
        """Layer 0: Jitter is deterministic per lead ID and spreads across the 5–25 minute window."""
        lead_a = "lead_alpha_001"
        lead_b = "lead_beta_002"

        jitter_a1 = compute_lead_jitter_minutes(lead_a)
        jitter_a2 = compute_lead_jitter_minutes(lead_a)
        self.assertEqual(jitter_a1, jitter_a2)  # Deterministic / idempotent
        self.assertGreaterEqual(jitter_a1, 5)
        self.assertLessEqual(jitter_a1, 25)

        jitter_b = compute_lead_jitter_minutes(lead_b)
        self.assertGreaterEqual(jitter_b, 5)
        self.assertLessEqual(jitter_b, 25)

    def test_layer0_calculate_sto_next_run_scheduling(self):
        """Layer 0: Schedules for today if time is before the STO slot, or next active day if past."""
        # 08:00 local time in America/New_York
        tz_ny = pytz.timezone("America/New_York")
        base_dt_morning = tz_ny.localize(datetime(2026, 10, 13, 8, 0, 0))  # A Tuesday

        # Schedule with best_hour = 10, start=9, end=17
        schedule = {"start_hour": 9, "end_hour": 17, "active_days": [0, 1, 2, 3, 4]}

        with patch("campaigns.backend.services.sto_service.compute_lead_sto_window") as mock_sto, \
             patch("campaigns.backend.services.sto_service.compute_lead_jitter_minutes") as mock_jit:
            mock_sto.return_value = {"best_hour": 10, "confidence": 0.8, "data_points": 5}
            mock_jit.return_value = 15

            next_run_today = calculate_sto_next_run(
                base_time=base_dt_morning,
                target_tz="America/New_York",
                lead_id="lead_test",
                schedule=schedule,
                supabase=self.mock_supabase
            )

            # Local time should be 10:15 AM today (Tuesday, Oct 13)
            local_scheduled = next_run_today.astimezone(tz_ny)
            self.assertEqual(local_scheduled.day, 13)
            self.assertEqual(local_scheduled.hour, 10)
            self.assertEqual(local_scheduled.minute, 15)

            # If current time is 16:00 PM, should schedule for Wednesday, Oct 14 at 10:15 AM
            base_dt_afternoon = tz_ny.localize(datetime(2026, 10, 13, 16, 0, 0))
            next_run_tomorrow = calculate_sto_next_run(
                base_time=base_dt_afternoon,
                target_tz="America/New_York",
                lead_id="lead_test",
                schedule=schedule,
                supabase=self.mock_supabase
            )
            local_scheduled_tomorrow = next_run_tomorrow.astimezone(tz_ny)
            self.assertEqual(local_scheduled_tomorrow.day, 14)
            self.assertEqual(local_scheduled_tomorrow.hour, 10)
            self.assertEqual(local_scheduled_tomorrow.minute, 15)

    def test_layer0_should_use_sto_flag_variants(self):
        """Layer 0: should_use_sto recognizes all campaign and schedule flag variants."""
        # Mode variants
        self.assertTrue(should_use_sto(campaign={"metadata": {"scheduling_mode": "ai_sto"}}))
        self.assertTrue(should_use_sto(campaign={"metadata": {"scheduling_mode": "sto_predictive"}}))
        self.assertTrue(should_use_sto(campaign={"metadata": {"scheduling_mode": "send_time_optimization"}}))

        # Boolean flags
        self.assertTrue(should_use_sto(campaign={"metadata": {"ai_sto_enabled": True}}))
        self.assertTrue(should_use_sto(schedule={"ai_sto_enabled": True}))
        self.assertTrue(should_use_sto(schedule={"sto_enabled": True}))

        # False cases
        self.assertFalse(should_use_sto(campaign={"metadata": {"scheduling_mode": "campaign_timezone"}}))
        self.assertFalse(should_use_sto(campaign={}))
        self.assertFalse(should_use_sto(None, None))

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS TESTS
    # =========================================================================

    def test_layer1_db_failure_or_missing_tables_fails_open_safely(self):
        """Layer 1: Database timeout or missing email_events table falls back cleanly to industry prior."""
        broken_db = MagicMock()
        broken_db.table.side_effect = Exception("Relation 'email_events' does not exist")

        res = compute_lead_sto_window(
            supabase=broken_db,
            lead_id="lead_err_789",
            tz_str="America/Chicago",
            schedule={"start_hour": 9, "end_hour": 17}
        )

        self.assertEqual(res["source"], "industry_prior")
        self.assertIn(res["best_hour"], DEFAULT_B2B_PEAK_HOURS)
        self.assertEqual(res["confidence"], 0.35)

    def test_layer1_safe_localize_dst_spring_forward(self):
        """Layer 1: calculate_sto_next_run handles spring-forward daylight saving gap gracefully."""
        # Sunday, March 8, 2026: 2:00 AM spring forward to 3:00 AM in America/New_York
        tz_ny = pytz.timezone("America/New_York")
        base_time = tz_ny.localize(datetime(2026, 3, 6, 17, 0, 0))  # Friday

        # Schedule allowing weekend sending
        schedule = {"start_hour": 2, "end_hour": 18, "weekend_sending": True, "active_days": [5, 6]}

        with patch("campaigns.backend.services.sto_service.compute_lead_sto_window") as mock_sto:
            mock_sto.return_value = {"best_hour": 2, "confidence": 0.5, "data_points": 2}
            next_run = calculate_sto_next_run(
                base_time=base_time,
                target_tz="America/New_York",
                lead_id="lead_dst",
                schedule=schedule,
                supabase=self.mock_supabase
            )
            self.assertIsNotNone(next_run)
            self.assertEqual(next_run.tzinfo, pytz.UTC)

    def test_layer1_weekend_and_curfew_enforcement(self):
        """Layer 1: Friday evening deferral advances past weekend to Monday morning STO slot."""
        tz_london = pytz.timezone("Europe/London")
        # Friday Oct 16, 2026 at 19:00 PM (curfew)
        friday_evening = tz_london.localize(datetime(2026, 10, 16, 19, 0, 0))
        schedule = {"start_hour": 9, "end_hour": 17, "active_days": [0, 1, 2, 3, 4]}  # Mon-Fri only

        with patch("campaigns.backend.services.sto_service.compute_lead_sto_window") as mock_sto, \
             patch("campaigns.backend.services.sto_service.compute_lead_jitter_minutes") as mock_jit:
            mock_sto.return_value = {"best_hour": 11, "confidence": 0.6, "data_points": 3}
            mock_jit.return_value = 10

            next_run = calculate_sto_next_run(
                base_time=friday_evening,
                target_tz="Europe/London",
                lead_id="lead_weekend_skip",
                schedule=schedule,
                supabase=self.mock_supabase
            )

            local_dt = next_run.astimezone(tz_london)
            # Must advance to Monday, Oct 19!
            self.assertEqual(local_dt.day, 19)
            self.assertEqual(local_dt.weekday(), 0)  # Monday
            self.assertEqual(local_dt.hour, 11)
            self.assertEqual(local_dt.minute, 10)

    def test_layer1_orchestrator_working_hours_deferral_with_sto(self):
        """Layer 1: EleInOrchestrator defers out-of-hours leads to the predicted STO slot."""
        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)

        # Mock campaign with AI STO enabled
        campaign = {
            "metadata": {
                "scheduling_mode": "ai_sto",
                "schedule": {"start_hour": 9, "end_hour": 17, "active_days": [0, 1, 2, 3, 4]},
                "timezone": "America/New_York",
                "enforce_working_hours": True
            }
        }
        lead = {"timezone": "America/New_York", "id": "lead_sto_defer"}

        # Simulate update_state call with use_sto=True
        base_utc = datetime(2026, 10, 13, 23, 0, 0)  # 23:00 UTC (after working hours in NY)

        with patch("campaigns.backend.services.elein_orchestrator.adjust_to_working_hours") as mock_std_adj, \
             patch("campaigns.backend.services.sto_service.calculate_sto_next_run") as mock_sto_calc:
            mock_sto_calc.return_value = pytz.UTC.localize(datetime(2026, 10, 14, 14, 15, 0))

            orchestrator.update_state(
                state_id="state_123",
                node_id="node_next",
                status="pending",
                next_run_at=base_utc,
                lease_token="lease_abc",
                tz_str="America/New_York",
                schedule=campaign["metadata"]["schedule"],
                lead_id=lead["id"],
                use_sto=True
            )

            # STO calculation should be called, not standard 9am adjustment
            mock_sto_calc.assert_called_once()
            mock_std_adj.assert_not_called()

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA TESTS
    # =========================================================================

    def test_layer2_invalid_or_non_iana_timezone_sanitization(self):
        """Layer 2: Handles non-IANA or garbage timezones ('PST', 'Underwater', None) safely without crash."""
        for bad_tz in ["PST", "EST", "GMT", "Faketown/Mars", "", None]:
            res = compute_lead_sto_window(
                supabase=self.mock_supabase,
                lead_id="lead_bad_tz",
                tz_str=bad_tz,
                schedule={"start_hour": 9, "end_hour": 17}
            )
            self.assertIsNotNone(res)
            self.assertIn(res["best_hour"], DEFAULT_B2B_PEAK_HOURS)

    def test_layer2_clamped_working_hours_boundary(self):
        """Layer 2: Constrains STO hour and jitter within narrow schedule boundaries (e.g. 11:00–13:00)."""
        narrow_schedule = {"start_hour": 11, "end_hour": 13, "active_days": [0, 1, 2, 3, 4]}

        res = compute_lead_sto_window(
            supabase=self.mock_supabase,
            lead_id="lead_narrow",
            tz_str="UTC",
            schedule=narrow_schedule
        )

        # Best hour MUST be either 11 or 12 (since end_hour is 13)
        self.assertIn(res["best_hour"], [11, 12])

    def test_layer2_evaluate_sto_slot_api_endpoint_and_idor(self):
        """Layer 2: API router endpoint enforces workspace isolation and returns complete STO preview."""
        from fastapi import HTTPException
        from campaigns.backend.routers.elein import evaluate_sto_slot, EvaluateStoSlotRequest

        # 1. IDOR Defense: foreign lead ID returns 404
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        req_idor = EvaluateStoSlotRequest(lead_id="foreign_lead_404")
        with self.assertRaises(HTTPException) as cm:
            evaluate_sto_slot(req=req_idor, workspace_id="my_ws", supabase=mock_db)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertIn("Lead not found in current workspace", cm.exception.detail)

        # 2. Legitimate preview with ad-hoc timezone
        req_valid = EvaluateStoSlotRequest(
            timezone="America/Los_Angeles",
            schedule={"start_hour": 9, "end_hour": 17}
        )
        api_res = evaluate_sto_slot(req=req_valid, workspace_id="my_ws", supabase=mock_db)
        self.assertEqual(api_res["status"], "success")
        self.assertEqual(api_res["timezone"], "America/Los_Angeles")
        self.assertIn("sto_window", api_res)
        self.assertIn("recommended_local_time", api_res)
        self.assertIn("next_run_at_utc", api_res)

    def test_layer2_tier_gating_free_vs_pro_on_sto_and_activation(self):
        """Layer 2: Free tier is blocked (402/403) on evaluate_sto_slot and activate_campaign with ai_sto; Pro tier succeeds."""
        from fastapi import HTTPException
        from campaigns.backend.routers.elein import (
            evaluate_sto_slot,
            EvaluateStoSlotRequest,
            activate_campaign,
        )

        # 1. Free tier blocked on evaluate_sto_slot with 402
        free_db = MagicMock()
        free_db.rpc.return_value.execute.return_value.data = {"tier": "FREE", "balance": 100}
        req = EvaluateStoSlotRequest(timezone="America/New_York")
        with self.assertRaises(HTTPException) as cm_free:
            evaluate_sto_slot(req=req, workspace_id="ws_real_free_tier", supabase=free_db)
        self.assertEqual(cm_free.exception.status_code, 402)
        self.assertIn("can_ai_sto", str(cm_free.exception.detail))

        # 2. Pro tier succeeds on evaluate_sto_slot
        pro_db = MagicMock()
        pro_db.rpc.return_value.execute.return_value.data = {"tier": "PRO", "balance": 5000}
        pro_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        pro_res = evaluate_sto_slot(req=req, workspace_id="ws_real_pro_tier", supabase=pro_db)
        self.assertEqual(pro_res["status"], "success")

        # 3. Free tier blocked on activate_campaign when scheduling_mode == 'ai_sto'
        act_db = MagicMock()

        def table_router(name):
            t = MagicMock()
            if name == "campaigns":
                q = MagicMock()
                q.eq.return_value.eq.return_value.execute.return_value.data = [{
                    "id": "camp_sto_1",
                    "status": "DRAFT",
                    "nodes_json": [{"id": "n1", "type": "connection_request"}],
                    "lead_list_id": "list_1",
                    "metadata": {"scheduling_mode": "ai_sto", "ai_sto_enabled": True},
                }]
                cnt_res = MagicMock()
                cnt_res.count = 0
                q.eq.return_value.eq.return_value.neq.return_value.execute.return_value = cnt_res
                t.select.return_value = q
            elif name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"tier": "FREE"}]
            elif name == "campaign_nodes":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"node_type": "connection_request"}]
            return t

        act_db.table.side_effect = table_router
        with self.assertRaises(HTTPException) as cm_act:
            activate_campaign(campaign_id="camp_sto_1", workspace_id="ws_real_free_tier", client=act_db)
        self.assertEqual(cm_act.exception.status_code, 403)
        self.assertIn("Send-Time Optimization", str(cm_act.exception.detail))


if __name__ == "__main__":
    unittest.main()

