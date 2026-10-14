-- Migration 077: Workspace Credit Auto-Recharge & In-Flight Overdraft Replenishment
-- Paranoia Framework: Layer 0 & Layer 1
-- Enables automated credit top-ups when balance drops below a threshold,
-- bounded by a monthly circuit-breaker cap and debounce cooldown.

CREATE TABLE IF NOT EXISTS public.workspace_auto_recharge_settings (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT false,
    threshold_credits INTEGER NOT NULL DEFAULT 100,
    recharge_package_id TEXT NOT NULL DEFAULT 'credits_1000',
    max_monthly_recharges INTEGER NOT NULL DEFAULT 5,
    recharges_this_month INTEGER NOT NULL DEFAULT 0,
    last_recharged_at TIMESTAMPTZ,
    last_reset_month TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workspace_auto_recharge_enabled ON public.workspace_auto_recharge_settings(enabled);

ALTER TABLE public.workspace_auto_recharge_settings ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'workspace_auto_recharge_settings' 
    AND policyname = 'workspace_auto_recharge_settings_isolation'
  ) THEN
    CREATE POLICY workspace_auto_recharge_settings_isolation ON public.workspace_auto_recharge_settings
      FOR ALL USING (true);
  END IF;
END $$;
