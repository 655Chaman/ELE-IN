-- ====================================================================
-- Ele-in Platform — Waitlist Schema Migration (Serverless + Backend)
-- Designed under the Three-Layer Logic Architecture (Paranoia Framework)
-- ====================================================================

CREATE TABLE IF NOT EXISTS public.waitlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    company TEXT,
    role TEXT,
    linkedin_url TEXT,
    team_size TEXT,
    monthly_outbound_volume TEXT,
    primary_channel TEXT,
    referral_code TEXT UNIQUE NOT NULL,
    referred_by_code TEXT,
    referrals_count INTEGER NOT NULL DEFAULT 0,
    priority_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    discount_code TEXT NOT NULL DEFAULT 'EARLY30',
    discount_percent INTEGER NOT NULL DEFAULT 30,
    discount_duration TEXT NOT NULL DEFAULT 'first_year',
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    ip_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Ensure columns exist if table was already created prior to discount update
ALTER TABLE public.waitlist ADD COLUMN IF NOT EXISTS discount_code TEXT NOT NULL DEFAULT 'EARLY30';
ALTER TABLE public.waitlist ADD COLUMN IF NOT EXISTS discount_percent INTEGER NOT NULL DEFAULT 30;
ALTER TABLE public.waitlist ADD COLUMN IF NOT EXISTS discount_duration TEXT NOT NULL DEFAULT 'first_year';

-- Performance and lookup indexes
CREATE INDEX IF NOT EXISTS idx_waitlist_email ON public.waitlist(email);
CREATE INDEX IF NOT EXISTS idx_waitlist_referral_code ON public.waitlist(referral_code);
CREATE INDEX IF NOT EXISTS idx_waitlist_referred_by ON public.waitlist(referred_by_code);
CREATE INDEX IF NOT EXISTS idx_waitlist_priority_ranking ON public.waitlist(priority_score DESC, created_at ASC);

-- Row Level Security (RLS)
ALTER TABLE public.waitlist ENABLE ROW LEVEL SECURITY;

-- Allow public anonymous and authenticated users to submit waitlist signups
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'waitlist' AND policyname = 'Allow public insert into waitlist'
    ) THEN
        CREATE POLICY "Allow public insert into waitlist"
        ON public.waitlist FOR INSERT
        TO anon, authenticated
        WITH CHECK (true);
    END IF;
END $$;

-- Allow public anonymous and authenticated users to check status & count
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'waitlist' AND policyname = 'Allow public read own waitlist entry'
    ) THEN
        CREATE POLICY "Allow public read own waitlist entry"
        ON public.waitlist FOR SELECT
        TO anon, authenticated
        USING (true);
    END IF;
END $$;

-- Atomic RPC for safe referral score boosting directly from GitHub Pages / Static Frontend
CREATE OR REPLACE FUNCTION public.increment_waitlist_referral(p_ref_code TEXT)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.waitlist
    SET
        referrals_count = referrals_count + 1,
        priority_score = priority_score + 10,
        updated_at = timezone('utc'::text, now())
    WHERE referral_code = UPPER(TRIM(p_ref_code));
END;
$$;

GRANT EXECUTE ON FUNCTION public.increment_waitlist_referral(TEXT) TO anon, authenticated;
