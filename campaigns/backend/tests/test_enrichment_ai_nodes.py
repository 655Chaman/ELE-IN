import unittest
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from integrations.backend.services.email_verifier import EmailVerifier


class TestEnrichmentAndAINodes(unittest.TestCase):
    """
    Unit test suite for Data Enrichment and AI Intelligence nodes.
    Built under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.mock_supabase,
            workspace_id="test-workspace-enrich-123"
        )
        self.executor._get_unified_brain = MagicMock(return_value={
            "personas": [],
            "target_customer_profile": "B2B SaaS founders",
            "core_value_prop": "Automated pipeline",
            "primary_pain_points_solved": ["manual prospecting"]
        })

    # ══════════════════════════════════════════════════════════════════════════
    # AI SCORE ICP FIT
    # ══════════════════════════════════════════════════════════════════════════

    @patch("knowledge.backend.services.elein_ai_service.score_icp_fit")
    def test_ai_score_icp_high_fit_branch(self, mock_score):
        """Layer 0: Score > 75 routes to 'High fit (>75)'"""
        mock_score.return_value = 85
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "lead_profile": {"title": "VP of Engineering"}
        }
        res = self.executor.handle_ai_score_icp(data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.HIGH_FIT.value)
        self.assertEqual(res["variables"]["icp_score"], 85)

    @patch("knowledge.backend.services.elein_ai_service.score_icp_fit")
    def test_ai_score_icp_medium_fit_branch(self, mock_score):
        """Layer 0: Score 50-75 routes to 'Medium fit (50-75)'"""
        mock_score.return_value = 65
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "lead_profile": {"title": "Engineering Manager"}
        }
        res = self.executor.handle_ai_score_icp(data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.MEDIUM_FIT.value)
        self.assertEqual(res["variables"]["icp_score"], 65)

    @patch("knowledge.backend.services.elein_ai_service.score_icp_fit")
    def test_ai_score_icp_low_fit_branch(self, mock_score):
        """Layer 0: Score < 50 routes to 'Low fit (<50)'"""
        mock_score.return_value = 30
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "lead_profile": {"title": "Intern"}
        }
        res = self.executor.handle_ai_score_icp(data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.LOW_FIT.value)
        self.assertEqual(res["variables"]["icp_score"], 30)

    @patch("knowledge.backend.services.elein_ai_service.score_icp_fit")
    def test_ai_score_icp_fallback_on_llm_failure(self, mock_score):
        """Layer 1 Paranoia: If LLM returns None or fails, falls back safely to 50 (Medium fit)"""
        mock_score.return_value = None
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "lead_profile": {}
        }
        res = self.executor.handle_ai_score_icp(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.MEDIUM_FIT.value)
        self.assertEqual(res["variables"]["icp_score"], 50)

    # ══════════════════════════════════════════════════════════════════════════
    # AI BUYING SIGNAL
    # ══════════════════════════════════════════════════════════════════════════

    @patch("knowledge.backend.services.elein_ai_service.detect_buying_signal")
    def test_ai_detect_buying_signal_detected(self, mock_signal):
        """Layer 0: Positive signal routes to 'Signal detected'"""
        mock_signal.return_value = "Yes"
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "lead_profile": {"summary": "We are hiring 10 SDRs this quarter"}
        }
        res = self.executor.handle_ai_detect_buying_signal(data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.SIGNAL_DETECTED.value)
        self.assertTrue(res["signal_detected"])

    @patch("knowledge.backend.services.elein_ai_service.detect_buying_signal")
    def test_ai_detect_buying_signal_no_signal_or_fallback(self, mock_signal):
        """Layer 1 & 2 Paranoia: Negative signal or unexpected string routes to 'No signal'"""
        mock_signal.return_value = "No"
        data = {"workspace_id": "test-workspace-enrich-123"}
        res = self.executor.handle_ai_detect_buying_signal(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.NO_SIGNAL.value)
        self.assertFalse(res["signal_detected"])

    # ══════════════════════════════════════════════════════════════════════════
    # AI SUMMARIZE PROFILE
    # ══════════════════════════════════════════════════════════════════════════

    @patch("knowledge.backend.services.elein_ai_service.summarize_profile")
    def test_ai_summarize_profile(self, mock_sum):
        """Layer 0: Summarizes profile and returns Branch.THEN.value"""
        mock_sum.return_value = "Veteran SaaS CTO with 15+ years scaling B2B infra."
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "lead_profile": {"title": "CTO"}
        }
        res = self.executor.handle_ai_summarize_profile(data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertIn("Veteran SaaS CTO", res["variables"]["profile_summary"])

    # ══════════════════════════════════════════════════════════════════════════
    # AI DETECT COMPETITOR
    # ══════════════════════════════════════════════════════════════════════════

    @patch("knowledge.backend.services.elein_ai_service.detect_competitor")
    def test_ai_detect_competitor_using_competitor(self, mock_det):
        """Layer 0: When competitor is detected, returns 'Using competitor'"""
        mock_det.return_value = True
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "competitors": "Lemlist, Apollo",
            "lead_profile": {"summary": "Using Lemlist currently"}
        }
        res = self.executor.handle_ai_detect_competitor(data, "https://linkedin.com/in/test")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "Using competitor")
        self.assertTrue(res["competitor_detected"])

    @patch("knowledge.backend.services.elein_ai_service.detect_competitor")
    def test_ai_detect_competitor_not_detected(self, mock_det):
        """Layer 0: When competitor is not detected, returns 'Not detected'"""
        mock_det.return_value = False
        data = {
            "workspace_id": "test-workspace-enrich-123",
            "competitors": ["Outreach"],
            "lead_profile": {}
        }
        res = self.executor.handle_ai_detect_competitor(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "Not detected")
        self.assertFalse(res["competitor_detected"])

    # ══════════════════════════════════════════════════════════════════════════
    # AI BEST SEND TIME
    # ══════════════════════════════════════════════════════════════════════════

    @patch("knowledge.backend.services.elein_ai_service.predict_best_send_time")
    def test_ai_best_send_time(self, mock_time):
        """Layer 0: Predicts best send time and returns Branch.THEN.value"""
        mock_time.return_value = "09:30 AM"
        data = {"workspace_id": "test-workspace-enrich-123"}
        res = self.executor.handle_ai_best_send_time(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertEqual(res["variables"]["best_send_time"], "09:30 AM")

    # ══════════════════════════════════════════════════════════════════════════
    # ENRICHMENT (FIND EMAIL, PERSONAL EMAIL, APOLLO ENRICH)
    # ══════════════════════════════════════════════════════════════════════════

    @patch("core.backend.services.credit_service.check_tier_access", return_value=True)
    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email")
    def test_find_email_success(self, mock_disc, mock_tier):
        """Layer 0: Successfully finds email via discovery and branches to 'Found'"""
        mock_disc.return_value = "john.doe@acme.com"
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}

        data = {
            "first_name": "John",
            "last_name": "Doe",
            "domain": "acme.com"
        }
        res = self.executor.handle_find_email(data, "https://linkedin.com/in/johndoe")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.FOUND.value)
        self.assertEqual(res["variables"]["email"], "john.doe@acme.com")

    @patch("core.backend.services.credit_service.check_tier_access", return_value=True)
    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email")
    def test_find_email_not_found(self, mock_disc, mock_tier):
        """Layer 0: Returns 'Not found' when email discovery yields nothing"""
        mock_disc.return_value = None
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}

        data = {
            "first_name": "Ghost",
            "last_name": "User",
            "domain": "nowhere.xyz"
        }
        res = self.executor.handle_find_email(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.NOT_FOUND.value)

    @patch("core.backend.services.credit_service.check_tier_access", return_value=True)
    def test_apollo_enrich_alias(self, mock_tier):
        """Layer 0: handle_apollo_enrich aliases _handle_enrichment correctly"""
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}
        data = {"email": "apollo.enriched@lead.com"}
        res = self.executor.handle_apollo_enrich(data, "https://linkedin.com/in/lead")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.FOUND.value)
        self.assertEqual(res["email"], "apollo.enriched@lead.com")

    # ══════════════════════════════════════════════════════════════════════════
    # EMAIL VERIFICATION
    # ══════════════════════════════════════════════════════════════════════════

    @patch("integrations.backend.services.email_verifier.EmailVerifier.verify_email")
    def test_verify_email_valid(self, mock_ver):
        """Layer 0: Valid email returns branch 'Valid'"""
        mock_ver.return_value = True
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}

        data = {"email": "verified@company.com"}
        res = self.executor.handle_verify_email(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "Valid")
        self.assertTrue(res["is_valid"])

    @patch("integrations.backend.services.email_verifier.EmailVerifier.verify_email")
    def test_verify_email_invalid_or_risky(self, mock_ver):
        """Layer 0: Bouncing/risky email returns branch 'Invalid / Risky'"""
        mock_ver.return_value = False
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}

        data = {"email": "bouncing@bad-domain.com"}
        res = self.executor.handle_verify_email(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "Invalid / Risky")
        self.assertFalse(res["is_valid"])

    def test_verify_email_syntax_and_missing_guards(self):
        """Layer 2 Paranoia: Missing or malformed email returns 'Invalid / Risky' without crashing"""
        data = {"email": "not-an-email"}
        res = self.executor.handle_verify_email(data, None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "Invalid / Risky")
        self.assertFalse(res["is_valid"])

        # Completely empty data
        res_empty = self.executor.handle_verify_email({}, None)
        self.assertEqual(res_empty["status"], "success")
        self.assertEqual(res_empty["branch"], "Invalid / Risky")
        self.assertFalse(res_empty["is_valid"])


if __name__ == "__main__":
    unittest.main()
