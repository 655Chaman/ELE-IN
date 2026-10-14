import unittest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import json
import os
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request

from inbox.backend.services.outbox_worker import (
    poll_outbox_once,
    reap_stuck_outbox_events,
    _process_in_app_notification,
    _process_slack_notification,
    _process_webhook_notification,
    MAX_ATTEMPTS,
)
from core.backend.api.rate_limit import rate_limit
from integrations.backend.services.voyager_scraper import (
    VoyagerScraper,
    DailyLimitExceeded,
    VoyagerThrottled,
    SessionExpired,
    DAILY_LIMIT,
)
from knowledge.backend.services.elein_ai_service import UsageLimitExceededError
from integrations.backend.services.linkedin_worker import (
    LinkedInWorker,
    linkedin_action_safe,
    SessionExpiredError,
    SecurityChallengeError,
    BrowserPoolExhaustedError,
)


class TestHorizon15OutboxQueueRateLimitVoyager(unittest.TestCase):
    """
    Test suite for Horizon 15: Outbox Worker, Dispatcher Queue, Rate Limiting &
    Voyager Interception Hardening.
    Three-Layer Paranoia Architecture.
    """

    def _setup_multi_table_mock(self):
        """Helper to create isolated mock per table name to prevent chaining collisions."""
        mock_svc = MagicMock()
        tables = defaultdict(MagicMock)

        def get_table(tbl_name):
            return tables[tbl_name]

        mock_svc.table.side_effect = get_table
        return mock_svc, tables

    # =========================================================================
    # 1. Outbox Worker & Queue Delivery (Layer 0, 1, 2)
    # =========================================================================

    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_poll_outbox_empty_events(self, mock_client):
        """Layer 0: Returns 0 when no pending outbox events exist."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc
        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 0)

    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_poll_outbox_atomic_claim_race_condition_skipped(self, mock_client):
        """Layer 1: If another concurrent worker claimed the event, it is skipped cleanly."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        # 1 event returned from pending select
        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_race", "event_type": "workspace.schedule_deletion", "attempts": 0}]
        )
        # But atomic update (claim) returns empty data because another worker claimed it
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 0)

    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_poll_outbox_successful_delivery(self, mock_client):
        """Layer 0: Valid event is claimed, processed, and marked delivered."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "evt_1",
                "workspace_id": "ws_1",
                "event_type": "workspace.schedule_deletion",
                "payload": {"scheduled_for": "2026-11-01"},
                "attempts": 0
            }]
        )
        # Claim succeeds
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_1", "status": "processing"}]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 1)

    @patch("inbox.backend.services.outbox_worker._process_in_app_notification", return_value=False)
    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_poll_outbox_retry_on_failure(self, mock_client, mock_process):
        """Layer 1: Event delivery failure resets status to 'pending' when attempts < MAX_ATTEMPTS."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_fail_1", "event_type": "notification.in_app", "attempts": 0}]
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_fail_1", "status": "processing"}]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 0)
        # Verify update set status to 'pending' for retry
        update_calls = tables["outbox_events"].update.call_args_list
        # Second update call is the failure/retry update
        fail_update = update_calls[-1][0][0]
        self.assertEqual(fail_update["status"], "pending")
        self.assertEqual(fail_update["attempts"], 1)

    @patch("inbox.backend.services.outbox_worker._process_in_app_notification", return_value=False)
    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_poll_outbox_dead_letter_max_attempts(self, mock_client, mock_process):
        """Layer 1: Event delivery failure on 3rd attempt transitions to 'failed' (dead letter)."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_dead", "event_type": "notification.in_app", "attempts": 2}]  # will become 3
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_dead", "status": "processing"}]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 0)
        update_calls = tables["outbox_events"].update.call_args_list
        fail_update = update_calls[-1][0][0]
        self.assertEqual(fail_update["status"], "failed")
        self.assertEqual(fail_update["attempts"], 3)

    @patch("inbox.backend.services.outbox_worker.get_service_client")
    def test_poll_outbox_unimplemented_channel_suspended(self, mock_client):
        """Layer 1: Unrecognized channel is marked 'suspended' to preserve data without burning retries."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["outbox_events"].select.return_value.eq.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_unknown", "event_type": "notification.telepathy", "attempts": 0}]
        )
        tables["outbox_events"].update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt_unknown", "status": "processing"}]
        )

        count = poll_outbox_once()
        self.assertEqual(count, 0)
        update_calls = tables["outbox_events"].update.call_args_list
        suspend_update = update_calls[-1][0][0]
        self.assertEqual(suspend_update["status"], "suspended")

    def test_reap_stuck_outbox_events_recovers_marooned_records(self):
        """Layer 1: Events marooned in 'processing' status past timeout are reaped back to 'pending'."""
        mock_svc, tables = self._setup_multi_table_mock()
        tables["outbox_events"].select.return_value.eq.return_value.lt.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "stuck_1", "attempts": 1},
                {"id": "stuck_2", "attempts": 3},  # max attempts exceeded -> failed
            ]
        )

        reaped = reap_stuck_outbox_events(mock_svc, stuck_timeout_minutes=15)
        self.assertEqual(reaped, 2)
        # Verify stuck_1 was reset to pending and stuck_2 to failed
        self.assertEqual(tables["outbox_events"].update.call_count, 2)
        first_call = tables["outbox_events"].update.call_args_list[0][0][0]
        second_call = tables["outbox_events"].update.call_args_list[1][0][0]
        self.assertEqual(first_call["status"], "pending")
        self.assertEqual(second_call["status"], "failed")

    # =========================================================================
    # 2. Notification Dispatch Channels & SSRF (Layer 0, 1, 2)
    # =========================================================================

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_process_in_app_notification_deduplicates(self, mock_client):
        """Layer 1: Duplicate in-app notifications for existing outbox_event_id are skipped."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "usr_1"}]
        )
        tables["notification_preferences"].select.return_value.eq.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "usr_1", "enabled": True}]
        )
        # Existing notifications contains usr_1 already
        tables["notifications"].select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "usr_1"}]
        )

        event = {
            "id": "evt_dup",
            "workspace_id": "ws_1",
            "payload": {
                "event_type": "campaign.completed",
                "title": "Campaign Finished",
                "body": "Your campaign has completed.",
            }
        }
        res = _process_in_app_notification(event)
        self.assertTrue(res)
        # Insert should not be called because usr_1 already has notification for this outbox event
        tables["notifications"].insert.assert_not_called()

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_process_in_app_notification_no_members_raises(self, mock_client):
        """Layer 2: Empty workspace members raises ValueError to prevent fake success."""
        mock_svc, tables = self._setup_multi_table_mock()
        mock_client.return_value = mock_svc

        tables["workspace_members"].select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        event = {
            "id": "evt_nomembers",
            "workspace_id": "ws_empty",
            "payload": {
                "event_type": "alert",
                "title": "Title",
                "body": "Body",
            }
        }
        with self.assertRaises(ValueError):
            _process_in_app_notification(event)

    def test_process_slack_notification_ssrf_blocked(self):
        """Layer 1 (Security): Slack webhook URL pointing to AWS metadata or loopback is blocked."""
        event = {
            "id": "evt_ssrf_slack",
            "payload": {
                "webhook_url": "http://169.254.169.254/latest/meta-data/",
                "text": "Leak credentials"
            }
        }
        res = _process_slack_notification(event)
        self.assertFalse(res)

    def test_process_webhook_notification_ssrf_blocked(self):
        """Layer 1 (Security): Outbound webhook URL pointing to localhost/private IP is blocked."""
        event = {
            "id": "evt_ssrf_hook",
            "payload": {
                "url": "http://127.0.0.1:8000/internal-admin",
                "data": {"ping": "pong"}
            }
        }
        res = _process_webhook_notification(event)
        self.assertFalse(res)

    # =========================================================================
    # 3. Token-Bucket API Rate Limiter (Layer 0, 1, 2)
    # =========================================================================

    def test_rate_limit_skipped_when_no_api_key(self):
        """Layer 0: Session UI requests (no api_key_id in request.state) skip the limiter."""
        limiter = rate_limit(cost=1, capacity=50)
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.api_key_id = None
        mock_svc = MagicMock()

        self.assertTrue(limiter(request, mock_svc))
        mock_svc.rpc.assert_not_called()

    def test_rate_limit_allowed_when_quota_available(self):
        """Layer 0: consume_api_quota returning True allows the request."""
        limiter = rate_limit(cost=1, capacity=100)
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.api_key_id = "key_live_123"
        mock_svc = MagicMock()
        mock_svc.rpc.return_value.execute.return_value = MagicMock(data=True)

        self.assertTrue(limiter(request, mock_svc))
        mock_svc.rpc.assert_called_once()

    def test_rate_limit_exceeded_raises_429(self):
        """Layer 1: consume_api_quota returning False raises HTTP 429."""
        limiter = rate_limit(cost=5, capacity=100)
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.api_key_id = "key_exhausted"
        mock_svc = MagicMock()
        mock_svc.rpc.return_value.execute.return_value = MagicMock(data=False)

        with self.assertRaises(HTTPException) as ctx:
            limiter(request, mock_svc)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("quota exhausted", ctx.exception.detail)

    def test_rate_limit_missing_rpc_graceful_fallback(self):
        """Layer 1: If consume_api_quota function is missing in Postgres, defaults to passing."""
        limiter = rate_limit(cost=1, capacity=100)
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.api_key_id = "key_fallback"
        mock_svc = MagicMock()
        mock_svc.rpc.return_value.execute.side_effect = Exception("could not find the function consume_api_quota")

        self.assertTrue(limiter(request, mock_svc))

    def test_rate_limit_db_failure_raises_503(self):
        """Layer 1: Real DB connection failure fails closed with 503 Service Unavailable."""
        limiter = rate_limit(cost=1, capacity=100)
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.api_key_id = "key_db_fail"
        mock_svc = MagicMock()
        mock_svc.rpc.return_value.execute.side_effect = Exception("Connection terminated unexpectedly")

        with self.assertRaises(HTTPException) as ctx:
            limiter(request, mock_svc)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_rate_limit_negative_parameters_sanitized(self):
        """Layer 2: Negative or zero cost and capacity inputs are safely clamped."""
        limiter = rate_limit(cost=-10, capacity=0, refill_rate_per_second=-2.5)
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.api_key_id = "key_sanitize"
        mock_svc = MagicMock()
        mock_svc.rpc.return_value.execute.return_value = MagicMock(data=True)

        self.assertTrue(limiter(request, mock_svc))
        call_args = mock_svc.rpc.call_args[0][1]
        self.assertEqual(call_args["p_cost"], 1)
        self.assertEqual(call_args["p_capacity"], 1)
        self.assertEqual(call_args["p_refill_rate_per_second"], 0.01)

    # =========================================================================
    # 4. Voyager Scraper & Budget Enforcement (Layer 0, 1, 2)
    # =========================================================================

    def test_voyager_scraper_missing_cookies_rejected(self):
        """Layer 2: Initializing VoyagerScraper without li_at or JSESSIONID raises ValueError."""
        mock_svc = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            VoyagerScraper(cookies_json="[]", account_id="acc_1", supabase=mock_svc)
        self.assertIn("Missing li_at or JSESSIONID", str(ctx.exception))

    def test_voyager_scraper_malformed_cookies_json_handled(self):
        """Layer 2: Malformed JSON string in cookies_json handled cleanly with ValueError."""
        mock_svc = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            VoyagerScraper(cookies_json="INVALID_JSON{{{{", account_id="acc_1", supabase=mock_svc)
        self.assertIn("Missing li_at or JSESSIONID", str(ctx.exception))

    def test_voyager_scraper_daily_budget_exceeded(self):
        """Layer 1: Account exceeding daily profile scrape limit raises DailyLimitExceeded."""
        mock_svc = MagicMock()
        cookies = json.dumps([
            {"name": "li_at", "value": "test_li_at"},
            {"name": "JSESSIONID", "value": "\"ajax:12345\""}
        ])
        scraper = VoyagerScraper(cookies_json=cookies, account_id="acc_capped", supabase=mock_svc)

        # Mock current day usage equal to DAILY_LIMIT (150)
        today = datetime.now(timezone.utc).date().isoformat()
        mock_svc.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"daily_scrape_count": DAILY_LIMIT, "last_scrape_date": today}
        )

        with self.assertRaises(DailyLimitExceeded) as ctx:
            scraper._check_daily_budget(10)
        self.assertIn("daily limit", str(ctx.exception))

    def test_voyager_scraper_get_budget_status(self):
        """Layer 0: Returns accurate budget status for frontend progress meter."""
        mock_svc = MagicMock()
        cookies = json.dumps([
            {"name": "li_at", "value": "test_li_at"},
            {"name": "JSESSIONID", "value": "\"ajax:12345\""}
        ])
        scraper = VoyagerScraper(cookies_json=cookies, account_id="acc_budget", supabase=mock_svc)

        today = datetime.now(timezone.utc).date().isoformat()
        mock_svc.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"daily_scrape_count": 45, "last_scrape_date": today}
        )

        status = scraper.get_budget_status()
        self.assertEqual(status["used"], 45)
        self.assertEqual(status["limit"], DAILY_LIMIT)
        self.assertEqual(status["remaining"], DAILY_LIMIT - 45)
        self.assertEqual(status["reset_date"], today)

    def test_voyager_scraper_parse_profiles(self):
        """Layer 0: Correctly parses MiniProfile entities from Voyager included array."""
        mock_svc = MagicMock()
        cookies = json.dumps([
            {"name": "li_at", "value": "test_li_at"},
            {"name": "JSESSIONID", "value": "\"ajax:12345\""}
        ])
        scraper = VoyagerScraper(cookies_json=cookies, account_id="acc_parse", supabase=mock_svc)

        raw_data = {
            "included": [
                {
                    "$type": "com.linkedin.voyager.dash.identity.profile.MiniProfile",
                    "firstName": "Demis",
                    "lastName": "Hassabis",
                    "headline": "CEO at Google DeepMind",
                    "publicIdentifier": "demis-hassabis"
                }
            ]
        }
        profiles = scraper._parse_profiles(raw_data)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["first_name"], "Demis")
        self.assertEqual(profiles[0]["last_name"], "Hassabis")
        self.assertEqual(profiles[0]["headline"], "CEO at Google DeepMind")
        self.assertEqual(profiles[0]["linkedin_url"], "https://www.linkedin.com/in/demis-hassabis")

    def test_voyager_scraper_search_people_usage_limit_exceeded(self):
        """Layer 1: When workspace leads monthly quota is exhausted, raises UsageLimitExceededError."""
        mock_svc = MagicMock()
        cookies = json.dumps([
            {"name": "li_at", "value": "test_li_at"},
            {"name": "JSESSIONID", "value": "\"ajax:12345\""}
        ])
        scraper = VoyagerScraper(cookies_json=cookies, account_id="acc_limit", supabase=mock_svc)

        mock_svc.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"workspace_id": "ws_over_limit"}
        )
        mock_svc.rpc.return_value.execute.side_effect = Exception("UsageLimitExceededError: Leads limit exceeded")

        with self.assertRaises(UsageLimitExceededError):
            scraper.search_people(search_params={"keywords": "CTO"}, max_results=50)

    # =========================================================================
    # 5. LinkedIn Worker Guards (Layer 0, 1, 2)
    # =========================================================================

    def test_linkedin_worker_missing_account_id_rejected(self):
        """Layer 2: Initializing LinkedInWorker with account_id=None raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            LinkedInWorker(cookies_json="[]", account_id=None)
        self.assertIn("requires a non-None account_id", str(ctx.exception))

    def test_linkedin_action_safe_handles_session_expired(self):
        """Layer 1: linkedin_action_safe catches SessionExpiredError and returns clean status."""
        @linkedin_action_safe
        def faulty_action():
            raise SessionExpiredError("Session cookies expired")

        res = faulty_action()
        self.assertEqual(res, {"status": "session_expired"})

    def test_linkedin_action_safe_handles_security_challenge(self):
        """Layer 1: linkedin_action_safe catches SecurityChallengeError and returns clean status."""
        @linkedin_action_safe
        def challenge_action():
            raise SecurityChallengeError("PIN verification challenge triggered")

        res = challenge_action()
        self.assertEqual(res, {"status": "security_challenge"})

    def test_linkedin_action_safe_handles_browser_pool_exhausted(self):
        """Layer 1: linkedin_action_safe catches BrowserPoolExhaustedError and returns pool_exhausted."""
        @linkedin_action_safe
        def pool_action():
            raise BrowserPoolExhaustedError("All browser slots occupied")

        res = pool_action()
        self.assertEqual(res, {"status": "pool_exhausted"})


if __name__ == "__main__":
    unittest.main()
