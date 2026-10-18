import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import json
import uuid
from fastapi import HTTPException

from campaigns.backend.routers.elein import (
    create_campaign,
    update_campaign,
    activate_campaign,
    enroll_leads,
    enroll_list_leads,
    allocate_leads_weighted_across_fleet,
    EnrollLeadsRequest,
    EnrollListRequest,
)
from campaigns.backend.schemas.elein import (
    CampaignCreate,
    EleInNode,
    EleInEdge,
)


class TestHorizon14CampaignEngine(unittest.TestCase):
    """
    Test suite for Horizon 14: Campaign Execution DAG Engine, Cross-Tenant Isolation,
    Collision Guards & Multi-Sender Quota Allocation.
    Three-Layer Paranoia Architecture.
    """

    def _setup_multi_table_mock(self):
        """Helper to create isolated mock per table name to prevent chaining collisions."""
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)

        def get_table(tbl_name):
            return tables[tbl_name]

        mock_svc.table.side_effect = get_table
        return mock_svc, tables

    # =========================================================================
    # 1. Multi-Sender Weighted Quota Allocation (Layer 0, 1, 2)
    # =========================================================================

    def test_allocate_leads_empty_inputs(self):
        """Layer 2: Empty accounts or 0 leads returns empty list cleanly."""
        self.assertEqual(allocate_leads_weighted_across_fleet([], 10), [])
        self.assertEqual(allocate_leads_weighted_across_fleet([{"id": "acc_1", "status": "ACTIVE"}], 0), [])
        self.assertEqual(allocate_leads_weighted_across_fleet([{"id": "acc_1", "status": "ACTIVE"}], -5), [])

    def test_allocate_leads_filters_inactive_accounts(self):
        """Layer 1: Accounts that are DISCONNECTED, BANNED, or ERROR are excluded."""
        accounts = [
            {"id": "acc_dead_1", "status": "DISCONNECTED"},
            {"id": "acc_dead_2", "status": "BANNED"},
            {"id": "acc_live_1", "status": "ACTIVE", "is_warmup": False},
        ]
        res = allocate_leads_weighted_across_fleet(accounts, 5)
        self.assertEqual(len(res), 5)
        self.assertTrue(all(a == "acc_live_1" for a in res))

    def test_allocate_leads_fallback_when_no_active_status(self):
        """Layer 1: Graceful fallback when accounts have no status or migrating status."""
        accounts = [
            {"id": "acc_migrating_1", "status": ""},
            {"id": "acc_migrating_2", "status": None},
        ]
        res = allocate_leads_weighted_across_fleet(accounts, 4)
        self.assertEqual(len(res), 4)
        self.assertEqual(set(res), {"acc_migrating_1", "acc_migrating_2"})

    def test_allocate_leads_warmup_and_standard_weighting(self):
        """Layer 0: Standard accounts (weight 50) receive higher proportional share than warmup (weight 10)."""
        accounts = [
            {"id": "acc_warm", "status": "ACTIVE", "is_warmup": True, "warmup_max_connections": 10},
            {"id": "acc_std", "status": "ACTIVE", "is_warmup": False},
        ]
        # 60 leads allocated across ratio 10:50 (1:5)
        res = allocate_leads_weighted_across_fleet(accounts, 60)
        self.assertEqual(len(res), 60)
        warm_count = res.count("acc_warm")
        std_count = res.count("acc_std")
        self.assertEqual(warm_count, 10)
        self.assertEqual(std_count, 50)

    def test_allocate_leads_even_distribution_single_account(self):
        """Layer 0: Single account absorbs 100% of allocation cleanly."""
        accounts = [{"id": "acc_solo", "status": "ACTIVE", "is_warmup": False}]
        res = allocate_leads_weighted_across_fleet(accounts, 12)
        self.assertEqual(len(res), 12)
        self.assertEqual(res, ["acc_solo"] * 12)

    # =========================================================================
    # 2. Campaign Creation Hardening (Layer 0, 1, 2)
    # =========================================================================

    def test_create_campaign_foreign_sender_rejected(self):
        """Layer 2 (Security): Sender account belonging to another tenant raises 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        # Query on accounts table scoped by workspace_id returns empty (not found in caller workspace)
        tables["accounts"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        payload = CampaignCreate(
            name="Q4 Enterprise Outreach",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={"message": "Hi"})],
            edges=[],
            senders=["acc_competitor_victim"],
        )

        with self.assertRaises(HTTPException) as ctx:
            create_campaign(payload, mock_svc, "ws_my_tenant", "user_123")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("do not belong to your workspace", ctx.exception.detail)

    def test_create_campaign_cycle_detected_422(self):
        """Layer 1: Graph cycle (n1 -> n2 -> n1) raises 422 Unprocessable Entity."""
        mock_svc, tables = self._setup_multi_table_mock()

        payload = CampaignCreate(
            name="Looped Campaign",
            nodes=[
                EleInNode(id="n1", type="linkedin_message", data={}),
                EleInNode(id="n2", type="delay", data={"delay_days": 1}),
            ],
            edges=[
                EleInEdge(id="e1", source="n1", target="n2"),
                EleInEdge(id="e2", source="n2", target="n1"),
            ],
            senders=[],
        )

        with self.assertRaises(HTTPException) as ctx:
            create_campaign(payload, mock_svc, "ws_123", "user_123")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("contains a cycle", ctx.exception.detail)

    def test_create_campaign_unreachable_if_replied_rejected_400(self):
        """Layer 2: Disabling stop_on_reply without a reachable 'if_replied' node raises 400."""
        mock_svc, tables = self._setup_multi_table_mock()

        payload = CampaignCreate(
            name="Unsafe Reply Handling",
            nodes=[
                EleInNode(id="n1", type="linkedin_message", data={}),
                EleInNode(id="n2", type="delay", data={}),
                EleInNode(id="n_orphan", type="if_replied", data={}),  # Orphaned, not in sequence
            ],
            edges=[
                EleInEdge(id="e1", source="n1", target="n2"),
            ],
            metadata={"stop_on_reply": False},
        )

        with self.assertRaises(HTTPException) as ctx:
            create_campaign(payload, mock_svc, "ws_123", "user_123")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Safety Violation", ctx.exception.detail)

    @patch("campaigns.backend.routers.elein.log_audit")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_create_campaign_reachable_if_replied_succeeds(self, mock_svc_dep, mock_audit):
        """Layer 0: Reachable 'if_replied' node with stop_on_reply=False saves successfully."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_dep.return_value = mock_svc

        tables["accounts"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1"}]
        )

        payload = CampaignCreate(
            name="Safe Dynamic Reply Campaign",
            nodes=[
                EleInNode(id="n1", type="linkedin_message", data={}),
                EleInNode(id="n2", type="if_replied", data={}),
            ],
            edges=[
                EleInEdge(id="e1", source="n1", target="n2"),
            ],
            senders=["acc_1"],
            metadata={"stop_on_reply": False},
        )

        res = create_campaign(payload, mock_svc, "ws_123", "user_123")
        self.assertEqual(res.name, "Safe Dynamic Reply Campaign")
        self.assertEqual(res.status, "DRAFT")

    def test_create_campaign_tier_limit_reached_403(self):
        """Layer 1: Creating campaign with status='ACTIVE' when tier limit reached raises 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            count=1
        )

        payload = CampaignCreate(
            name="Overlimit Active Campaign",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={"message": "Hey"})],
            edges=[],
            status="ACTIVE",
        )

        with self.assertRaises(HTTPException) as ctx:
            create_campaign(payload, mock_svc, "ws_123", "user_123")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Campaign limit reached", ctx.exception.detail)

    @patch("campaigns.backend.routers.elein.log_audit")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_create_campaign_draft_success(self, mock_svc_dep, mock_audit):
        """Layer 0: Standard draft campaign creation succeeds and persists relational entities."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_dep.return_value = mock_svc

        tables["accounts"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc_1"}]
        )

        payload = CampaignCreate(
            name="Standard Outbound",
            nodes=[
                EleInNode(id="n1", type="linkedin_connection", data={}),
                EleInNode(id="n2", type="linkedin_message", data={}),
            ],
            edges=[EleInEdge(id="e1", source="n1", target="n2")],
            senders=["acc_1"],
            status="DRAFT",
        )

        res = create_campaign(payload, mock_svc, "ws_123", "user_123")
        self.assertEqual(res.name, "Standard Outbound")
        self.assertEqual(res.status, "DRAFT")
        tables["campaigns"].insert.assert_called_once()
        tables["campaign_versions"].insert.assert_called_once()
        tables["campaign_nodes"].insert.assert_called_once()
        tables["campaign_edges"].insert.assert_called_once()

    # =========================================================================
    # 3. Campaign Update Hardening (Layer 0, 1, 2)
    # =========================================================================

    def test_update_campaign_not_found_404(self):
        """Layer 1: Updating nonexistent or foreign campaign returns 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = CampaignCreate(name="Updated", nodes=[], edges=[])
        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_ghost", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_campaign_foreign_sender_rejected_403(self):
        """Layer 2 (Security): Updating campaign with foreign sender accounts raises 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT"}]
        )
        tables["accounts"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )

        payload = CampaignCreate(
            name="Updated Campaign",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={})],
            edges=[],
            senders=["acc_foreign_tenant"],
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("do not belong to your workspace", ctx.exception.detail)

    def test_update_campaign_cycle_detected_422(self):
        """Layer 1: Introducing a cycle during update raises 422."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT"}]
        )

        payload = CampaignCreate(
            name="Looped Update",
            nodes=[
                EleInNode(id="n1", type="linkedin_message", data={}),
                EleInNode(id="n2", type="delay", data={}),
            ],
            edges=[
                EleInEdge(id="e1", source="n1", target="n2"),
                EleInEdge(id="e2", source="n2", target="n1"),
            ],
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_update_campaign_unreachable_if_replied_rejected_400(self):
        """Layer 2: Disabling stop_on_reply during update without reachable 'if_replied' raises 400."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT"}]
        )

        payload = CampaignCreate(
            name="Unsafe Update",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={})],
            edges=[],
            metadata={"stop_on_reply": False},
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Safety Violation", ctx.exception.detail)

    def test_update_campaign_tier_limit_enforced_403(self):
        """Layer 1: Changing campaign from DRAFT to ACTIVE when at tier limit raises 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT"}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
            count=1
        )

        payload = CampaignCreate(
            name="Activate via Update",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={"message": "Hey"})],
            edges=[],
            status="ACTIVE",
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Campaign limit reached", ctx.exception.detail)

    # =========================================================================
    # 4. Campaign Activation Hardening (Layer 0, 1, 2)
    # =========================================================================

    def test_activate_campaign_not_found_404(self):
        """Layer 1: Activating nonexistent campaign returns 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_ghost", "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_activate_campaign_no_touchpoints_rejected_400(self):
        """Layer 2: Campaign with no outreach touchpoints cannot be activated (HTTP 400)."""
        mock_svc, tables = self._setup_multi_table_mock()
        # Campaign with only logic/delay nodes
        nodes = [
            {"id": "n1", "type": "delay", "data": {"delay_days": 2}},
            {"id": "n2", "type": "condition", "data": {}},
        ]
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "nodes_json": json.dumps(nodes)}]
        )

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_1", "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("contains no outreach touchpoints", ctx.exception.detail)

    def test_activate_campaign_tier_limit_reached_403(self):
        """Layer 1: Activation blocked when active campaign quota is filled (HTTP 403)."""
        mock_svc, tables = self._setup_multi_table_mock()
        nodes = [{"id": "n1", "type": "linkedin_message", "data": {}}]
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "nodes_json": json.dumps(nodes)}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
            count=1
        )

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_1", "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Campaign limit reached", ctx.exception.detail)

    def test_activate_campaign_free_tier_restricted_enrichment_node_403(self):
        """Layer 1: Free tier attempting to activate apollo_enrich or apify_scrape node raises 403."""
        mock_svc, tables = self._setup_multi_table_mock()
        nodes = [{"id": "n1", "type": "linkedin_message", "data": {}}]
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "nodes_json": json.dumps(nodes)}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
            count=0
        )
        tables["campaign_nodes"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"node_type": "apollo_enrich"}]
        )

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_1", "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot activate campaigns with external enrichment", ctx.exception.detail)

    def test_activate_campaign_no_active_senders_rejected_400(self):
        """Layer 1: Campaign with no active sender accounts raises HTTP 400 (no_active_senders)."""
        mock_svc, tables = self._setup_multi_table_mock()
        nodes = [{"id": "n1", "type": "linkedin_message", "data": {}}]
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "nodes_json": json.dumps(nodes)}]
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
        # Senders query returns 0 active accounts
        tables["accounts"].select.return_value.in_.return_value.eq.return_value.or_.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_1", "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "no_active_senders")

    def test_activate_campaign_insufficient_credits_rejected_400(self):
        """Layer 1: Credit balance <= -500 blocks campaign activation with HTTP 400."""
        mock_svc, tables = self._setup_multi_table_mock()
        nodes = [{"id": "n1", "type": "linkedin_message", "data": {}}]
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "nodes_json": json.dumps(nodes)}]
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
        # Mock negative balance
        mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"balance": -600})

        with self.assertRaises(HTTPException) as ctx:
            activate_campaign("camp_1", "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "insufficient_credits")

    @patch("campaigns.backend.routers.elein.get_conflicting_active_leads")
    def test_activate_campaign_collision_guard_auto_pauses(self, mock_conflict):
        """Layer 1: Enrolled leads colliding with other active campaigns get paused upon activation."""
        mock_svc, tables = self._setup_multi_table_mock()
        nodes = [{"id": "n1", "type": "linkedin_message", "data": {}}]
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "nodes_json": json.dumps(nodes)}]
        )
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "GROWTH"}]
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
        mock_svc.rpc.return_value.execute.return_value = MagicMock(data={"balance": 100})

        # Lead enrollments
        tables["campaign_enrollments"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "enr_1", "lead_id": "lead_colliding"}]
        )
        mock_conflict.return_value = ["lead_colliding"]

        res = activate_campaign("camp_1", "ws_123", mock_svc)
        self.assertEqual(res, {"status": "activated"})
        tables["campaign_execution_states"].update.assert_called_once()
        update_args = tables["campaign_execution_states"].update.call_args[0][0]
        self.assertEqual(update_args["status"], "paused")

    # =========================================================================
    # 5. Lead Enrollment Hardening (Layer 0, 1, 2)
    # =========================================================================

    def test_enroll_leads_campaign_not_found_404(self):
        """Layer 1: Enrolling into non-existent or foreign campaign raises 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = EnrollLeadsRequest(opportunity_ids=["lead_1"])
        with self.assertRaises(HTTPException) as ctx:
            enroll_leads("camp_ghost", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("campaigns.backend.routers.elein.get_conflicting_active_leads")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_enroll_leads_cross_tenant_leads_filtered_out(self, mock_svc_dep, mock_conflict):
        """Layer 2 (Security): Leads belonging to other workspaces are strictly dropped."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_dep.return_value = mock_svc
        mock_conflict.return_value = []

        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        # Already enrolled check
        tables["campaign_enrollments"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        # Workspace leads check: only lead_valid belongs to ws_123, lead_foreign does not
        tables["leads"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead_valid", "linkedin_url": "https://linkedin.com/in/valid", "email": "valid@corp.io"}]
        )
        # Suppression check
        tables["suppression_list"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        # Active version and accounts
        tables["campaign_versions"].select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "ver_1"}]
        )
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_1", "accounts": {"id": "acc_1", "status": "ACTIVE"}}]
        )

        payload = EnrollLeadsRequest(opportunity_ids=["lead_valid", "lead_foreign"])
        res = enroll_leads("camp_1", payload, mock_svc, "ws_123")

        self.assertEqual(res["enrolled"], 1)
        self.assertEqual(res["skipped"], 1)
        self.assertEqual(res["collisions"], 0)

    @patch("campaigns.backend.routers.elein.get_conflicting_active_leads")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_enroll_leads_suppression_list_excludes_candidates(self, mock_svc_dep, mock_conflict):
        """Layer 1: Leads matching email or linkedin_url in suppression_list are skipped."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_dep.return_value = mock_svc
        mock_conflict.return_value = []

        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        tables["campaign_enrollments"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["leads"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "lead_supp", "linkedin_url": "https://linkedin.com/in/supp", "email": "supp@bad.com"},
                {"id": "lead_clean", "linkedin_url": "https://linkedin.com/in/clean", "email": "clean@good.com"},
            ]
        )
        # Return lead_supp email in suppression list
        tables["suppression_list"].select.return_value.eq.return_value.in_.return_value.execute.side_effect = [
            MagicMock(data=[]),  # linkedin check
            MagicMock(data=[{"email": "supp@bad.com"}]),  # email check
        ]
        tables["campaign_versions"].select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "ver_1"}]
        )
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_1", "accounts": {"id": "acc_1", "status": "ACTIVE"}}]
        )

        payload = EnrollLeadsRequest(opportunity_ids=["lead_supp", "lead_clean"])
        res = enroll_leads("camp_1", payload, mock_svc, "ws_123")

        self.assertEqual(res["enrolled"], 1)
        self.assertEqual(res["skipped"], 1)

    @patch("campaigns.backend.routers.elein.get_conflicting_active_leads")
    def test_enroll_leads_no_senders_linked_rejected_400(self, mock_conflict):
        """Layer 1: Enrolling leads when campaign has no linked senders raises HTTP 400."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_conflict.return_value = []

        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        tables["campaign_enrollments"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["leads"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead_1", "linkedin_url": "https://linkedin.com/in/1", "email": "1@a.com"}]
        )
        tables["suppression_list"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        tables["campaign_versions"].select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "ver_1"}]
        )
        # Campaign has no accounts
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = EnrollLeadsRequest(opportunity_ids=["lead_1"])
        with self.assertRaises(HTTPException) as ctx:
            enroll_leads("camp_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("no linked sender accounts", ctx.exception.detail)

    # =========================================================================
    # 6. List-Based Lead Enrollment Hardening (Layer 0, 1, 2)
    # =========================================================================

    def test_enroll_list_leads_campaign_not_found_404(self):
        """Layer 1: Enrolling list into nonexistent campaign raises 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        payload = EnrollListRequest(list_id="list_1")
        with self.assertRaises(HTTPException) as ctx:
            enroll_list_leads("camp_ghost", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_enroll_list_leads_foreign_list_rejected_404(self):
        """Layer 2 (Security): List ID belonging to another tenant raises 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        # lead_lists query scoped by workspace returns empty
        tables["lead_lists"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        payload = EnrollListRequest(list_id="list_competitor")
        with self.assertRaises(HTTPException) as ctx:
            enroll_list_leads("camp_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Lead list not found", ctx.exception.detail)

    def test_enroll_list_leads_foreign_exclude_list_rejected_404(self):
        """Layer 2 (Security): excludeListId belonging to another tenant raises 404."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        # First call for list_id succeeds, second call for excludeListId returns empty
        tables["lead_lists"].select.return_value.eq.return_value.eq.return_value.execute.side_effect = [
            MagicMock(data=[{"id": "list_own"}]),
            MagicMock(data=[]),
        ]

        payload = EnrollListRequest(list_id="list_own", excludeListId="list_foreign")
        with self.assertRaises(HTTPException) as ctx:
            enroll_list_leads("camp_1", payload, mock_svc, "ws_123")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Excluded lead list not found", ctx.exception.detail)

    @patch("campaigns.backend.routers.elein._fetch_all_list_members")
    @patch("campaigns.backend.routers.elein.get_conflicting_active_leads")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_enroll_list_leads_cross_tenant_and_suppression_filtered(self, mock_svc_dep, mock_conflict, mock_members):
        """Layer 1 & 2: Foreign leads and suppressed leads in list enrollment are filtered out."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_dep.return_value = mock_svc
        mock_conflict.return_value = []
        mock_members.return_value = ["lead_valid", "lead_supp", "lead_foreign"]

        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1"}]
        )
        tables["lead_lists"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "list_1"}]
        )
        # Already enrolled check
        tables["campaign_enrollments"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        # Workspace leads check: only lead_valid and lead_supp belong to ws_123; lead_foreign not returned
        tables["leads"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "lead_valid", "linkedin_url": "https://linkedin.com/in/val", "email": "val@co.com"},
                {"id": "lead_supp", "linkedin_url": "https://linkedin.com/in/sup", "email": "sup@co.com"},
            ]
        )
        # Suppression check: lead_supp is in suppression_list
        tables["suppression_list"].select.return_value.eq.return_value.in_.return_value.execute.side_effect = [
            MagicMock(data=[{"linkedin_url": "https://linkedin.com/in/sup"}]),  # linkedin check
            MagicMock(data=[]),  # email check
            MagicMock(data=[]),  # domain check
        ]
        # Active version and accounts
        tables["campaign_versions"].select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "ver_1"}]
        )
        tables["campaign_accounts"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"account_id": "acc_1", "accounts": {"id": "acc_1", "status": "ACTIVE"}}]
        )

        payload = EnrollListRequest(list_id="list_1")
        res = enroll_list_leads("camp_1", payload, mock_svc, "ws_123")

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["enrolled"], 1)  # only lead_valid
        self.assertEqual(res["skipped"], 2)   # lead_supp + lead_foreign
        self.assertEqual(res["collisions"], 0)


if __name__ == "__main__":
    unittest.main()
