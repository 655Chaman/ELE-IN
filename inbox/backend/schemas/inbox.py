from pydantic import BaseModel, Field

class AISuggestRequest(BaseModel):
    sender_name: str = Field(..., max_length=500)
    thread_messages: list
    intent: str = Field("unknown", max_length=100)
    lead_profile: dict = {}
    campaign_context: str = Field("", max_length=5000)

class IntentRequest(BaseModel):
    message_text: str = Field(..., max_length=2000)
