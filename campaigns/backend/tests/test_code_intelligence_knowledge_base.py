"""
test_code_intelligence_knowledge_base.py — Comprehensive EPF Test Battery.

Validates the REA + Ghidra Deep Code Intelligence & WebAssembly Knowledge Base Engine:
  - Layer 0: AST & Wasm binary analysis, manifest extraction, and markdown generation.
  - Layer 1: Zip-slip prevention, zip-bomb protection, quota gating, and file validation.
  - Layer 2: Zero-secret vector leakage, credential masking, and retry handling.
"""

import io
import os
import json
import zipfile
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, UploadFile

from knowledge.backend.services.code_intelligence_service import (
    CodeIntelligenceService,
    sanitize_code_secrets,
    WASM_MAGIC
)
from knowledge.backend.services.knowledge_service import KnowledgeService
from knowledge.backend.routers.assets import add_knowledge_code, retry_knowledge_asset


class TestCodeIntelligenceKnowledgeBase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.workspace_id = "ws_test_code_intelligence_001"
        self.asset_id = "asset_code_001"

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 0: FOUNDATIONAL MECHANICS
    # ─────────────────────────────────────────────────────────────────────────

    def test_js_bundle_analysis_extracts_frameworks_apis_and_storage(self):
        """
        Layer 0: Deterministic AST token parsing extracts frameworks, APIs,
        third-party SaaS integrations, and storage mechanisms.
        """
        js_code = """
        import React, { useState } from 'react';
        import { createStore } from 'zustand';
        import axios from 'axios';
        import * as Sentry from '@sentry/react';
        import { loadStripe } from '@stripe/stripe-js';

        const client = axios.create({ baseURL: '/api/v2/campaigns/dispatch' });
        const ws = new WebSocket('wss://stream.elein.ai/v1/inbox');
        
        function handleAuth() {
            localStorage.setItem('user_session', 'token');
            sessionStorage.setItem('temp_step', 'sequence');
        }
        """
        analysis = CodeIntelligenceService.analyze_js_bundle(js_code, "app_bundle.js")

        self.assertEqual(analysis["kind"], "javascript_bundle")
        self.assertIn("React", analysis["frameworks"])
        self.assertIn("Zustand", analysis["frameworks"])
        self.assertIn("Sentry", analysis["integrations"])
        self.assertIn("Stripe", analysis["integrations"])
        self.assertIn("/api/v2/campaigns/dispatch", analysis["discovered_endpoints"])
        self.assertIn("wss://stream.elein.ai/v1/inbox", analysis["websocket_endpoints"])
        self.assertIn("localStorage", analysis["storage_mechanisms"])
        self.assertIn("sessionStorage", analysis["storage_mechanisms"])

    def test_wasm_binary_analysis_extracts_sections_and_telemetry(self):
        """
        Layer 0: Parses WebAssembly binary sections and scans linear memory
        for anti-bot heuristics (WebGL fingerprinting, mouse kinematics, anti-debugging).
        """
        # Construct synthetic Wasm binary with magic header + custom section containing anti-bot strings
        custom_payload = b"WEBGL_debug_renderer_info movementX jerk Date.now debugger"
        section_id = 0  # Custom section
        sec_len = len(b"\x07telemet") + len(custom_payload)
        
        # \x00asm \x01\x00\x00\x00 + section 0
        wasm_bytes = WASM_MAGIC + b"\x01\x00\x00\x00" + bytes([section_id, sec_len, 7]) + b"telemet" + custom_payload

        analysis = CodeIntelligenceService.analyze_wasm_binary(wasm_bytes, "challenge.wasm")

        self.assertEqual(analysis["kind"], "wasm_binary")
        self.assertEqual(analysis["filename"], "challenge.wasm")
        self.assertGreater(analysis["total_bytes"], 0)
        self.assertIn("section_count", analysis["section_summary"])
        self.assertTrue(any(level in analysis["telemetry_risk"] for level in ["HIGH", "CRITICAL"]))
        findings = analysis["telemetry_findings"]
        self.assertIn("canvas_webgl_fingerprinting", findings)
        self.assertIn("WEBGL_debug_renderer_info", findings["canvas_webgl_fingerprinting"])
        self.assertIn("mouse_kinematics_and_jerk", findings)
        self.assertIn("movementX", findings["mouse_kinematics_and_jerk"])

    def test_chrome_extension_archive_parsing(self):
        """
        Layer 0: Unpacks Chrome Extension archive, extracts manifest.json permissions,
        and aggregates JavaScript analysis.
        """
        manifest = {
            "name": "Ele-in LinkedIn Companion",
            "version": "2.4.0",
            "manifest_version": 3,
            "permissions": ["storage", "activeTab", "webRequest"],
            "host_permissions": ["https://*.linkedin.com/*"]
        }
        background_js = """
        import { createClient } from '@supabase/supabase-js';
        chrome.storage.local.get(['session'], (res) => {
            fetch('/api/v1/telemetry/heartbeat');
        });
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("background.js", background_js)
        zip_bytes = buf.getvalue()

        analysis = CodeIntelligenceService.analyze_extension_or_archive(zip_bytes, "companion.zip")

        self.assertEqual(analysis["kind"], "extension_or_archive")
        self.assertEqual(analysis["manifest"]["name"], "Ele-in LinkedIn Companion")
        self.assertIn("storage", analysis["manifest"]["permissions"])
        self.assertIn("Supabase", analysis["integrations"])
        self.assertIn("chrome.storage", analysis["storage_mechanisms"])
        self.assertIn("/api/v1/telemetry/heartbeat", analysis["discovered_endpoints"])

    def test_markdown_synthesis_formatting(self):
        """
        Layer 0: Verifies that markdown synthesis outputs structured, semantic
        headings ready for SemanticBrain RAG indexing.
        """
        analysis = {
            "filename": "web_engine.js",
            "kind": "javascript_bundle",
            "frameworks": ["React", "Tailwind CSS", "Zustand"],
            "integrations": ["Stripe", "Datadog"],
            "storage_mechanisms": ["localStorage"],
            "discovered_endpoints": ["/api/v2/campaigns", "/api/v2/leads"],
            "websocket_endpoints": ["wss://api.example.com/ws"],
            "ui_routes": ["/dashboard", "/campaigns/new"],
            "wasm_modules": []
        }
        md = CodeIntelligenceService.generate_code_intelligence_markdown(analysis)

        self.assertIn("# Technical Architecture & Code Intelligence: web_engine.js", md)
        self.assertIn("## Tech Stack Profile", md)
        self.assertIn("React, Tailwind CSS, Zustand", md)
        self.assertIn("## API Topography & Endpoints", md)
        self.assertIn("`[REST/GraphQL]` /api/v2/campaigns", md)
        self.assertIn("`[WebSocket]` wss://api.example.com/ws", md)
        self.assertIn("## Third-Party Integrations & SaaS Ecosystem", md)
        self.assertIn("Stripe, Datadog", md)
        self.assertIn("## Architectural Strengths & Differentiators", md)

    def test_process_and_index_code_artifact_flow(self):
        """
        Layer 0: Verifies end-to-end driver indexation into SemanticBrain.
        """
        mock_supabase = MagicMock()
        mock_brain = MagicMock()

        with patch("knowledge.backend.services.vector_store.SemanticBrain", return_value=mock_brain):
            result = CodeIntelligenceService.process_and_index_code_artifact(
                workspace_id=self.workspace_id,
                filename="main.bundle.js",
                file_bytes=b"import React from 'react'; fetch('/api/v1/auth');",
                asset_id=self.asset_id,
                supabase=mock_supabase
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["asset_id"], self.asset_id)
            mock_brain.index_document.assert_called_once()
            call_kwargs = mock_brain.index_document.call_args[1]
            self.assertEqual(call_kwargs["doc_type"], "code_intelligence")
            self.assertEqual(call_kwargs["source_name"], "main.bundle.js")
            self.assertIn("React", call_kwargs["content"])

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS & ADVERSARIAL DEFENSE
    # ─────────────────────────────────────────────────────────────────────────

    def test_zip_slip_path_traversal_rejection(self):
        """
        Layer 1: Enforces immediate rejection of malicious archives containing
        Zip-Slip directory traversal paths (e.g. ../../etc/cron.d/malicious).
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/cron.d/malicious", "echo pwned")
        evil_bytes = buf.getvalue()

        with self.assertRaises(ValueError) as ctx:
            CodeIntelligenceService.analyze_extension_or_archive(evil_bytes, "malicious.zip")

        self.assertIn("Zip-slip path traversal detected", str(ctx.exception))

    def test_zip_bomb_uncompressed_ceiling_rejection(self):
        """
        Layer 1: Rejects zip bombs when total uncompressed bytes exceed safety limits.
        """
        fake_info = zipfile.ZipInfo("huge_file.bin")
        fake_info.file_size = 60 * 1024 * 1024  # 60MB > 50MB ceiling

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # write a dummy entry then manipulate infolist via mock
            zf.writestr("test.txt", "small")

        with patch("zipfile.ZipFile.infolist", return_value=[fake_info]):
            with self.assertRaises(ValueError) as ctx:
                CodeIntelligenceService.analyze_extension_or_archive(buf.getvalue(), "bomb.zip")

            self.assertIn("Zip-bomb defense", str(ctx.exception))

    def test_empty_or_corrupted_wasm_rejection(self):
        """
        Layer 1: Rejects invalid or truncated Wasm binaries before invoking decompiler.
        """
        with self.assertRaises(ValueError) as ctx1:
            CodeIntelligenceService.analyze_wasm_binary(b"", "empty.wasm")
        self.assertIn("is empty", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            CodeIntelligenceService.analyze_wasm_binary(b"NOT_WASM_CORRUPTED", "corrupt.wasm")
        self.assertIn("missing \\x00asm header", str(ctx2.exception))

    async def test_add_knowledge_code_file_type_validation(self):
        """
        Layer 1: Rejects disallowed file extensions (e.g. .exe, .sh, .py)
        with HTTP 400.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[{"tier": "PRO"}])
        mock_supabase.table().select().eq().neq().execute.return_value = MagicMock(count=0, data=[])

        # Mock UploadFile with disallowed extension
        file_mock = MagicMock(spec=UploadFile)
        file_mock.filename = "malicious.sh"
        file_mock.read = AsyncMock(return_value=b"#!/bin/sh\nrm -rf /")

        with self.assertRaises(HTTPException) as ctx:
            await add_knowledge_code(file=file_mock, supabase=mock_supabase, workspace_id=self.workspace_id)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid file type '.sh'", ctx.exception.detail)

    async def test_add_knowledge_code_tier_quota_enforcement(self):
        """
        Layer 1: Enforces workspace tier asset limits (FREE = 3 assets).
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[{"tier": "FREE"}])
        # Current count = 3 >= max_assets (3)
        mock_supabase.table().select().eq().neq().execute.return_value = MagicMock(count=3, data=[{"id": "1"}, {"id": "2"}, {"id": "3"}])

        file_mock = MagicMock(spec=UploadFile)
        file_mock.filename = "bundle.js"
        file_mock.read = AsyncMock(return_value=b"console.log('test');")

        with self.assertRaises(HTTPException) as ctx:
            await add_knowledge_code(file=file_mock, supabase=mock_supabase, workspace_id=self.workspace_id)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Knowledge Base limit reached", ctx.exception.detail)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 2: HUMAN PARANOIA & ZERO-SECRET LEAKAGE
    # ─────────────────────────────────────────────────────────────────────────

    def test_secret_sanitization_masks_all_credentials(self):
        """
        Layer 2: Zero-Secret Vector Leakage. Ensures that raw API keys, JWTs,
        AWS credentials, private RSA keys, and database passwords are redacted
        BEFORE vector store embedding.
        """
        raw_code = """
        // OpenAI Key
        const oai = 'sk-abcdefghijklmnopqrstuvwxyz1234567890';
        // NVIDIA Key
        const nva = 'nvapi-1234567890abcdefghijklmnopqrstuvwxyz';
        // AWS Access Key ID
        const awsKey = 'AKIAIOSFODNN7EXAMPLE';
        // GitHub PAT
        const ghPat = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz12';
        // JWT
        const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';
        // Sentry DSN
        const sentry = 'https://abcdef0123456789@o123456.ingest.sentry.io/7890123';
        // Database connection string
        const conn = 'postgres://postgres:SuperSecretP@ssword123@db.example.com:5432/production';
        // Private Key
        const rsa = `-----BEGIN RSA PRIVATE KEY-----
        MIIEowIBAAKCAQEA0Y3y...
        -----END RSA PRIVATE KEY-----`;
        """

        sanitized = sanitize_code_secrets(raw_code)

        # Assert no sensitive values survive in sanitized output
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", sanitized)
        self.assertNotIn("nvapi-1234567890abcdefghijklmnopqrstuvwxyz", sanitized)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", sanitized)
        self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuvwxyz12", sanitized)
        self.assertNotIn("SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c", sanitized)
        self.assertNotIn("abcdef0123456789@o123456", sanitized)
        self.assertNotIn("SuperSecretP@ssword123", sanitized)
        self.assertNotIn("MIIEowIBAAKCAQEA0Y3y", sanitized)

        # Assert clean redaction placeholders are substituted
        self.assertIn("[REDACTED_SECRET_OPENAI_KEY]", sanitized)
        self.assertIn("[REDACTED_SECRET_NVIDIA_KEY]", sanitized)
        self.assertIn("[REDACTED_SECRET_AWS_KEY_ID]", sanitized)
        self.assertIn("[REDACTED_SECRET_GITHUB_PAT]", sanitized)
        self.assertIn("[REDACTED_SECRET_JWT]", sanitized)
        self.assertIn("[REDACTED_SECRET_SENTRY_DSN]", sanitized)
        self.assertIn("[REDACTED_PASSWORD]", sanitized)
        self.assertIn("[REDACTED_SECRET_PRIVATE_KEY]", sanitized)

    async def test_retry_knowledge_asset_for_code_intelligence(self):
        """
        Layer 2: Handles retry of a failed code_intelligence asset cleanly.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
            data=[{
                "id": self.asset_id,
                "workspace_id": self.workspace_id,
                "name": "target_bundle.js",
                "type": "code_intelligence",
                "status": "failed"
            }]
        )

        with patch("knowledge.backend.routers.assets.enqueue_job", return_value={"id": "job_retry_1"}):
            resp = await retry_knowledge_asset(
                asset_id=self.asset_id,
                supabase=mock_supabase,
                workspace_id=self.workspace_id
            )
            self.assertEqual(resp["status"], "retrying")
            self.assertEqual(resp["asset_id"], self.asset_id)


if __name__ == "__main__":
    unittest.main()
