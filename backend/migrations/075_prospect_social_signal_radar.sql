-- Migration 075: Prospect Social Signal Radar & Live Activity Intent Engine
-- Supports capturing prospects' LinkedIn activity, intent signal harvesting,
-- buying intent scores (0-100), and personalized conversational icebreakers.

CREATE TABLE IF NOT EXISTS lead_social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    post_url TEXT,
    post_text TEXT NOT NULL,
    post_date TIMESTAMPTZ DEFAULT now(),
    engagement_count JSONB DEFAULT '{"likes": 0, "comments": 0, "reposts": 0}'::jsonb,
    media_type TEXT DEFAULT 'text',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lead_social_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    post_id UUID REFERENCES lead_social_posts(id) ON DELETE SET NULL,
    signal_type TEXT NOT NULL, -- HIRING_EXPANSION, TECH_STACK_PAIN, TOOL_EVALUATION, EXECUTIVE_PROMOTION, FUNDING_ANNOUNCEMENT, GENERAL_THOUGHT_LEADERSHIP
    intent_strength TEXT NOT NULL DEFAULT 'MEDIUM', -- HIGH, MEDIUM, LOW
    confidence_score FLOAT DEFAULT 0.8,
    detected_keywords JSONB DEFAULT '[]'::jsonb,
    signal_summary TEXT NOT NULL,
    quote_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Extend leads table with social intent fields if they don't already exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'social_intent_score') THEN
        ALTER TABLE leads ADD COLUMN social_intent_score INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'social_intent_tier') THEN
        ALTER TABLE leads ADD COLUMN social_intent_tier TEXT DEFAULT 'COLD';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'last_social_scan_at') THEN
        ALTER TABLE leads ADD COLUMN last_social_scan_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'best_outreach_angle') THEN
        ALTER TABLE leads ADD COLUMN best_outreach_angle TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'social_icebreaker') THEN
        ALTER TABLE leads ADD COLUMN social_icebreaker TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'recommended_timing') THEN
        ALTER TABLE leads ADD COLUMN recommended_timing TEXT DEFAULT 'PASSIVE_WARMUP';
    END IF;
END $$;

-- High-performance indexes for radar queries
CREATE INDEX IF NOT EXISTS idx_lead_social_posts_lead_ws ON lead_social_posts(lead_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_lead_social_posts_date ON lead_social_posts(post_date DESC);
CREATE INDEX IF NOT EXISTS idx_lead_social_signals_ws_type ON lead_social_signals(workspace_id, signal_type);
CREATE INDEX IF NOT EXISTS idx_leads_social_intent_ws ON leads(workspace_id, social_intent_score DESC);
