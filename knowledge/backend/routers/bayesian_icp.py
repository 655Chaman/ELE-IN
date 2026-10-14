"""
bayesian_icp.py — FastAPI Router for Bayesian ICP Calibration Studio & Adaptive Feedback Loop
Exposes endpoints for Bayesian prior monitoring, credible interval analytics, model drift detection,
operator signal freeze locks, and live prospect simulation scoring.
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from core.backend.api.auth_dep import get_supabase_client, get_current_workspace
from supabase import Client
from knowledge.backend.services.bayesian_icp_service import (
    record_outcome,
    record_adaptive_feedback,
    get_workspace_signal_weights,
    get_detailed_calibration_matrix,
    calibrate_signal,
    reset_all_signals_to_baseline,
    get_feedback_events,
    compute_bayesian_icp_score
)
from core.backend.services.credit_service import check_tier_access

router = APIRouter(prefix="/api/knowledge/icp", tags=["Bayesian ICP"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class RecordOutcomeRequest(BaseModel):
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    outcome: str = Field(..., description="Outcome: won, lost, POSITIVE_REPLY, MEETING_BOOKED, CONNECTION_ACCEPTED, GHOSTED_OR_LOST")
    signal_flags: Dict[str, bool] = Field(..., description="Binary flags indicating which ICP signals were present")
    details: Optional[Dict[str, Any]] = None


class ScoreRequest(BaseModel):
    profile_data: Optional[Dict[str, Any]] = None


class CalibrateSignalRequest(BaseModel):
    is_frozen: Optional[bool] = Field(default=None, description="Whether to lock signal against automated learning drift")
    weight_multiplier: Optional[float] = Field(default=None, ge=0.1, le=5.0, description="Multiplier for signal importance (0.1x to 5.0x)")
    reset_to_prior: Optional[bool] = Field(default=False, description="Reset this signal's alpha and beta to factory Beta(2,2)")


# ─────────────────────────────────────────────────────────────────────────────
# Calibration Studio Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/calibration", response_model=Dict[str, Any])
def api_get_calibration_matrix(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Returns full calibration matrix including:
    - All signals with Beta parameters, Credible Intervals, confidence tiers
    - Model drift alerts and divergence warnings
    - Recommended optimal score gate threshold
    """
    return get_detailed_calibration_matrix(supabase, workspace_id)


@router.post("/signals/{signal_name}/calibrate", response_model=Dict[str, Any])
def api_calibrate_signal(
    signal_name: str = Path(..., description="Target signal key e.g. is_decision_maker"),
    body: CalibrateSignalRequest = ...,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Allows human operators to freeze weights, adjust multipliers, or reset individual signal priors.
    """
    if not check_tier_access(workspace_id, 'bayesian_icp'):
        raise HTTPException(
            status_code=403,
            detail="Bayesian ICP Calibration Studio is a Growth Pro feature. Upgrade to unlock autonomous signal tuning."
        )

    res = calibrate_signal(
        supabase=supabase,
        workspace_id=workspace_id,
        signal_name=signal_name,
        is_frozen=body.is_frozen,
        weight_multiplier=body.weight_multiplier,
        reset_to_prior=body.reset_to_prior or False
    )
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to calibrate signal"))
    return res


@router.post("/reset-all", response_model=Dict[str, Any])
def api_reset_all_signals(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    1-Click Circuit Breaker: Resets all Bayesian priors in the workspace to factory Beta(2,2).
    """
    if not check_tier_access(workspace_id, 'bayesian_icp'):
        raise HTTPException(
            status_code=403,
            detail="Bayesian ICP Calibration Studio is a Growth Pro feature."
        )

    return reset_all_signals_to_baseline(supabase, workspace_id)


@router.get("/feedback-events", response_model=Dict[str, Any])
def api_get_feedback_events(
    limit: int = 30,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Returns chronological stream of recent learning events (replies, meetings, losses).
    """
    events = get_feedback_events(supabase, workspace_id, limit=limit)
    return {"status": "success", "events": events}


# ─────────────────────────────────────────────────────────────────────────────
# Existing Learning & Scoring Endpoints (Backward Compatible)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/record-outcome")
def api_record_outcome(
    req: RecordOutcomeRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not check_tier_access(workspace_id, 'bayesian_icp'):
        raise HTTPException(
            status_code=403,
            detail="Bayesian ICP Adaptive Weight Learning is a Growth Pro feature. Upgrade to unlock autonomous prospect scoring."
        )

    res = record_adaptive_feedback(
        supabase=supabase,
        workspace_id=workspace_id,
        lead_id=req.lead_id,
        campaign_id=req.campaign_id,
        event_type=req.outcome,
        signal_flags=req.signal_flags,
        details=req.details
    )
    return {"status": "success", "message": f"Outcome {req.outcome} recorded for Bayesian learning", "result": res}


@router.get("/weights")
def api_get_weights(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    weights = get_workspace_signal_weights(supabase, workspace_id)
    return {"status": "success", "weights": weights}


@router.post("/score")
def api_score_profile(
    req: ScoreRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not check_tier_access(workspace_id, 'bayesian_icp'):
        raise HTTPException(
            status_code=403,
            detail="Bayesian ICP Adaptive Weight Learning is a Growth Pro feature. Upgrade to unlock autonomous prospect scoring."
        )

    score, reasoning = compute_bayesian_icp_score(supabase, workspace_id, req.profile_data or {})
    return {"status": "success", "score": score, "reasoning": reasoning}
