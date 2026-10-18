"""
Three-Layer Paranoia Framework Test Suite:
Issue 2: Lead Name & Company Slogan Sanitizer (The AI Slop Eliminator)

- Layer 0 (Foundational): Core personal name, first name, and company name cleaning;
  standard {{first_name}} and {{company}} template interpolation.
- Layer 1 (Environmental Failure Analysis): 20+ real-world scraping artifacts,
  bracketed hiring/status announcements, recruitment emojis, attached titles,
  initials, international and Dutch name particles, domain company names,
  short acronym vs. brand capitalization, missing/None fallback values,
  pipe fallbacks, and spintax integration.
- Layer 2 (Human Paranoia): Malicious/messy inputs, title-only inputs ('Dr.'),
  only punctuation, single letter brands, poison strings ('None', 'null', 'undefined'),
  and accidental duplicate whitespace or punctuation removal.
"""

import unittest
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

from leads.backend.services.data_hygiene import DataHygieneService
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.services.template_spintax_guard import clean_enrichment_value


class TestLeadNameAndCompanySanitizerParanoia(unittest.TestCase):
    """
    Comprehensive verification battery for Issue 2 Lead Name & Company Slogan Sanitizer.
    Enforces Paranoia Layers 0, 1, and 2 across data hygiene and campaign node execution.
    """

    def setUp(self):
        self.executor = EleInNodeExecutor(linkedin_worker=None, supabase=None, workspace_id="ws-sanitizer-test")

    # =========================================================================
    # LAYER 0: FOUNDATIONAL SANITIZATION & INTERPOLATION
    # =========================================================================

    def test_layer0_clean_name_basic(self):
        """Layer 0: Standard name cleaning cleans trailing spaces and fixes casing."""
        self.assertEqual(DataHygieneService.clean_name("SARAH"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("sarah"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("  Sarah Miller  "), "Sarah Miller")

    def test_layer0_clean_first_name_basic(self):
        """Layer 0: Extracts the primary single first name token."""
        self.assertEqual(DataHygieneService.clean_first_name("Sarah"), "Sarah")
        self.assertEqual(DataHygieneService.clean_first_name("Sarah Miller"), "Sarah")
        self.assertEqual(DataHygieneService.clean_first_name("SARAH CONNOR"), "Sarah")

    def test_layer0_clean_company_basic(self):
        """Layer 0: Standard company cleaning strips legal entity suffixes."""
        self.assertEqual(DataHygieneService.clean_company("Notion, Inc."), "Notion")
        self.assertEqual(DataHygieneService.clean_company("Stripe LLC"), "Stripe")
        self.assertEqual(DataHygieneService.clean_company("Linear Corp"), "Linear")

    def test_layer0_template_interpolation_basic(self):
        """Layer 0: Basic template interpolation with standard clean values."""
        template = "Hey {{first_name}}, loved your recent updates at {{company}}!"
        data = {
            "lead": {
                "first_name": "Sarah",
                "company": "Notion",
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hey Sarah, loved your recent updates at Notion!")

    # =========================================================================
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS (20+ REAL-WORLD SCRAPING EDGE CASES)
    # =========================================================================

    def test_layer1_name_recruitment_tags_and_emojis(self):
        """
        Layer 1: Strips bracketed hiring notices, emojis, and decorative symbols.
        - "SARAH (WE'RE HIRING!)" -> "Sarah"
        - "🔥 Alex Rodriguez [Hiring AEs] 🔥" -> "Alex" (first_name), "Alex Rodriguez" (name)
        """
        # First name extraction
        self.assertEqual(DataHygieneService.clean_first_name("SARAH (WE'RE HIRING!)"), "Sarah")
        self.assertEqual(DataHygieneService.clean_name("SARAH (WE'RE HIRING!)"), "Sarah")

        self.assertEqual(DataHygieneService.clean_first_name("🔥 Alex Rodriguez [Hiring AEs] 🔥"), "Alex")
        self.assertEqual(DataHygieneService.clean_name("🔥 Alex Rodriguez [Hiring AEs] 🔥"), "Alex Rodriguez")

    def test_layer1_name_honorifics_and_professional_credentials(self):
        """
        Layer 1: Strips prefixes (Dr., Prof.) and suffixes (PhD, PMP, MD, MBA, CPA).
        - "Dr. Jonathan Smith, PhD, PMP" -> "Jonathan" (first_name), "Jonathan Smith" (name)
        """
        raw = "Dr. Jonathan Smith, PhD, PMP"
        self.assertEqual(DataHygieneService.clean_first_name(raw), "Jonathan")
        self.assertEqual(DataHygieneService.clean_name(raw), "Jonathan Smith")

        # Multi-prefix / suffix variations
        self.assertEqual(DataHygieneService.clean_first_name("Prof. Dr. Emily Watson, MD"), "Emily")
        self.assertEqual(DataHygieneService.clean_name("Prof. Dr. Emily Watson, MD"), "Emily Watson")

    def test_layer1_name_attached_role_and_separator(self):
        """
        Layer 1: Strips job title attached after hyphen, pipe, bullet, or slash.
        - "Sarah Miller - VP of Growth @ Fintech" -> "Sarah" (first_name), "Sarah Miller" (name)
        """
        cases = [
            ("Sarah Miller - VP of Growth @ Fintech", "Sarah", "Sarah Miller"),
            ("Sarah Miller | Founder & CEO", "Sarah", "Sarah Miller"),
            ("Sarah Miller • Keynote Speaker & Advisor", "Sarah", "Sarah Miller"),
            ("Sarah Miller / Chief Revenue Officer", "Sarah", "Sarah Miller"),
            ("Sarah Miller — Head of Sales", "Sarah", "Sarah Miller"),
        ]
        for raw, expected_first, expected_full in cases:
            self.assertEqual(DataHygieneService.clean_first_name(raw), expected_first, f"Failed first on {raw}")
            self.assertEqual(DataHygieneService.clean_name(raw), expected_full, f"Failed full on {raw}")

    def test_layer1_name_initials_handling(self):
        """
        Layer 1: Intelligently skips single-letter initials to extract real given name.
        - "J. Robert Oppenheimer" -> "Robert" (first_name)
        """
        self.assertEqual(DataHygieneService.clean_first_name("J. Robert Oppenheimer"), "Robert")
        self.assertEqual(DataHygieneService.clean_first_name("J Robert Oppenheimer"), "Robert")
        self.assertEqual(DataHygieneService.clean_first_name("A. B. Cooper"), "Cooper")

    def test_layer1_name_casing_preservation(self):
        """
        Layer 1: Preserves internal casing and particles for Celtic, Dutch, and French names.
        - "O'Connor", "McDonald", "van der Berg", "de Silva"
        """
        self.assertEqual(DataHygieneService.clean_name("O'Connor"), "O'Connor")
        self.assertEqual(DataHygieneService.clean_name("McDonald"), "McDonald")
        self.assertEqual(DataHygieneService.clean_name("van der Berg"), "van der Berg")
        self.assertEqual(DataHygieneService.clean_name("de Silva"), "de Silva")

        # Mixed casing in full names
        self.assertEqual(DataHygieneService.clean_name("Cillian O'Connor"), "Cillian O'Connor")
        self.assertEqual(DataHygieneService.clean_name("Ronald McDonald"), "Ronald McDonald")
        self.assertEqual(DataHygieneService.clean_name("Vincent van der Berg"), "Vincent van der Berg")
        self.assertEqual(DataHygieneService.clean_first_name("Vincent van der Berg"), "Vincent")

        # All-caps particle normalization
        self.assertEqual(DataHygieneService.clean_name("RONALD MCDONALD"), "Ronald McDonald")
        self.assertEqual(DataHygieneService.clean_name("CILLIAN O'CONNOR"), "Cillian O'Connor")

    def test_layer1_name_pronouns(self):
        """
        Layer 1: Strips bracketed or parenthesized gender pronouns.
        - "Emily Watson (she/her)" -> "Emily" (first_name), "Emily Watson" (name)
        """
        self.assertEqual(DataHygieneService.clean_first_name("Emily Watson (she/her)"), "Emily")
        self.assertEqual(DataHygieneService.clean_name("Emily Watson (she/her)"), "Emily Watson")
        self.assertEqual(DataHygieneService.clean_first_name("David Clark [he/him/his]"), "David")
        self.assertEqual(DataHygieneService.clean_name("David Clark [he/him/his]"), "David Clark")
        self.assertEqual(DataHygieneService.clean_first_name("Taylor Swift {they/them}"), "Taylor")

    def test_layer1_company_marketing_slogans_and_taglines(self):
        """
        Layer 1: Strips marketing slogans, value props, and taglines after separators.
        - "Notion - The all-in-one workspace for notes, docs, and tasks" -> "Notion"
        - "Stripe, Inc. | Financial infrastructure for the internet" -> "Stripe"
        - "Datadog: Cloud Monitoring as a Service" -> "Datadog"
        - "Linear • Issue tracking software" -> "Linear"
        """
        self.assertEqual(
            DataHygieneService.clean_company("Notion - The all-in-one workspace for notes, docs, and tasks"),
            "Notion",
        )
        self.assertEqual(
            DataHygieneService.clean_company("Stripe, Inc. | Financial infrastructure for the internet"),
            "Stripe",
        )
        self.assertEqual(
            DataHygieneService.clean_company("Datadog: Cloud Monitoring as a Service"),
            "Datadog",
        )
        self.assertEqual(
            DataHygieneService.clean_company("Linear • Issue tracking software"),
            "Linear",
        )

    def test_layer1_company_accelerator_and_acquisition_tags(self):
        """
        Layer 1: Strips accelerator cohorts and former company names in parentheses.
        - "Ramp (YC W19) - Spend Management Platform" -> "Ramp"
        """
        self.assertEqual(
            DataHygieneService.clean_company("Ramp (YC W19) - Spend Management Platform"),
            "Ramp",
        )
        self.assertEqual(
            DataHygieneService.clean_company("X (formerly Twitter)"),
            "X",
        )
        self.assertEqual(
            DataHygieneService.clean_company("DeepMind (acquired by Google)"),
            "DeepMind",
        )

    def test_layer1_company_domain_import_sanitization(self):
        """
        Layer 1: Converts website domains into clean company names, stripping 'try', 'get', 'use'.
        - "tryacme.io" -> "Acme"
        - "getscale.ai" -> "Scale"
        - "usefathom.com" -> "Fathom"
        """
        self.assertEqual(DataHygieneService.clean_company("tryacme.io"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("getscale.ai"), "Scale")
        self.assertEqual(DataHygieneService.clean_company("usefathom.com"), "Fathom")
        self.assertEqual(DataHygieneService.clean_company("https://www.tryacme.io"), "Acme")
        self.assertEqual(DataHygieneService.clean_company("linear.app"), "Linear")

    def test_layer1_company_acronym_preservation(self):
        """
        Layer 1: Preserves short legitimate corporate acronyms (<= 4 chars).
        - "IBM, Corporation" -> "IBM"
        """
        self.assertEqual(DataHygieneService.clean_company("IBM, Corporation"), "IBM")
        self.assertEqual(DataHygieneService.clean_company("AWS, LLC"), "AWS")
        self.assertEqual(DataHygieneService.clean_company("SAP AG"), "SAP")
        self.assertEqual(DataHygieneService.clean_company("HP, Inc."), "HP")
        self.assertEqual(DataHygieneService.clean_company("BMW Group"), "BMW Group")

    def test_layer1_company_article_and_suffix_stripping(self):
        """
        Layer 1: Strips redundant leading 'The ' when followed by brand name and entity suffix.
        - "The Coca-Cola Company" -> "Coca-Cola"
        """
        self.assertEqual(DataHygieneService.clean_company("The Coca-Cola Company"), "Coca-Cola")
        self.assertEqual(DataHygieneService.clean_company("The Walt Disney Company"), "Walt Disney")

    def test_layer1_company_comprehensive_legal_entities(self):
        """
        Layer 1: Strips diverse international legal entity suffixes.
        (LLC, L.L.C., Inc, Corp, GmbH, Ltd, Pty Ltd, Pvt Ltd, SA, BV, PLC)
        """
        entities = [
            ("Acme LLC", "Acme"),
            ("Acme L.L.C.", "Acme"),
            ("Acme, Inc.", "Acme"),
            ("Acme Incorporated", "Acme"),
            ("Acme Corp.", "Acme"),
            ("Acme Corporation", "Acme"),
            ("Acme Ltd.", "Acme"),
            ("Acme Limited", "Acme"),
            ("Acme GmbH", "Acme"),
            ("Acme Pty Ltd", "Acme"),
            ("Acme Pvt Ltd", "Acme"),
            ("Acme B.V.", "Acme"),
            ("Acme PLC", "Acme"),
        ]
        for raw, expected in entities:
            self.assertEqual(DataHygieneService.clean_company(raw), expected, f"Failed on {raw}")

    def test_layer1_dirty_lead_template_interpolation(self):
        """
        Layer 1: Interpolating a dirty scraped lead cleans first name and company.
        - Template: "Hey {{first_name}}, loved your recent updates at {{company}}!"
        - Lead: {"first_name": "SARAH (WE'RE HIRING!)", "company": "Notion, Inc. - The all-in-one workspace"}
        - Output: "Hey Sarah, loved your recent updates at Notion!"
        """
        template = "Hey {{first_name}}, loved your recent updates at {{company}}!"
        data = {
            "lead": {
                "first_name": "SARAH (WE'RE HIRING!)",
                "company": "Notion, Inc. - The all-in-one workspace",
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hey Sarah, loved your recent updates at Notion!")

    def test_layer1_missing_values_template_fallback(self):
        """
        Layer 1: Missing values safely fall back to 'there' and 'your company'.
        - Lead: {"first_name": None, "company": None}
        - Output: "Hey there, loved your recent updates at your company!"
        """
        template = "Hey {{first_name}}, loved your recent updates at {{company}}!"
        data = {
            "lead": {
                "first_name": None,
                "company": None,
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hey there, loved your recent updates at your company!")

    def test_layer1_explicit_clean_variable_tags(self):
        """
        Layer 1: Explicit {{first_name_clean}} and {{company_clean}} tags resolve correctly.
        """
        template = "Hi {{first_name_clean}}, congratulations on the work at {{company_clean}}!"
        data = {
            "lead": {
                "first_name": "🔥 Alex Rodriguez [Hiring AEs] 🔥",
                "company": "Stripe, Inc. | Financial infrastructure for the internet",
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hi Alex, congratulations on the work at Stripe!")

    def test_layer1_spintax_with_dirty_lead_interpolation(self):
        """
        Layer 1: Deterministic spintax resolution works seamlessly alongside sanitized variables.
        """
        template = "{Hi|Hello|Hey} {{first_name}}, big fan of {{company}}!"
        data = {
            "lead": {
                "first_name": "SARAH (WE'RE HIRING!)",
                "company": "Notion - The all-in-one workspace",
            }
        }
        res = self.executor._interpolate_template(template, data, "https://linkedin.com/in/sarah")
        self.assertTrue(res.startswith(("Hi Sarah", "Hello Sarah", "Hey Sarah")))
        self.assertIn("fan of Notion!", res)

    def test_layer1_pipe_fallback_syntax(self):
        """
        Layer 1: {{first_name | fallback}} pipe syntax resolves inline fallbacks when missing,
        and uses sanitized values when present.
        """
        template = "Hey {{first_name | friend}}, how are things at {{company | your team}}?"

        # Case A: Missing
        res_missing = self.executor._interpolate_template(template, {"lead": {}}, None)
        self.assertEqual(res_missing, "Hey friend, how are things at your team?")

        # Case B: Dirty present
        data_dirty = {
            "lead": {
                "first_name": "SARAH (WE'RE HIRING!)",
                "company": "Stripe, Inc. | Financial infrastructure",
            }
        }
        res_dirty = self.executor._interpolate_template(template, data_dirty, None)
        self.assertEqual(res_dirty, "Hey Sarah, how are things at Stripe?")

    def test_layer1_enrichment_field_type_guard(self):
        """
        Layer 1: clean_enrichment_value applies field-specific hygiene when field_type is passed.
        """
        self.assertEqual(
            clean_enrichment_value("SARAH (WE'RE HIRING!)", field_type="first_name"),
            "Sarah",
        )
        self.assertEqual(
            clean_enrichment_value("Notion, Inc. - Notes and Docs", field_type="company"),
            "Notion",
        )
        # Poison strings scrubbed to empty
        self.assertEqual(clean_enrichment_value("None", field_type="first_name"), "")
        self.assertEqual(clean_enrichment_value("null", field_type="company"), "")
        self.assertEqual(clean_enrichment_value("undefined", field_type="company"), "")

    # =========================================================================
    # LAYER 2: HUMAN PARANOIA (EXTREME USER INPUTS & BOUNDARY DEFENSES)
    # =========================================================================

    def test_layer2_single_letter_or_title_fallback(self):
        """
        Layer 2: When stripped candidate is empty or literally just an honorific,
        gracefully falls back to original trimmed string or stripped honorific.
        - "Dr." -> "Dr" or "Dr."
        """
        self.assertIn(DataHygieneService.clean_name("Dr."), ("Dr", "Dr."))
        self.assertIn(DataHygieneService.clean_first_name("Dr."), ("Dr", "Dr."))
        self.assertIn(DataHygieneService.clean_name("Prof."), ("Prof", "Prof."))

    def test_layer2_single_letter_company_or_initial(self):
        """
        Layer 2: Single-letter company names (like 'X' or 'A') or single initials are preserved.
        """
        self.assertEqual(DataHygieneService.clean_company("X"), "X")
        self.assertEqual(DataHygieneService.clean_company("A"), "A")
        self.assertEqual(DataHygieneService.clean_first_name("J."), "J")

    def test_layer2_only_punctuation_or_entity_fallbacks(self):
        """
        Layer 2: Extreme user inputs like only punctuation or only entity names fall back safely.
        - "LLC" -> "LLC"
        - "The Co" -> "The Co"
        - "-" -> "-"
        """
        self.assertEqual(DataHygieneService.clean_company("LLC"), "LLC")
        self.assertEqual(DataHygieneService.clean_company("The Co"), "The Co")
        self.assertEqual(DataHygieneService.clean_company("-"), "-")
        self.assertEqual(DataHygieneService.clean_company("--"), "--")

    def test_layer2_null_empty_type_safety(self):
        """
        Layer 2: Type safety for None, empty, whitespace, and non-string types.
        """
        self.assertEqual(DataHygieneService.clean_name(None), "")
        self.assertEqual(DataHygieneService.clean_name(""), "")
        self.assertEqual(DataHygieneService.clean_name("   "), "")
        self.assertEqual(DataHygieneService.clean_name(12345), "12345")

        self.assertEqual(DataHygieneService.clean_first_name(None), "")
        self.assertEqual(DataHygieneService.clean_first_name(""), "")
        self.assertEqual(DataHygieneService.clean_first_name("   "), "")

        self.assertEqual(DataHygieneService.clean_company(None), "")
        self.assertEqual(DataHygieneService.clean_company(""), "")
        self.assertEqual(DataHygieneService.clean_company("   "), "")

    def test_layer2_unresolved_variable_stripped_without_corrupting_text(self):
        """
        Layer 2: Unresolved variables in templates are stripped cleanly
        without leaving orphan braces or duplicate spaces.
        """
        template = "Hey {{first_name}}, check out {{non_existent_field}} at {{company}}!"
        data = {
            "lead": {
                "first_name": "SARAH (WE'RE HIRING!)",
                "company": "Notion - The all-in-one workspace",
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hey Sarah, check out at Notion!")
        self.assertNotIn("{{", res)
        self.assertNotIn("}}", res)

    def test_layer2_case_insensitivity_and_namespaces(self):
        """
        Layer 2: Template engine handles uppercase variable tags like {{FIRST_NAME}}
        and namespace tags like {{lead.first_name}} cleanly with sanitization.
        """
        template = "Hello {{FIRST_NAME}} and {{lead.company}}!"
        data = {
            "lead": {
                "first_name": "SARAH (WE'RE HIRING!)",
                "company": "Stripe, Inc. | Financial infrastructure",
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hello Sarah and Stripe!")


if __name__ == "__main__":
    unittest.main()
