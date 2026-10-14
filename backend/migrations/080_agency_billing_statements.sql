-- Migration 080: Agency Consolidated Invoicing and Billing Statements
-- Adds tables and indexes for consolidated agency multi-client billing statements, overdraft invoicing, and itemized fee tracking.

CREATE TABLE IF NOT EXISTS public.agency_billing_statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    client_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL, -- NULL indicates agency-wide multi-client consolidated roll-up
    invoice_number VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'issued', 'paid', 'void')),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    subtotal_cents BIGINT NOT NULL DEFAULT 0,
    markup_cents BIGINT NOT NULL DEFAULT 0,
    tax_cents BIGINT NOT NULL DEFAULT 0,
    total_cents BIGINT NOT NULL DEFAULT 0,
    breakdown_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agency_billing_statements_agency_id 
    ON public.agency_billing_statements(agency_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agency_billing_statements_client_period 
    ON public.agency_billing_statements(agency_id, client_workspace_id, period_start, period_end);

CREATE INDEX IF NOT EXISTS idx_agency_billing_statements_status 
    ON public.agency_billing_statements(agency_id, status);
