-- Migration: 035_lead_lists_regions_and_status
-- Description: Add timezone/region and missing status tracking columns to lead_lists

ALTER TABLE public.lead_lists
ADD COLUMN target_timezone TEXT NOT NULL DEFAULT 'UTC',
ADD COLUMN target_region_label TEXT,
ADD COLUMN status TEXT,
ADD COLUMN error_message TEXT;
