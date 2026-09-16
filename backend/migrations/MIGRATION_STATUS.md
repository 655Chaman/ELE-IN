# Migration Status

**RULE: Never create a migration file without updating this document.**

> [!WARNING]
> **DO NOT USE AN AUTOMATED FILENAME-SORTED RUNNER FOR MIGRATIONS.**
> Due to historical versioning conflicts, there are multiple migration files with the same prefix numbers (013, 017, 018, 023). These must be applied manually in a specific order to avoid dependency errors.

## Conflicting Migration Groups & Recommended Application Order

### Migration 013 (Campaign Accounts & Limits)
Due to multiple iterations of JSON-to-table migrations for campaign accounts, there are several 013 files.
**Recommended Order:**
1. `013_atomic_rate_limits_and_indexes.sql` (Creates `idx_accounts_workspace_status` and `try_consume_daily_action`)
2. `013_campaign_accounts_and_indexes.sql` (Creates `campaign_accounts` and migrating data)
**Superseded/Fallbacks:**
- `013_campaign_accounts.sql`, `013_campaign_accounts_fix.sql`, `013_campaign_accounts_fix2.sql` (Use `fix2` only if the `013_campaign_accounts_and_indexes.sql` migration fails due to JSON casting issues).

### Migration 017 (Constraints & Audits)
**Recommended Order:**
1. `017_dashboard_stats_constraints.sql` (**applied**) - Adds PK to `daily_workspace_stats` and `UNIQUE` to `daily_campaign_stats`.
2. `017_resolve_audit_flaws.sql` (**pending**) - Enforces suppression checks and fixes lead duplicate tags/constraints.
**Superseded/Moved:**
- `017_fix_rls_gaps.sql` (Superseded: policy was moved into `023_unified_rate_limits.sql` because the target table didn't exist yet).

### Migration 018 (Observability)
These are independent of each other but both share the 018 prefix.
**Recommended Order:**
1. `018_worker_heartbeat.sql` (Creates `worker_heartbeat` table)
2. `018_rollup_observability.sql` (**applied**) - Adds columns to `processing_jobs` and creates `daily_rollup_log`.

### Migration 023 (Advisory Locks & Unified Rate Limits)
**Recommended Order:**
1. `023_rollup_advisory_lock.sql` (Creates `processing_locks` and lock functions)
2. `023_unified_rate_limits.sql` (Creates `account_limit_overrides`, fixes rate limits, safely removes `daily_action_cap` while temporarily retaining `daily_connection_limit` and `daily_message_limit` to prevent breaking active code).

---

## Instructions: How to Apply Migrations via Supabase Dashboard
Because the Supabase Python client REST API (PostgREST) does not support executing raw DDL statements, these migrations must be run manually via the dashboard.

1. Log in to your Supabase project dashboard.
2. Go to the **SQL Editor** in the left sidebar.
3. Open a new query tab.
4. Copy the exact SQL contents of the migration files in the **Recommended Order** shown above.
5. Paste the SQL into the editor and click **Run**.
6. Once successfully executed, update the **Current Status** of the migration in this document.
