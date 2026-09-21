import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from supabase import Client

from core.backend.api.auth_dep import get_current_workspace, get_service_client, get_current_user_id
from core.backend.core.crypto import encrypt_bytes

router = APIRouter()

class CreateWebhookRequest(BaseModel):
    url: str
    event_types: List[str]

@router.post("")
def create_webhook(
    req: CreateWebhookRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Registers a new webhook endpoint."""
    if not req.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")
        
    # Generate a random signing secret (e.g. whsec_...)
    raw_secret = f"whsec_{secrets.token_hex(16)}"
    
    # Encrypt the secret at rest
    encrypted_secret_hex = encrypt_bytes(raw_secret.encode('utf-8')).hex()
    
    res = supabase.table("webhook_endpoints").insert({
        "workspace_id": workspace_id,
        "url": req.url,
        "event_types": req.event_types,
        "signing_secret": encrypted_secret_hex,
        "is_active": True
    }).execute()
    
    data = res.data[0]
    # Return raw secret ONCE to the user
    data["signing_secret"] = raw_secret
    return {"status": "success", "data": data}

@router.get("")
def list_webhooks(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Lists webhook endpoints."""
    res = supabase.table("webhook_endpoints").select("id, url, event_types, is_active, created_at").eq("workspace_id", workspace_id).execute()
    return {"status": "success", "data": res.data}

@router.delete("/{endpoint_id}")
def delete_webhook(
    endpoint_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Soft deletes a webhook endpoint."""
    res = supabase.table("webhook_endpoints").update({
        "is_active": False
    }).eq("id", endpoint_id).eq("workspace_id", workspace_id).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "success", "message": "Webhook deleted"}
