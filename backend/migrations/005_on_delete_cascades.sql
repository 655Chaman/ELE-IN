-- ============================================================
-- Migration 005: A8 - Foreign Key cascades
-- Covers: ON DELETE CASCADE for all FKs referencing workspaces, campaigns, accounts, leads
-- Safe to re-run
-- ============================================================

BEGIN;

-- 1. action_log -> accounts
ALTER TABLE public.action_log DROP CONSTRAINT IF EXISTS action_log_account_id_fkey;
ALTER TABLE public.action_log ADD CONSTRAINT action_log_account_id_fkey 
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

-- 2. messages -> accounts
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_account_id_fkey;
ALTER TABLE public.messages ADD CONSTRAINT messages_account_id_fkey 
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

-- 3. messages -> leads
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_lead_id_fkey;
ALTER TABLE public.messages ADD CONSTRAINT messages_lead_id_fkey 
    FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;

-- 4. approval_queue -> accounts
ALTER TABLE public.approval_queue DROP CONSTRAINT IF EXISTS approval_queue_account_id_fkey;
ALTER TABLE public.approval_queue ADD CONSTRAINT approval_queue_account_id_fkey 
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

-- 5. Fix missing FK in account_daily_action_counts (from migration 003) -> accounts
ALTER TABLE public.account_daily_action_counts DROP CONSTRAINT IF EXISTS account_daily_action_counts_account_id_fkey;
ALTER TABLE public.account_daily_action_counts ADD CONSTRAINT account_daily_action_counts_account_id_fkey 
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

COMMIT;
