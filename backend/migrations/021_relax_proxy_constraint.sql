BEGIN;

-- Drop the overly strict proxy constraint so agencies can intentionally share proxies across their own accounts
DROP INDEX IF EXISTS public.uq_proxy_single_account CASCADE;

COMMIT;
