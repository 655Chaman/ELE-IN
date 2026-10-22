-- ============================================================================
-- MIGRATION 105: ACCOUNTS SUBSYSTEM PARANOIA REMEDIATION
-- Idempotent resolution for FLAW-ACC-DB-01 through FLAW-ACC-DB-06 and SEC-03/07
-- Standard: Zero Emojis, Complete Relational Integrity, Strict Multi-Tenancy
-- Aligned with Live Supabase Production Database Schema
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PRE-FLIGHT TYPE OPERATOR EXTENSION (Eliminates PostgreSQL 42883 Operator Error)
-- ----------------------------------------------------------------------------
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_type t 
        JOIN pg_namespace n ON n.oid = t.typnamespace 
        WHERE t.typname = 'account_status' AND n.nspname = 'public'
    ) THEN
        EXECUTE $OP$
            CREATE OR REPLACE FUNCTION public.account_status_to_text(public.account_status)
            RETURNS text LANGUAGE sql IMMUTABLE STRICT AS 'SELECT $1::text;';

            CREATE OR REPLACE FUNCTION public.text_eq_account_status(text, public.account_status)
            RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS 'SELECT $1 = $2::text;';

            CREATE OR REPLACE FUNCTION public.account_status_eq_text(public.account_status, text)
            RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS 'SELECT $1::text = $2;';

            CREATE OR REPLACE FUNCTION public.text_neq_account_status(text, public.account_status)
            RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS 'SELECT $1 != $2::text;';

            CREATE OR REPLACE FUNCTION public.account_status_neq_text(public.account_status, text)
            RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS 'SELECT $1::text != $2;';
        $OP$;

        IF NOT EXISTS (
            SELECT 1 FROM pg_operator o
            JOIN pg_type t1 ON t1.oid = o.oprleft
            JOIN pg_type t2 ON t2.oid = o.oprright
            WHERE o.oprname = '=' AND t1.typname = 'text' AND t2.typname = 'account_status'
        ) THEN
            EXECUTE $OP$
                CREATE OPERATOR public.= (
                    LEFTARG = text,
                    RIGHTARG = public.account_status,
                    PROCEDURE = public.text_eq_account_status,
                    COMMUTATOR = =
                );
            $OP$;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_operator o
            JOIN pg_type t1 ON t1.oid = o.oprleft
            JOIN pg_type t2 ON t2.oid = o.oprright
            WHERE o.oprname = '=' AND t1.typname = 'account_status' AND t2.typname = 'text'
        ) THEN
            EXECUTE $OP$
                CREATE OPERATOR public.= (
                    LEFTARG = public.account_status,
                    RIGHTARG = text,
                    PROCEDURE = public.account_status_eq_text,
                    COMMUTATOR = =
                );
            $OP$;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_operator o
            JOIN pg_type t1 ON t1.oid = o.oprleft
            JOIN pg_type t2 ON t2.oid = o.oprright
            WHERE o.oprname = '<>' AND t1.typname = 'text' AND t2.typname = 'account_status'
        ) THEN
            EXECUTE $OP$
                CREATE OPERATOR public.<> (
                    LEFTARG = text,
                    RIGHTARG = public.account_status,
                    PROCEDURE = public.text_neq_account_status,
                    COMMUTATOR = <>
                );
            $OP$;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_operator o
            JOIN pg_type t1 ON t1.oid = o.oprleft
            JOIN pg_type t2 ON t2.oid = o.oprright
            WHERE o.oprname = '<>' AND t1.typname = 'account_status' AND t2.typname = 'text'
        ) THEN
            EXECUTE $OP$
                CREATE OPERATOR public.<> (
                    LEFTARG = public.account_status,
                    RIGHTARG = text,
                    PROCEDURE = public.account_status_neq_text,
                    COMMUTATOR = <>
                );
            $OP$;
        END IF;
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ----------------------------------------------------------------------------
-- 1. ACCOUNTS STATUS ENUM TO TEXT NORMALIZATION (FLAW-ACC-DB-01, FLAW-ACC-DB-02)
-- ----------------------------------------------------------------------------

-- A. Safely drop generated column is_active to allow altering status column type (0A000 prevention)
ALTER TABLE public.accounts DROP COLUMN IF EXISTS is_active CASCADE;

-- B. Drop legacy check constraints on accounts.status
DO $$ 
DECLARE
    c RECORD;
BEGIN
    FOR c IN 
        SELECT conname 
        FROM pg_constraint 
        WHERE conrelid = 'public.accounts'::regclass 
          AND contype = 'c'
          AND (conname ILIKE '%status%' OR conname ILIKE '%active%')
    LOOP
        EXECUTE 'ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS ' || quote_ident(c.conname) || ' CASCADE';
    END LOOP;
