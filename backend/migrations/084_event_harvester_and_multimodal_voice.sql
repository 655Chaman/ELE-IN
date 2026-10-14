-- Migration 084: LinkedIn Event & Group Harvester and Multimodal Voice/Video Prospecting
-- Description: Enables harvesting registered attendees from LinkedIn events/groups, seniority segmentation, and voice/video prospecting assets.
-- Paranoia Framework: Idempotent DDL with IF NOT EXISTS, RLS policies, and defensive defaults.

CREATE TABLE IF NOT EXISTS public.harvested_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    event_url TEXT NOT NULL,
    event_name TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'event' CHECK (event_type IN ('event', 'group', 'webinar')),
    attendee_count INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('harvesting', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.event_attendees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES public.harvested_events(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    prospect_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    title TEXT NOT NULL,
    linkedin_url TEXT,
    seniority TEXT NOT NULL DEFAULT 'director' CHECK (seniority IN ('c_level', 'vp', 'director', 'manager', 'ic')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'enrolled', 'disqualified')),
    generated_icebreaker TEXT,
    enrolled_campaign_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.multimodal_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('voice_script', 'video_card')),
    script_text TEXT NOT NULL,
    estimated_duration_sec INT NOT NULL DEFAULT 30,
    media_url TEXT,
    thumbnail_text TEXT,
    status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('draft', 'ready', 'delivered')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid querying
CREATE INDEX IF NOT EXISTS idx_harvested_events_ws ON public.harvested_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_event_attendees_event ON public.event_attendees(event_id, status);
CREATE INDEX IF NOT EXISTS idx_multimodal_assets_ws ON public.multimodal_assets(workspace_id, asset_type);

-- Row-Level Security
ALTER TABLE public.harvested_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_attendees ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.multimodal_assets ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'harvested_events' AND policyname = 'harvested_events_ws_policy') THEN
        CREATE POLICY harvested_events_ws_policy ON public.harvested_events FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'event_attendees' AND policyname = 'event_attendees_ws_policy') THEN
        CREATE POLICY event_attendees_ws_policy ON public.event_attendees FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'multimodal_assets' AND policyname = 'multimodal_assets_ws_policy') THEN
        CREATE POLICY multimodal_assets_ws_policy ON public.multimodal_assets FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
