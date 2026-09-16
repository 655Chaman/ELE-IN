-- =====================================================================
-- Migration 015: Settings DB fixes (workspace_members uniqueness & admin_grants)
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. workspace_members deduplication and UNIQUE constraint
-- ---------------------------------------------------------------------

-- Deduplicate workspace_members keeping the most privileged role, then newest
WITH ranked_members AS (
  SELECT id,
         ROW_NUMBER() OVER(
           PARTITION BY workspace_id, user_id 
           ORDER BY 
             CASE role 
               WHEN 'owner' THEN 1 
               WHEN 'admin' THEN 2 
               WHEN 'member' THEN 3 
               ELSE 4 
             END ASC,
             created_at DESC
         ) as rn
  FROM public.workspace_members
)
DELETE FROM public.workspace_members
WHERE id IN (
  SELECT id FROM ranked_members WHERE rn > 1
);

-- Drop any existing unique constraints on these columns just in case
ALTER TABLE public.workspace_members DROP CONSTRAINT IF EXISTS workspace_members_workspace_user_uniq;
ALTER TABLE public.workspace_members DROP CONSTRAINT IF EXISTS workspace_members_workspace_id_user_id_key;
ALTER TABLE public.workspace_members DROP CONSTRAINT IF EXISTS uq_workspace_member;

-- Add the unique constraint officially
ALTER TABLE public.workspace_members 
  ADD CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id);

-- ---------------------------------------------------------------------
-- 2. Create admin_grants table
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.admin_grants (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    granted_by    UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at    TIMESTAMPTZ,
    revoked_by    UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    reason        TEXT
);
COMMENT ON TABLE public.admin_grants IS 'Audit trail for superadmin privileges.';

CREATE INDEX IF NOT EXISTS admin_grants_user_id_idx ON public.admin_grants(user_id);

ALTER TABLE public.admin_grants ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
      AND tablename = 'admin_grants' 
      AND policyname = 'admin_grants_self'
  ) THEN
    CREATE POLICY admin_grants_self ON public.admin_grants FOR SELECT USING (user_id = auth.uid());
  END IF;
END $$;

-- Migrate existing superadmins to admin_grants
INSERT INTO public.admin_grants (user_id, granted_at, reason)
SELECT id, created_at, 'Migrated from user_profiles.is_superadmin'
FROM public.user_profiles
WHERE is_superadmin = TRUE
  AND NOT EXISTS (
    SELECT 1 FROM public.admin_grants WHERE admin_grants.user_id = user_profiles.id
  );

-- ---------------------------------------------------------------------
-- 3. Drop is_superadmin from user_profiles
-- ---------------------------------------------------------------------
ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS is_superadmin;

COMMIT;
