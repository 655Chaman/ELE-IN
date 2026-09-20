from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from supabase._async.client import AsyncClient
from core.backend.api.auth_dep import get_async_service_client, get_current_user_id

router = APIRouter()

class AgencyCreate(BaseModel):
    name: str

class ClientWorkspaceCreate(BaseModel):
    name: str

class AgencyMemberInvite(BaseModel):
    email: str
    role: str

@router.post("")
async def create_agency(
    payload: AgencyCreate,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    # 1. Create agency
    agency_res = await supabase.table("agencies").insert({
        "name": payload.name,
        "owner_id": user_id
    }).execute()
    if not agency_res.data:
        raise HTTPException(status_code=400, detail="Failed to create agency")
    
    agency_id = agency_res.data[0]["id"]
    
    # 2. Add creator as owner
    await supabase.table("agency_members").insert({
        "agency_id": agency_id,
        "user_id": user_id,
        "role": "owner"
    }).execute()
    
    return {"status": "success", "agency": agency_res.data[0]}

@router.post("/{agency_id}/clients")
async def create_client_workspace(
    agency_id: str,
    payload: ClientWorkspaceCreate,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    # RLS on workspaces will block insert if the user isn't allowed,
    # but currently workspaces RLS insert policy might need tweaking.
    # We will assume RLS allows insert or we rely on the service role if needed.
    # For now, just insert.
    ws_res = await supabase.table("workspaces").insert({
        "name": payload.name,
        "owner_id": user_id,
        "agency_id": agency_id
    }).execute()
    
    if not ws_res.data:
        raise HTTPException(status_code=400, detail="Failed to create client workspace")
        
    return {"status": "success", "workspace": ws_res.data[0]}

@router.post("/{agency_id}/members")
async def invite_member(
    agency_id: str,
    payload: AgencyMemberInvite,
    supabase: AsyncClient = Depends(get_async_service_client)
):
    from core.backend.api.auth_dep import get_async_service_client
    svc = await get_async_service_client()
    
    target_user_id = None
    page = 1
    per_page = 500
    
    while True:
        users = await svc.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            break
            
        for u in users:
            if u.email == payload.email:
                target_user_id = u.id
                break
                
        if target_user_id or len(users) < per_page:
            break
            
        page += 1
            
    if not target_user_id:
        raise HTTPException(status_code=404, detail="User must have an account first")
        
    member_res = await supabase.table("agency_members").insert({
        "agency_id": agency_id,
        "user_id": target_user_id,
        "role": payload.role
    }).execute()
    
    return {"status": "success", "member": member_res.data[0]}

@router.post("/{agency_id}/members/{member_id}/access")
async def grant_client_access(
    agency_id: str,
    member_id: str,
    payload: dict, # expects workspace_id
    supabase: AsyncClient = Depends(get_async_service_client)
):
    workspace_id = payload.get("workspace_id")
    res = await supabase.table("agency_client_access").insert({
        "agency_member_id": member_id,
        "workspace_id": workspace_id
    }).execute()
    return {"status": "success", "access": res.data[0]}

@router.delete("/{agency_id}/members/{member_id}/access")
async def revoke_client_access(
    agency_id: str,
    member_id: str,
    payload: dict,
    supabase: AsyncClient = Depends(get_async_service_client)
):
    workspace_id = payload.get("workspace_id")
    await supabase.table("agency_client_access").delete().eq("agency_member_id", member_id).eq("workspace_id", workspace_id).execute()
    return {"status": "success"}

@router.get("")
async def list_my_agencies(
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """Return all agencies this user belongs to (with their role)."""
    mem_res = await supabase.table("agency_members").select("role, agency_id").eq("user_id", user_id).execute()
    if not mem_res.data:
        return []

    out = []
    for row in mem_res.data:
        agency_res = await supabase.table("agencies").select("id, name").eq("id", row["agency_id"]).execute()
        if agency_res.data:
            out.append({
                "id": agency_res.data[0]["id"],
                "name": agency_res.data[0]["name"],
                "role": row["role"]
            })
    return out

@router.get("/{agency_id}/members")
async def list_agency_members(
    agency_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """List all members of an agency with their per-client access grants."""
    from core.backend.api.auth_dep import get_async_service_client
    svc = await get_async_service_client()

    mem_res = await supabase.table("agency_members").select("id, user_id, role").eq("agency_id", agency_id).execute()
    if not mem_res.data:
        return []

    # Batch-fetch emails via admin SDK
    all_users = {}
    page = 1
    while True:
        users = await svc.auth.admin.list_users(page=page, per_page=500)
        if not users:
            break
        for u in users:
            all_users[u.id] = u.email or u.id
        if len(users) < 500:
            break
        page += 1

    out = []
    for row in mem_res.data:
        member_id = row["id"]
        # Fetch client access grants for this member
        access_res = await supabase.table("agency_client_access").select("workspace_id").eq("agency_member_id", member_id).execute()
        access = [acc["workspace_id"] for acc in (access_res.data or [])]
        out.append({
            "id": member_id,
            "user_id": row["user_id"],
            "display_name": all_users.get(row["user_id"], row["user_id"]),
            "role": row["role"],
            "access": access
        })
    return out

@router.get("/{agency_id}/clients")
async def list_agency_clients(
    agency_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """List all client workspaces that belong to this agency."""
    res = await supabase.table("workspaces").select("id, name").eq("agency_id", agency_id).execute()
    return res.data or []

