import uuid
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from knowledge.backend.services.elein_ai_service import get_warmup_phase
from leads.backend.routers.leads import (
    export_leads_in_list,
    mask_phone,
    mask_email,
    sanitize_csv_value
)


class TestStage18EliteArchitecture(unittest.IsolatedAsyncioTestCase):
    """
    Stage 18 Elite-Tier Distributed Systems Architecture Test Suite
    Governance: Three-Layer Logic Architecture (Paranoia Framework)
    """

    # ── 1. LinkedIn Warmup Curve & Jitter Schedule Hardening ──────────────────

    def test_warmup_phase_polymorphic_created_at_parsing(self):
        """
        Layer 1: get_warmup_phase handles polymorphic timestamp types:
        ISO-8601 strings, Unix epoch integers/floats, and gracefully falls back
        on corrupted or None inputs without raising exceptions.
        """
        now = time.time()
        five_days_ago_ts = now - (5 * 86400)
        five_days_ago_iso = datetime.fromtimestamp(five_days_ago_ts, tz=timezone.utc).isoformat()

        # 1. Unix epoch float
        res_float = get_warmup_phase(created_at=five_days_ago_ts, actions_today=5, is_warmup=True, target_days=14)
        self.assertEqual(res_float["day"], 6)
        self.assertIn(res_float["phase"], ["observe", "seed", "ramp", "cruise"])
        self.assertIn("recommended_delay_seconds", res_float)

        # 2. ISO-8601 string
        res_iso = get_warmup_phase(created_at=five_days_ago_iso, actions_today=5, is_warmup=True, target_days=14)
        self.assertEqual(res_iso["day"], 6)

        # 3. Corrupted / Malformed input fallback (gracefully treated as today -> day 1)
        res_corrupt = get_warmup_phase(created_at="INVALID_TIMESTAMP_STRING", actions_today=0, is_warmup=True, target_days=14)
        self.assertEqual(res_corrupt["day"], 1)
        self.assertEqual(res_corrupt["phase"], "observe")

        # 4. None input fallback
        res_none = get_warmup_phase(created_at=None, actions_today=0, is_warmup=True, target_days=14)
        self.assertEqual(res_none["day"], 1)

    def test_warmup_phase_dynamic_safety_penalty_and_jitter(self):
        """
        Layer 1 & 2: Over-activity beyond daily quota applies a bounded dynamic penalty
        to the safety score, and recommended action delay scales with warmup day.
        """
        # Baseline on day 1 with observe limit 10: 5 actions -> within quota, score 90
        res_normal = get_warmup_phase(created_at=time.time(), actions_today=5, is_warmup=True, target_days=14)
        self.assertEqual(res_normal["safety_score"], 90)
        self.assertEqual(res_normal["daily_limit"], 10)
        self.assertEqual(res_normal["recommended_delay_seconds"], 240 - (1 * 4))

        # Over-activity: 35 actions on a limit of 10 -> excess 25 -> penalty applied
        res_over = get_warmup_phase(created_at=time.time(), actions_today=35, is_warmup=True, target_days=14)
        self.assertLess(res_over["safety_score"], 90)
        self.assertGreaterEqual(res_over["safety_score"], 20)  # Min floor is 20

        # Non-warmup mode returns active cruise defaults
        res_active = get_warmup_phase(created_at=time.time(), actions_today=50, is_warmup=False)
        self.assertEqual(res_active["phase"], "active")
        self.assertEqual(res_active["safety_score"], 100)
        self.assertEqual(res_active["daily_limit"], 100)
        self.assertEqual(res_active["recommended_delay_seconds"], 120)

    # ── 2. Inbound Webhook Booking Double-Attribution Guard ───────────────────

    @patch("integrations.backend.services.webhook_service.emit_webhook_event")
    async def test_calendar_booking_webhook_first_vs_repeat_idempotency(self, mock_emit_webhook):
        """
        Layer 1 & 2: First booking emits lead.meeting_booked webhook and halts campaigns.
        Repeat booking suppresses duplicate webhook emission and returns already_processed.
        """
        from campaigns.backend.routers.inbound_webhooks import calendar_booking_webhook
        from starlette.requests import Request

        workspace_id = "ws-booking-test"
        lead_id = f"lead-{uuid.uuid4()}"
        lead_email = "prospect@acmecorp.com"

        # Mock request with JSON body
        async def mock_json():
            return {
                "event": "invitee.created",
                "payload": {
                    "email": lead_email,
                    "event_type": {"name": "Demo Call"}
                }
            }

        mock_req = MagicMock(spec=Request)
        mock_req.json = mock_json
        mock_req.headers = {"user-agent": "Calendly/1.0", "content-type": "application/json"}
        mock_req.query_params = {}

        # 1. First Booking Scenario: Lead has meeting_booked: False
        first_lead_data = {
            "id": lead_id,
            "email": lead_email,
            "metadata": {"meeting_booked": False}
        }

        mock_sb_first = MagicMock()
        def fake_table_first(name):
            ret = MagicMock()
            if name == "workspaces":
                ret.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": workspace_id, "status": "active"}]
                )
            elif name == "workspace_settings":
                ret.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "leads":
                ret.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[first_lead_data]
                )
                ret.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "campaign_enrollments":
                ret.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "enr-1"}])
                ret.update.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            elif name == "campaign_execution_states":
                ret.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{"status": "running"}])
                ret.update.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            return ret

        mock_sb_first.table = fake_table_first

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_sb_first), \
             patch("campaigns.backend.routers.inbound_webhooks.get_inbound_idempotency_ledger") as mock_ledger_fn:
            mock_ledger = MagicMock()
            mock_ledger.check_and_set.return_value = (False, None)
            mock_ledger_fn.return_value = mock_ledger

            res1 = await calendar_booking_webhook(workspace_id=workspace_id, request=mock_req)

            self.assertEqual(res1["status"], "success")
            self.assertEqual(res1["lead_id"], lead_id)
            # Must emit webhook on first booking
            mock_emit_webhook.assert_called_once()
            called_kwargs = mock_emit_webhook.call_args[1]
            self.assertEqual(called_kwargs["workspace_id"], workspace_id)
            self.assertEqual(called_kwargs["event_type"], "lead.meeting_booked")
            self.assertEqual(called_kwargs["payload"]["lead_id"], lead_id)
            self.assertEqual(called_kwargs["payload"]["email"], lead_email)

        # 2. Repeat Booking Scenario: Lead already has meeting_booked: True
        mock_emit_webhook.reset_mock()
        second_lead_data = {
            "id": lead_id,
            "email": lead_email,
            "metadata": {"meeting_booked": True}
        }

        mock_sb_repeat = MagicMock()
        def fake_table_repeat(name):
            ret = MagicMock()
            if name == "workspaces":
                ret.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"id": workspace_id, "status": "active"}]
                )
            elif name == "workspace_settings":
                ret.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "leads":
                ret.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[second_lead_data]
                )
            elif name == "campaign_enrollments":
                ret.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "enr-1"}])
            elif name == "campaign_execution_states":
                ret.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{"status": "completed"}])
            return ret

        mock_sb_repeat.table = fake_table_repeat

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_sb_repeat), \
             patch("campaigns.backend.routers.inbound_webhooks.get_inbound_idempotency_ledger") as mock_ledger_fn:
            mock_ledger = MagicMock()
            mock_ledger.check_and_set.return_value = (False, None)
            mock_ledger_fn.return_value = mock_ledger

            res2 = await calendar_booking_webhook(workspace_id=workspace_id, request=mock_req)

            # Must return already_processed and NOT emit duplicate webhook
            self.assertEqual(res2["status"], "already_processed")
            mock_emit_webhook.assert_not_called()

    # ── 3. Lead Export Masking & Formula Injection Protection ─────────────────

    def test_mask_phone_utility(self):
        """
        Layer 2: mask_phone safely masks phone numbers, keeping only last 4 digits,
        and defensively handles None, non-strings, or short numbers.
        """
        self.assertEqual(mask_phone("+1 (555) 234-5678"), "***-***-5678")
        self.assertEqual(mask_phone("1234567890"), "***-***-7890")
        self.assertEqual(mask_phone("123"), "***")
        self.assertEqual(mask_phone(""), "")
        self.assertEqual(mask_phone(None), "")
        self.assertEqual(mask_phone(12345), "")

    def test_sanitize_csv_formula_injection(self):
        """
        Layer 2: sanitize_csv_value neutralizes formula injection vectors (=, +, -, @, tab).
        """
        self.assertEqual(sanitize_csv_value("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(sanitize_csv_value("+12345"), "'+12345")
        self.assertEqual(sanitize_csv_value("-500"), "'-500")
        self.assertEqual(sanitize_csv_value("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        # Already escaped stays unchanged
        self.assertEqual(sanitize_csv_value("'+already"), "'+already")
        # Regular text unchanged
        self.assertEqual(sanitize_csv_value("John Doe"), "John Doe")

    async def test_export_leads_in_list_free_vs_pro_tier_masking(self):
        """
        Layer 1 & 2: export_leads_in_list enforces subscription tier bounds,
        masks email & phone on FREE tier, exposes unmasked contacts on PRO tier,
        and defensively clamps selected_ids to 1,000.
        """
        # 1. Invalid list ID validation
        with self.assertRaises(HTTPException) as ctx:
            await export_leads_in_list(
                list_id="   ",
                workspace_id="ws-export",
                supabase=MagicMock()
            )
        self.assertEqual(ctx.exception.status_code, 400)

        # 2. FREE tier export test
        mock_supabase_free = MagicMock()
        mock_list_check = MagicMock()
        mock_list_check.execute = AsyncMock(return_value=MagicMock(data={"id": "list-1", "name": "Target List"}))

        mock_ws_check_free = MagicMock()
        mock_ws_check_free.execute = AsyncMock(return_value=MagicMock(data={"tier": "FREE"}))

        leads_raw = [
            {
                "id": f"lead-{i}",
                "first_name": f"Lead {i}",
                "last_name": "Smith",
                "email": f"lead{i}@enterprise.com",
                "phone": f"+1 555 000 {1000 + i}",
                "company_name": "=InjectedCompany"
            }
            for i in range(30)
        ]
        mock_leads_query_free = MagicMock()
        mock_leads_query_free.execute = AsyncMock(return_value=MagicMock(data=leads_raw[:25]))

        def fake_table_free(name):
            ret = MagicMock()
            if name == "lead_lists":
                ret.select.return_value.eq.return_value.eq.return_value.single.return_value = mock_list_check
            elif name == "workspaces":
                ret.select.return_value.eq.return_value.single.return_value = mock_ws_check_free
            elif name == "leads":
                ret.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value = mock_leads_query_free
            return ret

        mock_supabase_free.table = fake_table_free

        res_free = await export_leads_in_list(
            list_id="list-1",
            selected_ids=None,
            workspace_id="ws-export",
            supabase=mock_supabase_free
        )

        self.assertEqual(res_free["status"], "success")
        self.assertEqual(res_free["tier"], "FREE")
        self.assertFalse(res_free["can_export_unmasked"])
        self.assertEqual(res_free["max_export_limit"], 25)
        self.assertEqual(len(res_free["data"]), 25)
        # Check email and phone masking on Free tier
        self.assertTrue(res_free["data"][0]["email"].endswith("@enterprise.com"))
        self.assertTrue(res_free["data"][0]["email"].startswith("le***"))
        self.assertTrue(res_free["data"][0]["phone"].startswith("***-***-"))
        # Check CSV formula sanitization
        self.assertTrue(res_free["data"][0]["company_name"].startswith("'="))

        # 3. PRO tier export test with selected_ids > 1000 bound check
        mock_supabase_pro = MagicMock()
        mock_ws_check_pro = MagicMock()
        mock_ws_check_pro.execute = AsyncMock(return_value=MagicMock(data={"tier": "PRO"}))

        mock_leads_query_pro = MagicMock()
        mock_leads_query_pro.execute = AsyncMock(return_value=MagicMock(data=leads_raw))

        captured_in_filter = []
        def fake_table_pro(name):
            ret = MagicMock()
            if name == "lead_lists":
                ret.select.return_value.eq.return_value.eq.return_value.single.return_value = mock_list_check
            elif name == "workspaces":
                ret.select.return_value.eq.return_value.single.return_value = mock_ws_check_pro
            elif name == "leads":
                # Mock chain: select().eq().eq().order().in_().limit()
                query_builder = MagicMock()
                ret.select.return_value.eq.return_value.eq.return_value.order.return_value = query_builder
                def record_in(col, vals):
                    captured_in_filter.extend(vals)
                    return query_builder
                query_builder.in_ = record_in
                query_builder.limit.return_value = mock_leads_query_pro
            return ret

        mock_supabase_pro.table = fake_table_pro

        # Pass 1,500 selected lead IDs
        selected_1500 = ",".join([f"lead-{i}" for i in range(1500)])
        res_pro = await export_leads_in_list(
            list_id="list-1",
            selected_ids=selected_1500,
            workspace_id="ws-export",
            supabase=mock_supabase_pro
        )

        self.assertEqual(res_pro["status"], "success")
        self.assertEqual(res_pro["tier"], "PRO")
        self.assertTrue(res_pro["can_export_unmasked"])
        # Unmasked on Pro tier, sanitized with quote for leading plus
        self.assertEqual(res_pro["data"][0]["email"], "lead0@enterprise.com")
        self.assertEqual(res_pro["data"][0]["phone"], "'+1 555 000 1000")
        # Paranoia Layer 1: Bound to exactly 1,000 items
        self.assertEqual(len(captured_in_filter), 1000)


if __name__ == "__main__":
    unittest.main()
