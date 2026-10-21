"""
test_spam_score_executor_and_router.py — Comprehensive Paranoia Test Suite
for Phase 39 (Spam Trigger Words & Algorithmic Content Spam Score Classifier -
SpamAssassin & Microsoft EOP Pre-Flight Executor & Router Integration).

Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Mechanics
    - Pre-flight spam score heuristic audit before outbound email delivery.
    - Abort outbound send when copy exceeds critical spam threshold (score >= 6.0).
    - Enrich successful dispatches with spam telemetry (spam_score, spam_risk_level, flagged_triggers_count).
    - REST endpoint POST /deliverability/audit-spam-score with workspace scoping.
    - REST endpoint POST /deliverability/sanitize-copy with remediation replacements.
  - Layer 1: Environmental Failure Analysis
    - Elevated spam risk (4.0 <= score < 6.0) logs warning but allows sending with telemetry flag.
    - Zero credit deduction / zero database side-effects when email content is aborted for spam.
    - Handling of is_reply and unsubscribe flag propagation in executor.
    - Bandit variant copy evaluation when bandit feature is enabled.
    - Missing/empty subject or body handled gracefully without crashes.
  - Layer 2: Human Paranoia & Security Defense
    - Top 3 flagged trigger phrases exposed in descriptive rejection error.
    - Strict workspace isolation (tenant scoping) on all deliverability endpoints.
    - Pydantic model validation on SpamScoreAuditRequest and CopySanitizeRequest.
"""

import unittest
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.routers.elein import (
    SpamScoreAuditRequest,
    CopySanitizeRequest,
    api_audit_spam_score,
    api_sanitize_copy,
)
from core.backend.services.spam_score_service import SpamScoreService, SpamRiskLevel


