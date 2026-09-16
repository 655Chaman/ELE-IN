-- Fix API Key Column Name Mismatch
ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS api_key text;
