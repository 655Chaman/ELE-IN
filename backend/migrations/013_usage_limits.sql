-- ==============================================================================
-- MIGRATION: 013_usage_limits
-- PARANOIA FRAMEWORK: Layer 0 & Layer 1
-- Adds atomic usage tracking to prevent "Financial Ruin via Infinite Consumption"
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.workspace_usage (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    ai_requests_this_month INT DEFAULT 0 NOT NULL,
    leads_scraped_this_month INT DEFAULT 0 NOT NULL,
    billing_tier TEXT DEFAULT 'free' NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc', now()) NOT NULL
);

-- Paranoia framework indexing for FK
CREATE INDEX IF NOT EXISTS idx_workspace_usage_workspace_id ON public.workspace_usage(workspace_id);

-- Layer 1: Atomic increment to prevent race conditions during high concurrency.
-- This guarantees we never overshoot usage limits.
CREATE OR REPLACE FUNCTION public.increment_usage(p_workspace_id UUID, p_type TEXT, p_amount INT, p_limit INT)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_current INT;
    v_new INT;
BEGIN
    -- Atomically lock the row (or insert if missing)
    -- We use an UPSERT (INSERT ON CONFLICT) returning the current state
    INSERT INTO public.workspace_usage (workspace_id)
    VALUES (p_workspace_id)
    ON CONFLICT (workspace_id) DO NOTHING;
    
    -- Now lock it
    SELECT ai_requests_this_month, leads_scraped_this_month 
    INTO v_current, v_new  -- temporarily use v_new as second variable
    FROM public.workspace_usage
    WHERE workspace_id = p_workspace_id
    FOR UPDATE;

    IF p_type = 'ai' THEN
        v_current := (SELECT ai_requests_this_month FROM public.workspace_usage WHERE workspace_id = p_workspace_id);
        IF v_current + p_amount > p_limit THEN
            RAISE EXCEPTION 'UsageLimitExceededError: AI limit % exceeded by %', p_limit, (v_current + p_amount);
        END IF;
        
        UPDATE public.workspace_usage
        SET ai_requests_this_month = ai_requests_this_month + p_amount,
            updated_at = timezone('utc', now())
        WHERE workspace_id = p_workspace_id;
        
    ELSIF p_type = 'leads' THEN
        v_current := (SELECT leads_scraped_this_month FROM public.workspace_usage WHERE workspace_id = p_workspace_id);
        IF v_current + p_amount > p_limit THEN
            RAISE EXCEPTION 'UsageLimitExceededError: Leads limit % exceeded by %', p_limit, (v_current + p_amount);
        END IF;
        
        UPDATE public.workspace_usage
        SET leads_scraped_this_month = leads_scraped_this_month + p_amount,
            updated_at = timezone('utc', now())
        WHERE workspace_id = p_workspace_id;
        
    ELSE
        RAISE EXCEPTION 'Unknown usage type: %', p_type;
    END IF;
END;
$$;
