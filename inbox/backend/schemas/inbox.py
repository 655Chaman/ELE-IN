from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class AISuggestRequest(BaseModel):
    sender_name: str = Field(..., max_length=500)
    thread_messages: List[Dict[str, Any]] = Field(default_factory=list)
    intent: Optional[str] = Field("unknown", max_length=100)
    lead_profile: Optional[Dict[str, Any]] = Field(default_factory=dict)
    campaign_context: Optional[str] = Field("", max_length=5000)
    is_simulation: Optional[bool] = Field(False)
    idempotency_key: Optional[str] = Field(None, max_length=200)

class IntentRequest(BaseModel):
    message_text: str = Field(..., max_length=2000)
    idempotency_key: Optional[str] = Field(None, max_length=200)
