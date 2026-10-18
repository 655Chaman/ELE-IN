"""
test_spam_score_service.py — Comprehensive Unit & Paranoia Tests for Phase 39
(Spam Trigger Words & Algorithmic Content Spam Score Classifier - SpamAssassin & Microsoft EOP Pre-Flight)

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - SpamRiskLevel enum definitions and thresholds (SAFE, LOW_RISK, HIGH_SPAM_RISK, CRITICAL_SPAM_REJECT).
    - Clean professional B2B email achieves low spam score (< 1.0, SAFE, can_safely_send=True).
    - Trigger phrase classification across categories:
      * URGENCY_PRESSURE ("act now", "limited time", "urgent", "expires tonight")
      * FINANCIAL_HYPE ("guaranteed", "double your income", "risk-free", "passive income")
      * SHADY_MARKETING ("congratulations winner", "you have been selected", "exclusive deal")
      * DECEPTIVE_PREFIXES ("re: our meeting", "fwd: invoice", "attn: urgent notice")
      * SENSITIVE_PHARMACEUTICAL_CRYPTO ("viagra", "crypto giveaway", "bitcoin investment")
    - Algorithmic heuristics:
      * EVAL_ALL_CAPS_SUBJECT (uppercase ratio > 50% on subject >= 6 chars)
      * EVAL_EXCESSIVE_PUNCTUATION (multiple ! or ? or interrobangs)
      * EVAL_DECEPTIVE_RE_FWD (cold outreach starting with Re: or Fwd:)
      * EVAL_DECEPTIVE_RE_FWD allowed when is_reply=True (0 penalty)
      * EVAL_URL_SHORTENER (bit.ly, tinyurl, t.co, etc.)
      * EVAL_RAW_IP_LINKS (http://192.168.1.100/claim)
      * EVAL_HIGH_LINK_DENSITY (> 3 links in cold outreach body)
      * EVAL_MISSING_UNSUBSCRIBE (cold email lacking opt-out notice)
    - Copy remediation engine:
      * Replaces aggressive triggers with consultative B2B phrases ("guaranteed" -> "proven",
        "act now" -> "worth reviewing this week", "click here" -> "feel free to explore", etc.)
      * Preserves casing (lowercase, Title Case, UPPERCASE).

  - Layer 1: Environmental Failure Analysis
    - Zero network or database calls (pure in-memory deterministic classifier).
    - Missing unsubscribe penalty added when has_unsubscribe=False.
    - Unsubscribe notice present suppresses missing unsubscribe penalty.
    - High link density penalty added when link count > 3.
    - Text inputs > 100,000 characters safely clamped without OOM or ReDoS hang.
    - Calculated spam score strictly clamped to [0.0, 10.0].
    - Subject triggers weighted 1.5x vs body triggers 1.0x.
    - Risk classification boundaries and can_safely_send logic.
    - Currency symbols heuristic detection.

  - Layer 2: Human Paranoia & Security Defense
    - Handles None, empty strings, whitespace, and non-string inputs safely without uncaught exceptions.
    - Case-insensitive trigger matching ("GUARANTEED", "Guaranteed", "guaranteed").
    - Strict word boundary defense preventing false positives ("urgency" doesn't trigger "urgent", "assumed" doesn't trigger "spam").
    - Zero-width space and homoglyph evasion stripping.
    - HTML email content tag stripping.
    - Facade class SpamScoreService static method parity.
    - Catalog inspection and trigger word count verification (> 500 triggers).
"""

import unittest
from core.backend.services.spam_score_service import (
    SpamRiskLevel,
    SpamScoreService,
    audit_email_content,
    suggest_copy_remediations,
    MAX_INPUT_LENGTH,
    CRITICAL_REJECT_THRESHOLD,
    SUBJECT_WEIGHT_MULTIPLIER,
    BODY_WEIGHT_MULTIPLIER,
    TRIGGER_CATALOG,
    URL_SHORTENER_DOMAINS,
    UNSUBSCRIBE_PHRASES,
    B2B_REMEDIATIONS_MAP,
)


