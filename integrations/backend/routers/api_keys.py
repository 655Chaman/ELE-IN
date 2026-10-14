from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from supabase import Client
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client, get_current_user_id, get_supabase_client
from integrations.backend.services.api_key_service import issue_api_key

router = APIRouter()

@router.get("")
def list_api_keys(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    List all API keys for the current workspace with key prefixes.
    """
    res = supabase.table("api_keys").select(
        "id, name, key_prefix, scopes, is_active, created_at, revoked_at"
    ).eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": res.data or []}

class CreateApiKeyRequest(BaseModel):
    name: str
    scopes: List[str]


@router.post("")
def create_api_key(
    req: CreateApiKeyRequest,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Creates a new public API key. The raw secret is returned once and never stored.
    """
    # Paranoia Layer 2: Input validation
    raw_name = (req.name or "").strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="API key name cannot be empty")
    if not req.scopes:
        raise HTTPException(status_code=400, detail="At least one scope is required")

    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
    can_api_keys = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("can_use_api_keys", False)
    if not can_api_keys:
        raise HTTPException(
            status_code=403,
            detail="API key generation for external AI agents requires a Growth Pro subscription. Upgrade to connect Cursor, Claude Code, or custom pipelines."
        )

    try:
        result = issue_api_key(supabase, workspace_id, raw_name[:100], req.scopes, actor=user_id)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from datetime import datetime

@router.delete("/{key_id}")
def revoke_api_key(
    key_id: str,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
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

@router.post("/proxies/sync/webshare")
async def sync_webshare(
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_supabase_client)
):
    from integrations.backend.services.webshare_sync import sync_webshare_proxies
    result = sync_webshare_proxies(workspace_id, supabase)
    return result
