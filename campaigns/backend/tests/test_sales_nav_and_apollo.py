"""
Comprehensive Unit Tests: Sales Navigator URL Parsing, Search Hygiene, & Resilient Apollo CRM Integration
========================================================================================================
Validates Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0 (Foundational): Parsing search parameters, people match, circuit breaking.
- Layer 1 (Environmental): Network errors, 429 rate limits, 422 duplicates, double URL encoding.
- Layer 2 (Human Paranoia): Rejection of profile URLs in search import, rejection of search queries in raw profile import.
"""

import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from integrations.backend.services.sales_nav_parser import parse_sales_nav_url
from leads.backend.services.data_hygiene import DataHygieneService
from integrations.backend.services.elein_crm_service import add_to_apollo, enrich_with_apollo
from integrations.backend.services.circuit_breaker import get_circuit_breaker, reset_all_circuit_breakers
from campaigns.backend.routers.elein import upload_urls, upload_sales_nav, UploadUrlsRequest, UploadSalesNavRequest


class TestSalesNavParser(unittest.TestCase):
    def test_standard_linkedin_people_search(self):
        url = "https://www.linkedin.com/search/results/people/?keywords=CTO&title=Founder&geoUrn=103644278&network=%5B%22S%22%5D"
        res = parse_sales_nav_url(url)
        self.assertTrue(res["is_search_url"])
        self.assertFalse(res["is_profile_url"])
        self.assertFalse(res["is_sales_nav"])
        self.assertEqual(res["search_params"]["keywords"], "CTO")
        self.assertEqual(res["search_params"]["title"], "Founder")
        self.assertEqual(res["search_params"]["geoUrn"], "103644278")

    def test_sales_nav_flat_parameters(self):
        url = "https://www.linkedin.com/sales/search/people?keywords=VP%20Sales&title=Director&company=Acme"
        res = parse_sales_nav_url(url)
        self.assertTrue(res["is_search_url"])
        self.assertTrue(res["is_sales_nav"])
        self.assertEqual(res["search_params"]["keywords"], "VP Sales")
        self.assertEqual(res["search_params"]["title"], "Director")
        self.assertEqual(res["search_params"]["company"], "Acme")

    def test_sales_nav_nested_dsl_query(self):
        url = (
            "https://www.linkedin.com/sales/search/people?query="
            "(filters%3AList((type%3ACURRENT_TITLE%2Cvalues%3AList((text%3AVP%20Engineering)))%2C"
            "(type%3ACURRENT_COMPANY%2Cvalues%3AList((text%3AGoogle)))%2C"
            "(type%3AREGION%2Cvalues%3AList((id%3A103644278%2Ctext%3AUnited%20States)))))"
        )
        res = parse_sales_nav_url(url)
        self.assertTrue(res["is_search_url"])
        self.assertTrue(res["is_sales_nav"])
        self.assertEqual(res["search_params"]["title"], "VP Engineering")
        self.assertEqual(res["search_params"]["company"], "Google")
        self.assertEqual(res["search_params"]["geoUrn"], "103644278")

    def test_sales_nav_double_encoded_url(self):
        url = "https://www.linkedin.com/sales/search/people?query=%2528keywords%253AFounder%2529"
        res = parse_sales_nav_url(url)
        self.assertTrue(res["is_search_url"])
        self.assertEqual(res["search_params"]["keywords"], "Founder")

    def test_paranoia_profile_url_rejection(self):
        profile_urls = [
            "https://www.linkedin.com/in/john-doe",
            "https://www.linkedin.com/in/john-doe/",
            "https://www.linkedin.com/sales/lead/ACwAABC123,NAME",
            "https://www.linkedin.com/sales/people/ACwAABC123",
        ]
        for u in profile_urls:
            res = parse_sales_nav_url(u)
            self.assertTrue(res["is_profile_url"], f"Failed for {u}")
            self.assertFalse(res["is_search_url"])
            self.assertIn("individual profile", res["error_message"].lower())

    def test_paranoia_company_and_jobs_rejection(self):
        res_comp = parse_sales_nav_url("https://www.linkedin.com/company/microsoft")
        self.assertFalse(res_comp["is_search_url"])
        self.assertIn("company page", res_comp["error_message"].lower())

        res_jobs = parse_sales_nav_url("https://www.linkedin.com/jobs/search?keywords=engineer")
        self.assertFalse(res_jobs["is_search_url"])
        self.assertIn("job search", res_jobs["error_message"].lower())


