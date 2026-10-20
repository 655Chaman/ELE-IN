"""
test_stage19_dynamic_segmentation_preview.py — Stage 19 Paranoia Test Suite.
Validates Dynamic Rules Real-Time Simulation & Preview Engine under the
Three-Layer Logic Architecture (Paranoia Framework).

- Layer 0: Foundational evaluation, workspace-level simulation, list-scoped member reconciliation.
- Layer 1: Environmental bounds clamping, schema drift resilience (opportunity_id / lead_id).
- Layer 2: Pro tier gating, DoS prevention, and zero-mutation guarantees.
"""

import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from leads.backend.services.lead_segmentation_service import (
    preview_dynamic_segment,
    filter_leads_in_memory,
    SENIORITY_C_SUITE,
    SENIORITY_VP
)
from leads.backend.routers.leads import router, DynamicRulesEvaluateRequest


class TestStage19DynamicSegmentationPreview(unittest.TestCase):
    """
    Stage 19 Paranoia Verification Suite:
    Tests real-time dry-run preview simulation, workspace-level evaluation,
    schema drift resilience, tier permissions, and strict zero DB mutations.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws_test_stage19"
        self.list_id = "list_stage19_preview"

    # =========================================================================
    # Layer 0: Foundational Layer (Workspace Simulation & Reconciliation)
    # =========================================================================

    def test_layer0_workspace_level_preview_evaluates_rules_without_list_id(self):
        """
        Layer 0 Foundational:
        Evaluates dynamic segmentation rules across workspace leads when list_id is omitted.
        Verifies match count, percentage, distribution breakdowns, and sample prospect cards.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table

        # Mock workspace leads
        mock_table.execute.return_value = MagicMock(data=[
            {"id": "lead_01", "job_title": "CEO", "company_size": "51-200", "intent_score": 90.0, "email": "ceo@corp.com"},
            {"id": "lead_02", "job_title": "VP Engineering", "company_size": "11-50", "intent_score": 75.0, "email": "vp@startup.io"},
            {"id": "lead_03", "job_title": "Junior Developer", "company_size": "1-10", "intent_score": 20.0, "email": "jr@dev.org"}
        ])

        rules = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "in", "value": ["c_suite", "vp"]}
            ]
        }

        # Calling without list_id
        preview = preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id=None,
            rule_config=rules,
            supabase=self.mock_supabase,
            limit=500
        )

        self.assertEqual(preview["status"], "success")
        self.assertIsNone(preview["list_id"])
        self.assertEqual(preview["total_workspace_leads"], 3)
        self.assertEqual(preview["matching_count"], 2)
        self.assertEqual(preview["match_percentage"], 66.67)
        self.assertEqual(preview["current_list_members_count"], 0)
        self.assertEqual(preview["potential_added_count"], 2)
        self.assertEqual(preview["potential_removed_count"], 0)
        self.assertIn("execution_time_ms", preview)
        self.assertEqual(len(preview["sample_leads"]), 2)
        self.assertEqual(preview["sample_leads"][0]["seniority"], "c_suite")

    def test_layer0_list_scoped_preview_reconciles_existing_members(self):
        """
        Layer 0 Foundational:
        When list_id is provided, reconciles qualifying leads against current list_members,
        accurately computing potential_added_count and potential_removed_count.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table

        # 1. leads query, 2. list_members query
        mock_table.execute.side_effect = [
            MagicMock(data=[
                {"id": "lead_01", "job_title": "CEO", "company_size": "51-200", "intent_score": 90.0},
                {"id": "lead_02", "job_title": "VP Sales", "company_size": "11-50", "intent_score": 75.0},
                {"id": "lead_03", "job_title": "Intern", "company_size": "1-10", "intent_score": 10.0}
            ]),
            MagicMock(data=[
                {"opportunity_id": "lead_01"},
                {"opportunity_id": "lead_disqualified_09"}
            ])
        ]

        rules = {
            "match_type": "ALL",
            "conditions": [
                {"field": "seniority", "operator": "in", "value": ["c_suite", "vp"]}
            ]
        }

        preview = preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id=self.list_id,
            rule_config=rules,
            supabase=self.mock_supabase
        )

        self.assertEqual(preview["status"], "success")
        self.assertEqual(preview["list_id"], self.list_id)
        self.assertEqual(preview["current_list_members_count"], 2)
        self.assertEqual(preview["matching_count"], 2)  # lead_01 and lead_02
        self.assertEqual(preview["potential_added_count"], 1)  # lead_02
        self.assertEqual(preview["potential_removed_count"], 1)  # lead_disqualified_09

    def test_layer0_router_segments_preview_endpoint_registered(self):
        """
        Layer 0 Foundational:
        Verifies that /segments/preview is registered in the leads router.
        """
        route_paths = [r.path for r in router.routes]
        self.assertIn("/segments/preview", route_paths)

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Limits & Schema Drift)
    # =========================================================================

    def test_layer1_limit_clamping_prevents_memory_exhaustion(self):
        """
        Layer 1 Environmental Failure:
        Protects against extreme limits (> 2,000) or negative limits, safely
        bounding the query limit between 1 and 2,000.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        # Test limit > 2000 clamped to 2000
        preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id=None,
            rule_config={},
            supabase=self.mock_supabase,
            limit=999999
        )
        mock_table.limit.assert_called_with(2000)

        # Test limit < 1 clamped to 1
        preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id=None,
            rule_config={},
            supabase=self.mock_supabase,
            limit=-50
        )
        mock_table.limit.assert_called_with(1)

    def test_layer1_schema_resilience_coalesces_opportunity_and_lead_id(self):
        """
        Layer 1 Environmental Failure:
        Handles database schema variations seamlessly by coalescing opportunity_id
        and lead_id in list_members records without throwing KeyErrors.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table

        mock_table.execute.side_effect = [
            # leads
            MagicMock(data=[{"id": "lead_10", "job_title": "CTO"}]),
            # list_members with mixed columns
            MagicMock(data=[
                {"opportunity_id": "lead_10", "lead_id": None},
                {"opportunity_id": None, "lead_id": "lead_20"}
            ])
        ]

        rules = {"conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}]}

        preview = preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id="list_mixed_schema",
            rule_config=rules,
            supabase=self.mock_supabase
        )

        self.assertEqual(preview["current_list_members_count"], 2)
        self.assertEqual(preview["matching_count"], 1)
        self.assertEqual(preview["potential_removed_count"], 1)  # lead_20

    # =========================================================================
    # Layer 2: Human Paranoia (Tier Gating, Invariants & Malformed Input)
    # =========================================================================

    def test_layer2_preview_zero_db_mutations_invariant(self):
        """
        Layer 2 Human Paranoia:
        Guarantees that preview evaluation has zero database mutations
        (never calls insert, update, delete, or upsert).
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[
            {"id": "lead_01", "job_title": "Founder", "company_size": "1-10"}
        ])

        preview_dynamic_segment(
            workspace_id=self.workspace_id,
            list_id="list_invariant_test",
            rule_config={"conditions": []},
            supabase=self.mock_supabase
        )

        # Invariant verification: Zero mutation methods called
        mock_table.insert.assert_not_called()
        mock_table.update.assert_not_called()
        mock_table.delete.assert_not_called()
        mock_table.upsert.assert_not_called()

    def test_layer2_tier_gating_rejects_free_tier(self):
        """
        Layer 2 Human Paranoia:
        Verifies that non-Pro/Enterprise workspaces are blocked from dynamic
        segmentation evaluation via _check_workspace_tier_permission (HTTP 402).
        """
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace, get_supabase_client

        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"tier": "FREE"})
        mock_supabase.rpc.return_value = mock_rpc

        app.dependency_overrides[get_current_workspace] = lambda: "ws_live_free_tier"
        app.dependency_overrides[get_supabase_client] = lambda: mock_supabase

        try:
            client = TestClient(app)
            resp = client.post("/api/leads/segments/preview", json={
                "rules": {"conditions": []}
            })
            self.assertEqual(resp.status_code, 402)
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                self.assertEqual(detail.get("error"), "FEATURE_TIER_GATED")
                self.assertIn("can_dynamic_lead_segmentation", detail.get("message", ""))
            else:
                self.assertIn("can_dynamic_lead_segmentation", str(detail))
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
