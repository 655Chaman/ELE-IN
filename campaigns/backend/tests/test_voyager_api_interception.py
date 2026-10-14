import json
import pytest
from unittest.mock import MagicMock, patch
from integrations.backend.services.linkedin_worker import LinkedInWorker

class TestVoyagerAndSalesApiInterception:

    @pytest.fixture
    def worker(self):
        worker = LinkedInWorker(
            cookies_json=json.dumps([{"name": "li_at", "value": "test-li-at", "domain": ".linkedin.com"}]),
            account_id="acc-voyager-test"
        )
        return worker

    def test_voyager_api_interception_success(self, worker):
        """
        Layer 0 & 1: Intercepts Voyager /voyager/api/identity/dash/profiles response directly from Chromium
        and extracts full structured identity data without touching DOM selectors.
        """
        mock_response = MagicMock()
        mock_response.url = "https://www.linkedin.com/voyager/api/identity/dash/profiles?q=memberIdentity"
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "firstName": "Satya",
            "lastName": "Nadella",
            "headline": "Chairman and CEO at Microsoft",
            "included": [
                {"companyName": "Microsoft"}
            ]
        }

        mock_page = MagicMock()
        # When page.on("response", callback) is registered, invoke it with mock_response
        def fake_on(event, handler):
            if event == "response":
                handler(mock_response)
        mock_page.on.side_effect = fake_on

        with patch.object(worker, "_get_or_create_context") as mock_ctx, \
             patch.object(worker, "_http_get", side_effect=Exception("HTTP offload skipped")), \
             patch.object(worker, "_check_for_challenge"), \
             patch.object(worker, "_human_delay"):
            
            mock_ctx.return_value.__enter__.return_value = mock_page

            res = worker.scrape_basic_profile("https://www.linkedin.com/in/satyanadella")
            assert res["status"] == "success"
            assert res["method"] == "voyager_api_interception"
            assert res["name"] == "Satya Nadella"
            assert res["first_name"] == "Satya"
            assert res["title"] == "Chairman and CEO at Microsoft"
            assert res["company"] == "Microsoft"

    def test_sales_api_interception_success(self, worker):
        """
        Layer 0 & 2: Intercepts Sales Navigator /salesApiProfiles endpoint response.
        """
        mock_response = MagicMock()
        mock_response.url = "https://www.linkedin.com/salesApiProfiles/12345"
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json; charset=utf-8"}
        mock_response.json.return_value = {
            "first_name": "Jensen",
            "last_name": "Huang",
            "headline": "Founder and CEO, NVIDIA",
            "included": [
                {"companyName": "NVIDIA"}
            ]
        }

        mock_page = MagicMock()
        def fake_on(event, handler):
            if event == "response":
                handler(mock_response)
        mock_page.on.side_effect = fake_on

        with patch.object(worker, "_get_or_create_context") as mock_ctx, \
             patch.object(worker, "_http_get", side_effect=Exception("HTTP offload skipped")), \
             patch.object(worker, "_check_for_challenge"), \
             patch.object(worker, "_human_delay"):
            
            mock_ctx.return_value.__enter__.return_value = mock_page

            res = worker.scrape_basic_profile("https://www.linkedin.com/sales/lead/12345")
            assert res["status"] == "success"
            assert res["method"] == "voyager_api_interception"
            assert res["name"] == "Jensen Huang"
            assert res["first_name"] == "Jensen"
            assert res["company"] == "NVIDIA"
            assert res["title"] == "Founder and CEO, NVIDIA"

    def test_fallback_to_dom_when_api_missed(self, worker):
        """
        Layer 1 Paranoia: If no API response is received, seamlessly falls back to DOM selectors.
        """
        mock_page = MagicMock()
        mock_page.on.return_value = None
        
        name_loc = MagicMock()
        name_loc.is_visible.return_value = True
        name_loc.inner_text.return_value = "Tim Cook"

        title_loc = MagicMock()
        title_loc.is_visible.return_value = True
        title_loc.inner_text.return_value = "CEO at Apple"

        company_loc = MagicMock()
        company_loc.is_visible.return_value = True
        company_loc.inner_text.return_value = "Apple"

        def fake_locator(sel):
            if "text-heading-xlarge" in sel:
                return MagicMock(first=name_loc)
            if "Current company" in sel:
                return MagicMock(first=company_loc)
            if "text-body-medium" in sel:
                return MagicMock(first=title_loc)
            return MagicMock(first=MagicMock(is_visible=MagicMock(return_value=False)))

        mock_page.locator.side_effect = fake_locator

        with patch.object(worker, "_get_or_create_context") as mock_ctx, \
             patch.object(worker, "_http_get", side_effect=Exception("HTTP offload skipped")), \
             patch.object(worker, "_check_for_challenge"), \
             patch.object(worker, "_human_delay"):
            
            mock_ctx.return_value.__enter__.return_value = mock_page

            res = worker.scrape_basic_profile("https://www.linkedin.com/in/timcook")
            assert res["status"] == "success"
            assert res["method"] == "playwright"
            assert res["name"] == "Tim Cook"
            assert res["first_name"] == "Tim"
            assert res["company"] == "Apple"
            assert res["title"] == "CEO at Apple"
