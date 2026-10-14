import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException

from campaigns.backend.services.event_harvester_service import (
    harvest_event_attendees,
    list_events_and_attendees,
    enroll_event_attendees_batch,
    _HARVESTED_EVENT_LOCKS,
    _IN_MEMORY_EVENTS,
    _IN_MEMORY_ATTENDEES
)
from campaigns.backend.services.multimodal_service import (
    resolve_multimodal_asset_for_execution,
    list_multimodal_assets,
    delete_multimodal_asset,
    _ASSET_SYNTHESIS_LOCKS,
    _IN_MEMORY_MULTIMODAL
)
from campaigns.backend.routers.event_multimodal_router import (
    resolve_execution_asset_endpoint,
    ResolveMultimodalAssetPayload,
    enroll_attendees_endpoint,
    BatchEnrollAttendeesPayload,
    delete_multimodal_asset_endpoint
)


class TestHorizon35CEventMultimodalOrchestration(unittest.TestCase):
    """
    Horizon 35C: Event Harvester & Multimodal Personalized Asset Studio
    Unit tests under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    def setUp(self):
        # Clear locks before each test to ensure test isolation
        _HARVESTED_EVENT_LOCKS.clear()
        _ASSET_SYNTHESIS_LOCKS.clear()

    # -------------------------------------------------------------------------
    # TEST 1: Layer 0 (Foundational) - Event Harvester & Baseline Extraction
    # -------------------------------------------------------------------------
    def test_layer0_event_harvester_attendees_extraction_and_icebreaker(self):
        """Paranoia Layer 0: Harvests attendees with seniority tiers and baseline icebreakers."""
        res = harvest_event_attendees(
            event_url="https://www.linkedin.com/events/ai-outbound-summit-2026-901/",
            event_name="AI Outbound Summit 2026",
            workspace_id="ws-h35c-test1"
        )
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["count"], 1)
        self.assertFalse(res.get("duplicate_harvest_prevented", False))

        event_data = res["event"]
        self.assertEqual(event_data["event_name"], "AI Outbound Summit 2026")
        self.assertEqual(event_data["event_type"], "event")

        first_att = res["attendees"][0]
        self.assertIn("prospect_name", first_att)
        self.assertIn("company_name", first_att)
        self.assertIn("title", first_att)
        self.assertIn(first_att["seniority"], ["c_level", "vp", "director", "manager", "ic"])
        self.assertIn("AI Outbound Summit 2026", first_att["generated_icebreaker"])
        self.assertEqual(first_att["status"], "pending")

    # -------------------------------------------------------------------------
    # TEST 2: Layer 0 (Foundational) - Multimodal Voice & Video Execution Asset Resolution
    # -------------------------------------------------------------------------
    def test_layer0_multimodal_voice_script_and_video_card_resolution(self):
        """Paranoia Layer 0: Resolves standardized dict for both voice script and video card."""
        # 1. Voice script resolution
        voice_res = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-test2",
            lead_name="Evelyn Reed",
            company="Vanguard Data",
            title="VP Sales",
            asset_type="voice_script",
            tone="casual_peer"
        )
        self.assertEqual(voice_res["status"], "ready")
        self.assertEqual(voice_res["asset_type"], "voice_script")
        self.assertTrue(voice_res["asset_id"])
        self.assertIn("Evelyn", voice_res["multimodal_script"])
        self.assertIn("Vanguard Data", voice_res["multimodal_script"])
        self.assertGreaterEqual(voice_res["multimodal_duration"], 15)
        self.assertLessEqual(voice_res["multimodal_duration"], 45)
        self.assertIsNone(voice_res["multimodal_asset_url"])
        self.assertTrue(voice_res["lock_acquired"])
        self.assertFalse(voice_res["duplicate_prevented"])

        # 2. Video card resolution
        video_res = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-test2",
            lead_name="Marcus Vance",
            company="Apex Cloud",
            asset_type="video_card",
            video_topic="Pipeline Teardown"
        )
        self.assertEqual(video_res["status"], "ready")
        self.assertEqual(video_res["asset_type"], "video_card")
        self.assertTrue(video_res["asset_id"])
        self.assertIn("Marcus", video_res["multimodal_script"])
        self.assertTrue(video_res["multimodal_asset_url"].startswith("https://"))
        self.assertGreaterEqual(video_res["multimodal_duration"], 30)
        self.assertLessEqual(video_res["multimodal_duration"], 90)

    # -------------------------------------------------------------------------
    # TEST 3: Layer 0 (Foundational) - Tailored Event Icebreaker Synthesis
    # -------------------------------------------------------------------------
    def test_layer0_tailored_event_icebreaker_generation(self):
        """Paranoia Layer 0: Tailors event icebreaker when event_name is supplied."""
        # With event name
        res_with_event = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-test3",
            lead_name="Ada Lovelace",
            company="Analytical Engines",
            event_name="Women in Tech Summit 2026"
        )
        expected_icebreaker = "Ada, noticed you were also registered for Women in Tech Summit 2026! Would love to connect and share notes."
        self.assertEqual(res_with_event["event_icebreaker"], expected_icebreaker)

        # Without event name
        res_no_event = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-test3",
            lead_name="Charles Babbage",
            company="Difference Engine Corp",
            event_name=None
        )
        self.assertIsNone(res_no_event["event_icebreaker"])

    # -------------------------------------------------------------------------
    # TEST 4: Layer 1 (Environmental) - Event Harvester 2-Hour Deduplication Lock
    # -------------------------------------------------------------------------
    def test_layer1_event_harvester_deduplication_lock_2h_window(self):
        """Paranoia Layer 1: Returns cached harvest with duplicate_harvest_prevented=True within 2 hours."""
        url = "https://www.linkedin.com/events/gtm-pipeline-summit-2026-999/"
        ws = "ws-h35c-lock-evt"

        # First harvest: fresh
        res1 = harvest_event_attendees(event_url=url, event_name="GTM Summit", workspace_id=ws)
        self.assertEqual(res1["status"], "success")
        self.assertFalse(res1.get("duplicate_harvest_prevented", False))

        # Second harvest within 2 hours: locked duplicate prevented
        res2 = harvest_event_attendees(event_url=url, event_name="GTM Summit", workspace_id=ws)
        self.assertEqual(res2["status"], "success")
        self.assertTrue(res2.get("duplicate_harvest_prevented", False))
        self.assertEqual(res2["event"]["id"], res1["event"]["id"])
        self.assertEqual(len(res2["attendees"]), len(res1["attendees"]))

    # -------------------------------------------------------------------------
    # TEST 5: Layer 1 (Environmental) - Multimodal Synthesis 1-Hour Deduplication Lock
    # -------------------------------------------------------------------------
    def test_layer1_multimodal_synthesis_deduplication_lock_1h_window(self):
        """Paranoia Layer 1: Returns cached asset with duplicate_prevented=True on rapid retries within 1 hour."""
        ws = "ws-h35c-lock-synth"
        lead = "Grace Hopper"
        comp = "Navy Computing"

        # First call: fresh synthesis
        res1 = resolve_multimodal_asset_for_execution(
            workspace_id=ws,
            lead_name=lead,
            company=comp,
            asset_type="voice_script"
        )
        self.assertFalse(res1["duplicate_prevented"])
        self.assertTrue(res1["lock_acquired"])

        # Second call: cached
        res2 = resolve_multimodal_asset_for_execution(
            workspace_id=ws,
            lead_name=lead,
            company=comp,
            asset_type="voice_script"
        )
        self.assertTrue(res2["duplicate_prevented"])
        self.assertEqual(res2["asset_id"], res1["asset_id"])
        self.assertEqual(res2["multimodal_script"], res1["multimodal_script"])

    # -------------------------------------------------------------------------
    # TEST 6: Layer 1 (Environmental) - Voice & Video Duration Clamping
    # -------------------------------------------------------------------------
    def test_layer1_duration_clamping_voice_and_video(self):
        """Paranoia Layer 1: Enforces strict duration clamping (voice: 15-45s, video: 30-90s)."""
        # Voice duration is strictly clamped between 15s and 45s
        voice_res = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-durations",
            lead_name="Short Voice Test",
            company="Brief Inc",
            asset_type="voice_script"
        )
        self.assertGreaterEqual(voice_res["multimodal_duration"], 15)
        self.assertLessEqual(voice_res["multimodal_duration"], 45)

        # Video duration is strictly clamped between 30s and 90s
        video_res = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-durations",
            lead_name="Video Duration Test",
            company="Longform Inc",
            asset_type="video_card"
        )
        self.assertGreaterEqual(video_res["multimodal_duration"], 30)
        self.assertLessEqual(video_res["multimodal_duration"], 90)

    # -------------------------------------------------------------------------
    # TEST 7: Layer 2 (Human Paranoia) - Cross-Tenant IDOR Event & Attendee Isolation
    # -------------------------------------------------------------------------
    def test_layer2_idor_cross_tenant_event_and_attendee_isolation(self):
        """Paranoia Layer 2: Prevents cross-workspace data leakage and raises PermissionError on enrollment."""
        ws_alpha = "ws-tenant-alpha-7"
        ws_beta = "ws-tenant-beta-7"

        # Harvest under Tenant Alpha
        harvest_res = harvest_event_attendees(
            event_url="https://www.linkedin.com/events/alpha-private-summit-700/",
            event_name="Alpha Summit",
            workspace_id=ws_alpha
        )
        alpha_event_id = harvest_res["event"]["id"]
        alpha_att_id = harvest_res["attendees"][0]["id"]

        # Tenant Beta lists events & attendees: Tenant Alpha's data must NEVER leak
        beta_listing = list_events_and_attendees(workspace_id=ws_beta)
        beta_event_ids = [e["id"] for e in beta_listing["events"]]
        beta_att_ids = [a["id"] for a in beta_listing["attendees"]]
        self.assertNotIn(alpha_event_id, beta_event_ids)
        self.assertNotIn(alpha_att_id, beta_att_ids)

        # Tenant Beta attempts to enroll Tenant Alpha's attendee: MUST raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            enroll_event_attendees_batch(
                attendee_ids=[alpha_att_id],
                campaign_id="camp-beta-123",
                workspace_id=ws_beta
            )
        self.assertIn("Cross-workspace access denied for event attendee", str(ctx.exception))

    # -------------------------------------------------------------------------
    # TEST 8: Layer 2 (Human Paranoia) - Cross-Tenant IDOR Multimodal Asset Isolation
    # -------------------------------------------------------------------------
    def test_layer2_idor_cross_tenant_multimodal_asset_isolation(self):
        """Paranoia Layer 2: Prevents cross-workspace asset listing and raises PermissionError on deletion."""
        ws_alpha = "ws-tenant-alpha-8"
        ws_beta = "ws-tenant-beta-8"

        # Synthesize asset under Tenant Alpha
        alpha_asset = resolve_multimodal_asset_for_execution(
            workspace_id=ws_alpha,
            lead_name="Secret Lead",
            company="Confidential Corp",
            asset_type="voice_script"
        )
        alpha_asset_id = alpha_asset["asset_id"]

        # Tenant Beta lists assets: Tenant Alpha's asset must NEVER leak
        beta_assets = list_multimodal_assets(workspace_id=ws_beta)
        beta_asset_ids = [a["id"] for a in beta_assets]
        self.assertNotIn(alpha_asset_id, beta_asset_ids)

        # Tenant Beta attempts to delete Tenant Alpha's asset: MUST raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            delete_multimodal_asset(
                asset_id=alpha_asset_id,
                workspace_id=ws_beta
            )
        self.assertIn("Cross-workspace access denied for multimodal asset", str(ctx.exception))

    # -------------------------------------------------------------------------
    # TEST 9: Layer 2 (Human Paranoia) - Formula Injection & Strict HTTPS Protocol
    # -------------------------------------------------------------------------
    def test_layer2_formula_injection_and_strict_https_url_validation(self):
        """Paranoia Layer 2: Neutralizes formula injection and strictly enforces https:// schemes."""
        # 1. Formula injection neutralization in lead_name, company, and event_name
        res = resolve_multimodal_asset_for_execution(
            workspace_id="ws-h35c-security",
            lead_name="=@Alice Smith",
            company="+CorpSpreadsheet",
            event_name="@DangerousEvent"
        )
        # Leading formula characters stripped
        self.assertFalse(res["multimodal_script"].startswith(("=", "+", "-", "@", "\t", "\r")))
        self.assertIn("Alice", res["event_icebreaker"])
        self.assertNotIn("@DangerousEvent", res["event_icebreaker"])
        self.assertIn("DangerousEvent", res["event_icebreaker"])

        # 2. Strict https:// media URL enforcement: rejects javascript:, data:, file:, http:
        for bad_url in [
            "javascript:alert(document.cookie)",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "file:///etc/passwd",
            "http://insecure-domain.com/video.mp4"
        ]:
            with self.assertRaises(ValueError) as ctx:
                resolve_multimodal_asset_for_execution(
                    workspace_id="ws-h35c-security-2",
                    lead_name="Sec Test",
                    company="Sec Corp",
                    asset_type="video_card",
                    media_url=bad_url
                )
            self.assertIn("https", str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # TEST 10: Router Endpoints - Tier Permissions, 400, 402, and 403 Status Code Mapping
    # -------------------------------------------------------------------------
    def test_router_endpoints_tier_permissions_and_status_code_mapping(self):
        """Paranoia Layer 0, 1 & 2: Validates router error mappings: 402 for tier-gating, 400 for bad input, 403 for IDOR."""
        # 1. Feature Tier Gating (402) on free workspace
        mock_free_supabase = MagicMock()
        mock_free_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}

        payload = ResolveMultimodalAssetPayload(
            lead_name="Samantha Ray",
            company="OmniCorp",
            asset_type="voice_script"
        )
        with self.assertRaises(HTTPException) as ctx:
            resolve_execution_asset_endpoint(
                payload=payload,
                workspace_id="ws-real-free-tenant",
                supabase=mock_free_supabase
            )
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

        # 2. Invalid asset type maps ValueError to 400 Bad Request
        bad_payload = ResolveMultimodalAssetPayload(
            lead_name="Samantha Ray",
            company="OmniCorp",
            asset_type="unsupported_hologram"
        )
        with self.assertRaises(HTTPException) as ctx:
            resolve_execution_asset_endpoint(
                payload=bad_payload,
                workspace_id="ws-test",
                supabase=None
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # 3. Cross-Tenant Attendee Enrollment maps PermissionError to 403 Forbidden
        harvest = harvest_event_attendees(
            event_url="https://www.linkedin.com/events/restricted-conf-10/",
            event_name="Restricted Conf",
            workspace_id="ws-owner-alpha"
        )
        restricted_att_id = harvest["attendees"][0]["id"]

        enroll_payload = BatchEnrollAttendeesPayload(
            attendee_ids=[restricted_att_id],
            campaign_id="camp-intruder"
        )
        with self.assertRaises(HTTPException) as ctx:
            enroll_attendees_endpoint(
                payload=enroll_payload,
                workspace_id="ws-intruder-beta",
                supabase=None
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cross-workspace access denied", ctx.exception.detail)

        # 4. Cross-Tenant Multimodal Asset Deletion maps PermissionError to 403 Forbidden
        alpha_asset = resolve_multimodal_asset_for_execution(
            workspace_id="ws-owner-alpha",
            lead_name="Protected Lead",
            company="Vault Corp"
        )
        with self.assertRaises(HTTPException) as ctx:
            delete_multimodal_asset_endpoint(
                asset_id=alpha_asset["asset_id"],
                workspace_id="ws-intruder-beta",
                supabase=None
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cross-workspace access denied", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
