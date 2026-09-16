BEGIN;

-- 1. Create the new workspace-level stats table
CREATE TABLE IF NOT EXISTS public.daily_workspace_stats (
    workspace_id uuid REFERENCES public.workspaces(id) ON DELETE CASCADE,
    stat_date date NOT NULL,
    total_leads integer DEFAULT 0,
    active_campaigns integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT daily_workspace_stats_ws_date_uniq UNIQUE (workspace_id, stat_date)
);

-- 2. Drop the incorrectly modeled columns from the campaign stats table
ALTER TABLE public.daily_campaign_stats 
DROP COLUMN IF EXISTS total_leads,
DROP COLUMN IF EXISTS active_campaigns;

-- 3. Rewrite the Rollup RPC to populate BOTH tables cleanly
CREATE OR REPLACE FUNCTION public.rollup_daily_stats(p_target_date date, p_workspace_id uuid DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    -- STEP A: Rollup Workspace-Level Stats
    WITH workspace_totals AS (
        SELECT l.workspace_id, COUNT(l.id) as total_leads 
        FROM public.leads l
        WHERE EXISTS (
            SELECT 1 FROM public.campaigns c WHERE c.workspace_id = l.workspace_id AND c.status = 'ACTIVE'
        )
        AND (p_workspace_id IS NULL OR l.workspace_id = p_workspace_id)
        GROUP BY l.workspace_id
    ),
    campaign_totals AS (
        SELECT workspace_id, COUNT(*) as active_campaigns 
        FROM public.campaigns 
        WHERE status = 'ACTIVE' 
        AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id)
        GROUP BY workspace_id
    )
    INSERT INTO public.daily_workspace_stats (workspace_id, stat_date, total_leads, active_campaigns)
    SELECT 
        COALESCE(w.workspace_id, c.workspace_id),
        p_target_date,
        COALESCE(w.total_leads, 0),
        COALESCE(c.active_campaigns, 0)
    FROM workspace_totals w
    FULL OUTER JOIN campaign_totals c ON c.workspace_id = w.workspace_id
    ON CONFLICT (workspace_id, stat_date) 
    DO UPDATE SET 
        total_leads = EXCLUDED.total_leads,
        active_campaigns = EXCLUDED.active_campaigns,
        updated_at = NOW();

    -- STEP B: Rollup Campaign-Level Stats
    WITH action_aggs AS (
        SELECT 
            al.workspace_id,
            ls.campaign_id,
            COUNT(*) FILTER (WHERE al.action_type LIKE '%connection%') as connections_sent,
            COUNT(*) FILTER (WHERE al.action_type IN ('send_message', 'send_voice_note', 'send_message_with_doc', 'send_message_with_image')) as messages_sent
        FROM public.action_log al
        JOIN public.lead_states ls ON ls.id = al.lead_state_id
        WHERE al.executed_at >= p_target_date::timestamp 
          AND al.executed_at < (p_target_date + interval '1 day')::timestamp
          AND (p_workspace_id IS NULL OR al.workspace_id = p_workspace_id)
        GROUP BY al.workspace_id, ls.campaign_id
    ),
    funnel_aggs AS (
        SELECT
            ls.workspace_id,
            ls.campaign_id,
            COUNT(*) as enrolled,
            COUNT(*) FILTER (WHERE ls.status IN ('running', 'completed', 'exited')) as connected,
            COUNT(*) FILTER (WHERE ls.status = 'exited') as booked
        FROM public.lead_states ls
        WHERE (p_workspace_id IS NULL OR ls.workspace_id = p_workspace_id)
        GROUP BY ls.workspace_id, ls.campaign_id
    ),
    replies_aggs AS (
        SELECT 
            ls.workspace_id,
            ls.campaign_id,
            COUNT(DISTINCT m.lead_id) as replied
        FROM public.messages m
        JOIN public.lead_states ls ON ls.opportunity_id = m.lead_id
        WHERE m.direction = 'inbound'
        AND (p_workspace_id IS NULL OR ls.workspace_id = p_workspace_id)
        GROUP BY ls.workspace_id, ls.campaign_id
    )
    
    INSERT INTO public.daily_campaign_stats (
        workspace_id, campaign_id, stat_date, 
        connections_sent, messages_sent, 
        enrolled, connected, booked, replied
    )
    SELECT 
        COALESCE(a.workspace_id, f.workspace_id),
        COALESCE(a.campaign_id, f.campaign_id),
        p_target_date,
        COALESCE(a.connections_sent, 0),
        COALESCE(a.messages_sent, 0),
        COALESCE(f.enrolled, 0),
        COALESCE(f.connected, 0),
        COALESCE(f.booked, 0),
        COALESCE(r.replied, 0)
    FROM action_aggs a
    FULL OUTER JOIN funnel_aggs f ON a.workspace_id = f.workspace_id AND a.campaign_id = f.campaign_id
    LEFT JOIN replies_aggs r ON r.campaign_id = COALESCE(a.campaign_id, f.campaign_id)
    ON CONFLICT (campaign_id, stat_date) 
    DO UPDATE SET 
        connections_sent = EXCLUDED.connections_sent,
        messages_sent = EXCLUDED.messages_sent,
        enrolled = EXCLUDED.enrolled,
        connected = EXCLUDED.connected,
        booked = EXCLUDED.booked,
        replied = EXCLUDED.replied,
        updated_at = NOW();
END;
$$;

COMMIT;
