BEGIN;

-- 1. Add Primary Key to daily_workspace_stats
-- Clean up any duplicates before adding the constraint
WITH duplicates AS (
    SELECT ctid,
           ROW_NUMBER() OVER (PARTITION BY workspace_id, stat_date ORDER BY ctid) as row_num
    FROM public.daily_workspace_stats
)
DELETE FROM public.daily_workspace_stats WHERE ctid IN (SELECT ctid FROM duplicates WHERE row_num > 1);

ALTER TABLE public.daily_workspace_stats
  ALTER COLUMN workspace_id SET NOT NULL,
  ALTER COLUMN stat_date SET NOT NULL;

-- Drop the unique constraint if it exists to replace with PK
ALTER TABLE public.daily_workspace_stats 
  DROP CONSTRAINT IF EXISTS daily_workspace_stats_ws_date_uniq;

ALTER TABLE public.daily_workspace_stats
  ADD CONSTRAINT pk_daily_workspace_stats PRIMARY KEY (workspace_id, stat_date);

-- 2. Add Unique Constraint to daily_campaign_stats
-- Clean up any duplicates before adding the constraint (just in case they exist)
WITH duplicates AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY campaign_id, stat_date) as row_num
    FROM public.daily_campaign_stats
)
DELETE FROM public.daily_campaign_stats WHERE id IN (SELECT id FROM duplicates WHERE row_num > 1);

ALTER TABLE public.daily_campaign_stats 
  DROP CONSTRAINT IF EXISTS uq_campaign_stat_date;
ALTER TABLE public.daily_campaign_stats 
  ADD CONSTRAINT uq_campaign_stat_date UNIQUE (campaign_id, stat_date);

COMMIT;
