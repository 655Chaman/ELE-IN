import os
import time
import json
import hmac
import hashlib
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from fastapi import HTTPException

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

from integrations.backend.services.webhook_service import (
    SUPPORTED_WEBHOOK_EVENTS,
    sanitize_webhook_payload,
    generate_webhook_signature,
    emit_webhook_event,
    test_webhook_endpoint as run_test_webhook_endpoint
)
from integrations.backend.routers.webhooks import (
    create_webhook,
    list_webhooks,
    update_webhook,
    delete_webhook,
    test_webhook as api_test_webhook,
    get_supported_events,
    get_webhook_deliveries,
    CreateWebhookRequest,
    UpdateWebhookRequest
)


def test_get_supported_events_catalog():
    """Layer 0: get_supported_events returns full catalog with all expected core events."""
    res = get_supported_events()
    assert res["status"] == "success"
    events = res["events"]
    assert "lead.connected" in events
    assert "lead.email_discovered" in events
    assert "lead.meeting_booked" in events
    assert "lead.enrolled" in events
    assert "message.sent" in events
    assert "test.ping" in events


def test_sanitize_webhook_payload_strips_sensitive_data():
    """Layer 2 Paranoia: Recursively purges credentials and secrets from webhook payloads."""
    dirty_payload = {
        "lead_id": "lead-123",
        "email": "sarah@acme.com",
        "password": "super-secret-password",
        "api_key": "elein_live_sk9999",
        "nested": {
            "token": "bearer_xxx",
            "access_token": "oauth_yyy",
            "campaign_name": "Q4 Enterprise Outreach",
            "signing_secret": "whsec_123"
        },
        "tags": ["vip", "decision-maker"]
    }
    cleaned = sanitize_webhook_payload(dirty_payload)
    assert cleaned["lead_id"] == "lead-123"
    assert cleaned["email"] == "sarah@acme.com"
    assert "password" not in cleaned
    assert "api_key" not in cleaned
    assert "token" not in cleaned["nested"]
    assert "access_token" not in cleaned["nested"]
    assert "signing_secret" not in cleaned["nested"]
    assert cleaned["nested"]["campaign_name"] == "Q4 Enterprise Outreach"
    assert cleaned["tags"] == ["vip", "decision-maker"]


def test_generate_webhook_signature_hmac_sha256():
    """Layer 0 & 1: Deterministic HMAC-SHA256 signature verification."""
    secret = "whsec_test_secret_12345678"
    payload = {"event": "lead.connected", "lead_id": "123"}
    ts = 1700000000

    timestamp, signature = generate_webhook_signature(payload, secret, timestamp_override=ts)
    assert timestamp == "1700000000"

    expected_signed = f"1700000000.{json.dumps(payload, separators=(',', ':'))}"
    expected_sig = hmac.new(secret.encode(), expected_signed.encode(), hashlib.sha256).hexdigest()
    assert signature == expected_sig


def test_create_webhook_free_tier_rejected():
    """Layer 1 Paranoia: Free tier workspaces cannot create custom webhooks."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "ws-free", "tier": "FREE"}]
    )

    req = CreateWebhookRequest(url="https://api.acme.com/hooks/elein", event_types=["lead.connected"])
    with pytest.raises(HTTPException) as exc_info:
        create_webhook(req=req, workspace_id="ws-free", supabase=mock_supabase)

    assert exc_info.value.status_code == 403
    assert "Growth Pro" in exc_info.value.detail


def test_create_webhook_ssrf_prohibited():
    """Layer 1 Paranoia: Internal IP and loopback addresses trigger SSRF block."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "ws-pro", "tier": "PRO"}]
    )
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        count=0, data=[]
    )

    # Localhost SSRF
    req1 = CreateWebhookRequest(url="http://127.0.0.1:8000/internal/admin", event_types=["*"])
    with pytest.raises(HTTPException) as exc1:
        create_webhook(req=req1, workspace_id="ws-pro", supabase=mock_supabase)
    assert exc1.value.status_code == 400
    assert "SSRF" in exc1.value.detail

    # AWS metadata SSRF
    req2 = CreateWebhookRequest(url="http://169.254.169.254/latest/meta-data/", event_types=["*"])
    with pytest.raises(HTTPException) as exc2:
        create_webhook(req=req2, workspace_id="ws-pro", supabase=mock_supabase)
    assert exc2.value.status_code == 400
    assert "SSRF" in exc2.value.detail


