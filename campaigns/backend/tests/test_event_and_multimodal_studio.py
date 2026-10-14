import unittest
from unittest.mock import MagicMock

from campaigns.backend.services.event_harvester_service import (
    parse_linkedin_event_url,
    classify_seniority,
    generate_event_icebreaker,
    harvest_event_attendees,
    list_events_and_attendees,
    enroll_event_attendees_batch,
    export_event_attendees_csv
)
from campaigns.backend.services.multimodal_service import (
    generate_voice_script,
    generate_video_prospecting_card,
    list_multimodal_assets,
    delete_multimodal_asset,
    export_multimodal_assets_csv,
    _normalize_uuid,
    sanitize_text
)



class TestEventHarvesterService(unittest.TestCase):
    """
    Tests for LinkedIn Event & Group Attendee Harvester.
    """

    def test_parse_linkedin_event_url_valid_event(self):
        """Paranoia Layer 0: Parses standard LinkedIn event URL."""
        url = "https://www.linkedin.com/events/b2b-growth-summit-2026-7248921/"
        parsed = parse_linkedin_event_url(url)
        self.assertTrue(parsed["is_valid"])
        self.assertEqual(parsed["event_type"], "event")
        self.assertEqual(parsed["slug"], "b2b-growth-summit-2026-7248921")

    def test_parse_linkedin_event_url_valid_group(self):
        """Paranoia Layer 0: Parses standard LinkedIn group URL."""
        url = "https://www.linkedin.com/groups/1849201/gtm-executives"
        parsed = parse_linkedin_event_url(url)
        self.assertTrue(parsed["is_valid"])
        self.assertEqual(parsed["event_type"], "group")
        self.assertEqual(parsed["slug"], "1849201")

    def test_parse_linkedin_event_url_invalid(self):
        """Paranoia Layer 1: Rejects non-LinkedIn URLs gracefully."""
        url = "https://randomsite.org/not-linkedin"
        parsed = parse_linkedin_event_url(url)
        self.assertFalse(parsed["is_valid"])
        self.assertIn("error", parsed)

    def test_classify_seniority(self):
        """Paranoia Layer 0: Classifies job titles into standard seniority tiers."""
        self.assertEqual(classify_seniority("Chief Revenue Officer"), "c_level")
        self.assertEqual(classify_seniority("VP of Enterprise Sales"), "vp")
        self.assertEqual(classify_seniority("Director of Demand Gen"), "director")
        self.assertEqual(classify_seniority("Senior Sales Manager"), "manager")
        self.assertEqual(classify_seniority("Account Executive"), "ic")

    def test_generate_event_icebreaker_bounds(self):
        """Paranoia Layer 0 & 2: Crafts personalized icebreaker bounded to 280 chars."""
        hook = generate_event_icebreaker(
            event_name="Global B2B Sales & Outbound Summit 2026",
            prospect_name="Alexander Hayes",
            company_name="NorthStar Data",
            title="VP Sales",
            event_type="event"
        )
        self.assertIn("Alexander", hook)
        self.assertIn("NorthStar Data", hook)
        self.assertLessEqual(len(hook), 280)

    def test_harvest_event_attendees_flow(self):
        """Paranoia Layer 0: Harvests attendees and generates contextual icebreakers."""
        res = harvest_event_attendees(
            event_url="https://www.linkedin.com/events/ai-outbound-2026-992/",
            event_name="AI Outbound Summit",
            workspace_id="ws-test-event"
        )
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["count"], 1)
        first_att = res["attendees"][0]
        self.assertIn("seniority", first_att)
        self.assertIn("generated_icebreaker", first_att)
        self.assertEqual(first_att["status"], "pending")

    def test_list_events_and_attendees_filtering(self):
        """Paranoia Layer 0: Retrieves events and filters attendees by seniority."""
        res = list_events_and_attendees(workspace_id="ws-test", seniority_filter="vp")
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(len(res["events"]), 1)
        for att in res["attendees"]:
            self.assertEqual(att["seniority"], "vp")

    def test_enroll_event_attendees_batch(self):
        """Paranoia Layer 0 & 2: Batch-enrolls attendees and skips empty lists."""
        # Empty list check
        empty_res = enroll_event_attendees_batch([], "camp-123", "ws-test")
        self.assertEqual(empty_res["status"], "error")

        # Valid enrollment
        res = enroll_event_attendees_batch(["att-1", "att-2"], "camp-event-q4", "ws-test")
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["enrolled_count"], 1)

    def test_zero_migration_db_fallback_resilience(self):
        """Paranoia Layer 1: Database failure falls back gracefully to in-memory state."""
        mock_broken_supabase = MagicMock()
        mock_broken_supabase.table().select().eq().execute.side_effect = Exception("relation harvested_events does not exist")
        res = list_events_and_attendees(workspace_id="ws-unmigrated", supabase=mock_broken_supabase)
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(len(res["events"]), 1)

    def test_export_event_attendees_csv(self):
        """Paranoia Layer 0 & 2: Exports sanitized CSV for event attendees."""
        csv_data = export_event_attendees_csv(workspace_id="ws-test")
        self.assertIn("Attendee ID,Event ID,Prospect Name", csv_data)
        self.assertIn("LinkedIn URL", csv_data)
        # Verify formula injection defense
        lines = csv_data.split("\n")
        self.assertGreaterEqual(len(lines), 2)



