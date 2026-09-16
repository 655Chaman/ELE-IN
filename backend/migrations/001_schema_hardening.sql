-- =====================================================================
-- Migration 001: Schema hardening fixes (idempotent version)
-- Covers: is_active drift bug, missing unique constraints, missing
-- query-path indexes.
-- Safe to re-run — all statements use IF NOT EXISTS / DO NOTHING guards.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. accounts.is_active: replace the one-time DEFAULT with a real
--    generated column so it can never drift from `status`.
-- ---------------------------------------------------------------------
ALTER TABLE public.accounts DROP COLUMN IF EXISTS is_active;

ALTER TABLE public.accounts
  ADD COLUMN is_active boolean
  GENERATED ALWAYS AS (status = 'ACTIVE'::account_status) STORED;

-- ---------------------------------------------------------------------
-- 2. Uniqueness constraints (guarded so re-runs are safe)
-- ---------------------------------------------------------------------

DO $$ BEGIN
  -- 2a. workspace_members: one membership row per user per workspace
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'workspace_members_workspace_user_uniq'
  ) THEN
    ALTER TABLE public.workspace_members
      ADD CONSTRAINT workspace_members_workspace_user_uniq
      UNIQUE (workspace_id, user_id);
  END IF;
END $$;

DO $$ BEGIN
  -- 2b. daily_campaign_stats: one row per campaign per day
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'daily_campaign_stats_campaign_date_uniq'
  ) THEN
    ALTER TABLE public.daily_campaign_stats
      ADD CONSTRAINT daily_campaign_stats_campaign_date_uniq
      UNIQUE (campaign_id, stat_date);
  END IF;
END $$;

-- 2c. leads: prevent duplicate LinkedIn URL per workspace
CREATE UNIQUE INDEX IF NOT EXISTS leads_workspace_linkedin_url_uniq
  ON public.leads (workspace_id, linkedin_url);

-- ---------------------------------------------------------------------
-- 3. Query-path indexes (all IF NOT EXISTS — safe to re-run)
-- ---------------------------------------------------------------------

-- 3a. Scheduler core: lead_states due to run now
CREATE INDEX IF NOT EXISTS lead_states_status_next_run_at_idx
  ON public.lead_states (status, next_run_at);

-- 3b. Account sender picker: workspace + health status
CREATE INDEX IF NOT EXISTS accounts_workspace_status_idx
  ON public.accounts (workspace_id, status);

-- 3c. Approval queue filtered per workspace
CREATE INDEX IF NOT EXISTS approval_queue_workspace_status_idx
  ON public.approval_queue (workspace_id, status);

-- 3d. Action log per account, most recent first
CREATE INDEX IF NOT EXISTS action_log_account_executed_at_idx
  ON public.action_log (account_id, executed_at DESC);

-- 3e. Message thread view: by lead, most recent first
CREATE INDEX IF NOT EXISTS messages_lead_created_at_idx
  ON public.messages (lead_id, created_at DESC);

COMMIT;
