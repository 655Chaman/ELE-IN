-- Migration 081: Bayesian ICP Calibration Studio & Adaptive Feedback Loop
-- Designed under the Three-Layer Logic Architecture (Paranoia Framework)

BEGIN;

-- 1. Extend icp_signal_weights with calibration controls and human freeze locks
ALTER TABLE public.icp_signal_weights 
    ADD COLUMN IF NOT EXISTS is_frozen BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS weight_multiplier FLOAT DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'FIRMOGRAPHIC',
    ADD COLUMN IF NOT EXISTS description TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_icp_weights_frozen ON public.icp_signal_weights(workspace_id, is_frozen);

-- 2. Create icp_feedback_events audit ledger for live adaptive feedback loop
CREATE TABLE IF NOT EXISTS public.icp_feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL, -- 'POSITIVE_REPLY', 'MEETING_BOOKED', 'CONNECTION_ACCEPTED', 'GHOSTED', 'MANUAL_OVERRIDE', 'RECALIBRATION', 'RESET_ALL'
    signals_affected JSONB NOT NULL DEFAULT '[]'::jsonb,
    score_before INT DEFAULT NULL,
    score_after INT DEFAULT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_icp_events_workspace_created ON public.icp_feedback_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_icp_events_type ON public.icp_feedback_events(workspace_id, event_type);

-- Enable RLS
ALTER TABLE public.icp_feedback_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'icp_feedback_events' 
    AND policyname = 'icp_feedback_events_isolation'
  ) THEN
    CREATE POLICY icp_feedback_events_isolation ON public.icp_feedback_events
      FOR ALL USING (true);
  END IF;
END $$;

COMMIT;
