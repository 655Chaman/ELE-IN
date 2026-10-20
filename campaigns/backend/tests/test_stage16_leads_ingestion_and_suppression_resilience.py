import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from leads.backend.services.suppression_service import (
    add_suppression_entries_bulk,
    retroactive_purge_suppressed_leads,
    normalize_suppression_domain,
    normalize_suppression_entry
)
from campaigns.backend.routers.elein import process_csv_background
from leads.backend.schemas.lead import (
    LeadBase,
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadListBase,
    LeadListCreate,
    LeadListResponse,
    SuppressionEntryCreate,
    SuppressionEntryResponse,
    DynamicRuleCondition,
    DynamicRuleConfig
)


class TestStage16LeadsIngestionAndSuppressionResilience(unittest.TestCase):
    """
    Stage 16 Paranoia Test Suite:
    Validates Ingestion Pipeline High-Fidelity, Suppression Resilience & Schema Modernization (Bridge 1 & 2):
    - Layer 0: Suppression bulk upsert with duplicate tolerance and single-entry recovery.
    - Layer 1: Retroactive domain purge pagination across >1,000 leads.
    - Layer 2: Custom variable preservation in metadata['custom_variables'] during CSV processing.
    - Layer 2: Modern Pydantic v2 schemas serialization and type safety.
    """

    def test_layer0_suppression_bulk_upsert_tolerance_and_resilience(self):
        """
        Layer 0 Foundational (B2-F03):
        add_suppression_entries_bulk must bulk-upsert suppression records with duplicate tolerance
        (ignore_duplicates=True) rather than failing entire batches on collision.
        """
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Simulate successful batch upsert
        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute.return_value = MagicMock(data=[{"id": "sup-1"}, {"id": "sup-2"}])

        # Also mock retroactive purge query calls so it doesn't fail
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_select.eq.return_value.range.return_value.execute.return_value = MagicMock(data=[])

        raw_entries = [
            {"email": "competitor@rival.com", "reason": "Competitor"},
            {"domain": "rivalcorp.com", "reason": "Rival Domain"},
            # In-batch duplicate of the first entry
            {"email": "competitor@rival.com", "reason": "Competitor Dupe"},
            # Invalid entry format
            {"domain": "invalid_domain_no_tld", "reason": "Bad"}
        ]

        result = add_suppression_entries_bulk(
            supabase=mock_supabase,
            workspace_id="ws-stage16",
            entries=raw_entries,
            trigger_retroactive_purge=False
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["inserted_count"], 2)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["rejected_count"], 1)

        # Verify upsert was called with ignore_duplicates=True
        mock_table.upsert.assert_called()
        call_args, call_kwargs = mock_table.upsert.call_args
        self.assertTrue(call_kwargs.get("ignore_duplicates"))

    def test_layer1_suppression_chunk_upsert_failure_single_entry_recovery(self):
        """
        Layer 1 Paranoia (B2-F03):
        When a batch upsert raises a DB exception (e.g. single unhandled constraint error in PostgREST),
        the system must fall back to single-entry recovery so 1 corrupted row does not discard
        all valid rows in the chunk.
        """
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # First call on chunk upsert raises an error; subsequent single-row calls succeed for valid rows
        first_call = True

        def mock_upsert_dispatch(chunk_or_row, ignore_duplicates=True):
            nonlocal first_call
            upsert_mock = MagicMock()
            if isinstance(chunk_or_row, list):
                # Batch upsert fails
                upsert_mock.execute.side_effect = RuntimeError("PostgREST batch unique constraint failure")
            else:
                # Single-entry recovery: succeed for row 1, fail for row 2
                if chunk_or_row.get("email") == "safe1@competitor.com":
                    upsert_mock.execute.return_value = MagicMock(data=[{"id": "sup-rec-1"}])
                else:
                    upsert_mock.execute.side_effect = RuntimeError("Row duplicate")
            return upsert_mock

        mock_table.upsert.side_effect = mock_upsert_dispatch

        raw_entries = [
            {"email": "safe1@competitor.com", "reason": "Batch Test 1"},
            {"email": "conflict2@competitor.com", "reason": "Batch Test 2"}
        ]

        result = add_suppression_entries_bulk(
            supabase=mock_supabase,
            workspace_id="ws-stage16-recovery",
            entries=raw_entries,
            trigger_retroactive_purge=False
        )

        self.assertEqual(result["status"], "success")
        # 1 recovered row succeeded, 1 failed in recovery and was counted as duplicate
        self.assertEqual(result["inserted_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)

    def test_layer1_retroactive_domain_purge_paginates_beyond_1000_leads(self):
        """
        Layer 1 Paranoia (B2-F04):
        Supabase / PostgREST clamps unpaginated queries to 1,000 rows.
        retroactive_purge_suppressed_leads must paginate through leads in 1,000-row chunks
        and match both lead['domain'] and email domain (@domain.com) across multiple pages.
        """
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Simulate 2 pages of leads:
        # Page 1: 1000 leads, index 50 has domain "blocked-corp.com"
        # Page 2: 250 leads, index 10 has email "lead@blocked-corp.com" (domain field empty)
        page1_leads = [{"id": f"lead-p1-{i}", "email": f"user{i}@normal.com", "domain": "normal.com"} for i in range(1000)]
        page1_leads[50]["domain"] = "blocked-corp.com"

        page2_leads = [{"id": f"lead-p2-{i}", "email": f"user{i}@normal.com", "domain": "normal.com"} for i in range(250)]
        page2_leads[10]["email"] = "vp@blocked-corp.com"
        page2_leads[10]["domain"] = None  # Requires domain derivation from email

        ranges_called = []

        def router_table(tbl_name):
            t = MagicMock()
            if tbl_name == "leads":
                def mock_select(fields):
                    s = MagicMock()
                    def mock_eq(field, val):
                        e = MagicMock()
                        def mock_range(start, end):
                            ranges_called.append((start, end))
                            r = MagicMock()
                            if start == 0:
                                r.execute.return_value = MagicMock(data=page1_leads)
                            else:
                                r.execute.return_value = MagicMock(data=page2_leads)
                            return r
                        e.range = mock_range
                        return e
                    s.eq = mock_eq
                    return s
                t.select = mock_select
                t.update.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                return t
            elif tbl_name == "campaign_enrollments":
                t.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "enr-50"}, {"id": "enr-p2-10"}]
                )
                return t
            elif tbl_name == "campaign_execution_states":
                t.update.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(
                    data=[{"id": "state-50"}, {"id": "state-p2-10"}]
                )
                return t
            return t

        mock_supabase.table.side_effect = router_table

        purge_result = retroactive_purge_suppressed_leads(
            supabase=mock_supabase,
            workspace_id="ws-stage16-pagination",
            linkedin_urls=[],
            emails=[],
            domains=["blocked-corp.com"]
        )

        # Verified 2 pages were queried: (0, 999) and (1000, 1999)
        self.assertEqual(len(ranges_called), 2)
        self.assertEqual(ranges_called[0], (0, 999))
        self.assertEqual(ranges_called[1], (1000, 1999))

        # Verified 2 leads matched across pages: lead-p1-50 and lead-p2-10
        self.assertEqual(purge_result["matched_leads_count"], 2)
        self.assertIn("lead-p1-50", purge_result["lead_ids"])
        self.assertIn("lead-p2-10", purge_result["lead_ids"])
        self.assertEqual(purge_result["halted_states_count"], 2)

    def test_layer2_csv_background_preserves_custom_columns_in_metadata(self):
        """
        Layer 2 Paranoia (B1-F07):
        process_csv_background must forward non-standard custom CSV columns
        (e.g. 'custom_tier', 'deal_potential', 'crm_account_id') through lead_dict
        so that execute_bulk_import_leads preserves them in leads.metadata['custom_variables'].
        """
        csv_content = (
            "First Name,Last Name,Email,LinkedIn URL,Custom_Tier,Deal_Potential,CRM_Account_ID\n"
            "Ada,Lovelace,ada@analytical.org,https://www.linkedin.com/in/adalovelace,Tier-1-Enterprise,$250k,CRM-99482\n"
        )

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(csv_content)
            temp_path = tf.name

        mock_supabase = MagicMock()
        # Mock lead_lists status lookup
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "pending"}]
        )

        captured_leads = []

        def capture_bulk_import(supabase, list_id, workspace_id, leads, timezone=None, collision_policy="merge"):
            captured_leads.extend(leads)
            return {"inserted_count": len(leads), "duplicates_updated": 0, "collisions_skipped": 0}

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
                 patch("leads.backend.services.lead_ingestion_service.execute_bulk_import_leads", side_effect=capture_bulk_import):
                process_csv_background(
                    list_id="list-custom-vars",
                    file_path=temp_path,
                    workspace_id="ws-custom-vars"
                )

            self.assertEqual(len(captured_leads), 1)
            imported_lead = captured_leads[0]

            # Core fields mapped cleanly
            self.assertEqual(imported_lead["first_name"], "Ada")
            self.assertEqual(imported_lead["last_name"], "Lovelace")
            self.assertEqual(imported_lead["email"], "ada@analytical.org")
            self.assertEqual(imported_lead["linkedin_url"], "https://www.linkedin.com/in/adalovelace")

            # Custom fields forwarded in lead_dict
            self.assertEqual(imported_lead.get("Custom_Tier"), "Tier-1-Enterprise")
            self.assertEqual(imported_lead.get("Deal_Potential"), "$250k")
            self.assertEqual(imported_lead.get("CRM_Account_ID"), "CRM-99482")

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_layer2_pydantic_v2_lead_and_list_schemas_validation(self):
        """
        Layer 2 Paranoia (B2-F02):
        Modern Pydantic v2 schemas in leads/backend/schemas/lead.py must serialize and validate
        database records with type safety, supporting metadata custom_variables and campaign joins.
        """
        # 1. LeadResponse serialization
        db_lead_row = {
            "id": "lead-uuid-1",
            "workspace_id": "ws-1",
            "first_name": "Alan",
            "last_name": "Turing",
            "email": "alan@bletchley.gov.uk",
            "company_name": "Bletchley Park",
            "domain": "bletchley.gov.uk",
            "social_intent_score": 85.5,
            "social_intent_tier": "HOT",
            "email_classification": "CORPORATE",
            "deliverability_risk": "SAFE",
            "metadata": {
                "custom_variables": {
                    "cipher": "Enigma",
                    "priority": "ALPHA"
                }
            },
            "created_at": "2026-10-20T08:00:00Z"
        }
        lead_resp = LeadResponse.model_validate(db_lead_row)
        self.assertEqual(lead_resp.id, "lead-uuid-1")
        self.assertEqual(lead_resp.first_name, "Alan")
        self.assertEqual(lead_resp.social_intent_score, 85.5)
        self.assertEqual(lead_resp.deliverability_risk, "SAFE")
        self.assertEqual(lead_resp.metadata["custom_variables"]["cipher"], "Enigma")

        dumped = lead_resp.model_dump()
        self.assertEqual(dumped["id"], "lead-uuid-1")
        self.assertEqual(dumped["metadata"]["custom_variables"]["priority"], "ALPHA")

        # 2. LeadListResponse with enriched Campaign join (Stage 15 bridge)
        db_list_row = {
            "id": "list-uuid-2",
            "workspace_id": "ws-1",
            "name": "Cryptanalysts",
            "type": "csv",
            "row_count": 42,
            "target_timezone": "Europe/London",
            "status": "completed",
            "campaign": {
                "id": "camp-99",
                "name": "Bletchley Outbound",
                "status": "ACTIVE"
            }
        }
        list_resp = LeadListResponse.model_validate(db_list_row)
        self.assertEqual(list_resp.id, "list-uuid-2")
        self.assertEqual(list_resp.campaign["id"], "camp-99")
        self.assertEqual(list_resp.campaign["status"], "ACTIVE")

        # 3. DynamicRuleConfig validation
        rule_data = {
            "match_type": "ALL",
            "conditions": [
                {"id": "c1", "field": "job_title", "operator": "contains", "value": "Director"},
                {"id": "c2", "field": "social_intent_score", "operator": "gte", "value": 70}
            ],
            "auto_enroll_campaign_id": "camp-auto-1",
            "re_enroll_disqualified": False
        }
        rule_cfg = DynamicRuleConfig.model_validate(rule_data)
        self.assertEqual(rule_cfg.match_type, "ALL")
        self.assertEqual(len(rule_cfg.conditions), 2)
        self.assertEqual(rule_cfg.conditions[0].operator, "contains")
        self.assertEqual(rule_cfg.conditions[1].value, 70)

        # 4. SuppressionEntryResponse validation
        suppression_data = {
            "id": "sup-uuid-3",
            "workspace_id": "ws-1",
            "domain": "competitor.com",
            "reason": "Direct Rival",
            "value": "competitor.com",
            "created_at": "2026-10-20T08:30:00Z"
        }
        sup_resp = SuppressionEntryResponse.model_validate(suppression_data)
        self.assertEqual(sup_resp.id, "sup-uuid-3")
        self.assertEqual(sup_resp.domain, "competitor.com")
        self.assertEqual(sup_resp.reason, "Direct Rival")


if __name__ == "__main__":
    unittest.main()
