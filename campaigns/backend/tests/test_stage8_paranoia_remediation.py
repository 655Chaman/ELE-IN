import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from campaigns.backend.routers.elein import run_campaign_preflight_audit, get_lists
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class TestStage8ParanoiaRemediation(unittest.TestCase):
    """
    Test suite for Batch 4 Paranoia Remediation:
    - VULN-16, VULN-17, VULN-18, VULN-19: Database RLS & RPC Security Hardening
    - UI-14: Stale/Deleted Sender Account Detection in Preflight Gate
    - ENG-10 / ENG-13: Outbox Processing Lock Leak Recovery Sweeper
    - API-09: Paginated Lead List Retrieval with Strict Boundary Limits
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.workspace_id = "ws-test-stage8-uuid"

    # =========================================================================
    # VULN-16, 17, 18, 19: Database Security & Base Schema Parity
    # =========================================================================
    def test_schema_contains_campaign_versions_rls_and_rpc_revocations(self):
        """Verifies supabase_schema.sql and migration 100 contain RLS and RPC revocations."""
        with open("backend/supabase_schema.sql", "r") as f:
            schema_content = f.read()

        with open("backend/migrations/100_campaign_subsystem_paranoia_hardening.sql", "r") as f:
            migration_content = f.read()

        # Check RLS enabled on campaign_versions
        self.assertIn("ALTER TABLE public.campaign_versions ENABLE ROW LEVEL SECURITY;", schema_content)
        self.assertIn("ALTER TABLE public.campaign_versions ENABLE ROW LEVEL SECURITY;", migration_content)
        self.assertIn("campaign_versions_tenant_isolation", schema_content)
        self.assertIn("campaign_versions_tenant_isolation", migration_content)

        # Check dynamic revocation of sensitive RPCs
        for func_name in ["deduct_credits_safely", "bulk_import_leads", "get_user_id_by_email"]:
            self.assertIn(func_name, schema_content)
            self.assertIn(func_name, migration_content)
            self.assertIn("FROM PUBLIC", schema_content)
            self.assertIn("FROM anon, authenticated", schema_content)
            self.assertIn("TO service_role", schema_content)

    # =========================================================================
    # UI-14: Stale Sender Account Selection Surviving Account Deletion
    # =========================================================================
    def test_preflight_blocks_launch_when_sender_accounts_are_deleted(self):
        """Preflight audit fails with hard blocker if any assigned sender account has been deleted."""
        # Setup mock accounts query returning only 1 account when 2 were requested
        sender_ids = ["acc-valid-1", "acc-deleted-2"]
        mock_acc_table = MagicMock()
        mock_acc_res = MagicMock(data=[
            {
                "id": "acc-valid-1",
                "name": "Alex Sender",
                "status": "ACTIVE",
                "is_active": True,
                "proxy_id": "proxy-1"
            }
        ])
        mock_acc_table.select.return_value.in_.return_value.eq.return_value.execute.return_value = mock_acc_res
        self.mock_supabase.table.return_value = mock_acc_table

        nodes = [{"id": "node-1", "type": "linkedin_message", "data": {"body": "Hello {{first_name}}!"}}]
        edges = []

        result = run_campaign_preflight_audit(
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id,
            campaign_name="Outreach Campaign",
            nodes_raw=nodes,
            edges_raw=edges,
            sender_ids=sender_ids,
            lead_list_id="list-1"
        )

        # Verify launch is blocked due to missing/deleted account
        self.assertFalse(result["can_launch"])
        self.assertIn("deleted or unlinked", " ".join(result["critical_errors"]))
        sender_check = next(c for c in result["checks"] if c["id"] == "senders")
        self.assertEqual(sender_check["status"], "fail")
        self.assertEqual(sender_check["score"], 0)

    # =========================================================================
    # ENG-10 / ENG-13: Outbox Stale Processing Recovery
    # =========================================================================
    def test_sweep_stale_outbox_events_recovers_marooned_processing_events(self):
        """Orchestrator sweeps and resurrects events stuck in processing >10m."""
        mock_table = MagicMock()
        mock_update_res = MagicMock(data=[
            {"id": "evt-1", "status": "pending"},
            {"id": "evt-2", "status": "pending"}
        ])
        mock_table.update.return_value.eq.return_value.lt.return_value.execute.return_value = mock_update_res
        self.mock_supabase.table.return_value = mock_table

        orchestrator = EleInOrchestrator(supabase=self.mock_supabase)
        reaped_count = orchestrator.sweep_stale_outbox_events(timeout_minutes=10)

        self.assertEqual(reaped_count, 2)
        mock_table.update.assert_called_once()
        update_args = mock_table.update.call_args[0][0]
        self.assertEqual(update_args["status"], "pending")
        self.assertIn("auto-reaped", update_args["last_error"])

    # =========================================================================
    # API-09: Unbounded Lead List Endpoint Pagination
    # =========================================================================
    def test_get_lists_enforces_pagination_boundaries(self):
        """get_lists enforces limit and offset range query against Supabase."""
        mock_table = MagicMock()
        mock_res = MagicMock(data=[{"id": "list-1", "name": "CEOs"}])
        mock_table.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = mock_res
        self.mock_supabase.table.return_value = mock_table

        # Call with custom limit and offset
        result = get_lists(
            limit=25,
            offset=50,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "list-1")
        # Check range called with offset=50, offset + limit - 1 = 74
        mock_table.select.return_value.eq.return_value.order.return_value.range.assert_called_once_with(50, 74)

    def test_get_lists_clamps_limit_to_maximum_200(self):
        """get_lists clamps excessive limit to 200."""
        mock_table = MagicMock()
        mock_res = MagicMock(data=[])
        mock_table.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value = mock_res
        self.mock_supabase.table.return_value = mock_table

        get_lists(
            limit=9999,  # Attempt excessive limit
            offset=0,
            supabase=self.mock_supabase,
            workspace_id=self.workspace_id
        )

        # Clamped to 200 (range 0 to 199)
        mock_table.select.return_value.eq.return_value.order.return_value.range.assert_called_once_with(0, 199)


if __name__ == "__main__":
    unittest.main()
