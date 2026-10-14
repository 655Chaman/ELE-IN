-- Migration 073: Agency White-Label Branding & Client Portfolio Metrics
-- Paranoia Framework: Layer 0 (Foundational), Layer 1 (Environmental Fallbacks), Layer 2 (Human Safety)

-- 1. Add white-label configuration columns to public.agencies
ALTER TABLE public.agencies 
ADD COLUMN IF NOT EXISTS whitelabel_brand TEXT DEFAULT 'Ele-in Agency',
ADD COLUMN IF NOT EXISTS whitelabel_domain TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS whitelabel_color TEXT DEFAULT '#6366f1',
ADD COLUMN IF NOT EXISTS whitelabel_logo_url TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS whitelabel_enabled BOOLEAN DEFAULT true;

-- 2. Performance RPC: Single-pass client workspace telemetry aggregation
CREATE OR REPLACE FUNCTION public.get_agency_clients_overview(p_agency_id UUID)
RETURNS TABLE (
    id UUID,
    name TEXT,
    created_at TIMESTAMPTZ,
    campaigns_count BIGINT,
    active_campaigns_count BIGINT,
    leads_count BIGINT,
    senders_count BIGINT
) LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT 
        w.id,
        w.name,
        w.created_at,
        COALESCE(c.camp_count, 0)::BIGINT AS campaigns_count,
        COALESCE(c.active_camp_count, 0)::BIGINT AS active_campaigns_count,
        COALESCE(l.lead_count, 0)::BIGINT AS leads_count,
        COALESCE(a.acc_count, 0)::BIGINT AS senders_count
    FROM public.workspaces w
    LEFT JOIN (
        SELECT 
            workspace_id, 
            COUNT(*) AS camp_count,
            COUNT(*) FILTER (WHERE status = 'active') AS active_camp_count
        FROM public.campaigns
        GROUP BY workspace_id
    ) c ON c.workspace_id = w.id
    LEFT JOIN (
        SELECT 
            workspace_id, 
            COUNT(*) AS lead_count
        FROM public.leads
        GROUP BY workspace_id
    ) l ON l.workspace_id = w.id
    LEFT JOIN (
        SELECT 
            workspace_id, 
            COUNT(*) AS acc_count
        FROM public.accounts
        WHERE status IN ('connected', 'active', 'valid')
        GROUP BY workspace_id
    ) a ON a.workspace_id = w.id
    WHERE w.agency_id = p_agency_id
    ORDER BY w.created_at DESC;
END;
$$;
