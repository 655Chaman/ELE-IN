-- ==============================================================================
-- MIGRATION: supabase_master_combined.sql (999_master_pending_sync.sql)
-- PARANOIA FRAMEWORK: Layer 0, Layer 1 & Layer 2
-- Master consolidated, 100% self-contained & idempotent SQL sync script for Supabase.
-- Safe to run on a completely empty database OR an existing/partially-migrated database.
-- ==============================================================================

BEGIN;

-- ==============================================================================
-- 0.0 EXTENSIONS, ENUMS & FOUNDATIONAL CORE TABLES (Idempotent Bootstrap)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available or already installed, skipping...';
END $$;

DO $$ BEGIN CREATE TYPE public.subscription_tier AS ENUM ('FREE', 'PRO', 'ENTERPRISE'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.account_status AS ENUM ('ACTIVE', 'DISCONNECTED', 'RATE_LIMITED', 'BANNED', 'MANUAL_MODE', 'SUSPENDED', 'NEEDS_ATTENTION', 'NEEDS_REVIEW', 'DISABLED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.lead_state_status AS ENUM ('pending', 'running', 'completed', 'exited', 'error'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.message_direction AS ENUM ('inbound', 'outbound'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.approval_status AS ENUM ('pending', 'approved', 'skipped'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.campaign_status AS ENUM ('DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETED', 'ARCHIVED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.lead_status AS ENUM ('extracted','enriching','enriched','enrolled','connected','replied','disqualified','opted_out'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.workspace_member_role AS ENUM ('owner', 'admin', 'member'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.proxy_status AS ENUM ('healthy', 'degraded', 'banned', 'disabled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.outbox_event_status AS ENUM ('pending', 'delivered', 'failed', 'skipped'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE public.template_status AS ENUM ('private', 'pending', 'public', 'rejected'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS public.user_profiles (
    id            UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name  TEXT,
    avatar_url    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.admin_grants (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    granted_by    UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at    TIMESTAMPTZ,
    revoked_by    UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    reason        TEXT
);

CREATE TABLE IF NOT EXISTS public.agencies (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    name               TEXT NOT NULL,
    stripe_customer_id TEXT UNIQUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.workspaces (
    id                    UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id              UUID                     NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    agency_id             UUID                     REFERENCES public.agencies(id) ON DELETE CASCADE,
    name                  TEXT                     NOT NULL,
    tier                  public.subscription_tier NOT NULL DEFAULT 'FREE',
    require_2fa           BOOLEAN                  NOT NULL DEFAULT false,
    stripe_customer_id    TEXT                     UNIQUE,
    status                TEXT                     NOT NULL DEFAULT 'active',
    deletion_requested_at TIMESTAMPTZ,
    created_at            TIMESTAMPTZ              NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ              NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.workspaces
    ADD COLUMN IF NOT EXISTS agency_id UUID REFERENCES public.agencies(id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS public.workspace_members (
    id           UUID                         PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID                         NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id      UUID                         NOT NULL REFERENCES auth.users(id)        ON DELETE CASCADE,
    role         public.workspace_member_role NOT NULL DEFAULT 'member',
    invited_by   UUID                         REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ                  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.agency_members (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id  UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agency_member UNIQUE (agency_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.agency_client_access (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_member_id UUID NOT NULL REFERENCES public.agency_members(id) ON DELETE CASCADE,
    workspace_id     UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_client_access UNIQUE (agency_member_id, workspace_id)
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'my_workspace_ids'
    ) THEN
        EXECUTE $func$
            CREATE OR REPLACE FUNCTION public.my_workspace_ids()
            RETURNS SETOF UUID LANGUAGE sql STABLE SECURITY DEFINER AS $body$
                SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid();
            $body$;
        $func$;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'get_my_workspace_id'
    ) THEN
        EXECUTE $func$
            CREATE OR REPLACE FUNCTION public.get_my_workspace_id()
            RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER AS $body$
                SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid() ORDER BY created_at ASC LIMIT 1;
            $body$;
        $func$;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.workspace_invites (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    role         public.workspace_member_role NOT NULL DEFAULT 'member',
    invited_by   UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token        TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'pending',
    expires_at   TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pending_invite UNIQUE (workspace_id, email)
);

CREATE TABLE IF NOT EXISTS public.workspace_sending_defaults (
    workspace_id                   UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    default_daily_connection_limit INTEGER NOT NULL DEFAULT 20,
    default_daily_message_limit    INTEGER NOT NULL DEFAULT 40,
    default_warmup_target_days     INTEGER NOT NULL DEFAULT 30,
    default_working_hours_start    TIME NOT NULL DEFAULT '08:00',
    default_working_hours_end      TIME NOT NULL DEFAULT '18:00',
    default_timezone               TEXT NOT NULL DEFAULT 'UTC',
    weekend_sending_enabled        BOOLEAN NOT NULL DEFAULT false,
    updated_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.notification_preferences (
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL,
    channel      TEXT NOT NULL,
    enabled      BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (user_id, workspace_id, event_type, channel)
);

CREATE TABLE IF NOT EXISTS public.audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    actor_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action       TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    UUID,
    before_state JSONB,
    after_state  JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.subscriptions (
    id                      UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID                     NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    provider_subscription_id TEXT                    UNIQUE,
    provider_plan_id        TEXT,
    provider                TEXT                     NOT NULL DEFAULT 'mock',
    status                  TEXT                     NOT NULL DEFAULT 'active',
    tier                    public.subscription_tier NOT NULL DEFAULT 'FREE',
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN                  NOT NULL DEFAULT FALSE,
    canceled_at             TIMESTAMPTZ,
    trial_end               TIMESTAMPTZ,
    raw_webhook_event       JSONB,
    created_at              TIMESTAMPTZ              NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ              NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.proxies (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID        REFERENCES public.workspaces(id) ON DELETE CASCADE,
    provider          TEXT        DEFAULT 'custom',
    host              TEXT        NOT NULL,
    port              INTEGER     NOT NULL,
    username          TEXT,
    password          TEXT,
    secret_ref        TEXT,
    protocol          TEXT        NOT NULL DEFAULT 'http',
    country           TEXT,
    country_code      CHAR(2),
    exit_ip           TEXT,
    latency_ms        INTEGER     DEFAULT 0,
    health_score      INTEGER     DEFAULT 100,
    status            TEXT        NOT NULL DEFAULT 'active',
    quarantined_until TIMESTAMPTZ,
    quarantine_reason TEXT,
    failure_count     INTEGER     DEFAULT 0,
    last_checked_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.accounts (
    id                        UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id              UUID                  NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    proxy_id                  UUID                  REFERENCES public.proxies(id)             ON DELETE SET NULL,
    name                      TEXT                  NOT NULL,
    linkedin_profile_url      TEXT,
    cookie_secret_ref         UUID,
    session_cookies_encrypted BYTEA,
    is_warmup                 BOOLEAN               NOT NULL DEFAULT FALSE,
    warmup_start_date         TIMESTAMPTZ,
    warmup_target_days        INTEGER               NOT NULL DEFAULT 30,
    warmup_max_connections    INTEGER               NOT NULL DEFAULT 20,
    warmup_max_messages       INTEGER               NOT NULL DEFAULT 40,
    daily_connection_limit    INTEGER               NOT NULL DEFAULT 20,
    daily_message_limit       INTEGER               NOT NULL DEFAULT 40,
    status                    public.account_status NOT NULL DEFAULT 'ACTIVE',
    is_active                 BOOLEAN               NOT NULL GENERATED ALWAYS AS (status = 'ACTIVE') STORED,
    last_health_check_at      TIMESTAMPTZ,
    cookie_expires_at         TIMESTAMPTZ,
    session_locked_until      TIMESTAMPTZ,
    manual_send_suspected     BOOLEAN               DEFAULT false,
    manual_send_suspected_at  TIMESTAMPTZ,
    created_at                TIMESTAMPTZ           NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ           NOT NULL DEFAULT NOW(),
    CONSTRAINT accounts_workspace_linkedin_unique UNIQUE (workspace_id, linkedin_profile_url)
);

ALTER TABLE IF EXISTS public.accounts
    ADD COLUMN IF NOT EXISTS daily_connection_limit INTEGER NOT NULL DEFAULT 20,
    ADD COLUMN IF NOT EXISTS daily_message_limit INTEGER NOT NULL DEFAULT 40;

CREATE TABLE IF NOT EXISTS public.account_limit_overrides (
    account_id   UUID REFERENCES public.accounts(id) ON DELETE CASCADE,
    action_type  TEXT NOT NULL,
    custom_limit INTEGER NOT NULL,
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (account_id, action_type)
);

CREATE TABLE IF NOT EXISTS public.action_type_limits (
    action_type  TEXT    NOT NULL PRIMARY KEY,
    daily_limit  INTEGER NOT NULL,
    tier         INTEGER NOT NULL DEFAULT 3,
    description  TEXT
);

INSERT INTO public.action_type_limits (action_type, daily_limit, tier, description) VALUES
  ('view_profile',        80,  1, 'Viewing a LinkedIn profile page'),
  ('activity_check',      60,  1, 'Checking profile/post activity (background enrichment)'),
  ('follow_profile',      40,  2, 'Following a LinkedIn member'),
  ('follow_company',      30,  2, 'Following a company page'),
  ('react_post',          40,  2, 'Reacting to a post (like, celebrate, insightful, etc.)'),
  ('endorse_skill',       20,  2, 'Endorsing a skill on a profile'),
  ('comment_post',        10,  3, 'Commenting on a post'),
  ('share_post',           5,  3, 'Sharing / reposting someone''s post'),
  ('connection_request',  20,  3, 'Sending a connection request (with or without note, AI note)'),
  ('withdraw_request',    10,  3, 'Withdrawing a pending connection request'),
  ('message',             40,  3, 'Sending a DM (all message variants, breakup, re-engage, A/B, doc, image)'),
  ('inmail',              10,  3, 'Sending an InMail (standard or paid/sponsored seat)'),
  ('voice_note',           5,  3, 'Sending a LinkedIn voice note'),
  ('remove_connection',   15,  3, 'Removing a 1st-degree connection')
ON CONFLICT (action_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.account_daily_action_counts (
    id           UUID    NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    account_id   UUID    NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    action_type  TEXT    NOT NULL REFERENCES public.action_type_limits(action_type),
    usage_date   DATE    NOT NULL DEFAULT CURRENT_DATE,
    count        INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT account_daily_action_counts_unique UNIQUE (account_id, action_type, usage_date)
);

CREATE OR REPLACE FUNCTION public.get_account_action_limit(p_account_id uuid, p_action_type text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_override_limit integer;
    v_global_limit integer;
    v_is_warmup boolean;
    v_warmup_start_date timestamptz;
    v_warmup_limit integer;
BEGIN
    SELECT custom_limit INTO v_override_limit
    FROM public.account_limit_overrides
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND (expires_at IS NULL OR expires_at > now());

    IF v_override_limit IS NOT NULL THEN
        RETURN v_override_limit;
    END IF;

    SELECT daily_limit INTO v_global_limit
    FROM public.action_type_limits
    WHERE action_type = p_action_type;

    IF v_global_limit IS NULL THEN
        RETURN 20;
    END IF;

    SELECT is_warmup, warmup_start_date INTO v_is_warmup, v_warmup_start_date
    FROM public.accounts
    WHERE id = p_account_id;

    IF v_is_warmup = true AND warmup_start_date IS NOT NULL AND p_action_type IN ('connection_request', 'message', 'inmail') THEN
        v_warmup_limit := 15 + ( GREATEST(0, (CURRENT_DATE - v_warmup_start_date::date)) / 3 ) * 5;
        RETURN LEAST(v_warmup_limit, v_global_limit);
    END IF;

    RETURN v_global_limit;
END;
$$;

CREATE TABLE IF NOT EXISTS public.campaigns (
    id                      UUID                   PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID                   NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name                    TEXT                   NOT NULL,
    status                  public.campaign_status NOT NULL DEFAULT 'DRAFT',
    nodes_json              JSONB                  NOT NULL DEFAULT '[]',
    edges_json              JSONB                  NOT NULL DEFAULT '[]',
    sender_account_ids_json JSONB                  NOT NULL DEFAULT '[]',
    metadata                JSONB                  NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ            NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ            NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.campaign_accounts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    account_id  UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(campaign_id, account_id)
);

CREATE TABLE IF NOT EXISTS public.leads (
    id                  UUID               PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID               NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    first_name          TEXT,
    last_name           TEXT,
    linkedin_url        TEXT               NOT NULL,
    company_name        TEXT,
    email               TEXT,
    domain              TEXT,
    job_title           TEXT,
    company_description TEXT,
    location            TEXT,
    industry            TEXT,
    mutual_connections  TEXT,
    enrichment_source   TEXT               DEFAULT 'csv',
    status              public.lead_status NOT NULL DEFAULT 'extracted',
    metadata            JSONB              NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, linkedin_url)
);

CREATE TABLE IF NOT EXISTS public.lead_lists (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    type         TEXT        NOT NULL DEFAULT 'csv',
    row_count    INTEGER     NOT NULL DEFAULT 0,
    metadata     JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.list_members (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id        UUID NOT NULL REFERENCES public.lead_lists(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL REFERENCES public.leads(id)      ON DELETE CASCADE,
    UNIQUE (list_id, opportunity_id)
);

CREATE TABLE IF NOT EXISTS public.lead_states (
    id              UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID                     NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    opportunity_id  UUID                     NOT NULL REFERENCES public.leads(id)     ON DELETE CASCADE,
    current_node_id TEXT,
    status          public.lead_state_status NOT NULL DEFAULT 'pending',
    next_run_at     TIMESTAMPTZ,
    variables_json  JSONB                    NOT NULL DEFAULT '{}',
    error_reason    TEXT,
    attempts        INTEGER                  NOT NULL DEFAULT 0,
    max_attempts    INTEGER                  NOT NULL DEFAULT 5,
    updated_at      TIMESTAMPTZ              NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ              NOT NULL DEFAULT NOW(),
    UNIQUE (campaign_id, opportunity_id)
);

CREATE TABLE IF NOT EXISTS public.campaign_versions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id  UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    nodes_json   JSONB NOT NULL DEFAULT '[]',
    edges_json   JSONB NOT NULL DEFAULT '[]',
    metadata     JSONB NOT NULL DEFAULT '{}',
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT campaign_versions_id_campaign_id_key UNIQUE (id, campaign_id)
);

CREATE TABLE IF NOT EXISTS public.campaign_enrollments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id         UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    campaign_version_id UUID NOT NULL,
    lead_id             UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    account_id          UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    workspace_id        UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_campaign_enrollments_id_ws UNIQUE (id, workspace_id),
    CONSTRAINT fk_enrollment_version_integrity FOREIGN KEY (campaign_version_id, campaign_id) REFERENCES public.campaign_versions (id, campaign_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_enrollments_id_ws_idx ON public.campaign_enrollments (id, workspace_id);

CREATE TABLE IF NOT EXISTS public.campaign_execution_states (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id    UUID NOT NULL REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE,
    workspace_id     UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    current_node_id  TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    next_run_at      TIMESTAMPTZ,
    variables        JSONB NOT NULL DEFAULT '{}',
    lease_token      TEXT,
    lease_expires_at TIMESTAMPTZ,
    error_reason     TEXT,
    retry_count      INTEGER DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.campaign_node_executions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key     TEXT UNIQUE NOT NULL,
    status              TEXT NOT NULL DEFAULT 'running',
    node_id             TEXT NOT NULL,
    workspace_id        UUID,
    enrollment_id       UUID,
    campaign_version_id UUID,
    node_type           TEXT,
    attempt             INT,
    error_code          TEXT,
    output_payload      JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.messages (
    id                UUID                     PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID                     NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    account_id        UUID                     REFERENCES public.accounts(id)             ON DELETE SET NULL,
    lead_id           UUID                     REFERENCES public.leads(id)                ON DELETE SET NULL,
    sender_name       TEXT                     NOT NULL,
    message_text      TEXT                     NOT NULL,
    direction         public.message_direction NOT NULL,
    intent            TEXT                     NOT NULL DEFAULT 'unknown',
    intent_confidence FLOAT                    NOT NULL DEFAULT 0.0,
    thread_url        TEXT,
    created_at        TIMESTAMPTZ              NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ              NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.daily_campaign_stats (
    id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID    NOT NULL REFERENCES public.workspaces(id)  ON DELETE CASCADE,
    campaign_id      UUID    NOT NULL REFERENCES public.campaigns(id)   ON DELETE CASCADE,
    stat_date        DATE    NOT NULL,
    connections_sent INTEGER NOT NULL DEFAULT 0,
    messages_sent    INTEGER NOT NULL DEFAULT 0,
    accepted         INTEGER NOT NULL DEFAULT 0,
    replied          INTEGER NOT NULL DEFAULT 0,
    UNIQUE (campaign_id, stat_date)
);

CREATE TABLE IF NOT EXISTS public.templates (
    id           UUID                   PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID                   REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name         TEXT                   NOT NULL,
    description  TEXT,
    nodes_json   JSONB                  NOT NULL DEFAULT '[]',
    edges_json   JSONB                  NOT NULL DEFAULT '[]',
    status       public.template_status NOT NULL DEFAULT 'private',
    tags         TEXT[]                 DEFAULT '{}',
    downloads    INTEGER                NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ            NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ            NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.api_keys (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID        NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    key_hash     TEXT        NOT NULL UNIQUE,
    key_prefix   TEXT        NOT NULL,
    last_used_at TIMESTAMPTZ,
    expires_at   TIMESTAMPTZ,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.personas (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    pain_points   JSONB DEFAULT '[]'::jsonb,
    value_prop    TEXT DEFAULT '',
    target_titles JSONB DEFAULT '[]'::jsonb,
    tone_tweaks   TEXT DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.objections (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    trigger      TEXT NOT NULL,
    playbook     TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.knowledge_assets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    type         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'synced',
    source_url   TEXT,
    raw_text     TEXT,
    error_msg    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.knowledge_synthesis (
    workspace_id    UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    core_value_prop TEXT,
    identified_tone JSONB DEFAULT '[]'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.processing_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    asset_id        UUID REFERENCES public.knowledge_assets(id) ON DELETE CASCADE,
    job_type        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    payload         JSONB NOT NULL DEFAULT '{}',
    idempotency_key TEXT,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.workspace_usage (
    workspace_id             UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    ai_requests_this_month   INT DEFAULT 0 NOT NULL,
    leads_scraped_this_month INT DEFAULT 0 NOT NULL,
    billing_tier             TEXT DEFAULT 'free' NOT NULL,
    updated_at               TIMESTAMPTZ DEFAULT timezone('utc', now()) NOT NULL
);

-- 0.1 Workspaces Core Schema Extensions
ALTER TABLE IF EXISTS public.workspaces
    ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'FREE',
    ADD COLUMN IF NOT EXISTS data_cleaning_credits BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS billing_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS auto_recharge_settings JSONB DEFAULT '{
        "enabled": false,
        "threshold_credits": 100,
        "recharge_package_id": "credits_1000",
        "max_monthly_recharges": 5,
        "recharges_this_month": 0,
        "last_recharged_at": null
    }'::jsonb,
    ADD COLUMN IF NOT EXISTS webhook_signing_secret TEXT,
    ADD COLUMN IF NOT EXISTS sending_window JSONB DEFAULT '{
        "start": "09:00",
        "end": "18:00",
        "timezone": "UTC",
        "days": ["mon", "tue", "wed", "thu", "fri"]
    }'::jsonb;

-- 0.2 Proxies & SSRF /24 Subnet Isolation
CREATE TABLE IF NOT EXISTS public.proxies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT,
    password TEXT,
    protocol TEXT DEFAULT 'http',
    country TEXT,
    exit_ip TEXT,
    latency_ms INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    quarantined_until TIMESTAMPTZ,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proxies_workspace ON public.proxies(workspace_id);
ALTER TABLE IF EXISTS public.proxies ADD COLUMN IF NOT EXISTS password TEXT, ADD COLUMN IF NOT EXISTS country TEXT, ADD COLUMN IF NOT EXISTS exit_ip TEXT, ADD COLUMN IF NOT EXISTS latency_ms INTEGER DEFAULT 0, ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ, ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_proxies_active ON public.proxies(workspace_id, status);

ALTER TABLE public.proxies ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'proxies' AND policyname = 'proxies_ws_policy') THEN
        CREATE POLICY proxies_ws_policy ON public.proxies FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- Add proxy affiliation columns to accounts
ALTER TABLE IF EXISTS public.accounts
    ADD COLUMN IF NOT EXISTS proxy_id UUID REFERENCES public.proxies(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS proxy_country TEXT,
    ADD COLUMN IF NOT EXISTS health_score NUMERIC DEFAULT 100,
    ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ;

-- 0.3 Outbox Notification Queue (Exponential Backoff & Dead Letter Queue)
CREATE TABLE IF NOT EXISTS public.outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending',
    deliver_at TIMESTAMPTZ DEFAULT NOW(),
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.outbox_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_outbox_events_poll ON public.outbox_events(status, deliver_at);
CREATE INDEX IF NOT EXISTS idx_outbox_events_workspace ON public.outbox_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_events_dlq ON public.outbox_events(workspace_id, status);

ALTER TABLE public.outbox_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'outbox_events' AND policyname = 'outbox_events_ws_policy') THEN
        CREATE POLICY outbox_events_ws_policy ON public.outbox_events FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.4 Suppression List (Do-Not-Contact / DNC Engine)
CREATE TABLE IF NOT EXISTS public.suppression_list (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    linkedin_url TEXT,
    email TEXT,
    domain TEXT,
    value TEXT,
    reason TEXT DEFAULT 'manual_dnc',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.suppression_list ADD COLUMN IF NOT EXISTS linkedin_url TEXT, ADD COLUMN IF NOT EXISTS email TEXT, ADD COLUMN IF NOT EXISTS domain TEXT, ADD COLUMN IF NOT EXISTS value TEXT, ADD COLUMN IF NOT EXISTS reason TEXT DEFAULT 'manual_dnc';
CREATE INDEX IF NOT EXISTS idx_suppression_workspace ON public.suppression_list(workspace_id);
CREATE INDEX IF NOT EXISTS idx_suppression_li_url ON public.suppression_list(workspace_id, linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppression_email ON public.suppression_list(workspace_id, email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppression_domain ON public.suppression_list(workspace_id, domain) WHERE domain IS NOT NULL;

ALTER TABLE public.suppression_list ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'suppression_list' AND policyname = 'suppression_list_ws_policy') THEN
        CREATE POLICY suppression_list_ws_policy ON public.suppression_list FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.5 Sender Pods & Load Balancing
CREATE TABLE IF NOT EXISTS public.sender_pods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    rotation_strategy TEXT DEFAULT 'round_robin',
    max_daily_invites_per_pod INTEGER DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.sender_pod_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pod_id UUID NOT NULL REFERENCES public.sender_pods(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    workspace_id UUID NOT NULL,
    weight INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_pod_account UNIQUE(pod_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_sender_pods_workspace ON public.sender_pods(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sender_pod_acc_lookup ON public.sender_pod_accounts(workspace_id, pod_id, is_active);

ALTER TABLE public.sender_pods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sender_pod_accounts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'sender_pods' AND policyname = 'sender_pods_ws_policy') THEN
        CREATE POLICY sender_pods_ws_policy ON public.sender_pods FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'sender_pod_accounts' AND policyname = 'sender_pod_accounts_ws_policy') THEN
        CREATE POLICY sender_pod_accounts_ws_policy ON public.sender_pod_accounts FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.6 Worker Heartbeat & Action Audit Log
CREATE TABLE IF NOT EXISTS public.worker_heartbeat (
    worker_id TEXT PRIMARY KEY,
    last_beat_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'alive',
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS public.action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    execution_state_id TEXT,
    action_type TEXT NOT NULL,
    result TEXT NOT NULL,
    error_detail TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.action_log ADD COLUMN IF NOT EXISTS execution_state_id TEXT, ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_action_log_workspace ON public.action_log(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_exec_state ON public.action_log(execution_state_id);

ALTER TABLE public.worker_heartbeat ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.action_log ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'worker_heartbeat' AND policyname = 'worker_heartbeat_service_policy') THEN
        CREATE POLICY worker_heartbeat_service_policy ON public.worker_heartbeat FOR ALL USING (auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'action_log' AND policyname = 'action_log_ws_policy') THEN
        CREATE POLICY action_log_ws_policy ON public.action_log FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.7 Social Signal Cache
CREATE TABLE IF NOT EXISTS public.social_signal_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    linkedin_url TEXT NOT NULL,
    signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_social_signal_lead UNIQUE(workspace_id, linkedin_url)
);

CREATE INDEX IF NOT EXISTS idx_social_signal_lookup ON public.social_signal_cache(workspace_id, linkedin_url, expires_at);

ALTER TABLE public.social_signal_cache ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'social_signal_cache' AND policyname = 'social_signal_cache_ws_policy') THEN
        CREATE POLICY social_signal_cache_ws_policy ON public.social_signal_cache FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.8 Outbound Webhook Endpoints & Deliveries
CREATE TABLE IF NOT EXISTS public.webhook_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    url TEXT NOT NULL,
    events TEXT[] NOT NULL DEFAULT '{}',
    signing_secret TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    endpoint_id UUID REFERENCES public.webhook_endpoints(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    next_retry_at TIMESTAMPTZ DEFAULT NOW(),
    response_status INTEGER,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.webhook_endpoints ADD COLUMN IF NOT EXISTS events TEXT[] DEFAULT '{}', ADD COLUMN IF NOT EXISTS signing_secret TEXT, ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active', ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0, ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE IF EXISTS public.webhook_deliveries ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending', ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0, ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ DEFAULT NOW(), ADD COLUMN IF NOT EXISTS response_status INTEGER, ADD COLUMN IF NOT EXISTS last_error TEXT;
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_poll ON public.webhook_deliveries(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint ON public.webhook_deliveries(endpoint_id, created_at DESC);

ALTER TABLE public.webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhook_deliveries ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'webhook_endpoints' AND policyname = 'webhook_endpoints_ws_policy') THEN
        CREATE POLICY webhook_endpoints_ws_policy ON public.webhook_endpoints FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'webhook_deliveries' AND policyname = 'webhook_deliveries_ws_policy') THEN
        CREATE POLICY webhook_deliveries_ws_policy ON public.webhook_deliveries FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.9 AI Reply Approval Queue
CREATE TABLE IF NOT EXISTS public.approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id TEXT,
    account_id TEXT,
    exec_state_id TEXT,
    generated_reply TEXT,
    ai_draft TEXT,
    sender_name TEXT,
    status TEXT DEFAULT 'pending',
    token TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.approval_queue ADD COLUMN IF NOT EXISTS lead_id TEXT, ADD COLUMN IF NOT EXISTS exec_state_id TEXT, ADD COLUMN IF NOT EXISTS generated_reply TEXT, ADD COLUMN IF NOT EXISTS token TEXT, ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_approval_queue_workspace ON public.approval_queue(workspace_id, status);

ALTER TABLE public.approval_queue ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'approval_queue' AND policyname = 'approval_queue_ws_policy') THEN
        CREATE POLICY approval_queue_ws_policy ON public.approval_queue FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 0.10 Campaign Execution States & Leads Lifecycle Columns
ALTER TABLE IF EXISTS public.campaign_execution_states
    ADD COLUMN IF NOT EXISTS lease_token TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS error_reason TEXT,
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_ces_lease_token ON public.campaign_execution_states(lease_token) WHERE lease_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ces_next_run ON public.campaign_execution_states(workspace_id, status, next_run_at) WHERE status = 'pending';

ALTER TABLE IF EXISTS public.leads
    ADD COLUMN IF NOT EXISTS is_unsubscribed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_leads_workspace_email ON public.leads(workspace_id, email);
CREATE INDEX IF NOT EXISTS idx_leads_workspace_li ON public.leads(workspace_id, linkedin_url);

-- 1. BILLING TRANSACTIONS TABLE & INDEXES
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.billing_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'usd',
    status TEXT NOT NULL DEFAULT 'succeeded',
    provider TEXT NOT NULL,
    provider_tx_id TEXT UNIQUE,
    package_id TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.billing_transactions ADD COLUMN IF NOT EXISTS package_id TEXT;
ALTER TABLE public.billing_transactions ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_billing_transactions_workspace ON public.billing_transactions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_billing_transactions_created ON public.billing_transactions(workspace_id, created_at DESC);

ALTER TABLE public.billing_transactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own workspace billing transactions" ON public.billing_transactions;
CREATE POLICY "Users can view own workspace billing transactions"
    ON public.billing_transactions FOR SELECT
    USING (workspace_id IN (SELECT public.my_workspace_ids()));


-- ==============================================================================
-- 2. CHECKOUT SESSIONS TABLE & INDEXES
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.checkout_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    package_id TEXT NOT NULL,
    credits INT NOT NULL DEFAULT 0,
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkout_sessions_workspace ON public.checkout_sessions(workspace_id);

ALTER TABLE public.checkout_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own checkout sessions" ON public.checkout_sessions;
CREATE POLICY "Users can view own checkout sessions" 
    ON public.checkout_sessions FOR SELECT 
    USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Webhook Idempotency Registry
CREATE TABLE IF NOT EXISTS public.processed_webhook_events (
    event_id TEXT,
    provider TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (event_id, provider)
);
ALTER TABLE public.processed_webhook_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'processed_webhook_events' AND policyname = 'processed_webhook_events_service_role_policy') THEN
        CREATE POLICY processed_webhook_events_service_role_policy ON public.processed_webhook_events FOR ALL USING (auth.role() = 'service_role');
    END IF;
END $$;


-- ==============================================================================
-- 3. ADD CREDITS SAFELY RPC FUNCTION
-- ==============================================================================
ALTER TABLE public.workspaces ADD COLUMN IF NOT EXISTS data_cleaning_credits INT NOT NULL DEFAULT 0;

DROP FUNCTION IF EXISTS public.add_credits_safely(UUID, INT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.add_credits_safely(UUID, INT, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.add_credits_safely(
    p_workspace_id UUID,
    p_credits INT,
    p_event_id TEXT,
    p_provider TEXT
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_current_balance INT;
    v_new_balance INT;
    v_already_processed BOOLEAN;
BEGIN
    -- Lock workspace row to serialize credit additions
    SELECT data_cleaning_credits INTO v_current_balance
    FROM public.workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', 0,
            'reason', 'workspace_not_found'
        );
    END IF;

    v_current_balance := COALESCE(v_current_balance, 0);

    -- Check idempotency via billing_transactions provider_tx_id
    SELECT EXISTS (
        SELECT 1 FROM public.billing_transactions
        WHERE provider_tx_id = p_event_id
    ) INTO v_already_processed;

    IF v_already_processed THEN
        RETURN jsonb_build_object(
            'success', true,
            'balance', v_current_balance,
            'already_processed', true,
            'reason', 'event_already_processed'
        );
    END IF;

    -- Update balance
    v_new_balance := v_current_balance + p_credits;

    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance,
        updated_at = NOW()
    WHERE id = p_workspace_id;

    -- Record transaction
    INSERT INTO public.billing_transactions (
        workspace_id,
        amount,
        currency,
        status,
        provider,
        provider_tx_id,
        metadata
    ) VALUES (
        p_workspace_id,
        p_credits::numeric,
        'usd',
        'succeeded',
        p_provider,
        p_event_id,
        jsonb_build_object('credits_added', p_credits)
    );

    RETURN jsonb_build_object(
        'success', true,
        'balance', v_new_balance,
        'added', p_credits,
        'already_processed', false
    );
END;
$$;


-- ---------------------------------------------------------------------
-- 3B. CREDIT DEDUCTIONS & ACTION COSTS
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credit_deductions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    action_type       TEXT NOT NULL,
    amount            INT NOT NULL,
    balance_after     INT NOT NULL,
    idempotency_key   TEXT UNIQUE NOT NULL,
    metadata          JSONB DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_deductions_workspace_created ON public.credit_deductions(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_deductions_workspace_action ON public.credit_deductions(workspace_id, action_type);

ALTER TABLE public.credit_deductions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own workspace credit deductions" ON public.credit_deductions;
CREATE POLICY "Users can view their own workspace credit deductions"
    ON public.credit_deductions FOR SELECT
    USING (workspace_id IN (SELECT public.my_workspace_ids()));

CREATE TABLE IF NOT EXISTS public.credit_action_costs (
    action_type   TEXT PRIMARY KEY,
    credits       INT NOT NULL,
    description   TEXT,
    category      TEXT NOT NULL DEFAULT 'general',
    is_active     BOOLEAN NOT NULL DEFAULT true,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.credit_action_costs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view active credit costs" ON public.credit_action_costs;
CREATE POLICY "Anyone can view active credit costs"
    ON public.credit_action_costs FOR SELECT
    USING (true);

INSERT INTO public.credit_action_costs (action_type, credits, description, category, is_active)
VALUES 
    ('lead_enrichment', 5, 'Full profile waterfall enrichment', 'enrichment', true),
    ('email_discovery', 3, 'Find and verify professional email', 'enrichment', true),
    ('phone_lookup', 10, 'Verified direct dial mobile lookup', 'enrichment', true),
    ('ai_personalization', 2, 'LLM hyper-personalized icebreaker generation', 'ai', true),
    ('ai_reply_generation', 2, 'Context-aware objection handling and reply', 'ai', true),
    ('displacement_pitch', 2, 'AI Competitor Displacement Pitch Generation', 'displacement', true),
    ('social_prewarm_comment', 1, 'AI Contextual Social Pre-Warm Comment', 'social', true),
    ('thought_leadership_post', 2, 'AI Thought Leadership Post Generation', 'social', true),
    ('multimodal_voice_script', 2, 'AI Conversational Voice Drop Script', 'multimodal', true),
    ('multimodal_video_card', 3, 'AI Video Prospecting Card Generation', 'multimodal', true)
ON CONFLICT (action_type) DO NOTHING;

DROP FUNCTION IF EXISTS public.deduct_credits_safely(UUID, INT, TEXT, TEXT, JSONB);
CREATE OR REPLACE FUNCTION public.deduct_credits_safely(
    p_workspace_id UUID,
    p_amount INT,
    p_action_type TEXT,
    p_idempotency_key TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_current_balance INT;
    v_tier TEXT;
    v_min_balance INT := 0;
    v_actual_cost INT;
    v_new_balance INT;
    v_already_processed BOOLEAN;
BEGIN
    SELECT data_cleaning_credits, COALESCE(tier::TEXT, 'FREE')
    INTO v_current_balance, v_tier
    FROM public.workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', 0,
            'reason', 'workspace_not_found',
            'error', 'workspace_not_found'
        );
    END IF;

    v_current_balance := COALESCE(v_current_balance, 0);
    v_tier := UPPER(COALESCE(v_tier, 'FREE'));

    IF v_tier IN ('PRO', 'GROWTH', 'ENTERPRISE', 'AGENCY', 'UNLIMITED', 'SCALE') THEN
        v_min_balance := -500;
    ELSE
        v_min_balance := 0;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM public.credit_deductions 
        WHERE idempotency_key = p_idempotency_key
    ) INTO v_already_processed;

    IF v_already_processed THEN
        SELECT balance_after INTO v_new_balance FROM public.credit_deductions WHERE idempotency_key = p_idempotency_key;
        RETURN jsonb_build_object(
            'success', true,
            'balance', v_new_balance,
            'reason', 'already_processed',
            'already_processed', true
        );
    END IF;

    IF p_amount = 0 THEN
        SELECT credits INTO v_actual_cost
        FROM public.credit_action_costs
        WHERE action_type = p_action_type AND is_active = true;
        
        v_actual_cost := COALESCE(v_actual_cost, 0);
    ELSE
        v_actual_cost := p_amount;
    END IF;

    v_new_balance := v_current_balance - v_actual_cost;
    IF v_new_balance < v_min_balance THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', v_current_balance,
            'reason', 'insufficient_credits',
            'error', 'insufficient_credits',
            'shortfall', (v_min_balance - v_new_balance),
            'min_allowed', v_min_balance
        );
    END IF;

    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance,
        updated_at = NOW()
    WHERE id = p_workspace_id;

    INSERT INTO public.credit_deductions (
        workspace_id, action_type, amount, balance_after, idempotency_key, metadata
    ) VALUES (
        p_workspace_id, p_action_type, v_actual_cost, v_new_balance, p_idempotency_key, p_metadata
    );

    RETURN jsonb_build_object(
        'success', true,
        'balance', v_new_balance,
        'reason', 'ok'
    );
END;
$$;

DROP FUNCTION IF EXISTS public.get_credit_balance(UUID);
CREATE OR REPLACE FUNCTION public.get_credit_balance(
    p_workspace_id UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_balance INT;
    v_tier TEXT;
    v_usage JSONB;
BEGIN
    SELECT data_cleaning_credits, tier::TEXT INTO v_balance, v_tier
    FROM public.workspaces WHERE id = p_workspace_id;
    
    v_balance := COALESCE(v_balance, 0);

    SELECT COALESCE(jsonb_object_agg(action_type, total_amount), '{}'::jsonb) INTO v_usage
    FROM (
        SELECT action_type, SUM(amount) as total_amount
        FROM public.credit_deductions
        WHERE workspace_id = p_workspace_id
          AND date_trunc('month', created_at) = date_trunc('month', NOW())
        GROUP BY action_type
    ) sub;

    RETURN jsonb_build_object(
        'balance', v_balance,
        'tier', COALESCE(v_tier, 'free'),
        'usage_this_month', v_usage
    );
END;
$$;


-- ==============================================================================
-- 4. THREAD_URL ON MESSAGES AND APPROVAL_QUEUE
-- ==============================================================================
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS thread_url TEXT;
ALTER TABLE public.approval_queue ADD COLUMN IF NOT EXISTS thread_url TEXT;


-- ==============================================================================
-- 5. SOURCE, COUNTRY_CODE, LABEL, IS_ACTIVE ON PROXIES
-- ==============================================================================
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS country_code CHAR(2);
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS label TEXT;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;


-- ==============================================================================
-- 6. IDEMPOTENCY_KEY ON PROCESSING_JOBS
-- ==============================================================================
ALTER TABLE public.processing_jobs ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'uq_processing_jobs_idempotency' AND n.nspname = 'public'
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_processing_jobs_idempotency ON public.processing_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;
    END IF;
END $$;


-- ==============================================================================
-- 7. UQ_CAMPAIGN_LEAD_ENROLLMENT CONSTRAINT ON CAMPAIGN_ENROLLMENTS
-- ==============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'uq_campaign_lead_enrollment' AND table_name = 'campaign_enrollments'
    ) THEN
        ALTER TABLE public.campaign_enrollments
        ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
    END IF;
END $$;


-- ==============================================================================
-- 8. PERSONAS COLUMNS & KNOWLEDGE_ASSETS.RAW_TEXT
-- ==============================================================================
ALTER TABLE public.personas 
ADD COLUMN IF NOT EXISTS value_prop TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS target_titles JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS tone_tweaks TEXT DEFAULT '';

ALTER TABLE public.knowledge_assets
ADD COLUMN IF NOT EXISTS raw_text TEXT;

-- Migration 070: Knowledge Objections Playbook Registry
CREATE TABLE IF NOT EXISTS public.knowledge_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    trigger TEXT NOT NULL,
    playbook TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_objections_workspace ON public.knowledge_objections(workspace_id);

ALTER TABLE public.knowledge_objections ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'knowledge_objections' AND policyname = 'Users can manage their own workspace objections'
    ) THEN
        CREATE POLICY "Users can manage their own workspace objections"
        ON public.knowledge_objections FOR ALL
        USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- ==============================================================================
-- 9. ICP_SIGNAL_WEIGHTS TABLE & RECORD_BAYESIAN_ICP_OUTCOME RPC
-- ==============================================================================
CREATE TABLE IF NOT EXISTS public.icp_signal_weights (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    signal_name text NOT NULL,
    prior_alpha integer NOT NULL DEFAULT 2,
    prior_beta integer NOT NULL DEFAULT 2,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT icp_signal_weights_workspace_signal_key UNIQUE (workspace_id, signal_name)
);

CREATE INDEX IF NOT EXISTS idx_icp_signal_weights_workspace ON public.icp_signal_weights(workspace_id);

ALTER TABLE public.icp_signal_weights ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS icp_signal_weights_ws_all ON public.icp_signal_weights;
CREATE POLICY icp_signal_weights_ws_all ON public.icp_signal_weights FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));

DROP FUNCTION IF EXISTS public.record_bayesian_icp_outcome(uuid, text, text);
CREATE OR REPLACE FUNCTION public.record_bayesian_icp_outcome(
    p_workspace_id uuid,
    p_signal_name text,
    p_outcome text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_alpha integer;
    v_beta integer;
BEGIN
    INSERT INTO public.icp_signal_weights (workspace_id, signal_name, prior_alpha, prior_beta)
    VALUES (p_workspace_id, p_signal_name, 2, 2)
    ON CONFLICT (workspace_id, signal_name) DO NOTHING;

    SELECT prior_alpha, prior_beta INTO v_alpha, v_beta
    FROM public.icp_signal_weights
    WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;

    -- Damping: when total observations reach 200, scale down to maintain responsiveness
    IF (COALESCE(v_alpha, 2) + COALESCE(v_beta, 2)) >= 200 THEN
        UPDATE public.icp_signal_weights
        SET prior_alpha = GREATEST(2, (prior_alpha * 0.5)::integer),
            prior_beta = GREATEST(2, (prior_beta * 0.5)::integer),
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    END IF;

    IF p_outcome = 'won' THEN
        UPDATE public.icp_signal_weights
        SET prior_alpha = prior_alpha + 1,
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    ELSIF p_outcome = 'lost' THEN
        UPDATE public.icp_signal_weights
        SET prior_beta = prior_beta + 1,
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    END IF;
END;
$$;

-- ==============================================================================
-- 10. RELEASE CONSUMED DAILY ACTION RPC FUNCTION
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.release_consumed_daily_action(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.account_daily_action_counts
    SET count = GREATEST(0, count - 1)
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = CURRENT_DATE;
    RETURN true;
END;
$$;



-- Migration 072: Timezone-aware daily action consumption and reversal
DROP FUNCTION IF EXISTS public.try_consume_daily_action(uuid, text);
DROP FUNCTION IF EXISTS public.try_consume_daily_action(uuid, text, date);
CREATE OR REPLACE FUNCTION public.try_consume_daily_action(
    p_account_id  uuid,
    p_action_type text,
    p_usage_date  date DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit integer;
    v_new_count integer;
    v_date date;
BEGIN
    v_date := COALESCE(p_usage_date, CURRENT_DATE);
    v_limit := public.get_account_action_limit(p_account_id, p_action_type);
    
    -- Step 1: Ensure the daily row exists (starts at 0)
    INSERT INTO public.account_daily_action_counts (account_id, action_type, usage_date, count)
    VALUES (p_account_id, p_action_type, v_date, 0)
    ON CONFLICT (account_id, action_type, usage_date) DO NOTHING;

    -- Step 2: Atomically increment ONLY if it remains under the limit
    UPDATE public.account_daily_action_counts
    SET count = count + 1
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = v_date
      AND count < v_limit
    RETURNING count INTO v_new_count;

    -- Step 3: If v_new_count is NULL, the WHERE clause (count < limit) failed
    IF v_new_count IS NULL THEN
        RETURN false;
    END IF;

    RETURN true;
END;
$$;

DROP FUNCTION IF EXISTS public.release_consumed_daily_action(uuid, text);
DROP FUNCTION IF EXISTS public.release_consumed_daily_action(uuid, text, date);
CREATE OR REPLACE FUNCTION public.release_consumed_daily_action(
    p_account_id  uuid,
    p_action_type text,
    p_usage_date  date DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_date date;
BEGIN
    v_date := COALESCE(p_usage_date, CURRENT_DATE);
    UPDATE public.account_daily_action_counts
    SET count = GREATEST(0, count - 1)
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = v_date;
    RETURN true;
END;
$$;

-- ==============================================================================
-- 14. AGENCY WHITE-LABEL & CLIENT TELEMETRY (Migration 073)
-- ==============================================================================
ALTER TABLE public.agencies 
ADD COLUMN IF NOT EXISTS whitelabel_brand TEXT DEFAULT 'Ele-in Agency',
ADD COLUMN IF NOT EXISTS whitelabel_domain TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS whitelabel_color TEXT DEFAULT '#6366f1',
ADD COLUMN IF NOT EXISTS whitelabel_logo_url TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS whitelabel_enabled BOOLEAN DEFAULT true;

DROP FUNCTION IF EXISTS public.get_agency_clients_overview(UUID);
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
            COUNT(*) FILTER (WHERE status::text IN ('ACTIVE', 'active')) AS active_camp_count
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
        WHERE status::text IN ('ACTIVE', 'connected', 'active', 'valid')
        GROUP BY workspace_id
    ) a ON a.workspace_id = w.id
    WHERE w.agency_id = p_agency_id
    ORDER BY w.created_at DESC;
END;
$$;



-- Migration 074: Proxy Latency, Exit IP & Account Health Telemetry

ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS latency_ms INTEGER;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS exit_ip TEXT;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS health_score INTEGER DEFAULT 100;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS auto_heal_status TEXT;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS auto_heal_actions JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS health_score INTEGER DEFAULT 100;



-- Migration 076: Workspace AI Gateway & BYOK Configuration

CREATE TABLE IF NOT EXISTS public.workspace_ai_settings (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    default_model TEXT NOT NULL DEFAULT 'Auto-Route (Recommended)',
    byok_provider TEXT,
    byok_key_ciphertext TEXT,
    byok_key_last_chars TEXT,
    temperature NUMERIC DEFAULT 0.7,
    max_tokens_budget INTEGER DEFAULT 2000000,
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.workspace_ai_settings ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'workspace_ai_settings' AND policyname = 'workspace_ai_settings_workspace_isolation'
    ) THEN
        CREATE POLICY workspace_ai_settings_workspace_isolation ON public.workspace_ai_settings
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;



-- Migration 077: Proxy Quarantine & Sticky Geo-Affinity

ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_proxies_quarantined ON public.proxies(status, quarantined_until);



-- Migration 077b: Workspace Credit Auto-Recharge & In-Flight Overdraft Replenishment

CREATE TABLE IF NOT EXISTS public.workspace_auto_recharge_settings (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT false,
    threshold_credits INTEGER NOT NULL DEFAULT 100,
    recharge_package_id TEXT NOT NULL DEFAULT 'credits_1000',
    max_monthly_recharges INTEGER NOT NULL DEFAULT 5,
    recharges_this_month INTEGER NOT NULL DEFAULT 0,
    last_recharged_at TIMESTAMPTZ,
    last_reset_month TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workspace_auto_recharge_enabled ON public.workspace_auto_recharge_settings(enabled);

ALTER TABLE public.workspace_auto_recharge_settings ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'workspace_auto_recharge_settings' 
    AND policyname = 'workspace_auto_recharge_settings_isolation'
  ) THEN
    CREATE POLICY workspace_auto_recharge_settings_isolation ON public.workspace_auto_recharge_settings
      FOR ALL USING (true);
  END IF;
END $$;



-- Migration 078: Agency Credit Delegations & Sub-Account Quota Management

ALTER TABLE public.agencies 
ADD COLUMN IF NOT EXISTS master_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;

ALTER TABLE public.workspaces
ADD COLUMN IF NOT EXISTS allocated_credit_budget INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS monthly_credit_quota INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS exhaustion_alert_threshold INT NOT NULL DEFAULT 100;

CREATE TABLE IF NOT EXISTS public.agency_credit_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    client_workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    from_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    amount INT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'manual_allocation',
    allocated_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agency_allocations_agency_id ON public.agency_credit_allocations(agency_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agency_allocations_client_ws ON public.agency_credit_allocations(client_workspace_id);

ALTER TABLE public.agency_credit_allocations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'agency_credit_allocations' 
    AND policyname = 'agency_credit_allocations_isolation'
  ) THEN
    CREATE POLICY agency_credit_allocations_isolation ON public.agency_credit_allocations
      FOR ALL USING (true);
  END IF;
END $$;

DROP FUNCTION IF EXISTS public.transfer_agency_credits_safely(UUID, UUID, UUID, INT, TEXT, UUID, TEXT);
CREATE OR REPLACE FUNCTION public.transfer_agency_credits_safely(
    p_agency_id UUID,
    p_from_workspace_id UUID,
    p_to_workspace_id UUID,
    p_amount INT,
    p_action_type TEXT,
    p_allocated_by UUID,
    p_note TEXT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_from_balance INT;
    v_to_balance INT;
    v_new_from_balance INT;
    v_new_to_balance INT;
BEGIN
    IF p_amount <= 0 THEN
        RETURN jsonb_build_object('success', false, 'reason', 'invalid_amount');
    END IF;

    IF p_from_workspace_id < p_to_workspace_id THEN
        SELECT data_cleaning_credits INTO v_from_balance FROM public.workspaces WHERE id = p_from_workspace_id FOR UPDATE;
        SELECT data_cleaning_credits INTO v_to_balance FROM public.workspaces WHERE id = p_to_workspace_id FOR UPDATE;
    ELSE
        SELECT data_cleaning_credits INTO v_to_balance FROM public.workspaces WHERE id = p_to_workspace_id FOR UPDATE;
        SELECT data_cleaning_credits INTO v_from_balance FROM public.workspaces WHERE id = p_from_workspace_id FOR UPDATE;
    END IF;

    IF v_from_balance IS NULL OR v_to_balance IS NULL THEN
        RETURN jsonb_build_object('success', false, 'reason', 'workspace_not_found');
    END IF;

    IF v_from_balance < p_amount THEN
        RETURN jsonb_build_object('success', false, 'reason', 'insufficient_balance', 'available', v_from_balance);
    END IF;

    v_new_from_balance := v_from_balance - p_amount;
    v_new_to_balance := v_to_balance + p_amount;

    UPDATE public.workspaces SET data_cleaning_credits = v_new_from_balance WHERE id = p_from_workspace_id;
    UPDATE public.workspaces SET data_cleaning_credits = v_new_to_balance WHERE id = p_to_workspace_id;

    IF p_action_type = 'manual_allocation' OR p_action_type = 'monthly_recurring' THEN
        UPDATE public.workspaces 
        SET allocated_credit_budget = allocated_credit_budget + p_amount 
        WHERE id = p_to_workspace_id;
    ELSIF p_action_type = 'reclaim' THEN
        UPDATE public.workspaces 
        SET allocated_credit_budget = GREATEST(0, allocated_credit_budget - p_amount) 
        WHERE id = p_from_workspace_id;
    END IF;

    INSERT INTO public.agency_credit_allocations (
        agency_id, client_workspace_id, from_workspace_id, amount, action_type, allocated_by, note
    ) VALUES (
        p_agency_id, 
        CASE WHEN p_action_type = 'reclaim' THEN p_from_workspace_id ELSE p_to_workspace_id END,
        p_from_workspace_id,
        CASE WHEN p_action_type = 'reclaim' THEN -p_amount ELSE p_amount END,
        p_action_type,
        p_allocated_by,
        p_note
    );

    RETURN jsonb_build_object(
        'success', true,
        'from_balance', v_new_from_balance,
        'to_balance', v_new_to_balance
    );
END;
$$;



-- Migration 078b: Sender Pod Load Balancing, Fleet Failover & Quarantine

ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS is_pod_eligible BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_accounts_quarantined_until ON public.accounts(quarantined_until);
CREATE INDEX IF NOT EXISTS idx_accounts_pod_eligible ON public.accounts(is_pod_eligible, status);

ALTER TABLE public.campaigns ADD COLUMN IF NOT EXISTS pod_dispatch_strategy TEXT DEFAULT 'CAPACITY_WEIGHTED';
ALTER TABLE public.campaigns ADD COLUMN IF NOT EXISTS pod_failover_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE public.campaigns ADD COLUMN IF NOT EXISTS pod_emergency_paused BOOLEAN DEFAULT FALSE;

ALTER TABLE public.campaign_accounts ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 100;
ALTER TABLE public.campaign_accounts ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS public.sender_pod_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pod_audit_workspace_created ON public.sender_pod_audit_logs(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pod_audit_campaign ON public.sender_pod_audit_logs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_pod_audit_account ON public.sender_pod_audit_logs(account_id);

ALTER TABLE public.sender_pod_audit_logs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'sender_pod_audit_logs' 
    AND policyname = 'sender_pod_audit_isolation'
  ) THEN
    CREATE POLICY sender_pod_audit_isolation ON public.sender_pod_audit_logs
      FOR ALL USING (true);
  END IF;
END $$;



-- Migration 079: Viral Shareable Campaign Performance Card & ROI Certificate Engine

CREATE TABLE IF NOT EXISTS public.campaign_roi_certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    verification_token TEXT NOT NULL,
    issuer_signature TEXT NOT NULL,
    badge_tier TEXT NOT NULL DEFAULT 'SILVER',
    metrics_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_public BOOLEAN NOT NULL DEFAULT TRUE,
    mask_pii BOOLEAN NOT NULL DEFAULT TRUE,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_campaign_roi_certificate_token UNIQUE (verification_token)
);

CREATE INDEX IF NOT EXISTS idx_roi_cert_token ON public.campaign_roi_certificates(verification_token);
CREATE INDEX IF NOT EXISTS idx_roi_cert_ws_campaign ON public.campaign_roi_certificates(workspace_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_roi_cert_tier ON public.campaign_roi_certificates(badge_tier);

ALTER TABLE public.campaign_roi_certificates ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'campaign_roi_certificates' 
    AND policyname = 'campaign_roi_cert_public_read'
  ) THEN
    CREATE POLICY campaign_roi_cert_public_read ON public.campaign_roi_certificates
      FOR SELECT USING (is_public = TRUE);
  END IF;
END $$;



-- Migration 080: Agency Consolidated Invoicing and Billing Statements

CREATE TABLE IF NOT EXISTS public.agency_billing_statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    client_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    invoice_number VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'issued', 'paid', 'void')),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    subtotal_cents BIGINT NOT NULL DEFAULT 0,
    markup_cents BIGINT NOT NULL DEFAULT 0,
    tax_cents BIGINT NOT NULL DEFAULT 0,
    total_cents BIGINT NOT NULL DEFAULT 0,
    breakdown_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agency_billing_statements_agency_id 
    ON public.agency_billing_statements(agency_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agency_billing_statements_client_period 
    ON public.agency_billing_statements(agency_id, client_workspace_id, period_start, period_end);

CREATE INDEX IF NOT EXISTS idx_agency_billing_statements_status 
    ON public.agency_billing_statements(agency_id, status);

ALTER TABLE public.agency_billing_statements ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'agency_billing_statements' 
    AND policyname = 'agency_billing_statements_isolation'
  ) THEN
    CREATE POLICY agency_billing_statements_isolation ON public.agency_billing_statements
      FOR ALL USING (true);
  END IF;
END $$;


-- Migration 075: Prospect Social Signal Radar & Live Activity Intent Engine

CREATE TABLE IF NOT EXISTS public.lead_social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    post_url TEXT,
    post_text TEXT NOT NULL,
    post_date TIMESTAMPTZ DEFAULT now(),
    engagement_count JSONB DEFAULT '{"likes": 0, "comments": 0, "reposts": 0}'::jsonb,
    media_type TEXT DEFAULT 'text',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.lead_social_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    post_id UUID REFERENCES public.lead_social_posts(id) ON DELETE SET NULL,
    signal_type TEXT NOT NULL,
    intent_strength TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence_score FLOAT DEFAULT 0.8,
    detected_keywords JSONB DEFAULT '[]'::jsonb,
    signal_summary TEXT NOT NULL,
    quote_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'social_intent_score') THEN
        ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS social_intent_score INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'social_intent_tier') THEN
        ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS social_intent_tier TEXT DEFAULT 'COLD';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'last_social_scan_at') THEN
        ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS last_social_scan_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'best_outreach_angle') THEN
        ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS best_outreach_angle TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'social_icebreaker') THEN
        ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS social_icebreaker TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'recommended_timing') THEN
        ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS recommended_timing TEXT DEFAULT 'PASSIVE_WARMUP';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_lead_social_posts_lead_ws ON public.lead_social_posts(lead_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_lead_social_posts_date ON public.lead_social_posts(post_date DESC);
CREATE INDEX IF NOT EXISTS idx_lead_social_signals_ws_type ON public.lead_social_signals(workspace_id, signal_type);
CREATE INDEX IF NOT EXISTS idx_leads_social_intent_ws ON public.leads(workspace_id, social_intent_score DESC);

ALTER TABLE public.lead_social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lead_social_signals ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'lead_social_posts' 
    AND policyname = 'lead_social_posts_isolation'
  ) THEN
    CREATE POLICY lead_social_posts_isolation ON public.lead_social_posts
      FOR ALL USING (true);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'lead_social_signals' 
    AND policyname = 'lead_social_signals_isolation'
  ) THEN
    CREATE POLICY lead_social_signals_isolation ON public.lead_social_signals
      FOR ALL USING (true);
  END IF;
END $$;


-- Migration 081: Bayesian ICP Calibration Studio & Adaptive Feedback Loop

ALTER TABLE public.icp_signal_weights 
    ADD COLUMN IF NOT EXISTS is_frozen BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS weight_multiplier FLOAT DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'FIRMOGRAPHIC',
    ADD COLUMN IF NOT EXISTS description TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_icp_weights_frozen ON public.icp_signal_weights(workspace_id, is_frozen);

CREATE TABLE IF NOT EXISTS public.icp_feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    signals_affected JSONB NOT NULL DEFAULT '[]'::jsonb,
    score_before INT DEFAULT NULL,
    score_after INT DEFAULT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_icp_events_workspace_created ON public.icp_feedback_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_icp_events_type ON public.icp_feedback_events(workspace_id, event_type);

ALTER TABLE public.icp_feedback_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'icp_feedback_events' 
    AND policyname = 'icp_feedback_events_isolation'
  ) THEN
    CREATE POLICY icp_feedback_events_isolation ON public.icp_feedback_events
      FOR ALL USING (true);
  END IF;
END $$;



-- Migration 081B: AI Inbox Copilot, Real-Time Objection Battlecards & Deal Pipeline

ALTER TABLE IF EXISTS public.leads
ADD COLUMN IF NOT EXISTS deal_stage TEXT DEFAULT 'NEW_REPLY',
ADD COLUMN IF NOT EXISTS deal_stage_updated_at TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS deal_estimated_value NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_objection_type TEXT,
ADD COLUMN IF NOT EXISTS last_objection_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.lead_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID REFERENCES public.leads(id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS idx_leads_workspace_deal_stage ON public.leads(workspace_id, deal_stage);
CREATE INDEX IF NOT EXISTS idx_leads_deal_stage_updated ON public.leads(deal_stage_updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_objections_workspace ON public.lead_objections(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_objections_lead_id ON public.lead_objections(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_objections_type ON public.lead_objections(objection_type);

ALTER TABLE IF EXISTS public.lead_objections ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'lead_objections' 
    AND policyname = 'lead_objections_isolation'
  ) THEN
    CREATE POLICY lead_objections_isolation ON public.lead_objections
      FOR ALL USING (true);
  END IF;
END $$;


-- Migration 082: Social Feed Pre-Warmer, Thought Leadership & Omnichannel Cascade

CREATE TABLE IF NOT EXISTS public.lead_prewarm_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID NOT NULL,
    account_id UUID,
    action_type VARCHAR(50) NOT NULL,
    post_url TEXT,
    post_snippet TEXT,
    generated_comment TEXT,
    sentiment_score FLOAT DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'pending',
    scheduled_for TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prewarm_workspace_lead ON public.lead_prewarm_events(workspace_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_prewarm_status_scheduled ON public.lead_prewarm_events(status, scheduled_for);

CREATE TABLE IF NOT EXISTS public.omnichannel_fallback_configs (
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

CREATE INDEX IF NOT EXISTS idx_omnichannel_workspace ON public.omnichannel_fallback_configs(workspace_id);

CREATE TABLE IF NOT EXISTS public.omnichannel_cascade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID NOT NULL,
    campaign_id UUID,
    original_channel VARCHAR(50) NOT NULL DEFAULT 'linkedin',
    target_channel VARCHAR(50) NOT NULL,
    trigger_reason VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'completed',
    bridge_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cascade_logs_lead ON public.omnichannel_cascade_logs(workspace_id, lead_id);

CREATE TABLE IF NOT EXISTS public.thought_leadership_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    account_id UUID,
    topic VARCHAR(255) NOT NULL,
    hook_framework VARCHAR(100) NOT NULL,
    post_content TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',
    scheduled_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_posts_workspace_status ON public.thought_leadership_posts(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_posts_scheduled_at ON public.thought_leadership_posts(scheduled_at);

ALTER TABLE IF EXISTS public.lead_prewarm_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.omnichannel_fallback_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.omnichannel_cascade_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.thought_leadership_posts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'lead_prewarm_events' 
    AND policyname = 'lead_prewarm_events_isolation'
  ) THEN
    CREATE POLICY lead_prewarm_events_isolation ON public.lead_prewarm_events
      FOR ALL USING (true);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'omnichannel_fallback_configs' 
    AND policyname = 'omnichannel_fallback_configs_isolation'
  ) THEN
    CREATE POLICY omnichannel_fallback_configs_isolation ON public.omnichannel_fallback_configs
      FOR ALL USING (true);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'omnichannel_cascade_logs' 
    AND policyname = 'omnichannel_cascade_logs_isolation'
  ) THEN
    CREATE POLICY omnichannel_cascade_logs_isolation ON public.omnichannel_cascade_logs
      FOR ALL USING (true);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'thought_leadership_posts' 
    AND policyname = 'thought_leadership_posts_isolation'
  ) THEN
    CREATE POLICY thought_leadership_posts_isolation ON public.thought_leadership_posts
      FOR ALL USING (true);
  END IF;
END $$;

-- ============================================================================
-- Migration 083: Thompson Sampling Multi-Armed Bandit Copy Optimizer & Trigger Radar Events
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.bandit_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    campaign_id UUID,
    node_id TEXT,
    name TEXT NOT NULL DEFAULT 'Dynamic Copy Bandit',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    exploration_factor NUMERIC NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.copy_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID REFERENCES public.bandit_experiments(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    name TEXT NOT NULL,
    template_text TEXT NOT NULL,
    arm_type TEXT NOT NULL DEFAULT 'full_message' CHECK (arm_type IN ('hook', 'value_prop', 'cta', 'full_message')),
    alpha_param NUMERIC NOT NULL DEFAULT 1.0,
    beta_param NUMERIC NOT NULL DEFAULT 1.0,
    impressions INT NOT NULL DEFAULT 0,
    positive_replies INT NOT NULL DEFAULT 0,
    objections INT NOT NULL DEFAULT 0,
    unsubscribes INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'degraded', 'retired')),
    parent_variant_id UUID,
    generation INT NOT NULL DEFAULT 1,
    mutation_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.trigger_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('NEW_ROLE', 'PROMOTION', 'FUNDING_ROUND', 'HIRING_SURGE')),
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ENROLLED', 'DISMISSED')),
    generated_icebreaker TEXT,
    enrolled_campaign_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bandit_experiments_ws ON public.bandit_experiments(workspace_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_copy_variants_exp ON public.copy_variants(experiment_id, status);
CREATE INDEX IF NOT EXISTS idx_trigger_events_ws_status ON public.trigger_events(workspace_id, status);

ALTER TABLE IF EXISTS public.bandit_experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.copy_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.trigger_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'bandit_experiments' AND policyname = 'bandit_experiments_ws_policy') THEN
        CREATE POLICY bandit_experiments_ws_policy ON public.bandit_experiments FOR ALL USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'copy_variants' AND policyname = 'copy_variants_ws_policy') THEN
        CREATE POLICY copy_variants_ws_policy ON public.copy_variants FOR ALL USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'trigger_events' AND policyname = 'trigger_events_ws_policy') THEN
        CREATE POLICY trigger_events_ws_policy ON public.trigger_events FOR ALL USING (true);
    END IF;
END $$;

-- ============================================================================
-- Migration 084: LinkedIn Event & Group Harvester and Multimodal Voice/Video Prospecting
-- ============================================================================

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

CREATE INDEX IF NOT EXISTS idx_harvested_events_ws ON public.harvested_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_event_attendees_event ON public.event_attendees(event_id, status);
CREATE INDEX IF NOT EXISTS idx_multimodal_assets_ws ON public.multimodal_assets(workspace_id, asset_type);

ALTER TABLE IF EXISTS public.harvested_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.event_attendees ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.multimodal_assets ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'harvested_events' AND policyname = 'harvested_events_ws_policy') THEN
        CREATE POLICY harvested_events_ws_policy ON public.harvested_events FOR ALL USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'event_attendees' AND policyname = 'event_attendees_ws_policy') THEN
        CREATE POLICY event_attendees_ws_policy ON public.event_attendees FOR ALL USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'multimodal_assets' AND policyname = 'multimodal_assets_ws_policy') THEN
        CREATE POLICY multimodal_assets_ws_policy ON public.multimodal_assets FOR ALL USING (true);
    END IF;
END $$;

-- ============================================================================
-- Migration 085: Lead List Dynamic Segmentation Metadata
-- ============================================================================

ALTER TABLE IF EXISTS public.lead_lists
ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';


-- ============================================================================
-- Migration 086: Account-Based Marketing (ABM) Buying Committees & Multithreading
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.target_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    company_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'tier_1' CHECK (tier IN ('tier_1', 'tier_2', 'tier_3')),
    employee_count INT DEFAULT 250,
    industry TEXT DEFAULT 'Software & Technology',
    account_heat_score INT NOT NULL DEFAULT 10,
    stage TEXT NOT NULL DEFAULT 'discovery' CHECK (stage IN ('discovery', 'multithreaded', 'consensus_building', 'opportunity')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.account_committee_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES public.target_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT NOT NULL,
    title TEXT NOT NULL,
    email TEXT,
    linkedin_url TEXT,
    role_archetype TEXT NOT NULL DEFAULT 'champion' CHECK (role_archetype IN ('economic_buyer', 'champion', 'technical_evaluator', 'end_user')),
    status TEXT NOT NULL DEFAULT 'uncontacted' CHECK (status IN ('uncontacted', 'engaged', 'replied', 'meeting_booked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.account_committee_members ADD COLUMN IF NOT EXISTS email TEXT;

CREATE TABLE IF NOT EXISTS public.multithread_campaign_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES public.target_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    campaign_id UUID,
    committee_size INT NOT NULL DEFAULT 3,
    staggered_interval_hours INT NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    launched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid querying
CREATE INDEX IF NOT EXISTS idx_target_accounts_ws ON public.target_accounts(workspace_id, domain);
CREATE INDEX IF NOT EXISTS idx_committee_members_acc ON public.account_committee_members(account_id, role_archetype);
CREATE INDEX IF NOT EXISTS idx_committee_members_ws ON public.account_committee_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_multithread_runs_ws ON public.multithread_campaign_runs(workspace_id, account_id);

-- Row-Level Security
ALTER TABLE public.target_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_committee_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.multithread_campaign_runs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'target_accounts' AND policyname = 'target_accounts_ws_policy') THEN
        CREATE POLICY target_accounts_ws_policy ON public.target_accounts FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'account_committee_members' AND policyname = 'account_committee_members_ws_policy') THEN
        CREATE POLICY account_committee_members_ws_policy ON public.account_committee_members FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'multithread_campaign_runs' AND policyname = 'multithread_campaign_runs_ws_policy') THEN
        CREATE POLICY multithread_campaign_runs_ws_policy ON public.multithread_campaign_runs FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================================
-- Migration 087: Champion Job-Change Boomerang Tracker, Warm Intro Graph & Closed-Lost Revival Engine
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.champion_job_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT NOT NULL,
    linkedin_url TEXT,
    previous_company TEXT NOT NULL,
    previous_title TEXT NOT NULL,
    new_company TEXT NOT NULL,
    new_title TEXT NOT NULL,
    new_domain TEXT,
    relationship_type TEXT NOT NULL DEFAULT 'former_champion' CHECK (relationship_type IN ('past_customer', 'former_champion', 'closed_lost_contact', 'power_user')),
    days_in_new_role INT NOT NULL DEFAULT 14,
    buying_window_score INT NOT NULL DEFAULT 85,
    is_internal_promotion BOOLEAN NOT NULL DEFAULT FALSE,
    playbook_message TEXT,
    status TEXT NOT NULL DEFAULT 'detected' CHECK (status IN ('detected', 'playbook_drafted', 'enrolled', 'converted')),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.warm_intro_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    target_prospect_name TEXT NOT NULL,
    target_company TEXT NOT NULL,
    target_title TEXT NOT NULL,
    connector_name TEXT NOT NULL,
    connector_role TEXT NOT NULL,
    bridge_type TEXT NOT NULL DEFAULT 'shared_alumni' CHECK (bridge_type IN ('shared_alumni', 'mutual_connection', 'shared_investor', 'board_member')),
    overlap_context TEXT NOT NULL,
    warmth_score INT NOT NULL DEFAULT 88,
    intro_request_draft TEXT,
    direct_bridge_draft TEXT,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'requested', 'introduced', 'replied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.closed_lost_revivals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    prospect_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    title TEXT NOT NULL,
    lost_reason TEXT NOT NULL DEFAULT 'bad_timing' CHECK (lost_reason IN ('budget_freeze', 'missing_feature', 'bad_timing', 'competitor_chosen', 'ghosted_no_decision')),
    days_since_lost INT NOT NULL DEFAULT 120,
    original_deal_value NUMERIC NOT NULL DEFAULT 25000,
    revival_trigger TEXT,
    revival_score INT NOT NULL DEFAULT 80,
    resurrection_message TEXT,
    status TEXT NOT NULL DEFAULT 'ready_to_revive' CHECK (status IN ('ready_to_revive', 'revival_sent', 're_engaged', 'pipeline_restored')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_champion_job_changes_ws ON public.champion_job_changes(workspace_id, buying_window_score DESC);
CREATE INDEX IF NOT EXISTS idx_warm_intro_paths_ws ON public.warm_intro_paths(workspace_id, warmth_score DESC);
CREATE INDEX IF NOT EXISTS idx_closed_lost_revivals_ws ON public.closed_lost_revivals(workspace_id, revival_score DESC);

ALTER TABLE public.champion_job_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.warm_intro_paths ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.closed_lost_revivals ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'champion_job_changes' AND policyname = 'champion_job_changes_ws_policy') THEN
        CREATE POLICY champion_job_changes_ws_policy ON public.champion_job_changes FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'warm_intro_paths' AND policyname = 'warm_intro_paths_ws_policy') THEN
        CREATE POLICY warm_intro_paths_ws_policy ON public.warm_intro_paths FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'closed_lost_revivals' AND policyname = 'closed_lost_revivals_ws_policy') THEN
        CREATE POLICY closed_lost_revivals_ws_policy ON public.closed_lost_revivals FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================================
-- Migration 088: Autonomous Competitive Takeover & Tech-Stack Displacement Engine
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.competitor_displacements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    target_company TEXT NOT NULL,
    domain TEXT NOT NULL,
    target_contact_name TEXT NOT NULL,
    target_contact_title TEXT NOT NULL,
    incumbent_vendor TEXT NOT NULL DEFAULT 'apollo' CHECK (incumbent_vendor IN ('apollo', 'outreach', 'salesloft', 'lemlist', 'expandi', 'heyreach', 'other')),
    seat_count INT NOT NULL DEFAULT 10,
    contract_renewal_days INT NOT NULL DEFAULT 75,
    displacement_vulnerability_score INT NOT NULL DEFAULT 82,
    annual_potential_savings NUMERIC NOT NULL DEFAULT 14400.0,
    generated_displacement_copy TEXT,
    status TEXT NOT NULL DEFAULT 'radar_detected' CHECK (status IN ('radar_detected', 'displacement_pitched', 'migration_evaluating', 'displaced_won')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.vendor_battlecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    vendor_slug TEXT NOT NULL,
    vendor_display_name TEXT NOT NULL,
    primary_vulnerability TEXT NOT NULL,
    elein_killer_advantage TEXT NOT NULL,
    contract_buyout_offer TEXT NOT NULL,
    battlecard_pitch TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_competitor_displacements_ws ON public.competitor_displacements(workspace_id, displacement_vulnerability_score DESC);
CREATE INDEX IF NOT EXISTS idx_vendor_battlecards_ws ON public.vendor_battlecards(workspace_id, vendor_slug);

ALTER TABLE public.competitor_displacements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_battlecards ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'competitor_displacements' AND policyname = 'competitor_displacements_ws_policy') THEN
        CREATE POLICY competitor_displacements_ws_policy ON public.competitor_displacements FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'vendor_battlecards' AND policyname = 'vendor_battlecards_ws_policy') THEN
        CREATE POLICY vendor_battlecards_ws_policy ON public.vendor_battlecards FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================================
-- Migration 089: Autonomous Executive Calendar Concierge & Frictionless Meeting Booking Engine
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.meeting_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    lead_email TEXT NOT NULL,
    lead_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    assigned_rep_name TEXT NOT NULL DEFAULT 'Account Executive',
    assigned_rep_email TEXT NOT NULL,
    meeting_title TEXT NOT NULL DEFAULT 'Discovery & Strategy Session (30 min)',
    meeting_duration_minutes INT NOT NULL DEFAULT 30,
    prospect_timezone TEXT NOT NULL DEFAULT 'America/New_York',
    proposed_slots JSONB NOT NULL DEFAULT '[]'::jsonb,
    confirmed_slot TIMESTAMPTZ,
    meeting_link TEXT,
    calendar_provider TEXT NOT NULL DEFAULT 'google_calendar' CHECK (calendar_provider IN ('google_calendar', 'outlook', 'cal_com', 'calendly')),
    status TEXT NOT NULL DEFAULT 'slots_proposed' CHECK (status IN ('slots_proposed', 'confirmed', 'rescheduled', 'cancelled', 'completed')),
    confirmation_token TEXT UNIQUE NOT NULL,
    booking_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.rep_calendar_availability (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    rep_name TEXT NOT NULL,
    rep_email TEXT NOT NULL,
    working_hours_start TEXT NOT NULL DEFAULT '09:00',
    working_hours_end TEXT NOT NULL DEFAULT '17:00',
    working_days JSONB NOT NULL DEFAULT '[1, 2, 3, 4, 5]'::jsonb,
    rep_timezone TEXT NOT NULL DEFAULT 'America/New_York',
    buffer_minutes INT NOT NULL DEFAULT 15,
    max_meetings_per_day INT NOT NULL DEFAULT 6,
    custom_booking_link TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meeting_bookings_ws ON public.meeting_bookings(workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meeting_bookings_token ON public.meeting_bookings(confirmation_token);
CREATE INDEX IF NOT EXISTS idx_rep_availability_ws ON public.rep_calendar_availability(workspace_id, rep_email);

ALTER TABLE public.meeting_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rep_calendar_availability ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'meeting_bookings' AND policyname = 'meeting_bookings_ws_policy') THEN
        CREATE POLICY meeting_bookings_ws_policy ON public.meeting_bookings FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'rep_calendar_availability' AND policyname = 'rep_calendar_availability_ws_policy') THEN
        CREATE POLICY rep_calendar_availability_ws_policy ON public.rep_calendar_availability FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================================
-- Migration 090: Clay-Style Multi-Vendor Waterfall Enrichment Engine
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.waterfall_enrichment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    lead_name TEXT NOT NULL,
    company_domain TEXT NOT NULL,
    waterfall_sequence JSONB NOT NULL DEFAULT '["internal_cache", "apollo", "hunter", "smtp_handshake"]'::jsonb,
    resolved_email TEXT,
    resolved_vendor TEXT,
    deliverability_status TEXT NOT NULL DEFAULT 'valid' CHECK (deliverability_status IN ('valid', 'risky_catchall', 'invalid', 'unresolved')),
    confidence_score INT NOT NULL DEFAULT 95,
    vendors_queried JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_cost_credits NUMERIC NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.vendor_enrichment_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    vendor_slug TEXT NOT NULL,
    vendor_display_name TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    priority_order INT NOT NULL DEFAULT 1,
    cost_per_lookup_credits NUMERIC NOT NULL DEFAULT 1.0,
    api_key_configured BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waterfall_enrichment_ws ON public.waterfall_enrichment_runs(workspace_id, deliverability_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_waterfall_domain ON public.waterfall_enrichment_runs(workspace_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_vendor_configs_ws ON public.vendor_enrichment_configs(workspace_id, priority_order ASC);

ALTER TABLE public.waterfall_enrichment_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_enrichment_configs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'waterfall_enrichment_runs' AND policyname = 'waterfall_enrichment_runs_ws_policy') THEN
        CREATE POLICY waterfall_enrichment_runs_ws_policy ON public.waterfall_enrichment_runs FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'vendor_enrichment_configs' AND policyname = 'vendor_enrichment_configs_ws_policy') THEN
        CREATE POLICY vendor_enrichment_configs_ws_policy ON public.vendor_enrichment_configs FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================================
-- Migration 091: Peer-to-Peer AI Email Warmup & DNS Reputation Swarm
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.warmup_mailboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    email_address TEXT NOT NULL,
    sender_name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google_workspace' CHECK (provider IN ('google_workspace', 'microsoft_365', 'smtp_imap', 'custom')),
    warmup_status TEXT NOT NULL DEFAULT 'warming' CHECK (warmup_status IN ('warming', 'paused', 'graduated', 'cooling_down')),
    ramp_strategy TEXT NOT NULL DEFAULT 'balanced' CHECK (ramp_strategy IN ('gentle', 'balanced', 'aggressive')),
    current_daily_limit INT NOT NULL DEFAULT 10,
    max_daily_limit INT NOT NULL DEFAULT 40,
    current_ramp_day INT NOT NULL DEFAULT 1,
    target_reply_rate_pct INT NOT NULL DEFAULT 35,
    inbox_placement_rate_pct NUMERIC NOT NULL DEFAULT 98.5,
    health_score INT NOT NULL DEFAULT 94,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.mailbox_dns_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    domain TEXT NOT NULL,
    spf_valid BOOLEAN NOT NULL DEFAULT true,
    spf_record TEXT,
    dkim_valid BOOLEAN NOT NULL DEFAULT true,
    dkim_selector TEXT,
    dmarc_valid BOOLEAN NOT NULL DEFAULT true,
    dmarc_policy TEXT,
    mx_valid BOOLEAN NOT NULL DEFAULT true,
    mx_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    overall_dns_health_score INT NOT NULL DEFAULT 100,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_warmup_mailboxes_ws ON public.warmup_mailboxes(workspace_id, warmup_status);
CREATE INDEX IF NOT EXISTS idx_warmup_mailboxes_email ON public.warmup_mailboxes(workspace_id, email_address);
CREATE INDEX IF NOT EXISTS idx_mailbox_dns_audits_ws ON public.mailbox_dns_audits(workspace_id, domain);

ALTER TABLE public.warmup_mailboxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mailbox_dns_audits ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'warmup_mailboxes' AND policyname = 'warmup_mailboxes_ws_policy') THEN
        CREATE POLICY warmup_mailboxes_ws_policy ON public.warmup_mailboxes FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'mailbox_dns_audits' AND policyname = 'mailbox_dns_audits_ws_policy') THEN
        CREATE POLICY mailbox_dns_audits_ws_policy ON public.mailbox_dns_audits FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================================
-- Migration 092: Account-Level CRM Bi-Directional Auto-Sync & Real-Time Deal Attribution Engine
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.crm_account_sync_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    domain TEXT NOT NULL,
    company_name TEXT NOT NULL,
    crm_provider TEXT NOT NULL DEFAULT 'hubspot' CHECK (crm_provider IN ('hubspot', 'salesforce', 'pipedrive', 'zoho', 'custom')),
    crm_company_id TEXT NOT NULL,
    lifecycle_stage TEXT NOT NULL DEFAULT 'lead' CHECK (lifecycle_stage IN ('subscriber', 'lead', 'marketingqualifiedlead', 'salesqualifiedlead', 'opportunity', 'customer', 'evangelist', 'other')),
    sync_status TEXT NOT NULL DEFAULT 'synced' CHECK (sync_status IN ('synced', 'pending', 'error', 'paused')),
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.deal_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    deal_id TEXT NOT NULL,
    deal_name TEXT NOT NULL,
    deal_amount NUMERIC NOT NULL DEFAULT 0.0,
    pipeline_stage TEXT NOT NULL DEFAULT 'closed_won',
    attribution_model TEXT NOT NULL DEFAULT 'w_shaped' CHECK (attribution_model IN ('first_touch', 'last_touch', 'linear', 'w_shaped')),
    touchpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    touchpoint_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    attributed_pipeline_arr NUMERIC NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.crm_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    direction TEXT NOT NULL DEFAULT 'inbound_from_crm' CHECK (direction IN ('inbound_from_crm', 'outbound_to_crm')),
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'skipped_echo', 'failed')),
    payload_hash TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_accounts_ws ON public.crm_account_sync_mappings(workspace_id, domain);
