-- ============================================================
-- Migration 012: Ensure accounts are unique per workspace
-- ============================================================

BEGIN;

-- Remove duplicates if any exist (keep the most recently updated one)
DELETE FROM public.accounts a
WHERE a.id NOT IN (
    SELECT DISTINCT ON (workspace_id, linkedin_profile_url) id
    FROM public.accounts
    WHERE linkedin_profile_url IS NOT NULL
    ORDER BY workspace_id, linkedin_profile_url, updated_at DESC
);

-- Add the unique constraint
ALTER TABLE public.accounts
    ADD CONSTRAINT accounts_workspace_linkedin_unique
    UNIQUE (workspace_id, linkedin_profile_url);

COMMIT;
