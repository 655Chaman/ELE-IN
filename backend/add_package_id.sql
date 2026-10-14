ALTER TABLE public.billing_transactions ADD COLUMN IF NOT EXISTS package_id TEXT;
ALTER TABLE public.billing_transactions ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
