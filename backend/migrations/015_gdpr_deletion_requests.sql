-- 015_gdpr_deletion_requests.sql
CREATE TYPE public.gdpr_deletion_status AS ENUM ('requested', 'in_progress', 'completed', 'failed');

CREATE TABLE public.gdpr_deletion_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL, -- Do not reference workspaces(id) with a strict FK since the workspace gets deleted
    requested_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    status public.gdpr_deletion_status NOT NULL DEFAULT 'requested',
    error_log TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gdpr_requests_status ON public.gdpr_deletion_requests(status);
