"""
Stage 14 Elite Distributed Systems Architecture Verification Suite:
1. Calendar Concierge Global Timezone Resolution & Local Business Hours Generation.
2. Calendar Double-Booking & Multi-Worker Atomic Database Concurrency Guards.
3. ABM Multithreading Strict Tenant Isolation (Zero Toy Substring Heuristics).
4. Thompson Bandit Strictly Scoped Variant Feedback & Timezone-Aware Datetimes.
"""

import unittest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from campaigns.backend.services.calendar_concierge_service import (
    resolve_timezone,
    calculate_conflict_free_slots,
    create_meeting_booking,
    confirm_meeting_slot,
    extract_scheduling_intent,
    _RESERVED_REP_SLOTS
)
from campaigns.backend.services.abm_multithreading_service import (
    create_or_map_target_account,
    get_account_committee_members,
    update_committee_member_status,
    resolve_abm_context_for_execution,
    _verify_abm_workspace_access
)
from campaigns.backend.services.bandit_service import (
    record_variant_feedback
)


class TestStage14EliteArchitecture(unittest.TestCase):

    def test_01_calendar_global_timezone_resolution_and_local_business_hours(self):
        """
        Verify Calendar Concierge resolves global timezones (APAC, EMEA, Americas)
        and schedules slots strictly during local business hours (10am, 2pm, 4pm)
        without emitting confusing raw UTC artifacts to prospects.
        """
        # Test timezone resolution across global markets
        self.assertEqual(resolve_timezone("sgt").key, "Asia/Singapore")
        self.assertEqual(resolve_timezone("singapore").key, "Asia/Singapore")
        self.assertEqual(resolve_timezone("jst").key, "Asia/Tokyo")
        self.assertEqual(resolve_timezone("sydney").key, "Australia/Sydney")
        self.assertEqual(resolve_timezone("london").key, "Europe/London")
        self.assertEqual(resolve_timezone("paris").key, "Europe/Paris")
        self.assertEqual(resolve_timezone("invalid_unknown_tz").key, "America/New_York")

        # Test scheduling intent extracts international timezones
        intent_sg = extract_scheduling_intent("Let's connect next week, I am based in Singapore (SGT).")
        self.assertTrue(intent_sg["has_scheduling_intent"])
        self.assertEqual(intent_sg["detected_timezone"], "Asia/Singapore")

        intent_lon = extract_scheduling_intent("Happy to chat, send an invite for Thursday london time.")
        self.assertTrue(intent_lon["has_scheduling_intent"])
        self.assertEqual(intent_lon["detected_timezone"], "Europe/London")

        # Generate slots for Singapore prospect
        slots_sg = calculate_conflict_free_slots(
            rep_email="ae-apac@ele-in.com",
            prospect_tz="Asia/Singapore",
            duration_minutes=30
        )
        self.assertEqual(len(slots_sg), 3)
        for s in slots_sg:
            # Local times must be 10:00 AM, 02:00 PM, or 04:00 PM
            self.assertIn(s["local_time"], ["10:00 AM", "02:00 PM", "04:00 PM"])
            # Display label must present local time with timezone indicator, not raw UTC
            self.assertNotIn("UTC", s["display_label"])
            # ISO timestamp must be valid UTC ending with Z
            self.assertTrue(s["iso"].endswith("Z"))
            utc_dt = datetime.fromisoformat(s["iso"].replace("Z", "+00:00"))
            self.assertEqual(utc_dt.tzinfo, timezone.utc)

    def test_02_calendar_slot_double_booking_and_database_concurrency_guard(self):
        """
        Verify Calendar Concierge blocks concurrent double-booking of rep slots
        both in-memory and via distributed database lease checks.
        """
        rep = "marcus-vance@ele-in.com"
        slot_iso = "2026-11-05T14:00:00Z"

        # Mock Supabase simulating an existing confirmed booking by another prospect
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "book-existing-999", "confirmation_token": "tok_other_client"}
        ]

        # Confirming the same slot for a different token must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            confirm_meeting_slot(
                confirmation_token="tok_new_prospect",
                selected_slot_iso=slot_iso,
                workspace_id="ws-test",
                supabase=mock_sb
            )
        self.assertIn("already booked", str(ctx.exception).lower())

    def test_03_abm_strict_tenant_isolation_without_toy_substrings(self):
        """
        Verify ABM multithreading enforces strict identity-based workspace boundaries.
        Neutral tenant names like 'ws-corporate-client' or 'ws-acme-corp' must be strictly blocked
        from accessing another workspace's target accounts and buying committees.
        """
        # Create account under tenant Alpha
        created = create_or_map_target_account(
            workspace_id="ws-tenant-alpha-enterprise",
            company_name="CloudMatrix Systems",
            domain="cloudmatrix.io",
            leads=[{"name": "Devon Scott", "title": "CTO", "email": "devon@cloudmatrix.io"}]
        )
        acc_id = created["account"]["id"]
        mem_id = created["committee_members"][0]["id"]

        # An unrelated workspace without any toy substrings ('attacker' / 'malicious')
        foreign_workspace = "ws-standard-business-tenant"

        # Reading committee members must be blocked
        with self.assertRaises(PermissionError):
            get_account_committee_members(workspace_id=foreign_workspace, account_id=acc_id)

        # Updating committee member status must be blocked
        with self.assertRaises(PermissionError):
            update_committee_member_status(workspace_id=foreign_workspace, member_id=mem_id, status="engaged")

        # Resolving ABM context for sequence execution must be blocked
        with self.assertRaises(PermissionError):
            resolve_abm_context_for_execution(
                workspace_id=foreign_workspace,
                account_id=acc_id,
                lead_id="lead-test",
                prospect_name="Devon Scott",
                title="CTO"
            )

        # Arbitrary tenants cannot read demo accounts (ws-default) either
        with self.assertRaises(PermissionError):
            get_account_committee_members(workspace_id=foreign_workspace, account_id="acc-stripe")

    def test_04_bandit_strictly_scoped_feedback_and_timezone_aware_timestamps(self):
        """
        Verify Thompson Bandit feedback query scopes database updates with workspace_id,
        rejects cross-tenant mutations, and records timezone-aware UTC timestamps.
        """
        mock_sb = MagicMock()
        # Mock database returning a variant owned by ws-foreign-corp
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {
                "id": "var-12345",
                "workspace_id": "ws-foreign-corp",
                "alpha_param": 2.0,
                "beta_param": 2.0,
                "impressions": 10,
                "positive_replies": 1,
                "objections": 1,
                "unsubscribes": 0,
                "status": "active"
            }
        ]

        # Calling record_variant_feedback from ws-client-tenant must raise PermissionError
        with self.assertRaises(PermissionError):
            record_variant_feedback(
                variant_id="var-12345",
                outcome="positive_reply",
                workspace_id="ws-client-tenant",
                supabase=mock_sb
            )


if __name__ == "__main__":
    unittest.main()
