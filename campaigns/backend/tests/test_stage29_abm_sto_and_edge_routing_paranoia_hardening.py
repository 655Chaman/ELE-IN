"""
test_stage29_abm_sto_and_edge_routing_paranoia_hardening.py — Paranoia Test Suite for Stage 29
Advanced Decision Logic, ABM Multi-Threading, Send Time Optimization (STO) & Edge Routing Hardening

Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (STO jitter spread, peak hours window clamping, ABM committee role taxonomy, condition node matching, DAG edge resolution)
- Layer 1: Environmental Failure Analysis (Multi-tenant workspace isolation in STO, timezone-aware datetime arithmetic, safe custom fields extraction without SQL column errors, same-account collision cooldown, worker failure fallbacks)
- Layer 2: Human Paranoia (Auto-correcting inverted headcount bounds, dirty keyword formats, boolean branch coercion, ABM self-reference peer exclusion, non-numeric A/B ratio clamping)
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import pytz

from campaigns.backend.services.sto_service import (
    compute_lead_jitter_minutes,
    compute_lead_sto_window,
    calculate_sto_next_run,
    should_use_sto,
)
from campaigns.backend.services.abm_multithreading_service import (
    classify_committee_role,
    calculate_committee_penetration,
    resolve_abm_context_for_execution,
    _ACCOUNT_TOUCH_LEDGER,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestStage29AbmStoAndEdgeRoutingParanoiaHardening(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws_stage29_enterprise"
        self.campaign_id = "camp_stage29_abm"
        self.mock_supabase = MagicMock()
        _ACCOUNT_TOUCH_LEDGER.clear()

        # Mock orchestrator and executor
        self.orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        self.executor = EleInNodeExecutor(
            worker=None,
            account_id="acc_stage29_sender",
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            supabase=self.mock_supabase
        )

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER
    # =========================================================================

    def test_sto_jitter_deterministic_and_bounded(self):
        """Layer 0: Verifies STO jitter is deterministic for a lead and strictly bounded."""
        lead_id = "lead_stage29_alpha"
        jitter_1 = compute_lead_jitter_minutes(lead_id, min_jitter=5, max_jitter=25)
        jitter_2 = compute_lead_jitter_minutes(lead_id, min_jitter=5, max_jitter=25)
        
        self.assertEqual(jitter_1, jitter_2, "STO jitter must be 100% deterministic for identical lead IDs")
        self.assertTrue(5 <= jitter_1 <= 25, f"Jitter {jitter_1} must be bounded within [5, 25]")

    def test_sto_working_hours_and_weekend_clamping(self):
        """Layer 0: STO next run must land strictly within working hours and skip weekends."""
        # Force baseline to Saturday 2026-10-24 14:00:00 UTC
        saturday_utc = datetime(2026, 10, 24, 14, 0, 0, tzinfo=timezone.utc)
        
        # Mock empty DB data so STO uses working_hours
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        next_run = calculate_sto_next_run(
            base_time=saturday_utc,
            target_tz="America/New_York",
            lead_id="lead_sat_test",
            schedule={"working_hours": (9, 17), "working_days": [0, 1, 2, 3, 4]},
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

        # In America/New_York, next run must land on Monday (weekday 0) between 9:00 and 17:00
        ny_tz = pytz.timezone("America/New_York")
        local_run = next_run.astimezone(ny_tz)
        self.assertEqual(local_run.weekday(), 0, "Weekend run must be deferred to Monday")
        self.assertTrue(9 <= local_run.hour <= 17, f"Run time {local_run.hour} must be within working hours (9-17)")

    def test_abm_committee_role_classification_archetypes(self):
        """Layer 0: Verifies accurate categorization of buying committee personas."""
        test_cases = [
            ("Chief Executive Officer", "economic_buyer"),
            ("Founder & CEO", "economic_buyer"),
            ("VP, Global Sales / BizDev", "champion"),
            ("Head of Outbound", "champion"),
            ("Senior Director of Sales", "champion"),
            ("CTO & VP Engineering", "technical_evaluator"),
            ("Head of IT & Security", "technical_evaluator"),
            ("Lead Sales Development Representative", "end_user"),
            ("Account Executive", "end_user"),
        ]
        for title, expected_role in test_cases:
            role = classify_committee_role(title)
            self.assertEqual(role, expected_role, f"Title '{title}' expected '{expected_role}', got '{role}'")

    def test_decision_node_title_and_location_matching(self):
        """Layer 0: Decision nodes match on word boundaries and return standard Match / Does not match."""
        # Match case
        data_match = {
            "title_keyword": "VP Sales",
            "lead": {"title": "VP Sales & Partnerships"}
        }
        res_m = self.executor.handle_if_title_matches(data_match, None)
        self.assertEqual(res_m["status"], "success")
        self.assertEqual(res_m["branch"], Branch.MATCHES.value)
        self.assertTrue(res_m["matched"])

        # Non-match case
        data_no_match = {
            "title_keyword": "CTO",
            "lead": {"title": "Director of Medical Oncology"}  # "cto" in "doctor", must not match
        }
        res_nm = self.executor.handle_if_title_matches(data_no_match, None)
        self.assertEqual(res_nm["status"], "success")
        self.assertEqual(res_nm["branch"], Branch.DOES_NOT_MATCH.value)
        self.assertFalse(res_nm["matched"])

    def test_decision_node_headcount_ranges(self):
        """Layer 0: Company size condition node correctly checks overlap for formatted headcount strings."""
        test_cases = [
            ("51-200", 50, 100, Branch.IN_RANGE.value),
            ("10,001+ employees", 1000, 50000, Branch.IN_RANGE.value),
            ("10k", 500, 2000, Branch.OUT_OF_RANGE.value),
            ("25", 50, 200, Branch.OUT_OF_RANGE.value),
        ]
        for raw_hc, min_s, max_s, expected_branch in test_cases:
            data = {"lead": {"headcount": raw_hc}, "min_size": min_s, "max_size": max_s}
            res = self.executor.handle_if_company_size(data, None)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["branch"], expected_branch, f"Headcount '{raw_hc}' with ({min_s}, {max_s}) failed")

    def test_edge_routing_exact_and_synonym_resolution(self):
        """Layer 0: resolve_branch_edge correctly resolves exact, case-insensitive, and synonym handles."""
        edges = [
            {"source": "n1", "target": "n_yes", "source_handle": "yes"},
            {"source": "n1", "target": "n_no", "source_handle": "no"}
        ]
        # Exact synonym mapping: "Matches" should route to "yes"
        matched_edge, is_term = self.orchestrator.resolve_branch_edge(edges, "Matches")
        self.assertIsNotNone(matched_edge)
        self.assertEqual(matched_edge["target"], "n_yes")
        self.assertFalse(is_term)

        # "Does not match" should route to "no"
        matched_edge_no, is_term_no = self.orchestrator.resolve_branch_edge(edges, "Does not match")
        self.assertIsNotNone(matched_edge_no)
        self.assertEqual(matched_edge_no["target"], "n_no")
        self.assertTrue(is_term_no)

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # =========================================================================

    def test_sto_multi_tenant_workspace_isolation(self):
        """Layer 1: STO must scope queries by workspace_id, preventing cross-tenant leakage."""
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.in_.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        self.mock_supabase.table.return_value = mock_table

        calculate_sto_next_run(
            base_time=datetime.now(timezone.utc),
            target_tz="UTC",
            lead_id="lead_tenant_iso",
            supabase=self.mock_supabase,
            workspace_id="ws_strict_isolation_99"
        )

        # Check that eq was called with workspace_id
        eq_calls = mock_table.eq.call_args_list
        found_ws_scoping = any(
            call[0] == ("workspace_id", "ws_strict_isolation_99") for call in eq_calls
        )
        self.assertTrue(found_ws_scoping, "STO query must filter on workspace_id for tenant safety")

    def test_timezone_aware_datetime_sto_and_event_harvester(self):
        """Layer 1: Operations must use timezone-aware datetimes without naive subtraction TypeError."""
        from campaigns.backend.services.event_harvester_service import (
            harvest_event_attendees,
            _HARVESTED_EVENT_LOCKS
        )
        _HARVESTED_EVENT_LOCKS.clear()

        # First harvest
        res1 = harvest_event_attendees(
            workspace_id="ws_tz_test",
            event_url="https://www.linkedin.com/events/ai-summit-2026-101/",
            event_name="AI Summit 2026"
        )
        self.assertEqual(res1["status"], "success")

        # Second harvest within 2-hour deduplication window (exercises datetime subtraction)
        res2 = harvest_event_attendees(
            workspace_id="ws_tz_test",
            event_url="https://www.linkedin.com/events/ai-summit-2026-101/",
            event_name="AI Summit 2026"
        )
        self.assertEqual(res2["status"], "success")
        self.assertTrue(res2["duplicate_harvest_prevented"])

    def test_custom_fields_retrieval_without_missing_column_error(self):
        """Layer 1: _get_lead_field safely inspects custom_fields without breaking on missing SQL columns."""
        lead_data = {
            "lead": {
                "first_name": "Jane",
                "custom_fields": {
                    "department": "Infrastructure Engineering",
                    "Tier": "Strategic Enterprise"
                }
            }
        }
        # Retrieve direct custom field
        val1 = self.executor._get_lead_field(lead_data, None, "department")
        self.assertEqual(val1, "Infrastructure Engineering")

        # Retrieve case-insensitive custom field
        val2 = self.executor._get_lead_field(lead_data, None, "tier")
        self.assertEqual(val2, "Strategic Enterprise")

    def test_abm_same_account_collision_ledger(self):
        """Layer 1: Same-account touch collision ledger prevents concurrent SDR touchpoint collisions."""
        _ACCOUNT_TOUCH_LEDGER.clear()

        # First lead on megacorp.com
        res1 = resolve_abm_context_for_execution(
            workspace_id=self.workspace_id,
            domain="megacorp.com",
            company_name="MegaCorp",
            lead_id="lead_alice",
            prospect_name="Alice Smith",
            title="VP Marketing",
            staggered_interval_hours=24
        )
        self.assertFalse(res1.get("collision_deferred", False))

        # Second lead on megacorp.com within 24 hours -> collision deferred!
        res2 = resolve_abm_context_for_execution(
            workspace_id=self.workspace_id,
            domain="megacorp.com",
            company_name="MegaCorp",
            lead_id="lead_bob",
            prospect_name="Bob Jones",
            title="Director of Sales",
            staggered_interval_hours=24
        )
        self.assertTrue(res2.get("collision_deferred", False))
        self.assertIsNotNone(res2.get("next_available_slot_iso"))

        # Re-executing first lead (idempotent retry) -> not deferred!
        res1_retry = resolve_abm_context_for_execution(
            workspace_id=self.workspace_id,
            domain="megacorp.com",
            company_name="MegaCorp",
            lead_id="lead_alice",
            prospect_name="Alice Smith",
            title="VP Marketing",
            staggered_interval_hours=24
        )
        self.assertFalse(res1_retry.get("collision_deferred", False))
        self.assertTrue(res1_retry.get("idempotent_retry", False))

    def test_worker_unavailable_graceful_branch_fallback(self):
        """Layer 1: Missing Playwright worker returns clean non-crashing branch."""
        # if_connected without worker
        res_conn = self.executor.handle_if_connected({"lead": {"is_connected": False}}, "https://linkedin.com/in/test-unavail")
        self.assertEqual(res_conn["status"], "success")
        self.assertEqual(res_conn["branch"], Branch.NOT_CONNECTED.value)
        self.assertFalse(res_conn["connected"])

        # open_profile_check without worker
        res_open = self.executor.handle_open_profile_check({}, "https://linkedin.com/in/test-open-unavail")
        self.assertEqual(res_open["status"], "success")
        self.assertEqual(res_open["branch"], "Not open")
        self.assertFalse(res_open["open"])

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA
    # =========================================================================

    def test_human_headcount_inversion_auto_correction(self):
        """Layer 2: When human inputs min_size > max_size, system auto-inverts and evaluates correctly."""
        # User entered min=500, max=50
        data = {
            "lead": {"headcount": "150"},
            "min_size": 500,
            "max_size": 50
        }
        res = self.executor.handle_if_company_size(data, None)
        self.assertEqual(res["status"], "success")
        # 150 is between 50 and 500, so after auto-correct it must be In range!
        self.assertEqual(res["branch"], Branch.IN_RANGE.value)
        self.assertTrue(res["in_range"])

    def test_dirty_keyword_formats_list_and_pipes(self):
        """Layer 2: Handles array of keywords and pipe-delimited strings without crashing."""
        # Passing list directly: ["VP", "Director"]
        matched_list = self.executor._match_keywords("VP of Strategic Operations", ["VP", "Director"])
        self.assertTrue(matched_list)

        # Passing pipe-delimited string: "Founder|CEO|Managing Director"
        matched_pipe = self.executor._match_keywords("Founder and Chief Strategist", "Founder|CEO|Managing Director")
        self.assertTrue(matched_pipe)

        # Trailing commas and messy whitespace
        matched_messy = self.executor._match_keywords("Enterprise Account Executive", " , AE , Account Executive ,, ")
        self.assertTrue(matched_messy)

    def test_boolean_branch_coercion_in_orchestrator(self):
        """Layer 2: Boolean True/False or string booleans coerce to standard edge branches."""
        edges = [
            {"source": "n_dec", "target": "n_pass", "source_handle": "Matches"},
            {"source": "n_dec", "target": "n_fail", "source_handle": "Does not match"}
        ]

        # Raw boolean True
        edge_true, _ = self.orchestrator.resolve_branch_edge(edges, True)
        self.assertIsNotNone(edge_true)
        self.assertEqual(edge_true["target"], "n_pass")

        # Raw boolean False
        edge_false, is_term = self.orchestrator.resolve_branch_edge(edges, False)
        self.assertIsNotNone(edge_false)
        self.assertEqual(edge_false["target"], "n_fail")
        self.assertTrue(is_term)

    def test_abm_self_reference_peer_exclusion(self):
        """Layer 2: A prospect is never cited as their own cross-thread peer."""
        with patch("campaigns.backend.services.abm_multithreading_service.get_account_committee_members") as mock_cm:
            mock_cm.return_value = [
                {
                    "lead_id": "lead_john_doe",
                    "prospect_name": "John Doe",
                    "title": "VP of Revenue",
                    "status": "meeting_booked"
                }
            ]
            context = resolve_abm_context_for_execution(
                workspace_id=self.workspace_id,
                domain="acmecorp.com",
                company_name="Acme Corp",
                lead_id="lead_john_doe",
                prospect_name="John Doe",
                title="VP of Revenue"
            )
            # Because John Doe is the only member, peer reference must be empty string / None!
            self.assertFalse(bool(context.get("abm_peer_reference")))

    def test_a_b_split_non_numeric_and_out_of_bounds_ratio(self):
        """Layer 2: Extreme or non-numeric split inputs clamp cleanly between 0% and 100%."""
        # Non-numeric string input -> defaults to 50%
        res_nan = self.executor.handle_ab_split({"split_ratio": "fifty_percent", "_lead_id": "lead_123"}, None)
        self.assertEqual(res_nan["status"], "success")
        self.assertEqual(res_nan["path_a_pct"], 50.0)

        # Negative ratio -> clamps to 0%
        res_neg = self.executor.handle_ab_split({"split_ratio": -25, "_lead_id": "lead_123"}, None)
        self.assertEqual(res_neg["status"], "success")
        self.assertEqual(res_neg["path_a_pct"], 0.0)

        # >100% ratio -> clamps to 100%
        res_over = self.executor.handle_ab_split({"split_ratio": 150, "_lead_id": "lead_123"}, None)
        self.assertEqual(res_over["status"], "success")
        self.assertEqual(res_over["path_a_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
