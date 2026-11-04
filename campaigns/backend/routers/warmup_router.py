import re
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field

from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.warmup_service import (
    list_warmup_mailboxes,
    create_warmup_mailbox,
    toggle_warmup_status,
    delete_warmup_mailbox,
    export_warmup_fleet_csv,
    audit_domain_dns_health,
    simulate_swarm_cycle,
    get_warmup_telemetry,
    calculate_daily_ramp_limit
)
from integrations.backend.services.mailbox_warmup_service import execute_warmup_swarm_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/warmup", tags=["email_warmup"])


# Pydantic Schemas
class CreateWarmupMailboxPayload(BaseModel):
    email_address: str = Field(..., description="Outbound sender mailbox email address")
    sender_name: str = Field(..., description="Display name for outbound sender")
    provider: Optional[str] = Field("google_workspace", description="google_workspace, microsoft_365, smtp_imap, or custom")
    ramp_strategy: Optional[str] = Field("balanced", description="gentle, balanced, or aggressive")
    max_daily_limit: Optional[int] = Field(40, description="Max daily warmup emails (capped at 50)")


class ToggleWarmupPayload(BaseModel):
    new_status: str = Field(..., description="warming, paused, graduated, or cooling_down")


class DnsAuditPayload(BaseModel):
    domain: str = Field(..., description="Domain name to audit (e.g. outbound-scale.com)")


class ExecuteSwarmBatchPayload(BaseModel):
    target_exchanges_per_box: Optional[int] = Field(3, description="Target peer exchanges per active mailbox")
    mailbox_ids: Optional[List[str]] = Field(None, description="Optional subset of mailbox IDs")


@router.get("/mailboxes")
def get_mailboxes_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Retrieves the entire active warmup mailbox fleet for this workspace.
    """
    try:
        mailboxes = list_warmup_mailboxes(workspace_id=workspace_id, supabase=supabase)
        return {
            "success": True,
            "data": mailboxes,
            "count": len(mailboxes)
        }
    except Exception as e:
        logger.exception("Failed to retrieve warmup mailboxes: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mailboxes/export-csv")
def export_mailboxes_csv_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Streams the warmup mailbox fleet and deliverability scores as a sanitized CSV download.
    """
    try:
        csv_content = export_warmup_fleet_csv(workspace_id=workspace_id, supabase=supabase)
        clean_ws_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", workspace_id)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="warmup_fleet_{clean_ws_id}.csv"'}
        )
    except Exception as e:
        logger.exception("Failed to export warmup fleet CSV: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mailboxes")
def create_mailbox_endpoint(
    payload: CreateWarmupMailboxPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Enrolls a new sender mailbox into the P2P warmup swarm with automated ramp pacing.
    """
    try:
        mailbox = create_warmup_mailbox(
            workspace_id=workspace_id,
            email_address=payload.email_address,
            sender_name=payload.sender_name,
            provider=payload.provider or "google_workspace",
            ramp_strategy=payload.ramp_strategy or "balanced",
            max_daily_limit=payload.max_daily_limit or 40,
            supabase=supabase
        )
        return {
            "success": True,
            "data": mailbox,
            "message": "Mailbox successfully enrolled into AI warmup network."
        }
    except Exception as e:
        logger.exception("Failed to create warmup mailbox: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mailboxes/{mailbox_id}/toggle")
def toggle_mailbox_endpoint(
    mailbox_id: str,
    payload: ToggleWarmupPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Toggles the warmup state for a mailbox (pause, resume, graduate, cool down).
    """
    try:
        updated = toggle_warmup_status(
            mailbox_id=mailbox_id,
            workspace_id=workspace_id,
            new_status=payload.new_status,
            supabase=supabase
        )
        return {
            "success": True,
            "data": updated
        }
    except Exception as e:
        logger.exception("Failed to toggle mailbox status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mailboxes/{mailbox_id}")
def delete_mailbox_endpoint(
    mailbox_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Unenrolls a mailbox from the warmup fleet with strict tenant isolation.
    """
    try:
        res = delete_warmup_mailbox(
            mailbox_id=mailbox_id,
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {
            "success": True,
            "data": res
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Failed to delete warmup mailbox: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dns-audit")
def dns_audit_endpoint(
    payload: DnsAuditPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Performs an instant SPF, DKIM, DMARC, and MX reputation health audit on a domain.
    """
    try:
        audit = audit_domain_dns_health(
            domain=payload.domain,
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {
            "success": True,
            "data": audit
        }
    except Exception as e:
        logger.exception("Failed to execute domain DNS audit: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/simulate-swarm")
def simulate_swarm_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Triggers an on-demand peer-to-peer exchange cycle across active mailboxes with spam rescues.
    """
    try:
        result = simulate_swarm_cycle(
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.exception("Failed to run swarm cycle simulation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
def get_telemetry_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Returns aggregate warmup telemetry, deliverability indices, and daily send limits.
    """
    try:
        telemetry = get_warmup_telemetry(
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {
            "success": True,
            "data": telemetry
        }
    except Exception as e:
        logger.exception("Failed to get warmup telemetry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swarm/execute-batch")
def execute_swarm_batch_endpoint(
    payload: Optional[ExecuteSwarmBatchPayload] = None,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Paranoia Layer 0, 1 & 2:
    Executes a high-reputation P2P warmup swarm batch across active workspace mailboxes.
    Evaluates deliverability health (0-100), throttles compromised inboxes by 50% or pauses them,
    and inserts exchange records into warmup_swarm_exchanges.
    """
    try:
        raw_boxes = list_warmup_mailboxes(workspace_id=workspace_id, supabase=supabase)
        active_boxes = [b for b in raw_boxes if b.get("warmup_status") in ("warming", "active", "ramp")]
        
        target_ids = payload.mailbox_ids if payload and payload.mailbox_ids else None
        if target_ids:
            active_boxes = [b for b in active_boxes if b.get("id") in target_ids]

        target_exchanges = payload.target_exchanges_per_box if payload and payload.target_exchanges_per_box else 3
        
        result = execute_warmup_swarm_batch(
            mailboxes=active_boxes,
            supabase=supabase,
            target_exchanges_per_box=target_exchanges,
            workspace_id=workspace_id
        )
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.exception("Failed to execute warmup swarm batch: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
