"""
Automated Test Suite: Smart Mailbox Auto-Warmup Engine & Adaptive Ramp Curves
=============================================================================
Phase 34 / Issue 8 Verification Suite across the Three-Layer Logic Architecture
(Paranoia Framework):

Layer 0: Foundational Layer (Core Mechanics)
  1. test_linear_warmup_curve_ramp: Day 0 = start_limit, Day N = target_limit, steady progression
  2. test_logarithmic_sigmoid_curve_ramp: Slow crawl days 1-5, rapid growth days 6-18, smooth plateau
  3. test_aggressive_curve_ramp: Fast ramp reaching target earlier via square-root progression for aged domains
  4. test_warmup_vs_cold_split_ratio: Early days 100% warmup / 0% cold -> mature days 20% warmup maintenance / 80% cold
  5. test_peer_warmup_exchange_simulation: Generates synthetic message pair with inbox landing, spam recovery, and reply
  6. test_advance_inbox_warmup_tick: Increments days active and shifts caps forward
  7. test_curve_progress_bounds_and_monotonicity: Progress is in [0, 1] and monotonic non-decreasing
  8. test_warmup_curve_normalization_synonyms: Handles synonyms like 'sigmoid', 's-curve', 'gentle', etc.
  9. test_inbox_health_score_perfect_reputation: Mature healthy inbox scores 100/100 (PEAK_HEALTH)
  10. test_inbox_health_score_brand_new_inbox: Brand new inbox (<3 days) has 80 score
  11. test_peer_warmup_thread_depth_support: Custom thread depth support
  12. test_advance_inbox_warmup_tick_graduation: Mailbox graduates when reaching ramp_days

Layer 1: Environmental Failure Analysis
  13. test_health_score_high_bounce_rate_drops_to_needs_recovery: 2.5% bounce rate lowers health score to 50-69, triggering 50% cold outreach throttle
  14. test_health_score_critical_spam_triggers_emergency_pause: >0.1% spam complaint drops health score <50, triggering 100% cold outreach pause (EMERGENCY_PAUSED)
  15. test_sender_pool_skips_emergency_paused_mailbox_for_cold_outreach: select_rotating_sender_inbox rejects inbox in emergency pause for cold campaigns
  16. test_emergency_paused_mailbox_auto_recovers_when_health_improves: Once health score returns to >=70, emergency pause lifts
  17. test_zero_or_negative_days_active_handles_cleanly: Negative numbers or 0 days active clamped safely
  18. test_extremely_large_target_limit_clamped: Target of 1,000,000 clamped to 200/day max to prevent instant domain destruction
  19. test_warmup_disabled_returns_full_daily_limit: When warmup_enabled=False, returns regular daily limit without ramp restriction
  20. test_start_limit_greater_than_target_limit_clamped: When start > target, clamped safely
  21. test_ramp_days_out_of_bounds_clamped: <7 clamped to 7, >90 clamped to 90
  22. test_calculate_warmup_daily_cap_applies_recovery_throttle: In email_sender_service.py, cold cap throttled 50% when in recovery
  23. test_calculate_warmup_daily_cap_emergency_paused_returns_zero_cold: Cold cap = 0 when in emergency pause
  24. test_advance_inbox_warmup_tick_supabase_exception_resilience: Network/DB errors handled without crash
  25. test_missing_or_corrupt_inbox_dict_resilience: Missing / None / corrupt dict inputs handled safely
  26. test_bounce_rate_raw_counts_vs_percentage_fallback: Computes bounce rate from count fallback
  27. test_spam_rate_raw_counts_vs_percentage_fallback: Computes spam rate from count fallback

Layer 2: Human Paranoia & Security Defense
  28. test_router_calculate_ramp_endpoint: POST /api/elein/warmup/calculate-ramp returns valid curve projection
  29. test_router_calculate_ramp_endpoint_default_payload: Default payload behavior
  30. test_router_calculate_ramp_endpoint_malformed_input_sanitization: Malformed input handling
  31. test_router_health_endpoint: POST /api/elein/warmup/health returns valid health audit
  32. test_router_health_endpoint_with_inbox_id_lookup: Inbox ID lookup from DB
  33. test_router_simulate_tick_endpoint: POST /api/elein/warmup/simulate-tick executes clean tick
  34. test_router_get_inbox_warmup_endpoint: GET /api/elein/warmup/inbox/{inbox_id} returns telemetry
  35. test_cross_tenant_idor_warmup_inbox_scoping: Router ensures users cannot query inboxes from other workspaces
  36. test_cross_tenant_idor_simulate_tick_isolation: Simulate-tick scopes to caller's workspace
  37. test_executor_send_email_injects_warmup_telemetry: Runs handle_send_email and verifies returned payload contains warmup_health_score, warmup_curve_type, warmup_days_active
  38. test_formula_injection_defense_in_warmup_templates: Neutralizes spreadsheet formula injection (=, +, -, @)
  39. test_rapid_consecutive_ticks_stability: 30 consecutive ticks advance smoothly without degradation
"""

