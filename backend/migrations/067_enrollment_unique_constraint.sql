ALTER TABLE public.campaign_enrollments
ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
