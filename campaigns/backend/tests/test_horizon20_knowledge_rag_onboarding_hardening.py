import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import base64
from fastapi import HTTPException

from knowledge.backend.routers.assets import (
    add_knowledge_text,
    add_knowledge_url,
    add_knowledge_pdf,
    TextUpload,
    UrlUpload
)
from knowledge.backend.services.knowledge_service import KnowledgeService
from admin.backend.routers.onboarding import seed_demo_data
from admin.backend.services.persona_service import PersonaService


class TestHorizon20KnowledgeAssetTierLimitsAndSSRF(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Horizon 20: Knowledge Base Asset Tier Limits,
    SSRF Protection, and Ingestion Hardening.
    """

    def setUp(self):
        self.workspace_id = "ws_kb_202"
        self.supabase = MagicMock()
        # Ensure chained .neq() calls route to the same mock execution chain as .eq()
        self.supabase.table.return_value.select.return_value.eq.return_value.neq.return_value = (
            self.supabase.table.return_value.select.return_value.eq.return_value
        )

    async def test_add_knowledge_text_enforces_tier_limit(self):
        """Layer 1: Free tier workspaces cannot exceed max_knowledge_assets (3 documents)."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        mock_count = MagicMock(count=3)
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_count
        ]

        payload = TextUpload(title="Company Overview", text="This is our comprehensive company knowledge base text.")
        with self.assertRaises(HTTPException) as ctx:
            await add_knowledge_text(payload, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Knowledge Base limit reached", ctx.exception.detail)

    async def test_add_knowledge_text_rejects_too_short_text(self):
        """Layer 2: Rejects text snippets shorter than 10 characters with HTTP 400."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        mock_count = MagicMock(count=1)
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_count
        ]

        payload = TextUpload(title="Short", text="Too short")
        with self.assertRaises(HTTPException) as ctx:
            await add_knowledge_text(payload, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("too short", ctx.exception.detail.lower())

    async def test_add_knowledge_text_rejects_oversized_payload(self):
        """Layer 2: Rejects text payloads exceeding 500,000 characters with HTTP 413."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        mock_count = MagicMock(count=1)
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_count
        ]

        huge_text = "A" * 500001
        payload = TextUpload(title="Gigantic Text", text=huge_text)
        with self.assertRaises(HTTPException) as ctx:
            await add_knowledge_text(payload, self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 413)
        self.assertIn("too large", ctx.exception.detail.lower())

    @patch("knowledge.backend.routers.assets.enqueue_job")
    async def test_add_knowledge_text_success_within_limits(self, mock_enqueue):
        """Layer 0: Successfully creates knowledge asset and enqueues job within tier limits."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        mock_count = MagicMock(count=1)
        mock_jobs = MagicMock(data=[])
        mock_ins = MagicMock(data=[{"id": "asset-123"}])
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_count,
            mock_jobs
        ]
        self.supabase.table.return_value.insert.return_value.execute.return_value = mock_ins

        payload = TextUpload(title="Product Docs", text="Valid knowledge text explaining our platform architecture.")
        res = await add_knowledge_text(payload, self.supabase, self.workspace_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["asset"]["type"], "text")
        self.assertEqual(res["asset"]["status"], "queued")
        mock_enqueue.assert_called_once()

    async def test_add_knowledge_url_rejects_ssrf_and_private_ips(self):
        """Layer 1 & 2: Rejects SSRF targets (localhost, 127.0.0.1, 169.254.169.254) with HTTP 400."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        mock_count = MagicMock(count=1)
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_count,
            mock_ws,
            mock_count,
            mock_ws,
            mock_count
        ]

        # 127.0.0.1
        with self.assertRaises(HTTPException) as ctx1:
            await add_knowledge_url(UrlUpload(url="http://127.0.0.1:8000/internal"), self.supabase, self.workspace_id)
        self.assertEqual(ctx1.exception.status_code, 400)
        self.assertIn("security safety constraints", ctx1.exception.detail.lower())

        # Metadata IP
        with self.assertRaises(HTTPException) as ctx2:
            await add_knowledge_url(UrlUpload(url="http://169.254.169.254/latest/meta-data"), self.supabase, self.workspace_id)
        self.assertEqual(ctx2.exception.status_code, 400)
        self.assertIn("security safety constraints", ctx2.exception.detail.lower())

        # Localhost
        with self.assertRaises(HTTPException) as ctx3:
            await add_knowledge_url(UrlUpload(url="http://localhost:3000/api"), self.supabase, self.workspace_id)
        self.assertEqual(ctx3.exception.status_code, 400)
        self.assertIn("security safety constraints", ctx3.exception.detail.lower())

    async def test_add_knowledge_url_rejects_invalid_protocol(self):
        """Layer 2: Rejects non-HTTP/HTTPS URLs (file://, ftp://, javascript:) with HTTP 400."""
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        mock_count = MagicMock(count=1)
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_count
        ]

        with self.assertRaises(HTTPException) as ctx:
            await add_knowledge_url(UrlUpload(url="file:///etc/passwd"), self.supabase, self.workspace_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("must begin with http:// or https://", ctx.exception.detail)

    async def test_process_pdf_bg_rejects_empty_file(self):
        """Layer 1: Empty (0 bytes) PDF files raise ValueError without attempting corrupt decompression."""
        with self.assertRaises(ValueError) as ctx:
            await KnowledgeService.process_pdf_bg(
                self.supabase,
                self.workspace_id,
                "empty.pdf",
                b"",
                "asset-empty"
            )
        self.assertIn("empty (0 bytes)", str(ctx.exception).lower())


class TestHorizon20OnboardingPersonaIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Test suite for Onboarding Persona Generation and Schema Integrity.
    """

    def setUp(self):
        self.workspace_id = "ws_onboard_202"
        self.supabase = MagicMock()
        self.supabase.table.return_value.select.return_value.eq.return_value.neq.return_value = (
            self.supabase.table.return_value.select.return_value.eq.return_value
        )

    def test_persona_service_create_persona_schema_fidelity(self):
        """Layer 0: PersonaService.create_persona formats title, JSONB pain points, value_prop, and tone_tweaks."""
        mock_ins = MagicMock(data=[{
            "id": "pers-101",
            "workspace_id": self.workspace_id,
            "title": "VP of Engineering",
            "pain_points": ["Technical debt", "Scaling architecture"],
            "value_prop": "Automated code reliability",
            "tone_tweaks": "Technical and crisp"
        }])
        self.supabase.table.return_value.insert.return_value.execute.return_value = mock_ins

        data = {
            "title": "VP of Engineering",
            "pain_points": ["Technical debt", "Scaling architecture"],
            "value_prop": "Automated code reliability",
            "tone_tweaks": "Technical and crisp"
        }
        res = PersonaService.create_persona(self.supabase, self.workspace_id, data)
        self.assertEqual(res["title"], "VP of Engineering")
        self.assertEqual(res["painPoints"], ["Technical debt", "Scaling architecture"])
        self.assertEqual(res["valueProp"], "Automated code reliability")

    @patch("admin.backend.services.persona_service.PersonaService.create_persona")
    @patch("admin.backend.routers.onboarding.get_service_client")
    @patch("admin.backend.routers.onboarding.get_supabase_client")
    @patch("admin.backend.routers.onboarding.verify_token_and_get_user_id", return_value="user_onboard_123")
    async def test_seed_demo_data_calls_persona_service(self, mock_verify, mock_get_sb, mock_get_svc, mock_create_persona):
        """Layer 0 & 1: seed_demo_data provisions default persona through PersonaService."""
        mock_svc = MagicMock()
        mock_get_svc.return_value = mock_svc
        mock_get_sb.return_value = self.supabase

        mock_mem = MagicMock(data=[{"role": "owner"}])
        mock_ws = MagicMock(data=[{"id": self.workspace_id}])
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = mock_mem
        self.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_ws

        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda k: {
            "Authorization": "Bearer test-token",
            "X-Workspace-Id": self.workspace_id
        }.get(k)
        mock_request.json = AsyncMock(return_value={
            "company_name": "Acme Systems",
            "company_url": "https://acmesystems.io",
            "target_title": "Chief Technology Officer",
            "target_industry": "Enterprise AI",
            "core_value_prop": "End-to-end multi-agent orchestration",
            "force": True
        })

        res = await seed_demo_data(request=mock_request)

        self.assertEqual(res["status"], "seeded")
        mock_create_persona.assert_called_once()
        args, kwargs = mock_create_persona.call_args
        self.assertEqual(args[1], self.workspace_id)
        self.assertEqual(args[2]["title"], "Chief Technology Officer")
        self.assertIn("Enterprise AI", args[2]["pain_points"][0])

    @patch("admin.backend.routers.onboarding.get_service_client")
    @patch("admin.backend.routers.onboarding.get_supabase_client")
    @patch("admin.backend.routers.onboarding.verify_token_and_get_user_id", return_value="user_onboard_456")
    async def test_seed_demo_data_unmigrated_db_resilience(self, mock_verify, mock_get_sb, mock_get_svc):
        """Layer 1: seed_demo_data gracefully survives missing tables (unmigrated database) without throwing 500."""
        from admin.backend.routers.onboarding import seed_demo_data
        mock_svc = MagicMock()
        mock_get_svc.return_value = mock_svc
        mock_get_sb.return_value = self.supabase

        # Simulate missing tables (PostgREST PGRST205 errors)
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("PGRST205: relation 'workspace_members' does not exist")
        self.supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("PGRST205: relation 'workspaces' does not exist")
        self.supabase.table.return_value.insert.return_value.execute.side_effect = Exception("PGRST205: relation does not exist")
        mock_svc.table.return_value.insert.return_value.execute.side_effect = Exception("PGRST205: relation does not exist")

        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda k: {
            "Authorization": "Bearer test-token",
            "X-Workspace-Id": "ws_unmigrated_test"
        }.get(k)
        mock_request.json = AsyncMock(return_value={
            "company_name": "Test Company",
            "target_title": "VP Sales",
            "target_industry": "SaaS",
            "force": True
        })

        res = await seed_demo_data(request=mock_request)
        self.assertEqual(res["status"], "seeded")
        self.assertTrue(res.get("unmigrated"))
        self.assertTrue(res.get("campaign_id"))

    def test_sanitize_text_escapes_formulas_and_truncates(self):
        """Layer 2: sanitize_text escapes formula prefixes and clamps length."""
        from admin.backend.routers.onboarding import sanitize_text
        self.assertEqual(sanitize_text("=cmd|'/C calc'!A0", 50), "'=cmd|'/C calc'!A0")
        self.assertEqual(sanitize_text("+12345", 50), "'+12345")
        self.assertEqual(sanitize_text("@SUM(A1:A10)", 50), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_text("-evil", 50), "'-evil")
        self.assertEqual(sanitize_text("A" * 100, 20), "A" * 20)

    def test_sanitize_linkedin_url_normalizes_and_rejects_malicious_protocols(self):
        """Layer 1 & 2: sanitize_linkedin_url formats valid URLs and rejects javascript: / file: exploits."""
        from admin.backend.routers.onboarding import sanitize_linkedin_url
        self.assertEqual(sanitize_linkedin_url("linkedin.com/in/john-doe"), "https://linkedin.com/in/john-doe")
        self.assertEqual(sanitize_linkedin_url("john-doe"), "https://linkedin.com/in/john-doe")
        self.assertEqual(sanitize_linkedin_url("https://linkedin.com/in/john-doe"), "https://linkedin.com/in/john-doe")
        self.assertIsNone(sanitize_linkedin_url("javascript:alert(1)"))
        self.assertIsNone(sanitize_linkedin_url("file:///etc/passwd"))


    async def test_add_knowledge_asset_ignores_failed_assets_in_quota(self):
        """
        Layer 0 & 1 Paranoia (Flaw 5):
        When a workspace has failed ingestion assets, they must NOT count towards
        the maximum document quota, preventing Free Tier users from getting locked out.
        """
        mock_ws = MagicMock(data=[{"tier": "FREE"}])
        # Suppose exact count without 'failed' returns 2 (active/synced), so space remains!
        mock_active_count = MagicMock(count=2)
        
        # Reset side effect
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_ws,
            mock_active_count
        ]
        self.supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "new-asset-id", "name": "Valid Doc"}]
        )

        with patch("knowledge.backend.routers.assets.enqueue_job", return_value={"id": "job-1"}):
            payload = TextUpload(title="Valid Doc", text="This is valid company documentation.")
            res = await add_knowledge_text(payload, self.supabase, self.workspace_id)
            self.assertEqual(res["status"], "success")

if __name__ == "__main__":
    unittest.main()