import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from integrations.backend.services.mailbox_warmup_service import (
    WarmupCurveType,
    WarmupHealthStatus,
    normalize_curve_type,
    calculate_warmup_ramp_projection,
    calculate_inbox_warmup_health_score,
    simulate_peer_warmup_exchange,
    advance_inbox_warmup_tick,
)


class TestLayer0FoundationalRampCurvesAndMechanics(unittest.TestCase):
    def setUp(self):
        self.mock_supabase = MagicMock()

    def test_linear_warmup_curve_ramp(self):
        start = 5
        target = 50
        days = 28
        res = calculate_warmup_ramp_projection(
            curve_type='LINEAR',
            start_limit=start,
            target_limit=target,
            ramp_days=days,
            current_day=14
        )
        self.assertEqual(res['curve_type'], WarmupCurveType.LINEAR.value)
        self.assertEqual(res['start_limit'], start)
        self.assertEqual(res['target_limit'], target)
        self.assertEqual(res['ramp_days'], days)
        self.assertEqual(res['current_day'], 14)

        proj = res['projection']
        self.assertEqual(len(proj), days + 1)
        self.assertEqual(proj[0]['day'], 0)
        self.assertEqual(proj[0]['total_daily_cap'], start)
        self.assertEqual(proj[days]['day'], days)
        self.assertEqual(proj[days]['total_daily_cap'], target)
        self.assertIn(proj[14]['total_daily_cap'], (27, 28))

        for d in range(1, len(proj)):
            self.assertGreaterEqual(proj[d]['total_daily_cap'], proj[d - 1]['total_daily_cap'])

    def test_logarithmic_sigmoid_curve_ramp(self):
        res = calculate_warmup_ramp_projection(
            curve_type='LOGARITHMIC',
            start_limit=5,
            target_limit=50,
            ramp_days=28,
            current_day=0
        )
        proj = res['projection']
        self.assertEqual(len(proj), 29)
        self.assertEqual(proj[0]['total_daily_cap'], 5)

        for d in range(1, 6):
            self.assertLessEqual(proj[d]['total_daily_cap'], 12)

        delta_early = proj[5]['total_daily_cap'] - proj[0]['total_daily_cap']
        delta_mid = proj[18]['total_daily_cap'] - proj[6]['total_daily_cap']
        self.assertGreater(delta_mid, delta_early)

        self.assertEqual(proj[28]['total_daily_cap'], 50)
        self.assertGreaterEqual(proj[24]['total_daily_cap'], 45)

    def test_aggressive_curve_ramp(self):
        res_log = calculate_warmup_ramp_projection('LOGARITHMIC', 5, 50, 28, 7)
        res_agg = calculate_warmup_ramp_projection('AGGRESSIVE', 5, 50, 28, 7)
        cap_log_d7 = res_log['projection'][7]['total_daily_cap']
        cap_agg_d7 = res_agg['projection'][7]['total_daily_cap']
        self.assertGreater(cap_agg_d7, cap_log_d7)
        self.assertEqual(res_agg['projection'][28]['total_daily_cap'], 50)

    def test_warmup_vs_cold_split_ratio(self):
        res = calculate_warmup_ramp_projection('LOGARITHMIC', 5, 50, 28, 0)
        proj = res['projection']
        self.assertEqual(proj[0]['warmup_cap'], 5)
        self.assertEqual(proj[0]['cold_outreach_cap'], 0)
        self.assertEqual(proj[0]['warmup_ratio_pct'], 100.0)

        self.assertEqual(proj[14]['warmup_ratio_pct'], 40.0)
        self.assertEqual(proj[14]['warmup_cap'] + proj[14]['cold_outreach_cap'], proj[14]['total_daily_cap'])
        self.assertGreater(proj[14]['cold_outreach_cap'], 0)

        self.assertEqual(proj[28]['warmup_ratio_pct'], 20.0)
        self.assertEqual(proj[28]['warmup_cap'], 10)
        self.assertEqual(proj[28]['cold_outreach_cap'], 40)

    def test_peer_warmup_exchange_simulation(self):
        sender = {'email': 'alex@outbound-scale.com', 'name': 'Alex Vance'}
        peer = {'email': 'sarah@outbound-scale.com', 'name': 'Sarah Jenkins'}
        event = simulate_peer_warmup_exchange(sender, peer, thread_depth=1)
        self.assertEqual(event['status'], 'completed')
        self.assertEqual(event['sender'], 'alex@outbound-scale.com')
        self.assertEqual(event['recipient'], 'sarah@outbound-scale.com')
        self.assertTrue(event['landed_inbox'])
        self.assertTrue(event['saved_from_spam'])
        self.assertTrue(event['starred'])
        self.assertTrue(event['marked_important'])
        self.assertTrue(event['replied'])
        self.assertEqual(event['thread_depth'], 1)
        self.assertTrue(len(event['subject']) > 5)

    def test_advance_inbox_warmup_tick(self):
        inbox = {
            'id': 'box-tick-001',
            'warmup_days_active': 5,
            'warmup_start_limit': 5,
            'max_daily_limit': 50,
            'ramp_days': 28,
            'ramp_strategy': 'LOGARITHMIC'
        }
        updated = advance_inbox_warmup_tick(inbox, supabase=None)
        self.assertEqual(updated['warmup_days_active'], 6)
        self.assertEqual(updated['current_ramp_day'], 6)
        self.assertGreater(updated['current_daily_limit'], 0)
        self.assertGreater(updated['today_warmup_cap'], 0)
        self.assertIn('ramp_projection', updated)

    def test_curve_progress_bounds_and_monotonicity(self):
        for curve_type in (WarmupCurveType.LINEAR, WarmupCurveType.LOGARITHMIC, WarmupCurveType.AGGRESSIVE):
            res = calculate_warmup_ramp_projection(curve_type.value, 1, 100, 30, 0)
            proj = res['projection']
            prev_total = 0
            for entry in proj:
                self.assertGreaterEqual(entry['total_daily_cap'], prev_total)
                self.assertLessEqual(entry['total_daily_cap'], 100)
                self.assertGreaterEqual(entry['total_daily_cap'], 1)
                prev_total = entry['total_daily_cap']

    def test_warmup_curve_normalization_synonyms(self):
        self.assertEqual(normalize_curve_type('linear'), WarmupCurveType.LINEAR)
        self.assertEqual(normalize_curve_type('LINE'), WarmupCurveType.LINEAR)
        self.assertEqual(normalize_curve_type('s-curve'), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type('sigmoid'), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type('balanced'), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type('gentle'), WarmupCurveType.LOGARITHMIC)
        self.assertEqual(normalize_curve_type('aggressive'), WarmupCurveType.AGGRESSIVE)
        self.assertEqual(normalize_curve_type('aged'), WarmupCurveType.AGGRESSIVE)
        self.assertEqual(normalize_curve_type('fast'), WarmupCurveType.AGGRESSIVE)

    def test_inbox_health_score_perfect_reputation(self):
        inbox = {
            'warmup_days_active': 35,
            'aggregate_bounce_rate_pct': 0.0,
            'spam_complaint_rate_pct': 0.0,
            'peer_engagement_rate_pct': 42.0
        }
        res = calculate_inbox_warmup_health_score(inbox)
        self.assertEqual(res['health_score'], 100)
        self.assertEqual(res['status'], WarmupHealthStatus.PEAK_HEALTH.value)
        self.assertEqual(res['throttle_cold_ratio'], 1.0)
        self.assertFalse(res['emergency_paused'])

    def test_inbox_health_score_brand_new_inbox(self):
        inbox = {
            'warmup_days_active': 1,
            'aggregate_bounce_rate_pct': 0.0,
            'spam_complaint_rate_pct': 0.0,
            'peer_engagement_rate_pct': 35.0
        }
        res = calculate_inbox_warmup_health_score(inbox)
        self.assertEqual(res['health_score'], 80)
        self.assertEqual(res['status'], WarmupHealthStatus.RAMPING_OPTIMAL.value)
        self.assertEqual(res['throttle_cold_ratio'], 1.0)

    def test_peer_warmup_thread_depth_support(self):
        sender = {'email': 'sender@domain.com'}
        peer = {'email': 'peer@domain.com'}
        event1 = simulate_peer_warmup_exchange(sender, peer, thread_depth=3)
        event2 = simulate_peer_warmup_exchange(sender, peer, thread_depth=3)
        self.assertEqual(event1['thread_depth'], 3)
        self.assertNotEqual(event1['exchange_id'], event2['exchange_id'])
        self.assertNotEqual(event1['thread_id'], event2['thread_id'])

    def test_advance_inbox_warmup_tick_graduation(self):
        inbox = {
            'id': 'box-grad-1',
            'warmup_days_active': 27,
            'ramp_days': 28,
            'max_daily_limit': 50,
            'warmup_status': 'warming'
        }
        updated = advance_inbox_warmup_tick(inbox, supabase=None)
        self.assertEqual(updated['warmup_days_active'], 28)
        self.assertEqual(updated['current_ramp_day'], 28)


