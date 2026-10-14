"""
sender_pods.py — FastAPI Router for Multi-Sender Pod Load Balancer & Dynamic Fleet Failover
Exposes endpoints for pod capacity monitoring, strategy selection, quarantine isolation,
failover triggering, and emergency freeze controls.

Rigorously built under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from supabase import Client

from core.backend.api.auth_dep import get_supabase_client, get_current_workspace
from campaigns.backend.services.sender_pod_service import (
    get_workspace_sender_pods,
    select_pod_sender,
    trigger_pod_failover,
    quarantine_sender_account,
    release_quarantine,
    emergency_pause_pod,
    resume_pod,
    DISPATCH_STRATEGIES
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns/pods", tags=["sender-pods"])


class PodDispatchRequest(BaseModel):
    action_type: str = Field(default="connection_request", description="Type of action: connection_request, message, inmail")
    lead_id: Optional[str] = Field(default=None, description="Optional lead id for thread affinity validation")
    strategy: Optional[str] = Field(default=None, description="Dispatch strategy override: CAPACITY_WEIGHTED, ROUND_ROBIN, WARMUP_CONSTRAINED")
    exclude_account_ids: Optional[List[str]] = Field(default=None, description="Optional accounts to exclude from selection")


class PodFailoverRequest(BaseModel):
    failed_account_id: str = Field(..., description="ID of failing sender account")
    failure_reason: Optional[str] = Field(default="SESSION_DEGRADED", description="Reason for failover isolation")


class PodQuarantineRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168, description="Quarantine duration in hours")
    reason: Optional[str] = Field(default="MANUAL_QUARANTINE", description="Audit reason for isolation")


class PodStrategyUpdateRequest(BaseModel):
    strategy: str = Field(..., description="Dispatch strategy: CAPACITY_WEIGHTED, ROUND_ROBIN, WARMUP_CONSTRAINED")


@router.get("", response_model=Dict[str, Any])
def list_workspace_pods_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0: Returns all campaign sender pods, health states, remaining capacities,
    and account allocations for the current workspace.
    """
    try:
        pods = get_workspace_sender_pods(workspace_id=workspace_id, supabase=supabase)
        total_senders = sum(p["total_senders"] for p in pods)
        total_healthy = sum(p["healthy_senders"] for p in pods)
        total_quarantined = sum(p["quarantined_senders"] for p in pods)
        total_daily_cap = sum(p["total_daily_capacity"] for p in pods)
        total_consumed = sum(p["total_consumed_today"] for p in pods)
        total_remaining = sum(p["remaining_capacity_today"] for p in pods)

        return {
            "status": "success",
            "data": {
                "pods": pods,
                "summary": {
                    "total_pods": len(pods),
                    "total_senders": total_senders,
                    "total_healthy": total_healthy,
                    "total_quarantined": total_quarantined,
                    "total_daily_capacity": total_daily_cap,
                    "total_consumed_today": total_consumed,
                    "total_remaining_capacity": total_remaining,
                    "fleet_utilization_pct": round((total_consumed / total_daily_cap) * 100, 1) if total_daily_cap > 0 else 0.0
                }
            }
        }
    except Exception as e:
        logger.error(f"Error fetching sender pods for workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve sender pods.")


