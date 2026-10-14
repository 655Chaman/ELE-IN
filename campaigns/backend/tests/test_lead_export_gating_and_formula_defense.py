import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from leads.backend.routers.leads import (
    export_leads_in_list,
    export_social_radar_csv_endpoint,
    sanitize_csv_value
)


class TestLeadExportGatingAndFormulaDefense(unittest.IsolatedAsyncioTestCase):
    """
    Paranoia Layer 0, 1 & 2: Tests H-09 Lead Export Gating, Masking in Fallbacks, and Formula Defense.
    Guarantees:
    - Layer 0: Pro tier exports retain unmasked contacts.
    - Layer 1: Free tier exports mask emails even in in-memory error fallback; social-radar export is tier-gated.
    - Layer 2: CSV export values starting with =, +, -, @, \t, \r are neutralized against spreadsheet injection.
    """

    def test_sanitize_csv_value_neutralizes_formula_injection(self):
        """Layer 2: Spreadsheet formula injection characters are escaped with leading quote."""
        self.assertEqual(sanitize_csv_value("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_value("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(sanitize_csv_value("-5"), "'-5")
        self.assertEqual(sanitize_csv_value("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_csv_value("\tmalicious"), "'\tmalicious")
        self.assertEqual(sanitize_csv_value("Regular Name"), "Regular Name")
        self.assertEqual(sanitize_csv_value(""), "")
        self.assertEqual(sanitize_csv_value(None), "")

    async def test_lead_export_fallback_masks_emails_for_free_tier(self):
        """Layer 1: If database query errors, the in-memory fallback STILL masks emails for Free tier."""
        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("Database connection blip")

        mock_in_memory_leads = [
            {
                "id": "lead-1",
                "first_name": "Alice",
                "last_name": "Smith",
                "email": "alice.smith@acme.com",
                "company_name": "Acme Corp"
            }
        ]

        with patch("leads.backend.services.lead_ingestion_service.get_in_memory_leads_for_list", return_value=mock_in_memory_leads):
            res = await export_leads_in_list(
                list_id="list-123",
                workspace_id="ws-free-user",
                supabase=mock_supabase
            )

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["tier"], "FREE")
            self.assertFalse(res["can_export_unmasked"])
            self.assertEqual(len(res["data"]), 1)
            # Crucial verification: Email MUST be masked in fallback!
            self.assertNotEqual(res["data"][0]["email"], "alice.smith@acme.com")
            self.assertIn("***@acme.com", res["data"][0]["email"])

    async def test_lead_export_sanitizes_formula_injection_in_prospect_fields(self):
        """Layer 2: Leads with formula injection in names or company are sanitized in export."""
        mock_supabase = MagicMock()
        # Mock list check
        mock_list_check = MagicMock()
        mock_list_check.execute = AsyncMock(return_value=MagicMock(data={"id": "list-1", "name": "Test List"}))

        # Mock workspace tier (PRO)
        mock_ws_check = MagicMock()
        mock_ws_check.execute = AsyncMock(return_value=MagicMock(data={"tier": "PRO"}))

        # Mock query
        mock_leads_query = MagicMock()
        mock_leads_query.execute = AsyncMock(return_value=MagicMock(data=[
            {
                "id": "lead-x",
                "first_name": "=cmd|' /C calc'!A0",
                "last_name": "+Smith",
                "company_name": "@EvilCorp",
                "email": "victim@evil.com",
                "location": "New York"
            }
        ]))

        call_count = 0
        def fake_table(name):
            nonlocal call_count
            ret = MagicMock()
            if name == "lead_lists":
                ret.select.return_value.eq.return_value.eq.return_value.single.return_value = mock_list_check
            elif name == "workspaces":
                ret.select.return_value.eq.return_value.single.return_value = mock_ws_check
            elif name == "leads":
                ret.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value = mock_leads_query
            return ret

        mock_supabase.table = fake_table

        res = await export_leads_in_list(
            list_id="list-1",
            workspace_id="ws-pro-user",
            supabase=mock_supabase
        )

        data = res["data"][0]
        self.assertEqual(data["first_name"], "'=cmd|' /C calc'!A0")
        self.assertEqual(data["last_name"], "'+Smith")
        self.assertEqual(data["company_name"], "'@EvilCorp")

    def test_social_radar_export_csv_blocks_free_tier(self):
        """Layer 1: Free tier workspace is blocked from social radar CSV export with HTTP 402."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"tier": "FREE"})
        mock_supabase.rpc.return_value = mock_rpc

        with self.assertRaises(HTTPException) as ctx:
            export_social_radar_csv_endpoint(
                workspace_id="ws-free-user",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 402)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"], "FEATURE_TIER_GATED")


if __name__ == "__main__":
    unittest.main()
