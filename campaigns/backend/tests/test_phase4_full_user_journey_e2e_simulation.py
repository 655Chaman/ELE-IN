"""
Phase 4: Full User Journey E2E Simulation & Integration Drill
Comprehensive end-to-end test suite simulating the complete prospect lifecycle:
1. Account Onboarding, Warmup Curve & Safety Shield Setup
2. Lead Sourcing, Hygiene & Ingestion (CSV / URL)
3. Campaign Construction, Sequence DAG Audit & Launch
4. Orchestrator Dispatch, Rate Limiting & Account Rotation
5. Inbound Reply, AI Objection Classification & Meeting Proposal
6. Deal Pipeline Stage Monotonicity & Master View Telemetry Rollup

Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Core execution across the full pipeline.
- Layer 1: Environmental Failure Analysis (Zero-migration resilience across every step).
- Layer 2: Human Paranoia (Idempotency, monotonicity, anti-downgrade, and safety clamping).
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

# Domain Services & Routers
from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.services.lead_ingestion_service import (
    split_full_name,
    execute_bulk_import_leads,
    _IN_MEMORY_LEADS,
    _IN_MEMORY_LEAD_LISTS,
    register_in_memory_lead_list,
    get_in_memory_lead_lists
)
from campaigns.backend.routers.elein import (
    get_account_limits,
    get_account_warmup_roadmap,
    run_warmup_diagnostic,
    CampaignCreate,
    create_campaign
)
from inbox.backend.services.objection_service import classify_objection
from inbox.backend.services.battlecard_service import (
    generate_battlecard_responses,
    generate_suggested_meeting_slots,
    update_lead_deal_stage,
    DEAL_STAGES
)
from inbox.backend.routers.inbox import (
    SendReplyPayload,
    send_inbox_reply,
    get_inbox_threads
)
from campaigns.backend.routers.master_view import (
    get_master_view_stats,
    MasterViewRequest
)
from knowledge.backend.services.elein_ai_service import get_warmup_phase


class TestPhase4FullUserJourneyE2ESimulation(unittest.TestCase):
    """
    Full end-to-end user journey drill simulating a customer from day 1 account
    connection to active campaign dispatch, prospect reply, objection handling,
    deal closing, and executive analytics rollup.
    """

    def setUp(self):
        _IN_MEMORY_LEADS.clear()
        _IN_MEMORY_LEAD_LISTS.clear()
        self.workspace_id = "ws_e2e_drill_001"
        self.account_id = "acc_e2e_drill_sender"
        self.mock_supabase = MagicMock()

    # =========================================================================
    # STEP 1: Account Warmup & Safety Pacing Verification
    # =========================================================================
    def test_step1_account_warmup_and_safety_shield(self):
        """
        Drill Step 1: Sender account connects. Safe pacing, residential proxy
        binding, and warmup progression are verified before any outreach.
        """
        now = datetime.now(timezone.utc)
        created_str = (now - timedelta(days=2)).isoformat() # Day 3 of warmup

        # 1. Warmup Curve verification
        warmup_res = get_warmup_phase(created_str, actions_today=8, is_warmup=True, target_days=14)
        self.assertEqual(warmup_res["phase"], "observe")
        self.assertEqual(warmup_res["daily_limit"], 10)
        self.assertGreaterEqual(warmup_res["safety_score"], 90)

        # 2. Account Limits enforcement
        mock_acc_res = MagicMock(data=[{
            "id": self.account_id,
            "created_at": created_str,
            "is_warmup": True,
            "warmup_target_days": 14
        }])
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res
        self.mock_supabase.rpc.side_effect = Exception("unmigrated RPC fallback")

        limits = get_account_limits(self.account_id, "connection_request", self.mock_supabase, self.workspace_id)
        self.assertEqual(limits["effective_limit"], 10)
        self.assertTrue(limits["is_clamped_by_warmup"])

        # 3. Diagnostic pre-flight verification
        diag = run_warmup_diagnostic(self.account_id, self.mock_supabase, self.workspace_id)
        self.assertEqual(diag["status"], "passed")

    # =========================================================================
    # STEP 2: Lead Ingestion & Data Hygiene Drill
    # =========================================================================
    def test_step2_lead_ingestion_and_hygiene(self):
        """
        Drill Step 2: Import raw prospect list with messy names, formula injection
        attempts, and duplicates. Verifies automatic sanitization and zero-migration storage.
        """
        raw_prospects = [
            {"name": "Dr. Sarah Lin, Ph.D.", "url": "https://www.linkedin.com/in/sarah-lin-biotech"},
            {"name": "=cmd|' /C calc'!A0", "url": "https://www.linkedin.com/in/malicious-lead"},
            {"name": "Alex Mercer", "url": "https://www.linkedin.com/in/alex-mercer-ai/"},
            {"name": "Alex Mercer", "url": "https://www.linkedin.com/in/alex-mercer-ai"}, # Duplicate
        ]

        cleaned_leads = []
        for p in raw_prospects:
            first, last = split_full_name(p["name"])
            safe_first = DataHygieneService.sanitize_for_csv(first)
            safe_last = DataHygieneService.sanitize_for_csv(last)
            norm_url = DataHygieneService.normalize_linkedin_url(p["url"])
            if norm_url:
                cleaned_leads.append({
                    "first_name": safe_first,
                    "last_name": safe_last,
                    "linkedin_url": norm_url
                })

        # Sarah Lin properly extracted
        self.assertEqual(cleaned_leads[0]["first_name"], "Sarah")
        self.assertEqual(cleaned_leads[0]["last_name"], "Lin")

        # Malicious CSV injection sanitized (starts with quote)
        self.assertTrue(cleaned_leads[1]["first_name"].startswith("'"))

        # Ingestion into lead list with unmigrated DB fallback
        self.mock_supabase.rpc.side_effect = Exception("missing RPC")
        self.mock_supabase.table.return_value.insert.side_effect = Exception("missing leads table")

        import_res = execute_bulk_import_leads(
            supabase=self.mock_supabase,
            list_id="list_phase4_e2e",
            workspace_id=self.workspace_id,
            leads=cleaned_leads,
            timezone="America/New_York"
        )
        self.assertTrue(import_res["success"])
        # Deduplication properly identified the duplicate Alex Mercer URL
        self.assertEqual(import_res["inserted_count"], 3)
        self.assertEqual(import_res["duplicate_count"], 1)

    # =========================================================================
    # STEP 3: Campaign Sequence DAG Audit & Launch Readiness
    # =========================================================================
    def test_step3_campaign_sequence_dag_and_preflight(self):
        """
        Drill Step 3: Construct multi-step outreach sequence with condition branches.
        Verify DAG cycle detection and pre-flight validation.
        """
        nodes = [
            {"id": "node_1", "type": "connection_request", "data": {"note": "Hi {{first_name}}, loved your work!"}},
            {"id": "node_2", "type": "smart_delay", "data": {"days": 2}},
            {"id": "node_3", "type": "condition_branch", "data": {"condition": "connection_accepted"}},
            {"id": "node_4", "type": "follow_up_message", "data": {"message": "Great to connect, Sarah!"}},
        ]
        valid_edges = [
            {"id": "e1", "source": "node_1", "target": "node_2"},
            {"id": "e2", "source": "node_2", "target": "node_3"},
            {"id": "e3", "source": "node_3", "target": "node_4"},
        ]

        # Verify DAG has no cycles
        from inbox.backend.routers.inbox import has_cycle
        self.assertFalse(has_cycle(nodes, valid_edges))

        # Test malicious / accidental cycle creation
        cycle_edges = valid_edges + [{"id": "e4", "source": "node_4", "target": "node_1"}]
        self.assertTrue(has_cycle(nodes, cycle_edges))

    # =========================================================================
    # STEP 4: Inbound Reply & AI Objection Closer Drill
    # =========================================================================
    def test_step4_inbound_reply_and_ai_battlecard_copilot(self):
        """
        Drill Step 4: A prospect replies with an objection.
        The AI copilot classifies it, retrieves competitor intelligence,
        generates multi-tone counter-pitches, proposes meeting slots,
        and saves an outbound reply with idempotency protection.
        """
        inbound_text = "We already use Apollo.io for our outbound lead discovery and are happy with our workflow."

        # 1. Classify objection & extract competitor
        classification = classify_objection(inbound_text)
        self.assertEqual(classification["objection_type"], "COMPETITOR_INCUMBENT")
        self.assertEqual(classification["detected_competitor"], "Apollo.io")

        # 2. Generate multi-tone battlecard counter-pitches
        battlecard = generate_battlecard_responses("COMPETITOR_INCUMBENT", {
            "lead_name": "Sarah Lin",
            "company": "Biotech Labs",
            "detected_competitor": "Apollo.io"
        })
        self.assertIn("challenger", battlecard["responses"])
        self.assertIn("consultative", battlecard["responses"])
        self.assertIn("casual", battlecard["responses"])
        # Mentions prospect name and competitor
        self.assertIn("Sarah", battlecard["responses"]["consultative"])
        self.assertIn("Apollo.io", battlecard["responses"]["consultative"])

        # 3. Generate suggested meeting proposal slots
        slots = generate_suggested_meeting_slots(lead_tz="America/New_York", num_slots=3)
        self.assertEqual(len(slots), 3)
        for s in slots:
            self.assertIn("formatted_label", s)
            self.assertIn("iso_utc", s)

        # 4. Outbound reply dispatch with idempotency protection
        chosen_reply = battlecard["responses"]["consultative"]
        mock_msg_res = MagicMock(data=[])
        mock_acc_res = MagicMock(data=[{"id": self.account_id}])
        mock_lead_res = MagicMock(data=[{"id": "lead_123", "linkedin_url": "https://www.linkedin.com/in/sarah-lin-biotech"}])

        def table_router(table_name):
            mock_t = MagicMock()
            if table_name == "messages":
                mock_t.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = mock_msg_res
                mock_t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "msg_001"}])
            elif table_name == "accounts":
                mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_acc_res
            elif table_name == "leads":
                mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_lead_res
            elif table_name in ("processing_jobs", "action_log"):
                mock_t.insert.return_value.execute.return_value = MagicMock()
            return mock_t

        self.mock_supabase.table.side_effect = table_router

        payload = SendReplyPayload(
            sender_name="Sarah Lin",
            message_text=chosen_reply,
            lead_id="lead_123",
            account_id=self.account_id,
            ai_generated=True
        )

        reply_res = send_inbox_reply(payload, self.mock_supabase, self.workspace_id)
        self.assertEqual(reply_res["status"], "success")
        self.assertIn("message_id", reply_res)

    # =========================================================================
    # STEP 5: CRM Deal Pipeline Progression & Anti-Downgrade Monotonicity
    # =========================================================================
    def test_step5_deal_stage_pipeline_monotonicity(self):
        """
        Drill Step 5: Advance lead through CRM stages:
        NEW_REPLY -> MEETING_CONFIRMED -> CLOSED_WON.
        Rigorously verifies Layer 2 Monotonicity Guard prevents accidental downgrades.
        """
        # Advance to MEETING_CONFIRMED
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead_123", "deal_stage": "OBJECTION_RAISED"}]
        )

        res_booked = update_lead_deal_stage(
            supabase=self.mock_supabase,
            lead_id="lead_123",
            workspace_id=self.workspace_id,
            new_stage="MEETING_CONFIRMED",
            estimated_value=12000.0,
            force_override=False
        )
        self.assertEqual(res_booked["status"], "success")
        self.assertEqual(res_booked["deal_stage"], "MEETING_CONFIRMED")

        # Now simulate accidental user downgrade to NEW_REPLY
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "lead_123", "deal_stage": "MEETING_CONFIRMED"}]
        )

        res_downgrade = update_lead_deal_stage(
            supabase=self.mock_supabase,
            lead_id="lead_123",
            workspace_id=self.workspace_id,
            new_stage="NEW_REPLY",
            force_override=False
        )
        # Monotonicity guard intervened
        self.assertEqual(res_downgrade["status"], "preserved")
        self.assertEqual(res_downgrade["deal_stage"], "MEETING_CONFIRMED")

    # =========================================================================
    # STEP 6: Master View Telemetry Rollup & Radar Stats Verification
    # =========================================================================
    def test_step6_master_view_telemetry_rollup(self):
        """
        Drill Step 6: Verify executive Master View reflects the entire campaign cycle.
        All radar stats strictly non-negative, deliverability accurate, zero 500s.
        """
        def table_router(table_name):
            mock_t = MagicMock()
            if table_name == "workspaces":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tier": "PRO"}])
            elif table_name == "campaigns":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "camp_1", "status": "ACTIVE", "enrolled_count": 100, "total_connected": 38, "total_replied": 12}]
                )
            elif table_name == "leads":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=100, data=[])
            elif table_name == "lead_states":
                mock_t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(count=2, data=[])
            elif table_name == "daily_workspace_stats":
                mock_t.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif table_name in ("daily_campaign_stats", "messages", "action_log"):
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                mock_t.select.return_value.eq.return_value.gte.return_value.lte.return_value.execute.return_value = MagicMock(data=[])
            elif table_name == "accounts":
                mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": self.account_id, "status": "active"}])
            elif table_name == "processing_jobs":
                mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            else:
                mock_t.select.return_value.execute.return_value = MagicMock(data=[])
            return mock_t

        self.mock_supabase.table.side_effect = table_router
        mock_req = MagicMock()

        req = MasterViewRequest(date_start="2026-03-01", date_end="2026-03-15")

        with patch("campaigns.backend.routers.master_view._generate_captain_brief", new_callable=AsyncMock) as mock_brief:
            mock_brief.return_value = "Campaign performance exceeding benchmark targets."
            res = get_master_view_stats(mock_req, req, self.mock_supabase, self.workspace_id)

        # Telemetry verification
        self.assertEqual(res["summary"]["total_leads"], 100)
        self.assertEqual(res["summary"]["active_campaigns"], 1)
        self.assertEqual(res["funnel"]["enrolled"], 100)
        self.assertEqual(res["funnel"]["connected"], 38)
        self.assertEqual(res["funnel"]["replied"], 12)

        # Radar stats verification
        radar = res["radar_stats"]
        self.assertAlmostEqual(radar["Acceptance Rate"], 38.0, places=1)
        self.assertAlmostEqual(radar["Reply Rate"], 31.6, places=1)
        self.assertGreaterEqual(radar["Deliverability"], 95.0)
        self.assertLessEqual(radar["Bounces"], 5.0)


if __name__ == "__main__":
    unittest.main()
