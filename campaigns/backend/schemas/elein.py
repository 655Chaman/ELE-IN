from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Any, Dict

class EleInNode(BaseModel):
    id: str = Field(..., max_length=255)
    type: str = Field(..., max_length=100)
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Optional[Dict[str, float]] = None
    model_config = ConfigDict(extra="ignore")

class EleInEdge(BaseModel):
    id: str = Field(..., max_length=255)
    source: str = Field(..., max_length=255)
    target: str = Field(..., max_length=255)
    sourceHandle: Optional[str] = Field(None, max_length=100)
    targetHandle: Optional[str] = Field(None, max_length=100)
    model_config = ConfigDict(extra="ignore")

class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    nodes: List[EleInNode] = Field(..., max_length=1000)
    edges: List[EleInEdge] = Field(..., max_length=2000)
    senders: Optional[List[str]] = Field(default_factory=list, max_length=500)
    status: Optional[str] = Field("DRAFT", max_length=50)
    timezone: Optional[str] = Field(None, max_length=100)
    schedule: Optional[Dict[str, Any]] = None
    limit: Optional[int] = Field(50, ge=0, le=10000)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    expected_version: Optional[int] = Field(None, ge=0)
    expected_updated_at: Optional[str] = Field(None, max_length=100)
    allow_active_graph_mutation: Optional[bool] = False
    lead_list_id: Optional[str] = Field(None, max_length=255)
    model_config = ConfigDict(extra="ignore")

class CampaignResponse(BaseModel):
    id: str
    name: str
    status: str
    nodes_json: str
    edges_json: str

class CampaignVersionCreate(BaseModel):
    name: str = Field(..., max_length=255)
    model_config = ConfigDict(extra="ignore")

class CampaignNodeCreate(BaseModel):
    id: str = Field(..., max_length=255)
    node_type: str = Field(..., max_length=100)
    config: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="ignore")

class CampaignEdgeCreate(BaseModel):
    source_node_id: str = Field(..., max_length=255)
    target_node_id: str = Field(..., max_length=255)
    condition: Optional[str] = Field(None, max_length=100)
    model_config = ConfigDict(extra="ignore")

class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    linkedin_profile_url: Optional[str] = Field(None, max_length=1000)
    # API field kept as session_cookies_json for frontend compatibility.
    # The backend stores this as session_cookies_encrypted (BYTEA) in the DB.
    session_cookies_json: str = Field(..., max_length=500000)
    daily_connection_limit: Optional[int] = Field(20, ge=0, le=500)
    daily_message_limit: Optional[int] = Field(40, ge=0, le=1000)
    is_warmup: Optional[bool] = False
    warmup_start_date: Optional[str] = Field(None, max_length=100)
    warmup_target_days: Optional[int] = Field(30, ge=1, le=365)
    warmup_max_connections: Optional[int] = Field(20, ge=0, le=500)
    warmup_max_messages: Optional[int] = Field(40, ge=0, le=1000)
    proxy_id: Optional[str] = Field(None, max_length=255)
    model_config = ConfigDict(extra="ignore")

class AccountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    daily_connection_limit: Optional[int] = Field(None, ge=1, le=100)
    daily_message_limit: Optional[int] = Field(None, ge=1, le=150)
    proxy_id: Optional[str] = Field(None, max_length=255)
    model_config = ConfigDict(extra="ignore")

class AccountResponse(BaseModel):
    id: str
    name: str
    linkedin_profile_url: Optional[str] = None
    # Security Hardening (VULN-13): Session cookies are never streamed over REST API.
    # has_valid_session indicates cookie presence without exposing sensitive tokens.
    has_valid_session: bool = True
    session_cookies_json: Optional[str] = None
    daily_connection_limit: Optional[int] = 20
    daily_message_limit: Optional[int] = 40
    is_warmup: Optional[bool] = False
    warmup_start_date: Optional[str] = None
    is_active: bool
    status: Optional[str] = "ACTIVE"
    session_death_reason: Optional[str] = None
    auto_heal_status: Optional[str] = None
    health_score: Optional[int] = None
    cookie_expires_at: Optional[str] = None
    quarantined_until: Optional[str] = None
    quarantine_reason: Optional[str] = None
    manual_send_suspected: Optional[bool] = False
    last_health_check_at: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


class WorkspaceBlueprintCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    version: Optional[str] = Field("1.0.0", max_length=50)
    schema_version: Optional[str] = Field("elein-blueprint-v1", max_length=100)
    branding: Optional[Dict[str, Any]] = None
    sequence_data: Dict[str, Any]
    stats: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = Field(default_factory=list, max_length=50)
    is_public: Optional[bool] = False
    model_config = ConfigDict(extra="ignore")

    @field_validator("sequence_data")
    @classmethod
    def validate_sequence_data_payload_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        import json
        try:
            dumped = json.dumps(v)
            if len(dumped) > 2_000_000:  # 2MB maximum payload limit
                raise ValueError("Blueprint sequence payload exceeds the maximum 2MB size limit.")
        except (TypeError, OverflowError) as e:
            raise ValueError(f"Sequence data is not JSON-serializable: {e}")
        return v


class WorkspaceBlueprintResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    version: str = "1.0.0"
    schema_version: str = "elein-blueprint-v1"
    branding: Optional[Dict[str, Any]] = None
    sequence_data: Dict[str, Any]
    stats: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_public: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    model_config = ConfigDict(extra="ignore")

