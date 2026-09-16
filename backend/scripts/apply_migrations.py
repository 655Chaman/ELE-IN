import os
import sys
import json
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MIGRATIONS_DIR = "/Users/krdeeksha/Ele-in/backend/migrations"

# Correct application sequence derived from MIGRATION_STATUS.md and dependencies
ORDERED_MIGRATIONS = [
    "001_schema_hardening.sql",
    "002_knowledge_base.sql",
    "003_aggregate_rate_limiting.sql",
    "003_processing_jobs.sql",
    "004_dequeue_and_new_tables.sql",
    "004_fix_rate_limiting.sql",
    "004_rls_hardening.sql",
    "005_account_session_lock.sql",
    "005_fix_ghost_leads.sql",
    "005_fix_rate_limit_race.sql",
    "005_on_delete_cascades.sql",
    "005_rls_recursion_fix.sql",
    "006_rls_policies.sql",
    "006_safety_limits.sql",
    "007_manual_send_detection.sql",
    "007_revert_a8_safeguards.sql",
    "008_match_knowledge_rpc.sql",
    "008_split_action_limits.sql",
    "009_asset_columns.sql",
    "009_lead_states_unique.sql",
    "010_deprecate_old_usage_table.sql",
    "010_fix_api_keys.sql",
    "011_vector_index.sql",
    "011_worker_heartbeat.sql",
    "012_accounts_unique_constraint.sql",
    "012_scale_indexes.sql",
    "013_atomic_rate_limits_and_indexes.sql",
    "013_campaign_accounts_and_indexes.sql",
    "013_usage_limits.sql",
    "014_accounts_cleanup.sql",
    "014_dashboard_rollup_and_index.sql",
    "014_gdpr_cascades.sql",
    "015_gdpr_deletion_requests.sql",
    "015_partial_indexes_and_constraints.sql",
    "015_settings_fixes.sql",
    "015_workspace_stats.sql",
    "016_settings_production.sql",
    "016_strict_data_integrity.sql",
    "017_dashboard_stats_constraints.sql",
    "017_resolve_audit_flaws.sql",
    "018_worker_heartbeat.sql",
    "018_rollup_observability.sql",
    "019_knowledge_storage_bucket.sql",
    "020_accounts_lifecycle.sql",
    "021_add_total_campaigns.sql",
    "021_relax_proxy_constraint.sql",
    "022_envelope_encryption_vault.sql",
    "023_rollup_advisory_lock.sql",
    "023_unified_rate_limits.sql",
    "024_fix_leads_constraints.sql",
    "025_phase2_infrastructure.sql",
    "cleanup_orphaned_leads.sql",
    "rpc_claim_jobs.sql",
    "rpc_decrement_count.sql"
]

def print_manual_instructions(file_path):
    print(f"\n========================================")
    print(f"MANUAL MIGRATION REQUIRED FOR: {file_path}")
    print(f"========================================")
    print("Please paste the following SQL into the Supabase Dashboard SQL Editor:\n")
    try:
        with open(file_path, "r") as f:
            print(f.read())
    except Exception as e:
        print(f"Could not read {file_path}: {e}")
    print(f"\n========================================\n")

def apply_migrations(dry_run=False):
    migrations = [os.path.join(MIGRATIONS_DIR, m) for m in ORDERED_MIGRATIONS]
    
    # Check if we have a direct DB connection string
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            import psycopg2
            print("Found DATABASE_URL, attempting direct PostgreSQL connection...")
            conn = psycopg2.connect(db_url)
            # Use explicit transactions by disabling autocommit
            conn.autocommit = False 
            with conn.cursor() as cur:
                # 1. Create tracking table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        filename TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ DEFAULT now()
                    )
                """)
                conn.commit()

                # Get already applied migrations
                cur.execute("SELECT filename FROM schema_migrations")
                applied = {row[0] for row in cur.fetchall()}

                for mig in migrations:
                    basename = os.path.basename(mig)
                    if basename in applied:
                        # Skip quietly or log at debug level
                        # print(f"Skipping {basename} (already applied)")
                        continue

                    if dry_run:
                        print(f"[DRY RUN] Would apply: {basename}")
                        continue
                    
                    print(f"Applying {basename} via psycopg2...")
                    try:
                        with open(mig, "r") as f:
                            sql = f.read()
                        
                        # 2. Transaction wrap: Each file runs in its own transaction block
                        # The execute() and INSERT run in the same transaction, then commit
                        cur.execute(sql)
                        cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (basename,))
                        conn.commit()
                        print(f"Successfully applied {basename}")
                    except Exception as e:
                        # 3. Clear error reporting & isolating failure
                        conn.rollback()
                        print(f"\nERROR: Failed to apply {basename}")
                        print(f"SQL Error: {e}\nStopping migration process.")
                        conn.close()
                        return

            conn.close()
            return
        except ImportError:
            print("psycopg2 not installed. Falling back to Supabase client / Manual instructions.")
        except Exception as e:
            print(f"Failed to apply migrations via psycopg2: {e}")
            print("Falling back to manual instructions.")

    if dry_run:
        print("[DRY RUN] No database connection to check state. The following files are configured:")
        for mig in migrations:
            print(f"[DRY RUN] Would apply: {os.path.basename(mig)}")
        return

    # Try Supabase client approach
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_key:
        supabase_key = os.getenv("SUPABASE_KEY")
        
    if not supabase_url or not supabase_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")
        for mig in migrations:
            print_manual_instructions(mig)
        return

    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
        
        # Supabase Python client does not have a built-in way to run raw DDL SQL natively 
        # unless a custom RPC like 'exec_sql' exists. We will try that, but usually it fails.
        for mig in migrations:
            print(f"Attempting to apply {mig} via Supabase RPC...")
            try:
                with open(mig, "r") as f:
                    sql = f.read()
                
                # This is a shot in the dark; typically exec_sql is not defined.
                result = supabase.rpc('exec_sql', {'query': sql}).execute()
                print(f"Successfully applied {mig} via RPC.")
            except Exception as e:
                print(f"Failed to apply {mig} via RPC. The Supabase client does not support raw DDL by default.")
                print(f"Error: {e}")
                print_manual_instructions(mig)
                # Fail fast on RPC mode too
                break
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        for mig in migrations:
            print_manual_instructions(mig)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply database migrations")
    parser.add_argument("--dry-run", action="store_true", help="Print which migrations would be applied without executing them")
    args = parser.parse_args()
    
    apply_migrations(dry_run=args.dry_run)
