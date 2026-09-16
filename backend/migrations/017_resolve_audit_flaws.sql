-- ========================================================================================
-- ELE-IN MIGRATION 017: FULL RESOLUTION OF LEAD IDENTITY AUDIT
-- Description: Fixes constraints and enforces suppression at the DB layer correctly.
-- ========================================================================================

BEGIN;

-- 2.1 Enforce UNIQUE(workspace_id, linkedin_url) on `leads`
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS uq_leads_workspace_linkedin;
ALTER TABLE public.leads ADD CONSTRAINT uq_leads_workspace_linkedin UNIQUE (workspace_id, linkedin_url);

-- 2.2 Enforce UNIQUE constraints on tags and enrichment results
ALTER TABLE public.lead_tags DROP CONSTRAINT IF EXISTS uq_lead_tag;
ALTER TABLE public.lead_tags ADD CONSTRAINT uq_lead_tag UNIQUE (lead_id, tag);

ALTER TABLE public.enrichment_results DROP CONSTRAINT IF EXISTS uq_enrichment_lead_provider_field;
ALTER TABLE public.enrichment_results ADD CONSTRAINT uq_enrichment_lead_provider_field UNIQUE (lead_id, provider, field);

-- 2.3 Add uniqueness to suppression list so check targets are unambiguous
ALTER TABLE public.suppression_list DROP CONSTRAINT IF EXISTS uq_suppression_linkedin;
ALTER TABLE public.suppression_list ADD CONSTRAINT uq_suppression_linkedin UNIQUE (workspace_id, linkedin_url);

ALTER TABLE public.suppression_list DROP CONSTRAINT IF EXISTS uq_suppression_email;
ALTER TABLE public.suppression_list ADD CONSTRAINT uq_suppression_email UNIQUE (workspace_id, email);

-- Rebuild the suppression trigger properly
CREATE OR REPLACE FUNCTION public.enforce_suppression_list()
RETURNS TRIGGER AS $$
DECLARE
    v_linkedin_url TEXT;
    v_email TEXT;
    v_workspace_id UUID;
    v_is_suppressed BOOLEAN;
BEGIN
    -- Both tables use `opportunity_id` pointing to leads
    IF TG_TABLE_NAME = 'list_members' OR TG_TABLE_NAME = 'lead_states' THEN
        SELECT linkedin_url, email, workspace_id INTO v_linkedin_url, v_email, v_workspace_id 
        FROM public.leads 
        WHERE id = NEW.opportunity_id;
    END IF;

    -- Check against suppression list directly matching linkedin_url or email
    SELECT EXISTS (
        SELECT 1 FROM public.suppression_list sl
        WHERE sl.workspace_id = v_workspace_id
        AND (
            (sl.linkedin_url IS NOT NULL AND sl.linkedin_url != '' AND sl.linkedin_url = v_linkedin_url) OR
            (sl.email IS NOT NULL AND sl.email != '' AND sl.email = v_email)
        )
    ) INTO v_is_suppressed;

    IF v_is_suppressed THEN
        RAISE EXCEPTION 'suppression_list_violation: Lead matches a suppression list rule and cannot be processed.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Rebind triggers
DROP TRIGGER IF EXISTS enforce_suppression_list_members ON public.list_members;
CREATE TRIGGER enforce_suppression_list_members
    BEFORE INSERT ON public.list_members
    FOR EACH ROW EXECUTE FUNCTION public.enforce_suppression_list();

DROP TRIGGER IF EXISTS enforce_suppression_lead_states ON public.lead_states;
CREATE TRIGGER enforce_suppression_lead_states
    BEFORE INSERT ON public.lead_states
    FOR EACH ROW EXECUTE FUNCTION public.enforce_suppression_list();


-- 2.4 Duplicate campaign enrollment
ALTER TABLE public.lead_states DROP CONSTRAINT IF EXISTS uq_lead_state_campaign_lead;
ALTER TABLE public.lead_states ADD CONSTRAINT uq_lead_state_campaign_lead UNIQUE (campaign_id, opportunity_id);

-- 2.5 List membership can duplicate
ALTER TABLE public.list_members DROP CONSTRAINT IF EXISTS uq_list_member;
ALTER TABLE public.list_members ADD CONSTRAINT uq_list_member UNIQUE (list_id, opportunity_id);


-- Update bulk_import_leads to use the updated constraint name
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
        -- Upsert the lead using the exact constraint name requested by the audit
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
        ON CONFLICT ON CONSTRAINT uq_leads_workspace_linkedin DO UPDATE SET
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

-- 2.6 RPCs to enforce Upsert behavior strictly at the DB layer for Tags and Enrichment
CREATE OR REPLACE FUNCTION public.upsert_lead_tag(
    p_lead_id UUID,
    p_tag TEXT
)
RETURNS void AS $$
BEGIN
    INSERT INTO public.lead_tags (lead_id, tag)
    VALUES (p_lead_id, p_tag)
    ON CONFLICT ON CONSTRAINT uq_lead_tag DO NOTHING;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION public.upsert_enrichment_result(
    p_lead_id UUID,
    p_provider TEXT,
    p_field TEXT,
    p_value TEXT,
    p_cost NUMERIC DEFAULT 0
)
RETURNS void AS $$
BEGIN
    INSERT INTO public.enrichment_results (lead_id, provider, field, value, cost, fetched_at)
    VALUES (p_lead_id, p_provider, p_field, p_value, p_cost, now())
    ON CONFLICT ON CONSTRAINT uq_enrichment_lead_provider_field DO UPDATE SET
        value = EXCLUDED.value,
        cost = EXCLUDED.cost,
        fetched_at = EXCLUDED.fetched_at;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMIT;
