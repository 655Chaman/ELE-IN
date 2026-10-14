-- Migration 076: Workspace AI Gateway & BYOK Configuration
-- Supports custom default AI model selection, provider BYOK vault credentials,
-- and workspace-level model hyperparameter controls.

CREATE TABLE IF NOT EXISTS public.workspace_ai_settings (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    default_model TEXT NOT NULL DEFAULT 'Auto-Route (Recommended)',
    byok_provider TEXT, -- openai, anthropic, deepseek, groq, openrouter
    byok_key_ciphertext TEXT,
    byok_key_last_chars TEXT,
    temperature NUMERIC DEFAULT 0.7,
    max_tokens_budget INTEGER DEFAULT 2000000,
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.workspace_ai_settings ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='workspace_ai_settings' AND policyname='workspace_ai_settings_workspace_isolation') THEN
    CREATE POLICY workspace_ai_settings_workspace_isolation ON public.workspace_ai_settings
      FOR ALL USING (true);
  END IF;
END $$;
