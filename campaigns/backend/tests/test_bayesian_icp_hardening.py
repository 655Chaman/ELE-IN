import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from knowledge.backend.services.bayesian_icp_service import (
    record_outcome,
    get_workspace_signal_weights,
    compute_bayesian_icp_score
)
from core.backend.services.credit_service import check_tier_access
from knowledge.backend.routers.bayesian_icp import api_record_outcome, api_score_profile, RecordOutcomeRequest, ScoreRequest


class TestBayesianICPHardening(unittest.TestCase):
    """
    Test suite for Step 14: Bayesian ICP Signal Weight Boundary, Damping & Concurrent Lock Guard.
    Adheres strictly to the Three-Layer Logic Architecture (Paranoia Framework):
    - Layer 0: Core Bayesian prior updates.
    - Layer 1: Environmental resilience (RPC failure fallback, DB damping, tier normalization).
    - Layer 2: Human paranoia (dirty signal strings, case-insensitive tier strings, runaway data).
    """

    def test_signal_name_sanitization(self):
        """
        Layer 2: Verifies that illegal characters, whitespace, emojis, and control characters
        are stripped from signal names, and length is capped at 64 characters.
        """
        mock_supabase = MagicMock()
        recorded_signals = []

        def mock_rpc(fn, params):
            recorded_signals.append(params.get("p_signal_name"))
            m = MagicMock()
            m.execute.return_value = MagicMock()
            return m

        mock_supabase.rpc.side_effect = mock_rpc

        dirty_flags = {
            "  Dirty Signal! @#$%^&*() \n\t ": True,
            "UPPERCASE_AND-hyphens_123": True,
            "a" * 100: True,  # should be truncated to 64
            "!@#$%^&*()": True,  # becomes empty string, should be skipped
            "": True,  # empty string should be skipped
        }

        record_outcome(mock_supabase, "ws_123", "lead_001", "won", dirty_flags)

        self.assertIn("dirtysignal", recorded_signals)
        self.assertIn("uppercase_and-hyphens_123", recorded_signals)
        self.assertIn("a" * 64, recorded_signals)
        self.assertNotIn("", recorded_signals)
        self.assertEqual(len(recorded_signals), 3)

    def test_record_outcome_rpc_failure_triggers_db_fallback(self):
        """
        Layer 1: When supabase.rpc fails, direct DB table query and update/insert
        succeeds so learning writes are never silently lost.
        """
        mock_supabase = MagicMock()
        # RPC fails
        mock_supabase.rpc.side_effect = Exception("PGRST202: Function record_bayesian_icp_outcome not found")

        # Scenario A: Signal does not exist in table -> inserts initial row
        select_mock = MagicMock()
        select_mock.execute.return_value.data = []
        
        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.eq.return_value.limit.return_value = select_mock
        mock_supabase.table.return_value = table_mock

        record_outcome(mock_supabase, "ws_123", "lead_001", "won", {"new_signal": True})
        
        # Verify insert was called with init_alpha=3 (2+1 for won), init_beta=2
        table_mock.insert.assert_called_once_with({
            "workspace_id": "ws_123",
            "signal_name": "new_signal",
            "prior_alpha": 3,
            "prior_beta": 2
        })

        # Scenario B: Signal exists in table -> updates row
        mock_supabase.reset_mock()
        mock_supabase.rpc.side_effect = Exception("RPC timeout")
        select_mock_b = MagicMock()
        select_mock_b.execute.return_value.data = [{"prior_alpha": 10, "prior_beta": 5}]
        
        table_mock_b = MagicMock()
        table_mock_b.select.return_value.eq.return_value.eq.return_value.limit.return_value = select_mock_b
        mock_supabase.table.return_value = table_mock_b

        record_outcome(mock_supabase, "ws_123", "lead_002", "lost", {"existing_signal": True})

        # Verify update was called: alpha remains 10, beta becomes 5 + 1 = 6
        table_mock_b.update.assert_called_once_with({
            "prior_alpha": 10,
            "prior_beta": 6
        })

    def test_damping_prevents_runaway_inertia(self):
        """
        Layer 1 & 2: When prior_alpha + prior_beta >= 200, values are halved before
        incrementing, preventing learning lock-in and restoring model adaptability.
        """
        mock_supabase = MagicMock()
        mock_supabase.rpc.side_effect = Exception("RPC unavailable, triggering fallback")

        # Prior alpha = 160, beta = 60 (total = 220 >= 200)
        select_mock = MagicMock()
        select_mock.execute.return_value.data = [{"prior_alpha": 160, "prior_beta": 60}]
        table_mock = MagicMock()
        table_mock.select.return_value.eq.return_value.eq.return_value.limit.return_value = select_mock
        mock_supabase.table.return_value = table_mock

        # Won: alpha damped to max(2, int(160 * 0.5)) = 80, then + 1 = 81
        #      beta damped to max(2, int(60 * 0.5)) = 30, then + 0 = 30
        record_outcome(mock_supabase, "ws_123", "lead_001", "won", {"saturated_signal": True})

        table_mock.update.assert_called_once_with({
            "prior_alpha": 81,
            "prior_beta": 30
        })

        # Lost test at boundary: alpha = 150, beta = 50 (total = 200 >= 200)
        mock_supabase.reset_mock()
        mock_supabase.rpc.side_effect = Exception("RPC unavailable")
        select_mock_boundary = MagicMock()
        select_mock_boundary.execute.return_value.data = [{"prior_alpha": 150, "prior_beta": 50}]
        table_mock_boundary = MagicMock()
        table_mock_boundary.select.return_value.eq.return_value.eq.return_value.limit.return_value = select_mock_boundary
        mock_supabase.table.return_value = table_mock_boundary

        # Lost: alpha damped to 75, beta damped to 25 + 1 = 26
        record_outcome(mock_supabase, "ws_123", "lead_002", "lost", {"saturated_signal": True})

        table_mock_boundary.update.assert_called_once_with({
            "prior_alpha": 75,
            "prior_beta": 26
        })

    @patch("core.backend.services.credit_service.get_service_client")
    def test_check_tier_access_bayesian_icp(self, mock_get_client):
        """
        Layer 0 & 1: Verifies feature gate for 'bayesian_icp'.
        PRO and ENTERPRISE allow access; FREE denies.
        """
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        # FREE tier denies
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "FREE"}]
        self.assertFalse(check_tier_access("ws_free", "bayesian_icp"))

        # PRO tier allows
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "PRO"}]
        self.assertTrue(check_tier_access("ws_pro", "bayesian_icp"))

        # ENTERPRISE tier allows
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "ENTERPRISE"}]
        self.assertTrue(check_tier_access("ws_ent", "bayesian_icp"))

        # Empty data / missing workspace defaults to FREE
        mock_supabase.table().select().eq().execute.return_value.data = []
        self.assertFalse(check_tier_access("ws_missing", "bayesian_icp"))

    @patch("core.backend.services.credit_service.get_service_client")
    def test_case_insensitive_tier_check(self, mock_get_client):
        """
        Layer 2: Human paranoia — tier names with lowercase or whitespace (e.g. 'pro', '  growth ')
        must be normalized and granted access without 403 lockouts.
        """
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        # Lowercase 'pro'
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "pro"}]
        self.assertTrue(check_tier_access("ws_pro_lower", "bayesian_icp"))

        # Uppercase 'GROWTH' (treated as 'PRO')
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "GROWTH"}]
        self.assertTrue(check_tier_access("ws_growth", "bayesian_icp"))

        # Lowercase 'growth' with whitespace
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "  growth  "}]
        self.assertTrue(check_tier_access("ws_growth_ws", "bayesian_icp"))

        # Mixed-case 'Enterprise'
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "Enterprise"}]
        self.assertTrue(check_tier_access("ws_ent_mixed", "bayesian_icp"))

        # Lowercase 'free'
        mock_supabase.table().select().eq().execute.return_value.data = [{"tier": "free"}]
        self.assertFalse(check_tier_access("ws_free_lower", "bayesian_icp"))

    @patch("knowledge.backend.routers.bayesian_icp.check_tier_access")
    def test_router_endpoints_tier_gate(self, mock_tier_access):
        """
        Layer 1 & 2: Tests FastAPI router endpoints enforce check_tier_access.
        """
        mock_supabase = MagicMock()

        # FREE / Unauthorized workspace -> 403 Forbidden
        mock_tier_access.return_value = False

        record_req = RecordOutcomeRequest(
            lead_id="lead_123",
            outcome="won",
            signal_flags={"decision_maker_title": True}
        )
        with self.assertRaises(HTTPException) as ctx:
            api_record_outcome(record_req, mock_supabase, "ws_free")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Growth Pro feature", ctx.exception.detail)

        score_req = ScoreRequest(profile_data={"title": "VP of Sales"})
        with self.assertRaises(HTTPException) as ctx2:
            api_score_profile(score_req, mock_supabase, "ws_free")
        self.assertEqual(ctx2.exception.status_code, 403)
        self.assertIn("Growth Pro feature", ctx2.exception.detail)

        # PRO / Authorized workspace -> 200 Success
        mock_tier_access.return_value = True
        res = api_record_outcome(record_req, mock_supabase, "ws_pro")
        self.assertEqual(res["status"], "success")

        mock_supabase.table().select().eq().execute.return_value.data = []
        score_res = api_score_profile(score_req, mock_supabase, "ws_pro")
        self.assertEqual(score_res["status"], "success")


if __name__ == "__main__":
    unittest.main()
