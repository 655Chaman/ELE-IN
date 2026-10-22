-- ==============================================================================
-- MIGRATION: 106_leads_subsystem_paranoia_remediation.sql
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework)
-- Fixes:
-- 1. Deduplicates list_members and enforces UNIQUE (list_id, opportunity_id) & indexes
-- 2. Hardens foreign keys referencing public.leads with ON DELETE CASCADE / SET NULL
-- 3. Hardens suppression_list with workspace foreign key and fast composite indexes
-- 4. Upgrades enforce_suppression_list() trigger with domain wildcards & case-insensitivity
-- 5. Upgrades cleanup_orphaned_leads() trigger to preserve completed campaign analytics
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. DEDUPLICATE list_members AND ENFORCE UNIQUE (list_id, opportunity_id)
-- ------------------------------------------------------------------------------

-- Step 1a: Deduplicate any existing duplicate list_members rows (retaining oldest)
DELETE FROM public.list_members a
USING public.list_members b
WHERE a.id > b.id
  AND a.list_id = b.list_id
  AND a.opportunity_id = b.opportunity_id;

-- Step 1b: Enforce unique constraint on (list_id, opportunity_id) and cascade on lead_lists
ALTER TABLE public.list_members 
    DROP CONSTRAINT IF EXISTS uq_list_members_list_opportunity,
    DROP CONSTRAINT IF EXISTS list_members_list_id_opportunity_id_key,
    DROP CONSTRAINT IF EXISTS list_members_list_id_fkey;

ALTER TABLE public.list_members 
    ADD CONSTRAINT uq_list_members_list_opportunity UNIQUE (list_id, opportunity_id);

ALTER TABLE public.list_members 
    ADD CONSTRAINT list_members_list_id_fkey 
    FOREIGN KEY (list_id) REFERENCES public.lead_lists(id) ON DELETE CASCADE;

-- Step 1c: Create high-performance query indexes for workspace list queries
CREATE INDEX IF NOT EXISTS idx_list_members_ws_list 
    ON public.list_members (workspace_id, list_id);

CREATE INDEX IF NOT EXISTS idx_list_members_opp_id 
    ON public.list_members (opportunity_id);

-- ------------------------------------------------------------------------------
-- 2. HARDEN FOREIGN KEYS REFERENCING public.leads WITH ON DELETE CASCADE
-- ------------------------------------------------------------------------------

-- list_members
ALTER TABLE public.list_members 
    DROP CONSTRAINT IF EXISTS list_members_opportunity_id_fkey;
ALTER TABLE public.list_members 
    ADD CONSTRAINT list_members_opportunity_id_fkey 
    FOREIGN KEY (opportunity_id) REFERENCES public.leads(id) ON DELETE CASCADE;

-- campaign_enrollments
ALTER TABLE public.campaign_enrollments 
    DROP CONSTRAINT IF EXISTS campaign_enrollments_lead_id_fkey;
ALTER TABLE public.campaign_enrollments 
    ADD CONSTRAINT campaign_enrollments_lead_id_fkey 
    FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;

-- messages
ALTER TABLE public.messages 
    DROP CONSTRAINT IF EXISTS messages_lead_id_fkey;
ALTER TABLE public.messages 
    ADD CONSTRAINT messages_lead_id_fkey 
    FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;

