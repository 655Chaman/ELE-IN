-- =====================================================================
-- Migration 004: C1 dequeue function + D new tables
-- Covers: C1 (dequeue_due_leads with FOR UPDATE SKIP LOCKED),
--         D  (suppression_list, lead_tags, ai_generations,
--              enrichment_results, workspace_integrations,
--              voice_notes, profile_activity_snapshots)
-- Safe to re-run — all CREATE IF NOT EXISTS / OR REPLACE guards.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- C1. dequeue_due_leads — atomic batch dequeue with SKIP LOCKED
--     Prevents two workers from grabbing the same lead simultaneously.
--     Sets status = 'processing' atomically; caller MUST always reset
--     to 'pending' (next step), 'completed', or 'failed' — never leave
--     a lead stuck at 'processing'.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.dequeue_due_leads(p_batch_size integer DEFAULT 50)
RETURNS SETOF public.lead_states
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.lead_states
    SET
        status     = 'processing',
        updated_at = now()
    WHERE id IN (
        SELECT id
        FROM public.lead_states
        WHERE status IN ('pending', 'running')
          AND (next_run_at IS NULL OR next_run_at <= now())
        ORDER BY next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;


-- ---------------------------------------------------------------------
-- D1. suppression_list — hard stop for EVERY Tier-3 action
--     Check this before every send, connect, comment, share, voice note.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.suppression_list (
    id            uuid        NOT NULL DEFAULT gen_random_uuid(),
    workspace_id  uuid        NOT NULL DEFAULT public.get_my_workspace_id(),
    linkedin_url  text,
    email         text,
    reason        text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT suppression_list_pkey PRIMARY KEY (id),
    CONSTRAINT suppression_list_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE
);

ALTER TABLE public.suppression_list ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename  = 'suppression_list'
          AND indexname  = 'suppression_list_workspace_linkedin_idx'
    ) THEN
        CREATE INDEX suppression_list_workspace_linkedin_idx
            ON public.suppression_list (workspace_id, linkedin_url);
    END IF;
END $$;

-- RLS policies for suppression_list
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='suppression_list' AND policyname='suppression_list_ws_select') THEN
        CREATE POLICY suppression_list_ws_select ON public.suppression_list FOR SELECT
            USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='suppression_list' AND policyname='suppression_list_ws_insert') THEN
        CREATE POLICY suppression_list_ws_insert ON public.suppression_list FOR INSERT
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='suppression_list' AND policyname='suppression_list_ws_delete') THEN
        CREATE POLICY suppression_list_ws_delete ON public.suppression_list FOR DELETE
            USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- ---------------------------------------------------------------------
-- D2. lead_tags — flexible tagging for leads
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.lead_tags (
    id         uuid        NOT NULL DEFAULT gen_random_uuid(),
    lead_id    uuid        NOT NULL,
    tag        text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT lead_tags_pkey PRIMARY KEY (id),
    CONSTRAINT lead_tags_lead_id_fkey
        FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE,
    CONSTRAINT lead_tags_unique UNIQUE (lead_id, tag)
);

CREATE INDEX IF NOT EXISTS lead_tags_lead_id_idx ON public.lead_tags (lead_id);


-- ---------------------------------------------------------------------
-- D3. ai_generations — audit log for every LLM call
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.ai_generations (
    id           uuid          NOT NULL DEFAULT gen_random_uuid(),
    workspace_id uuid          NOT NULL DEFAULT public.get_my_workspace_id(),
    lead_id      uuid,
    node_id      text,
    prompt       text,
    output       text,
    model        text,
    tokens_used  integer,
    cost         numeric(10,6),
    created_at   timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT ai_generations_pkey PRIMARY KEY (id),
    CONSTRAINT ai_generations_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE,
    CONSTRAINT ai_generations_lead_id_fkey
        FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE SET NULL
);

