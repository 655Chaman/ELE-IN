import re
import logging
from typing import Optional, Dict, Any, List, Union
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.crm_attribution_service import (
    list_synced_accounts,
    upsert_synced_account,
    delete_synced_account,
    process_inbound_crm_event,
    calculate_deal_attribution,
    list_deal_attributions,
    export_crm_attributions_csv,
    get_crm_sync_telemetry
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm-sync", tags=["crm_sync_and_attribution"])


# Pydantic Schemas
class UpsertAccountPayload(BaseModel):
    domain: str = Field(..., description="Target company root domain")
    company_name: str = Field(..., description="Account company name")
    crm_provider: Optional[str] = Field("hubspot", description="hubspot, salesforce, pipedrive, zoho, or custom")
    crm_company_id: Optional[str] = Field("hs-default", description="Foreign CRM Account ID")
    lifecycle_stage: Optional[str] = Field("lead", description="Current lifecycle stage in CRM")


class InboundWebhookPayload(BaseModel):
    event_type: str = Field(..., description="CRM webhook event identifier (e.g. deal.stage_change)")
    payload: Dict[str, Any] = Field(..., description="Raw CRM webhook payload")


class TouchpointItem(BaseModel):
    channel: str
    campaign: Optional[str] = None
    step: Optional[int] = 1


class CalculateAttributionPayload(BaseModel):
    deal_id: str = Field(..., max_length=255, description="CRM deal ID")
    deal_name: str = Field(..., max_length=255, description="Deal title / name")
    deal_amount: float = Field(..., description="Total deal value in USD")
    touchpoints: List[Union[TouchpointItem, Dict[str, Any]]] = Field(default_factory=list, description="List of recorded touches across campaigns")
    model: Optional[str] = Field("w_shaped", max_length=50, description="first_touch, last_touch, linear, or w_shaped")


@router.get("/accounts")
def get_accounts_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Retrieves all mapped CRM accounts with synchronization and lifecycle stages.
    """
    try:
        accounts = list_synced_accounts(workspace_id=workspace_id, supabase=supabase)
        return {
            "success": True,
            "data": accounts,
            "count": len(accounts)
        }
    except Exception as e:
        logger.exception("Failed to retrieve synced CRM accounts: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts")
def upsert_account_endpoint(
    payload: UpsertAccountPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Creates or updates an account-level CRM mapping link.
    """
    try:
        acc = upsert_synced_account(
            workspace_id=workspace_id,
            domain=payload.domain,
            company_name=payload.company_name,
            crm_provider=payload.crm_provider or "hubspot",
            crm_company_id=payload.crm_company_id or "hs-default",
            lifecycle_stage=payload.lifecycle_stage or "lead",
            supabase=supabase
        )
        return {
            "success": True,
            "data": acc,
            "message": f"Successfully mapped account '{acc.get('company_name')}' to {acc.get('crm_provider')}."
        }
    except Exception as e:
        logger.exception("Failed to upsert CRM account: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/accounts/{account_id}")
def delete_account_endpoint(
    account_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Unlinks a mapped CRM account with strict tenant isolation.
    """
    try:
        res = delete_synced_account(workspace_id=workspace_id, account_id=account_id, supabase=supabase)
        return {
            "success": True,
            "data": res
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Failed to delete CRM account: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook-inbound")
def webhook_inbound_endpoint(
    payload: InboundWebhookPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Ingests inbound CRM webhooks with echo-loop debouncing and automatic campaign halting.
    """
    try:
        result = process_inbound_crm_event(
            event_type=payload.event_type,
            payload=payload.payload,
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.exception("Failed to process inbound CRM webhook: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate-attribution")
def calculate_attribution_endpoint(
    payload: CalculateAttributionPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Calculates multi-touch revenue attribution across campaigns and marketing touches.
    """
    try:
        clean_tps = [
            tp.dict() if hasattr(tp, "dict") else (tp.model_dump() if hasattr(tp, "model_dump") else (dict(tp) if isinstance(tp, dict) else {"channel": str(tp)}))
            for tp in (payload.touchpoints or [])
        ]
        record = calculate_deal_attribution(
            deal_id=payload.deal_id,
            deal_name=payload.deal_name,
            deal_amount=max(0.0, float(payload.deal_amount or 0.0)),
            touchpoints=clean_tps,
            model=payload.model or "w_shaped",
            workspace_id=workspace_id,
            supabase=supabase
        )
        return {
            "success": True,
            "data": record
        }
    except Exception as e:
        logger.exception("Failed to compute deal attribution: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attributions")
def get_attributions_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Lists deal revenue attributions for the workspace.
    """
    try:
        deals = list_deal_attributions(workspace_id=workspace_id, supabase=supabase)
        return {
            "success": True,
            "data": deals,
            "count": len(deals)
        }
    except Exception as e:
        logger.exception("Failed to list deal attributions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attributions/export-csv")
def export_attributions_csv_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Streams deal revenue attributions and touchpoint credit weights as a sanitized CSV download.
    """
    try:
        csv_content = export_crm_attributions_csv(workspace_id=workspace_id, supabase=supabase)
        clean_ws_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", workspace_id)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="crm_attributions_{clean_ws_id}.csv"'}
        )
    except Exception as e:
        logger.exception("Failed to export CRM attributions CSV: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
def get_telemetry_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase=Depends(get_service_client)
):
    """
    Returns aggregate CRM sync telemetry, attributed ARR, and echo prevention stats.
    """
    try:
        telemetry = get_crm_sync_telemetry(workspace_id=workspace_id, supabase=supabase)
        return {
            "success": True,
            "data": telemetry
        }
    except Exception as e:
        logger.exception("Failed to get CRM sync telemetry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
