BEGIN;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "supabase_vault";
CREATE EXTENSION IF NOT EXISTS "pgsodium";

-- Add column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'accounts'
        AND column_name = 'cookie_secret_ref'
    ) THEN
        ALTER TABLE public.accounts ADD COLUMN cookie_secret_ref UUID;
    END IF;
END $$;

-- Function to store secret in vault and return UUID
CREATE OR REPLACE FUNCTION public.store_account_secret(p_secret text)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_secret_id uuid;
BEGIN
    SELECT vault.create_secret(p_secret, 'Account DEK') INTO v_secret_id;
    RETURN v_secret_id;
END;
$$;

-- Function to get decrypted payload
CREATE OR REPLACE FUNCTION public.get_decrypted_account_payload(p_account_id uuid)
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
    WHERE id = p_account_id;

    IF v_cookie_secret_ref IS NOT NULL THEN
        SELECT secret INTO v_dek
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

-- Cleanup trigger function
CREATE OR REPLACE FUNCTION public.cleanup_vault_secret()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF OLD.cookie_secret_ref IS NOT NULL THEN
        DELETE FROM vault.secrets WHERE id = OLD.cookie_secret_ref;
    END IF;
    RETURN OLD;
END;
$$;

-- Trigger
DROP TRIGGER IF EXISTS trigger_cleanup_vault_secret ON public.accounts;
CREATE TRIGGER trigger_cleanup_vault_secret
    AFTER DELETE ON public.accounts
    FOR EACH ROW
    EXECUTE FUNCTION public.cleanup_vault_secret();

COMMIT;
