"""
test_csv_bulk_import_hardening.py

Unit tests for Step 22:
- Formula Injection Neutralization (CWE-1236)
- UTF-8 BOM Stripping & Header Normalization
- Smart Fuzzy Synonym Matching (LinkedIn, Names, Emails, Company)
- Universal Newlines (\r, \n, \r\n) & Delimiter Sniffing (,\t;|)
- Upload Guards (Extension, 50MB Ceiling, 0-Byte Rejection)
- Row Limits (>25,000 ceiling), Zero Valid Leads, and NUL Byte Stripping
"""

import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from leads.backend.services.data_hygiene import DataHygieneService
from campaigns.backend.routers.elein import process_csv_background, upload_csv


class MockSupabase:
    """Mock Supabase client for testing CSV import background and upload routines."""
    def __init__(self):
        self.updates = {}
        self.inserts = {}
        self.rpcs = []

    def table(self, table_name):
        mock_tbl = MagicMock()
        
        def mock_select(*args, **kwargs):
            sel_mock = MagicMock()
            sel_mock.eq.return_value.execute.return_value = MagicMock(data=[{"status": "pending"}])
            return sel_mock

        def mock_update(payload):
            if table_name not in self.updates:
                self.updates[table_name] = []
            self.updates[table_name].append(payload)
            upd_mock = MagicMock()
            upd_mock.eq.return_value.execute.return_value = MagicMock(data=[payload])
            return upd_mock

        def mock_insert(payload):
            if table_name not in self.inserts:
                self.inserts[table_name] = []
            self.inserts[table_name].append(payload)
            ins_mock = MagicMock()
            ins_mock.execute.return_value = MagicMock(data=[payload])
            return ins_mock

        mock_tbl.select = mock_select
        mock_tbl.update = mock_update
        mock_tbl.insert = mock_insert
        return mock_tbl

    def rpc(self, func_name, params=None):
        self.rpcs.append((func_name, params))
        rpc_mock = MagicMock()
        if func_name == "bulk_import_leads":
            leads = params.get("p_leads", []) if params else []
            rpc_mock.execute.return_value = MagicMock(data={"inserted_count": len(leads)})
        elif func_name == "get_credit_balance":
            rpc_mock.execute.return_value = MagicMock(data={"balance": 100})
        elif func_name == "deduct_credits_safely":
            rpc_mock.execute.return_value = MagicMock(data={"success": True})
        elif func_name == "add_credits_safely":
            rpc_mock.execute.return_value = MagicMock(data={"success": True})
        else:
            rpc_mock.execute.return_value = MagicMock(data={"success": True})
        return rpc_mock

    def get_imported_leads(self):
        imported = []
        for func_name, params in self.rpcs:
            if func_name == "bulk_import_leads" and params and "p_leads" in params:
                imported.extend(params["p_leads"])
        return imported