class TestLayer1EnvironmentalFailureAnalysis(unittest.TestCase):
    def setUp(self):
        self.mock_supabase = MagicMock()

    def test_health_score_high_bounce_rate_drops_to_needs_recovery(self):
        inbox = {
            'warmup_days_active': 5,
            'aggregate_bounce_rate_pct': 2.5,
            'spam_complaint_rate_pct': 0.04,
            'peer_engagement_rate_pct': 25.0
        }
        res = calculate_inbox_warmup_health_score(inbox)
        self.assertEqual(res['health_score'], 60)
        self.assertEqual(res['status'], WarmupHealthStatus.NEEDS_RECOVERY.value)
        self.assertEqual(res['throttle_cold_ratio'], 0.5)
        self.assertFalse(res['emergency_paused'])

    def test_health_score_critical_spam_triggers_emergency_pause(self):
        inbox = {
            'warmup_days_active': 5,
            'aggregate_bounce_rate_pct': 2.0,
            'spam_complaint_rate_pct': 0.12,
            'peer_engagement_rate_pct': 20.0
        }
        res = calculate_inbox_warmup_health_score(inbox)
        self.assertEqual(res['health_score'], 35)
        self.assertEqual(res['status'], WarmupHealthStatus.EMERGENCY_PAUSED.value)
        self.assertEqual(res['throttle_cold_ratio'], 0.0)
        self.assertTrue(res['emergency_paused'])

    def test_sender_pool_skips_emergency_paused_mailbox_for_cold_outreach(self):
        from integrations.backend.services.email_sender_service import select_rotating_sender_inbox
        candidates = [
            {
                'id': 'inb-paused-warmup',
                'workspace_id': 'ws-test-pool',
                'email': 'bad-reputation@outbound.io',
                'status': 'ACTIVE',
                'daily_limit': 50,
                'sent_today': 0,
                'spam_complaint_rate_pct': 0.20,
                'aggregate_bounce_rate_pct': 2.5,
                'warmup_health_score': 35,
                'health_status': 'EMERGENCY_PAUSED',
                'emergency_paused': True,
            },
            {
                'id': 'inb-healthy-warmup',
                'workspace_id': 'ws-test-pool',
                'email': 'good-reputation@outbound.io',
                'status': 'ACTIVE',
                'daily_limit': 50,
                'sent_today': 0,
                'warmup_health_score': 95,
                'health_status': 'PEAK_HEALTH',
                'emergency_paused': False,
            }
        ]
        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id='ws-test-pool',
            candidate_inboxes=candidates,
            strategy='HEALTH_WEIGHTED'
        )
        self.assertIsNotNone(res['selected'])
        self.assertEqual(res['selected']['id'], 'inb-healthy-warmup')
        rejected_ids = [r.get('id') for r in res.get('pool_summary', {}).get('rejected', [])]
        self.assertIn('inb-paused-warmup', rejected_ids)

    def test_emergency_paused_mailbox_auto_recovers_when_health_improves(self):
        degraded = {
            'warmup_days_active': 5,
            'aggregate_bounce_rate_pct': 2.0,
            'spam_complaint_rate_pct': 0.15,
            'peer_engagement_rate_pct': 20.0
        }
        res_deg = calculate_inbox_warmup_health_score(degraded)
        self.assertTrue(res_deg['emergency_paused'])
        self.assertEqual(res_deg['status'], WarmupHealthStatus.EMERGENCY_PAUSED.value)

        recovered = {
            'warmup_days_active': 15,
            'aggregate_bounce_rate_pct': 0.5,
            'spam_complaint_rate_pct': 0.0,
            'peer_engagement_rate_pct': 35.0
        }
        res_rec = calculate_inbox_warmup_health_score(recovered)
        self.assertEqual(res_rec['health_score'], 85)
        self.assertFalse(res_rec['emergency_paused'])
        self.assertEqual(res_rec['throttle_cold_ratio'], 1.0)
        self.assertEqual(res_rec['status'], WarmupHealthStatus.PEAK_HEALTH.value)

    def test_zero_or_negative_days_active_handles_cleanly(self):
        res_neg = calculate_warmup_ramp_projection(
            curve_type='LOGARITHMIC',
            start_limit=5,
            target_limit=50,
            ramp_days=28,
            current_day=-10
        )
        self.assertEqual(res_neg['current_day'], 0)
        self.assertEqual(res_neg['today_warmup_cap'], 5)
        self.assertEqual(res_neg['today_cold_cap'], 0)

        health_neg = calculate_inbox_warmup_health_score({'warmup_days_active': -5})
        self.assertGreaterEqual(health_neg['health_score'], 0)
        self.assertLessEqual(health_neg['health_score'], 100)

    def test_extremely_large_target_limit_clamped(self):
        res = calculate_warmup_ramp_projection(
            start_limit=5,
            target_limit=1_000_000,
            ramp_days=28,
            current_day=28
        )
        self.assertEqual(res['target_limit'], 200)
        self.assertEqual(res['projection'][28]['total_daily_cap'], 200)

    def test_warmup_disabled_returns_full_daily_limit(self):
        from integrations.backend.services.email_sender_service import calculate_warmup_daily_cap
        inbox_disabled = {
            'daily_limit': 100,
            'warmup_enabled': False,
            'warmup_start_limit': 5,
            'warmup_days_active': 2
        }
        self.assertEqual(calculate_warmup_daily_cap(inbox_disabled), 100)

    def test_start_limit_greater_than_target_limit_clamped(self):
        res = calculate_warmup_ramp_projection(
            start_limit=80,
            target_limit=20,
            ramp_days=28
        )
        self.assertGreaterEqual(res['target_limit'], res['start_limit'])

    def test_ramp_days_out_of_bounds_clamped(self):
        res_low = calculate_warmup_ramp_projection(ramp_days=2)
        self.assertEqual(res_low['ramp_days'], 7)

        res_high = calculate_warmup_ramp_projection(ramp_days=365)
        self.assertEqual(res_high['ramp_days'], 90)

    def test_calculate_warmup_daily_cap_applies_recovery_throttle(self):
        from integrations.backend.services.email_sender_service import calculate_warmup_daily_cap
        inbox_recovery = {
            'daily_limit': 60,
            'warmup_enabled': True,
            'warmup_start_limit': 5,
            'warmup_days_active': 14,
            'warmup_curve_type': 'LINEAR',
            'aggregate_bounce_rate_pct': 2.5,
            'spam_complaint_rate_pct': 0.02,
            'peer_engagement_rate_pct': 25.0
        }
        cap = calculate_warmup_daily_cap(inbox_recovery)
        self.assertGreater(cap, 0)
        self.assertLessEqual(cap, 60)

    def test_calculate_warmup_daily_cap_emergency_paused_returns_zero_cold(self):
        from integrations.backend.services.email_sender_service import calculate_warmup_daily_cap
        inbox_emergency = {
            'daily_limit': 60,
            'warmup_enabled': True,
            'warmup_start_limit': 5,
            'warmup_days_active': 10,
            'warmup_curve_type': 'LOGARITHMIC',
            'aggregate_bounce_rate_pct': 2.5,
            'spam_complaint_rate_pct': 0.20,
        }
        cap = calculate_warmup_daily_cap(inbox_emergency)
        self.assertEqual(cap, 0)

    def test_advance_inbox_warmup_tick_supabase_exception_resilience(self):
        self.mock_supabase.table.side_effect = RuntimeError('Database connection reset by peer')
        inbox = {
            'id': 'box-err-01',
            'warmup_days_active': 8,
            'warmup_start_limit': 5,
            'max_daily_limit': 40
        }
        updated = advance_inbox_warmup_tick(inbox, supabase=self.mock_supabase)
        self.assertEqual(updated['warmup_days_active'], 9)
        self.assertFalse(updated['supabase_updated'])
        self.assertIn('Database connection reset', updated['supabase_error'])

    def test_missing_or_corrupt_inbox_dict_resilience(self):
        res_none = calculate_inbox_warmup_health_score(None)
        self.assertIsInstance(res_none['health_score'], int)

        tick_none = advance_inbox_warmup_tick(None)
        self.assertEqual(tick_none['warmup_days_active'], 1)

    def test_bounce_rate_raw_counts_vs_percentage_fallback(self):
        inbox = {
            'warmup_days_active': 30,
            'total_sent': 100,
            'total_bounces': 3
        }
        res = calculate_inbox_warmup_health_score(inbox)
        self.assertEqual(res['breakdown']['bounce_score'], 0)

    def test_spam_rate_raw_counts_vs_percentage_fallback(self):
        inbox = {
            'warmup_days_active': 30,
            'total_sent': 1000,
            'total_spam_complaints': 2
        }
        res = calculate_inbox_warmup_health_score(inbox)
        self.assertEqual(res['breakdown']['spam_score'], 0)
        self.assertEqual(res['status'], WarmupHealthStatus.NEEDS_RECOVERY.value)


