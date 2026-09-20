import jwt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
from supabase import Client

# We must import these from the correct location. 
# They are defined in elein.py but they depend on auth_dep.py.
# To avoid circular imports, let's just use auth_dep.py and re-implement get_current_workspace here.
from core.backend.api.auth_dep import get_supabase_client, get_current_workspace, get_current_user_id, get_service_client
from fastapi import Request

router = APIRouter()

async def require_workspace_admin(
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_service_client)
):
    result = supabase.table("workspace_members") \
        .select("role") \
        .eq("workspace_id", workspace_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()
    if not result.data or result.data["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return workspace_id

class HubspotAuth(BaseModel):
    access_token: str

@router.get("/status")
async def get_hubspot_status(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """Returns the stored token if it exists (so the UI can show Connected on load)"""
    res = supabase.table("workspaces").select("hubspot_token").eq("id", workspace_id).execute()
    if not res.data or not res.data[0].get("hubspot_token"):
        return {"connected": False}
    return {"connected": True}

@router.post("/auth")
async def authenticate_hubspot(
    data: HubspotAuth,
    workspace_id: str = Depends(require_workspace_admin),
    supabase: Client = Depends(get_supabase_client)
):
    # Verify the token by calling HubSpot API
    headers = {
        "Authorization": f"Bearer {data.access_token}",
        "Content-Type": "application/json"
    }
    from core.backend.services.http_client import async_external_request
    
    # Using the CRM properties endpoint as a simple validation
    resp = await async_external_request("GET", "https://api.hubapi.com/crm/v3/properties/contacts", headers=headers)
    
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid HubSpot Access Token")
        
    # Valid token! Save it to the workspace.
    supabase.table("workspaces").update({
        "hubspot_token": data.access_token
    }).eq("id", workspace_id).execute()

    return {"status": "ok", "message": "Authenticated and token saved successfully"}

@router.get("/lists")
async def get_hubspot_lists(
    access_token: str = None,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    # If no token passed in query, try fetching from DB
    if not access_token:
        res = supabase.table("workspaces").select("hubspot_token").eq("id", workspace_id).execute()
        if res.data and res.data[0].get("hubspot_token"):
            access_token = res.data[0]["hubspot_token"]
            
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token provided or found in workspace")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    from core.backend.services.http_client import async_external_request
    
    # Using legacy lists API because v3 lists is often in beta
    resp = await async_external_request("GET", "https://api.hubapi.com/contacts/v1/lists", headers=headers)
    
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
    supabase: Client = Depends(get_supabase_client)
):
    import uuid
    import logging
    from core.backend.services.job_queue import enqueue_job
    logger = logging.getLogger(__name__)

    # Fetch token from workspace
    res = supabase.table("workspaces").select("hubspot_token").eq("id", workspace_id).execute()
    if not res.data or not res.data[0].get("hubspot_token"):
        raise HTTPException(status_code=400, detail="HubSpot not connected")
    
    # We do NOT put the raw access_token in the payload; the worker fetches it securely.
    
    # Create internal lead list to store the imported leads
    internal_list_id = str(uuid.uuid4())
    try:
        supabase.table("lead_lists").insert({
            "id": internal_list_id,
            "name": f"HubSpot Import {list_id}",
            "type": "hubspot",
            "row_count": -1,
            "workspace_id": workspace_id,
        }).execute()
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