CREATE INDEX IF NOT EXISTS idx_crm_accounts_crm_id ON public.crm_account_sync_mappings(workspace_id, crm_company_id);
CREATE INDEX IF NOT EXISTS idx_deal_attributions_ws ON public.deal_attributions(workspace_id, deal_id);
CREATE INDEX IF NOT EXISTS idx_crm_sync_logs_ws ON public.crm_sync_logs(workspace_id, created_at DESC);

ALTER TABLE public.crm_account_sync_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deal_attributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_sync_logs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'crm_account_sync_mappings' AND policyname = 'crm_account_sync_mappings_ws_policy') THEN
        CREATE POLICY crm_account_sync_mappings_ws_policy ON public.crm_account_sync_mappings FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'deal_attributions' AND policyname = 'deal_attributions_ws_policy') THEN
        CREATE POLICY deal_attributions_ws_policy ON public.deal_attributions FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'crm_sync_logs' AND policyname = 'crm_sync_logs_ws_policy') THEN
        CREATE POLICY crm_sync_logs_ws_policy ON public.crm_sync_logs FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- ── Migration 093: Employee Advocacy & Viral LinkedIn Post Booster Pod ────────────────
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

CREATE INDEX IF NOT EXISTS idx_advocacy_pods_ws ON public.advocacy_pods(workspace_id, is_active);
CREATE INDEX IF NOT EXISTS idx_advocacy_members_pod ON public.advocacy_pod_members(pod_id, is_active);
CREATE INDEX IF NOT EXISTS idx_advocacy_boosts_ws ON public.advocacy_post_boosts(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_advocacy_boosts_url ON public.advocacy_post_boosts(workspace_id, post_url);
CREATE INDEX IF NOT EXISTS idx_advocacy_engagements_boost ON public.advocacy_engagements(post_boost_id, status);
CREATE INDEX IF NOT EXISTS idx_advocacy_engagements_acc ON public.advocacy_engagements(account_id, scheduled_at);

ALTER TABLE public.advocacy_pods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.advocacy_pod_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.advocacy_post_boosts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.advocacy_engagements ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_pods' AND policyname = 'advocacy_pods_ws_policy') THEN
        CREATE POLICY advocacy_pods_ws_policy ON public.advocacy_pods FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_pod_members' AND policyname = 'advocacy_pod_members_ws_policy') THEN
        CREATE POLICY advocacy_pod_members_ws_policy ON public.advocacy_pod_members FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_post_boosts' AND policyname = 'advocacy_post_boosts_ws_policy') THEN
        CREATE POLICY advocacy_post_boosts_ws_policy ON public.advocacy_post_boosts FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'advocacy_engagements' AND policyname = 'advocacy_engagements_ws_policy') THEN
        CREATE POLICY advocacy_engagements_ws_policy ON public.advocacy_engagements FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;


COMMIT;
