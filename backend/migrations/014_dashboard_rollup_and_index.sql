BEGIN;

-- 1. Create the composite index
CREATE INDEX IF NOT EXISTS idx_daily_campaign_stats_workspace_date 
ON public.daily_campaign_stats(workspace_id, stat_date);

-- 2. Add extra funnel columns if they don't exist
ALTER TABLE public.daily_campaign_stats 
ADD COLUMN IF NOT EXISTS enrolled integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS connected integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS booked integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_leads integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS active_campaigns integer DEFAULT 0;

-- 3. Create the Rollup RPC
CREATE OR REPLACE FUNCTION public.rollup_daily_stats(p_target_date date)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
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
        GROUP BY ls.workspace_id, ls.campaign_id
    ),
    workspace_totals AS (
        SELECT 
            workspace_id, 
            COUNT(*) as total_leads 
        FROM public.leads 
        GROUP BY workspace_id
    ),
    campaign_totals AS (
        SELECT 
            workspace_id, 
            COUNT(*) as active_campaigns 
        FROM public.campaigns 
        WHERE status = 'ACTIVE' 
        GROUP BY workspace_id
    ),
    replies_aggs AS (
        SELECT 
            ls.workspace_id,
            ls.campaign_id,
            COUNT(DISTINCT m.lead_id) as replied
        FROM public.messages m
        JOIN public.lead_states ls ON ls.opportunity_id = m.lead_id
        WHERE m.direction = 'inbound'
        GROUP BY ls.workspace_id, ls.campaign_id
    )
    
    INSERT INTO public.daily_campaign_stats (
        workspace_id, campaign_id, stat_date, 
        connections_sent, messages_sent, 
        enrolled, connected, booked, replied,
        total_leads, active_campaigns
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
        COALESCE(r.replied, 0),
        COALESCE(w.total_leads, 0),
        COALESCE(c.active_campaigns, 0)
    FROM action_aggs a
    FULL OUTER JOIN funnel_aggs f ON a.workspace_id = f.workspace_id AND a.campaign_id = f.campaign_id
    LEFT JOIN workspace_totals w ON w.workspace_id = COALESCE(a.workspace_id, f.workspace_id)
    LEFT JOIN campaign_totals c ON c.workspace_id = COALESCE(a.workspace_id, f.workspace_id)
    LEFT JOIN replies_aggs r ON r.campaign_id = COALESCE(a.campaign_id, f.campaign_id)
    
    ON CONFLICT (campaign_id, stat_date) 
    DO UPDATE SET 
        connections_sent = EXCLUDED.connections_sent,
        messages_sent = EXCLUDED.messages_sent,
        enrolled = EXCLUDED.enrolled,
        connected = EXCLUDED.connected,
        booked = EXCLUDED.booked,
        replied = EXCLUDED.replied,
        total_leads = EXCLUDED.total_leads,
        active_campaigns = EXCLUDED.active_campaigns,
        updated_at = NOW();
END;
$$;

COMMIT;
