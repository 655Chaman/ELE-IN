-- Migration 108: Accounts Subsystem Engine & Security Hardening
-- Paranoia Layers 0, 1, 2:
-- 1. Seed missing 'event_invite' into action_type_limits (prevents orchestrator FK crash)
-- 2. Expand account_health_checks constraints for auto_heal, proxy_availability, session_renewed, restriction_signals, and challenge
-- 3. Update proxies RLS to allow authenticated users to select system shared proxies (workspace_id IS NULL)

BEGIN;

-- 1. Seed missing 'event_invite' into action_type_limits
INSERT INTO public.action_type_limits (action_type, daily_limit, tier, description)
VALUES ('event_invite', 20, 2, 'LinkedIn Event Invitation')
ON CONFLICT (action_type) DO UPDATE
SET daily_limit = EXCLUDED.daily_limit,
    description = EXCLUDED.description;

-- 2. Expand account_health_checks check constraints
DO $$
DECLARE
    r RECORD;
BEGIN
    -- Drop existing check constraints on check_type and result if any
    FOR r IN (
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.account_health_checks'::regclass
          AND contype = 'c'
    ) LOOP
        EXECUTE 'ALTER TABLE public.account_health_checks DROP CONSTRAINT IF EXISTS ' || quote_ident(r.conname);
    END LOOP;
END $$;

ALTER TABLE public.account_health_checks
    ADD CONSTRAINT account_health_checks_check_type_check
    CHECK (check_type IN (
        'session_valid',
        'cookie_freshness',
        'profile_reachable',
        'restriction_detected',
        'restriction_signals',
        'decryption',
        'proxy_availability',
        'auto_heal',
        'session_renewed',
        'health_check'
    ));

ALTER TABLE public.account_health_checks
    ADD CONSTRAINT account_health_checks_result_check
    CHECK (result IN ('pass', 'warn', 'fail', 'challenge', 'degraded', 'healthy', 'unhealthy'));

-- 3. Proxies RLS update: Allow SELECT of system/shared proxies (workspace_id IS NULL) for authenticated users
DO $$
BEGIN
    DROP POLICY IF EXISTS "proxies_system_read_policy" ON public.proxies;
    CREATE POLICY "proxies_system_read_policy" ON public.proxies
        FOR SELECT
        USING (workspace_id IS NULL);
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

COMMIT;
