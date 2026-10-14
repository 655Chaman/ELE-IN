-- Migration 092: Account-Level CRM Bi-Directional Auto-Sync & Real-Time Deal Attribution Engine
-- Description: Creates tables for bi-directional CRM account sync, multi-touch deal revenue attribution, and echo-loop audit ledgers.
-- Paranoia Framework: Fully idempotent DDL with IF NOT EXISTS, composite indexes, and workspace tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.crm_account_sync_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    domain TEXT NOT NULL,
    company_name TEXT NOT NULL,
    crm_provider TEXT NOT NULL DEFAULT 'hubspot' CHECK (crm_provider IN ('hubspot', 'salesforce', 'pipedrive', 'zoho', 'custom')),
    crm_company_id TEXT NOT NULL,
    lifecycle_stage TEXT NOT NULL DEFAULT 'lead' CHECK (lifecycle_stage IN ('subscriber', 'lead', 'marketingqualifiedlead', 'salesqualifiedlead', 'opportunity', 'customer', 'evangelist', 'other')),
    sync_status TEXT NOT NULL DEFAULT 'synced' CHECK (sync_status IN ('synced', 'pending', 'error', 'paused')),
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.deal_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    deal_id TEXT NOT NULL,
    deal_name TEXT NOT NULL,
    deal_amount NUMERIC NOT NULL DEFAULT 0.0,
    pipeline_stage TEXT NOT NULL DEFAULT 'closed_won',
    attribution_model TEXT NOT NULL DEFAULT 'w_shaped' CHECK (attribution_model IN ('first_touch', 'last_touch', 'linear', 'w_shaped')),
    touchpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    touchpoint_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    attributed_pipeline_arr NUMERIC NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.crm_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    direction TEXT NOT NULL DEFAULT 'inbound_from_crm' CHECK (direction IN ('inbound_from_crm', 'outbound_to_crm')),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'skipped_echo', 'failed')),
    payload_hash TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid sync lookups, deduplication, and telemetry
CREATE INDEX IF NOT EXISTS idx_crm_accounts_ws ON public.crm_account_sync_mappings(workspace_id, domain);
CREATE INDEX IF NOT EXISTS idx_crm_accounts_crm_id ON public.crm_account_sync_mappings(workspace_id, crm_company_id);
CREATE INDEX IF NOT EXISTS idx_deal_attributions_ws ON public.deal_attributions(workspace_id, deal_id);
CREATE INDEX IF NOT EXISTS idx_crm_sync_logs_ws ON public.crm_sync_logs(workspace_id, created_at DESC);

-- Enable Row-Level Security
ALTER TABLE public.crm_account_sync_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deal_attributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_sync_logs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'crm_account_sync_mappings' AND policyname = 'crm_account_sync_mappings_ws_policy') THEN
        CREATE POLICY crm_account_sync_mappings_ws_policy ON public.crm_account_sync_mappings FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'deal_attributions' AND policyname = 'deal_attributions_ws_policy') THEN
        CREATE POLICY deal_attributions_ws_policy ON public.deal_attributions FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'crm_sync_logs' AND policyname = 'crm_sync_logs_ws_policy') THEN
        CREATE POLICY crm_sync_logs_ws_policy ON public.crm_sync_logs FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
