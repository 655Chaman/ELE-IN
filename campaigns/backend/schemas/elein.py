from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class EleInNode(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]
    position: Optional[Dict[str, float]] = None

class EleInEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None

class CampaignCreate(BaseModel):
    name: str
    nodes: List[EleInNode]
    edges: List[EleInEdge]
    senders: Optional[List[str]] = []
    status: Optional[str] = "DRAFT"
    timezone: Optional[str] = None
    schedule: Optional[Dict[str, Any]] = None
    limit: Optional[int] = 50

class CampaignResponse(BaseModel):
    id: str
    name: str
    status: str
    nodes_json: str
    edges_json: str

class CampaignVersionCreate(BaseModel):
    name: str

class CampaignNodeCreate(BaseModel):
    id: str
    node_type: str
    config: Dict[str, Any]

class CampaignEdgeCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    condition: Optional[str] = None

class AccountCreate(BaseModel):
    name: str
    linkedin_profile_url: Optional[str] = None
    # API field kept as session_cookies_json for frontend compatibility.
    # The backend stores this as session_cookies_encrypted (BYTEA) in the DB.
    session_cookies_json: str
    daily_connection_limit: Optional[int] = 20
    daily_message_limit: Optional[int] = 40
    is_warmup: Optional[bool] = False
    warmup_start_date: Optional[str] = None
    warmup_target_days: Optional[int] = 30
    warmup_max_connections: Optional[int] = 20
    warmup_max_messages: Optional[int] = 40
    proxy_id: Optional[str] = None

class AccountResponse(BaseModel):
    id: str
    name: str
    linkedin_profile_url: Optional[str] = None
    # Returns the decrypted cookie JSON string (never the raw BYTEA)
    session_cookies_json: Optional[str] = None
    daily_connection_limit: Optional[int] = 20
    daily_message_limit: Optional[int] = 40
    is_warmup: Optional[bool] = False
    warmup_start_date: Optional[str] = None
    is_active: bool
    status: Optional[str] = "ACTIVE"
    manual_send_suspected: Optional[bool] = False
    last_health_check_at: Optional[str] = None
