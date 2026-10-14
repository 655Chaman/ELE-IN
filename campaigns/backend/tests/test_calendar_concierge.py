import pytest
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.calendar_concierge_service import (
    extract_scheduling_intent,
    calculate_conflict_free_slots,
    format_frictionless_calendar_reply,
    create_meeting_booking,
    confirm_meeting_slot,
    list_meeting_bookings,
    get_rep_availability
)


class FailingTableMock:
    """Simulates Supabase table missing error (Zero-Migration guard)."""
    def select(self, *args, **kwargs):
        raise RuntimeError("relation 'public.meeting_bookings' does not exist")
    def insert(self, *args, **kwargs):
        raise RuntimeError("relation 'public.meeting_bookings' does not exist")
    def update(self, *args, **kwargs):
        raise RuntimeError("relation 'public.meeting_bookings' does not exist")


class FailingSupabaseMock:
    def table(self, table_name: str):
        return FailingTableMock()


@pytest.fixture
def auth_client():
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-calendar"
    app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestSchedulingIntentExtraction:
    def test_extract_positive_scheduling_intent_and_tz(self):
        text = "Hi Marcus, let's talk next Tuesday morning! I am located in SF (PST)."
        intent = extract_scheduling_intent(text)
        assert intent["has_scheduling_intent"] is True
        assert intent["confidence_score"] > 0.8
        assert intent["detected_timezone"] == "America/Los_Angeles"
        assert intent["preferred_day"] == "Tuesday"
        assert intent["preferred_period"] == "morning"

    def test_extract_negative_or_rejection(self):
        text = "Please remove me from your list, not interested at all."
        intent = extract_scheduling_intent(text)
        assert intent["has_scheduling_intent"] is False
        assert intent["confidence_score"] < 0.5


class TestSlotGenerationAndFrictionlessCopy:
    def test_calculate_conflict_free_slots(self):
        slots = calculate_conflict_free_slots(
            rep_email="rep@ele-in.com",
            prospect_tz="America/New_York",
            duration_minutes=30
        )
        assert len(slots) == 3
        for s in slots:
            assert "iso" in s
            assert "display_label" in s
            assert s["duration_minutes"] == 30
            assert s["day_name"] in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

    def test_format_frictionless_calendar_reply(self):
        slots = calculate_conflict_free_slots(rep_email="rep@ele-in.com", prospect_tz="America/New_York")
        copy = format_frictionless_calendar_reply(
            prospect_name="Sarah Connor",
            slots=slots,
            rep_name="Alex Vance",
            confirmation_token="tok_123"
        )
        assert "Sarah" in copy
        assert "Alex" in copy
        assert "Option 1:" in copy
        assert "Option 2:" in copy
        assert "Option 3:" in copy
        assert "Google Meet link" in copy


class TestMeetingBookingAndCampaignHalt:
    def test_confirm_slot_and_halt_campaigns(self):
        token = "tok_test_confirm_999"
        # Create booking in memory
        booking = create_meeting_booking(
            workspace_id="ws-test-calendar",
            lead_email="alex@scale.ai",
            lead_name="Alexandr Wang",
            company_name="Scale AI",
            assigned_rep_email="marcus@ele-in.com",
            supabase=None
        )
        t = booking["confirmation_token"]

        res = confirm_meeting_slot(
            confirmation_token=t,
            selected_slot_iso="2026-10-15T18:00:00Z"
        )
        assert res["success"] is True
        assert res["campaign_halted"] is True
        assert "meet.google.com" in res["booking"]["meeting_link"]
        assert res["booking"]["status"] == "confirmed"


