BEGIN;

-- Add session_locked_until to accounts if not exists
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='session_locked_until') THEN
    ALTER TABLE public.accounts ADD COLUMN session_locked_until timestamptz;
  END IF;
END $$;

-- account_health_checks
CREATE TABLE IF NOT EXISTS public.account_health_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
  check_type text NOT NULL CHECK (check_type IN ('session_valid', 'cookie_freshness', 'profile_reachable', 'restriction_detected')),
  result text NOT NULL CHECK (result IN ('pass', 'warn', 'fail')),
  detail jsonb NOT NULL DEFAULT '{}',
  checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_account_health_checks_account_time ON public.account_health_checks (account_id, checked_at DESC);

ALTER TABLE public.account_health_checks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_health_checks_ws ON public.account_health_checks;
CREATE POLICY account_health_checks_ws
    ON public.account_health_checks FOR ALL
    USING (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())))
    WITH CHECK (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())));

-- account_reconnect_requests
CREATE TABLE IF NOT EXISTS public.account_reconnect_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
  requested_by uuid NOT NULL REFERENCES auth.users(id),
  token text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'expired')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reconnect_requests_token ON public.account_reconnect_requests (token) WHERE status = 'pending';

ALTER TABLE public.account_reconnect_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_reconnect_requests_ws ON public.account_reconnect_requests;
CREATE POLICY account_reconnect_requests_ws
    ON public.account_reconnect_requests FOR ALL
    USING (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())))
    WITH CHECK (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())));

-- account_connection_sessions
CREATE TABLE IF NOT EXISTS public.account_connection_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  initiated_by uuid NOT NULL REFERENCES auth.users(id),
  token text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'awaiting_extension' CHECK (status IN ('awaiting_extension', 'completed', 'expired')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_connection_sessions_token ON public.account_connection_sessions (token) WHERE status = 'awaiting_extension';

ALTER TABLE public.account_connection_sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_connection_sessions_ws ON public.account_connection_sessions;
CREATE POLICY account_connection_sessions_ws
    ON public.account_connection_sessions FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));

-- account_tags
CREATE TABLE IF NOT EXISTS public.account_tags (
  account_id uuid NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
  tag text NOT NULL CHECK (length(tag) > 0 AND length(tag) <= 50),
  PRIMARY KEY (account_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_account_tags_tag ON public.account_tags (tag);

ALTER TABLE public.account_tags ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_tags_ws ON public.account_tags;
CREATE POLICY account_tags_ws
    ON public.account_tags FOR ALL
    USING (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())))
    WITH CHECK (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())));

-- cleanup function
CREATE OR REPLACE FUNCTION public.cleanup_expired_account_sessions()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  UPDATE public.account_connection_sessions SET status = 'expired'
    WHERE status = 'awaiting_extension' AND expires_at < now();
  UPDATE public.account_reconnect_requests SET status = 'expired'
    WHERE status = 'pending' AND expires_at < now();
END;
$$;

COMMIT;
