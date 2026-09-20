BEGIN;

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
    ),
    all_campaigns_totals AS (
        SELECT workspace_id, COUNT(*) as total_campaigns
        FROM public.campaigns
        WHERE (p_workspace_id IS NULL OR workspace_id = p_workspace_id)
        GROUP BY workspace_id
    )
    INSERT INTO public.daily_workspace_stats (workspace_id, stat_date, total_leads, active_campaigns, total_campaigns)
    SELECT 
        COALESCE(w.workspace_id, c.workspace_id, a.workspace_id),
        p_target_date,
        COALESCE(w.total_leads, 0),
        COALESCE(c.active_campaigns, 0),
        COALESCE(a.total_campaigns, 0)
    FROM workspace_totals w
    FULL OUTER JOIN campaign_totals c ON c.workspace_id = w.workspace_id
    FULL OUTER JOIN all_campaigns_totals a ON a.workspace_id = COALESCE(w.workspace_id, c.workspace_id)
    ON CONFLICT (workspace_id, stat_date) 
    DO UPDATE SET 
        total_leads = EXCLUDED.total_leads,
        active_campaigns = EXCLUDED.active_campaigns,
        total_campaigns = EXCLUDED.total_campaigns,
        updated_at = NOW();

    -- STEP B: Rollup Campaign-Level Stats
    WITH action_aggs AS (
        SELECT 
            al.workspace_id,
            ce.campaign_id,
            COUNT(*) FILTER (WHERE al.action_type LIKE '%connection%') as connections_sent,
            COUNT(*) FILTER (WHERE al.action_type IN ('send_message', 'send_voice_note', 'send_message_with_doc', 'send_message_with_image')) as messages_sent
        FROM public.action_log al
        JOIN public.campaign_execution_states ces ON ces.id = al.execution_state_id
        JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
        WHERE al.executed_at >= p_target_date::timestamp 
          AND al.executed_at < (p_target_date + interval '1 day')::timestamp
          AND (p_workspace_id IS NULL OR al.workspace_id = p_workspace_id)
        GROUP BY al.workspace_id, ce.campaign_id
    ),
    funnel_aggs AS (
        SELECT
            ces.workspace_id,
            ce.campaign_id,
            COUNT(*) as enrolled,
            COUNT(*) FILTER (WHERE ces.status IN ('running', 'completed', 'exited')) as connected,
            COUNT(*) FILTER (WHERE ces.status = 'exited' AND ces.error_reason IN ('mark_converted', 'hubspot_deal_won')) as booked
        FROM public.campaign_execution_states ces
        JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
        WHERE (p_workspace_id IS NULL OR ces.workspace_id = p_workspace_id)
        GROUP BY ces.workspace_id, ce.campaign_id
    ),
    replies_aggs AS (
        SELECT 
            ces.workspace_id,
            ce.campaign_id,
            COUNT(DISTINCT m.lead_id) as replied
        FROM public.messages m
        JOIN public.campaign_enrollments ce ON ce.lead_id = m.lead_id
        JOIN public.campaign_execution_states ces ON ces.enrollment_id = ce.id
        WHERE m.direction = 'inbound'
        AND (p_workspace_id IS NULL OR ces.workspace_id = p_workspace_id)
        GROUP BY ces.workspace_id, ce.campaign_id
    ),
    target_campaigns AS (
        -- Narrowed anchor: Only campaigns with existing stats today or active events today
        SELECT campaign_id, workspace_id
        FROM public.daily_campaign_stats
        WHERE stat_date = p_target_date
          AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id)
        UNION
        SELECT campaign_id, workspace_id FROM action_aggs
        UNION
        SELECT campaign_id, workspace_id FROM funnel_aggs
        UNION
        SELECT campaign_id, workspace_id FROM replies_aggs
    )
    
    INSERT INTO public.daily_campaign_stats (
        workspace_id, campaign_id, stat_date, 
        connections_sent, messages_sent, 
        enrolled, connected, booked, replied
    )
    SELECT 
        tc.workspace_id,
        tc.campaign_id,
        p_target_date,
        COALESCE(a.connections_sent, 0),
        COALESCE(a.messages_sent, 0),
        COALESCE(f.enrolled, 0),
        COALESCE(f.connected, 0),
        COALESCE(f.booked, 0),
        COALESCE(r.replied, 0)
    FROM target_campaigns tc
    LEFT JOIN action_aggs a ON a.campaign_id = tc.campaign_id
    LEFT JOIN funnel_aggs f ON f.campaign_id = tc.campaign_id
    LEFT JOIN replies_aggs r ON r.campaign_id = tc.campaign_id
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
