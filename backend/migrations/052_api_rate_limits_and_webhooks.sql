-- 1. Token Bucket Rate Limiting Table
CREATE TABLE IF NOT EXISTS public.api_rate_limits_window (
    api_key_id uuid REFERENCES public.api_keys(id) ON DELETE CASCADE PRIMARY KEY,
    tokens int NOT NULL,
    last_refill timestamptz NOT NULL DEFAULT now()
);

-- 2. Atomic Token Bucket Consumption RPC
CREATE OR REPLACE FUNCTION public.consume_api_quota(
    p_key_id uuid,
    p_cost int,
    p_capacity int,
    p_refill_rate_per_second float
) RETURNS boolean AS $$
DECLARE
    v_window public.api_rate_limits_window%ROWTYPE;
    v_time_passed float;
    v_new_tokens float;
    v_final_tokens int;
BEGIN
    -- Lock the row for update
    SELECT * INTO v_window 
    FROM public.api_rate_limits_window 
    WHERE api_key_id = p_key_id 
    FOR UPDATE;

    IF NOT FOUND THEN
        -- First time seeing this key, initialize at max capacity minus cost
        IF p_capacity >= p_cost THEN
            INSERT INTO public.api_rate_limits_window (api_key_id, tokens, last_refill)
            VALUES (p_key_id, p_capacity - p_cost, now());
            RETURN true;
        ELSE
            RETURN false;
        END IF;
    END IF;

    -- Calculate elapsed time and tokens to add
    v_time_passed := extract(epoch from (now() - v_window.last_refill));
    v_new_tokens := v_window.tokens + (v_time_passed * p_refill_rate_per_second);

    -- Cap at capacity
    IF v_new_tokens > p_capacity THEN
        v_new_tokens := p_capacity;
    END IF;

    -- Check if we can afford the cost
    IF v_new_tokens >= p_cost THEN
        v_final_tokens := floor(v_new_tokens - p_cost);
        UPDATE public.api_rate_limits_window
        SET tokens = v_final_tokens,
            last_refill = now()
        WHERE api_key_id = p_key_id;
        RETURN true;
    ELSE
        -- Update the tokens but don't consume (so they keep regenerating up to capacity)
        v_final_tokens := floor(v_new_tokens);
        UPDATE public.api_rate_limits_window
        SET tokens = v_final_tokens,
            last_refill = now()
        WHERE api_key_id = p_key_id;
        RETURN false;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 3. Webhooks Platform
CREATE TABLE IF NOT EXISTS public.webhook_endpoints (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id uuid REFERENCES public.workspaces(id) ON DELETE CASCADE NOT NULL,
    url text NOT NULL,
    event_types jsonb DEFAULT '[]'::jsonb NOT NULL,
    signing_secret text NOT NULL, -- Encrypted at rest
    is_active boolean DEFAULT true,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.webhook_deliveries (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id uuid REFERENCES public.workspaces(id) ON DELETE CASCADE NOT NULL,
    endpoint_id uuid REFERENCES public.webhook_endpoints(id) ON DELETE CASCADE NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    status_code int,
    response_body text,
    delivery_status text NOT NULL DEFAULT 'pending', -- pending, success, failed
    attempt_count int DEFAULT 0,
    next_retry_at timestamptz,
    created_at timestamptz DEFAULT now()
);

-- 4. Simple API Audit Logs (Minimal)
CREATE TABLE IF NOT EXISTS public.api_request_logs (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id uuid REFERENCES public.workspaces(id) ON DELETE CASCADE,
    api_key_id uuid REFERENCES public.api_keys(id) ON DELETE SET NULL,
    endpoint text NOT NULL,
    status_code int,
    created_at timestamptz DEFAULT now()
);

-- Apply RLS policies
ALTER TABLE public.webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_request_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_rate_limits_window ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (assuming workspaces access is managed via service role for API)
CREATE POLICY "service_role_all_webhook_endpoints" ON public.webhook_endpoints USING (true);
CREATE POLICY "service_role_all_webhook_deliveries" ON public.webhook_deliveries USING (true);
CREATE POLICY "service_role_all_api_request_logs" ON public.api_request_logs USING (true);
CREATE POLICY "service_role_all_api_rate_limits" ON public.api_rate_limits_window USING (true);
