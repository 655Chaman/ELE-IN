import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from supabase import Client

from core.backend.api.auth_dep import get_current_workspace, get_service_client, get_current_user_id
from core.backend.core.crypto import encrypt_bytes
from integrations.backend.services.webhook_service import (
    SUPPORTED_WEBHOOK_EVENTS, 
    test_webhook_endpoint
)

router = APIRouter()

class CreateWebhookRequest(BaseModel):
    url: str
    event_types: List[str]

class UpdateWebhookRequest(BaseModel):
    url: Optional[str] = None
    event_types: Optional[List[str]] = None
    is_active: Optional[bool] = None

class VerifySignatureRequest(BaseModel):
    payload: str
    secret: str
    signature: str
    timestamp: str
    tolerance_seconds: Optional[int] = 300

@router.get("/events")
def get_supported_events():
    """Returns catalog of supported webhook events for frontend tag selection."""
    return {
        "status": "success",
        "events": SUPPORTED_WEBHOOK_EVENTS
    }

@router.get("/sample")
def get_sample_event_payload(
    event: Optional[str] = "lead.replied"
):
    """
    Returns realistic sample payload for Zapier / Make schema mapping.
    """
    from integrations.backend.services.webhook_service import get_sample_webhook_payload
    selected_event = event if event in SUPPORTED_WEBHOOK_EVENTS else "lead.replied"
    sample = get_sample_webhook_payload(selected_event)
    return {
        "status": "success",
        "event": selected_event,
        "sample": sample
    }

@router.post("/verify-signature")
def verify_signature_endpoint(
    req: VerifySignatureRequest
):
    """
    Diagnostic endpoint to test and troubleshoot customer HMAC signature verification.
    """
    from integrations.backend.services.webhook_service import debug_verify_signature
    result = debug_verify_signature(
        payload_str=req.payload,
        secret=req.secret,
        signature=req.signature,
        timestamp=req.timestamp,
        tolerance_seconds=req.tolerance_seconds or 300
    )
    return {
        "status": "success",
        "result": result
    }

