-- =====================================================================
-- Migration 003: Aggregate rate limiting + B7 action-type seed data
--                + B8 peek function
-- Covers: B1 (action_type_limits + account_daily_action_counts),
--         B2 (try_consume_daily_action with warmup-aware aggregate cap),
--         B7 (complete node-to-action_type seed including remove_connection),
--         B8 (peek_daily_action_headroom — non-consuming read-only check).
-- Safe to re-run — all statements use IF NOT EXISTS / OR REPLACE guards.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Add daily_action_cap to accounts if it doesn't already exist.
--    This is a GENERATED column = daily_connection_limit + daily_message_limit.
--    Changing either parent column automatically updates it.
-- ---------------------------------------------------------------------

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'accounts'
          AND column_name  = 'daily_action_cap'
    ) THEN
        ALTER TABLE public.accounts
            ADD COLUMN daily_action_cap integer
            GENERATED ALWAYS AS (daily_connection_limit + daily_message_limit) STORED;
    END IF;
END $$;


-- ---------------------------------------------------------------------
-- 1. action_type_limits — master config table for per-type daily caps
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.action_type_limits (
    action_type  text    NOT NULL,
    daily_limit  integer NOT NULL,
    tier         integer NOT NULL DEFAULT 1,
    description  text,
    CONSTRAINT action_type_limits_pkey PRIMARY KEY (action_type)
);

-- Seed all 14 confirmed action types (ON CONFLICT DO NOTHING = idempotent re-runs)
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


-- ---------------------------------------------------------------------
-- 2. account_daily_action_counts — per-account, per-type, per-day tally
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.account_daily_action_counts (
    id           uuid    NOT NULL DEFAULT gen_random_uuid(),
    account_id   uuid    NOT NULL,
    action_type  text    NOT NULL,
    usage_date   date    NOT NULL DEFAULT CURRENT_DATE,
    count        integer NOT NULL DEFAULT 0,
    CONSTRAINT account_daily_action_counts_pkey PRIMARY KEY (id),
    CONSTRAINT account_daily_action_counts_unique
        UNIQUE (account_id, action_type, usage_date),
    CONSTRAINT account_daily_action_counts_action_type_fkey
        FOREIGN KEY (action_type) REFERENCES public.action_type_limits (action_type)
);

CREATE INDEX IF NOT EXISTS account_daily_action_counts_account_date_idx
    ON public.account_daily_action_counts (account_id, usage_date);


-- ---------------------------------------------------------------------
-- 3. account_daily_usage_today — convenience view for C3 sender selection
-- ---------------------------------------------------------------------

CREATE OR REPLACE VIEW public.account_daily_usage_today AS
SELECT
    a.id                               AS account_id,
    a.daily_action_cap,
    COALESCE(SUM(c.count), 0)::integer AS total_actions_today
FROM public.accounts a
LEFT JOIN public.account_daily_action_counts c
    ON c.account_id = a.id AND c.usage_date = CURRENT_DATE
GROUP BY a.id, a.daily_action_cap;