class TestCsvBulkImportHardening(unittest.TestCase):
    """Test suite covering the 12 CSV bulk import hardening requirements."""

    def test_formula_injection_sanitization(self):
        """
        Requirement 1: Neutralizes formula triggers (=, @, +, -) with a leading single quote.
        Legitimate signed numbers (-42, +3.14) are preserved.
        """
        # Triggers neutralized
        self.assertEqual(DataHygieneService.sanitize_text("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(DataHygieneService.sanitize_text("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(DataHygieneService.sanitize_text("+cmd"), "'+cmd")
        self.assertEqual(DataHygieneService.sanitize_text("-cmd"), "'-cmd")

        # Legitimate signed numbers preserved
        self.assertEqual(DataHygieneService.sanitize_text("-42"), "-42")
        self.assertEqual(DataHygieneService.sanitize_text("+3.14"), "+3.14")
        self.assertEqual(DataHygieneService.sanitize_text(-42), "-42")
        self.assertEqual(DataHygieneService.sanitize_text("+0.05"), "+0.05")

        # Dedicated helper sanitize_csv_cell
        self.assertEqual(DataHygieneService.sanitize_csv_cell("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(DataHygieneService.sanitize_csv_cell("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(DataHygieneService.sanitize_csv_cell("+cmd"), "'+cmd")
        self.assertEqual(DataHygieneService.sanitize_csv_cell("-cmd"), "'-cmd")
        self.assertEqual(DataHygieneService.sanitize_csv_cell("-42"), "-42")
        self.assertEqual(DataHygieneService.sanitize_csv_cell("+3.14"), "+3.14")

    def test_utf8_bom_header_stripping(self):
        """
        Requirement 2: Headers starting with \ufeff BOM are stripped and parsed correctly.
        """
        mock_sb = MockSupabase()
        content = "\ufefffirst_name,last_name,linkedin\nJohn,Doe,https://www.linkedin.com/in/johndoe\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                process_csv_background("list_bom", temp_path)
            leads = mock_sb.get_imported_leads()
            self.assertEqual(len(leads), 1)
            self.assertEqual(leads[0]["first_name"], "John")
            self.assertEqual(leads[0]["last_name"], "Doe")
            self.assertEqual(leads[0]["linkedin_url"], "https://www.linkedin.com/in/johndoe")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_fuzzy_header_matching_linkedin(self):
        """
        Requirement 3: Column 'Person LinkedIn Profile' matches linkedin_url.
        """
        mock_sb = MockSupabase()
        content = "Person LinkedIn Profile,first_name,last_name\nhttps://www.linkedin.com/in/alice,Alice,Smith\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                process_csv_background("list_li", temp_path)
            leads = mock_sb.get_imported_leads()
            self.assertEqual(len(leads), 1)
            self.assertEqual(leads[0]["linkedin_url"], "https://www.linkedin.com/in/alice")
            self.assertEqual(leads[0]["first_name"], "Alice")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_fuzzy_header_matching_names_and_email(self):
        """
        Requirement 4: Headers 'fname', 'lname', 'Work Email Address', 'Organization' match properly.
        """
        mock_sb = MockSupabase()
        content = "fname,lname,Work Email Address,Organization,linkedin\nBob,Jones,bob@example.com,Acme Corp,https://www.linkedin.com/in/bobjones\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                process_csv_background("list_fuzzy", temp_path)
            leads = mock_sb.get_imported_leads()
            self.assertEqual(len(leads), 1)
            self.assertEqual(leads[0]["first_name"], "Bob")
            self.assertEqual(leads[0]["last_name"], "Jones")
            self.assertEqual(leads[0]["email"], "bob@example.com")
            self.assertEqual(leads[0]["company_name"], "Acme")
            self.assertEqual(leads[0]["linkedin_url"], "https://www.linkedin.com/in/bobjones")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_universal_newlines_carriage_return(self):
        """
        Requirement 5: CSV with carriage-return \r line endings parses multiple rows seamlessly.
        """
        mock_sb = MockSupabase()
        content = b"first_name,last_name,linkedin\rUser One,Smith,https://www.linkedin.com/in/user1\rUser Two,Doe,https://www.linkedin.com/in/user2\r"
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                process_csv_background("list_cr", temp_path)
            leads = mock_sb.get_imported_leads()
            self.assertEqual(len(leads), 2)
            self.assertEqual(leads[0]["first_name"], "User")
            self.assertEqual(leads[1]["first_name"], "User")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_delimiter_sniffing_tab_and_semicolon(self):
        """
        Requirement 6: Sniffs tab (\\t) and semicolon (;) delimiters accurately.
        """
        # Part A: Tab delimited
        mock_sb_tab = MockSupabase()
        tab_content = "first_name\tlast_name\tlinkedin\nJohn\tDoe\thttps://www.linkedin.com/in/johndoe\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(tab_content)
            tab_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb_tab):
                process_csv_background("list_tab", tab_path)
            leads_tab = mock_sb_tab.get_imported_leads()
            self.assertEqual(len(leads_tab), 1)
            self.assertEqual(leads_tab[0]["first_name"], "John")
            self.assertEqual(leads_tab[0]["last_name"], "Doe")
        finally:
            if os.path.exists(tab_path):
                os.remove(tab_path)

        # Part B: Semicolon delimited
        mock_sb_semi = MockSupabase()
        semi_content = "first_name;last_name;linkedin\nJane;Smith;https://www.linkedin.com/in/janesmith\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(semi_content)
            semi_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb_semi):
                process_csv_background("list_semi", semi_path)
            leads_semi = mock_sb_semi.get_imported_leads()
            self.assertEqual(len(leads_semi), 1)
            self.assertEqual(leads_semi[0]["first_name"], "Jane")
            self.assertEqual(leads_semi[0]["last_name"], "Smith")
        finally:
            if os.path.exists(semi_path):
                os.remove(semi_path)

    def test_upload_csv_rejects_non_csv_extension(self):
        """
        Requirement 7: Uploading .exe or .sh returns HTTP 400.
        """
        mock_sb = MockSupabase()

        # Reject .exe
        file_exe = UploadFile(filename="malicious_payload.exe", file=io.BytesIO(b"binary executable"))
        with self.assertRaises(HTTPException) as ctx_exe:
            upload_csv(
                file=file_exe,
                list_name="Payload Test",
                supabase=mock_sb,
                workspace_id="ws_1",
                user_id="u_1"
            )
        self.assertEqual(ctx_exe.exception.status_code, 400)
        self.assertEqual(ctx_exe.exception.detail, "Only CSV or text files (.csv, .txt) are supported.")

        # Reject .sh
        file_sh = UploadFile(filename="hack.sh", file=io.BytesIO(b"#!/bin/bash\nrm -rf /"))
        with self.assertRaises(HTTPException) as ctx_sh:
            upload_csv(
                file=file_sh,
                list_name="Shell Script Test",
                supabase=mock_sb,
                workspace_id="ws_1",
                user_id="u_1"
            )
        self.assertEqual(ctx_sh.exception.status_code, 400)
        self.assertEqual(ctx_sh.exception.detail, "Only CSV or text files (.csv, .txt) are supported.")

    def test_upload_csv_rejects_empty_file(self):
        """
        Requirement 8: Uploading a 0-byte file returns HTTP 400.
        """
        mock_sb = MockSupabase()
        empty_file = UploadFile(filename="empty_leads.csv", file=io.BytesIO(b""))
        with self.assertRaises(HTTPException) as ctx:
            upload_csv(
                file=empty_file,
                list_name="Empty List",
                supabase=mock_sb,
                workspace_id="ws_1",
                user_id="u_1"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Uploaded CSV file is empty.")

    def test_upload_csv_rejects_oversized_file(self):
        """
        Requirement 9: Uploading a file exceeding 50MB returns HTTP 400.
        """
        mock_sb = MockSupabase()

        class MockOversizedStream:
            def __init__(self, target_size):
                self.target_size = target_size
                self.delivered = 0
                self.chunk = b"A" * (1024 * 1024)

            def read(self, size=-1):
                if self.delivered >= self.target_size:
                    return b""
                remaining = self.target_size - self.delivered
                send_len = min(len(self.chunk), remaining)
                self.delivered += send_len
                return self.chunk[:send_len]

        oversized_stream = MockOversizedStream(51 * 1024 * 1024)
        file_oversized = UploadFile(filename="huge_leads.csv", file=oversized_stream)

        with self.assertRaises(HTTPException) as ctx:
            upload_csv(
                file=file_oversized,
                list_name="Huge List",
                supabase=mock_sb,
                workspace_id="ws_1",
                user_id="u_1"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Uploaded CSV exceeds maximum allowed file size of 50MB.")

    def test_process_csv_background_max_rows_ceiling(self):
        """
        Requirement 10: > 25,000 rows raises error and marks status error.
        """
        mock_sb = MockSupabase()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write("first_name,last_name,linkedin\n")
            # 25,001 rows
            tf.write("John,Doe,https://www.linkedin.com/in/johndoe\n" * 25001)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb), \
                 patch("campaigns.backend.routers.elein.get_service_client", return_value=mock_sb):
                with self.assertRaises(ValueError) as ctx:
                    process_csv_background("list_overflow", temp_path)
            self.assertIn("25,000", str(ctx.exception))
            # Verify status in database was updated to error
            lead_list_updates = mock_sb.updates.get("lead_lists", [])
            error_updates = [u for u in lead_list_updates if u.get("status") == "error"]
            self.assertTrue(len(error_updates) > 0)
            self.assertIn("25,000", error_updates[0].get("error_message", ""))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_process_csv_background_zero_valid_leads(self):
        """
        Requirement 11: 0 valid leads completes cleanly with row_count=0 without hanging.
        """
        mock_sb = MockSupabase()
        # Non-linkedin URLs are invalid leads
        content = "first_name,last_name,linkedin\nInvalid,Lead,https://example.com/not-linkedin\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".csv") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                process_csv_background("list_zero", temp_path)
            
            lead_list_updates = mock_sb.updates.get("lead_lists", [])
            completed_updates = [u for u in lead_list_updates if u.get("status") == "completed"]
            self.assertTrue(len(completed_updates) > 0)
            self.assertEqual(completed_updates[-1].get("row_count"), 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_process_csv_background_nul_bytes(self):
        """
        Requirement 12: Strips \\x00 NUL bytes without crashing and imports successfully.
        """
        mock_sb = MockSupabase()
        content = b"first_name,last_name,linkedin\nJo\x00hn,D\x00oe,https://www.linkedin.com/in/johndoe\n"
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as tf:
            tf.write(content)
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_sb):
                process_csv_background("list_nul", temp_path)
            leads = mock_sb.get_imported_leads()
            self.assertEqual(len(leads), 1)
            self.assertEqual(leads[0]["first_name"], "John")
            self.assertEqual(leads[0]["last_name"], "Doe")
            self.assertEqual(leads[0]["linkedin_url"], "https://www.linkedin.com/in/johndoe")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
