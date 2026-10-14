-- ============================================================================
-- Migration 081: AI Inbox Copilot, Real-Time Objection Battlecards & Deal Pipeline
-- Blue Ocean Phase 10: The Conversation Closer
-- Governance: Three-Layer Logic Architecture (Paranoia Framework)
-- ============================================================================

-- 1. Extend leads table with Deal Stage & Value Tracking
ALTER TABLE IF EXISTS leads
ADD COLUMN IF NOT EXISTS deal_stage TEXT DEFAULT 'NEW_REPLY',
ADD COLUMN IF NOT EXISTS deal_stage_updated_at TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS deal_estimated_value NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_objection_type TEXT,
ADD COLUMN IF NOT EXISTS last_objection_at TIMESTAMPTZ;

-- 2. Create lead_objections audit table for conversation intelligence
CREATE TABLE IF NOT EXISTS lead_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    thread_key TEXT,
    objection_type TEXT NOT NULL,
    detected_competitor TEXT,
    detected_timing TEXT,
    confidence NUMERIC DEFAULT 1.0,
    raw_message_snippet TEXT,
    selected_strategy TEXT,
    selected_tone TEXT,
    resulting_deal_stage TEXT DEFAULT 'OBJECTION_RAISED',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Indexes for fast workspace queries and pipeline analytics
CREATE INDEX IF NOT EXISTS idx_leads_workspace_deal_stage ON leads(workspace_id, deal_stage);
CREATE INDEX IF NOT EXISTS idx_leads_deal_stage_updated ON leads(deal_stage_updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_objections_workspace ON lead_objections(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_objections_lead_id ON lead_objections(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_objections_type ON lead_objections(objection_type);

-- 4. Audit Log Action Type Registration
COMMENT ON COLUMN leads.deal_stage IS 'Current conversation lifecycle: NEW_REPLY, OBJECTION_RAISED, BATTLECARD_ENGAGED, MEETING_PROPOSED, MEETING_CONFIRMED, CLOSED_WON, DISQUALIFIED';
