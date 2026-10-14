import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import hmac
import json
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from core.backend.api.routers.billing import (
    checkout,
    verify_payment,
    webhook_razorpay,
    webhook_lemonsqueezy,
    get_credit_balance_endpoint,
    get_transaction_receipt,
    add_credits_safely_fallback,
    async_add_credits_safely_fallback,
    _PROCESSED_FALLBACK_EVENTS,
    CheckoutRequest,
    VerifyPaymentRequest,
    PACKAGES
)
from core.backend.services.credit_service import check_and_notify_low_balance, deduct_credits


class TestHorizon6BillingAndLedgers(unittest.IsolatedAsyncioTestCase):
    """
    Horizon 6: Billing, Stripe/Razorpay/LemonSqueezy Webhooks, Credit Ledgers & Paywalls.
    Tests compliance with the Three-Layer Logic Architecture (Paranoia Framework).
    """

    # =========================================================================
    # Test 1: Checkout Input Validation & Deferral of Tier Promotion
    # =========================================================================
    async def test_checkout_validation_and_no_premature_tier_promotion(self):
        mock_supabase = MagicMock()

        # Case A: Invalid package_id rejected
        req_bad_pkg = CheckoutRequest(package_id="nonexistent_pkg", provider="razorpay")
        with self.assertRaises(HTTPException) as cm:
            await checkout(req_bad_pkg, workspace_id="ws_123", supabase=mock_supabase)
        self.assertEqual(cm.exception.status_code, 400)

        # Case B: Invalid provider rejected
        req_bad_prov = CheckoutRequest(package_id="growth_tier", provider="unsupported_pay")
        with self.assertRaises(HTTPException) as cm:
            await checkout(req_bad_prov, workspace_id="ws_123", supabase=mock_supabase)
        self.assertEqual(cm.exception.status_code, 400)

        # Case C: Mock checkout creates pending session and DOES NOT promote tier to PRO before verify
        req_valid = CheckoutRequest(package_id="growth_tier", provider="razorpay")
        with patch.dict("os.environ", {"ALLOW_MOCK_BILLING": "true", "RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": ""}):
            res = await checkout(req_valid, workspace_id="ws_123", supabase=mock_supabase)

        self.assertIn("order_id", res)
        self.assertIn("session_id", res)
        # Verify workspaces table was NOT updated to PRO prematurely
        update_calls = mock_supabase.table("workspaces").update.call_args_list
        self.assertEqual(len(update_calls), 0, "Workspace tier must NOT be promoted to PRO before payment verification")

    # =========================================================================
    # Test 2: Synchronous Payment Verification & Cross-Workspace Isolation
    # =========================================================================
    async def test_verify_payment_cross_workspace_defense(self):
        mock_supabase = MagicMock()
        mock_txn_table = MagicMock()

        # Session belongs to ws_attacker, but caller is ws_victim
        mock_txn_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"workspace_id": "ws_other", "package_id": "growth_tier", "status": "pending"}]
        )
        mock_supabase.table.return_value = mock_txn_table

        req = VerifyPaymentRequest(
            razorpay_payment_id="pay_123",
            razorpay_order_id="order_mock_123",
            razorpay_signature="sig_123",
            session_id="sess_123"
        )

        with self.assertRaises(HTTPException) as cm:
            await verify_payment(req, workspace_id="ws_my_workspace", supabase=mock_supabase)
        self.assertEqual(cm.exception.status_code, 403, "Cross-workspace session verification must be blocked")

    # =========================================================================
    # Test 3: Razorpay Downgrade Kill-Switch & Tier Reversion
    # =========================================================================
    async def test_razorpay_downgrade_killswitch_reverts_tier_and_pauses(self):
        secret = "rzp_secret_test_123"
        payload_data = {
            "event": "subscription.cancelled",
            "payload": {
                "subscription": {
                    "entity": {
                        "notes": {
                            "workspace_id": "ws_churned_1"
                        }
                    }
                }
            }
        }
        body_bytes = json.dumps(payload_data).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body_bytes, "sha256").hexdigest()

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body_bytes)
        mock_request.headers = {"X-Razorpay-Signature": signature}

        mock_async_supabase = MagicMock()
        mock_camp_table = MagicMock()
        mock_ws_table = MagicMock()

        mock_camp_table.update.return_value.eq.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock())
        mock_ws_table.update.return_value.eq.return_value.execute = AsyncMock(return_value=MagicMock())

        def table_router(table_name):
            if table_name == "campaigns":
                return mock_camp_table
            elif table_name == "workspaces":
                return mock_ws_table
            return MagicMock()

        mock_async_supabase.table.side_effect = table_router

        with patch.dict("os.environ", {"RAZORPAY_WEBHOOK_SECRET": secret}), \
             patch("core.backend.api.routers.billing.get_async_service_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_async_supabase
            res = await webhook_razorpay(mock_request)

        self.assertEqual(res["status"], "ok")
        # Verify active campaigns were PAUSED
        mock_camp_table.update.assert_called_with({"status": "PAUSED"})
        # Verify workspace tier was downgraded to FREE
        mock_ws_table.update.assert_called_with({"tier": "FREE"})

    # =========================================================================
    # Test 4: Low Balance Alert Owner Resolution & 7-Day Throttling
    # =========================================================================
    def test_low_balance_alert_resolves_owner_and_throttles(self):
        mock_supabase = MagicMock()
        mock_outbox = MagicMock()
        mock_ws = MagicMock()
        mock_user = MagicMock()

        # Case A: Balance >= 100 does nothing
        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            check_and_notify_low_balance("ws_healthy", 150)
            self.assertEqual(mock_supabase.table.call_count, 0)

        # Case B: Balance < 100, but alert already sent in last 7 days -> throttled
        mock_outbox.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_recent_alert"}]
        )
        mock_supabase.table.return_value = mock_outbox

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            check_and_notify_low_balance("ws_low", 40)
            mock_outbox.insert.assert_not_called()

    # =========================================================================
    # Test 5: Unmigrated RPC Fallback for Credit Balance (Layer 1 Paranoia)
    # =========================================================================
    async def test_get_credit_balance_unmigrated_rpc_fallback(self):
        """Layer 1: When get_credit_balance RPC fails (unmigrated database), fallback queries workspaces table directly."""
        mock_supabase = MagicMock()
        # RPC fails
        mock_supabase.rpc.return_value.execute.side_effect = Exception("PGRST202: Could not find the function public.get_credit_balance")
        
        # Workspaces table returns valid tier and balance
        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO", "data_cleaning_credits": 2500}]
        )
        mock_supabase.table.return_value = mock_ws_table

        res = await get_credit_balance_endpoint("ws_pro_test", supabase=mock_supabase)
        self.assertEqual(res["balance"], 2500)
        self.assertEqual(res["tier"], "PRO")
        self.assertTrue(res.get("unmigrated_rpc"))

    # =========================================================================
    # Test 6: Corporate Tax Receipt Generation & IDOR Defense (Layer 0, 1 & 2)
    # =========================================================================
    async def test_get_transaction_receipt_idor_defense_and_tax_calculation(self):
        """Layer 2 IDOR: Reject cross-workspace receipt requests with 403; Layer 0: Calculate GST & line items correctly."""
        mock_supabase = MagicMock()
        mock_txn_table = MagicMock()

        # Transaction belongs to ws_company_a
        mock_txn_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "txn_12345678abcdef",
                "workspace_id": "ws_company_a",
                "created_at": "2026-10-10T12:00:00Z",
                "provider": "razorpay",
                "provider_order_id": "order_rzp_999",
                "package_id": "growth_tier",
                "amount_cents": 799900,
                "currency": "INR",
                "credits_added": 5000,
                "status": "paid"
            }]
        )
        mock_supabase.table.return_value = mock_txn_table

        # Case A: Attacker from ws_intruder attempts to fetch receipt -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            await get_transaction_receipt("txn_12345678abcdef", workspace_id="ws_intruder", supabase=mock_supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Access denied", ctx.exception.detail)

        # Case B: Authorized workspace fetches receipt -> formatted tax receipt
        res = await get_transaction_receipt("txn_12345678abcdef", workspace_id="ws_company_a", supabase=mock_supabase)
        self.assertEqual(res["invoice_number"], "INV-TXN_1234")
        self.assertEqual(res["amount_cents"], 799900)
        self.assertGreater(res["tax_cents"], 0, "18% GST must be computed for INR invoices")
        self.assertEqual(res["subtotal_cents"] + res["tax_cents"], 799900)
        self.assertEqual(res["credits_added"], 5000)
        self.assertIn("Ele-in Technologies Inc.", res["seller"]["company_name"])

    # =========================================================================
    # Test 7: Add Credits Safely Fallback (Layer 1 Paranoia)
    # =========================================================================
    def test_add_credits_safely_fallback_when_rpc_fails(self):
        """Layer 1: If add_credits_safely RPC throws missing function error, direct update increments balance safely."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.side_effect = Exception("PGRST202: function add_credits_safely does not exist")

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 1000}]
        )
        mock_supabase.table.return_value = mock_ws_table

        add_credits_safely_fallback(
            supabase=mock_supabase,
            workspace_id="ws_client",
            credits=500,
            event_id="evt_test_123",
            provider="mock"
        )

        # Verify workspaces table was updated with 1000 + 500 = 1500
        mock_ws_table.update.assert_called_with({"data_cleaning_credits": 1500})

    # =========================================================================
    # Test 8: Fallback Deduplication and Replay Protection (H-01 Paranoia)
    # =========================================================================
    def test_add_credits_safely_fallback_deduplicates_duplicate_event_replays(self):
        """Layer 1 & 2: Repeated fallback calls with the same event_id and provider must not double-credit."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.side_effect = Exception("RPC disabled")

        mock_evt_table = MagicMock()
        mock_evt_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 2000}]
        )

        def table_router(table_name):
            if table_name == "processed_webhook_events":
                return mock_evt_table
            return mock_ws_table

        mock_supabase.table.side_effect = table_router

        # First call: adds 300 credits
        add_credits_safely_fallback(
            supabase=mock_supabase,
            workspace_id="ws_dedup_test",
            credits=300,
            event_id="evt_replay_999",
            provider="stripe"
        )
        self.assertEqual(mock_ws_table.update.call_count, 1)
        mock_ws_table.update.assert_called_with({"data_cleaning_credits": 2300})

        # Second call with same event_id & provider: caught by deduplication, NO additional update
        add_credits_safely_fallback(
            supabase=mock_supabase,
            workspace_id="ws_dedup_test",
            credits=300,
            event_id="evt_replay_999",
            provider="stripe"
        )
        self.assertEqual(mock_ws_table.update.call_count, 1, "Duplicate fallback replay must be deduplicated")

    async def test_async_add_credits_safely_fallback_deduplication(self):
        """Layer 1 & 2: Async fallback must deduplicate replays and record event."""
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.side_effect = Exception("RPC disabled")

        mock_evt_table = MagicMock()
        mock_evt_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 5000}]
        )

        def table_router(table_name):
            if table_name == "processed_webhook_events":
                return mock_evt_table
            return mock_ws_table

        mock_supabase.table.side_effect = table_router

        # First call
        await async_add_credits_safely_fallback(
            supabase=mock_supabase,
            workspace_id="ws_async_dedup",
            credits=1000,
            event_id="evt_async_unique_1",
            provider="stripe"
        )
        self.assertEqual(mock_ws_table.update.call_count, 1)

        # Duplicate call
        await async_add_credits_safely_fallback(
            supabase=mock_supabase,
            workspace_id="ws_async_dedup",
            credits=1000,
            event_id="evt_async_unique_1",
            provider="stripe"
        )
        self.assertEqual(mock_ws_table.update.call_count, 1, "Duplicate async fallback call must be ignored")


if __name__ == "__main__":
    unittest.main()
