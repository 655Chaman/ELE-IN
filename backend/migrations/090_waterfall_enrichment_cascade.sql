-- Migration 090: Clay-Style Multi-Vendor Waterfall Enrichment Engine
-- Description: Creates tables for multi-vendor cascade enrichment runs, provider priority chains, catch-all deliverability audit, and credit usage telemetry.
-- Paranoia Framework: Idempotent DDL with IF NOT EXISTS, composite indexes, and workspace tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.waterfall_enrichment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    lead_name TEXT NOT NULL,
    company_domain TEXT NOT NULL,
    waterfall_sequence JSONB NOT NULL DEFAULT '["internal_cache", "apollo", "hunter", "smtp_handshake"]'::jsonb,
    resolved_email TEXT,
    resolved_vendor TEXT,
    deliverability_status TEXT NOT NULL DEFAULT 'valid' CHECK (deliverability_status IN ('valid', 'risky_catchall', 'invalid', 'unresolved')),
    confidence_score INT NOT NULL DEFAULT 95,
    vendors_queried JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_cost_credits NUMERIC NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.vendor_enrichment_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    vendor_slug TEXT NOT NULL,
    vendor_display_name TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    priority_order INT NOT NULL DEFAULT 1,
    cost_per_lookup_credits NUMERIC NOT NULL DEFAULT 1.0,
    api_key_configured BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid query and audit
CREATE INDEX IF NOT EXISTS idx_waterfall_enrichment_ws ON public.waterfall_enrichment_runs(workspace_id, deliverability_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_waterfall_domain ON public.waterfall_enrichment_runs(workspace_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_vendor_configs_ws ON public.vendor_enrichment_configs(workspace_id, priority_order ASC);

-- Enable Row-Level Security
ALTER TABLE public.waterfall_enrichment_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_enrichment_configs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'waterfall_enrichment_runs' AND policyname = 'waterfall_enrichment_runs_ws_policy') THEN
        CREATE POLICY waterfall_enrichment_runs_ws_policy ON public.waterfall_enrichment_runs FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'vendor_enrichment_configs' AND policyname = 'vendor_enrichment_configs_ws_policy') THEN
        CREATE POLICY vendor_enrichment_configs_ws_policy ON public.vendor_enrichment_configs FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
