from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from supabase import Client
from core.backend.api.auth_dep import get_current_workspace, get_current_user_id, get_supabase_client

router = APIRouter()

@router.get("/notifications")
def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
):
    # Paranoia Layer 2: Sanitize pagination bounds
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    query = supabase.table("notifications").select("*").eq("workspace_id", workspace_id).eq("user_id", user_id).order("created_at", desc=True)
    if unread_only:
        query = query.is_("read_at", "null")
    
    query = query.range(offset, offset + limit - 1)
    res = query.execute()
    return res.data or []

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

@router.post("/notifications/read-all")
def mark_all_notifications_read(
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
):
    """Marks all unread notifications as read for the user in current workspace."""
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("notifications").update({"read_at": now_iso}).eq("workspace_id", workspace_id).eq("user_id", user_id).is_("read_at", "null").execute()
    return {"status": "ok", "message": "All notifications marked as read"}

from pydantic import BaseModel

class TestNotificationRequest(BaseModel):
    event_type: Optional[str] = "lead_replied_instant"
    channel: Optional[str] = "in_app"

@router.post("/notifications/test")
def send_test_notification(
    payload: TestNotificationRequest = TestNotificationRequest(),
    workspace_id: str = Depends(get_current_workspace),
    user_id: str = Depends(get_current_user_id),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Dispatches an interactive sample notification for onboarding test-bench and pre-permission teaser.
    Layer 1 & 2 Paranoia: Idempotent, safe sample data, bounded insertion, never crashes.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    test_event_type = payload.event_type or "lead_replied_instant"
    
    sample_content = {
        "lead_replied_instant": {
            "title": "Sarah Lin (Head of Growth @ DataPulse) just replied",
            "body": "Asking if Ele-in syncs with HubSpot & handles residential proxies. AI Ghostwriter has drafted a reply ready for 1-click review.",
            "link": "/inbox"
        },
        "account_needs_attention": {
            "title": "Account Safety Alert: Natural Jitter Active",
            "body": "Account 'David SDR' reached 80% daily invite ceiling. Outreach slowed to prevent LinkedIn detection.",
            "link": "/accounts"
        },
        "campaign_completed": {
            "title": "Campaign Completed: VP Sales Outreach",
            "body": "All 250 enrolled prospects contacted. 18.4% acceptance rate with 11 positive responses.",
            "link": "/campaigns"
        }
    }.get(test_event_type, {
        "title": "Real-Time Notification Test",
        "body": "Your real-time notification alerts are configured and working properly.",
        "link": "/inbox"
    })
    
    notification_data = {
        "id": "test-preview",
        "workspace_id": workspace_id,
        "user_id": user_id,
        "title": sample_content["title"],
        "body": sample_content["body"],
        "link": sample_content["link"],
        "event_type": test_event_type,
        "created_at": now_iso
    }
    return {"status": "ok", "notification": notification_data}


@router.get("/notifications/dlq")
def list_notification_dlq(
    limit: int = 50,
    offset: int = 0,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 2: Lists dead-lettered ('failed' or 'suspended') outbox notification events
    for the current workspace with strict pagination bounds.
    """
    from inbox.backend.services.outbox_worker import get_outbox_dead_letter_events
    res = get_outbox_dead_letter_events(supabase, workspace_id=workspace_id, limit=limit, offset=offset)
    if res.get("status") == "error" and "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res


@router.post("/notifications/dlq/{event_id}/retry")
def retry_notification_dlq_event(
    event_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 2: Re-queues a quarantined dead-letter outbox event after verifying
    workspace ownership, status eligibility, and SSRF safety.
    """
    clean_id = (event_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="Invalid event_id")

    from inbox.backend.services.outbox_worker import retry_outbox_dead_letter_event
    res = retry_outbox_dead_letter_event(supabase, event_id=clean_id, workspace_id=workspace_id)
    if res.get("status") == "error":
        msg = res.get("message", "Failed to retry DLQ event")
        if "not found" in msg.lower() or "unauthorized" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return res