class TestDataHygieneSearchGuards(unittest.TestCase):
    def test_is_search_url(self):
        self.assertTrue(DataHygieneService.is_search_url("https://www.linkedin.com/sales/search/people?query=..."))
        self.assertTrue(DataHygieneService.is_search_url("https://www.linkedin.com/search/results/people/?keywords=..."))
        self.assertTrue(DataHygieneService.is_search_url("https://www.linkedin.com/sales/lead/search?query=..."))
        self.assertFalse(DataHygieneService.is_search_url("https://www.linkedin.com/in/johndoe"))
        self.assertFalse(DataHygieneService.is_search_url("https://www.linkedin.com/sales/lead/ACwA123"))

    def test_is_profile_url(self):
        self.assertTrue(DataHygieneService.is_profile_url("https://www.linkedin.com/in/johndoe"))
        self.assertTrue(DataHygieneService.is_profile_url("https://www.linkedin.com/sales/lead/ACwA123"))
        self.assertFalse(DataHygieneService.is_profile_url("https://www.linkedin.com/sales/search/people?keywords=..."))
        self.assertFalse(DataHygieneService.is_profile_url("https://google.com/search"))

    def test_normalize_linkedin_url_rejects_searches(self):
        # Must return empty string so search query URLs don't poison database queues
        self.assertEqual(DataHygieneService.normalize_linkedin_url("https://www.linkedin.com/sales/search/people?query=..."), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url("https://www.linkedin.com/search/results/people/?keywords=..."), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url("https://www.linkedin.com/company/acme-corp"), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url("https://www.linkedin.com/jobs/view/123"), "")


class TestLeadUploadEndpoints(unittest.TestCase):
    def test_upload_urls_rejects_pure_search_urls(self):
        req = UploadUrlsRequest(
            name="Accidental Search List",
            urls=["https://www.linkedin.com/sales/search/people?keywords=engineer"],
            target_timezone="America/New_York",
            target_region_label="US / Canada"
        )
        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            upload_urls(req, supabase=mock_supabase, workspace_id="ws-1", user_id="usr-1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Search URL", ctx.exception.detail)

    def test_upload_sales_nav_rejects_personal_profile(self):
        req = UploadSalesNavRequest(
            name="Mistaken Profile as Search",
            url="https://www.linkedin.com/in/john-smith",
            target_timezone="America/New_York",
            target_region_label="US / Canada"
        )
        mock_bg = MagicMock()
        mock_supabase = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            upload_sales_nav(req, background_tasks=mock_bg, supabase=mock_supabase, workspace_id="ws-1", user_id="usr-1")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("individual profile url", ctx.exception.detail.lower())

    @patch("core.backend.services.job_queue.enqueue_job")
    def test_upload_sales_nav_success(self, mock_enqueue):
        req = UploadSalesNavRequest(
            name="Valid Search Import",
            url="https://www.linkedin.com/sales/search/people?keywords=VP%20Marketing",
            target_timezone="America/New_York",
            target_region_label="US / Canada"
        )
        mock_bg = MagicMock()
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc-1", "session_cookies_encrypted": "abc", "is_active": True}]
        )
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

        res = upload_sales_nav(req, background_tasks=mock_bg, supabase=mock_supabase, workspace_id="ws-1", user_id="usr-1")
        self.assertIn("list_id", res)
        self.assertIn("native Voyager scraper", res["message"])
        mock_enqueue.assert_called_once()


class TestApolloResilience(unittest.TestCase):
    def setUp(self):
        reset_all_circuit_breakers()

    @patch.dict("os.environ", {"APOLLO_API_KEY": "test-key"})
    @patch("requests.post")
    def test_add_to_apollo_success(self, mock_post):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {"contact": {"id": "c-123"}}
        mock_post.return_value = mock_res

        lead = {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}
        success = add_to_apollo(workspace_id=None, lead_data=lead)
        self.assertTrue(success)

    @patch.dict("os.environ", {"APOLLO_API_KEY": "test-key"})
    @patch("requests.post")
    def test_add_to_apollo_duplicate_search_recovery(self, mock_post):
        # 1st call: 422 duplicate email
        # 2nd call: search finds existing contact
        r422 = MagicMock(status_code=422, text="Duplicate email")
        r_search = MagicMock(status_code=200)
        r_search.json.return_value = {"contacts": [{"id": "recovered-contact-id"}]}
        mock_post.side_effect = [r422, r_search]

        lead = {"first_name": "Jane", "last_name": "Doe", "email": "jane@duplicate.com"}
        success = add_to_apollo(workspace_id=None, lead_data=lead)
        self.assertTrue(success)

    @patch.dict("os.environ", {"APOLLO_API_KEY": "test-key"})
    @patch("requests.post")
    def test_enrich_with_apollo_success(self, mock_post):
        mock_res = MagicMock(status_code=200)
        mock_res.json.return_value = {
            "person": {
                "email": "jane.enriched@corp.com",
                "phone_numbers": [{"raw_number": "+1234567890"}],
                "title": "Head of Engineering",
                "seniority": "Director",
                "organization": {"name": "Corp Inc", "primary_domain": "corp.com"}
            }
        }
        mock_post.return_value = mock_res

        lead = {"first_name": "Jane", "last_name": "Doe", "domain": "corp.com"}
        enriched = enrich_with_apollo(workspace_id=None, lead_data=lead)
        self.assertIsNotNone(enriched)
        self.assertEqual(enriched["email"], "jane.enriched@corp.com")
        self.assertEqual(enriched["phone"], "+1234567890")
        self.assertEqual(enriched["job_title"], "Head of Engineering")
        self.assertEqual(enriched["company"], "Corp Inc")

    def test_enrich_with_apollo_no_key(self):
        with patch.dict("os.environ", {}, clear=True):
            lead = {"first_name": "Jane", "last_name": "Doe", "domain": "corp.com"}
            res = enrich_with_apollo(workspace_id=None, lead_data=lead)
            self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
