from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from supabase import Client
from core.backend.api.auth_dep import get_current_workspace, get_service_client, get_current_user_id
from integrations.backend.services.api_key_service import issue_api_key

router = APIRouter()

class CreateApiKeyRequest(BaseModel):
    name: str
    scopes: List[str]

@router.post("")
def create_api_key(
    req: CreateApiKeyRequest,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_service_client)
):
    """
    Creates a new public API key. The raw secret is returned once and never stored.
    """
    try:
        result = issue_api_key(supabase, workspace_id, req.name, req.scopes, actor=user_id)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from datetime import datetime

@router.delete("/{key_id}")
def revoke_api_key(
    key_id: str,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_service_client)
):
    """
    Revokes an API key softly, leaving it in the database for foreign keys.
    """
    res = supabase.table("api_keys").update({
        "is_active": False,
        "revoked_at": datetime.utcnow().isoformat()
    }).eq("id", key_id).eq("workspace_id", workspace_id).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="API key not found")
        
    # Write to audit log
    supabase.table("api_key_audit_logs").insert({
        "workspace_id": workspace_id,
        "api_key_id": key_id,
        "actor": user_id,
        "action": "revoked"
    }).execute()
        
    return {"status": "success", "message": "API key revoked"}