ALTER TABLE public.ai_generations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='ai_generations' AND policyname='ai_generations_ws_select') THEN
        CREATE POLICY ai_generations_ws_select ON public.ai_generations FOR SELECT
            USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='ai_generations' AND policyname='ai_generations_ws_insert') THEN
        CREATE POLICY ai_generations_ws_insert ON public.ai_generations FOR INSERT
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ai_generations_workspace_lead_idx
    ON public.ai_generations (workspace_id, lead_id);


-- ---------------------------------------------------------------------
-- D4. enrichment_results — cache for third-party enrichment API results
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.enrichment_results (
    id         uuid          NOT NULL DEFAULT gen_random_uuid(),
    lead_id    uuid          NOT NULL,
    provider   text          NOT NULL,
    field      text          NOT NULL,
    value      text,
    cost       numeric(10,6),
    fetched_at timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT enrichment_results_pkey PRIMARY KEY (id),
    CONSTRAINT enrichment_results_lead_id_fkey
        FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS enrichment_results_lead_provider_field_idx
    ON public.enrichment_results (lead_id, provider, field);


-- ---------------------------------------------------------------------
-- D5. workspace_integrations — encrypted third-party credentials store
--     Credentials column must be encrypted same as session_cookies_encrypted.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.workspace_integrations (
    id                    uuid        NOT NULL DEFAULT gen_random_uuid(),
    workspace_id          uuid        NOT NULL DEFAULT public.get_my_workspace_id(),
    provider              text        NOT NULL,
    encrypted_credentials bytea       NOT NULL,
    status                text        NOT NULL DEFAULT 'active',
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT workspace_integrations_pkey PRIMARY KEY (id),
    CONSTRAINT workspace_integrations_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE,
    CONSTRAINT workspace_integrations_unique UNIQUE (workspace_id, provider)
);

ALTER TABLE public.workspace_integrations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='workspace_integrations' AND policyname='workspace_integrations_ws_select') THEN
        CREATE POLICY workspace_integrations_ws_select ON public.workspace_integrations FOR SELECT
            USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='workspace_integrations' AND policyname='workspace_integrations_ws_insert') THEN
        CREATE POLICY workspace_integrations_ws_insert ON public.workspace_integrations FOR INSERT
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='workspace_integrations' AND policyname='workspace_integrations_ws_update') THEN
        CREATE POLICY workspace_integrations_ws_update ON public.workspace_integrations FOR UPDATE
            USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='workspace_integrations' AND policyname='workspace_integrations_ws_delete') THEN
        CREATE POLICY workspace_integrations_ws_delete ON public.workspace_integrations FOR DELETE
            USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- ---------------------------------------------------------------------
-- D6. voice_notes — references to Supabase Storage bucket 'voice-notes'
--     Store the path only; actual audio lives in the storage bucket.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.voice_notes (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    workspace_id     uuid        NOT NULL DEFAULT public.get_my_workspace_id(),
    lead_id          uuid        NOT NULL,
    storage_path     text        NOT NULL,
    duration_seconds integer,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT voice_notes_pkey PRIMARY KEY (id),
    CONSTRAINT voice_notes_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE,
    CONSTRAINT voice_notes_lead_id_fkey
        FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE
);


-- ---------------------------------------------------------------------
-- D7. profile_activity_snapshots — cache for C10 condition nodes
--     Condition nodes (if_recently_active, if_has_recent_posts, etc.)
--     must read from here first; only fall back to live LinkedIn if
--     no snapshot exists or it is older than your staleness threshold.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.profile_activity_snapshots (
    id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
    lead_id             uuid        NOT NULL,
    follower_count      integer,
    mutual_connections  integer,
    has_recent_posts    boolean,
    last_post_date      timestamptz,
    is_recently_active  boolean,
    is_open_profile     boolean,
    is_premium          boolean,
    raw_json            jsonb,
    captured_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT profile_activity_snapshots_pkey PRIMARY KEY (id),
    CONSTRAINT profile_activity_snapshots_lead_id_fkey
        FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS profile_activity_snapshots_lead_captured_idx
    ON public.profile_activity_snapshots (lead_id, captured_at DESC);


COMMIT;
