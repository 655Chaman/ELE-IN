import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.calendar_concierge_service import (
    _IN_MEMORY_BOOKINGS,
    _RESERVED_REP_SLOTS,
    calculate_conflict_free_slots,
    create_meeting_booking,
    confirm_meeting_slot,
    list_meeting_bookings,
    resolve_calendar_slots_for_execution,
)
from campaigns.backend.routers.calendar_concierge_router import (
    ResolveExecutionSlotsPayload,
    ConfirmBookingPayload,
    resolve_execution_slots_endpoint,
    confirm_booking_endpoint,
)


class _FailingSupabaseMock:
    def table(self, _name: str):
        raise RuntimeError("Simulated DB offline - fallback to in-memory store")


class TestHorizon34CCalendarConciergeOrchestration(unittest.TestCase):
    """
    Horizon 34C: AI Calendar Concierge & Frictionless Meeting Slot Injection
    Three-Layer Paranoia Verification Suite (10 unit tests).
    """

    def setUp(self):
        self._saved_bookings = [dict(b) for b in _IN_MEMORY_BOOKINGS]
        self._saved_locks = dict(_RESERVED_REP_SLOTS)
        _RESERVED_REP_SLOTS.clear()

    def tearDown(self):
        _IN_MEMORY_BOOKINGS.clear()
        _IN_MEMORY_BOOKINGS.extend(self._saved_bookings)
        _RESERVED_REP_SLOTS.clear()
        _RESERVED_REP_SLOTS.update(self._saved_locks)
        app.dependency_overrides.clear()

    def test_01_layer0_resolve_calendar_slots_for_execution_basic(self):
        """Layer 0: resolve_calendar_slots_for_execution creates booking hold, 3 slots, inline text, and reply copy."""
        result = resolve_calendar_slots_for_execution(
            workspace_id="ws-h34c-unit",
            prospect_name="Elena Rostova",
            lead_email="elena@vercel.com",
            company_name="Vercel",
            prospect_timezone="America/Los_Angeles",
            rep_name="Marcus Vance",
            rep_email="marcus@ele-in.com",
            duration_minutes=30,
            supabase=None,
        )
        self.assertIn("booking_id", result)
        self.assertTrue(result["confirmation_token"].startswith("tok_"))
        self.assertEqual(len(result["slots"]), 3)
        self.assertIn("Option 1:", result["slots_inline_text"])
        self.assertIn("Option 2:", result["slots_inline_text"])
        self.assertIn("Option 3:", result["slots_inline_text"])
        self.assertIn("Elena", result["reply_copy"])
        self.assertIn("Marcus Vance", result["reply_copy"])

    def test_02_layer0_router_resolve_execution_slots_endpoint(self):
        """Layer 0: POST /api/elein/calendar/resolve-execution-slots returns 200 with structured slot bundle."""
        app.dependency_overrides[get_current_workspace] = lambda: "ws-test-calendar"
        app.dependency_overrides[get_service_client] = lambda: _FailingSupabaseMock()
        client = TestClient(app)

        resp = client.post(
            "/api/elein/calendar/resolve-execution-slots",
            json={
                "prospect_name": "Claire Temple",
                "lead_email": "claire@stripe.com",
                "company_name": "Stripe",
                "prospect_timezone": "America/New_York",
                "rep_name": "Marcus Vance",
                "rep_email": "marcus@ele-in.com",
                "duration_minutes": 30,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        data = body["data"]
        self.assertEqual(len(data["slots"]), 3)
        self.assertIn("Option 1:", data["slots_inline_text"])
        self.assertIn("Claire", data["reply_copy"])

    def test_03_layer1_double_booking_conflict_guard_in_service(self):
        """Layer 1: _RESERVED_REP_SLOTS prevents two prospects from confirming the same rep slot."""
        b1 = create_meeting_booking(
            workspace_id="ws-h34c",
            lead_email="p1@acme.com",
            lead_name="Prospect One",
            company_name="Acme",
            assigned_rep_email="marcus@ele-in.com",
        )
        b2 = create_meeting_booking(
            workspace_id="ws-h34c",
            lead_email="p2@beta.com",
            lead_name="Prospect Two",
            company_name="Beta",
            assigned_rep_email="marcus@ele-in.com",
        )
        contested_slot = b1["proposed_slots"][0]

        res1 = confirm_meeting_slot(
            confirmation_token=b1["confirmation_token"],
            selected_slot_iso=contested_slot,
            workspace_id="ws-h34c",
        )
        self.assertTrue(res1["success"])

        # Idempotent re-confirmation by the same booking succeeds
        res1_repeat = confirm_meeting_slot(
            confirmation_token=b1["confirmation_token"],
            selected_slot_iso=contested_slot,
            workspace_id="ws-h34c",
        )
        self.assertTrue(res1_repeat["success"])

        # Second prospect attempting to confirm the exact same rep slot raises ValueError
        with self.assertRaises(ValueError) as ctx:
            confirm_meeting_slot(
                confirmation_token=b2["confirmation_token"],
                selected_slot_iso=contested_slot,
                workspace_id="ws-h34c",
            )
        self.assertIn("already booked", str(ctx.exception))

    def test_04_layer1_router_double_booking_returns_http_409(self):
        """Layer 1: POST /api/elein/calendar/confirm maps double-booking ValueError to HTTP 409 Conflict."""
        app.dependency_overrides[get_current_workspace] = lambda: "ws-test-calendar"
        app.dependency_overrides[get_service_client] = lambda: _FailingSupabaseMock()
        client = TestClient(app)

        b1 = create_meeting_booking(
            workspace_id="ws-test-calendar",
            lead_email="lead1@corp.com",
            lead_name="Lead One",
            company_name="Corp 1",
            assigned_rep_email="sarah@ele-in.com",
        )
        b2 = create_meeting_booking(
            workspace_id="ws-test-calendar",
            lead_email="lead2@corp.com",
            lead_name="Lead Two",
            company_name="Corp 2",
            assigned_rep_email="sarah@ele-in.com",
        )
        shared_slot = "2026-10-20T15:00:00+00:00"

        r1 = client.post(
            "/api/elein/calendar/confirm",
            json={
                "confirmation_token": b1["confirmation_token"],
                "selected_slot_iso": shared_slot,
            },
        )
        self.assertEqual(r1.status_code, 200)

        r2 = client.post(
            "/api/elein/calendar/confirm",
            json={
                "confirmation_token": b2["confirmation_token"],
                "selected_slot_iso": shared_slot,
            },
        )
        self.assertEqual(r2.status_code, 409)
        self.assertIn("already booked", str(r2.json()))

    def test_05_layer1_calculate_slots_skips_reserved_rep_slots(self):
        """Layer 1: calculate_conflict_free_slots skips any slot locked in _RESERVED_REP_SLOTS for that rep."""
        rep = "marcus@ele-in.com"
        initial_slots = calculate_conflict_free_slots(rep_email=rep, prospect_tz="America/New_York")
        first_slot_iso = initial_slots[0]["iso"]

        # Lock the first slot for this rep
        _RESERVED_REP_SLOTS[f"{rep}:{first_slot_iso}"] = "book-locked-001"

        next_slots = calculate_conflict_free_slots(rep_email=rep, prospect_tz="America/New_York")
        next_isos = [s["iso"] for s in next_slots]
        self.assertEqual(len(next_isos), 3)
        self.assertNotIn(first_slot_iso, next_isos)

    def test_06_layer1_stale_slot_hold_expiration_and_expired_confirm_rejection(self):
        """Layer 1: resolve_calendar_slots_for_execution expires stale holds (> hold_ttl_hours) and blocks confirmation."""
        stale_booking = create_meeting_booking(
            workspace_id="ws-expire-test",
            lead_email="stale@old.io",
            lead_name="Stale Prospect",
            company_name="OldCo",
            assigned_rep_email="marcus@ele-in.com",
        )
        stale_booking["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=96)).isoformat()

        res = resolve_calendar_slots_for_execution(
            workspace_id="ws-expire-test",
            prospect_name="Fresh Prospect",
            hold_ttl_hours=72,
        )
        self.assertGreaterEqual(res["expired_holds_cleaned"], 1)
        self.assertEqual(stale_booking["status"], "expired")

        with self.assertRaises(ValueError) as ctx:
            confirm_meeting_slot(
                confirmation_token=stale_booking["confirmation_token"],
                selected_slot_iso=stale_booking["proposed_slots"][0],
                workspace_id="ws-expire-test",
            )
        self.assertIn("expired", str(ctx.exception).lower())

    def test_07_layer2_cross_tenant_idor_isolation_in_list_and_confirm(self):
        """Layer 2: Tenant A bookings are hidden from Tenant B list_meeting_bookings and blocked on confirm."""
        tenant_a_booking = create_meeting_booking(
            workspace_id="ws-tenant-alpha",
            lead_email="vip@alpha.io",
            lead_name="Alpha VIP",
            company_name="Alpha Inc",
        )

        tenant_b_list = list_meeting_bookings(workspace_id="ws-tenant-beta", supabase=None)
        tenant_b_ids = [b["id"] for b in tenant_b_list]
        self.assertNotIn(tenant_a_booking["id"], tenant_b_ids)

        with self.assertRaises(PermissionError) as ctx:
            confirm_meeting_slot(
                confirmation_token=tenant_a_booking["confirmation_token"],
                selected_slot_iso=tenant_a_booking["proposed_slots"][0],
                workspace_id="ws-tenant-beta",
            )
        self.assertIn("Cross-workspace access denied", str(ctx.exception))

    def test_08_layer2_router_cross_tenant_confirm_returns_http_403(self):
        """Layer 2: POST /api/elein/calendar/confirm returns HTTP 403 on cross-workspace IDOR attempt."""
        tenant_a_booking = create_meeting_booking(
            workspace_id="ws-tenant-alpha",
            lead_email="ceo@alpha.io",
            lead_name="Alpha CEO",
            company_name="Alpha Inc",
        )

        payload = ConfirmBookingPayload(
            confirmation_token=tenant_a_booking["confirmation_token"],
            selected_slot_iso=tenant_a_booking["proposed_slots"][0],
        )
        with self.assertRaises(HTTPException) as ctx:
            confirm_booking_endpoint(
                payload=payload,
                workspace_id="ws-test-calendar",
                supabase=_FailingSupabaseMock(),
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Cross-workspace access denied", str(ctx.exception.detail))

    def test_09_layer2_meeting_link_scheme_guard_blocks_xss_and_non_https(self):
        """Layer 2: confirm_meeting_slot rejects javascript:, data:, and http:// schemes while allowing https://."""
        booking = create_meeting_booking(
            workspace_id="ws-scheme-test",
            lead_email="sec@test.io",
            lead_name="Sec Lead",
            company_name="SecCo",
        )
        slot_iso = booking["proposed_slots"][0]

        for unsafe_link in ("javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "http://meet.google.com/abc"):
            with self.assertRaises(ValueError):
                confirm_meeting_slot(
                    confirmation_token=booking["confirmation_token"],
                    selected_slot_iso=slot_iso,
                    meeting_link=unsafe_link,
                    workspace_id="ws-scheme-test",
                )

        valid_res = confirm_meeting_slot(
            confirmation_token=booking["confirmation_token"],
            selected_slot_iso=slot_iso,
            meeting_link="https://meet.google.com/safe-room-xyz",
            workspace_id="ws-scheme-test",
        )
        self.assertTrue(valid_res["success"])
        self.assertEqual(valid_res["booking"]["meeting_link"], "https://meet.google.com/safe-room-xyz")

    def test_10_layer2_free_tier_402_gate_on_resolve_execution_slots(self):
        """Layer 2: resolve_execution_slots_endpoint blocks FREE tier workspaces with HTTP 402."""
        mock_sb = MagicMock()
        mock_sb.rpc.return_value.execute.return_value.data = {"tier": "FREE"}
        free_ws_id = "00000000-0000-0000-0000-000000000099"

        payload = ResolveExecutionSlotsPayload(prospect_name="Free Tier User")
        with self.assertRaises(HTTPException) as ctx:
            resolve_execution_slots_endpoint(
                payload=payload,
                workspace_id=free_ws_id,
                supabase=mock_sb,
            )
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["error"], "FEATURE_TIER_GATED")


if __name__ == "__main__":
    unittest.main()
