-- ==============================================================================
-- MIGRATION: 102_leads_storage_and_schema_drift.sql
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework)
-- Fixes:
-- 1. Missing EmailShield hygiene columns on leads table (Layer 0 Foundational)
-- 2. Multi-tenancy isolation and RLS on lead_tags with workspace_id (Layer 1 Security)
-- 3. Promoted lead_list_id on campaigns table for robust deletion guards (Layer 1 & 2)
-- 4. Canonical unique index on suppression_list domain vector (Layer 2 Paranoia)
-- 5. Exception-safe suppression handling in bulk_import_leads_atomic RPC
-- ==============================================================================

BEGIN;

-- 1. ADD MISSING EMAIL SHIELD HYGIENE COLUMNS TO LEADS TABLE
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS email_classification TEXT DEFAULT 'CORPORATE',
    ADD COLUMN IF NOT EXISTS is_role_based BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_disposable BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deliverability_risk TEXT DEFAULT 'SAFE';

-- 2. HARDEN LEAD_TAGS WITH WORKSPACE_ID AND ROW LEVEL SECURITY
ALTER TABLE public.lead_tags
    ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;

-- Backfill workspace_id from parent leads
UPDATE public.lead_tags lt
SET workspace_id = l.workspace_id
FROM public.leads l
WHERE lt.lead_id = l.id AND lt.workspace_id IS NULL;

-- Remove any dangling orphaned tags without parent lead
DELETE FROM public.lead_tags WHERE workspace_id IS NULL;

ALTER TABLE public.lead_tags ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.lead_tags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lead_tags_ws_all ON public.lead_tags;
CREATE POLICY lead_tags_ws_all ON public.lead_tags
    FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_lead_tags_ws_tag 
    ON public.lead_tags (workspace_id, tag);

-- 3. PROMOTE lead_list_id COLUMN ON CAMPAIGNS TABLE
ALTER TABLE public.campaigns
    ADD COLUMN IF NOT EXISTS lead_list_id UUID REFERENCES public.lead_lists(id) ON DELETE SET NULL;

-- Backfill from metadata JSONB where present
DO $$
BEGIN
    UPDATE public.campaigns
    SET lead_list_id = (metadata->>'lead_list_id')::uuid
    WHERE lead_list_id IS NULL 
      AND metadata IS NOT NULL 
      AND metadata ? 'lead_list_id'
      AND metadata->>'lead_list_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
EXCEPTION WHEN OTHERS THEN
    -- Ignore unparseable historical UUIDs in metadata
    NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_campaigns_lead_list_id 
    ON public.campaigns (lead_list_id);

-- 4. HARDEN SUPPRESSION_LIST WITH CANONICAL DOMAIN UNIQUE INDEX
CREATE UNIQUE INDEX IF NOT EXISTS uq_suppression_domain_canonical
    ON public.suppression_list (workspace_id, LOWER(TRIM(domain)))
    WHERE domain IS NOT NULL AND TRIM(domain) != '';

-- 5. UPGRADE bulk_import_leads_atomic RPC WITH EXCEPTION-SAFE SUPPRESSION HANDLING AND METADATA MERGE
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
    -- Layer 1 Paranoia: Advisory transaction lock on list to serialize concurrent ingestions
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
                domain = COALESCE(NULLIF(v_item->>'domain', ''), domain),
                timezone = COALESCE(NULLIF(v_item->>'timezone', ''), timezone, p_timezone),
                is_open_profile = COALESCE((v_item->>'is_open_profile')::boolean, is_open_profile),
                quarantine_reason = COALESCE(NULLIF(v_item->>'quarantine_reason', ''), quarantine_reason),
                email_classification = COALESCE(NULLIF(v_item->>'email_classification', ''), email_classification),
                is_role_based = COALESCE((v_item->>'is_role_based')::boolean, is_role_based),
                is_disposable = COALESCE((v_item->>'is_disposable')::boolean, is_disposable),
                deliverability_risk = COALESCE(NULLIF(v_item->>'deliverability_risk', ''), deliverability_risk),
                metadata = CASE 
                    WHEN v_item ? 'metadata' AND jsonb_typeof(v_item->'metadata') = 'object' 
                    THEN COALESCE(metadata, '{}'::jsonb) || (v_item->'metadata')
                    ELSE metadata
                END,
                updated_at = NOW()
            WHERE id = v_lead_id;
            v_updated := v_updated + 1;
        ELSE
            -- Insert new lead
            v_lead_id := gen_random_uuid();
            INSERT INTO public.leads (
                id, workspace_id, first_name, last_name, linkedin_url, company_name, email,
                domain, job_title, location, timezone, is_open_profile,
                quarantine_reason, email_classification, is_role_based, is_disposable, deliverability_risk,
                metadata, status
            ) VALUES (
                v_lead_id, p_workspace_id,
                v_item->>'first_name', v_item->>'last_name', v_linkedin, v_item->>'company_name',
                v_email, v_item->>'domain', v_item->>'job_title', v_item->>'location',
                COALESCE(v_item->>'timezone', p_timezone),
                COALESCE((v_item->>'is_open_profile')::boolean, false),
                v_item->>'quarantine_reason',
                COALESCE(v_item->>'email_classification', 'CORPORATE'),
                COALESCE((v_item->>'is_role_based')::boolean, false),
                COALESCE((v_item->>'is_disposable')::boolean, false),
                COALESCE(v_item->>'deliverability_risk', 'SAFE'),
                COALESCE(v_item->'metadata', '{}'::jsonb),
                COALESCE(v_item->>'status', 'extracted')
            );
            v_inserted := v_inserted + 1;
        END IF;

        -- Bind to list_members (safely handling suppression trigger rejection)
        BEGIN
            INSERT INTO public.list_members (id, workspace_id, list_id, opportunity_id)
            VALUES (gen_random_uuid(), p_workspace_id, p_list_id, v_lead_id)
            ON CONFLICT (list_id, opportunity_id) DO NOTHING;
        EXCEPTION WHEN SQLSTATE 'U0001' THEN
            -- Lead is suppressed, skip adding to active list without aborting bulk import
            NULL;
        END;
    END LOOP;

    -- Update list row count atomically
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

-- 6. Canonical delegation wrapper from bulk_import_leads to bulk_import_leads_atomic
CREATE OR REPLACE FUNCTION public.bulk_import_leads(
    p_list_id UUID,
    p_workspace_id UUID,
    p_leads JSONB,
    p_timezone TEXT DEFAULT 'UTC',
    p_location TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN public.bulk_import_leads_atomic(p_list_id, p_workspace_id, p_leads, p_timezone, p_location);
END;
$$;

COMMIT;
