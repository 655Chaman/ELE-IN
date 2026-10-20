export interface CampaignRef {
  id: string
  name: string
  status: string
}

export interface LeadList {
  id: string
  workspace_id?: string
  name: string
  type: "csv" | "sales_nav" | "linkedin_url" | "search" | "hubspot" | "dynamic"
  row_count: number
  campaign?: CampaignRef | string | null
  target_timezone?: string
  target_region_label?: string
  created_at: string
  updated_at?: string
  status?: "pending" | "importing" | "processing" | "completed" | "error" | "failed" | string
  error_message?: string
  source_metadata?: Record<string, any>
  metadata?: Record<string, any>
  tags?: string[]
}

export interface LeadMetadata {
  custom_variables?: Record<string, any>
  source_list_id?: string
  enrichment_provider?: string
  email_bounced?: boolean
  email_replied?: boolean
  [key: string]: any
}

export interface Lead {
  id: string
  workspace_id: string
  first_name?: string | null
  last_name?: string | null
  full_name?: string | null
  email?: string | null
  company_name?: string | null
  job_title?: string | null
  linkedin_url?: string | null
  phone?: string | null
  city?: string | null
  country?: string | null
  location?: string | null
  timezone?: string | null
  domain?: string | null
  status?: string
  is_open_profile?: boolean
  metadata?: LeadMetadata

  // EmailShield & Deliverability fields (Migration 102)
  email_classification?: "valid" | "risky" | "invalid" | "unverified" | string | null
  deliverability_risk?: "SAFE" | "MODERATE" | "HIGH" | string | null
  is_role_based?: boolean
  is_disposable?: boolean
  quarantine_reason?: string | null

  // Social Intent
  social_intent_score?: number
  social_intent_tier?: "HOT" | "WARM" | "MILD" | "COLD" | null
  last_social_scan_at?: string | null
  best_outreach_angle?: string | null
  social_icebreaker?: string | null
  recommended_timing?: string | null

  // Campaign & DAG Telemetry
  campaign_id?: string | null
  enrollment_id?: string | null
  enrollment_status?: string | null
  campaign_enrollment?: {
    enrollment_id?: string
    campaign_id?: string
    status?: string
  }
  created_at?: string
  updated_at?: string
}

export interface ListMember {
  id?: string
  list_id: string
  opportunity_id: string
  workspace_id: string
  created_at?: string
}

export interface SuppressionEntry {
  id: string
  workspace_id: string
  linkedin_url?: string | null
  email?: string | null
  domain?: string | null
  value?: string | null
  reason: "bounced" | "unsubscribed" | "manual" | "complaint" | "system" | "email_hard_bounce" | string
  created_at: string
}

export interface LeadTag {
  id: string
  workspace_id: string
  lead_id: string
  tag: string
  created_at?: string
}

export interface DynamicRuleCondition {
  id: string
  field: string
  operator: string
  value: any
}

export interface DynamicRuleConfig {
  match_type: "ALL" | "ANY"
  conditions: DynamicRuleCondition[]
  auto_enroll_campaign_id?: string | null
  re_enroll_disqualified?: boolean
}

export interface CollisionCheckResult {
  conflicting_lead_ids: string[]
  safe_lead_ids: string[]
  suppressed_count: number
}
