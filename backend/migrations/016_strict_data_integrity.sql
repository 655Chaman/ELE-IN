-- ========================================================================================
-- ELE-IN MIGRATION 016: STRICT DATA INTEGRITY (PARANOIA LAYER)
-- ========================================================================================

BEGIN;

-- 1. Enforce UNIQUE(workspace_id, linkedin_url) on `leads`
DO $$
DECLARE
    dup RECORD;
BEGIN
    FOR dup IN 
        WITH duplicates AS (
            SELECT id, workspace_id, linkedin_url,
                   ROW_NUMBER() OVER (PARTITION BY workspace_id, linkedin_url ORDER BY created_at ASC) as row_num
            FROM public.leads
            WHERE linkedin_url IS NOT NULL AND linkedin_url != ''
        ),
        survivors AS (
            SELECT workspace_id, linkedin_url, id as survivor_id
            FROM duplicates
            WHERE row_num = 1
        )
        SELECT d.id as dup_id, s.survivor_id
        FROM duplicates d
        JOIN survivors s ON d.workspace_id = s.workspace_id AND d.linkedin_url = s.linkedin_url
        WHERE d.row_num > 1
    LOOP
        UPDATE public.list_members SET opportunity_id = dup.survivor_id
        WHERE opportunity_id = dup.dup_id
        AND NOT EXISTS (SELECT 1 FROM public.list_members WHERE opportunity_id = dup.survivor_id AND list_id = public.list_members.list_id);
        
        UPDATE public.lead_states SET lead_id = dup.survivor_id
        WHERE lead_id = dup.dup_id
        AND NOT EXISTS (SELECT 1 FROM public.lead_states WHERE lead_id = dup.survivor_id AND campaign_id = public.lead_states.campaign_id);

        DELETE FROM public.leads WHERE id = dup.dup_id;
    END LOOP;
END $$;

ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_workspace_linkedin_key;
ALTER TABLE public.leads ADD CONSTRAINT leads_workspace_linkedin_key UNIQUE (workspace_id, linkedin_url);


-- 2. Enforce UNIQUE(lead_id, tag) on `lead_tags`
WITH tag_duplicates AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY lead_id, tag ORDER BY created_at ASC) as row_num
    FROM public.lead_tags
)
DELETE FROM public.lead_tags WHERE id IN (SELECT id FROM tag_duplicates WHERE row_num > 1);

ALTER TABLE public.lead_tags DROP CONSTRAINT IF EXISTS lead_tags_lead_tag_key;
ALTER TABLE public.lead_tags ADD CONSTRAINT lead_tags_lead_tag_key UNIQUE (lead_id, tag);


-- 3. Enforce UNIQUE(lead_id, provider, field) on `enrichment_results`
WITH enrichment_duplicates AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY lead_id, provider, field ORDER BY fetched_at DESC) as row_num
    FROM public.enrichment_results
)
DELETE FROM public.enrichment_results WHERE id IN (SELECT id FROM enrichment_duplicates WHERE row_num > 1);

ALTER TABLE public.enrichment_results DROP CONSTRAINT IF EXISTS enrichment_lead_provider_field_key;
ALTER TABLE public.enrichment_results ADD CONSTRAINT enrichment_lead_provider_field_key UNIQUE (lead_id, provider, field);


-- 4. DB-Layer Enforcement for `suppression_list`
CREATE OR REPLACE FUNCTION public.enforce_suppression_list()
RETURNS TRIGGER AS $$
DECLARE
    v_domain TEXT;
    v_email TEXT;
    v_workspace_id UUID;
    v_is_suppressed BOOLEAN;
BEGIN
    IF TG_TABLE_NAME = 'list_members' THEN
        SELECT domain, email, workspace_id INTO v_domain, v_email, v_workspace_id FROM public.leads WHERE id = NEW.opportunity_id;
    ELSIF TG_TABLE_NAME = 'lead_states' THEN
        SELECT domain, email, workspace_id INTO v_domain, v_email, v_workspace_id FROM public.leads WHERE id = NEW.lead_id;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM public.suppression_list sl
        WHERE sl.workspace_id = v_workspace_id
        AND (
            (sl.type = 'domain' AND v_domain IS NOT NULL AND v_domain != '' AND v_domain ILIKE '%' || sl.value || '%') OR
            (sl.type = 'email' AND v_email IS NOT NULL AND v_email != '' AND v_email ILIKE sl.value)
        )
    ) INTO v_is_suppressed;

    IF v_is_suppressed THEN
        RAISE EXCEPTION 'suppression_list_violation: Lead matches a suppression list rule and cannot be processed.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS enforce_suppression_list_members ON public.list_members;
CREATE TRIGGER enforce_suppression_list_members
    BEFORE INSERT ON public.list_members
    FOR EACH ROW EXECUTE FUNCTION public.enforce_suppression_list();

DROP TRIGGER IF EXISTS enforce_suppression_lead_states ON public.lead_states;
CREATE TRIGGER enforce_suppression_lead_states
    BEFORE INSERT ON public.lead_states
    FOR EACH ROW EXECUTE FUNCTION public.enforce_suppression_list();


-- 5. RPC to Bulk Import Leads Safely (Upsert + Ignore duplicates)
CREATE OR REPLACE FUNCTION public.bulk_import_leads(
    p_list_id UUID,
    p_workspace_id UUID,
    p_leads JSONB
)
RETURNS JSONB AS $$
DECLARE
    v_lead JSONB;
    v_opp_id UUID;
    v_inserted_count INT := 0;
BEGIN
    FOR v_lead IN SELECT * FROM jsonb_array_elements(p_leads)
    LOOP
        -- Upsert the lead
        INSERT INTO public.leads (
            workspace_id, linkedin_url, first_name, last_name, 
            company_name, email, domain, job_title
        ) VALUES (
            p_workspace_id,
            v_lead->>'linkedin_url',
            v_lead->>'first_name',
            v_lead->>'last_name',
            v_lead->>'company_name',
            v_lead->>'email',
            v_lead->>'domain',
            v_lead->>'job_title'
        )
        ON CONFLICT (workspace_id, linkedin_url) DO UPDATE SET
            first_name = COALESCE(EXCLUDED.first_name, leads.first_name),
            last_name = COALESCE(EXCLUDED.last_name, leads.last_name),
            company_name = COALESCE(EXCLUDED.company_name, leads.company_name),
            job_title = COALESCE(EXCLUDED.job_title, leads.job_title)
        RETURNING id INTO v_opp_id;

        -- Link to the list (ignoring if already linked)
        BEGIN
            INSERT INTO public.list_members (list_id, opportunity_id)
            VALUES (p_list_id, v_opp_id);
            v_inserted_count := v_inserted_count + 1;
        EXCEPTION WHEN unique_violation THEN
            -- already in list, do nothing
        WHEN OTHERS THEN
            -- suppression list might block it, catch and ignore
            IF SQLERRM LIKE '%suppression_list_violation%' THEN
                -- skipped due to suppression
            ELSE
                RAISE;
            END IF;
        END;
    END LOOP;

    RETURN jsonb_build_object('success', true, 'inserted_count', v_inserted_count);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMIT;
