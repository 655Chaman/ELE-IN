from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from supabase import Client
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from integrations.backend.services.api_key_service import issue_api_key

router = APIRouter()

class CreateApiKeyRequest(BaseModel):
    name: str
    scopes: List[str]

@router.post("")
def create_api_key(
    req: CreateApiKeyRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """
    Creates a new public API key. The raw secret is returned once and never stored.
    """
    try:
        result = issue_api_key(supabase, workspace_id, req.name, req.scopes)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{key_id}")
def revoke_api_key(
    key_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """
    Revokes (deletes) an API key.
    """
    res = supabase.table("api_keys").delete().eq("id", key_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "success", "message": "API key revoked"}
