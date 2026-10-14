import os
import unittest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from core.backend.services.credit_service import (
    trigger_auto_recharge_if_needed,
    get_workspace_auto_recharge_settings,
    update_workspace_auto_recharge_settings,
    is_mock_billing_allowed,
    execute_off_session_charge,
    _FALLBACK_AUTO_RECHARGE_SETTINGS
)
from core.backend.api.routers.billing import (
    simulate_auto_recharge,
    update_auto_recharge,
    AutoRechargeSettingsUpdate
)

class TestAutoRechargeHardening(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-test-autorecharge-101"
        _FALLBACK_AUTO_RECHARGE_SETTINGS.clear()

    def test_auto_recharge_disabled_returns_disabled(self):
        """Layer 0: Returns disabled when settings.enabled is False."""
        _FALLBACK_AUTO_RECHARGE_SETTINGS[self.workspace_id] = {
            "workspace_id": self.workspace_id,
            "enabled": False,
            "threshold_credits": 100,
            "recharge_package_id": "credits_1000",
            "max_monthly_recharges": 5,
            "recharges_this_month": 0,
            "last_recharged_at": None,
            "last_reset_month": "2026-10"
        }
        res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=50)
        self.assertFalse(res["triggered"])
        self.assertEqual(res["reason"], "disabled")

    def test_auto_recharge_balance_above_threshold(self):
        """Layer 0: Does not trigger when balance is above threshold."""
        _FALLBACK_AUTO_RECHARGE_SETTINGS[self.workspace_id] = {
            "workspace_id": self.workspace_id,
            "enabled": True,
            "threshold_credits": 100,
            "recharge_package_id": "credits_1000",
            "max_monthly_recharges": 5,
            "recharges_this_month": 0,
            "last_recharged_at": None,
            "last_reset_month": "2026-10"
        }
        res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=150)
        self.assertFalse(res["triggered"])
        self.assertEqual(res["reason"], "balance_above_threshold")

    def test_auto_recharge_monthly_cap_circuit_breaker(self):
        """Layer 1: Engages circuit breaker when monthly cap is reached."""
        _FALLBACK_AUTO_RECHARGE_SETTINGS[self.workspace_id] = {
            "workspace_id": self.workspace_id,
            "enabled": True,
            "threshold_credits": 100,
            "recharge_package_id": "credits_1000",
            "max_monthly_recharges": 5,
            "recharges_this_month": 5,
            "last_recharged_at": None,
            "last_reset_month": "2026-10"
        }
        res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=20)
        self.assertFalse(res["triggered"])
        self.assertEqual(res["reason"], "monthly_cap_reached")

    def test_auto_recharge_cooldown_debounce(self):
        """Layer 1: Prevents double charges within 5-minute cooldown window."""
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        _FALLBACK_AUTO_RECHARGE_SETTINGS[self.workspace_id] = {
            "workspace_id": self.workspace_id,
            "enabled": True,
            "threshold_credits": 100,
            "recharge_package_id": "credits_1000",
            "max_monthly_recharges": 5,
            "recharges_this_month": 1,
            "last_recharged_at": recent_time,
            "last_reset_month": "2026-10"
        }
        res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=10)
        self.assertFalse(res["triggered"])
        self.assertEqual(res["reason"], "cooldown_active")

    @patch("core.backend.services.credit_service.is_mock_billing_allowed", return_value=False)
    def test_production_fails_closed_without_payment_method(self, mock_is_mock):
        """Layer 0 & 2: In production with no card on file, auto-recharge MUST fail closed."""
        _FALLBACK_AUTO_RECHARGE_SETTINGS[self.workspace_id] = {
            "workspace_id": self.workspace_id,
            "enabled": True,
            "threshold_credits": 100,
            "recharge_package_id": "credits_1000",
            "max_monthly_recharges": 5,
            "recharges_this_month": 0,
            "last_recharged_at": None,
            "last_reset_month": "2026-10"
        }
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=25)
            self.assertFalse(res["triggered"])
            self.assertEqual(res["reason"], "payment_failed")
            self.assertIn("No valid payment method", res["error"])
            # Verified: add_credits_safely RPC was NEVER called!
            mock_supabase.rpc.assert_not_called()
            # Verified: Auto-recharge was auto-paused
            self.assertFalse(_FALLBACK_AUTO_RECHARGE_SETTINGS[self.workspace_id]["enabled"])

    @patch("core.backend.services.credit_service.is_mock_billing_allowed", return_value=False)
    @patch("requests.post")
    def test_production_card_declined_fails_closed_and_pauses(self, mock_post, mock_is_mock):
        """Layer 1 & 2: Stripe card decline fails closed, pauses auto-recharge, and adds 0 credits."""
        mock_supabase = MagicMock()
        mock_settings_table = MagicMock()
        mock_settings_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "workspace_id": self.workspace_id,
                "enabled": True,
                "threshold_credits": 100,
                "recharge_package_id": "credits_1000",
                "max_monthly_recharges": 5,
                "recharges_this_month": 0,
                "last_recharged_at": None,
                "last_reset_month": "2026-10"
            }]
        )
        mock_settings_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"stripe_customer_id": "cus_test123"}]
        )

        mock_other = MagicMock()
        mock_other.insert.return_value.execute.return_value = MagicMock(data=[])

        def table_router(table_name):
            if table_name == "workspace_auto_recharge_settings":
                return mock_settings_table
            elif table_name == "workspaces":
                return mock_ws_table
            return mock_other

        mock_supabase.table.side_effect = table_router

        # Stripe API returns 402 Card Declined
        mock_resp = MagicMock()
        mock_resp.status_code = 402
        mock_resp.json.return_value = {"error": {"message": "Your card was declined: Insufficient Funds"}}
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake123"}):
            with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
                res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=10)
                self.assertFalse(res["triggered"])
                self.assertEqual(res["reason"], "payment_failed")
                self.assertIn("Insufficient Funds", res["error"])
                # Verified: Zero credits minted
                mock_supabase.rpc.assert_not_called()
                # Verified: Settings update called with enabled=False
                mock_settings_table.update.assert_called_with({
                    "enabled": False,
                    "updated_at": mock_settings_table.update.call_args[0][0]["updated_at"]
                })

    @patch("core.backend.services.credit_service.is_mock_billing_allowed", return_value=False)
    @patch("requests.post")
    def test_production_stripe_success_charges_and_credits(self, mock_post, mock_is_mock):
        """Layer 0: Successful Stripe charge captures payment, then mints credits atomically."""
        mock_supabase = MagicMock()
        mock_settings_table = MagicMock()
        mock_settings_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "workspace_id": self.workspace_id,
                "enabled": True,
                "threshold_credits": 100,
                "recharge_package_id": "credits_1000",
                "max_monthly_recharges": 5,
                "recharges_this_month": 0,
                "last_recharged_at": None,
                "last_reset_month": "2026-10"
            }]
        )
        mock_settings_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_ws_table = MagicMock()
        mock_ws_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"stripe_customer_id": "cus_valid_card"}]
        )

        mock_other = MagicMock()
        mock_other.insert.return_value.execute.return_value = MagicMock(data=[])

        def table_router(table_name):
            if table_name == "workspace_auto_recharge_settings":
                return mock_settings_table
            elif table_name == "workspaces":
                return mock_ws_table
            return mock_other

        mock_supabase.table.side_effect = table_router

        # Stripe API returns 200 succeeded
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "pi_captured_123", "status": "succeeded"}
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_fake123"}):
            with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
                res = trigger_auto_recharge_if_needed(self.workspace_id, current_balance=10)
                self.assertTrue(res["triggered"])
                self.assertEqual(res["credits_added"], 1000)
                self.assertEqual(res["provider"], "stripe")
                self.assertEqual(res["charge_id"], "pi_captured_123")
                # Verified: add_credits_safely called
                mock_supabase.rpc.assert_called_once_with('add_credits_safely', {
                    'p_workspace_id': self.workspace_id,
                    'p_credits': 1000,
                    'p_event_id': mock_supabase.rpc.call_args[0][1]['p_event_id'],
                    'p_provider': 'mock'
                })

    @patch("core.backend.api.routers.billing.is_mock_billing_allowed", return_value=False)
    def test_simulate_trigger_endpoint_forbidden_in_production(self, mock_is_mock):
        """Layer 2: POST /billing/auto-recharge/simulate-trigger must return 403 in production."""
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(simulate_auto_recharge(workspace_id=self.workspace_id))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("permanently disabled in production", ctx.exception.detail)

    @patch("core.backend.api.routers.billing.is_mock_billing_allowed", return_value=False)
    @patch("core.backend.api.routers.billing.check_tier_access", return_value=True)
    def test_update_auto_recharge_rejects_enable_without_card_in_production(self, mock_tier, mock_is_mock):
        """Layer 2: PUT /billing/auto-recharge rejects enabled=True if no card on file."""
        mock_supabase = MagicMock()
        # No stripe_customer_id, no active subscription
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        req = AutoRechargeSettingsUpdate(enabled=True, threshold_credits=100)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_auto_recharge(request=req, workspace_id=self.workspace_id, supabase=mock_supabase))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("No payment card or active subscription on file", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
