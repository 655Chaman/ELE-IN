"""
Three-Layer Paranoia Framework Unit Test Suite:
Exclusion & DNC Settings API Endpoints (Search, Filter, Export, Freemail Guards)
"""
import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException
from leads.backend.routers.leads import (
    get_suppression_list_endpoint,
    export_suppression_csv_endpoint,
    delete_suppression_entry_endpoint,
    delete_suppression_batch_endpoint,
    SuppressionBatchDeleteRequest,
    add_suppression_entry_endpoint,
    SuppressionEntryRequest
)

class TestSuppressionSettingsAPI(unittest.TestCase):

    def test_get_suppression_list_with_search_and_type_filters(self):
        """Layer 0 & 1: Supports searching by term and filtering by entry_type."""
        mock_supabase = MagicMock()
        mock_query = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value = mock_query

        mock_query.not_.is_.return_value = mock_query
        mock_query.or_.return_value = mock_query
        mock_query.order.return_value.range.return_value.execute.return_value = MagicMock(
            count=2,
            data=[
                {"id": "s1", "domain": "competitor.com", "value": "competitor.com", "reason": "competitor"},
                {"id": "s2", "email": "optout@acme.com", "value": "optout@acme.com", "reason": "customer_request"}
            ]
        )

        res = get_suppression_list_endpoint(
            limit=50,
            offset=0,
            search="competitor",
            entry_type="domain",
            workspace_id="ws_1",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["data"]), 2)
        mock_query.not_.is_.assert_called_with("domain", "null")
        mock_query.or_.assert_called()

    def test_export_suppression_csv_sanitizes_injection_characters(self):
        """Layer 2: Export CSV strictly prefixes formula injection tokens (=, +, -, @, \\t, \\r)."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "value": "=cmd|' /C calc'!A0",
                    "email": "+123456789@evil.com",
                    "domain": "-SUM(A1:B2).com",
                    "linkedin_url": "@malicious_profile",
                    "reason": "\tstealth_reason",
                    "created_at": "2026-11-02T08:00:00Z"
                }
            ]
        )

        res = export_suppression_csv_endpoint(
            workspace_id="ws_1",
            supabase=mock_supabase
        )

        self.assertEqual(res.media_type, "text/csv")
        content = res.body.decode("utf-8")
        self.assertIn("Type,Value,Email,Domain,LinkedIn URL,Reason,Created At", content)
        # Verify formula characters are safely neutralized with leading single quote
        self.assertIn("'=cmd|' /C calc'!A0", content)
        self.assertIn("'+123456789@evil.com", content)
        self.assertIn("'-SUM(A1:B2).com", content)
        self.assertIn("'@malicious_profile", content)
        self.assertIn("'\tstealth_reason", content)

    def test_delete_suppression_entry_verifies_tenant_boundary(self):
        """Layer 1: Reject deletion if the suppression entry belongs to another workspace (IDOR defense)."""
        mock_supabase = MagicMock()
        # Mock chk query returning empty data (unauthorized / not found)
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with self.assertRaises(HTTPException) as ctx:
            delete_suppression_entry_endpoint(
                entry_id="entry_other_tenant",
                workspace_id="ws_attacker",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found or unauthorized", ctx.exception.detail)

    def test_delete_suppression_batch_endpoint_success(self):
        """Layer 0 & 1: Multi-select batch unblock verifies tenant ownership and deletes matched rows."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "entry_1"}, {"id": "entry_2"}]
        )
        mock_supabase.table.return_value.delete.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        req = SuppressionBatchDeleteRequest(entry_ids=["entry_1", "entry_2", "unauthorized_entry"])
        res = delete_suppression_batch_endpoint(
            payload=req,
            workspace_id="ws_1",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "batch_deleted")
        self.assertEqual(res["deleted_count"], 2)
        self.assertEqual(res["ids"], ["entry_1", "entry_2"])

    def test_delete_suppression_batch_endpoint_empty(self):
        """Layer 2: Empty input payload safely returns zero deleted count without running DB queries."""
        mock_supabase = MagicMock()
        req = SuppressionBatchDeleteRequest(entry_ids=[])
        res = delete_suppression_batch_endpoint(
            payload=req,
            workspace_id="ws_1",
            supabase=mock_supabase
        )
        self.assertEqual(res["status"], "batch_deleted")
        self.assertEqual(res["deleted_count"], 0)
        self.assertEqual(res["ids"], [])
