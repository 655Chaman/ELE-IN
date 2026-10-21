"""
Step 11D — Overdraft Boundary Consistency & Tier-Aware Credit Guard (M-04 Hardening)
Three-Layer Logic Architecture (Paranoia Framework) Automated Verification Suite

Layer 0: Foundational Mechanics
- Free tier allowed floor is strictly 0 (no overdraft allowed).
- Paid tiers (PRO, GROWTH, ENTERPRISE, AGENCY, UNLIMITED, SCALE) allowed floor is -500.
- Centralized check_overdraft_allowance correctly projects balance and evaluates floors.

Layer 1: Environmental Failure Analysis
- Schema drift tolerance (tier vs plan vs plan_tier).
- Suspended / paused / pending_deletion workspaces fail closed.
- Orchestrator _workspace_has_credits respects exact boundaries (-500 for paid, > 0 for free).

Layer 2: Human Paranoia
- Extreme values, string whitespace/casing normalization.
- Zero and negative cost protection.
- Malformed workspace IDs fail closed.
- activate_campaign rejects free debt while allowing legitimate paid overdraft.
"""

import unittest
import json
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from core.backend.services.credit_service import (
    get_workspace_overdraft_floor,
    check_overdraft_allowance,
    clamp_negative_balance,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.routers.elein import activate_campaign


class TestOverdraftBoundaryConsistencyHardening(unittest.TestCase):

    # ─── LAYER 0: FOUNDATIONAL MECHANICS ─────────────────────────────────────────

    def test_get_workspace_overdraft_floor_mappings(self):
        """Layer 0: Paid tiers get -500 overdraft floor, Free/unknown get 0."""
        for paid in ["PRO", "pro", " Pro ", "GROWTH", "enterprise", "AGENCY", "UNLIMITED", "SCALE"]:
            self.assertEqual(
                get_workspace_overdraft_floor(paid),
                -500,
                f"Expected -500 floor for {paid}"
            )

        for free in ["FREE", "free", "starter", "trial", "", None, "unknown_tier"]:
            self.assertEqual(
                get_workspace_overdraft_floor(free),
                0,
                f"Expected 0 floor for {free}"
            )

    def test_check_overdraft_allowance_free_tier_boundary(self):
        """Layer 0: Free tier cannot overdraft past 0."""
        mock_supabase = MagicMock()
        # Free tier with 5 credits
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 5, "tier": "FREE", "status": "active"}]
        )

        # 5 credits, cost 5 -> balance becomes 0 (>= 0) -> Allowed
        allowed, bal, reason = check_overdraft_allowance("ws-free-1", cost=5, supabase_client=mock_supabase)
        self.assertTrue(allowed)
        self.assertEqual(bal, 5)
        self.assertEqual(reason, "ok")

        # Free tier with 4 credits
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 4, "tier": "FREE", "status": "active"}]
        )
        # 4 credits, cost 5 -> balance becomes -1 (< 0) -> Rejected
        allowed, bal, reason = check_overdraft_allowance("ws-free-1", cost=5, supabase_client=mock_supabase)
        self.assertFalse(allowed)
        self.assertEqual(bal, 4)
        self.assertEqual(reason, "insufficient_credits")

    def test_check_overdraft_allowance_paid_tier_boundary(self):
        """Layer 0: Paid tier can overdraft down to exactly -500."""
        mock_supabase = MagicMock()
        # Pro tier at -495
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -495, "tier": "PRO", "status": "active"}]
        )
        # -495, cost 5 -> balance becomes -500 (>= -500) -> Allowed
        allowed, bal, reason = check_overdraft_allowance("ws-pro-1", cost=5, supabase_client=mock_supabase)
        self.assertTrue(allowed)
        self.assertEqual(bal, -495)
        self.assertEqual(reason, "ok")

        # Pro tier at -496
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -496, "tier": "PRO", "status": "active"}]
        )
        # -496, cost 5 -> balance becomes -501 (< -500) -> Rejected
        allowed, bal, reason = check_overdraft_allowance("ws-pro-1", cost=5, supabase_client=mock_supabase)
        self.assertFalse(allowed)
        self.assertEqual(bal, -496)
        self.assertEqual(reason, "insufficient_credits")

        # Pro tier at -500, cost 1 -> -501 (< -500) -> Rejected
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -500, "tier": "PRO", "status": "active"}]
        )
        allowed, bal, reason = check_overdraft_allowance("ws-pro-1", cost=1, supabase_client=mock_supabase)
        self.assertFalse(allowed)
        self.assertEqual(bal, -500)
        self.assertEqual(reason, "insufficient_credits")

    # ─── LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS ─────────────────────────────────

    def test_schema_drift_tolerance_plan_columns(self):
        """Layer 1: Correctly reads tier from 'plan' or 'plan_tier' if 'tier' is absent."""
        mock_supabase = MagicMock()
        # Fallback to plan column
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -200, "plan": "growth", "status": "active"}]
        )
        allowed, bal, reason = check_overdraft_allowance("ws-drift-1", cost=10, supabase_client=mock_supabase)
        self.assertTrue(allowed)
        self.assertEqual(bal, -200)

        # Fallback to plan_tier column
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"credits": -300, "plan_tier": "enterprise", "status": "active"}]
        )
        allowed, bal, reason = check_overdraft_allowance("ws-drift-2", cost=10, supabase_client=mock_supabase)
        self.assertTrue(allowed)
        self.assertEqual(bal, -300)

    def test_suspended_or_paused_workspace_fails_closed(self):
        """Layer 1: Suspended or paused workspace fails closed even with positive balance."""
        mock_supabase = MagicMock()
        for bad_status in ["suspended", "paused", "pending_deletion"]:
            mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"data_cleaning_credits": 10000, "tier": "PRO", "status": bad_status}]
            )
            allowed, bal, reason = check_overdraft_allowance("ws-bad-status", cost=1, supabase_client=mock_supabase)
            self.assertFalse(allowed)
            self.assertEqual(reason, f"workspace_{bad_status}")

    def test_orchestrator_preflight_boundary_alignment(self):
        """Layer 1: EleInOrchestrator._workspace_has_credits adheres strictly to boundaries."""
        orch = EleInOrchestrator.__new__(EleInOrchestrator)
        orch.supabase = MagicMock()
        orch._credit_cache = {}
        orch._credit_cache_ttl = 60

        # Paid tier at -500: permitted
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -500, "tier": "PRO", "status": "active"}]
        )
        self.assertTrue(orch._workspace_has_credits("ws-orch-1"))

        # Paid tier at -501: halted
        orch._credit_cache.clear()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": -501, "tier": "PRO", "status": "active"}]
        )
        self.assertFalse(orch._workspace_has_credits("ws-orch-2"))

        # Free tier at 0: halted
        orch._credit_cache.clear()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 0, "tier": "FREE", "status": "active"}]
        )
        self.assertFalse(orch._workspace_has_credits("ws-orch-3"))

        # Free tier at 1: permitted
        orch._credit_cache.clear()
        orch.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 1, "tier": "FREE", "status": "active"}]
        )
        self.assertTrue(orch._workspace_has_credits("ws-orch-4"))

    # ─── LAYER 2: HUMAN PARANOIA ─────────────────────────────────────────────────

    def test_zero_and_negative_cost_sanitization(self):
        """Layer 2: Zero or negative cost does not cause arithmetic overflows or deductions."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"data_cleaning_credits": 100, "tier": "FREE", "status": "active"}]
        )
        allowed, bal, reason = check_overdraft_allowance("ws-zero-cost", cost=0, supabase_client=mock_supabase)
        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")

        allowed, bal, reason = check_overdraft_allowance("ws-neg-cost", cost=-50, supabase_client=mock_supabase)
        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")

    def test_missing_or_none_workspace_id_fails_closed(self):
        """Layer 2: Missing or None workspace_id fails closed immediately."""
        allowed, bal, reason = check_overdraft_allowance("", cost=5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "missing_workspace_id")

        allowed, bal, reason = check_overdraft_allowance(None, cost=5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "missing_workspace_id")

    def test_activate_campaign_tier_aware_overdraft(self):
        """Layer 2: activate_campaign rejects Free debt while allowing legitimate Paid overdraft."""
        from collections import defaultdict
        client = MagicMock()
        tables = defaultdict(MagicMock)

        client.table.side_effect = lambda name: tables[name]
        nodes = [{"id": "n1", "type": "linkedin_message", "data": {}}]
        nodes_str = json.dumps(nodes)

        # 1. Free tier with negative balance (-10) is rejected
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_free", "status": "DRAFT", "nodes_json": nodes_str}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
            count=0
        )
        tables["campaign_nodes"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_1"}]
        )
        tables["accounts"].select.return_value.in_.return_value.eq.return_value.or_.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1"}]
        )
        client.rpc.return_value.execute.return_value = MagicMock(
            data={"balance": -10, "tier": "FREE"}
        )

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_free", "ws_free", client=client)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "insufficient_credits")

        # 2. Paid tier with -400 balance is allowed to activate
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_pro", "status": "DRAFT", "nodes_json": nodes_str}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO"}]
        )
        client.rpc.return_value.execute.return_value = MagicMock(
            data={"balance": -400, "tier": "PRO"}
        )
        tables["campaign_enrollments"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["campaigns"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        res = activate_campaign("camp_pro", "ws_pro", client=client)
        self.assertEqual(res, {"status": "activated"})

        # 3. Paid tier exceeding -500 (e.g. -501) is rejected
        client.rpc.return_value.execute.return_value = MagicMock(
            data={"balance": -501, "tier": "PRO"}
        )
        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_pro", "ws_pro", client=client)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "insufficient_credits")


if __name__ == "__main__":
    unittest.main()
