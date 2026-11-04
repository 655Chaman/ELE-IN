"""
Phase 1 Verification Suite: Anti-Detection, Distributed Redlock & SSRF Attachment Guard
Tests:
1. send_message_with_attachment rejects loopback/internal hosts and relative URLs without PUBLIC_ASSET_BASE_URL.
2. send_message_with_attachment correctly resolves relative paths with configured PUBLIC_ASSET_BASE_URL.
3. BrowserPool distributed lock generates UUID fencing tokens and uses Lua release script.
4. EmailVerifier does not spoof Google domains and respects ENABLE_DIRECT_SMTP_VERIFICATION.
5. EleInNodeExecutor if_connected does not prematurely collapse waiting windows on unparsable timestamps.
6. EleInNodeExecutor find_funding_round handles invalid dates gracefully under recency constraints.
"""
import pytest
import os
import uuid
from unittest.mock import MagicMock, patch
from integrations.backend.services.linkedin_worker import LinkedInWorker
from integrations.backend.services.linkedin_pool import BrowserPool
from integrations.backend.services.email_verifier import EmailVerifier
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch


def test_attachment_rejects_loopback():
    """Verify that send_message_with_attachment refuses to send 127.0.0.1 or localhost links."""
    worker = LinkedInWorker(account_id="acc_test_123", profile_dir="/tmp/test_profile", headless=True)
    
    # Test localhost loopback
    res = worker.send_message_with_attachment(
        profile_url="https://www.linkedin.com/in/test-prospect",
        body="Here is our brochure",
        attachment_url="http://127.0.0.1:8000/uploads/pitch.pdf"
    )
    assert res["status"] == "error"
    assert "Security Guard" in res["error"]
    assert "127.0.0.1" in res["error"]

    # Test localhost hostname
    res2 = worker.send_message_with_attachment(
        profile_url="https://www.linkedin.com/in/test-prospect",
        body="Here is our brochure",
        attachment_url="http://localhost:3000/uploads/pitch.pdf"
    )
    assert res2["status"] == "error"
    assert "Security Guard" in res2["error"]


def test_attachment_relative_without_base_url():
    """Verify relative URL without PUBLIC_ASSET_BASE_URL returns a clear actionable error."""
    worker = LinkedInWorker(account_id="acc_test_123", profile_dir="/tmp/test_profile", headless=True)
    with patch.dict(os.environ, {}, clear=True):
        res = worker.send_message_with_attachment(
            profile_url="https://www.linkedin.com/in/test-prospect",
            body="Review this",
            attachment_url="/api/elein/assets/deck.pdf"
        )
        assert res["status"] == "error"
        assert "PUBLIC_ASSET_BASE_URL is not configured" in res["error"]


def test_attachment_relative_with_base_url():
    """Verify relative URL with PUBLIC_ASSET_BASE_URL resolves to a clean public URL."""
    worker = LinkedInWorker(account_id="acc_test_123", profile_dir="/tmp/test_profile", headless=True)
    with patch.dict(os.environ, {"PUBLIC_ASSET_BASE_URL": "https://cdn.elein.ai"}):
        with patch.object(worker, "_get_or_create_context") as mock_ctx:
            mock_page = MagicMock()
            mock_ctx.return_value.__enter__.return_value = mock_page
            mock_page.locator.return_value.first.is_visible.return_value = True
            
            with patch.object(worker, "_safe_click", return_value=True):
                with patch.object(worker, "_human_delay"):
                    with patch.object(worker, "_human_type"):
                        res = worker.send_message_with_attachment(
                            profile_url="https://www.linkedin.com/in/test-prospect",
                            body="Here is the deck",
                            attachment_url="/api/elein/assets/deck.pdf"
                        )
                        assert res["status"] == "success"
                        # Verify the typed message contained the public CDN url
                        typed_text = worker._human_type.call_args[0][2]
                        assert "https://cdn.elein.ai/api/elein/assets/deck.pdf" in typed_text
                        assert "127.0.0.1" not in typed_text


