-- ============================================================================
-- Migration 107: Inbox & Unibox Subsystem Three-Layer Paranoia Remediation
-- Subsystem: Inbox, Unibox, Approvals, Objections & Outbox Notifications
-- 
-- Remediation Scope:
-- 1. FLAW-INBOX-DB-1: Add missing campaign_id, enrollment_id, node_id to approval_queue
--    with foreign key cascades.
-- 2. FLAW-INBOX-DB-2: Add composite performance indexes on messages, approval_queue,
--    and ai_reply_approvals to permanently prevent table scan HTTP 504 timeouts.
-- 3. FLAW-INBOX-DB-3: Add partial index on outbox_events for sub-millisecond pending poll.
-- 4. FLAW-INBOX-DB-4: Add missing foreign keys and indexes on lead_objections and
--    notifications to enforce multi-tenant isolation and prevent orphaned records.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. FLAW-INBOX-DB-1: approval_queue Column & Foreign Key Parity
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    -- Add campaign_id column and foreign key if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'campaign_id'
    ) THEN
        ALTER TABLE public.approval_queue ADD COLUMN campaign_id UUID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_campaign') THEN
        ALTER TABLE public.approval_queue 
            ADD CONSTRAINT fk_approval_queue_campaign FOREIGN KEY (campaign_id) 
            REFERENCES public.campaigns(id) ON DELETE CASCADE;
    END IF;

    -- Add enrollment_id column and foreign key if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'enrollment_id'
    ) THEN
        ALTER TABLE public.approval_queue ADD COLUMN enrollment_id UUID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_enrollment') THEN
        ALTER TABLE public.approval_queue 
            ADD CONSTRAINT fk_approval_queue_enrollment FOREIGN KEY (enrollment_id) 
            REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE;
    END IF;

    -- Add node_id column and foreign key if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'node_id'
    ) THEN
        ALTER TABLE public.approval_queue ADD COLUMN node_id UUID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_node') THEN
        ALTER TABLE public.approval_queue 
            ADD CONSTRAINT fk_approval_queue_node FOREIGN KEY (node_id) 
            REFERENCES public.campaign_nodes(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 2. FLAW-INBOX-DB-2: High-Performance Composite Indexes for Inbox Queries
-- ----------------------------------------------------------------------------
-- Messages workspace feed index (used by get_inbox_threads)
CREATE INDEX IF NOT EXISTS idx_messages_ws_created 
    ON public.messages (workspace_id, created_at DESC);

-- Messages account-filtered feed index
CREATE INDEX IF NOT EXISTS idx_messages_ws_acc_created 
    ON public.messages (workspace_id, account_id, created_at DESC);

-- Messages thread history lookup index (used by get_thread_messages)
CREATE INDEX IF NOT EXISTS idx_messages_ws_sender 
    ON public.messages (workspace_id, sender_name, created_at DESC);

-- Messages lead-specific thread lookup index
CREATE INDEX IF NOT EXISTS idx_messages_ws_lead 
    ON public.messages (workspace_id, lead_id, created_at ASC);

-- Messages bulk deduplication index (used by sync_inbox_messages)
CREATE INDEX IF NOT EXISTS idx_messages_acc_text 
    ON public.messages (account_id, message_text);

-- Approval queue workspace pending filter index (used by list_approvals)
CREATE INDEX IF NOT EXISTS idx_approval_queue_ws_status_created 
    ON public.approval_queue (workspace_id, status, created_at DESC);

-- AI reply approvals workspace filter index (used by list_approvals)
CREATE INDEX IF NOT EXISTS idx_ai_reply_approvals_ws_status_created 
    ON public.ai_reply_approvals (workspace_id, status, created_at DESC);

-- Approval queue campaign and enrollment cascades
CREATE INDEX IF NOT EXISTS idx_approval_queue_campaign 
    ON public.approval_queue (campaign_id);

CREATE INDEX IF NOT EXISTS idx_approval_queue_enrollment 
    ON public.approval_queue (enrollment_id);

-- ----------------------------------------------------------------------------
-- 3. FLAW-INBOX-DB-3: Outbox Poller Partial Index
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_outbox_events_pending 
    ON public.outbox_events (status, deliver_at) 
    WHERE status = 'pending';

-- ----------------------------------------------------------------------------
-- 4. FLAW-INBOX-DB-4: Multi-Tenant FK Enforcement & Indexing on Objections & Notifications
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    -- Foreign key: lead_objections -> workspaces
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_lead_objections_workspace') THEN
        ALTER TABLE public.lead_objections 
            ADD CONSTRAINT fk_lead_objections_workspace FOREIGN KEY (workspace_id) 
            REFERENCES public.workspaces(id) ON DELETE CASCADE;
    END IF;

    -- Foreign key: notifications -> workspaces
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_notifications_workspace') THEN
        ALTER TABLE public.notifications 
            ADD CONSTRAINT fk_notifications_workspace FOREIGN KEY (workspace_id) 
            REFERENCES public.workspaces(id) ON DELETE CASCADE;
    END IF;

    -- Foreign key: notifications -> outbox_events
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_notifications_outbox_event') THEN
        ALTER TABLE public.notifications 
            ADD CONSTRAINT fk_notifications_outbox_event FOREIGN KEY (outbox_event_id) 
            REFERENCES public.outbox_events(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Indexes for lead_objections
CREATE INDEX IF NOT EXISTS idx_lead_objections_ws_created 
    ON public.lead_objections (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lead_objections_ws_lead 
    ON public.lead_objections (workspace_id, lead_id);

-- Indexes for notifications
CREATE INDEX IF NOT EXISTS idx_notifications_ws_user_read 
    ON public.notifications (workspace_id, user_id, read_at);

CREATE INDEX IF NOT EXISTS idx_notifications_ws_created 
    ON public.notifications (workspace_id, created_at DESC);
