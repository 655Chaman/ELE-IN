import os
import unittest
from unittest.mock import patch, MagicMock
from integrations.backend.services.elein_crm_service import (
    add_to_smartlead,
    add_to_instantly,
    _clean_and_dedup_crm_leads,
)
from integrations.backend.services.circuit_breaker import get_circuit_breaker


class TestSmartleadInstantlySyncHardeningGuard(unittest.TestCase):
    def setUp(self):
        self.workspace_id = "ws_sync_test"
        self.campaign_id = "camp_sync_test"
        # Reset circuit breakers
        cb_sl = get_circuit_breaker("smartlead")
        cb_sl.reset()
        cb_inst = get_circuit_breaker("instantly")
        cb_inst.reset()

    def test_clean_and_dedup_crm_leads(self):
        """Verifies deduplication, email validation, and formula injection sanitization."""
        raw_leads = [
            {"email": "ALICE@EXAMPLE.COM", "first_name": "=CMD|'calc'!A0", "company": "Acme Corp"},
            {"email": "alice@example.com", "first_name": "Alice Duplicate", "company": "Acme"},
            {"email": "", "first_name": "Bob Empty"},
            {"email": "not-an-email", "first_name": "Charlie Invalid"},
            {"email": "dave@example.com", "first_name": "+Dave", "last_name": "-Smith", "company": "@Alpha"},
        ]
        cleaned = _clean_and_dedup_crm_leads(raw_leads)
        self.assertEqual(len(cleaned), 2)
        # Verify Alice was deduplicated
        self.assertEqual(cleaned[0]["email"], "alice@example.com")
        self.assertEqual(cleaned[0]["first_name"], "'=CMD|'calc'!A0")
        # Verify Dave was sanitized
        self.assertEqual(cleaned[1]["email"], "dave@example.com")
        self.assertEqual(cleaned[1]["first_name"], "'+Dave")
        self.assertEqual(cleaned[1]["last_name"], "'-Smith")
        self.assertEqual(cleaned[1]["company"], "'@Alpha")

    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_add_to_smartlead_intra_batch_deduplication(self, mock_get_client, mock_resilience):
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})
        mock_get_client.return_value = mock_supabase

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resilience.return_value = mock_resp

        leads = [
            {"email": "prospect1@acme.com", "first_name": "Jane"},
            {"email": "PROSPECT1@acme.com", "first_name": "Jane Dup"},
            {"email": "prospect2@acme.com", "first_name": "John"},
        ]

        with patch.dict(os.environ, {"SMARTLEAD_API_KEY": "dummy_key"}):
            success = add_to_smartlead(self.workspace_id, leads, self.campaign_id)

        self.assertTrue(success)
        # Verify credits deducted for only 2 unique leads
        mock_supabase.rpc.assert_called_with('deduct_credits_safely', {
            'p_workspace_id': self.workspace_id,
            'p_amount': 2,
            'p_action_type': 'crm_push_bulk',
            'p_idempotency_key': unittest.mock.ANY,
        })

    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_add_to_smartlead_all_invalid_emails_no_charge(self, mock_get_client, mock_resilience):
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        leads = [
            {"email": "", "first_name": "Ghost"},
            {"email": "invalid-email-format", "first_name": "Broken"},
        ]

        with patch.dict(os.environ, {"SMARTLEAD_API_KEY": "dummy_key"}):
            success = add_to_smartlead(self.workspace_id, leads, self.campaign_id)

        self.assertTrue(success)
        # Deduct should not be called
        mock_supabase.rpc.assert_not_called()
        mock_resilience.assert_not_called()

    @patch("requests.post")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_add_to_smartlead_chunking_large_batch(self, mock_get_client, mock_post):
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})
        mock_get_client.return_value = mock_supabase

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        leads = [{"email": f"user{i}@example.com", "first_name": f"User {i}"} for i in range(150)]

        with patch.dict(os.environ, {"SMARTLEAD_API_KEY": "dummy_key"}):
            success = add_to_smartlead(self.workspace_id, leads, self.campaign_id)

        self.assertTrue(success)
        # 150 credits deducted
        mock_supabase.rpc.assert_called_with('deduct_credits_safely', {
            'p_workspace_id': self.workspace_id,
            'p_amount': 150,
            'p_action_type': 'crm_push_bulk',
            'p_idempotency_key': unittest.mock.ANY,
        })
        # Two POST calls (100 in first, 50 in second)
        self.assertEqual(mock_post.call_count, 2)

    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_add_to_smartlead_refunds_on_api_error(self, mock_get_client, mock_resilience):
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})
        mock_get_client.return_value = mock_supabase

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resilience.return_value = mock_resp

        leads = [{"email": "target@acme.com", "first_name": "Target"}]

        with patch.dict(os.environ, {"SMARTLEAD_API_KEY": "dummy_key"}):
            success = add_to_smartlead(self.workspace_id, leads, self.campaign_id)

        self.assertFalse(success)
        # Verify refund RPC was triggered
        refund_called = any(
            call[0][0] == 'add_credits_safely' and call[0][1]['p_credits'] == 1 and call[0][1]['p_provider'] == 'system_refund'
            for call in mock_supabase.rpc.call_args_list
        )
        self.assertTrue(refund_called, "Credits were not refunded on Smartlead failure")

    @patch("integrations.backend.services.circuit_breaker.execute_with_resilience")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_add_to_instantly_intra_batch_dedup_and_filtering(self, mock_get_client, mock_resilience):
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})
        mock_get_client.return_value = mock_supabase

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resilience.return_value = mock_resp

        leads = [
            {"email": "lead1@acme.com", "first_name": "Lead1"},
            {"email": "lead1@acme.com", "first_name": "Lead1 Dup"},
            {"email": "bad-email", "first_name": "Bad"},
            {"email": "lead2@acme.com", "first_name": "Lead2"},
        ]

        with patch.dict(os.environ, {"INSTANTLY_API_KEY": "dummy_instantly_key"}):
            success = add_to_instantly(self.workspace_id, leads, self.campaign_id)

        self.assertTrue(success)
        mock_supabase.rpc.assert_called_with('deduct_credits_safely', {
            'p_workspace_id': self.workspace_id,
            'p_amount': 2,
            'p_action_type': 'crm_push_bulk',
            'p_idempotency_key': unittest.mock.ANY,
        })

    @patch("requests.post")
    @patch("core.backend.api.auth_dep.get_service_client")
    def test_add_to_instantly_partial_chunk_refund_on_failure(self, mock_get_client, mock_post):
        mock_supabase = MagicMock()
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data={"success": True})
        mock_get_client.return_value = mock_supabase

        # First chunk 100 succeeds, second chunk 20 fails
        resp_success = MagicMock(status_code=200)
        resp_fail = MagicMock(status_code=500)
        mock_post.side_effect = [resp_success, resp_fail]

        leads = [{"email": f"inst_user{i}@example.com", "first_name": f"User {i}"} for i in range(120)]

        with patch.dict(os.environ, {"INSTANTLY_API_KEY": "dummy_instantly_key"}):
            success = add_to_instantly(self.workspace_id, leads, self.campaign_id)

        self.assertFalse(success)
        # Should refund unpushed 20 credits
        refund_called = any(
            call[0][0] == 'add_credits_safely' and call[0][1]['p_credits'] == 20
            for call in mock_supabase.rpc.call_args_list
        )
        self.assertTrue(refund_called, "Unpushed credits were not refunded on chunk failure")

    @patch("core.backend.api.auth_dep.get_service_client")
    def test_circuit_breaker_open_blocks_push_without_deduction(self, mock_get_client):
        import time
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        cb = get_circuit_breaker("smartlead")
        # Force breaker open and ensure last_failure_time is current
        cb.state = "OPEN"
        cb.last_failure_time = time.time()
        cb.failure_count = 10

        leads = [{"email": "valid@example.com", "first_name": "Valid"}]
        with patch.dict(os.environ, {"SMARTLEAD_API_KEY": "dummy_key"}):
            success = add_to_smartlead(self.workspace_id, leads, self.campaign_id)

        self.assertFalse(success)
        mock_supabase.rpc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
