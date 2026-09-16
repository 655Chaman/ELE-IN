import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

sql = """
CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node UUID,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = p_next_status,
        current_node_id = COALESCE(p_next_node, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        attempts = COALESCE(p_attempts, attempts),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id AND lease_token = p_lease_token;
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;
"""

try:
    res = supabase.rpc('exec_sql', {'query': sql}).execute()
    print("exec_sql OK:", res.data)
except Exception as e:
    print("exec_sql Error:", e)

