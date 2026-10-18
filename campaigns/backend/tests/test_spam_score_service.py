"""
test_spam_score_service.py — Comprehensive Test Suite for Spam Trigger Words &
Algorithmic Content Spam Score Classifier (SpamAssassin & Microsoft EOP Pre-Flight)

Tests all Three Layers of the Paranoia Framework:
  - Layer 0: Foundational mechanics, 500+ triggers catalog, heuristic evaluators,
    scoring math, risk level boundaries, copy remediations, facade methods.
  - Layer 1: ReDoS resilience, bounded execution on large inputs, thread-safe catalogs.
  - Layer 2: Sanitization of human inputs (NoneType, numbers, zero-width evasion, HTML tags).
"""

import unittest
from typing import Dict, Any

from core.backend.services.spam_score_service import (
    SpamRiskLevel,
    SpamScoreService,
    TRIGGER_CATALOG,
    URL_SHORTENER_DOMAINS,
    B2B_REMEDIATIONS_MAP,
    audit_email_content,
    suggest_copy_remediations,
)


class TestSpamScoreServiceCore(unittest.TestCase):
    """
    Test suite for SpamRiskLevel, trigger word catalogs, heuristic evaluators,
    weighting mathematics, and copy remediation engine.
    """

    def setUp(self):
        self.service = SpamScoreService()

    # =========================================================================
    # 1. ENUMS & THRESHOLDS
    # =========================================================================

    def test_spam_risk_level_enum_values(self):
        """Verify all required risk level enum values exist."""
        self.assertEqual(SpamRiskLevel.SAFE.value, "SAFE")
        self.assertEqual(SpamRiskLevel.LOW_RISK.value, "LOW_RISK")
        self.assertEqual(SpamRiskLevel.HIGH_SPAM_RISK.value, "HIGH_SPAM_RISK")
        self.assertEqual(SpamRiskLevel.CRITICAL_SPAM_REJECT.value, "CRITICAL_SPAM_REJECT")

    def test_risk_level_boundaries(self):
        """Verify score mapping to exact risk tiers and sendability clearance."""
        # Score 0.0 -> SAFE, can_safely_send = True
        res_0 = audit_email_content("Introductory chat", "Hi John, would you like to connect?", has_unsubscribe=True)
        self.assertEqual(res_0["risk_level"], SpamRiskLevel.SAFE.value)
        self.assertTrue(res_0["can_safely_send"])
        self.assertIsNone(res_0["rejection_reason"])

        # Score < 2.0 -> SAFE
        res_safe = audit_email_content("Quick check", "Here is a special promotion for your review.", has_unsubscribe=True)
        self.assertLess(res_safe["spam_score"], 2.0)
        self.assertEqual(res_safe["risk_level"], SpamRiskLevel.SAFE.value)
        self.assertTrue(res_safe["can_safely_send"])

        # Score >= 6.0 -> CRITICAL_SPAM_REJECT, can_safely_send = False
        res_crit = audit_email_content(
            "URGENT: WINNER NOTIFICATION!!!",
            "CONGRATULATIONS! Act now to earn $ and get 100% free money! Pure profit guaranteed!",
            is_reply=False,
            has_unsubscribe=False,
        )
        self.assertGreaterEqual(res_crit["spam_score"], 6.0)
        self.assertEqual(res_crit["risk_level"], SpamRiskLevel.CRITICAL_SPAM_REJECT.value)
        self.assertFalse(res_crit["can_safely_send"])
        self.assertIsNotNone(res_crit["rejection_reason"])
        self.assertIn("CRITICAL_SPAM_SCORE_EXCEEDED", res_crit["rejection_reason"])

    # =========================================================================
    # 2. TRIGGER WORD CATALOG VERIFICATION (500+ KEYWORDS & REGEXES)
    # =========================================================================

    def test_catalog_size_exceeds_500_keywords(self):
        """Verify the trigger word catalog contains at least 500 distinct items."""
        total_count = SpamScoreService.get_trigger_word_count()
        self.assertGreaterEqual(
            total_count,
            500,
            f"Expected at least 500 keywords, found {total_count}",
        )

    def test_required_categories_present(self):
        """Verify all 6 required categories are defined in the catalog."""
        required_categories = [
            "URGENCY_PRESSURE",
            "FINANCIAL_HYPE",
            "SHADY_MARKETING",
            "DECEPTIVE_PREFIXES",
            "SENSITIVE_PHARMACEUTICAL_CRYPTO",
            "URL_SHORTENER_DOMAINS",
        ]
        for cat in required_categories:
            self.assertIn(cat, TRIGGER_CATALOG, f"Missing category: {cat}")
            self.assertGreater(len(TRIGGER_CATALOG[cat]), 0)

    def test_required_sample_keywords_present(self):
        """Verify specific required keywords specified in prompt exist in catalog."""
        # URGENCY_PRESSURE
        urgency = TRIGGER_CATALOG["URGENCY_PRESSURE"]
        for kw in [
            "act now", "limited time", "urgent", "immediate action",
            "expires tonight", "once in a lifetime", "last chance",
            "don't delete", "order now", "apply now", "call now",
            "time sensitive", "action required", "instant access",
        ]:
            self.assertIn(kw, urgency)

        # FINANCIAL_HYPE
        finance = TRIGGER_CATALOG["FINANCIAL_HYPE"]
        for kw in [
            "guaranteed", "earn $", "risk-free", "risk free",
            "double your income", "make money fast", "passive income",
            "billion dollars", "cash bonus", "extra income",
            "financial freedom", "no investment", "pure profit",
            "unlimited earnings", "100% free", "millionaire",
            "investment opportunity",
        ]:
            self.assertIn(kw, finance)

        # SHADY_MARKETING
        marketing = TRIGGER_CATALOG["SHADY_MARKETING"]
        for kw in [
            "click here", "click below", "free trial no credit card",
            "as seen on", "congratulations", "winner",
            "you have been selected", "exclusive deal", "special promotion",
            "miracle", "satisfaction guaranteed", "unsolicited",
            "no catch", "hidden fees", "dear friend",
        ]:
            self.assertIn(kw, marketing)

        # DECEPTIVE_PREFIXES
        deceptive = TRIGGER_CATALOG["DECEPTIVE_PREFIXES"]
        for kw in [
            "re: our meeting", "re: your inquiry", "fwd: invoice",
            "fwd: receipt", "attn: urgent notice", "regarding payment",
        ]:
            self.assertIn(kw, deceptive)

        # SENSITIVE_PHARMACEUTICAL_CRYPTO
        pharma = TRIGGER_CATALOG["SENSITIVE_PHARMACEUTICAL_CRYPTO"]
        for kw in [
            "viagra", "cialis", "crypto giveaway", "bitcoin investment",
            "wallet balance", "casino", "wire transfer", "offshore",
            "nigerian prince",
        ]:
            self.assertIn(kw, pharma)

        # URL_SHORTENER_DOMAINS
        shorteners = TRIGGER_CATALOG["URL_SHORTENER_DOMAINS"]
        for domain in [
            "bit.ly", "tinyurl.com", "t.co", "ow.ly", "is.gd",
            "buff.ly", "rebrand.ly", "adf.ly",
        ]:
            self.assertIn(domain, shorteners)

    def test_weights_within_valid_range(self):
        """Verify all catalog weights are calibrated between 0.3 and 1.0."""
        for category, words in TRIGGER_CATALOG.items():
            for kw, weight in words.items():
                self.assertGreaterEqual(
                    weight, 0.3, f"Weight too low for {kw} in {category}: {weight}"
                )
                self.assertLessEqual(
                    weight, 1.0, f"Weight too high for {kw} in {category}: {weight}"
                )

    # =========================================================================
    # 3. HEURISTIC EVALUATOR TESTS (SPAMASSASSIN & EOP ALGORITHMS)
    # =========================================================================

    def test_heuristic_eval_all_caps_subject(self):
        """EVAL_ALL_CAPS_SUBJECT: Subject uppercase ratio > 50% and length >= 6 chars (+1.5 points)."""
        # Triggers: 100% caps, length 12 >= 6
        res = audit_email_content("URGENT OFFER", "Hi Alex, hope you are well.", has_unsubscribe=True)
        penalties = [p["code"] for p in res["heuristic_penalties"]]
        self.assertIn("EVAL_ALL_CAPS_SUBJECT", penalties)
        penalty_obj = next(p for p in res["heuristic_penalties"] if p["code"] == "EVAL_ALL_CAPS_SUBJECT")
        self.assertEqual(penalty_obj["penalty"], 1.5)

        # Does NOT trigger: short length < 6 chars even if all caps
        res_short = audit_email_content("HI", "Hi Alex, hope you are well.", has_unsubscribe=True)
        penalties_short = [p["code"] for p in res_short["heuristic_penalties"]]
        self.assertNotIn("EVAL_ALL_CAPS_SUBJECT", penalties_short)

        # Does NOT trigger: normal title case
        res_normal = audit_email_content("Quick question about your quarterly pipeline", "Hello", has_unsubscribe=True)
        self.assertNotIn("EVAL_ALL_CAPS_SUBJECT", [p["code"] for p in res_normal["heuristic_penalties"]])

    def test_heuristic_eval_excessive_caps_body(self):
        """EVAL_EXCESSIVE_CAPS_BODY: Body uppercase words ratio > 20% (+1.0 points)."""
        # 6 uppercase words out of 8 (> 20%)
        shouting_body = "WE MUST SCHEDULE A CALL TODAY TO DISCUSS PARTNERSHIP."
        res = audit_email_content("Intro", shouting_body, has_unsubscribe=True)
        penalties = [p["code"] for p in res["heuristic_penalties"]]
        self.assertIn("EVAL_EXCESSIVE_CAPS_BODY", penalties)
        penalty_obj = next(p for p in res["heuristic_penalties"] if p["code"] == "EVAL_EXCESSIVE_CAPS_BODY")
        self.assertEqual(penalty_obj["penalty"], 1.0)

        # Normal text with 1-2 acronyms: does NOT trigger
        normal_body = "We help B2B SaaS companies scale outbound pipelines with AI automation."
        res_normal = audit_email_content("Intro", normal_body, has_unsubscribe=True)
        self.assertNotIn("EVAL_EXCESSIVE_CAPS_BODY", [p["code"] for p in res_normal["heuristic_penalties"]])

    def test_heuristic_eval_excessive_punctuation(self):
        """EVAL_EXCESSIVE_PUNCTUATION: Exclamation marks >= 3, question marks >= 3, or ?! (+0.8 points)."""
        # Test 3 exclamation marks
        res_excl = audit_email_content("Great news!", "Check this out!!", has_unsubscribe=True)
        self.assertIn("EVAL_EXCESSIVE_PUNCTUATION", [p["code"] for p in res_excl["heuristic_penalties"]])

        # Test 3 question marks
        res_ques = audit_email_content("Are you free?", "Can we talk? Is this you?", has_unsubscribe=True)
        self.assertIn("EVAL_EXCESSIVE_PUNCTUATION", [p["code"] for p in res_ques["heuristic_penalties"]])

        # Test interrobang ?!
        res_inter = audit_email_content("Really?!", "Let me know what you think.", has_unsubscribe=True)
        self.assertIn("EVAL_EXCESSIVE_PUNCTUATION", [p["code"] for p in res_inter["heuristic_penalties"]])

        # Test single punctuation: does NOT trigger
        res_clean = audit_email_content("Quick question", "Are you available Thursday?", has_unsubscribe=True)
        self.assertNotIn("EVAL_EXCESSIVE_PUNCTUATION", [p["code"] for p in res_clean["heuristic_penalties"]])

    def test_heuristic_eval_currency_symbols(self):
        """EVAL_CURRENCY_SYMBOLS: 3 or more currency signs in text (+0.8 points)."""
        # 3 dollar signs
        res = audit_email_content("Save $100 today", "Tier 1: $10, Tier 2: $20", has_unsubscribe=True)
        self.assertIn("EVAL_CURRENCY_SYMBOLS", [p["code"] for p in res["heuristic_penalties"]])
        penalty_obj = next(p for p in res["heuristic_penalties"] if p["code"] == "EVAL_CURRENCY_SYMBOLS")
        self.assertEqual(penalty_obj["penalty"], 0.8)

        # 2 symbols: does NOT trigger
        res_2 = audit_email_content("Pricing", "Cost is $50 or €45.", has_unsubscribe=True)
        self.assertNotIn("EVAL_CURRENCY_SYMBOLS", [p["code"] for p in res_2["heuristic_penalties"]])

    def test_heuristic_eval_deceptive_re_fwd(self):
        """EVAL_DECEPTIVE_RE_FWD: Subject starts with Re: or Fwd: when is_reply=False (+2.0 points)."""
        # Cold outreach with Re: -> Triggers (+2.0)
        res_re = audit_email_content("Re: our meeting yesterday", "Following up", is_reply=False, has_unsubscribe=True)
        self.assertIn("EVAL_DECEPTIVE_RE_FWD", [p["code"] for p in res_re["heuristic_penalties"]])
        penalty_obj = next(p for p in res_re["heuristic_penalties"] if p["code"] == "EVAL_DECEPTIVE_RE_FWD")
        self.assertEqual(penalty_obj["penalty"], 2.0)

        # Cold outreach with Fwd: -> Triggers
        res_fwd = audit_email_content("Fwd: invoice copy", "Attached here", is_reply=False, has_unsubscribe=True)
        self.assertIn("EVAL_DECEPTIVE_RE_FWD", [p["code"] for p in res_fwd["heuristic_penalties"]])

        # Legitimate reply with is_reply=True -> Bypassed
        res_legit = audit_email_content("Re: our meeting yesterday", "Thanks for chatting!", is_reply=True, has_unsubscribe=True)
        self.assertNotIn("EVAL_DECEPTIVE_RE_FWD", [p["code"] for p in res_legit["heuristic_penalties"]])

    def test_heuristic_eval_high_link_density(self):
        """EVAL_HIGH_LINK_DENSITY: Links count > 3 in cold outreach body (+1.2 points)."""
        body_many_links = (
            "Check our site at https://acme.com, docs at https://docs.acme.com, "
            "pricing at https://pricing.acme.com, and blog at https://blog.acme.com."
        )
        res = audit_email_content("Update", body_many_links, has_unsubscribe=True)
        self.assertIn("EVAL_HIGH_LINK_DENSITY", [p["code"] for p in res["heuristic_penalties"]])
        penalty_obj = next(p for p in res["heuristic_penalties"] if p["code"] == "EVAL_HIGH_LINK_DENSITY")
        self.assertEqual(penalty_obj["penalty"], 1.2)

        # 2 links: does NOT trigger
        body_2_links = "Visit https://acme.com or https://docs.acme.com."
        res_2 = audit_email_content("Update", body_2_links, has_unsubscribe=True)
        self.assertNotIn("EVAL_HIGH_LINK_DENSITY", [p["code"] for p in res_2["heuristic_penalties"]])

    def test_heuristic_eval_raw_ip_links(self):
        """EVAL_RAW_IP_LINKS: Links with raw IP address (+3.0 points)."""
        body_ip = "Log in to your account at http://192.168.1.1/login"
        res = audit_email_content("Action required", body_ip, has_unsubscribe=True)
        self.assertIn("EVAL_RAW_IP_LINKS", [p["code"] for p in res["heuristic_penalties"]])
        penalty_obj = next(p for p in res["heuristic_penalties"] if p["code"] == "EVAL_RAW_IP_LINKS")
        self.assertEqual(penalty_obj["penalty"], 3.0)

        # Standard hostname: does NOT trigger
        body_domain = "Log in at https://app.acme.com/login"
        res_clean = audit_email_content("Action", body_domain, has_unsubscribe=True)
        self.assertNotIn("EVAL_RAW_IP_LINKS", [p["code"] for p in res_clean["heuristic_penalties"]])

    def test_heuristic_eval_shortener_domains(self):
        """EVAL_SHORTENER_DOMAINS: Any link pointing to known URL shortener domain (+2.5 points)."""
        body_shortener = "See our proposal here: https://bit.ly/3xY8a9"
        res = audit_email_content("Proposal", body_shortener, has_unsubscribe=True)
        self.assertIn("EVAL_SHORTENER_DOMAINS", [p["code"] for p in res["heuristic_penalties"]])
        penalty_obj = next(p for p in res["heuristic_penalties"] if p["code"] == "EVAL_SHORTENER_DOMAINS")
        self.assertEqual(penalty_obj["penalty"], 2.5)

        # Another shortener domain
        body_tinyurl = "Click link: http://tinyurl.com/special-deal"
        res_tiny = audit_email_content("Deal", body_tinyurl, has_unsubscribe=True)
        self.assertIn("EVAL_SHORTENER_DOMAINS", [p["code"] for p in res_tiny["heuristic_penalties"]])

    def test_heuristic_eval_missing_unsubscribe(self):
        """EVAL_MISSING_UNSUBSCRIBE: Cold email body lacks unsubscribe/opt-out phrase (+1.0 points)."""
        # Cold outreach without unsubscribe flag and no text phrase -> Triggers (+1.0)
        res_missing = audit_email_content("Intro", "Would love to chat Thursday.", is_reply=False, has_unsubscribe=False)
        self.assertIn("EVAL_MISSING_UNSUBSCRIBE", [p["code"] for p in res_missing["heuristic_penalties"]])
        penalty_obj = next(p for p in res_missing["heuristic_penalties"] if p["code"] == "EVAL_MISSING_UNSUBSCRIBE")
        self.assertEqual(penalty_obj["penalty"], 1.0)

        # has_unsubscribe=True (e.g. system header injected) -> Bypassed
        res_header = audit_email_content("Intro", "Would love to chat Thursday.", is_reply=False, has_unsubscribe=True)
        self.assertNotIn("EVAL_MISSING_UNSUBSCRIBE", [p["code"] for p in res_header["heuristic_penalties"]])

        # has_unsubscribe=False BUT body contains opt-out phrase -> Bypassed
        res_phrase = audit_email_content(
            "Intro",
            "Would love to chat. To unsubscribe, click here.",
            is_reply=False,
            has_unsubscribe=False,
        )
        self.assertNotIn("EVAL_MISSING_UNSUBSCRIBE", [p["code"] for p in res_phrase["heuristic_penalties"]])

        # Reply thread (is_reply=True) -> Bypassed
        res_reply = audit_email_content("Re: Intro", "Sounds good, see you then.", is_reply=True, has_unsubscribe=False)
        self.assertNotIn("EVAL_MISSING_UNSUBSCRIBE", [p["code"] for p in res_reply["heuristic_penalties"]])

    # =========================================================================
    # 4. WEIGHTING & SCORING MATHEMATICS
    # =========================================================================

    def test_subject_1_5x_multiplier_vs_body_1_0x(self):
        """Verify subject trigger matches receive 1.5x multiplier while body matches receive 1.0x."""
        # "guaranteed" has weight 0.8 in FINANCIAL_HYPE
        # Subject match: penalty = 0.8 * 1.5 = 1.20
        res_subj = audit_email_content("Guaranteed results", "Hello world.", has_unsubscribe=True)
        subj_trigger = next(t for t in res_subj["flagged_triggers"] if t["trigger"] == "guaranteed")
        self.assertEqual(subj_trigger["location"], "subject")
        self.assertEqual(subj_trigger["multiplier"], 1.5)
        self.assertEqual(subj_trigger["penalty"], 1.2)

        # Body match: penalty = 0.8 * 1.0 = 0.80
        res_body = audit_email_content("Results overview", "We offer guaranteed outcomes.", has_unsubscribe=True)
        body_trigger = next(t for t in res_body["flagged_triggers"] if t["trigger"] == "guaranteed")
        self.assertEqual(body_trigger["location"], "body")
        self.assertEqual(body_trigger["multiplier"], 1.0)
        self.assertEqual(body_trigger["penalty"], 0.8)

    def test_score_clamping_to_ten(self):
        """Verify cumulative penalties clamp cleanly to 10.0 max."""
        horrific_spam = (
            "CONGRATULATIONS WINNER! Act now to earn $ and get 100% free money! "
            "Double your income with pure profit guaranteed! Click here: http://192.168.1.1/free "
            "or visit http://bit.ly/cash !!! Free bitcoin crypto giveaway! Nigerian prince wire transfer."
        )
        res = audit_email_content("URGENT: WINNER NOTIFICATION!!!", horrific_spam, is_reply=False, has_unsubscribe=False)
        self.assertEqual(res["spam_score"], 10.0)
        self.assertEqual(res["risk_level"], SpamRiskLevel.CRITICAL_SPAM_REJECT.value)
        self.assertFalse(res["can_safely_send"])

    # =========================================================================
    # 5. PARANOIA LAYER 1 & 2: DEFENSIVE SANITIZATION & HUMAN ERROR
    # =========================================================================

    def test_sanitization_handles_none_and_non_strings(self):
        """Paranoia Layer 2: handles None, integers, dicts, lists gracefully without crashing."""
        res_none = audit_email_content(None, None)
        self.assertEqual(res_none["spam_score"], 0.0)
        self.assertEqual(res_none["risk_level"], SpamRiskLevel.SAFE.value)
        self.assertTrue(res_none["can_safely_send"])

        res_int = audit_email_content(12345, 67890)
        self.assertEqual(res_int["risk_level"], SpamRiskLevel.SAFE.value)

    def test_zero_width_evasion_stripping(self):
        """Paranoia Layer 2: strips zero-width spaces (\u200B) used to evade keyword filters."""
        # "v\u200bi\u200ba\u200bg\u200br\u200ba" -> "viagra"
        evasive_text = "Check out our cheap v\u200bi\u200ba\u200bg\u200br\u200ba pills online"
        res = audit_email_content("Hello", evasive_text, has_unsubscribe=True)
        triggers = [t["trigger"] for t in res["flagged_triggers"]]
        self.assertIn("viagra", triggers)

    def test_html_tag_stripping(self):
        """Paranoia Layer 2: extracts readable plain text from HTML email content."""
        html_body = "<p>Please <a href='https://acme.com'>click here</a> for details.</p>"
        res = audit_email_content("Subject", html_body, has_unsubscribe=True)
        triggers = [t["trigger"] for t in res["flagged_triggers"]]
        self.assertIn("click here", triggers)

    def test_string_boolean_coercion(self):
        """Paranoia Layer 2: coerces string representations of booleans ('true', 'false', '1', '0')."""
        res_false = audit_email_content("Re: test", "Body", is_reply="false", has_unsubscribe="false")
        self.assertIn("EVAL_DECEPTIVE_RE_FWD", [p["code"] for p in res_false["heuristic_penalties"]])
        self.assertIn("EVAL_MISSING_UNSUBSCRIBE", [p["code"] for p in res_false["heuristic_penalties"]])

        res_true = audit_email_content("Re: test", "Body", is_reply="true", has_unsubscribe="true")
        self.assertNotIn("EVAL_DECEPTIVE_RE_FWD", [p["code"] for p in res_true["heuristic_penalties"]])
        self.assertNotIn("EVAL_MISSING_UNSUBSCRIBE", [p["code"] for p in res_true["heuristic_penalties"]])

    def test_overlong_input_clamping(self):
        """Paranoia Layer 1: Clamps inputs exceeding 100,000 chars without OOM or crash."""
        massive_text = "Hello world! " * 10000  # ~130,000 characters
        res = audit_email_content("Massive test", massive_text, has_unsubscribe=True)
        self.assertIsNotNone(res["spam_score"])

    # =========================================================================
    # 6. COPY REMEDIATION ENGINE (SUGGEST_COPY_REMEDIATIONS)
    # =========================================================================

    def test_suggest_copy_remediations_b2b_replacements(self):
        """Verify professional B2B replacements for detected trigger phrases."""
        text = "Guaranteed to make money fast! Click here and act now for 100% free risk-free access."
        rem = suggest_copy_remediations(text)

        self.assertIn("sanitized_text", rem)
        self.assertIn("replacements_count", rem)
        self.assertIn("replacements", rem)

        sanitized = rem["sanitized_text"]
        # Check that aggressive terms were replaced
        self.assertNotIn("make money fast", sanitized.lower())
        self.assertNotIn("click here", sanitized.lower())
        self.assertNotIn("100% free", sanitized.lower())
        self.assertNotIn("risk-free", sanitized.lower())

        # Check that professional replacements were inserted
        self.assertIn("proven", sanitized.lower())
        self.assertIn("accelerate revenue", sanitized.lower())
        self.assertIn("feel free to explore", sanitized.lower())
        self.assertIn("worth reviewing this week", sanitized.lower())
        self.assertIn("complimentary", sanitized.lower())
        self.assertIn("low friction", sanitized.lower())

    def test_suggest_copy_remediations_preserves_casing(self):
        """Verify Title Case, UPPERCASE, and lowercase preservation in remediated copy."""
        # Capitalized
        rem1 = suggest_copy_remediations("Guaranteed results")
        self.assertTrue(rem1["sanitized_text"].startswith("Proven"))

        # UPPERCASE
        rem2 = suggest_copy_remediations("ACT NOW to receive proposal")
        self.assertTrue(rem2["sanitized_text"].startswith("WORTH REVIEWING THIS WEEK"))

        # lowercase
        rem3 = suggest_copy_remediations("our 100% free pilot")
        self.assertIn("complimentary", rem3["sanitized_text"])

    # =========================================================================
    # 7. FACADE CLASS SPAMSCORESERVICE
    # =========================================================================

    def test_facade_static_methods(self):
        """Verify SpamScoreService facade methods produce identical results to standalone functions."""
        res_facade = SpamScoreService.audit_email_content("Quick question", "Hey there", has_unsubscribe=True)
        res_func = audit_email_content("Quick question", "Hey there", has_unsubscribe=True)
        self.assertEqual(res_facade["spam_score"], res_func["spam_score"])
        self.assertEqual(res_facade["risk_level"], res_func["risk_level"])

        rem_facade = SpamScoreService.suggest_copy_remediations("Guaranteed results")
        rem_func = suggest_copy_remediations("Guaranteed results")
        self.assertEqual(rem_facade["sanitized_text"], rem_func["sanitized_text"])

        catalog = SpamScoreService.get_catalog()
        self.assertIn("URGENCY_PRESSURE", catalog)


if __name__ == "__main__":
    unittest.main()
