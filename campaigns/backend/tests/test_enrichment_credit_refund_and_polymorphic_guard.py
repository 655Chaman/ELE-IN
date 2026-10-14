import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Ensure paths work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

class TestEnrichmentCreditRefundAndPolymorphicGuard(unittest.TestCase):

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("os.environ", {"APOLLO_API_KEY": "test_key"})
    def test_enrich_with_apollo_polymorphic_kwargs(self, mock_resilience, mock_post):
        from integrations.backend.services.elein_crm_service import enrich_with_apollo
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "person": {
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "title": "Engineer"
            },
            "organization": {
                "name": "Example Corp",
                "primary_domain": "example.com"
            }
        }
        mock_resilience.return_value = mock_response

        res = enrich_with_apollo(
            workspace_id="ws-1",
            first_name="John",
            last_name="Doe",
            company_domain="example.com",
            linkedin_url="https://linkedin.com/in/johndoe"
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["email"], "john.doe@example.com")
        self.assertEqual(res["first_name"], "John")

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("os.environ", {"APOLLO_API_KEY": "test_key"})
    def test_enrich_with_apollo_lead_data_dict(self, mock_resilience, mock_post):
        from integrations.backend.services.elein_crm_service import enrich_with_apollo
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "person": {
                "email": "jane.smith@acme.com",
                "first_name": "Jane",
                "last_name": "Smith"
            },
            "organization": {
                "name": "Acme",
                "primary_domain": "acme.com"
            }
        }
        mock_resilience.return_value = mock_response

        res = enrich_with_apollo(
            workspace_id="ws-1",
            lead_data={"first_name": "Jane", "domain": "acme.com"}
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["email"], "jane.smith@acme.com")

    @patch("integrations.backend.services.elein_crm_service.requests.post")
    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("os.environ", {"APOLLO_API_KEY": "test_key"})
    def test_enrich_with_apollo_sanitizes_invalid_email(self, mock_resilience, mock_post):
        from integrations.backend.services.elein_crm_service import enrich_with_apollo
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "person": {
                "email": "none@example.com",
                "first_name": "Bad",
                "last_name": "Email"
            },
            "organization": {"primary_domain": "example.com"}
        }
        mock_resilience.return_value = mock_response

        res = enrich_with_apollo(
            workspace_id="ws-1",
            lead_data={"first_name": "Bad", "domain": "example.com"}
        )
        self.assertIsNone(res["email"])

    @patch("integrations.backend.services.elein_crm_service.enrich_with_apollo", return_value=None)
    def test_enrichment_refunds_credits_when_not_found(self, mock_enrich):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
        mock_supabase = MagicMock()
        mock_rpc_res = MagicMock()
        mock_rpc_res.data = {"success": True}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc_res

        executor = EleInNodeExecutor(workspace_id="ws-1", supabase=mock_supabase)
        res = executor._handle_enrichment({"first_name": "Unknown", "domain": "unknown.com"}, None)
        self.assertEqual(res["branch"], Branch.NOT_FOUND.value)

    def test_verify_email_refunds_when_email_empty(self):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
        mock_supabase = MagicMock()
        mock_rpc_res = MagicMock()
        mock_rpc_res.data = {"success": True}
        mock_supabase.rpc.return_value.execute.return_value = mock_rpc_res

        executor = EleInNodeExecutor(workspace_id="ws-1", supabase=mock_supabase)
        res = executor.handle_verify_email({}, None)
        self.assertEqual(res["branch"], Branch.INVALID_OR_RISKY.value)

    @patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email")
    def test_zero_cost_discovery_rejects_malformed_email(self, mock_discover):
        mock_discover.return_value = "N/A"
        mock_supabase = MagicMock()

        from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
        executor = EleInNodeExecutor(workspace_id="ws-1", supabase=mock_supabase)
        
        lead = {"id": "lead-1", "first_name": "Test", "last_name": "User", "domain": "example.com"}
        res = executor.handle_zero_cost_discovery(lead, None)
        self.assertEqual(res["branch"], Branch.NOT_FOUND.value)
        self.assertFalse(res["result"])

if __name__ == "__main__":
    unittest.main()
