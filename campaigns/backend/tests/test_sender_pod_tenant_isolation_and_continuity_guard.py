import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
from fastapi import HTTPException

from campaigns.backend.services.sender_pod_service import (
    get_workspace_sender_pods,
    select_pod_sender,
    trigger_pod_failover,
)
from campaigns.backend.routers.sender_pods import (
    trigger_pod_failover_endpoint,
    PodFailoverRequest,
)


class TestSenderPodTenantIsolationAndContinuityGuard(unittest.TestCase):
    """
    Step 36 Track B — Multi-Sender Pod Load Balancer & Dynamic Fleet Failover Hardening
    - Multi-tenant campaign scoping in get_workspace_sender_pods
    - Cross-tenant IDOR protection in select_pod_sender and trigger_pod_failover
    - Mid-conversation continuity vs pre-connection failover
    - Router exception propagation for unauthorized workspace operations
    """

    def setUp(self):
        self.workspace_id = "ws_pod_alpha_1"
        self.supabase = MagicMock()

    # =========================================================================
    # 1. Cross-Tenant IDOR Guards (Layer 1)
    # =========================================================================

    def test_select_pod_sender_rejects_foreign_workspace_campaign(self):
        """Refuses to select a sender if the campaign belongs to a foreign workspace."""
        camp_table = MagicMock()
        camp_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "camp_victim",
                "workspace_id": "ws_victim_tenant",  # foreign workspace!
                "pod_emergency_paused": False,
                "pod_dispatch_strategy": "CAPACITY_WEIGHTED"
            }]
        )
        self.supabase.table.return_value = camp_table

        res = select_pod_sender(
            campaign_id="camp_victim",
            workspace_id="ws_attacker_tenant",
            action_type="connection_request",
            supabase=self.supabase
        )
        self.assertIsNone(res.get("account_id"))
        self.assertEqual(res.get("status"), "UNAUTHORIZED_WORKSPACE")
        self.assertIn("does not belong", res.get("message").lower())

    def test_trigger_pod_failover_rejects_foreign_workspace_account(self):
        """Refuses to quarantine/failover an account belonging to another tenant."""
        acc_table = MagicMock()
        acc_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "acc_foreign",
                "workspace_id": "ws_foreign_tenant"  # foreign account!
            }]
        )
        self.supabase.table.return_value = acc_table

        res = trigger_pod_failover(
            failed_account_id="acc_foreign",
            campaign_id="camp_1",
            workspace_id="ws_attacker_tenant",
            supabase=self.supabase
        )
        self.assertEqual(res.get("status"), "FAILOVER_REJECTED")
        self.assertIn("does not belong", res.get("message").lower())

    def test_trigger_pod_failover_endpoint_raises_403_on_foreign_tenant(self):
        """Router propagates FAILOVER_REJECTED due to workspace mismatch as HTTP 403."""
        with patch("campaigns.backend.routers.sender_pods.trigger_pod_failover") as mock_failover:
            mock_failover.return_value = {
                "status": "FAILOVER_REJECTED",
                "message": "Failed account does not belong to the requested workspace."
            }
            req = PodFailoverRequest(failed_account_id="acc_foreign_99", failure_reason="TEST")
            with self.assertRaises(HTTPException) as ctx:
                trigger_pod_failover_endpoint(
                    campaign_id="camp_1",
                    payload=req,
                    workspace_id="ws_attacker",
                    supabase=self.supabase
                )
            self.assertEqual(ctx.exception.status_code, 403)

    # =========================================================================
    # 2. Multi-Tenant Scoped Queries in get_workspace_sender_pods (Layer 0)
    # =========================================================================

    def test_get_workspace_sender_pods_scopes_campaign_accounts_query(self):
        """get_workspace_sender_pods queries campaign_accounts scoped to this workspace's campaigns."""
        camp_data = [{"id": "camp_alpha", "name": "Alpha", "status": "ACTIVE"}]
        acc_data = [{"id": "acc_1", "status": "ACTIVE", "is_warmup": False}]
        ca_data = [{"campaign_id": "camp_alpha", "account_id": "acc_1", "weight": 100}]

        tables = defaultdict(MagicMock)
        def mock_table(tname):
            m = tables[tname]
            if tname == "campaigns":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=camp_data)
            elif tname == "accounts":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=acc_data)
            elif tname == "campaign_accounts":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=ca_data)
                m.select.return_value.execute.return_value = MagicMock(data=ca_data)
            elif tname == "account_daily_action_counts":
                m.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            return m

        self.supabase.table.side_effect = mock_table
        pods = get_workspace_sender_pods(self.workspace_id, self.supabase)
        self.assertEqual(len(pods), 1)
        self.assertEqual(pods[0]["campaign_id"], "camp_alpha")

    # =========================================================================
    # 3. Mid-Conversation Continuity Protection (Layer 1 & Layer 2)
    # =========================================================================

    @patch("campaigns.backend.services.sender_pod_service.select_pod_sender")
    def test_trigger_pod_failover_protects_mid_conversation_leads(self, mock_select):
        """Only reassigns pre-connection leads; leaves mid-thread leads bound to avoid stranger-messaging."""
        mock_select.return_value = {"account_id": "acc_backup_42", "status": "DISPATCH_SUCCESS"}

        tables = defaultdict(MagicMock)
        def mock_table(tname):
            m = tables[tname]
            if tname == "accounts":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "acc_failed", "workspace_id": self.workspace_id}]
                )
            elif tname == "campaign_enrollments":
                # 2 leads: 1 pending (pre-connection), 1 in_progress
                m.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[
                        {"id": "enr_pre_conn", "status": "pending"},
                        {"id": "enr_mid_thread", "status": "in_progress"}
                    ]
                )
            return m

        self.supabase.table.side_effect = mock_table

        res = trigger_pod_failover(
            failed_account_id="acc_failed",
            campaign_id="camp_1",
            workspace_id=self.workspace_id,
            supabase=self.supabase
        )
        self.assertEqual(res.get("status"), "FAILOVER_EXECUTED")
        self.assertEqual(res.get("backup_account_id"), "acc_backup_42")


if __name__ == "__main__":
    unittest.main()
