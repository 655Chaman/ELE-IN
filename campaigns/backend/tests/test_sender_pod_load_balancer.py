"""
test_sender_pod_load_balancer.py — Test Suite for Multi-Sender Pod Load Balancer & Dynamic Fleet Failover Engine
Rigorously tests the Three-Layer Logic Architecture (Paranoia Framework) for Smartlead/Instantly-style sender pods.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from campaigns.backend.services.sender_pod_service import (
    get_workspace_sender_pods,
    select_pod_sender,
    trigger_pod_failover,
    quarantine_sender_account,
    release_quarantine,
    emergency_pause_pod,
    resume_pod,
    _calculate_account_action_capacity,
    _is_account_quarantined
)


class TestSenderPodLoadBalancer(unittest.TestCase):
    """
    Rigorously tests Multi-Sender Pod Load Balancer & Fleet Failover.
    Layer 0: Foundational capacity evaluation & strategy rotation.
    Layer 1: Environmental failure analysis (exhaustion, critical health, failover).
    Layer 2: Human paranoia (thread affinity lock, emergency pause, collision guard).
    """

    def setUp(self):
        self.supabase = MagicMock()
        self.workspace_id = "ws_pod_test_101"
        self.campaign_id = "camp_alpha_202"

    # =========================================================================
    # Layer 0: Capacity Calculation & Quarantine Detection
    # =========================================================================

    def test_is_account_quarantined_detection(self):
        """Layer 0: Correctly identifies quarantined or cooling down accounts."""
        # 1. Status based
        self.assertTrue(_is_account_quarantined({"status": "QUARANTINED"}))
        self.assertTrue(_is_account_quarantined({"status": "COOLING_DOWN"}))
        self.assertTrue(_is_account_quarantined({"status": "DISCONNECTED"}))
        self.assertFalse(_is_account_quarantined({"status": "ACTIVE"}))

        # 2. Quarantined until date in future
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        self.assertTrue(_is_account_quarantined({"status": "ACTIVE", "quarantined_until": future_iso}))

        # 3. Quarantined until date in past
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        self.assertFalse(_is_account_quarantined({"status": "ACTIVE", "quarantined_until": past_iso}))

    def test_calculate_account_action_capacity_mature_account(self):
        """Layer 0: Computes mature account remaining headroom accurately."""
        account = {
            "id": "acc_mature_1",
            "is_warmup": False,
            "daily_connection_limit": 50
        }
        # Mock usage query returning 18 actions consumed today
        usage_table = MagicMock()
        usage_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"count": 18}]
        )
        self.supabase.table.return_value = usage_table

        cap = _calculate_account_action_capacity(account, "connection_request", self.supabase, "2026-10-10")
        self.assertEqual(cap["daily_limit"], 50)
        self.assertEqual(cap["consumed_today"], 18)
        self.assertEqual(cap["remaining_headroom"], 32)
        self.assertEqual(cap["utilization_pct"], 36.0)
        self.assertFalse(cap["is_warmup"])

    def test_calculate_account_action_capacity_warmup_account(self):
        """Layer 0: Computes warmup account cap correctly."""
        account = {
            "id": "acc_warmup_1",
            "is_warmup": True,
            "warmup_max_connections": 15
        }
        usage_table = MagicMock()
        usage_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"count": 10}]
        )
        self.supabase.table.return_value = usage_table

        cap = _calculate_account_action_capacity(account, "connection_request", self.supabase, "2026-10-10")
        self.assertEqual(cap["daily_limit"], 15)
        self.assertEqual(cap["consumed_today"], 10)
        self.assertEqual(cap["remaining_headroom"], 5)
        self.assertTrue(cap["is_warmup"])

    # =========================================================================
    # Layer 0: Workspace Pod Fleet Metrics Aggregation
    # =========================================================================

    def test_get_workspace_sender_pods_metrics_aggregation(self):
        """Layer 0: Correctly aggregates pod capacity, healthy counts, and utilization."""
        # Mock tables
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": "camp_1",
                        "name": "Outbound Pod Alpha",
                        "status": "ACTIVE",
                        "pod_dispatch_strategy": "CAPACITY_WEIGHTED",
                        "pod_failover_enabled": True,
                        "pod_emergency_paused": False
                    }]
                )
            elif tbl_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": "acc_1",
                            "name": "Alex Sender",
                            "status": "ACTIVE",
                            "is_warmup": False,
                            "daily_connection_limit": 40
                        },
                        {
                            "id": "acc_2",
                            "name": "Beth Sender",
                            "status": "ACTIVE",
                            "is_warmup": False,
                            "daily_connection_limit": 30
                        }
                    ]
                )
            elif tbl_name == "campaign_accounts":
                t.select.return_value.execute.return_value = MagicMock(
                    data=[
                        {"campaign_id": "camp_1", "account_id": "acc_1", "weight": 100},
                        {"campaign_id": "camp_1", "account_id": "acc_2", "weight": 100}
                    ]
                )
            elif tbl_name == "account_daily_action_counts":
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"count": 10}]
                )
            return t

        self.supabase.table.side_effect = table_side_effect

        pods = get_workspace_sender_pods(self.workspace_id, self.supabase)
        self.assertEqual(len(pods), 1)
        pod = pods[0]
        self.assertEqual(pod["campaign_id"], "camp_1")
        self.assertEqual(pod["total_senders"], 2)
        self.assertEqual(pod["healthy_senders"], 2)
        self.assertEqual(pod["total_daily_capacity"], 70)  # 40 + 30
        self.assertEqual(pod["total_consumed_today"], 20)  # 10 + 10
        self.assertEqual(pod["remaining_capacity_today"], 50)
        self.assertEqual(pod["pod_health_status"], "HEALTHY")

    # =========================================================================
    # Strategy Dispatching: Capacity-Weighted vs Round-Robin vs Warmup
    # =========================================================================

    def test_select_pod_sender_capacity_weighted_picks_highest_headroom(self):
        """Layer 0: CAPACITY_WEIGHTED picks account with greatest remaining capacity headroom."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False, "pod_dispatch_strategy": "CAPACITY_WEIGHTED"}]
                )
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {"account_id": "acc_low_cap", "weight": 100},
                        {"account_id": "acc_high_cap", "weight": 100}
                    ]
                )
            elif tbl_name == "accounts":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "acc_low_cap", "name": "Low Cap", "status": "ACTIVE", "daily_connection_limit": 40},
                        {"id": "acc_high_cap", "name": "High Cap", "status": "ACTIVE", "daily_connection_limit": 50}
                    ]
                )
            elif tbl_name == "account_daily_action_counts":
                # acc_low_cap has 35 consumed (headroom 5)
                # acc_high_cap has 10 consumed (headroom 40)
                def count_side_effect():
                    # We can inspect the eq calls or return depending on account_id
                    return MagicMock(data=[{"count": 10}])
                t.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute = count_side_effect
            elif tbl_name == "sender_pod_audit_logs":
                t.insert.return_value.execute.return_value = MagicMock()
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            mock_calc.side_effect = [
                {"daily_limit": 40, "consumed_today": 35, "remaining_headroom": 5, "utilization_pct": 87.5, "is_warmup": False},
                {"daily_limit": 50, "consumed_today": 10, "remaining_headroom": 40, "utilization_pct": 20.0, "is_warmup": False}
            ]

            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="connection_request",
                supabase=self.supabase,
                strategy="CAPACITY_WEIGHTED"
            )

            self.assertEqual(result["status"], "DISPATCH_SUCCESS")
            self.assertEqual(result["account_id"], "acc_high_cap")
            self.assertEqual(result["remaining_headroom"], 40)

    def test_select_pod_sender_round_robin_picks_lowest_consumed(self):
        """Layer 0: ROUND_ROBIN picks account with lowest consumed count today."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False, "pod_dispatch_strategy": "ROUND_ROBIN"}]
                )
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[
                        {"account_id": "acc_busy", "weight": 100},
                        {"account_id": "acc_idle", "weight": 100}
                    ]
                )
            elif tbl_name == "accounts":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "acc_busy", "name": "Busy", "status": "ACTIVE", "daily_connection_limit": 50},
                        {"id": "acc_idle", "name": "Idle", "status": "ACTIVE", "daily_connection_limit": 50}
                    ]
                )
            elif tbl_name == "sender_pod_audit_logs":
                t.insert.return_value.execute.return_value = MagicMock()
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            mock_calc.side_effect = [
                {"daily_limit": 50, "consumed_today": 25, "remaining_headroom": 25, "utilization_pct": 50.0, "is_warmup": False},
                {"daily_limit": 50, "consumed_today": 2, "remaining_headroom": 48, "utilization_pct": 4.0, "is_warmup": False}
            ]

            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="connection_request",
                supabase=self.supabase,
                strategy="ROUND_ROBIN"
            )

            self.assertEqual(result["status"], "DISPATCH_SUCCESS")
            self.assertEqual(result["account_id"], "acc_idle")

    # =========================================================================
    # Layer 2 Paranoia: Lead Thread Affinity Inviolability
    # =========================================================================

    def test_thread_affinity_locks_to_initiating_account(self):
        """Layer 2: Once a lead is enrolled with an account, all touches stay locked to that sender."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False, "pod_dispatch_strategy": "CAPACITY_WEIGHTED"}]
                )
            elif tbl_name == "campaign_enrollments":
                # Lead is bound to acc_original
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"account_id": "acc_original"}]
                )
            elif tbl_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": "acc_original",
                        "name": "Original Sender",
                        "status": "ACTIVE",
                        "daily_message_limit": 40
                    }]
                )
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            mock_calc.return_value = {
                "daily_limit": 40,
                "consumed_today": 12,
                "remaining_headroom": 28,
                "utilization_pct": 30.0,
                "is_warmup": False
            }

            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="message",
                supabase=self.supabase,
                lead_id="lead_vip_999"
            )

            self.assertEqual(result["status"], "THREAD_AFFINITY_LOCKED")
            self.assertEqual(result["account_id"], "acc_original")

    def test_thread_affinity_waits_when_initiating_account_reached_limit(self):
        """Layer 2: When initiating account has 0 headroom today, outreach waits instead of hijacking thread."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False}]
                )
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"account_id": "acc_capped"}]
                )
            elif tbl_name == "accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_capped", "status": "ACTIVE", "daily_message_limit": 40}]
                )
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            # 0 headroom remaining
            mock_calc.return_value = {
                "daily_limit": 40,
                "consumed_today": 40,
                "remaining_headroom": 0,
                "utilization_pct": 100.0,
                "is_warmup": False
            }

            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="message",
                supabase=self.supabase,
                lead_id="lead_vip_999"
            )

            self.assertEqual(result["status"], "THREAD_AFFINITY_CAPACITY_WAIT")
            self.assertIsNone(result["account_id"])
            self.assertEqual(result["initiating_account_id"], "acc_capped")

    # =========================================================================
    # Layer 1: Environmental Failure Analysis (Exhaustion & Critical Health)
    # =========================================================================

    def test_all_pod_capacities_exhausted_returns_next_window(self):
        """Layer 1: When all pod accounts have exhausted limits, returns ALL_CAPACITIES_EXHAUSTED."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False}]
                )
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"account_id": "acc_1", "weight": 100}]
                )
            elif tbl_name == "accounts":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_1", "status": "ACTIVE"}]
                )
            return t

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service._calculate_account_action_capacity") as mock_calc:
            mock_calc.return_value = {"daily_limit": 40, "consumed_today": 40, "remaining_headroom": 0}

            result = select_pod_sender(
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                action_type="connection_request",
                supabase=self.supabase
            )

            self.assertEqual(result["status"], "ALL_CAPACITIES_EXHAUSTED")
            self.assertIsNone(result["account_id"])
            self.assertIn("next_window_retry_at", result)

    def test_critical_pod_health_when_all_accounts_quarantined(self):
        """Layer 1: When all accounts are quarantined or restricted, returns POD_HEALTH_CRITICAL."""
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "campaigns":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"pod_emergency_paused": False}]
                )
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif tbl_name == "campaign_accounts":
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"account_id": "acc_dead", "weight": 100}]
                )
            elif tbl_name == "accounts":
                t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_dead", "status": "DISCONNECTED"}]
                )
            return t

        self.supabase.table.side_effect = table_side_effect

        result = select_pod_sender(
            campaign_id=self.campaign_id,
            workspace_id=self.workspace_id,
            action_type="connection_request",
            supabase=self.supabase
        )

        self.assertEqual(result["status"], "POD_HEALTH_CRITICAL")
        self.assertIsNone(result["account_id"])

    # =========================================================================
    # Layer 1 & 2: Dynamic Failover & Quarantine Management
    # =========================================================================

    def test_trigger_pod_failover_quarantines_and_reassigns_leads(self):
        """Layer 1 & 2: Dynamic failover isolates failed account and reassigns in-flight enrollments."""
        accounts_table = MagicMock()
        enrollments_table = MagicMock()
        outbox_table = MagicMock()
        audit_table = MagicMock()

        mock_data = MagicMock(data=[{"id": "enr_1"}, {"id": "enr_2"}])
        enrollments_table.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = mock_data
        enrollments_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = mock_data

        def table_side_effect(tbl_name):
            if tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "campaign_enrollments":
                return enrollments_table
            elif tbl_name == "outbox_events":
                return outbox_table
            elif tbl_name == "sender_pod_audit_logs":
                return audit_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        with patch("campaigns.backend.services.sender_pod_service.select_pod_sender") as mock_select:
            mock_select.return_value = {
                "account_id": "acc_backup_healthy",
                "status": "DISPATCH_SUCCESS"
            }

            result = trigger_pod_failover(
                failed_account_id="acc_failing",
                campaign_id=self.campaign_id,
                workspace_id=self.workspace_id,
                supabase=self.supabase,
                failure_reason="COOKIE_EXPIRED"
            )

            self.assertEqual(result["status"], "FAILOVER_EXECUTED")
            self.assertEqual(result["backup_account_id"], "acc_backup_healthy")
            self.assertEqual(result["reassigned_count"], 2)

            # Check failing account was quarantined
            accounts_table.update.assert_called()
            quarantine_call = accounts_table.update.call_args[0][0]
            self.assertEqual(quarantine_call["status"], "QUARANTINED")

            # Check enrollments were updated
            enrollments_table.update.assert_called_with({"account_id": "acc_backup_healthy"})

    def test_quarantine_and_release_sender_account(self):
        """Layer 1: Manual quarantine and release cycle."""
        accounts_table = MagicMock()
        audit_table = MagicMock()

        def table_side_effect(tbl_name):
            if tbl_name == "accounts":
                return accounts_table
            elif tbl_name == "sender_pod_audit_logs":
                return audit_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        # 1. Quarantine
        q_res = quarantine_sender_account("acc_test", self.workspace_id, self.supabase, hours=48, reason="SUSPECT_CAPTCHA")
        self.assertEqual(q_res["status"], "QUARANTINED")
        self.assertEqual(q_res["reason"], "SUSPECT_CAPTCHA")
        accounts_table.update.assert_called()

        # 2. Release
        r_res = release_quarantine("acc_test", self.workspace_id, self.supabase)
        self.assertEqual(r_res["status"], "ACTIVE")
        self.assertIn("restored", r_res["message"])

    def test_emergency_pause_and_resume_pod(self):
        """Layer 2: Emergency pause freeze and resume toggles."""
        camp_table = MagicMock()
        audit_table = MagicMock()

        def table_side_effect(tbl_name):
            if tbl_name == "campaigns":
                return camp_table
            elif tbl_name == "sender_pod_audit_logs":
                return audit_table
            return MagicMock()

        self.supabase.table.side_effect = table_side_effect

        # 1. Pause
        p_res = emergency_pause_pod(self.campaign_id, self.workspace_id, self.supabase)
        self.assertTrue(p_res["pod_emergency_paused"])
        camp_table.update.assert_called_with({"pod_emergency_paused": True})

        # 2. Resume
        res_res = resume_pod(self.campaign_id, self.workspace_id, self.supabase)
        self.assertFalse(res_res["pod_emergency_paused"])
        camp_table.update.assert_called_with({"pod_emergency_paused": False})