-- ai_reply_approvals
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ai_reply_approvals') THEN
        ALTER TABLE public.ai_reply_approvals DROP CONSTRAINT IF EXISTS ai_reply_approvals_lead_id_fkey;
        ALTER TABLE public.ai_reply_approvals ADD CONSTRAINT ai_reply_approvals_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- lead_social_posts
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'lead_social_posts') THEN
        ALTER TABLE public.lead_social_posts DROP CONSTRAINT IF EXISTS lead_social_posts_lead_id_fkey;
        ALTER TABLE public.lead_social_posts ADD CONSTRAINT lead_social_posts_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- lead_social_signals
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'lead_social_signals') THEN
        ALTER TABLE public.lead_social_signals DROP CONSTRAINT IF EXISTS lead_social_signals_lead_id_fkey;
        ALTER TABLE public.lead_social_signals ADD CONSTRAINT lead_social_signals_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- icp_feedback_events
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'icp_feedback_events') THEN
        ALTER TABLE public.icp_feedback_events DROP CONSTRAINT IF EXISTS icp_feedback_events_lead_id_fkey;
        ALTER TABLE public.icp_feedback_events ADD CONSTRAINT icp_feedback_events_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- lead_objections
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'lead_objections') THEN
        ALTER TABLE public.lead_objections DROP CONSTRAINT IF EXISTS lead_objections_lead_id_fkey;
        ALTER TABLE public.lead_objections ADD CONSTRAINT lead_objections_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- lead_tags
DELETE FROM public.lead_tags WHERE lead_id NOT IN (SELECT id FROM public.leads);
ALTER TABLE public.lead_tags DROP CONSTRAINT IF EXISTS lead_tags_lead_id_fkey;
ALTER TABLE public.lead_tags ADD CONSTRAINT lead_tags_lead_id_fkey 
    FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;

-- enrichment_results
DELETE FROM public.enrichment_results WHERE lead_id NOT IN (SELECT id FROM public.leads);
ALTER TABLE public.enrichment_results DROP CONSTRAINT IF EXISTS enrichment_results_lead_id_fkey;
ALTER TABLE public.enrichment_results ADD CONSTRAINT enrichment_results_lead_id_fkey 
    FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;

-- voice_notes
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'voice_notes') THEN
        DELETE FROM public.voice_notes WHERE lead_id NOT IN (SELECT id FROM public.leads);
        ALTER TABLE public.voice_notes DROP CONSTRAINT IF EXISTS voice_notes_lead_id_fkey;
        ALTER TABLE public.voice_notes ADD CONSTRAINT voice_notes_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- profile_activity_snapshots
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'profile_activity_snapshots') THEN
        DELETE FROM public.profile_activity_snapshots WHERE lead_id NOT IN (SELECT id FROM public.leads);
        ALTER TABLE public.profile_activity_snapshots DROP CONSTRAINT IF EXISTS profile_activity_snapshots_lead_id_fkey;
        ALTER TABLE public.profile_activity_snapshots ADD CONSTRAINT profile_activity_snapshots_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ai_generations
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ai_generations') THEN
        UPDATE public.ai_generations SET lead_id = NULL WHERE lead_id IS NOT NULL AND lead_id NOT IN (SELECT id FROM public.leads);
        ALTER TABLE public.ai_generations DROP CONSTRAINT IF EXISTS ai_generations_lead_id_fkey;
        ALTER TABLE public.ai_generations ADD CONSTRAINT ai_generations_lead_id_fkey 
            FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- 3. HARDEN suppression_list WITH WORKSPACE FK AND PERFORMANCE INDEXES
-- ------------------------------------------------------------------------------

-- Prune orphaned suppression records whose workspace no longer exists
DELETE FROM public.suppression_list WHERE workspace_id NOT IN (SELECT id FROM public.workspaces);

-- Add workspace FK with ON DELETE CASCADE
ALTER TABLE public.suppression_list 
    DROP CONSTRAINT IF EXISTS suppression_list_workspace_id_fkey;

ALTER TABLE public.suppression_list 
    ADD CONSTRAINT suppression_list_workspace_id_fkey 
    FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

-- Composite index for fast targeted suppression lookups across all identifier columns
CREATE INDEX IF NOT EXISTS idx_suppression_lookup 
    ON public.suppression_list (workspace_id, domain, email, linkedin_url);

CREATE INDEX IF NOT EXISTS idx_suppression_value 
    ON public.suppression_list (workspace_id, value);

