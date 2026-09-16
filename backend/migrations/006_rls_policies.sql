-- ============================================================
-- Migration 006: A3 - Missing RLS Policies (Corrected)
-- Covers: Adding RLS to tables from migrations 003 and 004
-- Safe to re-run
-- ============================================================

BEGIN;

-- 1. account_daily_action_counts (from 003)
ALTER TABLE public.account_daily_action_counts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_daily_action_counts_ws_select ON public.account_daily_action_counts;
CREATE POLICY account_daily_action_counts_ws_select ON public.account_daily_action_counts FOR SELECT
    USING (account_id IN (SELECT id FROM public.accounts WHERE workspace_id IN (SELECT public.my_workspace_ids())));

-- 2. action_type_limits (from 003)
ALTER TABLE public.action_type_limits ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS action_type_limits_select ON public.action_type_limits;
CREATE POLICY action_type_limits_select ON public.action_type_limits FOR SELECT USING (true);

-- 3. profile_activity_snapshots (from 004)
ALTER TABLE public.profile_activity_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS profile_activity_snapshots_ws_select ON public.profile_activity_snapshots;
CREATE POLICY profile_activity_snapshots_ws_select ON public.profile_activity_snapshots FOR SELECT
    USING (lead_id IN (SELECT id FROM public.leads WHERE workspace_id IN (SELECT public.my_workspace_ids())));

-- 4. lead_tags (from 004)
ALTER TABLE public.lead_tags ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lead_tags_ws_select ON public.lead_tags;
CREATE POLICY lead_tags_ws_select ON public.lead_tags FOR SELECT
    USING (lead_id IN (SELECT id FROM public.leads WHERE workspace_id IN (SELECT public.my_workspace_ids())));
DROP POLICY IF EXISTS lead_tags_ws_all ON public.lead_tags;
CREATE POLICY lead_tags_ws_all ON public.lead_tags FOR ALL
    USING (lead_id IN (SELECT id FROM public.leads WHERE workspace_id IN (SELECT public.my_workspace_ids())));

-- 5. voice_notes (from 004)
ALTER TABLE public.voice_notes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS voice_notes_ws_select ON public.voice_notes;
CREATE POLICY voice_notes_ws_select ON public.voice_notes FOR SELECT
    USING (workspace_id IN (SELECT public.my_workspace_ids()));
DROP POLICY IF EXISTS voice_notes_ws_all ON public.voice_notes;
CREATE POLICY voice_notes_ws_all ON public.voice_notes FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- 6. enrichment_results (from 004)
ALTER TABLE public.enrichment_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS enrichment_results_ws_select ON public.enrichment_results;
CREATE POLICY enrichment_results_ws_select ON public.enrichment_results FOR SELECT
    USING (lead_id IN (SELECT id FROM public.leads WHERE workspace_id IN (SELECT public.my_workspace_ids())));
DROP POLICY IF EXISTS enrichment_results_ws_all ON public.enrichment_results;
CREATE POLICY enrichment_results_ws_all ON public.enrichment_results FOR ALL
    USING (lead_id IN (SELECT id FROM public.leads WHERE workspace_id IN (SELECT public.my_workspace_ids())));

COMMIT;
