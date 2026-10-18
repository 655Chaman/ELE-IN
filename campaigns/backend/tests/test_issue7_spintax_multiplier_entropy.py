"""
Three-Layer Paranoia Framework Unit Test Suite — Issue 7:
Linguistic Spintax Multiplier, Combinatorial Variation Calculator & Entropy Guard

Layer 0 (Foundational):
- Spintax combinations accurately calculated across nested, branched, and sequential blocks.
- Spintax entropy and diversity ratio evaluated against lead campaign volume.
- B2B cold outreach synonyms injected across greetings, openers, connectors, CTAs, and sign-offs.
- Deterministic deduplicated previews generated with reproducible seeds.

Layer 1 (Environmental):
- Massive combinations capped at 100,000,000.
- Safe handling of zero/negative lead counts, poison literals, null/empty strings.
- {{variable | fallback}} double-braces masked and protected.

Layer 2 (Human Paranoia):
- Syntax validation pre-check catches unclosed braces and flags invalid spintax.
- Existing spintax and variables protected against corruption or double-nesting.
- Variant count clamped between 1 and 20.
"""

import os
import unittest

if not os.environ.get("COOKIE_PUBLIC_KEY"):
    os.environ["COOKIE_PUBLIC_KEY"] = (
        "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFqRnJpSlhYaUJtbENKVHRLUXNTdQpiWFEyaE1KNUtDTHk5SVc4c05hQ1hzWnloeVRGNmUvOFlFT0dVT28xWDMvdWcrakd1YzV1T1pRSzRDekx4K2t0CktsdWN1TDAyMzhham9jSmJsZGF1bHo4TCtpcGlrSkhMbHErMWdpRU9GdWsvM2FTdS91MXBKREl3b3l5N3RqcUwKR3NIOVU4eFpsQlJNZUkyZCtUNEQvc2QvdlJxSGN0U1hGOStHSGxXUEMwdXgvdWRENEwvZHZqU1BKdVpsb0JGMgp4eTBveEVnOVQycGtOajFlSlBmZGxiTmJzMDI4ZHh2RytZQU02RnNnNnBwVnhVa3hzYkk0ZVhKbk1kUzRBUUw0CnJOcDBmVzJrWXFrQ3ZDNzI1VkpNODByZTdURkFDSFg4ekx2TlFLQkV1TldEeERKMDhlMFVrd2tIcU1Yc1J0NUkKTlFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="
    )

from campaigns.backend.services.template_spintax_guard import (
    calculate_spintax_combinations,
    calculate_spintax_entropy,
    generate_linguistic_spintax,
    preview_spintax_variants,
    resolve_spintax,
    validate_template_and_spintax_syntax,
)


