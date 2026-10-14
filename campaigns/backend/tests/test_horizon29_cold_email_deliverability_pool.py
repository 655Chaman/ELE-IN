import unittest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from core.backend.services.deliverability_guard import (
    sanitize_domain_input,
    verify_domain_dns_health,
    evaluate_inbox_deliverability_tripwire,
    rewrite_tracking_links,
)
from integrations.backend.services.email_sender_service import (
    calculate_warmup_daily_cap,
    select_rotating_sender_inbox,
    record_inbox_delivery_outcome,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestHorizon29ColdEmailDeliverabilityPool(unittest.TestCase):
    """
    Test suite for Horizon 29: Outbox Cold-Email Deliverability Pool, Custom Tracking Domains
    & SPF/DKIM/DMARC Health Tripwires.
    Implements Three-Layer Logic Architecture (Paranoia Framework):
      Layer 0: Foundational Layer (DNS verification, bounce/spam tripwires, warmup ramp, sender pool rotation, thread affinity)
      Layer 1: Environmental Failure Analysis (small-sample false-positive guard, unverified SSL bypass, expired quarantine recovery)
      Layer 2: Human Paranoia (SSRF/domain sanitization, RFC 7208 multiple-SPF collision, +all spoofing check, IDOR tenant defense)
    """

    def setUp(self):
        self.workspace_id = "ws_test_horizon29"
        self.mock_supabase = MagicMock()

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER TESTS
    # =========================================================================

    def test_layer0_verify_domain_dns_healthy(self):
        """Layer 0: Full SPF, DKIM, DMARC (p=reject), and CNAME verification yields 100/100 HEALTHY."""
        mock_dns = {
            "spf": ["v=spf1 include:_spf.google.com include:sendgrid.net ~all"],
            "dkim": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"],
            "dmarc": ["v=DMARC1; p=reject; rua=mailto:dmarc@acmecorp.com"],
            "cname": "track.elein.ai",
            "ssl_verified": True,
        }
        res = verify_domain_dns_health(
            domain="acmecorp.com",
            tracking_subdomain="track",
            expected_cname_target="track.elein.ai",
            dkim_selector="elein",
            mock_records=mock_dns,
        )
        self.assertTrue(res["valid"])
        self.assertEqual(res["health_status"], "HEALTHY")
        self.assertEqual(res["deliverability_score"], 100)
        self.assertTrue(res["can_send_safely"])
        self.assertTrue(res["ssl_tracking_ready"])
        self.assertEqual(len(res["errors"]), 0)

    def test_layer0_evaluate_bounce_and_spam_tripwires(self):
        """Layer 0: Tripwires trigger quarantine when bounce rate >= 2.5% or spam rate >= 0.1%."""
        # Healthy inbox (1% bounce rate, 0% spam)
        healthy = evaluate_inbox_deliverability_tripwire(
            {"sent_count": 100, "bounce_count": 1, "spam_complaint_count": 0}
        )
        self.assertFalse(healthy["should_quarantine"])
        self.assertEqual(healthy["recommended_status"], "ACTIVE")

        # High bounce inbox (4% bounce rate on 100 sends >= 2.5%)
        bounced = evaluate_inbox_deliverability_tripwire(
            {"sent_count": 100, "bounce_count": 4, "spam_complaint_count": 0}
        )
        self.assertTrue(bounced["should_quarantine"])
        self.assertEqual(bounced["recommended_status"], "QUARANTINED")
        self.assertIn("BOUNCE_RATE_EXCEEDED", bounced["quarantine_reason"])
        self.assertIsNotNone(bounced["quarantined_until"])

        # Spam complaint tripwire (1 complaint on 500 sends = 0.2% >= 0.1%)
        spammed = evaluate_inbox_deliverability_tripwire(
            {"sent_count": 500, "bounce_count": 2, "spam_complaint_count": 1}
        )
        self.assertTrue(spammed["should_quarantine"])
        self.assertIn("SPAM_COMPLAINT_THRESHOLD_EXCEEDED", spammed["quarantine_reason"])

    def test_layer0_warmup_daily_cap_ramp(self):
        """Layer 0: Linear warmup ramp starts at warmup_start_limit and caps at daily_limit."""
        inbox_day0 = {
            "daily_limit": 60,
            "warmup_enabled": True,
            "warmup_start_limit": 15,
            "warmup_increment_per_day": 5,
            "warmup_days_active": 0,
        }
        self.assertEqual(calculate_warmup_daily_cap(inbox_day0), 15)

        inbox_day4 = dict(inbox_day0, warmup_days_active=4)
        self.assertEqual(calculate_warmup_daily_cap(inbox_day4), 35)

        inbox_day20 = dict(inbox_day0, warmup_days_active=20)
        self.assertEqual(calculate_warmup_daily_cap(inbox_day20), 60)

    def test_layer0_sender_pool_rotation_and_thread_affinity(self):
        """Layer 0: Selects optimal healthy inbox and honors lead-to-sender thread affinity locks."""
        candidates = [
            {
                "id": "inb-1",
                "workspace_id": self.workspace_id,
                "email": "alex@sales1.acme.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 45,  # Only 5 remaining
                "deliverability_score": 90,
                "affinity_lead_ids": ["lead-locked-99"],
            },
            {
                "id": "inb-2",
                "workspace_id": self.workspace_id,
                "email": "alex@sales2.acme.com",
                "status": "ACTIVE",
                "daily_limit": 50,
                "sent_today": 5,  # 45 remaining
                "deliverability_score": 98,
            },
        ]

        # Normal selection picks inb-2 due to much higher composite capacity + health score
        res_optimal = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead-new-1",
            candidate_inboxes=candidates,
            strategy="HEALTH_WEIGHTED",
        )
        self.assertEqual(res_optimal["selected"]["id"], "inb-2")
        self.assertEqual(res_optimal["selection_reason"], "HEALTH_WEIGHTED_OPTIMAL")

        # Thread affinity lock forces selection of inb-1 for lead-locked-99
        res_affinity = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            lead_id="lead-locked-99",
            candidate_inboxes=candidates,
            strategy="HEALTH_WEIGHTED",
        )
        self.assertEqual(res_affinity["selected"]["id"], "inb-1")
        self.assertEqual(res_affinity["selection_reason"], "THREAD_AFFINITY_LOCK")

    def test_layer0_executor_handle_send_email_with_pool_and_tracking(self):
        """Layer 0: EleInNodeExecutor.handle_send_email rotates sender inbox and rewrites tracking URLs."""
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}
        executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
        )
        node_data = {
            "_lead_id": "lead-29",
            "to": "cto@prospect.io",
            "subject": "Quick question on pipeline",
            "body": "Check our case study at https://elein.ai/case-study.",
            "use_sender_pool": True,
            "sender_pool_inboxes": [
                {
                    "id": "inb-prime",
                    "workspace_id": self.workspace_id,
                    "email": "founder@tryacme.io",
                    "status": "ACTIVE",
                    "daily_limit": 50,
                    "sent_today": 2,
                    "tracking_domain": "track.tryacme.io",
                    "ssl_verified": True,
                }
            ],
        }
        result = executor.handle_send_email(node_data, linkedin_url=None)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["branch"], Branch.THEN.value)
        self.assertEqual(result["from_email"], "founder@tryacme.io")
        self.assertEqual(result["sender_inbox_id"], "inb-prime")
        self.assertEqual(result["tracking_rewritten"], 1)
        self.assertIn("https://track.tryacme.io/t/c/", result["body"])

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS TESTS
    # =========================================================================

    def test_layer1_small_sample_size_false_positive_protection(self):
        """Layer 1: 1 bounce on 5 sends (20%) does not trip quarantine, but 5 raw bounces trips absolute floor."""
        small_sample = evaluate_inbox_deliverability_tripwire(
            {"sent_count": 5, "bounce_count": 1, "spam_complaint_count": 0},
            min_sample_size=20,
        )
        self.assertFalse(small_sample["should_quarantine"])
        self.assertFalse(small_sample["metrics"]["sample_size_reached"])

        catastrophic_small = evaluate_inbox_deliverability_tripwire(
            {"sent_count": 6, "bounce_count": 5, "spam_complaint_count": 0},
            min_sample_size=20,
        )
        self.assertTrue(catastrophic_small["should_quarantine"])
        self.assertIn("BOUNCE_RATE_EXCEEDED", catastrophic_small["quarantine_reason"])

    def test_layer1_unverified_ssl_tracking_link_bypass(self):
        """Layer 1: When custom tracking domain SSL is unverified, links remain unrewritten to avoid browser SSL warnings."""
        raw_body = "Book a slot at https://cal.com/acme/15min today!"
        res = rewrite_tracking_links(
            body=raw_body,
            tracking_domain="track.acmecorp.com",
            email_id="em-101",
            workspace_id=self.workspace_id,
            ssl_verified=False,
        )
        self.assertFalse(res["tracking_applied"])
        self.assertEqual(res["rewritten_count"], 0)
        self.assertEqual(res["body"], raw_body)
        self.assertEqual(res["fallback_reason"], "SSL_OR_DOMAIN_UNVERIFIED")

    def test_layer1_expired_quarantine_auto_recovery(self):
        """Layer 1: An inbox whose quarantined_until is in the past automatically recovers for pool selection."""
        expired_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        future_ts = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()

        candidates = [
            {
                "id": "inb-still-locked",
                "workspace_id": self.workspace_id,
                "email": "rep1@acme.com",
                "status": "QUARANTINED",
                "quarantined_until": future_ts,
                "daily_limit": 40,
                "sent_today": 0,
            },
            {
                "id": "inb-recovered",
                "workspace_id": self.workspace_id,
                "email": "rep2@acme.com",
                "status": "QUARANTINED",
                "quarantined_until": expired_ts,
                "daily_limit": 40,
                "sent_today": 0,
            },
        ]
        res = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=candidates,
        )
        self.assertIsNotNone(res["selected"])
        self.assertEqual(res["selected"]["id"], "inb-recovered")

    def test_layer1_record_delivery_outcome_trips_and_alerts(self):
        """Layer 1: Recording a bounce that crosses 2.5% transitions inbox to QUARANTINED and emits outbox alert."""
        inbox_rec = {
            "id": "inb-trip-1",
            "workspace_id": self.workspace_id,
            "email": "outreach@acme.com",
            "sent_count": 40,
            "sent_today": 10,
            "bounce_count": 0,
            "spam_complaint_count": 0,
            "status": "ACTIVE",
        }
        outcome = record_inbox_delivery_outcome(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            inbox_id="inb-trip-1",
            event_type="bounced",
            inbox_record=inbox_rec,
            bounce_threshold_pct=2.5,
        )
        self.assertTrue(outcome["quarantined"])
        self.assertEqual(outcome["status"], "QUARANTINED")
        self.assertEqual(outcome["metrics"]["bounce_rate_pct"], 2.5)
        self.mock_supabase.table.assert_any_call("outbox_events")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA (USER ERROR & SECURITY) TESTS
    # =========================================================================

    def test_layer2_domain_sanitization_and_ssrf_block(self):
        """Layer 2: Sanitizes messy user URLs/emails into clean domains and blocks SSRF/localhost."""
        self.assertEqual(
            sanitize_domain_input("  https://www.AcmeCorp.com:8080/settings?tab=dns#top "),
            "acmecorp.com",
        )
        self.assertEqual(sanitize_domain_input("founder@sub.tryacme.io"), "sub.tryacme.io")

        # SSRF / internal host rejections
        self.assertIsNone(sanitize_domain_input("http://169.254.169.254/latest/meta-data/"))
        self.assertIsNone(sanitize_domain_input("localhost:3000"))
        self.assertIsNone(sanitize_domain_input("127.0.0.1"))
        self.assertIsNone(sanitize_domain_input("redis.internal"))

    def test_layer2_multiple_spf_collision_and_permissive_all(self):
        """Layer 2: Detects RFC 7208 multiple-SPF collision, '+all' spoofing risk, and DMARC p=none warning."""
        collision_dns = {
            "spf": [
                "v=spf1 include:_spf.google.com ~all",
                "v=spf1 include:sendgrid.net ~all",
            ],
            "dkim": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"],
            "dmarc": ["v=DMARC1; p=none;"],
            "cname": "wrong.target.com",
        }
        res = verify_domain_dns_health("acmecorp.com", mock_records=collision_dns)
        self.assertFalse(res["can_send_safely"])
        self.assertEqual(res["health_status"], "CRITICAL")
        self.assertTrue(any("Multiple SPF records" in e for e in res["errors"]))
        self.assertTrue(any("p=none" in w for w in res["warnings"]))

        # Check permissive +all
        permissive_dns = {
            "spf": ["v=spf1 +all"],
            "dkim": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"],
            "dmarc": ["v=DMARC1; p=reject;"],
        }
        res_perm = verify_domain_dns_health("acmecorp.com", mock_records=permissive_dns)
        self.assertFalse(res_perm["can_send_safely"])
        self.assertTrue(any("+all" in e for e in res_perm["errors"]))

    def test_layer2_cross_tenant_idor_protection_in_pool_and_endpoints(self):
        """Layer 2: Rejects foreign workspace inboxes and enforces 404 on cross-tenant lead_id."""
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace
        from campaigns.backend.routers.elein import get_supabase_client

        # 1. Pool filters out cross-tenant inboxes
        foreign_pool = select_rotating_sender_inbox(
            supabase=None,
            workspace_id=self.workspace_id,
            candidate_inboxes=[
                {
                    "id": "inb-foreign",
                    "workspace_id": "ws_attacker_999",
                    "email": "attacker@evil.com",
                    "status": "ACTIVE",
                }
            ],
        )
        self.assertIsNone(foreign_pool["selected"])
        self.assertEqual(
            foreign_pool["pool_summary"]["rejected"][0]["reason"],
            "CROSS_TENANT_MISMATCH",
        )

        # 2. Router endpoint enforces 404 when lead belongs to another workspace
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"id": "lead_foreign", "workspace_id": "ws_other_tenant"}
        ]

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/elein/deliverability/evaluate-pool",
                json={"lead_id": "lead_foreign", "strategy": "HEALTH_WEIGHTED"},
            )
            self.assertEqual(resp.status_code, 404)

            # Verify SSRF domain via endpoint returns 400
            resp_ssrf = client.post(
                "/api/elein/deliverability/verify-domain",
                json={"domain": "http://169.254.169.254/latest"},
            )
            self.assertEqual(resp_ssrf.status_code, 400)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_layer2_tier_gating_free_vs_pro_deliverability_pool(self):
        """Layer 2: Free tier is blocked (402/403) on deliverability endpoints & activation; Pro tier succeeds."""
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace
        from campaigns.backend.routers.elein import get_supabase_client, activate_campaign
        from fastapi import HTTPException

        mock_sb_free = MagicMock()
        mock_sb_free.rpc.return_value.execute.return_value.data = {"tier": "FREE", "balance": 100}

        # 1. Free tier blocked on verify-domain with 402
        app.dependency_overrides[get_current_workspace] = lambda: "ws_real_free_tier"
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb_free
        try:
            client = TestClient(app)
            resp_free_dns = client.post(
                "/api/elein/deliverability/verify-domain",
                json={"domain": "acmecorp.com"},
            )
            self.assertEqual(resp_free_dns.status_code, 402)
            self.assertIn("can_deliverability_pool", str(resp_free_dns.json()))

            # 2. Free tier blocked on evaluate-pool with 402
            resp_free_pool = client.post(
                "/api/elein/deliverability/evaluate-pool",
                json={"strategy": "HEALTH_WEIGHTED"},
            )
            self.assertEqual(resp_free_pool.status_code, 402)
            self.assertIn("can_deliverability_pool", str(resp_free_pool.json()))
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

        # 3. Pro tier succeeds on verify-domain and evaluate-pool
        mock_sb_pro = MagicMock()
        mock_sb_pro.rpc.return_value.execute.return_value.data = {"tier": "PRO", "balance": 5000}
        app.dependency_overrides[get_current_workspace] = lambda: "ws_real_pro_tier"
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb_pro
        try:
            client = TestClient(app)
            resp_pro_dns = client.post(
                "/api/elein/deliverability/verify-domain",
                json={
                    "domain": "acmecorp.com",
                    "mock_records": {
                        "spf": ["v=spf1 include:_spf.google.com ~all"],
                        "dkim": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890abcdef"],
                        "dmarc": ["v=DMARC1; p=reject;"],
                        "cname": "track.elein.ai",
                        "ssl_verified": True,
                    },
                },
            )
            self.assertEqual(resp_pro_dns.status_code, 200)

            resp_pro_pool = client.post(
                "/api/elein/deliverability/evaluate-pool",
                json={
                    "candidate_inboxes": [
                        {
                            "id": "inb-pro",
                            "workspace_id": "ws_real_pro_tier",
                            "email": "rep@acme.com",
                            "status": "ACTIVE",
                            "daily_limit": 50,
                            "sent_today": 5,
                        }
                    ]
                },
            )
            self.assertEqual(resp_pro_pool.status_code, 200)
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

        # 4. Free tier blocked on activate_campaign with deliverability pool node or metadata
        act_db = MagicMock()

        def table_router(name):
            t = MagicMock()
            if name == "campaigns":
                q = MagicMock()
                q.eq.return_value.eq.return_value.execute.return_value.data = [{
                    "id": "camp_pool_1",
                    "status": "DRAFT",
                    "nodes_json": [{"id": "n1", "type": "send_email", "data": {"use_sender_pool": True}}],
                    "lead_list_id": "list_1",
                    "metadata": {"use_deliverability_pool": True},
                }]
                cnt_res = MagicMock()
                cnt_res.count = 0
                q.eq.return_value.eq.return_value.neq.return_value.execute.return_value = cnt_res
                t.select.return_value = q
            elif name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"tier": "FREE"}]
            elif name == "campaign_nodes":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"node_type": "send_email"}]
            return t

        act_db.table.side_effect = table_router
        with self.assertRaises(HTTPException) as cm_act:
            activate_campaign(campaign_id="camp_pool_1", workspace_id="ws_real_free_tier", client=act_db)
        self.assertEqual(cm_act.exception.status_code, 403)
        self.assertIn("Deliverability Pool", str(cm_act.exception.detail))


if __name__ == "__main__":
    unittest.main()

