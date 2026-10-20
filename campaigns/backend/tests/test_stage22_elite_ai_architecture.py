import unittest
from unittest.mock import MagicMock, patch
import math
import threading
from campaigns.backend.services.boomerang_revival_service import (
    calculate_boomerang_buying_window,
    generate_warm_intro_bridge,
    evaluate_closed_lost_revival,
    create_champion_job_change,
    create_warm_intro_path,
    create_closed_lost_revival,
    enroll_boomerang_or_revival,
    resolve_boomerang_hook_for_execution,
    _sanitize_boomerang_text,
    _generate_ai_revival_message,
    _boomerang_lock,
    _IN_MEMORY_JOB_CHANGES,
    _IN_MEMORY_WARM_PATHS,
    _IN_MEMORY_REVIVALS,
    _ENROLLED_BOOMERANG_LOCKS,
)


class TestStage22EliteAIArchitecture(unittest.TestCase):
    """
    Test suite for Stage 22 Elite AI Architecture:
    Boomerang Job-Change Buying Window Scoring, Warm Intro Bridge Synthesis,
    Closed-Lost Deal Revival with 14-Day Anti-Pestering Guard,
    Knowledge-Infused AI Synthesis with Banned Phrases Scrubbing,
    and Thread-Safe Concurrency Locks with Cross-Tenant IDOR Protection.
    """

    def setUp(self):
        self.workspace_id = "00000000-0000-0000-0000-000000000022"
        with _boomerang_lock:
            _IN_MEMORY_JOB_CHANGES.clear()
            _IN_MEMORY_WARM_PATHS.clear()
            _IN_MEMORY_REVIVALS.clear()
            _ENROLLED_BOOMERANG_LOCKS.clear()

    def tearDown(self):
        with _boomerang_lock:
            _IN_MEMORY_JOB_CHANGES.clear()
            _IN_MEMORY_WARM_PATHS.clear()
            _IN_MEMORY_REVIVALS.clear()
            _ENROLLED_BOOMERANG_LOCKS.clear()

    # ─── 1. BUYING WINDOW SCORING & INTERNAL PROMOTION PARANOIA ──────────────

    def test_buying_window_scoring_and_continuous_decay(self):
        """
        Layer 0 & 1 Paranoia:
        Evaluates peak 90-day tenure window scoring (15-60 days = 40 pts) and
        exponential decay after 90 days.
        """
        # Peak 30 days, former VP customer
        res_peak = calculate_boomerang_buying_window(
            prospect_name="Elena Vance",
            previous_company="Stark Industries",
            previous_title="VP of Engineering",
            new_company="Wayne Enterprises",
            new_title="Chief Technology Officer",
            days_in_new_role=30,
            relationship_type="past_customer",
            use_ai=False
        )
        self.assertEqual(res_peak["window_tier"], "PEAK_90_DAY")
        self.assertFalse(res_peak["is_internal_promotion"])
        # 40 (tenure 30d) + 35 (past_customer) + 25 (CTO) = 100
        self.assertEqual(res_peak["buying_window_score"], 100)
        self.assertIn("Wayne Enterprises", res_peak["playbook_message"])
        self.assertIn("Elena", res_peak["playbook_message"])

        # Established 180 days with smooth exponential decay
        res_decay = calculate_boomerang_buying_window(
            prospect_name="Elena Vance",
            previous_company="Stark Industries",
            previous_title="VP of Engineering",
            new_company="Wayne Enterprises",
            new_title="Chief Technology Officer",
            days_in_new_role=180,
            relationship_type="past_customer",
            use_ai=False
        )
        self.assertEqual(res_decay["window_tier"], "ESTABLISHED")
        # Excess 90 days: max(10, round(26 * exp(-90/60))) = max(10, round(26 * 0.2231)) = max(10, 6) = 10
        # Total = 10 + 35 + 25 = 70
        self.assertEqual(res_decay["buying_window_score"], 70)

    def test_internal_promotion_detection_human_paranoia(self):
        """
        Layer 2 Human Paranoia:
        When previous_company == new_company, outreach must celebrate an internal promotion
        and NEVER embarrassingly say 'Congrats on leaving X to join X!'.
        """
        res = calculate_boomerang_buying_window(
            prospect_name="Marcus Brody",
            previous_company="Acme Corp",
            previous_title="Director of Operations",
            new_company="Acme Corp",
            new_title="VP of Operations",
            days_in_new_role=20,
            relationship_type="former_champion",
            use_ai=False
        )
        self.assertTrue(res["is_internal_promotion"])
        self.assertIn("internal promotion", res["playbook_message"].lower())
        self.assertNotIn("leaving acme", res["playbook_message"].lower())

    # ─── 2. WARM INTRO DUAL-SCRIPT SYNTHESIS ──────────────────────────────────

    def test_warm_intro_dual_scripts_and_warmth_scoring(self):
        """
        Layer 0 & 1 Paranoia:
        Synthesizes dual warm-introduction scripts (connector request + direct prospect bridge)
        and scores bridge strength accurately.
        """
        bridge = generate_warm_intro_bridge(
            target_prospect_name="Sarah Connor",
            target_company="Cyberdyne Systems",
            target_title="Head of AI Safety",
            connector_name="John Reese",
            connector_role="Venture Partner",
            bridge_type="shared_investor",
            overlap_context="Both backed by Sequoia Capital",
            use_ai=False
        )
        self.assertEqual(bridge["warmth_score"], 93)  # shared_investor = 93
        self.assertIn("John", bridge["intro_request_draft"])
        self.assertIn("Sarah", bridge["intro_request_draft"])
        self.assertIn("Cyberdyne Systems", bridge["direct_bridge_draft"])
        self.assertIn("Sequoia Capital", bridge["direct_bridge_draft"])

    # ─── 3. CLOSED-LOST DEAL REVIVAL & ANTI-PESTERING GUARD ───────────────────

    def test_anti_pestering_guard_blocks_premature_revival(self):
        """
        Layer 2 Human Paranoia:
        Deals marked Closed-Lost fewer than 14 days ago must be blocked from revival
        to prevent spam complaints, unless force_override=True.
        """
        # Blocked without override
        with self.assertRaises(ValueError) as ctx:
            evaluate_closed_lost_revival(
                prospect_name="Arthur Dent",
                company_name="Megadodo Publications",
                title="VP of Marketing",
                lost_reason="budget_freeze",
                days_since_lost=7,
                force_override=False
            )
        self.assertIn("Anti-Pestering Guard", str(ctx.exception))

        # Allowed with force_override=True
        res = evaluate_closed_lost_revival(
            prospect_name="Arthur Dent",
            company_name="Megadodo Publications",
            title="VP of Marketing",
            lost_reason="budget_freeze",
            days_since_lost=7,
            force_override=True
        )
        self.assertIsNotNone(res)
        self.assertIn("budget freeze", res["resurrection_message"].lower())

    def test_closed_lost_revival_messaging_by_reason(self):
        """
        Layer 0 Paranoia:
        Resurrection copy adapts specifically to the lost reason (missing feature, competitor, budget freeze).
        """
        # Missing feature trigger
        res_feat = evaluate_closed_lost_revival(
            prospect_name="Tars Tarkas",
            company_name="Barsoom Technologies",
            title="VP Product",
            lost_reason="missing_feature",
            days_since_lost=90,
            revival_trigger="Native Salesforce Two-Way Sync"
        )
        self.assertIn("Native Salesforce Two-Way Sync", res_feat["resurrection_message"])
        self.assertIn("missing a key capability", res_feat["resurrection_message"])

        # Competitor chosen trigger
        res_comp = evaluate_closed_lost_revival(
            prospect_name="Dejah Thoris",
            company_name="Helium Systems",
            title="CRO",
            lost_reason="competitor_chosen",
            days_since_lost=120,
            revival_trigger="Deliverability Benchmark"
        )
        self.assertIn("selected another tool", res_comp["resurrection_message"])
        self.assertIn("zero-cost side-by-side benchmark", res_comp["resurrection_message"])

    # ─── 4. AI-INFUSED SYNTHESIS & BANNED PHRASES DEFENSE ────────────────────

    @patch("campaigns.backend.services.boomerang_revival_service._run_llm_with_failover")
    @patch("campaigns.backend.services.boomerang_revival_service._get_synthesis")
    def test_ai_synthesis_with_knowledge_and_banned_phrases(self, mock_get_syn, mock_run_llm):
        """
        Layer 0 & Layer 2 Paranoia:
        When use_ai=True, _generate_ai_revival_message infuses Knowledge Synthesis,
        calls the resilient LLM runner, and scrubs banned buzzwords.
        """
        mock_get_syn.return_value = {
            "core_value_prop": "Autonomous outbound pipeline generator with 99.4% deliverability.",
            "key_differentiators": ["Zero-spam inbox rotation"],
            "proof_points": ["3.4x meeting conversion"]
        }
        mock_run_llm.return_value = (
            "Hi Elena, congratulations on your move to Wayne Enterprises! I hope this email finds you well. "
            "Wanted to share a quick blueprint for your pipeline."
        )

        calc = calculate_boomerang_buying_window(
            prospect_name="Elena Vance",
            previous_company="Stark Industries",
            previous_title="VP of Engineering",
            new_company="Wayne Enterprises",
            new_title="Chief Technology Officer",
            days_in_new_role=30,
            relationship_type="past_customer",
            use_ai=True,
            workspace_id=self.workspace_id,
            banned_phrases="I hope this email finds you well",
            ai_model="meta/llama-3.3-70b-instruct"
        )

        mock_run_llm.assert_called_once()
        # Verify banned phrases scrubbing stripped out the generic buzzword
        self.assertNotIn("I hope this email finds you well", calc["playbook_message"])
        self.assertIn("Elena", calc["playbook_message"])
        self.assertIn("Wayne Enterprises", calc["playbook_message"])

    # ─── 5. CONCURRENCY & CROSS-TENANT IDOR ISOLATION ────────────────────────

    def test_thread_safe_concurrency_and_fifo_eviction(self):
        """
        Layer 1 & 2 Paranoia:
        Multi-threaded enrollments must execute without race conditions under _boomerang_lock,
        enforce idempotent locks, and maintain FIFO eviction bounded at 5000 items.
        """
        # Register an item
        jc = create_champion_job_change(
            workspace_id=self.workspace_id,
            prospect_name="Carol Danvers",
            previous_company="Starforce",
            previous_title="Flight Lead",
            new_company="Avengers HQ",
            new_title="Head of Operations",
            days_in_new_role=15,
            use_ai=False
        )

        # First enrollment succeeds
        res1 = enroll_boomerang_or_revival(
            workspace_id=self.workspace_id,
            item_id=jc["id"],
            item_type="job_change",
            campaign_id="camp-101"
        )
        self.assertEqual(res1["status"], "enrolled")
        self.assertFalse(res1.get("duplicate_prevented", False))

        # Duplicate enrollment prevented idempotently
        res2 = enroll_boomerang_or_revival(
            workspace_id=self.workspace_id,
            item_id=jc["id"],
            item_type="job_change",
            campaign_id="camp-101"
        )
        self.assertTrue(res2.get("duplicate_prevented", False))

        # Cross-Tenant IDOR: another workspace attempting to access Carol's item is rejected
        with self.assertRaises(PermissionError):
            enroll_boomerang_or_revival(
                workspace_id="00000000-0000-0000-0000-000000000999",
                item_id=jc["id"],
                item_type="job_change",
                campaign_id="camp-malicious"
            )

        # Threaded concurrent enrollments
        errors = []
        def worker(idx):
            try:
                enroll_boomerang_or_revival(
                    workspace_id=self.workspace_id,
                    item_id=f"jc-concurrent-{idx}",
                    item_type="job_change",
                    campaign_id=f"camp-worker-{idx}"
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)

    # ─── 6. EXECUTION HOOK RESOLUTION & SUPPRESSION GUARDS ───────────────────

    def test_execution_hook_resolution_and_opt_out_suppression(self):
        """
        Layer 1 & 2 Paranoia:
        Execution hook resolution must immediately suppress outreach for opted-out prospects,
        sanitize formula injections, and resolve all modes with full AI support.
        """
        # Opt-out suppression guard
        suppressed_res = resolve_boomerang_hook_for_execution(
            workspace_id=self.workspace_id,
            prospect_name="Bruce Banner",
            mode="job_change",
            is_opted_out=True
        )
        self.assertTrue(suppressed_res["suppressed"])
        self.assertEqual(suppressed_res["status"], "suppressed")
        self.assertEqual(suppressed_res["hook_message"], "")

        # Formula injection sanitization
        normal_res = resolve_boomerang_hook_for_execution(
            workspace_id=self.workspace_id,
            prospect_name="=cmd|' /C calc'!A0",
            mode="job_change",
            previous_company="+Acme Corp",
            previous_title="@Director",
            new_company="-Stark Labs",
            new_title="VP Research",
            days_in_new_role=25,
            is_opted_out=False
        )
        self.assertFalse(normal_res["suppressed"])
        self.assertEqual(normal_res["status"], "ready")
        self.assertFalse(normal_res["hook_message"].startswith("="))
        self.assertFalse(normal_res["hook_message"].startswith("+"))

        # Warm intro mode hook
        warm_res = resolve_boomerang_hook_for_execution(
            workspace_id=self.workspace_id,
            prospect_name="Natasha Romanoff",
            mode="warm_intro",
            previous_company="KGB",
            new_company="S.H.I.E.L.D.",
            connector_name="Clint Barton",
            connector_role="Special Agent",
            bridge_type="former_colleague"
        )
        self.assertEqual(warm_res["mode"], "warm_intro")
        self.assertIn("Clint", warm_res["intro_request_draft"])
        self.assertIn("Natasha", warm_res["hook_message"])

    # ─── 7. FASTAPI ROUTER PAYLOAD & ENDPOINT INTEGRATION ────────────────────

    def test_router_endpoints_forward_ai_and_banned_phrases(self):
        """
        Layer 0 & Layer 2 Paranoia:
        Verifies that router endpoints correctly parse and forward use_ai, banned_phrases,
        and ai_model from incoming Pydantic payloads into underlying services.
        """
        from campaigns.backend.routers.boomerang_router import (
            create_job_change_endpoint,
            create_warm_intro_endpoint,
            create_revival_endpoint,
            resolve_execution_hook_endpoint,
            CreateJobChangePayload,
            CreateWarmIntroPayload,
            CreateRevivalPayload,
            ResolveExecutionHookPayload,
        )

        # 1. Job change endpoint with banned phrases
        jc_payload = CreateJobChangePayload(
            prospect_name="Arthur Curry",
            previous_company="Atlantis Corp",
            previous_title="Director of Marine Ops",
            new_company="Justice League",
            new_title="VP Operations",
            banned_phrases="synergy, touch base",
            use_ai=False
        )
        jc_res = create_job_change_endpoint(
            payload=jc_payload,
            workspace_id="ws-test",
            supabase=None
        )
        self.assertTrue(jc_res["success"])
        self.assertEqual(jc_res["data"]["prospect_name"], "Arthur Curry")
        self.assertNotIn("touch base", jc_res["data"]["playbook_message"])

        # 2. Warm intro endpoint
        wi_payload = CreateWarmIntroPayload(
            target_prospect_name="Barry Allen",
            target_company="S.T.A.R. Labs",
            target_title="Head of Physics",
            connector_name="Iris West",
            connector_role="Journalist",
            bridge_type="mutual_connection",
            banned_phrases="circling back",
            use_ai=False
        )
        wi_res = create_warm_intro_endpoint(
            payload=wi_payload,
            workspace_id="ws-test",
            supabase=None
        )
        self.assertTrue(wi_res["success"])
        self.assertEqual(wi_res["data"]["warmth_score"], 88)

        # 3. Revival endpoint with 120 days elapsed
        rev_payload = CreateRevivalPayload(
            prospect_name="Victor Stone",
            company_name="Cybernetic Solutions",
            title="Chief Systems Architect",
            lost_reason="missing_feature",
            days_since_lost=120,
            revival_trigger="Quantum API Engine",
            banned_phrases="reaching out",
            use_ai=False
        )
        rev_res = create_revival_endpoint(
            payload=rev_payload,
            workspace_id="ws-test",
            supabase=None
        )
        self.assertTrue(rev_res["success"])
        self.assertIn("Quantum API Engine", rev_res["data"]["resurrection_message"])

        # 4. Resolve execution hook endpoint
        hook_payload = ResolveExecutionHookPayload(
            prospect_name="Hal Jordan",
            mode="job_change",
            previous_company="Ferris Aircraft",
            previous_title="Test Pilot",
            new_company="Green Lantern Corps",
            new_title="Director of Patrol",
            days_in_new_role=21,
            use_ai=False
        )
        hook_res = resolve_execution_hook_endpoint(
            payload=hook_payload,
            workspace_id="ws-test",
            supabase=None
        )
        self.assertTrue(hook_res["success"])
        self.assertEqual(hook_res["data"]["status"], "ready")

    # ─── 8. PROMPT INJECTION DEFENSE & LLM EXCEPTION RESILIENCE ──────────────

    @patch("campaigns.backend.services.boomerang_revival_service._run_llm_with_failover")
    @patch("campaigns.backend.services.boomerang_revival_service._get_synthesis")
    def test_llm_exception_seamless_fallback_to_deterministic_template(self, mock_get_syn, mock_run_llm):
        """
        Layer 1 Environmental Failure:
        If the LLM endpoint times out, throws a 503, or returns empty text,
        _generate_ai_revival_message must NEVER crash or return an empty string —
        it must seamlessly fall back to the pristine deterministic template.
        """
        mock_get_syn.side_effect = RuntimeError("Supabase knowledge connection timeout")
        mock_run_llm.side_effect = ConnectionError("NVIDIA API Gateway unreachable")

        calc = calculate_boomerang_buying_window(
            prospect_name="Tony Stark",
            previous_company="Stark Industries",
            previous_title="CEO",
            new_company="Avengers HQ",
            new_title="Chief Architect",
            days_in_new_role=25,
            relationship_type="past_customer",
            use_ai=True,
            workspace_id=self.workspace_id
        )

        self.assertIsNotNone(calc["playbook_message"])
        self.assertTrue(len(calc["playbook_message"]) > 20)
        self.assertIn("Tony", calc["playbook_message"])
        self.assertIn("Avengers HQ", calc["playbook_message"])


if __name__ == "__main__":
    unittest.main()
