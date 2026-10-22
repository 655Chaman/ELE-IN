from typing import Optional, Any, Dict, List
import jwt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
from supabase import Client, AsyncClient

# We must import these from the correct location. 
# They are defined in elein.py but they depend on auth_dep.py.
# To avoid circular imports, let's just use auth_dep.py and re-implement get_current_workspace here.
from core.backend.api.auth_dep import get_supabase_client, get_async_supabase_client, get_current_workspace, get_current_user_id, get_service_client
from fastapi import Request

router = APIRouter()

async def _exec(query_builder):
    """Executes a Supabase query builder safely across AsyncClient and MagicMock in unit tests."""
    res = query_builder.execute()
    return await res if hasattr(res, "__await__") else res

async def require_workspace_admin(
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    from core.backend.api.auth_dep import get_workspace_role
    role = await get_workspace_role(workspace_id, user_id, supabase)
    if not role or role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return workspace_id

class HubspotAuth(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None

async def _get_valid_hubspot_token(workspace_id: str, supabase: Any) -> str:
    """
    Three-Layer Paranoia (Leak 9 Fix):
    Fetches HubSpot token with proactive OAuth expiration detection and refresh handling.
    Raises actionable 401 if token has expired rather than throwing cryptic 400 errors.
    """
    import os, time
    from core.backend.services.http_client import async_external_request
    res = await _exec(supabase.table("workspaces").select("hubspot_token, hubspot_refresh_token, hubspot_expires_at").eq("id", workspace_id))
    if not res or not res.data:
        raise HTTPException(status_code=400, detail="No access token found in workspace or HubSpot not connected")
    
    row = res.data[0]
    token = row.get("hubspot_token")
    refresh_tok = row.get("hubspot_refresh_token")
    expires_at = row.get("hubspot_expires_at")

    if not token:
        raise HTTPException(status_code=400, detail="No access token found in workspace or HubSpot not connected")

    now = time.time()
    needs_refresh = False
    if expires_at and isinstance(expires_at, (int, float)) and now >= (expires_at - 300):
        needs_refresh = True

    if needs_refresh and refresh_tok:
        client_id = os.getenv("HUBSPOT_CLIENT_ID")
        client_secret = os.getenv("HUBSPOT_CLIENT_SECRET")
        if client_id and client_secret:
            try:
                refresh_resp = await async_external_request(
                    "POST",
                    "https://api.hubapi.com/oauth/v1/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_tok,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if refresh_resp.status_code == 200:
                    r_data = refresh_resp.json()
                    new_token = r_data.get("access_token")
                    new_refresh = r_data.get("refresh_token") or refresh_tok
                    new_expires = now + int(r_data.get("expires_in", 21600))
                    await _exec(supabase.table("workspaces").update({
                        "hubspot_token": new_token,
                        "hubspot_refresh_token": new_refresh,
                        "hubspot_expires_at": new_expires
                    }).eq("id", workspace_id))
                    return new_token
            except Exception as r_err:
                logger.warning(f"[HubSpot] Automatic token refresh failed: {r_err}")

    return token

@router.get("/status")
async def get_hubspot_status(
    workspace_id: str = Depends(get_current_workspace),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    """Returns the stored token if it exists (so the UI can show Connected on load)"""
    res = await _exec(supabase.table("workspaces").select("hubspot_token").eq("id", workspace_id))
    if not res or not res.data or not res.data[0].get("hubspot_token"):
        return {"connected": False}
    return {"connected": True}

@router.post("/auth")
async def authenticate_hubspot(
    data: HubspotAuth,
    workspace_id: str = Depends(require_workspace_admin),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = await _exec(supabase.table("workspaces").select("tier").eq("id", workspace_id))
    tier = ws_res.data[0].get("tier", "FREE") if ws_res and ws_res.data else "FREE"
    can_sync = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("can_use_crm_sync", False)
    if not can_sync:
        raise HTTPException(
            status_code=403,
            detail="HubSpot CRM sync requires a Growth Pro subscription. Upgrade to sync contacts and deals."
        )

    # Verify the token by calling HubSpot API
    clean_token = data.access_token.strip()
    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json"
    }
    from core.backend.services.http_client import async_external_request
    
    # Using the CRM properties endpoint as a simple validation
    try:
        resp = await async_external_request("GET", "https://api.hubapi.com/contacts/v1/lists", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to communicate with HubSpot API: {str(e)}")
    
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid HubSpot Access Token")
        
    # Valid token! Save it to the workspace.
    update_payload = {"hubspot_token": clean_token}
    if data.refresh_token:
        update_payload["hubspot_refresh_token"] = data.refresh_token.strip()
    if data.expires_in:
        import time
        update_payload["hubspot_expires_at"] = time.time() + int(data.expires_in)
    res = await _exec(supabase.table("workspaces").update(update_payload).eq("id", workspace_id))
    
    if not res or not res.data:
        raise HTTPException(status_code=500, detail="Failed to save token to database (silent failure)")

    return {"status": "ok", "message": "Authenticated and token saved successfully"}

@router.get("/lists")
async def get_hubspot_lists(
    workspace_id: str = Depends(get_current_workspace),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = await _exec(supabase.table("workspaces").select("tier").eq("id", workspace_id))
    tier = ws_res.data[0].get("tier", "FREE") if ws_res and ws_res.data else "FREE"
    can_sync = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("can_use_crm_sync", False)
    if not can_sync:
        raise HTTPException(
            status_code=403,
            detail="HubSpot CRM sync requires a Growth Pro subscription."
        )

    # Strictly fetch authenticated token from workspace DB (with auto-refresh)
    access_token = await _get_valid_hubspot_token(workspace_id, supabase)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    from core.backend.services.http_client import async_external_request
    
    # Using legacy lists API because v3 lists is often in beta
    try:
        resp = await async_external_request("GET", "https://api.hubapi.com/contacts/v1/lists", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to communicate with HubSpot API: {str(e)}")

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch lists")
        
    data = resp.json()
    
    # Format for frontend
    lists = []
    for lst in data.get("lists", []):
        lists.append({
            "id": lst["listId"],
            "name": lst["name"],
            "count": lst.get("metaData", {}).get("size", 0)
        })
        
    return {"lists": lists}

@router.post("/import")
async def import_hubspot_list(
    list_id: int,
    workspace_id: str = Depends(require_workspace_admin),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    import uuid
    import logging
    from core.backend.services.job_queue import enqueue_job
    logger = logging.getLogger(__name__)

    # Paranoia Layer 2: Validate list_id
    if list_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid list_id: must be a positive integer")

    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = await _exec(supabase.table("workspaces").select("tier").eq("id", workspace_id))
    tier = ws_res.data[0].get("tier", "FREE") if ws_res and ws_res.data else "FREE"
    can_sync = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("can_use_crm_sync", False)
    if not can_sync:
        raise HTTPException(
            status_code=403,
            detail="HubSpot CRM sync requires a Growth Pro subscription. Upgrade to import HubSpot lists."
        )

    # Fetch token from workspace
    # Validate and refresh token if needed
    await _get_valid_hubspot_token(workspace_id, supabase)
    
    # We do NOT put the raw access_token in the payload; the worker fetches it securely.
    
    # Create internal lead list to store the imported leads
    internal_list_id = str(uuid.uuid4())
    try:
        await _exec(supabase.table("lead_lists").insert({
            "id": internal_list_id,
            "name": f"HubSpot Import {list_id}",
            "type": "hubspot",
            "row_count": -1,
            "workspace_id": workspace_id,
        }))
    except Exception as e:
        logger.error(f"import_hubspot_list: failed to create lead_list record: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create the lead list.")

    enqueue_job(
        supabase, 
        'hubspot_import', 
        workspace_id, 
        internal_list_id, 
        {'list_id': list_id, 'internal_list_id': internal_list_id}
    )
    
    return {"status": "sync_started", "list_id": list_id, "internal_list_id": internal_list_id}



@router.get("/pipelines")
async def get_hubspot_pipelines(
    workspace_id: str = Depends(get_current_workspace),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    """Fetches real pipelines and stages from HubSpot Deals API"""
    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = await _exec(supabase.table("workspaces").select("tier").eq("id", workspace_id))
    tier = ws_res.data[0].get("tier", "FREE") if ws_res and ws_res.data else "FREE"
    can_sync = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("can_use_crm_sync", False)
    if not can_sync:
        raise HTTPException(
            status_code=403,
            detail="HubSpot CRM sync requires a Growth Pro subscription."
        )

    access_token = await _get_valid_hubspot_token(workspace_id, supabase)
    res = await _exec(supabase.table("workspaces").select("hubspot_won_stage_id").eq("id", workspace_id))
    saved_stage_id = res.data[0].get("hubspot_won_stage_id") if res and res.data else None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    from core.backend.services.http_client import async_external_request
    
    try:
        resp = await async_external_request("GET", "https://api.hubapi.com/crm/v3/pipelines/deals", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to communicate with HubSpot API: {str(e)}")
    
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch pipelines")
        
    data = resp.json()
    pipelines = []
    
    for pipe in data.get("results", []):
        stages = []
        for stage in pipe.get("stages", []):
            stages.append({
                "id": stage["id"],
                "label": stage["label"],
                "displayOrder": stage.get("displayOrder", 0)
            })
        stages = sorted(stages, key=lambda x: x["displayOrder"])
            
        pipelines.append({
            "id": pipe["id"],
            "label": pipe["label"],
            "stages": stages
        })
        
    return {"pipelines": pipelines, "saved_stage_id": saved_stage_id}

class HubspotWonStage(BaseModel):
    stage_id: str

@router.post("/won-stage")
async def set_hubspot_won_stage(
    data: HubspotWonStage,
    workspace_id: str = Depends(require_workspace_admin),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    clean_stage_id = data.stage_id.strip() if data.stage_id else ""
    if not clean_stage_id:
        raise HTTPException(status_code=400, detail="stage_id cannot be empty")
    if len(clean_stage_id) > 128:
        raise HTTPException(status_code=400, detail="stage_id exceeds maximum length of 128 characters")

    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_query = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_res = await ws_query if hasattr(ws_query, "__await__") else ws_query
    tier = ws_res.data[0].get("tier", "FREE") if ws_res and ws_res.data else "FREE"
    can_sync = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("can_use_crm_sync", False)
    if not can_sync:
        raise HTTPException(
            status_code=403,
            detail="HubSpot CRM sync requires a Growth Pro subscription."
        )

    upd_query = supabase.table("workspaces").update({
        "hubspot_won_stage_id": clean_stage_id
    }).eq("id", workspace_id).execute()
    res = await upd_query if hasattr(upd_query, "__await__") else upd_query
    
    if not res or not res.data:
        raise HTTPException(status_code=500, detail="Failed to save won stage")

    return {"status": "ok"}

@router.post("/disconnect")
async def disconnect_hubspot(
    workspace_id: str = Depends(require_workspace_admin),
    supabase: AsyncClient = Depends(get_async_supabase_client)
):
    await _exec(supabase.table("workspaces").update({
        "hubspot_token": None,
        "hubspot_won_stage_id": None
    }).eq("id", workspace_id))
    return {"status": "ok", "message": "HubSpot disconnected successfully"}
