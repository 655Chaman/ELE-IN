import unittest
from unittest.mock import MagicMock, patch, call
import json
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from campaigns.backend.routers.elein import (
    get_campaigns,
    create_campaign,
    update_campaign,
    delete_campaign,
    get_lead_scores,
    get_message_attribution,
)
from campaigns.backend.schemas.elein import (
    CampaignCreate,
    EleInNode,
    EleInEdge,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class MockQueryBuilder:
    def __init__(self, data=None, count=0):
        self._data = data if data is not None else []
        self._count = count

    def select(self, *args, **kwargs):
        if kwargs.get("count") == "exact":
            self._count = len(self._data)
        return self

    def update(self, *args, **kwargs):
        return self

    def insert(self, *args, **kwargs):
        return self

    def delete(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def or_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def gt(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def lt(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def ilike(self, *args, **kwargs):
        return self

    def execute(self):
        res = MagicMock()
        res.data = self._data
        res.count = self._count
        return res


class MockTable:
    def __init__(self, name):
        self.name = name
        self.builder = MockQueryBuilder()
        self.executed_calls = []

    def select(self, *args, **kwargs):
        self.executed_calls.append(("select", args, kwargs))
        return self.builder.select(*args, **kwargs)

    def update(self, *args, **kwargs):
        self.executed_calls.append(("update", args, kwargs))
        return self.builder.update(*args, **kwargs)

    def insert(self, *args, **kwargs):
        self.executed_calls.append(("insert", args, kwargs))
        return self.builder.insert(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.executed_calls.append(("delete", args, kwargs))
        return self.builder.delete(*args, **kwargs)


class TestStage25CampaignsSubsystemParanoiaHardening(unittest.TestCase):
    """
    Stage 25: Paranoia-grade test suite for the Campaigns Subsystem.
    Rigorous verification against the Three-Layer Logic Architecture:
    - Layer 0: Foundational listing, attribution calculation, sanitization.
    - Layer 1: Environmental Failure Analysis (N+1 elimination, distributed locks, cascade cleanup, graph fallbacks).
    - Layer 2: Human Paranoia (active campaign deletion prevention, touchpoint requirement on activation).
    """

    def setUp(self):
        self.tables = {}
        self.client = MagicMock()

        def get_table(name):
            if name not in self.tables:
                self.tables[name] = MockTable(name)
            return self.tables[name]

        self.client.table.side_effect = get_table
        self.get_table = get_table

    # =========================================================================
    # 1. Campaign Listing, Pagination & Summary Counts (Layer 0, 1)
    # =========================================================================

    def test_get_campaigns_listing_pagination_and_node_counts(self):
        """Layer 0 & 1: GET /api/elein/campaigns returns paginated items with computed node/sender counts."""
        camp_tbl = self.get_table("campaigns")
        mock_camps = [
            {
                "id": "camp_1",
                "name": "Enterprise Outreach",
                "status": "ACTIVE",
                "created_at": "2026-10-20T10:00:00Z",
                "updated_at": "2026-10-20T10:30:00Z",
                "metadata": json.dumps({"target_industry": "SaaS"}),
                "nodes_json": json.dumps([{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]),
                "sender_account_ids_json": json.dumps(["acc_1", "acc_2"]),
            },
            {
                "id": "camp_2",
                "name": "Nurture Track",
                "status": "DRAFT",
                "created_at": "2026-10-19T08:00:00Z",
                "updated_at": "2026-10-19T08:00:00Z",
                "metadata": {"tags": ["inbound"]},
                "nodes_json": [{"id": "n1"}],
                "sender_account_ids_json": [],
            }
        ]
        camp_tbl.builder._data = mock_camps
        camp_tbl.builder._count = 2

        resp = get_campaigns(limit=10, offset=0, status=None, supabase=self.client, workspace_id="ws_123")

        self.assertEqual(resp["total"], 2)
        self.assertEqual(resp["limit"], 10)
        self.assertEqual(resp["offset"], 0)
        self.assertEqual(len(resp["campaigns"]), 2)

        c1 = resp["campaigns"][0]
        self.assertEqual(c1["id"], "camp_1")
        self.assertEqual(c1["name"], "Enterprise Outreach")
        self.assertEqual(c1["status"], "ACTIVE")
        self.assertEqual(c1["node_count"], 3)
        self.assertEqual(c1["senders_count"], 2)
        self.assertEqual(c1["metadata"]["target_industry"], "SaaS")

        c2 = resp["campaigns"][1]
        self.assertEqual(c2["id"], "camp_2")
        self.assertEqual(c2["node_count"], 1)
        self.assertEqual(c2["senders_count"], 0)

    def test_get_campaigns_handles_corrupt_json_gracefully(self):
        """Layer 1: Broken nodes_json or metadata JSON string does not cause HTTP 500."""
        camp_tbl = self.get_table("campaigns")
        camp_tbl.builder._data = [
            {
                "id": "camp_corrupt",
                "name": None,
                "status": None,
                "created_at": None,
                "updated_at": None,
                "metadata": "{invalid_json_str",
                "nodes_json": "['corrupt_json'",
                "sender_account_ids_json": "{not_a_list",
            }
        ]
        camp_tbl.builder._count = 1

        resp = get_campaigns(limit=5, offset=0, status=None, supabase=self.client, workspace_id="ws_123")
        self.assertEqual(len(resp["campaigns"]), 1)
        item = resp["campaigns"][0]
        self.assertEqual(item["name"], "Untitled Campaign")
        self.assertEqual(item["status"], "DRAFT")
        self.assertEqual(item["node_count"], 0)
        self.assertEqual(item["senders_count"], 0)
        self.assertEqual(item["metadata"], {})

    # =========================================================================
    # 2. Campaign Creation & Whitespace Name Sanitization (Layer 2)
    # =========================================================================

    @patch("campaigns.backend.routers.elein.log_audit")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_create_campaign_trims_whitespace_name_and_defaults_untitled(self, mock_svc, mock_audit):
        """Layer 2: Blank or whitespace-only campaign names are sanitized to 'Untitled Campaign'."""
        mock_svc.return_value = self.client
        self.get_table("accounts").builder._data = [{"id": "acc_1"}]
        self.get_table("workspaces").builder._data = [{"tier": "GROWTH"}]

        payload = CampaignCreate(
            name="   \t\n   ",
            nodes=[EleInNode(id="n1", type="linkedin_message", data={"message": "Hello"})],
            edges=[],
            status="DRAFT",
        )

        resp = create_campaign(payload, self.client, "ws_123", "user_1")
        self.assertEqual(resp.name, "Untitled Campaign")

    def test_create_active_campaign_requires_touchpoint_node_400(self):
        """Layer 2: Activating campaign with no outreach touchpoints (only logic/delay nodes) raises HTTP 400."""
        self.get_table("workspaces").builder._data = [{"tier": "GROWTH"}]
        self.get_table("campaigns").builder._count = 0

        payload = CampaignCreate(
            name="Logic Only Campaign",
            nodes=[
                EleInNode(id="n1", type="delay", data={"days": 2}),
                EleInNode(id="n2", type="filter", data={})
            ],
            edges=[EleInEdge(id="e1", source="n1", target="n2")],
            status="ACTIVE",
        )

        with self.assertRaises(HTTPException) as ctx:
            create_campaign(payload, self.client, "ws_123", "user_1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("no outreach touchpoints", ctx.exception.detail)

    # =========================================================================
    # 3. Lead Scores Batch Message Lookup (N+1 Elimination) (Layer 1)
    # =========================================================================

    @patch("knowledge.backend.services.elein_ai_service.compute_heat_score")
    def test_get_lead_scores_batches_message_lookup_eliminating_n_plus_one(self, mock_compute):
        """Layer 1: get_lead_scores executes a single batch message query for all campaign leads."""
        mock_compute.return_value = (85, "HOT")

        # Mock campaign
        self.get_table("campaigns").builder._data = [{"id": "camp_1"}]

        # Mock enrollments
        self.get_table("campaign_enrollments").builder._data = [
            {"id": "enr_1", "lead_id": "lead_1"},
            {"id": "enr_2", "lead_id": "lead_2"},
        ]

        # Mock execution states
        self.get_table("campaign_execution_states").builder._data = [
            {"enrollment_id": "enr_1", "status": "running"},
            {"enrollment_id": "enr_2", "status": "waiting_for_reply"},
        ]

        # Mock leads
        self.get_table("leads").builder._data = [
            {"id": "lead_1", "first_name": "Alice", "last_name": "Smith", "company_name": "Acme", "job_title": "VP", "linkedin_url": "https://linkedin.com/in/alice"},
            {"id": "lead_2", "first_name": "Bob", "last_name": "Jones", "company_name": "Globex", "job_title": "Director", "linkedin_url": "https://linkedin.com/in/bob"},
        ]

        # Mock batch messages
        self.get_table("messages").builder._data = [
            {"lead_id": "lead_1", "sender_name": "Alice Smith", "direction": "inbound", "message_text": "Sounds interesting!", "intent": "positive", "created_at": "2026-10-20T10:00:00Z"},
            {"lead_id": "lead_2", "sender_name": "Bob Jones", "direction": "outbound", "message_text": "Following up", "intent": None, "created_at": "2026-10-19T10:00:00Z"},
        ]

        scores = get_lead_scores("camp_1", supabase=self.client, workspace_id="ws_123")

        self.assertEqual(len(scores), 2)
        self.assertEqual(scores[0]["heat_score"], 85)
        self.assertEqual(scores[0]["heat_label"], "HOT")
        # Verify compute_heat_score received messages from the batch map
        self.assertEqual(mock_compute.call_count, 2)
        call1_msgs = mock_compute.call_args_list[0][0][1]
        self.assertTrue(any(m["lead_id"] == "lead_1" for m in call1_msgs))

    # =========================================================================
    # 4. Message Attribution Multi-Key Reply Resolution (Layer 0, 1)
    # =========================================================================

    def test_get_message_attribution_multi_key_reply_resolution(self):
        """Layer 0 & 1: Attribution accurately maps replies by lead_id, linkedin_url, and sender_name."""
        self.get_table("campaigns").builder._data = [{"id": "camp_1"}]
        self.get_table("campaign_enrollments").builder._data = [{"id": "enr_1", "lead_id": "lead_100"}]
        self.get_table("campaign_execution_states").builder._data = [{"id": "state_1", "enrollment_id": "enr_1"}]
        self.get_table("leads").builder._data = [{
            "id": "lead_100",
            "first_name": "Carol",
            "last_name": "Danvers",
            "linkedin_url": "https://linkedin.com/in/carol-danvers"
        }]

        # Action log entry: outreach sent at 10:00:00Z
        self.get_table("action_log").builder._data = [{
            "action_type": "message",
            "metadata": {"node_id": "node_pitch_1"},
            "executed_at": "2026-10-20T10:00:00Z",
            "result": "success",
            "execution_state_id": "state_1"
        }]

        # Inbound message received at 11:00:00Z (after outreach)
        self.get_table("messages").builder._data = [{
            "lead_id": "lead_100",
            "sender_name": "Carol Danvers",
            "thread_url": "https://linkedin.com/in/carol-danvers",
            "created_at": "2026-10-20T11:00:00Z"
        }]

        resp = get_message_attribution("camp_1", supabase=self.client, workspace_id="ws_123")

        self.assertIn("nodes", resp)
        self.assertEqual(len(resp["nodes"]), 1)
        node_stat = resp["nodes"][0]
        self.assertEqual(node_stat["node_id"], "node_pitch_1")
        self.assertEqual(node_stat["sent"], 1)
        self.assertEqual(node_stat["replied"], 1)
        self.assertEqual(node_stat["reply_rate"], 100.0)

    def test_get_message_attribution_ignores_prior_inbound_messages(self):
        """Layer 1: Inbound message arriving BEFORE outreach (T0 < T1) is not attributed as a reply."""
        self.get_table("campaigns").builder._data = [{"id": "camp_1"}]
        self.get_table("campaign_enrollments").builder._data = [{"id": "enr_1", "lead_id": "lead_100"}]
        self.get_table("campaign_execution_states").builder._data = [{"id": "state_1", "enrollment_id": "enr_1"}]
        self.get_table("leads").builder._data = [{
            "id": "lead_100",
            "first_name": "Carol",
            "last_name": "Danvers",
            "linkedin_url": "https://linkedin.com/in/carol-danvers"
        }]

        # Outreach sent at 12:00:00Z
        self.get_table("action_log").builder._data = [{
            "action_type": "message",
            "metadata": {"node_id": "node_pitch_1"},
            "executed_at": "2026-10-20T12:00:00Z",
            "result": "success",
            "execution_state_id": "state_1"
        }]

        # Inbound message was historical (received at 09:00:00Z, before outreach)
        self.get_table("messages").builder._data = [{
            "lead_id": "lead_100",
            "sender_name": "Carol Danvers",
            "thread_url": "https://linkedin.com/in/carol-danvers",
            "created_at": "2026-10-20T09:00:00Z"
        }]

        resp = get_message_attribution("camp_1", supabase=self.client, workspace_id="ws_123")

        node_stat = resp["nodes"][0]
        self.assertEqual(node_stat["sent"], 1)
        self.assertEqual(node_stat["replied"], 0)
        self.assertEqual(node_stat["reply_rate"], 0.0)

    # =========================================================================
    # 5. Distributed Locking & Cascade Deletion (Layer 1, 2)
    # =========================================================================

    def test_delete_active_campaign_without_force_rejected_400(self):
        """Layer 2: Deleting an ACTIVE campaign with enrolled leads without force=True raises HTTP 400."""
        self.get_table("campaigns").builder._data = [{"id": "camp_active", "name": "Active Q4", "status": "ACTIVE"}]
        self.get_table("campaign_enrollments").builder._data = [{"id": "enr_1"}]
        self.get_table("campaign_enrollments").builder._count = 1

        with self.assertRaises(HTTPException) as ctx:
            delete_campaign("camp_active", force=False, workspace_id="ws_123", client=self.client)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Please pause the campaign before deleting it", ctx.exception.detail)

    @patch("core.backend.services.credit_service.distributed_workspace_lock")
    def test_delete_campaign_distributed_locking_and_full_cascade(self, mock_lock):
        """Layer 1: delete_campaign acquires distributed lock and cascades deletion across versions, nodes, and outbox."""
        mock_lock.return_value.__enter__.return_value = True

        self.get_table("campaigns").builder._data = [{"id": "camp_target", "name": "Target Campaign", "status": "PAUSED"}]
        self.get_table("campaign_enrollments").builder._data = [{"id": "enr_1"}]
        self.get_table("campaign_versions").builder._data = [{"id": "ver_1"}]

        resp = delete_campaign("camp_target", force=True, workspace_id="ws_123", client=self.client)

        self.assertEqual(resp["status"], "deleted")
        self.assertEqual(resp["campaign_id"], "camp_target")
        # Verify distributed lock was requested with campaign_status key
        mock_lock.assert_called_once()
        lock_key = mock_lock.call_args[0][0]
        self.assertEqual(lock_key, "campaign_status:ws_123:camp_target")

        # Verify execution states were updated to exited
        ex_tbl = self.get_table("campaign_execution_states")
        self.assertTrue(any(c[0] == "update" for c in ex_tbl.executed_calls))
        self.assertTrue(any(c[0] == "delete" for c in ex_tbl.executed_calls))

        # Verify campaign_versions and campaign_accounts were cleaned up
        ver_tbl = self.get_table("campaign_versions")
        self.assertTrue(any(c[0] == "delete" for c in ver_tbl.executed_calls))

        # Verify outbox event audit record was emitted
        outbox_tbl = self.get_table("outbox_events")
        self.assertTrue(any(c[0] == "insert" for c in outbox_tbl.executed_calls))

    # =========================================================================
    # 6. Orchestrator Dual Schema & Graph Fallback (Layer 0, 1)
    # =========================================================================

    def test_orchestrator_dual_schema_action_and_data_resolution(self):
        """Layer 0 & 1: Orchestrator resolves node action and data from either node_type/config or type/data."""
        orchestrator = EleInOrchestrator(self.client)

        # Relational format (node_type & config)
        rel_node = {"id": "n1", "node_type": "linkedin_message", "config": {"message": "Relational message"}}
        action_rel = rel_node.get("node_type") or rel_node.get("type")
        data_rel = rel_node.get("config") or rel_node.get("data") or {}
        self.assertEqual(action_rel, "linkedin_message")
        self.assertEqual(data_rel["message"], "Relational message")

        # ReactFlow canvas format (type & data)
        rf_node = {"id": "n2", "type": "linkedin_connection", "data": {"note": "Canvas connection"}}
        action_rf = rf_node.get("node_type") or rf_node.get("type")
        data_rf = rf_node.get("config") or rf_node.get("data") or {}
        self.assertEqual(action_rf, "linkedin_connection")
        self.assertEqual(data_rf["note"], "Canvas connection")


if __name__ == "__main__":
    unittest.main()
