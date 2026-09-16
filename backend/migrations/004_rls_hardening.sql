
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "accounts_service_bypass" ON public.accounts
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "accounts_workspace_isolation" ON public.accounts
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.action_log ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "action_log_service_bypass" ON public.action_log
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "action_log_workspace_isolation" ON public.action_log
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "api_keys_service_bypass" ON public.api_keys
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "api_keys_workspace_isolation" ON public.api_keys
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.approval_queue ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "approval_queue_service_bypass" ON public.approval_queue
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "approval_queue_workspace_isolation" ON public.approval_queue
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.campaigns ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "campaigns_service_bypass" ON public.campaigns
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "campaigns_workspace_isolation" ON public.campaigns
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.daily_campaign_stats ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "daily_campaign_stats_service_bypass" ON public.daily_campaign_stats
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "daily_campaign_stats_workspace_isolation" ON public.daily_campaign_stats
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.knowledge_assets ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "knowledge_assets_service_bypass" ON public.knowledge_assets
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "knowledge_assets_workspace_isolation" ON public.knowledge_assets
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.knowledge_chunks ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "knowledge_chunks_service_bypass" ON public.knowledge_chunks
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "knowledge_chunks_workspace_isolation" ON public.knowledge_chunks
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.knowledge_synthesis ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "knowledge_synthesis_service_bypass" ON public.knowledge_synthesis
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "knowledge_synthesis_workspace_isolation" ON public.knowledge_synthesis
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.knowledge_vectors ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "knowledge_vectors_service_bypass" ON public.knowledge_vectors
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "knowledge_vectors_workspace_isolation" ON public.knowledge_vectors
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.lead_lists ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "lead_lists_service_bypass" ON public.lead_lists
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "lead_lists_workspace_isolation" ON public.lead_lists
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "leads_service_bypass" ON public.leads
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "leads_workspace_isolation" ON public.leads
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "messages_service_bypass" ON public.messages
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "messages_workspace_isolation" ON public.messages
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.objections ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "objections_service_bypass" ON public.objections
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "objections_workspace_isolation" ON public.objections
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.personas ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "personas_service_bypass" ON public.personas
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "personas_workspace_isolation" ON public.personas
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.proxies ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "proxies_service_bypass" ON public.proxies
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "proxies_workspace_isolation" ON public.proxies
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.suppression_list ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "suppression_list_service_bypass" ON public.suppression_list
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "suppression_list_workspace_isolation" ON public.suppression_list
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.ai_generations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "ai_generations_service_bypass" ON public.ai_generations
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "ai_generations_workspace_isolation" ON public.ai_generations
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.workspace_integrations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "workspace_integrations_service_bypass" ON public.workspace_integrations
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "workspace_integrations_workspace_isolation" ON public.workspace_integrations
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "workspace_members_service_bypass" ON public.workspace_members
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "workspace_members_workspace_isolation" ON public.workspace_members
    FOR ALL
    USING (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ))
    WITH CHECK (workspace_id IN (
      SELECT wm.workspace_id FROM public.workspace_members wm
      WHERE wm.user_id = auth.uid()
      UNION
      SELECT w.id FROM public.workspaces w
      WHERE w.owner_id = auth.uid()
    ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "user_profiles_service_bypass" ON public.user_profiles
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "user_profiles_own_profile" ON public.user_profiles
    FOR ALL
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