class TestIssue7SpintaxMultiplierAndEntropy(unittest.TestCase):

    # =========================================================================
    # 1. Combinatorial Spintax Multiplier (Layer 0 & 1)
    # =========================================================================

    def test_calculate_spintax_combinations_nested_structures(self):
        """Paranoia Layer 0: Accurately computes combinations for single, nested, and sequential spintax."""
        # 1. Single nested spintax from spec: {opt1|opt2|{opt3|opt4}} = 1 + 1 + 2 = 4
        self.assertEqual(calculate_spintax_combinations("{opt1|opt2|{opt3|opt4}}"), 4)

        # 2. Sequential spintax blocks: {Hi|Hello} {{first_name}}, {wanted to reach out|reaching out}! = 2 * 2 = 4
        self.assertEqual(
            calculate_spintax_combinations("{Hi|Hello} {{first_name}}, {wanted to reach out|reaching out}!"),
            4
        )

        # 3. Deeply nested & branched: {Hi {there|friend}|Hello|Hey {pal|buddy}} = 2 + 1 + 2 = 5
        self.assertEqual(
            calculate_spintax_combinations("{Hi {there|friend}|Hello|Hey {pal|buddy}}"),
            5
        )

        # 4. Multi-item branch: {A {1|2} B {X|Y}|C} = (2 * 2) + 1 = 5
        self.assertEqual(
            calculate_spintax_combinations("{A {1|2} B {X|Y}|C}"),
            5
        )

    def test_calculate_spintax_combinations_masks_double_braces(self):
        """Paranoia Layer 1: Liquid/Mustache {{variable}} and {{var | fallback}} pipes are masked and never counted."""
        tpl_pipe = "Hello {{first_name | there}}, saw your work at {{company | your company}}!"
        self.assertEqual(calculate_spintax_combinations(tpl_pipe), 1)

        tpl_mixed = "{Hi|Hello} {{first_name | friend}}, {reaching out|connecting} with {{company | your team}}!"
        self.assertEqual(calculate_spintax_combinations(tpl_mixed), 4)

    def test_calculate_spintax_combinations_safety_caps_and_empty_inputs(self):
        """Paranoia Layer 1: Clamps return to 100,000,000 and returns 1 on empty/no spintax."""
        self.assertEqual(calculate_spintax_combinations(""), 1)
        self.assertEqual(calculate_spintax_combinations(None), 1)
        self.assertEqual(calculate_spintax_combinations("Plain cold outreach message."), 1)
        self.assertEqual(calculate_spintax_combinations("{not a spintax choice}"), 1)

        # 20 spintax blocks of 3 choices each = 3^20 = 3,486,784,401 > 100,000,000
        massive = " ".join(["{A|B|C}"] * 20)
        combs = calculate_spintax_combinations(massive)
        self.assertEqual(combs, 100_000_000)

    # =========================================================================
    # 2. Spintax Entropy & ESP Spam Resistance (Layer 0, 1 & 2)
    # =========================================================================

    def test_calculate_spintax_entropy_invalid_syntax_handled_gracefully(self):
        """Paranoia Layer 2: Invalid template syntax returns INVALID rating without throwing exceptions."""
        res_unclosed = calculate_spintax_entropy("{Hi|Hello {{first_name}}")
        self.assertFalse(res_unclosed["valid"])
        self.assertEqual(res_unclosed["entropy_rating"], "INVALID")
        self.assertTrue(len(res_unclosed["errors"]) > 0)
        self.assertEqual(res_unclosed["total_combinations"], 0)

        res_malformed_var = calculate_spintax_entropy("Hi {{first_name, how are you?")
        self.assertFalse(res_malformed_var["valid"])
        self.assertEqual(res_malformed_var["entropy_rating"], "INVALID")

    def test_calculate_spintax_entropy_ratings_and_diversity_ratios(self):
        """Paranoia Layer 0: Correctly evaluates diversity ratio and assigns entropy ratings."""
        # 1. CRITICAL_SPAM_RISK: < 5 combinations
        res_crit = calculate_spintax_entropy("{Hi|Hello} {{first_name}}", campaign_lead_count=100)
        self.assertTrue(res_crit["valid"])
        self.assertEqual(res_crit["total_combinations"], 2)
        self.assertEqual(res_crit["diversity_ratio"], 0.02)
        self.assertEqual(res_crit["entropy_rating"], "CRITICAL_SPAM_RISK")
        self.assertTrue(any("greeting" not in r.lower() or "add spintax" in r.lower() for r in res_crit["recommendations"]))

        # 2. CRITICAL_SPAM_RISK via low diversity ratio (< 0.05) even if combinations >= 5
        res_low_ratio = calculate_spintax_entropy("{A|B|C} {D|E|F}", campaign_lead_count=1000)
        self.assertEqual(res_low_ratio["total_combinations"], 9)
        self.assertEqual(res_low_ratio["diversity_ratio"], 0.009)
        self.assertEqual(res_low_ratio["entropy_rating"], "CRITICAL_SPAM_RISK")

        # 3. MODERATE_VARIATION: 5 <= combinations < 50 and diversity_ratio >= 0.05
        # 3 * 3 = 9 combinations with 100 leads => ratio = 0.09 >= 0.05
        res_mod = calculate_spintax_entropy("{A|B|C} {D|E|F}", campaign_lead_count=100)
        self.assertEqual(res_mod["total_combinations"], 9)
        self.assertEqual(res_mod["diversity_ratio"], 0.09)
        self.assertEqual(res_mod["entropy_rating"], "MODERATE_VARIATION")

        # 4. HIGH_DIVERSITY: 50 <= combinations < 200 and diversity_ratio >= 0.05
        # 3 * 3 * 3 * 3 = 81 combinations with 500 leads => ratio = 0.162 >= 0.05
        res_high = calculate_spintax_entropy("{A|B|C} {D|E|F} {G|H|I} {J|K|L}", campaign_lead_count=500)
        self.assertEqual(res_high["total_combinations"], 81)
        self.assertEqual(res_high["entropy_rating"], "HIGH_DIVERSITY")

        # 5. ENTERPRISE_IMMUNITY: combinations >= 200 and diversity_ratio >= 0.05
        # 3^5 = 243 combinations with 1000 leads => ratio = 0.243 >= 0.05
        res_enterprise = calculate_spintax_entropy("{A|B|C} {D|E|F} {G|H|I} {J|K|L} {M|N|O}", campaign_lead_count=1000)
        self.assertEqual(res_enterprise["total_combinations"], 243)
        self.assertEqual(res_enterprise["entropy_rating"], "ENTERPRISE_IMMUNITY")

    def test_calculate_spintax_entropy_max_depth_detection(self):
        """Paranoia Layer 0: Tracks max spintax nesting depth accurately."""
        res_flat = calculate_spintax_entropy("{Hi|Hello} {{first_name}}")
        self.assertEqual(res_flat["max_depth_detected"], 1)

        res_nested = calculate_spintax_entropy("{A|{B|C}}")
        self.assertEqual(res_nested["max_depth_detected"], 2)

        res_none = calculate_spintax_entropy("Plain text without spintax {{name}}")
        self.assertEqual(res_none["max_depth_detected"], 0)

    # =========================================================================
    # 3. Linguistic Spintax Multiplier Generator (Layer 0, 1 & 2)
    # =========================================================================

    def test_generate_linguistic_spintax_replaces_all_categories_and_protects_vars(self):
        """Paranoia Layer 0 & 2: Injects B2B cold outreach synonyms across all 5 categories while protecting variables."""
        plain = (
            "Hi {{first_name}},\n\n"
            "I noticed your recent momentum at {{company | your company}}. "
            "Wanted to reach out because I thought this could be helpful. "
            "Are you free for a quick chat? Best, Sarah"
        )
        res = generate_linguistic_spintax(plain, intensity="balanced")
        self.assertIn("original_text", res)
        self.assertIn("spintax_text", res)
        self.assertIn("entropy", res)
        self.assertTrue(res["replacements_count"] >= 5)

        enriched = res["spintax_text"]
        # Verify protected variables untouched
        self.assertIn("{{first_name}}", enriched)
        self.assertIn("{{company | your company}}", enriched)

        # Verify spintax blocks injected
        self.assertIn("{Hi|Hello|Hey}", enriched)
        self.assertIn("{recent updates|recent momentum|recent progress}", enriched)
        self.assertIn("{wanted to reach out|reaching out because|wanted to connect}", enriched)
        self.assertIn("{thought it might be relevant|thought this could be helpful|thought you might find this interesting}", enriched)
        self.assertIn("{Are you free for a quick chat|Open to a brief 10-minute call|Would you be open to connecting for a quick chat}", enriched)
        self.assertIn("{Best,|Thanks,|Cheers,}", enriched)

        # Verify entropy rating and combinations on the enriched result
        entropy = res["entropy"]
        self.assertTrue(entropy["valid"])
        self.assertGreaterEqual(entropy["total_combinations"], 200)
        self.assertEqual(entropy["entropy_rating"], "ENTERPRISE_IMMUNITY")

    def test_generate_linguistic_spintax_protects_existing_spintax(self):
        """Paranoia Layer 2: Existing spintax blocks are preserved and not double-mutated."""
        plain_with_spintax = (
            "{Hi|Hello} {{first_name}},\n"
            "I saw your recent updates. Let me know if you are open to exploring. Thanks, Alex"
        )
        res = generate_linguistic_spintax(plain_with_spintax)
        enriched = res["spintax_text"]

        # Original spintax '{Hi|Hello}' preserved intact
        self.assertIn("{Hi|Hello}", enriched)
        self.assertNotIn("{{Hi|Hello}", enriched)

        # New spintax added
        self.assertIn("{let me know if you're open to|worth a quick chat about|open to exploring}", enriched)
        self.assertIn("{Best,|Thanks,|Cheers,}", enriched)

    def test_generate_linguistic_spintax_empty_or_none(self):
        """Paranoia Layer 1: Handles empty or None text safely."""
        res_empty = generate_linguistic_spintax("")
        self.assertEqual(res_empty["replacements_count"], 0)
        self.assertEqual(res_empty["spintax_text"], "")

        res_none = generate_linguistic_spintax(None)
        self.assertEqual(res_none["replacements_count"], 0)
        self.assertEqual(res_none["spintax_text"], "")

    # =========================================================================
    # 4. Spintax Preview Generator (Layer 0, 1 & 2)
    # =========================================================================

    def test_preview_spintax_variants_deterministic_and_deduplicated(self):
        """Paranoia Layer 0 & 1: Deterministic generation with seed and deduplicated outputs."""
        tpl = "{Hi|Hello|Hey} {{first_name}}, {worth a chat|let's connect}!"
        # 3 * 2 = 6 possible combinations

        # Generate 4 samples with deterministic seed
        v1 = preview_spintax_variants(tpl, count=4, seed="campaign_alpha")
        v2 = preview_spintax_variants(tpl, count=4, seed="campaign_alpha")
        self.assertEqual(v1, v2)
        self.assertEqual(len(v1), 4)
        self.assertEqual(len(set(v1)), 4)  # All 4 are unique

        # Count clamped between 1 and 20
        v_large = preview_spintax_variants(tpl, count=50, seed="test_seed")
        # Since total combinations is 6, should return exactly 6 unique variants
        self.assertEqual(len(v_large), 6)
        self.assertEqual(len(set(v_large)), 6)

        # Count 0 or negative clamped to 1
        v_zero = preview_spintax_variants(tpl, count=0, seed="test_seed")
        self.assertEqual(len(v_zero), 1)

    def test_preview_spintax_variants_without_spintax(self):
        """Paranoia Layer 1: Plain text without spintax produces exactly one sample."""
        plain = "Hello {{first_name}}, have a nice day."
        samples = preview_spintax_variants(plain, count=5)
        self.assertEqual(samples, ["Hello {{first_name}}, have a nice day."])


if __name__ == "__main__":
    unittest.main()
