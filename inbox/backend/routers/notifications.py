from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from supabase import Client
from core.backend.api.auth_dep import get_current_workspace, get_current_user_id, get_supabase_client

router = APIRouter()

@router.get("/notifications")
def get_notifications(
    unread_only: bool = False,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
):
    query = supabase.table("notifications").select("*").eq("workspace_id", workspace_id).eq("user_id", user_id).order("created_at", desc=True)
    if unread_only:
        query = query.is_("read_at", "null")
    
    res = query.execute()
    return res.data

@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
):
    res = supabase.table("notifications").update({"read_at": datetime.now(timezone.utc).isoformat()}).eq("id", notification_id).eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok"}
