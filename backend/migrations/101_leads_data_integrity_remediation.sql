-- ==============================================================================
-- MIGRATION: 101_leads_data_integrity_remediation.sql
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework)
-- Fixes: RLS on list_members, Dropping Dangerous Cleanup Trigger, Schema Drift,
-- Foreign Keys, Indexes, Function Overloads, and Idempotent Atomic Ingestion.
-- ==============================================================================

BEGIN;

-- 1. DROP DANGEROUS CRM LEAD DELETION TRIGGER (VULN-LEAD-02)
DROP TRIGGER IF EXISTS trigger_cleanup_orphaned_leads ON public.list_members;
DROP FUNCTION IF EXISTS public.cleanup_orphaned_leads();

-- 2. HARDEN list_members WITH WORKSPACE_ID AND ROW LEVEL SECURITY (VULN-LEAD-01)
ALTER TABLE public.list_members
    ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;

-- Backfill workspace_id from parent lead_lists
UPDATE public.list_members lm
SET workspace_id = l.workspace_id
FROM public.lead_lists l
WHERE lm.list_id = l.id AND lm.workspace_id IS NULL;

-- In case any orphaned list_members have no parent list, clean them
DELETE FROM public.list_members WHERE workspace_id IS NULL;

ALTER TABLE public.list_members ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.list_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS list_members_isolation ON public.list_members;
CREATE POLICY list_members_isolation ON public.list_members
    FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_list_members_ws ON public.list_members (workspace_id);
CREATE INDEX IF NOT EXISTS idx_list_members_list_lead ON public.list_members (list_id, opportunity_id);

-- 3. RESOLVE LEADS TABLE SCHEMA DRIFT (VULN-LEAD-06, VULN-LEAD-07)
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS is_open_profile BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_social_retargeted_at TIMESTAMPTZ DEFAULT NULL;

-- 4. RESOLVE CAMPAIGN VERSIONS ORDERING COLUMN (VULN-LEAD-09)
ALTER TABLE public.campaign_versions
    ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;

-- 5. RESOLVE OPEN USING (true) RLS POLICIES (VULN-LEAD-12)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_posts') THEN
        DROP POLICY IF EXISTS lead_social_posts_isolation ON public.lead_social_posts;
        CREATE POLICY lead_social_posts_isolation ON public.lead_social_posts
            FOR ALL
            USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;

    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_signals') THEN
        DROP POLICY IF EXISTS lead_social_signals_isolation ON public.lead_social_signals;
        CREATE POLICY lead_social_signals_isolation ON public.lead_social_signals
            FOR ALL
            USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;

    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_objections') THEN
        DROP POLICY IF EXISTS lead_objections_isolation ON public.lead_objections;
        CREATE POLICY lead_objections_isolation ON public.lead_objections
            FOR ALL
            USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 6. ADD PERFORMANCE INDEXES FOR CLEANUP, SUPPRESSION & INTENT (VULN-LEAD-10, VULN-LEAD-11)
CREATE INDEX IF NOT EXISTS idx_approval_queue_lead_id 
    ON public.approval_queue (lead_id);

CREATE INDEX IF NOT EXISTS idx_messages_lead_id 
    ON public.messages (lead_id);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_posts') THEN
        CREATE INDEX IF NOT EXISTS idx_lead_social_posts_lookup 
            ON public.lead_social_posts (workspace_id, lead_id, post_date DESC);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leads_social_intent_feed 
    ON public.leads (workspace_id, social_intent_score DESC, last_social_scan_at DESC)
    WHERE social_intent_score > 0;

CREATE INDEX IF NOT EXISTS idx_suppression_composite_lookup 
    ON public.suppression_list (workspace_id, linkedin_url, email, domain);

-- 7. REMOVE AMBIGUOUS FUNCTION OVERLOADS (VULN-LEAD-15)
DROP FUNCTION IF EXISTS public.dequeue_due_leads(integer, uuid[]);

