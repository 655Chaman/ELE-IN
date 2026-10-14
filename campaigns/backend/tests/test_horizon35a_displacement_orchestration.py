from datetime import datetime
import os
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from campaigns.backend.routers.displacement_router import (
    LaunchDisplacementPayload,
    ResolveBattlecardExecutionPayload,
    launch_displacement_endpoint,
    resolve_battlecard_execution_endpoint,
)
from campaigns.backend.services.displacement_service import (
    _DISPLACEMENT_LOCKS,
    _IN_MEMORY_DISPLACEMENTS,
    _SEED_DISPLACEMENTS,
    create_competitor_displacement,
    launch_displacement_sequence,
    list_competitor_displacements,
    resolve_displacement_battlecard_for_execution,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


class TestHorizon35aDisplacementOrchestration(unittest.TestCase):
    """
    Horizon 35A: Competitive Displacement & Technographic Battlecard Injection.
    Verifies Layer 0 (Foundational), Layer 1 (Environmental Failure Analysis),
    and Layer 2 (Human Paranoia / Cross-Tenant IDOR & Formula Sanitization).
    """

    def setUp(self):
        _IN_MEMORY_DISPLACEMENTS.clear()
        _IN_MEMORY_DISPLACEMENTS.extend([dict(d) for d in _SEED_DISPLACEMENTS])
        _DISPLACEMENT_LOCKS.clear()
        os.environ["TEST_MODE"] = "true"

    # -------------------------------------------------------------------------
    # LAYER 0: FOUNDATIONAL LAYER
    # -------------------------------------------------------------------------
    def test_layer0_resolve_displacement_battlecard_normalizes_and_generates_wedge_and_buyout(self):
        """Layer 0: Resolves vendor slug, calculates opportunity score, generates copy wedge, and buyout offer."""
        res = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-default",
            target_company="Datadog",
            target_contact_name="Arthur Pendelton",
            target_contact_title="VP of Revenue Operations",
            incumbent_vendor="Apollo.io",
            seat_count=15,
            contract_renewal_days=60,
        )
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["vendor_slug"], "apollo")
        self.assertEqual(res["vendor_display_name"], "Apollo.io")
        self.assertEqual(res["competitor_name"], "Apollo.io")
        self.assertIn("Apollo.io", res["displacement_wedge"])
        self.assertIn("Arthur", res["displacement_wedge"])
        self.assertTrue(
            "waterfall" in res["displacement_hook"].lower() or "linkedin" in res["displacement_hook"].lower()
        )
        self.assertIn("credit", res["buyout_offer"].lower())
        self.assertIn("60 days", res["buyout_offer"])
        self.assertTrue(len(res["elein_killer_advantage"]) > 0)
        self.assertGreater(res["annual_savings"], 0)
        self.assertEqual(res["renewal_days"], 60)
        self.assertEqual(res["window_status"], "PEAK_EVALUATION")
        self.assertGreaterEqual(res["vulnerability_score"], 80)
        self.assertTrue(res["lock_acquired"])
        self.assertFalse(res["duplicate_prevented"])
        self.assertFalse(res["renewal_expired"])

    def test_layer0_executor_handle_displacement_populates_sequence_variables(self):
        """Layer 0: Verifies EleInNodeExecutor competitive displacement execution populates sequence variables."""
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-default")
        node_data = {
            "target_company": "NorthStar Logistics",
            "target_contact_name": "Arthur Pendelton",
            "target_contact_title": "VP of RevOps",
            "incumbent_vendor": "outreach",
            "seat_count": 18,
            "contract_renewal_days": 65,
        }
        res = executor.handle_competitive_displacement(node_data, "https://linkedin.com/in/arthur-pendelton")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "then")
        self.assertEqual(res["displacement"]["vendor_slug"], "outreach")

        vars_dict = res["variables"]
        self.assertEqual(vars_dict["competitor_name"], "Outreach")
        self.assertIn("Outreach", vars_dict["displacement_wedge"])
        self.assertIn("62%", vars_dict["displacement_hook"])
        self.assertTrue(vars_dict["annual_savings"].startswith("$"))
        self.assertFalse(vars_dict["duplicate_prevented"])

    def test_layer0_router_resolve_battlecard_endpoint_success(self):
        """Layer 0: Router resolve endpoint successfully executes and returns structured battlecard data."""
        payload = ResolveBattlecardExecutionPayload(
            target_company="CloudMetric Labs",
            target_contact_name="Samantha Wu",
            target_contact_title="Head of Global Outbound",
            incumbent_vendor="salesloft",
            seat_count=25,
            contract_renewal_days=45,
            domain="cloudmetriclabs.io",
        )
        resp = resolve_battlecard_execution_endpoint(payload, workspace_id="ws-test", supabase=None)
        self.assertTrue(resp["success"])
        data = resp["data"]
        self.assertEqual(data["vendor_slug"], "salesloft")
        self.assertEqual(data["vendor_display_name"], "Salesloft")
        self.assertTrue(data["lock_acquired"])
        self.assertFalse(data["duplicate_prevented"])
        self.assertFalse(data["renewal_expired"])
        self.assertGreater(data["annual_savings"], 0)

    # -------------------------------------------------------------------------
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # -------------------------------------------------------------------------
    def test_layer1_duplicate_concurrent_sequence_lock_prevents_duplicate_campaign(self):
        """Layer 1: Prevents duplicate concurrent displacement sequences against the same company."""
        first = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-env-lock",
            target_company="Ramp Financial",
            target_contact_name="Samantha",
            target_contact_title="Head of SDRs",
            incumbent_vendor="apollo",
            domain="ramp.com",
        )
        self.assertTrue(first["lock_acquired"])
        self.assertFalse(first["duplicate_prevented"])
        self.assertIn("ws-env-lock:ramp.com", _DISPLACEMENT_LOCKS)

        # Immediate concurrent call against same company in same workspace
        second = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-env-lock",
            target_company="Ramp Financial",
            target_contact_name="Samantha",
            target_contact_title="Head of SDRs",
            incumbent_vendor="apollo",
            domain="ramp.com",
        )
        self.assertFalse(second["lock_acquired"])
        self.assertTrue(second["duplicate_prevented"])

        # Executor reflects duplicate_prevented flag
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-env-lock")
        exec_res = executor.handle_competitive_displacement(
            {"target_company": "Ramp Financial", "domain": "ramp.com", "incumbent_vendor": "apollo"},
            "https://linkedin.com/in/samantha-ramp",
        )
        self.assertTrue(exec_res["variables"]["duplicate_prevented"])

    def test_layer1_domain_fallback_and_multi_tenant_lock_isolation(self):
        """Layer 1: Locks are isolated per tenant workspace and domain normalization prevents collisions."""
        # Tenant Alpha locks stripe.com
        alpha_res = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-tenant-alpha",
            target_company="Stripe, Inc.",
            target_contact_name="Marcus",
            target_contact_title="CFO",
            domain="https://Stripe.com/",
        )
        self.assertTrue(alpha_res["lock_acquired"])
        self.assertIn("ws-tenant-alpha:stripe.com", _DISPLACEMENT_LOCKS)

        # Tenant Beta targeting the same company/domain acquires their own isolated lock
        beta_res = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-tenant-beta",
            target_company="Stripe",
            target_contact_name="Elena",
            target_contact_title="CRO",
            domain="stripe.com",
        )
        self.assertTrue(beta_res["lock_acquired"])
        self.assertIn("ws-tenant-beta:stripe.com", _DISPLACEMENT_LOCKS)

        # Subsequent call by Tenant Beta on same domain detects duplicate
        beta_second = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-tenant-beta",
            target_company="Stripe",
            target_contact_name="Elena",
            target_contact_title="CRO",
            domain="stripe.com",
        )
        self.assertTrue(beta_second["duplicate_prevented"])
        self.assertFalse(beta_second["lock_acquired"])

    def test_layer1_expired_contract_renewal_flags_renewal_passed_and_routes_failed_branch(self):
        """Layer 1: Flags renewal_expired=True and branches to FAILED when contract renewal days <= 0."""
        res_zero = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-expired-test",
            target_company="LegacyCorp",
            target_contact_name="David",
            target_contact_title="Director",
            incumbent_vendor="outreach",
            contract_renewal_days=0,
        )
        self.assertTrue(res_zero["renewal_expired"])
        self.assertEqual(res_zero["status"], "renewal_passed")
        self.assertEqual(res_zero["renewal_days"], 0)
        self.assertEqual(res_zero["window_status"], "EXPIRED")

        # Executor routes expired contract to FAILED branch
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-expired-test")
        exec_res = executor.handle_competitive_displacement(
            {
                "target_company": "LegacyCorp",
                "target_contact_name": "David",
                "incumbent_vendor": "outreach",
                "contract_renewal_days": -15,
            },
            "https://linkedin.com/in/david-legacy",
        )
        self.assertEqual(exec_res["branch"], Branch.FAILED.value)
        self.assertTrue(exec_res["displacement"]["renewal_expired"])

    # -------------------------------------------------------------------------
    # LAYER 2: HUMAN PARANOIA (CROSS-TENANT IDOR, FORMULA SANITIZATION, BOUNDS)
    # -------------------------------------------------------------------------
    def test_layer2_formula_injection_sanitized_across_text_inputs(self):
        """Layer 2: Neutralizes spreadsheet formula injection (=, +, -, @, \\t, \\r) across all fields."""
        res = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-formula-test",
            target_company="=cmd|' /C calc'!A0 EvilCorp",
            target_contact_name="+@SUM(1+1) Eve",
            target_contact_title="-VP of Sales",
            domain="\t\r=evilcorp.io",
            incumbent_vendor="apollo",
        )
        self.assertFalse(res["displacement_wedge"].startswith(("=", "+", "-", "@", "\t", "\r")))
        self.assertFalse(res["competitor_name"].startswith(("=", "+", "-", "@", "\t", "\r")))
        self.assertFalse(res["displacement_hook"].startswith(("=", "+", "-", "@", "\t", "\r")))

        # Concurrency lock key does not retain formula characters
        self.assertIn("ws-formula-test:evilcorp.io", _DISPLACEMENT_LOCKS)
        self.assertNotIn("ws-formula-test:=evilcorp.io", _DISPLACEMENT_LOCKS)

    def test_layer2_input_bounds_clamping_seats_and_renewal_days(self):
        """Layer 2: Clamps extreme/erroneous seat counts (1-5000) and renewal days (0-365)."""
        # Upper bound test
        res_upper = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-bounds-test",
            target_company="MegaCorp",
            target_contact_name="CEO",
            target_contact_title="Chief Executive",
            seat_count=999999,
            contract_renewal_days=9999,
        )
        self.assertEqual(res_upper["renewal_days"], 365)
        # Savings calculation does not overflow
        self.assertLessEqual(res_upper["annual_savings"], 5000 * 140 * 12)

        # Lower bound test
        res_lower = resolve_displacement_battlecard_for_execution(
            workspace_id="ws-bounds-test",
            target_company="TinyCorp",
            target_contact_name="Solo",
            target_contact_title="Founder",
            seat_count=-100,
            contract_renewal_days=-50,
        )
        self.assertEqual(res_lower["renewal_days"], 0)
        self.assertTrue(res_lower["renewal_expired"])
        self.assertGreaterEqual(res_lower["annual_savings"], 0)

    def test_layer2_cross_tenant_idor_isolation_in_list_and_launch(self):
        """Layer 2: Enforces cross-workspace IDOR isolation across listing, launching, and resolving."""
        # Create private displacement record for Tenant Alpha
        private_record = create_competitor_displacement(
            workspace_id="ws-tenant-alpha",
            target_company="AlphaShield Global",
            target_contact_name="Victoria Sterling",
            target_contact_title="Chief Revenue Officer",
            incumbent_vendor="outreach",
            domain="alphashieldglobal.com",
        )
        disp_id = private_record["id"]

        # Attacker workspace listing opportunities cannot see Tenant Alpha's record
        attacker_disps = list_competitor_displacements(workspace_id="ws-tenant-attacker")
        attacker_ids = [d["id"] for d in attacker_disps]
        self.assertNotIn(disp_id, attacker_ids)

        # Attacker workspace attempting to launch Tenant Alpha's sequence is blocked
        with self.assertRaises(PermissionError):
            launch_displacement_sequence(
                workspace_id="ws-tenant-attacker",
                displacement_id=disp_id,
            )

        # Attacker workspace attempting to resolve battlecard targeting Tenant Alpha's record is blocked
        with self.assertRaises(PermissionError):
            resolve_displacement_battlecard_for_execution(
                workspace_id="ws-tenant-attacker",
                target_company="AlphaShield Global",
                target_contact_name="Victoria",
                target_contact_title="CRO",
                domain="alphashieldglobal.com",
            )

    def test_layer2_router_maps_permission_error_to_403_and_value_error_to_400(self):
        """Layer 2: Router endpoints translate PermissionError to HTTP 403 and ValueError to HTTP 400."""
        # Create private record for Tenant Alpha
        private_record = create_competitor_displacement(
            workspace_id="ws-tenant-alpha",
            target_company="VaultSecure Systems",
            target_contact_name="Devon",
            target_contact_title="VP Sales",
            domain="vaultsecure.io",
        )
        disp_id = private_record["id"]

        # Launching with cross-workspace displacement_id raises HTTP 403
        with self.assertRaises(HTTPException) as ctx_launch:
            launch_displacement_endpoint(
                LaunchDisplacementPayload(displacement_id=disp_id),
                workspace_id="ws-tenant-attacker",
                supabase=None,
            )
        self.assertEqual(ctx_launch.exception.status_code, 403)

        # Resolving cross-workspace company in resolve endpoint raises HTTP 403
        with self.assertRaises(HTTPException) as ctx_resolve_perm:
            resolve_battlecard_execution_endpoint(
                ResolveBattlecardExecutionPayload(
                    target_company="VaultSecure Systems",
                    target_contact_name="Devon",
                    target_contact_title="VP Sales",
                    domain="vaultsecure.io",
                ),
                workspace_id="ws-tenant-attacker",
                supabase=None,
            )
        self.assertEqual(ctx_resolve_perm.exception.status_code, 403)

        # Resolving with invalid/empty company raises HTTP 400
        with self.assertRaises(HTTPException) as ctx_resolve_val:
            resolve_battlecard_execution_endpoint(
                ResolveBattlecardExecutionPayload(
                    target_company="",
                    target_contact_name="Test",
                    target_contact_title="VP",
                ),
                workspace_id="ws-test",
                supabase=None,
            )
        self.assertEqual(ctx_resolve_val.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
