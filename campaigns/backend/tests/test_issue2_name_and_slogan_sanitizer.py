import unittest
from unittest.mock import MagicMock
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads
from leads.backend.services.data_hygiene import DataHygieneService


class TestIssue2NameAndSloganSanitizer(unittest.TestCase):
    """
    Comprehensive Three-Layer Paranoia Test Suite for Issue 2:
    Lead Name & Company Slogan Sanitizer.
    """

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.mock_supabase,
            workspace_id="ws-sanitizer-test"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 0: Foundational Layer
    # ─────────────────────────────────────────────────────────────────────────

    def test_layer0_interpolate_clean_first_name_and_company(self):
        """
        Layer 0: {{first_name}}, {{firstname}}, {{first_name_clean}} and
        {{company}}, {{company_name}}, {{company_clean}} always receive clean brand and natural names.
        """
        template = (
            "Hi {{first_name}} (or {{firstname}} / {{first_name_clean}}), "
            "welcome to {{company}} (or {{company_name}} / {{company_clean}})!"
        )
        data = {
            "lead": {
                "first_name": "SARAH (WE'RE HIRING!)",
                "company": "Stripe, Inc. - Financial infrastructure for the internet"
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(
            res,
            "Hi Sarah (or Sarah / Sarah), welcome to Stripe (or Stripe / Stripe)!"
        )

    def test_layer0_lead_ingestion_clean_storage(self):
        """
        Layer 0: Lead ingestion applies clean_first_name and clean_company when storing
        into processed_lead before RPC or database upsert.
        """
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value.data = {"inserted_count": 1, "duplicate_count": 0}
        self.mock_supabase.rpc.return_value = mock_rpc

        leads = [
            {
                "first_name": "SARAH (WE'RE HIRING!)",
                "last_name": "O'CONNOR",
                "company_name": "Stripe, Inc. - Financial infrastructure for the internet",
                "linkedin_url": "https://www.linkedin.com/in/sarah-oconnor",
                "email": "sarah@stripe.com"
            }
        ]
        res = execute_bulk_import_leads(
            supabase=self.mock_supabase,
            list_id="list-ingest-clean",
            workspace_id="ws-sanitizer-test",
            leads=leads
        )
        self.assertTrue(res["success"])
        rpc_call = self.mock_supabase.rpc.call_args
        self.assertIsNotNone(rpc_call)
        p_leads = rpc_call[0][1]["p_leads"]
        self.assertEqual(len(p_leads), 1)
        self.assertEqual(p_leads[0]["first_name"], "Sarah")
        self.assertEqual(p_leads[0]["company_name"], "Stripe")

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 1: Environmental Failure Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def test_layer1_fallbacks_when_values_empty_or_stripped(self):
        """
        Layer 1: When first_name or company are empty, whitespace-only, or stripped
        to empty, fallbacks 'there' and 'your company' remain fully functional.
        """
        template = "Hello {{first_name}}, how are things at {{company}}? Clean: {{first_name_clean}} at {{company_clean}}."
        data = {
            "lead": {
                "first_name": "   ",
                "company": "   "
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(
            res,
            "Hello there, how are things at your company? Clean: there at your company."
        )

    def test_layer1_variables_override_sanitization(self):
        """
        Layer 1: If custom variables override first_name or company, they pass through
        DataHygieneService sanitization to avoid leaking raw slogans.
        """
        template = "Hi {{first_name}} from {{company}}!"
        data = {
            "lead": {"first_name": "Old", "company": "OldCo"},
            "variables": {
                "first_name": "ALEXANDER (HE/HIM)",
                "company": "Notion - The all-in-one workspace"
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hi Alexander from Notion!")

    def test_layer1_lead_ingestion_direct_table_fallback(self):
        """
        Layer 1: If Postgres RPC fails/is unmigrated, chunked direct table insertion
        still stores clean first_name and company_name values.
        """
        mock_table = MagicMock()
        self.mock_supabase.table.return_value = mock_table
        self.mock_supabase.rpc.side_effect = Exception("PGRST202: RPC not found")
        mock_table.select.return_value.eq.return_value.execute.return_value.data = []
        mock_table.insert.return_value.execute.return_value.data = [{"id": "lead-clean-1"}]

        leads = [
            {
                "first_name": "DR. JANE DOE [HIRING AES]",
                "last_name": "DOE",
                "company_name": "Acme Corp - The Roadrunner Specialists",
                "email": "jane@acme.com",
                "linkedin_url": "https://www.linkedin.com/in/jane-doe"
            }
        ]
        res = execute_bulk_import_leads(
            supabase=self.mock_supabase,
            list_id="list-clean-table",
            workspace_id="ws-sanitizer-test",
            leads=leads
        )
        self.assertTrue(res["success"])
        insert_calls = mock_table.insert.call_args_list
        self.assertTrue(len(insert_calls) > 0)
        inserted_batch = insert_calls[0][0][0]
        self.assertEqual(inserted_batch[0]["first_name"], "Jane")
        self.assertEqual(inserted_batch[0]["company_name"], "Acme")

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 2: Human Paranoia Element
    # ─────────────────────────────────────────────────────────────────────────

    def test_layer2_human_paranoia_initials_and_domains(self):
        """
        Layer 2: Handles initial prefixes ('J. Robert' -> 'Robert'), single letters ('J.' -> 'J'),
        and domain company imports ('tryacme.io' -> 'Acme').
        """
        template = "Hi {{first_name}}, glad to connect with {{company}}."
        data = {
            "lead": {
                "first_name": "J. Robert Oppenheimer",
                "company": "tryacme.io"
            }
        }
        res = self.executor._interpolate_template(template, data, None)
        self.assertEqual(res, "Hi Robert, glad to connect with Acme.")

    def test_layer2_human_paranoia_inline_fallback_syntax(self):
        """
        Layer 2: Handles piped inline fallback syntax {{first_name | friend}} safely
        when name is empty or present.
        """
        template_empty = "Hey {{first_name | friend}}, let's talk about {{company | your startup}}!"
        data_empty = {"lead": {"first_name": "", "company": ""}}
        res_empty = self.executor._interpolate_template(template_empty, data_empty, None)
        self.assertEqual(res_empty, "Hey friend, let's talk about your startup!")

        data_present = {
            "lead": {
                "first_name": "SARAH (HIRING)",
                "company": "Stripe, Inc."
            }
        }
        res_present = self.executor._interpolate_template(template_empty, data_present, None)
        self.assertEqual(res_present, "Hey Sarah, let's talk about Stripe!")


if __name__ == "__main__":
    unittest.main()
