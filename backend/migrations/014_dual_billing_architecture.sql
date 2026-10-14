ALTER TABLE public.subscriptions RENAME COLUMN stripe_subscription_id TO provider_subscription_id;
ALTER INDEX subscriptions_stripe_subscription_id_key RENAME TO subscriptions_provider_subscription_id_key;
ALTER TABLE public.subscriptions RENAME COLUMN stripe_price_id TO provider_plan_id;
ALTER TABLE public.subscriptions ADD COLUMN provider TEXT NOT NULL DEFAULT 'mock' CHECK (provider IN ('razorpay', 'lemonsqueezy', 'mock'));
ALTER TABLE public.subscriptions RENAME COLUMN raw_stripe_event TO raw_webhook_event;

CREATE TABLE public.billing_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('razorpay', 'lemonsqueezy', 'mock')),
    provider_order_id TEXT UNIQUE NOT NULL, 
    provider_payment_id TEXT, 
    amount_cents INTEGER NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    credits_added INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.billing_transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view their own workspace billing history"
    ON public.billing_transactions FOR SELECT
    USING (workspace_id IN (SELECT public.my_workspace_ids()));

CREATE TABLE public.processed_webhook_events (
    event_id TEXT,
    provider TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (event_id, provider)
);
ALTER TABLE public.processed_webhook_events ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION add_credits_safely(p_workspace_id UUID, p_credits INT, p_event_id TEXT, p_provider TEXT) RETURNS void AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM processed_webhook_events WHERE event_id = p_event_id AND provider = p_provider) THEN
        RETURN; 
    END IF;
    PERFORM id FROM public.workspaces WHERE id = p_workspace_id FOR UPDATE;
    UPDATE public.workspaces SET data_cleaning_credits = COALESCE(data_cleaning_credits, 0) + p_credits WHERE id = p_workspace_id;
    INSERT INTO processed_webhook_events(event_id, provider) VALUES (p_event_id, p_provider);
END;
$$ LANGUAGE plpgsql;
