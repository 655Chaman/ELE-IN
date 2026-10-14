import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from campaigns.backend.routers.elein import allocate_leads_weighted_across_fleet

def test_allocate_leads_weighted_across_fleet_warmup_vs_veteran():
    """
    Paranoia Layer 0 & 1: Verify D'Hondt weighted quota allocation.
    A warmup account (cap 15) vs a veteran account (cap 50) across 65 leads.
    """
    accounts = [
        {"id": "acc-warmup", "status": "ACTIVE", "is_warmup": True, "warmup_max_connections": 15},
        {"id": "acc-veteran", "status": "ACTIVE", "is_warmup": False}
    ]
    allocation = allocate_leads_weighted_across_fleet(accounts, 65)
    assert len(allocation) == 65
    warmup_count = allocation.count("acc-warmup")
    veteran_count = allocation.count("acc-veteran")
    
    # Warmup should receive ~15 (ratio 15/65 = 23.07%)
    # Veteran should receive ~50 (ratio 50/65 = 76.92%)
    assert 14 <= warmup_count <= 16
    assert 49 <= veteran_count <= 51

def test_allocate_leads_filters_inactive_accounts():
    """
    Paranoia Layer 1: Inactive, disconnected, or banned accounts must never be assigned leads.
    """
    accounts = [
        {"id": "acc-active", "status": "ACTIVE", "is_warmup": False},
        {"id": "acc-disconnected", "status": "DISCONNECTED", "is_warmup": False},
        {"id": "acc-banned", "status": "RESTRICTED", "is_warmup": False}
    ]
    allocation = allocate_leads_weighted_across_fleet(accounts, 20)
    assert len(allocation) == 20
    assert all(acc == "acc-active" for acc in allocation)

def test_allocate_leads_empty_and_zero_handling():
    """
    Paranoia Layer 2: Gracefully handles empty accounts list or 0 leads without crashing.
    """
    assert allocate_leads_weighted_across_fleet([], 10) == []
    assert allocate_leads_weighted_across_fleet([{"id": "acc-1", "status": "ACTIVE"}], 0) == []
    assert allocate_leads_weighted_across_fleet([{"id": "acc-1", "status": "ACTIVE"}], -5) == []

def test_allocate_leads_all_inactive_fallback():
    """
    Paranoia Layer 1 fallback: If statuses are unset/unmigrated, distribute across fleet rather than dropping leads.
    """
    accounts = [
        {"id": "acc-1", "status": ""},
        {"id": "acc-2", "status": ""}
    ]
    allocation = allocate_leads_weighted_across_fleet(accounts, 10)
    assert len(allocation) == 10
    assert "acc-1" in allocation
    assert "acc-2" in allocation

def test_intent_webhook_unauthorized_token():
    """
    Paranoia Layer 1: Inbound Webhook rejects unauthenticated or revoked tokens with 401.
    """
    from campaigns.backend.routers.inbound_webhooks import intent_webhook
    from fastapi import HTTPException
    
    mock_supabase = MagicMock()
    # Mock invalid token return (empty data)
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])
    
    with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc:
            intent_webhook("camp-1", {"email": "lead@company.com"}, "invalid-token-123")
        assert exc.value.status_code == 401
        assert "Invalid or revoked API token" in exc.value.detail


def test_intent_webhook_missing_token_returns_401():
    """
    Paranoia Layer 0 & 2: When no token is passed in query or headers, return actionable 401.
    """
    from campaigns.backend.routers.inbound_webhooks import intent_webhook
    from fastapi import HTTPException

    mock_supabase = MagicMock()
    with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
        with pytest.raises(HTTPException) as exc:
            intent_webhook("camp-1", {"email": "lead@company.com"})
        assert exc.value.status_code == 401
        assert "Missing API token" in exc.value.detail


def _build_test_supabase_mock(workspace_id="ws-99", campaign_id="camp-1", on_insert_states=None):
    supabase = MagicMock()
    
    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "api_keys":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"workspace_id": workspace_id}])
        elif table_name == "campaigns":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": campaign_id}])
        elif table_name == "campaign_accounts":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"account_id": "acc-1", "accounts": {"id": "acc-1", "status": "ACTIVE"}}])
        elif table_name == "campaign_versions":
            mock_t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "ver-1"}])
        elif table_name == "leads":
            mock_t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            mock_t.insert.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "campaign_enrollments":
            mock_t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            mock_t.insert.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "campaign_execution_states":
            mock_t.select.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            if on_insert_states:
                mock_t.insert.side_effect = on_insert_states
            else:
                mock_t.insert.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    supabase.table.side_effect = table_router
    return supabase


