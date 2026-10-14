"""
Step 11B — Credit Pre-Authorization Guard
Three-Layer Paranoia Framework Tests
"""
import unittest
from unittest.mock import MagicMock, patch
import time


class TestCreditPreflight(unittest.TestCase):

    def _make_orchestrator(self):
        from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
        orch = EleInOrchestrator.__new__(EleInOrchestrator)
        orch.supabase = MagicMock()
        orch._credit_cache = {}
        orch._credit_cache_ttl = 60
        return orch

    def test_positive_credits_returns_true(self):
        """Layer 0: Workspace with positive credits passes preflight."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"credits": 500, "plan_tier": "starter"}]
        )
        result = orch._workspace_has_credits("ws-1")
        self.assertTrue(result)

    def test_zero_credits_returns_false(self):
        """Layer 0: Workspace with zero credits fails preflight."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"credits": 0, "plan_tier": "starter"}]
        )
        result = orch._workspace_has_credits("ws-2")
        self.assertFalse(result)

    def test_enterprise_plan_bypasses_credit_gate(self):
        """Layer 1: Enterprise plan always passes regardless of credits value."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"credits": 0, "plan_tier": "enterprise"}]
        )
        result = orch._workspace_has_credits("ws-enterprise")
        self.assertTrue(result)

    def test_cache_prevents_redundant_db_queries(self):
        """Layer 1: Second call within TTL uses cache, not DB."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"credits": 100, "plan_tier": "growth"}]
        )
        orch._workspace_has_credits("ws-cache")
        orch._workspace_has_credits("ws-cache")  # Second call
        call_count = orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.call_count
        self.assertEqual(call_count, 1, f"Expected 1 DB query, got {call_count}")

    def test_db_error_fails_open(self):
        """Layer 1: DB error during credit check fails open (does not block campaigns)."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("DB timeout")
        result = orch._workspace_has_credits("ws-dberror")
        self.assertTrue(result, "DB error should fail open to avoid blocking campaigns")

    def test_unknown_workspace_fails_open(self):
        """Layer 1: Unknown workspace (empty data) fails open."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        result = orch._workspace_has_credits("ws-unknown")
        self.assertTrue(result)

    def test_production_schema_positive_credits_passes(self):
        """Layer 0: Verified production schema with data_cleaning_credits passes."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 1000, "tier": "PRO", "status": "active"}]
        )
        self.assertTrue(orch._workspace_has_credits("ws-prod-1"))

    def test_production_schema_free_tier_zero_credits_fails(self):
        """Layer 0: Verified production schema with 0 data_cleaning_credits on FREE tier fails."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 0, "tier": "FREE", "status": "active"}]
        )
        self.assertFalse(orch._workspace_has_credits("ws-prod-2"))

    def test_overdraft_buffer_allowed_within_500(self):
        """Layer 1: PRO tier within -500 overdraft buffer is permitted for active campaigns."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -350, "tier": "PRO", "status": "active"}]
        )
        self.assertTrue(orch._workspace_has_credits("ws-overdraft-ok"))

    def test_overdraft_buffer_blocked_exceeding_500(self):
        """Layer 1: PRO tier exceeding -500 overdraft buffer is halted."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -501, "tier": "PRO", "status": "active"}]
        )
        self.assertFalse(orch._workspace_has_credits("ws-overdraft-breached"))

    def test_suspended_workspace_fails_preflight(self):
        """Layer 2: Suspended workspace fails preflight even if credits are positive."""
        orch = self._make_orchestrator()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 5000, "tier": "PRO", "status": "suspended"}]
        )
        self.assertFalse(orch._workspace_has_credits("ws-suspended"))

    @patch("campaigns.backend.services.elein_orchestrator.is_working_hours", return_value=True)
    def test_process_pending_leads_pauses_state_when_zero_credits(self, mock_working_hours):
        """Layer 2: Leads from a zero-credit workspace are paused instead of processed."""
        orch = self._make_orchestrator()
        orch.requeue_waiting_for_reply_leads = MagicMock()
        orch._workspace_has_credits = MagicMock(return_value=False)

        mock_ces = MagicMock()
        mock_ces.update.return_value.eq.return_value.lt.return_value.execute.return_value = MagicMock(data=[])
        mock_ces.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "state-1", "status": "paused"}])
        mock_ces.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        def table_router(table_name):
            if table_name == "campaign_execution_states":
                return mock_ces
            m = MagicMock()
            if table_name == "campaigns":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "camp-1", "workspace_id": "ws-zero", "metadata": {"scheduling_mode": "lead_local_time"}}]
                )
            elif table_name == "workspaces":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "ws-zero", "status": "active"}]
                )
            elif table_name == "campaign_enrollments":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-1", "campaign_id": "camp-1", "workspace_id": "ws-zero", "lead_id": "lead-1", "campaign_version_id": "ver-1"}]
                )
            elif table_name == "leads":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "lead-1", "timezone": "UTC"}]
                )
            elif table_name in ("campaign_nodes", "campaign_edges", "ai_reply_approvals"):
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                m.select.return_value.eq.return_value.lt.return_value.execute.return_value = MagicMock(data=[])
            return m

        orch.supabase.table.side_effect = table_router

        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data=[{"id": "state-1", "enrollment_id": "enr-1"}])
        orch.supabase.rpc.return_value = mock_rpc

        result = orch.process_pending_leads()

        self.assertEqual(result, [])
        orch._workspace_has_credits.assert_called_with("ws-zero")
        mock_ces.update.assert_any_call({
            "status": "paused",
            "error_reason": "Paused: workspace has insufficient credits. Top up to resume.",
            "next_run_at": None,
        })



