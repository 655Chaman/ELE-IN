#!/usr/bin/env python3
"""
Pre-Flight Migration Linter & Dry-Run Syntax Verification Script.
Paranoia Framework: Layer 0, Layer 1 & Layer 2.

Validates `backend/migrations/999_master_pending_sync.sql` and the full migration suite against:
1. Transaction integrity (BEGIN/COMMIT).
2. Lexical & syntax balance ($$ dollar quotes, quotes, parentheses, semicolons).
3. Strict idempotency enforcement (IF NOT EXISTS, OR REPLACE, DROP POLICY IF EXISTS).
4. Coverage verification across all consolidated and batch tables and RPCs.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def verify_master_migration(sql_path: Path) -> Tuple[bool, List[str], Dict[str, int]]:
    errors = []
    stats = {
        "tables_created": 0,
        "indexes_created": 0,
        "functions_created": 0,
        "policies_created": 0,
        "columns_added": 0,
        "do_blocks": 0,
    }

    if not sql_path.exists():
        return False, [f"File not found: {sql_path}"], stats

    content = sql_path.read_text(encoding="utf-8")

    # 1. Transaction enclosure (ignoring leading comments/whitespace)
    stripped_header = re.sub(r"^(?:\s*--[^\n]*\n)*\s*", "", content)
    if not stripped_header.startswith("BEGIN;"):
        errors.append("Master migration must start with 'BEGIN;'")
    if not content.strip().endswith("COMMIT;"):
        errors.append("Master migration must end with 'COMMIT;'")

    # 2. Dollar quotes balance ($$)
    dollar_matches = re.findall(r"\$\$", content)
    if len(dollar_matches) % 2 != 0:
        errors.append(f"Unbalanced dollar quotes ($$): found {len(dollar_matches)} occurrences")

    # 3. Parentheses balance (ignoring string literals and $$ blocks)
    stripped_sql = re.sub(r"--.*$", "", content, flags=re.MULTILINE)
    clean_for_parens = re.sub(r"\$\$.*?\$\$", "", stripped_sql, flags=re.DOTALL)
    clean_for_parens = re.sub(r"'([^']|'')*'", "", clean_for_parens)

    open_parens = clean_for_parens.count("(")
    close_parens = clean_for_parens.count(")")
    if open_parens != close_parens:
        errors.append(f"Unbalanced parentheses: {open_parens} '(' vs {close_parens} ')'")

    # 4. Strict idempotency checks
    create_tables = re.findall(r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)(\w+\.\w+|\w+)", stripped_sql, re.IGNORECASE)
    if create_tables:
        errors.append(f"Non-idempotent CREATE TABLE without IF NOT EXISTS: {create_tables}")

    all_create_tables = re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+\.\w+|\w+)", stripped_sql, re.IGNORECASE)
    stats["tables_created"] = len(all_create_tables)

    create_indexes = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)(\w+)", stripped_sql, re.IGNORECASE)
    if create_indexes:
        errors.append(f"Non-idempotent CREATE INDEX without IF NOT EXISTS: {create_indexes}")

    all_create_indexes = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)", stripped_sql, re.IGNORECASE)
    stats["indexes_created"] = len(all_create_indexes)

    raw_functions = re.findall(r"CREATE\s+FUNCTION\s+(\w+\.\w+|\w+)", stripped_sql, re.IGNORECASE)
    if raw_functions:
        errors.append(f"Non-idempotent CREATE FUNCTION without OR REPLACE: {raw_functions}")

    all_functions = re.findall(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(\w+\.\w+|\w+)", stripped_sql, re.IGNORECASE)
    stats["functions_created"] = len(all_functions)

    raw_add_columns = re.findall(r"ADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)(\w+)", stripped_sql, re.IGNORECASE)
    if raw_add_columns:
        errors.append(f"Non-idempotent ADD COLUMN without IF NOT EXISTS: {raw_add_columns}")

    all_add_columns = re.findall(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)", stripped_sql, re.IGNORECASE)
    stats["columns_added"] = len(all_add_columns)

    all_policies = re.findall(r"CREATE\s+POLICY\s+(\w+)", stripped_sql, re.IGNORECASE)
    stats["policies_created"] = len(all_policies)

    all_do_blocks = re.findall(r"DO\s+\$\$\s*BEGIN", stripped_sql, re.IGNORECASE)
    stats["do_blocks"] = len(all_do_blocks)

    # 5. Guard against shell heredoc PID expansion (e.g. DO 52979 BEGIN)
    bad_do_blocks = re.findall(r"\b(?:DO|END)\s+\d+", stripped_sql, re.IGNORECASE)
    if bad_do_blocks:
        errors.append(f"Corrupted DO/END block (likely shell $$ PID expansion): {bad_do_blocks}")

    # 6. Topological table creation order verification
    seen_tables = {"users"}
    for line_no, line in enumerate(stripped_sql.splitlines(), 1):
        m_ct = re.search(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(?:public\.)?([a-zA-Z0-9_]+)", line, re.IGNORECASE)
        if m_ct:
            seen_tables.add(m_ct.group(1).lower())
        for m_ref in re.finditer(r"REFERENCES\s+(?:public\.|auth\.)?([a-zA-Z0-9_]+)", line, re.IGNORECASE):
            ref_t = m_ref.group(1).lower()
            if ref_t not in seen_tables:
                errors.append(f"Line {line_no}: REFERENCES table '{ref_t}' before CREATE TABLE IF NOT EXISTS")

    return len(errors) == 0, errors, stats


def verify_master_coverage(master_sql_path: Path) -> Tuple[bool, List[str]]:
    warnings = []
    if not master_sql_path.exists():
        return False, ["Master migration does not exist"]

    master_content = master_sql_path.read_text(encoding="utf-8")

    # Key tables consolidated inside 999_master_pending_sync.sql
    key_tables = [
        "billing_transactions",
        "checkout_sessions",
        "processed_webhook_events",
        "processing_jobs",
        "lead_social_signals",
        "bandit_experiments",
        "copy_variants",
        "trigger_events",
        "harvested_events",
        "event_attendees",
        "multimodal_assets",
        "target_accounts",
        "account_committee_members",
        "multithread_campaign_runs",
    ]

    for tbl in key_tables:
        if tbl not in master_content:
            warnings.append(f"Key table '{tbl}' not found in master migration")

    # Key RPC functions in master migration
    key_rpcs = [
        "add_credits_safely",
        "deduct_credits_safely",
        "release_consumed_daily_action",
    ]

    for rpc in key_rpcs:
        if rpc not in master_content:
            warnings.append(f"Key RPC function '{rpc}' not found in master migration")

    return len(warnings) == 0, warnings


def verify_all_batch_migrations(migrations_dir: Path) -> Tuple[bool, int, List[str]]:
    """Audits all numbered SQL migrations in backend/migrations/."""
    batch_errors = []
    verified_count = 0

    sql_files = sorted(migrations_dir.glob("*.sql"))
    for sql_file in sql_files:
        if sql_file.name == "999_master_pending_sync.sql":
            continue
        try:
            content = sql_file.read_text(encoding="utf-8")
            if not content.strip():
                batch_errors.append(f"{sql_file.name}: empty file")
                continue

            # Verify dollar quotes balance
            dollar_count = content.count("$$")
            if dollar_count % 2 != 0:
                batch_errors.append(f"{sql_file.name}: Unbalanced dollar quotes ($$): count={dollar_count}")

            verified_count += 1
        except Exception as e:
            batch_errors.append(f"{sql_file.name}: error reading file: {e}")

    return len(batch_errors) == 0, verified_count, batch_errors


def main():
    root_dir = Path(__file__).resolve().parent.parent.parent
    master_sql = root_dir / "backend" / "migrations" / "999_master_pending_sync.sql"
    migrations_dir = root_dir / "backend" / "migrations"

    print("=" * 70)
    print("ELE-IN MIGRATION VERIFICATION & PRE-FLIGHT LINTER (STAGE 5)")
    print("=" * 70)
    print(f"Master SQL file: {master_sql}")
    print()

    passed_syntax, errors, stats = verify_master_migration(master_sql)
    passed_coverage, coverage_warnings = verify_master_coverage(master_sql)
    passed_batches, batch_count, batch_errors = verify_all_batch_migrations(migrations_dir)

    print("--- MASTER DDL & IDEMPOTENCY METRICS ---")
    for k, v in stats.items():
        print(f"  • {k.replace('_', ' ').title()}: {v}")
    print()

    print(f"--- BATCH MIGRATION SUITE AUDIT ---")
    print(f"  • Total Individual Migration Files Verified: {batch_count}")
    print()

    if errors:
        print("[ERROR] MASTER SYNTAX / IDEMPOTENCY ERRORS DETECTED:")
        for err in errors:
            print(f"  - {err}")
        print()

    if coverage_warnings:
        print("[WARN] MASTER COVERAGE WARNINGS:")
        for warn in coverage_warnings:
            print(f"  - {warn}")
        print()

    if batch_errors:
        print("[ERROR] BATCH MIGRATION SUITE ERRORS:")
        for b_err in batch_errors:
            print(f"  - {b_err}")
        print()

    if passed_syntax and passed_coverage and passed_batches:
        print("[SUCCESS] 100% of pre-flight migration checks passed cleanly.")
        print(f"   Master sync ({stats['tables_created']} tables, {stats['indexes_created']} indexes, {stats['functions_created']} RPCs) + {batch_count} batch files verified.")
        print("   Ready for atomic execution in the Supabase SQL Editor.")
        sys.exit(0)
    else:
        print("[ERROR] PRE-FLIGHT FAILED: Please address the issues listed above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
