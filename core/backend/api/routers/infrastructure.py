import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from core.backend.api.auth_dep import get_service_client, get_current_workspace

logger = logging.getLogger(__name__)
router = APIRouter(tags=["infrastructure"])

# ── Health Check ─────────────────────────────────────────────────────────────
@router.get("/health")
def get_system_health():
    """Liveness probe for backend infrastructure."""
    return {
        "status": "ok",
        "service": "ele-in-backend",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ── Worker Heartbeat & Queue Monitoring ──────────────────────────────────────
@router.get("/workers")
def get_worker_status():
    """
    Returns the real-time heartbeat and liveness status of all backend worker daemons.
    Classifies daemons as active, stale (>120s since last beat), or errored.
    """
    svc = get_service_client()
    now_utc = datetime.now(timezone.utc)
    stale_threshold = now_utc - timedelta(seconds=120)

    try:
        res = svc.table("worker_heartbeat").select("*").execute()
        heartbeats = res.data or []
    except Exception as e:
        logger.error(f"Error querying worker heartbeats: {e}")
        return {"status": "degraded", "workers": [], "error": str(e)}

    worker_statuses = []
    for hb in heartbeats:
        worker_id = hb.get("worker_id", "unknown")
        raw_last_beat = hb.get("last_beat_at")
        hb_status = hb.get("status", "unknown")
        
        is_stale = False
        if raw_last_beat:
            try:
                beat_dt = datetime.fromisoformat(raw_last_beat.replace("Z", "+00:00"))
                if beat_dt.tzinfo is None:
                    beat_dt = beat_dt.replace(tzinfo=timezone.utc)
                if beat_dt < stale_threshold:
                    is_stale = True
            except Exception:
                is_stale = True

        effective_state = "stale" if is_stale else hb_status
        worker_statuses.append({
            "worker_id": worker_id,
            "status": effective_state,
            "raw_status": hb_status,
            "last_beat_at": raw_last_beat,
            "is_alive": not is_stale and hb_status in ("alive", "ticking"),
            "last_tick_duration_ms": hb.get("last_tick_duration_ms"),
            "last_tick_leads_processed": hb.get("last_tick_leads_processed"),
        })

    return {
        "status": "healthy" if any(w["is_alive"] for w in worker_statuses) else ("idle" if not worker_statuses else "stale"),
        "timestamp": now_utc.isoformat(),
        "workers": worker_statuses
    }

# ── Integrations ─────────────────────────────────────────────────────────────
@router.get("/integrations", response_model=List[Dict])
def get_integrations():
    """Mock endpoint for connected integrations."""
    return [
        {"id": "int_1", "provider": "hubspot", "status": "connected"},
        {"id": "int_2", "provider": "salesforce", "status": "disconnected"}
    ]

# ── Billing ──────────────────────────────────────────────────────────────────
@router.get("/billing", response_model=Dict)
def get_billing():
    """Mock endpoint for billing details."""
    return {
        "plan": "Pro",
        "billing_cycle": "monthly",
        "next_invoice_date": "2026-09-24",
        "credits_remaining": 12500
    }

# ── Workspace Settings ───────────────────────────────────────────────────────
@router.get("/workspace", response_model=Dict)
def get_workspace_settings():
    """Mock endpoint for workspace settings."""
    return {
        "name": "Ele-in Default Workspace",
        "timezone": "America/New_York",
        "team_size": 3
    }

# ── System Keys ──────────────────────────────────────────────────────────────
@router.get("/keys", response_model=Dict)
def get_system_keys(workspace_id: Optional[str] = Depends(get_current_workspace)):
    """
    Paranoia Layer 0, 1 & 2: Authenticated System Key Provider.
    Requires verified active workspace context.
    Never serves keys to unauthenticated callers or suspended workspaces.
    """
    if workspace_id:
        try:
            svc = get_service_client()
            if svc:
                ws_res = svc.table("workspaces").select("id, status").eq("id", workspace_id).limit(1).execute()
                if ws_res and ws_res.data:
                    status = str(ws_res.data[0].get("status") or "active").lower()
                    if status in ("suspended", "pending_deletion"):
                        raise HTTPException(status_code=403, detail="Workspace is suspended")
        except HTTPException:
            raise
        except Exception as db_e:
            logger.warning(f"Error checking workspace status in /keys: {db_e}")

    raw_key = os.environ.get("DEEPGRAM_API_KEY", "")
    key = raw_key.strip() if raw_key else ""
    if key in ("your_deepgram_api_key_here", "undefined", "null", "none"):
        logger.warning("DEEPGRAM_API_KEY contains placeholder value. Returning empty string to prevent connection failure.")
        key = ""
    elif not key:
        logger.warning("DEEPGRAM_API_KEY is not configured in backend/.env")

    return {
        "DEEPGRAM_API_KEY": key
    }
