import unittest
from unittest.mock import MagicMock, patch
import io
import csv

from leads.backend.services.data_hygiene import DataHygieneService
from campaigns.backend.routers.elein import upload_urls, UploadUrlsRequest


class TestHorizon4LeadsAndDeduplication(unittest.TestCase):
    """
    Horizon 4: Leads Management, Deduplication & CSV Ingestion Engine.
    Tests compliance with the Three-Layer Logic Architecture (Paranoia Framework).
    """

    # =========================================================================
    # Layer 0 & Layer 1: Data Hygiene Service - Personal Name Cleaning
    # =========================================================================
    def test_clean_name_paranoia(self):
        # Layer 0: Basic casing and whitespace
        self.assertEqual(DataHygieneService.clean_name("JOHN DOE"), "John Doe")
        self.assertEqual(DataHygieneService.clean_name("john doe"), "John Doe")
        self.assertEqual(DataHygieneService.clean_name("  Jane   Smith  "), "Jane Smith")

        # Layer 1: Accents and international names
        self.assertEqual(DataHygieneService.clean_name("DR. JOSÉ MÜLLER, PHD"), "José Müller")
        self.assertEqual(DataHygieneService.clean_name("François Hollande"), "François Hollande")

        # Layer 1: Apostrophes in surnames
        self.assertEqual(DataHygieneService.clean_name("siobhan o'connor"), "Siobhan O'Connor")
        self.assertEqual(DataHygieneService.clean_name("d'angelo barksdale"), "D'Angelo Barksdale")

        # Layer 1: Non-string type safety
        self.assertEqual(DataHygieneService.clean_name(None), "")
        self.assertEqual(DataHygieneService.clean_name(12345), "12345")

        # Layer 2: Extreme user inputs / Fallbacks
        self.assertEqual(DataHygieneService.clean_name(""), "")
        self.assertEqual(DataHygieneService.clean_name("   "), "")
        # Standalone title should not be erased to blank (falls back gracefully)
        self.assertIn(DataHygieneService.clean_name("Dr."), ("Dr.", "Dr"))

    # =========================================================================
    # Layer 0 & Layer 1: Data Hygiene Service - Company Name Cleaning
    # =========================================================================
    def test_clean_company_paranoia(self):
        # Layer 0: Stripping corporate legal entities
        self.assertEqual(DataHygieneService.clean_company("Acme Corp, LLC"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Global Tech Solutions Ltd."), "Global Tech Solutions")
        self.assertEqual(DataHygieneService.clean_company("BIG ENTERPRISE INC"), "Big Enterprise")

        # Layer 1: Preserving & and - in business names
        self.assertEqual(DataHygieneService.clean_company("AT&T Inc."), "AT&T")
        self.assertEqual(DataHygieneService.clean_company("Johnson & Johnson, LLC"), "Johnson & Johnson")
        self.assertEqual(DataHygieneService.clean_company("Rolls-Royce plc"), "Rolls-Royce")

        # Layer 1: Type safety
        self.assertEqual(DataHygieneService.clean_company(None), "")
        self.assertEqual(DataHygieneService.clean_company(""), "")

        # Layer 2: Entity names that would be completely emptied fallback safely
        self.assertEqual(DataHygieneService.clean_company("The Co"), "The Co")
        self.assertEqual(DataHygieneService.clean_company("LLC"), "LLC")

    # =========================================================================
    # Layer 0, 1 & 2: LinkedIn Profile URL Normalization & Deduplication
    # =========================================================================
    def test_normalize_linkedin_url_paranoia(self):
        expected_canonical = "https://www.linkedin.com/in/johndoe"

        # Variations that should all resolve to the exact same canonical URL:
        variations = [
            "https://www.linkedin.com/in/johndoe",
            "https://www.linkedin.com/in/johndoe/",
            "http://www.linkedin.com/in/johndoe",
            "http://linkedin.com/in/johndoe/",
            "linkedin.com/in/johndoe",
            "www.linkedin.com/in/johndoe",
            "https://in.linkedin.com/in/johndoe",
            "https://uk.linkedin.com/in/johndoe/",
            "https://www.linkedin.com/in/JohnDoe",
            "https://www.linkedin.com/in/JOHNDOE/",
            "https://www.linkedin.com/in/johndoe?miniProfileUrn=urn%3Ali%3A123",
            "https://www.linkedin.com/in/johndoe?trk=public_profile&utm_source=share",
            "https://www.linkedin.com/in/johndoe#experience",
            " <https://www.linkedin.com/in/johndoe> ",
            "\"https://www.linkedin.com/in/johndoe/\"",
            "['https://www.linkedin.com/in/johndoe']",
        ]

        for url in variations:
            normalized = DataHygieneService.normalize_linkedin_url(url)
            self.assertEqual(normalized, expected_canonical, f"Failed for URL: {url}")

        # Invalid or non-LinkedIn domains must return empty string
        self.assertEqual(DataHygieneService.normalize_linkedin_url("https://google.com/search?q=johndoe"), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url("https://facebook.com/in/johndoe"), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url("not a url at all"), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url(None), "")
        self.assertEqual(DataHygieneService.normalize_linkedin_url(""), "")

    # =========================================================================
    # Endpoint Simulation: upload_urls In-Memory Deduplication
    # =========================================================================
    def test_upload_urls_deduplicates_and_normalizes(self):
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"inserted_count": 1})
        mock_supabase.rpc.return_value = mock_rpc

        # Input with 4 variations of the same person + 1 invalid non-LinkedIn URL
        raw_urls = [
            "https://in.linkedin.com/in/johndoe/",
            "https://www.linkedin.com/in/johndoe?trk=test",
            "linkedin.com/in/JohnDoe",
            "http://www.linkedin.com/in/johndoe",
            "https://github.com/johndoe",  # Invalid, must be dropped
        ]

        req = UploadUrlsRequest(
            name="Test List Dedupe",
            urls=raw_urls,
            target_timezone="UTC",
            target_region_label="Global"
        )

        with patch("campaigns.backend.routers.elein.log_audit"):
            res = upload_urls(
                body=req,
                supabase=mock_supabase,
                workspace_id="ws_dedupe_test",
                user_id="user_123"
            )

        # Verify bulk_import_leads was called with exactly 1 deduplicated lead
        mock_supabase.rpc.assert_called_with("bulk_import_leads", {
            "p_list_id": res["list_id"],
            "p_workspace_id": "ws_dedupe_test",
            "p_leads": [{"linkedin_url": "https://www.linkedin.com/in/johndoe", "email": "", "first_name": "", "last_name": "", "company_name": "", "job_title": "", "location": "", "domain": "", "timezone": "UTC", "is_open_profile": False}],
            "p_timezone": "UTC"
        })

    # =========================================================================
    # CSV Delimiter & BOM Detection Simulation
    # =========================================================================
    def test_csv_bom_and_delimiter_sniffing(self):
        # 1. UTF-8 with BOM
        bom_csv_bytes = b"\xef\xbb\xbfFirst Name,Last Name,LinkedIn\nAlice,Smith,https://www.linkedin.com/in/alicesmith"
        content_decoded = bom_csv_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content_decoded))
        first_row = next(reader)
        # Header keys must NOT contain the \ufeff character
        self.assertIn("First Name", first_row)
        self.assertNotIn("\ufeffFirst Name", first_row)

        # 2. Semicolon delimiter sniffing
        semicolon_csv = "First Name;Last Name;LinkedIn\nBob;Jones;https://www.linkedin.com/in/bobjones"
        dialect = csv.Sniffer().sniff(semicolon_csv, delimiters=",\t;|")
        self.assertEqual(dialect.delimiter, ";")
        semi_reader = csv.DictReader(io.StringIO(semicolon_csv), delimiter=dialect.delimiter)
        row = next(semi_reader)
        self.assertEqual(row["First Name"], "Bob")
        self.assertEqual(row["LinkedIn"], "https://www.linkedin.com/in/bobjones")


if __name__ == "__main__":
    unittest.main()
