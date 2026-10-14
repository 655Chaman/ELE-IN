BEGIN;

CREATE TABLE IF NOT EXISTS public.icp_signal_weights (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    signal_name text NOT NULL,
    prior_alpha integer NOT NULL DEFAULT 2,
    prior_beta integer NOT NULL DEFAULT 2,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT icp_signal_weights_workspace_signal_key UNIQUE (workspace_id, signal_name)
);

CREATE INDEX IF NOT EXISTS idx_icp_signal_weights_workspace ON public.icp_signal_weights(workspace_id);

-- RPC for ATOMIC updates of Bayesian priors (fixes read-modify-write race condition)
CREATE OR REPLACE FUNCTION public.record_bayesian_icp_outcome(
    p_workspace_id uuid,
    p_signal_name text,
    p_outcome text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_alpha integer;
    v_beta integer;
BEGIN
    INSERT INTO public.icp_signal_weights (workspace_id, signal_name, prior_alpha, prior_beta)
    VALUES (p_workspace_id, p_signal_name, 2, 2)
    ON CONFLICT (workspace_id, signal_name) DO NOTHING;

    SELECT prior_alpha, prior_beta INTO v_alpha, v_beta
    FROM public.icp_signal_weights
    WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;

    -- Damping: when total observations reach 200, scale down to maintain responsiveness
    IF (COALESCE(v_alpha, 2) + COALESCE(v_beta, 2)) >= 200 THEN
        UPDATE public.icp_signal_weights
        SET prior_alpha = GREATEST(2, (prior_alpha * 0.5)::integer),
            prior_beta = GREATEST(2, (prior_beta * 0.5)::integer),
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    END IF;

    IF p_outcome = 'won' THEN
        UPDATE public.icp_signal_weights
        SET prior_alpha = prior_alpha + 1,
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    ELSIF p_outcome = 'lost' THEN
        UPDATE public.icp_signal_weights
        SET prior_beta = prior_beta + 1,
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    END IF;
END;
$$;

COMMIT;
