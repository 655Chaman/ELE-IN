import unittest
from unittest.mock import MagicMock, patch
import json
import os
from datetime import datetime, timezone, timedelta

from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestMultichannelAndCRMNodes(unittest.TestCase):
    """
    Comprehensive test suite for Family F (Multichannel, CRM & Enrichment) nodes
    under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        self.supabase = MagicMock()
        self.worker = MagicMock()
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws-test-fam-f"
        )
        self.executor.account_id = "acc-test-fam-f"

    # ══════════════════════════════════════════════════════════════════════════
    # ZERO-COST EMAIL DISCOVERY
    # ══════════════════════════════════════════════════════════════════════════

    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email")
    def test_zero_cost_discovery_smtp_success_updates_lead_and_exports_vars(self, mock_discover):
        """Layer 0: SMTP discovery finds email, standardizes branch to 'Found', exports {{email}} and {{work_email}}."""
        mock_discover.return_value = "elena.rostova@techcorp.io"
        
        self.supabase.table().select().eq().execute.return_value.data = [{
            "id": "lead-zc-1",
            "first_name": "Elena",
            "last_name": "Rostova",
            "domain": "techcorp.io",
            "email": None
        }]

        data = {"_lead_id": "lead-zc-1"}
        res = self.executor.handle_zero_cost_discovery(data, "https://linkedin.com/in/elena")

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("email"), "elena.rostova@techcorp.io")
        self.assertEqual(res.get("variables", {}).get("email"), "elena.rostova@techcorp.io")
        self.assertEqual(res.get("variables", {}).get("work_email"), "elena.rostova@techcorp.io")
        self.supabase.table("leads").update.assert_called_with({"email": "elena.rostova@techcorp.io", "domain": "techcorp.io"})

    def test_zero_cost_discovery_cache_hit_returns_found_instantly(self):
        """Layer 0: Lead with existing cached email immediately returns 'Found' without network calls."""
        data = {
            "first_name": "Marcus",
            "last_name": "Aurelius",
            "domain": "rome.gov",
            "email": "marcus@rome.gov"
        }
        res = self.executor.handle_zero_cost_discovery(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("source"), "cache")
        self.assertEqual(res.get("variables", {}).get("email"), "marcus@rome.gov")

    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email", return_value=None)
    @patch("integrations.backend.services.elein_crm_service.enrich_with_apollo")
    def test_zero_cost_discovery_smtp_fails_apollo_fallback_succeeds(self, mock_apollo, mock_discover):
        """Layer 1 Environmental: When SMTP verification fails, falls back safely to Apollo and routes to 'Found'."""
        mock_apollo.return_value = {"email": "marcus.dev@apollo-match.io"}

        data = {
            "first_name": "Marcus",
            "last_name": "Developer",
            "domain": "apollo-match.io"
        }
        res = self.executor.handle_zero_cost_discovery(data, "https://linkedin.com/in/marcus")

        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("source"), "apollo")
        self.assertEqual(res.get("email"), "marcus.dev@apollo-match.io")

    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email", return_value=None)
    @patch("integrations.backend.services.elein_crm_service.enrich_with_apollo", return_value=None)
    def test_zero_cost_discovery_both_fail_routes_to_not_found(self, mock_apollo, mock_discover):
        """Layer 1 Environmental: When both discovery mechanisms fail, cleanly returns 'Not found'."""
        data = {
            "first_name": "Ghost",
            "last_name": "Prospect",
            "domain": "nowhere-land.xyz"
        }
        res = self.executor.handle_zero_cost_discovery(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)
        self.assertFalse(res.get("result"))

    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email")
    def test_zero_cost_discovery_sanitizes_messy_protocol_and_query_domains(self, mock_discover):
        """Layer 2 Human Paranoia: Strips protocols, www, and query params from messy operator URLs."""
        mock_discover.return_value = "clean@enterprisecorp.com"
        data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "domain": "https://www.enterprisecorp.com/about/team?utm_source=linkedin"
        }
        res = self.executor.handle_zero_cost_discovery(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        mock_discover.assert_called_with("Jane", "Doe", "enterprisecorp.com")

    # ══════════════════════════════════════════════════════════════════════════
    # PERSONAL EMAIL ENRICHMENT
    # ══════════════════════════════════════════════════════════════════════════

    @patch("core.backend.services.credit_service.check_tier_access", return_value=True)
    def test_find_personal_email_exports_personal_email_variable(self, mock_tier):
        """Layer 0: handle_find_personal_email exports 'personal_email' variable in payload."""
        self.supabase.rpc().execute.return_value.data = {"success": True}
        data = {
            "_node_type": "find_personal_email",
            "email": "founder.personal@gmail.com",
            "is_personal": True
        }
        res = self.executor.handle_find_personal_email(data, "https://linkedin.com/in/founder")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("variables", {}).get("personal_email"), "founder.personal@gmail.com")

    @patch("core.backend.services.credit_service.check_tier_access", return_value=False)
    def test_find_personal_email_tier_restricted_returns_not_found(self, mock_tier):
        """Layer 1 Environmental: Free tier credit restriction returns 'Not found' branch safely."""
        data = {"_node_type": "find_personal_email"}
        res = self.executor.handle_find_personal_email(data, "https://linkedin.com/in/prospect")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)
        self.assertEqual(res.get("reason"), "tier_restricted")

    # ══════════════════════════════════════════════════════════════════════════
    # FIND PHONE NUMBER
    # ══════════════════════════════════════════════════════════════════════════

    def test_find_phone_from_lead_data_returns_found(self):
        """Layer 0: Lead with phone number returns 'Found' and exports clean phone variables."""
        data = {
            "_lead_id": "lead-phone-1",
            "phone": "+1 (555) 019-2834"
        }
        res = self.executor.handle_find_phone(data, "https://linkedin.com/in/lead")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("variables", {}).get("phone"), "+1 (555) 019-2834")
        self.assertEqual(res.get("variables", {}).get("phone_number"), "+1 (555) 019-2834")

    def test_find_phone_absent_returns_not_found(self):
        """Layer 0: Missing phone without external enrichment returns 'Not found'."""
        data = {}
        res = self.executor.handle_find_phone(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)

    @patch("core.backend.services.credit_service.check_tier_access", return_value=False)
    def test_find_phone_external_enrichment_tier_restricted_returns_not_found(self, mock_tier):
        """Layer 1 Environmental: Tier restriction on external phone enrichment returns 'Not found'."""
        data = {"external_enrichment": True}
        res = self.executor.handle_find_phone(data, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)
        self.assertEqual(res.get("reason"), "tier_restricted")

    # ══════════════════════════════════════════════════════════════════════════
    # FIND COMPANY TECH STACK
    # ══════════════════════════════════════════════════════════════════════════

    def test_find_tech_stack_array_serialization_and_match(self):
        """Layer 0 & 1: Serializes JSON list from Apollo/PDL and matches target tools cleanly."""
        data = {
            "tech_stack": ["React", "PostgreSQL", "TailwindCSS", "Node.js"],
            "target_tools": "React, Salesforce"
        }
        res = self.executor.handle_find_tech_stack(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertIn("React", res.get("variables", {}).get("tech_stack"))

    def test_find_tech_stack_target_tools_unmatched_routes_to_not_found(self):
        """Layer 0: When target_tools filter does not match discovered tools, routes to 'Not found'."""
        data = {
            "tech_stack": "WordPress, PHP, MySQL",
            "target_tools": "Kubernetes, Snowflake"
        }
        res = self.executor.handle_find_tech_stack(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)

    def test_find_tech_stack_no_tools_found_routes_to_not_found(self):
        """Layer 2 Paranoia: Missing tech stack data routes cleanly to 'Not found' without throwing."""
        data = {}
        res = self.executor.handle_find_tech_stack(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)

    # ══════════════════════════════════════════════════════════════════════════
    # FIND FUNDING ROUND
    # ══════════════════════════════════════════════════════════════════════════

    def test_find_funding_round_recently_funded(self):
        """Layer 0: Funded company routes to 'Recently funded' and exports funding round."""
        data = {
            "funding_round": "Series B",
            "funding_date": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            "recency_months": 6
        }
        res = self.executor.handle_find_funding_round(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.RECENTLY_FUNDED.value)
        self.assertEqual(res.get("variables", {}).get("funding_round"), "Series B")

    def test_find_funding_round_outside_recency_window_routes_to_no_recent_funding(self):
        """Layer 1 Environmental: Funding older than recency_months cutoff routes to 'No recent funding'."""
        data = {
            "funding_round": "Seed",
            "funding_date": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
            "recency_months": 12
        }
        res = self.executor.handle_find_funding_round(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NO_RECENT_FUNDING.value)

    def test_find_funding_round_bootstrapped_or_none_routes_to_no_recent_funding(self):
        """Layer 2 Paranoia: 'bootstrapped' or 'none' values do not trigger false positive funding branches."""
        for val in ["bootstrapped", "None", "0", "false", ""]:
            data = {"funding_round": val}
            res = self.executor.handle_find_funding_round(data, None)
            self.assertEqual(res.get("branch"), Branch.NO_RECENT_FUNDING.value)

    # ══════════════════════════════════════════════════════════════════════════
    # FIND COMPANY HEADCOUNT
    # ══════════════════════════════════════════════════════════════════════════

    def test_find_headcount_found_exports_headcount_and_company_size(self):
        """Layer 0: Headcount extracted and exported in both headcount and company_size variables."""
        data = {"headcount": "250-500"}
        res = self.executor.handle_find_headcount(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.FOUND.value)
        self.assertEqual(res.get("variables", {}).get("headcount"), "250-500")
        self.assertEqual(res.get("variables", {}).get("company_size"), "250-500")

    def test_find_headcount_missing_or_zero_returns_not_found(self):
        """Layer 2 Paranoia: Missing or zero headcount returns 'Not found'."""
        data = {"headcount": "0"}
        res = self.executor.handle_find_headcount(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_FOUND.value)

    # ══════════════════════════════════════════════════════════════════════════
    # FIND OPEN JOB POSTINGS
    # ══════════════════════════════════════════════════════════════════════════

    def test_find_job_postings_role_filter_matched_routes_to_hiring(self):
        """Layer 0: Open roles matching role_filter keyword route to 'Hiring'."""
        data = {
            "open_roles": "Senior Software Engineer, Account Executive, Sales Development Representative",
            "role_filter": "Sales, SDR"
        }
        res = self.executor.handle_find_job_postings(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.HIRING.value)
        self.assertTrue(res.get("variables", {}).get("is_hiring"))

    def test_find_job_postings_role_filter_unmatched_routes_to_not_hiring(self):
        """Layer 0: Open roles not matching role_filter route to 'Not hiring'."""
        data = {
            "open_roles": "Graphic Designer, Copywriter",
            "role_filter": "Software Engineer, DevOps"
        }
        res = self.executor.handle_find_job_postings(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_HIRING.value)
        self.assertFalse(res.get("variables", {}).get("is_hiring"))

    def test_find_job_postings_worker_fallback(self):
        """Layer 1 Environmental: Falls back to worker check_company_hiring when data is absent."""
        self.worker.check_company_hiring.return_value = {"branch": "Hiring"}
        data = {"role_filter": "Engineering"}
        res = self.executor.handle_find_job_postings(data, "https://linkedin.com/in/prospect")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.HIRING.value)
        self.assertTrue(res.get("variables", {}).get("is_hiring"))

    # ══════════════════════════════════════════════════════════════════════════
    # GET LINKEDIN ACTIVITY SCORE
    # ══════════════════════════════════════════════════════════════════════════

    def test_get_linkedin_activity_active_branch(self):
        """Layer 0: Activity score >= 4 routes to 'Active (>4 posts/month)'."""
        data = {"activity_score": 6.5}
        res = self.executor.handle_get_linkedin_activity(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.ACTIVE_MONTHLY.value)
        self.assertEqual(res.get("variables", {}).get("activity_score"), 6.5)

    def test_get_linkedin_activity_passive_branch(self):
        """Layer 0: Activity score between 1 and 4 routes to 'Passive (1-4)'."""
        data = {"activity_score": 2}
        res = self.executor.handle_get_linkedin_activity(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.PASSIVE_MONTHLY.value)

    def test_get_linkedin_activity_inactive_branch(self):
        """Layer 0: Activity score < 1 routes to 'Inactive (<1)'."""
        data = {"activity_score": 0.2}
        res = self.executor.handle_get_linkedin_activity(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.INACTIVE_MONTHLY.value)

    def test_get_linkedin_activity_worker_fallback(self):
        """Layer 1 Environmental: Falls back to worker check_has_recent_posts."""
        self.worker.check_has_recent_posts.return_value = {"branch": "Active"}
        data = {}
        res = self.executor.handle_get_linkedin_activity(data, "https://linkedin.com/in/creator")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.ACTIVE_MONTHLY.value)

    # ══════════════════════════════════════════════════════════════════════════
    # GET MUTUAL CONNECTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def test_get_mutual_connections_has_mutuals(self):
        """Layer 0: Shared connections > 0 routes to 'Has mutuals' and exports count."""
        data = {"mutual_connections_count": 8}
        res = self.executor.handle_get_mutual_connections(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.HAS_MUTUALS.value)
        self.assertTrue(res.get("variables", {}).get("has_mutuals"))
        self.assertEqual(res.get("variables", {}).get("mutual_connections_count"), 8)

    def test_get_mutual_connections_no_mutuals(self):
        """Layer 0: Zero shared connections routes to 'No mutuals'."""
        data = {"mutual_connections_count": 0}
        res = self.executor.handle_get_mutual_connections(data, None)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NO_MUTUALS.value)
        self.assertFalse(res.get("variables", {}).get("has_mutuals"))

    def test_get_mutual_connections_worker_fallback(self):
        """Layer 1 Environmental: Falls back to worker get_mutual_connection_count."""
        self.worker.get_mutual_connection_count.return_value = {"count": 4}
        data = {}
        res = self.executor.handle_get_mutual_connections(data, "https://linkedin.com/in/lead")
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.HAS_MUTUALS.value)
        self.assertEqual(res.get("variables", {}).get("mutual_connections_count"), 4)

    # ══════════════════════════════════════════════════════════════════════════
    # SEND EMAIL (MULTICHANNEL)
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_email_interpolates_template_recipient(self):
        """Layer 2 Human Paranoia: Interpolates {{lead.email}} before validating email syntax."""
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "", "ENV": "development", "TEST_MODE": "true"}):
            data = {
                "to": "{{lead.email}}",
                "lead": {"email": "interpolated@client.com"},
                "subject": "Hi {{first_name}}",
                "body": "Message body",
                "first_name": "Oliver"
            }
            res = self.executor.handle_send_email(data, "https://linkedin.com/in/oliver")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)
            self.assertEqual(res.get("to"), "interpolated@client.com")

    def test_send_email_clamps_long_subject_and_body(self):
        """Layer 2 Human Paranoia: Clamps subject to 200 chars and body to 50,000 chars."""
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "", "ENV": "development", "TEST_MODE": "true"}):
            data = {
                "email": "test@domain.com",
                "subject": "S" * 350,
                "body": "B" * 60000
            }
            res = self.executor.handle_send_email(data, "https://linkedin.com/in/prospect")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)
            self.assertLessEqual(len(res.get("subject")), 200)

    # ══════════════════════════════════════════════════════════════════════════
    # PUSH TO CRM
    # ══════════════════════════════════════════════════════════════════════════

    def test_push_to_crm_hubspot_normalized_provider(self):
        """Layer 0: Pushes lead to HubSpot and returns 'then' branch."""
        self.supabase.table().select().eq().eq().limit().execute.return_value.data = [{
            "id": "lead-crm-1", "first_name": "Cynthia", "email": "cynthia@tech.com"
        }]
        self.supabase.table().select().eq().single().execute.return_value.data = {
            "hubspot_token": "hs-token-abc"
        }
        with patch("campaigns.backend.services.elein_executor.push_to_hubspot", return_value=True):
            data = {"provider": "hubspot", "pipeline_stage": "Qualified Lead"}
            res = self.executor.handle_push_to_crm(data, "https://linkedin.com/in/cynthia")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_push_to_crm_unknown_provider_fails_cleanly(self):
        """Layer 2 Human Paranoia: Invalid provider name returns 'failed' branch without unhandled exception."""
        data = {"provider": "NonExistentCRMProvider"}
        res = self.executor.handle_push_to_crm(data, "https://linkedin.com/in/user")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)

    # ══════════════════════════════════════════════════════════════════════════
    # SLACK ALERT & WEBHOOK
    # ══════════════════════════════════════════════════════════════════════════

    def test_send_slack_alert_missing_webhook_skips_without_crashing(self):
        """Layer 1 Environmental: Missing Slack webhook URL safely skips and proceeds down 'then' branch."""
        self.supabase.table().select().eq().limit().execute.return_value.data = []
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": ""}):
            data = {"message": "Test notification"}
            res = self.executor.handle_send_slack_alert(data, "https://linkedin.com/in/test")
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.THEN.value)

    def test_send_webhook_invalid_url_fails_gracefully(self):
        """Layer 1 Environmental: Malformed URL returns 'failed' branch without system crash."""
        data = {"url": "not-a-valid-url"}
        res = self.executor.handle_send_webhook(data, "https://linkedin.com/in/test")
        self.assertEqual(res.get("status"), "error")
        self.assertEqual(res.get("branch"), Branch.FAILED.value)


if __name__ == "__main__":
    unittest.main()
