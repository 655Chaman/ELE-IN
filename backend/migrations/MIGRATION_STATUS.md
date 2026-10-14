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

### Migration 033 (Lead-Local Timezone Scheduling — Phase 1 Foundation)
This migration supersedes and replaces the now-deleted `032_timezone_foundation.sql`. The earlier file used `normalized_location` as the primary key directly and lacked a `CHECK` constraint on `resolution_status`; this version uses a safer surrogate `id UUID` primary key, promotes `normalized_location` to a `UNIQUE NOT NULL` constraint, and adds the `CHECK` constraint. All statements are idempotent (`IF NOT EXISTS`).
**Recommended Order:**
1. `033_timezone_scheduling.sql` (**pending**) - Adds `timezone TEXT` column to `public.leads`; creates `public.location_timezone_cache` table (surrogate UUID PK, UNIQUE `normalized_location`, CHECK on `resolution_status`); creates `idx_location_timezone_cache_status` index.
**Superseded/Deleted:**
- `032_timezone_foundation.sql` (Deleted: superseded by this migration — conflicting primary key shape and missing CHECK constraint).


## Instructions: How to Apply Migrations via Supabase Dashboard
Because the Supabase Python client REST API (PostgREST) does not support executing raw DDL statements, these migrations must be run manually via the dashboard.

1. Log in to your Supabase project dashboard.
2. Go to the **SQL Editor** in the left sidebar.
3. Open a new query tab.
4. Copy the exact SQL contents of the migration files in the **Recommended Order** shown above.
5. Paste the SQL into the editor and click **Run**.
6. Once successfully executed, update the **Current Status** of the migration in this document.

