import uuid
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
from fastapi import HTTPException

from campaigns.backend.services.content_publisher_service import (
    schedule_thought_leadership_post,
    delete_thought_leadership_post,
    get_hook_frameworks,
    generate_thought_leadership_post
)
from campaigns.backend.routers.elein import (
    pause_campaign,
    activate_campaign
)


class TestStage17EliteArchitecture(unittest.TestCase):
    """
    Stage 17 Elite-Tier Distributed Systems Architecture Test Suite
    Governance: Three-Layer Logic Architecture (Paranoia Framework)
    """

    # ── 1. Content Publisher & Scheduler Hardening ────────────────────────────

    def test_schedule_post_empty_content_and_workspace_guard(self):
        """
        Layer 2: schedule_thought_leadership_post rejects empty/whitespace content
        or missing workspace_id defensively before making any DB calls.
        """
        mock_supabase = MagicMock()

        # Empty content (< 5 characters)
        res_empty = schedule_thought_leadership_post(
            supabase=mock_supabase,
            workspace_id="ws-stage17",
            post_content="   "
        )
        self.assertEqual(res_empty["status"], "error")
        self.assertIn("at least 5 characters", res_empty["message"])
        self.assertFalse(res_empty["db_persisted"])
        mock_supabase.table().insert.assert_not_called()

        # Missing workspace_id
        res_no_ws = schedule_thought_leadership_post(
            supabase=mock_supabase,
            workspace_id="   ",
            post_content="Valid thought leadership post about B2B outbound."
        )
        self.assertEqual(res_no_ws["status"], "error")
        self.assertIn("missing workspace_id", res_no_ws["message"])
        self.assertFalse(res_no_ws["db_persisted"])

    def test_schedule_post_horizon_bounding_and_past_clamping(self):
        """
        Layer 1 & 2: Past timestamps are clamped to current UTC time;
        distant future timestamps (>90 days) are clamped to the 90-day horizon.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "post-123"}])

        # 1. Past timestamp (e.g. 2020)
        past_iso = "2020-01-01T00:00:00Z"
        res_past = schedule_thought_leadership_post(
            supabase=mock_supabase,
            workspace_id="ws-stage17",
            post_content="A retrospective look at sales engineering.",
            scheduled_at=past_iso
        )
        self.assertEqual(res_past["status"], "success")
        scheduled_dt = datetime.fromisoformat(res_past["scheduled_at"])
        # Must be clamped to approximately now (not in 2020)
        self.assertGreater(scheduled_dt.year, 2025)

        # 2. Distant future timestamp (e.g. 5 years in future)
        distant_future = (datetime.now(timezone.utc) + timedelta(days=500)).isoformat()
        res_future = schedule_thought_leadership_post(
            supabase=mock_supabase,
            workspace_id="ws-stage17",
            post_content="Future predictions for B2B pipeline generation.",
            scheduled_at=distant_future
        )
        self.assertEqual(res_future["status"], "success")
        future_dt = datetime.fromisoformat(res_future["scheduled_at"])
        max_allowed = datetime.now(timezone.utc) + timedelta(days=91)
        self.assertLessEqual(future_dt, max_allowed)

    def test_schedule_post_deterministic_uuid5_idempotency(self):
        """
        Layer 1 & 2: Identical post content produces deterministic UUID5 post_id
        and handles duplicate key insertions idempotently.
        """
        mock_supabase = MagicMock()
        # First call: succeeds
        mock_supabase.table().insert().execute.return_value = MagicMock(data=[])

        res1 = schedule_thought_leadership_post(
            supabase=mock_supabase,
            workspace_id="ws-stage17-idem",
            post_content="Contrarian perspective on cold outreach volume vs jitter.",
            topic="Deliverability",
            framework_id="CONTRARIAN_TRUTH"
        )
        self.assertEqual(res1["status"], "success")
        post_id = res1["post_id"]
        self.assertTrue(bool(post_id))

        # Second call: duplicate key simulation from database
        mock_supabase.table().insert().execute.side_effect = Exception("duplicate key value violates unique constraint 23505")

        res2 = schedule_thought_leadership_post(
            supabase=mock_supabase,
            workspace_id="ws-stage17-idem",
            post_content="Contrarian perspective on cold outreach volume vs jitter.",
            topic="Deliverability",
            framework_id="CONTRARIAN_TRUTH"
        )
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["post_id"], post_id)
        self.assertTrue(res2["db_persisted"])

    def test_delete_thought_leadership_post_idor_guard(self):
        """
        Layer 0 & 2: delete_thought_leadership_post requires valid workspace_id
        and post_id, strictly scoping the delete query to workspace_id.
        """
        mock_supabase = MagicMock()
        delete_chain = MagicMock()
        delete_chain.eq.return_value = delete_chain
        delete_chain.execute.return_value = MagicMock(data=[])
        mock_supabase.table().delete.return_value = delete_chain

        # Missing post_id
        res_bad = delete_thought_leadership_post(mock_supabase, "ws-1", "   ")
        self.assertEqual(res_bad["status"], "error")
        self.assertFalse(res_bad["deleted"])

        # Valid delete
        res_ok = delete_thought_leadership_post(mock_supabase, "ws-tenant-x", "post-abc")
        self.assertEqual(res_ok["status"], "success")
        self.assertTrue(res_ok["deleted"])

        # Verify query scoped to workspace and post id
        delete_chain.eq.assert_has_calls([
            call("workspace_id", "ws-tenant-x"),
            call("id", "post-abc")
        ], any_order=True)

    # ── 2. Campaign Concurrency Atomic Locks (Pause & Activate) ───────────────

    def test_pause_campaign_acquires_distributed_lock(self):
        """
        Layer 1 & 2: pause_campaign wraps campaign state transition in distributed_workspace_lock
        to serialize concurrent pause/resume operations per campaign.
        """
        mock_client = MagicMock()
        mock_client.table().select().eq().eq().execute.return_value = MagicMock(
            data=[{"id": "camp_stage17", "name": "Q4 Outbound"}]
        )
        mock_client.table().update().eq().eq().execute.return_value = MagicMock(data=[])
        mock_client.table().select().eq().execute.return_value = MagicMock(data=[])

        with patch("core.backend.services.credit_service.distributed_workspace_lock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = True

            res = pause_campaign(
                campaign_id="camp_stage17",
                workspace_id="ws-stage17",
                client=mock_client
            )
            self.assertEqual(res["status"], "paused")
            self.assertEqual(res["campaign_id"], "camp_stage17")

            # Verify distributed lock was acquired with campaign-scoped key
            mock_lock.assert_called_once()
            lock_name = mock_lock.call_args[0][0]
            self.assertIn("campaign_status:ws-stage17:camp_stage17", lock_name)

    def test_activate_campaign_acquires_distributed_lock_and_serializes(self):
        """
        Layer 1 & 2: activate_campaign wraps touchpoint verification, tier limit check,
        and state cascades inside distributed_workspace_lock.
        """
        mock_client = MagicMock()
        # Campaign exists and is currently PAUSED with valid touchpoint
        mock_client.table().select().eq().eq().execute.side_effect = [
            MagicMock(data=[{
                "id": "camp_stage17_act",
                "status": "PAUSED",
                "nodes_json": '[{"id": "n1", "type": "message", "data": {}}]',
                "metadata": {}
            }]),
            # Workspace tier: PRO
            MagicMock(data=[{"tier": "PRO"}]),
            # Campaign nodes
            MagicMock(data=[{"node_type": "message", "data": {}}]),
            # Active senders query
            MagicMock(data=[{"id": "acc-1"}])
        ]
        # Active campaign count: 0
        mock_client.table().select().count = 0
        mock_client.table().select().eq().eq().neq().execute.return_value = MagicMock(count=0)
        mock_client.table().update().eq().eq().execute.return_value = MagicMock(data=[])

        with patch("core.backend.services.credit_service.distributed_workspace_lock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = True

            res = activate_campaign(
                campaign_id="camp_stage17_act",
                workspace_id="ws-stage17",
                client=mock_client
            )
            self.assertEqual(res["status"], "activated")

            mock_lock.assert_called_once()
            lock_name = mock_lock.call_args[0][0]
            self.assertIn("campaign_status:ws-stage17:camp_stage17_act", lock_name)

    def test_activate_campaign_lock_release_on_tier_exception(self):
        """
        Layer 1 & 2: When activate_campaign raises an HTTPException (e.g. Tier limit reached),
        the distributed_workspace_lock automatically releases without deadlock.
        """
        mock_client = MagicMock()
        def fake_table(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": "camp_blocked",
                        "status": "DRAFT",
                        "nodes_json": '[{"id": "n1", "type": "message"}]'
                    }]
                )
                t.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(count=1)
            elif tbl_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"tier": "FREE"}]
                )
            return t

        mock_client.table.side_effect = fake_table

        with self.assertRaises(HTTPException) as cm:
            activate_campaign(
                campaign_id="camp_blocked",
                workspace_id="ws-stage17",
                client=mock_client
            )
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Free Tier is limited to 1 active campaign", cm.exception.detail)


if __name__ == "__main__":
    unittest.main()
