import os
from dotenv import load_dotenv
load_dotenv("backend/.env")
if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from core.backend.api.routers.billing import checkout, PACKAGES, CheckoutRequest
from campaigns.backend.routers.elein import activate_campaign, delete_campaign, update_campaign, get_billing_info
from campaigns.backend.schemas.elein import CampaignCreate, EleInNode, EleInEdge

class TestBillingRouter(unittest.TestCase):
    def setUp(self):
        self.supabase = MagicMock()
        self.workspace_id = "ws-test-123"

    def test_packages_structure(self):
        """Verify all packages define required metadata including tier, credits, and price."""
        for pkg_id, pkg in PACKAGES.items():
            self.assertIn("credits", pkg)
            self.assertIn("inr_paise", pkg)
            self.assertIn("usd_cents", pkg)
            self.assertIn("tier", pkg)
            if "tier" in pkg_id:
                self.assertEqual(pkg["tier"], "PRO")
            else:
                self.assertIsNone(pkg["tier"])

    def test_checkout_growth_tier_razorpay(self):
        """Mock checkout for growth tier upgrades workspace to PRO and returns order_id."""
        req = CheckoutRequest(package_id="growth_tier", provider="razorpay")
        
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        table_mock.insert.return_value.execute.return_value = MagicMock(data=[])
        self.supabase.rpc.return_value.execute.return_value = MagicMock(data=True)

        res = asyncio.run(checkout(req, workspace_id=self.workspace_id, supabase=self.supabase))
        
        self.assertIn("order_id", res)
        self.assertTrue(res["order_id"].startswith("order_mock_"))
        self.assertIn("amount", res)
        self.assertIn("key_id", res)
        
        # Verify workspace tier is NOT prematurely updated in checkout (deferred to verify_payment)
        update_ws_calls = [
            call for call in self.supabase.table.mock_calls
            if call[1] and call[1][0] == "workspaces"
        ]
        self.assertEqual(len(update_ws_calls), 0, "Workspace tier must not be upgraded in checkout before payment verification")
        
        # Verify billing transaction was logged
        self.supabase.table.assert_any_call("billing_transactions")

    def test_verify_mock_payment(self):
        """Verifying a mock payment marks transaction paid and returns verified status."""
        from core.backend.api.routers.billing import verify_payment, VerifyPaymentRequest
        req = VerifyPaymentRequest(
            razorpay_payment_id="pay_mock_123",
            razorpay_order_id="order_mock_123",
            razorpay_signature="mock_sig",
            session_id="sess-123"
        )
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        session_mock = MagicMock(data=[{"workspace_id": self.workspace_id, "package_id": "growth_tier", "status": "pending"}])
        table_mock.select.return_value.eq.return_value.execute.return_value = session_mock
        table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        res = asyncio.run(verify_payment(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(res, {"status": "verified", "tier": "PRO"})

    def test_verify_mock_payment_blocked_in_production(self):
        """Mock verification must be strictly rejected with 403 when ENVIRONMENT is production."""
        from core.backend.api.routers.billing import verify_payment, VerifyPaymentRequest
        req = VerifyPaymentRequest(
            razorpay_payment_id="pay_mock_123",
            razorpay_order_id="order_mock_123",
            razorpay_signature="mock_sig",
            session_id="sess-123"
        )
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        session_mock = MagicMock(data=[{"workspace_id": self.workspace_id, "package_id": "growth_tier", "status": "pending"}])
        table_mock.select.return_value.eq.return_value.execute.return_value = session_mock

        with patch.dict("os.environ", {"ENVIRONMENT": "production", "ALLOW_MOCK_BILLING": "true"}):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(verify_payment(req, workspace_id=self.workspace_id, supabase=self.supabase))
            self.assertEqual(cm.exception.status_code, 403)
            self.assertIn("Simulated payment verification is disabled in production", cm.exception.detail)

    def test_verify_mock_payment_mismatched_order_id_blocked(self):
        """Trying to verify a real order session using a mock order id is blocked with 400."""
        from core.backend.api.routers.billing import verify_payment, VerifyPaymentRequest
        req = VerifyPaymentRequest(
            razorpay_payment_id="pay_mock_123",
            razorpay_order_id="order_mock_123",
            razorpay_signature="mock_sig",
            session_id="sess-123"
        )
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        # Session was created for real razorpay order
        session_mock = MagicMock(data=[{
            "workspace_id": self.workspace_id,
            "package_id": "growth_tier",
            "status": "pending",
            "provider_order_id": "order_real_rzp_9999"
        }])
        table_mock.select.return_value.eq.return_value.execute.return_value = session_mock

        with self.assertRaises(HTTPException) as cm:
            asyncio.run(verify_payment(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Mismatched session provider order ID", cm.exception.detail)

    def test_verify_payment_empty_params_blocked(self):
        """Empty or whitespace-only verification parameters are rejected with 400."""
        from core.backend.api.routers.billing import verify_payment, VerifyPaymentRequest
        req = VerifyPaymentRequest(
            razorpay_payment_id="   ",
            razorpay_order_id="order_mock_123",
            razorpay_signature="",
            session_id="sess-123"
        )
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(verify_payment(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 400)

    def test_checkout_annual_tier_lemonsqueezy(self):
        """Mock checkout for annual tier returns lemonsqueezy checkout url."""
        req = CheckoutRequest(package_id="growth_tier_annual", provider="lemonsqueezy")
        
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        table_mock.insert.return_value.execute.return_value = MagicMock(data=[])

        res = asyncio.run(checkout(req, workspace_id=self.workspace_id, supabase=self.supabase))
        
        self.assertIn("checkout_url", res)
        self.assertTrue(res["checkout_url"].startswith("https://mock.lemonsqueezy.com/checkout/"))

    def test_checkout_invalid_package(self):
        """Checkout with non-existent package raises 400."""
        req = CheckoutRequest(package_id="invalid_tier", provider="razorpay")
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(checkout(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 400)

    def test_checkout_invalid_provider(self):
        """Checkout with unsupported provider raises 400."""
        req = CheckoutRequest(package_id="growth_tier", provider="stripe_unsupported")
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(checkout(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 400)


class TestCampaignLimits(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.workspace_id = "ws-test-456"

    def test_activate_campaign_free_tier_under_limit(self):
        """Free tier with 0 other active campaigns can activate cleanly."""
        # Mock workspace tier as FREE
        ws_mock = MagicMock(data=[{"tier": "FREE"}])
        camp_count_mock = MagicMock(count=0)
        
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.execute.side_effect = [
            ws_mock,
            MagicMock(data=[]),
            MagicMock(data=[]),
            MagicMock(data=[{"id": "acc-1"}]),
        ]
        table_mock.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = camp_count_mock
        table_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        res = activate_campaign("camp-1", workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(res, {"status": "activated"})

    def test_activate_campaign_free_tier_blocked_at_limit(self):
        """Free tier with 1 existing active campaign is blocked with 403."""
        ws_mock = MagicMock(data=[{"tier": "FREE"}])
        camp_count_mock = MagicMock(count=1)
        
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.execute.side_effect = [
            ws_mock,
        ]
        table_mock.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = camp_count_mock

        with self.assertRaises(HTTPException) as cm:
            activate_campaign("camp-new", workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Free Tier is limited to 1 active campaign", cm.exception.detail)

    def test_activate_campaign_pro_tier_unlimited(self):
        """PRO tier bypasses limit check and activates even with 5 existing active campaigns."""
        ws_mock = MagicMock(data=[{"tier": "PRO"}])
        
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.execute.return_value = ws_mock
        table_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        res = activate_campaign("camp-any", workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(res, {"status": "activated"})


    def test_activate_campaign_not_found(self):
        """Activating a non-existent campaign raises 404."""
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as cm:
            activate_campaign("non-existent-camp", workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(cm.exception.detail, "Campaign not found")

    def test_delete_campaign_not_found(self):
        """Deleting a non-existent campaign raises 404."""
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as cm:
            delete_campaign("non-existent-camp", workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(cm.exception.detail, "Campaign not found")

    def test_update_already_active_campaign_validates_variables(self):
        """Updating an already ACTIVE campaign must still validate template variables."""
        # Existing campaign is ACTIVE
        existing_camp = MagicMock(data=[{"id": "camp-active", "status": "ACTIVE", "metadata": {}}])
        
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = existing_camp
        
        # Node with an invalid variable tag
        invalid_node = EleInNode(
            id="n1",
            type="send_message",
            position={"x": 0, "y": 0},
            data={"body": "Hello {{forbidden_variable}}"}
        )
        payload = CampaignCreate(
            name="Active Campaign Edit",
            nodes=[invalid_node],
            edges=[],
            status="ACTIVE"
        )

        with self.assertRaises(HTTPException) as cm:
            update_campaign("camp-active", payload, workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Invalid template variable", cm.exception.detail)

    def test_activate_campaign_no_active_senders(self):
        """Activating a campaign with no active senders raises 400 no_active_senders."""
        table_mock = MagicMock()
        self.client.table.return_value = table_mock
        
        camp_mock = MagicMock(data=[{"id": "camp-1", "status": "PAUSED"}])
        ws_mock = MagicMock(data=[{"tier": "PRO"}])
        empty_senders_mock = MagicMock(data=[])
        
        table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = camp_mock
        table_mock.select.return_value.eq.return_value.execute.return_value = ws_mock
        table_mock.select.return_value.eq.return_value.or_.return_value.execute.return_value = empty_senders_mock

        with self.assertRaises(HTTPException) as cm:
            activate_campaign("camp-1", workspace_id=self.workspace_id, client=self.client)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.detail, "no_active_senders")


class TestBillingInfoFallback(unittest.TestCase):
    def test_get_billing_info_fallback(self):
        """When database fails, get_billing_info returns safe defaults for all frontend keys."""
        broken_client = MagicMock()
        broken_client.table.side_effect = RuntimeError("DB connection failure")

        info = get_billing_info(supabase=broken_client, workspace_id="ws-any")
        self.assertEqual(info["tier"], "FREE")
        self.assertEqual(info["plan_name"], "Free Tier")
        self.assertEqual(info["active_campaigns"], 0)
        self.assertIn("data_cleaning_credits", info)


class TestSalvageOfferSecurity(unittest.TestCase):
    def setUp(self):
        self.supabase = MagicMock()
        self.workspace_id = "ws-salvage-test"

    def test_salvage_offer_free_tier_blocked(self):
        """Free-tier workspace cannot claim salvage retention offers."""
        from core.backend.api.routers.billing import apply_salvage_offer, SalvageOfferRequest
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        # Workspace is FREE tier
        table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE", "status": "active"}]
        )

        req = SalvageOfferRequest(offerType="starter_downsell", reason="expensive")
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(apply_salvage_offer(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("paid active subscriptions", cm.exception.detail)

    def test_salvage_offer_starter_downsell_once_only(self):
        """Starter downsell offer cannot be claimed twice by the same workspace."""
        from core.backend.api.routers.billing import apply_salvage_offer, SalvageOfferRequest
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        # Workspace is PRO tier
        table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO", "status": "active"}]
        )
        # Already redeemed starter downsell
        table_mock.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "prev-1", "package_id": "offer_starter_downsell", "created_at": "2026-09-01T00:00:00Z"}]
        )

        req = SalvageOfferRequest(offerType="starter_downsell", reason="expensive")
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(apply_salvage_offer(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("already been redeemed", cm.exception.detail)

    def test_salvage_offer_pro_tier_first_time_succeeds(self):
        """PRO tier claiming starter downsell for the first time succeeds and sets PRO status."""
        from core.backend.api.routers.billing import apply_salvage_offer, SalvageOfferRequest
        table_mock = MagicMock()
        self.supabase.table.return_value = table_mock
        # Workspace is PRO tier
        table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO", "status": "active"}]
        )
        # No prior redemptions
        table_mock.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        table_mock.insert.return_value.execute.return_value = MagicMock(data=[])
        table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        req = SalvageOfferRequest(offerType="starter_downsell", reason="expensive")
        res = asyncio.run(apply_salvage_offer(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["offer_applied"], "starter_downsell")

    def test_salvage_offer_invalid_type_rejected(self):
        """Invalid offer types are rejected with 400 Bad Request."""
        from core.backend.api.routers.billing import apply_salvage_offer, SalvageOfferRequest
        req = SalvageOfferRequest(offerType="free_money_exploit")
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(apply_salvage_offer(req, workspace_id=self.workspace_id, supabase=self.supabase))
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
