ALTER TABLE public.accounts 
ADD COLUMN IF NOT EXISTS manual_send_suspected BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS manual_send_suspected_at TIMESTAMPTZ;
