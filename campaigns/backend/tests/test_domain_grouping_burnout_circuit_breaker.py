import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call

from integrations.backend.services.email_sender_service import (
    extract_root_domain,
    aggregate_domain_metrics,
    evaluate_domain_burnout_tripwire,
    select_rotating_sender_inbox,
    record_inbox_delivery_outcome,
)


class TestDomainGroupingBurnoutCircuitBreaker(unittest.TestCase):
    """
    Test suite for Issue 5: Dynamic Sender Domain & Mailbox Rotation with Burnout Protection.
    Implements Three-Layer Logic Architecture (Paranoia Framework):
      Layer 0: Foundational Layer (domain grouping, root domain extraction, metrics aggregation,
               domain balanced rotation, and affinity fallback)
      Layer 1: Environmental Failure Analysis (small-sample false-positive guard, absolute floors,
               domain daily cap exhaustion, hourly velocity limiting, expired cooldown auto-recovery)
      Layer 2: Human Paranoia (malformed domain inputs, SSRF rejection, cross-tenant IDOR,
               affinity postpone mode, domain burnout propagation in Supabase)
    """

    def setUp(self):
        self.workspace_id = "ws_test_burnout_breaker"
        self.mock_supabase = MagicMock()

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER TESTS
    # =========================================================================

    def test_layer0_extract_root_domain_various_formats(self):
        """Layer 0: Correctly extracts root domain across subdomains, multi-part ccTLDs, and emails."""
        # Simple subdomains
        self.assertEqual(extract_root_domain("mail.getacme.com"), "getacme.com")
        self.assertEqual(extract_root_domain("outbound.sales.acme.com"), "acme.com")

        # Multi-part public suffixes (.co.uk, .com.au, .co.nz, .com.br, etc.)
        self.assertEqual(extract_root_domain("outbound.sales.acme.co.uk"), "acme.co.uk")
        self.assertEqual(extract_root_domain("sales.acme.com.au"), "acme.com.au")
        self.assertEqual(extract_root_domain("dev.team.acme.co.nz"), "acme.co.nz")
        self.assertEqual(extract_root_domain("corp.acme.com.br"), "acme.com.br")
        self.assertEqual(extract_root_domain("mail.acme.co.in"), "acme.co.in")
        self.assertEqual(extract_root_domain("outbound.acme.co.za"), "acme.co.za")

        # Already root domains
        self.assertEqual(extract_root_domain("tryacme.io"), "tryacme.io")
        self.assertEqual(extract_root_domain("getacme.com"), "getacme.com")
        self.assertEqual(extract_root_domain("acme.co.uk"), "acme.co.uk")

        # Email addresses
        self.assertEqual(extract_root_domain("alex@mail.getacme.com"), "getacme.com")
        self.assertEqual(extract_root_domain("sarah@outbound.sales.acme.co.uk"), "acme.co.uk")
        self.assertEqual(extract_root_domain("ceo@tryacme.io"), "tryacme.io")

        # URLs / protocol inputs
        self.assertEqual(extract_root_domain("https://mail.getacme.com/v1/send"), "getacme.com")
        self.assertEqual(extract_root_domain("http://outbound.acme.com.au:8080/path"), "acme.com.au")

    def test_layer0_aggregate_domain_metrics_calculation(self):
        """Layer 0: Aggregates metrics accurately across grouped inboxes per root domain."""
        inboxes = [
            # Domain 1: getacme.com (2 inboxes)
            {
                "id": "inb_1",
                "email": "alex@mail.getacme.com",
                "status": "ACTIVE",
                "sent_count": 100,
                "sent_today": 25,
                "bounce_count": 1,
                "spam_complaint_count": 0,
            },
            {
                "id": "inb_2",
                "email": "sales@outbound.getacme.com",
                "status": "ACTIVE",
                "sent_count": 150,
                "sent_today": 35,
                "bounce_count": 2,
                "spam_complaint_count": 0,
            },
            # Domain 2: tryacme.io (1 inbox)
            {
                "id": "inb_3",
                "email": "ops@tryacme.io",
                "status": "ACTIVE",
                "sent_count": 50,
                "sent_today": 10,
                "bounce_count": 0,
                "spam_complaint_count": 0,
            },
        ]

        metrics = aggregate_domain_metrics(inboxes, domain_daily_cap=150)
        self.assertIn("getacme.com", metrics)
        self.assertIn("tryacme.io", metrics)

        d1 = metrics["getacme.com"]
        self.assertEqual(d1["domain"], "getacme.com")
        self.assertEqual(d1["inbox_count"], 2)
        self.assertEqual(d1["active_inbox_count"], 2)
        self.assertEqual(d1["total_sent"], 250)
        self.assertEqual(d1["total_sent_today"], 60)
        self.assertEqual(d1["domain_daily_cap"], 150)
        self.assertEqual(d1["remaining_domain_capacity"], 90)
        self.assertEqual(d1["total_bounces"], 3)
        self.assertEqual(d1["total_spam_complaints"], 0)
        # 3 / 250 = 1.2%
        self.assertEqual(d1["aggregate_bounce_rate_pct"], 1.2)
        self.assertEqual(d1["aggregate_spam_rate_pct"], 0.0)
        self.assertEqual(d1["domain_burnout_status"], "HEALTHY")
        self.assertIsNone(d1["quarantined_until"])

        d2 = metrics["tryacme.io"]
        self.assertEqual(d2["domain"], "tryacme.io")
        self.assertEqual(d2["inbox_count"], 1)
        self.assertEqual(d2["remaining_domain_capacity"], 140)
        self.assertEqual(d2["domain_burnout_status"], "HEALTHY")

    def test_layer0_domain_balanced_rotation_strategy(self):
        """Layer 0: DOMAIN_BALANCED picks least sent domain, then highest remaining capacity inbox."""
        inboxes = [
            # Domain A: getacme.com — total_sent_today = 30
            {
                "id": "inb_a1",
                "workspace_id": self.workspace_id,
                "email": "alex@mail.getacme.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 20,
                "deliverability_score": 95,
            },
            {
                "id": "inb_a2",
                "workspace_id": self.workspace_id,
                "email": "bob@sales.getacme.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 10,
                "deliverability_score": 95,
            },
            # Domain B: tryacme.io — total_sent_today = 5 (least sent today!)
            {
                "id": "inb_b1",
                "workspace_id": self.workspace_id,
                "email": "clara@tryacme.io",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 5,
                "deliverability_score": 95,
            },
            {
                "id": "inb_b2",
                "workspace_id": self.workspace_id,
                "email": "dan@app.tryacme.io",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 0,  # 0 sent today -> 50 remaining capacity (highest in domain B)
                "deliverability_score": 95,
            },
        ]

        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=inboxes,
            strategy="DOMAIN_BALANCED",
            domain_daily_cap=150,
        )

        self.assertIsNotNone(res["selected"])
        # Should pick domain B because 5 sent today < 30 sent today on domain A
        self.assertEqual(res["sender_domain"], "tryacme.io")
        # Within domain B, inb_b2 has 50 remaining capacity vs inb_b1's 45
        self.assertEqual(res["selected"]["id"], "inb_b2")
        self.assertEqual(res["selection_reason"], "DOMAIN_BALANCED_OPTIMAL")
        self.assertEqual(res["strategy_applied"], "DOMAIN_BALANCED")
        self.assertEqual(res["domain_metrics"]["domain"], "tryacme.io")
        self.assertIn("tryacme.io", res["pool_summary"]["domain_metrics"])

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS TESTS
    # =========================================================================

    def test_layer1_domain_burnout_small_sample_false_positive_guard(self):
        """Layer 1: Small sample (under 15 sends) does not trip burnout unless absolute floors reached."""
        # 6 sends, 1 bounce = 16.7% bounce rate (far above 3.0%).
        # But sample_size = 6 < 15, and absolute bounces = 1 < 5. Must NOT quarantine!
        small_sample_metrics = {
            "domain": "test.com",
            "inbox_count": 1,
            "active_inbox_count": 1,
            "total_sent": 6,
            "total_bounces": 1,
            "total_spam_complaints": 0,
            "aggregate_bounce_rate_pct": 16.67,
            "aggregate_spam_rate_pct": 0.0,
        }
        res = evaluate_domain_burnout_tripwire(small_sample_metrics, min_sample_size=15)
        self.assertFalse(res["should_quarantine"])
        self.assertEqual(res["status"], "HEALTHY")

        # Once sample >= 15 with bounce rate >= 3.0%: TRIPS BURNOUT!
        sample_reached_metrics = {
            "domain": "test.com",
            "inbox_count": 1,
            "active_inbox_count": 1,
            "total_sent": 20,
            "total_bounces": 1,
            "total_spam_complaints": 0,
            "aggregate_bounce_rate_pct": 5.0,  # 1/20 = 5% >= 3%
            "aggregate_spam_rate_pct": 0.0,
        }
        res2 = evaluate_domain_burnout_tripwire(sample_reached_metrics, min_sample_size=15)
        self.assertTrue(res2["should_quarantine"])
        self.assertEqual(res2["status"], "BURNOUT_QUARANTINED")
        self.assertIn("DOMAIN_BOUNCE_RATE_EXCEEDED", res2["quarantine_reason"])
        self.assertIsNotNone(res2["quarantined_until"])

        # Absolute bounce floor: 5 bounces on only 8 sends -> TRIPS IMMEDIATELY!
        abs_bounce_metrics = {
            "domain": "test.com",
            "inbox_count": 1,
            "active_inbox_count": 1,
            "total_sent": 8,
            "total_bounces": 5,
            "total_spam_complaints": 0,
            "aggregate_bounce_rate_pct": 62.5,
            "aggregate_spam_rate_pct": 0.0,
        }
        res3 = evaluate_domain_burnout_tripwire(abs_bounce_metrics, min_sample_size=15)
        self.assertTrue(res3["should_quarantine"])
        self.assertIn("DOMAIN_ABSOLUTE_BOUNCE_CEILING_EXCEEDED", res3["quarantine_reason"])

        # Absolute spam floor: 2 spam complaints on 10 sends -> TRIPS IMMEDIATELY!
        abs_spam_metrics = {
            "domain": "test.com",
            "inbox_count": 1,
            "active_inbox_count": 1,
            "total_sent": 10,
            "total_bounces": 0,
            "total_spam_complaints": 2,
            "aggregate_bounce_rate_pct": 0.0,
            "aggregate_spam_rate_pct": 20.0,
        }
        res4 = evaluate_domain_burnout_tripwire(abs_spam_metrics, min_sample_size=15)
        self.assertTrue(res4["should_quarantine"])
        self.assertIn("DOMAIN_ABSOLUTE_SPAM_CEILING_EXCEEDED", res4["quarantine_reason"])

        # Majority inboxes quarantined: 4 inboxes, 2 active (2 quarantined) = 50% >= 50%
        majority_quarantined_metrics = {
            "domain": "test.com",
            "inbox_count": 4,
            "active_inbox_count": 2,
            "total_sent": 5,
            "total_bounces": 0,
            "total_spam_complaints": 0,
        }
        res5 = evaluate_domain_burnout_tripwire(majority_quarantined_metrics)
        self.assertTrue(res5["should_quarantine"])
        self.assertIn("DOMAIN_MAJORITY_INBOXES_QUARANTINED", res5["quarantine_reason"])

    def test_layer1_domain_daily_cap_and_hourly_limit_exhaustion(self):
        """Layer 1: Rejects inboxes when domain daily cap is reached or hourly limit is hit."""
        # Case A: Domain daily cap exhausted (150 sent today against 150 cap)
        capped_inboxes = [
            {
                "id": "inb_cap",
                "workspace_id": self.workspace_id,
                "email": "sender@cappeddomain.com",
                "status": "ACTIVE",
                "daily_limit": 200,
                "sent_today": 150,  # domain total_sent_today = 150
            }
        ]
        res_cap = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=capped_inboxes,
            domain_daily_cap=150,
        )
        self.assertIsNone(res_cap["selected"])
        self.assertEqual(res_cap["selection_reason"], "NO_HEALTHY_INBOXES_AVAILABLE")
        self.assertEqual(res_cap["pool_summary"]["rejected"][0]["reason"], "DOMAIN_DAILY_CAP_EXHAUSTED")

        # Case B: Hourly velocity limit exhausted
        hourly_inboxes = [
            {
                "id": "inb_hour",
                "workspace_id": self.workspace_id,
                "email": "sender@velocitydomain.com",
                "status": "ACTIVE",
                "daily_limit": 100,
                "sent_today": 10,
                "hourly_limit": 10,
                "sent_this_hour": 10,  # 10 >= 10 -> hourly exhausted
            }
        ]
        res_hour = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=hourly_inboxes,
            domain_daily_cap=150,
        )
        self.assertIsNone(res_hour["selected"])
        self.assertEqual(res_hour["pool_summary"]["rejected"][0]["reason"], "HOURLY_LIMIT_EXHAUSTED")

    def test_layer1_burnout_cooldown_and_recovery(self):
        """Layer 1: Preserves active cooldown, auto-recovers when timestamp expires."""
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        quarantined_metrics = {
            "domain": "cooldown.com",
            "inbox_count": 1,
            "active_inbox_count": 1,
            "total_sent": 100,
            "total_bounces": 0,
            "total_spam_complaints": 0,
            "quarantined_until": future_iso,
            "quarantine_reason": "DOMAIN_BURNOUT_PREVIOUS",
        }
        res_active = evaluate_domain_burnout_tripwire(quarantined_metrics)
        self.assertTrue(res_active["should_quarantine"])
        self.assertEqual(res_active["status"], "BURNOUT_QUARANTINED")

        # Expired cooldown (1 hour ago in UTC)
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        quarantined_metrics["quarantined_until"] = past_iso
        res_expired = evaluate_domain_burnout_tripwire(quarantined_metrics)
        self.assertFalse(res_expired["should_quarantine"])
        self.assertEqual(res_expired["status"], "HEALTHY")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA & TENANT SECURITY TESTS
    # =========================================================================

    def test_layer2_malformed_domain_inputs_and_ssrf_rejection(self):
        """Layer 2: Rejects localhost, private IPs, SSRF URLs, and malformed domain inputs."""
        self.assertIsNone(extract_root_domain(None))
        self.assertIsNone(extract_root_domain(""))
        self.assertIsNone(extract_root_domain("   "))
        self.assertIsNone(extract_root_domain("localhost"))
        self.assertIsNone(extract_root_domain("127.0.0.1"))
        self.assertIsNone(extract_root_domain("192.168.1.100"))
        self.assertIsNone(extract_root_domain("10.0.0.1"))
        self.assertIsNone(extract_root_domain("alex@127.0.0.1"))
        self.assertIsNone(extract_root_domain("http://169.254.169.254/latest/meta-data"))
        self.assertIsNone(extract_root_domain("co.uk"))  # Naked TLD without domain label
        self.assertIsNone(extract_root_domain("invalid..domain.com"))
        self.assertIsNone(extract_root_domain("not-a-domain"))

    def test_layer2_lead_affinity_fallbacks(self):
        """Layer 2: Thread affinity respects lock, or falls back to same_domain, any_healthy, or postpone."""
        # Inbox 1 is locked to lead_999, but is capped (sent_today = 50/50)
        # Inbox 2 is on the SAME root domain (getacme.com) and is healthy
        # Inbox 3 is on a DIFFERENT root domain (othercorp.com) and is healthy
        inboxes = [
            {
                "id": "inb_locked_capped",
                "workspace_id": self.workspace_id,
                "email": "alex@sales.getacme.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 50,  # Capped!
                "affinity_lead_ids": ["lead_999"],
            },
            {
                "id": "inb_same_domain_healthy",
                "workspace_id": self.workspace_id,
                "email": "clara@support.getacme.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 10,  # Healthy, 40 remaining
            },
            {
                "id": "inb_other_domain_healthy",
                "workspace_id": self.workspace_id,
                "email": "dan@othercorp.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 0,
            },
        ]

        # 1. Fallback mode: same_domain -> picks inb_same_domain_healthy on getacme.com
        res_same = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_999",
            candidate_inboxes=inboxes,
            affinity_fallback_mode="same_domain",
        )
        self.assertIsNotNone(res_same["selected"])
        self.assertEqual(res_same["selected"]["id"], "inb_same_domain_healthy")
        self.assertEqual(res_same["selection_reason"], "THREAD_AFFINITY_SAME_DOMAIN_FALLBACK")
        self.assertEqual(res_same["sender_domain"], "getacme.com")

        # 2. Fallback mode: postpone -> returns postpone_required = True
        res_postpone = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_999",
            candidate_inboxes=inboxes,
            affinity_fallback_mode="postpone",
        )
        self.assertIsNone(res_postpone["selected"])
        self.assertEqual(res_postpone["selection_reason"], "AFFINITY_INBOX_CAPPED_POSTPONE")
        self.assertTrue(res_postpone["postpone_required"])

        # 3. Fallback mode: any_healthy -> falls through to pool selection with reason THREAD_AFFINITY_ANY_HEALTHY_FALLBACK
        res_any = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead_999",
            candidate_inboxes=inboxes,
            affinity_fallback_mode="any_healthy",
            strategy="HEALTH_WEIGHTED",
        )
        self.assertIsNotNone(res_any["selected"])
        self.assertEqual(res_any["selection_reason"], "THREAD_AFFINITY_ANY_HEALTHY_FALLBACK")

    def test_layer2_record_delivery_outcome_domain_circuit_breaker(self):
        """Layer 2: Trips domain circuit breaker on bounce threshold and updates all inboxes on that domain."""
        mock_supabase = MagicMock()
        inbox_record = {
            "id": "inb_burn_target",
            "workspace_id": self.workspace_id,
            "email": "agent@burnout-test.com",
            "sent_count": 20,
            "sent_today": 10,
            "bounce_count": 4,  # Next bounce will make it 5 bounces (absolute ceiling)
            "spam_complaint_count": 0,
            "status": "ACTIVE",
        }

        # Supabase returns two inboxes sharing the domain 'burnout-test.com'
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                inbox_record,
                {
                    "id": "inb_burn_sibling",
                    "workspace_id": self.workspace_id,
                    "email": "backup@mail.burnout-test.com",
                    "sent_count": 10,
                    "sent_today": 5,
                    "bounce_count": 0,
                    "spam_complaint_count": 0,
                    "status": "ACTIVE",
                },
            ]
        )

        outcome = record_inbox_delivery_outcome(
            supabase=mock_supabase,
            workspace_id=self.workspace_id,
            inbox_id="inb_burn_target",
            event_type="bounce",
            inbox_record=inbox_record,
        )

        self.assertEqual(outcome["status"], "QUARANTINED")
        self.assertTrue(outcome["quarantined"])
        self.assertTrue(outcome["domain_burnout_triggered"])
        self.assertEqual(outcome["domain_burnout_status"], "BURNOUT_QUARANTINED")
        self.assertEqual(outcome["domain"], "burnout-test.com")
        self.assertIn("DOMAIN_BURNOUT", outcome["quarantine_reason"])

        # Verify Supabase update was triggered for sibling inbox
        mock_supabase.table.assert_any_call("email_sender_inboxes")
        mock_supabase.table.assert_any_call("outbox_events")


if __name__ == "__main__":
    unittest.main()
