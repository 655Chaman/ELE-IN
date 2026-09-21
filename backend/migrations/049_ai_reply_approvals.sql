-- Migration 049: Phase 3 Confidence-Gated Auto-Send

-- 1. Add threshold config to workspaces
ALTER TABLE public.workspaces 
ADD COLUMN IF NOT EXISTS ai_reply_confidence_threshold FLOAT DEFAULT 0.65;

-- 2. Add awaiting_approval status to campaign execution states
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'awaiting_approval';

-- 3. Create the approvals table
CREATE TABLE IF NOT EXISTS public.ai_reply_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES public.leads(id) ON DELETE CASCADE,
    enrollment_id UUID REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE,
    execution_state_id UUID REFERENCES public.campaign_execution_states(id) ON DELETE CASCADE,
    generated_reply TEXT NOT NULL,
    retrieval_score FLOAT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected, expired
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_reply_approvals_workspace ON public.ai_reply_approvals(workspace_id);
CREATE INDEX IF NOT EXISTS idx_ai_reply_approvals_status ON public.ai_reply_approvals(status);