def test_create_webhook_success_encrypts_secret_and_returns_raw():
    """Layer 0 & 2: Successful endpoint registration encrypts secret at rest and returns raw secret once."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "ws-pro", "tier": "PRO"}]
    )
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        count=0, data=[]
    )
    inserted_records = []
    def capture_insert(row):
        inserted_records.append(row)
        m = MagicMock()
        m.execute.return_value = MagicMock(data=[dict(row, id="ep-123")])
        return m

    mock_supabase.table.return_value.insert = capture_insert

    req = CreateWebhookRequest(
        url="https://hooks.zapier.com/hooks/catch/123",
        event_types=["lead.connected", "lead.replied"]
    )
    res = create_webhook(req=req, workspace_id="ws-pro", supabase=mock_supabase)

    assert res["status"] == "success"
    endpoint = res["data"]
    assert endpoint["url"] == "https://hooks.zapier.com/hooks/catch/123"
    assert endpoint["signing_secret"].startswith("whsec_")
    
    assert len(inserted_records) == 1
    stored_secret = inserted_records[0]["signing_secret"]
    assert not stored_secret.startswith("whsec_")


def test_emit_webhook_event_enqueues_deliveries():
    """Layer 0 & 1: Emits event to active subscribed endpoints."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "ep-1", "url": "https://api.acme.com/all", "event_types": ["*"], "is_active": True},
            {"id": "ep-2", "url": "https://api.acme.com/emails", "event_types": ["lead.email_discovered"], "is_active": True},
            {"id": "ep-3", "url": "https://api.acme.com/meetings", "event_types": ["lead.meeting_booked"], "is_active": True}
        ]
    )
    inserted_deliveries = []
    def capture_deliveries(rows):
        inserted_deliveries.extend(rows)
        m = MagicMock()
        m.execute.return_value = MagicMock(data=rows)
        return m

    mock_supabase.table.return_value.insert = capture_deliveries

    count = emit_webhook_event(
        workspace_id="ws-1",
        event_type="lead.email_discovered",
        payload={"lead_id": "lead-1", "email": "vp@acme.com", "api_key": "hide_me"},
        supabase=mock_supabase
    )

    assert count == 2
    assert len(inserted_deliveries) == 2
    for d in inserted_deliveries:
        assert d["event_type"] == "lead.email_discovered"
        assert d["payload"]["event"] == "lead.email_discovered"
        assert d["payload"]["data"]["email"] == "vp@acme.com"
        assert "api_key" not in d["payload"]["data"]


def test_test_webhook_endpoint_records_latency_and_response():
    """Layer 0 & 2: Diagnostic test harness ping records round-trip latency and delivery log."""
    from core.backend.core.crypto import encrypt_bytes, decrypt_bytes
    raw_secret = "whsec_testsecret12345678"

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "ep-123",
            "workspace_id": "ws-1",
            "url": "https://hooks.zapier.com/hooks/catch/123",
            "signing_secret": "deadbeef12345678",
            "event_types": ["*"],
            "is_active": True
        }]
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"success":true,"received":true}'

    with patch("requests.post", return_value=mock_resp), \
         patch("integrations.backend.services.webhook_service.decrypt_bytes", return_value=raw_secret.encode('utf-8')):
        res = run_test_webhook_endpoint(
            endpoint_id="ep-123",
            workspace_id="ws-1",
            supabase=mock_supabase
        )
        assert res["status"] == "success"
        assert res["status_code"] == 200
        assert res["latency_ms"] >= 0
        assert "received" in res["response_body"]
        assert res["url"] == "https://hooks.zapier.com/hooks/catch/123"
        assert len(res["signature_header"]) >= 16


def test_list_and_update_webhook_endpoints():
    """Layer 0: list_webhooks, update_webhook, delete_webhook functionality."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[{"id": "ep-1", "url": "https://hooks.zapier.com/v1", "event_types": ["*"], "is_active": True}]
    )
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "ep-1", "url": "https://hooks.zapier.com/v2", "event_types": ["lead.connected"], "is_active": False}]
    )
    mock_supabase.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "ep-1"}]
    )

    # 1. List
    listed = list_webhooks(workspace_id="ws-1", supabase=mock_supabase)
    assert listed["status"] == "success"
    assert len(listed["data"]) == 1

    # 2. Update
    up_req = UpdateWebhookRequest(url="https://hooks.zapier.com/v2", event_types=["lead.connected"], is_active=False)
    updated = update_webhook("ep-1", up_req, workspace_id="ws-1", supabase=mock_supabase)
    assert updated["status"] == "success"
    assert updated["data"]["url"] == "https://hooks.zapier.com/v2"

    # 3. Delete
    deleted = delete_webhook("ep-1", workspace_id="ws-1", supabase=mock_supabase)
    assert deleted["status"] == "success"