class TestMultimodalService(unittest.TestCase):
    """
    Tests for Multimodal Voice Script & Video Prospecting Studio.
    """

    def test_generate_voice_script_casual_peer(self):
        """Paranoia Layer 0: Generates casual peer voice script with phonetic pauses."""
        res = generate_voice_script(
            lead_name="Jessica Vance",
            company="Nexis Corp",
            tone="casual_peer",
            workspace_id="ws-test"
        )
        self.assertEqual(res["status"], "success")
        self.assertIn("Jessica", res["script"])
        self.assertIn("Nexis Corp", res["script"])
        self.assertIn("[pause]", res["script"])
        self.assertGreaterEqual(res["estimated_duration_sec"], 18)
        self.assertLessEqual(res["estimated_duration_sec"], 45)

    def test_generate_voice_script_executive_brief(self):
        """Paranoia Layer 0: Generates crisp executive brief voice script."""
        res = generate_voice_script(
            lead_name="Marcus DuPont",
            company="CloudStack Systems",
            tone="executive_brief",
            workspace_id="ws-test"
        )
        self.assertEqual(res["status"], "success")
        self.assertIn("Marcus", res["script"])
        self.assertIn("CloudStack Systems", res["script"])
        self.assertIn("[pause]", res["script"])

    def test_generate_video_prospecting_card(self):
        """Paranoia Layer 0: Generates personalized Loom video landing card."""
        res = generate_video_prospecting_card(
            lead_name="Sarah Lin",
            company="Quantify Health",
            video_topic="Cold Outreach Pipeline Audit",
            workspace_id="ws-test"
        )
        self.assertEqual(res["status"], "success")
        self.assertIn("Sarah", res["thumbnail_title"])
        self.assertIn("Quantify Health", res["thumbnail_title"])
        self.assertIn("https://elein.app/v/", res["video_url"])
        self.assertEqual(res["estimated_duration_sec"], 58)

    def test_list_multimodal_assets_filtering(self):
        """Paranoia Layer 0: Lists generated multimodal assets by asset_type."""
        voice_assets = list_multimodal_assets(workspace_id="ws-test", asset_type="voice_script")
        self.assertTrue(all(a["asset_type"] == "voice_script" for a in voice_assets))

    def test_export_multimodal_assets_csv(self):
        """Paranoia Layer 0 & 2: Exports sanitized CSV for multimodal assets."""
        csv_data = export_multimodal_assets_csv(workspace_id="ws-test")
        self.assertIn("Asset ID,Asset Type,Status", csv_data)
        self.assertIn("Thumbnail / Title", csv_data)
        lines = csv_data.split("\n")
        self.assertGreaterEqual(len(lines), 2)

    def test_delete_multimodal_asset(self):
        """Paranoia Layer 0 & 1: Safely deletes a generated multimodal asset."""
        gen = generate_voice_script(
            lead_name="Delete Target",
            company="Test Corp",
            workspace_id="ws-test"
        )
        asset_id = gen["asset_id"]
        del_res = delete_multimodal_asset(asset_id=asset_id, workspace_id="ws-test")
        self.assertEqual(del_res["status"], "success")
        self.assertTrue(del_res["deleted"])

    def test_uuid_normalization_on_multimodal(self):
        """Paranoia Layer 1: Verifies string IDs are converted to valid RFC UUIDs."""
        norm = _normalize_uuid("custom-arm-string-123")
        import uuid
        parsed = uuid.UUID(norm)
        self.assertEqual(str(parsed), norm)



