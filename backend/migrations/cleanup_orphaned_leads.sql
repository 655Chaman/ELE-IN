-- ========================================================================================
-- ELE-IN: ORPHANED LEADS CLEANUP TRIGGER (PARANOIA LAYER 1)
-- Description: When a lead is removed from a list (or a list is deleted, cascading to list_members),
-- check if that lead belongs to any other lists. If not, permanently delete the lead to prevent
-- storage leaks on the Free Tier.
-- ========================================================================================

CREATE OR REPLACE FUNCTION public.cleanup_orphaned_leads()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if the lead still exists in ANY other list
    IF NOT EXISTS (
        SELECT 1 FROM public.list_members 
        WHERE opportunity_id = OLD.opportunity_id
    ) THEN
        -- Safely delete the orphaned lead
        DELETE FROM public.leads WHERE id = OLD.opportunity_id;
    END IF;
    
    RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop trigger if it already exists to allow idempotent re-runs
DROP TRIGGER IF EXISTS trigger_cleanup_orphaned_leads ON public.list_members;

-- Create the AFTER DELETE trigger
CREATE TRIGGER trigger_cleanup_orphaned_leads
    AFTER DELETE ON public.list_members
    FOR EACH ROW EXECUTE FUNCTION public.cleanup_orphaned_leads();

