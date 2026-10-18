"""
Three-Layer Paranoia Test Automation Suite — Issue 7:
Spintax & Linguistic Variation Multiplier Core Mechanics, Deliverability Entropy, and API Routing
===================================================================================================
- Layer 0 (Foundational): Spintax combinations math (flat, multi-block, nested),
  entropy classification (CRITICAL_SPAM_RISK, MODERATE_VARIATION, HIGH_DIVERSITY, ENTERPRISE_IMMUNITY),
  deterministic per-lead seed resolution, and multi-variant previewers.
- Layer 1 (Environmental): B2B linguistic synonym generator with Mustache variable and pre-existing
  spintax preservation, depth and combination bomb bounding, malformed brace diagnostics,
  empty option handling, and extreme text clamping.
- Layer 2 (Human Paranoia & Security Defense): Full FastAPI endpoint testing for
  /api/elein/spintax/analyze, /api/elein/spintax/generate, and /api/elein/spintax/preview,
  plus EleInNodeExecutor channel dispatch telemetry verification (email, message, connection).
"""

import os
import unittest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    validate_campaign_nodes_templates,
    MAX_SPINTAX_DEPTH,
    MAX_SPINTAX_COMBINATIONS,
    MAX_TEMPLATE_CHARS,
)
from campaigns.backend.routers import elein
from campaigns.backend.routers.elein import (
    SpintaxAnalyzeRequest,
    SpintaxGenerateRequest,
    SpintaxPreviewRequest,
    analyze_spintax_endpoint,
    generate_spintax_endpoint,
    preview_spintax_endpoint,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from core.backend.api.auth_dep import get_current_workspace


class TestSpintaxAndLinguisticVariationMultiplier(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws_spintax_test"
        self.mock_supabase = MagicMock()
        self.mock_supabase.rpc.return_value.execute.return_value.data = {"success": True}
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        self.app = FastAPI()
        self.app.include_router(elein.router, prefix="/api/elein")
        self.app.dependency_overrides[get_current_workspace] = lambda: self.workspace_id
        self.client = TestClient(self.app)

    # =========================================================================
    # LAYER 0: Foundational Layer (Core Mechanics)
    # =========================================================================

    def test_calculate_spintax_combinations_flat(self):
        """Layer 0: Flat spintax '{Hi|Hello|Hey}' yields exactly 3 combinations."""
        text = "{Hi|Hello|Hey}"
        combs = calculate_spintax_combinations(text)
        self.assertEqual(combs, 3)

    def test_calculate_spintax_combinations_multi_block(self):
        """Layer 0: Multi-block spintax '{Hi|Hello} {{first_name}}, {a|b|c}' returns 2 * 3 = 6."""
        text = "{Hi|Hello} {{first_name}}, {a|b|c}"
        combs = calculate_spintax_combinations(text)
        self.assertEqual(combs, 6)

    def test_calculate_spintax_combinations_nested(self):
        """Layer 0: Nested spintax '{a|{b|c|d}}' returns 1 + 3 = 4 combinations."""
        text = "{a|{b|c|d}}"
        combs = calculate_spintax_combinations(text)
        self.assertEqual(combs, 4)

    def test_calculate_spintax_combinations_nested_deep_tree(self):
        """Layer 0: Branching nested spintax '{A|{B|C}|{D|{E|F}}}' returns 1 + 2 + 1 + 2 = 6."""
        text = "{A|{B|C}|{D|{E|F}}}"
        combs = calculate_spintax_combinations(text)
        self.assertEqual(combs, 6)

    def test_calculate_spintax_combinations_no_spintax_returns_one(self):
        """Layer 0: Plain text with no spintax blocks returns 1 combination."""
        self.assertEqual(calculate_spintax_combinations("Plain static outreach copy."), 1)
        self.assertEqual(calculate_spintax_combinations(""), 1)
        self.assertEqual(calculate_spintax_combinations(None), 1)

    def test_calculate_spintax_combinations_masks_double_braces(self):
        """Layer 0: Double-brace Liquid/Mustache tags {{var}} and {{var | fallback}} are masked and never counted as spintax."""
        text = "Hi {{first_name | there}}, welcome to {{company | your company}}!"
        self.assertEqual(calculate_spintax_combinations(text), 1)

        text_mixed = "{Hi|Hello} {{first_name | there}}, how is {{company}}?"
        self.assertEqual(calculate_spintax_combinations(text_mixed), 2)

    def test_calculate_spintax_combinations_single_choice_blocks(self):
        """Layer 0: Single-choice block '{only_one}' without a pipe has no alternatives and returns 1."""
        text = "Hello {only_one} world"
        self.assertEqual(calculate_spintax_combinations(text), 1)

    def test_calculate_spintax_entropy_ratings(self):
        """Layer 0: Verifies CRITICAL_SPAM_RISK (<5), MODERATE_VARIATION, HIGH_DIVERSITY, and ENTERPRISE_IMMUNITY."""
        # 1. Critical Spam Risk (<5 combinations or low diversity ratio)
        low_res = calculate_spintax_entropy("{Hi|Hello} {{first_name}}", campaign_lead_count=1000)
        self.assertEqual(low_res["entropy_rating"], "CRITICAL_SPAM_RISK")
        self.assertEqual(low_res["total_combinations"], 2)

        # 2. Moderate Variation (5 <= combinations < 50) with sufficient diversity ratio
        mod_res = calculate_spintax_entropy("{1|2|3|4|5|6|7|8|9|10} {a|b}", campaign_lead_count=100)
        self.assertEqual(mod_res["entropy_rating"], "MODERATE_VARIATION")
        self.assertEqual(mod_res["total_combinations"], 20)

        # 3. High Diversity (50 <= combinations < 200)
        high_res = calculate_spintax_entropy("{1|2|3|4|5|6|7|8|9|10} {a|b|c|d|e|f|g|h}", campaign_lead_count=100)
        self.assertEqual(high_res["entropy_rating"], "HIGH_DIVERSITY")
        self.assertEqual(high_res["total_combinations"], 80)

        # 4. Enterprise Immunity (200+ combinations)
        ent_res = calculate_spintax_entropy("{1|2|3|4|5|6|7|8|9|10} {a|b|c|d|e} {A|B|C|D|E}", campaign_lead_count=1000)
        self.assertEqual(ent_res["entropy_rating"], "ENTERPRISE_IMMUNITY")
        self.assertEqual(ent_res["total_combinations"], 250)

    def test_calculate_spintax_entropy_diversity_ratio_calculation(self):
        """Layer 0: Computes diversity_ratio = round(total_combinations / campaign_lead_count, 3)."""
        res = calculate_spintax_entropy("{a|b|c|d|e}", campaign_lead_count=200)
        self.assertEqual(res["total_combinations"], 5)
        self.assertEqual(res["diversity_ratio"], 0.025)
        # Even though combinations == 5, diversity_ratio < 0.05 triggers CRITICAL_SPAM_RISK
        self.assertEqual(res["entropy_rating"], "CRITICAL_SPAM_RISK")

    def test_calculate_spintax_entropy_recommendations_actionability(self):
        """Layer 0: Generates structured recommendations for missing greeting, hook, CTA, or signoff variations."""
        plain_text = "Hi {{first_name}}, check this out. Best, Alex"
        res = calculate_spintax_entropy(plain_text, campaign_lead_count=500)
        recs = res.get("recommendations", [])
        self.assertTrue(any("greeting" in r.lower() for r in recs))
        self.assertTrue(any("opening hook" in r.lower() for r in recs))
        self.assertTrue(any("call-to-action" in r.lower() for r in recs))
        self.assertTrue(any("sign-off" in r.lower() for r in recs))

    def test_preview_spintax_variants(self):
        """Layer 0: Returns distinct rendered variations without unrendered '{' or '|'."""
        text = "{Hi|Hello|Hey} {{first_name}}, {a|b|c}!"
        variants = preview_spintax_variants(text, count=5, seed="lead_preview_1")
        self.assertGreaterEqual(len(variants), 3)
        self.assertLessEqual(len(variants), 5)
        for v in variants:
            # Mask double brace {{first_name}}
            stripped = v.replace("{{first_name}}", "")
            self.assertNotIn("{", stripped)
            self.assertNotIn("}", stripped)
            self.assertNotIn("|", stripped)

    def test_preview_spintax_variants_clamping(self):
        """Layer 0: Clamps variant count between 1 and 20."""
        text = "{1|2|3|4|5|6|7|8|9|10}"
        self.assertEqual(len(preview_spintax_variants(text, count=-5)), 1)
        self.assertLessEqual(len(preview_spintax_variants(text, count=100)), 20)

    def test_deterministic_per_lead_seed_consistency(self):
        """Layer 0: Same lead seed produces identical phrasing across multiple calls; different seeds produce distinct phrasings."""
        text = "{Hi|Hello|Hey} {{first_name}}, {quick chat|brief call|10 mins} about {scaling|growth|pipeline}?"
        seed_a = "lead_sarah_123"
        seed_b = "lead_john_456"

        render_a1 = resolve_spintax(text, seed=seed_a)
        render_a2 = resolve_spintax(text, seed=seed_a)
        render_b = resolve_spintax(text, seed=seed_b)

        self.assertEqual(render_a1, render_a2)
        # With 3*3*3=27 variants, two distinct seeds should resolve differently
        self.assertNotEqual(render_a1, render_b)

    # =========================================================================
    # LAYER 1: Environmental Failure Analysis
    # =========================================================================

    def test_generate_linguistic_spintax_greetings_hooks_ctas_signoffs(self):
        """Layer 1: Plain outbound text converts into spintax with greetings, hooks, CTAs, signoffs."""
        text = "Hi {{first_name}}, I noticed your recent updates. Wanted to reach out because I thought this could be helpful. Are you free for a quick chat? Best, Alex"
        res = generate_linguistic_spintax(text)

        spintax_text = res["spintax_text"]
        self.assertIn("{Hi|Hello|Hey}", spintax_text)
        self.assertIn("{I saw|I noticed|came across}", spintax_text)
        self.assertIn("{recent updates|recent momentum|recent progress}", spintax_text)
        self.assertIn("{wanted to reach out|reaching out because|wanted to connect}", spintax_text)
        self.assertIn("{thought it might be relevant|thought this could be helpful|thought you might find this interesting}", spintax_text)
        self.assertIn("{Are you free for a quick chat|Open to a brief 10-minute call|Would you be open to connecting for a quick chat}", spintax_text)
        self.assertIn("{Best,|Thanks,|Cheers,}", spintax_text)
        self.assertGreaterEqual(res["replacements_count"], 5)
        self.assertEqual(res["entropy"]["entropy_rating"], "ENTERPRISE_IMMUNITY")

    def test_generate_linguistic_spintax_preserves_mustache_variables(self):
        """Layer 1: Double-brace variables like {{first_name}}, {{company}}, {{title}} are 100% untouched and uncorrupted."""
        text = "Hello {{first_name}}, I noticed your role as {{title}} at {{company | your firm}}. Are you free for a quick chat? Regards, Alex"
        res = generate_linguistic_spintax(text)
        spintax_text = res["spintax_text"]

        self.assertIn("{{first_name}}", spintax_text)
        self.assertIn("{{title}}", spintax_text)
        self.assertIn("{{company | your firm}}", spintax_text)

    def test_generate_linguistic_spintax_preserves_existing_spintax(self):
        """Layer 1: Pre-existing spintax blocks are preserved and not double-wrapped or mangled."""
        text = "{Bonjour|Salut} {{first_name}}, I noticed your profile. Are you free for a quick call? Best, Alex"
        res = generate_linguistic_spintax(text)
        spintax_text = res["spintax_text"]

        self.assertIn("{Bonjour|Salut}", spintax_text)
        self.assertNotIn("{{Bonjour|Salut}}", spintax_text)
        self.assertNotIn("{{Hi|Hello|Hey}}", spintax_text)

    def test_generate_linguistic_spintax_intensity_levels(self):
        """Layer 1: Supports intensity options ('balanced', 'aggressive', 'light')."""
        text = "Hi {{first_name}}, let's discuss some questions to help you. Best, Alex"
        res_balanced = generate_linguistic_spintax(text, intensity="balanced")
        res_aggressive = generate_linguistic_spintax(text, intensity="aggressive")

        # Aggressive replaces 'discuss', 'questions', 'help'
        self.assertGreater(res_aggressive["replacements_count"], res_balanced["replacements_count"])
        self.assertIn("{discuss|explore|chat about}", res_aggressive["spintax_text"])

    def test_generate_linguistic_spintax_idempotent_reapplication(self):
        """Layer 1: Re-running generator on already-generated spintax is safe and does not double-wrap blocks."""
        first_pass = generate_linguistic_spintax("Hi {{first_name}}, are you free for a quick chat? Best, Alex")
        second_pass = generate_linguistic_spintax(first_pass["spintax_text"])

        self.assertEqual(first_pass["spintax_text"], second_pass["spintax_text"])
        self.assertEqual(second_pass["replacements_count"], 0)

    def test_combinatorial_spintax_bomb_depth_cap(self):
        """Layer 1: Deeply nested spintax (>5 levels) is flagged with clear diagnostic error."""
        deep_bomb = "{1|{2|{3|{4|{5|{6|7}}}}}}"
        val = validate_template_and_spintax_syntax(deep_bomb)
        self.assertFalse(val["valid"])
        self.assertTrue(any("nesting depth exceeds maximum" in err.lower() for err in val["errors"]))

    def test_combinatorial_spintax_combinations_cap_safety(self):
        """Layer 1: Combinations counter clamps at 100_000_000 to prevent integer overflow and hangs."""
        # 10 blocks of 10 choices = 10^10 = 10,000,000,000 (exceeds cap)
        blocks = " ".join(["{1|2|3|4|5|6|7|8|9|10}" for _ in range(10)])
        combs = calculate_spintax_combinations(blocks)
        self.assertEqual(combs, MAX_SPINTAX_COMBINATIONS)

    def test_malformed_spintax_unclosed_braces_diagnostics(self):
        """Layer 1: Unclosed opening brace '{Hi|Hello' returns clean diagnostic without crashing."""
        val = validate_template_and_spintax_syntax("{Hi|Hello {{first_name}}")
        self.assertFalse(val["valid"])
        self.assertTrue(any("unclosed opening brace" in err.lower() for err in val["errors"]))

    def test_unmatched_closing_brace_diagnostics(self):
        """Layer 1: Unmatched closing brace 'Hi|Hello}' returns clean diagnostic without crashing."""
        val = validate_template_and_spintax_syntax("Hi|Hello} {{first_name}}")
        self.assertFalse(val["valid"])
        self.assertTrue(any("unmatched closing brace" in err.lower() for err in val["errors"]))

    def test_empty_spintax_options_handling(self):
        """Layer 1: Empty spintax options '{|}', '{}', and '{a||b}' are handled gracefully without crash."""
        val_empty = validate_template_and_spintax_syntax("{}")
        self.assertFalse(val_empty["valid"])
        self.assertTrue(any("empty curly braces" in err.lower() for err in val_empty["errors"]))

        val_pipe_only = validate_template_and_spintax_syntax("{|}")
        self.assertFalse(val_pipe_only["valid"])
        self.assertTrue(any("no non-empty options" in err.lower() for err in val_pipe_only["errors"]))

        # Resolution of '{a||b}' does not crash and picks non-empty option
        resolved = resolve_spintax("{a||b}", seed="seed_empty_opt")
        self.assertIn(resolved, ("a", "b"))

    def test_spintax_resolution_timeout_safety(self):
        """Layer 1: Spintax resolution honors timeout_ms safety threshold gracefully."""
        text = "{Hi|Hello} world"
        resolved = resolve_spintax(text, timeout_ms=500)
        self.assertIn(resolved, ("Hi world", "Hello world"))

    def test_extreme_text_length_clamping(self):
        """Layer 1: Template exceeding MAX_TEMPLATE_CHARS (10,000) is rejected by validator and clamped in resolver."""
        huge_text = "A" * 20000 + " {Hi|Hello}"
        val = validate_template_and_spintax_syntax(huge_text)
        self.assertFalse(val["valid"])
        self.assertTrue(any("exceeds maximum allowed length" in err.lower() for err in val["errors"]))

        resolved = resolve_spintax(huge_text, seed="seed_huge")
        self.assertLessEqual(len(resolved), MAX_TEMPLATE_CHARS + 20)

    def test_spintax_with_empty_or_whitespace_options(self):
        """Layer 1: Resolves options with whitespace without crashing."""
        res = resolve_spintax("{Hello|  }", seed="seed_whitespace")
        self.assertIn(res, ("Hello", ""))

    def test_spintax_with_special_characters_and_newlines(self):
        """Layer 1: Spintax containing punctuation, commas, quotes, and newlines parses accurately."""
        text = "{\nHi,\n|\nHello!\n|\nHey?\n} {{first_name}}"
        res = resolve_spintax(text, seed="seed_newlines")
        self.assertTrue(res.endswith("{{first_name}}"))
        self.assertTrue(any(res.startswith(prefix) for prefix in ("\nHi,\n", "\nHello!\n", "\nHey?\n")))

    def test_calculate_spintax_entropy_invalid_syntax_error_handling(self):
        """Layer 1: Invalid template syntax returns valid=False and entropy_rating='INVALID'."""
        res = calculate_spintax_entropy("{unclosed|syntax {{first_name}}")
        self.assertFalse(res["valid"])
        self.assertEqual(res["entropy_rating"], "INVALID")
        self.assertEqual(res["total_combinations"], 0)
        self.assertIn("Fix template syntax errors", res["recommendations"][0])

    # =========================================================================
    # LAYER 2: Human Paranoia & Security Defense
    # =========================================================================

    def test_router_spintax_analyze_endpoint(self):
        """Layer 2: POST /api/elein/spintax/analyze returns HTTP 200 with complete entropy telemetry."""
        payload = {
            "template": "{Hi|Hello|Hey} {{first_name}}, {saw your work|loved your profile}. Are you open to a {quick chat|brief call}?",
            "campaign_lead_count": 100,
        }
        res = self.client.post("/api/elein/spintax/analyze", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["total_combinations"], 3 * 2 * 2)  # 12
        self.assertEqual(data["entropy_rating"], "MODERATE_VARIATION")
        self.assertAlmostEqual(data["diversity_ratio"], round(12 / 100, 3))
        self.assertIsInstance(data["recommendations"], list)
        self.assertEqual(data["max_depth_detected"], 1)

    def test_router_spintax_analyze_endpoint_invalid_template(self):
        """Layer 2: POST /api/elein/spintax/analyze handles malformed templates without throwing 500."""
        payload = {
            "template": "{unclosed|template {{first_name}",
            "campaign_lead_count": 100,
        }
        res = self.client.post("/api/elein/spintax/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["valid"])
        self.assertEqual(data["entropy_rating"], "INVALID")
        self.assertGreater(len(data["errors"]), 0)

    def test_router_spintax_generate_endpoint(self):
        """Layer 2: POST /api/elein/spintax/generate returns HTTP 200 with enriched text and entropy."""
        payload = {
            "text": "Hi {{first_name}}, I noticed your recent updates. Are you free for a quick chat? Best, Alex",
            "intensity": "balanced",
        }
        res = self.client.post("/api/elein/spintax/generate", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertIn("spintax_text", data)
        self.assertIn("{Hi|Hello|Hey}", data["spintax_text"])
        self.assertIn("entropy", data)
        self.assertEqual(data["entropy"]["entropy_rating"], "ENTERPRISE_IMMUNITY")
        self.assertGreaterEqual(data["replacements_count"], 3)

    def test_router_spintax_generate_endpoint_preserves_variables(self):
        """Layer 2: POST /api/elein/spintax/generate guarantees {{variables}} remain uncorrupted."""
        payload = {
            "text": "Hello {{first_name}}, saw your work at {{company}}. Best, {{sender_name}}",
            "intensity": "balanced",
        }
        res = self.client.post("/api/elein/spintax/generate", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("{{first_name}}", data["spintax_text"])
        self.assertIn("{{company}}", data["spintax_text"])
        self.assertIn("{{sender_name}}", data["spintax_text"])

    def test_router_spintax_preview_endpoint(self):
        """Layer 2: POST /api/elein/spintax/preview returns HTTP 200 with list of rendered variants."""
        payload = {
            "template": "{Hi|Hello|Hey} {{first_name}}, {a|b}!",
            "count": 4,
            "seed": "endpoint_seed_1",
        }
        res = self.client.post("/api/elein/spintax/preview", json=payload)
        self.assertEqual(res.status_code, 200)
        variants = res.json()
        self.assertIsInstance(variants, list)
        self.assertGreaterEqual(len(variants), 2)
        self.assertLessEqual(len(variants), 4)

    def test_router_spintax_preview_endpoint_seed_determinism(self):
        """Layer 2: POST /api/elein/spintax/preview with identical seed produces identical variants."""
        payload = {
            "template": "{Hi|Hello|Hey} {{first_name}}, {alpha|beta|gamma}",
            "count": 3,
            "seed": "static_session_seed",
        }
        res1 = self.client.post("/api/elein/spintax/preview", json=payload)
        res2 = self.client.post("/api/elein/spintax/preview", json=payload)
        self.assertEqual(res1.json(), res2.json())

    def test_executor_interpolates_and_resolves_spintax_with_telemetry(self):
        """Layer 2: handle_send_email in EleInNodeExecutor resolves spintax and emits spintax_resolved=True."""
        executor = EleInNodeExecutor(workspace_id=self.workspace_id, supabase=self.mock_supabase)

        res = executor.handle_send_email(
            data={
                "to_email": "target@domain.com",
                "subject": "{Hello|Hi} {{first_name}}",
                "body": "{I noticed|I saw} your recent momentum at {{company}}",
                "first_name": "Sarah",
                "company": "Acme",
                "_lead_id": "lead_telemetry_1",
                "_current_node_id": "email_node_99",
            },
            linkedin_url="https://linkedin.com/in/target",
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res.get("spintax_resolved"))
        self.assertIn(res["subject"], ("Hello Sarah", "Hi Sarah"))
        self.assertIn(res["body"], ("I noticed your recent momentum at Acme", "I saw your recent momentum at Acme"))

    def test_executor_send_message_spintax_telemetry(self):
        """Layer 2: handle_send_message in EleInNodeExecutor resolves spintax and emits spintax_resolved=True."""
        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success", "branch": "then"}
        executor = EleInNodeExecutor(workspace_id=self.workspace_id, supabase=self.mock_supabase, worker=mock_worker)

        res = executor.handle_send_message(
            data={
                "message": "{Hi|Hello} {{first_name}}, great to connect!",
                "first_name": "Dave",
                "_lead_id": "lead_msg_1",
                "_current_node_id": "msg_node_1",
            },
            linkedin_url="https://linkedin.com/in/dave",
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res.get("spintax_resolved"))

    def test_executor_connection_request_spintax_telemetry(self):
        """Layer 2: handle_connection_request in EleInNodeExecutor resolves spintax and emits spintax_resolved=True."""
        mock_worker = MagicMock()
        mock_worker.send_connection_request.return_value = {"status": "success", "branch": "then"}
        executor = EleInNodeExecutor(workspace_id=self.workspace_id, supabase=self.mock_supabase, worker=mock_worker)

        res = executor.handle_connection_request(
            data={
                "note": "{Hi|Hey} {{first_name}}, let's connect!",
                "first_name": "Elena",
                "_lead_id": "lead_conn_1",
                "_current_node_id": "conn_node_1",
            },
            linkedin_url="https://linkedin.com/in/elena",
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res.get("spintax_resolved"))

    def test_executor_spintax_not_tagged_when_no_spintax_present(self):
        """Layer 2: When outbound copy contains no spintax, spintax_resolved is not flagged as True."""
        executor = EleInNodeExecutor(workspace_id=self.workspace_id, supabase=self.mock_supabase)

        res = executor.handle_send_email(
            data={
                "to_email": "static@domain.com",
                "subject": "Hello {{first_name}}",
                "body": "Saw your work at {{company}}",
                "first_name": "Lisa",
                "company": "Corp",
                "_lead_id": "lead_static_1",
            },
            linkedin_url="https://linkedin.com/in/static",
        )

        self.assertEqual(res["status"], "success")
        self.assertFalse(res.get("spintax_resolved"))

    def test_validate_campaign_nodes_templates_with_spintax(self):
        """Layer 2: validate_campaign_nodes_templates detects malformed spintax across sequence nodes."""
        nodes = [
            {"id": "node_valid", "data": {"body": "{Hi|Hello} {{first_name}}"}},
            {"id": "node_broken", "data": {"body": "{Unclosed|spintax {{first_name}}"}},
        ]
        errors = validate_campaign_nodes_templates(nodes)
        self.assertEqual(len(errors), 1)
        self.assertIn("node_broken", errors[0])
        self.assertIn("Unclosed opening brace", errors[0])


if __name__ == "__main__":
    unittest.main()
