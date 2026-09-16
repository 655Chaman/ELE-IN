-- Migration: 016_settings_production.sql

-- Add 2FA policy flag
ALTER TABLE public.workspaces ADD COLUMN require_2fa boolean NOT NULL DEFAULT false;
ALTER TABLE public.workspaces ADD COLUMN status text NOT NULL DEFAULT 'active';
ALTER TABLE public.workspaces ADD COLUMN deletion_requested_at timestamp with time zone;

-- Workspace Invites
CREATE TABLE public.workspace_invites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  email text NOT NULL,
  role public.workspace_member_role NOT NULL DEFAULT 'member',
  invited_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  token text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'pending',  -- pending | accepted | revoked | expired
  expires_at timestamp with time zone NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT uq_pending_invite UNIQUE (workspace_id, email)
);

-- Sending Defaults
CREATE TABLE public.workspace_sending_defaults (
  workspace_id uuid PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
  default_daily_connection_limit integer NOT NULL DEFAULT 20,
  default_daily_message_limit integer NOT NULL DEFAULT 40,
  default_warmup_target_days integer NOT NULL DEFAULT 30,
  default_working_hours_start time NOT NULL DEFAULT '08:00',
  default_working_hours_end time NOT NULL DEFAULT '18:00',
  default_timezone text NOT NULL DEFAULT 'UTC',
  weekend_sending_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Notification Preferences
CREATE TABLE public.notification_preferences (
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  channel text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  PRIMARY KEY (user_id, workspace_id, event_type, channel)
);

-- Audit Log
CREATE TABLE public.audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  actor_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  action text NOT NULL,
  target_type text NOT NULL,
  target_id uuid,
  before_state jsonb,
  after_state jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_workspace_created ON public.audit_log (workspace_id, created_at DESC);

-- Enable RLS
ALTER TABLE public.workspace_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_sending_defaults ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY workspace_invites_ws ON public.workspace_invites FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY workspace_sending_defaults_ws ON public.workspace_sending_defaults FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY notification_preferences_ws ON public.notification_preferences FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));

-- Audit log is readable by workspace members, but typically insert-only from backend service role.
-- For safety, we allow read, but backend usually inserts via service role.
CREATE POLICY audit_log_ws_read ON public.audit_log FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Insert default sending configurations for all existing workspaces
INSERT INTO public.workspace_sending_defaults (workspace_id)
SELECT id FROM public.workspaces
ON CONFLICT DO NOTHING;
