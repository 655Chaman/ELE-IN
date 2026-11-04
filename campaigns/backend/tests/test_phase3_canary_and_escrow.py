"""
Phase 3 Verification Suite: Decoupled Proxy Canary & Credit Escrow Rate Limiting
Tests:
1. canary_check_proxy returns healthy when proxy connects to 204 endpoint.
2. canary_check_proxy returns false when proxy fails connection.
3. account_auto_heal_service preserves healthy proxies across account challenges.
4. enrich-batch rejects requests with balance < 5 with 402.
5. enrich-batch rate-limits after 10 batches/min with 429.
"""
import pytest
import time
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from core.backend.services.proxy_routing import canary_check_proxy, quarantine_proxy
from accounts.backend.services.account_auto_heal_service import auto_heal_account
from campaigns.backend.routers.waterfall_enrichment_router import (
    enrich_batch_endpoint,
    EnrichBatchPayload,
    LeadItem,
    _workspace_last_batch_times
)


def test_canary_check_proxy_success():
    """Verify canary_check_proxy succeeds when target endpoint returns 204."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"host": "proxy.example.com", "port": 8080, "username": "u", "password": "p", "protocol": "http"}
    ]

    with patch("urllib.request.build_opener") as mock_opener_builder:
        mock_opener = MagicMock()
        mock_opener_builder.return_value = mock_opener
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_opener.open.return_value.__enter__.return_value = mock_resp

        res = canary_check_proxy(mock_supabase, "prx_123")
        assert res["is_healthy"] is True
        assert res["reason"] == "canary_passed"


def test_canary_check_proxy_failure():
    """Verify canary_check_proxy handles connection timeouts gracefully."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"host": "proxy.example.com", "port": 8080, "username": "u", "password": "p", "protocol": "http"}
    ]

    with patch("urllib.request.build_opener") as mock_opener_builder:
        mock_opener = MagicMock()
        mock_opener_builder.return_value = mock_opener
        mock_opener.open.side_effect = TimeoutError("Connection timed out")

        res = canary_check_proxy(mock_supabase, "prx_123")
        assert res["is_healthy"] is False
        assert "canary_failed" in res["reason"]


def test_auto_heal_preserves_healthy_proxy():
    """Verify auto_heal_account does not quarantine a healthy proxy during an account challenge."""
    from integrations.backend.services.linkedin_worker import SecurityChallengeError

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "id": "acc_1",
            "workspace_id": "ws_1",
            "account_type": "linkedin",
            "status": "ACTIVE",
            "proxy_id": "prx_healthy",
            "session_cookies": "hex_bytes",
            "session_probe_last_error": "checkpoint challenge detected",
            "healing_attempts": 0
        }
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = []
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = []

    with patch("core.backend.core.crypto.decrypt_bytes", return_value=b'{"li_at": "mock"}'):
        with patch("accounts.backend.services.account_auto_heal_service.probe_proxy_health", return_value={"ok": True, "latency_ms": 100, "status": "healthy"}):
            with patch("core.backend.services.proxy_routing.build_authenticated_proxy_url", return_value="http://proxy:8080"):
                with patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker") as mock_worker:
                    mock_worker.return_value._http_get.side_effect = SecurityChallengeError("checkpoint challenge detected")
                    with patch("core.backend.services.proxy_routing.canary_check_proxy", return_value={"is_healthy": True, "reason": "canary_passed"}):
                        with patch("core.backend.services.proxy_routing.quarantine_proxy") as mock_quarantine:
                            res = auto_heal_account(account_id="acc_1", workspace_id="ws_1", supabase=mock_supabase)
                            # Quarantine proxy must NOT have been called!
                            mock_quarantine.assert_not_called()
                            # Actions should confirm proxy was preserved
                            actions = res.get("actions_taken", [])
                            assert any("proxy preserved for fleet" in str(a).lower() for a in actions)


def test_enrich_batch_insufficient_credits():
    """Verify enrich_batch rejects requests when balance < 5 credits with 402."""
    payload = EnrichBatchPayload(leads=[LeadItem(name="Jane Doe", domain="stripe.com")])
    mock_supabase = MagicMock()

    with patch("campaigns.backend.routers.waterfall_enrichment_router.check_tier_access", return_value=True):
        with patch("campaigns.backend.routers.waterfall_enrichment_router.get_credit_balance", return_value=2):
            with pytest.raises(HTTPException) as exc:
                enrich_batch_endpoint(payload, workspace_id="ws_test", supabase=mock_supabase)
            assert exc.value.status_code == 402
            assert "Insufficient credit balance" in exc.value.detail


def test_enrich_batch_rate_limit_exceeded():
    """Verify enrich_batch enforces 10 batches/min limit per workspace."""
    payload = EnrichBatchPayload(leads=[LeadItem(name="Jane Doe", domain="stripe.com")])
    mock_supabase = MagicMock()

    # Pre-populate workspace with 10 recent batch timestamps
    ws_id = "ws_rate_limited"
    now_t = time.time()
    _workspace_last_batch_times[ws_id] = [now_t - i for i in range(10)]

    with patch("campaigns.backend.routers.waterfall_enrichment_router.check_tier_access", return_value=True):
        with pytest.raises(HTTPException) as exc:
            enrich_batch_endpoint(payload, workspace_id=ws_id, supabase=mock_supabase)
        assert exc.value.status_code == 429
        assert "rate limit exceeded" in exc.value.detail
