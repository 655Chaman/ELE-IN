-- Fix the RPC get_decrypted_account_payload to select decrypted_secret instead of secret
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
