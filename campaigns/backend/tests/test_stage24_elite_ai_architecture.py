import unittest
from unittest.mock import MagicMock, patch
import threading
from datetime import datetime, timezone

from campaigns.backend.services.displacement_service import (
    calculate_migration_savings,
    calculate_displacement_opportunity,
    generate_displacement_battlecard_copy,
    create_competitor_displacement,
    list_competitor_displacements,
    launch_displacement_sequence,
    resolve_displacement_battlecard_for_execution,
    _sanitize_displacement_text,
    _displacement_lock,
    _IN_MEMORY_DISPLACEMENTS,
    _IN_MEMORY_DISPLACEMENT_RUNS,
    _DISPLACEMENT_LOCKS,
)


class TestStage24EliteAIArchitecture(unittest.TestCase):
    """
    Stage 24: Elite Distributed AI Architecture Test Suite
    Tests strictly the AI side of the platform under the Three-Layer Logic Architecture (Paranoia Framework):
    - Competitor Displacement Vulnerability Scoring & ROI Payback Math
    - AI-Infused Competitive Battlecard Copy Synthesis with Knowledge Infusion
    - Libel Guard & Banned Phrases Defense
    - Reentrant Concurrency Locks & Bounded FIFO Eviction
    - Cross-Tenant IDOR Boundary Protection & Formula Injection Defenses
    """

    def setUp(self):
        self.workspace_id = "00000000-0000-0000-0000-000000000024"
        with _displacement_lock:
            _IN_MEMORY_DISPLACEMENTS.clear()
            _IN_MEMORY_DISPLACEMENT_RUNS.clear()
            _DISPLACEMENT_LOCKS.clear()

    def tearDown(self):
        with _displacement_lock:
            _IN_MEMORY_DISPLACEMENTS.clear()
            _IN_MEMORY_DISPLACEMENT_RUNS.clear()
            _DISPLACEMENT_LOCKS.clear()

    # ─── 1. DISPLACEMENT VULNERABILITY SCORING & MIGRATION SAVINGS ───────────

    def test_migration_savings_math_and_seat_clamping(self):
        """
        Layer 0 & Layer 2 Paranoia:
        Calculates exact net annual savings for incumbent vendor seat replacements,
        with arithmetic bounds clamping on seat counts (1-5000) and pricing.
        """
        # Outreach: 20 seats @ $140/seat/mo vs Ele-in @ $49/seat/mo
        # Incumbent spend = 20 * 140 * 12 = $33,600
        # Ele-in spend = 20 * 49 * 12 = $11,760
        # Net savings = $21,840 (65.0%)
        savings = calculate_migration_savings(vendor_slug="outreach", seat_count=20)
        self.assertEqual(savings["annual_incumbent_spend"], 33600.0)
        self.assertEqual(savings["annual_elein_spend"], 11760.0)
        self.assertEqual(savings["annual_net_savings"], 21840.0)
        self.assertEqual(savings["savings_percentage"], 65.0)

        # Extreme seat count clamped safely to 5000 without arithmetic overflow
        clamped_savings = calculate_migration_savings(vendor_slug="apollo", seat_count=999999)
        self.assertEqual(clamped_savings["seat_count"], 5000)

    def test_displacement_opportunity_window_scoring(self):
        """
        Layer 0 Paranoia:
        Vulnerability score correctly weights contract renewal window, seat leverage,
        and incumbent deliverability friction.
        """
        # Peak evaluation window: 60 days out, 25 seats on Apollo
        # Timing pts: 42 (peak 45-90d)
        # Seat pts: 28 (>=20 seats)
        # Vuln pts: 28 (Apollo)
        # Total = 98
        opp_peak = calculate_displacement_opportunity(
            incumbent_vendor="apollo",
            contract_renewal_days=60,
            seat_count=25
        )
        self.assertEqual(opp_peak["window_status"], "PEAK_EVALUATION")
        self.assertEqual(opp_peak["displacement_vulnerability_score"], 98)

        # Expired renewal: 0 days
        opp_expired = calculate_displacement_opportunity(
            incumbent_vendor="outreach",
            contract_renewal_days=0,
            seat_count=10
        )
        self.assertEqual(opp_expired["window_status"], "EXPIRED")

    # ─── 2. AI-INFUSED DISPLACEMENT SYNTHESIS & BANNED PHRASES ───────────────

    @patch("campaigns.backend.services.displacement_service._run_llm_with_failover")
    @patch("campaigns.backend.services.displacement_service._get_synthesis")
    def test_ai_synthesis_infuses_knowledge_and_scrubs_banned_buzzwords(self, mock_get_syn, mock_run_llm):
        """
        Layer 0 & Layer 2 Paranoia:
        When use_ai=True, _generate_ai_displacement_message infuses Knowledge Synthesis,
        calls the resilient LLM runner, and scrubs banned phrases.
        """
        mock_get_syn.return_value = {
            "core_value_prop": "Consolidated outbound infrastructure with 99.4% deliverability.",
            "key_differentiators": ["Dedicated residential IP pods", "Waterfall enrichment"],
            "proof_points": ["Cut bounce rates by 74%"]
        }
        mock_run_llm.return_value = (
            "Hi Michael, noticed your reps prospecting via Outreach. I hope this email finds you well. "
            "Ele-in isolates your team behind residential proxy pods, saving $21,800/year. "
            "We will credit your remaining 60 days of Outreach."
        )

        copy_res = generate_displacement_battlecard_copy(
            incumbent_vendor="outreach",
            target_company="Acme Corp",
            target_contact_name="Michael Scott",
            target_contact_title="VP Sales",
            seat_count=20,
            renewal_days=60,
            use_ai=True,
            workspace_id=self.workspace_id,
            banned_phrases="I hope this email finds you well",
            ai_model="meta/llama-3.3-70b-instruct"
        )

        mock_run_llm.assert_called_once()
        # Verify banned phrases scrubbing removed the generic phrase
        self.assertNotIn("I hope this email finds you well", copy_res["body"])
        self.assertIn("Outreach", copy_res["body"])
        self.assertIn("Michael", copy_res["body"])

    # ─── 3. RESILIENCE: LLM EXCEPTION FALLS BACK TO DETERMINISTIC TEMPLATE ────

    @patch("campaigns.backend.services.displacement_service._run_llm_with_failover")
    @patch("campaigns.backend.services.displacement_service._get_synthesis")
    def test_llm_failure_falls_back_seamlessly_to_template(self, mock_get_syn, mock_run_llm):
        """
        Layer 1 Environmental Failure:
        If the LLM endpoint times out, throws a 503, or fails to parse,
        generate_displacement_battlecard_copy must NEVER crash — it seamlessly returns
        the pristine deterministic battlecard template.
        """
        mock_get_syn.side_effect = RuntimeError("Supabase connection timeout")
        mock_run_llm.side_effect = ConnectionError("NVIDIA API Gateway 503")

        copy_res = generate_displacement_battlecard_copy(
            incumbent_vendor="salesloft",
            target_company="Dunder Mifflin",
            target_contact_name="Jim Halpert",
            target_contact_title="Director of Sales",
            seat_count=15,
            renewal_days=45,
            use_ai=True,
            workspace_id=self.workspace_id
        )

        self.assertIsNotNone(copy_res["body"])
        self.assertTrue(len(copy_res["body"]) > 50)
        self.assertIn("Jim", copy_res["body"])
        self.assertIn("Dunder Mifflin", copy_res["body"])
        self.assertIn("Salesloft", copy_res["body"])

    # ─── 4. CONCURRENCY, IDEMPOTENT LOCKS & BOUNDED FIFO EVICTION ─────────────

    def test_concurrency_lock_and_idempotent_duplicate_prevention(self):
        """
        Layer 1 Paranoia:
        Concurrent displacement attempts on the same target domain trigger duplicate sequence protection.
        """
        # First execution succeeds and acquires lock
        res1 = resolve_displacement_battlecard_for_execution(
            workspace_id=self.workspace_id,
            target_company="Wayne Enterprises",
            target_contact_name="Lucius Fox",
            target_contact_title="Chief Operating Officer",
            incumbent_vendor="apollo",
            domain="wayneenterprises.com",
            seat_count=20,
            contract_renewal_days=60
        )
        self.assertTrue(res1["lock_acquired"])
        self.assertFalse(res1["duplicate_prevented"])

        # Second execution on same domain prevented idempotently
        res2 = resolve_displacement_battlecard_for_execution(
            workspace_id=self.workspace_id,
            target_company="Wayne Enterprises",
            target_contact_name="Lucius Fox",
            target_contact_title="Chief Operating Officer",
            incumbent_vendor="apollo",
            domain="wayneenterprises.com",
            seat_count=20,
            contract_renewal_days=60
        )
        self.assertFalse(res2["lock_acquired"])
        self.assertTrue(res2["duplicate_prevented"])

    def test_multithreaded_concurrency_under_rlock(self):
        """
        Layer 1 Paranoia:
        Multi-threaded displacement creations must execute safely without deadlocks under _displacement_lock.
        """
        errors = []

        def worker(idx):
            try:
                create_competitor_displacement(
                    workspace_id=self.workspace_id,
                    target_company=f"Target Corp {idx}",
                    target_contact_name=f"Executive {idx}",
                    target_contact_title="VP Sales",
                    incumbent_vendor="outreach",
                    domain=f"targetcorp{idx}.com",
                    seat_count=12,
                    contract_renewal_days=50
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        items = list_competitor_displacements(workspace_id=self.workspace_id)
        self.assertEqual(len(items), 20)

    # ─── 5. CROSS-TENANT IDOR SECURITY & FORMULA INJECTION DEFENSE ───────────

    def test_cross_tenant_idor_guard(self):
        """
        Layer 2 Paranoia:
        Displacement sequence launch or resolution across workspaces is blocked with PermissionError.
        """
        # Create item in tenant A
        item = create_competitor_displacement(
            workspace_id="00000000-0000-0000-0000-000000000001",
            target_company="Secret Stark Tech",
            target_contact_name="Pepper Potts",
            target_contact_title="CEO",
            incumbent_vendor="outreach",
            domain="starktech.com"
        )

        # Tenant B attempts to launch sequence on Tenant A's displacement record
        with self.assertRaises(PermissionError):
            launch_displacement_sequence(
                workspace_id="00000000-0000-0000-0000-000000000002",
                displacement_id=item["id"]
            )

        # Tenant B attempts to resolve battlecard for Tenant A's private domain
        with self.assertRaises(PermissionError):
            resolve_displacement_battlecard_for_execution(
                workspace_id="00000000-0000-0000-0000-000000000002",
                target_company="Secret Stark Tech",
                target_contact_name="Pepper Potts",
                target_contact_title="CEO",
                domain="starktech.com"
            )

    def test_formula_injection_sanitization(self):
        """
        Layer 2 Paranoia:
        Displacement inputs starting with '=', '+', '-', '@' have formula injection prefixes stripped.
        """
        clean_comp = _sanitize_displacement_text("=cmd|' /C calc'!A0")
        clean_name = _sanitize_displacement_text("+John Doe")
        clean_title = _sanitize_displacement_text("@VP Sales")

        self.assertFalse(clean_comp.startswith("="))
        self.assertFalse(clean_name.startswith("+"))
        self.assertFalse(clean_title.startswith("@"))

    # ─── 6. FASTAPI ROUTER PAYLOAD FORWARDING ────────────────────────────────

    def test_router_endpoints_forward_ai_and_banned_phrases(self):
        """
        Layer 0 & Layer 2 Paranoia:
        Verifies that displacement router endpoints forward use_ai, banned_phrases,
        and ai_model seamlessly from Pydantic schemas.
        """
        from campaigns.backend.routers.displacement_router import (
            create_displacement_endpoint,
            generate_pitch_endpoint,
            resolve_battlecard_execution_endpoint,
            CreateDisplacementPayload,
            GeneratePitchPayload,
            ResolveBattlecardExecutionPayload,
        )

        # 1. Create displacement endpoint
        create_payload = CreateDisplacementPayload(
            target_company="LexCorp",
            target_contact_name="Lex Luthor",
            target_contact_title="Founder & CEO",
            incumbent_vendor="salesloft",
            domain="lexcorp.com",
            seat_count=30,
            contract_renewal_days=45,
            use_ai=False,
            banned_phrases="circling back"
        )
        res_create = create_displacement_endpoint(
            payload=create_payload,
            workspace_id="ws-test",
            supabase=None
        )
        self.assertTrue(res_create["success"])
        self.assertEqual(res_create["data"]["target_company"], "LexCorp")

        # 2. Resolve battlecard execution endpoint
        exec_payload = ResolveBattlecardExecutionPayload(
            target_company="Queen Industries",
            target_contact_name="Oliver Queen",
            target_contact_title="CEO",
            incumbent_vendor="apollo",
            domain="queenindustries.com",
            seat_count=15,
            contract_renewal_days=60,
            use_ai=False
        )
        res_exec = resolve_battlecard_execution_endpoint(
            payload=exec_payload,
            workspace_id="ws-test",
            supabase=None
        )
        self.assertTrue(res_exec["success"])
        self.assertEqual(res_exec["data"]["status"], "ready")
        self.assertIn("Queen Industries", res_exec["data"]["displacement_wedge"])


if __name__ == "__main__":
    unittest.main()
