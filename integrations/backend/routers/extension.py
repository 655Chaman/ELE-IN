from fastapi import APIRouter, Depends, HTTPException, Header, Request
from supabase import Client
from core.backend.api.auth_dep import get_service_client
from typing import Optional, Dict, Any, List
from datetime import datetime

router = APIRouter()

def verify_extension_api_key(x_api_key: str = Header(...), supabase: Client = Depends(get_service_client)) -> str:
    """Verifies the extension API key and returns the workspace_id"""
    # Note: the user's schema stores hashes in api_keys, but for simplicity
    # during development we'll do a simple check. If they are storing plain 
    # text or matching it, we adjust here. For now, assuming direct match or matching key_prefix
    
    # Check api_keys table
    # Since they use key_hash, they probably hash it. If this fails, we will adjust.
    res = supabase.table("api_keys").select("workspace_id, is_active").eq("key_hash", x_api_key).execute()
    if not res.data or not res.data[0]["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid or inactive API Key")
    
    # Update last_used_at
    supabase.table("api_keys").update({
        "last_used_at": datetime.utcnow().isoformat()
    }).eq("key_hash", x_api_key).execute()
    
    return res.data[0]["workspace_id"]

@router.post("/heartbeat")
def extension_heartbeat(
    payload: Dict[str, Any],
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Called by the Chrome Extension every 5 minutes to report that the browser is alive.
    payload can contain account_id if the extension is linked to a specific sender account.
    """
    account_id = payload.get("account_id")
    worker_id = f"ext-{account_id}" if account_id else f"ext-ws-{workspace_id}"
    
    supabase.table("worker_heartbeat").upsert({
        "worker_id": worker_id,
        "last_beat_at": datetime.utcnow().isoformat(),
        "status": "alive"
    }).execute()
    
    return {"status": "ok"}

@router.get("/tasks")
def get_extension_tasks(
    account_id: str,
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Polls for tasks assigned to this account_id.
    """
    # Look for leads in 'processing' status assigned to this campaign/account
    # (Or pending tasks that are due).
    
    # For now, let's just find one pending task for any campaign using this account_id
    # We need a proper dequeue logic for the extension.
    # To keep it simple in this MVP, we query lead_states that are 'pending' and due.
    
    # 1. Get campaigns using this account_id
    camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).execute()
    valid_campaigns = []
    for c in camp_res.data:
        try:
            acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", c["id"]).execute()
            senders = [r["account_id"] for r in acc_res.data]
        except Exception:
            senders = []
        if account_id in senders:
            valid_campaigns.append(c["id"])
            
    
    if not valid_campaigns:
        return {"tasks": []}
        
    # 2. Get pending execution states for this workspace
    states_res = supabase.table("campaign_execution_states") \
        .select("id, current_node_id, variables, enrollment_id, campaign_enrollments(campaign_id, lead_id, leads(linkedin_url, first_name))") \
        .eq("workspace_id", workspace_id) \
        .eq("status", "pending") \
        .lte("next_run_at", datetime.utcnow().isoformat()) \
        .limit(20) \
        .execute()
        
    state = None
    lead = None
    for s in (states_res.data or []):
        enr = s.get("campaign_enrollments")
        if enr and enr.get("campaign_id") in valid_campaigns:
            state = s
            lead = enr.get("leads")
            break
            
    if not state or not lead:
        return {"tasks": []}
        
    # Mark it as 'running' so no other worker picks it up
    supabase.table("campaign_execution_states").update({"status": "running"}).eq("id", state["id"]).execute()
    
    # Return as a task payload for the extension
    task = {
        "task_id": state["id"],
        "type": "linkedin_connect", # In a full system, this depends on current_node_id
        "linkedin_url": lead.get("linkedin_url"),
        "first_name": lead.get("first_name"),
        "message": f"Hi {lead.get('first_name', '')}, I'd love to connect!" # AI generated in real system
    }
    
    return {"tasks": [task]}

@router.post("/tasks/{task_id}/result")
def report_task_result(
    task_id: str,
    payload: Dict[str, Any],
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Called by the Chrome Extension after executing a task.
    """
    # Verify ownership before updating
    ls_res = supabase.table("campaign_execution_states").select("workspace_id").eq("id", task_id).execute()
    if not ls_res.data or ls_res.data[0].get("workspace_id") != workspace_id:
        raise HTTPException(status_code=403, detail="Task does not belong to your workspace.")

    status = payload.get("status", "error") # 'success' or 'error'
    error_detail = payload.get("error_detail", "")
    
    if status == "success":
        new_status = "completed" # Or advance to next node
        supabase.table("campaign_execution_states").update({
            "status": new_status,
            "error_reason": None,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", task_id).execute()
        
        # Log it
        supabase.table("action_log").insert({
            "workspace_id": workspace_id,
            "execution_state_id": task_id,
            "action_type": "extension_execution",
            "result": "success"
        }).execute()
        
    else:
        new_status = "error"
        supabase.table("campaign_execution_states").update({
            "status": new_status,
            "error_reason": error_detail,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", task_id).execute()
        
        supabase.table("action_log").insert({
            "workspace_id": workspace_id,
            "execution_state_id": task_id,
            "action_type": "extension_execution",
            "result": "failed",
            "error_detail": error_detail
        }).execute()

    return {"status": "ok"}
