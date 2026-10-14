import unittest
from unittest.mock import MagicMock, patch
import concurrent.futures

from core.backend.services.credit_service import (
    reconcile_workspace_credit_ledger,
    clamp_negative_balance,
    generate_fleet_architecture_certification,
    _credit_ledger_mutex
)

class TestFinalArchitectureCertificationGuard(unittest.TestCase):
    """
    Step 40 Track B — Final Credit Ledger Reconciliation, Audit Certification & Production Architecture Lock.
    Tests compliance with the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def test_reconcile_workspace_credit_ledger_balanced(self):
        """1. Verifies clean 0 discrepancy report when balance matches ledger."""
        mock_supabase = MagicMock()
        mock_ws = MagicMock()
        mock_ws.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 1000}]
        )
        mock_txn = MagicMock()
        mock_txn.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"credits_added": 1000, "status": "success"}]
        )

        def side_effect(table_name):
            if table_name == "workspaces":
                return mock_ws
            elif table_name == "billing_transactions":
                return mock_txn
            return MagicMock()

        mock_supabase.table.side_effect = side_effect

        res = reconcile_workspace_credit_ledger("ws_test_1", auto_repair=False, supabase=mock_supabase)
        self.assertEqual(res["status"], "reconciled")
        self.assertEqual(res["current_balance"], 1000)
        self.assertEqual(res["expected_balance"], 1000)
        self.assertEqual(res["discrepancy"], 0)
        self.assertFalse(res["auto_repaired"])

    def test_reconcile_workspace_credit_ledger_detects_discrepancy(self):
        """2. Verifies discrepancy detection when balance does not match ledger."""
        mock_supabase = MagicMock()
        mock_ws = MagicMock()
        mock_ws.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 2500}]
        )
        mock_txn = MagicMock()
        mock_txn.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"credits_added": 1000, "status": "success"}]
        )

        def side_effect(table_name):
            if table_name == "workspaces":
                return mock_ws
            elif table_name == "billing_transactions":
                return mock_txn
            return MagicMock()

        mock_supabase.table.side_effect = side_effect

        res = reconcile_workspace_credit_ledger("ws_test_2", auto_repair=False, supabase=mock_supabase)
        self.assertEqual(res["status"], "discrepancy_detected")
        self.assertEqual(res["current_balance"], 2500)
        self.assertEqual(res["expected_balance"], 1000)
        self.assertEqual(res["discrepancy"], 1500)
        self.assertFalse(res["auto_repaired"])

    def test_reconcile_workspace_credit_ledger_auto_repair(self):
        """3. Verifies balance auto-repair when auto_repair=True."""
        mock_supabase = MagicMock()
        mock_ws = MagicMock()
        mock_ws.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 2500}]
        )
        mock_txn = MagicMock()
        mock_txn.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"credits_added": 1000, "status": "success"}]
        )

        def side_effect(table_name):
            if table_name == "workspaces":
                return mock_ws
            elif table_name == "billing_transactions":
                return mock_txn
            return MagicMock()

        mock_supabase.table.side_effect = side_effect

        res = reconcile_workspace_credit_ledger("ws_test_3", auto_repair=True, supabase=mock_supabase)
        self.assertEqual(res["status"], "repaired")
        self.assertEqual(res["current_balance"], 1000)
        self.assertEqual(res["expected_balance"], 1000)
        self.assertEqual(res["discrepancy"], 0)
        self.assertTrue(res["auto_repaired"])
        mock_ws.update.assert_called_once()

    def test_clamp_negative_balance(self):
        """4. Verifies negative numbers, strings, and None clamped to 0."""
        self.assertEqual(clamp_negative_balance(-500), 0)
        self.assertEqual(clamp_negative_balance("150"), 150)
        self.assertEqual(clamp_negative_balance(None), 0)
        self.assertEqual(clamp_negative_balance("invalid"), 0)
        self.assertEqual(clamp_negative_balance(450.75), 450)

    def test_generate_fleet_architecture_certification(self):
        """5. Verifies 40 certified domains and production_ready=True."""
        cert = generate_fleet_architecture_certification()
        self.assertEqual(cert["status"], "CERTIFIED")
        self.assertTrue(cert["production_ready"])
        self.assertEqual(cert["total_certified_domains"], 40)
        self.assertIn("orchestrator_concurrency", cert["certified_domains"])
        self.assertIn("credit_ledger_reconciliation", cert["certified_domains"])
        self.assertEqual(len(cert["layers_verified"]), 3)

    def test_concurrency_lock_thread_safety(self):
        """6. Verifies thread safety under concurrent reconciliation calls."""
        mock_supabase = MagicMock()
        mock_ws = MagicMock()
        mock_ws.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 1000}]
        )
        mock_txn = MagicMock()
        mock_txn.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"credits_added": 1000, "status": "success"}]
        )

        def side_effect(table_name):
            if table_name == "workspaces":
                return mock_ws
            elif table_name == "billing_transactions":
                return mock_txn
            return MagicMock()

        mock_supabase.table.side_effect = side_effect

        results = []
        def worker():
            res = reconcile_workspace_credit_ledger("ws_concurrent", auto_repair=False, supabase=mock_supabase)
            results.append(res)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker) for _ in range(10)]
            concurrent.futures.wait(futures)

        self.assertEqual(len(results), 10)
        for r in results:
            self.assertEqual(r["status"], "reconciled")
            self.assertEqual(r["current_balance"], 1000)

if __name__ == "__main__":
    unittest.main()