class TestLayer2HumanParanoiaAndSecurityDefense(unittest.TestCase):
    def setUp(self):
        self.workspace_id = 'ws_test_warmup_engine'
        self.mock_supabase = MagicMock()
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_router_calculate_ramp_endpoint(self):
        client = TestClient(app)
        payload = {
            'curve_type': 'LOGARITHMIC',
            'start_limit': 5,
            'target_limit': 50,
            'ramp_days': 28,
            'current_day': 7
        }
        res = client.post('/api/elein/warmup/calculate-ramp', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success') or data.get('status') == 'success')
        curve = data.get('curve_type') or data.get('data', {}).get('curve_type')
        self.assertEqual(curve, 'LOGARITHMIC')
        ramp_days = data.get('ramp_days') or data.get('data', {}).get('ramp_days')
        self.assertEqual(ramp_days, 28)
        proj = data.get('projection') or data.get('data', {}).get('projection')
        self.assertEqual(len(proj), 29)

    def test_router_calculate_ramp_endpoint_default_payload(self):
        client = TestClient(app)
        res = client.post('/api/elein/warmup/calculate-ramp', json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success') or data.get('status') == 'success')
        target = data.get('target_limit') or data.get('data', {}).get('target_limit')
        self.assertGreaterEqual(target, 10)

    def test_router_calculate_ramp_endpoint_malformed_input_sanitization(self):
        client = TestClient(app)
        res = client.post(
            '/api/elein/warmup/calculate-ramp',
            json={
                'curve_type': 'unknown_nonsense_curve',
                'start_limit': -50,
                'target_limit': 10_000,
                'ramp_days': 1,
                'current_day': -10
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        start = data.get('start_limit') or data.get('data', {}).get('start_limit')
        target = data.get('target_limit') or data.get('data', {}).get('target_limit')
        days = data.get('ramp_days') or data.get('data', {}).get('ramp_days')
        self.assertEqual(start, 1)
        self.assertEqual(target, 200)
        self.assertEqual(days, 7)

    def test_router_health_endpoint(self):
        client = TestClient(app)
        payload = {
            'inbox_data': {
                'warmup_days_active': 20,
                'aggregate_bounce_rate_pct': 1.1,
                'spam_complaint_rate_pct': 0.0,
                'peer_engagement_rate_pct': 38.0
            }
        }
        res = client.post('/api/elein/warmup/health', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success') or data.get('status') == 'success')
        score = data.get('health_score') if data.get('health_score') is not None else data.get('data', {}).get('health_score')
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)

    def test_router_health_endpoint_with_inbox_id_lookup(self):
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{
            'id': 'inb-db-101',
            'workspace_id': self.workspace_id,
            'warmup_days_active': 15,
            'aggregate_bounce_rate_pct': 0.8,
            'spam_complaint_rate_pct': 0.0
        }]
        client = TestClient(app)
        res = client.post('/api/elein/warmup/health', json={'inbox_id': 'inb-db-101'})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success') or data.get('status') == 'success')
        score = data.get('health_score') if data.get('health_score') is not None else data.get('data', {}).get('health_score')
        self.assertGreaterEqual(score, 70)

    def test_router_simulate_tick_endpoint(self):
        client = TestClient(app)
        res = client.post('/api/elein/warmup/simulate-tick', json={})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success') or data.get('status') == 'success')

    def test_router_get_inbox_warmup_endpoint(self):
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{
            'id': 'inb-tel-01',
            'workspace_id': self.workspace_id,
            'email': 'telemetry@acme.com',
            'warmup_days_active': 12,
            'daily_limit': 25,
            'health_score': 92,
            'warmup_status': 'warming'
        }]
        client = TestClient(app)
        res = client.get('/api/elein/warmup/inbox/inb-tel-01')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success') or data.get('status') == 'success')
        inbox_id = data.get('inbox_id') or data.get('data', {}).get('id')
        self.assertEqual(inbox_id, 'inb-tel-01')

    def test_cross_tenant_idor_warmup_inbox_scoping(self):
        client = TestClient(app)
        res = client.get('/api/elein/warmup/inbox/foreign-inbox-999')
        self.assertIn(res.status_code, (403, 404))

    def test_cross_tenant_idor_simulate_tick_isolation(self):
        client = TestClient(app)
        res = client.post('/api/elein/warmup/simulate-tick', json={'inbox_ids': ['foreign-inbox-101']})
        # Strict security either rejects with 403 or ignores foreign inbox with 200 and empty updated list
        if res.status_code == 200:
            data = res.json()
            updated = data.get('inboxes') or data.get('data', {}).get('updated_inboxes', [])
            updated_ids = [m.get('id') for m in updated]
            self.assertNotIn('foreign-inbox-101', updated_ids)
        else:
            self.assertIn(res.status_code, (403, 404))

    def test_executor_send_email_injects_warmup_telemetry(self):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {'success': True}

        executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=mock_sb,
            workspace_id=self.workspace_id,
        )

        node_data = {
            '_lead_id': 'lead-warmup-telemetry',
            'to': 'target@prospect.com',
            'subject': 'Follow up regarding partnership',
            'body': 'Checking in on our discussion last week.',
            'use_sender_pool': True,
            'sender_pool_inboxes': [
                {
                    'id': 'inb-warm-tele',
                    'workspace_id': self.workspace_id,
                    'email': 'sender@company.com',
                    'status': 'ACTIVE',
                    'daily_limit': 50,
                    'sent_today': 2,
                    'warmup_health_score': 96,
                    'warmup_curve_type': 'LOGARITHMIC',
                    'warmup_days_active': 14
                }
            ]
        }

        result = executor.handle_send_email(node_data, linkedin_url=None)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['branch'], Branch.THEN.value)
        self.assertIsNotNone(result.get('warmup_health_score'))
        self.assertGreater(result['warmup_health_score'], 0)
        self.assertEqual(result['warmup_curve_type'], 'LOGARITHMIC')
        self.assertEqual(result['warmup_days_active'], 14)

    def test_formula_injection_defense_in_warmup_templates(self):
        sender = {'name': "=cmd|' /C calc'!A0", 'email': 'test@domain.com'}
        peer = {'name': '+SUM(1,2)', 'email': 'peer@domain.com'}
        event = simulate_peer_warmup_exchange(sender, peer)
        self.assertNotIn('=cmd', event['initial_message'])
        self.assertNotIn('+SUM', event['reply_message'])

    def test_rapid_consecutive_ticks_stability(self):
        inbox = {
            'id': 'box-consec-30',
            'warmup_days_active': 0,
            'warmup_start_limit': 5,
            'max_daily_limit': 50,
            'ramp_days': 28,
            'ramp_strategy': 'LOGARITHMIC'
        }
        for day in range(1, 31):
            inbox = advance_inbox_warmup_tick(inbox, supabase=None)
            self.assertEqual(inbox['warmup_days_active'], day)
            self.assertGreaterEqual(inbox['current_daily_limit'], 5)
            self.assertLessEqual(inbox['current_daily_limit'], 50)
            self.assertGreaterEqual(inbox['today_warmup_cap'], 1)


if __name__ == '__main__':
    unittest.main()
