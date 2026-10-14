import ipaddress
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from core.backend.core.validators import is_safe_ssrf_url
from inbox.backend.services.outbox_worker import _process_webhook_notification, _process_slack_notification
from campaigns.backend.routers.elein import delete_campaign, update_campaign, get_campaign_detail, CampaignCreate
from backend.scripts.verify_migrations import verify_master_migration, verify_master_coverage


class TestStage5ProductionSecurityAndAudit(unittest.TestCase):
    """
    Stage 5: Pre-Flight Production Readiness, Security Hardening & Migration Verification.
    Architected under the Three-Layer Logic Architecture (Paranoia Framework).
    """

    # ──────────────────────────────────────────────────────────────────────────
    # 1. SSRF DEFENSE & PROTOCOL EXPLOIT SUITE (Layers 0, 1 & 2)
    # ──────────────────────────────────────────────────────────────────────────

    def test_ssrf_blocks_loopback_and_mapped_ipv6(self):
        """Layer 1: Blocks 127.0.0.1, [::1], and IPv4-mapped IPv6 (::ffff:127.0.0.1)."""
        disallowed = [
            "http://127.0.0.1:8000/api",
            "http://127.0.0.2/admin",
            "http://[::1]/internal",
            "http://[::ffff:127.0.0.1]/status",
            "http://0.0.0.0:3000",
        ]
        for url in disallowed:
            self.assertFalse(is_safe_ssrf_url(url), f"Should have blocked loopback URL: {url}")

    def test_ssrf_blocks_cloud_metadata_and_cgnat(self):
        """Layer 1: Blocks AWS/GCP/Azure link-local metadata (169.254.169.254) and CGNAT."""
        disallowed = [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://instance-data/latest/meta-data/",
            "http://metadata.azure.com/metadata/instance",
            "http://100.64.0.1/cgnat-endpoint",
        ]
        for url in disallowed:
            self.assertFalse(is_safe_ssrf_url(url), f"Should have blocked metadata/CGNAT URL: {url}")

    def test_ssrf_blocks_rfc1918_private_ranges(self):
        """Layer 1: Blocks 10.0.0.0/8, 172.16.0.0/12, and 192.168.0.0/16 subnets."""
        disallowed = [
            "http://10.0.0.5:8080/metrics",
            "http://10.255.255.1/db",
            "http://172.16.0.1/internal",
            "http://172.31.255.255/admin",
            "http://192.168.1.1/setup",
            "http://192.168.100.50/api",
        ]
        for url in disallowed:
            self.assertFalse(is_safe_ssrf_url(url), f"Should have blocked RFC1918 URL: {url}")

    def test_ssrf_blocks_internal_domain_suffixes(self):
        """Layer 1: Blocks .local, .internal, .localhost, .lan, and .corp hostnames."""
        disallowed = [
            "http://app.local/secret",
            "http://database.internal:5432",
            "http://auth.localhost:8080",
            "http://nas.lan/share",
            "http://intranet.corp/keys",
            "http://host.docker.internal:8000",
        ]
        for url in disallowed:
            self.assertFalse(is_safe_ssrf_url(url), f"Should have blocked internal domain suffix: {url}")

    def test_ssrf_blocks_authority_confusion_and_crlf_injections(self):
        """Layer 2 Human Paranoia: Blocks user-info credential confusion and CRLF injection."""
        malicious = [
            "http://admin:secret@api.partner.com/webhook",
            "http://user:pass@127.0.0.1/",
            "http://api.partner.com\r\nHost: 127.0.0.1",
            "http://api.partner.com\nHost: 127.0.0.1",
            "http://api.partner.com\0/bypass",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "ftp://ftp.safe-site.com/file",
        ]
        for url in malicious:
            self.assertFalse(is_safe_ssrf_url(url), f"Should have blocked malicious authority/injection URL: {url}")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. REDIRECT-CHAIN SSRF DEFENSE (Layers 1 & 2)
    # ──────────────────────────────────────────────────────────────────────────

    @patch("requests.post")
    def test_outbound_webhooks_disallow_redirects(self, mock_post):
        """Layer 1: Webhook and Slack dispatches explicitly enforce allow_redirects=False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        event = {
            "id": "evt_sec_redirect",
            "workspace_id": "ws-sec",
            "payload": {
                "url": "https://api.partner.com/webhook",
                "lead_id": "lead-1"
            }
        }
        with patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True):
            success = _process_webhook_notification(event)

        self.assertTrue(success)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertFalse(kwargs.get("allow_redirects", True), "Outbound webhooks must set allow_redirects=False")

    @patch("requests.post")
    def test_outbound_slack_disallows_redirects(self, mock_post):
        """Layer 1: Slack alert dispatches explicitly enforce allow_redirects=False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        event = {
            "id": "evt_slack_redirect",
            "workspace_id": "ws-sec",
            "payload": {
                "webhook_url": "https://hooks.slack.com/services/T00/B00/X00",
                "text": "Alert"
            }
        }
        with patch("core.backend.core.validators.is_safe_ssrf_url", return_value=True):
            success = _process_slack_notification(event)

        self.assertTrue(success)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertFalse(kwargs.get("allow_redirects", True), "Slack alerts must set allow_redirects=False")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. MULTI-TENANT ISOLATION & IDOR DEFENSE (Layers 0 & 1)
    # ──────────────────────────────────────────────────────────────────────────

    def test_campaign_detail_enforces_workspace_isolation(self):
        """Layer 0 & 1: Fetching campaign detail requires caller's workspace ownership."""
        mock_client = MagicMock()
        # Mock workspace query returning empty (i.e. campaign belongs to another workspace)
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with self.assertRaises(HTTPException) as ctx:
            get_campaign_detail(
                campaign_id="camp-foreign-123",
                supabase=mock_client,
                workspace_id="ws-caller-tenant"
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_campaign_delete_enforces_workspace_isolation(self):
        """Layer 0 & 1: Deleting a campaign requires caller's workspace ownership."""
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with self.assertRaises(HTTPException) as ctx:
            delete_campaign(
                campaign_id="camp-foreign-456",
                force=False,
                workspace_id="ws-caller-tenant",
                client=mock_client
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_campaign_update_blocks_unowned_senders(self):
        """Layer 1 IDOR: Rejects campaign update if senders belong to another workspace."""
        mock_client = MagicMock()
        # Existing campaign belongs to workspace
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "camp-1", "status": "DRAFT", "metadata": {}}]
        )
        # Senders check returns only 1 out of 2 requested senders (1 is foreign)
        mock_client.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc-owned-1"}]
        )

        payload = CampaignCreate(
            name="Updated Campaign",
            lead_list_id="list-1",
            senders=["acc-owned-1", "acc-foreign-999"],
            nodes=[],
            edges=[]
        )

        with self.assertRaises(HTTPException) as ctx:
            update_campaign(
                campaign_id="camp-1",
                payload=payload,
                workspace_id="ws-caller-tenant",
                client=mock_client
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("do not belong to your workspace", str(ctx.exception.detail))

    # ──────────────────────────────────────────────────────────────────────────
    # 4. PRE-FLIGHT MIGRATION VERIFICATION (Layer 1 Environmental)
    # ──────────────────────────────────────────────────────────────────────────

    def test_master_migration_passes_all_preflight_checks(self):
        """Layer 1: 999_master_pending_sync.sql is 100% syntactically valid and idempotent."""
        root_dir = Path(__file__).resolve().parent.parent.parent.parent
        master_sql = root_dir / "backend" / "migrations" / "999_master_pending_sync.sql"

        passed_syntax, errors, stats = verify_master_migration(master_sql)
        self.assertTrue(passed_syntax, f"Master migration failed syntax/idempotency checks: {errors}")
        self.assertEqual(len(errors), 0)

        passed_coverage, coverage_warnings = verify_master_coverage(master_sql)
        self.assertTrue(passed_coverage, f"Master migration failed coverage checks: {coverage_warnings}")
        self.assertEqual(len(coverage_warnings), 0)

        # Confirm critical stats
        self.assertGreaterEqual(stats["tables_created"], 25)
        self.assertGreaterEqual(stats["indexes_created"], 40)
        self.assertGreaterEqual(stats["functions_created"], 8)
        self.assertGreaterEqual(stats["policies_created"], 20)


if __name__ == "__main__":
    unittest.main()