### Migration 051 (Phase C)
**Recommended Order:**
1. `051_calendar_integration.sql` (**pending**) - Adds calendar_provider, calendar_token, and calendar_link to accounts for autonomous meeting booking.
- `069_bayesian_icp_weights.sql` (Creates icp_signal_weights table and record_bayesian_icp_outcome RPC)
- `070_personas_columns_and_objections_unification.sql` (**pending**) - Adds value_prop, target_titles, tone_tweaks to personas; adds raw_text to knowledge_assets; unifies knowledge_objections and syncs legacy objections.
- `071_release_consumed_daily_action.sql` (**pending**) - Adds safe decrement RPC for failed action releases.
- `072_timezone_aware_daily_action_limits.sql` (**pending**) - Adds timezone-aware daily limit calculations and window functions.
- `073_agency_whitelabel_and_client_metrics.sql` (**pending**) - Adds white-label columns (brand, domain, color, logo_url, enabled) to public.agencies and creates get_agency_clients_overview RPC for aggregated client portfolio telemetry.
- `074_proxy_latency_and_exit_ip.sql` (**pending**) - Adds proxy latency and exit IP columns for proxy health telemetry.
- `075_prospect_social_signal_radar.sql` (**pending**) - Adds prospect social signals and engagement radar tables.
- `076_workspace_ai_gateway_settings.sql` (**pending**) - Adds workspace-level AI provider routing and BYOK credentials.
- `077_proxy_quarantine_and_sticky_affinity.sql` (**pending**) - Adds proxy quarantine expiration and sticky geo-affinity.
- `077_workspace_auto_recharge_settings.sql` (**pending**) - Adds workspace auto-recharge settings, thresholds, and package selection.
- `078_agency_credit_delegations.sql` (**pending**) - Adds agency credit allocation audit ledger, sub-account quotas, and deadlock-free transfer_agency_credits_safely RPC.
- `078_sender_pod_load_balancing.sql` (**pending**) - Adds sender pod load balancing, fleet failover, and quarantine auditing.
- `079_campaign_roi_certificates.sql` (**pending**) - Adds viral shareable ROI performance certificate table and public lookup RLS.
- `080_agency_billing_statements.sql` (**pending**) - Adds agency multi-client consolidated billing statements, overdraft invoicing, and itemized breakdown tables.
- `081_bayesian_icp_calibration_studio.sql` (**pending**) - Adds is_frozen, weight_multiplier, category, description to icp_signal_weights, creates icp_feedback_events audit ledger, and enables RLS.
- `081_ai_inbox_battlecards_and_deal_stages.sql` (**pending**) - Extends leads with deal_stage, deal_stage_updated_at, deal_estimated_value, last_objection_type, and creates lead_objections audit ledger with RLS.
- `082_social_prewarm_and_omnichannel_cascade.sql` (**pending**) - Adds lead_prewarm_events, omnichannel_fallback_configs, omnichannel_cascade_logs, thought_leadership_posts with RLS.
- `083_bandit_optimizer_and_trigger_radar.sql` (**pending**) - Adds bandit_experiments, copy_variants (Thompson sampling parameters, mutation tracking), trigger_events, indexes, and RLS.
- `084_event_harvester_and_multimodal_voice.sql` (**pending**) - Adds harvested_events, event_attendees, multimodal_assets, indexes, and RLS for event harvesting and voice/video prospecting.
- `085_lead_list_dynamic_segmentation.sql` (**pending**) - Adds JSONB metadata column to lead_lists for dynamic rule AST criteria and auto-enrollment campaign bindings.
- `086_abm_buying_committees_and_multithreading.sql` (**pending**) - Adds target_accounts, account_committee_members, multithread_campaign_runs tables, indexes, and RLS for ABM multithreading and account heat score rollups.
- `087_champion_job_changes_and_deal_revival.sql` (**pending**) - Adds champion_job_changes, warm_intro_paths, and closed_lost_revivals tables, indexes, and RLS for Phase 15 Boomerang & Deal Revival Engine.
- `088_competitive_displacement_and_vendor_takeover.sql` (**pending**) - Adds competitor_displacements, vendor_battlecards tables, indexes, and RLS for Phase 16 Autonomous Competitive Takeover & Tech-Stack Displacement Engine.
- `089_calendar_concierge_and_meeting_booking.sql` (**pending**) - Adds meeting_bookings, rep_calendar_availability tables, indexes, and RLS for Phase 17 Autonomous Executive Calendar Concierge & Frictionless Meeting Booking Engine.
- `090_waterfall_enrichment_cascade.sql` (**pending**) - Adds waterfall_enrichment_runs, vendor_enrichment_configs tables, indexes, and RLS for Phase 18 Clay-Style Multi-Vendor Waterfall Enrichment Engine.
- `091_email_warmup_and_dns_reputation.sql` (**pending**) - Adds warmup_mailboxes, mailbox_dns_audits tables, indexes, and RLS for Phase 19 Peer-to-Peer AI Email Warmup & DNS Reputation Swarm.
- `092_crm_sync_and_deal_attribution.sql` (**pending**) - Adds crm_account_sync_mappings, deal_attributions, and crm_sync_logs tables, indexes, and RLS for Phase 20 Account-Level CRM Bi-Directional Auto-Sync & Real-Time Deal Attribution Engine.
- `093_employee_advocacy_and_viral_pods.sql` (**pending**) - Adds advocacy_pods, advocacy_pod_members, advocacy_post_boosts, and advocacy_engagements tables, indexes, and RLS for Phase 21 Employee Advocacy & Viral LinkedIn Post Booster Pod.

## 🚀 One-Click Master Execution
All pending migrations from 001 through 093, including all foundational infrastructure tables and stages 1 through 41, have been combined into **`999_master_pending_sync.sql`** (2,182 lines, 59 tables, 8 stored procedures, 95 indexes).
This file is fully idempotent (`IF NOT EXISTS`, transaction blocks, `DO $$` guards, RLS enabled across 100% of tables).
When you are ready to apply all schema changes to Supabase:
1. Open your **Supabase Dashboard &rarr; SQL Editor**.
2. Open `backend/migrations/999_master_pending_sync.sql`.
3. Copy all contents, paste into the SQL Editor, and click **Run**.


