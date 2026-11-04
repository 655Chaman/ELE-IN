"""
Three-Layer Paranoia Framework Closed-Loop Integration Test Suite:
Settings Execution Engine (Holidays, Day Matrix, Webhooks, Session Inactivity, Bulk Invites, Audit Trail)
"""
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import pytz
from fastapi import HTTPException

from campaigns.backend.services.timezone_utils import (
    is_national_holiday,
    is_working_hours,
    calculate_next_run_at,
    get_day_override_window
)
from core.backend.services.notification_service import (
    dispatch_workspace_alert_webhooks,
    dispatch_invitation_email
)
from core.backend.api.auth_dep import SessionActivityTracker
from leads.backend.routers.leads import (
    delete_suppression_batch_endpoint,
    SuppressionBatchDeleteRequest
)


class TestNationalHolidayAndDayMatrix(unittest.TestCase):

    def test_national_holiday_detection(self):
        """Layer 0 & 1: Correctly identifies national public holidays and normalizes country codes."""
        # Christmas Day in US
        xmas = datetime(2026, 12, 25, 10, 0, tzinfo=pytz.UTC)
        self.assertTrue(is_national_holiday(xmas, "US"))
        
        # Non-holiday regular weekday (e.g. Wednesday, October 14, 2026)
        regular_day = datetime(2026, 10, 14, 10, 0, tzinfo=pytz.UTC)
        self.assertFalse(is_national_holiday(regular_day, "US"))

        # UK / GB normalization
        boxing_day = datetime(2026, 12, 26, 12, 0, tzinfo=pytz.UTC)
        self.assertTrue(is_national_holiday(boxing_day, "UK"))

    def test_working_hours_blocked_on_national_holiday(self):
        """Layer 1: Auto-pause blocks outreach on holidays when pause_on_national_holidays is True."""
        tz_ny = "America/New_York"
        # Christmas 2026 at 11:00 AM NY time (normally peak business hours)
        ny_tz_obj = pytz.timezone(tz_ny)
        xmas_local = ny_tz_obj.localize(datetime(2026, 12, 25, 11, 0, 0))

        # Schedule with holiday pause enabled
        schedule_with_holiday_pause = {
            "start_hour": 9,
            "end_hour": 17,
            "pause_on_national_holidays": True,
            "national_holiday_country": "US"
        }
        # Outreach MUST be paused
        self.assertFalse(is_working_hours(tz_ny, schedule=schedule_with_holiday_pause, now_dt=xmas_local))

        # Schedule with holiday pause disabled allows sending on Christmas
        schedule_without_pause = {
            "start_hour": 9,
            "end_hour": 17,
            "pause_on_national_holidays": False,
            "national_holiday_country": "US"
        }
        self.assertTrue(is_working_hours(tz_ny, schedule=schedule_without_pause, now_dt=xmas_local))

    def test_granular_day_matrix_overrides(self):
        """Layer 1 & 2: Day matrix overrides enforce day-specific hours and weekend curfews."""
        tz_str = "UTC"
        day_overrides = {
            "friday": {"enabled": True, "start": "08:30", "end": "13:00"},
            "sunday": {"enabled": False, "start": "10:00", "end": "15:00"}
        }
        schedule = {
            "start_hour": 8,
            "end_hour": 18,
            "day_schedule_overrides": day_overrides
        }

        # Friday Oct 16, 2026 at 11:00 UTC -> inside Friday half-day window
        fri_inside = datetime(2026, 10, 16, 11, 0, tzinfo=pytz.UTC)
        self.assertTrue(is_working_hours(tz_str, schedule=schedule, now_dt=fri_inside))

        # Friday Oct 16, 2026 at 13:05 UTC -> outside Friday half-day window (would pass standard 18:00 without override)
        fri_outside = datetime(2026, 10, 16, 13, 5, tzinfo=pytz.UTC)
        self.assertFalse(is_working_hours(tz_str, schedule=schedule, now_dt=fri_outside))

        # Sunday Oct 18, 2026 at 12:00 UTC -> explicitly disabled
        sun_disabled = datetime(2026, 10, 18, 12, 0, tzinfo=pytz.UTC)
        self.assertFalse(is_working_hours(tz_str, schedule=schedule, now_dt=sun_disabled))

    def test_calculate_next_run_at_skips_holidays_and_disabled_days(self):
        """Layer 2: Next run calculation safely leaps across holidays to the next valid operational window."""
        tz_ny = "America/New_York"
        ny_tz_obj = pytz.timezone(tz_ny)
        # Thursday, Nov 26, 2026 is Thanksgiving in the US
        thanksgiving = ny_tz_obj.localize(datetime(2026, 11, 26, 10, 0, 0))

        schedule = {
            "start_hour": 9,
            "end_hour": 17,
            "pause_on_national_holidays": True,
            "national_holiday_country": "US"
        }

        next_run = calculate_next_run_at(thanksgiving, tz_ny, schedule=schedule)
        next_run_ny = next_run.astimezone(ny_tz_obj)

        # Must not be scheduled on Thanksgiving Day
        self.assertNotEqual(next_run_ny.date(), thanksgiving.date())
        # Should land on Friday, Nov 27, 2026 at 9:00 AM NY time
        self.assertEqual(next_run_ny.year, 2026)
        self.assertEqual(next_run_ny.month, 11)
        self.assertEqual(next_run_ny.day, 27)
        self.assertEqual(next_run_ny.hour, 9)