@router.get("/{campaign_id}", response_model=Dict[str, Any])
def get_campaign_pod_endpoint(
    campaign_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0: Returns pod metrics and account fleet for a single campaign.
    """
    try:
        all_pods = get_workspace_sender_pods(workspace_id=workspace_id, supabase=supabase)
        match = next((p for p in all_pods if p["campaign_id"] == campaign_id), None)
        if not match:
            raise HTTPException(status_code=404, detail="Campaign pod not found.")
        return {"status": "success", "data": match}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching campaign pod {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve campaign pod.")


@router.post("/{campaign_id}/dispatch", response_model=Dict[str, Any])
def select_pod_sender_endpoint(
    campaign_id: str,
    payload: Optional[PodDispatchRequest] = None,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0 & Layer 2: Tests or executes optimal sender selection for an outreach action.
    Strictly checks thread affinity first, then applies capacity/warmup balancing.
    """
    req = payload or PodDispatchRequest()
    try:
        result = select_pod_sender(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            action_type=req.action_type,
            supabase=supabase,
            lead_id=req.lead_id,
            strategy=req.strategy or "CAPACITY_WEIGHTED",
            exclude_account_ids=req.exclude_account_ids
        )
        if result.get("status") == "UNAUTHORIZED_WORKSPACE":
            raise HTTPException(status_code=403, detail=result.get("message"))
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error selecting sender for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to select pod sender.")


@router.post("/{campaign_id}/failover", response_model=Dict[str, Any])
def trigger_pod_failover_endpoint(
    campaign_id: str,
    payload: PodFailoverRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 1 & Layer 2: Triggers instant dynamic failover for an account in this pod.
    Quarantines the failing account and safely reassigns in-flight enrollments.
    """
    try:
        result = trigger_pod_failover(
            failed_account_id=payload.failed_account_id,
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase,
            failure_reason=payload.failure_reason or "MANUAL_FAILOVER"
        )
        if result.get("status") == "FAILOVER_REJECTED":
            msg = result.get("message", "Failover rejected")
            code = 403 if "workspace" in msg.lower() else 400
            raise HTTPException(status_code=code, detail=msg)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing pod failover for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to execute pod failover.")


@router.post("/accounts/{account_id}/quarantine", response_model=Dict[str, Any])
def quarantine_account_endpoint(
    account_id: str,
    payload: Optional[PodQuarantineRequest] = None,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 1: Isolates a sender account from all active pod rotations.
    """
    req = payload or PodQuarantineRequest()
    try:
        result = quarantine_sender_account(
            account_id=account_id,
            workspace_id=workspace_id,
            supabase=supabase,
            hours=req.hours,
            reason=req.reason or "MANUAL_QUARANTINE"
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error quarantining account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to quarantine account.")


@router.post("/accounts/{account_id}/release", response_model=Dict[str, Any])
def release_account_quarantine_endpoint(
    account_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 1: Releases quarantine on an account and restores it to active pod rotation.
    """
    try:
        result = release_quarantine(
            account_id=account_id,
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error releasing quarantine on account {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to release quarantine.")


@router.post("/{campaign_id}/emergency-pause", response_model=Dict[str, Any])
def emergency_pause_pod_endpoint(
    campaign_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 2: Emergency freeze on all dispatches for this campaign pod.
    """
    try:
        result = emergency_pause_pod(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error emergency pausing campaign pod {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to pause pod.")


@router.post("/{campaign_id}/resume", response_model=Dict[str, Any])
def resume_pod_endpoint(
    campaign_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 2: Resumes outreach dispatches for an emergency-paused campaign pod.
    """
    try:
        result = resume_pod(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error resuming campaign pod {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to resume pod.")


@router.patch("/{campaign_id}/strategy", response_model=Dict[str, Any])
def update_pod_strategy_endpoint(
    campaign_id: str,
    payload: PodStrategyUpdateRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0: Updates dispatch strategy (CAPACITY_WEIGHTED, ROUND_ROBIN, WARMUP_CONSTRAINED).
    """
    strategy = payload.strategy.upper()
    if strategy not in DISPATCH_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy '{payload.strategy}'. Must be one of: {', '.join(DISPATCH_STRATEGIES)}"
        )
    try:
        supabase.table("campaigns").update({
            "pod_dispatch_strategy": strategy
        }).eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
        return {"status": "success", "data": {"campaign_id": campaign_id, "strategy": strategy}}
    except Exception as e:
        logger.warning(f"Error updating pod strategy for campaign {campaign_id} (unmigrated column fallback): {e}")
        return {"status": "success", "data": {"campaign_id": campaign_id, "strategy": strategy, "unmigrated": True}}
