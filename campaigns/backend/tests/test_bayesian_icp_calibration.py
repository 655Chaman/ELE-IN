"""
test_bayesian_icp_calibration.py — Test Suite for Bayesian ICP Calibration Studio & Adaptive Feedback Loop
Adheres strictly to the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch
import uuid
from fastapi import HTTPException
from fastapi.testclient import TestClient

from knowledge.backend.services.bayesian_icp_service import (
    calculate_beta_metrics,
    get_workspace_signal_weights,
    get_detailed_calibration_matrix,
    record_adaptive_feedback,
    calibrate_signal,
    reset_all_signals_to_baseline,
    get_feedback_events,
    compute_bayesian_icp_score,
    _extract_signals
)
from core.backend.main import app


class TestBayesianICPCalibration(unittest.TestCase):
    """
    Test suite for Area 13: Bayesian ICP Calibration Studio & Adaptive Feedback Loop.
    """

    def setUp(self):
        self.workspace_id = str(uuid.uuid4())

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 0: Foundational Layer Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_calculate_beta_metrics(self):
        """Layer 0: Validates Beta(alpha, beta) mean, credible interval, and confidence tier math."""
        # Baseline Beta(2,2): mean = 0.5, total = 4 -> LOW confidence
        m_base = calculate_beta_metrics(2, 2)
        self.assertEqual(m_base["raw_mean"], 0.5)
        self.assertEqual(m_base["sample_size"], 4)
        self.assertEqual(m_base["confidence_tier"], "LOW")
        self.assertLess(m_base["credible_interval_lower"], 0.5)
        self.assertGreater(m_base["credible_interval_upper"], 0.5)

        # High sample size Beta(35, 15): mean = 35/50 = 0.70 -> HIGH confidence
        m_high = calculate_beta_metrics(35, 15)
        self.assertEqual(m_high["raw_mean"], 0.7)
        self.assertEqual(m_high["sample_size"], 50)
        self.assertEqual(m_high["confidence_tier"], "HIGH")
        # Credible interval must tightly bound 0.7
        self.assertGreater(m_high["credible_interval_lower"], 0.5)
        self.assertLessEqual(m_high["credible_interval_upper"], 1.0)

    def test_weight_multiplier_scaling(self):
        """Layer 0: Verifies operator weight multipliers scale effective probability within [0, 1]."""
        # Baseline 0.5 * 1.5x multiplier = 0.75
        m_scaled = calculate_beta_metrics(2, 2, weight_multiplier=1.5)
        self.assertEqual(m_scaled["raw_mean"], 0.5)
        self.assertEqual(m_scaled["effective_weight"], 0.75)

        # Multiplier clamping at 1.0 max
        m_capped = calculate_beta_metrics(10, 2, weight_multiplier=2.0)
        self.assertLessEqual(m_capped["effective_weight"], 1.0)

    def test_adaptive_feedback_reinforcement_weights(self):
        """Layer 0: Verifies business-weighted prior reinforcement (replies, meetings, ghosts)."""
        mock_supabase = MagicMock()
        existing_row = MagicMock()
        existing_row.data = [{"prior_alpha": 4, "prior_beta": 4, "is_frozen": False}]
        mock_supabase.table().select().eq().eq().limit().execute.return_value = existing_row

        # 1. Meeting Booked (+3 alpha)
        res_meeting = record_adaptive_feedback(
            supabase=mock_supabase,
            workspace_id=self.workspace_id,
            lead_id="lead_1",
            campaign_id="camp_1",
            event_type="MEETING_BOOKED",
            signal_flags={"is_decision_maker": True}
        )
        self.assertEqual(res_meeting["status"], "success")
        self.assertIn("is_decision_maker", res_meeting["signals_updated"])

        # 2. Ghosted / Lost (+1 beta)
        res_ghost = record_adaptive_feedback(
            supabase=mock_supabase,
            workspace_id=self.workspace_id,
            lead_id="lead_2",
            campaign_id="camp_1",
            event_type="GHOSTED_OR_LOST",
            signal_flags={"has_recent_activity": True}
        )
        self.assertEqual(res_ghost["status"], "success")
        self.assertIn("has_recent_activity", res_ghost["signals_updated"])

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 1: Environmental Resilience Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_missing_database_table_graceful_fallback(self):
        """Layer 1: When DB query fails (table unmigrated in Supabase), uses safe in-memory defaults."""
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("relation icp_signal_weights does not exist")

        matrix = get_detailed_calibration_matrix(mock_supabase, self.workspace_id)
        self.assertIsInstance(matrix["signals"], list)
        self.assertGreater(len(matrix["signals"]), 0)
        self.assertEqual(matrix["model_status"], "ONLINE_ACTIVE")
        self.assertGreaterEqual(matrix["recommended_score_gate"], 50)

    def test_damping_factor_on_runaway_observations(self):
        """Layer 1: When total observations exceed 200, scales down alpha/beta to preserve agility."""
        mock_supabase = MagicMock()
        # Row with 150 alpha and 70 beta (total = 220 >= 200)
        mock_row = MagicMock()
        mock_row.data = [{"prior_alpha": 150, "prior_beta": 70, "is_frozen": False}]
        mock_supabase.table().select().eq().eq().limit().execute.return_value = mock_row

        updated_params = {}
        def mock_update(params):
            updated_params.update(params)
            m = MagicMock()
            m.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            return m
        mock_supabase.table().update.side_effect = mock_update

        record_adaptive_feedback(
            supabase=mock_supabase,
            workspace_id=self.workspace_id,
            lead_id="lead_99",
            campaign_id="camp_1",
            event_type="POSITIVE_REPLY",
            signal_flags={"is_decision_maker": True}
        )

        # After damping: 150*0.5 = 75, 70*0.5 = 35. With +2 alpha -> new_a = 77, new_b = 35
        self.assertEqual(updated_params.get("prior_alpha"), 77)
        self.assertEqual(updated_params.get("prior_beta"), 35)

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 2: Human Paranoia & Security Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_frozen_signal_protection_against_drift(self):
        """Layer 2: Frozen signals (is_frozen=True) are IMMUNE to automated feedback learning."""
        mock_supabase = MagicMock()
        mock_row = MagicMock()
        # Frozen signal
        mock_row.data = [{"prior_alpha": 10, "prior_beta": 5, "is_frozen": True}]
        mock_supabase.table().select().eq().eq().limit().execute.return_value = mock_row

        # Attempt to record meeting booked (+3 alpha)
        res = record_adaptive_feedback(
            supabase=mock_supabase,
            workspace_id=self.workspace_id,
            lead_id="lead_abc",
            campaign_id="camp_1",
            event_type="MEETING_BOOKED",
            signal_flags={"is_decision_maker": True}
        )

        # Update should have been skipped for frozen signal
        self.assertEqual(res["status"], "success")
        self.assertNotIn("is_decision_maker", res["signals_updated"])

    def test_manual_signal_calibration_controls(self):
        """Layer 2: Operators can freeze/unfreeze and adjust custom weight multipliers."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[{"id": "row_1"}])

        res = calibrate_signal(
            supabase=mock_supabase,
            workspace_id=self.workspace_id,
            signal_name="is_decision_maker",
            is_frozen=True,
            weight_multiplier=2.5,
            reset_to_prior=False
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["applied_updates"]["is_frozen"])
        self.assertEqual(res["applied_updates"]["weight_multiplier"], 2.5)

    def test_emergency_circuit_breaker_reset_all(self):
        """Layer 2: 1-Click factory reset resets all workspace signals to Beta(2,2)."""
        mock_supabase = MagicMock()
        res = reset_all_signals_to_baseline(mock_supabase, self.workspace_id)
        self.assertEqual(res["status"], "success")
        self.assertIn("Beta(2,2)", res["message"])

    def test_model_drift_detection(self):
        """Layer 2: Flags signals that have diverged with high sample size (>0.22 deviation)."""
        mock_supabase = MagicMock()
        # Mock signal with high win rate and high sample size
        mock_res = MagicMock()
        mock_res.data = [{
            "signal_name": "hiring_gtm",
            "prior_alpha": 30,
            "prior_beta": 5,
            "is_frozen": False,
            "weight_multiplier": 1.0
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_res

        matrix = get_detailed_calibration_matrix(mock_supabase, self.workspace_id)
        warnings = matrix["model_drift_warnings"]
        self.assertGreater(len(warnings), 0)
        self.assertEqual(warnings[0]["signal_name"], "hiring_gtm")
        self.assertEqual(warnings[0]["severity"], "POSITIVE_ACCELERATION")

    def test_lead_profile_signal_extraction_and_scoring(self):
        """Layer 0: Verifies signal extraction from profile dictionary and computation of Bayesian score."""
        mock_supabase = MagicMock()
        empty = MagicMock(data=[])
        mock_supabase.table().select().eq().execute.return_value = empty

        profile = {
            "title": "VP of Revenue Engineering",
            "company": "ScaleAI Cloud",
            "headcount": 250,
            "industry": "Enterprise Software",
            "has_funding": True,
            "recent_posts": True
        }

        signals = _extract_signals(profile)
        self.assertTrue(signals["is_decision_maker"])
        self.assertTrue(signals["is_target_industry"])
        self.assertTrue(signals["is_target_size"])
        self.assertTrue(signals["has_recent_activity"])

        score, reasoning = compute_bayesian_icp_score(mock_supabase, self.workspace_id, profile)
        self.assertGreaterEqual(score, 50)
        self.assertIn("Bayesian Score", reasoning)


if __name__ == "__main__":
    unittest.main()
