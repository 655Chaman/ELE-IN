-- ========================================================================================
-- ELE-IN: ORPHANED LEADS CLEANUP TRIGGER (PARANOIA LAYER 0, 1 & 2)
-- Description: When a lead is removed from a list (or a list is deleted, cascading to list_members),
-- check if that lead belongs to any other lists.
-- CRITICAL GUARDS:
-- 1. Must NOT delete if lead has active/in-flight campaign execution states.
-- 2. Must NOT delete if lead has conversation/message history in public.messages.
-- 3. Must NOT delete if lead has pending approvals in public.approval_queue.
-- 4. Creates index on list_members(opportunity_id) to prevent $O(N \times M)$ sequential table scans.
-- ========================================================================================

-- Performance index: Prevent sequential table scan per deleted row
CREATE INDEX IF NOT EXISTS idx_list_members_opp_id 
    ON public.list_members (opportunity_id);

CREATE OR REPLACE FUNCTION public.cleanup_orphaned_leads()
RETURNS TRIGGER AS $$
DECLARE
    v_has_other_lists BOOLEAN;
    v_has_active_campaigns BOOLEAN;
    v_has_messages BOOLEAN;
    v_has_pending_approvals BOOLEAN;
BEGIN
    -- Layer 0: Check if the lead still exists in ANY other list
    SELECT EXISTS (
        SELECT 1 FROM public.list_members 
        WHERE opportunity_id = OLD.opportunity_id
    ) INTO v_has_other_lists;

    IF v_has_other_lists THEN
        RETURN OLD;
    END IF;

    -- Layer 1: Check if lead has active/pending/waiting campaign execution states
    SELECT EXISTS (
        SELECT 1 FROM public.campaign_execution_states ces
        JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
        WHERE ce.lead_id = OLD.opportunity_id
          AND ces.status IN ('pending', 'running', 'waiting_for_reply', 'awaiting_approval', 'snoozed_ooo')
    ) INTO v_has_active_campaigns;

    IF v_has_active_campaigns THEN
        -- Lead is active in an ongoing sequence; preserve the lead record
        RETURN OLD;
    END IF;

    -- Layer 1: Check if lead has conversation/message history
    SELECT EXISTS (
        SELECT 1 FROM public.messages
        WHERE lead_id = OLD.opportunity_id
    ) INTO v_has_messages;

    IF v_has_messages THEN
        -- Preserve conversation audit trail and sentiment attribution
        RETURN OLD;
    END IF;

    -- Layer 2 (Human Paranoia): Check if lead has pending approval queue actions
    SELECT EXISTS (
        SELECT 1 FROM public.approval_queue
        WHERE lead_id = OLD.opportunity_id::text
    ) INTO v_has_pending_approvals;

    IF v_has_pending_approvals THEN
        RETURN OLD;
    END IF;

    -- Safely delete only genuinely orphaned, unengaged, inactive leads
    DELETE FROM public.leads WHERE id = OLD.opportunity_id;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop trigger if it already exists to allow idempotent re-runs
DROP TRIGGER IF EXISTS trigger_cleanup_orphaned_leads ON public.list_members;

-- Create the AFTER DELETE trigger
CREATE TRIGGER trigger_cleanup_orphaned_leads
    AFTER DELETE ON public.list_members
    FOR EACH ROW EXECUTE FUNCTION public.cleanup_orphaned_leads();


