-- ============================================================
-- Migration 008: B7 - Split Action Limits
-- Covers: Adding distinct rate limits for paid_inmail and meeting_invite
-- Safe to re-run
-- ============================================================

BEGIN;

INSERT INTO public.action_type_limits (action_type, daily_limit, tier, description) VALUES
  ('meeting_invite',       5,  3, 'LinkedIn Intro Call Invite via messaging'),
  ('paid_inmail',         15,  3, 'Paid InMail via Sales Navigator / Ads API')
ON CONFLICT (action_type) DO UPDATE 
SET daily_limit = EXCLUDED.daily_limit,
    description = EXCLUDED.description;

COMMIT;
