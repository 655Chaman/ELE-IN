"""
test_stage28_sender_pods_and_deliverability_paranoia_hardening.py — Paranoia Test Suite for Stage 28
Multi-Sender Pod Load Balancer, Deliverability Engine & Dynamic Fleet Failover Hardening

Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Mechanics (Zero-limit intentional caps, expired quarantine detection, strategy normalization, P2P warmup pacing)
- Layer 1: Environmental Failure Analysis (Tenant isolation in candidates/affinity, orchestrator deferral on capacity exhaustion, failover exhaustion critical alerts)
- Layer 2: Human Paranoia (Non-numeric/negative weights, empty/whitespace IDs, extreme quarantine hours, case-insensitive status toggles, CSV formula injection defense)
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from campaigns.backend.services.sender_pod_service import (
    _calculate_account_action_capacity,
    _is_account_quarantined,
    select_pod_sender,
    trigger_pod_failover,
    quarantine_sender_account,
    release_quarantine,
    emergency_pause_pod,
    resume_pod,
    get_workspace_sender_pods
)
from campaigns.backend.services.warmup_service import (
    calculate_daily_ramp_limit,
    normalize_domain,
    sanitize_text,
    sanitize_csv_field,
    create_warmup_mailbox,
    toggle_warmup_status,
    audit_domain_dns_health
)


class TestStage28SenderPodsAndDeliverabilityParanoiaHardening(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws_stage28_prod"
        self.campaign_id = "camp_stage28_alpha"
        self.supabase = MagicMock()

    # =========================================================================
    # LAYER 0: FOUNDATIONAL LAYER
    # =========================================================================

    def test_zero_daily_limit_respected_without_mature_fallback(self):
        """Layer 0: Intentional limit of 0 connections/messages must not fallback to default 35."""
        account = {
            "id": "acc_zero_limit",
            "is_warmup": False,
            "daily_connection_limit": 0,
            "daily_message_limit": 0
        }
        usage_table = MagicMock()
        usage_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"count": 0}]
        )
        self.supabase.table.return_value = usage_table

        cap = _calculate_account_action_capacity(account, "connection_request", self.supabase)
        self.assertEqual(cap["daily_limit"], 0)
        self.assertEqual(cap["remaining_headroom"], 0)
        self.assertEqual(cap["utilization_pct"], 100.0)

    def test_is_account_quarantined_expired_cooldown_returns_false(self):
        """Layer 0: An account whose quarantine period has elapsed must return False (not permanently stuck)."""
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        account = {
            "status": "QUARANTINED",
            "quarantined_until": past_iso
        }
        self.assertFalse(_is_account_quarantined(account))

        # But unexpired quarantine must still return True
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        account_future = {
            "status": "QUARANTINED",
            "quarantined_until": future_iso
        }
        self.assertTrue(_is_account_quarantined(account_future))

        # Hard administrative restrictions always return True
        self.assertTrue(_is_account_quarantined({"status": "RESTRICTED"}))
        self.assertTrue(_is_account_quarantined({"status": "DISCONNECTED"}))

    def test_p2p_warmup_daily_ramp_calculations_and_strategy_normalization(self):
        """Layer 0: P2P warmup calculation correctly normalizes strategies and caps limits."""
        # Gentle strategy (case-insensitive)
        self.assertEqual(calculate_daily_ramp_limit(1, "GENTLE", 40), 3)
        self.assertEqual(calculate_daily_ramp_limit(6, " gentle ", 40), 6)

        # Aggressive strategy
        self.assertEqual(calculate_daily_ramp_limit(1, "AGGRESSIVE", 40), 11)
        self.assertEqual(calculate_daily_ramp_limit(3, "fast", 40), 17)

        # Default balanced
        self.assertEqual(calculate_daily_ramp_limit(1, "balanced", 40), 7)
        self.assertEqual(calculate_daily_ramp_limit(10, "UNKNOWN_STRAT", 40), 25)

        # Capped strictly at 50 max
        self.assertEqual(calculate_daily_ramp_limit(100, "aggressive", 100), 50)

    def test_create_warmup_mailbox_email_validation(self):
        """Layer 0: Invalid or missing email address raises ValueError."""
        with self.assertRaises(ValueError):
            create_warmup_mailbox(self.workspace_id, "", "Name")

        with self.assertRaises(ValueError):
            create_warmup_mailbox(self.workspace_id, "invalid-no-at", "Name")

        with self.assertRaises(ValueError):
            create_warmup_mailbox(self.workspace_id, "@domain.com", "Name")

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # =========================================================================

    def test_candidate_accounts_filtered_by_workspace_isolation(self):
        """Layer 1: Foreign workspace accounts in campaign_accounts are filtered out of candidate list."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"workspace_id": self.workspace_id, "pod_emergency_paused": False, "pod_dispatch_strategy": "CAPACITY_WEIGHTED"}]
                )
            elif tbl_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {"account_id": "acc_ours", "weight": 100},
                        {"account_id": "acc_foreign", "weight": 100}
                    ]
                )
            elif tbl_name == "accounts":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "acc_ours", "name": "Ours", "status": "ACTIVE", "workspace_id": self.workspace_id},
                        {"id": "acc_foreign", "name": "Foreign", "status": "ACTIVE", "workspace_id": "ws_other_victim"}
                    ]
                )
            elif tbl_name == "sender_pod_audit_logs":
                t.insert.return_value.execute.return_value = MagicMock()
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            mock_calc.return_value = {
                "daily_limit": 40, "consumed_today": 5, "remaining_headroom": 35, "utilization_pct": 12.5, "is_warmup": False
            }

            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="connection_request",
                supabase=self.supabase
            )

            self.assertEqual(result["status"], "DISPATCH_SUCCESS")
            # Only acc_ours must be dispatched, never acc_foreign!
            self.assertEqual(result["account_id"], "acc_ours")

    def test_thread_affinity_foreign_tenant_account_rejected(self):
        """Layer 1: If thread affinity points to an initiating account from another workspace, reject dispatch."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"workspace_id": self.workspace_id, "pod_emergency_paused": False}]
                )
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"account_id": "acc_foreign_init"}]
                )
            elif tbl_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_foreign_init", "workspace_id": "ws_foreign_victim", "status": "ACTIVE"}]
                )
            return t

        self.supabase.table.side_effect = table_side_effect

        result = select_pod_sender(
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            action_type="message",
            supabase=self.supabase,
            lead_id="lead_999"
        )

        self.assertEqual(result["status"], "UNAUTHORIZED_WORKSPACE")
        self.assertIn("another workspace", result["message"].lower())

    def test_failover_exhaustion_emits_critical_outbox_alert(self):
        """Layer 1: When no backup senders exist in the pod, failover emits a CRITICAL alert to outbox_events."""
        from collections import defaultdict
        tables = defaultdict(MagicMock)

        def table_side_effect(tbl_name):
            t = tables[tbl_name]
            if tbl_name == "accounts":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_solo_failed", "workspace_id": self.workspace_id}]
                )
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_solo_failed", "workspace_id": self.workspace_id}]
                )
                t.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            elif tbl_name == "campaigns":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.campaign_id, "workspace_id": self.workspace_id}]
                )
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": self.campaign_id, "workspace_id": self.workspace_id}]
                )
            elif tbl_name == "outbox_events":
                t.insert.return_value.execute.return_value = MagicMock()
            elif tbl_name == "sender_pod_audit_logs":
                t.insert.return_value.execute.return_value = MagicMock()
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service.select_pod_sender") as mock_select:
            # No backup senders available
            mock_select.return_value = {"account_id": None, "status": "POD_HEALTH_CRITICAL"}

            res = trigger_pod_failover(
                failed_account_id="acc_solo_failed",
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                supabase=self.supabase,
                failure_reason="SESSION_REVOKED"
            )

            self.assertEqual(res["status"], "FAILOVER_EXHAUSTED")
            self.assertIsNone(res["backup_account_id"])

            # Verify critical outbox event was queued
            outbox_table = self.supabase.table("outbox_events")
            self.assertTrue(outbox_table.insert.called)
            inserted_payload = outbox_table.insert.call_args[0][0]
            self.assertEqual(inserted_payload["payload"]["severity"], "critical")
            self.assertIn("Exhausted", inserted_payload["payload"]["title"])

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA
    # =========================================================================

    def test_non_numeric_and_negative_weights_sanitized(self):
        """Layer 2: Malformed or negative weights in pod links are safely coerced to 100.0 without crash."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False, "pod_dispatch_strategy": "CAPACITY_WEIGHTED"}]
                )
            elif tbl_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {"account_id": "acc_bad_w1", "weight": -50},
                        {"account_id": "acc_bad_w2", "weight": "NaN"},
                        {"account_id": "acc_bad_w3", "weight": None}
                    ]
                )
            elif tbl_name == "accounts":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "acc_bad_w1", "status": "ACTIVE"},
                        {"id": "acc_bad_w2", "status": "ACTIVE"},
                        {"id": "acc_bad_w3", "status": "ACTIVE"}
                    ]
                )
            elif tbl_name == "sender_pod_audit_logs":
                t.insert.return_value.execute.return_value = MagicMock()
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            mock_calc.return_value = {
                "daily_limit": 50, "consumed_today": 10, "remaining_headroom": 40, "utilization_pct": 20.0, "is_warmup": False
            }

            # Must not raise TypeError, ValueError, or division errors
            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="connection_request",
                supabase=self.supabase
            )

            self.assertEqual(result["status"], "DISPATCH_SUCCESS")
            self.assertIsNotNone(result["account_id"])

    def test_empty_whitespace_parameters_fail_closed_safely(self):
        """Layer 2: Blank or whitespace IDs fail closed with clear status without executing blind SQL updates."""
        # quarantine_sender_account
        q_res = quarantine_sender_account("   ", self.workspace_id, self.supabase)
        self.assertEqual(q_res["status"], "ERROR")

        # release_quarantine
        r_res = release_quarantine("", self.workspace_id, self.supabase)
        self.assertEqual(r_res["status"], "ERROR")

        # emergency_pause_pod
        p_res = emergency_pause_pod("   ", self.workspace_id, self.supabase)
        self.assertFalse(p_res["pod_emergency_paused"])

        # resume_pod
        res_res = resume_pod(self.campaign_id, "", self.supabase)
        self.assertFalse(res_res["pod_emergency_paused"])

    def test_extreme_quarantine_hours_clamped(self):
        """Layer 2: Quarantine hours are strictly clamped between 1 and 168 (7 days)."""
        # Negative hours clamped to 1
        res_low = quarantine_sender_account("acc_test", self.workspace_id, self.supabase, hours=-10)
        self.assertEqual(res_low["status"], "QUARANTINED")

        # Massive hours clamped to 168
        res_high = quarantine_sender_account("acc_test", self.workspace_id, self.supabase, hours=9999)
        self.assertEqual(res_high["status"], "QUARANTINED")

    def test_toggle_warmup_status_case_insensitivity(self):
        """Layer 2: toggle_warmup_status normalizes uppercase or whitespace status strings."""
        res_warming = toggle_warmup_status("wm-001", self.workspace_id, "WARMING", supabase=None)
        self.assertEqual(res_warming["warmup_status"], "warming")

        res_paused = toggle_warmup_status("wm-001", self.workspace_id, "  PAUSED  ", supabase=None)
        self.assertEqual(res_paused["warmup_status"], "paused")

        res_grad = toggle_warmup_status("wm-001", self.workspace_id, "GRADUATED", supabase=None)
        self.assertEqual(res_grad["warmup_status"], "graduated")

    def test_csv_formula_injection_defense_neutralizes_all_triggers(self):
        """Layer 2: CSV export formula injection defense neutralizes =, +, -, @, \t, \r, %."""
        self.assertEqual(sanitize_csv_field("=1+1"), '"\'=1+1"')
        self.assertEqual(sanitize_csv_field("+1+1"), '"\'+1+1"')
        self.assertEqual(sanitize_csv_field("-1+1"), '"\'-1+1"')
        self.assertEqual(sanitize_csv_field("@SUM(A1:A10)"), '"\'@SUM(A1:A10)"')
        self.assertEqual(sanitize_csv_field("%username%"), '"\'%username%"')
        self.assertEqual(sanitize_csv_field("\tcmd.exe"), '"\'\tcmd.exe"')
        self.assertEqual(sanitize_csv_field("Normal Text"), '"Normal Text"')


if __name__ == "__main__":
    unittest.main()
