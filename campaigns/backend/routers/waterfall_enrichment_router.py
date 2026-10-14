import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.backend.api.auth_dep import get_current_workspace, get_service_client
from core.backend.services.credit_service import check_tier_access, get_credit_balance, check_overdraft_allowance
from campaigns.backend.services.waterfall_enrichment_service import (
    execute_waterfall_enrichment,
    list_waterfall_runs,
    get_vendor_configs,
    get_waterfall_telemetry
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/waterfall", tags=["waterfall_enrichment"])


# Pydantic Models
class EnrichSinglePayload(BaseModel):
    lead_name: str = Field(..., description="Lead full name")
    company_domain: str = Field(..., description="Company domain or website URL")
    custom_sequence: Optional[List[str]] = None


class LeadItem(BaseModel):
    name: str
    domain: str


class EnrichBatchPayload(BaseModel):
    leads: List[LeadItem]
    custom_sequence: Optional[List[str]] = None


@router.post("/enrich-single")
def enrich_single_endpoint(
    payload: EnrichSinglePayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Executes a multi-vendor waterfall cascade for a single prospect.
    """
    # Paranoia Layer 0 & 2: Tier Gate (Pro/Enterprise requirement)
    if not check_tier_access(workspace_id, "enrichment", supabase_client=supabase):
        raise HTTPException(
            status_code=403,
            detail="Waterfall enrichment requires a Pro or Enterprise plan. Please upgrade your subscription."
        )

    # Paranoia Layer 0 & 1: Credit Preflight Check (aligned with tier-aware -500 overdraft buffer)
    balance = get_credit_balance(workspace_id, supabase_client=supabase)
    allowed, _, _ = check_overdraft_allowance(workspace_id, cost=5, supabase_client=supabase)
    if not allowed or balance < -495:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credit balance for waterfall enrichment. Please top up your credits in Billing."
        )

    try:
        run = execute_waterfall_enrichment(
            lead_name=payload.lead_name,
            company_domain=payload.company_domain,
            workspace_id=workspace_id,
            custom_sequence=payload.custom_sequence,
            supabase=supabase
        )
        return {
            "success": True,
            "data": run
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to execute single waterfall enrichment: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enrich-batch")
def enrich_batch_endpoint(
    payload: EnrichBatchPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Batch multi-vendor waterfall enrichment across multiple target prospects.
    """
    # Paranoia Layer 2: Empty payload handling
    if not payload.leads:
        return {
            "success": True,
            "results": [],
            "total_processed": 0,
            "matched_count": 0,
            "stopped_early": False
        }

    # Paranoia Layer 0 & 2: Tier Gate
    if not check_tier_access(workspace_id, "enrichment", supabase_client=supabase):
        raise HTTPException(
            status_code=403,
            detail="Waterfall enrichment requires a Pro or Enterprise plan. Please upgrade your subscription."
        )

    # Paranoia Layer 0 & 1: Credit Preflight Check
    balance = get_credit_balance(workspace_id, supabase_client=supabase)
    allowed, _, _ = check_overdraft_allowance(workspace_id, cost=5, supabase_client=supabase)
    if not allowed or balance < -495:
        raise HTTPException(
            status_code=402,
            detail="Insufficient credit balance for waterfall enrichment batch. Please top up your credits in Billing."
        )

    try:
        results = []
        stopped_early = False
        leads_to_process = payload.leads[:50]  # Limit 50 per batch

        for l in leads_to_process:
            # Paranoia Layer 1 & 2: Check balance mid-batch to halt before overdraft limit breach
            curr_balance = get_credit_balance(workspace_id, supabase_client=supabase)
            can_proceed, _, _ = check_overdraft_allowance(workspace_id, cost=5, supabase_client=supabase)
            if not can_proceed or curr_balance < -495:
                logger.warning(f"Batch enrichment halted mid-run for workspace {workspace_id} due to credit depletion.")
                stopped_early = True
                break

            r = execute_waterfall_enrichment(
                lead_name=l.name,
                company_domain=l.domain,
                workspace_id=workspace_id,
                custom_sequence=payload.custom_sequence,
                supabase=supabase
            )
            results.append(r)

        return {
            "success": True,
            "results": results,
            "total_processed": len(results),
            "matched_count": sum(1 for r in results if r.get("resolved_email")),
            "stopped_early": stopped_early
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to execute batch waterfall enrichment: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
def get_runs_endpoint(
    status: Optional[str] = None,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Lists historical waterfall runs with deliverability status filtering.
    """
    try:
        runs = list_waterfall_runs(workspace_id=workspace_id, supabase=supabase, status_filter=status)
        return {
            "success": True,
            "runs": runs,
            "total": len(runs)
        }
    except Exception as e:
        logger.exception("Failed to retrieve waterfall runs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs")
def get_configs_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Returns available enrichment providers, priority orders, and cost per lookup.
    """
    try:
        configs = get_vendor_configs(workspace_id=workspace_id, supabase=supabase)
        return {
            "success": True,
            "configs": configs
        }
    except Exception as e:
        logger.exception("Failed to retrieve vendor configs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
def get_telemetry_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Aggregates overall match rate, lift % over single-vendor, and credits saved.
    """
    try:
        telemetry = get_waterfall_telemetry(workspace_id=workspace_id, supabase=supabase)
        return {
            "success": True,
            "telemetry": telemetry
        }
    except Exception as e:
        logger.exception("Failed to retrieve waterfall telemetry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
