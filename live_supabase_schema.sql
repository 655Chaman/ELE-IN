-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.account_daily_usage (
  account_id uuid NOT NULL,
  usage_date date NOT NULL,
  connections_sent integer NOT NULL DEFAULT 0,
  messages_sent integer NOT NULL DEFAULT 0,
  CONSTRAINT account_daily_usage_pkey PRIMARY KEY (account_id, usage_date)
);
CREATE TABLE public.action_type_limits (
  action_type text NOT NULL,
  daily_limit integer NOT NULL,
  tier integer NOT NULL DEFAULT 1,
  description text,
  CONSTRAINT action_type_limits_pkey PRIMARY KEY (action_type)
);
CREATE TABLE public.account_daily_action_counts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL,
  action_type text NOT NULL,
  usage_date date NOT NULL DEFAULT CURRENT_DATE,
  count integer NOT NULL DEFAULT 0,
  CONSTRAINT account_daily_action_counts_pkey PRIMARY KEY (id),
  CONSTRAINT account_daily_action_counts_action_type_fkey FOREIGN KEY (action_type) REFERENCES public.action_type_limits(action_type)
);
CREATE TABLE public.suppression_list (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  linkedin_url text,
  email text,
  reason text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  domain text,
  value text,
  CONSTRAINT suppression_list_pkey PRIMARY KEY (id)
);
CREATE TABLE public.lead_tags (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lead_id uuid NOT NULL,
  tag text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  workspace_id uuid NOT NULL,
  CONSTRAINT lead_tags_pkey PRIMARY KEY (id),
  CONSTRAINT lead_tags_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.ai_generations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  lead_id uuid,
  node_id uuid,
  prompt text,
  output text,
  model text,
  tokens_used integer,
  cost numeric,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  campaign_id uuid,
  enrollment_id uuid,
  billing_source text CHECK (billing_source = ANY (ARRAY['platform'::text, 'byok'::text])),
  CONSTRAINT ai_generations_pkey PRIMARY KEY (id),
  CONSTRAINT ai_generations_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.campaign_nodes(id),
  CONSTRAINT ai_generations_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT ai_generations_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id)
);
CREATE TABLE public.enrichment_results (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lead_id uuid NOT NULL,
  provider text NOT NULL,
  field text NOT NULL,
  value text,
  cost numeric,
  fetched_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT enrichment_results_pkey PRIMARY KEY (id)
);
CREATE TABLE public.workspace_integrations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  provider text NOT NULL,
  encrypted_credentials bytea NOT NULL,
  status text NOT NULL DEFAULT 'active'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT workspace_integrations_pkey PRIMARY KEY (id)
);
CREATE TABLE public.voice_notes (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  lead_id uuid NOT NULL,
  storage_path text NOT NULL,
  duration_seconds integer,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT voice_notes_pkey PRIMARY KEY (id)
);
CREATE TABLE public.profile_activity_snapshots (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lead_id uuid NOT NULL,
  follower_count integer,
  mutual_connections integer,
  has_recent_posts boolean,
  last_post_date timestamp with time zone,
  is_recently_active boolean,
  is_open_profile boolean,
  is_premium boolean,
  raw_json jsonb,
  captured_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT profile_activity_snapshots_pkey PRIMARY KEY (id)
);
CREATE TABLE public.worker_heartbeat (
  worker_id text NOT NULL,
  last_beat_at timestamp with time zone NOT NULL DEFAULT now(),
  tick_count bigint NOT NULL DEFAULT 0,
  last_tick_duration_ms integer,
  last_tick_leads_processed integer,
  status text NOT NULL DEFAULT 'alive'::text,
  metadata jsonb DEFAULT '{}'::jsonb,
  CONSTRAINT worker_heartbeat_pkey PRIMARY KEY (worker_id)
);
CREATE TABLE public.knowledge_vectors (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  asset_id uuid NOT NULL,
  content text NOT NULL,
  embedding USER-DEFINED,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT knowledge_vectors_pkey PRIMARY KEY (id)
);
CREATE TABLE public.processing_jobs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  asset_id uuid,
  job_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending'::text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_msg text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  completed_at timestamp with time zone,
  metadata jsonb,
  idempotency_key text,
  CONSTRAINT processing_jobs_pkey PRIMARY KEY (id),
  CONSTRAINT fk_processing_jobs_asset FOREIGN KEY (asset_id) REFERENCES public.knowledge_assets(id)
);
CREATE TABLE public.daily_workspace_stats (
  workspace_id uuid NOT NULL,
  stat_date date NOT NULL,
  total_leads integer DEFAULT 0,
  active_campaigns integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  total_campaigns integer DEFAULT 0,
  CONSTRAINT daily_workspace_stats_pkey PRIMARY KEY (workspace_id, stat_date)
);
CREATE TABLE public.user_profiles (
  id uuid NOT NULL,
  display_name text,
  avatar_url text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT user_profiles_pkey PRIMARY KEY (id),
  CONSTRAINT user_profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id)
);
CREATE TABLE public.admin_grants (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  granted_by uuid,
  granted_at timestamp with time zone NOT NULL DEFAULT now(),
  revoked_at timestamp with time zone,
  revoked_by uuid,
  reason text,
  CONSTRAINT admin_grants_pkey PRIMARY KEY (id),
  CONSTRAINT admin_grants_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id),
  CONSTRAINT admin_grants_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES auth.users(id),
  CONSTRAINT admin_grants_revoked_by_fkey FOREIGN KEY (revoked_by) REFERENCES auth.users(id)
);
CREATE TABLE public.workspaces (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  owner_id uuid NOT NULL,
  name text NOT NULL,
  tier USER-DEFINED NOT NULL DEFAULT 'FREE'::subscription_tier,
  stripe_customer_id text UNIQUE,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  last_queue_poll_at timestamp with time zone NOT NULL DEFAULT '-infinity'::timestamp with time zone,
  require_2fa boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active'::text,
  deletion_requested_at timestamp with time zone,
  hubspot_token text,
  hubspot_won_stage_id text,
  agency_id uuid,
  ai_reply_confidence_threshold double precision DEFAULT 0.65,
  llm_provider text CHECK (llm_provider = ANY (ARRAY['openai'::text, 'nvidia'::text, 'openrouter'::text, 'anthropic'::text, 'gemini'::text, 'moonshot'::text, 'deepseek'::text])),
  llm_model text,
  data_cleaning_credits integer NOT NULL DEFAULT 0,
  billing_status text DEFAULT 'active'::text,
  auto_recharge_settings jsonb DEFAULT '{"enabled": false, "last_recharged_at": null, "threshold_credits": 100, "recharge_package_id": "credits_1000", "recharges_this_month": 0, "max_monthly_recharges": 5}'::jsonb,
  webhook_signing_secret text,
  sending_window jsonb DEFAULT '{"end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"], "start": "09:00", "timezone": "UTC"}'::jsonb,
  allocated_credit_budget integer NOT NULL DEFAULT 0,
  monthly_credit_quota integer NOT NULL DEFAULT 0,
  exhaustion_alert_threshold integer NOT NULL DEFAULT 100,
  ai_provider text DEFAULT 'nvidia'::text,
  ai_model text DEFAULT 'meta/llama-3.1-70b-instruct'::text,
  custom_llm_api_key text,
  ai_temperature numeric DEFAULT 0.70,
  agency_credit_quota integer,
  agency_credits_allocated integer DEFAULT 0,
  CONSTRAINT workspaces_pkey PRIMARY KEY (id),
  CONSTRAINT workspaces_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES auth.users(id),
  CONSTRAINT workspaces_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agencies(id)
);
CREATE TABLE public.workspace_members (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  user_id uuid NOT NULL,
  role USER-DEFINED NOT NULL DEFAULT 'member'::workspace_member_role,
  invited_by uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT workspace_members_pkey PRIMARY KEY (id),
  CONSTRAINT workspace_members_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT workspace_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id),
  CONSTRAINT workspace_members_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES auth.users(id)
);
CREATE TABLE public.subscriptions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  stripe_subscription_id text NOT NULL UNIQUE,
  stripe_price_id text,
  status text NOT NULL,
  tier USER-DEFINED NOT NULL DEFAULT 'FREE'::subscription_tier,
  current_period_start timestamp with time zone,
  current_period_end timestamp with time zone,
  cancel_at_period_end boolean NOT NULL DEFAULT false,
  canceled_at timestamp with time zone,
  trial_end timestamp with time zone,
  raw_stripe_event jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT subscriptions_pkey PRIMARY KEY (id),
  CONSTRAINT subscriptions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.proxies (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid,
  provider text NOT NULL,
  host text NOT NULL,
  port integer NOT NULL,
  username text,
  secret_ref text,
  protocol text NOT NULL DEFAULT 'http'::text,
  country_code character,
  status USER-DEFINED NOT NULL DEFAULT 'healthy'::proxy_status,
  last_checked_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  password_encrypted bytea,
  source text,
  label text,
  is_active boolean DEFAULT true,
  password text,
  country text,
  exit_ip text,
  latency_ms integer DEFAULT 0,
  quarantined_until timestamp with time zone,
  failure_count integer DEFAULT 0,
  health_score integer DEFAULT 100,
  quarantine_reason text,
  CONSTRAINT proxies_pkey PRIMARY KEY (id),
  CONSTRAINT proxies_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.accounts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  proxy_id uuid,
  name text NOT NULL,
  linkedin_profile_url text,
  session_cookies_encrypted bytea,
  is_warmup boolean NOT NULL DEFAULT false,
  warmup_start_date timestamp with time zone,
  warmup_target_days integer NOT NULL DEFAULT 30,
  warmup_max_connections integer NOT NULL DEFAULT 20,
  warmup_max_messages integer NOT NULL DEFAULT 40,
  status USER-DEFINED NOT NULL DEFAULT 'ACTIVE'::account_status,
  is_active boolean NOT NULL DEFAULT (status = 'ACTIVE'::account_status),
  last_health_check_at timestamp with time zone,
  cookie_expires_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  session_locked_until timestamp with time zone,
  manual_send_suspected boolean DEFAULT false,
  manual_send_suspected_at timestamp with time zone,
  cookie_secret_ref uuid,
  session_lock_worker_id text,
  status_changed_at timestamp with time zone NOT NULL DEFAULT now(),
  proxy_country text,
  health_score numeric DEFAULT 100,
  quarantined_until timestamp with time zone,
  auto_heal_status text,
  auto_heal_actions jsonb DEFAULT '[]'::jsonb,
  quarantine_reason text,
  is_pod_eligible boolean DEFAULT true,
  daily_connection_limit integer NOT NULL DEFAULT 20,
  daily_message_limit integer NOT NULL DEFAULT 40,
  preferred_proxy_id uuid,
  CONSTRAINT accounts_pkey PRIMARY KEY (id),
  CONSTRAINT accounts_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT accounts_proxy_id_fkey FOREIGN KEY (proxy_id) REFERENCES public.proxies(id)
);
CREATE TABLE public.campaigns (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  name text NOT NULL,
  status USER-DEFINED NOT NULL DEFAULT 'DRAFT'::campaign_status,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  nodes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  edges_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  sender_account_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  pod_dispatch_strategy text DEFAULT 'CAPACITY_WEIGHTED'::text,
  pod_failover_enabled boolean DEFAULT true,
  pod_emergency_paused boolean DEFAULT false,
  pod_pause_reason text,
  lead_list_id uuid,
  CONSTRAINT campaigns_pkey PRIMARY KEY (id),
  CONSTRAINT campaigns_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT campaigns_lead_list_id_fkey FOREIGN KEY (lead_list_id) REFERENCES public.lead_lists(id)
);
CREATE TABLE public.leads (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  first_name text,
  last_name text,
  linkedin_url text NOT NULL,
  company_name text,
  email text,
  domain text,
  job_title text,
  company_description text,
  location text,
  industry text,
  mutual_connections text,
  enrichment_source text DEFAULT 'csv'::text,
  status USER-DEFINED NOT NULL DEFAULT 'extracted'::lead_status,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  timezone text,
  hubspot_deal_id text,
  is_unsubscribed boolean DEFAULT false,
  unsubscribed_at timestamp with time zone,
  social_intent_score integer DEFAULT 0,
  social_intent_tier text DEFAULT 'COLD'::text,
  last_social_scan_at timestamp with time zone,
  best_outreach_angle text,
  social_icebreaker text,
  recommended_timing text DEFAULT 'PASSIVE_WARMUP'::text,
  deal_stage text DEFAULT 'NEW_REPLY'::text,
  deal_stage_updated_at timestamp with time zone DEFAULT now(),
  deal_estimated_value numeric DEFAULT 0,
  last_objection_type text,
  last_objection_at timestamp with time zone,
  is_open_profile boolean DEFAULT false,
  last_social_retargeted_at timestamp with time zone,
  quarantine_reason text,
  email_classification text DEFAULT 'CORPORATE'::text,
  is_role_based boolean DEFAULT false,
  is_disposable boolean DEFAULT false,
  deliverability_risk text DEFAULT 'SAFE'::text,
  CONSTRAINT leads_pkey PRIMARY KEY (id),
  CONSTRAINT leads_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.lead_lists (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  name text NOT NULL,
  type text NOT NULL DEFAULT 'csv'::text,
  row_count integer NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  target_timezone text NOT NULL DEFAULT 'UTC'::text,
  target_region_label text,
  status text,
  error_message text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT lead_lists_pkey PRIMARY KEY (id),
  CONSTRAINT lead_lists_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.list_members (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  list_id uuid NOT NULL,
  opportunity_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  CONSTRAINT list_members_pkey PRIMARY KEY (id),
  CONSTRAINT list_members_list_id_fkey FOREIGN KEY (list_id) REFERENCES public.lead_lists(id),
  CONSTRAINT list_members_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES public.leads(id),
  CONSTRAINT list_members_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.action_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  account_id uuid,
  execution_state_id uuid,
  action_type text NOT NULL,
  result text NOT NULL DEFAULT 'success'::text,
  error_detail text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  executed_at timestamp with time zone NOT NULL DEFAULT now(),
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT action_log_pkey PRIMARY KEY (id),
  CONSTRAINT action_log_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT action_log_execution_state_id_fkey FOREIGN KEY (execution_state_id) REFERENCES public.campaign_execution_states(id),
  CONSTRAINT action_log_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.messages (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  account_id uuid,
  lead_id uuid,
  sender_name text NOT NULL,
  message_text text NOT NULL,
  direction USER-DEFINED NOT NULL,
  intent text NOT NULL DEFAULT 'unknown'::text,
  intent_confidence double precision NOT NULL DEFAULT 0.0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  campaign_id uuid,
  enrollment_id uuid,
  node_id uuid,
  thread_url text,
  CONSTRAINT messages_pkey PRIMARY KEY (id),
  CONSTRAINT messages_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT messages_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT messages_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id),
  CONSTRAINT messages_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT messages_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id)
);
CREATE TABLE public.approval_queue (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  account_id uuid,
  sender_name text NOT NULL,
  thread_messages_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  intent text NOT NULL DEFAULT 'unknown'::text,
  heat_score double precision NOT NULL DEFAULT 0.0,
  ai_draft text,
  status USER-DEFINED NOT NULL DEFAULT 'pending'::approval_status,
  reviewed_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  thread_url text,
  lead_id text,
  exec_state_id text,
  generated_reply text,
  token text,
  metadata jsonb DEFAULT '{}'::jsonb,
  CONSTRAINT approval_queue_pkey PRIMARY KEY (id),
  CONSTRAINT approval_queue_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT approval_queue_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.daily_campaign_stats (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  campaign_id uuid NOT NULL,
  stat_date date NOT NULL,
  connections_sent integer NOT NULL DEFAULT 0,
  messages_sent integer NOT NULL DEFAULT 0,
  accepted integer NOT NULL DEFAULT 0,
  replied integer NOT NULL DEFAULT 0,
  enrolled integer DEFAULT 0,
  connected integer DEFAULT 0,
  booked integer DEFAULT 0,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT daily_campaign_stats_pkey PRIMARY KEY (id),
  CONSTRAINT daily_campaign_stats_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT daily_campaign_stats_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id)
);
CREATE TABLE public.templates (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid,
  name text NOT NULL,
  description text,
  nodes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  edges_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  status USER-DEFINED NOT NULL DEFAULT 'private'::template_status,
  tags ARRAY DEFAULT '{}'::text[],
  downloads integer NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT templates_pkey PRIMARY KEY (id),
  CONSTRAINT templates_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.outbox_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text UNIQUE,
  status USER-DEFINED NOT NULL DEFAULT 'pending'::outbox_event_status,
  attempts integer NOT NULL DEFAULT 0,
  last_error text,
  deliver_at timestamp with time zone NOT NULL DEFAULT now(),
  delivered_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  campaign_id uuid,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT outbox_events_pkey PRIMARY KEY (id),
  CONSTRAINT outbox_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT outbox_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id)
);
CREATE TABLE public.api_keys (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  name text NOT NULL,
  key_hash text NOT NULL UNIQUE,
  key_prefix text NOT NULL,
  last_used_at timestamp with time zone,
  expires_at timestamp with time zone,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  scopes jsonb DEFAULT '["extension:all"]'::jsonb,
  revoked_at timestamp with time zone,
  CONSTRAINT api_keys_pkey PRIMARY KEY (id),
  CONSTRAINT api_keys_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.personas (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  title text NOT NULL,
  pain_points jsonb DEFAULT '[]'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  value_prop text DEFAULT ''::text,
  target_titles jsonb DEFAULT '[]'::jsonb,
  tone_tweaks text DEFAULT ''::text,
  CONSTRAINT personas_pkey PRIMARY KEY (id),
  CONSTRAINT personas_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.objections (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  trigger text NOT NULL,
  playbook text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT objections_pkey PRIMARY KEY (id),
  CONSTRAINT objections_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.knowledge_assets (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  name text NOT NULL,
  type text NOT NULL,
  status text NOT NULL DEFAULT 'synced'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  source_url text,
  error_msg text,
  raw_text text,
  CONSTRAINT knowledge_assets_pkey PRIMARY KEY (id),
  CONSTRAINT knowledge_assets_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.knowledge_chunks (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL DEFAULT get_my_workspace_id(),
  asset_id uuid NOT NULL,
  content text NOT NULL,
  embedding USER-DEFINED,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT knowledge_chunks_pkey PRIMARY KEY (id),
  CONSTRAINT knowledge_chunks_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT knowledge_chunks_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.knowledge_assets(id)
);
CREATE TABLE public.knowledge_synthesis (
  workspace_id uuid NOT NULL,
  core_value_prop text,
  identified_tone jsonb DEFAULT '[]'::jsonb,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  target_customer_profile text,
  key_differentiators jsonb DEFAULT '[]'::jsonb,
  proof_points jsonb DEFAULT '[]'::jsonb,
  primary_pain_points_solved jsonb DEFAULT '[]'::jsonb,
  generated_from_vector_count integer DEFAULT 0,
  CONSTRAINT knowledge_synthesis_pkey PRIMARY KEY (workspace_id),
  CONSTRAINT knowledge_synthesis_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.knowledge_synthesis_drafts (
  workspace_id uuid NOT NULL,
  core_value_prop text,
  identified_tone ARRAY,
  target_customer_profile text,
  key_differentiators ARRAY,
  proof_points ARRAY,
  primary_pain_points_solved ARRAY,
  status text DEFAULT 'pending_review'::text,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()),
  updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()),
  generated_from_vector_count integer DEFAULT 0,
  CONSTRAINT knowledge_synthesis_drafts_pkey PRIMARY KEY (workspace_id),
  CONSTRAINT knowledge_synthesis_drafts_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.knowledge_objections (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  trigger text NOT NULL,
  playbook text NOT NULL,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()),
  objection_topic text,
  rebuttal_strategy text,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT knowledge_objections_pkey PRIMARY KEY (id),
  CONSTRAINT knowledge_objections_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.daily_rollup_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid,
  stat_date date,
  rolled_up_at timestamp with time zone DEFAULT now(),
  status text,
  error_message text,
  CONSTRAINT daily_rollup_log_pkey PRIMARY KEY (id),
  CONSTRAINT daily_rollup_log_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.processing_locks (
  lock_name text NOT NULL,
  locked_until timestamp with time zone,
  CONSTRAINT processing_locks_pkey PRIMARY KEY (lock_name)
);
CREATE TABLE public.account_health_checks (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL,
  check_type text NOT NULL CHECK (check_type = ANY (ARRAY['session_valid'::text, 'cookie_freshness'::text, 'profile_reachable'::text, 'restriction_detected'::text, 'decryption'::text])),
  result text NOT NULL CHECK (result = ANY (ARRAY['pass'::text, 'warn'::text, 'fail'::text])),
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  checked_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT account_health_checks_pkey PRIMARY KEY (id),
  CONSTRAINT account_health_checks_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.account_reconnect_requests (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL,
  requested_by uuid NOT NULL,
  token text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'completed'::text, 'expired'::text])),
  expires_at timestamp with time zone NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT account_reconnect_requests_pkey PRIMARY KEY (id),
  CONSTRAINT account_reconnect_requests_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT account_reconnect_requests_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES auth.users(id)
);
CREATE TABLE public.account_connection_sessions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  initiated_by uuid NOT NULL,
  token text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'awaiting_extension'::text CHECK (status = ANY (ARRAY['awaiting_extension'::text, 'completed'::text, 'expired'::text])),
  expires_at timestamp with time zone NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT account_connection_sessions_pkey PRIMARY KEY (id),
  CONSTRAINT account_connection_sessions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT account_connection_sessions_initiated_by_fkey FOREIGN KEY (initiated_by) REFERENCES auth.users(id)
);
CREATE TABLE public.account_tags (
  account_id uuid NOT NULL,
  tag text NOT NULL CHECK (length(tag) > 0 AND length(tag) <= 50),
  CONSTRAINT account_tags_pkey PRIMARY KEY (account_id, tag),
  CONSTRAINT account_tags_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.account_limit_overrides (
  account_id uuid NOT NULL,
  action_type text NOT NULL,
  custom_limit integer NOT NULL,
  expires_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT account_limit_overrides_pkey PRIMARY KEY (account_id, action_type),
  CONSTRAINT account_limit_overrides_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.gdpr_deletion_requests (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  requested_by uuid,
  status USER-DEFINED NOT NULL DEFAULT 'requested'::gdpr_deletion_status,
  error_log text,
  started_at timestamp with time zone,
  completed_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT gdpr_deletion_requests_pkey PRIMARY KEY (id),
  CONSTRAINT gdpr_deletion_requests_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES auth.users(id)
);
CREATE TABLE public.campaign_versions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  campaign_id uuid NOT NULL,
  version integer NOT NULL,
  status text NOT NULL DEFAULT 'published'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_versions_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_versions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id)
);
CREATE TABLE public.campaign_nodes (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  campaign_version_id uuid NOT NULL,
  node_key text NOT NULL,
  node_type text NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  position_x numeric,
  position_y numeric,
  campaign_id uuid,
  ui_position jsonb NOT NULL DEFAULT '{"x": 0, "y": 0}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_nodes_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_nodes_campaign_version_id_fkey FOREIGN KEY (campaign_version_id) REFERENCES public.campaign_versions(id),
  CONSTRAINT campaign_nodes_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id)
);
CREATE TABLE public.campaign_edges (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  campaign_version_id uuid NOT NULL,
  source_node_id uuid NOT NULL,
  target_node_id uuid NOT NULL,
  source_handle text,
  target_handle text,
  condition text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_edges_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_edges_campaign_version_id_fkey FOREIGN KEY (campaign_version_id) REFERENCES public.campaign_versions(id),
  CONSTRAINT campaign_edges_source_node_id_fkey FOREIGN KEY (source_node_id) REFERENCES public.campaign_nodes(id),
  CONSTRAINT campaign_edges_target_node_id_fkey FOREIGN KEY (target_node_id) REFERENCES public.campaign_nodes(id)
);
CREATE TABLE public.campaign_enrollments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid NOT NULL,
  campaign_version_id uuid NOT NULL,
  lead_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'active'::text,
  enrolled_at timestamp with time zone NOT NULL DEFAULT now(),
  account_id uuid,
  CONSTRAINT campaign_enrollments_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_enrollments_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT campaign_enrollments_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT campaign_enrollments_campaign_version_id_fkey FOREIGN KEY (campaign_version_id) REFERENCES public.campaign_versions(id),
  CONSTRAINT campaign_enrollments_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id),
  CONSTRAINT campaign_enrollments_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.campaign_execution_states (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  enrollment_id uuid NOT NULL UNIQUE,
  current_node_id uuid,
  status USER-DEFINED NOT NULL DEFAULT 'pending'::lead_state_status,
  next_run_at timestamp with time zone,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  variables jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_reason text,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  lease_token uuid,
  lease_expires_at timestamp with time zone,
  workspace_id uuid NOT NULL,
  retry_count integer DEFAULT 0,
  CONSTRAINT campaign_execution_states_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_execution_states_current_node_id_fkey FOREIGN KEY (current_node_id) REFERENCES public.campaign_nodes(id),
  CONSTRAINT fk_ces_enrollment_ws FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id),
  CONSTRAINT fk_ces_enrollment_ws FOREIGN KEY (workspace_id) REFERENCES public.campaign_enrollments(workspace_id)
);
CREATE TABLE public.campaign_node_executions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  enrollment_id uuid NOT NULL,
  campaign_version_id uuid NOT NULL,
  node_id uuid,
  node_type text NOT NULL,
  status text NOT NULL,
  attempt integer NOT NULL DEFAULT 1,
  idempotency_key text UNIQUE,
  started_at timestamp with time zone,
  completed_at timestamp with time zone,
  input_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code text,
  error_message text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_node_executions_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_node_executions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT campaign_node_executions_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id),
  CONSTRAINT campaign_node_executions_campaign_version_id_fkey FOREIGN KEY (campaign_version_id) REFERENCES public.campaign_versions(id),
  CONSTRAINT campaign_node_executions_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.campaign_nodes(id)
);
CREATE TABLE public.campaign_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid NOT NULL,
  enrollment_id uuid,
  node_id uuid,
  event_type text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamp with time zone NOT NULL DEFAULT now(),
  account_id uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_events_pkey PRIMARY KEY (id, occurred_at),
  CONSTRAINT campaign_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT campaign_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT campaign_events_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id),
  CONSTRAINT campaign_events_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.campaign_nodes(id),
  CONSTRAINT campaign_events_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.campaign_events_y2026m09 (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid NOT NULL,
  enrollment_id uuid,
  node_id uuid,
  event_type text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamp with time zone NOT NULL DEFAULT now(),
  account_id uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_events_y2026m09_pkey PRIMARY KEY (id, occurred_at),
  CONSTRAINT campaign_events_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT campaign_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT campaign_events_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id),
  CONSTRAINT campaign_events_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.campaign_nodes(id),
  CONSTRAINT campaign_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.campaign_events_y2026m10 (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid NOT NULL,
  enrollment_id uuid,
  node_id uuid,
  event_type text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamp with time zone NOT NULL DEFAULT now(),
  account_id uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT campaign_events_y2026m10_pkey PRIMARY KEY (id, occurred_at),
  CONSTRAINT campaign_events_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT campaign_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT campaign_events_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id),
  CONSTRAINT campaign_events_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.campaign_nodes(id),
  CONSTRAINT campaign_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.location_timezone_cache (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  normalized_location text NOT NULL UNIQUE,
  iana_timezone text,
  resolution_status text NOT NULL CHECK (resolution_status = ANY (ARRAY['resolved'::text, 'ambiguous'::text, 'unresolved'::text])),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT location_timezone_cache_pkey PRIMARY KEY (id)
);
CREATE TABLE public.campaign_accounts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  campaign_id uuid NOT NULL,
  account_id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  weight integer DEFAULT 100,
  is_primary boolean DEFAULT false,
  failover_count integer DEFAULT 0,
  last_dispatched_at timestamp with time zone,
  CONSTRAINT campaign_accounts_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_accounts_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT campaign_accounts_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.agencies (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  owner_id uuid NOT NULL,
  name text NOT NULL,
  stripe_customer_id text UNIQUE,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  whitelabel_brand text DEFAULT 'Ele-in Agency'::text,
  whitelabel_domain text DEFAULT ''::text,
  whitelabel_color text DEFAULT '#6366f1'::text,
  whitelabel_logo_url text DEFAULT ''::text,
  whitelabel_enabled boolean DEFAULT true,
  master_workspace_id uuid,
  CONSTRAINT agencies_pkey PRIMARY KEY (id),
  CONSTRAINT agencies_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES auth.users(id),
  CONSTRAINT agencies_master_workspace_id_fkey FOREIGN KEY (master_workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.agency_members (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL,
  user_id uuid NOT NULL,
  role text NOT NULL DEFAULT 'member'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT agency_members_pkey PRIMARY KEY (id),
  CONSTRAINT agency_members_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agencies(id),
  CONSTRAINT agency_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id)
);
CREATE TABLE public.agency_client_access (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  agency_member_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT agency_client_access_pkey PRIMARY KEY (id),
  CONSTRAINT agency_client_access_agency_member_id_fkey FOREIGN KEY (agency_member_id) REFERENCES public.agency_members(id),
  CONSTRAINT agency_client_access_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.ai_reply_approvals (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid,
  lead_id uuid,
  enrollment_id uuid,
  execution_state_id uuid,
  generated_reply text NOT NULL,
  retrieval_score double precision NOT NULL,
  status text NOT NULL DEFAULT 'pending'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  resolved_at timestamp with time zone,
  CONSTRAINT ai_reply_approvals_pkey PRIMARY KEY (id),
  CONSTRAINT ai_reply_approvals_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT ai_reply_approvals_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id),
  CONSTRAINT ai_reply_approvals_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id),
  CONSTRAINT ai_reply_approvals_execution_state_id_fkey FOREIGN KEY (execution_state_id) REFERENCES public.campaign_execution_states(id)
);
CREATE TABLE public.api_rate_limits_window (
  api_key_id uuid NOT NULL,
  tokens integer NOT NULL,
  last_refill timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT api_rate_limits_window_pkey PRIMARY KEY (api_key_id),
  CONSTRAINT api_rate_limits_window_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.api_keys(id)
);
CREATE TABLE public.webhook_endpoints (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  url text NOT NULL,
  event_types jsonb NOT NULL DEFAULT '[]'::jsonb,
  signing_secret text NOT NULL,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  events ARRAY DEFAULT '{}'::text[],
  status text DEFAULT 'active'::text,
  failure_count integer DEFAULT 0,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT webhook_endpoints_pkey PRIMARY KEY (id),
  CONSTRAINT webhook_endpoints_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.webhook_deliveries (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  endpoint_id uuid NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  status_code integer,
  response_body text,
  delivery_status text NOT NULL DEFAULT 'pending'::text,
  attempt_count integer DEFAULT 0,
  next_retry_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  status text DEFAULT 'pending'::text,
  attempts integer DEFAULT 0,
  response_status integer,
  last_error text,
  CONSTRAINT webhook_deliveries_pkey PRIMARY KEY (id),
  CONSTRAINT webhook_deliveries_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT webhook_deliveries_endpoint_id_fkey FOREIGN KEY (endpoint_id) REFERENCES public.webhook_endpoints(id)
);
CREATE TABLE public.api_key_audit_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  api_key_id uuid NOT NULL,
  actor text NOT NULL,
  action text NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT api_key_audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT api_key_audit_logs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT api_key_audit_logs_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.api_keys(id)
);
CREATE TABLE public.api_request_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid,
  api_key_id uuid,
  endpoint text NOT NULL,
  status_code integer,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT api_request_logs_pkey PRIMARY KEY (id),
  CONSTRAINT api_request_logs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT api_request_logs_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.api_keys(id)
);
CREATE TABLE public.workspace_invites (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  email text NOT NULL,
  role USER-DEFINED NOT NULL DEFAULT 'member'::workspace_member_role,
  invited_by uuid NOT NULL,
  token text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'pending'::text,
  expires_at timestamp with time zone NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT workspace_invites_pkey PRIMARY KEY (id),
  CONSTRAINT workspace_invites_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT workspace_invites_invited_by_fkey FOREIGN KEY (invited_by) REFERENCES auth.users(id)
);
CREATE TABLE public.workspace_sending_defaults (
  workspace_id uuid NOT NULL,
  default_daily_connection_limit integer NOT NULL DEFAULT 20,
  default_daily_message_limit integer NOT NULL DEFAULT 40,
  default_warmup_target_days integer NOT NULL DEFAULT 30,
  default_working_hours_start time without time zone NOT NULL DEFAULT '08:00:00'::time without time zone,
  default_working_hours_end time without time zone NOT NULL DEFAULT '18:00:00'::time without time zone,
  default_timezone text NOT NULL DEFAULT 'UTC'::text,
  weekend_sending_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT workspace_sending_defaults_pkey PRIMARY KEY (workspace_id),
  CONSTRAINT workspace_sending_defaults_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.notification_preferences (
  user_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  event_type text NOT NULL,
  channel text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  CONSTRAINT notification_preferences_pkey PRIMARY KEY (user_id, workspace_id, event_type, channel),
  CONSTRAINT notification_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id),
  CONSTRAINT notification_preferences_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.audit_log (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  actor_id uuid,
  action text NOT NULL,
  target_type text NOT NULL,
  target_id uuid,
  before_state jsonb,
  after_state jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT audit_log_pkey PRIMARY KEY (id),
  CONSTRAINT audit_log_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT audit_log_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES auth.users(id)
);
CREATE TABLE public.notifications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  user_id uuid NOT NULL,
  title text NOT NULL,
  body text NOT NULL,
  link text,
  event_type text NOT NULL,
  read_at timestamp with time zone,
  outbox_event_id uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT notifications_pkey PRIMARY KEY (id)
);
CREATE TABLE public.workspace_api_keys (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  provider text NOT NULL CHECK (provider = ANY (ARRAY['openai'::text, 'nvidia'::text, 'openrouter'::text, 'anthropic'::text, 'gemini'::text, 'moonshot'::text, 'deepseek'::text, 'apify'::text, 'mailsso'::text])),
  secret_ref uuid NOT NULL,
  key_last4 text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT workspace_api_keys_pkey PRIMARY KEY (id),
  CONSTRAINT workspace_api_keys_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.credit_deductions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  action_type text NOT NULL,
  amount integer NOT NULL,
  balance_after integer NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT credit_deductions_pkey PRIMARY KEY (id),
  CONSTRAINT credit_deductions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.credit_action_costs (
  action_type text NOT NULL,
  credits integer NOT NULL,
  description text,
  category text NOT NULL DEFAULT 'general'::text,
  is_active boolean NOT NULL DEFAULT true,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT credit_action_costs_pkey PRIMARY KEY (action_type)
);
CREATE TABLE public.billing_transactions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  amount numeric NOT NULL,
  currency text NOT NULL DEFAULT 'usd'::text,
  status text NOT NULL DEFAULT 'succeeded'::text,
  provider text NOT NULL,
  provider_tx_id text UNIQUE,
  package_id text,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  amount_cents bigint DEFAULT 0,
  provider_order_id text,
  provider_payment_id text,
  credits_added bigint DEFAULT 0,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT billing_transactions_pkey PRIMARY KEY (id),
  CONSTRAINT billing_transactions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.checkout_sessions (
  session_id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  package_id text NOT NULL,
  credits integer NOT NULL DEFAULT 0,
  provider text NOT NULL,
  status text NOT NULL DEFAULT 'pending'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  id uuid DEFAULT gen_random_uuid(),
  user_id uuid,
  provider_order_id text,
  amount_cents integer DEFAULT 0,
  currency text DEFAULT 'USD'::text,
  metadata jsonb DEFAULT '{}'::jsonb,
  expires_at timestamp with time zone,
  completed_at timestamp with time zone,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT checkout_sessions_pkey PRIMARY KEY (session_id),
  CONSTRAINT checkout_sessions_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.icp_signal_weights (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  signal_name text NOT NULL,
  prior_alpha integer NOT NULL DEFAULT 2,
  prior_beta integer NOT NULL DEFAULT 2,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  is_frozen boolean DEFAULT false,
  weight_multiplier double precision DEFAULT 1.0,
  category text DEFAULT 'FIRMOGRAPHIC'::text,
  description text,
  CONSTRAINT icp_signal_weights_pkey PRIMARY KEY (id),
  CONSTRAINT icp_signal_weights_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.sender_pods (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  name text NOT NULL,
  status text DEFAULT 'active'::text,
  rotation_strategy text DEFAULT 'round_robin'::text,
  max_daily_invites_per_pod integer DEFAULT 100,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT sender_pods_pkey PRIMARY KEY (id)
);
CREATE TABLE public.sender_pod_accounts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  pod_id uuid NOT NULL,
  account_id text NOT NULL,
  workspace_id uuid NOT NULL,
  weight integer DEFAULT 1,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT sender_pod_accounts_pkey PRIMARY KEY (id),
  CONSTRAINT sender_pod_accounts_pod_id_fkey FOREIGN KEY (pod_id) REFERENCES public.sender_pods(id)
);
CREATE TABLE public.social_signal_cache (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  linkedin_url text NOT NULL,
  signals jsonb NOT NULL DEFAULT '{}'::jsonb,
  expires_at timestamp with time zone NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT social_signal_cache_pkey PRIMARY KEY (id)
);
CREATE TABLE public.processed_webhook_events (
  event_id text NOT NULL,
  provider text NOT NULL,
  processed_at timestamp with time zone DEFAULT now(),
  CONSTRAINT processed_webhook_events_pkey PRIMARY KEY (event_id, provider)
);
CREATE TABLE public.workspace_ai_settings (
  workspace_id uuid NOT NULL,
  default_model text NOT NULL DEFAULT 'Auto-Route (Recommended)'::text,
  byok_provider text,
  byok_key_ciphertext text,
  byok_key_last_chars text,
  temperature numeric DEFAULT 0.7,
  max_tokens_budget integer DEFAULT 2000000,
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT workspace_ai_settings_pkey PRIMARY KEY (workspace_id),
  CONSTRAINT workspace_ai_settings_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.workspace_auto_recharge_settings (
  workspace_id uuid NOT NULL,
  enabled boolean NOT NULL DEFAULT false,
  threshold_credits integer NOT NULL DEFAULT 100,
  recharge_package_id text NOT NULL DEFAULT 'credits_1000'::text,
  max_monthly_recharges integer NOT NULL DEFAULT 5,
  recharges_this_month integer NOT NULL DEFAULT 0,
  last_recharged_at timestamp with time zone,
  last_reset_month text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT workspace_auto_recharge_settings_pkey PRIMARY KEY (workspace_id),
  CONSTRAINT workspace_auto_recharge_settings_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.agency_credit_allocations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL,
  client_workspace_id uuid NOT NULL,
  from_workspace_id uuid,
  amount integer NOT NULL,
  action_type text NOT NULL DEFAULT 'manual_allocation'::text,
  allocated_by uuid,
  note text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT agency_credit_allocations_pkey PRIMARY KEY (id),
  CONSTRAINT agency_credit_allocations_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agencies(id),
  CONSTRAINT agency_credit_allocations_client_workspace_id_fkey FOREIGN KEY (client_workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT agency_credit_allocations_from_workspace_id_fkey FOREIGN KEY (from_workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT agency_credit_allocations_allocated_by_fkey FOREIGN KEY (allocated_by) REFERENCES auth.users(id)
);
CREATE TABLE public.sender_pod_audit_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid,
  account_id uuid,
  event_type text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT sender_pod_audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT sender_pod_audit_logs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT sender_pod_audit_logs_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT sender_pod_audit_logs_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.campaign_roi_certificates (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid NOT NULL,
  verification_token text NOT NULL UNIQUE,
  issuer_signature text NOT NULL,
  badge_tier text NOT NULL DEFAULT 'SILVER'::text,
  metrics_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_public boolean NOT NULL DEFAULT true,
  mask_pii boolean NOT NULL DEFAULT true,
  issued_at timestamp with time zone NOT NULL DEFAULT now(),
  expires_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  token text,
  campaign_display_name text,
  agency_brand_name text DEFAULT 'Ele-in Outbound Engine'::text,
  agency_logo_url text,
  theme_color text DEFAULT '#2563eb'::text,
  anonymize_client boolean DEFAULT false,
  metrics_snapshot jsonb DEFAULT '{}'::jsonb,
  views_count integer DEFAULT 0,
  is_revoked boolean DEFAULT false,
  CONSTRAINT campaign_roi_certificates_pkey PRIMARY KEY (id),
  CONSTRAINT campaign_roi_certificates_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT campaign_roi_certificates_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id)
);
CREATE TABLE public.agency_billing_statements (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  agency_id uuid NOT NULL,
  client_workspace_id uuid,
  invoice_number character varying NOT NULL UNIQUE,
  status character varying NOT NULL DEFAULT 'draft'::character varying CHECK (status::text = ANY (ARRAY['draft'::character varying, 'issued'::character varying, 'paid'::character varying, 'void'::character varying]::text[])),
  period_start timestamp with time zone NOT NULL,
  period_end timestamp with time zone NOT NULL,
  currency character varying NOT NULL DEFAULT 'INR'::character varying,
  subtotal_cents bigint NOT NULL DEFAULT 0,
  markup_cents bigint NOT NULL DEFAULT 0,
  tax_cents bigint NOT NULL DEFAULT 0,
  total_cents bigint NOT NULL DEFAULT 0,
  breakdown_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  statement_number text,
  client_name text,
  retainer_fee_usd numeric DEFAULT 0.00,
  credits_allocated integer DEFAULT 0,
  credits_consumed integer DEFAULT 0,
  overdraft_credits integer DEFAULT 0,
  overdraft_rate_usd numeric DEFAULT 0.0500,
  total_amount_usd numeric DEFAULT 0.00,
  line_items jsonb DEFAULT '[]'::jsonb,
  CONSTRAINT agency_billing_statements_pkey PRIMARY KEY (id),
  CONSTRAINT agency_billing_statements_agency_id_fkey FOREIGN KEY (agency_id) REFERENCES public.agencies(id),
  CONSTRAINT agency_billing_statements_client_workspace_id_fkey FOREIGN KEY (client_workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.lead_social_posts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lead_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  post_url text,
  post_text text NOT NULL,
  post_date timestamp with time zone DEFAULT now(),
  engagement_count jsonb DEFAULT '{"likes": 0, "reposts": 0, "comments": 0}'::jsonb,
  media_type text DEFAULT 'text'::text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT lead_social_posts_pkey PRIMARY KEY (id),
  CONSTRAINT lead_social_posts_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id),
  CONSTRAINT lead_social_posts_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id)
);
CREATE TABLE public.lead_social_signals (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lead_id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  post_id uuid,
  signal_type text NOT NULL,
  intent_strength text NOT NULL DEFAULT 'MEDIUM'::text,
  confidence_score double precision DEFAULT 0.8,
  detected_keywords jsonb DEFAULT '[]'::jsonb,
  signal_summary text NOT NULL,
  quote_snippet text,
  created_at timestamp with time zone DEFAULT now(),
  intent_score integer DEFAULT 50,
  summary text,
  recommended_hook text,
  is_actioned boolean DEFAULT false,
  detected_at timestamp with time zone DEFAULT now(),
  CONSTRAINT lead_social_signals_pkey PRIMARY KEY (id),
  CONSTRAINT lead_social_signals_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id),
  CONSTRAINT lead_social_signals_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT lead_social_signals_post_id_fkey FOREIGN KEY (post_id) REFERENCES public.lead_social_posts(id)
);
CREATE TABLE public.icp_feedback_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid,
  lead_id uuid,
  event_type text NOT NULL,
  signals_affected jsonb NOT NULL DEFAULT '[]'::jsonb,
  score_before integer,
  score_after integer,
  details jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  signal_key text,
  outcome_type text,
  alpha_delta integer DEFAULT 0,
  beta_delta integer DEFAULT 0,
  source text DEFAULT 'system'::text,
  CONSTRAINT icp_feedback_events_pkey PRIMARY KEY (id),
  CONSTRAINT icp_feedback_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id),
  CONSTRAINT icp_feedback_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id),
  CONSTRAINT icp_feedback_events_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id)
);
CREATE TABLE public.lead_objections (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  lead_id uuid,
  thread_key text,
  objection_type text NOT NULL,
  detected_competitor text,
  detected_timing text,
  confidence numeric DEFAULT 1.0,
  raw_message_snippet text,
  selected_strategy text,
  selected_tone text,
  resulting_deal_stage text DEFAULT 'OBJECTION_RAISED'::text,
  created_at timestamp with time zone DEFAULT now(),
  prospect_message text,
  suggested_rebuttal text,
  chosen_framework text,
  resolved boolean DEFAULT false,
  CONSTRAINT lead_objections_pkey PRIMARY KEY (id),
  CONSTRAINT lead_objections_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id)
);
CREATE TABLE public.lead_prewarm_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  lead_id uuid NOT NULL,
  account_id uuid,
  action_type character varying NOT NULL,
  post_url text,
  post_snippet text,
  generated_comment text,
  sentiment_score double precision DEFAULT 0.0,
  status character varying DEFAULT 'pending'::character varying,
  scheduled_for timestamp with time zone,
  executed_at timestamp with time zone,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  campaign_id uuid,
  target_url text,
  warmth_points integer DEFAULT 10,
  CONSTRAINT lead_prewarm_events_pkey PRIMARY KEY (id)
);
CREATE TABLE public.omnichannel_fallback_configs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid,
  days_pending_threshold integer DEFAULT 7,
  auto_withdraw_linkedin boolean DEFAULT true,
  fallback_to_email boolean DEFAULT true,
  fallback_to_inmail boolean DEFAULT true,
  bridge_template_id character varying DEFAULT 'linkedin_connection_followup'::character varying,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  enabled boolean DEFAULT true,
  linkedin_invite_timeout_hours integer DEFAULT 72,
  fallback_channel text DEFAULT 'email'::text,
  provider text DEFAULT 'smartlead'::text,
  external_campaign_id text,
  inmail_template text,
  email_subject_template text,
  email_body_template text,
  CONSTRAINT omnichannel_fallback_configs_pkey PRIMARY KEY (id)
);
CREATE TABLE public.omnichannel_cascade_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  lead_id uuid NOT NULL,
  campaign_id uuid,
  original_channel character varying NOT NULL DEFAULT 'linkedin'::character varying,
  target_channel character varying NOT NULL,
  trigger_reason character varying NOT NULL,
  status character varying DEFAULT 'completed'::character varying,
  bridge_snippet text,
  created_at timestamp with time zone DEFAULT now(),
  from_channel text DEFAULT 'linkedin_invite'::text,
  to_channel text,
  reason text,
  metadata jsonb DEFAULT '{}'::jsonb,
  CONSTRAINT omnichannel_cascade_logs_pkey PRIMARY KEY (id)
);
CREATE TABLE public.thought_leadership_posts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  account_id uuid,
  topic character varying NOT NULL,
  hook_framework character varying NOT NULL,
  post_content text NOT NULL,
  status character varying DEFAULT 'draft'::character varying,
  scheduled_at timestamp with time zone,
  published_at timestamp with time zone,
  tags jsonb DEFAULT '[]'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  framework text DEFAULT 'contrarian'::text,
  hook_line text,
  post_body text,
  target_persona text,
  viral_score integer DEFAULT 80,
  scheduled_for timestamp with time zone,
  CONSTRAINT thought_leadership_posts_pkey PRIMARY KEY (id)
);
CREATE TABLE public.bandit_experiments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  campaign_id uuid,
  node_id text,
  name text NOT NULL DEFAULT 'Dynamic Copy Bandit'::text,
  status text NOT NULL DEFAULT 'active'::text CHECK (status = ANY (ARRAY['active'::text, 'paused'::text, 'completed'::text])),
  exploration_factor numeric NOT NULL DEFAULT 1.0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  step_type text DEFAULT 'connection_note'::text,
  auto_mutate boolean DEFAULT true,
  min_trials_before_mutation integer DEFAULT 25,
  CONSTRAINT bandit_experiments_pkey PRIMARY KEY (id)
);
CREATE TABLE public.copy_variants (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  experiment_id uuid,
  workspace_id uuid NOT NULL,
  name text NOT NULL,
  template_text text NOT NULL,
  arm_type text NOT NULL DEFAULT 'full_message'::text CHECK (arm_type = ANY (ARRAY['hook'::text, 'value_prop'::text, 'cta'::text, 'full_message'::text])),
  alpha_param numeric NOT NULL DEFAULT 1.0,
  beta_param numeric NOT NULL DEFAULT 1.0,
  impressions integer NOT NULL DEFAULT 0,
  positive_replies integer NOT NULL DEFAULT 0,
  objections integer NOT NULL DEFAULT 0,
  unsubscribes integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'active'::text CHECK (status = ANY (ARRAY['active'::text, 'degraded'::text, 'retired'::text])),
  parent_variant_id uuid,
  generation integer NOT NULL DEFAULT 1,
  mutation_notes text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  variant_label text,
  angle_tag text DEFAULT 'value_prop'::text,
  alpha integer DEFAULT 1,
  beta integer DEFAULT 1,
  positive_outcomes integer DEFAULT 0,
  is_challenger boolean DEFAULT false,
  CONSTRAINT copy_variants_pkey PRIMARY KEY (id),
  CONSTRAINT copy_variants_experiment_id_fkey FOREIGN KEY (experiment_id) REFERENCES public.bandit_experiments(id)
);
CREATE TABLE public.trigger_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  lead_id uuid,
  prospect_name text NOT NULL,
  company_name text NOT NULL,
  event_type text NOT NULL CHECK (event_type = ANY (ARRAY['NEW_ROLE'::text, 'PROMOTION'::text, 'FUNDING_ROUND'::text, 'HIRING_SURGE'::text])),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  detected_at timestamp with time zone NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'PENDING'::text CHECK (status = ANY (ARRAY['PENDING'::text, 'ENROLLED'::text, 'DISMISSED'::text])),
  generated_icebreaker text,
  enrolled_campaign_id uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  headline text,
  source_url text,
  urgency_score integer DEFAULT 75,
  generated_hook text,
  CONSTRAINT trigger_events_pkey PRIMARY KEY (id)
);
CREATE TABLE public.harvested_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  event_url text NOT NULL,
  event_name text NOT NULL,
  event_type text NOT NULL DEFAULT 'event'::text CHECK (event_type = ANY (ARRAY['event'::text, 'group'::text, 'webinar'::text])),
  attendee_count integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'completed'::text CHECK (status = ANY (ARRAY['harvesting'::text, 'completed'::text, 'failed'::text])),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  source_type text DEFAULT 'linkedin_event'::text,
  source_url text,
  title text,
  organizer text,
  topic_tags ARRAY DEFAULT '{}'::text[],
  total_scraped integer DEFAULT 0,
  icp_matched integer DEFAULT 0,
  auto_campaign_id uuid,
  harvested_at timestamp with time zone DEFAULT now(),
  CONSTRAINT harvested_events_pkey PRIMARY KEY (id)
);
