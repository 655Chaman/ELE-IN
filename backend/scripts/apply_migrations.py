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
    "026_phase3_performance_and_isolation.sql",
    "027_phase3_version_integrity_and_fairness.sql",
    "028_phase3_final_audit_fixes.sql",
    "029_phase3_account_eligibility.sql",
    "030_phase_b_a_schema_additions.sql",
    "030_phase_b_b_concurrent_unique_index.sql",
    "030_phase_b_c_composite_fk.sql",
    "030_phase_b_d_validate_constraints.sql",
    "030_phase_b_e_not_null.sql",
    "030_phase_b_f1_workspace_queue_index.sql",
    "030_phase_b_f2_ces_queue_index.sql",
    "031_get_user_by_email.sql",
    "031_phase_b_security_hardening.sql",
    "032_advance_reply_waiting.sql",
    "033_fix_manual_mode_column.sql",
    "033_timezone_scheduling.sql",
    "034_add_location_to_bulk_import.sql",
    "034_fix_account_status_enum.sql",
    "035_lead_lists_regions_and_status.sql",
    "036_update_bulk_import_timezone.sql",
    "037_suppression_errcode.sql",
    "038_enrollment_suppression_trigger.sql",
    "040_fix_zero_policy_tables.sql",
    "041_drop_dead_bench_tables.sql",
    "042_add_hubspot_token_column.sql",
    "043_add_paused_execution_state.sql",
    "044_add_hubspot_deal_id.sql",
    "045_add_hubspot_won_stage_id.sql",
    "046_agency_mode.sql",
    "046_knowledge_synthesis_schema.sql",
    "047_booking_rate_fix.sql",
    "048_fix_rollup_stats.sql",
    "049_ai_reply_approvals.sql",
    "050_vector_dimension_fix.sql",
    "051_api_keys_secure_hashing.sql",
    "051_calendar_integration.sql",
    "052_api_rate_limits_and_webhooks.sql",
    "053_add_message_node_id.sql",
    "054_in_app_notifications.sql",
    "054_notifications.sql",
    "055_add_password_encrypted_to_proxies.sql",
    "056_fix_vault_rpc.sql",
    "059_revoke_vault_rpc_public_execute.sql",
    "061_phase_9_objections.sql",
    "062_phase_4_synthesis.sql",
    "063_fix_jobs_rls.sql",
    "065_vector_optimization_migration_v2.sql",
    "066_credit_system_core.sql",
    "067_billing_transactions_package_id.sql",
    "067_checkout_sessions.sql",
    "067_enrollment_unique_constraint.sql",
    "068_messages_thread_url.sql",
    "068_processing_jobs_idempotency.sql",
    "069_bayesian_icp_weights.sql",
    "069_proxies_webshare_columns.sql",
    "070_personas_columns_and_objections_unification.sql",
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
