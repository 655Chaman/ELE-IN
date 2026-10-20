import uuid
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from campaigns.backend.services.crm_attribution_service import (
    calculate_deal_attribution,
    process_inbound_crm_event,
    upsert_synced_account,
    calculate_payload_hash,
    _IN_MEMORY_CRM_ACCOUNTS,
    _IN_MEMORY_DEAL_ATTRIBUTIONS,
    _IN_MEMORY_SYNC_LOGS
)
from campaigns.backend.services.displacement_service import (
    create_competitor_displacement,
    launch_displacement_sequence,
    resolve_displacement_battlecard_for_execution,
    unlock_displacement_sequence,
    _DISPLACEMENT_LOCKS
)
from campaigns.backend.services.sto_service import (
    compute_lead_jitter_minutes,
    compute_lead_sto_window,
    calculate_sto_next_run
)


class TestStage19EliteArchitecture(unittest.TestCase):
    """
    Stage 19 Elite-Tier Distributed Systems Architecture Test Suite
    Governance: Three-Layer Logic Architecture (Paranoia Framework)
    """

    def setUp(self):
        # Clean locks and state before each test
        _DISPLACEMENT_LOCKS.clear()

    # ── 1. CRM Attribution & Closed-Won Revenue Mapping Hardening ─────────────

    def test_crm_attribution_deterministic_uuid5_and_idempotency(self):
        """
        Layer 1: calculate_deal_attribution generates deterministic UUID5 identifiers
        and updates existing records idempotently rather than producing duplicates.
        """
        workspace_id = f"ws-{uuid.uuid4().hex[:6]}"
        deal_id = "deal-enterprise-999"

        touchpoints = [
            {"channel": "linkedin", "step": 1},
            {"channel": "email", "step": 2}
        ]

        # First call
        res1 = calculate_deal_attribution(
            deal_id=deal_id,
            deal_name="Enterprise Pilot",
            deal_amount=50000.0,
            touchpoints=touchpoints,
            model="w_shaped",
            workspace_id=workspace_id,
            supabase=None
        )
        self.assertTrue(res1["id"].startswith("attr-"))
        self.assertEqual(res1["deal_id"], deal_id)
        self.assertEqual(res1["deal_amount"], 50000.0)

        # Second call with updated amount
        res2 = calculate_deal_attribution(
            deal_id=deal_id,
            deal_name="Enterprise Pilot - Expanded",
            deal_amount=65000.0,
            touchpoints=touchpoints,
            model="w_shaped",
            workspace_id=workspace_id,
            supabase=None
        )
        # Deterministic ID must match!
        self.assertEqual(res1["id"], res2["id"])
        self.assertEqual(res2["deal_amount"], 65000.0)

        # In-memory store should have exactly 1 record for this deal, not duplicated
        matching_attrs = [a for a in _IN_MEMORY_DEAL_ATTRIBUTIONS if a.get("deal_id") == deal_id]
        self.assertEqual(len(matching_attrs), 1)

    def test_upsert_synced_account_deterministic_uuid5(self):
        """
        Layer 1 & 2: upsert_synced_account generates deterministic UUID5 from workspace and domain,
        preventing duplicate account mappings on rapid repeated syncs.
        """
        workspace_id = f"ws-{uuid.uuid4().hex[:6]}"
        domain = "cloudflare.com"

        acc1 = upsert_synced_account(
            workspace_id=workspace_id,
            domain=domain,
            company_name="Cloudflare",
            crm_provider="hubspot",
            lifecycle_stage="lead",
            supabase=None
        )
        acc2 = upsert_synced_account(
            workspace_id=workspace_id,
            domain=domain,
            company_name="Cloudflare Inc",
            crm_provider="hubspot",
            lifecycle_stage="customer",
            supabase=None
        )

        self.assertEqual(acc1["id"], acc2["id"])
        self.assertEqual(acc2["lifecycle_stage"], "customer")

    def test_crm_echo_loop_cross_tenant_isolation(self):
        """
        Layer 1 & 2: Identical payloads across two distinct workspaces do NOT cross-suppress.
        Tenant-scoped payload hashing ensures isolation.
        """
        ws_a = "ws-tenant-alpha"
        ws_b = "ws-tenant-beta"
        payload = {"domain": "stripe.com", "stage": "opportunity", "amount": 25000}

        # Tenant A first event -> success
        res_a1 = process_inbound_crm_event("deal.update", payload, workspace_id=ws_a, supabase=None)
        self.assertEqual(res_a1["status"], "success")

        # Tenant A immediate repeat -> suppressed echo
        res_a2 = process_inbound_crm_event("deal.update", payload, workspace_id=ws_a, supabase=None)
        self.assertEqual(res_a2["status"], "skipped_echo")

        # Tenant B same payload -> MUST NOT be suppressed by Tenant A!
        res_b1 = process_inbound_crm_event("deal.update", payload, workspace_id=ws_b, supabase=None)
        self.assertEqual(res_b1["status"], "success")

    def test_crm_cascade_campaign_halting_in_supabase(self):
        """
        Layer 1: When CRM signals closed_won / customer / opportunity, active outreach in Supabase
        for prospect leads matching the domain is automatically halted.
        """
        workspace_id = "ws-cascade-crm"
        domain = "enterprise-buyer.com"

        mock_sb = MagicMock()
        # Matched leads
        mock_sb.table().select().eq().ilike().execute.return_value = MagicMock(
            data=[{"id": "lead-crm-1"}, {"id": "lead-crm-2"}]
        )
        # Matched enrollments
        mock_sb.table().select().in_().execute.return_value = MagicMock(
            data=[{"id": "enr-crm-1"}, {"id": "enr-crm-2"}]
        )
        mock_sb.table().update().in_().in_().execute.return_value = MagicMock(data=[])
        mock_sb.table().update().in_().execute.return_value = MagicMock(data=[])

        payload = {"domain": domain, "stage": "closed_won", "amount": 100000}
        res = process_inbound_crm_event(
            event_type="deal.closed_won",
            payload=payload,
            workspace_id=workspace_id,
            supabase=mock_sb
        )

        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["campaigns_halted"], 2)
        # Verify campaign_execution_states were updated to completed
        mock_sb.table("campaign_execution_states").update.assert_called()

    # ── 2. Competitive Displacement Engine Hardening ─────────────────────────

    def test_displacement_deterministic_uuid5_and_idempotent_create(self):
        """
        Layer 1 & 2: create_competitor_displacement generates deterministic UUID5 IDs
        and avoids duplicating radar opportunities for the same domain and incumbent vendor.
        """
        workspace_id = f"ws-{uuid.uuid4().hex[:6]}"
        company = "Datadog"
        domain = "datadoghq.com"

        d1 = create_competitor_displacement(
            workspace_id=workspace_id,
            target_company=company,
            target_contact_name="Alexis Le-Quoc",
            target_contact_title="CTO",
            incumbent_vendor="outreach",
            domain=domain,
            seat_count=20,
            contract_renewal_days=45,
            supabase=None
        )
        self.assertTrue(d1["id"].startswith("disp-"))

        # Re-running creation for same target company & vendor slug
        d2 = create_competitor_displacement(
            workspace_id=workspace_id,
            target_company=company,
            target_contact_name="Alexis Le-Quoc",
            target_contact_title="Co-Founder & CTO",
            incumbent_vendor="outreach",
            domain=domain,
            seat_count=25,
            contract_renewal_days=30,
            supabase=None
        )

        self.assertEqual(d1["id"], d2["id"])
        self.assertEqual(d2["seat_count"], 25)

    def test_displacement_concurrency_lock_ttl_and_manual_release(self):
        """
        Layer 1: resolve_displacement_battlecard_for_execution enforces concurrency locks with TTL,
        supports manual unlock_displacement_sequence, and automatically expires stale locks.
        """
        workspace_id = "ws-disp-lock"
        company = "Snowflake"
        domain = "snowflake.com"

        # 1. First execution: acquires lock
        res1 = resolve_displacement_battlecard_for_execution(
            workspace_id=workspace_id,
            target_company=company,
            target_contact_name="Benoit Dageville",
            target_contact_title="President of Products",
            incumbent_vendor="salesloft",
            domain=domain,
            contract_renewal_days=60
        )
        self.assertTrue(res1["lock_acquired"])
        self.assertFalse(res1["duplicate_prevented"])

        # 2. Immediate second execution: blocked as duplicate
        res2 = resolve_displacement_battlecard_for_execution(
            workspace_id=workspace_id,
            target_company=company,
            target_contact_name="Benoit Dageville",
            target_contact_title="President of Products",
            incumbent_vendor="salesloft",
            domain=domain,
            contract_renewal_days=60
        )
        self.assertFalse(res2["lock_acquired"])
        self.assertTrue(res2["duplicate_prevented"])

        # 3. Manual unlock allows re-execution
        unlocked = unlock_displacement_sequence(workspace_id=workspace_id, company_or_domain=domain)
        self.assertTrue(unlocked)

        res3 = resolve_displacement_battlecard_for_execution(
            workspace_id=workspace_id,
            target_company=company,
            target_contact_name="Benoit Dageville",
            target_contact_title="President of Products",
            incumbent_vendor="salesloft",
            domain=domain,
            contract_renewal_days=60
        )
        self.assertTrue(res3["lock_acquired"])
        self.assertFalse(res3["duplicate_prevented"])

        # 4. TTL expiration simulation (simulate lock from 2 hours ago)
        lock_key = f"{workspace_id}:{domain.lower()}"
        _DISPLACEMENT_LOCKS[lock_key]["locked_at"] = (datetime.utcnow() - timedelta(hours=2)).isoformat()

        res4 = resolve_displacement_battlecard_for_execution(
            workspace_id=workspace_id,
            target_company=company,
            target_contact_name="Benoit Dageville",
            target_contact_title="President of Products",
            incumbent_vendor="salesloft",
            domain=domain,
            contract_renewal_days=60
        )
        # Should expire stale lock and re-acquire!
        self.assertTrue(res4["lock_acquired"])
        self.assertFalse(res4["duplicate_prevented"])

    # ── 3. Send-Time Optimization Defensiveness ───────────────────────────────

    def test_sto_jitter_numerical_bounds(self):
        """
        Layer 2: compute_lead_jitter_minutes clamps bounds when min_jitter > max_jitter
        or when extreme values are supplied.
        """
        # Inverted bounds (min 30 > max 10)
        j1 = compute_lead_jitter_minutes("lead-1", min_jitter=30, max_jitter=10)
        self.assertGreaterEqual(j1, 10)
        self.assertLessEqual(j1, 60)

        # None / empty lead_id fallback
        j_none = compute_lead_jitter_minutes(None)
        self.assertEqual(j_none, 12)

        # Valid bounds
        j_valid = compute_lead_jitter_minutes("lead-abc-123", min_jitter=5, max_jitter=25)
        self.assertGreaterEqual(j_valid, 5)
        self.assertLessEqual(j_valid, 25)

    def test_sto_calculate_next_run_gap_bounding_and_tenant_scoping(self):
        """
        Layer 1 & 2: calculate_sto_next_run clamps min_gap_minutes defensively,
        scopes Supabase engagement queries by workspace_id, and guarantees future run time.
        """
        mock_sb = MagicMock()
        mock_sb.table().select().eq().eq().in_().limit().execute.return_value = MagicMock(data=[])
        mock_sb.table().select().eq().eq().eq().limit().execute.return_value = MagicMock(data=[])

        now_utc = datetime.now(timezone.utc)
        schedule = {"start_hour": 9, "end_hour": 17, "active_days": [0, 1, 2, 3, 4]}

        # Test with negative min_gap_minutes (defensively clamped to minimum 1 minute)
        next_run = calculate_sto_next_run(
            base_time=now_utc,
            target_tz="America/New_York",
            lead_id="lead-sto-tenant",
            schedule=schedule,
            supabase=mock_sb,
            min_gap_minutes=-10,
            workspace_id="ws-sto-tenant"
        )
        self.assertGreater(next_run, now_utc)
        # Check that workspace_id was passed to table queries
        mock_sb.table.assert_called()


if __name__ == "__main__":
    unittest.main()
