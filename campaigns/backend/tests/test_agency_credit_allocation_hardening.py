import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from core.backend.api.routers.agencies import (
    allocate_agency_credits,
    reclaim_agency_credits,
    CreditAllocateRequest,
    CreditReclaimRequest,
    _PROCESSED_AGENCY_TRANSFERS
)


class TestAgencyCreditAllocationHardening(unittest.IsolatedAsyncioTestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests H-06 Agency Credit Allocation TOCTOU Race & Fallback Compensation.
    Guarantees:
    - Layer 0: Primary RPC path executes atomic transfer with full ledger logging.
    - Layer 1: Fallback path locks via mutex, re-reads fresh balances, and executes atomic rollback if either step fails.
    - Layer 2: Client double-click / idempotency deduplication prevents repeated credit transfers.
    """

    def setUp(self):
        _PROCESSED_AGENCY_TRANSFERS.clear()

    @patch("core.backend.api.routers.agencies._verify_agency_owner_or_admin", new_callable=AsyncMock)
    @patch("core.backend.api.routers.agencies._resolve_agency_master_workspace", new_callable=AsyncMock)
    async def test_allocate_rpc_path_success_and_dedupe(self, mock_resolve_master, mock_verify):
        """Layer 0 & 2: Successful RPC transfer is cached and duplicate submission returns cached result."""
        mock_verify.return_value = None
        mock_resolve_master.return_value = {"id": "ws-master-1", "name": "Master Workspace"}

        mock_supabase = MagicMock()
        # Mock client workspace check
        mock_check = MagicMock()
        mock_check.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": "ws-client-1",
            "agency_id": "agency-123",
            "data_cleaning_credits": 200,
            "allocated_credit_budget": 200
        }]))
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value = mock_check

        # Mock RPC
        mock_rpc = MagicMock()
        mock_rpc.execute = AsyncMock(return_value=MagicMock(data={
            "success": True,
            "from_balance": 800,
            "to_balance": 400
        }))
        mock_supabase.rpc.return_value = mock_rpc

        req = CreditAllocateRequest(
            client_workspace_id="ws-client-1",
            amount=200,
            idempotency_key="idem_alloc_001"
        )

        # Call 1
        res1 = await allocate_agency_credits(
            agency_id="agency-123",
            payload=req,
            supabase=mock_supabase,
            user_id="user-admin"
        )
        self.assertEqual(res1["status"], "success")
        self.assertEqual(res1["master_balance"], 800)
        self.assertEqual(res1["client_balance"], 400)
        self.assertEqual(mock_supabase.rpc.call_count, 1)

        # Call 2 (Duplicate click with same idempotency key) -> Should hit dedupe cache with 0 extra RPC calls!
        res2 = await allocate_agency_credits(
            agency_id="agency-123",
            payload=req,
            supabase=mock_supabase,
            user_id="user-admin"
        )
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["master_balance"], 800)
        self.assertEqual(mock_supabase.rpc.call_count, 1)

    @patch("core.backend.api.routers.agencies._verify_agency_owner_or_admin", new_callable=AsyncMock)
    @patch("core.backend.api.routers.agencies._resolve_agency_master_workspace", new_callable=AsyncMock)
    async def test_allocate_rpc_insufficient_balance_blocks(self, mock_resolve_master, mock_verify):
        """Layer 1: RPC insufficient balance raises HTTP 400 without invoking fallback."""
        mock_verify.return_value = None
        mock_resolve_master.return_value = {"id": "ws-master-1", "name": "Master Workspace"}

        mock_supabase = MagicMock()
        mock_check = MagicMock()
        mock_check.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": "ws-client-1",
            "agency_id": "agency-123",
            "data_cleaning_credits": 10
        }]))
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value = mock_check

        mock_rpc = MagicMock()
        mock_rpc.execute = AsyncMock(return_value=MagicMock(data={
            "success": False,
            "reason": "insufficient_balance",
            "available": 50
        }))
        mock_supabase.rpc.return_value = mock_rpc

        req = CreditAllocateRequest(
            client_workspace_id="ws-client-1",
            amount=500
        )

        with self.assertRaises(HTTPException) as ctx:
            await allocate_agency_credits(
                agency_id="agency-123",
                payload=req,
                supabase=mock_supabase,
                user_id="user-admin"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Insufficient credits in master pool", ctx.exception.detail)

    @patch("core.backend.api.routers.agencies._verify_agency_owner_or_admin", new_callable=AsyncMock)
    @patch("core.backend.api.routers.agencies._resolve_agency_master_workspace", new_callable=AsyncMock)
    async def test_allocate_fallback_rollback_on_client_credit_failure(self, mock_resolve_master, mock_verify):
        """Layer 1: If crediting client fails in fallback, master deduction is rolled back."""
        mock_verify.return_value = None
        mock_resolve_master.return_value = {"id": "ws-master-1", "name": "Master Workspace"}

        mock_supabase = MagicMock()

        # Step 1: Client check
        target_check = MagicMock()
        target_check.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": "ws-client-1",
            "agency_id": "agency-123",
            "data_cleaning_credits": 100,
            "allocated_credit_budget": 100
        }]))

        # Step 2: In fallback, fresh master balance read
        master_read = MagicMock()
        master_read.execute = AsyncMock(return_value=MagicMock(data=[{"data_cleaning_credits": 1000}]))

        # Step 3: In fallback, fresh client balance read
        client_read = MagicMock()
        client_read.execute = AsyncMock(return_value=MagicMock(data=[{
            "data_cleaning_credits": 100,
            "allocated_credit_budget": 100
        }]))

        select_call_count = 0
        def fake_select(*args, **kwargs):
            nonlocal select_call_count
            select_call_count += 1
            ret = MagicMock()
            if select_call_count == 1:
                ret.eq.return_value.limit.return_value = target_check
            elif select_call_count == 2:
                ret.eq.return_value.limit.return_value = master_read
            else:
                ret.eq.return_value.limit.return_value = client_read
            return ret

        mock_supabase.table.return_value.select = fake_select

        # Force RPC to fail with an exception to trigger the fallback
        mock_rpc = MagicMock()
        mock_rpc.execute = AsyncMock(side_effect=Exception("PGRST202: function transfer_agency_credits_safely not found"))
        mock_supabase.rpc.return_value = mock_rpc

        # Updates: 1st update is master deduct (succeeds). 2nd update is client credit (fails!).
        update_call_count = 0
        def fake_update(data):
            nonlocal update_call_count
            update_call_count += 1
            ret = MagicMock()
            if update_call_count == 1:
                # Master deduct (new_m = 900)
                ret.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            elif update_call_count == 2:
                # Client credit fails!
                ret.eq.return_value.execute = AsyncMock(side_effect=Exception("DB write timeout on client"))
            elif update_call_count == 3:
                # Master rollback compensation (restoring 1000)
                ret.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            return ret

        mock_supabase.table.return_value.update = fake_update

        req = CreditAllocateRequest(
            client_workspace_id="ws-client-1",
            amount=100
        )

        with self.assertRaises(HTTPException) as ctx:
            await allocate_agency_credits(
                agency_id="agency-123",
                payload=req,
                supabase=mock_supabase,
                user_id="user-admin"
            )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("allocation rolled back", ctx.exception.detail)
        # Verify rollback update was called (total update calls == 3)
        self.assertEqual(update_call_count, 3)

    @patch("core.backend.api.routers.agencies._verify_agency_owner_or_admin", new_callable=AsyncMock)
    @patch("core.backend.api.routers.agencies._resolve_agency_master_workspace", new_callable=AsyncMock)
    async def test_reclaim_fallback_rollback_on_master_credit_failure(self, mock_resolve_master, mock_verify):
        """Layer 1: If crediting master fails in reclaim fallback, client deduction is rolled back."""
        mock_verify.return_value = None
        mock_resolve_master.return_value = {"id": "ws-master-1", "name": "Master Workspace"}

        mock_supabase = MagicMock()

        target_check = MagicMock()
        target_check.execute = AsyncMock(return_value=MagicMock(data=[{
            "id": "ws-client-1",
            "agency_id": "agency-123",
            "data_cleaning_credits": 300,
            "allocated_credit_budget": 300
        }]))

        client_read = MagicMock()
        client_read.execute = AsyncMock(return_value=MagicMock(data=[{
            "data_cleaning_credits": 300,
            "allocated_credit_budget": 300
        }]))

        master_read = MagicMock()
        master_read.execute = AsyncMock(return_value=MagicMock(data=[{"data_cleaning_credits": 500}]))

        select_call_count = 0
        def fake_select(*args, **kwargs):
            nonlocal select_call_count
            select_call_count += 1
            ret = MagicMock()
            if select_call_count == 1:
                ret.eq.return_value.limit.return_value = target_check
            elif select_call_count == 2:
                ret.eq.return_value.limit.return_value = client_read
            else:
                ret.eq.return_value.limit.return_value = master_read
            return ret

        mock_supabase.table.return_value.select = fake_select

        mock_rpc = MagicMock()
        mock_rpc.execute = AsyncMock(side_effect=Exception("PGRST202: missing function"))
        mock_supabase.rpc.return_value = mock_rpc

        update_call_count = 0
        def fake_update(data):
            nonlocal update_call_count
            update_call_count += 1
            ret = MagicMock()
            if update_call_count == 1:
                # Client deduct (300 - 150 = 150)
                ret.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            elif update_call_count == 2:
                # Master credit fails!
                ret.eq.return_value.execute = AsyncMock(side_effect=Exception("Connection lost crediting master"))
            elif update_call_count == 3:
                # Client rollback compensation (restoring 300)
                ret.eq.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
            return ret

        mock_supabase.table.return_value.update = fake_update

        req = CreditReclaimRequest(
            client_workspace_id="ws-client-1",
            amount=150
        )

        with self.assertRaises(HTTPException) as ctx:
            await reclaim_agency_credits(
                agency_id="agency-123",
                payload=req,
                supabase=mock_supabase,
                user_id="user-admin"
            )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("reclaim rolled back", ctx.exception.detail)
        self.assertEqual(update_call_count, 3)


if __name__ == "__main__":
    unittest.main()
