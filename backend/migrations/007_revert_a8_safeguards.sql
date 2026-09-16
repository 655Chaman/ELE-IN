-- ============================================================
-- Migration 007: Revert A8 overreach on Audit tables
-- Covers: Restoring SET NULL for account_id/lead_id on 
--         action_log, messages, and approval_queue to preserve history
-- Safe to re-run
-- ============================================================

BEGIN;

-- 1. action_log -> accounts
ALTER TABLE public.action_log DROP CONSTRAINT IF EXISTS action_log_account_id_fkey;
ALTER TABLE public.action_log ADD CONSTRAINT action_log_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;

-- 2. messages -> accounts
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_account_id_fkey;
ALTER TABLE public.messages ADD CONSTRAINT messages_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;

-- 3. messages -> leads
ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_lead_id_fkey;
ALTER TABLE public.messages ADD CONSTRAINT messages_lead_id_fkey
    FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE SET NULL;

-- 4. approval_queue -> accounts
ALTER TABLE public.approval_queue DROP CONSTRAINT IF EXISTS approval_queue_account_id_fkey;
ALTER TABLE public.approval_queue ADD CONSTRAINT approval_queue_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;

COMMIT;
