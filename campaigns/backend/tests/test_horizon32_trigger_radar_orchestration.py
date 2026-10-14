from datetime import datetime, timedelta
import os
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from campaigns.backend.routers.bandit_router import (
    EnrollTriggerPayload,
    IngestTriggerSignalPayload,
    enroll_trigger_endpoint,
    ingest_trigger_signal_endpoint,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.services.trigger_radar_service import (
    _IN_MEMORY_TRIGGERS,
    _SEED_TRIGGER_EVENTS,
    dismiss_trigger_event,
    enroll_lead_from_trigger,
    ingest_trigger_radar_signal,
    resolve_trigger_icebreaker_for_lead,
)


class TestHorizon32TriggerRadarOrchestration(unittest.TestCase):
    """
    Horizon 32: Trigger Radar Live Signal Ingestion, Deduplicated Auto-Enrollment
    & Icebreaker Injection in Sequence Orchestrator.
    Verifies Layer 0 (Foundational), Layer 1 (Environmental Resilience), and Layer 2 (Human Paranoia).
    """

    def setUp(self):
        _IN_MEMORY_TRIGGERS.clear()
        _IN_MEMORY_TRIGGERS.extend([dict(t) for t in _SEED_TRIGGER_EVENTS])
        os.environ["TEST_MODE"] = "true"

    # -------------------------------------------------------------------------
    # LAYER 0: FOUNDATIONAL LAYER
    # -------------------------------------------------------------------------
    def test_layer0_ingest_trigger_signal_generates_icebreaker_and_auto_enrolls(self):
        res = ingest_trigger_radar_signal(
            workspace_id="ws-h32",
            prospect_name="Kiran Rao",
            company_name="NovaScale AI",
            event_type="FUNDING_ROUND",
            event_data={"round_type": "Series A", "amount_raised": "$18M"},
            lead_id="lead-kiran-1",
            auto_enroll_campaign_id="camp-funding-blitz",
        )
        self.assertEqual(res["status"], "success")
        self.assertIn("$18M Series A", res["icebreaker"])
        self.assertIn("NovaScale AI", res["icebreaker"])
        self.assertIsNotNone(res["auto_enrollment"])
        self.assertEqual(res["auto_enrollment"]["status"], "success")
        self.assertEqual(res["trigger_event"]["status"], "ENROLLED")
        self.assertEqual(res["trigger_event"]["enrolled_campaign_id"], "camp-funding-blitz")

    def test_layer0_sequence_message_interpolates_trigger_icebreaker_and_event_type(self):
        ingest_trigger_radar_signal(
            workspace_id="ws-h32-exec",
            prospect_name="Sora Takahashi",
            company_name="ZetaCloud",
            event_type="PROMOTION",
            event_data={"new_title": "VP of Sales"},
            lead_id="lead-sora-9",
        )
        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success"}
        executor = EleInNodeExecutor(worker=mock_worker, supabase=None, workspace_id="ws-h32-exec")

        msg_res = executor.handle_send_message(
            {
                "_lead_id": "lead-sora-9",
                "first_name": "Sora",
                "last_name": "Takahashi",
                "company": "ZetaCloud",
                "body": "{{trigger_icebreaker}} (Signal: {{trigger_event_type}})",
            },
            "https://linkedin.com/in/sora",
        )
        self.assertEqual(msg_res["status"], "success")
        self.assertIn("VP of Sales", msg_res["body_sent"])
        self.assertIn("ZetaCloud", msg_res["body_sent"])
        self.assertIn("(Signal: PROMOTION)", msg_res["body_sent"])

    def test_layer0_handle_trigger_radar_enrich_node_resolves_or_ingests_signal(self):
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-h32-node")
        res = executor.handle_trigger_radar_enrich(
            {
                "_lead_id": "lead-hiring-1",
                "first_name": "Liam",
                "last_name": "Vance",
                "company": "OrbitOps",
                "event_type": "HIRING_SURGE",
                "event_data": {"open_sales_roles": 8},
            },
            "https://linkedin.com/in/liam",
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "Found")
        self.assertEqual(res["event_type"], "HIRING_SURGE")
        self.assertIn("8 new SDRs", res["icebreaker"])
        self.assertIn("trigger_icebreaker", res["variables"])

    def test_layer0_ingest_trigger_signal_endpoint_executes_cleanly(self):
        payload = IngestTriggerSignalPayload(
            prospect_name="Nadia Malik",
            company_name="VectorFlow",
            event_type="NEW_ROLE",
            event_data={"new_title": "CRO"},
            lead_id="lead-nadia-1",
            auto_enroll_campaign_id="camp-cro-1",
        )
        res = ingest_trigger_signal_endpoint(payload, workspace_id="ws-test", supabase=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["auto_enrollment"]["campaign_id"], "camp-cro-1")

    # -------------------------------------------------------------------------
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # -------------------------------------------------------------------------
    def test_layer1_stale_signal_expiration_guard_rejects_old_events(self):
        stale_date = (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d")
        res = ingest_trigger_radar_signal(
            workspace_id="ws-stale",
            prospect_name="Arthur Pendelton",
            company_name="LegacyCorp",
            event_type="NEW_ROLE",
            event_data={"new_title": "VP Growth", "start_date": stale_date},
            max_signal_age_days=90,
        )
        self.assertEqual(res["status"], "expired_signal")
        self.assertEqual(res["reason"], "STALE_SIGNAL_EXPIRED")
        self.assertGreater(res["age_days"], 90)

    def test_layer1_duplicate_signal_ingestion_is_idempotent(self):
        first = ingest_trigger_radar_signal(
            workspace_id="ws-dedupe",
            prospect_name="Chloe Bennett",
            company_name="PulseMetrics",
            event_type="FUNDING_ROUND",
            event_data={"round_type": "Seed", "amount_raised": "$5M"},
            lead_id="lead-chloe-1",
        )
        self.assertEqual(first["status"], "success")

        second = ingest_trigger_radar_signal(
            workspace_id="ws-dedupe",
            prospect_name="Chloe Bennett",
            company_name="PulseMetrics",
            event_type="FUNDING_ROUND",
            event_data={"round_type": "Seed", "amount_raised": "$5M"},
            lead_id="lead-chloe-1",
        )
        self.assertEqual(second["status"], "deduplicated")
        self.assertEqual(second["trigger_event_id"], first["trigger_event_id"])

    def test_layer1_missing_trigger_signal_falls_back_cleanly_without_raw_braces(self):
        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success"}
        executor = EleInNodeExecutor(worker=mock_worker, supabase=None, workspace_id="ws-empty-trig")

        res = executor.handle_send_message(
            {
                "_lead_id": "lead-no-signal-999",
                "first_name": "Tessa",
                "company": "StealthCo",
                "body": "{{trigger_icebreaker}} Let's connect!",
            },
            "https://linkedin.com/in/tessa",
        )
        self.assertEqual(res["status"], "success")
        self.assertNotIn("{{trigger_icebreaker}}", res["body_sent"])
        self.assertIn("Tessa", res["body_sent"])
        self.assertIn("StealthCo", res["body_sent"])

    def test_layer1_dismissed_trigger_excluded_from_lead_icebreaker_resolution(self):
        ingested = ingest_trigger_radar_signal(
            workspace_id="ws-dismiss-res",
            prospect_name="Victor Hugo",
            company_name="LesMis Tech",
            event_type="NEW_ROLE",
            lead_id="lead-victor-1",
        )
        trig_id = ingested["trigger_event_id"]
        dismiss_trigger_event(trig_id, workspace_id="ws-dismiss-res")

        resolved = resolve_trigger_icebreaker_for_lead(
            workspace_id="ws-dismiss-res",
            lead_id="lead-victor-1",
        )
        self.assertFalse(resolved["found"])

    # -------------------------------------------------------------------------
    # LAYER 2: HUMAN PARANOIA (THE HUMAN ERROR ELEMENT)
    # -------------------------------------------------------------------------
    def test_layer2_cross_tenant_idor_blocked_on_enroll_and_dismiss_trigger(self):
        ingested = ingest_trigger_radar_signal(
            workspace_id="ws-tenant-owner",
            prospect_name="Owner Prospect",
            company_name="OwnerCo",
            event_type="NEW_ROLE",
        )
        trig_id = ingested["trigger_event_id"]

        with self.assertRaises(PermissionError):
            enroll_lead_from_trigger(
                trigger_event_id=trig_id,
                campaign_id="camp-attacker",
                workspace_id="ws-tenant-attacker",
            )

        with self.assertRaises(PermissionError):
            dismiss_trigger_event(
                trigger_event_id=trig_id,
                workspace_id="ws-tenant-attacker",
            )

    def test_layer2_cannot_enroll_dismissed_trigger_event(self):
        ingested = ingest_trigger_radar_signal(
            workspace_id="ws-dismiss-guard",
            prospect_name="Dismissed Lead",
            company_name="DismissCo",
            event_type="PROMOTION",
        )
        trig_id = ingested["trigger_event_id"]
        dismiss_trigger_event(trig_id, workspace_id="ws-dismiss-guard")

        enroll_res = enroll_lead_from_trigger(
            trigger_event_id=trig_id,
            campaign_id="camp-1",
            workspace_id="ws-dismiss-guard",
        )
        self.assertEqual(enroll_res["status"], "ignored")
        self.assertIn("dismissed", enroll_res["message"].lower())

    def test_layer2_formula_injection_sanitized_in_ingested_trigger_signal(self):
        res = ingest_trigger_radar_signal(
            workspace_id="ws-formula-trig",
            prospect_name="=CMD|' /C calc'!A0 Jane",
            company_name="+@SUM(1+1) EvilCorp",
            event_type="NEW_ROLE",
            event_data={"new_title": "-=IMPORTXML('http://evil') VP Sales"},
        )
        self.assertEqual(res["status"], "success")
        ev = res["trigger_event"]
        self.assertFalse(ev["prospect_name"].startswith("="))
        self.assertFalse(ev["company_name"].startswith(("+", "@")))
        self.assertFalse(ev["event_data"]["new_title"].startswith(("-", "=")))
        self.assertFalse(res["icebreaker"].startswith(("=", "+", "-", "@")))

    def test_layer2_router_returns_403_on_cross_tenant_trigger_enroll(self):
        ingested = ingest_trigger_radar_signal(
            workspace_id="ws-tenant-a",
            prospect_name="Tenant A Lead",
            company_name="Tenant A Corp",
            event_type="FUNDING_ROUND",
        )
        payload = EnrollTriggerPayload(
            trigger_event_id=ingested["trigger_event_id"],
            campaign_id="camp-b",
        )
        with self.assertRaises(HTTPException) as ctx:
            enroll_trigger_endpoint(payload, workspace_id="ws-test", supabase=None)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
