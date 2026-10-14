"""
Step 10 — Voyager Session Cookie Expiry & Silent Re-Auth Trap
Three-Layer Paranoia Framework Tests
"""
import unittest
from unittest.mock import MagicMock, patch


class TestVoyagerSessionExpiry(unittest.TestCase):

    def _make_scraper(self):
        from integrations.backend.services.voyager_scraper import VoyagerScraper, SessionExpired
        supabase = MagicMock()
        supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data={})
        cookies = '[{"name": "li_at", "value": "testtoken"}, {"name": "JSESSIONID", "value": "\\"sess123\\""}]'
        scraper = VoyagerScraper(cookies_json=cookies, account_id="acc-test", supabase=supabase)
        return scraper, supabase, SessionExpired

    def test_401_raises_session_expired_and_marks_disconnected(self):
        """Layer 0 & 1: 401 response raises SessionExpired and marks account DISCONNECTED."""
        scraper, supabase, SessionExpired = self._make_scraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with self.assertRaises(SessionExpired):
                scraper._fetch_page({}, 0)
        # Account should have been marked DISCONNECTED
        update_calls = supabase.table.return_value.update.call_args_list
        self.assertTrue(any(
            call[0][0].get("status") == "DISCONNECTED" for call in update_calls if call[0]
        ) or any(
            "DISCONNECTED" in str(call) for call in update_calls
        ), f"Expected DISCONNECTED update. Got: {update_calls}")

    def test_403_raises_session_expired_and_marks_disconnected(self):
        """Layer 1: 403 response should be treated like 401 — raises SessionExpired."""
        scraper, supabase, SessionExpired = self._make_scraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with self.assertRaises(SessionExpired):
                scraper._fetch_page({}, 0)

    def test_silent_authwall_redirect_raises_session_expired(self):
        """Layer 1: 200 response with HTML authwall body raises SessionExpired."""
        scraper, supabase, SessionExpired = self._make_scraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = "<html><body>Please sign-in to continue</body></html>"
        mock_resp.json.side_effect = Exception("Not JSON")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with self.assertRaises(SessionExpired):
                scraper._fetch_page({}, 0)

    def test_session_expired_propagates_out_of_search_people(self):
        """Layer 0: SessionExpired in _fetch_page propagates through search_people without swallowing."""
        scraper, supabase, SessionExpired = self._make_scraper()
        # Stub daily budget check to pass
        scraper._check_daily_budget = MagicMock(return_value=10)
        scraper._fetch_page = MagicMock(side_effect=SessionExpired("expired"))
        # Stub workspace query to avoid DB calls
        supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data={"workspace_id": None})
        with self.assertRaises(SessionExpired):
            scraper.search_people({}, max_results=10)

    def test_process_background_session_expired_queues_outbox_notification(self):
        """Layer 2: SessionExpired during background import queues outbox_events in-app alert."""
        from campaigns.backend.routers.elein import process_voyager_search_background
        from integrations.backend.services.voyager_scraper import SessionExpired

        mock_supabase = MagicMock()
        # Simulate account query returning encrypted cookies so it doesn't fail on missing cookies
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "acc-123", "session_cookies_encrypted": "dummy", "is_active": True}])
        with patch("campaigns.backend.routers.elein.get_service_client", return_value=mock_supabase), \
             patch("campaigns.backend.routers.elein.VoyagerScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.search_people.side_effect = SessionExpired("test expired")
            # Patch crypto and DataHygieneService correctly
            with patch("core.backend.core.crypto.pg_hex_to_bytes", return_value=b"x"), \
                 patch("core.backend.core.crypto.decrypt_bytes", return_value=b'[{"name":"li_at","value":"x"},{"name":"JSESSIONID","value":"y"}]'), \
                 patch("integrations.backend.services.sales_nav_parser.parse_sales_nav_url", return_value={"search_params": {"keywords": "cto"}}), \
                 patch("leads.backend.services.data_hygiene.DataHygieneService"):
                process_voyager_search_background(
                    list_id="list-1",
                    url="https://www.linkedin.com/search/results/people/?keywords=cto",
                    workspace_id="ws-1",
                    account_id="acc-123",
                    max_results=10,
                    target_timezone="America/New_York"
                )
        # Verify outbox_events was inserted
        insert_calls = str(mock_supabase.table.return_value.insert.call_args_list)
        self.assertIn("outbox_events", str(mock_supabase.table.call_args_list) or str(mock_supabase.mock_calls), f"Expected outbox_events insert. Calls: {mock_supabase.mock_calls[:10]}")

    def test_non_json_non_authwall_returns_none_gracefully(self):
        """Layer 1: Unknown non-JSON response without authwall fingerprint returns None (soft failure)."""
        scraper, supabase, SessionExpired = self._make_scraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = "<html><body>Maintenance mode</body></html>"  # No authwall keyword
        mock_resp.json.side_effect = Exception("Not JSON")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            result = scraper._fetch_page({}, 0)
        self.assertIsNone(result, "Non-JSON non-authwall response should return None gracefully")


if __name__ == "__main__":
    unittest.main()
