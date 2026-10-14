-- Migration 088: Autonomous Competitive Takeover & Tech-Stack Displacement Engine
-- Description: Creates tables for tracking competitor incumbent installations, renewal window countdowns, displacement vulnerability scoring, and vendor battlecards.
-- Paranoia Framework: Fully idempotent DDL with IF NOT EXISTS, composite indexes, and tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.competitor_displacements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    target_company TEXT NOT NULL,
    domain TEXT NOT NULL,
    target_contact_name TEXT NOT NULL,
    target_contact_title TEXT NOT NULL,
    incumbent_vendor TEXT NOT NULL DEFAULT 'apollo' CHECK (incumbent_vendor IN ('apollo', 'outreach', 'salesloft', 'lemlist', 'expandi', 'heyreach', 'other')),
    seat_count INT NOT NULL DEFAULT 10,
    contract_renewal_days INT NOT NULL DEFAULT 75,
    displacement_vulnerability_score INT NOT NULL DEFAULT 82,
    annual_potential_savings NUMERIC NOT NULL DEFAULT 14400.0,
    generated_displacement_copy TEXT,
    status TEXT NOT NULL DEFAULT 'radar_detected' CHECK (status IN ('radar_detected', 'displacement_pitched', 'migration_evaluating', 'displaced_won')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.vendor_battlecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    vendor_slug TEXT NOT NULL,
    vendor_display_name TEXT NOT NULL,
    primary_vulnerability TEXT NOT NULL,
    elein_killer_advantage TEXT NOT NULL,
    contract_buyout_offer TEXT NOT NULL,
    battlecard_pitch TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid querying
CREATE INDEX IF NOT EXISTS idx_competitor_displacements_ws ON public.competitor_displacements(workspace_id, displacement_vulnerability_score DESC);
CREATE INDEX IF NOT EXISTS idx_vendor_battlecards_ws ON public.vendor_battlecards(workspace_id, vendor_slug);

-- Enable Row-Level Security
ALTER TABLE public.competitor_displacements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_battlecards ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'competitor_displacements' AND policyname = 'competitor_displacements_ws_policy') THEN
        CREATE POLICY competitor_displacements_ws_policy ON public.competitor_displacements FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'vendor_battlecards' AND policyname = 'vendor_battlecards_ws_policy') THEN
        CREATE POLICY vendor_battlecards_ws_policy ON public.vendor_battlecards FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
