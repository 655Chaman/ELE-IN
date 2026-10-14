-- ==============================================================================
-- Migration: 082_social_prewarm_and_omnichannel_cascade.sql
-- Blue Ocean Phase 11: Social Feed Pre-Warmer, Thought Leadership & Omnichannel Cascade
-- Governance: Three-Layer Logic Architecture (Paranoia Framework)
-- Idempotent, safe migration with IF NOT EXISTS guards
-- ==============================================================================

-- 1. Pre-Warm Touchpoint Events Audit Table
CREATE TABLE IF NOT EXISTS lead_prewarm_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID NOT NULL,
    account_id UUID,
    action_type VARCHAR(50) NOT NULL, -- 'profile_view', 'post_like', 'post_comment'
    post_url TEXT,
    post_snippet TEXT,
    generated_comment TEXT,
    sentiment_score FLOAT DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'completed', 'skipped', 'failed'
    scheduled_for TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prewarm_workspace_lead ON lead_prewarm_events(workspace_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_prewarm_status_scheduled ON lead_prewarm_events(status, scheduled_for);

-- 2. Omnichannel Fallback Cascade Configuration & State Table
CREATE TABLE IF NOT EXISTS omnichannel_fallback_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    campaign_id UUID,
    days_pending_threshold INT DEFAULT 7,
    auto_withdraw_linkedin BOOLEAN DEFAULT TRUE,
    fallback_to_email BOOLEAN DEFAULT TRUE,
    fallback_to_inmail BOOLEAN DEFAULT TRUE,
    bridge_template_id VARCHAR(100) DEFAULT 'linkedin_connection_followup',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_omnichannel_workspace ON omnichannel_fallback_configs(workspace_id);

CREATE TABLE IF NOT EXISTS omnichannel_cascade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID NOT NULL,
    campaign_id UUID,
    original_channel VARCHAR(50) NOT NULL DEFAULT 'linkedin',
    target_channel VARCHAR(50) NOT NULL, -- 'email', 'inmail', 'sms'
    trigger_reason VARCHAR(100) NOT NULL, -- 'linkedin_pending_timeout_7d'
    status VARCHAR(50) DEFAULT 'completed', -- 'completed', 'failed', 'suppressed'
    bridge_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cascade_logs_lead ON omnichannel_cascade_logs(workspace_id, lead_id);

-- 3. Thought Leadership Content Studio & Schedule Table
CREATE TABLE IF NOT EXISTS thought_leadership_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    account_id UUID,
    topic VARCHAR(255) NOT NULL,
    hook_framework VARCHAR(100) NOT NULL,
    post_content TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'scheduled', 'published'
    scheduled_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_posts_workspace_status ON thought_leadership_posts(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_posts_scheduled_at ON thought_leadership_posts(scheduled_at);
