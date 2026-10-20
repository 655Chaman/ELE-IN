import unittest
from unittest.mock import MagicMock, patch, call
from collections import defaultdict
import json
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from campaigns.backend.routers.elein import (
    pause_campaign,
    pause_all_campaigns,
    activate_campaign,
    delete_campaign,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class MockTable:
    def __init__(self, name):
        self.name = name
        self.select_builder = MagicMock()
        self.update_builder = MagicMock()
        self.insert_builder = MagicMock()
        self.delete_builder = MagicMock()

        for b in [self.select_builder, self.update_builder, self.insert_builder, self.delete_builder]:
            b.select.return_value = b
            b.update.return_value = b
            b.insert.return_value = b
            b.delete.return_value = b
            b.eq.return_value = b
            b.neq.return_value = b
            b.in_.return_value = b
            b.or_.return_value = b
            b.limit.return_value = b
            b.order.return_value = b
            b.execute.return_value = MagicMock(data=[], count=0)

    def select(self, *args, **kwargs):
        self.select_builder.select(*args, **kwargs)
        return self.select_builder

    def update(self, *args, **kwargs):
        self.update_builder.update(*args, **kwargs)
        return self.update_builder

    def insert(self, *args, **kwargs):
        self.insert_builder.insert(*args, **kwargs)
        return self.insert_builder

    def delete(self, *args, **kwargs):
        self.delete_builder.delete(*args, **kwargs)
        return self.delete_builder


class TestCampaignLifecycleAndCascadeCleanup(unittest.TestCase):
    """
    Test suite for Campaign Lifecycle and Cascade Cleanup (Step 18).
    Three-Layer Paranoia Framework:
    - Layer 0: Pause, resume, delete foundational logic.
    - Layer 1: Environmental failure analysis (cascade pause/unpause/exited transitions to prevent orphaned worker leases).
    - Layer 2: Human paranoia (accidental active deletion guards, outbox audit events, panic button).
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
    # 1. Pause Campaign & Cascade Pause (Layer 0, 1)
    # =========================================================================

    def test_pause_campaign_cascades_to_execution_states(self):
        """
        Pausing a campaign updates campaigns.status to 'PAUSED' and cascades
        to pause all in-flight (pending / waiting_for_reply) execution states.
        """
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "name": "Q4 Enterprise Outreach"}]
        )

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "enr_1"}, {"id": "enr_2"}]
        )

        res = pause_campaign(campaign_id="camp_1", workspace_id="ws_1", client=self.client)

        self.assertEqual(res, {"status": "paused", "campaign_id": "camp_1"})

        # Verify campaign updated to PAUSED
        camp_tbl.update_builder.update.assert_called_with({"status": "PAUSED"})
        camp_tbl.update_builder.eq.assert_has_calls([
            call("id", "camp_1"),
            call("workspace_id", "ws_1")
        ], any_order=True)

        # Verify execution states cascade paused
        state_tbl = self.get_table("campaign_execution_states")
        state_tbl.update_builder.update.assert_called_with({
            "status": "paused",
            "error_reason": "Campaign 'Q4 Enterprise Outreach' paused by operator"
        })
        state_tbl.update_builder.in_.assert_has_calls([
            call("enrollment_id", ["enr_1", "enr_2"]),
            call("status", ["pending", "waiting_for_reply", "running", "processing"])
        ], any_order=True)

    def test_pause_campaign_not_found_raises_404(self):
        """Nonexistent campaign raises HTTP 404."""
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            pause_campaign(campaign_id="ghost_camp", workspace_id="ws_1", client=self.client)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Campaign not found", ctx.exception.detail)

    # =========================================================================
    # 2. Panic Button: Pause All Campaigns (Layer 1, 2)
    # =========================================================================

    def test_pause_all_campaigns_panic_button(self):
        """
        Panic button pauses all ACTIVE campaigns in workspace and cascades
        pause to all of their in-flight execution states.
        """
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[
                {"id": "c1", "name": "Campaign Alpha"},
                {"id": "c2", "name": "Campaign Beta"}
            ]
        )

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "enr_1"}, {"id": "enr_2"}, {"id": "enr_3"}]
        )

        res = pause_all_campaigns(workspace_id="ws_1", client=self.client)

        self.assertEqual(res, {"status": "all_paused", "paused_count": 2})

        # Verify campaigns status updated
        camp_tbl.update_builder.update.assert_called_with({"status": "PAUSED"})
        camp_tbl.update_builder.eq.assert_has_calls([
            call("workspace_id", "ws_1"),
            call("status", "ACTIVE")
        ], any_order=True)

        # Verify execution states cascade paused
        state_tbl = self.get_table("campaign_execution_states")
        state_tbl.update_builder.update.assert_called_with({
            "status": "paused",
            "error_reason": "All campaigns paused via Panic Button"
        })
        state_tbl.update_builder.in_.assert_has_calls([
            call("enrollment_id", ["enr_1", "enr_2", "enr_3"]),
            call("status", ["pending", "waiting_for_reply", "running", "processing"])
        ], any_order=True)

    def test_pause_all_campaigns_no_active_campaigns(self):
        """Panic button with 0 active campaigns returns paused_count 0 immediately."""
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(data=[])

        res = pause_all_campaigns(workspace_id="ws_1", client=self.client)
        self.assertEqual(res, {"status": "all_paused", "paused_count": 0})

    # =========================================================================
    # 3. Activate Campaign & Cascade Unpause (Layer 1)
    # =========================================================================

    @patch("campaigns.backend.routers.elein.get_conflicting_active_leads")
    def test_activate_campaign_cascades_unpause_non_colliding_states(self, mock_conflict):
        """
        Activating campaign transitions paused execution states back to 'pending',
        while preserving collision-locked states.
        """
        mock_conflict.return_value = []

        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{
                "id": "camp_1",
                "status": "PAUSED",
                "nodes_json": json.dumps([{"id": "n1", "type": "linkedin_message"}]),
                "metadata": {}
            }]
        )

        ws_tbl = self.get_table("workspaces")
        ws_tbl.select_builder.execute.return_value = MagicMock(data=[{"tier": "GROWTH"}])

        self.get_table("campaign_nodes").select_builder.execute.return_value = MagicMock(data=[])

        acc_tbl = self.get_table("accounts")
        acc_tbl.select_builder.execute.return_value = MagicMock(data=[{"id": "acc_1"}])

        self.client.rpc.return_value.execute.return_value = MagicMock(data={"balance": 500})

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "enr_1", "lead_id": "l_1"}, {"id": "enr_2", "lead_id": "l_2"}]
        )

        res = activate_campaign(campaign_id="camp_1", workspace_id="ws_1", client=self.client)

        self.assertEqual(res, {"status": "activated"})

        # Verify campaign updated to ACTIVE
        camp_tbl.update_builder.update.assert_called_with({"status": "ACTIVE"})

        # Verify cascade unpause execution states
        state_tbl = self.get_table("campaign_execution_states")
        state_tbl.update_builder.update.assert_called()
        update_args = state_tbl.update_builder.update.call_args[0][0]
        self.assertEqual(update_args["status"], "pending")
        self.assertIsNone(update_args["error_reason"])
        self.assertIn("next_run_at", update_args)

        # Verify non-collision guard filter was applied
        state_tbl.update_builder.eq.assert_called_with("status", "paused")
        state_tbl.update_builder.neq.assert_called_with(
            "error_reason",
            "Paused to prevent cross-campaign collision with active campaign"
        )

    # =========================================================================
    # 4. Delete Campaign Active Guard (Layer 2 Paranoia)
    # =========================================================================

    def test_delete_active_campaign_without_force_raises_400(self):
        """
        Human Paranoia: Deleting an ACTIVE campaign with enrollments without force=True
        is blocked with HTTP 400 and an actionable message.
        """
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "name": "Active Q4", "status": "ACTIVE"}]
        )

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "e1"}, {"id": "e2"}, {"id": "e3"}],
            count=3
        )

        with self.assertRaises(HTTPException) as ctx:
            delete_campaign("camp_1", force=False, workspace_id="ws_1", client=self.client)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot delete active campaign 'Active Q4'", ctx.exception.detail)
        self.assertIn("3 enrolled lead(s)", ctx.exception.detail)
        self.assertIn("Please pause the campaign before deleting it.", ctx.exception.detail)

    def test_delete_active_campaign_with_zero_enrollments_succeeds(self):
        """
        Deleting an ACTIVE campaign with 0 enrollments succeeds even without force=True.
        """
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "name": "Empty Active", "status": "ACTIVE"}]
        )

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(data=[], count=0)

        res = delete_campaign("camp_1", force=False, workspace_id="ws_1", client=self.client)
        self.assertEqual(res, {"status": "deleted", "campaign_id": "camp_1", "name": "Empty Active"})

    # =========================================================================
    # 5. Delete Paused Campaign & Cascade Cleanup (Layer 0, 1, 2)
    # =========================================================================

    def test_delete_paused_campaign_succeeds_with_cascade_cleanup(self):
        """
        Deleting a PAUSED campaign performs complete cascade cleanup:
        - Releases worker leases by marking execution states 'exited'.
        - Deletes execution states and enrollments.
        - Deletes campaign accounts and campaign nodes.
        - Deletes campaign record.
        - Emits 'campaign.deleted' audit event in outbox_events.
        """
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "name": "Paused Q4", "status": "PAUSED"}]
        )

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "enr_1"}, {"id": "enr_2"}]
        )

        res = delete_campaign("camp_1", force=False, workspace_id="ws_1", client=self.client)

        self.assertEqual(res, {"status": "deleted", "campaign_id": "camp_1", "name": "Paused Q4"})

        # Verify states marked exited first
        state_tbl = self.get_table("campaign_execution_states")
        state_tbl.update_builder.update.assert_called_with({
            "status": "exited",
            "error_reason": "Campaign 'Paused Q4' deleted by operator"
        })
        state_tbl.update_builder.in_.assert_has_calls([
            call("enrollment_id", ["enr_1", "enr_2"]),
            call("status", ["pending", "waiting_for_reply", "running", "paused"])
        ], any_order=True)

        # Verify deletion of states and enrollments
        state_tbl.delete_builder.delete.assert_called()
        state_tbl.delete_builder.in_.assert_called_with("enrollment_id", ["enr_1", "enr_2"])

        enr_tbl.delete_builder.delete.assert_called()
        enr_tbl.delete_builder.eq.assert_any_call("campaign_id", "camp_1")

        # Verify accounts and nodes deleted
        self.get_table("campaign_accounts").delete_builder.delete.assert_called()
        self.get_table("campaign_nodes").delete_builder.delete.assert_called()

        # Verify campaign deleted
        camp_tbl.delete_builder.delete.assert_called()
        camp_tbl.delete_builder.eq.assert_has_calls([
            call("id", "camp_1"),
            call("workspace_id", "ws_1")
        ], any_order=True)

        # Verify audit event in outbox_events
        outbox_tbl = self.get_table("outbox_events")
        outbox_tbl.insert_builder.insert.assert_called()
        event_payload = outbox_tbl.insert_builder.insert.call_args[0][0]
        self.assertEqual(event_payload["event_type"], "campaign.deleted")
        self.assertEqual(event_payload["workspace_id"], "ws_1")
        self.assertEqual(event_payload["payload"]["campaign_id"], "camp_1")
        self.assertEqual(event_payload["payload"]["name"], "Paused Q4")

    def test_delete_campaign_not_found_raises_404(self):
        """Deleting nonexistent campaign raises HTTP 404."""
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(data=[])

        with self.assertRaises(HTTPException) as ctx:
            delete_campaign("ghost_camp", force=False, workspace_id="ws_1", client=self.client)
        self.assertEqual(ctx.exception.status_code, 404)

    # =========================================================================
    # 6. Delete Active Campaign with Force=True (Layer 2 Override)
    # =========================================================================

    def test_delete_active_campaign_with_force_succeeds(self):
        """
        Operator override: With force=True, an ACTIVE campaign with enrollments
        is deleted cleanly along with all cascade targets.
        """
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "camp_1", "name": "Force Active", "status": "ACTIVE"}]
        )

        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "enr_1"}],
            count=1
        )

        res = delete_campaign("camp_1", force=True, workspace_id="ws_1", client=self.client)

        self.assertEqual(res, {"status": "deleted", "campaign_id": "camp_1", "name": "Force Active"})

        # Verify execution states and enrollments deleted
        state_tbl = self.get_table("campaign_execution_states")
        state_tbl.delete_builder.delete.assert_called()
        enr_tbl.delete_builder.delete.assert_called()
        camp_tbl.delete_builder.delete.assert_called()

    # =========================================================================
    # 7. Orchestrator: Skip Requeuing Waiting Leads for Non-Active Campaigns
    # =========================================================================

    def test_requeue_waiting_for_reply_skips_paused_campaigns(self):
        """
        Orchestrator paranoia: requeue_waiting_for_reply_leads verifies
        campaign_id on enrollments and skips any leads whose parent campaign
        is not ACTIVE (e.g. PAUSED, DRAFT, ARCHIVED).
        """
        orch = EleInOrchestrator(supabase=self.client)

        # Execution states in waiting_for_reply:
        # 1. state_paused belongs to a PAUSED campaign
        # 2. state_active belongs to an ACTIVE campaign
        state_tbl = self.get_table("campaign_execution_states")
        state_tbl.select_builder.execute.return_value = MagicMock(
            data=[
                {
                    "id": "state_paused",
                    "enrollment_id": "enr_paused",
                    "workspace_id": "ws_1",
                    "current_node_id": "node_1",
                    "variables": {},
                    "updated_at": "2026-10-01T00:00:00Z",
                    "next_run_at": "2026-10-02T00:00:00Z"
                },
                {
                    "id": "state_active",
                    "enrollment_id": "enr_active",
                    "workspace_id": "ws_1",
                    "current_node_id": "node_2",
                    "variables": {},
                    "updated_at": "2026-10-01T00:00:00Z",
                    "next_run_at": "2026-10-02T00:00:00Z"
                }
            ]
        )

        # Enrollments query returning campaign_id
        enr_tbl = self.get_table("campaign_enrollments")
        enr_tbl.select_builder.execute.return_value = MagicMock(
            data=[
                {
                    "id": "enr_paused",
                    "lead_id": "lead_paused",
                    "enrolled_at": "2026-10-01T00:00:00Z",
                    "campaign_id": "camp_paused"
                },
                {
                    "id": "enr_active",
                    "lead_id": "lead_active",
                    "enrolled_at": "2026-10-01T00:00:00Z",
                    "campaign_id": "camp_active"
                }
            ]
        )

        # Campaigns query: only camp_active is ACTIVE
        camp_tbl = self.get_table("campaigns")
        camp_tbl.select_builder.execute.return_value = MagicMock(
            data=[{"id": "camp_active"}]
        )

        # Messages query: no inbound messages
        msg_tbl = self.get_table("messages")
        msg_tbl.select_builder.execute.return_value = MagicMock(data=[])

        # State update for requeuing
        state_tbl.update_builder.execute.return_value = MagicMock(
            data=[{"id": "state_active"}]
        )

        requeued_ids = orch.requeue_waiting_for_reply_leads()

        # Only the state from the ACTIVE campaign is requeued!
        self.assertEqual(requeued_ids, ["state_active"])

        # Verify that state_paused was NEVER touched/updated
        update_calls = state_tbl.update_builder.eq.call_args_list
        for c in update_calls:
            self.assertNotEqual(c, call("id", "state_paused"))


if __name__ == "__main__":
    unittest.main()