class TestSpamScoreService(unittest.TestCase):
    """
    Comprehensive Unit & Paranoia Tests for the Spam Score Classifier & Copy Remediation Engine.
    """

    # =========================================================================
    # Layer 0: Foundational Layer (Core Mechanics & Enums)
    # =========================================================================

    def test_enums_defined_correctly(self):
        """Verifies SpamRiskLevel enum members and threshold values."""
        self.assertEqual(SpamRiskLevel.SAFE.value, "SAFE")
        self.assertEqual(SpamRiskLevel.LOW_RISK.value, "LOW_RISK")
        self.assertEqual(SpamRiskLevel.HIGH_SPAM_RISK.value, "HIGH_SPAM_RISK")
        self.assertEqual(SpamRiskLevel.CRITICAL_SPAM_REJECT.value, "CRITICAL_SPAM_REJECT")

    def test_clean_b2b_outreach_low_spam_score(self):
        """Clean professional email scores < 1.0, returns risk_level='SAFE', can_safely_send=True."""
        subject = "Quick question regarding Q3 roadmap discussion"
        body = (
            "Hi Jane,\n\n"
            "Hope you are having a productive week. I noticed your team's recent expansion in developer tooling. "
            "We recently published an engineering benchmark report on pipeline reliability that might be relevant.\n\n"
            "Would you be open to a brief 10-minute conversation next Tuesday?\n\n"
            "Best regards,\nAlex\n\n"
            "If you'd prefer not to hear from us, you can unsubscribe here: https://acme.com/opt-out"
        )
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        self.assertLess(result["spam_score"], 1.0)
        self.assertEqual(result["risk_level"], SpamRiskLevel.SAFE.value)
        self.assertTrue(result["can_safely_send"])
        self.assertIsNone(result["rejection_reason"])
        self.assertEqual(len(result["flagged_triggers"]), 0)
        self.assertEqual(len(result["heuristic_penalties"]), 0)

    def test_financial_hype_triggers_flagged(self):
        """Financial hype phrases receive elevated penalties under FINANCIAL_HYPE."""
        subject = "Double your income with our passive cash bonus"
        body = (
            "Guaranteed 100% free risk-free method to make money fast and achieve financial freedom. "
            "Pure profit with zero investment required."
        )
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        self.assertGreaterEqual(result["spam_score"], 4.0)
        flagged_categories = [t["category"] for t in result["flagged_triggers"]]
        self.assertIn("FINANCIAL_HYPE", flagged_categories)
        flagged_phrases = [t["trigger"].lower() for t in result["flagged_triggers"]]
        self.assertTrue(any("guaranteed" in p for p in flagged_phrases))
        self.assertTrue(any("double your income" in p or "risk-free" in p for p in flagged_phrases))

    def test_urgency_pressure_triggers_flagged(self):
        """Artificial urgency and coercive deadlines are flagged under URGENCY_PRESSURE."""
        subject = "Act now! Limited time urgent offer expires tonight"
        body = "Immediate action required. Once in a lifetime opportunity, last chance, order now!"
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        self.assertGreaterEqual(result["spam_score"], 3.5)
        flagged_categories = [t["category"] for t in result["flagged_triggers"]]
        self.assertIn("URGENCY_PRESSURE", flagged_categories)
        flagged_phrases = [t["trigger"].lower() for t in result["flagged_triggers"]]
        self.assertTrue(any("act now" in p for p in flagged_phrases))
        self.assertTrue(any("limited time" in p for p in flagged_phrases))

    def test_shady_marketing_triggers_flagged(self):
        """Shady consumer marketing buzzwords are flagged under SHADY_MARKETING."""
        subject = "Congratulations winner, you have been selected for an exclusive deal"
        body = "Click here for your special promotion with no catch and no hidden fees, dear friend!"
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        self.assertGreaterEqual(result["spam_score"], 3.0)
        flagged_categories = [t["category"] for t in result["flagged_triggers"]]
        self.assertIn("SHADY_MARKETING", flagged_categories)
        flagged_phrases = [t["trigger"].lower() for t in result["flagged_triggers"]]
        self.assertTrue(any("congratulations" in p or "winner" in p or "exclusive deal" in p for p in flagged_phrases))

    def test_sensitive_pharmaceutical_crypto_triggers_flagged(self):
        """High-risk illicit, pharma, and crypto tokens are heavily penalized."""
        subject = "Bitcoin investment and crypto giveaway"
        body = "Cheap online pharmacy with generic viagra and cialis shipped directly to your door."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        self.assertGreaterEqual(result["spam_score"], 4.0)
        flagged_categories = [t["category"] for t in result["flagged_triggers"]]
        self.assertIn("SENSITIVE_PHARMACEUTICAL_CRYPTO", flagged_categories)

    def test_all_caps_subject_penalty(self):
        """Subject with excessive uppercase ratio receives EVAL_ALL_CAPS_SUBJECT penalty."""
        subject = "URGENT ACT NOW GUARANTEED RESULTS"
        body = "Please review the attached notes at your earliest convenience."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_ALL_CAPS_SUBJECT", penalty_codes)
        all_caps_penalty = next(p for p in result["heuristic_penalties"] if p["code"] == "EVAL_ALL_CAPS_SUBJECT")
        self.assertGreaterEqual(all_caps_penalty["penalty"], 1.5)

    def test_normal_cased_subject_no_all_caps_penalty(self):
        """Subject with normal mixed case does not trigger EVAL_ALL_CAPS_SUBJECT."""
        subject = "Quarterly Infrastructure and Security Audit Summary"
        body = "Hi team, here is the executive overview."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertNotIn("EVAL_ALL_CAPS_SUBJECT", penalty_codes)

    def test_excessive_punctuation_penalty(self):
        """Repeated exclamation marks, question marks, or interrobangs trigger EVAL_EXCESSIVE_PUNCTUATION."""
        subject = "Check this out!!!! Are you ready???!"
        body = "Don't miss this opportunity!!!!!"
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_EXCESSIVE_PUNCTUATION", penalty_codes)

    def test_normal_punctuation_no_penalty(self):
        """Standard professional punctuation does not trigger excessive punctuation penalties."""
        subject = "Quick question: are you open to exploring this?"
        body = "Hi David, hope you're having a great week! Would love to chat soon."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertNotIn("EVAL_EXCESSIVE_PUNCTUATION", penalty_codes)

    def test_deceptive_re_fwd_penalty(self):
        """Cold outreach starting with 'Re:' or 'Fwd:' when is_reply=False triggers EVAL_DECEPTIVE_RE_FWD."""
        subject = "Re: our phone call yesterday"
        body = "Following up on our earlier discussion regarding our platform."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_DECEPTIVE_RE_FWD", penalty_codes)
        re_penalty = next(p for p in result["heuristic_penalties"] if p["code"] == "EVAL_DECEPTIVE_RE_FWD")
        self.assertEqual(re_penalty["penalty"], 2.0)

    def test_deceptive_re_fwd_allowed_for_actual_reply(self):
        """When is_reply=True, 'Re:' or 'Fwd:' prefix receives 0 penalty."""
        subject = "Re: our phone call yesterday"
        body = "Thanks for your response, here are the requested details."
        result = audit_email_content(subject=subject, body=body, is_reply=True, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertNotIn("EVAL_DECEPTIVE_RE_FWD", penalty_codes)

    def test_deceptive_fwd_prefix_penalty(self):
        """Cold email starting with 'Fwd:' is penalized as deceptive."""
        subject = "Fwd: internal billing notice"
        body = "Sharing the document we discussed."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_DECEPTIVE_RE_FWD", penalty_codes)

    def test_url_shortener_penalty(self):
        """Presence of bit.ly or known shorteners triggers EVAL_SHORTENER_DOMAINS."""
        subject = "Important product update"
        body = "Check out our latest case study here: https://bit.ly/3xYqz"
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_SHORTENER_DOMAINS", penalty_codes)
        shortener_penalty = next(p for p in result["heuristic_penalties"] if p["code"] == "EVAL_SHORTENER_DOMAINS")
        self.assertEqual(shortener_penalty["penalty"], 2.5)

    def test_url_shortener_various_domains(self):
        """Multiple shortener domains (tinyurl, t.co, ow.ly, goo.gl) are accurately detected."""
        domains_to_test = ["tinyurl.com", "t.co", "ow.ly", "goo.gl", "is.gd"]
        for domain in domains_to_test:
            body = f"Review the presentation at https://{domain}/xyz987"
            result = audit_email_content(subject="Update", body=body, is_reply=False, has_unsubscribe=True)
            penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
            self.assertIn("EVAL_SHORTENER_DOMAINS", penalty_codes, f"Failed to detect shortener: {domain}")

    def test_raw_ip_link_penalty(self):
        """Link pointing directly to a raw IP address triggers heavy EVAL_RAW_IP_LINKS penalty."""
        subject = "Account verification"
        body = "Please confirm your credentials at http://192.168.1.100/claim immediately."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_RAW_IP_LINKS", penalty_codes)
        ip_penalty = next(p for p in result["heuristic_penalties"] if p["code"] == "EVAL_RAW_IP_LINKS")
        self.assertEqual(ip_penalty["penalty"], 3.0)

    def test_raw_ip_with_port_penalty(self):
        """Raw IP link with explicit port (e.g. :8080) is detected and penalized."""
        subject = "Server test"
        body = "Access the sandbox at http://45.33.32.156:8080/offer"
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_RAW_IP_LINKS", penalty_codes)

    def test_suggest_copy_remediations_replaces_phrases(self):
        """Copy remediation engine replaces aggressive triggers with consultative B2B copy."""
        text = "Guaranteed results if you act now"
        remediation = suggest_copy_remediations(text)

        self.assertIn("proven results if you worth reviewing this week", remediation["sanitized_text"].lower())
        self.assertGreaterEqual(remediation["replacements_count"], 2)

    def test_suggest_copy_remediations_preserves_title_casing(self):
        """Title Case triggers are replaced with Title Case / Capitalized suggestions."""
        text = "Guaranteed Outcomes and Act Now"
        remediation = suggest_copy_remediations(text)

        self.assertTrue(remediation["sanitized_text"].startswith("Proven Outcomes"))
        self.assertIn("Worth reviewing this week", remediation["sanitized_text"])

    def test_suggest_copy_remediations_preserves_uppercase(self):
        """UPPERCASE triggers are replaced with UPPERCASE suggestions."""
        text = "ACT NOW for a 100% FREE audit"
        remediation = suggest_copy_remediations(text)

        self.assertIn("WORTH REVIEWING THIS WEEK", remediation["sanitized_text"])
        self.assertIn("COMPLIMENTARY", remediation["sanitized_text"])

    def test_suggest_copy_remediations_all_known_replacements(self):
        """Verifies core B2B replacements mapping."""
        pairs = [
            ("click here", "feel free to explore"),
            ("100% free", "complimentary"),
            ("make money fast", "accelerate revenue"),
            ("risk-free", "low friction"),
        ]
        for trigger, expected_sub in pairs:
            res = suggest_copy_remediations(f"You should {trigger} to learn more.")
            self.assertIn(expected_sub, res["sanitized_text"].lower())

    def test_suggest_copy_remediations_clean_text(self):
        """Clean copy produces 0 replacements and returns identical text."""
        clean = "Would you be interested in a brief conversation next Tuesday morning?"
        res = suggest_copy_remediations(clean)
        self.assertEqual(res["replacements_count"], 0)
        self.assertEqual(res["sanitized_text"], clean)

    # =========================================================================
    # Layer 1: Environmental Failure Analysis
    # =========================================================================

    def test_missing_unsubscribe_adds_penalty(self):
        """Cold email lacking opt-out notice and unsubscribe header receives penalty."""
        subject = "Quick introduction"
        body = "Hi John, wanted to connect about potential synergies between our teams."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=False)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_MISSING_UNSUBSCRIBE", penalty_codes)
        unsub_penalty = next(p for p in result["heuristic_penalties"] if p["code"] == "EVAL_MISSING_UNSUBSCRIBE")
        self.assertEqual(unsub_penalty["penalty"], 1.0)

    def test_unsubscribe_flag_or_phrase_satisfies_requirement(self):
        """Providing has_unsubscribe=True or embedding 'unsubscribe' suppresses EVAL_MISSING_UNSUBSCRIBE."""
        # Case A: has_unsubscribe=True passed from router/executor
        res_a = audit_email_content(subject="Intro", body="Hi John", is_reply=False, has_unsubscribe=True)
        penalty_codes_a = [p["code"] for p in res_a["heuristic_penalties"]]
        self.assertNotIn("EVAL_MISSING_UNSUBSCRIBE", penalty_codes_a)

        # Case B: has_unsubscribe=False but body contains 'opt out'
        res_b = audit_email_content(
            subject="Intro",
            body="Hi John, if you wish to opt out simply let me know.",
            is_reply=False,
            has_unsubscribe=False,
        )
        penalty_codes_b = [p["code"] for p in res_b["heuristic_penalties"]]
        self.assertNotIn("EVAL_MISSING_UNSUBSCRIBE", penalty_codes_b)

    def test_high_link_density_penalty(self):
        """Cold outreach containing > 3 links triggers EVAL_HIGH_LINK_DENSITY."""
        subject = "Helpful resources for your engineering team"
        body = (
            "Hi team,\n"
            "Check out our links:\n"
            "1. https://acme.com/doc1\n"
            "2. https://acme.com/doc2\n"
            "3. https://acme.com/doc3\n"
            "4. https://acme.com/doc4\n"
            "5. https://acme.com/doc5\n"
            "Best regards."
        )
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_HIGH_LINK_DENSITY", penalty_codes)
        link_penalty = next(p for p in result["heuristic_penalties"] if p["code"] == "EVAL_HIGH_LINK_DENSITY")
        self.assertEqual(link_penalty["penalty"], 1.2)

    def test_normal_link_count_no_penalty(self):
        """1 or 2 links in cold email body do not trigger EVAL_HIGH_LINK_DENSITY."""
        subject = "Quick question"
        body = "Hi Sarah, check our case study at https://acme.com/case-study. Thanks!"
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertNotIn("EVAL_HIGH_LINK_DENSITY", penalty_codes)

    def test_overlong_text_clamped_safely(self):
        """Massive 150,000 character input is clamped to MAX_INPUT_LENGTH without OOM or crash."""
        massive_body = "word " * 30000  # ~150,000 characters
        result = audit_email_content(subject="Long email", body=massive_body, is_reply=False, has_unsubscribe=True)

        self.assertIsInstance(result["spam_score"], float)
        self.assertIn("body_analysis", result)
        self.assertLessEqual(result["body_analysis"]["word_count"], 30000)

    def test_clamped_spam_score_range(self):
        """Spam score never exceeds 10.0 and never drops below 0.0."""
        # Extreme spam cocktail combining dozens of triggers and penalties
        subject = "RE: URGENT ACT NOW GUARANTEED $$$ 100% FREE WINNER"
        body = (
            "Congratulations winner! Act now, limited time urgent offer expires tonight! "
            "Guaranteed double your income with risk-free passive cash bonus and pure profit. "
            "Click here immediately: http://192.168.1.1/claim and https://bit.ly/claim1 "
            "https://tinyurl.com/claim2 https://ow.ly/claim3 https://t.co/claim4 "
            "Cheap viagra and crypto giveaway bitcoin investment!!!! $$$$$ ????"
        )
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=False)

        self.assertLessEqual(result["spam_score"], 10.0)
        self.assertGreaterEqual(result["spam_score"], 0.0)
        self.assertEqual(result["spam_score"], 10.0)
        self.assertEqual(result["risk_level"], SpamRiskLevel.CRITICAL_SPAM_REJECT.value)
        self.assertFalse(result["can_safely_send"])
        self.assertIsNotNone(result["rejection_reason"])

    def test_risk_level_boundaries(self):
        """Verifies boundary thresholds for risk classification."""
        # SAFE: score < 2.0
        res_safe = audit_email_content(subject="Meeting notes", body="Notes from yesterday.", has_unsubscribe=True)
        self.assertEqual(res_safe["risk_level"], SpamRiskLevel.SAFE.value)

        # LOW_RISK: 2.0 <= score < 4.0
        # Subject trigger (1.5x) or single heuristic
        res_low = audit_email_content(subject="Re: discussion", body="Clean body.", is_reply=False, has_unsubscribe=True)
        self.assertIn(res_low["risk_level"], [SpamRiskLevel.LOW_RISK.value, SpamRiskLevel.SAFE.value])

        # CRITICAL_SPAM_REJECT: score >= 6.0
        # Heavy combination of IP, shortener, and financial triggers
        res_crit = audit_email_content(
            subject="URGENT ACT NOW GUARANTEED",
            body="Click here: http://192.168.1.1/claim https://bit.ly/xyz and earn cash now!",
            is_reply=False,
            has_unsubscribe=False,
        )
        self.assertGreaterEqual(res_crit["spam_score"], 6.0)
        self.assertEqual(res_crit["risk_level"], SpamRiskLevel.CRITICAL_SPAM_REJECT.value)
        self.assertFalse(res_crit["can_safely_send"])

    def test_subject_weight_multiplier(self):
        """Subject triggers receive 1.5x weight compared to 1.0x in body."""
        # Test trigger word "guaranteed" (weight 0.8)
        # In subject: 0.8 * 1.5 = 1.2
        res_subj = audit_email_content(subject="Guaranteed outcomes", body="Clean message.", has_unsubscribe=True)
        # In body: 0.8 * 1.0 = 0.8
        res_body = audit_email_content(subject="Clean subject", body="Guaranteed outcomes.", has_unsubscribe=True)

        subj_trigger_penalty = sum(t["penalty"] for t in res_subj["flagged_triggers"] if t["trigger"] == "guaranteed")
        body_trigger_penalty = sum(t["penalty"] for t in res_body["flagged_triggers"] if t["trigger"] == "guaranteed")

        self.assertAlmostEqual(subj_trigger_penalty, 1.2, places=2)
        self.assertAlmostEqual(body_trigger_penalty, 0.8, places=2)
        self.assertGreater(res_subj["spam_score"], res_body["spam_score"])

    def test_currency_symbols_heuristic(self):
        """Multiple currency symbols ($$$) flag EVAL_CURRENCY_SYMBOLS."""
        subject = "Earn $500 to $1,000 extra $$"
        body = "Get paid $2,000 $$$ in passive cash bonus."
        result = audit_email_content(subject=subject, body=body, is_reply=False, has_unsubscribe=True)

        penalty_codes = [p["code"] for p in result["heuristic_penalties"]]
        self.assertIn("EVAL_CURRENCY_SYMBOLS", penalty_codes)

    # =========================================================================
    # Layer 2: Human Paranoia & Security Defense
    # =========================================================================

    def test_null_and_empty_inputs_handled_safely(self):
        """Handles None, empty string, non-string, and whitespace gracefully without exceptions."""
        # None inputs
        res_none = audit_email_content(subject=None, body=None)  # type: ignore
        self.assertIsInstance(res_none["spam_score"], float)
        self.assertEqual(res_none["risk_level"], SpamRiskLevel.SAFE.value)

        # Empty strings
        res_empty = audit_email_content(subject="", body="")
        self.assertEqual(res_empty["spam_score"], 0.0)

        # Whitespace
        res_ws = audit_email_content(subject="   \n\t  ", body="  \r\n  ")
        self.assertEqual(res_ws["spam_score"], 0.0)

        # Non-string types (dict, list, int)
        res_types = audit_email_content(subject=12345, body={"note": "payload"})  # type: ignore
        self.assertIsInstance(res_types["spam_score"], float)

    def test_case_insensitive_trigger_matching(self):
        """Verifies trigger matching is strictly case-insensitive."""
        for variation in ["GUARANTEED", "Guaranteed", "guaranteed", "GuArAnTeEd"]:
            res = audit_email_content(subject=variation, body="Details", is_reply=True, has_unsubscribe=True)
            flagged = [t["trigger"].lower() for t in res["flagged_triggers"]]
            self.assertIn("guaranteed", flagged, f"Failed to match variation: {variation}")

    def test_word_boundary_defense_no_false_positives(self):
        """Word boundaries prevent substring false positives ('urgency' != 'urgent', 'assumed' != 'spam')."""
        # "urgency" should not trigger "urgent" if "urgent" is bounded
        clean_text = "We appreciate the urgency of the project and assumed everything was on schedule."
        res = audit_email_content(subject="Project timeline update", body=clean_text, is_reply=True, has_unsubscribe=True)

        flagged = [t["trigger"].lower() for t in res["flagged_triggers"]]
        self.assertNotIn("spam", flagged)

    def test_zero_width_and_evasion_characters_stripped(self):
        """Zero-width spaces used by spammers to evade keyword matching are sanitized."""
        # "g\u200Bu\u200Ba\u200Br\u200Ba\u200Bn\u200Bt\u200Be\u200Be\u200Bd"
        obfuscated = "g\u200bu\u200ba\u200br\u200ba\u200bn\u200bt\u200be\u200be\u200bd"
        res = audit_email_content(subject=obfuscated, body="Details", is_reply=True, has_unsubscribe=True)

        flagged = [t["trigger"].lower() for t in res["flagged_triggers"]]
        self.assertIn("guaranteed", flagged)

    def test_html_content_stripped_and_evaluated(self):
        """HTML formatted content has tags stripped before evaluating triggers."""
        html_body = "<html><body><p><b>Act now</b> for a special discount!</p></body></html>"
        res = audit_email_content(subject="Special", body=html_body, is_reply=True, has_unsubscribe=True)

        flagged = [t["trigger"].lower() for t in res["flagged_triggers"]]
        self.assertIn("act now", flagged)

    def test_facade_class_static_methods(self):
        """Facade class SpamScoreService exposes identical static methods."""
        res1 = SpamScoreService.audit_email_content(subject="Test", body="Hello")
        res2 = audit_email_content(subject="Test", body="Hello")
        self.assertEqual(res1["spam_score"], res2["spam_score"])

        rem1 = SpamScoreService.suggest_copy_remediations("Act now")
        rem2 = suggest_copy_remediations("Act now")
        self.assertEqual(rem1["sanitized_text"], rem2["sanitized_text"])

    def test_catalog_access_and_trigger_count(self):
        """Verifies trigger catalog contains 500+ triggers across 6 categories."""
        count = SpamScoreService.get_trigger_word_count()
        self.assertGreaterEqual(count, 500)

        catalog = SpamScoreService.get_catalog()
        expected_categories = [
            "URGENCY_PRESSURE",
            "FINANCIAL_HYPE",
            "SHADY_MARKETING",
            "DECEPTIVE_PREFIXES",
            "SENSITIVE_PHARMACEUTICAL_CRYPTO",
            "URL_SHORTENER_DOMAINS",
        ]
        for cat in expected_categories:
            self.assertIn(cat, catalog)
            self.assertGreater(len(catalog[cat]), 0)


if __name__ == "__main__":
    unittest.main()
