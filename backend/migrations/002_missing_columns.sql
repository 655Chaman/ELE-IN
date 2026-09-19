-- =====================================================================
-- Migration 002: Add columns confirmed missing from production DB
-- Date: 2026-09-17
--
-- Pre-flight verification confirmed via read-only information_schema
-- probe that these six columns do NOT exist in the live production DB
-- even though they are defined in backend/supabase_schema.sql (v3).
--
-- Safe to run:
--   - All statements use ADD COLUMN IF NOT EXISTS (idempotent).
--   - No DROP, TRUNCATE, DELETE, UPDATE, or INSERT statements.
--   - No index, trigger, RLS, or grant changes.
--   - campaigns.metadata already exists in production — NOT included.
-- =====================================================================

BEGIN;

-- -----------------------------------------------------------------
-- public.workspaces: three columns added in the v3 schema design
-- that were never applied to production.
-- -----------------------------------------------------------------

ALTER TABLE public.workspaces
  ADD COLUMN IF NOT EXISTS require_2fa BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.workspaces
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

ALTER TABLE public.workspaces
  ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMPTZ;

-- -----------------------------------------------------------------
-- public.campaigns: three JSONB columns that store the visual
-- sequence tree (nodes/edges) and assigned sender account IDs.
-- campaigns.metadata already exists — excluded.
-- -----------------------------------------------------------------

ALTER TABLE public.campaigns
  ADD COLUMN IF NOT EXISTS nodes_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.campaigns
  ADD COLUMN IF NOT EXISTS edges_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.campaigns
  ADD COLUMN IF NOT EXISTS sender_account_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
