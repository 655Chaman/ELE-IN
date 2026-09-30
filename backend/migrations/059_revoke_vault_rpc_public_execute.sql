-- Revoke PUBLIC execute permissions from sensitive vault RPCs
REVOKE EXECUTE ON FUNCTION public.get_decrypted_account_payload(uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.get_decrypted_account_payload(uuid) FROM anon, authenticated;

REVOKE EXECUTE ON FUNCTION public.get_decrypted_proxy_payload(uuid) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.get_decrypted_proxy_payload(uuid) FROM anon, authenticated;

REVOKE EXECUTE ON FUNCTION public.store_account_secret(text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.store_account_secret(text) FROM anon, authenticated;

-- Ensure service_role retains execute permissions
GRANT EXECUTE ON FUNCTION public.get_decrypted_account_payload(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_decrypted_proxy_payload(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.store_account_secret(text) TO service_role;
