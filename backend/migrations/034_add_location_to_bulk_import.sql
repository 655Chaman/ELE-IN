-- Migration: 034_add_location_to_bulk_import
-- Description: Add p_location parameter to bulk_import_leads RPC.

CREATE OR REPLACE FUNCTION public.bulk_import_leads(
    p_list_id UUID,
    p_workspace_id UUID,
    p_leads JSONB,
    p_location TEXT DEFAULT NULL
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
            company_name, email, domain, job_title, location
        ) VALUES (
            p_workspace_id,
            v_lead->>'linkedin_url',
            v_lead->>'first_name',
            v_lead->>'last_name',
            v_lead->>'company_name',
            v_lead->>'email',
            v_lead->>'domain',
            v_lead->>'job_title',
            COALESCE(v_lead->>'p_location', p_location)
        )
        ON CONFLICT ON CONSTRAINT uq_leads_workspace_linkedin DO UPDATE SET
            first_name = COALESCE(EXCLUDED.first_name, leads.first_name),
            last_name = COALESCE(EXCLUDED.last_name, leads.last_name),
            company_name = COALESCE(EXCLUDED.company_name, leads.company_name),
            job_title = COALESCE(EXCLUDED.job_title, leads.job_title),
            location = COALESCE(EXCLUDED.location, leads.location)
        RETURNING id INTO v_opp_id;

        -- Link to the list (ignoring if already linked)
        BEGIN
            INSERT INTO public.list_members (list_id, opportunity_id)
            VALUES (p_list_id, v_opp_id);
            v_inserted_count := v_inserted_count + 1;
        EXCEPTION WHEN unique_violation THEN
            -- already in list, do nothing
            NULL;
        WHEN OTHERS THEN
            -- suppression list might block it, catch and ignore
            IF SQLERRM LIKE '%suppression_list_violation%' THEN
                -- skipped due to suppression
                NULL;
            ELSE
                RAISE;
            END IF;
        END;
    END LOOP;

    RETURN jsonb_build_object('success', true, 'inserted_count', v_inserted_count);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
