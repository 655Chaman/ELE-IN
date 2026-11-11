"""
waitlist.py
===========
FastAPI router for Ele-in Waitlist management.
Public submission, status lookup, and administrative lead oversight.
Built under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import io
import csv
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.backend.core.security import limiter
from core.backend.api.rate_limit import get_client_ip
from core.backend.services.waitlist_service import waitlist_service
from core.backend.api.auth_dep import get_current_user_id

logger = logging.getLogger("elein.api.waitlist")

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


# ─── Pydantic Request Schemas ───

class WaitlistSubmissionRequest(BaseModel):
    email: str = Field(..., description="Lead work or business email address")
    full_name: str = Field(..., min_length=1, max_length=120, description="Applicant full name")
    company: Optional[str] = Field(None, max_length=120, description="Company name")
    role: Optional[str] = Field(None, max_length=100, description="Current role or title")
    linkedin_url: Optional[str] = Field(None, max_length=250, description="LinkedIn profile or company URL")
    team_size: Optional[str] = Field(None, max_length=50, description="Sales/GTM team size bracket")
    monthly_outbound_volume: Optional[str] = Field(None, max_length=50, description="Expected monthly outreach volume")
    primary_channel: Optional[str] = Field(None, max_length=80, description="Target outbound channel")
    referred_by_code: Optional[str] = Field(None, max_length=30, description="Referral code if invited")
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    # Paranoia Layer 2: Invisible Honeypot Trap
    hp_website_security: Optional[str] = Field(None, description="Honeypot field - must be left empty by humans")


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: pending, approved, invited, rejected")


# ─── Public Endpoints ───

@router.post("", summary="Join the Ele-in Priority Waitlist")
@limiter.limit("20/minute")
async def join_waitlist(payload: WaitlistSubmissionRequest, request: Request):
    """
    Submits an applicant to the Ele-in waitlist.
    Returns calculated queue position, referral code, and sharing metrics.
    """
    client_ip = get_client_ip(request)
    try:
        result = waitlist_service.submit_lead(
            email=payload.email,
            full_name=payload.full_name,
            company=payload.company,
            role=payload.role,
            linkedin_url=payload.linkedin_url,
            team_size=payload.team_size,
            monthly_outbound_volume=payload.monthly_outbound_volume,
            primary_channel=payload.primary_channel,
            referred_by_code=payload.referred_by_code,
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            client_ip=client_ip,
            honeypot_value=payload.hp_website_security,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[Waitlist] Unexpected failure during join_waitlist: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while securing your spot on the waitlist. Please try again."
        )


@router.get("/status", summary="Check Queue Position by Email or Referral Code")
@limiter.limit("60/minute")
async def check_status(
    request: Request,
    q: str = Query(..., min_length=2, max_length=150, description="Email address or referral code")
):
    """
    Looks up existing waitlist entry and returns real-time queue position and referral metrics.
    """
    lead = waitlist_service.get_lead_status(q)
    if not lead:
        raise HTTPException(status_code=404, detail="No waitlist entry found for the provided information.")
    return lead


@router.get("/stats", summary="Public Waitlist Aggregate Statistics")
@limiter.limit("120/minute")
async def public_stats(request: Request):
    """
    Returns public aggregate metrics (total waiting count, active waves) for social proof.
    """
    return waitlist_service.get_public_stats()


# ─── Admin Endpoints (Protected) ───

@router.get("/admin/leads", summary="List Waitlist Leads (Admin)")
async def admin_list_leads(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("all"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id)
):
    """
    Administrative list of waitlist entrants with search and pagination.
    """
    return waitlist_service.list_leads_admin(
        search=search,
        status_filter=status,
        limit=limit,
        offset=offset
    )


@router.patch("/admin/leads/{lead_id}", summary="Update Lead Status (Admin)")
async def admin_update_lead(
    lead_id: str,
    payload: UpdateStatusRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Updates the approval/onboarding status of a lead.
    """
    try:
        success = waitlist_service.update_lead_status_admin(lead_id, payload.status)
        if not success:
            raise HTTPException(status_code=404, detail="Lead not found or update failed.")
        return {"status": "success", "message": f"Lead status updated to {payload.status}"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/admin/export.csv", summary="Export Waitlist as CSV (Admin)")
async def admin_export_csv(
    user_id: str = Depends(get_current_user_id)
):
    """
    Streams a CSV file containing all waitlist signups for GTM campaign export.
    """
    data = waitlist_service.list_leads_admin(limit=10000, offset=0)
    entries = data.get("entries", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Full Name", "Email", "Company", "Role", "LinkedIn URL",
        "Team Size", "Monthly Volume", "Primary Channel", "Referral Code",
        "Referred By", "Referrals Count", "Priority Score", "Status",
        "UTM Source", "Created At"
    ])

    for row in entries:
        writer.writerow([
            row.get("computed_rank", ""),
            row.get("full_name", ""),
            row.get("email", ""),
            row.get("company", ""),
            row.get("role", ""),
            row.get("linkedin_url", ""),
            row.get("team_size", ""),
            row.get("monthly_outbound_volume", ""),
            row.get("primary_channel", ""),
            row.get("referral_code", ""),
            row.get("referred_by_code", ""),
            row.get("referrals_count", 0),
            row.get("priority_score", 0),
            row.get("status", "pending"),
            row.get("utm_source", ""),
            row.get("created_at", "")
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="elein_waitlist_export.csv"'}
    )
