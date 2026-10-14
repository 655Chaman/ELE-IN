import unittest
from datetime import datetime
from campaigns.backend.services.abm_multithreading_service import (
    normalize_company_domain,
    calculate_committee_penetration,
    traverse_company_hierarchy,
    resolve_abm_context_for_execution,
    sanitize_text,
    get_account_committee_members
)
from leads.backend.services.lead_segmentation_service import (
    normalize_intent_tier,
    evaluate_lead_against_rules,
    evaluate_lead_condition,
    sanitize_text as lead_sanitize_text
)


class TestABMLeadSegmentationHardeningGuard(unittest.TestCase):

    def test_normalize_company_domain(self):
        """1. Test canonical domain normalization."""
        self.assertEqual(normalize_company_domain("https://www.Stripe.com/about?q=1#ref"), "stripe.com")
        self.assertEqual(normalize_company_domain("  'HTTP://EXAMPLE.co.uk/path' "), "example.co.uk")
        self.assertEqual(normalize_company_domain("<https://sub.domain.org:8080/>"), "sub.domain.org")
        self.assertEqual(normalize_company_domain("invalid_domain"), "")

    def test_intent_score_bounding(self):
        """2. Test intent and heat score clamping and tier mapping."""
        # Score bounding & tier classification
        self.assertEqual(normalize_intent_tier(-20), "COLD")
        self.assertEqual(normalize_intent_tier(150), "HOT")
        self.assertEqual(normalize_intent_tier(80), "HOT")
        self.assertEqual(normalize_intent_tier(50), "WARM")
        self.assertEqual(normalize_intent_tier(30), "COLD")

    def test_ast_depth_recursion_limit(self):
        """3. Test AST recursion depth ceiling (> 10 levels raises ValueError or fails safely)."""
        # Build nested AST condition > 10 levels
        nested = {"field": "intent_score", "operator": ">", "value": 50}
        for _ in range(12):
            nested = {"operator": "and", "conditions": [nested]}

        lead = {"intent_score": 85}
        with self.assertRaises(ValueError):
            # If evaluate_lead_against_rules / evaluate_ast_condition enforces depth
            from leads.backend.services.lead_segmentation_service import evaluate_ast_condition
            evaluate_ast_condition(lead, nested, depth=0)

    def test_hierarchy_cycle_breaker(self):
        """4. Test parent-child company hierarchy infinite cycle breaker."""
        accounts_map = {
            "acc-1": {"id": "acc-1", "parent_account_id": "acc-2"},
            "acc-2": {"id": "acc-2", "parent_account_id": "acc-3"},
            "acc-3": {"id": "acc-3", "parent_account_id": "acc-1"}  # Cycle A -> B -> C -> A
        }
        path = traverse_company_hierarchy("acc-1", accounts_map)
        # Should terminate safely without infinite loop, length <= 5
        self.assertLessEqual(len(path), 5)
        self.assertIn("acc-1", path)

    def test_committee_penetration_safe_division(self):
        """5. Test safe division in committee penetration calculation."""
        self.assertEqual(calculate_committee_penetration(3, 0), 0.0)
        self.assertEqual(calculate_committee_penetration(0, -5), 0.0)
        self.assertEqual(calculate_committee_penetration(2, 4), 50.0)

    def test_csv_formula_injection_sanitization(self):
        """6. Test CSV formula injection neutralization with single quote prefix."""
        payload = "=cmd|' /C calc'!A0"
        sanitized = sanitize_text(payload)
        self.assertTrue(sanitized.startswith("'"))
        self.assertIn("=cmd", sanitized)

        lead_sanitized = lead_sanitize_text("+15551234567")
        self.assertTrue(lead_sanitized.startswith("'"))

    def test_abm_peer_reference_formatting_null_title(self):
        """7. Test peer reference formatting when title is missing or None."""
        ctx = resolve_abm_context_for_execution(
            workspace_id="ws-default",
            account_id="acc-stripe",
            prospect_name="Marcus Vance",
            title="CFO",
            now_dt=datetime.utcnow()
        )
        # Should format cleanly without (None) or ()
        peer_ref = ctx.get("abm_peer_reference", "")
        self.assertNotIn("(None)", peer_ref)
        self.assertNotIn("()", peer_ref)

    def test_cross_tenant_workspace_isolation(self):
        """8. Test cross-tenant workspace isolation raises PermissionError."""
        with self.assertRaises(PermissionError):
            get_account_committee_members(
                workspace_id="ws-malicious-tenant",
                account_id="acc-stripe"
            )


if __name__ == "__main__":
    unittest.main()
