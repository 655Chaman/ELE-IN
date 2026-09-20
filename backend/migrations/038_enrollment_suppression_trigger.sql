CREATE OR REPLACE FUNCTION public.enforce_suppression_list()
RETURNS TRIGGER AS $$
DECLARE
    v_linkedin_url TEXT;
    v_email TEXT;
    v_workspace_id UUID;
    v_is_suppressed BOOLEAN;
BEGIN
    -- Handle list_members and legacy lead_states
    IF TG_TABLE_NAME = 'list_members' OR TG_TABLE_NAME = 'lead_states' THEN
        IF TG_OP = 'INSERT' THEN
            SELECT workspace_id, linkedin_url, email
            INTO v_workspace_id, v_linkedin_url, v_email
            FROM public.leads
            WHERE id = NEW.opportunity_id;
        END IF;
        
    -- Handle campaign_enrollments
    ELSIF TG_TABLE_NAME = 'campaign_enrollments' THEN
        IF TG_OP = 'INSERT' THEN
            v_workspace_id := NEW.workspace_id;
            SELECT linkedin_url, email
            INTO v_linkedin_url, v_email
            FROM public.leads
            WHERE id = NEW.lead_id;
        END IF;
    END IF;

    -- Unified suppression enforcement
    IF v_workspace_id IS NOT NULL AND (v_linkedin_url IS NOT NULL OR v_email IS NOT NULL) THEN
        SELECT EXISTS (
            SELECT 1 
            FROM public.suppression_list 
            WHERE workspace_id = v_workspace_id 
              AND (
                  (v_linkedin_url IS NOT NULL AND linkedin_url = v_linkedin_url)
                  OR (v_email IS NOT NULL AND email = v_email)
              )
        ) INTO v_is_suppressed;

        IF v_is_suppressed THEN
            RAISE EXCEPTION USING 
                ERRCODE = 'U0001',
                MESSAGE = 'suppression_list_violation: Lead is on the suppression list.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Bind the trigger
DROP TRIGGER IF EXISTS enforce_suppression_campaign_enrollments ON public.campaign_enrollments;
CREATE TRIGGER enforce_suppression_campaign_enrollments
    BEFORE INSERT ON public.campaign_enrollments
    FOR EACH ROW EXECUTE FUNCTION public.enforce_suppression_list();
