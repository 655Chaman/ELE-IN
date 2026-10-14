"""
Three-Layer Paranoia Framework Unit Test Suite — Step 34 Track A:
AI Prompt Template Variable Sanitization, Missing-Fallback Guard & Spintax Syntax Balance Validator
"""
import os
import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from campaigns.backend.services.template_spintax_guard import (
    clean_enrichment_value,
    validate_template_and_spintax_syntax,
    resolve_spintax,
)
from campaigns.backend.services.elein_orchestrator import interpolate
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.routers.elein import validate_campaign_variables, ALLOWED_TEMPLATE_VARS


class TestTemplateSpintaxAndFallbackGuard(unittest.TestCase):
    # =========================================================================
    # 1. Poison Enrichment Value Sanitization (Layer 1)
    # =========================================================================

    def test_clean_enrichment_value_scrubs_poison_strings(self):
        """Paranoia Layer 1: Poison strings ('None', 'null', 'undefined', 'N/A', 'nan', '-') scrub to ''."""
        for poison in ("None", "none", "null", "NULL", "undefined", "N/A", "n/a", "nan", "NaN", "[object Object]", "-", "--", "unknown", None, False):
            self.assertEqual(clean_enrichment_value(poison), "", f"Failed to scrub poison value: {poison!r}")

        self.assertEqual(clean_enrichment_value("  Acme\x00 Corp  "), "Acme Corp")
        self.assertEqual(clean_enrichment_value("Sarah"), "Sarah")

    def test_orchestrator_interpolate_scrubs_poison_values_and_uses_fallback(self):
        """Paranoia Layer 1: Orchestrator interpolate replaces 'None'/'null' lead fields with fallbacks instead of 'Hi None'."""
        opp = {
            "id": "lead_1",
            "kdm_first": "None",
            "company_name": "null",
            "job_title": "undefined",
        }
        msg = interpolate("Hi {{first_name}}, saw your work at {{company | your organization}} as {{job_title | a leader}}!", opp)
        self.assertEqual(msg, "Hi there, saw your work at your organization as a leader!")

    def test_executor_interpolate_template_supports_pipe_fallback_and_scrubs_poison(self):
        """Paranoia Layer 0 & 1: Executor _interpolate_template supports {{var | fallback}} and scrubs poison literals."""
        mock_worker = MagicMock()
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        executor = EleInNodeExecutor(worker=mock_worker, supabase=mock_sb, workspace_id="ws_1")

        # Lead has poison strings 'None' and 'N/A'
        data = {
            "lead": {
                "first_name": "None",
                "company": "N/A",
                "title": "VP of Engineering",
            }
        }
        tpl = "{Hi|Hello} {{first_name | friend}}, noticed {{company | your engineering team}} is scaling for {{title}}s."
        rendered = executor._interpolate_template(tpl, data, "https://www.linkedin.com/in/test")
        self.assertIn(rendered, [
            "Hi friend, noticed your engineering team is scaling for VP of Engineerings.",
            "Hello friend, noticed your engineering team is scaling for VP of Engineerings.",
        ])
        self.assertNotIn("None", rendered)
        self.assertNotIn("N/A", rendered)
        self.assertNotIn("{{", rendered)

    # =========================================================================
    # 2. Spintax Resolution & Determinism (Layer 0 & 1)
    # =========================================================================

    def test_resolve_spintax_nested_and_deterministic_seed(self):
        """Paranoia Layer 0 & 1: Resolves flat and nested spintax deterministically with seed without touching {{vars}}."""
        tpl = "{Hi {there|friend}|Hello} {{first_name}}, {wanted to connect|reaching out}!"
        out1 = resolve_spintax(tpl, seed="lead_abc_123")
        out2 = resolve_spintax(tpl, seed="lead_abc_123")
        self.assertEqual(out1, out2)
        self.assertIn("{{first_name}}", out1)
        self.assertNotIn("|", out1)

    # =========================================================================
    # 3. Pre-Activation Syntax & Balance Validation (Layer 2 Human Paranoia)
    # =========================================================================

    def test_validate_template_and_spintax_syntax_detects_unclosed_double_braces(self):
        """Paranoia Layer 2: Detects '{{first_name' or '{{first_name}' mismatched braces."""
        res1 = validate_template_and_spintax_syntax("Hi {{first_name, welcome aboard!", ALLOWED_TEMPLATE_VARS)
        self.assertFalse(res1["valid"])

        res2 = validate_template_and_spintax_syntax("Hi {{first_name}, welcome aboard!", ALLOWED_TEMPLATE_VARS)
        self.assertFalse(res2["valid"])

        res3 = validate_template_and_spintax_syntax("Hi first_name}}, welcome aboard!", ALLOWED_TEMPLATE_VARS)
        self.assertFalse(res3["valid"])

    def test_validate_template_and_spintax_syntax_detects_unbalanced_spintax(self):
        """Paranoia Layer 2: Detects unclosed '{Hi|Hello' or unmatched '}' or empty '{|}'."""
        res_unclosed = validate_template_and_spintax_syntax("{Hi|Hello {{first_name}}, how are you?", ALLOWED_TEMPLATE_VARS)
        self.assertFalse(res_unclosed["valid"])
        self.assertTrue(any("Unclosed opening brace" in e for e in res_unclosed["errors"]))

        res_unmatched = validate_template_and_spintax_syntax("Hi|Hello} {{first_name}}", ALLOWED_TEMPLATE_VARS)
        self.assertFalse(res_unmatched["valid"])
        self.assertTrue(any("Unmatched closing brace" in e for e in res_unmatched["errors"]))

        res_empty = validate_template_and_spintax_syntax("{|} {{first_name}}", ALLOWED_TEMPLATE_VARS)
        self.assertFalse(res_empty["valid"])

    def test_validate_campaign_variables_blocks_malformed_braces_and_invalid_vars_400(self):
        """Paranoia Layer 2: validate_campaign_variables raises HTTP 400 on unclosed braces, unbalanced spintax, or unknown vars."""
        # 1. Unclosed variable brace
        with self.assertRaises(HTTPException) as ctx1:
            validate_campaign_variables([{"id": "n1", "data": {"message": "Hello {{first_name, how is work?"}}])
        self.assertEqual(ctx1.exception.status_code, 400)

        # 2. Unbalanced spintax
        with self.assertRaises(HTTPException) as ctx2:
            validate_campaign_variables([{"id": "n1", "data": {"message": "{Hi|Hey {{first_name}}"}}])
        self.assertEqual(ctx2.exception.status_code, 400)

        # 3. Unknown variable
        with self.assertRaises(HTTPException) as ctx3:
            validate_campaign_variables([{"id": "n1", "data": {"message": "Hi {{secret_ssn}}"}}])
        self.assertEqual(ctx3.exception.status_code, 400)
        self.assertIn("Invalid template variable", ctx3.exception.detail)

        # 4. Valid spintax + pipe fallback + lead. prefix passes cleanly
        validate_campaign_variables([
            {
                "id": "n1",
                "data": {
                    "message": "{Hi|Hello} {{lead.first_name | there}}, saw {{company | your team}} is growing!"
                },
            }
        ])


if __name__ == "__main__":
    unittest.main()
