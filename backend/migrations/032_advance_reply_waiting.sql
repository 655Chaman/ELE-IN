CREATE OR REPLACE FUNCTION public.advance_reply_waiting_leads(p_lead_id uuid)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE v_count integer;
BEGIN
  UPDATE public.campaign_execution_states ces
  SET status = 'pending', next_run_at = now(),
      lease_token = NULL, lease_expires_at = NULL, updated_at = now()
  FROM public.campaign_enrollments ce
  WHERE ce.id = ces.enrollment_id
    AND ce.lead_id = p_lead_id
    AND ces.status = 'waiting_for_reply';
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END; $$;