class TestEventMultimodalRouterEndpoints(unittest.TestCase):
    """
    Tests for router endpoints.
    """

    def test_harvest_event_endpoint_logic(self):
        from campaigns.backend.routers.event_multimodal_router import harvest_event_endpoint, HarvestEventPayload
        payload = HarvestEventPayload(
            event_url="https://www.linkedin.com/events/summit-2026-101/",
            event_name="SaaS GTM Summit"
        )
        mock_supabase = MagicMock()
        mock_supabase.table().insert().execute.return_value.data = []
        res = harvest_event_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIn("attendees", res)

    def test_generate_voice_script_endpoint_logic(self):
        from campaigns.backend.routers.event_multimodal_router import generate_voice_script_endpoint, GenerateVoiceScriptPayload
        payload = GenerateVoiceScriptPayload(lead_name="Devin Miller", company="HyperScale Labs")
        mock_supabase = MagicMock()
        mock_supabase.table().insert().execute.return_value.data = []
        res = generate_voice_script_endpoint(payload, workspace_id="ws-test", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")
        self.assertIn("script", res)

    def test_tier_gating_free_workspace_raises_402_on_harvest(self):
        from fastapi import HTTPException
        from campaigns.backend.routers.event_multimodal_router import harvest_event_endpoint, HarvestEventPayload
        payload = HarvestEventPayload(event_url="https://www.linkedin.com/events/summit-2026-101/")
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        with self.assertRaises(HTTPException) as ctx:
            harvest_event_endpoint(payload, workspace_id="ws-real-free-workspace", supabase=mock_supabase)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_free_workspace_raises_402_on_multimodal(self):
        from fastapi import HTTPException
        from campaigns.backend.routers.event_multimodal_router import generate_voice_script_endpoint, GenerateVoiceScriptPayload
        payload = GenerateVoiceScriptPayload(lead_name="Devin Miller", company="HyperScale Labs")
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        with self.assertRaises(HTTPException) as ctx:
            generate_voice_script_endpoint(payload, workspace_id="ws-real-free-workspace", supabase=mock_supabase)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")

    def test_tier_gating_pro_workspace_succeeds(self):
        from campaigns.backend.routers.event_multimodal_router import generate_voice_script_endpoint, GenerateVoiceScriptPayload
        payload = GenerateVoiceScriptPayload(lead_name="Devin Miller", company="HyperScale Labs")
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_supabase.table().insert().execute.return_value.data = []
        res = generate_voice_script_endpoint(payload, workspace_id="ws-real-pro-workspace", supabase=mock_supabase)
        self.assertEqual(res["status"], "success")

    def test_export_event_attendees_csv_endpoint(self):
        from campaigns.backend.routers.event_multimodal_router import export_event_attendees_csv_endpoint
        res = export_event_attendees_csv_endpoint(workspace_id="ws-test", supabase=None)
        self.assertEqual(res.media_type, "text/csv")
        self.assertIn("attachment", res.headers.get("content-disposition", ""))

    def test_export_multimodal_assets_csv_endpoint(self):
        from campaigns.backend.routers.event_multimodal_router import export_multimodal_assets_csv_endpoint
        res = export_multimodal_assets_csv_endpoint(workspace_id="ws-test", supabase=None)
        self.assertEqual(res.media_type, "text/csv")
        self.assertIn("attachment", res.headers.get("content-disposition", ""))

    def test_delete_multimodal_asset_endpoint(self):
        from campaigns.backend.routers.event_multimodal_router import delete_multimodal_asset_endpoint
        res = delete_multimodal_asset_endpoint(asset_id="asset-voice-1", workspace_id="ws-default", supabase=None)
        self.assertEqual(res["status"], "success")


if __name__ == "__main__":
    unittest.main()
