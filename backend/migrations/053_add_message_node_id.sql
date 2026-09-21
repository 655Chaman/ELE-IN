-- Migration 053
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS node_id UUID;