class TestOverdraftDebtReconciliation(unittest.TestCase):
    """Paranoia Layer 0, 1 & 2: Tests C-07 overdraft debt preservation and ledger reconciliation."""

    def test_clamp_negative_balance_preserves_paid_tier_debt(self):
        from core.backend.services.credit_service import clamp_negative_balance

        # Positive numbers
        self.assertEqual(clamp_negative_balance(100), 100)
        self.assertEqual(clamp_negative_balance("250.5"), 250)

        # Invalid inputs return 0 safely
        self.assertEqual(clamp_negative_balance(None), 0)
        self.assertEqual(clamp_negative_balance("invalid_input"), 0)

        # Free tier: min_allowed=0 (debt clamped to 0)
        self.assertEqual(clamp_negative_balance(-150, min_allowed=0), 0)

        # Paid tier: min_allowed=-500 (legitimate overdraft debt PRESERVED)
        self.assertEqual(clamp_negative_balance(-450, min_allowed=-500), -450)
        self.assertEqual(clamp_negative_balance(-500, min_allowed=-500), -500)

        # Overdraft breach: clamped to buffer limit (-500)
        self.assertEqual(clamp_negative_balance(-999, min_allowed=-500), -500)

    def test_reconcile_pro_workspace_preserves_overdraft_debt(self):
        from core.backend.services.credit_service import reconcile_workspace_credit_ledger

        mock_supabase = MagicMock()
        # Mock workspace query: Pro tier with -350 balance
        mock_ws_select = MagicMock()
        mock_ws_select.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -350, "tier": "PRO", "plan_tier": "PRO"}]
        )
        # Mock billing transactions: credited=1000, deducted=1350 -> expected = -350
        mock_txn_select = MagicMock()
        mock_txn_select.execute.return_value = MagicMock(
            data=[{"credits_added": 1000, "status": "paid"}]
        )
        mock_audit_select = MagicMock()
        mock_audit_select.execute.return_value = MagicMock(
            data=[{"amount": 1350, "operation_type": "deduct"}]
        )

        def mock_table(table_name):
            m = MagicMock()
            if table_name == "workspaces":
                m.select.return_value.eq.return_value = mock_ws_select
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "billing_transactions":
                m.select.return_value.eq.return_value = mock_txn_select
            elif table_name == "credit_ledger_audit":
                m.select.return_value.eq.return_value = mock_audit_select
                m.insert.return_value.execute.return_value = MagicMock(data=[])
            return m

        mock_supabase.table.side_effect = mock_table

        res = reconcile_workspace_credit_ledger("ws-pro-debt", auto_repair=True, supabase=mock_supabase)
        self.assertEqual(res["status"], "reconciled")
        self.assertEqual(res["tier"], "PRO")
        self.assertEqual(res["current_balance"], -350)
        self.assertEqual(res["expected_balance"], -350)
        self.assertEqual(res["discrepancy"], 0)
        # Debt was NOT wiped to 0!


if __name__ == "__main__":
    unittest.main()
