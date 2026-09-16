-- Part 1: Fix workspace_members policy to avoid infinite recursion

-- Drop the broken recursive policy
DROP POLICY IF EXISTS "workspace_members_workspace_isolation" ON public.workspace_members;
DROP POLICY IF EXISTS "workspace_members_service_bypass" ON public.workspace_members;

-- Service role bypasses all RLS
DO $$ BEGIN
  CREATE POLICY "workspace_members_service_bypass" ON public.workspace_members
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Non-recursive: user sees their own rows, or rows for workspaces they own
DO $$ BEGIN
  CREATE POLICY "workspace_members_self_or_owner" ON public.workspace_members
    FOR ALL
    USING (
      user_id = auth.uid()  -- they are the member
      OR workspace_id IN (
        SELECT id FROM public.workspaces WHERE owner_id = auth.uid()  -- they own the workspace
      )
    )
    WITH CHECK (
      user_id = auth.uid()
      OR workspace_id IN (
        SELECT id FROM public.workspaces WHERE owner_id = auth.uid()
      )
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Part 2: Create a security definer function to avoid RLS recursion when looking up workspaces

-- Create a security definer function that bypasses RLS to get workspace IDs for a user
CREATE OR REPLACE FUNCTION public.get_user_workspace_ids()
RETURNS SETOF UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
  UNION
  SELECT id FROM public.workspaces WHERE owner_id = auth.uid();
$$;

-- Part 3: Update all workspace-scoped tables to use the new security definer function

-- Table: accounts
DROP POLICY IF EXISTS "accounts_workspace_isolation" ON public.accounts;
DROP POLICY IF EXISTS "accounts_service_bypass" ON public.accounts;
DO $$ BEGIN
  CREATE POLICY "accounts_service_bypass" ON public.accounts USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "accounts_workspace_isolation" ON public.accounts FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: action_log
DROP POLICY IF EXISTS "action_log_workspace_isolation" ON public.action_log;
DROP POLICY IF EXISTS "action_log_service_bypass" ON public.action_log;
DO $$ BEGIN
  CREATE POLICY "action_log_service_bypass" ON public.action_log USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "action_log_workspace_isolation" ON public.action_log FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: api_keys
DROP POLICY IF EXISTS "api_keys_workspace_isolation" ON public.api_keys;
DROP POLICY IF EXISTS "api_keys_service_bypass" ON public.api_keys;
DO $$ BEGIN
  CREATE POLICY "api_keys_service_bypass" ON public.api_keys USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "api_keys_workspace_isolation" ON public.api_keys FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: approval_queue
DROP POLICY IF EXISTS "approval_queue_workspace_isolation" ON public.approval_queue;
DROP POLICY IF EXISTS "approval_queue_service_bypass" ON public.approval_queue;
DO $$ BEGIN
  CREATE POLICY "approval_queue_service_bypass" ON public.approval_queue USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "approval_queue_workspace_isolation" ON public.approval_queue FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: campaigns
DROP POLICY IF EXISTS "campaigns_workspace_isolation" ON public.campaigns;
DROP POLICY IF EXISTS "campaigns_service_bypass" ON public.campaigns;
DO $$ BEGIN
  CREATE POLICY "campaigns_service_bypass" ON public.campaigns USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "campaigns_workspace_isolation" ON public.campaigns FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: daily_campaign_stats
DROP POLICY IF EXISTS "daily_campaign_stats_workspace_isolation" ON public.daily_campaign_stats;
DROP POLICY IF EXISTS "daily_campaign_stats_service_bypass" ON public.daily_campaign_stats;
DO $$ BEGIN
  CREATE POLICY "daily_campaign_stats_service_bypass" ON public.daily_campaign_stats USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "daily_campaign_stats_workspace_isolation" ON public.daily_campaign_stats FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: knowledge_assets
DROP POLICY IF EXISTS "knowledge_assets_workspace_isolation" ON public.knowledge_assets;
DROP POLICY IF EXISTS "knowledge_assets_service_bypass" ON public.knowledge_assets;
DO $$ BEGIN
  CREATE POLICY "knowledge_assets_service_bypass" ON public.knowledge_assets USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "knowledge_assets_workspace_isolation" ON public.knowledge_assets FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: knowledge_chunks
DROP POLICY IF EXISTS "knowledge_chunks_workspace_isolation" ON public.knowledge_chunks;
DROP POLICY IF EXISTS "knowledge_chunks_service_bypass" ON public.knowledge_chunks;
DO $$ BEGIN
  CREATE POLICY "knowledge_chunks_service_bypass" ON public.knowledge_chunks USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "knowledge_chunks_workspace_isolation" ON public.knowledge_chunks FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: knowledge_synthesis
DROP POLICY IF EXISTS "knowledge_synthesis_workspace_isolation" ON public.knowledge_synthesis;
DROP POLICY IF EXISTS "knowledge_synthesis_service_bypass" ON public.knowledge_synthesis;
DO $$ BEGIN
  CREATE POLICY "knowledge_synthesis_service_bypass" ON public.knowledge_synthesis USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "knowledge_synthesis_workspace_isolation" ON public.knowledge_synthesis FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: knowledge_vectors
DROP POLICY IF EXISTS "knowledge_vectors_workspace_isolation" ON public.knowledge_vectors;
DROP POLICY IF EXISTS "knowledge_vectors_service_bypass" ON public.knowledge_vectors;
DO $$ BEGIN
  CREATE POLICY "knowledge_vectors_service_bypass" ON public.knowledge_vectors USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "knowledge_vectors_workspace_isolation" ON public.knowledge_vectors FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: lead_lists
DROP POLICY IF EXISTS "lead_lists_workspace_isolation" ON public.lead_lists;
DROP POLICY IF EXISTS "lead_lists_service_bypass" ON public.lead_lists;
DO $$ BEGIN
  CREATE POLICY "lead_lists_service_bypass" ON public.lead_lists USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "lead_lists_workspace_isolation" ON public.lead_lists FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: leads
DROP POLICY IF EXISTS "leads_workspace_isolation" ON public.leads;
DROP POLICY IF EXISTS "leads_service_bypass" ON public.leads;
DO $$ BEGIN
  CREATE POLICY "leads_service_bypass" ON public.leads USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "leads_workspace_isolation" ON public.leads FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: messages
DROP POLICY IF EXISTS "messages_workspace_isolation" ON public.messages;
DROP POLICY IF EXISTS "messages_service_bypass" ON public.messages;
DO $$ BEGIN
  CREATE POLICY "messages_service_bypass" ON public.messages USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "messages_workspace_isolation" ON public.messages FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: objections
DROP POLICY IF EXISTS "objections_workspace_isolation" ON public.objections;
DROP POLICY IF EXISTS "objections_service_bypass" ON public.objections;
DO $$ BEGIN
  CREATE POLICY "objections_service_bypass" ON public.objections USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "objections_workspace_isolation" ON public.objections FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: personas
DROP POLICY IF EXISTS "personas_workspace_isolation" ON public.personas;
DROP POLICY IF EXISTS "personas_service_bypass" ON public.personas;
DO $$ BEGIN
  CREATE POLICY "personas_service_bypass" ON public.personas USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "personas_workspace_isolation" ON public.personas FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: proxies
DROP POLICY IF EXISTS "proxies_workspace_isolation" ON public.proxies;
DROP POLICY IF EXISTS "proxies_service_bypass" ON public.proxies;
DO $$ BEGIN
  CREATE POLICY "proxies_service_bypass" ON public.proxies USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "proxies_workspace_isolation" ON public.proxies FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: suppression_list
DROP POLICY IF EXISTS "suppression_list_workspace_isolation" ON public.suppression_list;
DROP POLICY IF EXISTS "suppression_list_service_bypass" ON public.suppression_list;
DO $$ BEGIN
  CREATE POLICY "suppression_list_service_bypass" ON public.suppression_list USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "suppression_list_workspace_isolation" ON public.suppression_list FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: ai_generations
DROP POLICY IF EXISTS "ai_generations_workspace_isolation" ON public.ai_generations;
DROP POLICY IF EXISTS "ai_generations_service_bypass" ON public.ai_generations;
DO $$ BEGIN
  CREATE POLICY "ai_generations_service_bypass" ON public.ai_generations USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "ai_generations_workspace_isolation" ON public.ai_generations FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Table: workspace_integrations
DROP POLICY IF EXISTS "workspace_integrations_workspace_isolation" ON public.workspace_integrations;
DROP POLICY IF EXISTS "workspace_integrations_service_bypass" ON public.workspace_integrations;
DO $$ BEGIN
  CREATE POLICY "workspace_integrations_service_bypass" ON public.workspace_integrations USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY "workspace_integrations_workspace_isolation" ON public.workspace_integrations FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