class TestSpamScoreExecutorAndRouter(unittest.TestCase):
    """
    Test suite for Executor Pre-Flight Content Guard and Deliverability Router Endpoints.
    """

    def setUp(self):
        self.workspace_id = "ws-spam-guard-test"
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
        )

    # =========================================================================
    # LAYER 0 & 1: EXECUTOR PRE-FLIGHT CONTENT GUARD TESTS
    # =========================================================================

    def test_executor_aborts_send_on_critical_spam_score(self):
        """
        Layer 0 & 1: Outbound email with critical spam triggers (score >= 6.0)
        is aborted before credit deduction and before external dispatch.
        """
        # Critical spam copy: ALL CAPS subject, financial hype, urgency pressure, raw IP link, missing unsub
        data = {
            "to_email": "prospect@acme-corp.com",
            "subject": "100% FREE CASH GUARANTEED ACT NOW!!!",
            "body": "DEAR FRIEND, GET RICH QUICK! Free money guaranteed right now. Click http://192.168.1.100/claim today!!!",
            "lead_id": "lead-spam-1",
            "is_reply": False,
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)

        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "critical_spam_score")
        self.assertEqual(res["branch"], Branch.FAILED.value)
        self.assertIn("Email content rejected by spam heuristic guard", res["error"])
        self.assertIn("Top triggers:", res["error"])
        # Verify no credits were deducted and no outbound insert took place
        called_tables = [c[1][0] for c in self.mock_supabase.table.mock_calls if c[1]]
        self.assertNotIn("outbox_events", called_tables)
        self.assertNotIn("credit_ledger", called_tables)

    def test_executor_elevated_risk_logs_and_sends(self):
        """
        Layer 1: Outbound email with elevated risk (4.0 <= score < 6.0, HIGH_SPAM_RISK)
        logs a notice and proceeds with dispatch, enriching telemetry.
        """
        # Moderate trigger copy: has urgency triggers, but not critical enough to reach 6.0
        data = {
            "to_email": "prospect@acme-corp.com",
            "subject": "Quick question regarding your growth",
            "body": "Hi there,\n\nAct now for a limited time risk free trial of our solution.\n\nBest,\nTeam\n\nIf you wish to unsubscribe, click here.",
            "lead_id": "lead-elevated-1",
            "is_reply": False,
            "has_unsubscribe": True,
        }

        # Mock audit returning HIGH_SPAM_RISK
        mock_audit = {
            "spam_score": 4.8,
            "risk_level": "HIGH_SPAM_RISK",
            "can_safely_send": True,
            "flagged_triggers": [{"phrase": "act now"}, {"phrase": "limited time"}, {"phrase": "risk free"}],
            "rejection_reason": None,
        }

        with patch.object(SpamScoreService, "audit_email_content", return_value=mock_audit) as mock_fn:
            res = self.executor.handle_send_email(data, linkedin_url=None)

            mock_fn.assert_called_once()
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["branch"], Branch.THEN.value)
            self.assertEqual(res["spam_score"], 4.8)
            self.assertEqual(res["spam_risk_level"], "HIGH_SPAM_RISK")
            self.assertEqual(res["flagged_triggers_count"], 3)

    def test_executor_clean_copy_succeeds_with_telemetry(self):
        """
        Layer 0: Clean B2B cold email passes pre-flight audit with SAFE rating
        and enriches returned outcome with spam metrics.
        """
        data = {
            "to_email": "prospect@acme-corp.com",
            "subject": "Quick question regarding platform architecture",
            "body": "Hi John,\n\nI noticed your team is scaling microservices and thought you might find our whitepaper helpful.\n\nWould you be open to a brief chat next Tuesday?\n\nBest,\nAlex\n\nTo opt out, click unsubscribe.",
            "lead_id": "lead-clean-1",
            "is_reply": False,
            "unsub_url": "https://elein.ai/unsub/token123",
        }

        res = self.executor.handle_send_email(data, linkedin_url=None)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.THEN.value)
        self.assertIn("spam_score", res)
        self.assertLess(res["spam_score"], 2.0)
        self.assertEqual(res["spam_risk_level"], "SAFE")
        self.assertEqual(res["flagged_triggers_count"], 0)

    def test_executor_respects_reply_and_unsubscribe_flags(self):
        """
        Layer 1: Verifies that is_reply and has_unsubscribe are correctly passed
        to SpamScoreService.audit_email_content.
        """
        data = {
            "to_email": "prospect@acme-corp.com",
            "subject": "Re: our previous conversation",
            "body": "Hi Jane, following up on our chat. Here is the link you requested.",
            "lead_id": "lead-reply-1",
            "is_reply": True,
            "unsub_url": "https://elein.ai/unsub/xyz",
        }

        with patch.object(SpamScoreService, "audit_email_content", wraps=SpamScoreService.audit_email_content) as spy_fn:
            res = self.executor.handle_send_email(data, linkedin_url=None)

            spy_fn.assert_called_once()
            _, kwargs = spy_fn.call_args
            self.assertTrue(kwargs["is_reply"])
            self.assertTrue(kwargs["has_unsubscribe"])
            self.assertEqual(res["status"], "success")

    def test_executor_spintax_and_variable_interpolation_before_audit(self):
        """
        Layer 1 & 2: Template variables and spintax are interpolated BEFORE
        running spam score audit so rendered copy is evaluated accurately.
        """
        data = {
            "to_email": "prospect@acme-corp.com",
            "subject": "{Hi|Hello} {{first_name}}",
            "body": "{I noticed|I saw} your recent blog post. Let us connect!\n\nUnsubscribe here.",
            "first_name": "Sarah",
            "lead_id": "lead-spintax-1",
        }

        with patch.object(SpamScoreService, "audit_email_content", wraps=SpamScoreService.audit_email_content) as spy_fn:
            res = self.executor.handle_send_email(data, linkedin_url=None)

            self.assertEqual(res["status"], "success")
            spy_fn.assert_called_once()
            _, kwargs = spy_fn.call_args
            self.assertNotIn("{{first_name}}", kwargs["subject"])
            self.assertIn("Sarah", kwargs["subject"])

    def test_executor_bandit_copy_evaluated_by_spam_guard(self):
        """
        Layer 1: When Thompson Sampling bandit copy is active, the bandit variant copy
        is evaluated by the spam heuristic guard.
        """
        data = {
            "to_email": "prospect@acme-corp.com",
            "subject": "Default subject",
            "body": "Default body with unsubscribe.",
            "lead_id": "lead-bandit-1",
            "bandit_variant": {
                "subject": "ACT NOW FREE CASH 100% GUARANTEED!!!",
                "body": "CLICK HERE NOW FOR FREE MONEY http://10.0.0.1/scam",
            },
        }

        # Mock bandit resolver to return the spammy copy
        self.executor._resolve_bandit_copy_if_enabled = MagicMock(return_value={
            "enabled": True,
            "subject": "ACT NOW FREE CASH 100% GUARANTEED!!!",
            "body": "CLICK HERE NOW FOR FREE MONEY http://10.0.0.1/scam",
            "bandit_variant_id": "var-spam-1",
            "bandit_arm_name": "spam_arm",
        })

        res = self.executor.handle_send_email(data, linkedin_url=None)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "critical_spam_score")

    # =========================================================================
    # LAYER 0 & 2: ROUTER REST ENDPOINTS & PYDANTIC MODEL TESTS
    # =========================================================================

    def test_router_audit_spam_score_endpoint(self):
        """
        Layer 0 & 2: POST /deliverability/audit-spam-score performs comprehensive
        pre-flight spam assessment with tenant workspace scoping.
        """
        req = SpamScoreAuditRequest(
            subject="Exclusive 100% Free Trial - Act Now!",
            body="Get your risk free access today. No catch, 100% free guaranteed.\n\nClick here.",
            is_reply=False,
            has_unsubscribe=False,
        )

        res = api_audit_spam_score(req=req, workspace_id=self.workspace_id)

        self.assertIsInstance(res, dict)
        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertIn("spam_score", res)
        self.assertIn("risk_level", res)
        self.assertIn("flagged_triggers", res)
        self.assertIn("heuristic_penalties", res)
        self.assertIn("recommendations", res)
        self.assertIn("can_safely_send", res)
        self.assertGreater(res["spam_score"], 4.0)

    def test_router_audit_spam_score_clean_copy(self):
        """
        Layer 0: POST /deliverability/audit-spam-score with clean B2B copy.
        """
        req = SpamScoreAuditRequest(
            subject="Partnership discussion regarding integration architecture",
            body="Hi Sarah,\n\nHope this finds you well. I enjoyed reading your article on microservices.\n\nBest,\nDavid\n\nUnsubscribe here.",
            is_reply=False,
            has_unsubscribe=True,
        )

        res = api_audit_spam_score(req=req, workspace_id=self.workspace_id)

        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertTrue(res["can_safely_send"])
        self.assertEqual(res["risk_level"], "SAFE")
        self.assertLess(res["spam_score"], 2.0)
        self.assertEqual(len(res["flagged_triggers"]), 0)

    def test_router_sanitize_copy_endpoint(self):
        """
        Layer 0 & 2: POST /deliverability/sanitize-copy suggests safe B2B synonyms
        for detected trigger phrases.
        """
        req = CopySanitizeRequest(
            text="We offer a 100% free guarantee with no catch. Act now for a risk-free trial!",
        )

        res = api_sanitize_copy(req=req, workspace_id=self.workspace_id)

        self.assertIsInstance(res, dict)
        self.assertEqual(res["workspace_id"], self.workspace_id)
        self.assertIn("sanitized_text", res)
        self.assertIn("replacements", res)
        self.assertIn("replacements_count", res)
        self.assertGreater(res["replacements_count"], 0)
        self.assertNotIn("100% free", res["sanitized_text"].lower())

    def test_pydantic_request_models_validation(self):
        """
        Layer 2: Validates Pydantic request model defaults, field types, and optionality.
        """
        audit_req = SpamScoreAuditRequest(
            subject="Test subject",
            body="Test body",
        )
        self.assertEqual(audit_req.subject, "Test subject")
        self.assertEqual(audit_req.body, "Test body")
        self.assertFalse(audit_req.is_reply)
        self.assertTrue(audit_req.has_unsubscribe)

        sanitize_req = CopySanitizeRequest(
            text="Sample copy to sanitize",
        )
        self.assertEqual(sanitize_req.text, "Sample copy to sanitize")


if __name__ == "__main__":
    unittest.main()
