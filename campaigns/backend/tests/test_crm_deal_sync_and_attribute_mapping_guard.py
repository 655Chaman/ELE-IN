import unittest
from typing import Dict, Any, List

from integrations.backend.services.elein_crm_service import (
    _PROCESSED_DEAL_EVENTS,
    _DEAL_STATE_LEDGER,
    _DEAL_WORKSPACE_OWNER,
    validate_crm_field_mappings,
    normalize_crm_deal_stage,
    map_canonical_to_provider_stage,
    _sanitize_deal_amount,
    _sanitize_currency,
    sync_crm_deal_stage_event,
)


class FakeSupabaseForTest:
    def __init__(self):
        self.tables = {
            "leads": [],
            "campaigns": [],
            "campaign_enrollments": [],
            "campaign_execution_states": [],
            "crm_deals": [],
        }

    def table(self, name: str):
        class FakeQuery:
            def __init__(self, rows):
                self._rows = rows
                self._filters = {}
                self._pending_update = None

            def select(self, *args, **kwargs):
                return self

            def eq(self, key, val):
                self._filters[key] = val
                return self

            def limit(self, n):
                return self

            def update(self, payload):
                self._pending_update = dict(payload)
                return self

            def upsert(self, payload, **kwargs):
                return self

            def execute(self):
                matched = []
                for r in self._rows:
                    ok = True
                    for k, v in self._filters.items():
                        if str(r.get(k)) != str(v):
                            ok = False
                            break
                    if ok:
                        if self._pending_update is not None:
                            r.update(self._pending_update)
                        matched.append(r)
                class Res:
                    data = matched
                return Res()

        return FakeQuery(self.tables.setdefault(name, []))