-- ---------------------------------------------------------------------
-- 4. try_consume_daily_action — rate-limiting gate (increments on success)
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.try_consume_daily_action(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_account       public.accounts%ROWTYPE;
    v_type_limit    integer;
    v_type_count    integer;
    v_agg_count     integer;
    v_age_days      integer;
    v_effective_cap integer;
BEGIN
    -- Load account row (daily_action_cap is a generated column = conn_limit + msg_limit)
    SELECT * INTO v_account FROM public.accounts WHERE id = p_account_id;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    -- Load per-type daily limit from config table
    SELECT daily_limit INTO v_type_limit
    FROM public.action_type_limits WHERE action_type = p_action_type;
    IF v_type_limit IS NULL THEN
        -- Unknown action type: block rather than silently skip
        RETURN false;
    END IF;

    -- Apply warmup ramp if account is in warmup period
    v_effective_cap := v_account.daily_action_cap;
    IF v_account.is_warmup AND v_account.warmup_start_date IS NOT NULL THEN
        v_age_days := GREATEST(0, CURRENT_DATE - v_account.warmup_start_date::date);
        IF v_age_days < 30 THEN
            IF v_age_days <= 3 THEN
                v_effective_cap := LEAST(v_effective_cap, 7);
                v_type_limit    := LEAST(v_type_limit,    2);
            ELSIF v_age_days <= 7 THEN
                v_effective_cap := LEAST(v_effective_cap, 17);
                v_type_limit    := LEAST(v_type_limit,    5);
            ELSIF v_age_days <= 14 THEN
                v_effective_cap := LEAST(v_effective_cap, 35);
                v_type_limit    := LEAST(v_type_limit,    10);
            ELSIF v_age_days <= 21 THEN
                v_effective_cap := LEAST(v_effective_cap, 55);
                v_type_limit    := LEAST(v_type_limit,    15);
            ELSE  -- days 22-29: approach full limit
                v_effective_cap := LEAST(v_effective_cap, (v_account.daily_action_cap * 0.8)::integer);
            END IF;
        END IF;
    END IF;

    -- Check per-type count for today
    SELECT COALESCE(count, 0) INTO v_type_count
    FROM public.account_daily_action_counts
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date  = CURRENT_DATE;
    v_type_count := COALESCE(v_type_count, 0);

    IF v_type_count + 1 > v_type_limit THEN
        RETURN false;
    END IF;

    -- Check aggregate daily cap (all action types combined)
    SELECT COALESCE(SUM(count), 0) INTO v_agg_count
    FROM public.account_daily_action_counts
    WHERE account_id = p_account_id
      AND usage_date  = CURRENT_DATE;

    IF v_agg_count + 1 > v_effective_cap THEN
        RETURN false;
    END IF;

    -- Both checks passed — upsert the counter
    INSERT INTO public.account_daily_action_counts
        (account_id, action_type, usage_date, count)
    VALUES
        (p_account_id, p_action_type, CURRENT_DATE, 1)
    ON CONFLICT (account_id, action_type, usage_date)
    DO UPDATE SET count = public.account_daily_action_counts.count + 1;

    RETURN true;
END;
$$;


-- ---------------------------------------------------------------------
-- 5. peek_daily_action_headroom (B8) — read-only, never increments.
--    Wire "Daily Limit Check" condition nodes to call THIS, not
--    try_consume_daily_action — otherwise you double-count every action.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.peek_daily_action_headroom(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_account       public.accounts%ROWTYPE;
    v_type_limit    integer;
    v_type_count    integer;
    v_agg_count     integer;
    v_age_days      integer;
    v_effective_cap integer;
BEGIN
    SELECT * INTO v_account FROM public.accounts WHERE id = p_account_id;
    IF NOT FOUND THEN RETURN false; END IF;

    SELECT daily_limit INTO v_type_limit
    FROM public.action_type_limits WHERE action_type = p_action_type;
    IF v_type_limit IS NULL THEN RETURN false; END IF;

    v_effective_cap := v_account.daily_action_cap;
    IF v_account.is_warmup AND v_account.warmup_start_date IS NOT NULL THEN
        v_age_days := GREATEST(0, CURRENT_DATE - v_account.warmup_start_date::date);
        IF v_age_days < 30 THEN
            IF v_age_days <= 3 THEN
                v_effective_cap := LEAST(v_effective_cap, 7);
                v_type_limit    := LEAST(v_type_limit,    2);
            ELSIF v_age_days <= 7 THEN
                v_effective_cap := LEAST(v_effective_cap, 17);
                v_type_limit    := LEAST(v_type_limit,    5);
            ELSIF v_age_days <= 14 THEN
                v_effective_cap := LEAST(v_effective_cap, 35);
                v_type_limit    := LEAST(v_type_limit,    10);
            ELSIF v_age_days <= 21 THEN
                v_effective_cap := LEAST(v_effective_cap, 55);
                v_type_limit    := LEAST(v_type_limit,    15);
            ELSE
                v_effective_cap := LEAST(v_effective_cap, (v_account.daily_action_cap * 0.8)::integer);
            END IF;
        END IF;
    END IF;

    SELECT COALESCE(count, 0) INTO v_type_count
    FROM public.account_daily_action_counts
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date  = CURRENT_DATE;
    v_type_count := COALESCE(v_type_count, 0);

    SELECT COALESCE(SUM(count), 0) INTO v_agg_count
    FROM public.account_daily_action_counts
    WHERE account_id = p_account_id
      AND usage_date  = CURRENT_DATE;

    -- Pure read — no INSERT/UPDATE ever happens here
    RETURN (v_type_count + 1 <= v_type_limit)
       AND (v_agg_count  + 1 <= v_effective_cap);
END;
$$;


COMMIT;
