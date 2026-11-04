-- Migration 115: Invoices and Billing Hardening
-- Pillar 8: Billing, Metering & Production Reliability

CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    invoice_number TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    payment_id TEXT,
    base_amount NUMERIC(12,2) NOT NULL,
    tax_amount NUMERIC(12,2) NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    tax_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    customer_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'PAID',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_ws_time 
    ON invoices(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_payment_id 
    ON invoices(provider, payment_id);

-- Enable RLS
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'invoices' AND policyname = 'invoices_tenant_isolation'
    ) THEN
        CREATE POLICY invoices_tenant_isolation ON invoices
            FOR ALL
            USING (workspace_id IN (SELECT get_user_workspace_ids()))
            WITH CHECK (workspace_id IN (SELECT get_user_workspace_ids()));
    END IF;
END $$;
