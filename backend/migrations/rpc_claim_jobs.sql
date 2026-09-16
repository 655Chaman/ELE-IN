-- Create atomic job claiming RPC for the job_processor worker
CREATE OR REPLACE FUNCTION claim_processing_jobs(claim_limit INT)
RETURNS TABLE (
  id UUID,
  workspace_id UUID,
  asset_id UUID,
  job_type TEXT,
  payload JSONB,
  status TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  RETURN QUERY
  WITH claimed AS (
    SELECT processing_jobs.id
    FROM processing_jobs
    WHERE processing_jobs.status = 'pending'
    ORDER BY processing_jobs.created_at ASC
    LIMIT claim_limit
    FOR UPDATE SKIP LOCKED
  )
  UPDATE processing_jobs
  SET status = 'running', updated_at = NOW()
  WHERE processing_jobs.id IN (SELECT claimed.id FROM claimed)
  RETURNING 
    processing_jobs.id,
    processing_jobs.workspace_id,
    processing_jobs.asset_id,
    processing_jobs.job_type,
    processing_jobs.payload,
    processing_jobs.status,
    processing_jobs.created_at,
    processing_jobs.updated_at;
END;
$$;
