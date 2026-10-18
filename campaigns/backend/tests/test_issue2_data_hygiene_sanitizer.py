"""
Unit Test Suite for Issue 2: Lead Name & Company Slogan Sanitizer
Adheres strictly to the Three-Layer Paranoia Framework:
- Layer 0: Foundational Name & Company cleaning (titles, delimiters, suffixes, domain stripping, casing)
- Layer 1: Environmental Edge Cases (initials in names, hyphenated names/companies, acronym preservation)
- Layer 2: Human Paranoia & Fallbacks (all-stripped string fallback, poison string scrub, field_type routing)
"""
import unittest
from leads.backend.services.data_hygiene import DataHygieneService
from campaigns.backend.services.template_spintax_guard import clean_enrichment_value


class TestLeadNameSanitizer(unittest.TestCase):
    """Test DataHygieneService.clean_name across all Three Paranoia Layers."""

    def test_strip_parenthetical_and_bracketed_tags(self):
        """Layer 0: Strips parenthetical, bracketed, or curly-brace tags."""
        self.assertEqual(DataHygieneService.clean_name("John Doe (We're hiring)"), "John Doe")
        self.assertEqual(DataHygieneService.clean_name("Sarah (she/her)"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("Alex [Hiring AEs]"), "Alex")
        self.assertEqual(DataHygieneService.clean_name("Sam {Open to work}"), "Sam")
        self.assertEqual(DataHygieneService.clean_name("Emily (she/they) [Hiring]"), "Emily")

    def test_strip_attached_job_titles_and_separators(self):
        """Layer 0: Strips attached job titles after separators ( - , | , • , / , – , — )."""
        self.assertEqual(DataHygieneService.clean_name("John - VP of Sales"), "John")
        self.assertEqual(DataHygieneService.clean_name("Sarah | Founder & CEO"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("Bob • 2nd"), "Bob")
        self.assertEqual(DataHygieneService.clean_name("Alex / Tech Lead"), "Alex")
        self.assertEqual(DataHygieneService.clean_name("David – Head of Growth"), "David")
        self.assertEqual(DataHygieneService.clean_name("Elena — VP Marketing"), "Elena")

    def test_preserve_hyphenated_names_and_accents(self):
        """Layer 1: Preserves hyphenated personal names and accents."""
        self.assertEqual(DataHygieneService.clean_name("Mary-Jane Watson"), "Mary-Jane Watson")
        self.assertEqual(DataHygieneService.clean_name("Jean-Luc Picard"), "Jean-Luc Picard")
        self.assertEqual(DataHygieneService.clean_name("René Müller"), "René Müller")

    def test_strip_emojis_and_decorative_symbols(self):
        """Layer 0 & 2: Strips emojis and decorative symbols."""
        self.assertEqual(DataHygieneService.clean_name("Sarah 🚀✨"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("👑 Bob Vance 🔥"), "Bob Vance")
        self.assertEqual(DataHygieneService.clean_name("Alice • Smith 💼"), "Alice")

    def test_strip_formal_honorifics_and_suffixes(self):
        """Layer 0: Strips formal honorifics and professional/generational suffixes."""
        self.assertEqual(DataHygieneService.clean_name("Dr. John Doe, MD"), "John Doe")
        self.assertEqual(DataHygieneService.clean_name("Prof. Sarah Smith, PhD"), "Sarah Smith")
        self.assertEqual(DataHygieneService.clean_name("Jane Doe, PMP"), "Jane Doe")
        self.assertEqual(DataHygieneService.clean_name("Robert Downey Jr"), "Robert Downey")
        self.assertEqual(DataHygieneService.clean_name("William Gates III"), "William Gates")
        self.assertEqual(DataHygieneService.clean_name("Bob Vance, CPA"), "Bob Vance")
        self.assertEqual(DataHygieneService.clean_name("Jane Doe, Esq."), "Jane Doe")

    def test_name_casing_all_caps_and_particles(self):
        """Layer 1: Converts ALL-CAPS or all-lowercase to title case while preserving mixed-case particles."""
        self.assertEqual(DataHygieneService.clean_name("SARAH"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("sarah"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("SARAH DOE"), "Sarah Doe")
        self.assertEqual(DataHygieneService.clean_name("McCall"), "McCall")
        self.assertEqual(DataHygieneService.clean_name("O'Connor"), "O'Connor")
        self.assertEqual(DataHygieneService.clean_name("van der Merwe"), "van der Merwe")
        self.assertEqual(DataHygieneService.clean_name("de Silva"), "de Silva")

    def test_name_fallback_layer2_paranoia(self):
        """Layer 2 Paranoia: Gracefully falls back to original trimmed string if all characters were stripped."""
        self.assertEqual(DataHygieneService.clean_name("Dr."), "Dr.")
        self.assertEqual(DataHygieneService.clean_name("Mr."), "Mr.")
        self.assertEqual(DataHygieneService.clean_name("🚀"), "🚀")
        self.assertEqual(DataHygieneService.clean_name(""), "")
        self.assertEqual(DataHygieneService.clean_name(None), "")


class TestLeadFirstNameSanitizer(unittest.TestCase):
    """Test DataHygieneService.clean_first_name."""

    def test_extract_first_name_token(self):
        """Layer 0: Extracts single first name token."""
        self.assertEqual(DataHygieneService.clean_first_name("Sarah Smith"), "Sarah")
        self.assertEqual(DataHygieneService.clean_first_name("SARAH"), "Sarah")
        self.assertEqual(DataHygieneService.clean_first_name("John - VP of Sales"), "John")
        self.assertEqual(DataHygieneService.clean_first_name("Jane (she/her)"), "Jane")
        self.assertEqual(DataHygieneService.clean_first_name("Dr. Jane Doe"), "Jane")

    def test_handle_initials_in_first_name(self):
        """Layer 1: Advances past single letter initials to pick the actual first name."""
        self.assertEqual(DataHygieneService.clean_first_name("J. Robert Oppenheimer"), "Robert")
        self.assertEqual(DataHygieneService.clean_first_name("J Robert Oppenheimer"), "Robert")
        self.assertEqual(DataHygieneService.clean_first_name("A. B. Cooper"), "Cooper")
        # Single initial fallback
        self.assertEqual(DataHygieneService.clean_first_name("J."), "J")

    def test_hyphenated_first_name_and_punctuation(self):
        """Layer 1 & 2: Handles hyphenated first names and strips trailing punctuation."""
        self.assertEqual(DataHygieneService.clean_first_name("Jean-Luc Picard"), "Jean-Luc")
        self.assertEqual(DataHygieneService.clean_first_name("Mary-Jane Watson"), "Mary-Jane")
        self.assertEqual(DataHygieneService.clean_first_name("John,"), "John")
        self.assertEqual(DataHygieneService.clean_first_name(None), "")
        self.assertEqual(DataHygieneService.clean_first_name(""), "")


class TestCompanySanitizer(unittest.TestCase):
    """Test DataHygieneService.clean_company across all Three Paranoia Layers."""

    def test_strip_parenthetical_tags(self):
        """Layer 0: Strips parenthetical tags (YC W19, formerly Twitter, acquired by Google)."""
        self.assertEqual(DataHygieneService.clean_company("Substack (YC W19)"), "Substack")
        self.assertEqual(DataHygieneService.clean_company("X (formerly Twitter)"), "X")
        self.assertEqual(DataHygieneService.clean_company("DeepMind (acquired by Google)"), "DeepMind")
        self.assertEqual(DataHygieneService.clean_company("Figma [YC S12]"), "Figma")
        self.assertEqual(DataHygieneService.clean_company("OpenAI {Non-profit}"), "OpenAI")

    def test_strip_marketing_taglines_and_slogans(self):
        """Layer 0: Strips marketing slogans after delimiters ( - , | , : , • , – , — )."""
        self.assertEqual(DataHygieneService.clean_company("Notion - The all-in-one workspace"), "Notion")
        self.assertEqual(DataHygieneService.clean_company("Stripe | Financial Infrastructure"), "Stripe")
        self.assertEqual(DataHygieneService.clean_company("Datadog : Cloud Monitoring as a Service"), "Datadog")
        self.assertEqual(DataHygieneService.clean_company("Gong • Revenue Intelligence"), "Gong")
        self.assertEqual(DataHygieneService.clean_company("Ramp – Spend Management Platform"), "Ramp")
        self.assertEqual(DataHygieneService.clean_company("Brex — Corporate Cards & Spend Management"), "Brex")

    def test_preserve_hyphenated_company_names(self):
        """Layer 1: Preserves hyphenated company names without spaces."""
        self.assertEqual(DataHygieneService.clean_company("Hewlett-Packard"), "Hewlett-Packard")
        self.assertEqual(DataHygieneService.clean_company("Coca-Cola"), "Coca-Cola")
        self.assertEqual(DataHygieneService.clean_company("Mercedes-Benz"), "Mercedes-Benz")

    def test_strip_legal_entity_suffixes(self):
        """Layer 0: Strips legal entity suffixes (LLC, Inc, Corp, GmbH, Ltd, etc.)."""
        self.assertEqual(DataHygieneService.clean_company("Acme LLC"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme L.L.C."), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Apple, Inc."), "Apple")
        self.assertEqual(DataHygieneService.clean_company("Acme Incorporated"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Corp"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Corporation"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme GmbH"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Ltd"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Limited"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Pvt Ltd"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Pty Ltd"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme AG"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme PLC"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("Acme Company"), "Acme")

    def test_strip_domain_extensions(self):
        """Layer 1: Strips domain extensions and leading try/get/use."""
        self.assertEqual(DataHygieneService.clean_company("tryacme.io"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("getscale.ai"), "Scale")
        self.assertEqual(DataHygieneService.clean_company("usefathom.com"), "Fathom")
        self.assertEqual(DataHygieneService.clean_company("https://www.tryacme.io"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("acme.com"), "Acme")

    def test_casing_and_acronym_preservation(self):
        """Layer 1: Fixes ALL CAPS for names > 4 letters, while preserving short legitimate acronyms."""
        self.assertEqual(DataHygieneService.clean_company("APPLE, INC."), "Apple")
        self.assertEqual(DataHygieneService.clean_company("MICROSOFT CORP"), "Microsoft")
        self.assertEqual(DataHygieneService.clean_company("IBM"), "IBM")
        self.assertEqual(DataHygieneService.clean_company("AWS"), "AWS")
        self.assertEqual(DataHygieneService.clean_company("SAP"), "SAP")
        self.assertEqual(DataHygieneService.clean_company("BMW"), "BMW")
        self.assertEqual(DataHygieneService.clean_company("HP"), "HP")
        self.assertEqual(DataHygieneService.clean_company("GMC"), "GMC")

    def test_company_fallback_layer2_paranoia(self):
        """Layer 2 Paranoia: Falls back to original trimmed company if stripping leaves empty or single letter."""
        self.assertEqual(DataHygieneService.clean_company("LLC"), "LLC")
        self.assertEqual(DataHygieneService.clean_company("The Co"), "The Co")
        self.assertEqual(DataHygieneService.clean_company("A Inc"), "A Inc")
        self.assertEqual(DataHygieneService.clean_company("X"), "X")
        self.assertEqual(DataHygieneService.clean_company(""), "")
        self.assertEqual(DataHygieneService.clean_company(None), "")


class TestCleanEnrichmentValueIntegration(unittest.TestCase):
    """Test clean_enrichment_value routing with field_type."""

    def test_clean_enrichment_value_with_first_name(self):
        """Layer 1 & 2: Routes first_name through clean_first_name and scrubs poison values."""
        self.assertEqual(clean_enrichment_value("SARAH (she/her)", field_type="first_name"), "Sarah")
        self.assertEqual(clean_enrichment_value("J. Robert Oppenheimer", field_type="first_name"), "Robert")
        self.assertEqual(clean_enrichment_value("John - VP of Sales", field_type="first_name"), "John")
        self.assertEqual(clean_enrichment_value("None", field_type="first_name"), "")
        self.assertEqual(clean_enrichment_value(None, field_type="first_name"), "")

    def test_clean_enrichment_value_with_company(self):
        """Layer 1 & 2: Routes company through clean_company and scrubs poison values."""
        self.assertEqual(clean_enrichment_value("Notion - The all-in-one workspace", field_type="company"), "Notion")
        self.assertEqual(clean_enrichment_value("tryacme.io", field_type="company"), "Acme")
        self.assertEqual(clean_enrichment_value("APPLE, INC.", field_type="company"), "Apple")
        self.assertEqual(clean_enrichment_value("IBM", field_type="company"), "IBM")
        self.assertEqual(clean_enrichment_value("null", field_type="company"), "")
        self.assertEqual(clean_enrichment_value(None, field_type="company"), "")

    def test_clean_enrichment_value_without_field_type_preserves_behavior(self):
        """Layer 0 & 1: Preserves existing poison scrubbing when field_type is omitted."""
        self.assertEqual(clean_enrichment_value("  Acme\x00 Corp  "), "Acme Corp")
        self.assertEqual(clean_enrichment_value("Sarah"), "Sarah")
        self.assertEqual(clean_enrichment_value("undefined"), "")


if __name__ == "__main__":
    unittest.main()
