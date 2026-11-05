-- ==============================================================================
-- MIGRATION 122: RPC OVERLOAD RECONCILIATION & STRICT TYPE CAST DEFENSE
-- ==============================================================================
-- PARANOIA FRAMEWORK: Layer 0, Layer 1 & Layer 2
-- 1. Eliminates PostgREST PGRST203 ambiguity by dropping the duplicate 8-parameter overload of release_lead_claim.
-- 2. Fixes PostgreSQL 42883 (operator does not exist: uuid = text) by ensuring strict type equivalence in lease_token matching.
-- 3. Drops any legacy release_lead_claim functions that conflict with the unified 9-parameter signature.
-- ==============================================================================

-- A. Drop duplicate/conflicting function signatures to eliminate PGRST203
DROP FUNCTION IF EXISTS public.release_lead_claim(UUID, UUID, TEXT, TEXT, TIMESTAMPTZ, JSONB, TEXT, INT);
DROP FUNCTION IF EXISTS public.release_lead_claim(UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, JSONB, TEXT, INT);

-- B. Install Unified, Canonical release_lead_claim with Polymorphic Lease Token Matching
CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node TEXT,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT,
    p_workspace_id UUID DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = CASE 
            -- Protect operator-initiated pause from being reverted by in-flight worker
            WHEN status = 'paused' THEN 'paused'
            ELSE p_next_status 
        END,
        current_node_id = COALESCE(p_next_node, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        attempts = COALESCE(p_attempts, attempts),
        retry_count = COALESCE(p_attempts, retry_count),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id 
      AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id)
      AND (
          p_lease_token IS NULL 
          OR lease_token = p_lease_token 
          OR lease_token::TEXT = p_lease_token::TEXT
      );
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION public.release_lead_claim(UUID, UUID, TEXT, TEXT, TIMESTAMPTZ, JSONB, TEXT, INT, UUID) TO authenticated, service_role;
