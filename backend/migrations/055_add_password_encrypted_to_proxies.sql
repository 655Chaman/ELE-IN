BEGIN;

ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS password_encrypted BYTEA;

-- Create an RPC to safely retrieve the proxy DEK and encrypted password
CREATE OR REPLACE FUNCTION public.get_decrypted_proxy_payload(p_proxy_id uuid)
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
    WHERE id = p_proxy_id;

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

CREATE OR REPLACE FUNCTION public.cleanup_proxy_vault_secret()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF OLD.secret_ref IS NOT NULL THEN
        DELETE FROM vault.secrets WHERE id = OLD.secret_ref::uuid;
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trigger_cleanup_proxy_vault_secret ON public.proxies;
CREATE TRIGGER trigger_cleanup_proxy_vault_secret
    AFTER DELETE ON public.proxies
    FOR EACH ROW
    EXECUTE FUNCTION public.cleanup_proxy_vault_secret();

COMMIT;