class TestUnifiedWebhookDispatcher(unittest.TestCase):

    @patch("requests.post")
    def test_dispatcher_respects_channel_routing(self, mock_post):
        """Layer 1: Dispatches only to channels enabled in routing matrix."""
        mock_resp = MagicMock(status_code=200)
        mock_post.return_value = mock_resp

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "metadata": {
                    "webhooks": {
                        "slack_webhook_url": "https://hooks.slack.com/services/T00/B00/X00",
                        "discord_webhook_url": "https://discord.com/api/webhooks/123/abc",
                        "channel_routing": {
                            "lead_replied_instant": {"slack": True, "discord": False}
                        }
                    }
                }
            }]
        )

        res = dispatch_workspace_alert_webhooks(
            svc=mock_supabase,
            workspace_id="ws_webhooks_1",
            event_type="lead_replied_instant",
            title="Lead Replied!",
            description="John Doe responded to your email."
        )

        self.assertEqual(res["slack"], "sent")
        self.assertEqual(res["discord"], "skipped")
        self.assertEqual(mock_post.call_count, 1)

    @patch("requests.post")
    def test_dispatcher_blocks_ssrf_malicious_urls(self, mock_post):
        """Layer 2 (Security): Blocks SSRF attempts to AWS metadata or loopback hosts."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "metadata": {
                    "webhooks": {
                        "slack_webhook_url": "https://169.254.169.254/latest/meta-data/",
                        "discord_webhook_url": "https://localhost:8000/internal",
                        "channel_routing": {
                            "account_suspended": {"slack": True, "discord": True}
                        }
                    }
                }
            }]
        )

        res = dispatch_workspace_alert_webhooks(
            svc=mock_supabase,
            workspace_id="ws_webhooks_ssrf",
            event_type="account_suspended",
            title="Suspended",
            description="Alert"
        )

        self.assertEqual(res["slack"], "blocked_ssrf")
        self.assertEqual(res["discord"], "blocked_ssrf")
        self.assertEqual(mock_post.call_count, 0)


class TestSessionInactivityAndFingerprint(unittest.TestCase):

    def setUp(self):
        self.tracker = SessionActivityTracker(max_entries=100)

    def test_session_idle_timeout_expiration(self):
        """Layer 1: Session expires when inactivity threshold is exceeded."""
        ws_id = "ws_test_timeout"
        user_id = "usr_alice"
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

        # Initial request: records active timestamp
        self.tracker.record_and_verify(
            workspace_id=ws_id,
            user_id=user_id,
            timeout_minutes=30,
            enforce_fingerprint=False,
            user_agent=ua
        )

        # Immediate follow-up: succeeds
        self.tracker.record_and_verify(
            workspace_id=ws_id,
            user_id=user_id,
            timeout_minutes=30,
            enforce_fingerprint=False,
            user_agent=ua
        )

        # Fast forward time past 30 minutes
        with patch("time.time", return_value=self.tracker._activity[f"{ws_id}:{user_id}"][0] + (31 * 60)):
            with self.assertRaises(HTTPException) as ctx:
                self.tracker.record_and_verify(
                    workspace_id=ws_id,
                    user_id=user_id,
                    timeout_minutes=30,
                    enforce_fingerprint=False,
                    user_agent=ua
                )
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("inactivity", ctx.exception.detail)

    def test_device_fingerprint_mismatch_invalidation(self):
        """Layer 2: Invalidates session when enforce_device_fingerprint=True and client fingerprint changes."""
        ws_id = "ws_test_fp"
        user_id = "usr_bob"
        initial_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        attacker_ua = "Python-urllib/3.9 attacker-script"

        # Legitimate login
        self.tracker.record_and_verify(
            workspace_id=ws_id,
            user_id=user_id,
            timeout_minutes=60,
            enforce_fingerprint=True,
            user_agent=initial_ua
        )

        # Hijacked request with different user-agent
        with self.assertRaises(HTTPException) as ctx:
            self.tracker.record_and_verify(
                workspace_id=ws_id,
                user_id=user_id,
                timeout_minutes=60,
                enforce_fingerprint=True,
                user_agent=attacker_ua
            )
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("fingerprint mismatch", ctx.exception.detail)


class TestTransactionalBulkInvitesAndAuditLog(unittest.TestCase):

    def test_dispatch_invitation_email_enqueues_outbox(self):
        """Layer 0 & 1: Enqueues invitation email to outbox_events with unique token and idempotent key."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "evt_1"}])

        success = dispatch_invitation_email(
            svc=mock_supabase,
            workspace_id="ws_invite_1",
            email="colleague@acme.com",
            role="member",
            token="secret_token_123"
        )

        self.assertTrue(success)
        mock_supabase.table.assert_called_with("outbox_events")
        call_args = mock_supabase.table.return_value.upsert.call_args[0][0]
        self.assertEqual(call_args["workspace_id"], "ws_invite_1")
        self.assertEqual(call_args["event_type"], "notification.email")
        self.assertEqual(call_args["payload"]["recipient_email"], "colleague@acme.com")
        self.assertIn("/accept-invite?token=secret_token_123", call_args["payload"]["link"])

    @patch("admin.backend.routers.workspaces.log_audit")
    def test_delete_suppression_batch_logs_audit_trail(self, mock_log_audit):
        """Layer 1: Batch suppression deletion writes SOC-2 compliant immutable audit logs."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "s_1"}, {"id": "s_2"}]
        )
        mock_supabase.table.return_value.delete.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        req = SuppressionBatchDeleteRequest(entry_ids=["s_1", "s_2"])
        res = delete_suppression_batch_endpoint(
            payload=req,
            workspace_id="ws_audit_1",
            supabase=mock_supabase,
            user_id="usr_compliance_officer"
        )

        self.assertEqual(res["status"], "batch_deleted")
        self.assertEqual(res["deleted_count"], 2)
        mock_log_audit.assert_called_once_with(
            svc=mock_supabase,
            workspace_id="ws_audit_1",
            actor_id="usr_compliance_officer",
            action="suppression.batch_deleted",
            target_type="suppression_list",
            target_id="ws_audit_1",
            before_state={"deleted_ids": ["s_1", "s_2"]},
            after_state={"deleted_count": 2}
        )


if __name__ == "__main__":
    unittest.main()