END $$;

-- C. Drop default on status column before type alteration
ALTER TABLE public.accounts ALTER COLUMN status DROP DEFAULT;

-- D. Convert status column directly to TEXT
ALTER TABLE public.accounts ALTER COLUMN status TYPE TEXT USING status::TEXT;

-- E. Restore clean TEXT default
ALTER TABLE public.accounts ALTER COLUMN status SET DEFAULT 'ACTIVE';

-- F. Sanitize invalid status values now that column is confirmed TEXT in the catalog
UPDATE public.accounts 
SET status = 'ACTIVE' 
WHERE status IS NULL 
   OR status NOT IN (
       'ACTIVE',
       'DISCONNECTED',
       'RATE_LIMITED',
       'BANNED',
       'MANUAL_MODE',
       'SUSPENDED',
       'NEEDS_ATTENTION',
       'NEEDS_REVIEW',
       'DISABLED',
       'QUARANTINED',
       'CHALLENGE_REQUIRED',
       'RESTRICTED',
       'COOLING_DOWN'
   );

-- G. Add comprehensive check constraint covering all operational statuses
ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS chk_accounts_status_valid;
ALTER TABLE public.accounts
    ADD CONSTRAINT chk_accounts_status_valid CHECK (
        status IN (
            'ACTIVE',
            'DISCONNECTED',
            'RATE_LIMITED',
            'BANNED',
            'MANUAL_MODE',
            'SUSPENDED',
            'NEEDS_ATTENTION',
            'NEEDS_REVIEW',
            'DISABLED',
            'QUARANTINED',
            'CHALLENGE_REQUIRED',
            'RESTRICTED',
            'COOLING_DOWN'
        )
    );

-- H. Recreate is_active as a clean generated column
ALTER TABLE public.accounts 
    ADD COLUMN is_active BOOLEAN GENERATED ALWAYS AS (status = 'ACTIVE') STORED;

-- ----------------------------------------------------------------------------
-- 2. ACCOUNT_DAILY_ACTION_COUNTS INTEGRITY & CONSTRAINTS (FLAW-ACC-DB-03, 04)
-- ----------------------------------------------------------------------------

-- A. Deduplicate existing rows in account_daily_action_counts
DELETE FROM public.account_daily_action_counts a
USING public.account_daily_action_counts b
WHERE a.id > b.id
  AND a.account_id = b.account_id
  AND a.action_type = b.action_type
  AND a.usage_date = b.usage_date;

-- B. Clean up orphaned rows where account no longer exists
DELETE FROM public.account_daily_action_counts
WHERE account_id NOT IN (SELECT id FROM public.accounts);

-- C. Enforce UNIQUE constraint on (account_id, action_type, usage_date)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_account_daily_action_counts'
    ) THEN
        ALTER TABLE public.account_daily_action_counts
            ADD CONSTRAINT uq_account_daily_action_counts UNIQUE (account_id, action_type, usage_date);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- D. Enforce ON DELETE CASCADE foreign key from account_daily_action_counts to accounts
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_adac_account'
    ) THEN
        ALTER TABLE public.account_daily_action_counts
            ADD CONSTRAINT fk_adac_account FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- E. Performance composite indexes
CREATE INDEX IF NOT EXISTS idx_adac_account_usage_date 
    ON public.account_daily_action_counts (account_id, usage_date);

CREATE INDEX IF NOT EXISTS idx_accounts_ws_status_active 
    ON public.accounts (workspace_id, status) WHERE status = 'ACTIVE';

-- ----------------------------------------------------------------------------
-- 3. ROW LEVEL SECURITY REPAIRS (FLAW-ACC-DB-05)
-- ----------------------------------------------------------------------------

ALTER TABLE public.account_daily_action_counts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS account_daily_action_counts_ws_select ON public.account_daily_action_counts;
DROP POLICY IF EXISTS account_daily_action_counts_ws_all ON public.account_daily_action_counts;

CREATE POLICY account_daily_action_counts_ws_all ON public.account_daily_action_counts
    FOR ALL
    USING (
        account_id IN (
            SELECT id FROM public.accounts 
            WHERE workspace_id IN (SELECT public.my_workspace_ids())
        )
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        account_id IN (
            SELECT id FROM public.accounts 
            WHERE workspace_id IN (SELECT public.my_workspace_ids())
        )
        OR auth.role() = 'service_role'
    );

-- ----------------------------------------------------------------------------
-- 4. RPC SECURITY HARDENING: MULTI-TENANT ISOLATION (FLAW-ACC-SEC-03, 07)
-- ----------------------------------------------------------------------------