-- 8. ATOMIC BULK IMPORT RPC (VULN-LEAD-13)
CREATE OR REPLACE FUNCTION public.bulk_import_leads_atomic(
    p_workspace_id UUID,
    p_list_id UUID,
    p_leads JSONB,
    p_timezone TEXT DEFAULT 'UTC'
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_item JSONB;
    v_lead_id UUID;
    v_linkedin TEXT;
    v_email TEXT;
    v_inserted INT := 0;
    v_updated INT := 0;
BEGIN
    -- Layer 1 Paranoia: Acquire advisory transaction lock on list to eliminate concurrent write races
    PERFORM pg_advisory_xact_lock(hashtext(p_list_id::text));

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_leads)
    LOOP
        v_linkedin := NULLIF(LOWER(TRIM(v_item->>'linkedin_url')), '');
        v_email := NULLIF(LOWER(TRIM(v_item->>'email')), '');
        v_lead_id := NULL;

        -- Seek existing lead by canonical identity
        IF v_linkedin IS NOT NULL THEN
            SELECT id INTO v_lead_id FROM public.leads
            WHERE workspace_id = p_workspace_id AND LOWER(TRIM(linkedin_url)) = v_linkedin
            LIMIT 1;
        END IF;

        IF v_lead_id IS NULL AND v_email IS NOT NULL THEN
            SELECT id INTO v_lead_id FROM public.leads
            WHERE workspace_id = p_workspace_id AND LOWER(TRIM(email)) = v_email
            LIMIT 1;
        END IF;

        IF v_lead_id IS NOT NULL THEN
            -- Merge existing lead
            UPDATE public.leads
            SET first_name = COALESCE(NULLIF(v_item->>'first_name', ''), first_name),
                last_name = COALESCE(NULLIF(v_item->>'last_name', ''), last_name),
                company_name = COALESCE(NULLIF(v_item->>'company_name', ''), company_name),
                job_title = COALESCE(NULLIF(v_item->>'job_title', ''), job_title),
                location = COALESCE(NULLIF(v_item->>'location', ''), location),
                timezone = COALESCE(NULLIF(v_item->>'timezone', ''), timezone, p_timezone),
                is_open_profile = COALESCE((v_item->>'is_open_profile')::boolean, is_open_profile),
                updated_at = NOW()
            WHERE id = v_lead_id;
            v_updated := v_updated + 1;
        ELSE
            -- Insert new lead
            v_lead_id := gen_random_uuid();
            INSERT INTO public.leads (
                id, workspace_id, first_name, last_name, linkedin_url, company_name, email,
                domain, job_title, location, timezone, is_open_profile, status
            ) VALUES (
                v_lead_id, p_workspace_id,
                v_item->>'first_name', v_item->>'last_name', v_linkedin, v_item->>'company_name',
                v_email, v_item->>'domain', v_item->>'job_title', v_item->>'location',
                COALESCE(v_item->>'timezone', p_timezone),
                COALESCE((v_item->>'is_open_profile')::boolean, false),
                'extracted'
            );
            v_inserted := v_inserted + 1;
        END IF;

        -- Bind to list_members
        INSERT INTO public.list_members (id, workspace_id, list_id, opportunity_id)
        VALUES (gen_random_uuid(), p_workspace_id, p_list_id, v_lead_id)
        ON CONFLICT (list_id, opportunity_id) DO NOTHING;
    END LOOP;

    -- Update row count
    UPDATE public.lead_lists
    SET row_count = (SELECT COUNT(*) FROM public.list_members WHERE list_id = p_list_id),
        updated_at = NOW()
    WHERE id = p_list_id;

    RETURN jsonb_build_object(
        'success', true,
        'inserted_count', v_inserted,
        'updated_count', v_updated,
        'total_processed', v_inserted + v_updated
    );
END;
$$;

COMMIT;
