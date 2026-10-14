import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
import os

from core.backend.api.routers.billing import router, calculate_proration_credit, _PROCESSED_STRIPE_EVENTS
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)

class TestBillingStripeIdempotencyGuard(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Clear in-memory replay ledger before each test
        _PROCESSED_STRIPE_EVENTS.clear()

    @patch("core.backend.api.routers.billing.get_async_service_client")
    def test_stripe_webhook_checkout_session_completed_grants_credits(self, mock_get_service_client):
        mock_supabase = MagicMock()
        mock_get_service_client.return_value = mock_supabase
        
        # Workspace exists check
        mock_ws_res = MagicMock()
        mock_ws_res.data = [{"id": "ws_123", "status": "active"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws_res

        event_payload = {
            "id": "evt_test_checkout_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_1",
                    "client_reference_id": "ws_123",
                    "metadata": {
                        "package_id": "credits_1000",
                        "workspace_id": "ws_123"
                    }
                }
            }
        }

        with patch("core.backend.api.routers.billing.os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_test"}):
            with patch("core.backend.api.routers.billing.verify_stripe_signature", return_value=True):
                response = self.client.post(
                    "/webhook/stripe",
                    json=event_payload,
                    headers={"stripe-signature": "t=123,v1=mock"}
                )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    @patch("core.backend.api.routers.billing.get_async_service_client")
    def test_stripe_webhook_replay_idempotency(self, mock_get_service_client):
        mock_supabase = MagicMock()
        mock_get_service_client.return_value = mock_supabase
        
        mock_ws_res = MagicMock()
        mock_ws_res.data = [{"id": "ws_123", "status": "active"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws_res

        event_payload = {
            "id": "evt_duplicate_999",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_dup",
                    "client_reference_id": "ws_123",
                    "metadata": {"package_id": "credits_1000"}
                }
            }
        }

        with patch("core.backend.api.routers.billing.verify_stripe_signature", return_value=True):
            # First delivery
            res1 = self.client.post("/webhook/stripe", json=event_payload, headers={"stripe-signature": "sig"})
            self.assertEqual(res1.status_code, 200)

            # Replay delivery (duplicate event ID)
            res2 = self.client.post("/webhook/stripe", json=event_payload, headers={"stripe-signature": "sig"})
            self.assertEqual(res2.status_code, 200)
            data = res2.json()
            self.assertEqual(data.get("status"), "idempotent_duplicate")
            self.assertEqual(data.get("event_id"), "evt_duplicate_999")

    @patch("core.backend.api.routers.billing.get_async_service_client")
    def test_stripe_webhook_invoice_payment_succeeded(self, mock_get_service_client):
        mock_supabase = MagicMock()
        mock_get_service_client.return_value = mock_supabase
        
        mock_ws_res = MagicMock()
        mock_ws_res.data = [{"id": "ws_sub_1", "status": "active"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws_res

        event_payload = {
            "id": "evt_invoice_1",
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_1",
                    "subscription": "sub_1",
                    "customer_email": "test@example.com",
                    "lines": {
                        "data": [{"metadata": {"workspace_id": "ws_sub_1", "package_id": "growth_tier"}}]
                    }
                }
            }
        }

        with patch("core.backend.api.routers.billing.verify_stripe_signature", return_value=True):
            response = self.client.post("/webhook/stripe", json=event_payload, headers={"stripe-signature": "sig"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("status"), "ok")

    @patch("core.backend.api.routers.billing.get_async_service_client")
    def test_stripe_webhook_subscription_deleted_downgrades_to_free(self, mock_get_service_client):
        mock_supabase = MagicMock()
        mock_get_service_client.return_value = mock_supabase
        
        event_payload = {
            "id": "evt_sub_del_1",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_1",
                    "metadata": {"workspace_id": "ws_downgrade_1"}
                }
            }
        }

        with patch("core.backend.api.routers.billing.verify_stripe_signature", return_value=True):
            response = self.client.post("/webhook/stripe", json=event_payload, headers={"stripe-signature": "sig"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("status"), "ok")

    @patch("core.backend.api.routers.billing.get_async_service_client")
    def test_stripe_webhook_invalid_workspace_rejected(self, mock_get_service_client):
        mock_supabase = MagicMock()
        mock_get_service_client.return_value = mock_supabase
        
        # Workspace not found in DB
        mock_ws_res = MagicMock()
        mock_ws_res.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws_res

        event_payload = {
            "id": "evt_bad_ws",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_bad",
                    "client_reference_id": "ws_nonexistent",
                    "metadata": {"package_id": "credits_1000"}
                }
            }
        }

        with patch("core.backend.api.routers.billing.verify_stripe_signature", return_value=True):
            response = self.client.post("/webhook/stripe", json=event_payload, headers={"stripe-signature": "sig"})
            self.assertEqual(response.status_code, 400)

    def test_calculate_proration_credit_safe_division_and_bounds(self):
        # Normal proration: 1000 credits, 15 days remaining out of 30 days = 500
        self.assertEqual(calculate_proration_credit(1000, 15, 30), 500)
        
        # Zero total days safety guard (total_days = 0 should default/clamp to 1 without zero division error)
        self.assertEqual(calculate_proration_credit(1000, 15, 0), 1000)
        
        # Upper bound clamping (<= 60,000)
        self.assertEqual(calculate_proration_credit(100000, 30, 30), 60000)
        
        # Lower bound clamping (>= 0)
        self.assertEqual(calculate_proration_credit(-500, 10, 30), 0)

    def test_stripe_webhook_signature_failure_rejected(self):
        event_payload = {"id": "evt_sig_fail", "type": "checkout.session.completed"}
        with patch("core.backend.api.routers.billing.os.environ", {"STRIPE_WEBHOOK_SECRET": "whsec_secret"}):
            with patch("core.backend.api.routers.billing.verify_stripe_signature", return_value=False):
                response = self.client.post("/webhook/stripe", json=event_payload, headers={"stripe-signature": "invalid_sig"})
                self.assertEqual(response.status_code, 400)
