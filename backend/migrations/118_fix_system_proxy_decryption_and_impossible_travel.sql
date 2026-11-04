-- ============================================================================
-- Migration 118: Fix System Proxy Decryption & Impossible Travel Telemetry
-- ============================================================================
-- 1. Fixes get_decrypted_proxy_payload RPC to allow shared system proxies (workspace_id IS NULL)
--    to be decrypted by any authenticated workspace without failing tenant isolation checks (FLAW-20).
-- 2. Creates impossible_travel_logs table for audit trail of geodesic velocity anomalies (FLAW-03).
-- 3. Ensures accounts table possesses geographic footprint and extension heartbeat columns.

-- A. Patch get_decrypted_proxy_payload
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
    -- Paranoia Layer 1: Allow decryption if:
    -- 1. No workspace specified (system service role)
    -- 2. Proxy is a shared system proxy (workspace_id IS NULL)
    -- 3. Proxy belongs to the requesting workspace (workspace_id = p_workspace_id)
    SELECT secret_ref, password_encrypted
    INTO v_secret_ref, v_password_encrypted
    FROM public.proxies
    WHERE id = p_proxy_id
      AND (p_workspace_id IS NULL OR workspace_id IS NULL OR workspace_id = p_workspace_id);

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

-- B. Forensic Audit Trail: Impossible Travel Logs
CREATE TABLE IF NOT EXISTS public.impossible_travel_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid NOT NULL,
    prev_country text,
    curr_country text,
    prev_ip text,
    curr_ip text,
    distance_km numeric,
    velocity_kmh numeric,
    channel text,
    detected_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_impossible_travel_acc_time 
    ON public.impossible_travel_logs (account_id, detected_at DESC);

-- C. Geographic Footprint & Heartbeat Columns on Accounts
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accounts' AND column_name = 'last_country_code') THEN
        ALTER TABLE public.accounts ADD COLUMN last_country_code text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accounts' AND column_name = 'last_ip') THEN
        ALTER TABLE public.accounts ADD COLUMN last_ip text;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accounts' AND column_name = 'last_geo_lat') THEN
        ALTER TABLE public.accounts ADD COLUMN last_geo_lat double precision;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accounts' AND column_name = 'last_geo_lon') THEN
        ALTER TABLE public.accounts ADD COLUMN last_geo_lon double precision;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'accounts' AND column_name = 'last_extension_active_at') THEN
        ALTER TABLE public.accounts ADD COLUMN last_extension_active_at timestamptz;
    END IF;
END $$;
