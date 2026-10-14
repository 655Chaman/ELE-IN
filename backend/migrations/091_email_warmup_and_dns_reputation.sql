-- Migration 091: Peer-to-Peer AI Email Warmup & DNS Reputation Swarm
-- Description: Creates tables for automated peer-to-peer mailbox warm-up, ramp schedules, SPF/DKIM/DMARC DNS audits, and spam rescue telemetry.
-- Paranoia Framework: Fully idempotent DDL with IF NOT EXISTS, composite indexes, and workspace tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.warmup_mailboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    email_address TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google_workspace' CHECK (provider IN ('google_workspace', 'microsoft_365', 'smtp_imap', 'custom')),
    warmup_status TEXT NOT NULL DEFAULT 'warming' CHECK (warmup_status IN ('warming', 'paused', 'graduated', 'cooling_down')),
    ramp_strategy TEXT NOT NULL DEFAULT 'balanced' CHECK (ramp_strategy IN ('gentle', 'balanced', 'aggressive')),
    current_daily_limit INT NOT NULL DEFAULT 10,
    max_daily_limit INT NOT NULL DEFAULT 40,
    current_ramp_day INT NOT NULL DEFAULT 1,
    target_reply_rate_pct INT NOT NULL DEFAULT 35,
    inbox_placement_rate_pct NUMERIC NOT NULL DEFAULT 98.5,
    health_score INT NOT NULL DEFAULT 94,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.mailbox_dns_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    domain TEXT NOT NULL,
    spf_valid BOOLEAN NOT NULL DEFAULT true,
    spf_record TEXT,
    dkim_valid BOOLEAN NOT NULL DEFAULT true,
    dkim_selector TEXT,
    dmarc_valid BOOLEAN NOT NULL DEFAULT true,
    dmarc_policy TEXT,
    mx_valid BOOLEAN NOT NULL DEFAULT true,
    mx_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    overall_dns_health_score INT NOT NULL DEFAULT 100,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid mailbox query and status monitoring
CREATE INDEX IF NOT EXISTS idx_warmup_mailboxes_ws ON public.warmup_mailboxes(workspace_id, warmup_status);
CREATE INDEX IF NOT EXISTS idx_warmup_mailboxes_email ON public.warmup_mailboxes(workspace_id, email_address);
CREATE INDEX IF NOT EXISTS idx_mailbox_dns_audits_ws ON public.mailbox_dns_audits(workspace_id, domain);

-- Enable Row-Level Security
ALTER TABLE public.warmup_mailboxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mailbox_dns_audits ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'warmup_mailboxes' AND policyname = 'warmup_mailboxes_ws_policy') THEN
        CREATE POLICY warmup_mailboxes_ws_policy ON public.warmup_mailboxes FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'mailbox_dns_audits' AND policyname = 'mailbox_dns_audits_ws_policy') THEN
        CREATE POLICY mailbox_dns_audits_ws_policy ON public.mailbox_dns_audits FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