def test_intent_webhook_header_x_api_key_auth():
    """
    Paranoia Layer 1: X-API-Key header authentication succeeds and resolves workspace.
    """
    from campaigns.backend.routers.inbound_webhooks import intent_webhook

    test_token = "elein_live_sec_12345"
    mock_supabase = _build_test_supabase_mock()

    mock_request = MagicMock()
    mock_request.headers = {"x-api-key": test_token}

    with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
        res = intent_webhook(
            campaign_id="camp-1",
            body={"email": "sarah@acme.com", "first_name": "Sarah"},
            request=mock_request
        )
        assert res["status"] == "success"
        assert res["enrolled"] == 1


def test_intent_webhook_header_bearer_auth_and_preserves_intent_variables():
    """
    Paranoia Layer 0, 1 & 2: Bearer token auth extracts and populates execution variables.
    """
    from campaigns.backend.routers.inbound_webhooks import intent_webhook

    test_token = "bearer_secret_token_abc"
    inserted_states = []
    def capture_states_insert(payload):
        inserted_states.extend(payload)
        m = MagicMock()
        m.execute.return_value = MagicMock(data=payload)
        return m

    mock_supabase = _build_test_supabase_mock(on_insert_states=capture_states_insert)

    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {test_token}"}

    intent_payload = {
        "email": "alex@apollo.io",
        "first_name": "Alex",
        "buying_signal": "recent_funding_round",
        "intent_score": 92,
        "hiring_role": "VP Engineering",
        "funding_amount": "$15M Series A"
    }

    with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase):
        res = intent_webhook(
            campaign_id="camp-1",
            body=intent_payload,
            request=mock_request
        )
        assert res["status"] == "success"
        assert res["enrolled"] == 1
        assert len(inserted_states) == 1
        state_vars = inserted_states[0]["variables"]
        assert state_vars["buying_signal"] == "recent_funding_round"
        assert state_vars["intent_score"] == 92
        assert state_vars["hiring_role"] == "VP Engineering"
        assert state_vars["funding_amount"] == "$15M Series A"


def test_intent_webhook_emits_lead_enrolled_event():
    """
    Layer 0 & 1: Enrolling leads via intent webhook emits lead.enrolled event.
    """
    from campaigns.backend.routers.inbound_webhooks import intent_webhook
    test_token = "bearer_secret_token_123"
    mock_supabase = _build_test_supabase_mock()
    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {test_token}"}

    with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
         patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
        res = intent_webhook(
            campaign_id="camp-1",
            body={"email": "prospect@acme.com", "first_name": "Jane"},
            request=mock_request
        )
        assert res["status"] == "success"
        assert res["enrolled"] == 1
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["event_type"] == "lead.enrolled"
        assert call_kwargs["workspace_id"] == "ws-99"
        assert call_kwargs["payload"]["campaign_id"] == "camp-1"
        assert call_kwargs["payload"]["enrolled_count"] == 1


def test_calendar_booking_webhook_emits_meeting_booked_event():
    """
    Layer 0, 1 & 2: Calendar booking webhook successfully halts outreach and emits lead.meeting_booked.
    """
    import asyncio
    from campaigns.backend.routers.inbound_webhooks import calendar_booking_webhook
    mock_supabase = MagicMock()
    # Workspace lookup
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "ws-1", "status": "active"}])
    # Secret lookup (no secret required or matched)
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    # Lead lookup
    mock_supabase.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "lead-999", "metadata": {}}])
    # Enrollment lookup
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "enr-1"}])

    mock_request = MagicMock()
    mock_request.headers = {"user-agent": "Calendly-Hook/1.0"}
    mock_request.query_params = {}
    mock_request.json = AsyncMock(return_value={"email": "sarah@client.com", "event": "invitee.created"})

    with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
         patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
        res = asyncio.run(calendar_booking_webhook(workspace_id="ws-1", request=mock_request))
        assert res["status"] == "success"
        assert res["lead_id"] == "lead-999"
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args[1]
        assert call_kwargs["event_type"] == "lead.meeting_booked"
        assert call_kwargs["workspace_id"] == "ws-1"
        assert call_kwargs["payload"]["lead_id"] == "lead-999"
        assert call_kwargs["payload"]["email"] == "sarah@client.com"
        assert call_kwargs["payload"]["platform"] == "calendly"



