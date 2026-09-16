BEGIN;

CREATE TABLE IF NOT EXISTS public.account_limit_overrides (
    account_id uuid REFERENCES public.accounts(id) ON DELETE CASCADE,
    action_type text NOT NULL,
    custom_limit integer NOT NULL,
    expires_at timestamptz,
    created_at timestamptz DEFAULT now(),
    PRIMARY KEY (account_id, action_type)
);

ALTER TABLE public.account_limit_overrides ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "account_limit_overrides_ws" ON public.account_limit_overrides
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.accounts a 
      WHERE a.id = account_limit_overrides.account_id
        AND a.workspace_id = ANY(public.my_workspace_ids())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.accounts a 
      WHERE a.id = account_limit_overrides.account_id
        AND a.workspace_id = ANY(public.my_workspace_ids())
    )
  );

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'account_limit_overrides' AND policyname = 'Users can access overrides for their workspaces'
    ) THEN
        CREATE POLICY "Users can access overrides for their workspaces"
            ON public.account_limit_overrides
            FOR ALL
            USING (
                account_id IN (
                    SELECT id FROM public.accounts WHERE workspace_id IN (
                        SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
                    )
                )
            )
            WITH CHECK (
                account_id IN (
                    SELECT id FROM public.accounts WHERE workspace_id IN (
                        SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
                    )
                )
            );
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.get_account_action_limit(p_account_id uuid, p_action_type text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_override_limit integer;
    v_global_limit integer;
    v_is_warmup boolean;
    v_warmup_start_date timestamptz;
    v_warmup_limit integer;
BEGIN
    -- Logic Step 1: Look for an active override
    SELECT custom_limit INTO v_override_limit
    FROM public.account_limit_overrides
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND (expires_at IS NULL OR expires_at > now());

    IF v_override_limit IS NOT NULL THEN
        RETURN v_override_limit;
    END IF;

    -- Logic Step 2: Fetch global max
    SELECT daily_limit INTO v_global_limit
    FROM public.action_type_limits
    WHERE action_type = p_action_type;

    IF v_global_limit IS NULL THEN
        RETURN 0;
    END IF;

    -- Logic Step 3: Check is_warmup
    SELECT is_warmup, warmup_start_date INTO v_is_warmup, v_warmup_start_date
    FROM public.accounts
    WHERE id = p_account_id;

    IF v_is_warmup = true AND p_action_type IN ('connection_request', 'message', 'inmail') THEN
        v_warmup_limit := 15 + ( GREATEST(0, (CURRENT_DATE - warmup_start_date::date)) / 3 ) * 5;
        RETURN LEAST(v_warmup_limit, v_global_limit);
    END IF;

    RETURN v_global_limit;
END;
$$;

ALTER TABLE public.accounts 
DROP COLUMN IF EXISTS daily_action_cap;

COMMIT;
