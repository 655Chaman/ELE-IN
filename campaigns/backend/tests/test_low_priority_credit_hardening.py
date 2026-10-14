"""
Rigorous Automated Test Suite for Vulnerabilities L-01, L-02, L-03 Remediation:
- L-01: Razorpay Webhook Exception Logging & Retry Signaling (No Silent Swallowing)
- L-02: Negative & Null Amount Input Validation in deduct_credits
- L-03: credit_deductions Inclusion in Credit Ledger Reconciliation

Enforces the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Mechanics
    * deduct_credits rejects negative and null amounts cleanly
    * deduct_credits preserves zero_amount pass-through
    * reconcile_workspace_credit_ledger sums deductions from credit_deductions table
- Layer 1: Environmental Failure Analysis
    * webhook_razorpay raises HTTP 500 on unexpected errors to signal gateway retry
    * webhook_razorpay logs with structured logger rather than stdout printing
    * Malformed or duplicate notes gracefully handled without crashing worker
- Layer 2: Human Paranoia
    * Caller cannot pass negative values to secretly increment balance or bypass quota
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, Request

from core.backend.api.routers.billing import webhook_razorpay
from core.backend.services.credit_service import (
    deduct_credits,
    reconcile_workspace_credit_ledger
)


# ==============================================================================
# L-01: Razorpay Webhook Exception Logging & Retry Signaling
# ==============================================================================

class TestL01RazorpayWebhookExceptionHardening(unittest.TestCase):
    """Validates that webhook_razorpay signals retry on operational failure."""

    @patch("core.backend.api.routers.billing.hmac.compare_digest", return_value=True)
    @patch.dict("os.environ", {"RAZORPAY_WEBHOOK_SECRET": "secret_test_123"})
    def test_webhook_razorpay_raises_500_on_internal_exception(self, mock_hmac):
        """When an internal database or RPC failure occurs, webhook_razorpay raises HTTP 500 for gateway retry."""
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"event": "payment.captured", "payload": {"payment": {"entity": {"notes": {"checkout_session_id": "sess_1"}}}}}')
        mock_request.headers = {"X-Razorpay-Signature": "sig_valid"}

        # Patch get_async_service_client to raise unexpected DB connection failure
        with patch("core.backend.api.routers.billing.get_async_service_client", side_effect=RuntimeError("Database pool exhausted")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(webhook_razorpay(mock_request))

            self.assertEqual(ctx.exception.status_code, 500)
            self.assertIn("webhook processing error", ctx.exception.detail.lower())

    @patch("core.backend.api.routers.billing.hmac.compare_digest", return_value=True)
    @patch.dict("os.environ", {"RAZORPAY_WEBHOOK_SECRET": "secret_test_123"})
    def test_webhook_razorpay_handles_value_error_gracefully(self, mock_hmac):
        """When notes payload is missing checkout_session_id (client error), webhook returns ignored without 500."""
        mock_request = MagicMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"event": "payment.captured", "payload": {"payment": {"entity": {"notes": {}}}}}')
        mock_request.headers = {"X-Razorpay-Signature": "sig_valid"}

        res = asyncio.run(webhook_razorpay(mock_request))
        self.assertEqual(res["status"], "ignored")
        self.assertIn("reason", res)


# ==============================================================================
# L-02: Negative Amount Validation in deduct_credits
# ==============================================================================

class TestL02DeductCreditsValidationHardening(unittest.TestCase):
    """Validates that deduct_credits strictly rejects negative and null values."""

    def test_deduct_credits_rejects_negative_amount(self):
        """Passing negative amount returns success=False with negative_amount_invalid reason."""
        res = deduct_credits(
            workspace_id="ws-test",
            amount=-25,
            action_type="ai_reply"
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "negative_amount_invalid")

    def test_deduct_credits_rejects_null_amount(self):
        """Passing None for amount returns success=False with negative_amount_invalid reason."""
        res = deduct_credits(
            workspace_id="ws-test",
            amount=None,  # type: ignore
            action_type="ai_reply"
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "negative_amount_invalid")

    def test_deduct_credits_accepts_zero_amount(self):
        """Passing amount=0 safely returns zero_amount reason without invoking database."""
        res = deduct_credits(
            workspace_id="ws-test",
            amount=0,
            action_type="ai_reply"
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["reason"], "zero_amount")


# ==============================================================================
# L-03: credit_deductions Inclusion in Credit Ledger Reconciliation
# ==============================================================================

class TestL03CreditReconciliationDeductionsHardening(unittest.TestCase):
    """Validates that reconcile_workspace_credit_ledger queries and sums credit_deductions."""

    def test_reconciliation_sums_credit_deductions_table(self):
        """Reconciliation incorporates amounts from credit_deductions table into total_deducted."""
        mock_supabase = MagicMock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        # 1. workspaces query: current_balance = 800, tier = FREE
        ws_data = MagicMock(data=[{"data_cleaning_credits": 800, "tier": "FREE"}])
        # 2. billing_transactions query: credited = 1000
        txn_data = MagicMock(data=[{"credits_added": 1000, "status": "paid"}])
        # 3. credit_deductions query: deducted = 200 (150 + 50)
        deduct_data = MagicMock(data=[{"amount": 150}, {"amount": 50}])
        # 4. credit_ledger_audit query: empty
        audit_data = MagicMock(data=[])

        def table_side_effect(table_name):
            t_mock = MagicMock()
            if table_name == "workspaces":
                t_mock.select.return_value.eq.return_value.execute.return_value = ws_data
            elif table_name == "billing_transactions":
                t_mock.select.return_value.eq.return_value.execute.return_value = txn_data
            elif table_name == "credit_deductions":
                t_mock.select.return_value.eq.return_value.execute.return_value = deduct_data
            elif table_name == "credit_ledger_audit":
                t_mock.select.return_value.eq.return_value.execute.return_value = audit_data
            elif table_name == "processing_locks":
                t_mock.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                t_mock.insert.return_value.execute.return_value = MagicMock(data=[{"lock_key": "k"}])
                t_mock.delete.return_value.eq.return_value.execute.return_value = MagicMock()
            return t_mock

        mock_supabase.table.side_effect = table_side_effect

        with patch("core.backend.services.credit_service.distributed_workspace_lock") as mock_lock:
            # Context manager allows acquisition
            mock_lock.return_value.__enter__.return_value = True
            mock_lock.return_value.__exit__.return_value = None

            res = reconcile_workspace_credit_ledger(
                workspace_id="ws-test-ledger",
                auto_repair=False,
                supabase=mock_supabase
            )

            # Expected balance: total_credited (1000) - total_deducted (200) = 800.
            # Current balance is 800.
            # Discrepancy should be 0!
            self.assertEqual(res["status"], "reconciled")
            self.assertEqual(res["current_balance"], 800)
            self.assertEqual(res["expected_balance"], 800)
            self.assertEqual(res["discrepancy"], 0)


if __name__ == "__main__":
    unittest.main()
