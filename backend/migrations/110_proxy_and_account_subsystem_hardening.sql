-- Migration 110: Proxy and Account Subsystem Paranoia Hardening
-- Paranoia Layer 0 & 1:
-- 1. Adds execution_channel to accounts to cleanly partition CLOUD (residential proxy Playwright worker)
--    from EXTENSION (local Chrome extension Voyager worker).
-- 2. Hardens proxies table schema: allows NULL workspace_id for system proxies, widens country_code to VARCHAR(10)
--    for sub-national regional profiles (US-CA, AU-VIC), adds missing provider/secret_ref/last_checked_at columns,
--    and ensures status supports granular failure classifications.

BEGIN;

-- 1. Add execution_channel to accounts table
ALTER TABLE public.accounts 
ADD COLUMN IF NOT EXISTS execution_channel VARCHAR(20) DEFAULT 'CLOUD';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_execution_channel_check'
    ) THEN
        ALTER TABLE public.accounts
        ADD CONSTRAINT accounts_execution_channel_check
        CHECK (execution_channel IN ('CLOUD', 'EXTENSION'));
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_accounts_execution_channel 
ON public.accounts(workspace_id, execution_channel, status);

-- 2. Ensure proxies schema columns and nullability for system-wide pools
DO $$
BEGIN
    -- Allow workspace_id to be NULL for system/shared proxies
    ALTER TABLE public.proxies ALTER COLUMN workspace_id DROP NOT NULL;
EXCEPTION
    WHEN OTHERS THEN NULL;
END $$;

ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'custom';
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS secret_ref TEXT DEFAULT NULL;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS subnet TEXT DEFAULT NULL;

-- 3. Widen country_code to VARCHAR(10) to support sub-national regional routing (e.g. 'US-CA', 'CA-BC')
DO $$
BEGIN
    ALTER TABLE public.proxies ALTER COLUMN country_code TYPE VARCHAR(10);
EXCEPTION
    WHEN OTHERS THEN NULL;
END $$;

-- 4. Convert status to TEXT if it was an ENUM, or widen check constraint to support granular statuses
DO $$
BEGIN
    -- If status is an enum type, convert to TEXT to avoid rigid migration friction
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'proxies' 
          AND column_name = 'status' AND udt_name = 'proxy_status'
    ) THEN
        ALTER TABLE public.proxies ALTER COLUMN status TYPE TEXT USING status::TEXT;
    END IF;
EXCEPTION
    WHEN OTHERS THEN NULL;
END $$;

-- Ensure default status is 'healthy'
ALTER TABLE public.proxies ALTER COLUMN status SET DEFAULT 'healthy';

-- 5. Create index on proxies(status) for auto_cooling and health check crons
CREATE INDEX IF NOT EXISTS idx_proxies_status ON public.proxies(status);

COMMIT;