class TestCalendarRouterEndpoints:
    def test_router_bookings_crud(self, auth_client: TestClient):
        # 1. List bookings
        get_res = auth_client.get("/api/elein/calendar/bookings")
        assert get_res.status_code == 200
        body = get_res.json()
        assert body["success"] is True
        assert len(body["bookings"]) >= 1

        # 2. Create booking
        create_res = auth_client.post(
            "/api/elein/calendar/bookings",
            json={
                "lead_email": "cto@anthropic.com",
                "lead_name": "Dario Amodei",
                "company_name": "Anthropic",
                "assigned_rep_email": "marcus@ele-in.com",
                "prospect_timezone": "America/Los_Angeles",
                "meeting_duration_minutes": 30,
                "booking_notes": "Discussing 50-seat deployment"
            }
        )
        assert create_res.status_code == 200
        new_b = create_res.json()["data"]
        assert new_b["company_name"] == "Anthropic"
        assert len(new_b["proposed_slots"]) == 3

    def test_router_availability_endpoint(self, auth_client: TestClient):
        res = auth_client.get("/api/elein/calendar/availability")
        assert res.status_code == 200
        avail = res.json()["availability"]
        assert avail["working_hours_start"] == "09:00"
        assert avail["buffer_minutes"] == 15

    def test_router_propose_slots_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/calendar/propose-slots",
            json={
                "prospect_name": "Rachel Zane",
                "prospect_timezone": "America/Chicago",
                "rep_name": "Marcus Vance",
                "duration_minutes": 30
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["slots"]) == 3
        assert "Rachel" in data["reply_copy"]

    def test_router_extract_intent_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/calendar/extract-intent",
            json={"reply_text": "Sounds interesting, free tomorrow afternoon PST"}
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["has_scheduling_intent"] is True
        assert data["detected_timezone"] == "America/Los_Angeles"

    def test_router_confirm_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/calendar/confirm",
            json={
                "confirmation_token": "tok_linear_danielle_778",
                "selected_slot_iso": "2026-10-14T17:00:00Z"
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["campaign_halted"] is True

    def test_free_tier_rejection_http_402_on_calendar_endpoints(self):
        """Layer 2 Paranoia: Endpoints return HTTP 402 FEATURE_TIER_GATED when workspace is on Free tier."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from campaigns.backend.routers.calendar_concierge_router import (
            get_bookings_endpoint,
            get_availability_endpoint,
            create_booking_endpoint,
            propose_slots_endpoint,
            confirm_booking_endpoint,
            extract_intent_endpoint,
            CreateBookingPayload,
            ProposeSlotsPayload,
            ConfirmBookingPayload,
            ExtractIntentPayload
        )

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        free_ws_id = "00000000-0000-0000-0000-000000000001"

        # 1. Bookings GET endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_bookings_endpoint(status=None, workspace_id=free_ws_id, supabase=mock_sb)
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail["error"] == "FEATURE_TIER_GATED"

        # 2. Availability GET endpoint
        with pytest.raises(HTTPException) as exc_info:
            get_availability_endpoint(rep_email=None, workspace_id=free_ws_id, supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # 3. Create booking POST endpoint
        book_payload = CreateBookingPayload(
            lead_email="prospect@acme.corp",
            lead_name="Danielle Brooks",
            company_name="Acme Corp"
        )
        with pytest.raises(HTTPException) as exc_info:
            create_booking_endpoint(book_payload, workspace_id=free_ws_id, supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # 4. Propose slots POST endpoint
        propose_payload = ProposeSlotsPayload(
            prospect_name="Danielle Brooks"
        )
        with pytest.raises(HTTPException) as exc_info:
            propose_slots_endpoint(propose_payload, workspace_id=free_ws_id, supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # 5. Confirm booking POST endpoint
        confirm_payload = ConfirmBookingPayload(
            confirmation_token="tok_preview",
            selected_slot_iso="2026-10-15T15:00:00Z"
        )
        with pytest.raises(HTTPException) as exc_info:
            confirm_booking_endpoint(confirm_payload, workspace_id=free_ws_id, supabase=mock_sb)
        assert exc_info.value.status_code == 402

        # 6. Extract intent POST endpoint
        intent_payload = ExtractIntentPayload(
            reply_text="Let's meet tomorrow at 2pm"
        )
        with pytest.raises(HTTPException) as exc_info:
            extract_intent_endpoint(intent_payload, workspace_id=free_ws_id, supabase=mock_sb)
        assert exc_info.value.status_code == 402

    def test_pro_tier_allowed_on_calendar_endpoints(self):
        """Growth Pro and Enterprise workspaces have full access to calendar concierge endpoints."""
        from unittest.mock import MagicMock
        from campaigns.backend.routers.calendar_concierge_router import get_bookings_endpoint

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "PRO"}
        mock_sb.table.side_effect = Exception("table not migrated yet")

        res = get_bookings_endpoint(status=None, workspace_id="00000000-0000-0000-0000-000000000002", supabase=mock_sb)
        assert res["success"] is True
        assert res["total"] >= 1

    def test_free_tier_campaign_activation_blocked_for_calendar_nodes(self):
        """Layer 2: Free tier campaign activation is rejected with 403 when calendar concierge is enabled."""
        from unittest.mock import MagicMock
        from fastapi.testclient import TestClient
        from core.backend.main import app
        from core.backend.api.auth_dep import get_current_workspace
        from campaigns.backend.routers.elein import get_supabase_client

        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        mock_data = [
            {
                "id": "camp-cal-free",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "metadata": {"calendar_concierge_enabled": True},
            }
        ]
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = mock_data
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = mock_data

        free_ws_id = "00000000-0000-0000-0000-000000000001"
        app.dependency_overrides[get_current_workspace] = lambda: free_ws_id
        app.dependency_overrides[get_supabase_client] = lambda: mock_sb
        try:
            client = TestClient(app)
            resp = client.patch("/api/elein/campaigns/camp-cal-free/activate")
            assert resp.status_code == 403
            assert "Executive Calendar Concierge" in str(resp.json())
        finally:
            app.dependency_overrides.pop(get_current_workspace, None)
            app.dependency_overrides.pop(get_supabase_client, None)
