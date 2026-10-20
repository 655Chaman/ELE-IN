from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, ConfigDict


class LeadBase(BaseModel):
    """
    Paranoia Layer 0 & 1: Production-aligned Lead schema mirroring PostgreSQL public.leads.
    Includes backward-compatible fields for prototype resilience.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    workspace_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    domain: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = "UTC"
    status: Optional[str] = "extracted"
    is_open_profile: Optional[bool] = False

    # Social Radar & Intent
    social_intent_score: Optional[float] = 0.0
    social_intent_tier: Optional[str] = "COLD"
    last_social_scan_at: Optional[str] = None
    best_outreach_angle: Optional[str] = None
    social_icebreaker: Optional[str] = None
    recommended_timing: Optional[str] = None
    radar_signals: Optional[List[Dict[str, Any]]] = Field(default_factory=list)

    # Email Shield & Deliverability (Migration 102)
    email_classification: Optional[str] = None
    is_role_based: Optional[bool] = False
    is_disposable: Optional[bool] = False
    deliverability_risk: Optional[str] = "SAFE"
    quarantine_reason: Optional[str] = None

    # Arbitrary custom attributes & enrichment
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    enrichment_source: Optional[str] = "csv"
    enriched_at: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)

    # Backward compatibility aliases
    market: Optional[str] = None
    side: Optional[str] = None
    pipeline_id: Optional[str] = None
    company_description: Optional[str] = None
    kdm_first: Optional[str] = None
    kdm_last: Optional[str] = None
    verified_email: Optional[str] = None
    target_campaign_tier: Optional[str] = None


class LeadCreate(LeadBase):
    id: Optional[str] = None


class LeadUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    status: Optional[str] = None
    enriched_at: Optional[str] = None
    tags: Optional[List[str]] = None
    radar_signals: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class LeadResponse(LeadBase):
    id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LeadListBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    type: str = "csv"
    row_count: int = 0
    target_timezone: Optional[str] = "UTC"
    target_region_label: Optional[str] = None
    status: Optional[str] = "completed"
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class LeadListCreate(LeadListBase):
    workspace_id: str


class LeadListResponse(LeadListBase):
    id: str
    workspace_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    campaign: Optional[Dict[str, Any]] = None


class SuppressionEntryCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    domain: Optional[str] = None
    reason: Optional[str] = "manual"


class SuppressionEntryResponse(SuppressionEntryCreate):
    id: str
    created_at: Optional[str] = None
    value: Optional[str] = None


class DynamicRuleCondition(BaseModel):
    id: str
    field: str
    operator: str
    value: Any


class DynamicRuleConfig(BaseModel):
    match_type: str = "ALL"  # "ALL" or "ANY"
    conditions: List[DynamicRuleCondition] = Field(default_factory=list)
    auto_enroll_campaign_id: Optional[str] = None
    re_enroll_disqualified: bool = False
