import pytest
import os
import json
import hashlib
from unittest.mock import MagicMock, patch

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

from fastapi import HTTPException
from integrations.backend.routers.extension import (
    verify_extension_api_key,
    sync_cookies,
    ExtensionSyncPayload
)

class TestExtensionSync:
    """
    Three-Layer Paranoia Test Suite for Chrome Extension Synchronization
    """

    def test_verify_extension_api_key_valid(self):
        """Layer 0: Valid active API key resolves to workspace_id."""
        mock_sb = MagicMock()
        raw_key = "test_ext_key_123"
        hashed = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        mock_select = MagicMock()
        mock_select.eq.return_value.execute.return_value.data = [{"workspace_id": "ws_alpha", "is_active": True}]
        mock_sb.table.return_value.select.return_value = mock_select

        mock_update = MagicMock()
        mock_update.eq.return_value.execute.return_value.data = []
        mock_sb.table.return_value.update.return_value = mock_update

        ws_id = verify_extension_api_key(x_api_key=raw_key, supabase=mock_sb)
        assert ws_id == "ws_alpha"

    def test_verify_extension_api_key_inactive_or_missing(self):
        """Layer 1: Inactive or revoked API key raises 401."""
        mock_sb = MagicMock()
        raw_key = "revoked_key"

        mock_select = MagicMock()
        mock_select.eq.return_value.execute.return_value.data = [{"workspace_id": "ws_alpha", "is_active": False}]
        mock_sb.table.return_value.select.return_value = mock_select

        with pytest.raises(HTTPException) as exc:
            verify_extension_api_key(x_api_key=raw_key, supabase=mock_sb)
        assert exc.value.status_code == 401

    def test_sync_cookies_missing_li_at_fails(self):
        """Layer 2: Reject cookie payload without essential li_at session token."""
        mock_sb = MagicMock()
        cookies = [{"name": "JSESSIONID", "value": "ajax:12345", "domain": ".linkedin.com"}]
        payload = ExtensionSyncPayload(
            account_name="Test Sender",
            cookies_json=json.dumps(cookies)
        )

        with pytest.raises(HTTPException) as exc:
            sync_cookies(payload=payload, workspace_id="ws_alpha", supabase=mock_sb)
        assert exc.value.status_code == 400
        assert "li_at cookie missing" in exc.value.detail

    def test_sync_cookies_malformed_json_fails(self):
        """Layer 1: Malformed JSON payload fails safely with 400."""
        mock_sb = MagicMock()
        payload = ExtensionSyncPayload(
            account_name="Test Sender",
            cookies_json="this-is-not-valid-json"
        )

        with pytest.raises(HTTPException) as exc:
            sync_cookies(payload=payload, workspace_id="ws_alpha", supabase=mock_sb)
        assert exc.value.status_code == 400
        assert "Invalid cookies payload" in exc.value.detail

    def test_sync_cookies_unauthorized_account_fails(self):
        """Layer 2 (IDOR Prevention): Specifying an account_id belonging to another workspace fails with 403."""
        mock_sb = MagicMock()
        cookies = [{"name": "li_at", "value": "AQEDA...", "domain": ".linkedin.com"}]
        payload = ExtensionSyncPayload(
            account_id="acc_alien",
            cookies_json=json.dumps(cookies)
        )

        # Mock account check query returning empty (account does not belong to ws_alpha)
        mock_acc_check = MagicMock()
        mock_acc_check.eq.return_value.eq.return_value.execute.return_value.data = []
        mock_sb.table.return_value.select.return_value = mock_acc_check

        with pytest.raises(HTTPException) as exc:
            sync_cookies(payload=payload, workspace_id="ws_alpha", supabase=mock_sb)
        assert exc.value.status_code == 403
        assert "Account does not belong to your workspace" in exc.value.detail

    def test_sync_cookies_success_inserts_account(self):
        """Layer 0: Valid cookies for a new account successfully create and encrypt account."""
        mock_sb = MagicMock()
        cookies = [
            {"name": "li_at", "value": "AQEDA1234567890", "domain": ".linkedin.com"},
            {"name": "JSESSIONID", "value": "ajax:999", "domain": ".linkedin.com"}
        ]
        payload = ExtensionSyncPayload(
            account_name="VP Outreach",
            cookies_json=json.dumps(cookies)
        )

        # Mock no disconnected accounts found
        mock_exist = MagicMock()
        mock_exist.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_sb.table.return_value.select.return_value = mock_exist

        # Mock insert
        mock_insert = MagicMock()
        mock_insert.execute.return_value.data = [{"id": "new_acc_uuid"}]
        mock_sb.table.return_value.insert.return_value = mock_insert

        res = sync_cookies(payload=payload, workspace_id="ws_alpha", supabase=mock_sb)
        assert res["status"] == "ok"
        assert res["account_id"] is not None
        assert "successfully synced and encrypted" in res["message"]
