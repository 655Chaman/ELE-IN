import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException

from campaigns.backend.services.boomerang_revival_service import (
    _ENROLLED_BOOMERANG_LOCKS,
    _sanitize_boomerang_text,
    create_champion_job_change,
    create_warm_intro_path,
    create_closed_lost_revival,
    list_champion_job_changes,
    list_warm_intro_paths,
    list_closed_lost_revivals,
    enroll_boomerang_or_revival,
    resolve_boomerang_hook_for_execution,
)
from campaigns.backend.routers.boomerang_router import (
    EnrollItemPayload,
    ResolveExecutionHookPayload,
    enroll_item_endpoint,
    resolve_execution_hook_endpoint,
)


class TestHorizon34bBoomerangOrchestration(unittest.TestCase):
    def setUp(self):
        _ENROLLED_BOOMERANG_LOCKS.clear()

    def test_01_layer0_job_change_buying_window_resolution(self):
        """Layer 0: Resolves Peak 90-Day job-change boomerang hook and score."""
        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="Elena Vance",
            mode="job_change",
            previous_company="Stripe",
            previous_title="Director of Revenue Operations",
            new_company="Datadog",
            new_title="VP of Global Revenue Operations",
            days_in_new_role=25,
            relationship_type="past_customer",
        )
        self.assertEqual(res["status"], "ready")
        self.assertFalse(res["suppressed"])
        self.assertEqual(res["mode"], "job_change")
        self.assertGreaterEqual(res["score"], 90)
        self.assertIn("Datadog", res["hook_message"])
        self.assertIn("Stripe", res["hook_message"])
        self.assertEqual(res["metadata"]["window_tier"], "PEAK_90_DAY")

    def test_02_layer0_closed_lost_revival_resolution(self):
        """Layer 0: Resolves Closed-Lost deal revival hook with feature trigger."""
        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="Marcus Sterling",
            mode="closed_lost_revival",
            previous_company="Figma",
            new_company="Figma",
            new_title="VP of Sales",
            lost_reason="missing_feature",
            days_since_lost=120,
            original_deal_value=55000.0,
            revival_trigger="Autonomous ABM Buying Committee Studio",
        )
        self.assertEqual(res["status"], "ready")
        self.assertFalse(res["suppressed"])
        self.assertEqual(res["mode"], "closed_lost_revival")
        self.assertEqual(res["score"], 90)
        self.assertIn("Autonomous ABM Buying Committee Studio", res["hook_message"])

    def test_03_layer0_warm_intro_bridge_resolution(self):
        """Layer 0: Resolves Warm-Intro dual scripts (direct bridge + connector ask)."""
        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="aria Montgomery",
            mode="warm_intro",
            new_company="OpenAI",
            new_title="Head of Enterprise GTM",
            connector_name="David Kim",
            connector_role="General Partner at Sequoia",
            bridge_type="shared_investor",
            overlap_context="Series B GTM Advisory Board",
        )
        self.assertEqual(res["status"], "ready")
        self.assertFalse(res["suppressed"])
        self.assertEqual(res["score"], 93)
        self.assertIn("David Kim", res["hook_message"])
        self.assertIn("Series B GTM Advisory Board", res["intro_request_draft"])

    def test_04_layer1_opted_out_prospect_suppression_guard(self):
        """Layer 1: Immediately suppresses boomerang outreach if prospect is opted out."""
        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="Opted Out Exec",
            mode="job_change",
            previous_company="Plaid",
            new_company="Ramp",
            new_title="CRO",
            is_opted_out=True,
        )
        self.assertEqual(res["status"], "suppressed")
        self.assertTrue(res["suppressed"])
        self.assertEqual(res["hook_message"], "")
        self.assertEqual(res["score"], 0)

    def test_05_layer1_supabase_suppression_list_guard(self):
        """Layer 1: Blocks revival when prospect email matches workspace suppression_list in Supabase."""
        mock_sb = MagicMock()
        chain = mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value
        chain.execute.return_value = MagicMock(data=[{"id": "sup-1", "email": "dnc@vercel.com"}])

        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="Blocked Prospect",
            mode="closed_lost_revival",
            new_company="Vercel",
            days_since_lost=90,
            email="DNC@vercel.com",
            supabase=mock_sb,
        )
        self.assertEqual(res["status"], "suppressed")
        self.assertTrue(res["suppressed"])
        self.assertEqual(res["hook_message"], "")
        self.assertEqual(res["score"], 0)

    def test_06_layer1_idempotent_duplicate_enrollment_lock(self):
        """Layer 1: Prevents duplicate enrollment of the same boomerang item into the same campaign."""
        first = enroll_boomerang_or_revival(
            workspace_id="ws-alpha",
            item_id="jc-101",
            item_type="job_change",
            campaign_id="camp-exec-90",
        )
        self.assertFalse(first["duplicate_prevented"])

        second = enroll_boomerang_or_revival(
            workspace_id="ws-alpha",
            item_id="jc-101",
            item_type="job_change",
            campaign_id="camp-exec-90",
        )
        self.assertTrue(second["duplicate_prevented"])
        self.assertEqual(first["enrolled_at"], second["enrolled_at"])

    def test_07_layer2_internal_company_promotion_detection(self):
        """Layer 2: Detects internal company promotion so copy never says 'left X to join X'."""
        res = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="Claire Dunphy",
            mode="job_change",
            previous_company="Snowflake",
            previous_title="VP of Sales",
            new_company="snowflake",
            new_title="Chief Revenue Officer",
            days_in_new_role=18,
        )
        self.assertTrue(res["metadata"]["is_internal_promotion"])
        self.assertIn("internal promotion", res["hook_message"])
        self.assertNotIn("move from", res["hook_message"])

    def test_08_layer2_anti_pestering_14_day_cooldown_guard(self):
        """Layer 2: Blocks reviving Closed-Lost deals lost < 14 days ago unless force_override=True."""
        with self.assertRaises(ValueError):
            resolve_boomerang_hook_for_execution(
                workspace_id="ws-alpha",
                prospect_name="Too Soon",
                mode="closed_lost_revival",
                new_company="Linear",
                days_since_lost=5,
                force_override=False,
            )

        with self.assertRaises(HTTPException) as ctx:
            resolve_execution_hook_endpoint(
                payload=ResolveExecutionHookPayload(
                    prospect_name="Too Soon",
                    mode="closed_lost_revival",
                    new_company="Linear",
                    days_since_lost=5,
                    force_override=False,
                ),
                workspace_id="ws-test",
                supabase=None,
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # Succeeds when force_override=True
        overridden = resolve_boomerang_hook_for_execution(
            workspace_id="ws-alpha",
            prospect_name="Too Soon",
            mode="closed_lost_revival",
            new_company="Linear",
            days_since_lost=5,
            force_override=True,
        )
        self.assertEqual(overridden["status"], "ready")

    def test_09_layer2_formula_injection_sanitization(self):
        """Layer 2: Strips leading spreadsheet formula injection characters (=, +, -, @) on creation and execution."""
        self.assertEqual(_sanitize_boomerang_text("=CMD|' /C calc'!A0"), "CMD|' /C calc'!A0")
        self.assertEqual(_sanitize_boomerang_text("+@=-jected Company"), "jected Company")

        created = create_champion_job_change(
            workspace_id="ws-test",
            prospect_name="=Malicious Prospect",
            previous_company="@EvilOldCorp",
            previous_title="-Director",
            new_company="+SafeNewCorp",
            new_title="=VP of Growth",
        )
        self.assertFalse(created["prospect_name"].startswith("="))
        self.assertEqual(created["previous_company"], "EvilOldCorp")
        self.assertEqual(created["new_company"], "SafeNewCorp")
        self.assertEqual(created["new_title"], "VP of Growth")

    def test_10_layer2_cross_tenant_idor_isolation(self):
        """Layer 2: Prevents Tenant B from listing or enrolling Tenant A's private boomerang records."""
        tenant_a_jc = create_champion_job_change(
            workspace_id="ws-tenant-a",
            prospect_name="Tenant A Secret Champion",
            previous_company="Twilio",
            previous_title="VP Sales",
            new_company="Stripe",
            new_title="CRO",
        )
        tenant_a_wp = create_warm_intro_path(
            workspace_id="ws-tenant-a",
            target_prospect_name="Tenant A Target",
            target_company="Anthropic",
            target_title="CRO",
            connector_name="Tenant A Connector",
            connector_role="Board Partner",
        )
        tenant_a_rev = create_closed_lost_revival(
            workspace_id="ws-tenant-a",
            prospect_name="Tenant A Revival",
            company_name="Notion",
            title="VP RevOps",
            days_since_lost=90,
        )

        # Tenant B listing must not include Tenant A's records
        b_jcs = list_champion_job_changes(workspace_id="ws-tenant-b")
        b_wps = list_warm_intro_paths(workspace_id="ws-tenant-b")
        b_revs = list_closed_lost_revivals(workspace_id="ws-tenant-b")
        self.assertNotIn(tenant_a_jc["id"], [r["id"] for r in b_jcs])
        self.assertNotIn(tenant_a_wp["id"], [r["id"] for r in b_wps])
        self.assertNotIn(tenant_a_rev["id"], [r["id"] for r in b_revs])

        # Tenant B attempting to enroll Tenant A's item raises PermissionError / HTTP 403
        with self.assertRaises(PermissionError):
            enroll_boomerang_or_revival(
                workspace_id="ws-tenant-b",
                item_id=tenant_a_jc["id"],
                item_type="job_change",
            )

        with self.assertRaises(HTTPException) as ctx:
            enroll_item_endpoint(
                payload=EnrollItemPayload(item_id=tenant_a_jc["id"], item_type="job_change"),
                workspace_id="ws-tenant-b",
                supabase=None,
            )
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
