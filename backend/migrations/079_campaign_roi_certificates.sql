-- Migration 079: Viral Shareable Campaign Performance Card & ROI Certificate Engine
-- Designed under the Three-Layer Logic Architecture (Paranoia Framework)

CREATE TABLE IF NOT EXISTS public.campaign_roi_certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    verification_token TEXT NOT NULL,
    issuer_signature TEXT NOT NULL,
    badge_tier TEXT NOT NULL DEFAULT 'SILVER', -- 'DIAMOND', 'PLATINUM', 'GOLD', 'SILVER'
    metrics_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    mask_pii BOOLEAN NOT NULL DEFAULT TRUE,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_campaign_roi_certificate_token UNIQUE (verification_token)
);

CREATE INDEX IF NOT EXISTS idx_roi_cert_token ON public.campaign_roi_certificates(verification_token);
CREATE INDEX IF NOT EXISTS idx_roi_cert_ws_campaign ON public.campaign_roi_certificates(workspace_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_roi_cert_tier ON public.campaign_roi_certificates(badge_tier);

-- Enable RLS
ALTER TABLE public.campaign_roi_certificates ENABLE ROW LEVEL SECURITY;

-- Tenant isolation policy for workspace users
DROP POLICY IF EXISTS campaign_roi_cert_workspace_isolation ON public.campaign_roi_certificates;
CREATE POLICY campaign_roi_cert_workspace_isolation ON public.campaign_roi_certificates
    FOR ALL
    USING (workspace_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'workspace_id')::UUID)
    WITH CHECK (workspace_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'workspace_id')::UUID);

-- Public read policy for public certificates (unauthenticated verification lookup)
DROP POLICY IF EXISTS campaign_roi_cert_public_read ON public.campaign_roi_certificates;
CREATE POLICY campaign_roi_cert_public_read ON public.campaign_roi_certificates
    FOR SELECT
    USING (is_public = TRUE);