def test_browser_pool_redlock_fencing_token():
    """Verify BrowserPool generates UUID fencing token and uses Lua script on release."""
    pool = BrowserPool(max_size=2)
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_context.new_page.return_value = mock_page

    with patch("integrations.backend.services.linkedin_pool._get_redis_client", return_value=mock_redis):
        with patch("integrations.backend.services.linkedin_pool.sync_playwright") as mock_pw_cls:
            mock_pw_inst = MagicMock()
            mock_pw_cls.return_value.start.return_value = mock_pw_inst
            
            # Acquire
            pool.acquire("acc_123", setup_func=lambda p: (mock_browser, mock_context))
            
            # Verify redis.set called with NX, PX and a valid UUID token
            assert mock_redis.set.called
            call_args = mock_redis.set.call_args
            lock_key = call_args[0][0]
            token = call_args[0][1]
            assert lock_key == "lock:linkedin:account:acc_123"
            # Validate that token is a valid UUID
            parsed_uuid = uuid.UUID(token)
            assert str(parsed_uuid) == token
            assert pool.active_lock_tokens.get("acc_123") == token

            # Release
            pool.release("acc_123")
            
            # Verify redis.eval called with Lua script and the exact fencing token
            assert mock_redis.eval.called
            eval_args = mock_redis.eval.call_args[0]
            lua_script = eval_args[0]
            assert "redis.call(\"get\", KEYS[1]) == ARGV[1]" in lua_script
            assert eval_args[2] == "lock:linkedin:account:acc_123"
            assert eval_args[3] == token
            assert "acc_123" not in pool.active_lock_tokens


def test_email_verifier_no_spoofing():
    """Verify EmailVerifier does not spoof Google and respects ENABLE_DIRECT_SMTP_VERIFICATION."""
    # When disabled, returns False immediately without touching network
    with patch.dict(os.environ, {"ENABLE_DIRECT_SMTP_VERIFICATION": "false"}):
        assert EmailVerifier.verify_email_smtp("test@example.com", "mx.example.com") is False

    # When enabled, does NOT use mail.google.com
    with patch.dict(os.environ, {"ENABLE_DIRECT_SMTP_VERIFICATION": "true", "SMTP_HELO_HOST": "mail.elein.ai"}):
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
            mock_smtp.rcpt.return_value = (250, b"OK")
            
            res = EmailVerifier.verify_email_smtp("test@example.com", "mx.example.com")
            assert res is True
            # Verify HELO used mail.elein.ai, NOT mail.google.com
            mock_smtp.helo.assert_called_with("mail.elein.ai")
            mock_smtp.mail.assert_called_with("<verify@mail.elein.ai>")


def test_if_connected_unparsable_date_resilience():
    """Verify if_connected resets evaluation window instead of prematurely collapsing to NOT_CONNECTED."""
    executor = EleInNodeExecutor(worker=None, supabase=None, workspace_id="ws_1")
    data = {
        "timeout_days": 2,
        "_current_node_id": "node_1",
        "variables": {
            "condition_started_at_node_1": "INVALID_CORRUPT_TIMESTAMP"
        }
    }
    
    res = executor.handle_if_connected(data, "https://www.linkedin.com/in/prospect")
    # Must be waiting, NOT immediately NOT_CONNECTED!
    assert res["status"] == "waiting"
    assert "Waiting for connection acceptance" in res["message"]


def test_find_funding_round_invalid_date():
    """Verify find_funding_round with recency constraint handles unparsable date without false positive."""
    executor = EleInNodeExecutor(worker=None, supabase=None, workspace_id="ws_1")
    data = {
        "funding_round": "Series A",
        "recency_months": 6,
        "funding_date": "INVALID_DATE_FORMAT"
    }
    res = executor.handle_find_funding_round(data, "https://www.linkedin.com/in/prospect")
    assert res["status"] == "success"
    # Should not blindly claim recently funded when date is corrupt
    assert res["branch"] == Branch.NO_RECENT_FUNDING.value
