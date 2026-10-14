"""
test_horizon26_lead_segmentation_dynamic_rules.py — Horizon 26 Test Suite
Smart Lead List Segmentation, Dynamic Rule Filter Engine & Campaign Auto-Enrollment.
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from leads.backend.services.lead_segmentation_service import (
    parse_job_title_seniority,
    normalize_company_size_tier,
    normalize_intent_tier,
    normalize_connection_degree,
    normalize_verification_status,
    extract_lead_attributes,
    evaluate_lead_condition,
    evaluate_lead_against_rules,
    filter_leads_in_memory,
    preview_dynamic_segment,
    sync_dynamic_segment_members,
    SENIORITY_C_SUITE,
    SENIORITY_FOUNDER,
    SENIORITY_VP,
    SENIORITY_DIRECTOR,
    SENIORITY_MANAGER,
    SENIORITY_CONTRIBUTOR,
    SENIORITY_UNKNOWN,
    COMPANY_SIZE_1_10,
    COMPANY_SIZE_11_50,
    COMPANY_SIZE_51_200,
    COMPANY_SIZE_201_500,
    COMPANY_SIZE_501_1000,
    COMPANY_SIZE_1001_5000,
    COMPANY_SIZE_5001_PLUS,
    COMPANY_SIZE_UNKNOWN,
    INTENT_HOT,
    INTENT_WARM,
    INTENT_COLD
)


class TestHorizon26LeadSegmentationDynamicRules(unittest.TestCase):
    """
    Horizon 26 Verification Suite: Dynamic rule filter engine, Seniority parser,
    Headcount normalizer, CollisionGuard auto-enrollment, and Disqualified pause guards.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_test_horizon26"
        self.list_id = "list_seg_test_1"
        self.campaign_id = "camp_auto_enroll_1"

    # =========================================================================
    # Layer 0: The Foundational Layer (Parsing, Normalization & Filtering)
    # =========================================================================

    def test_parse_job_title_seniority(self):
        """Layer 0: Accurately classifies job titles into standard seniority tiers."""
        # C-Suite
        self.assertEqual(parse_job_title_seniority("Chief Executive Officer"), SENIORITY_C_SUITE)
        self.assertEqual(parse_job_title_seniority("CTO"), SENIORITY_C_SUITE)
        self.assertEqual(parse_job_title_seniority("Chief Revenue Officer"), SENIORITY_C_SUITE)
        self.assertEqual(parse_job_title_seniority("CFO & Co-Founder"), SENIORITY_C_SUITE)

        # Founder
        self.assertEqual(parse_job_title_seniority("Founder & Owner"), SENIORITY_FOUNDER)
        self.assertEqual(parse_job_title_seniority("Co-Founder"), SENIORITY_FOUNDER)
        self.assertEqual(parse_job_title_seniority("Managing Partner"), SENIORITY_FOUNDER)

        # VP
        self.assertEqual(parse_job_title_seniority("Vice President of Sales"), SENIORITY_VP)
        self.assertEqual(parse_job_title_seniority("VP, Engineering"), SENIORITY_VP)
        self.assertEqual(parse_job_title_seniority("SVP Marketing"), SENIORITY_VP)

        # Director
        self.assertEqual(parse_job_title_seniority("Director of Product"), SENIORITY_DIRECTOR)
        self.assertEqual(parse_job_title_seniority("Head of Growth"), SENIORITY_DIRECTOR)
        self.assertEqual(parse_job_title_seniority("Managing Director"), SENIORITY_DIRECTOR)

        # Manager
        self.assertEqual(parse_job_title_seniority("Engineering Manager"), SENIORITY_MANAGER)
        self.assertEqual(parse_job_title_seniority("Tech Lead"), SENIORITY_MANAGER)
        self.assertEqual(parse_job_title_seniority("Customer Success Lead"), SENIORITY_MANAGER)

        # Contributor (Critical distinction: Account Executive is Contributor, NOT C-Suite!)
        self.assertEqual(parse_job_title_seniority("Account Executive"), SENIORITY_CONTRIBUTOR)
        self.assertEqual(parse_job_title_seniority("Senior Software Engineer"), SENIORITY_CONTRIBUTOR)
        self.assertEqual(parse_job_title_seniority("Product Designer"), SENIORITY_CONTRIBUTOR)
        self.assertEqual(parse_job_title_seniority("SDR"), SENIORITY_CONTRIBUTOR)

        # Unknown / None / Empty
        self.assertEqual(parse_job_title_seniority(""), SENIORITY_UNKNOWN)
        self.assertEqual(parse_job_title_seniority(None), SENIORITY_UNKNOWN)
        self.assertEqual(parse_job_title_seniority("Some Random Role 123"), SENIORITY_UNKNOWN)

    def test_normalize_company_size_tier(self):
        """Layer 0: Normalizes numeric counts, range strings, and messy text into standard tiers."""
        # Integers
        self.assertEqual(normalize_company_size_tier(5), COMPANY_SIZE_1_10)
        self.assertEqual(normalize_company_size_tier(25), COMPANY_SIZE_11_50)
        self.assertEqual(normalize_company_size_tier(150), COMPANY_SIZE_51_200)
        self.assertEqual(normalize_company_size_tier(350), COMPANY_SIZE_201_500)
        self.assertEqual(normalize_company_size_tier(800), COMPANY_SIZE_501_1000)
        self.assertEqual(normalize_company_size_tier(2500), COMPANY_SIZE_1001_5000)
        self.assertEqual(normalize_company_size_tier(10000), COMPANY_SIZE_5001_PLUS)

        # Range strings
        self.assertEqual(normalize_company_size_tier("1-10"), COMPANY_SIZE_1_10)
        self.assertEqual(normalize_company_size_tier("11-50 employees"), COMPANY_SIZE_11_50)
        self.assertEqual(normalize_company_size_tier("51-200"), COMPANY_SIZE_51_200)
        self.assertEqual(normalize_company_size_tier("201-500"), COMPANY_SIZE_201_500)
        self.assertEqual(normalize_company_size_tier("501-1000"), COMPANY_SIZE_501_1000)
        self.assertEqual(normalize_company_size_tier("1,001-5,000"), COMPANY_SIZE_1001_5000)
        self.assertEqual(normalize_company_size_tier("10k+"), COMPANY_SIZE_5001_PLUS)
        self.assertEqual(normalize_company_size_tier("5000+"), COMPANY_SIZE_5001_PLUS)

        # Empty / Unknown
        self.assertEqual(normalize_company_size_tier(None), COMPANY_SIZE_UNKNOWN)
        self.assertEqual(normalize_company_size_tier("N/A"), COMPANY_SIZE_UNKNOWN)
        self.assertEqual(normalize_company_size_tier(-10), COMPANY_SIZE_UNKNOWN)

    def test_evaluate_lead_against_rules_all_and_any(self):
        """Layer 0: Evaluates complex boolean AST rules with 'ALL' (AND) and 'ANY' (OR)."""
        lead_c_suite = {
            "id": "lead_1",
            "job_title": "Chief Technology Officer",
            "company_size": "51-200",
            "intent_score": 85.0,
            "connection_degree": "2nd",
            "email_verification_status": "VALID"
        }

        lead_sdr = {
            "id": "lead_2",
            "job_title": "Sales Development Representative",
            "company_size": "1-10",
            "intent_score": 30.0,
            "connection_degree": "3rd",
            "email_verification_status": "UNVERIFIED"
        }

        rule_target_execs = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "in", "value": ["c_suite", "vp"]},
                {"field": "company_size", "operator": "equals", "value": "51-200"},
                {"field": "intent_score", "operator": ">=", "value": 75.0},
                {"field": "email_verification_status", "operator": "equals", "value": "VALID"}
            ]
        }

        self.assertTrue(evaluate_lead_against_rules(lead_c_suite, rule_target_execs))
        self.assertFalse(evaluate_lead_against_rules(lead_sdr, rule_target_execs))

        # 'ANY' rule matching either hot intent OR founder
        rule_any = {
            "match_type": "ANY",
            "conditions": [
                {"field": "seniority", "operator": "equals", "value": "founder"},
                {"field": "intent_tier", "operator": "equals", "value": "HOT"}
            ]
        }
        self.assertTrue(evaluate_lead_against_rules(lead_c_suite, rule_any))
        self.assertFalse(evaluate_lead_against_rules(lead_sdr, rule_any))

    def test_between_operator_intent_score(self):
        """Layer 0: Evaluates 'between' operator for numerical intent score ranges."""
        lead = {"id": "lead_warm", "intent_score": 60.0}
        rule_warm = {
            "match_type": "ALL",
            "conditions": [
                {"field": "intent_score", "operator": "between", "value": [45.0, 75.0]}
            ]
        }
        self.assertTrue(evaluate_lead_against_rules(lead, rule_warm))

        lead_cold = {"id": "lead_cold", "intent_score": 20.0}
        self.assertFalse(evaluate_lead_against_rules(lead_cold, rule_warm))

    # =========================================================================
    # Layer 1: Environmental Failure Analysis & Collision Guards
    # =========================================================================

    @patch("campaigns.backend.services.collision_guard.get_conflicting_active_leads")
    def test_collision_guard_suppresses_conflicting_auto_enrollment(self, mock_get_conflicts):
        """Layer 1: When a lead is active in another campaign, auto-enrollment is suppressed."""
        mock_get_conflicts.return_value = {"lead_conflicting_1"}

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.update.return_value = mock_table

        mock_table.execute.side_effect = [
            # 1. lead_lists select
            MagicMock(data=[{
                "id": self.list_id,
                "name": "Dynamic VIPs",
                "type": "dynamic",
                "metadata": {
                    "dynamic_rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]
                    },
                    "auto_enroll_campaign_id": self.campaign_id
                }
            }]),
            # 2. leads select (2 matching leads: lead_clean and lead_conflicting_1)
            MagicMock(data=[
                {"id": "lead_clean", "job_title": "CEO", "workspace_id": self.workspace_id},
                {"id": "lead_conflicting_1", "job_title": "CTO", "workspace_id": self.workspace_id}
            ]),
            # 3. current list_members (currently empty)
            MagicMock(data=[]),
            # 4. list_members insert (2 members)
            MagicMock(data=[]),
            # 5. lead_lists update row_count
            MagicMock(data=[]),
            # 6. campaigns select (verify auto_enroll_campaign_id)
            MagicMock(data=[{"id": self.campaign_id, "status": "ACTIVE"}]),
            # 7. campaign_enrollments select (check if already enrolled)
            MagicMock(data=[]),
            # 8. campaign_enrollments upsert (only lead_clean enrolled!)
            MagicMock(data=[]),
            # 9. campaign_execution_states upsert
            MagicMock(data=[]),
            # 10. action_log insert
            MagicMock(data=[])
        ]

        res = sync_dynamic_segment_members(
            list_id=self.list_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
            auto_enroll=True
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["qualified_leads_count"], 2)
        self.assertEqual(res["added_to_list"], 2)
        self.assertEqual(res["auto_enrolled_count"], 1)  # Only lead_clean!
        self.assertEqual(res["collision_suppressed_count"], 1)  # lead_conflicting_1 suppressed!

    @patch("campaigns.backend.routers.elein._pause_lead_execution_core")
    def test_disqualified_lead_auto_pause(self, mock_pause):
        """Layer 1: Leads disqualified from the dynamic list are safely paused in linked campaign."""
        mock_pause.return_value = {"status": "success", "paused_count": 1}

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.update.return_value = mock_table

        mock_table.execute.side_effect = [
            # 1. lead_lists select
            MagicMock(data=[{
                "id": self.list_id,
                "name": "Dynamic VIPs",
                "metadata": {
                    "dynamic_rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]
                    },
                    "auto_enroll_campaign_id": self.campaign_id
                }
            }]),
            # 2. leads select (lead_demoted is now an SDR!)
            MagicMock(data=[{"id": "lead_demoted", "job_title": "SDR", "workspace_id": self.workspace_id}]),
            # 3. current list_members (lead_demoted was previously a member)
            MagicMock(data=[{"opportunity_id": "lead_demoted"}]),
            # 4. list_members delete lead_demoted
            MagicMock(data=[]),
            # 5. update row_count to 0
            MagicMock(data=[])
        ]

        res = sync_dynamic_segment_members(
            list_id=self.list_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase,
            auto_enroll=True
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["removed_from_list"], 1)
        self.assertEqual(res["paused_disqualified_count"], 1)
        mock_pause.assert_called_once_with(
            lead_id="lead_demoted",
            workspace_id=self.workspace_id,
            client=self.mock_supabase,
            status_override="paused",
            error_reason_override="Disqualified from dynamic segment"
        )

    def test_dirty_lead_attributes_resilience(self):
        """Layer 1: Handles malformed lead attributes, int job titles, and dirty dicts without crashing."""
        dirty_lead = {
            "id": "lead_dirty",
            "job_title": 12345,  # Invalid type
            "company_size": {"bad": "data"},  # Invalid dict
            "intent_score": "not_a_float",
            "metadata": None,
            "mutual_connections": None
        }

        attrs = extract_lead_attributes(dirty_lead)
        self.assertEqual(attrs["seniority"], SENIORITY_UNKNOWN)
        self.assertEqual(attrs["company_size"], COMPANY_SIZE_UNKNOWN)
        self.assertEqual(attrs["intent_score"], 0.0)
        self.assertEqual(attrs["intent_tier"], INTENT_COLD)

        rule = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "equals", "value": "c_suite"},
                {"field": "intent_score", "operator": ">=", "value": 50.0}
            ]
        }
        # Fails closed safely
        self.assertFalse(evaluate_lead_against_rules(dirty_lead, rule))

    # =========================================================================
    # Layer 2: Human Paranoia (IDOR, Preview Safety & Malformed Inputs)
    # =========================================================================

    def test_cross_workspace_idor_protection(self):
        """Layer 2: Rejects unauthorized access when list belongs to another workspace."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        # Returns empty when queried with foreign workspace
        mock_table.execute.return_value = MagicMock(data=[])

        with self.assertRaises(ValueError) as ctx:
            sync_dynamic_segment_members(
                list_id="foreign_list",
                workspace_id=self.workspace_id,
                supabase=self.mock_supabase
            )
        self.assertIn("Lead list not found or unauthorized", str(ctx.exception))

    def test_preview_dynamic_segment_zero_side_effects(self):
        """Layer 2: Preview endpoint computes match counts and breakdowns with zero DB mutations."""
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table

        mock_table.execute.side_effect = [
            # 1. leads query
            MagicMock(data=[
                {"id": "lead_1", "job_title": "CEO", "company_size": "51-200", "intent_score": 80.0},
                {"id": "lead_2", "job_title": "VP Sales", "company_size": "11-50", "intent_score": 60.0},
                {"id": "lead_3", "job_title": "Intern", "company_size": "1-10", "intent_score": 10.0}
            ]),
            # 2. current list members
            MagicMock(data=[{"opportunity_id": "lead_1"}])
        ]

        rule_execs = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "in", "value": ["c_suite", "vp"]}
            ]
        }

        preview = preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id=self.list_id,
            rule_config=rule_execs,
            supabase=self.mock_supabase
        )

        self.assertEqual(preview["status"], "success")
        self.assertEqual(preview["total_workspace_leads"], 3)
        self.assertEqual(preview["matching_count"], 2)  # CEO and VP Sales
        self.assertEqual(preview["current_list_members_count"], 1)  # lead_1
        self.assertEqual(preview["potential_added_count"], 1)  # lead_2
        self.assertEqual(preview["potential_removed_count"], 0)
        self.assertEqual(preview["breakdown"]["seniority"]["c_suite"], 1)
        self.assertEqual(preview["breakdown"]["seniority"]["vp"], 1)

        # Invariant check: Zero mutations executed
        mock_table.insert.assert_not_called()
        mock_table.update.assert_not_called()
        mock_table.delete.assert_not_called()
        mock_table.upsert.assert_not_called()

    def test_malformed_rule_conditions_handled_safely(self):
        """Layer 2: Sanitizes invalid fields, unknown operators, and caps condition count to 25."""
        lead = {"id": "lead_1", "job_title": "CEO"}

        # Unknown field
        bad_field_rule = {"conditions": [{"field": "hacker_column", "operator": "equals", "value": "pwned"}]}
        self.assertFalse(evaluate_lead_against_rules(lead, bad_field_rule))

        # Unknown operator
        bad_op_rule = {"conditions": [{"field": "seniority", "operator": "exploit_eval", "value": "c_suite"}]}
        self.assertFalse(evaluate_lead_against_rules(lead, bad_op_rule))

        # Empty rule matches all
        self.assertTrue(evaluate_lead_against_rules(lead, {}))
        self.assertTrue(evaluate_lead_against_rules(lead, {"conditions": []}))

    def test_fastapi_endpoints_registered_in_router(self):
        """Layer 2: Verifies dynamic segmentation endpoints are properly mounted in leads router."""
        from leads.backend.routers.leads import router
        route_paths = [r.path for r in router.routes]
        self.assertIn("/lists/{list_id}/dynamic-rules", route_paths)
        self.assertIn("/lists/{list_id}/evaluate-rules", route_paths)
        self.assertIn("/lists/{list_id}/sync-members", route_paths)

    def test_api_dynamic_rules_get_and_post_flow(self):
        """Layer 2: Tests GET and POST /api/leads/lists/{list_id}/dynamic-rules via TestClient."""
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace, get_supabase_client

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        try:
            client = TestClient(app)

            # 1. GET dynamic rules
            mock_table.execute.return_value = MagicMock(data=[{
                "id": self.list_id,
                "name": "VIP Dynamic",
                "type": "dynamic",
                "metadata": {
                    "dynamic_rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]
                    },
                    "auto_enroll_campaign_id": self.campaign_id
                }
            }])
            resp_get = client.get(f"/api/leads/lists/{self.list_id}/dynamic-rules")
            self.assertEqual(resp_get.status_code, 200)
            data_get = resp_get.json()
            self.assertEqual(data_get["status"], "success")
            self.assertEqual(data_get["type"], "dynamic")
            self.assertEqual(data_get["auto_enroll_campaign_id"], self.campaign_id)

            # 2. POST dynamic rules with valid payload
            mock_table.execute.side_effect = [
                # verify list
                MagicMock(data=[{"id": self.list_id, "name": "VIP Dynamic", "metadata": {}}]),
                # verify campaign
                MagicMock(data=[{"id": self.campaign_id, "status": "ACTIVE"}]),
                # update lead_lists
                MagicMock(data=[])
            ]
            resp_post = client.post(
                f"/api/leads/lists/{self.list_id}/dynamic-rules",
                json={
                    "match_type": "ALL",
                    "conditions": [{"field": "seniority", "operator": "in", "value": ["c_suite", "vp"]}],
                    "auto_enroll_campaign_id": self.campaign_id
                }
            )
            self.assertEqual(resp_post.status_code, 200)
            data_post = resp_post.json()
            self.assertEqual(data_post["status"], "success")
            self.assertEqual(data_post["dynamic_rules"]["match_type"], "ALL")

            # 3. POST dynamic rules with foreign campaign -> 400 IDOR defense
            mock_table.execute.side_effect = [
                MagicMock(data=[{"id": self.list_id, "name": "VIP Dynamic", "metadata": {}}]),
                MagicMock(data=[])  # campaign not found in workspace
            ]
            resp_bad_camp = client.post(
                f"/api/leads/lists/{self.list_id}/dynamic-rules",
                json={
                    "match_type": "ALL",
                    "conditions": [],
                    "auto_enroll_campaign_id": "foreign_campaign_id"
                }
            )
            self.assertEqual(resp_bad_camp.status_code, 400)
            err_msg = resp_bad_camp.json().get("error", {}).get("message") or resp_bad_camp.json().get("detail", "")
            self.assertIn("Target auto-enroll campaign does not exist or belongs to another workspace", err_msg)

        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_api_evaluate_rules_preview_flow(self):
        """Layer 2: Tests POST /api/leads/lists/{list_id}/evaluate-rules via TestClient."""
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace, get_supabase_client

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        try:
            client = TestClient(app)

            mock_table.execute.side_effect = [
                # 1. list verify
                MagicMock(data=[{"id": self.list_id, "metadata": {}}]),
                # 2. leads query
                MagicMock(data=[
                    {"id": "lead_1", "job_title": "CEO", "workspace_id": self.workspace_id},
                    {"id": "lead_2", "job_title": "Intern", "workspace_id": self.workspace_id}
                ]),
                # 3. current members query
                MagicMock(data=[])
            ]

            resp = client.post(
                f"/api/leads/lists/{self.list_id}/evaluate-rules",
                json={
                    "rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]
                    }
                }
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["matching_count"], 1)
            self.assertEqual(data["total_workspace_leads"], 2)

        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    def test_api_sync_members_endpoint_flow(self):
        """Layer 2: Tests POST /api/leads/lists/{list_id}/sync-members via TestClient."""
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace, get_supabase_client

        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.update.return_value = mock_table

        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        try:
            client = TestClient(app)

            mock_table.execute.side_effect = [
                # 1. list verify
                MagicMock(data=[{
                    "id": self.list_id,
                    "name": "Dynamic List",
                    "type": "dynamic",
                    "metadata": {
                        "dynamic_rules": {
                            "match_type": "ALL",
                            "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]
                        }
                    }
                }]),
                # 2. leads select
                MagicMock(data=[{"id": "lead_1", "job_title": "CEO", "workspace_id": self.workspace_id}]),
                # 3. current members
                MagicMock(data=[]),
                # 4. list_members insert
                MagicMock(data=[]),
                # 5. update row_count
                MagicMock(data=[])
            ]

            resp = client.post(
                f"/api/leads/lists/{self.list_id}/sync-members",
                json={"auto_enroll": False}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["added_to_list"], 1)
            self.assertEqual(data["qualified_leads_count"], 1)

        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)

    # =========================================================================
    # Layer 1: Monetization & Subscription Tier Paywall Gating (402 Verification)
    # =========================================================================

    def test_tier_gating_free_workspace_raises_402_on_set_rules(self):
        """Paranoia Layer 1: Asserts Free tier workspace receives HTTP 402 on setting dynamic rules."""
        from fastapi import HTTPException
        from leads.backend.routers.leads import set_list_dynamic_rules_endpoint, DynamicRulesConfigRequest

        payload = DynamicRulesConfigRequest(
            match_type="ALL",
            conditions=[{"field": "seniority", "operator": "equals", "value": "c_suite"}]
        )
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}

        with self.assertRaises(HTTPException) as ctx:
            set_list_dynamic_rules_endpoint(
                list_id=self.list_id,
                payload=payload,
                workspace_id="ws_real_free_tier",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_free_workspace_raises_402_on_sync_members(self):
        """Paranoia Layer 1: Asserts Free tier workspace receives HTTP 402 on syncing dynamic members."""
        from fastapi import HTTPException
        from leads.backend.routers.leads import sync_list_members_endpoint

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}

        with self.assertRaises(HTTPException) as ctx:
            sync_list_members_endpoint(
                list_id=self.list_id,
                payload=None,
                workspace_id="ws_real_free_tier",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_free_workspace_raises_402_on_evaluate_preview(self):
        """Paranoia Layer 1: Asserts Free tier workspace receives HTTP 402 on preview evaluation."""
        from fastapi import HTTPException
        from leads.backend.routers.leads import evaluate_list_rules_preview_endpoint

        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}

        with self.assertRaises(HTTPException) as ctx:
            evaluate_list_rules_preview_endpoint(
                list_id=self.list_id,
                payload=None,
                workspace_id="ws_real_free_tier",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_pro_workspace_succeeds_on_set_rules(self):
        """Paranoia Layer 1: Asserts Pro workspace passes tier check and proceeds with execution."""
        from leads.backend.routers.leads import set_list_dynamic_rules_endpoint, DynamicRulesConfigRequest

        payload = DynamicRulesConfigRequest(
            match_type="ALL",
            conditions=[{"field": "seniority", "operator": "equals", "value": "c_suite"}]
        )
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.side_effect = [
            # 1. list check
            MagicMock(data=[{"id": self.list_id, "name": "Dynamic List", "metadata": {}}]),
            # 2. update metadata
            MagicMock(data=[])
        ]

        res = set_list_dynamic_rules_endpoint(
            list_id=self.list_id,
            payload=payload,
            workspace_id="ws_real_pro_tier",
            supabase=mock_supabase
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["type"], "dynamic")

    def test_ui_alias_email_verification_and_3rd_plus_normalization(self):
        """Layer 2: Verifies UI field alias 'email_verification' and '3rd+' connection degree normalization."""
        lead = {
            "id": "lead_ui_alias",
            "job_title": "VP of Engineering",
            "connection_degree": "3rd",
            "email_verification_status": "VALID",
            "intent_score": 82.0
        }
        ui_rule = {
            "match_type": "ALL",
            "conditions": [
                {"field": "email_verification", "operator": "in", "value": ["valid", "catch_all"]},
                {"field": "connection_degree", "operator": "in", "value": ["2nd", "3rd+"]}
            ]
        }
        self.assertTrue(evaluate_lead_against_rules(lead, ui_rule))

    def test_export_dynamic_segment_csv_neutralizes_formula_injection(self):
        """Layer 2: Verifies CSV export neutralizes spreadsheet formula injection (=, +, -, @)."""
        from leads.backend.services.lead_segmentation_service import export_dynamic_segment_csv

        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table

        mock_table.execute.side_effect = [
            # 1. lead_lists query
            MagicMock(data=[{
                "id": self.list_id,
                "name": "Dynamic VIPs",
                "metadata": {
                    "dynamic_rules": {
                        "match_type": "ALL",
                        "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]
                    }
                }
            }]),
            # 2. leads query
            MagicMock(data=[{
                "id": "lead_formula_1",
                "first_name": "=CMD|' /C calc'!A0",
                "last_name": "Doe",
                "job_title": "Chief Executive Officer",
                "company": "@EvilCorp",
                "company_size": "51-200",
                "intent_score": 90.0,
                "connection_degree": "2nd",
                "email": "+hack@evil.io",
                "email_verification_status": "VALID",
                "linkedin_url": "https://linkedin.com/in/johndoe"
            }])
        ]

        csv_out = export_dynamic_segment_csv(
            workspace_id=self.workspace_id,
            list_id=self.list_id,
            supabase=self.mock_supabase
        )
        self.assertIn("Lead ID,First Name,Last Name,Email,Company Name,Job Title,Seniority Tier", csv_out)
        self.assertIn("'=CMD|' /C calc'!A0", csv_out)
        self.assertIn("'@EvilCorp", csv_out)
        self.assertIn("'+hack@evil.io", csv_out)


if __name__ == "__main__":
    unittest.main()


