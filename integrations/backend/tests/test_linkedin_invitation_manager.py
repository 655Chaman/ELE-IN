"""
test_linkedin_invitation_manager.py — Test Suite for LinkedIn Pending Invitation GC & Algorithmic Connection Safety Cooldown.

Phase 41: Advanced LinkedIn Health & Garbage Collection Service.
Testing across the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
  - Layer 1: Environmental Failure Analysis (Edge Cases, Clamping, Datetime Robustness, DB Drops)
  - Layer 2: Human Paranoia (Malformed Inputs, Type Confusion, Boundary Violations, Multi-Key Tolerance)
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from integrations.backend.services.linkedin_invitation_manager import (
    AccountHealthRisk,
    CooldownReason,
    InvitationStatus,
    LinkedInInvitationManager,
    _parse_utc_datetime,
    check_linkedin_3week_resend_cooldown,
    evaluate_account_connection_health,
    filter_stale_invitations,
    is_account_in_cooldown,
    trigger_account_cooldown,
    withdraw_stale_invitations,
)


class TestLinkedInInvitationManagerLayer0(unittest.TestCase):
    """Layer 0: Foundational Layer — Core Mechanics & Primary Business Logic."""

    def test_evaluate_health_score_optimal(self):
        """Pending < 300 returns OPTIMAL (score >= 85), can_send_invitations=True."""
        res = evaluate_account_connection_health(pending_count=150, weekly_sent_count=40)
        self.assertEqual(res["risk_level"], AccountHealthRisk.OPTIMAL.value)
        self.assertGreaterEqual(res["health_score"], 85)
        self.assertLessEqual(res["health_score"], 100)
        self.assertTrue(res["can_send_invitations"])
        self.assertEqual(res["pending_count"], 150)
        self.assertIn("optimal", res["recommendation"].lower())

    def test_evaluate_health_score_approaching_ceiling(self):
        """Pending 350 returns APPROACHING_CEILING (score 50-84), recommends withdrawing invites > 14 days."""
        res = evaluate_account_connection_health(pending_count=350, weekly_sent_count=70)
        self.assertEqual(res["risk_level"], AccountHealthRisk.APPROACHING_CEILING.value)
        self.assertGreaterEqual(res["health_score"], 50)
        self.assertLessEqual(res["health_score"], 84)
        self.assertTrue(res["can_send_invitations"])
        self.assertEqual(res["pending_count"], 350)
        self.assertIn("14 days", res["recommendation"])

    def test_evaluate_health_score_critical_risk(self):
        """Pending 550 returns CRITICAL_RESTRICTION_RISK (score < 50), aggressive GC required, cannot send."""
        res = evaluate_account_connection_health(pending_count=550, weekly_sent_count=100)
        self.assertEqual(res["risk_level"], AccountHealthRisk.CRITICAL_RESTRICTION_RISK.value)
        self.assertLess(res["health_score"], 50)
        self.assertFalse(res["can_send_invitations"])
        self.assertEqual(res["pending_count"], 550)
        self.assertIn("Critical restriction risk", res["recommendation"])

    def test_filter_stale_invitations_finds_old_invites(self):
        """Finds invites with age >= 14 days and ignores younger invites."""
        now = datetime.now(timezone.utc)
        invitations = [
            {"id": "inv_1", "sent_at": (now - timedelta(days=20)).isoformat(), "recipient_name": "Alice"},
            {"id": "inv_2", "sent_at": (now - timedelta(days=5)).isoformat(), "recipient_name": "Bob"},
            {"id": "inv_3", "days_pending": 18, "recipient_name": "Charlie"},
            {"id": "inv_4", "days_pending": 8, "recipient_name": "David"},
        ]
        stale = filter_stale_invitations(invitations, max_age_days=14)
        stale_ids = [s["id"] for s in stale]
        self.assertIn("inv_1", stale_ids)
        self.assertNotIn("inv_2", stale_ids)
        self.assertIn("inv_3", stale_ids)
        self.assertNotIn("inv_4", stale_ids)
        self.assertEqual(len(stale), 2)

    def test_withdraw_stale_invitations_updates_status(self):
        """Status set to WITHDRAWN and remaining pending count recalculated correctly."""
        now = datetime.now(timezone.utc)
        mock_invites = [
            {"id": "inv_old_1", "sent_at": (now - timedelta(days=25)).isoformat()},
            {"id": "inv_old_2", "sent_at": (now - timedelta(days=16)).isoformat()},
            {"id": "inv_fresh", "sent_at": (now - timedelta(days=3)).isoformat()},
        ]
        account = {"id": "acc_123", "pending_count": 3}
        res = withdraw_stale_invitations(account, max_age_days=14, batch_limit=25, mock_invitations=mock_invites)
        self.assertEqual(res["account_id"], "acc_123")
        self.assertEqual(res["withdrawn_count"], 2)
        self.assertEqual(res["remaining_pending"], 1)
        self.assertEqual(len(res["withdrawn_items"]), 2)
        for item in res["withdrawn_items"]:
            self.assertEqual(item["status"], InvitationStatus.WITHDRAWN.value)
            self.assertIn("withdrawn_at", item)
            self.assertIn("cooldown_until", item)

    def test_record_21_day_resend_cooldown(self):
        """Withdrawing invite stamps 21-day cooldown (linkedin_reconnect_cooldown_until / cooldown_until)."""
        now = datetime.now(timezone.utc)
        mock_invites = [{"id": "inv_target", "sent_at": (now - timedelta(days=21)).isoformat()}]
        account = {"id": "acc_1"}
        res = withdraw_stale_invitations(account, max_age_days=14, mock_invitations=mock_invites)
        self.assertEqual(res["cooldown_enforced_days"], 21)
        item = res["withdrawn_items"][0]
        cooldown_dt = _parse_utc_datetime(item["cooldown_until"])
        self.assertIsNotNone(cooldown_dt)
        # Expected to be ~21 days in future
        diff_days = (cooldown_dt - now).total_seconds() / 86400.0
        self.assertAlmostEqual(diff_days, 21.0, delta=0.1)

    def test_check_3week_resend_cooldown_blocks_resend(self):
        """Active 21-day cooldown returns (True, reason)."""
        future = datetime.now(timezone.utc) + timedelta(days=15)
        lead = {
            "id": "lead_123",
            "linkedin_reconnect_cooldown_until": future.isoformat(),
        }
        is_blocked, reason = check_linkedin_3week_resend_cooldown(lead)
        self.assertTrue(is_blocked)
        self.assertIsNotNone(reason)
        self.assertIn("LinkedIn 21-day anti-resend cooldown", reason)

    def test_check_3week_resend_cooldown_permits_after_expiry(self):
        """Expired 21-day cooldown returns (False, None)."""
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        lead = {
            "id": "lead_123",
            "linkedin_reconnect_cooldown_until": past.isoformat(),
        }
        is_blocked, reason = check_linkedin_3week_resend_cooldown(lead)
        self.assertFalse(is_blocked)
        self.assertIsNone(reason)

    def test_trigger_account_cooldown_and_check(self):
        """Sets cooldown_until for 48 hours and confirms is_account_in_cooldown."""
        res = trigger_account_cooldown("acc_99", CooldownReason.INVITATION_LIMIT_REACHED, duration_hours=48)
        self.assertEqual(res["account_id"], "acc_99")
        self.assertTrue(res["in_cooldown"])
        self.assertEqual(res["reason"], CooldownReason.INVITATION_LIMIT_REACHED.value)
        self.assertEqual(res["duration_hours"], 48)

        # Check account state with resulting object
        account_record = {
            "id": "acc_99",
            "cooldown_until": res["cooldown_until"],
            "cooldown_reason": res["reason"],
        }
        in_cd, cd_reason = is_account_in_cooldown(account_record)
        self.assertTrue(in_cd)
        self.assertEqual(cd_reason, CooldownReason.INVITATION_LIMIT_REACHED.value)


class TestLinkedInInvitationManagerLayer1(unittest.TestCase):
    """Layer 1: Environmental Failure Analysis — Clamping, Corrupt Data, DB Drops, Datetime Parsing."""

    def test_max_age_days_clamped_to_minimum_7(self):
        """Passing max_age_days=1 is clamped to 7 to prevent accidental mass withdrawal of fresh invites."""
        now = datetime.now(timezone.utc)
        invitations = [
            {"id": "inv_3d", "sent_at": (now - timedelta(days=3)).isoformat()},
            {"id": "inv_8d", "sent_at": (now - timedelta(days=8)).isoformat()},
        ]
        # Requesting 1 day should be clamped to 7 days
        stale = filter_stale_invitations(invitations, max_age_days=1)
        stale_ids = [s["id"] for s in stale]
        self.assertNotIn("inv_3d", stale_ids)
        self.assertIn("inv_8d", stale_ids)

    def test_max_age_days_clamped_to_maximum_90(self):
        """Passing max_age_days=365 clamped to 90."""
        now = datetime.now(timezone.utc)
        invitations = [
            {"id": "inv_80d", "sent_at": (now - timedelta(days=80)).isoformat()},
            {"id": "inv_95d", "sent_at": (now - timedelta(days=95)).isoformat()},
        ]
        # Requesting 365 days clamped to 90 days: inv_95d qualifies (>=90d), inv_80d does not (<90d)
        stale = filter_stale_invitations(invitations, max_age_days=365)
        stale_ids = [s["id"] for s in stale]
        self.assertNotIn("inv_80d", stale_ids)
        self.assertIn("inv_95d", stale_ids)

    def test_batch_limit_clamped_to_50(self):
        """Passing batch_limit=500 clamped to 50 to prevent LinkedIn bot detection."""
        now = datetime.now(timezone.utc)
        mock_invites = [
            {"id": f"inv_{i}", "sent_at": (now - timedelta(days=20)).isoformat()}
            for i in range(100)
        ]
        account = {"id": "acc_clamp"}
        res = withdraw_stale_invitations(account, max_age_days=14, batch_limit=500, mock_invitations=mock_invites)
        self.assertEqual(res["withdrawn_count"], 50)
        self.assertEqual(len(res["withdrawn_items"]), 50)

    def test_batch_limit_clamped_to_minimum_1(self):
        """Passing batch_limit=0 or negative is clamped to 1."""
        now = datetime.now(timezone.utc)
        mock_invites = [
            {"id": f"inv_{i}", "sent_at": (now - timedelta(days=20)).isoformat()}
            for i in range(10)
        ]
        account = {"id": "acc_clamp_min"}
        res = withdraw_stale_invitations(account, max_age_days=14, batch_limit=-5, mock_invitations=mock_invites)
        self.assertEqual(res["withdrawn_count"], 1)

    def test_database_drop_non_fatal_fallback(self):
        """Database outage or table error during withdrawal simulation handled gracefully."""
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = RuntimeError("Supabase connection refused (PostgREST 503)")

        now = datetime.now(timezone.utc)
        mock_invites = [
            {"id": "inv_1", "lead_id": "lead_1", "sent_at": (now - timedelta(days=25)).isoformat()}
        ]
        account = {"id": "acc_db_fail"}
        # Should not raise exception
        res = withdraw_stale_invitations(
            account,
            max_age_days=14,
            batch_limit=10,
            mock_invitations=mock_invites,
            supabase=mock_supabase,
        )
        self.assertEqual(res["withdrawn_count"], 1)
        self.assertEqual(res["withdrawn_items"][0]["status"], InvitationStatus.WITHDRAWN.value)

    def test_terminal_statuses_ignored_by_filter(self):
        """Invitations with status WITHDRAWN, ACCEPTED, EXPIRED are ignored."""
        invitations = [
            {"id": "inv_w", "status": "WITHDRAWN", "days_pending": 30},
            {"id": "inv_a", "status": "ACCEPTED", "days_pending": 30},
            {"id": "inv_e", "status": "EXPIRED", "days_pending": 30},
            {"id": "inv_p", "status": "PENDING", "days_pending": 30},
        ]
        stale = filter_stale_invitations(invitations, max_age_days=14)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["id"], "inv_p")

    def test_datetime_parsing_iso_z_and_numeric_and_naive(self):
        """_parse_utc_datetime parses ISO with Z, ISO with offset, float timestamp, and naive datetime."""
        # 1. Trailing Z
        dt1 = _parse_utc_datetime("2026-10-18T12:00:00Z")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.tzinfo, timezone.utc)
        self.assertEqual(dt1.hour, 12)

        # 2. Offset
        dt2 = _parse_utc_datetime("2026-10-18T14:00:00+02:00")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.astimezone(timezone.utc).hour, 12)

        # 3. Numeric timestamp
        dt3 = _parse_utc_datetime(1729252800)
        self.assertIsNotNone(dt3)
        self.assertEqual(dt3.tzinfo, timezone.utc)

        # 4. Naive datetime converted to UTC
        naive = datetime(2026, 10, 18, 12, 0, 0)
        dt4 = _parse_utc_datetime(naive)
        self.assertIsNotNone(dt4)
        self.assertEqual(dt4.tzinfo, timezone.utc)

        # 5. Invalid string returns None
        self.assertIsNone(_parse_utc_datetime("invalid-timestamp-string"))
        self.assertIsNone(_parse_utc_datetime(None))

    def test_duration_hours_clamped(self):
        """Trigger account cooldown clamps duration_hours between 1 and 720 hours."""
        res_min = trigger_account_cooldown("acc_clamp_dur", CooldownReason.CAPTCHA_CHALLENGE, duration_hours=-10)
        self.assertEqual(res_min["duration_hours"], 1)

        res_max = trigger_account_cooldown("acc_clamp_dur", CooldownReason.CAPTCHA_CHALLENGE, duration_hours=9999)
        self.assertEqual(res_max["duration_hours"], 720)


class TestLinkedInInvitationManagerLayer2(unittest.TestCase):
    """Layer 2: Human Paranoia & Defensive Input Sanitization."""

    def test_malformed_account_and_empty_inputs_handled_safely(self):
        """Handles None, empty dicts, empty lists, and garbage types without exceptions."""
        # evaluate_account_connection_health with None / strings
        res1 = evaluate_account_connection_health(pending_count=None, weekly_sent_count=None)  # type: ignore
        self.assertEqual(res1["pending_count"], 0)
        self.assertEqual(res1["risk_level"], AccountHealthRisk.OPTIMAL.value)

        res2 = evaluate_account_connection_health(pending_count="garbage_string", weekly_sent_count="invalid")  # type: ignore
        self.assertEqual(res2["pending_count"], 0)
        self.assertEqual(res2["risk_level"], AccountHealthRisk.OPTIMAL.value)

        # Negative pending counts clamped to 0
        res3 = evaluate_account_connection_health(pending_count=-50, weekly_sent_count=-10)
        self.assertEqual(res3["pending_count"], 0)

        # filter_stale_invitations with None / empty
        self.assertEqual(filter_stale_invitations([], max_age_days=14), [])
        self.assertEqual(filter_stale_invitations(None, max_age_days=14), [])  # type: ignore
        self.assertEqual(filter_stale_invitations(["not_a_dict", 123, None], max_age_days=14), [])  # type: ignore

        # withdraw_stale_invitations with empty account
        res4 = withdraw_stale_invitations({})
        self.assertEqual(res4["account_id"], "unknown_account")
        self.assertEqual(res4["withdrawn_count"], 0)

        # check_linkedin_3week_resend_cooldown with None or empty
        self.assertEqual(check_linkedin_3week_resend_cooldown(None), (False, None))  # type: ignore
        self.assertEqual(check_linkedin_3week_resend_cooldown({}), (False, None))
        self.assertEqual(check_linkedin_3week_resend_cooldown({"cooldown_until": "corrupt_date"}), (False, None))

        # is_account_in_cooldown with None or empty
        self.assertEqual(is_account_in_cooldown(None), (False, None))  # type: ignore
        self.assertEqual(is_account_in_cooldown({}), (False, None))

    def test_facade_class_methods(self):
        """LinkedInInvitationManager exposes all static methods accurately."""
        health = LinkedInInvitationManager.evaluate_account_connection_health(200)
        self.assertEqual(health["risk_level"], AccountHealthRisk.OPTIMAL.value)

        cd_status, _ = LinkedInInvitationManager.is_account_in_cooldown({"in_cooldown": True})
        self.assertTrue(cd_status)

        cd_lead, _ = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown({})
        self.assertFalse(cd_lead)

    def test_multi_key_cooldown_attribute_tolerance(self):
        """check_linkedin_3week_resend_cooldown checks reconnect_cooldown_until and cooldown_until as fallbacks."""
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()

        lead1 = {"reconnect_cooldown_until": future}
        self.assertTrue(check_linkedin_3week_resend_cooldown(lead1)[0])

        lead2 = {"cooldown_until": future}
        self.assertTrue(check_linkedin_3week_resend_cooldown(lead2)[0])


if __name__ == "__main__":
    unittest.main()
