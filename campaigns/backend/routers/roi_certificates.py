"""
roi_certificates.py — FastAPI Router for Campaign ROI Achievement Certificates & Performance Cards
Provides authenticated endpoints for campaign managers to generate, customize, and manage
viral performance cards, plus a public unauthenticated verification endpoint.

Built rigorously under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Response
from pydantic import BaseModel, Field
from supabase import Client

from core.backend.api.auth_dep import get_supabase_client, get_current_workspace, get_service_client
from campaigns.backend.services.roi_certificate_service import (
    mint_campaign_roi_certificate,
    get_campaign_roi_certificate,
    update_certificate_privacy_settings,
    verify_public_certificate_token,
    export_roi_certificate_csv
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["roi-certificates"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class GenerateCertificateRequest(BaseModel):
    custom_deal_size: Optional[float] = Field(default=None, ge=1.0, le=1000000.0, description="Optional custom ACV deal size in USD per booked meeting")
    mask_pii: Optional[bool] = Field(default=True, description="Whether to mask lead names, emails, and company names")
    is_public: Optional[bool] = Field(default=True, description="Whether certificate can be verified on public endpoint")


class UpdatePrivacySettingsRequest(BaseModel):
    mask_pii: Optional[bool] = Field(default=None, description="Toggle PII masking on certificate preview")
    is_public: Optional[bool] = Field(default=None, description="Toggle public access for verification token")


# ─────────────────────────────────────────────────────────────────────────────
# Authenticated Endpoints (Workspace Member Access)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/campaigns/{campaign_id}/roi-certificate/generate", response_model=Dict[str, Any])
def generate_roi_certificate_endpoint(
    campaign_id: str = Path(..., description="ID of target campaign"),
    body: Optional[GenerateCertificateRequest] = None,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0: Mints or refreshes a cryptographically verified ROI Achievement Certificate.
    Computes conversion rates, SDR time savings, pipeline value, and tier badges.
    """
    req = body or GenerateCertificateRequest()
    try:
        cert = mint_campaign_roi_certificate(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase,
            custom_deal_size=req.custom_deal_size,
            mask_pii=req.mask_pii if req.mask_pii is not None else True,
            is_public=req.is_public if req.is_public is not None else True
        )
        return cert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating ROI certificate for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate campaign ROI certificate.")


@router.get("/api/campaigns/{campaign_id}/roi-certificate", response_model=Dict[str, Any])
def get_roi_certificate_endpoint(
    campaign_id: str = Path(..., description="ID of target campaign"),
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0: Retrieves the existing ROI Achievement Certificate for a campaign.
    If none exists yet, automatically mints one.
    """
    try:
        return get_campaign_roi_certificate(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching ROI certificate for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch campaign ROI certificate.")


@router.patch("/api/campaigns/{campaign_id}/roi-certificate/settings", response_model=Dict[str, Any])
def update_certificate_privacy_endpoint(
    campaign_id: str = Path(..., description="ID of target campaign"),
    body: UpdatePrivacySettingsRequest = ...,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 2: Allows campaign operators to toggle PII masking (public safe mode vs internal ops view)
    and public verification sharing.
    """
    try:
        return update_certificate_privacy_settings(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase,
            mask_pii=body.mask_pii,
            is_public=body.is_public
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating certificate privacy for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update certificate privacy settings.")


@router.get("/api/campaigns/{campaign_id}/roi-certificate/export-csv")
def export_roi_certificate_csv_endpoint(
    campaign_id: str = Path(..., description="ID of target campaign"),
    mask_pii: bool = Query(default=True, description="Whether to mask PII in exported CSV"),
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Layer 0 & Layer 2: Exports the campaign ROI certificate telemetry and sample converted leads
    as a sanitized CSV download.
    """
    try:
        csv_content = export_roi_certificate_csv(
            campaign_id=campaign_id,
            workspace_id=workspace_id,
            supabase=supabase,
            mask_pii=mask_pii
        )
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="elein-roi-certificate-{campaign_id[:16]}.csv"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting ROI certificate CSV for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to export campaign ROI certificate CSV.")


# ─────────────────────────────────────────────────────────────────────────────
# Public Unauthenticated Verification Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/public/verify-certificate/{token}", response_model=Dict[str, Any])
def public_verify_certificate_endpoint(
    token: str = Path(..., description="Cryptographic certificate verification token e.g. ELEIN-CERT-A3F9-82E1"),
    supabase: Client = Depends(get_service_client)
):
    """
    Public verification endpoint (No login required).
    Validates token integrity, authenticates HMAC-SHA256 signature, and provides
    tamper-proof proof of performance.
    """
    try:
        return verify_public_certificate_token(
            token=token,
            supabase=supabase
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during public certificate verification for token {token}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Verification system encountered an unexpected error.")
