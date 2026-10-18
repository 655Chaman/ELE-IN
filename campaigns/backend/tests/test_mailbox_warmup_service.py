"""
Unit Tests for Smart Mailbox Auto-Warmup Engine & Adaptive Ramp Curves
======================================================================
Tests integrations/backend/services/mailbox_warmup_service.py against
the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Core mathematical curves (Linear, Sigmoid, Aggressive),
           reputation weighting, peer exchange simulation, and daily ticks.
- Layer 1: Environmental Failure Analysis (boundary clamping, no division by zero,
           exponent safety, Supabase resilient fallbacks).
- Layer 2: Human Paranoia (malformed types, inverted limits, negative inputs,
           missing fields, extreme outliers).
"""

import unittest
from unittest.mock import MagicMock

from integrations.backend.services.mailbox_warmup_service import (
    WarmupCurveType,
    WarmupHealthStatus,
    normalize_curve_type,
    calculate_warmup_ramp_projection,
    calculate_inbox_warmup_health_score,
    simulate_peer_warmup_exchange,
    advance_inbox_warmup_tick,
)


class TestMailboxWarmupService(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()

    # =========================================================================
    # LAYER 0: FOUNDATIONAL MATHEMATICAL CURVES & PROJECTIONS
    # =========================================================================

    def test_normalize_curve_type(self):
        """Verify normalization across strings, enums, and synonyms."""
        self.assertEqual(normalize_curve_type("linear"), WarmupCurveType.LINEAR)
        self.assertEqual(normalize_curve_type("LINEAR"), WarmupCurveType.LINEAR)
        self.assertEqual(normalize_curve_type("logarithmic"), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type("s-curve"), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type("sigmoid"), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type("balanced"), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type("aggressive"), WarmupCurveType.AGGRESSIVE)
        self.assertEqual(normalize_curve_type("aged"), WarmupCurveType.AGGRESSIVE)
        # Fallback for unknowns and None
        self.assertEqual(normalize_curve_type("unknown_random"), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type(None), WarmupCurveType.LOGARITHMIC)

    def test_linear_projection_foundational(self):
        """Layer 0: Linear ramp projects steady incremental growth."""
        res = calculate_warmup_ramp_projection(
            curve_type="LINEAR",
            start_limit=5,
            target_limit=50,
            ramp_days=28,
            current_day=14
        )

        self.assertEqual(res["curve_type"], "LINEAR")
        self.assertEqual(res["start_limit"], 5)
        self.assertEqual(res["target_limit"], 50)
        self.assertEqual(res["ramp_days"], 28)
        self.assertEqual(res["current_day"], 14)

        proj = res["projection"]
        self.assertEqual(len(proj), 29)  # Days 0 to 28 inclusive

        # Day 0: start limit, 100% warmup, 0 cold outreach
        self.assertEqual(proj[0]["day"], 0)
        self.assertEqual(proj[0]["total_daily_cap"], 5)
        self.assertEqual(proj[0]["warmup_cap"], 5)
        self.assertEqual(proj[0]["cold_outreach_cap"], 0)
        self.assertEqual(proj[0]["warmup_ratio_pct"], 100.0)

        # Day 14 (halfway): total cap ~ 28 (5 + 45*0.5)
        # Warmup ratio: 0.20 + 0.80 * (1 - 0.5)^2 = 0.40 (40%)
        self.assertEqual(proj[14]["day"], 14)
        self.assertEqual(proj[14]["warmup_ratio_pct"], 40.0)
        self.assertEqual(proj[14]["warmup_cap"] + proj[14]["cold_outreach_cap"], proj[14]["total_daily_cap"])

        # Day 28 (final): target limit 50, 20% warmup ratio
        self.assertEqual(proj[28]["day"], 28)
        self.assertEqual(proj[28]["total_daily_cap"], 50)
        self.assertEqual(proj[28]["warmup_ratio_pct"], 20.0)
        self.assertEqual(proj[28]["warmup_cap"], 10)  # 50 * 0.20
        self.assertEqual(proj[28]["cold_outreach_cap"], 40) # 50 - 10

    def test_logarithmic_sigmoid_projection_foundational(self):
        """Layer 0: Sigmoid curve exhibits gentle initial crawl and smooth plateau."""
        res = calculate_warmup_ramp_projection(
            curve_type="LOGARITHMIC",
            start_limit=5,
            target_limit=50,
            ramp_days=28,
            current_day=0
        )

        proj = res["projection"]
        # Day 0 to 5 should crawl slowly (IP trust building)
        day_5_cap = proj[5]["total_daily_cap"]
        self.assertLessEqual(day_5_cap, 12, "Day 5 must crawl gently below 12 for IP trust")

        # Day 28 must exactly reach target limit and never exceed it
        self.assertEqual(proj[28]["total_daily_cap"], 50)
        for entry in proj:
            self.assertLessEqual(entry["total_daily_cap"], 50)
            self.assertGreaterEqual(entry["total_daily_cap"], 5)
            self.assertEqual(entry["warmup_cap"] + entry["cold_outreach_cap"], entry["total_daily_cap"])

    def test_aggressive_projection_foundational(self):
        """Layer 0: Aggressive curve scales faster for aged domains."""
        res_log = calculate_warmup_ramp_projection("LOGARITHMIC", 5, 50, 28, 7)
        res_agg = calculate_warmup_ramp_projection("AGGRESSIVE", 5, 50, 28, 7)

        # On day 7, aggressive curve must have higher capacity than gentle logarithmic crawl
        day_7_log = res_log["projection"][7]["total_daily_cap"]
        day_7_agg = res_agg["projection"][7]["total_daily_cap"]
        self.assertGreater(day_7_agg, day_7_log, "Aggressive curve must ramp faster than logarithmic on day 7")

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS & BOUNDS CLAMPING
    # =========================================================================

    def test_parameter_clamping_environmental_safety(self):
        """Layer 1: Enforces physical parameter bounds."""
        # start_limit >= 1, target_limit <= 200, ramp_days in [7, 90]
        res = calculate_warmup_ramp_projection(
            curve_type="LOGARITHMIC",
            start_limit=-10,      # should clamp to 1
            target_limit=5000,    # should clamp to 200
            ramp_days=3,          # should clamp to 7
            current_day=-5        # should clamp to 0
        )

        self.assertEqual(res["start_limit"], 1)
        self.assertEqual(res["target_limit"], 200)
        self.assertEqual(res["ramp_days"], 7)
        self.assertEqual(res["current_day"], 0)
        self.assertEqual(len(res["projection"]), 8)  # Days 0 to 7

        # Inverted limits: start_limit > target_limit
        res_inv = calculate_warmup_ramp_projection(
            start_limit=80,
            target_limit=20
        )
        self.assertGreaterEqual(res_inv["target_limit"], res_inv["start_limit"])

    def test_current_day_beyond_ramp_days(self):
        """Layer 1: Safely handles mailboxes active beyond the initial ramp schedule."""
        res = calculate_warmup_ramp_projection(
            start_limit=5,
            target_limit=50,
            ramp_days=28,
            current_day=45
        )
        self.assertEqual(res["current_day"], 45)
        # Should retain maintenance floor caps (50 total, ~10 warmup, ~40 cold)
        self.assertEqual(res["today_warmup_cap"] + res["today_cold_cap"], 50)
        self.assertGreaterEqual(res["today_warmup_cap"], 1)

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & MALFORMED INPUTS
    # =========================================================================

    def test_malformed_types_human_paranoia(self):
        """Layer 2: Handles strings, floats, None, and garbage types gracefully."""
        res = calculate_warmup_ramp_projection(
            curve_type="nonsense_curve_123",
            start_limit="5",
            target_limit="50",
            ramp_days="28",
            current_day="10"
        )
        self.assertEqual(res["curve_type"], "LOGARITHMIC")
        self.assertEqual(res["start_limit"], 5)
        self.assertEqual(res["target_limit"], 50)
        self.assertEqual(res["ramp_days"], 28)
        self.assertEqual(res["current_day"], 10)

    # =========================================================================
    # HEALTH SCORE REPUTATION & THROTTLING TESTS
    # =========================================================================

    def test_health_score_pristine_peak_health(self):
        """Evaluates pristine mailbox reaching PEAK_HEALTH (>=85)."""
        inbox = {
            "warmup_days_active": 35,
            "aggregate_bounce_rate_pct": 0.0,
            "spam_complaint_rate_pct": 0.0,
            "peer_engagement_rate_pct": 45.0
        }
        res = calculate_inbox_warmup_health_score(inbox)

        # 20 (age >=30) + 30 (bounce 0%) + 30 (spam 0%) + 20 (peer >=40%) = 100
        self.assertEqual(res["health_score"], 100)
        self.assertEqual(res["status"], WarmupHealthStatus.PEAK_HEALTH.value)
        self.assertEqual(res["throttle_cold_ratio"], 1.0)
        self.assertFalse(res["emergency_paused"])

    def test_health_score_ramping_optimal(self):
        """Evaluates ramping mailbox in RAMPING_OPTIMAL (70-84)."""
        inbox = {
            "warmup_days_active": 14,             # 15 pts
            "aggregate_bounce_rate_pct": 1.2,     # 25 pts (<1.5%)
            "spam_complaint_rate_pct": 0.02,      # 20 pts (<0.05%)
            "peer_engagement_rate_pct": 30.0      # 15 pts (>=25%)
        }
        res = calculate_inbox_warmup_health_score(inbox)
        # 15 + 25 + 20 + 15 = 75
        self.assertEqual(res["health_score"], 75)
        self.assertEqual(res["status"], WarmupHealthStatus.RAMPING_OPTIMAL.value)
        self.assertEqual(res["throttle_cold_ratio"], 1.0)
        self.assertFalse(res["emergency_paused"])

    def test_health_score_needs_recovery_50_percent_throttle(self):
        """Evaluates mailbox entering recovery zone (50-69) triggering 50% cold throttle."""
        inbox = {
            "warmup_days_active": 5,              # 10 pts (3-6 days)
            "aggregate_bounce_rate_pct": 2.2,     # 15 pts (<3.0%)
            "spam_complaint_rate_pct": 0.07,      # 10 pts (<0.10%)
            "peer_engagement_rate_pct": 30.0      # 15 pts
        }
        res = calculate_inbox_warmup_health_score(inbox)
        # 10 + 15 + 10 + 15 = 50
        self.assertEqual(res["health_score"], 50)
        self.assertEqual(res["status"], WarmupHealthStatus.NEEDS_RECOVERY.value)
        self.assertEqual(res["throttle_cold_ratio"], 0.5)
        self.assertFalse(res["emergency_paused"])
        self.assertTrue(any("50%" in r for r in res["recommendations"]))

    def test_health_score_emergency_paused(self):
        """Evaluates severe reputation hit (<50) triggering 100% cold outreach emergency pause."""
        inbox = {
            "warmup_days_active": 2,              # 5 pts (<3 days)
            "aggregate_bounce_rate_pct": 4.5,     # 0 pts (>=3.0%)
            "spam_complaint_rate_pct": 0.15,      # 0 pts (>=0.10%)
            "peer_engagement_rate_pct": 20.0      # 10 pts
        }
        res = calculate_inbox_warmup_health_score(inbox)
        # 5 + 0 + 0 + 10 = 15
        self.assertEqual(res["health_score"], 15)
        self.assertEqual(res["status"], WarmupHealthStatus.EMERGENCY_PAUSED.value)
        self.assertEqual(res["throttle_cold_ratio"], 0.0)
        self.assertTrue(res["emergency_paused"])
        self.assertTrue(any("Critical" in r or "pause" in r.lower() for r in res["recommendations"]))

    def test_health_score_derives_rates_from_counts(self):
        """Layer 1: Gracefully calculates rates from raw event counts if pct keys omitted."""
        metrics = {
            "warmup_days_active": 30,
            "total_sent": 200,
            "total_bounces": 1,        # 1/200 = 0.5% (<1.5% -> 25 pts)
            "total_spam_complaints": 0 # 0% -> 30 pts
        }
        res = calculate_inbox_warmup_health_score({}, recent_metrics=metrics)
        # 20 (age) + 25 (bounce) + 30 (spam) + 15 (default engagement 35%) = 90
        self.assertEqual(res["health_score"], 90)
        self.assertEqual(res["status"], WarmupHealthStatus.PEAK_HEALTH.value)

    # =========================================================================
    # SYNTHETIC PEER WARMUP EXCHANGE TESTS
    # =========================================================================

    def test_simulate_peer_warmup_exchange(self):
        """Verifies synthetic B2B conversation generation and mailbox interaction flags."""
        sender = {"email": "alex@outbound-acme.com", "name": "Alex Taylor"}
        peer = {"email": "jordan@peer-corp.io", "name": "Jordan Lee"}

        exchange = simulate_peer_warmup_exchange(sender, peer, thread_depth=2)

        self.assertEqual(exchange["status"], "completed")
        self.assertEqual(exchange["sender"], "alex@outbound-acme.com")
        self.assertEqual(exchange["recipient"], "jordan@peer-corp.io")
        self.assertTrue(exchange["landed_inbox"])
        self.assertTrue(exchange["saved_from_spam"])
        self.assertTrue(exchange["starred"])
        self.assertTrue(exchange["marked_important"])
        self.assertTrue(exchange["replied"])
        self.assertEqual(exchange["thread_depth"], 2)
        self.assertIn("Hi Jordan", exchange["initial_message"])
        self.assertIn("Alex", exchange["reply_message"])
        self.assertTrue(exchange["subject"].strip())

    def test_simulate_peer_warmup_exchange_fallback_emails(self):
        """Layer 2: Handles missing email dictionaries safely."""
        exchange = simulate_peer_warmup_exchange({}, {}, thread_depth=-1)
        self.assertEqual(exchange["status"], "completed")
        self.assertIn("@", exchange["sender"])
        self.assertIn("@", exchange["recipient"])
        self.assertEqual(exchange["thread_depth"], 1)

    # =========================================================================
    # ADVANCE INBOX WARMUP TICK & SUPABASE PERSISTENCE TESTS
    # =========================================================================

    def test_advance_inbox_warmup_tick_without_supabase(self):
        """Tick increments day, recalculates caps and health score without external DB."""
        inbox = {
            "warmup_days_active": 5,
            "warmup_start_limit": 5,
            "max_daily_limit": 50,
            "ramp_days": 28,
            "aggregate_bounce_rate_pct": 0.0,
            "spam_complaint_rate_pct": 0.0
        }

        updated = advance_inbox_warmup_tick(inbox, supabase=None)

        self.assertEqual(updated["warmup_days_active"], 6)
        self.assertEqual(updated["current_ramp_day"], 6)
        self.assertGreater(updated["current_daily_limit"], 0)
        self.assertGreater(updated["health_score"], 0)
        self.assertFalse(updated["supabase_updated"])

    def test_advance_inbox_warmup_tick_with_mock_supabase_success(self):
        """Layer 1: Updates Supabase record when client is provided."""
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_execute = MagicMock(return_value=MagicMock(data=[{"id": "box-123"}]))

        self.mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq
        mock_eq.execute = mock_execute

        inbox = {
            "id": "box-123",
            "warmup_days_active": 10,
            "warmup_start_limit": 5,
            "max_daily_limit": 50,
            "ramp_days": 28
        }

        updated = advance_inbox_warmup_tick(inbox, supabase=self.mock_supabase)

        self.assertEqual(updated["warmup_days_active"], 11)
        self.assertTrue(updated["supabase_updated"])
        self.mock_supabase.table.assert_called_with("warmup_mailboxes")

    def test_advance_inbox_warmup_tick_with_supabase_failure_resilience(self):
        """Layer 1: Resilient fallback when Supabase throws exception."""
        self.mock_supabase.table.side_effect = Exception("Supabase connection timeout")

        inbox = {
            "id": "box-error-test",
            "warmup_days_active": 2,
            "warmup_start_limit": 5,
            "max_daily_limit": 50,
            "ramp_days": 28
        }

        # Must not raise an exception; gracefully logs error and continues
        updated = advance_inbox_warmup_tick(inbox, supabase=self.mock_supabase)

        self.assertEqual(updated["warmup_days_active"], 3)
        self.assertFalse(updated["supabase_updated"])
        self.assertIn("Supabase connection timeout", updated["supabase_error"])


if __name__ == "__main__":
    unittest.main()
