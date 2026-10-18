"""
test_domain_rotation_and_burnout_protection.py — Automated Test Suite for Issue 5
Dynamic Sender Domain & Mailbox Rotation with Burnout Protection in Ele-in.

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
  - Layer 1: Environmental Failure Analysis
  - Layer 2: Human Paranoia & Extreme Edge Cases
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from integrations.backend.services.email_sender_service import (
    extract_root_domain,
    aggregate_domain_metrics,
    evaluate_domain_burnout_tripwire,
    select_rotating_sender_inbox,
    record_inbox_delivery_outcome,
    calculate_warmup_daily_cap,
    is_valid_sender_email,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestDomainRotationAndBurnoutProtection(unittest.TestCase):
    """
    Comprehensive test suite with 35 edge cases across the Three-Layer Logic Architecture.
    """

    def setUp(self):
        self.workspace_id = "ws_issue5_test_primary"
        self.mock_supabase = MagicMock()
        # Default mock RPC for credit deduction & refund
        self.mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER (CORE MECHANICS)
    # =========================================================================

    def test_extract_root_domain(self):
        """
        Layer 0: Validates extract_root_domain with simple domains, subdomains,
        two-part public suffixes, and full email addresses.
        """
        # Simple domains
        self.assertEqual(extract_root_domain("acme.com"), "acme.com")
        self.assertEqual(extract_root_domain("getscale.ai"), "getscale.ai")
        self.assertEqual(extract_root_domain("elein.in"), "elein.in")

        # Subdomains (1-3 levels)
        self.assertEqual(extract_root_domain("outbound.mail.acme.com"), "acme.com")
        self.assertEqual(extract_root_domain("mail.getscale.ai"), "getscale.ai")
        self.assertEqual(extract_root_domain("app.staging.corp.example.org"), "example.org")

        # Two-part public suffixes / ccTLDs
        self.assertEqual(extract_root_domain("sales.acme.co.uk"), "acme.co.uk")
        self.assertEqual(extract_root_domain("mail.agency.com.au"), "agency.com.au")
        self.assertEqual(extract_root_domain("dev.corp.co.nz"), "corp.co.nz")
        self.assertEqual(extract_root_domain("br.empresa.com.br"), "empresa.com.br")
        self.assertEqual(extract_root_domain("support.tokyo.co.jp"), "tokyo.co.jp")

        # Email strings
        self.assertEqual(extract_root_domain("alex@mail.getscale.ai"), "getscale.ai")
        self.assertEqual(extract_root_domain("sarah@outbound.sales.acme.co.uk"), "acme.co.uk")
        self.assertEqual(extract_root_domain("founder@acme.com"), "acme.com")

    def test_extract_root_domain_case_and_whitespace_normalization(self):
        """Layer 0: Normalizes uppercase characters and whitespace cleanly."""
        self.assertEqual(extract_root_domain("  ALEX@MAIL.GETSCALE.AI  "), "getscale.ai")
        self.assertEqual(extract_root_domain("  OutBound.Sales.Acme.CO.UK  "), "acme.co.uk")

    def test_aggregate_domain_metrics_calculation(self):
        """
        Layer 0: Verifies accurate summing of total_sent, total_sent_today, total_bounces,
        total_spam_complaints, aggregate_bounce_rate_pct, and remaining_domain_capacity
        across multiple inboxes sharing the same root domain.
        """
        inboxes = [
            {
                "id": "inb_1",
                "email": "sarah@mail.acme.com",
                "sent_count": 50,
                "sent_today": 30,
                "bounce_count": 1,
                "spam_complaint_count": 0,
                "status": "ACTIVE",
            },
            {
                "id": "inb_2",
                "email": "alex@outbound.acme.com",
                "sent_count": 40,
                "sent_today": 25,
                "bounce_count": 0,
                "spam_complaint_count": 0,
                "status": "ACTIVE",
            },
            {
                "id": "inb_3",
                "email": "team@acme.com",
                "sent_count": 10,
                "sent_today": 5,
                "bounce_count": 0,
                "spam_complaint_count": 0,
                "status": "ACTIVE",
            },
        ]

        metrics = aggregate_domain_metrics(inboxes, domain_daily_cap=150)
        self.assertIn("acme.com", metrics)
        m = metrics["acme.com"]

        self.assertEqual(m["domain"], "acme.com")
        self.assertEqual(m["inbox_count"], 3)
        self.assertEqual(m["active_inbox_count"], 3)
        self.assertEqual(m["total_sent"], 100)
        self.assertEqual(m["total_sent_today"], 60)
        self.assertEqual(m["domain_daily_cap"], 150)
        self.assertEqual(m["remaining_domain_capacity"], 90)  # 150 - 60
        self.assertEqual(m["total_bounces"], 1)
        self.assertEqual(m["total_spam_complaints"], 0)
        self.assertEqual(m["aggregate_bounce_rate_pct"], 1.0)  # (1 / 100) * 100
        self.assertEqual(m["aggregate_spam_rate_pct"], 0.0)
        self.assertEqual(m["domain_burnout_status"], "HEALTHY")

    def test_aggregate_domain_metrics_at_risk_status(self):
        """Layer 0: Domain is marked AT_RISK when bounce rate reaches 2.0% on 15+ sends."""
        inboxes = [
            {"id": "i1", "email": "a@riskydomain.com", "sent_count": 50, "bounce_count": 1, "status": "ACTIVE"},
            {"id": "i2", "email": "b@riskydomain.com", "sent_count": 50, "bounce_count": 1, "status": "ACTIVE"},
        ]
        metrics = aggregate_domain_metrics(inboxes, domain_daily_cap=150)
        m = metrics["riskydomain.com"]
        self.assertEqual(m["total_sent"], 100)
        self.assertEqual(m["aggregate_bounce_rate_pct"], 2.0)
        self.assertEqual(m["domain_burnout_status"], "AT_RISK")

    def test_aggregate_domain_metrics_multiple_distinct_domains(self):
        """Layer 0: Groups distinct domains independently without metric leakage."""
        inboxes = [
            {"id": "i1", "email": "a@acme.com", "sent_count": 10, "sent_today": 5, "bounce_count": 0, "status": "ACTIVE"},
            {"id": "i2", "email": "b@beta.io", "sent_count": 20, "sent_today": 12, "bounce_count": 0, "status": "ACTIVE"},
            {"id": "i3", "email": "c@gamma.co.uk", "sent_count": 30, "sent_today": 15, "bounce_count": 0, "status": "ACTIVE"},
        ]
        metrics = aggregate_domain_metrics(inboxes, domain_daily_cap=100)
        self.assertEqual(len(metrics), 3)
        self.assertIn("acme.com", metrics)
        self.assertIn("beta.io", metrics)
        self.assertIn("gamma.co.uk", metrics)
        self.assertEqual(metrics["acme.com"]["total_sent_today"], 5)
        self.assertEqual(metrics["beta.io"]["total_sent_today"], 12)
        self.assertEqual(metrics["gamma.co.uk"]["total_sent_today"], 15)

    def test_aggregate_domain_metrics_zero_sends_division_safety(self):
        """Layer 0: Validates division by zero safety when total_sent is 0."""
        inboxes = [
            {"id": "i0", "email": "brandnew@freshdomain.com", "sent_count": 0, "sent_today": 0, "bounce_count": 0, "status": "ACTIVE"}
        ]
        metrics = aggregate_domain_metrics(inboxes, domain_daily_cap=100)
        m = metrics["freshdomain.com"]
        self.assertEqual(m["aggregate_bounce_rate_pct"], 0.0)
        self.assertEqual(m["aggregate_spam_rate_pct"], 0.0)
        self.assertEqual(m["remaining_domain_capacity"], 100)
        self.assertEqual(m["domain_burnout_status"], "HEALTHY")

    def test_aggregate_domain_metrics_active_vs_total_inbox_count(self):
        """Layer 0: Distinguishes between all assigned inboxes and active ones."""
        inboxes = [
            {"id": "i1", "email": "rep1@acme.com", "status": "ACTIVE"},
            {"id": "i2", "email": "rep2@acme.com", "status": "QUARANTINED"},
            {"id": "i3", "email": "rep3@acme.com", "status": "PAUSED"},
            {"id": "i4", "email": "rep4@acme.com", "status": "DISCONNECTED"},
        ]
        metrics = aggregate_domain_metrics(inboxes, domain_daily_cap=150)
        m = metrics["acme.com"]
        self.assertEqual(m["inbox_count"], 4)
        self.assertEqual(m["active_inbox_count"], 1)

    def test_domain_balanced_strategy_round_robin(self):
        """
        Layer 0: Validates that DOMAIN_BALANCED rotates across distinct domains
        (e.g. Domain A then Domain B) based on lowest total_sent_today.
        """
        inboxes = [
            # Domain A: total_sent_today = 20
            {"id": "inb_a1", "workspace_id": self.workspace_id, "email": "alex@domain-a.com", "daily_limit": 50, "sent_today": 20, "status": "ACTIVE"},
            # Domain B: total_sent_today = 10
            {"id": "inb_b1", "workspace_id": self.workspace_id, "email": "beth@domain-b.com", "daily_limit": 50, "sent_today": 10, "status": "ACTIVE"},
        ]

        # First dispatch should pick Domain B because it has sent fewer emails today (10 < 20)
        res1 = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res1["selected"])
        self.assertEqual(res1["selected"]["id"], "inb_b1")
        self.assertEqual(res1["sender_domain"], "domain-b.com")
        self.assertEqual(res1["selection_reason"], "DOMAIN_BALANCED_OPTIMAL")

        # Now simulate Domain B sending 15 more emails (total 25 > Domain A's 20)
        inboxes[1]["sent_today"] = 25
        res2 = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res2["selected"])
        self.assertEqual(res2["selected"]["id"], "inb_a1")
        self.assertEqual(res2["sender_domain"], "domain-a.com")

    def test_domain_balanced_strategy_picks_highest_capacity_inbox_within_domain(self):
        """Layer 0: Within chosen domain, selects mailbox with highest remaining headroom."""
        inboxes = [
            # Domain A inbox 1: 50 limit - 20 sent = 30 remaining
            {"id": "inb_a1", "workspace_id": self.workspace_id, "email": "rep1@domain-a.com", "daily_limit": 50, "sent_today": 20, "status": "ACTIVE"},
            # Domain A inbox 2: 50 limit - 5 sent = 45 remaining
            {"id": "inb_a2", "workspace_id": self.workspace_id, "email": "rep2@domain-a.com", "daily_limit": 50, "sent_today": 5, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res["selected"])
        # Should pick inb_a2 due to larger headroom (45 > 30)
        self.assertEqual(res["selected"]["id"], "inb_a2")

    def test_domain_daily_cap_enforcement(self):
        """
        Layer 0: When domain acme.com hits domain_daily_cap (e.g. 150 sends across 3 mailboxes),
        inboxes on acme.com are skipped, selecting an inbox from healthy Domain B.
        """
        inboxes = [
            # Domain A: 3 mailboxes summing to 150 sends today (hits 150 cap)
            {"id": "inb_a1", "workspace_id": self.workspace_id, "email": "m1@acme.com", "daily_limit": 100, "sent_today": 50, "status": "ACTIVE"},
            {"id": "inb_a2", "workspace_id": self.workspace_id, "email": "m2@acme.com", "daily_limit": 100, "sent_today": 50, "status": "ACTIVE"},
            {"id": "inb_a3", "workspace_id": self.workspace_id, "email": "m3@acme.com", "daily_limit": 100, "sent_today": 50, "status": "ACTIVE"},
            # Domain B: Healthy and has capacity
            {"id": "inb_b1", "workspace_id": self.workspace_id, "email": "rep@getscale.ai", "daily_limit": 100, "sent_today": 10, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
            domain_daily_cap=150,
        )

        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_b1")
        self.assertEqual(res["sender_domain"], "getscale.ai")

        # Verify acme.com inboxes were rejected with DOMAIN_DAILY_CAP_EXHAUSTED
        rejected_reasons = [r["reason"] for r in res["pool_summary"]["rejected"] if r.get("domain") == "acme.com"]
        self.assertTrue(all(r == "DOMAIN_DAILY_CAP_EXHAUSTED" for r in rejected_reasons))

    def test_domain_daily_cap_all_domains_exhausted(self):
        """Layer 0: When all domains have hit their daily caps, returns None safely."""
        inboxes = [
            {"id": "i1", "workspace_id": self.workspace_id, "email": "a@acme.com", "daily_limit": 100, "sent_today": 100, "status": "ACTIVE"},
            {"id": "i2", "workspace_id": self.workspace_id, "email": "b@beta.io", "daily_limit": 100, "sent_today": 100, "status": "ACTIVE"},
        ]
        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
            domain_daily_cap=100,
        )
        self.assertIsNone(res["selected"])
        self.assertEqual(res["selection_reason"], "NO_HEALTHY_INBOXES_AVAILABLE")

    def test_domain_balanced_strategy_empty_inbox_pool(self):
        """Layer 0: Empty candidate list returns None gracefully with structured summary."""
        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=[],
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNone(res["selected"])
        self.assertEqual(res["selection_reason"], "NO_HEALTHY_INBOXES_AVAILABLE")
        self.assertEqual(res["pool_summary"]["total_candidates"], 0)

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # =========================================================================

    def test_domain_burnout_tripwire_triggers_quarantine(self):
        """
        Layer 1: When aggregate bounce rate on a domain exceeds threshold (e.g. 4.0% > 3.0% on 100 sends),
        domain burnout tripwire triggers, marking domain BURNOUT_QUARANTINED and rejecting all inboxes.
        """
        inboxes = [
            {"id": "inb_1", "workspace_id": self.workspace_id, "email": "rep1@burned-domain.com", "sent_count": 50, "bounce_count": 2, "sent_today": 5, "status": "ACTIVE"},
            {"id": "inb_2", "workspace_id": self.workspace_id, "email": "rep2@burned-domain.com", "sent_count": 50, "bounce_count": 2, "sent_today": 5, "status": "ACTIVE"},
        ]
        # Total sent = 100, Total bounces = 4 => 4.0% bounce rate >= 3.0% default threshold

        metrics = aggregate_domain_metrics(inboxes)
        d_meta = metrics["burned-domain.com"]
        self.assertEqual(d_meta["domain_burnout_status"], "BURNOUT_QUARANTINED")
        self.assertIsNotNone(d_meta["quarantined_until"])
        self.assertIn("DOMAIN_BOUNCE_RATE_EXCEEDED", d_meta["quarantine_reason"])

        # In pool selection, all inboxes on this domain must be rejected
        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNone(res["selected"])
        self.assertTrue(any(r["reason"] == "DOMAIN_BURNOUT_QUARANTINED" for r in res["pool_summary"]["rejected"]))

    def test_domain_burnout_spam_complaint_tripwire(self):
        """Layer 1: Domain trips burnout when aggregate spam complaint rate >= 0.1%."""
        tripwire = evaluate_domain_burnout_tripwire({
            "domain": "badspam.com",
            "total_sent": 500,
            "total_bounces": 0,
            "total_spam_complaints": 1,  # 1 complaint on 500 sends = 0.2% >= 0.1%
            "aggregate_bounce_rate_pct": 0.0,
            "aggregate_spam_rate_pct": 0.2,
            "inbox_count": 2,
            "active_inbox_count": 2,
        })
        self.assertTrue(tripwire["should_quarantine"])
        self.assertEqual(tripwire["status"], "BURNOUT_QUARANTINED")
        self.assertIn("DOMAIN_SPAM_RATE_EXCEEDED", tripwire["quarantine_reason"])

    def test_domain_burnout_absolute_bounce_ceiling_trigger(self):
        """Layer 1: 5 absolute bounces immediately triggers burnout quarantine regardless of sample percentage."""
        tripwire = evaluate_domain_burnout_tripwire({
            "domain": "highbounce.com",
            "total_sent": 250,
            "total_bounces": 5,
            "total_spam_complaints": 0,
            "aggregate_bounce_rate_pct": 2.0,  # 2.0% < 3.0% threshold
            "aggregate_spam_rate_pct": 0.0,
            "inbox_count": 2,
            "active_inbox_count": 2,
        })
        self.assertTrue(tripwire["should_quarantine"])
        self.assertIn("DOMAIN_ABSOLUTE_BOUNCE_CEILING_EXCEEDED", tripwire["quarantine_reason"])

    def test_domain_burnout_absolute_spam_ceiling_trigger(self):
        """Layer 1: 2 absolute spam complaints immediately triggers burnout quarantine."""
        tripwire = evaluate_domain_burnout_tripwire({
            "domain": "highspam.com",
            "total_sent": 3000,
            "total_bounces": 1,
            "total_spam_complaints": 2,
            "aggregate_bounce_rate_pct": 0.03,
            "aggregate_spam_rate_pct": 0.06,  # 0.06% < 0.1% threshold
            "inbox_count": 2,
            "active_inbox_count": 2,
        })
        self.assertTrue(tripwire["should_quarantine"])
        self.assertIn("DOMAIN_ABSOLUTE_SPAM_CEILING_EXCEEDED", tripwire["quarantine_reason"])

    def test_domain_burnout_small_sample_size_protection(self):
        """
        Layer 1: 1 bounce on 5 sends (20% bounce rate) does NOT trigger domain burnout
        due to small sample size floor (min_sample_size=15).
        """
        tripwire = evaluate_domain_burnout_tripwire({
            "domain": "newdomain.com",
            "total_sent": 5,
            "total_bounces": 1,
            "total_spam_complaints": 0,
            "aggregate_bounce_rate_pct": 20.0,  # High % but small sample
            "aggregate_spam_rate_pct": 0.0,
            "inbox_count": 1,
            "active_inbox_count": 1,
        }, min_sample_size=15)

        self.assertFalse(tripwire["should_quarantine"])
        self.assertEqual(tripwire["status"], "HEALTHY")
        self.assertIsNone(tripwire["quarantined_until"])

    def test_domain_burnout_majority_inbox_quarantine_tripwire(self):
        """Layer 1: If >= 50% of inboxes on a domain are quarantined (and >=2), domain trips burnout."""
        tripwire = evaluate_domain_burnout_tripwire({
            "domain": "multi-inbox.com",
            "total_sent": 10,
            "total_bounces": 0,
            "total_spam_complaints": 0,
            "aggregate_bounce_rate_pct": 0.0,
            "aggregate_spam_rate_pct": 0.0,
            "inbox_count": 4,
            "active_inbox_count": 2,  # 2 of 4 (50%) quarantined
        })
        self.assertTrue(tripwire["should_quarantine"])
        self.assertIn("DOMAIN_MAJORITY_INBOXES_QUARANTINED", tripwire["quarantine_reason"])

    def test_lead_thread_affinity_retention(self):
        """
        Layer 1: Follow-up for lead_id="lead_123" routes to the exact same inbox
        when that inbox is healthy.
        """
        inboxes = [
            {"id": "inb_target", "workspace_id": self.workspace_id, "email": "alex@acme.com", "daily_limit": 50, "sent_today": 10, "status": "ACTIVE", "affinity_lead_ids": ["lead_123"]},
            {"id": "inb_other", "workspace_id": self.workspace_id, "email": "beth@acme.com", "daily_limit": 50, "sent_today": 0, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_123",
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_target")
        self.assertEqual(res["selection_reason"], "THREAD_AFFINITY_LOCK")

    def test_lead_thread_affinity_same_domain_fallback(self):
        """
        Layer 1: When affinity inbox hits its daily cap, system falls back to another
        healthy inbox on the SAME root domain if affinity_fallback_mode="same_domain".
        """
        inboxes = [
            # Locked inbox is capped for today
            {"id": "inb_locked", "workspace_id": self.workspace_id, "email": "alex@acme.com", "daily_limit": 50, "sent_today": 50, "status": "ACTIVE", "affinity_lead_ids": ["lead_123"]},
            # Healthy fallback on SAME domain
            {"id": "inb_same_domain", "workspace_id": self.workspace_id, "email": "backup@mail.acme.com", "daily_limit": 50, "sent_today": 10, "status": "ACTIVE"},
            # Healthy inbox on DIFFERENT domain
            {"id": "inb_different_domain", "workspace_id": self.workspace_id, "email": "rep@otherdomain.com", "daily_limit": 50, "sent_today": 0, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_123",
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
            affinity_fallback_mode="same_domain",
        )

        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_same_domain")
        self.assertEqual(res["sender_domain"], "acme.com")
        self.assertEqual(res["selection_reason"], "THREAD_AFFINITY_SAME_DOMAIN_FALLBACK")

    def test_lead_thread_affinity_any_healthy_fallback(self):
        """Layer 1: When affinity inbox is capped and mode is 'any_healthy', falls back across pool."""
        inboxes = [
            {"id": "inb_locked", "workspace_id": self.workspace_id, "email": "alex@acme.com", "daily_limit": 50, "sent_today": 50, "status": "ACTIVE", "affinity_lead_ids": ["lead_123"]},
            {"id": "inb_other", "workspace_id": self.workspace_id, "email": "rep@other.com", "daily_limit": 50, "sent_today": 5, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_123",
            candidate_inboxes=inboxes,
            strategy="HEALTH_WEIGHTED",
            affinity_fallback_mode="any_healthy",
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_other")

    def test_lead_thread_affinity_postpone_when_configured(self):
        """
        Layer 1: When affinity inbox is capped and affinity_fallback_mode="postpone",
        returns postpone_required=True without selecting an unrelated sender.
        """
        inboxes = [
            {"id": "inb_locked", "workspace_id": self.workspace_id, "email": "alex@acme.com", "daily_limit": 50, "sent_today": 50, "status": "ACTIVE", "affinity_lead_ids": ["lead_999"]},
            {"id": "inb_other", "workspace_id": self.workspace_id, "email": "stranger@otherdomain.com", "daily_limit": 50, "sent_today": 0, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_999",
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
            affinity_fallback_mode="postpone",
        )

        self.assertIsNone(res["selected"])
        self.assertTrue(res.get("postpone_required"))
        self.assertEqual(res["selection_reason"], "AFFINITY_INBOX_CAPPED_POSTPONE")

    def test_lead_thread_affinity_same_domain_unavailable_handling(self):
        """Layer 1: When same domain fallback is unavailable, falls through or handles safely."""
        inboxes = [
            # Only 1 inbox on acme.com, and it's capped
            {"id": "inb_locked", "workspace_id": self.workspace_id, "email": "alex@acme.com", "daily_limit": 50, "sent_today": 50, "status": "ACTIVE", "affinity_lead_ids": ["lead_solo"]},
            # Other healthy inbox on different domain
            {"id": "inb_other", "workspace_id": self.workspace_id, "email": "beth@othercorp.com", "daily_limit": 50, "sent_today": 0, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_solo",
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
            affinity_fallback_mode="same_domain",
        )
        # Should fall through to the available healthy inbox
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_other")

    def test_hourly_velocity_throttling(self):
        """Layer 1: Inbox that has reached its hourly_limit is temporarily deferred."""
        inboxes = [
            {
                "id": "inb_throttled",
                "workspace_id": self.workspace_id,
                "email": "speedy@acme.com",
                "daily_limit": 100,
                "sent_today": 20,
                "hourly_limit": 10,
                "sent_this_hour": 10,  # Reached hourly velocity ceiling
                "status": "ACTIVE",
            },
            {
                "id": "inb_available",
                "workspace_id": self.workspace_id,
                "email": "steady@acme.com",
                "daily_limit": 100,
                "sent_today": 20,
                "hourly_limit": 10,
                "sent_this_hour": 2,  # Has hourly headroom
                "status": "ACTIVE",
            },
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_available")

        # Throttled inbox should appear in rejected list
        rejected_reasons = {r["id"]: r["reason"] for r in res["pool_summary"]["rejected"]}
        self.assertEqual(rejected_reasons.get("inb_throttled"), "HOURLY_LIMIT_EXHAUSTED")

    def test_expired_domain_quarantine_auto_recovery(self):
        """Layer 1: Once quarantined_until expires in UTC, domain automatically recovers to HEALTHY."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        inboxes = [
            {
                "id": "inb_rec",
                "workspace_id": self.workspace_id,
                "email": "recovered@restored-domain.com",
                "status": "ACTIVE",
                "domain_burnout_status": "BURNOUT_QUARANTINED",
                "domain_quarantined_until": past_time,
                "daily_limit": 50,
                "sent_today": 5,
                "sent_count": 20,
                "bounce_count": 0,
            }
        ]

        metrics = aggregate_domain_metrics(inboxes)
        m = metrics["restored-domain.com"]
        self.assertEqual(m["domain_burnout_status"], "HEALTHY")
        self.assertIsNone(m["quarantined_until"])

        # Eligible for selection
        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_rec")

    def test_record_inbox_delivery_outcome_domain_tripwire_trigger(self):
        """
        Layer 1: Calling record_inbox_delivery_outcome that triggers domain burnout
        quarantines the domain and updates all inboxes on that domain in Supabase.
        """
        mock_sb = MagicMock()
        mock_inbox = {
            "id": "inb_trip",
            "workspace_id": self.workspace_id,
            "email": "sender@brittle.com",
            "sent_count": 99,
            "sent_today": 10,
            "bounce_count": 2,
            "spam_complaint_count": 0,
            "status": "ACTIVE",
        }

        # Query for all domain inboxes returns 2 inboxes on brittle.com
        mock_query = MagicMock()
        mock_query.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                mock_inbox,
                {"id": "inb_sibling", "workspace_id": self.workspace_id, "email": "sibling@brittle.com", "sent_count": 0, "status": "ACTIVE"},
            ]
        )
        mock_sb.table.return_value = mock_query

        # Record a bounce that pushes total bounces to 3 / 100 sends = 3.0% (>= 3.0% threshold)
        res = record_inbox_delivery_outcome(
            supabase=mock_sb,
            workspace_id=self.workspace_id,
            inbox_id="inb_trip",
            event_type="bounce",
            inbox_record=mock_inbox,
            domain_bounce_threshold_pct=3.0,
        )

        self.assertTrue(res["quarantined"])
        self.assertTrue(res["domain_burnout_triggered"])
        self.assertEqual(res["status"], "QUARANTINED")
        self.assertIn("DOMAIN_BURNOUT", res["quarantine_reason"])

    def test_database_outage_fail_safe_defaults(self):
        """Layer 1: When Supabase throws an exception, functions degrade gracefully without raising."""
        broken_sb = MagicMock()
        broken_sb.table.side_effect = RuntimeError("Database connection timed out")

        # In-memory candidate evaluation proceeds without crashing
        res = select_rotating_sender_inbox(
            supabase=broken_sb,
            workspace_id=self.workspace_id,
            candidate_inboxes=[
                {"id": "i1", "workspace_id": self.workspace_id, "email": "ok@acme.com", "daily_limit": 50, "sent_today": 1, "status": "ACTIVE"}
            ],
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "i1")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & EXTREME EDGE CASES
    # =========================================================================

    def test_cross_tenant_idor_domain_isolation(self):
        """Layer 2: Inboxes belonging to workspace B are strictly rejected from workspace A."""
        candidate_inboxes = [
            {"id": "inb_attacker", "workspace_id": "ws_attacker_666", "email": "hacked@evil.com", "status": "ACTIVE"},
            {"id": "inb_legit", "workspace_id": self.workspace_id, "email": "rep@acme.com", "daily_limit": 50, "sent_today": 5, "status": "ACTIVE"},
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=candidate_inboxes,
            strategy="DOMAIN_BALANCED",
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb_legit")

        # Verify attacker inbox rejected due to CROSS_TENANT_MISMATCH
        rejected = res["pool_summary"]["rejected"]
        attacker_rejections = [r for r in rejected if r.get("id") == "inb_attacker"]
        self.assertEqual(len(attacker_rejections), 1)
        self.assertEqual(attacker_rejections[0]["reason"], "CROSS_TENANT_MISMATCH")

    def test_malformed_domain_and_email_inputs(self):
        """Layer 2: Handles malformed strings, IPs, localhost, and bad types safely without throwing."""
        malformed_inputs = [
            None,
            "",
            "   ",
            "user@localhost",
            "admin@192.168.1.1",
            "bad-domain..com",
            "127.0.0.1",
            "192.168.1.1",
            "::1",
            "http://169.254.169.254/latest",
            "invalid_domain_without_tld",
            12345,
            {},
        ]
        for bad_input in malformed_inputs:
            out = extract_root_domain(bad_input)
            self.assertIsNone(out, f"Expected None for malformed input: {bad_input}")

    def test_concurrent_domain_metrics_aggregation_resilience(self):
        """Layer 2: Malformed or missing keys in inboxes default safely."""
        malformed_inboxes = [
            {"id": "m1", "email": "valid@acme.com", "sent_count": None, "sent_today": "not_an_int", "bounce_count": None},
            {"id": "m2", "email": "valid2@acme.com"},  # completely missing count keys
            None,  # None row
            "random_string_in_list",
            {},  # empty dict
        ]
        metrics = aggregate_domain_metrics(malformed_inboxes, domain_daily_cap=150)
        self.assertIn("acme.com", metrics)
        m = metrics["acme.com"]
        self.assertEqual(m["total_sent"], 0)
        self.assertEqual(m["total_sent_today"], 0)
        self.assertEqual(m["total_bounces"], 0)
        self.assertEqual(m["aggregate_bounce_rate_pct"], 0.0)
        self.assertEqual(m["domain_burnout_status"], "HEALTHY")

    def test_domain_daily_cap_clamping_and_extreme_inputs(self):
        """Layer 2: Extreme domain daily cap values (e.g. negative or string) are safely clamped."""
        inboxes = [{"id": "i1", "email": "rep@acme.com", "sent_today": 5, "status": "ACTIVE"}]
        # Negative cap clamped to 1
        m_neg = aggregate_domain_metrics(inboxes, domain_daily_cap=-50)
        self.assertEqual(m_neg["acme.com"]["domain_daily_cap"], 1)

        # String cap safely parsed
        m_str = aggregate_domain_metrics(inboxes, domain_daily_cap="200")
        self.assertEqual(m_str["acme.com"]["domain_daily_cap"], 200)

    def test_executor_handle_send_email_injects_domain_telemetry(self):
        """
        Layer 2: Runs EleInNodeExecutor.handle_send_email with sender pool enabled and verifies
        returned payload contains sender_domain, strategy_applied, thread_affinity_maintained,
        and domain_health_status.
        """
        executor = EleInNodeExecutor(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
        )

        node_data = {
            "_campaign_id": "camp_domain_test_1",
            "use_sender_pool": True,
            "use_domain_balancing": True,
            "rotation_strategy": "DOMAIN_BALANCED",
            "domain_daily_cap": 150,
            "affinity_fallback_mode": "same_domain",
            "sender_pool_inboxes": [
                {
                    "id": "inb_exec_1",
                    "workspace_id": self.workspace_id,
                    "email": "outreach@scalecorp.io",
                    "sender_domain": "scalecorp.io",
                    "daily_limit": 50,
                    "sent_today": 10,
                    "status": "ACTIVE",
                }
            ],
            "subject": "Quick question",
            "body": "Hello {{first_name}}, following up on our scale conversation.",
            "to_email": "prospect@targetcorp.com",
        }

        lead = {
            "id": "lead_exec_test_42",
            "email": "prospect@targetcorp.com",
            "first_name": "Dave",
            "company": "TargetCorp",
        }

        with patch("integrations.backend.services.email_sender_service.record_inbox_delivery_outcome") as mock_record:
            mock_record.return_value = {"quarantined": False}
            res = executor.handle_send_email(node_data, lead)

        self.assertIn("sender_domain", res)
        self.assertEqual(res["sender_domain"], "scalecorp.io")
        self.assertEqual(res["strategy_applied"], "DOMAIN_BALANCED")
        self.assertIn("selection_reason", res)
        self.assertIn("thread_affinity_maintained", res)
        self.assertIn("domain_health_status", res)
        self.assertEqual(res["domain_health_status"], "HEALTHY")

    def test_executor_handle_send_email_affinity_postpone_preserves_credits(self):
        """
        Layer 2: When affinity inbox is capped and fallback mode is 'postpone',
        executor returns postponed status without failing or burning credits.
        """
        executor = EleInNodeExecutor(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
        )

        node_data = {
            "_campaign_id": "camp_postpone_1",
            "use_sender_pool": True,
            "rotation_strategy": "DOMAIN_BALANCED",
            "affinity_fallback_mode": "postpone",
            "to_email": "client@enterprise.com",
            "sender_pool_inboxes": [
                # Locked affinity inbox is capped
                {
                    "id": "inb_capped_lock",
                    "workspace_id": self.workspace_id,
                    "email": "founder@acme.com",
                    "daily_limit": 50,
                    "sent_today": 50,
                    "status": "ACTIVE",
                    "affinity_lead_ids": ["lead_locked_77"],
                }
            ],
            "subject": "Follow up",
            "body": "Hello",
        }

        lead = {"id": "lead_locked_77", "email": "client@enterprise.com", "first_name": "Alice"}

        res = executor.handle_send_email(node_data, lead)

        self.assertEqual(res["status"], "postponed")
        self.assertEqual(res["reason"], "affinity_inbox_daily_cap_reached")
        self.assertEqual(res["next_run_delta_hours"], 12)
        self.assertEqual(res["branch"], Branch.FAILED.value)

    def test_router_evaluate_deliverability_pool_domain_parameters(self):
        """
        Layer 2: Endpoint /api/elein/deliverability/evaluate-pool accepts and applies
        domain_daily_cap, affinity_fallback_mode, and use_domain_balancing.
        """
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "PRO", "balance": 5000}

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            payload = {
                "candidate_inboxes": [
                    {
                        "id": "inb_rt_1",
                        "workspace_id": self.workspace_id,
                        "email": "sales@alpha.com",
                        "daily_limit": 50,
                        "sent_today": 2,
                        "status": "ACTIVE",
                    }
                ],
                "use_domain_balancing": True,
                "domain_daily_cap": 100,
                "affinity_fallback_mode": "same_domain",
            }
            resp = client.post("/api/elein/deliverability/evaluate-pool", json=payload)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIsNotNone(data.get("selected"))
            self.assertEqual(data.get("sender_domain"), "alpha.com")
            self.assertEqual(data.get("strategy_applied"), "DOMAIN_BALANCED")
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_router_get_sender_pool_domains_endpoint(self):
        """
        Layer 2: Endpoint /api/elein/sender-pool/domains returns aggregated domain metrics
        for the authenticated workspace.
        """
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "i1", "workspace_id": self.workspace_id, "email": "a@domain1.com", "sent_count": 10, "status": "ACTIVE"},
                {"id": "i2", "workspace_id": self.workspace_id, "email": "b@domain2.com", "sent_count": 20, "status": "ACTIVE"},
            ]
        )

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            resp = client.get("/api/elein/sender-pool/domains")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["workspace_id"], self.workspace_id)
            self.assertEqual(data["total_domains"], 2)
            self.assertIn("domain1.com", data["domains"])
            self.assertIn("domain2.com", data["domains"])
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)


if __name__ == "__main__":
    unittest.main()