-- ------------------------------------------------------------------------------
-- 4. UPGRADE enforce_suppression_list() TRIGGER (DOMAIN WILDCARDS & LOWERCASE)
-- ------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enforce_suppression_list()
RETURNS TRIGGER AS $$
DECLARE
    v_linkedin_url TEXT;
    v_email TEXT;
    v_domain TEXT;
    v_workspace_id UUID;
    v_is_suppressed BOOLEAN := FALSE;
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

    -- Extract domain from email if available
    IF v_email IS NOT NULL AND position('@' in v_email) > 0 THEN
        v_domain := LOWER(TRIM(split_part(v_email, '@', 2)));
    END IF;

    -- Paranoia Layer 0 & 1: Case-insensitive and wildcard domain suppression check
    IF v_workspace_id IS NOT NULL AND (v_linkedin_url IS NOT NULL OR v_email IS NOT NULL OR v_domain IS NOT NULL) THEN
        SELECT EXISTS (
            SELECT 1 
            FROM public.suppression_list 
            WHERE workspace_id = v_workspace_id 
              AND (
                  (v_linkedin_url IS NOT NULL AND TRIM(v_linkedin_url) != '' AND (
                      LOWER(TRIM(linkedin_url)) = LOWER(TRIM(v_linkedin_url))
                      OR LOWER(TRIM(value)) = LOWER(TRIM(v_linkedin_url))
                  ))
                  OR (v_email IS NOT NULL AND TRIM(v_email) != '' AND (
                      LOWER(TRIM(email)) = LOWER(TRIM(v_email))
                      OR LOWER(TRIM(value)) = LOWER(TRIM(v_email))
                  ))
                  OR (v_domain IS NOT NULL AND TRIM(v_domain) != '' AND (
                      LOWER(TRIM(domain)) = v_domain
                      OR LOWER(TRIM(value)) = v_domain
                      OR LOWER(TRIM(value)) = '@' || v_domain
                  ))
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

-- Rebind the trigger to campaign_enrollments
DROP TRIGGER IF EXISTS enforce_suppression_campaign_enrollments ON public.campaign_enrollments;
CREATE TRIGGER enforce_suppression_campaign_enrollments
    BEFORE INSERT ON public.campaign_enrollments
    FOR EACH ROW EXECUTE FUNCTION public.enforce_suppression_list();

-- ------------------------------------------------------------------------------
-- 5. UPGRADE cleanup_orphaned_leads() TRIGGER (PRESERVE CAMPAIGN ANALYTICS)
-- ------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.cleanup_orphaned_leads()
RETURNS TRIGGER AS $$
DECLARE
    v_has_other_lists BOOLEAN;
    v_has_campaign_enrollments BOOLEAN;
    v_has_messages BOOLEAN;
    v_has_pending_approvals BOOLEAN;
BEGIN
    -- Check if lead still belongs to other lists
    SELECT EXISTS (
        SELECT 1 FROM public.list_members 
        WHERE opportunity_id = OLD.opportunity_id
          AND id != OLD.id
    ) INTO v_has_other_lists;

    IF v_has_other_lists THEN
        RETURN OLD;
    END IF;

    -- Paranoia Layer 1: Check if lead was ever enrolled in ANY campaign (active or past)
    -- Preserves historical campaign metrics, delivery telemetry, and reply funnels
    SELECT EXISTS (
        SELECT 1 FROM public.campaign_enrollments ce
        WHERE ce.lead_id = OLD.opportunity_id
    ) INTO v_has_campaign_enrollments;

    IF v_has_campaign_enrollments THEN
        RETURN OLD;
    END IF;

    -- Check if lead has message history
    SELECT EXISTS (
        SELECT 1 FROM public.messages
        WHERE lead_id = OLD.opportunity_id
    ) INTO v_has_messages;

    IF v_has_messages THEN
        RETURN OLD;
    END IF;

    -- Check if lead has pending approvals
    SELECT EXISTS (
        SELECT 1 FROM public.approval_queue
        WHERE lead_id = OLD.opportunity_id::text
    ) INTO v_has_pending_approvals;

    IF v_has_pending_approvals THEN
        RETURN OLD;
    END IF;

    -- Lead is truly an uncontacted orphan: safely delete
    DELETE FROM public.leads WHERE id = OLD.opportunity_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
