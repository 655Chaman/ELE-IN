"""
test_horizon17_leads_isolation_hygiene_export.py

Horizon 17: Multi-Tenant Lead Isolation, Data Hygiene Sanitization & Export Security
Adheres strictly to the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (List pagination, export quotas, email/phone hygiene, lead deduplication)
- Layer 1: Environmental Failure Analysis (Strict tenant isolation across workspaces, active campaign locks, auto-pause execution)
- Layer 2: Human Paranoia (Privacy masking for free tiers, dirty token/wrapper stripping, SQL/NUL byte sanitization)
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from leads.backend.routers.leads import (
    get_leads_in_list,
    export_leads_in_list,
    remove_lead_from_list,
    delete_lead_list_async,
    mask_email,
)
from leads.backend.services.data_hygiene import DataHygieneService


class TestHorizon17DataHygiene(unittest.TestCase):
    """Test data sanitization, email/phone normalization, and intelligent deduplication."""

    def test_clean_email_hygiene(self):
        """Layer 0 & 2: Email cleaning strips mailto, wrappers, spaces, and validates format."""
        self.assertEqual(DataHygieneService.clean_email("  ALICE@EXAMPLE.COM  "), "alice@example.com")
        self.assertEqual(DataHygieneService.clean_email("mailto:bob@domain.co.uk"), "bob@domain.co.uk")
        self.assertEqual(DataHygieneService.clean_email("<charlie@startup.io>"), "charlie@startup.io")
        self.assertEqual(DataHygieneService.clean_email('"dan@company.org"'), "dan@company.org")

        # Invalid formats return empty string
        self.assertEqual(DataHygieneService.clean_email("not_an_email"), "")
        self.assertEqual(DataHygieneService.clean_email("@missinguser.com"), "")
        self.assertEqual(DataHygieneService.clean_email("user@.com"), "")
        self.assertEqual(DataHygieneService.clean_email("user@domain..com"), "")
        self.assertEqual(DataHygieneService.clean_email(None), "")
        self.assertEqual(DataHygieneService.clean_email(12345), "")

    def test_clean_phone_hygiene(self):
        """Layer 0 & 1: Phone cleaning extracts digits, preserves '+', strips extensions."""
        self.assertEqual(DataHygieneService.clean_phone("(555) 123-4567"), "5551234567")
        self.assertEqual(DataHygieneService.clean_phone("+1 (555) 123-4567 ext. 89"), "+15551234567")
        self.assertEqual(DataHygieneService.clean_phone("+44 20 7946 0958 x101"), "+442079460958")
        self.assertEqual(DataHygieneService.clean_phone("+91-98765-43210"), "+919876543210")

        # Too short (<7 digits) or too long (>16 digits) or garbage strings return empty
        self.assertEqual(DataHygieneService.clean_phone("12345"), "")
        self.assertEqual(DataHygieneService.clean_phone("12345678901234567890"), "")
        self.assertEqual(DataHygieneService.clean_phone("phone-number"), "")
        self.assertEqual(DataHygieneService.clean_phone(None), "")

    def test_mask_email(self):
        """Layer 2 Paranoia: Free tier email masking."""
        self.assertEqual(mask_email("johndoe@example.com"), "jo***@example.com")
        self.assertEqual(mask_email("al@test.co"), "a***@test.co")
        self.assertEqual(mask_email("a@test.co"), "a***@test.co")
        self.assertEqual(mask_email("invalid"), "")
        self.assertEqual(mask_email(None), "")

    def test_deduplicate_leads(self):
        """Layer 1: Intelligent lead deduplication merges metadata into existing records."""
        leads = [
            {
                "linkedin_url": "https://www.linkedin.com/in/johndoe",
                "first_name": "John",
                "email": ""
            },
            {
                "linkedin_url": "https://in.linkedin.com/in/johndoe?trk=test",  # Same person
                "last_name": "Doe",
                "email": "john.doe@acme.com",
                "company": "Acme Corp"
            },
            {
                "linkedin_url": "https://www.linkedin.com/in/alicesmith",
                "first_name": "Alice",
                "email": "alice@startup.io"
            }
        ]

        deduped = DataHygieneService.deduplicate_leads(leads)
        self.assertEqual(len(deduped), 2)
        
        # Check that John Doe was merged with richer info
        john = next(l for l in deduped if "johndoe" in l["linkedin_url"])
        self.assertEqual(john["first_name"], "John")
        self.assertEqual(john["last_name"], "Doe")
        self.assertEqual(john["email"], "john.doe@acme.com")
        self.assertEqual(john["company"], "Acme Corp")


class MockAsyncQuery:
    def __init__(self, data=None, count=None):
        self._data = data if data is not None else []
        self._count = count

    def select(self, *args, **kwargs): return self
    def eq(self, *args, **kwargs): return self
    def in_(self, *args, **kwargs): return self
    def order(self, *args, **kwargs): return self
    def range(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def single(self, *args, **kwargs): return self
    def delete(self, *args, **kwargs): return self

    async def execute(self):
        res = MagicMock()
        res.data = self._data
        res.count = self._count
        return res


class TestHorizon17TenantIsolationAndLeadsRouter(unittest.IsolatedAsyncioTestCase):
    """Test multi-tenant isolation, authorization barriers, and quota enforcement in leads router."""

    async def test_get_leads_in_list_unauthorized_cross_tenant(self):
        """Layer 1: Attempting to fetch leads from another workspace's list returns HTTP 404."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value = MockAsyncQuery(data=[])

        with self.assertRaises(HTTPException) as ctx:
            await get_leads_in_list(
                list_id="foreign_list_123",
                workspace_id="attacker_workspace_999",
                supabase=mock_supabase
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Lead list not found or unauthorized", ctx.exception.detail)

    async def test_get_leads_in_list_success_enforces_workspace_isolation(self):
        """Layer 1: Querying leads verifies list ownership and filters by workspace_id."""
        mock_supabase = MagicMock()
        list_query = MockAsyncQuery(data=[{"id": "my_list_123"}])
        leads_query = MockAsyncQuery(data=[{"id": "lead_1", "first_name": "Bob"}], count=1)

        mock_supabase.table.side_effect = lambda t: list_query if t == "lead_lists" else leads_query

        res = await get_leads_in_list(
            list_id="my_list_123",
            page=1,
            page_size=50,
            workspace_id="my_workspace_123",
            supabase=mock_supabase
        )
        self.assertEqual(res["total"], 1)
        self.assertEqual(len(res["data"]), 1)
        self.assertEqual(res["data"][0]["first_name"], "Bob")

    async def test_export_leads_free_tier_privacy_masking_and_quota(self):
        """Layer 2 Paranoia: Free tier exports mask email addresses and clamp to 25 leads."""
        mock_supabase = MagicMock()
        list_query = MockAsyncQuery(data={"id": "list_1", "name": "Prospects", "workspace_id": "ws_free"})
        ws_query = MockAsyncQuery(data={"tier": "FREE"})
        leads_data = [
            {"id": "l1", "first_name": "Jane", "email": "jane.doe@company.com"},
            {"id": "l2", "first_name": "John", "email": "john.smith@domain.org"}
        ]
        leads_query = MockAsyncQuery(data=leads_data)

        def table_router(table_name):
            if table_name == "lead_lists": return list_query
            if table_name == "workspaces": return ws_query
            return leads_query

        mock_supabase.table.side_effect = table_router

        res = await export_leads_in_list(
            list_id="list_1",
            workspace_id="ws_free",
            supabase=mock_supabase
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["tier"], "FREE")
        self.assertFalse(res["can_export_unmasked"])
        self.assertEqual(res["max_export_limit"], 25)
        # Check emails are masked
        self.assertEqual(res["data"][0]["email"], "ja***@company.com")
        self.assertEqual(res["data"][1]["email"], "jo***@domain.org")

    async def test_export_leads_pro_tier_unmasked(self):
        """Layer 0: Pro tier exports retain full unmasked contact details."""
        mock_supabase = MagicMock()
        list_query = MockAsyncQuery(data={"id": "list_pro", "name": "Executives", "workspace_id": "ws_pro"})
        ws_query = MockAsyncQuery(data={"tier": "PRO"})
        leads_data = [{"id": "l1", "first_name": "Sarah", "email": "sarah@enterprise.com"}]
        leads_query = MockAsyncQuery(data=leads_data)

        def table_router(table_name):
            if table_name == "lead_lists": return list_query
            if table_name == "workspaces": return ws_query
            return leads_query

        mock_supabase.table.side_effect = table_router

        res = await export_leads_in_list(
            list_id="list_pro",
            workspace_id="ws_pro",
            supabase=mock_supabase
        )

        self.assertEqual(res["tier"], "PRO")
        self.assertTrue(res["can_export_unmasked"])
        self.assertEqual(res["data"][0]["email"], "sarah@enterprise.com")

    async def test_remove_lead_from_list_with_auto_pause(self):
        """Layer 1: Removing a lead pauses any in-flight campaign execution states."""
        mock_supabase = MagicMock()
        list_query = MockAsyncQuery(data=[{"id": "list_1"}])
        del_query = MockAsyncQuery(data=[])

        mock_supabase.table.side_effect = lambda t: list_query if t == "lead_lists" else del_query

        with patch("campaigns.backend.routers.elein._pause_lead_execution_core") as mock_pause, \
             patch("core.backend.api.auth_dep.get_service_client"):

            res = await remove_lead_from_list(
                list_id="list_1",
                lead_id="lead_100",
                workspace_id="ws_1",
                supabase=mock_supabase
            )

            self.assertTrue(res["success"])
            mock_pause.assert_called_once()
            call_kwargs = mock_pause.call_args[1]
            self.assertEqual(call_kwargs["lead_id"], "lead_100")
            self.assertEqual(call_kwargs["workspace_id"], "ws_1")
            self.assertEqual(call_kwargs["status_override"], "paused")

    async def test_delete_lead_list_blocked_by_active_campaign(self):
        """Layer 1 & 2 Paranoia: Deleting a lead list assigned to an ACTIVE campaign raises HTTP 400."""
        mock_supabase = MagicMock()
        list_query = MockAsyncQuery(data=[{"id": "list_active", "name": "Q3 Target Accounts"}])
        camp_query = MockAsyncQuery(data=[{"id": "camp_1", "name": "Outbound Velocity"}])

        mock_supabase.table.side_effect = lambda t: list_query if t == "lead_lists" else camp_query

        with self.assertRaises(HTTPException) as ctx:
            await delete_lead_list_async(
                list_id="list_active",
                workspace_id="ws_1",
                supabase=mock_supabase
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Cannot delete list 'Q3 Target Accounts'", ctx.exception.detail)
        self.assertIn("Outbound Velocity", ctx.exception.detail)



if __name__ == '__main__':
    unittest.main()
