-- Migration 093: Employee Advocacy & Viral LinkedIn Post Booster Pod ("The Algorithmic Velocity Pod")
-- Description: Creates tables for team advocacy pods, member quotas, post boost scheduling, and execution ledgers.
-- Paranoia Framework: Fully idempotent DDL with IF NOT EXISTS, composite indexes, and workspace tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.advocacy_pods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    settings JSONB NOT NULL DEFAULT '{"auto_boost": true, "golden_hour_minutes": 60, "min_delay_seconds": 120, "max_delay_seconds": 420}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.advocacy_pod_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    pod_id UUID NOT NULL,
    account_id TEXT NOT NULL,
    account_name TEXT NOT NULL DEFAULT '',
    daily_like_cap INTEGER NOT NULL DEFAULT 15,
    daily_comment_cap INTEGER NOT NULL DEFAULT 5,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.advocacy_post_boosts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    pod_id UUID NOT NULL,
    author_account_id TEXT NOT NULL,
    post_url TEXT NOT NULL,
    post_content TEXT NOT NULL DEFAULT '',
    target_likes INTEGER NOT NULL DEFAULT 10,
    target_comments INTEGER NOT NULL DEFAULT 5,
    target_window_minutes INTEGER NOT NULL DEFAULT 60,
    status TEXT NOT NULL DEFAULT 'boosting' CHECK (status IN ('scheduled', 'boosting', 'completed', 'paused', 'cancelled', 'expired')),
    likes_count INTEGER NOT NULL DEFAULT 0,
    comments_count INTEGER NOT NULL DEFAULT 0,
    golden_hour_deadline TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.advocacy_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    post_boost_id UUID NOT NULL,
    account_id TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('like', 'comment', 'repost')),
    reaction_type TEXT NOT NULL DEFAULT 'LIKE' CHECK (reaction_type IN ('LIKE', 'CELEBRATE', 'SUPPORT', 'INSIGHTFUL', 'FUNNY', 'LOVE')),
    comment_text TEXT NOT NULL DEFAULT '',
    scheduled_at TIMESTAMPTZ NOT NULL,
    executed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'executed', 'failed', 'skipped')),
    failure_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for performance and tenant isolation
CREATE INDEX IF NOT EXISTS idx_advocacy_pods_ws ON public.advocacy_pods(workspace_id, is_active);
CREATE INDEX IF NOT EXISTS idx_advocacy_members_pod ON public.advocacy_pod_members(pod_id, is_active);
CREATE INDEX IF NOT EXISTS idx_advocacy_boosts_ws ON public.advocacy_post_boosts(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_advocacy_boosts_url ON public.advocacy_post_boosts(workspace_id, post_url);
CREATE INDEX IF NOT EXISTS idx_advocacy_engagements_boost ON public.advocacy_engagements(post_boost_id, status);
CREATE INDEX IF NOT EXISTS idx_advocacy_engagements_acc ON public.advocacy_engagements(account_id, scheduled_at);

-- Enable Row-Level Security
ALTER TABLE public.advocacy_pods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.advocacy_pod_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.advocacy_post_boosts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.advocacy_engagements ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_pods' AND policyname = 'advocacy_pods_ws_policy') THEN
        CREATE POLICY advocacy_pods_ws_policy ON public.advocacy_pods FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_pod_members' AND policyname = 'advocacy_pod_members_ws_policy') THEN
        CREATE POLICY advocacy_pod_members_ws_policy ON public.advocacy_pod_members FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_post_boosts' AND policyname = 'advocacy_post_boosts_ws_policy') THEN
        CREATE POLICY advocacy_post_boosts_ws_policy ON public.advocacy_post_boosts FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_engagements' AND policyname = 'advocacy_engagements_ws_policy') THEN
        CREATE POLICY advocacy_engagements_ws_policy ON public.advocacy_engagements FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
