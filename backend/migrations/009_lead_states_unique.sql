DO $$ BEGIN 
    ALTER TABLE public.lead_states 
    ADD CONSTRAINT lead_states_campaign_opportunity_unique 
    UNIQUE (campaign_id, opportunity_id);
EXCEPTION 
    WHEN duplicate_table THEN null; 
END $$;
