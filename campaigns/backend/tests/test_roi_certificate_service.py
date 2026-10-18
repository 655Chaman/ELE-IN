"""
test_roi_certificate_service.py — Test Suite for Viral Campaign Performance Card & ROI Certificate Engine
Rigorously tests Layer 0 (Foundational), Layer 1 (Environmental Resilience), and Layer 2 (Human Paranoia).
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient

from campaigns.backend.services.roi_certificate_service import (
    calculate_campaign_metrics,
    compute_badge_tier,
    generate_verification_token,
    sign_certificate_payload,
    verify_certificate_signature,
    mask_text_token,
    mask_full_name,
    mask_company_name,
    mask_email_address,
    generate_viral_social_copy,
    mint_campaign_roi_certificate,
    get_campaign_roi_certificate,
    update_certificate_privacy_settings,
    verify_public_certificate_token,
    format_metrics_for_presentation,
    TIER_DIAMOND,
    TIER_PLATINUM,
    TIER_GOLD,
    TIER_SILVER
)
from core.backend.main import app


class TestROICertificateService(unittest.TestCase):
    """
    Test suite for Campaign ROI Achievement Certificates & Performance Cards.
    Follows the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.workspace_id = str(uuid.uuid4())
        self.campaign_id = str(uuid.uuid4())

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 0: Foundational Layer Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_compute_badge_tiers(self):
        """Layer 0: Verifies correct tier assignment according to outbound conversion thresholds."""
        # Diamond: High acceptance or high replies or high meetings
        self.assertEqual(compute_badge_tier(acceptance_rate=42.0, reply_rate=10.0, meetings_booked=1), TIER_DIAMOND)
        self.assertEqual(compute_badge_tier(acceptance_rate=15.0, reply_rate=23.0, meetings_booked=1), TIER_DIAMOND)
        self.assertEqual(compute_badge_tier(acceptance_rate=15.0, reply_rate=10.0, meetings_booked=14), TIER_DIAMOND)

        # Platinum
        self.assertEqual(compute_badge_tier(acceptance_rate=32.0, reply_rate=5.0, meetings_booked=1), TIER_PLATINUM)
        self.assertEqual(compute_badge_tier(acceptance_rate=15.0, reply_rate=16.0, meetings_booked=1), TIER_PLATINUM)
        self.assertEqual(compute_badge_tier(acceptance_rate=15.0, reply_rate=5.0, meetings_booked=7), TIER_PLATINUM)

        # Gold
        self.assertEqual(compute_badge_tier(acceptance_rate=22.0, reply_rate=4.0, meetings_booked=0), TIER_GOLD)
        self.assertEqual(compute_badge_tier(acceptance_rate=12.0, reply_rate=9.0, meetings_booked=0), TIER_GOLD)
        self.assertEqual(compute_badge_tier(acceptance_rate=12.0, reply_rate=4.0, meetings_booked=3), TIER_GOLD)

        # Silver
        self.assertEqual(compute_badge_tier(acceptance_rate=10.0, reply_rate=3.0, meetings_booked=0), TIER_SILVER)

    def test_verification_token_format(self):
        """Layer 0: Verifies verification token matches ELEIN-CERT-XXXX-XXXX uppercase alphanumeric format."""
        token = generate_verification_token()
        self.assertTrue(token.startswith("ELEIN-CERT-"))
        parts = token.split("-")
        self.assertEqual(len(parts), 4)
        self.assertEqual(len(parts[2]), 4)
        self.assertEqual(len(parts[3]), 4)
        self.assertTrue(parts[2].isalnum())
        self.assertTrue(parts[3].isalnum())

    def test_hmac_signature_generation_and_verification(self):
        """Layer 0 & Layer 2: Verifies HMAC-SHA256 signature generation and exact verification."""
        token = "ELEIN-CERT-A1B2-C3D4"
        metrics = {
            "enrolled_leads": 150,
            "acceptance_rate": 38.5,
            "reply_rate": 21.0,
            "meetings_booked": 9,
            "sdr_hours_saved": 42.5
        }
        sig = sign_certificate_payload(token, self.campaign_id, self.workspace_id, TIER_PLATINUM, metrics)
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 64)  # SHA-256 hex length

        # Signature must verify successfully
        valid = verify_certificate_signature(token, self.campaign_id, self.workspace_id, TIER_PLATINUM, metrics, sig)
        self.assertTrue(valid)

    def test_sdr_hours_saved_and_pipeline_value_calculation(self):
        """Layer 0: Validates manual SDR hours saved math and pipeline values."""
        mock_supabase = MagicMock()
        mock_camp_res = MagicMock()
        mock_camp_res.data = [{"id": self.campaign_id, "name": "Enterprise FinTech Outreach", "status": "ACTIVE"}]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_camp_res

        mock_leads_res = MagicMock()
        mock_leads_res.data = [{"id": str(i)} for i in range(100)]
        
        # Setup mock executions
        mock_execs_res = MagicMock()
        mock_execs_res.data = (
            [{"node_type": "linkedin_connection", "status": "completed"} for _ in range(80)] +
            [{"node_type": "linkedin_message", "status": "completed"} for _ in range(40)] +
            [{"node_type": "check_reply", "status": "replied"} for _ in range(15)] +
            [{"node_type": "meeting_tracker", "status": "booked"} for _ in range(5)]
        )

        def table_router(table_name):
            t_mock = MagicMock()
            if table_name == "campaigns":
                t_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_camp_res
            elif table_name == "campaign_leads":
                t_mock.select.return_value.eq.return_value.execute.return_value = mock_leads_res
            elif table_name == "campaign_node_executions":
                t_mock.select.return_value.eq.return_value.execute.return_value = mock_execs_res
            else:
                empty = MagicMock()
                empty.data = []
                t_mock.select.return_value.eq.return_value.execute.return_value = empty
            return t_mock

        mock_supabase.table.side_effect = table_router

        metrics = calculate_campaign_metrics(
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            supabase=mock_supabase,
            custom_deal_size=3000.0
        )

        self.assertEqual(metrics["enrolled_leads"], 100)
        self.assertEqual(metrics["connections_sent"], 80)
        self.assertEqual(metrics["connections_accepted"], 80)
        self.assertEqual(metrics["acceptance_rate"], 100.0)
        self.assertEqual(metrics["meetings_booked"], 5)
        # Expected hours: (100*3.5 + 80*2.0 + 40*4.0 + 15*6.0) / 60 = (350 + 160 + 160 + 90) / 60 = 760 / 60 = 12.66 -> 12.7 hrs
        self.assertEqual(metrics["sdr_hours_saved"], 12.7)
        self.assertEqual(metrics["pipeline_value_usd"], 15000.0)
        self.assertEqual(metrics["account_safety_score"], 100.0)

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 1: Environmental Failure Analysis Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_zero_division_guard(self):
        """Layer 1: Ensures 0 sent, 0 accepted, 0 enrolled never throws ZeroDivisionError."""
        mock_supabase = MagicMock()
        mock_camp_res = MagicMock()
        mock_camp_res.data = [{"id": self.campaign_id, "name": "Zero Outreach Campaign", "status": "DRAFT"}]
        mock_supabase.table().select().eq().eq().execute.return_value = mock_camp_res

        # All empty
        empty = MagicMock()
        empty.data = []
        mock_supabase.table().select().eq().return_value.execute.return_value = empty

        # Should not throw zero-division error, should provide safe preview baseline
        metrics = calculate_campaign_metrics(self.campaign_id, self.workspace_id, mock_supabase)
        self.assertGreater(metrics["acceptance_rate"], 0.0)
        self.assertGreater(metrics["sdr_hours_saved"], 0.0)
        self.assertEqual(metrics["account_safety_score"], 100.0)

    def test_campaign_not_found_raises_404(self):
        """Layer 1: Fails closed with 404 when campaign does not exist in workspace."""
        mock_supabase = MagicMock()
        empty = MagicMock()
        empty.data = []
        mock_supabase.table().select().eq().eq().execute.return_value = empty

        with self.assertRaises(HTTPException) as ctx:
            calculate_campaign_metrics("non-existent-id", self.workspace_id, mock_supabase)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_malformed_token_rejection(self):
        """Layer 1: Rejects malformed verification tokens before hitting database."""
        mock_supabase = MagicMock()
        # Invalid format
        with self.assertRaises(HTTPException) as ctx:
            verify_public_certificate_token("INVALID_TOKEN", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 400)

        # Empty token
        with self.assertRaises(HTTPException) as ctx:
            verify_public_certificate_token("", mock_supabase)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_expired_certificate_handling(self):
        """Layer 1: Detects expired certificates and flags is_expired=True, is_verified=False."""
        mock_supabase = MagicMock()
        token = "ELEIN-CERT-9999-AAAA"
        past_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        metrics = {"enrolled_leads": 100, "acceptance_rate": 35.0, "reply_rate": 15.0, "meetings_booked": 4, "sdr_hours_saved": 20.0}
        sig = sign_certificate_payload(token, self.campaign_id, self.workspace_id, TIER_PLATINUM, metrics)

        mock_res = MagicMock()
        mock_res.data = [{
            "verification_token": token,
            "campaign_id": self.campaign_id,
            "workspace_id": self.workspace_id,
            "badge_tier": TIER_PLATINUM,
            "issuer_signature": sig,
            "metrics_payload": metrics,
            "is_public": True,
            "mask_pii": True,
            "issued_at": (datetime.now(timezone.utc) - timedelta(days=375)).isoformat(),
            "expires_at": past_date
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_res

        result = verify_public_certificate_token(token, mock_supabase)
        self.assertTrue(result["is_expired"])
        self.assertFalse(result["is_verified"])

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 2: Human Paranoia & Security Tests
    # ─────────────────────────────────────────────────────────────────────────

    def test_pii_masking_algorithm(self):
        """Layer 2: Rigorously verifies masking for names, companies, and email addresses."""
        # Single token
        self.assertEqual(mask_text_token("Sarah"), "S****")
        self.assertEqual(mask_text_token("A"), "A")
        self.assertEqual(mask_text_token(""), "")

        # Full names
        self.assertEqual(mask_full_name("Sarah Jenkins"), "S**** J******")
        self.assertEqual(mask_full_name("David Lee Chen"), "D**** L** C***")
        self.assertEqual(mask_full_name(None), "P******* L***")

        # Companies
        self.assertEqual(mask_company_name("Stripe Technologies"), "S***** T***********")
        self.assertEqual(mask_company_name("Google"), "G*****")
        self.assertEqual(mask_company_name(None), "E********* C***")

        # Emails
        self.assertEqual(mask_email_address("sarah.jenkins@stripe.com"), "s***@s*****.com")
        self.assertEqual(mask_email_address("alex@databricks.io"), "a***@d*********.io")
        self.assertEqual(mask_email_address("invalid-email"), "p****@c******.com")

    def test_tamper_detection(self):
        """Layer 2: Detects any unauthorized modification to certificate payload numbers."""
        token = "ELEIN-CERT-B2C3-D4E5"
        real_metrics = {
            "enrolled_leads": 100,
            "acceptance_rate": 25.0,
            "reply_rate": 10.0,
            "meetings_booked": 3,
            "sdr_hours_saved": 15.0
        }
        sig = sign_certificate_payload(token, self.campaign_id, self.workspace_id, TIER_GOLD, real_metrics)

        # Altered metrics (e.g. attacker changes 3 meetings to 30 meetings)
        tampered_metrics = dict(real_metrics)
        tampered_metrics["meetings_booked"] = 30

        is_valid = verify_certificate_signature(
            token=token,
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            badge_tier=TIER_GOLD,
            metrics=tampered_metrics,
            provided_signature=sig
        )
        self.assertFalse(is_valid)

        # Verify public endpoint flags tamper status
        mock_supabase = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{
            "verification_token": token,
            "campaign_id": self.campaign_id,
            "workspace_id": self.workspace_id,
            "badge_tier": TIER_GOLD,
            "issuer_signature": sig,
            "metrics_payload": tampered_metrics,
            "is_public": True,
            "mask_pii": True,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_res

        pub_result = verify_public_certificate_token(token, mock_supabase)
        self.assertFalse(pub_result["is_verified"])
        self.assertEqual(pub_result["tamper_status"], "TAMPERED_OR_CORRUPT")

    def test_private_certificate_access_denial(self):
        """Layer 2: Certificates marked is_public=False are blocked with HTTP 403 on public endpoint."""
        token = "ELEIN-CERT-1122-3344"
        mock_supabase = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{
            "verification_token": token,
            "is_public": False
        }]
        mock_supabase.table().select().eq().execute.return_value = mock_res

        with self.assertRaises(HTTPException) as ctx:
            verify_public_certificate_token(token, mock_supabase)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("marked private", ctx.exception.detail)

    def test_social_share_copy_generation(self):
        """Layer 2: Generates formatted viral sharing copy for LinkedIn, X/Twitter, and Slack."""
        metrics = {
            "campaign_name": "Outbound Engine Q3",
            "acceptance_rate": 41.5,
            "reply_rate": 22.0,
            "meetings_booked": 14,
            "sdr_hours_saved": 65.4,
            "badge_tier": TIER_DIAMOND,
            "tier_title": "Apex Outbound Performer"
        }
        token = "ELEIN-CERT-5555-6666"
        copy = generate_viral_social_copy(metrics, token)

        self.assertIn("41.5%", copy["linkedin"])
        self.assertIn("65.4 hrs", copy["linkedin"])
        self.assertIn("ELEIN-CERT-5555-6666", copy["linkedin"])
        self.assertIn("Apex Outbound Performer", copy["twitter"])
        self.assertIn("ELEIN-CERT-5555-6666", copy["slack"])
        self.assertEqual(copy["verification_url"], "https://app.ele-in.com/verify/ELEIN-CERT-5555-6666")

    # ─────────────────────────────────────────────────────────────────────────
    # Integration Tests with FastAPI TestClient
    # ─────────────────────────────────────────────────────────────────────────

    def test_public_verify_endpoint(self):
        """Integration: Test /api/public/verify-certificate/{token} route."""
        mock_supabase = MagicMock()
        from core.backend.api.auth_dep import get_service_client
        app.dependency_overrides[get_service_client] = lambda: mock_supabase
        try:
            client = TestClient(app)
            # Malformed token test
            resp = client.get("/api/public/verify-certificate/not-a-token")
            self.assertEqual(resp.status_code, 400)

            # Valid token format not found in DB
            empty = MagicMock()
            empty.data = []
            mock_supabase.table().select().eq().execute.return_value = empty
            resp404 = client.get("/api/public/verify-certificate/ELEIN-CERT-1234-5678")
            self.assertEqual(resp404.status_code, 404)
        finally:
            app.dependency_overrides.pop(get_service_client, None)

    def test_export_roi_certificate_csv_with_pii_masking_and_formula_defense(self):
        """Layer 2: Verifies CSV export respects mask_pii and neutralizes spreadsheet formula injection."""
        from campaigns.backend.services.roi_certificate_service import export_roi_certificate_csv, sanitize_csv_field

        self.assertEqual(sanitize_csv_field("=CMD|' /C calc'!A0"), "'=CMD|' /C calc'!A0")
        self.assertEqual(sanitize_csv_field("@EvilCorp"), "'@EvilCorp")

        mock_supabase = MagicMock()
        mock_camp = MagicMock()
        mock_camp.data = [{"id": self.campaign_id, "name": "=DangerousCampaign", "status": "ACTIVE"}]
        mock_leads = MagicMock()
        mock_leads.data = [{"id": "lead-1", "lead_id": "l-1", "name": "Sarah Jenkins", "company": "Stripe Technologies", "title": "VP", "status": "booked"}]

        def table_router(table_name):
            t_mock = MagicMock()
            if table_name == "campaigns":
                t_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_camp
            elif table_name == "campaign_leads":
                t_mock.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = mock_leads
                t_mock.select.return_value.eq.return_value.execute.return_value = mock_leads
            else:
                empty = MagicMock()
                empty.data = []
                t_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = empty
                t_mock.select.return_value.eq.return_value.execute.return_value = empty
            return t_mock

        mock_supabase.table.side_effect = table_router

        csv_masked = export_roi_certificate_csv(
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            supabase=mock_supabase,
            mask_pii=True
        )
        self.assertIn("Verification Token,Badge Tier,Tier Title,Campaign Name", csv_masked)
        self.assertIn("'=DangerousCampaign", csv_masked)
        self.assertIn("S**** J******", csv_masked)

        csv_unmasked = export_roi_certificate_csv(
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            supabase=mock_supabase,
            mask_pii=False
        )
        self.assertIn("Sarah Jenkins", csv_unmasked)


if __name__ == "__main__":
    unittest.main()

