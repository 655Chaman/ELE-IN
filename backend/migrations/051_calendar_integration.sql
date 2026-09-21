-- Migration 051: Phase C Calendar Integrations

-- Add calendar configurations to accounts table
ALTER TABLE public.accounts
ADD COLUMN IF NOT EXISTS calendar_provider TEXT CHECK (calendar_provider IN ('cal.com', 'calendly')),
ADD COLUMN IF NOT EXISTS calendar_token TEXT,
ADD COLUMN IF NOT EXISTS calendar_link TEXT;
