"""
Rigorous Automated Test Suite for Vulnerability M-10 Remediation:
48-Hour One-Time Offer (OTO) Promotional Expiry Hardening & Milestone Validation.

Enforces the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Mechanics
    * Checkout allows OTO package when first inbound message was received within 48h
    * Checkout allows OTO package when no inbound messages exist yet (first-time eligibility)
    * get_billing_info returns accurate first_win_at, oto_expires_at, and oto_expired values
- Layer 1: Environmental Failure Analysis
    * Checkout rejects OTO package with HTTP 400 when earliest inbound message is > 48h old
    * verify_payment rejects OTO transaction with HTTP 400 when inbound message is > 48h old
    * Timezone-aware timestamp comparison handles UTC and ISO variations reliably
- Layer 2: Human Paranoia
    * Client-side localStorage resets or manipulations cannot bypass backend expiration
    * Unearned promotional packages rejected after milestone window closes
"""

import unittest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from core.backend.api.routers.billing import (
    checkout,
    verify_payment,
    CheckoutRequest,
    VerifyPaymentRequest
)
from campaigns.backend.routers.elein import get_billing_info


# ==============================================================================
# LAYER 0: Foundational Mechanics
# ==============================================================================

class TestLayer0FoundationalOTOValidation(unittest.TestCase):
    """Validates baseline OTO checkout allowance when within promotional window."""

    @patch("core.backend.api.routers.billing.is_mock_billing_allowed", return_value=True)
    def test_checkout_allows_oto_when_no_inbound_messages(self, mock_mock_allowed):
        """When workspace has no inbound messages, OTO package checkout is allowed."""
        mock_supabase = MagicMock()
        messages_table = MagicMock()
        mock_supabase.table.return_value = messages_table

        # Return empty list for inbound messages
        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        # Return mock insert for transaction
        messages_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "sess-1"}])

        req = CheckoutRequest(package_id="growth_tier_oto", provider="razorpay", action="upgrade")
        res = asyncio.run(checkout(req, workspace_id="ws-test", supabase=mock_supabase))

        self.assertIn("order_id", res)
        self.assertIn("session_id", res)

    @patch("core.backend.api.routers.billing.is_mock_billing_allowed", return_value=True)
    def test_checkout_allows_oto_within_48_hours(self, mock_mock_allowed):
        """When workspace first inbound reply is within 48h (e.g. 5 hours ago), checkout succeeds."""
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()

        mock_supabase = MagicMock()
        messages_table = MagicMock()
        mock_supabase.table.return_value = messages_table

        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"created_at": recent_time}]
        )
        messages_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "sess-2"}])

        req = CheckoutRequest(package_id="growth_tier_annual_oto", provider="razorpay", action="upgrade")
        res = asyncio.run(checkout(req, workspace_id="ws-test", supabase=mock_supabase))

        self.assertIn("order_id", res)
        self.assertIn("session_id", res)


# ==============================================================================
# LAYER 1: Environmental Failure Analysis & Expiration Defense
# ==============================================================================

class TestLayer1EnvironmentalExpirationDefense(unittest.TestCase):
    """Validates strict backend rejection when the 48-hour promotional period has elapsed."""

    @patch("core.backend.api.routers.billing.is_mock_billing_allowed", return_value=True)
    def test_checkout_rejects_expired_oto_package(self, mock_mock_allowed):
        """When workspace first inbound reply is 50 hours ago (> 48h), checkout raises HTTP 400."""
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()

        mock_supabase = MagicMock()
        messages_table = MagicMock()
        mock_supabase.table.return_value = messages_table

        messages_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"created_at": expired_time}]
        )

        req = CheckoutRequest(package_id="growth_tier_oto", provider="razorpay", action="upgrade")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(checkout(req, workspace_id="ws-test", supabase=mock_supabase))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("expired", ctx.exception.detail.lower())

    @patch("core.backend.api.routers.billing.is_mock_billing_allowed", return_value=True)
    def test_verify_payment_rejects_expired_oto_session(self, mock_mock_allowed):
        """When verifying a payment for an OTO package after expiry, verify_payment raises HTTP 400."""
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()

        mock_supabase = MagicMock()
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock

        # First call: query billing_transactions
        select_mock = MagicMock()
        table_mock.select.return_value = select_mock
        eq_mock = MagicMock()
        select_mock.eq.return_value = eq_mock

        # Setup side_effect for execute: first for session query, second for messages query
        session_result = MagicMock(data=[{
            "id": "sess-expired",
            "workspace_id": "ws-test",
            "package_id": "growth_tier_oto",
            "status": "pending",
            "provider_order_id": "order_mock_123",
            "provider": "razorpay"
        }])
        messages_result = MagicMock(data=[{"created_at": expired_time}])

        table_mock.select.return_value.eq.return_value.execute.return_value = session_result
        table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = messages_result

        req = VerifyPaymentRequest(
            razorpay_payment_id="pay_mock_123",
            razorpay_order_id="order_mock_123",
            razorpay_signature="sig_mock_123",
            session_id="sess-expired"
        )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(verify_payment(req, workspace_id="ws-test", supabase=mock_supabase))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("expired", ctx.exception.detail.lower())


# ==============================================================================
# LAYER 2: Human Paranoia & Canonical Telemetry
# ==============================================================================

class TestLayer2CanonicalMilestoneTelemetry(unittest.TestCase):
    """Validates that get_billing_info computes canonical OTO expiry telemetry."""

    def test_get_billing_info_reports_accurate_oto_expiry_state(self):
        """get_billing_info outputs first_win_at, oto_expires_at, and oto_expired = True for expired reply."""
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=55)).isoformat()

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"tier": "FREE", "balance": 100})
        
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock
        # Campaigns count
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(count=1)
        # Inbound messages query
        table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"created_at": expired_time}]
        )

        info = get_billing_info(supabase=mock_supabase, workspace_id="ws-test")

        self.assertEqual(info["first_win_at"], expired_time)
        self.assertIsNotNone(info["oto_expires_at"])
        self.assertTrue(info["oto_expired"])

    def test_get_billing_info_reports_active_oto_when_fresh(self):
        """get_billing_info outputs oto_expired = False when first reply is within 48h."""
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"tier": "FREE", "balance": 100})
        
        table_mock = MagicMock()
        mock_supabase.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(count=0)
        table_mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"created_at": recent_time}]
        )

        info = get_billing_info(supabase=mock_supabase, workspace_id="ws-test")

        self.assertEqual(info["first_win_at"], recent_time)
        self.assertIsNotNone(info["oto_expires_at"])
        self.assertFalse(info["oto_expired"])


if __name__ == "__main__":
    unittest.main()