@router.post("")
def create_webhook(
    req: CreateWebhookRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    # Paranoia Layer 1: Check Workspace Tier Limit
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    tier = ws_res.data[0].get("tier", "FREE") if (ws_res.data and isinstance(ws_res.data, list)) else "FREE"
    max_wh = TIER_LIMITS.get(tier, TIER_LIMITS["FREE"]).get("max_webhooks", 0)
    if max_wh <= 0:
        raise HTTPException(
            status_code=403,
            detail="Custom Webhooks require a Growth Pro subscription. Upgrade to stream live event payloads to external endpoints."
        )

    from integrations.backend.services.webhook_service import normalize_webhook_url
    norm_url = normalize_webhook_url(req.url)
    if not norm_url:
        raise HTTPException(status_code=400, detail="Invalid webhook URL")

    from core.backend.core.validators import is_safe_ssrf_url
    if not is_safe_ssrf_url(norm_url):
        raise HTTPException(status_code=400, detail="Invalid or unsafe webhook URL (SSRF violation).")

    # Paranoia Layer 2: Duplicate Endpoint Detection for active URLs in workspace
    existing_dup = supabase.table("webhook_endpoints") \
        .select("id") \
        .eq("workspace_id", workspace_id) \
        .eq("url", norm_url) \
        .eq("is_active", True) \
        .execute()
    if isinstance(getattr(existing_dup, "data", None), list) and len(existing_dup.data) > 0:
        raise HTTPException(
            status_code=409,
            detail="An active webhook endpoint with this URL already exists in this workspace."
        )

    existing_wh = supabase.table("webhook_endpoints").select("id", count="exact").eq("workspace_id", workspace_id).eq("is_active", True).execute()
    wh_count = getattr(existing_wh, "count", 0) or 0
    if wh_count >= max_wh:
        raise HTTPException(
            status_code=403,
            detail=f"Webhook endpoint limit reached ({max_wh}). Upgrade to Enterprise for up to 50 active webhook endpoints."
        )
        
    # Generate a random signing secret (e.g. whsec_...)
    raw_secret = f"whsec_{secrets.token_hex(16)}"
    
    # Encrypt the secret at rest
    encrypted_secret_hex = encrypt_bytes(raw_secret.encode('utf-8')).hex()
    
    res = supabase.table("webhook_endpoints").insert({
        "workspace_id": workspace_id,
        "url": norm_url,
        "event_types": req.event_types or ["*"],
        "signing_secret": encrypted_secret_hex,
        "is_active": True
    }).execute()
    
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create webhook endpoint.")

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
    res = supabase.table("webhook_endpoints").select("id, url, event_types, is_active, created_at").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": res.data or []}

@router.patch("/{endpoint_id}")
def update_webhook(
    endpoint_id: str,
    req: UpdateWebhookRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Updates an existing webhook endpoint's URL, events, or active state."""
    updates: Dict[str, Any] = {}
    if req.url is not None:
        from core.backend.core.validators import is_safe_ssrf_url
        if not is_safe_ssrf_url(req.url):
            raise HTTPException(status_code=400, detail="Invalid or unsafe webhook URL (SSRF violation).")
        updates["url"] = req.url
    if req.event_types is not None:
        updates["event_types"] = req.event_types
    if req.is_active is not None:
        updates["is_active"] = req.is_active

    if not updates:
        return {"status": "success", "message": "No changes specified."}

    res = supabase.table("webhook_endpoints").update(updates).eq("id", endpoint_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found.")

    return {"status": "success", "data": res.data[0]}

@router.post("/{endpoint_id}/rotate-secret")
def rotate_webhook_secret_endpoint(
    endpoint_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Atomically rotates a webhook endpoint's signing secret."""
    from integrations.backend.services.webhook_service import rotate_webhook_signing_secret
    res = rotate_webhook_signing_secret(endpoint_id, workspace_id, supabase)
    if res.get("status") == "error":
        msg = res.get("message", "Failed to rotate secret")
        if "not found" in msg.lower() or "unauthorized" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return res

@router.delete("/dead-letter-queue/prune")
def prune_webhook_dlq_endpoint(
    retention_days: Optional[int] = 30,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Prunes expired dead-letter queue webhook deliveries."""
    from integrations.backend.services.webhook_service import prune_expired_webhook_dlq
    res = prune_expired_webhook_dlq(workspace_id=workspace_id, retention_days=retention_days or 30, supabase=supabase)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("message", "Prune failed"))
    return res

@router.delete("/{endpoint_id}")
def delete_webhook(
    endpoint_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Deletes a webhook endpoint."""
    res = supabase.table("webhook_endpoints").delete().eq("id", endpoint_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "success", "message": "Webhook deleted"}

@router.post("/{endpoint_id}/test")
def test_webhook(
    endpoint_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 0 & 2: Dispatches an instantaneous test ping to the endpoint,
    returning HTTP status code, round-trip latency (ms), and response snippet.
    """
    res = test_webhook_endpoint(endpoint_id, workspace_id, supabase)
    if res.get("status") == "error" and "not found" in res.get("message", "").lower():
        raise HTTPException(status_code=404, detail=res["message"])
    return res

@router.get("/{endpoint_id}/deliveries")
def get_webhook_deliveries(
    endpoint_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """Returns the 25 most recent delivery records for observability."""
    res = supabase.table("webhook_deliveries") \
        .select("id, event_type, status_code, delivery_status, attempt_count, response_body, created_at") \
        .eq("endpoint_id", endpoint_id) \
        .eq("workspace_id", workspace_id) \
        .order("created_at", desc=True) \
        .limit(25) \
        .execute()

    return {"status": "success", "data": res.data or []}

@router.get("/dead-letter-queue")
def get_dead_letter_queue_endpoint(
    limit: Optional[int] = 50,
    offset: Optional[int] = 0,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 0, 1 & 2: Lists quarantined webhook deliveries from the Dead-Letter Queue (DLQ).
    """
    from integrations.backend.services.webhook_service import get_dead_letter_queue
    res = get_dead_letter_queue(workspace_id=workspace_id, limit=limit or 50, offset=offset or 0, supabase=supabase)
    if res.get("status") == "error":
        raise HTTPException(status_code=500, detail=res.get("error", "Failed to retrieve DLQ"))
    return res

@router.post("/deliveries/{delivery_id}/replay")
def replay_delivery_endpoint(
    delivery_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 0, 1 & 2: Replays a failed or past webhook delivery.
    """
    from integrations.backend.services.webhook_service import replay_webhook_delivery
    res = replay_webhook_delivery(delivery_id, workspace_id, supabase)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to replay delivery"))
    return res

@router.post("/deliveries/{delivery_id}/retry-dlq")
def retry_dlq_delivery_endpoint(
    delivery_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 0, 1 & 2: Re-enqueues a dead-lettered webhook delivery for immediate execution.
    Verifies tenant workspace ownership (IDOR defense) and resets delivery attempt counters.
    """
    from integrations.backend.services.webhook_service import retry_dead_letter_delivery
    res = retry_dead_letter_delivery(delivery_id=delivery_id, workspace_id=workspace_id, supabase=supabase)
    if res.get("status") == "error":
        msg = res.get("message", "Failed to re-enqueue DLQ delivery")
        if "not found" in msg.lower() or "foreign workspace" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return res