class TestSenderPodRouterEndpoints(unittest.TestCase):
    """
    Tests FastAPI router endpoints for sender pods.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.workspace_id = "ws_mock_router_1"
        self.mock_supabase = MagicMock()

        # Override dependencies
        app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        app.dependency_overrides[get_supabase_client] = lambda: self.mock_supabase

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("campaigns.backend.routers.sender_pods.get_workspace_sender_pods")
    def test_get_pods_endpoint_success(self, mock_get_pods):
        mock_get_pods.return_value = [{
            "pod_id": "pod-1",
            "campaign_id": "c-1",
            "campaign_name": "Test Pod",
            "campaign_status": "ACTIVE",
            "pod_health_status": "HEALTHY",
            "dispatch_strategy": "CAPACITY_WEIGHTED",
            "total_senders": 2,
            "healthy_senders": 2,
            "quarantined_senders": 0,
            "degraded_senders": 0,
            "total_daily_capacity": 80,
            "total_consumed_today": 20,
            "remaining_capacity_today": 60,
            "pod_utilization_pct": 25.0,
            "accounts": []
        }]

        resp = self.client.get("/api/campaigns/pods")
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data["status"], "success")
        self.assertEqual(json_data["data"]["summary"]["total_pods"], 1)
        self.assertEqual(json_data["data"]["summary"]["total_healthy"], 2)

    @patch("campaigns.backend.routers.sender_pods.select_pod_sender")
    def test_dispatch_endpoint_success(self, mock_dispatch):
        mock_dispatch.return_value = {
            "account_id": "acc_best_123",
            "status": "DISPATCH_SUCCESS",
            "remaining_headroom": 25
        }

        resp = self.client.post("/api/campaigns/pods/camp_1/dispatch", json={"action_type": "connection_request"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["account_id"], "acc_best_123")

    @patch("campaigns.backend.routers.sender_pods.quarantine_sender_account")
    def test_quarantine_account_endpoint(self, mock_quarantine):
        mock_quarantine.return_value = {
            "account_id": "acc_target",
            "status": "QUARANTINED",
            "quarantined_until": "2026-10-11T00:00:00Z",
            "reason": "MANUAL_QUARANTINE"
        }

        resp = self.client.post("/api/campaigns/pods/accounts/acc_target/quarantine", json={"hours": 24})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "QUARANTINED")


if __name__ == "__main__":
    unittest.main()
