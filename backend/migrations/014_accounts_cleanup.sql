BEGIN;

-- 1. Drop the duplicate legacy usage table (already deprecated but never physically dropped)
DROP TABLE IF EXISTS public.account_daily_usage CASCADE;

-- 2. Drop the generated daily_action_cap (since try_consume_daily_action computes it manually to properly split limits)
ALTER TABLE public.accounts DROP COLUMN IF EXISTS daily_action_cap CASCADE;

-- 3. Drop the unused cookie_secret_ref to completely remove the "dual secret storage" confusion
ALTER TABLE public.accounts DROP COLUMN IF EXISTS cookie_secret_ref CASCADE;

-- 4. Drop the old aggregate view that relied on account_daily_usage
DROP VIEW IF EXISTS public.vw_account_action_usage CASCADE;

COMMIT;
