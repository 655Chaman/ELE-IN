"""
Stage 29: Accounts Subsystem Paranoia Hardening Tests
Verifies:
1. Active campaign deletion guard (409 Conflict when account is in active campaign without force=True)
2. SSRF and private-IP defense on proxy_url in /accounts/validate
3. Fail-closed proxy requirement on account addition (no naked datacenter IP fallback)
4. Ghost-column removal and daily action counts aggregation
5. HTTP 999 / 403 anti-bot detection in proxy health probes
"""
import unittest
from unittest.mock import MagicMock, patch
import json
from fastapi import HTTPException
from campaigns.backend.routers.elein import (
    delete_account,
    update_account,
    get_accounts,
    get_account_actions_today,
    validate_cookies,
    add_account,
    toggle_account_warmup,
    ToggleWarmupPayload,
)
from campaigns.backend.schemas.elein import AccountUpdate
from accounts.backend.services.account_auto_heal_service import probe_proxy_health


class TestStage29AccountsParanoiaHardening(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws-test-123"
        self.account_id = "acc-test-456"

    def test_layer0_delete_account_blocks_active_campaign_without_force(self):
        """Layer 0 & 2: Active campaign deletion guard returns 409 Conflict unless force=True."""
        mock_supabase = MagicMock()
        
        # Account exists
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {"id": self.account_id, "name": "Alex Vance"}
        ]
        
        # Campaign is active and contains account_id in sender_account_ids_json
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {
                "id": "camp-active-1",
                "name": "Q4 Enterprise Outreach",
                "status": "ACTIVE",
                "sender_account_ids_json": [self.account_id, "acc-other-999"]
            }
        ]

        with self.assertRaises(HTTPException) as ctx:
            delete_account(
                account_id=self.account_id,
                force=False,
                supabase=mock_supabase,
                workspace_id=self.workspace_id
            )
        
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("Q4 Enterprise Outreach", str(ctx.exception.detail))
        self.assertIn("assigned to active campaign", str(ctx.exception.detail))

    def test_layer1_delete_account_with_force_cleans_campaign_senders_and_deletes(self):
        """Layer 1: Deleting with force=True removes sender from active campaign and cascades."""
        mock_supabase = MagicMock()
        
        # Account exists
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {"id": self.account_id, "name": "Alex Vance"}
        ]
        
        # Campaign is active
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {
                "id": "camp-active-1",
                "name": "Q4 Enterprise Outreach",
                "status": "ACTIVE",
                "sender_account_ids_json": [self.account_id, "acc-other-999"]
            }
        ]

        with patch("campaigns.backend.routers.elein.get_service_client", return_value=mock_supabase):
            res = delete_account(
                account_id=self.account_id,
                force=True,
                supabase=mock_supabase,
                workspace_id=self.workspace_id
            )
            
        self.assertEqual(res["status"], "deleted")
        self.assertEqual(res["account_id"], self.account_id)

    def test_layer2_validate_cookies_rejects_ssrf_proxy_urls(self):
        """Layer 2 (Human Paranoia & Security): Rejects private IPs and metadata services in proxy_url."""
        # 1. AWS Cloud Metadata
        with self.assertRaises(HTTPException) as ctx:
            validate_cookies(
                payload={
                    "session_cookies_json": json.dumps([{"name": "li_at", "value": "test_val"}]),
                    "proxy_url": "http://169.254.169.254:80"
                },
                workspace_id=self.workspace_id
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("rejected by security policy", str(ctx.exception.detail))

        # 2. Localhost
        with self.assertRaises(HTTPException) as ctx:
            validate_cookies(
                payload={
                    "session_cookies_json": json.dumps([{"name": "li_at", "value": "test_val"}]),
                    "proxy_url": "http://127.0.0.1:8000"
                },
                workspace_id=self.workspace_id
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # 3. Disallowed scheme
        with self.assertRaises(HTTPException) as ctx:
            validate_cookies(
                payload={
                    "session_cookies_json": json.dumps([{"name": "li_at", "value": "test_val"}]),
                    "proxy_url": "ftp://proxy.example.com:21"
                },
                workspace_id=self.workspace_id
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_layer1_fail_closed_proxy_on_add_account(self):
        """Layer 1: add_account raises 422 if no healthy residential proxy is available."""
        mock_supabase = MagicMock()
        
        # Workspace tier check and count check
        mock_count_res = MagicMock()
        mock_count_res.count = 0
        mock_count_res.data = []
        mock_supabase.table().select().eq().execute.return_value = mock_count_res

        # No healthy proxies in workspace or system pool
        mock_supabase.table().select().eq().eq().execute.return_value.data = []
        mock_supabase.table().select().eq().is_().execute.return_value.data = []

        # Account payload mock
        account_mock = MagicMock()
        account_mock.session_cookies_json = json.dumps([{"name": "li_at", "value": "val123"}])
        account_mock.proxy_id = None
        account_mock.proxy = None
        account_mock.proxy_url = None
        account_mock.linkedin_profile_url = "https://linkedin.com/in/alex"
        account_mock.name = "Alex Vance"
        account_mock.is_warmup = True

        mock_request = MagicMock()

        with patch("campaigns.backend.routers.elein.get_service_client", return_value=mock_supabase):
            with self.assertRaises(HTTPException) as ctx:
                add_account(
                    account=account_mock,
                    request=mock_request,
                    supabase=mock_supabase,
                    workspace_id=self.workspace_id,
                    user_id="user-123"
                )
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertIn("No healthy residential proxies available", str(ctx.exception.detail))

    def test_layer0_auto_string_proxy_id_normalizes_to_auto_assignment(self):
        """Layer 0 & 2: proxy_id='auto' normalizes to automatic assignment instead of 404 query."""
        mock_supabase = MagicMock()
        
        # Workspace tier check and count check
        mock_count_res = MagicMock()
        mock_count_res.count = 0
        mock_count_res.data = []
        mock_supabase.table().select().eq().execute.return_value = mock_count_res

        # Healthy proxy found in pool
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {"id": "proxy-auto-assigned", "country_code": "US", "workspace_id": self.workspace_id}
        ]
        mock_supabase.table().select().eq().is_().execute.return_value.data = []
        mock_supabase.rpc().execute.return_value.data = "secret-ref-123"

        # Account payload mock with proxy_id="auto"
        account_mock = MagicMock()
        account_mock.session_cookies_json = json.dumps([{"name": "li_at", "value": "val123"}])
        account_mock.proxy_id = "auto"
        account_mock.proxy = None
        account_mock.proxy_url = None
        account_mock.linkedin_profile_url = "https://linkedin.com/in/alex"
        account_mock.name = "Alex Vance"
        account_mock.is_warmup = False

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "US"

        with patch("campaigns.backend.routers.elein.get_service_client", return_value=mock_supabase), \
             patch("core.backend.core.crypto.generate_dek", return_value="bW9jay1kZWstYnl0ZXM="), \
             patch("core.backend.core.crypto.encrypt_bytes", return_value=b"encrypted"):
            res = add_account(
                account=account_mock,
                request=mock_request,
                supabase=mock_supabase,
                workspace_id=self.workspace_id,
                user_id="user-123"
            )
            self.assertEqual(res["status"], "success")
            account_insert_payload = [c[0][0] for c in mock_supabase.table().insert.call_args_list if "proxy_id" in c[0][0]][0]
            self.assertEqual(account_insert_payload["proxy_id"], "proxy-auto-assigned")

    def test_layer0_get_account_actions_today_aggregates_cleanly(self):
        """Layer 0: Safely aggregates counts from account_daily_action_counts without ghost columns."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {"count": 12},
            {"count": 8},
            {"count": 5}
        ]

        total = get_account_actions_today(mock_supabase, self.account_id, "2026-10-22")
        self.assertEqual(total, 25)

    def test_layer1_probe_proxy_health_treats_http_999_as_banned(self):
        """Layer 1: Proxy probe recognizes HTTP 999 (Anti-bot challenge) as banned, not healthy."""
        mock_proxy = {
            "id": "proxy-123",
            "host": "198.51.100.25",
            "port": 8080,
            "protocol": "http",
            "workspace_id": self.workspace_id
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 999

        with patch("httpx.Client.get", return_value=mock_resp):
            res = probe_proxy_health(mock_proxy)
            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "banned")
            self.assertIn("Anti-Bot Challenge", res["error"])


    def test_layer0_toggle_account_warmup_success(self):
        """Layer 0 & 1: Toggles warmup flag on account and initializes warmup_start_date when missing."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {"id": self.account_id, "warmup_start_date": None}
        ]

        payload = ToggleWarmupPayload(is_warmup=True)
        res = toggle_account_warmup(
            account_id=self.account_id,
            payload=payload,
            supabase=mock_supabase,
            workspace_id=self.workspace_id
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["account_id"], self.account_id)
        self.assertTrue(res["is_warmup"])

        # Verify update was called with is_warmup=True and warmup_start_date set
        update_call = mock_supabase.table().update.call_args[0][0]
        self.assertTrue(update_call["is_warmup"])
        self.assertIn("warmup_start_date", update_call)

    def test_layer2_toggle_account_warmup_not_found(self):
        """Layer 2: Rejects toggle request for account outside tenant workspace."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value.data = []

        payload = ToggleWarmupPayload(is_warmup=False)
        with self.assertRaises(HTTPException) as ctx:
            toggle_account_warmup(
                account_id=self.account_id,
                payload=payload,
                supabase=mock_supabase,
                workspace_id=self.workspace_id
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_layer0_update_account_settings_success(self):
        """Layer 0: Successfully updates name, limits, and valid proxy."""
        mock_supabase = MagicMock()
        # Mock account exists
        mock_supabase.table().select().eq().eq().execute.side_effect = [
            # Check ownership
            MagicMock(data=[{"id": self.account_id, "name": "Old Name", "proxy_id": None}]),
            # Check proxy
            MagicMock(data=[{"id": "proxy-123"}]),
            # Re-fetch updated account
            MagicMock(data=[{
                "id": self.account_id,
                "name": "Jane Doe",
                "daily_connection_limit": 30,
                "daily_message_limit": 60,
                "proxy_id": "proxy-123",
                "session_cookies_encrypted": b"test_enc"
            }])
        ]

        payload = AccountUpdate(
            name="Jane Doe",
            daily_connection_limit=30,
            daily_message_limit=60,
            proxy_id="proxy-123"
        )
        res = update_account(
            account_id=self.account_id,
            payload=payload,
            supabase=mock_supabase,
            workspace_id=self.workspace_id
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["account"]["name"], "Jane Doe")
        self.assertEqual(res["account"]["daily_connection_limit"], 30)
        self.assertTrue(res["account"]["has_valid_session"])
        self.assertNotIn("session_cookies_encrypted", res["account"])

    def test_layer1_update_account_normalizes_auto_proxy_to_none(self):
        """Layer 1: Normalizes auto/none/empty proxy to None."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.side_effect = [
            MagicMock(data=[{"id": self.account_id, "name": "Old Name", "proxy_id": "proxy-old"}]),
            MagicMock(data=[{
                "id": self.account_id,
                "name": "Old Name",
                "proxy_id": None
            }])
        ]

        payload = AccountUpdate(proxy_id="auto")
        res = update_account(
            account_id=self.account_id,
            payload=payload,
            supabase=mock_supabase,
            workspace_id=self.workspace_id
        )

        update_call = mock_supabase.table().update.call_args[0][0]
        self.assertIsNone(update_call["proxy_id"])

    def test_layer1_update_account_rejects_foreign_proxy(self):
        """Layer 1: Rejects proxy not belonging to current workspace."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.side_effect = [
            MagicMock(data=[{"id": self.account_id, "name": "Old Name"}]),
            MagicMock(data=[])  # Proxy not found
        ]

        payload = AccountUpdate(proxy_id="foreign-proxy-999")
        with self.assertRaises(HTTPException) as ctx:
            update_account(
                account_id=self.account_id,
                payload=payload,
                supabase=mock_supabase,
                workspace_id=self.workspace_id
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("not exist or belong to this workspace", str(ctx.exception.detail))

    def test_layer2_update_account_rejects_empty_name(self):
        """Layer 2 (Human Paranoia): Rejects blank account name."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value.data = [
            {"id": self.account_id, "name": "Current"}
        ]

        payload = AccountUpdate(name="   ")
        with self.assertRaises(HTTPException) as ctx:
            update_account(
                account_id=self.account_id,
                payload=payload,
                supabase=mock_supabase,
                workspace_id=self.workspace_id
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", str(ctx.exception.detail))

    def test_layer0_get_accounts_aggregates_tags_in_single_query(self):
        """Layer 0: Batch-fetches and aggregates tags for all accounts in workspace."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().order().execute.return_value = MagicMock(data=[
            {"id": "acc-1", "name": "Alice", "session_cookies_encrypted": b"raw_1"},
            {"id": "acc-2", "name": "Bob", "session_cookies_encrypted": None}
        ])
        mock_supabase.table().select().in_().execute.return_value = MagicMock(data=[
            {"account_id": "acc-1", "tag": "EMEA"},
            {"account_id": "acc-1", "tag": "Tier1"},
            {"account_id": "acc-2", "tag": "US"}
        ])

        rows = get_accounts(supabase=mock_supabase, workspace_id=self.workspace_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["tags"], ["EMEA", "Tier1"])
        self.assertTrue(rows[0]["has_valid_session"])
        self.assertEqual(rows[1]["tags"], ["US"])
        self.assertFalse(rows[1]["has_valid_session"])

    def test_layer1_get_accounts_tag_query_failure_gracefully_degrades(self):
        """Layer 1: Gracefully degrades to empty tags if account_tags query throws error."""
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().order().execute.return_value = MagicMock(data=[
            {"id": "acc-1", "name": "Alice", "session_cookies_encrypted": b"raw_1"}
        ])
        # account_tags query fails
        mock_supabase.table().select().in_().execute.side_effect = Exception("DB Connection Timeout")

        rows = get_accounts(supabase=mock_supabase, workspace_id=self.workspace_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tags"], [])


if __name__ == "__main__":
    unittest.main()
