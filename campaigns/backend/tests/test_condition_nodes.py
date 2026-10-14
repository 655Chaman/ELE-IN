import unittest
from unittest.mock import MagicMock, patch
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch

class TestConditionNodesExecutor(unittest.TestCase):
    def setUp(self):
        self.worker = MagicMock()
        self.supabase = MagicMock()
        self.executor = EleInNodeExecutor(
            linkedin_worker=self.worker,
            supabase=self.supabase,
            workspace_id="ws_conditions_test"
        )
        self.test_lead_url = "https://www.linkedin.com/in/prospect-ceo"

    # =========================================================================
    # Node: if_connected
    # =========================================================================
    def test_if_connected_fast_path_payload(self):
        """Layer 0: If payload already specifies connected, returns Connected branch immediately."""
        data = {"is_connected": True}
        res = self.executor.handle_if_connected(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.CONNECTED.value)
        self.assertTrue(res.get("connected"))
        self.worker.check_if_connected.assert_not_called()

    def test_if_connected_fast_path_database(self):
        """Layer 1: If database confirms lead is connected, saves Playwright browser overhead."""
        data = {"_lead_id": "lead_101"}
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"status": "connected", "is_connected": True}]
        )

        res = self.executor.handle_if_connected(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.CONNECTED.value)
        self.worker.check_if_connected.assert_not_called()

    def test_if_connected_worker_dispatch(self):
        """Layer 0: Dispatches to worker and standardizes branch to Connected or Not connected."""
        data = {"_lead_id": "lead_102"}
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        # Sub-case A: Worker says Connected
        self.worker.check_if_connected.return_value = {"status": "success", "branch": "Connected"}
        res = self.executor.handle_if_connected(data, self.test_lead_url)
        self.assertEqual(res.get("branch"), Branch.CONNECTED.value)
        self.assertTrue(res.get("connected"))

        # Sub-case B: Worker says Not connected
        self.worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}
        res2 = self.executor.handle_if_connected(data, self.test_lead_url)
        self.assertEqual(res2.get("branch"), Branch.NOT_CONNECTED.value)
        self.assertFalse(res2.get("connected"))

    def test_if_connected_worker_unavailable_graceful_fallback(self):
        """Layer 1: If worker is missing/disconnected, gracefully returns Not connected without halting."""
        executor_no_worker = EleInNodeExecutor(
            linkedin_worker=None,
            supabase=self.supabase,
            workspace_id="ws_conditions_test"
        )
        data = {}
        res = executor_no_worker.handle_if_connected(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NOT_CONNECTED.value)
        self.assertFalse(res.get("connected"))

    # =========================================================================
    # Node: seamless_identity_matching
    # =========================================================================
    def test_seamless_identity_matching_connected_branch(self):
        """Layer 0: If prospect accepted on LinkedIn, routes directly to Connected branch."""
        data = {"is_connected": True}
        res = self.executor.handle_seamless_identity_matching(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.CONNECTED.value)

    def test_seamless_identity_matching_email_discovered_branch(self):
        """Layer 0: If still pending, zero-cost engine discovers email and routes to Email Discovered branch."""
        self.worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}
        
        with patch.object(self.executor, "handle_zero_cost_discovery", return_value={
            "status": "success",
            "result": True,
            "email": "ceo@datacorp.com"
        }):
            res = self.executor.handle_seamless_identity_matching({}, self.test_lead_url)
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), "Email Discovered")
            self.assertEqual(res.get("email"), "ceo@datacorp.com")

    def test_seamless_identity_matching_fallback_when_no_email(self):
        """Layer 1: If neither connected nor email found, safely returns Not connected rather than crashing."""
        self.worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}
        
        with patch.object(self.executor, "handle_zero_cost_discovery", return_value={
            "status": "success",
            "result": False,
            "email": None
        }):
            res = self.executor.handle_seamless_identity_matching({}, self.test_lead_url)
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), Branch.NOT_CONNECTED.value)

    def test_seamless_identity_matching_uses_cached_email_shortcut(self):
        """Layer 2 Paranoia: If email is already in payload or lead record, skip expensive discovery."""
        self.worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}
        data = {"email": "sarah@acme.com"}
        with patch.object(self.executor, "handle_zero_cost_discovery") as mock_disc:
            res = self.executor.handle_seamless_identity_matching(data, self.test_lead_url)
            mock_disc.assert_not_called()
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["branch"], "Email Discovered")
            self.assertEqual(res["email"], "sarah@acme.com")
            self.assertEqual(data["variables"]["discovered_email"], "sarah@acme.com")

    def test_seamless_identity_matching_auto_withdraws_invite(self):
        """Layer 1 Paranoia: Auto-withdraw pending connection request when pivoting to email."""
        self.worker.check_if_connected.return_value = {"status": "success", "branch": "Not connected"}
        data = {"auto_withdraw_invite": True, "email": "vp@target.com"}
        self.worker.withdraw_connection_request.return_value = {"status": "success"}

        res = self.executor.handle_seamless_identity_matching(data, self.test_lead_url)
        self.assertEqual(res["branch"], "Email Discovered")
        self.worker.withdraw_connection_request.assert_called_once_with(self.test_lead_url)

    def test_zero_cost_discovery_sanitizes_domain_and_uses_smtp(self):
        """Layer 0 & 1: Sanitizes dirty URLs and discovers email via SMTP handshake."""
        lead_data = {
            "first_name": "John",
            "last_name": "Doe",
            "company_name": "Acme Corp",
            "custom_fields": {"website": "https://www.acme.com/team"}
        }
        with patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email", return_value="john.doe@acme.com") as mock_smtp:
            res = self.executor.handle_zero_cost_discovery(lead_data, self.test_lead_url)
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["result"], True)
            self.assertEqual(res["email"], "john.doe@acme.com")
            self.assertEqual(res["source"], "smtp")
            mock_smtp.assert_called_once_with("John", "Doe", "acme.com")

    def test_zero_cost_discovery_apollo_fallback_when_smtp_fails(self):
        """Layer 1 Paranoia: Falls back to Apollo People Match when SMTP discovery fails."""
        lead_data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "domain": "catchall-tech.io"
        }
        with patch("integrations.backend.services.email_verifier.EmailVerifier.discover_email", return_value=None):
            with patch("integrations.backend.services.elein_crm_service.enrich_with_apollo", return_value={"email": "jane@catchall-tech.io"}) as mock_apollo:
                res = self.executor.handle_zero_cost_discovery(lead_data, self.test_lead_url)
                self.assertEqual(res["status"], "success")
                self.assertEqual(res["result"], True)
                self.assertEqual(res["email"], "jane@catchall-tech.io")
                self.assertEqual(res["source"], "apollo")
                mock_apollo.assert_called_once_with(
                    workspace_id=self.executor.workspace_id,
                    first_name="Jane",
                    last_name="Smith",
                    company_domain="catchall-tech.io",
                    linkedin_url=self.test_lead_url
                )


    # =========================================================================
    # Node: if_replied
    # =========================================================================
    def test_if_replied_from_variables(self):
        """Layer 0: Returns clean sentiment branch from variables."""
        for sentiment in ["Positive", "Negative", "Neutral", "No Reply"]:
            data = {"variables": {"last_reply_sentiment": sentiment}}
            res = self.executor.handle_if_replied(data, self.test_lead_url)
            self.assertEqual(res.get("status"), "success")
            self.assertEqual(res.get("branch"), sentiment)

    def test_if_replied_heuristic_when_sentiment_tag_missing(self):
        """Layer 1: If sentiment detector node was omitted but lead replied in DB, classifies intent."""
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"has_replied": True, "last_message_received": "Yes, I would love to see a demo!"}]
        )
        data = {"_lead_id": "lead_replied_001"}
        res = self.executor.handle_if_replied(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.POSITIVE.value)

    def test_if_replied_worker_detection_fallback(self):
        """Layer 1: If variable is missing but worker sees unread inbox reply, prevents No Reply drop."""
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        
        self.worker.check_if_replied.return_value = {"status": "success", "branch": "Replied"}
        data = {"_lead_id": "lead_inbox_reply"}
        res = self.executor.handle_if_replied(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.POSITIVE.value)

    def test_if_replied_clean_no_reply_default(self):
        """Layer 2: With no reply in variables, DB, or inbox, cleanly returns No Reply branch."""
        mock_table = MagicMock()
        self.supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        self.worker.check_if_replied.return_value = {"status": "success", "branch": "No reply"}

        data = {"_lead_id": "lead_silent"}
        res = self.executor.handle_if_replied(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), Branch.NO_REPLY.value)

    # =========================================================================
    # Node: open_profile_check
    # =========================================================================
    def test_open_profile_check_fast_path(self):
        """Layer 0: Returns Open branch if cached on payload or in DB."""
        data = {"is_open_profile": True}
        res = self.executor.handle_open_profile_check(data, self.test_lead_url)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("branch"), "Open")
        self.assertTrue(res.get("open"))
        self.worker.check_open_profile.assert_not_called()

    def test_open_profile_worker_dispatch_and_fallback(self):
        """Layer 1: Dispatches to worker or safely falls back to Not open on error."""
        # Worker says Open
        self.worker.check_open_profile.return_value = {"status": "success", "branch": "Open"}
        res1 = self.executor.handle_open_profile_check({}, self.test_lead_url)
        self.assertEqual(res1.get("branch"), "Open")

        # Worker unavailable fallback
        executor_no_worker = EleInNodeExecutor(linkedin_worker=None, supabase=self.supabase)
        res2 = executor_no_worker.handle_open_profile_check({}, self.test_lead_url)
        self.assertEqual(res2.get("status"), "success")
        self.assertEqual(res2.get("branch"), "Not open")
        self.assertFalse(res2.get("open"))

    # =========================================================================
    # Node: if_meeting_booked
    # =========================================================================
    def test_if_meeting_booked_kill_switch(self):
        """Layer 0 & 2: Detects booked status to activate safety stop."""
        data_booked = {"variables": {"meeting_booked": True}}
        res1 = self.executor.handle_if_meeting_booked(data_booked, self.test_lead_url)
        self.assertEqual(res1.get("branch"), Branch.BOOKED.value)
        self.assertTrue(res1.get("booked"))

        data_not_booked = {"variables": {}}
        res2 = self.executor.handle_if_meeting_booked(data_not_booked, self.test_lead_url)
        self.assertEqual(res2.get("branch"), Branch.NOT_BOOKED.value)
        self.assertFalse(res2.get("booked"))


if __name__ == "__main__":
    unittest.main()
