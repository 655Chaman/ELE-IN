import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.advocacy_pod_service import (
    create_pod,
    list_pods,
    add_pod_member,
    list_pod_members,
    submit_post_for_boost,
    list_post_boosts,
    cancel_post_boost,
    get_advocacy_telemetry
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/advocacy", tags=["advocacy_pods_and_viral_booster"])


# ── Pydantic Request Models ────────────────────────────────────────────────────

class CreatePodPayload(BaseModel):
    name: str = Field(..., description="Advocacy pod name")
    description: Optional[str] = Field("", description="Optional pod purpose and team scope")
    settings: Optional[Dict[str, Any]] = Field(None, description="Optional customization settings")


class AddPodMemberPayload(BaseModel):
    account_id: str = Field(..., description="Sender account ID to enroll in pod")
    account_name: Optional[str] = Field("", description="Display name / title of account holder")
    daily_like_cap: Optional[int] = Field(15, description="Max likes allocated to advocacy per day")
    daily_comment_cap: Optional[int] = Field(5, description="Max comments allocated to advocacy per day")
    role: Optional[str] = Field("member", description="member or admin")


class SubmitPostBoostPayload(BaseModel):
    pod_id: str = Field(..., description="Target advocacy pod ID")
    author_account_id: str = Field(..., description="Account ID of author (strictly excluded from self-boost)")
    post_url: str = Field(..., description="LinkedIn post URL or activity URN to boost")
    post_content: Optional[str] = Field("", description="Post text for contextual comment generation")
    target_likes: Optional[int] = Field(10, description="Desired like count within golden hour")
    target_comments: Optional[int] = Field(5, description="Desired contextual comment count")
    target_window_minutes: Optional[int] = Field(60, description="Golden hour window duration in minutes")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/pods")
def get_pods_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Lists all advocacy pods for the workspace."""
    try:
        pods = list_pods(workspace_id, supabase)
        return {"success": True, "data": pods, "count": len(pods)}
    except Exception as e:
        logger.error(f"Error fetching advocacy pods: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pods")
def create_pod_endpoint(
    payload: CreatePodPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Creates a new advocacy pod for team members."""
    try:
        pod = create_pod(
            workspace_id=workspace_id,
            name=payload.name,
            description=payload.description or "",
            settings=payload.settings,
            supabase=supabase
        )
        return {"success": True, "pod": pod}
    except Exception as e:
        logger.error(f"Error creating advocacy pod: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pods/{pod_id}/members")
def add_pod_member_endpoint(
    pod_id: str,
    payload: AddPodMemberPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Enrolls a sender account into an advocacy pod."""
    try:
        member = add_pod_member(
            workspace_id=workspace_id,
            pod_id=pod_id,
            account_id=payload.account_id,
            account_name=payload.account_name or "",
            daily_like_cap=payload.daily_like_cap or 15,
            daily_comment_cap=payload.daily_comment_cap or 5,
            role=payload.role or "member",
            supabase=supabase
        )
        return {"success": True, "member": member}
    except Exception as e:
        logger.error(f"Error adding member to advocacy pod: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pods/{pod_id}/members")
def get_pod_members_endpoint(
    pod_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Lists all enrolled members for a specific pod."""
    try:
        members = list_pod_members(workspace_id, pod_id, supabase)
        return {"success": True, "data": members, "count": len(members)}
    except Exception as e:
        logger.error(f"Error listing pod members: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boost-post")
def submit_post_boost_endpoint(
    payload: SubmitPostBoostPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Submits a LinkedIn post for golden-hour algorithmic boosting."""
    if not payload.post_url or not payload.author_account_id:
        raise HTTPException(status_code=400, detail="post_url and author_account_id are required")
    
    try:
        boost = submit_post_for_boost(
            workspace_id=workspace_id,
            pod_id=payload.pod_id,
            author_account_id=payload.author_account_id,
            post_url=payload.post_url,
            post_content=payload.post_content or "",
            target_likes=payload.target_likes or 10,
            target_comments=payload.target_comments or 5,
            target_window_minutes=payload.target_window_minutes or 60,
            supabase=supabase
        )
        return {"success": True, "boost": boost}
    except Exception as e:
        logger.error(f"Error submitting post for boost: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boosts")
def list_boosts_endpoint(
    pod_id: Optional[str] = Query(None, description="Filter by pod ID"),
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Lists all active and historical post boosts."""
    try:
        boosts = list_post_boosts(workspace_id, pod_id, supabase)
        return {"success": True, "data": boosts, "count": len(boosts)}
    except Exception as e:
        logger.error(f"Error listing post boosts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/boosts/{boost_id}/cancel")
def cancel_boost_endpoint(
    boost_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Cancels an in-progress post boost."""
    try:
        res = cancel_post_boost(workspace_id, boost_id, supabase)
        return {"success": True, "data": res}
    except Exception as e:
        logger.error(f"Error cancelling boost: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
def get_telemetry_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_service_client)
):
    """Returns workspace-wide advocacy and virality telemetry."""
    try:
        telemetry = get_advocacy_telemetry(workspace_id, supabase)
        return {"success": True, "telemetry": telemetry}
    except Exception as e:
        logger.error(f"Error fetching advocacy telemetry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