class TestCrmDealSyncAndAttributeMappingGuard(unittest.TestCase):
    def setUp(self):
        _PROCESSED_DEAL_EVENTS.clear()
        _DEAL_STATE_LEDGER.clear()
        _DEAL_WORKSPACE_OWNER.clear()

    def test_validate_crm_field_mappings_valid(self):
        """Test 1: Validates clean field mappings dict with allowed source fields."""
        mappings = {
            "email": "contact_email",
            "first_name": "fname",
            "last_name": "lname",
            "company": "company_name"
        }
        allowed = {"email", "first_name", "last_name", "company", "title", "phone", "deal_stage", "deal_amount"}
        is_valid, errors, normalized = validate_crm_field_mappings(mappings, allowed_source_fields=allowed)
        self.assertTrue(is_valid)
        self.assertEqual(errors, [])
        self.assertEqual(normalized["email"], "contact_email")
        self.assertEqual(normalized["first_name"], "fname")

    def test_validate_crm_field_mappings_rejects_empty_and_invalid(self):
        """Test 2: Rejects non-dict, empty keys/values, circular mappings, or disallowed fields."""
        # Non-dict
        is_valid, errors, _ = validate_crm_field_mappings("not-a-dict")
        self.assertFalse(is_valid)

        # Empty keys/values & disallowed fields & circular mapping
        mappings = {
            "": "empty_key",
            "email": "",
            "unauthorized_field": "some_dest",
            "email": "email" # circular src == dst
        }
        allowed = {"email", "first_name"}
        is_valid, errors, normalized = validate_crm_field_mappings(mappings, allowed_source_fields=allowed)
        self.assertFalse(is_valid)
        self.assertTrue(any("empty" in e.lower() or "source field" in e.lower() or "circular" in e.lower() for e in errors))

    def test_normalize_crm_deal_stage_hubspot_and_salesforce(self):
        """Test 3: Tests bi-directional mapping across HubSpot and Salesforce stage names."""
        # HubSpot
        self.assertEqual(normalize_crm_deal_stage("lead", "hubspot"), "discovery")
        self.assertEqual(normalize_crm_deal_stage("subscriber", "hubspot"), "discovery")
        self.assertEqual(normalize_crm_deal_stage("mql", "hubspot"), "demo_completed")
        self.assertEqual(normalize_crm_deal_stage("sql", "hubspot"), "proposal_sent")
        self.assertEqual(normalize_crm_deal_stage("customer", "hubspot"), "closed_won")
        self.assertEqual(normalize_crm_deal_stage("evangelist", "hubspot"), "closed_lost")

        # Salesforce
        self.assertEqual(normalize_crm_deal_stage("prospecting", "salesforce"), "discovery")
        self.assertEqual(normalize_crm_deal_stage("qualification", "salesforce"), "discovery")
        self.assertEqual(normalize_crm_deal_stage("needs analysis", "salesforce"), "demo_completed")
        self.assertEqual(normalize_crm_deal_stage("value proposition", "salesforce"), "demo_completed")
        self.assertEqual(normalize_crm_deal_stage("proposal/price quote", "salesforce"), "proposal_sent")
        self.assertEqual(normalize_crm_deal_stage("negotiation/review", "salesforce"), "proposal_sent")
        self.assertEqual(normalize_crm_deal_stage("closed won", "salesforce"), "closed_won")
        self.assertEqual(normalize_crm_deal_stage("closed lost", "salesforce"), "closed_lost")

    def test_map_canonical_to_provider_stage(self):
        """Test 4: Tests reverse translation to provider stage strings."""
        self.assertEqual(map_canonical_to_provider_stage("discovery", "hubspot"), "appointmentscheduled")
        self.assertEqual(map_canonical_to_provider_stage("demo_completed", "hubspot"), "presentationscheduled")
        self.assertEqual(map_canonical_to_provider_stage("proposal_sent", "hubspot"), "decisionmakerboughtin")
        self.assertEqual(map_canonical_to_provider_stage("closed_won", "hubspot"), "closedwon")
        self.assertEqual(map_canonical_to_provider_stage("closed_lost", "hubspot"), "closedlost")

        self.assertEqual(map_canonical_to_provider_stage("discovery", "salesforce"), "Qualification")
        self.assertEqual(map_canonical_to_provider_stage("demo_completed", "salesforce"), "Value Proposition")
        self.assertEqual(map_canonical_to_provider_stage("proposal_sent", "salesforce"), "Proposal/Price Quote")
        self.assertEqual(map_canonical_to_provider_stage("closed_won", "salesforce"), "Closed Won")
        self.assertEqual(map_canonical_to_provider_stage("closed_lost", "salesforce"), "Closed Lost")

    def test_sanitize_deal_amount_and_currency(self):
        """Test 5: Tests parsing '$2,500.00', negative numbers clamped to 0.0, NaN handled safely, and uppercase 3-letter currency."""
        self.assertEqual(_sanitize_deal_amount("$2,500.00"), 2500.0)
        self.assertEqual(_sanitize_deal_amount("1500 USD"), 1500.0)
        self.assertEqual(_sanitize_deal_amount(-500.0), 0.0)
        self.assertEqual(_sanitize_deal_amount(float("nan")), 0.0)
        self.assertEqual(_sanitize_deal_amount(None), 0.0)
        # Extreme float clamped to 1,000,000,000.0
        self.assertEqual(_sanitize_deal_amount(2e10), 1_000_000_000.0)

        self.assertEqual(_sanitize_currency("usd"), "USD")
        self.assertEqual(_sanitize_currency("eur"), "EUR")
        self.assertEqual(_sanitize_currency("GBP"), "GBP")
        self.assertEqual(_sanitize_currency(None), "USD")
        self.assertEqual(_sanitize_currency("invalid"), "USD")

    def test_sync_inbound_deal_event_stale_event_rejected(self):
        """Test 6: Older timestamp event does not overwrite newer deal state in ledger."""
        db = FakeSupabaseForTest()
        # First sync at t=2000 (Closed Won)
        res1 = sync_crm_deal_stage_event(
            workspace_id="ws-stale",
            deal_id="deal-999",
            raw_stage="closedwon",
            updated_at=2000.0,
            supabase=db,
        )
        self.assertEqual(res1["normalized_stage"], "closed_won")

        # Second sync at t=1000 (Older timestamp trying to move back to discovery)
        res2 = sync_crm_deal_stage_event(
            workspace_id="ws-stale",
            deal_id="deal-999",
            raw_stage="discovery",
            updated_at=1000.0,
            supabase=db,
        )
        self.assertTrue(res2["stale_event"])
        self.assertEqual(res2["status"], "ignored_stale_event")
        # Ledger state remains closed_won
        self.assertEqual(_DEAL_STATE_LEDGER[("ws-stale", "deal-999")]["normalized_stage"], "closed_won")

    def test_sync_inbound_deal_event_cross_tenant_idor_blocked(self):
        """Test 7: Verifies PermissionError when accessing a deal belonging to another workspace."""
        # Register deal-100 to ws-alpha
        sync_crm_deal_stage_event(
            workspace_id="ws-alpha",
            deal_id="deal-100",
            raw_stage="discovery",
        )

        # Attempt to access deal-100 from ws-beta
        with self.assertRaises(PermissionError):
            sync_crm_deal_stage_event(
                workspace_id="ws-beta",
                deal_id="deal-100",
                raw_stage="closedwon",
            )

    def test_formula_injection_defense_in_deal_name(self):
        """Test 8: Verifies '\'' prefixing on '=cmd|'/C calc'!A0' in deal names."""
        malicious_name = "=cmd|'/C calc'!A0"
        res = sync_crm_deal_stage_event(
            workspace_id="ws-formula",
            deal_id="deal-formula",
            raw_stage="discovery",
            deal_name=malicious_name,
        )
        saved_name = res["deal_name"]
        self.assertTrue(saved_name.startswith("'") or not saved_name.startswith("="))
        from integrations.backend.services.elein_crm_service import _sanitize_crm_text
        sanitized = _sanitize_crm_text(malicious_name)
        self.assertFalse(sanitized.startswith("="))