-- A. get_decrypted_proxy_payload with workspace verification
CREATE OR REPLACE FUNCTION public.get_decrypted_proxy_payload(
    p_proxy_id uuid,
    p_workspace_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_secret_ref uuid;
    v_password_encrypted bytea;
    v_dek text := null;
BEGIN
    SELECT secret_ref, password_encrypted
    INTO v_secret_ref, v_password_encrypted
    FROM public.proxies
    WHERE id = p_proxy_id
      AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id);

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    IF v_secret_ref IS NOT NULL THEN
        SELECT decrypted_secret INTO v_dek
        FROM vault.decrypted_secrets
        WHERE id = v_secret_ref;
    END IF;

    RETURN jsonb_build_object(
        'secret_ref', v_secret_ref,
        'dek', v_dek,
        'password_encrypted', encode(v_password_encrypted, 'base64')
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.get_decrypted_proxy_payload(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_decrypted_proxy_payload(uuid, uuid) TO service_role;

-- B. get_decrypted_account_payload with workspace verification
CREATE OR REPLACE FUNCTION public.get_decrypted_account_payload(
    p_account_id uuid,
    p_workspace_id uuid DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_cookie_secret_ref uuid;
    v_session_cookies_encrypted bytea;
    v_dek text := null;
BEGIN
    SELECT cookie_secret_ref, session_cookies_encrypted
    INTO v_cookie_secret_ref, v_session_cookies_encrypted
    FROM public.accounts
    WHERE id = p_account_id
      AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id);

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    IF v_cookie_secret_ref IS NOT NULL THEN
        SELECT decrypted_secret INTO v_dek
        FROM vault.decrypted_secrets
        WHERE id = v_cookie_secret_ref;
    END IF;

    RETURN jsonb_build_object(
        'cookie_secret_ref', v_cookie_secret_ref,
        'dek', v_dek,
        'session_cookies_encrypted', encode(v_session_cookies_encrypted, 'base64')
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.get_decrypted_account_payload(uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_decrypted_account_payload(uuid, uuid) TO service_role;

-- ----------------------------------------------------------------------------
-- 5. ATOMIC RATE LIMIT RESOLUTION RPC (FLAW-ACC-POD-03)
-- Canonical database rate limit calculation matching Python services
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_account_action_limit(
    p_account_id  uuid,
    p_action_type text
) RETURNS integer
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_account RECORD;
    v_tier_limit integer;
    v_account_age_days integer;
    v_warmup_limit integer;
BEGIN
    SELECT 
        is_warmup,
        warmup_start_date,
        warmup_target_days,
        warmup_max_connections,
        warmup_max_messages,
        daily_connection_limit,
        daily_message_limit
    INTO v_account
    FROM public.accounts
    WHERE id = p_account_id;

    IF NOT FOUND THEN
        RETURN 0;
    END IF;

    -- Connection request limits
    IF p_action_type = 'connection_request' THEN
        IF v_account.is_warmup THEN
            v_account_age_days := GREATEST(0, (CURRENT_DATE - DATE(COALESCE(v_account.warmup_start_date, NOW()))));
            -- S-Curve linear progression up to warmup_max_connections
            v_warmup_limit := LEAST(
                COALESCE(v_account.warmup_max_connections, 20),
                GREATEST(8, 8 + (v_account_age_days * COALESCE(v_account.warmup_max_connections, 20)) / GREATEST(1, COALESCE(v_account.warmup_target_days, 30)))
            );
            RETURN v_warmup_limit;
        ELSE
            RETURN COALESCE(v_account.daily_connection_limit, 20);
        END IF;

    -- Message limits
    ELSIF p_action_type IN ('send_message', 'message') THEN
        IF v_account.is_warmup THEN
            v_account_age_days := GREATEST(0, (CURRENT_DATE - DATE(COALESCE(v_account.warmup_start_date, NOW()))));
            v_warmup_limit := LEAST(
                COALESCE(v_account.warmup_max_messages, 40),
                GREATEST(10, 10 + (v_account_age_days * COALESCE(v_account.warmup_max_messages, 40)) / GREATEST(1, COALESCE(v_account.warmup_target_days, 30)))
            );
            RETURN v_warmup_limit;
        ELSE
            RETURN COALESCE(v_account.daily_message_limit, 40);
        END IF;

    -- InMail limits
    ELSIF p_action_type = 'inmail' THEN
        RETURN 15;

    -- Fallback default
    ELSE
        SELECT daily_limit INTO v_tier_limit
        FROM public.action_type_limits
        WHERE action_type = p_action_type;
        
        RETURN COALESCE(v_tier_limit, 20);
    END IF;
END;
$$;

-- ============================================================================
-- END OF MIGRATION 105
-- ============================================================================
