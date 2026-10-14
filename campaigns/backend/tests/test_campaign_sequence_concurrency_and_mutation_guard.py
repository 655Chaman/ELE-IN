"""
Three-Layer Paranoia Framework Unit Test Suite — Step 33 Track A:
Campaign Sequence Graph Optimistic Concurrency, Active-Enrollment Structural Mutation Lock & Orphaned Node Guard
"""
import os
import json
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from campaigns.backend.schemas.elein import CampaignCreate, EleInNode, EleInEdge
from campaigns.backend.services.dag_validator import (
    check_optimistic_concurrency,
    validate_active_campaign_graph_mutation,
)
from campaigns.backend.routers.elein import create_campaign, update_campaign


class TestCampaignSequenceConcurrencyAndMutationGuard(unittest.TestCase):
    def _setup_multi_table_mock(self):
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)
        mock_svc.table.side_effect = lambda name: tables[name]
        return mock_svc, tables

    # =========================================================================
    # 1. Optimistic Concurrency Control (OCC) — Multi-Tab Overwrite Guard
    # =========================================================================

    def test_check_optimistic_concurrency_version_conflict(self):
        """Paranoia Layer 1 & 2: Stale expected_version triggers OCC conflict."""
        existing = {
            "id": "camp_1",
            "status": "DRAFT",
            "updated_at": "2026-10-11T10:05:00Z",
            "metadata": {"version": 3},
        }
        res = check_optimistic_concurrency(existing, current_version=3, expected_version=2)
        self.assertTrue(res["conflict"])
        self.assertIn("expected version 2, current version is 3", res["reason"])

        res_ok = check_optimistic_concurrency(existing, current_version=3, expected_version=3)
        self.assertFalse(res_ok["conflict"])

    def test_check_optimistic_concurrency_updated_at_conflict(self):
        """Paranoia Layer 1 & 2: Stale expected_updated_at timestamp triggers OCC conflict."""
        existing = {
            "id": "camp_1",
            "status": "DRAFT",
            "updated_at": "2026-10-11T10:05:00Z",
            "metadata": {"version": 2},
        }
        res = check_optimistic_concurrency(
            existing,
            expected_updated_at="2026-10-11T10:00:00Z",
        )
        self.assertTrue(res["conflict"])
        self.assertIn("expected updated_at", res["reason"])

    def test_update_campaign_rejects_stale_expected_version_409(self):
        """Paranoia Layer 2: Multi-tab save with outdated expected_version raises HTTP 409."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_occ_1",
                "status": "DRAFT",
                "updated_at": "2026-10-11T12:00:00Z",
                "metadata": {"version": 4},
                "nodes_json": [{"id": "n1", "type": "linkedin_message", "data": {}}],
                "edges_json": [],
            }]
        )

        payload = CampaignCreate(
            name="Tab 1 Stale Overwrite",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={"message": "Stale"})],
            edges=[],
            expected_version=2,
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_occ_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Optimistic concurrency conflict", ctx.exception.detail)

    def test_update_campaign_rejects_stale_expected_updated_at_409(self):
        """Paranoia Layer 2: Multi-tab save with outdated expected_updated_at raises HTTP 409."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_occ_2",
                "status": "DRAFT",
                "updated_at": "2026-10-11T12:30:00Z",
                "metadata": {"version": 2},
                "nodes_json": [],
                "edges_json": [],
            }]
        )

        payload = CampaignCreate(
            name="Tab 2 Stale Timestamp",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={})],
            edges=[],
            expected_updated_at="2026-10-11T12:00:00Z",
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_occ_2", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Optimistic concurrency conflict", ctx.exception.detail)

    # =========================================================================
    # 2. Active-Enrollment Structural Mutation Lock
    # =========================================================================

    def test_validate_active_campaign_graph_mutation_detects_deleted_and_retyped_nodes(self):
        """Paranoia Layer 0 & 1: Detects node deletion and node type mutation while allowing copy edits and new appended nodes."""
        existing_nodes = [
            {"id": "n1", "type": "linkedin_connection", "data": {"note": "Hi"}},
            {"id": "n2", "type": "delay", "data": {"delay_days": 2}},
            {"id": "n3", "type": "linkedin_message", "data": {"message": "Followup"}},
        ]
        # Case A: Safe copy edit + adding a new node n4
        safe_new_nodes = [
            {"id": "n1", "type": "linkedin_connection", "data": {"note": "Updated Hi"}},
            {"id": "n2", "type": "delay", "data": {"delay_days": 3}},
            {"id": "n3", "type": "linkedin_message", "data": {"message": "Updated Followup"}},
            {"id": "n4", "type": "linkedin_message", "data": {"message": "Extra step"}},
        ]
        rep_safe = validate_active_campaign_graph_mutation(existing_nodes, safe_new_nodes)
        self.assertTrue(rep_safe["is_safe"])
        self.assertEqual(rep_safe["deleted_node_ids"], [])
        self.assertEqual(rep_safe["type_mutated_nodes"], [])

        # Case B: Unsafe deletion of n2 and retyping of n3
        unsafe_new_nodes = [
            {"id": "n1", "type": "linkedin_connection", "data": {"note": "Hi"}},
            {"id": "n3", "type": "delay", "data": {"delay_days": 1}},
        ]
        rep_unsafe = validate_active_campaign_graph_mutation(
            existing_nodes, unsafe_new_nodes, in_flight_node_ids={"n2"}
        )
        self.assertFalse(rep_unsafe["is_safe"])
        self.assertEqual(rep_unsafe["deleted_node_ids"], ["n2"])
        self.assertEqual(len(rep_unsafe["type_mutated_nodes"]), 1)
        self.assertEqual(rep_unsafe["type_mutated_nodes"][0]["node_id"], "n3")
        self.assertEqual(rep_unsafe["orphaned_in_flight_nodes"], ["n2"])

    def test_update_active_campaign_blocks_node_deletion_without_override_409(self):
        """Paranoia Layer 1 & 2: Deleting a node from an ACTIVE campaign raises HTTP 409 unless overridden."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_active_1",
                "status": "ACTIVE",
                "metadata": {"version": 1},
                "nodes_json": [
                    {"id": "n1", "type": "linkedin_connection", "data": {}},
                    {"id": "n2", "type": "linkedin_message", "data": {"message": "Hello {{first_name}}"}},
                ],
                "edges_json": [{"id": "e1", "source": "n1", "target": "n2"}],
            }]
        )

        # Operator deletes n2 while campaign is ACTIVE
        payload = CampaignCreate(
            name="Active Campaign Destructive Edit",
            nodes=[EleInNode(id="n1", type="linkedin_connection", data={})],
            edges=[],
            status="ACTIVE",
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign("camp_active_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Structural graph mutation blocked on ACTIVE campaign", ctx.exception.detail)
        self.assertIn("n2", ctx.exception.detail)

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_update_active_campaign_allows_copy_edit_and_allow_override(self, mock_svc_dep):
        """Paranoia Layer 0 & 2: Copy edits on ACTIVE campaigns succeed, and allow_active_graph_mutation=True permits structural overrides."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_svc_dep.return_value = mock_svc
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_active_2",
                "status": "ACTIVE",
                "metadata": {"version": 1},
                "nodes_json": [
                    {"id": "n1", "type": "linkedin_connection", "data": {}},
                    {"id": "n2", "type": "linkedin_message", "data": {"message": "Old text"}},
                ],
                "edges_json": [{"id": "e1", "source": "n1", "target": "n2"}],
            }]
        )
        tables["campaign_versions"].select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"version": 1}]
        )

        # 1. Copy edit (nodes n1 and n2 preserved with same types)
        payload_copy = CampaignCreate(
            name="Active Campaign Safe Copy Edit",
            nodes=[
                EleInNode(id="n1", type="linkedin_connection", data={}),
                EleInNode(id="n2", type="linkedin_message", data={"message": "New text {{first_name}}"}),
            ],
            edges=[EleInEdge(id="e1", source="n1", target="n2")],
            status="ACTIVE",
        )
        res = update_campaign("camp_active_2", payload_copy, "ws_123", mock_svc)
        self.assertEqual(res.status, "ACTIVE")

        # 2. Structural delete with explicit allow_active_graph_mutation=True
        payload_override = CampaignCreate(
            name="Active Campaign Explicit Override",
            nodes=[EleInNode(id="n1", type="linkedin_connection", data={})],
            edges=[],
            status="ACTIVE",
            allow_active_graph_mutation=True,
        )
        res2 = update_campaign("camp_active_2", payload_override, "ws_123", mock_svc)
        self.assertEqual(res2.name, "Active Campaign Explicit Override")

    # =========================================================================
    # 3. Dangling Edges & Active-Campaign Orphaned Node Guard
    # =========================================================================

    def test_create_and_update_campaign_reject_dangling_edges_422(self):
        """Paranoia Layer 1 & 2: Edges referencing deleted/non-existent node IDs raise HTTP 422."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "status": "DRAFT", "metadata": {}}]
        )

        payload = CampaignCreate(
            name="Dangling Edge Campaign",
            nodes=[EleInNode(id="n1", type="linkedin_connection", data={})],
            edges=[EleInEdge(id="e_bad", source="n1", target="n_deleted_ghost")],
            status="DRAFT",
        )

        with self.assertRaises(HTTPException) as ctx_create:
            create_campaign(payload, mock_svc, "ws_123", "user_1")
        self.assertEqual(ctx_create.exception.status_code, 422)
        self.assertIn("dangling edges", ctx_create.exception.detail)

        with self.assertRaises(HTTPException) as ctx_update:
            update_campaign("camp_1", payload, "ws_123", mock_svc)
        self.assertEqual(ctx_update.exception.status_code, 422)
        self.assertIn("dangling edges", ctx_update.exception.detail)

    def test_active_campaign_rejects_disconnected_orphaned_nodes_422(self):
        """Paranoia Layer 2: Activating/saving an ACTIVE campaign with isolated orphan nodes on canvas raises HTTP 422."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["workspaces"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "GROWTH"}]
        )
        tables["campaigns"].select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            count=0,
            data=[{"id": "camp_1", "status": "DRAFT", "metadata": {}}],
        )

        payload = CampaignCreate(
            name="Orphaned Canvas Campaign",
            nodes=[
                EleInNode(id="n1", type="linkedin_connection", data={}),
                EleInNode(id="n2", type="linkedin_message", data={"message": "Connected step"}),
                EleInNode(id="n_forgotten_island", type="linkedin_message", data={"message": "Unconnected island"}),
            ],
            edges=[EleInEdge(id="e1", source="n1", target="n2")],
            status="ACTIVE",
        )

        with self.assertRaises(HTTPException) as ctx:
            create_campaign(payload, mock_svc, "ws_123", "user_1")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("orphaned nodes", ctx.exception.detail)
        self.assertIn("n_forgotten_island", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
