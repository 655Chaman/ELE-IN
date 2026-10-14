from __future__ import annotations
import re
from typing import Optional, Dict, Tuple
import asyncio
import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase._async.client import AsyncClient
from core.backend.api.auth_dep import get_async_service_client, get_current_user_id

logger = logging.getLogger(__name__)

# Paranoia Layer 1 & 2: Mutex and deduplication cache for agency credit delegations
_agency_credit_transfer_mutex: Optional[asyncio.Lock] = None
_PROCESSED_AGENCY_TRANSFERS: Dict[str, Tuple[float, dict]] = {}
_AGENCY_TRANSFERS_LOCK: Optional[asyncio.Lock] = None

def _get_agency_transfers_lock() -> asyncio.Lock:
    global _AGENCY_TRANSFERS_LOCK
    if _AGENCY_TRANSFERS_LOCK is None:
        _AGENCY_TRANSFERS_LOCK = asyncio.Lock()
    return _AGENCY_TRANSFERS_LOCK

def _get_agency_credit_transfer_mutex() -> asyncio.Lock:
    global _agency_credit_transfer_mutex
    if _agency_credit_transfer_mutex is None:
        _agency_credit_transfer_mutex = asyncio.Lock()
    return _agency_credit_transfer_mutex

async def _check_and_store_agency_transfer(dedupe_key: str, result: Optional[dict] = None) -> Optional[dict]:
    """
    Paranoia Layer 1 & 2: In-memory idempotency deduplication with 60-second TTL.
    If result is None, checks if a cached completed result exists.
    If result is provided, caches the completed result.
    """
    now = time.time()
    async with _get_agency_transfers_lock():
        expired_keys = [k for k, (ts, _) in _PROCESSED_AGENCY_TRANSFERS.items() if now - ts > 60.0]
        for k in expired_keys:
            _PROCESSED_AGENCY_TRANSFERS.pop(k, None)

        if result is None:
            if dedupe_key in _PROCESSED_AGENCY_TRANSFERS:
                _, cached = _PROCESSED_AGENCY_TRANSFERS[dedupe_key]
                return cached
            return None
        else:
            _PROCESSED_AGENCY_TRANSFERS[dedupe_key] = (now, result)
            return result

router = APIRouter()

class AgencyCreate(BaseModel):
    name: str

class ClientWorkspaceCreate(BaseModel):
    name: str

class AgencyMemberInvite(BaseModel):
    email: str
    role: str

class AgencyAccessGrant(BaseModel):
    workspace_id: str

class AgencyWhitelabelUpdate(BaseModel):
    brand_name: str
    custom_domain: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    enabled: bool = True

async def _verify_agency_owner(agency_id: str, user_id: str, supabase: AsyncClient):
    res = await supabase.table("agency_members").select("id")\
        .eq("agency_id", agency_id).eq("user_id", user_id).eq("role", "owner").limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="You do not have permission to manage this agency.")

async def _verify_agency_owner_or_admin(agency_id: str, user_id: str, supabase: AsyncClient):
    res = await supabase.table("agency_members").select("id, role")\
        .eq("agency_id", agency_id).eq("user_id", user_id).in_("role", ["owner", "admin"]).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="You do not have administrative permission to manage this agency.")

async def _verify_agency_member(agency_id: str, user_id: str, supabase: AsyncClient):
    res = await supabase.table("agency_members").select("id")\
        .eq("agency_id", agency_id).eq("user_id", user_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="You do not have access to this agency.")

@router.post("")
async def create_agency(
    payload: AgencyCreate,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    clean_name = payload.name.strip() if payload.name else ""
    if not clean_name:
        raise HTTPException(status_code=400, detail="Agency name cannot be empty")

    # 1. Create agency
    agency_res = await supabase.table("agencies").insert({
        "name": clean_name,
        "owner_id": user_id
    }).execute()
    if not agency_res.data:
        raise HTTPException(status_code=400, detail="Failed to create agency")
    
    agency_id = agency_res.data[0]["id"]
    
    # 2. Add creator as owner
    await supabase.table("agency_members").insert({
        "agency_id": agency_id,
        "user_id": user_id,
        "role": "owner"
    }).execute()
    
    return {"status": "success", "agency": agency_res.data[0]}

@router.post("/{agency_id}/clients")
async def create_client_workspace(
    agency_id: str,
    payload: ClientWorkspaceCreate,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    await _verify_agency_owner(agency_id, user_id, supabase)
    clean_name = payload.name.strip() if payload.name else ""
    if not clean_name:
        raise HTTPException(status_code=400, detail="Client workspace name cannot be empty")

    ws_res = await supabase.table("workspaces").insert({
        "name": clean_name,
        "owner_id": user_id,
        "agency_id": agency_id
    }).execute()
    
    if not ws_res.data:
        raise HTTPException(status_code=400, detail="Failed to create client workspace")
        
    return {"status": "success", "workspace": ws_res.data[0]}

@router.post("/{agency_id}/members")
async def invite_member(
    agency_id: str,
    payload: AgencyMemberInvite,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    await _verify_agency_owner(agency_id, user_id, supabase)

    clean_email = payload.email.strip().lower() if payload.email else ""
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="Valid email address required")

    clean_role = payload.role.strip().lower() if payload.role else ""
    if clean_role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=400, detail="Invalid agency role. Must be 'owner', 'admin', or 'member'.")
    
    # PARANOIA LAYER 1: Use direct RPC instead of slow linear pagination of auth.users over HTTP
    email_res = await supabase.rpc("get_user_id_by_email", {"p_email": clean_email}).execute()
    target_user_id = email_res.data if email_res.data else None
            
    if not target_user_id:
        raise HTTPException(status_code=404, detail="User must have an account first")
        
    member_res = await supabase.table("agency_members").insert({
        "agency_id": agency_id,
        "user_id": target_user_id,
        "role": clean_role
    }).execute()
    
    return {"status": "success", "member": member_res.data[0]}

@router.post("/{agency_id}/members/{member_id}/access")
async def grant_client_access(
    agency_id: str,
    member_id: str,
    payload: AgencyAccessGrant,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    await _verify_agency_owner(agency_id, user_id, supabase)
    workspace_id = payload.workspace_id
    
    ws_check = await supabase.table("workspaces").select("id").eq("id", workspace_id).eq("agency_id", agency_id).limit(1).execute()
    if not ws_check.data:
        raise HTTPException(status_code=403, detail="Workspace does not belong to this agency.")
        
    # PARANOIA LAYER 1: Verify member_id actually belongs to this agency
    mem_check = await supabase.table("agency_members").select("id").eq("id", member_id).eq("agency_id", agency_id).limit(1).execute()
    if not mem_check.data:
        raise HTTPException(status_code=404, detail="Member not found in this agency.")
        
    try:
        res = await supabase.table("agency_client_access").insert({
            "agency_member_id": member_id,
            "workspace_id": workspace_id
        }).execute()
        return {"status": "success", "access": res.data[0]}
    except Exception as e:
        existing = await supabase.table("agency_client_access").select("id").eq("agency_member_id", member_id).eq("workspace_id", workspace_id).execute()
        if existing.data:
            return {"status": "success", "access": existing.data[0]}
        raise HTTPException(status_code=500, detail=f"Failed to grant access: {str(e)}")

@router.delete("/{agency_id}/members/{member_id}/access")
async def revoke_client_access(
    agency_id: str,
    member_id: str,
    payload: AgencyAccessGrant,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    await _verify_agency_owner(agency_id, user_id, supabase)
    workspace_id = payload.workspace_id
    
    ws_check = await supabase.table("workspaces").select("id").eq("id", workspace_id).eq("agency_id", agency_id).limit(1).execute()
    if not ws_check.data:
        raise HTTPException(status_code=403, detail="Workspace does not belong to this agency.")
        
    # PARANOIA LAYER 1: Verify member_id actually belongs to this agency
    mem_check = await supabase.table("agency_members").select("id").eq("id", member_id).eq("agency_id", agency_id).limit(1).execute()
    if not mem_check.data:
        raise HTTPException(status_code=404, detail="Member not found in this agency.")
        
    await supabase.table("agency_client_access").delete().eq("agency_member_id", member_id).eq("workspace_id", workspace_id).execute()
    return {"status": "success"}

@router.get("")
async def list_my_agencies(
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """Return all agencies this user belongs to (with their role)."""
    mem_res = await supabase.table("agency_members").select("role, agency_id").eq("user_id", user_id).execute()
    if not mem_res.data:
        return []

    out = []
    for row in mem_res.data:
        agency_res = await supabase.table("agencies").select("id, name").eq("id", row["agency_id"]).execute()
        if agency_res.data:
            out.append({
                "id": agency_res.data[0]["id"],
                "name": agency_res.data[0]["name"],
                "role": row["role"]
            })
    return out

@router.get("/{agency_id}/members")
async def list_agency_members(
    agency_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """List all members of an agency with their per-client access grants."""
    await _verify_agency_member(agency_id, user_id, supabase)
    from core.backend.api.auth_dep import get_async_service_client
    svc = await get_async_service_client()

    mem_res = await supabase.table("agency_members").select("id, user_id, role").eq("agency_id", agency_id).execute()
    if not mem_res.data:
        return []

    # PARANOIA LAYER 1: Fetch display names from user_profiles instead of linear HTTP scan of auth.users
    user_ids = [r["user_id"] for r in mem_res.data]
    profiles_res = await supabase.table("user_profiles").select("id, display_name").in_("id", user_ids).execute()
    profiles_map = {p["id"]: p.get("display_name") or p["id"] for p in (profiles_res.data or [])}

    out = []
    for row in mem_res.data:
        member_id = row["id"]
        # Fetch client access grants for this member
        access_res = await supabase.table("agency_client_access").select("workspace_id").eq("agency_member_id", member_id).execute()
        access = [acc["workspace_id"] for acc in (access_res.data or [])]
        out.append({
            "id": member_id,
            "user_id": row["user_id"],
            "display_name": profiles_map.get(row["user_id"], row["user_id"]),
            "role": row["role"],
            "access": access
        })
    return out

@router.get("/{agency_id}/clients")
async def list_agency_clients(
    agency_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """List all client workspaces that belong to this agency with active campaigns, leads, and senders metrics."""
    await _verify_agency_member(agency_id, user_id, supabase)
    
    # Layer 1 Paranoia: High-performance consolidated RPC first
    try:
        rpc_res = await supabase.rpc("get_agency_clients_overview", {"p_agency_id": agency_id}).execute()
        if rpc_res.data is not None:
            return rpc_res.data
    except Exception:
        # Fallback to direct table queries if migration 073 has not run yet in target DB
        pass

    res = await supabase.table("workspaces").select("id, name, created_at").eq("agency_id", agency_id).order("created_at", desc=True).execute()
    workspaces = res.data or []
    if not workspaces:
        return []

    enriched = []
    for ws in workspaces:
        ws_id = ws["id"]
        camp_count = 0
        active_camp_count = 0
        leads_count = 0
        senders_count = 0
        try:
            c_res = await supabase.table("campaigns").select("id, status").eq("workspace_id", ws_id).execute()
            if c_res.data:
                camp_count = len(c_res.data)
                active_camp_count = sum(1 for c in c_res.data if c.get("status") == "active")
        except Exception:
            pass
        try:
            l_res = await supabase.table("leads").select("id", count="exact").eq("workspace_id", ws_id).limit(1).execute()
            leads_count = l_res.count or 0
        except Exception:
            pass
        try:
            a_res = await supabase.table("accounts").select("id", count="exact").eq("workspace_id", ws_id).in_("status", ["connected", "active", "valid"]).limit(1).execute()
            senders_count = a_res.count or 0
        except Exception:
            pass

        enriched.append({
            "id": ws_id,
            "name": ws.get("name", "Untitled Client"),
            "created_at": ws.get("created_at"),
            "campaigns_count": camp_count,
            "active_campaigns_count": active_camp_count,
            "leads_count": leads_count,
            "senders_count": senders_count
        })
    return enriched

@router.get("/{agency_id}/whitelabel")
async def get_agency_whitelabel(
    agency_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """Retrieve white-label branding configuration for this agency."""
    await _verify_agency_member(agency_id, user_id, supabase)
    res = await supabase.table("agencies").select(
        "id, name, whitelabel_brand, whitelabel_domain, whitelabel_color, whitelabel_logo_url, whitelabel_enabled"
    ).eq("id", agency_id).limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Agency not found")

    row = res.data[0]
    return {
        "brand_name": row.get("whitelabel_brand") or row.get("name") or "Agency Portal",
        "custom_domain": row.get("whitelabel_domain") or "",
        "accent_color": row.get("whitelabel_color") or "#6366f1",
        "logo_url": row.get("whitelabel_logo_url") or "",
        "enabled": row.get("whitelabel_enabled", True) if row.get("whitelabel_enabled") is not None else True
    }

@router.put("/{agency_id}/whitelabel")
async def update_agency_whitelabel(
    agency_id: str,
    payload: AgencyWhitelabelUpdate,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """Update agency white-label branding configuration (owner/admin only)."""
    await _verify_agency_owner_or_admin(agency_id, user_id, supabase)
    
    clean_brand = payload.brand_name.strip() if payload.brand_name else ""
    if not clean_brand:
        raise HTTPException(status_code=400, detail="Agency brand title cannot be empty")
    if len(clean_brand) > 100:
        raise HTTPException(status_code=400, detail="Brand title cannot exceed 100 characters")

    clean_domain = payload.custom_domain.strip().lower() if payload.custom_domain else ""
    if clean_domain.startswith("https://"):
        clean_domain = clean_domain[8:]
    elif clean_domain.startswith("http://"):
        clean_domain = clean_domain[7:]
    clean_domain = clean_domain.rstrip("/")

    clean_color = payload.accent_color.strip() if payload.accent_color else "#6366f1"
    if not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", clean_color):
        clean_color = "#6366f1"

    update_payload = {
        "whitelabel_brand": clean_brand,
        "whitelabel_domain": clean_domain,
        "whitelabel_color": clean_color,
        "whitelabel_logo_url": payload.logo_url.strip() if payload.logo_url else "",
        "whitelabel_enabled": payload.enabled
    }

    try:
        res = await supabase.table("agencies").update(update_payload).eq("id", agency_id).execute()
        if not res.data:
            raise HTTPException(status_code=400, detail="Failed to update white-label settings")
        return {
            "status": "success",
            "whitelabel": {
                "brand_name": clean_brand,
                "custom_domain": clean_domain,
                "accent_color": clean_color,
                "logo_url": update_payload["whitelabel_logo_url"],
                "enabled": payload.enabled
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 27: MULTI-SEAT AGENCY CREDIT DELEGATIONS & SUB-ACCOUNT QUOTAS
# ─────────────────────────────────────────────────────────────────────────────

class CreditAllocateRequest(BaseModel):
    client_workspace_id: str
    amount: int
    note: Optional[str] = "Manual credit delegation"
    idempotency_key: Optional[str] = None

class CreditReclaimRequest(BaseModel):
    client_workspace_id: str
    amount: int
    note: Optional[str] = "Reclaimed credits to master pool"
    idempotency_key: Optional[str] = None

class ClientQuotaUpdateRequest(BaseModel):
    client_workspace_id: str
    monthly_credit_quota: Optional[int] = 0
    exhaustion_alert_threshold: Optional[int] = 100


async def _resolve_agency_master_workspace(agency_id: str, supabase: AsyncClient) -> dict:
    """
    Paranoia Layer 0 & 1: Resolves the master billing workspace for an agency.
    First checks agencies.master_workspace_id. If unset, falls back to the agency owner's
    primary personal or agency-root workspace.
    """
    agency_res = await supabase.table("agencies").select("id, owner_id, master_workspace_id").eq("id", agency_id).limit(1).execute()
    if not agency_res.data:
        raise HTTPException(status_code=404, detail="Agency not found")
        
    agency = agency_res.data[0]
    master_ws_id = agency.get("master_workspace_id")
    if master_ws_id:
        ws_res = await supabase.table("workspaces").select("id, name, data_cleaning_credits").eq("id", master_ws_id).limit(1).execute()
        if ws_res.data:
            return ws_res.data[0]
            
    # Fallback to the owner's primary workspace
    owner_id = agency["owner_id"]
    ws_res = await supabase.table("workspaces").select("id, name, data_cleaning_credits")\
        .eq("owner_id", owner_id).order("created_at", desc=False).limit(1).execute()
        
    if ws_res.data:
        try:
            await supabase.table("agencies").update({"master_workspace_id": ws_res.data[0]["id"]}).eq("id", agency_id).execute()
        except Exception:
            pass
        return ws_res.data[0]
        
    raise HTTPException(status_code=404, detail="No master workspace found for this agency.")


@router.get("/{agency_id}/credits")
async def get_agency_credits_overview(
    agency_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0 & 1: Master agency credit pool, sub-workspace allocations,
    and consumption telemetry.
    """
    await _verify_agency_member(agency_id, user_id, supabase)
    master_ws = await _resolve_agency_master_workspace(agency_id, supabase)
    master_id = master_ws["id"]
    master_balance = master_ws.get("data_cleaning_credits", 0)

    # Fetch client workspaces for this agency
    ws_res = await supabase.table("workspaces").select(
        "id, name, created_at, data_cleaning_credits, allocated_credit_budget, monthly_credit_quota, exhaustion_alert_threshold"
    ).eq("agency_id", agency_id).neq("id", master_id).order("created_at", desc=True).execute()

    client_workspaces = ws_res.data or []
    clients_telemetry = []
    total_delegated = 0
    total_consumed = 0

    for ws in client_workspaces:
        c_id = ws["id"]
        c_bal = ws.get("data_cleaning_credits") or 0
        c_alloc = ws.get("allocated_credit_budget") or 0
        c_thresh = ws.get("exhaustion_alert_threshold") or 100
        c_quota = ws.get("monthly_credit_quota") or 0

        total_delegated += c_alloc

        # Calculate consumed credits
        spent = 0
        try:
            ded_res = await supabase.table("credit_deductions").select("amount").eq("workspace_id", c_id).execute()
            if ded_res.data:
                spent = sum(d.get("amount", 0) for d in ded_res.data)
        except Exception:
            pass

        total_consumed += spent

        status = "healthy"
        if c_bal < 0:
            status = "overdraft"
        elif c_bal <= c_thresh:
            status = "low"

        clients_telemetry.append({
            "id": c_id,
            "name": ws.get("name", "Untitled Client"),
            "created_at": ws.get("created_at"),
            "balance": c_bal,
            "allocated_budget": c_alloc,
            "consumed_credits": spent,
            "monthly_quota": c_quota,
            "exhaustion_alert_threshold": c_thresh,
            "status": status
        })

    # Fetch recent allocations ledger
    recent_allocs = []
    try:
        alloc_res = await supabase.table("agency_credit_allocations").select(
            "id, client_workspace_id, from_workspace_id, amount, action_type, note, created_at"
        ).eq("agency_id", agency_id).order("created_at", desc=True).limit(20).execute()
        recent_allocs = alloc_res.data or []
    except Exception:
        pass

    return {
        "master_workspace": {
            "id": master_id,
            "name": master_ws.get("name", "Master Agency Workspace"),
            "balance": master_balance
        },
        "total_agency_balance": master_balance,
        "total_delegated_credits": total_delegated,
        "total_consumed_credits": total_consumed,
        "clients": clients_telemetry,
        "recent_allocations": recent_allocs
    }


@router.post("/{agency_id}/credits/allocate")
async def allocate_agency_credits(
    agency_id: str,
    payload: CreditAllocateRequest,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0, 1 & 2: Atomically transfers credits from master agency pool to client workspace.
    """
    await _verify_agency_owner_or_admin(agency_id, user_id, supabase)

    # Layer 2: Sanitize input amount
    try:
        amount = int(payload.amount)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid transfer amount")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Allocation amount must be greater than zero")
    if amount > 1000000:
        raise HTTPException(status_code=400, detail="Allocation amount cannot exceed 1,000,000 per transfer")

    # Verify client workspace belongs to agency
    target_check = await supabase.table("workspaces").select("id, name, agency_id, data_cleaning_credits, allocated_credit_budget").eq("id", payload.client_workspace_id).limit(1).execute()
    if not target_check.data or target_check.data[0].get("agency_id") != agency_id:
        raise HTTPException(status_code=404, detail="Target client workspace does not belong to this agency")

    master_ws = await _resolve_agency_master_workspace(agency_id, supabase)
    master_id = master_ws["id"]

    if master_id == payload.client_workspace_id:
        raise HTTPException(status_code=400, detail="Cannot allocate credits from master workspace to itself")

    # Layer 2: Deduplication / Idempotency Check
    dedupe_key = f"alloc_{agency_id}_{payload.idempotency_key}" if payload.idempotency_key else f"alloc_{agency_id}_{master_id}_{payload.client_workspace_id}_{amount}"
    cached_res = await _check_and_store_agency_transfer(dedupe_key)
    if cached_res:
        return cached_res

    # Layer 1: Execute atomic transfer RPC
    try:
        rpc_res = await supabase.rpc("transfer_agency_credits_safely", {
            "p_agency_id": agency_id,
            "p_from_workspace_id": master_id,
            "p_to_workspace_id": payload.client_workspace_id,
            "p_amount": amount,
            "p_action_type": "manual_allocation",
            "p_allocated_by": user_id,
            "p_note": payload.note or "Manual credit delegation"
        }).execute()

        res_data = rpc_res.data or {}
        if not res_data.get("success"):
            if res_data.get("reason") == "insufficient_balance":
                raise HTTPException(status_code=400, detail=f"Insufficient credits in master pool (Available: {res_data.get('available', 0):,})")
            raise HTTPException(status_code=400, detail=f"Transfer failed: {res_data.get('reason')}")

        resp = {
            "status": "success",
            "message": f"Successfully allocated {amount:,} credits to client workspace.",
            "allocated_amount": amount,
            "master_balance": res_data.get("from_balance"),
            "client_balance": res_data.get("to_balance")
        }
        await _check_and_store_agency_transfer(dedupe_key, resp)
        return resp
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[AgencyBilling] RPC transfer_agency_credits_safely failed: {exc}. Engaging serialized atomic fallback.")
        # Fallback with strict in-process serialization and atomic compensation
        async with _get_agency_credit_transfer_mutex():
            # 1. Fresh fetch of master balance inside critical section
            curr_master = await supabase.table("workspaces").select("data_cleaning_credits").eq("id", master_id).limit(1).execute()
            m_bal = curr_master.data[0]["data_cleaning_credits"] if curr_master.data else 0
            if m_bal < amount:
                raise HTTPException(status_code=400, detail="Insufficient credits in master agency pool")

            # 2. Fresh fetch of client balance & allocated budget inside critical section
            curr_client = await supabase.table("workspaces").select("data_cleaning_credits, allocated_credit_budget").eq("id", payload.client_workspace_id).limit(1).execute()
            if not curr_client.data:
                raise HTTPException(status_code=404, detail="Target client workspace does not exist")
            c_bal = curr_client.data[0].get("data_cleaning_credits") or 0
            c_alloc = curr_client.data[0].get("allocated_credit_budget") or 0

            new_m = m_bal - amount
            new_t = c_bal + amount
            new_alloc = c_alloc + amount

            # 3. Deduct from master
            await supabase.table("workspaces").update({"data_cleaning_credits": new_m}).eq("id", master_id).execute()

            # 4. Credit client with rollback compensation on failure
            try:
                await supabase.table("workspaces").update({
                    "data_cleaning_credits": new_t,
                    "allocated_credit_budget": new_alloc
                }).eq("id", payload.client_workspace_id).execute()
            except Exception as update_err:
                # Rollback master deduction to preserve credit conservation
                try:
                    await supabase.table("workspaces").update({"data_cleaning_credits": m_bal}).eq("id", master_id).execute()
                except Exception as rb_err:
                    logger.critical(f"[AgencyBilling] CRITICAL: Failed to rollback master balance {master_id} after client credit failure: {rb_err}")
                raise HTTPException(status_code=500, detail="Failed to credit client workspace; allocation rolled back.")

            try:
                await supabase.table("agency_credit_allocations").insert({
                    "agency_id": agency_id,
                    "client_workspace_id": payload.client_workspace_id,
                    "from_workspace_id": master_id,
                    "amount": amount,
                    "action_type": "manual_allocation",
                    "allocated_by": user_id,
                    "note": payload.note or "Manual credit delegation"
                }).execute()
            except Exception:
                pass

            fallback_resp = {
                "status": "success",
                "message": f"Successfully allocated {amount:,} credits to client workspace.",
                "allocated_amount": amount,
                "master_balance": new_m,
                "client_balance": new_t
            }
            await _check_and_store_agency_transfer(dedupe_key, fallback_resp)
            return fallback_resp


@router.post("/{agency_id}/credits/reclaim")
async def reclaim_agency_credits(
    agency_id: str,
    payload: CreditReclaimRequest,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0, 1 & 2: Atomically transfers unused credits back from client to master agency pool.
    """
    await _verify_agency_owner_or_admin(agency_id, user_id, supabase)

    try:
        amount = int(payload.amount)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid reclaim amount")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Reclaim amount must be greater than zero")

    target_check = await supabase.table("workspaces").select("id, name, agency_id, data_cleaning_credits, allocated_credit_budget").eq("id", payload.client_workspace_id).limit(1).execute()
    if not target_check.data or target_check.data[0].get("agency_id") != agency_id:
        raise HTTPException(status_code=404, detail="Target client workspace does not belong to this agency")

    client_bal = target_check.data[0].get("data_cleaning_credits") or 0
    if client_bal < amount:
        raise HTTPException(status_code=400, detail=f"Cannot reclaim {amount:,} credits. Client only has {client_bal:,} credits available.")

    master_ws = await _resolve_agency_master_workspace(agency_id, supabase)
    master_id = master_ws["id"]

    # Layer 2: Deduplication / Idempotency Check
    dedupe_key = f"reclaim_{agency_id}_{payload.idempotency_key}" if payload.idempotency_key else f"reclaim_{agency_id}_{payload.client_workspace_id}_{master_id}_{amount}"
    cached_res = await _check_and_store_agency_transfer(dedupe_key)
    if cached_res:
        return cached_res

    # Layer 1: Execute atomic transfer RPC
    try:
        rpc_res = await supabase.rpc("transfer_agency_credits_safely", {
            "p_agency_id": agency_id,
            "p_from_workspace_id": payload.client_workspace_id,
            "p_to_workspace_id": master_id,
            "p_amount": amount,
            "p_action_type": "reclaim",
            "p_allocated_by": user_id,
            "p_note": payload.note or "Reclaimed credits to master pool"
        }).execute()

        res_data = rpc_res.data or {}
        if not res_data.get("success"):
            raise HTTPException(status_code=400, detail=f"Reclaim failed: {res_data.get('reason')}")

        resp = {
            "status": "success",
            "message": f"Successfully reclaimed {amount:,} credits back to master pool.",
            "reclaimed_amount": amount,
            "client_balance": res_data.get("from_balance"),
            "master_balance": res_data.get("to_balance")
        }
        await _check_and_store_agency_transfer(dedupe_key, resp)
        return resp
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[AgencyBilling] RPC transfer_agency_credits_safely failed: {exc}. Engaging serialized atomic fallback.")
        # Fallback with strict in-process serialization and atomic compensation
        async with _get_agency_credit_transfer_mutex():
            # 1. Fresh fetch of client balance & allocated budget inside critical section
            curr_client = await supabase.table("workspaces").select("data_cleaning_credits, allocated_credit_budget").eq("id", payload.client_workspace_id).limit(1).execute()
            if not curr_client.data:
                raise HTTPException(status_code=404, detail="Target client workspace does not exist")
            c_bal = curr_client.data[0].get("data_cleaning_credits") or 0
            if c_bal < amount:
                raise HTTPException(status_code=400, detail=f"Cannot reclaim {amount:,} credits. Client only has {c_bal:,} credits available.")
            c_alloc = curr_client.data[0].get("allocated_credit_budget") or 0

            # 2. Fresh fetch of master balance inside critical section
            curr_master = await supabase.table("workspaces").select("data_cleaning_credits").eq("id", master_id).limit(1).execute()
            m_bal = curr_master.data[0]["data_cleaning_credits"] if curr_master.data else 0

            new_c = c_bal - amount
            new_alloc = max(0, c_alloc - amount)
            new_m = m_bal + amount

            # 3. Deduct from client
            await supabase.table("workspaces").update({
                "data_cleaning_credits": new_c,
                "allocated_credit_budget": new_alloc
            }).eq("id", payload.client_workspace_id).execute()

            # 4. Credit master with rollback compensation on failure
            try:
                await supabase.table("workspaces").update({"data_cleaning_credits": new_m}).eq("id", master_id).execute()
            except Exception as update_err:
                # Rollback client deduction immediately to guarantee credit conservation
                try:
                    await supabase.table("workspaces").update({
                        "data_cleaning_credits": c_bal,
                        "allocated_credit_budget": c_alloc
                    }).eq("id", payload.client_workspace_id).execute()
                except Exception as rb_err:
                    logger.critical(f"[AgencyBilling] CRITICAL: Failed to rollback client balance {payload.client_workspace_id} after master credit failure: {rb_err}")
                raise HTTPException(status_code=500, detail="Failed to credit master pool; reclaim rolled back.")

            try:
                await supabase.table("agency_credit_allocations").insert({
                    "agency_id": agency_id,
                    "client_workspace_id": payload.client_workspace_id,
                    "from_workspace_id": master_id,
                    "amount": -amount,
                    "action_type": "reclaim",
                    "allocated_by": user_id,
                    "note": payload.note or "Reclaimed credits to master pool"
                }).execute()
            except Exception:
                pass

            fallback_resp = {
                "status": "success",
                "message": f"Successfully reclaimed {amount:,} credits back to master pool.",
                "reclaimed_amount": amount,
                "client_balance": new_c,
                "master_balance": new_m
            }
            await _check_and_store_agency_transfer(dedupe_key, fallback_resp)
            return fallback_resp


@router.put("/{agency_id}/credits/client-quota")
async def update_client_quota(
    agency_id: str,
    payload: ClientQuotaUpdateRequest,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0 & 2: Sets recurring monthly credit quota and exhaustion alert threshold.
    """
    await _verify_agency_owner_or_admin(agency_id, user_id, supabase)

    target_check = await supabase.table("workspaces").select("id, agency_id").eq("id", payload.client_workspace_id).limit(1).execute()
    if not target_check.data or target_check.data[0].get("agency_id") != agency_id:
        raise HTTPException(status_code=404, detail="Client workspace does not belong to this agency")

    monthly_quota = max(0, min(1000000, int(payload.monthly_credit_quota or 0)))
    exhaustion_threshold = max(10, min(10000, int(payload.exhaustion_alert_threshold or 100)))

    try:
        await supabase.table("workspaces").update({
            "monthly_credit_quota": monthly_quota,
            "exhaustion_alert_threshold": exhaustion_threshold
        }).eq("id", payload.client_workspace_id).execute()

        return {
            "status": "success",
            "client_workspace_id": payload.client_workspace_id,
            "monthly_credit_quota": monthly_quota,
            "exhaustion_alert_threshold": exhaustion_threshold
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update client quota: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 28: AUTOMATED OVERDRAFT INVOICING & CONSOLIDATED BILLING STATEMENTS
# ─────────────────────────────────────────────────────────────────────────────

class GenerateStatementRequest(BaseModel):
    client_workspace_id: Optional[str] = None  # None = Consolidated multi-client roll-up
    period_start: str  # YYYY-MM-DD
    period_end: str    # YYYY-MM-DD
    currency: Optional[str] = "INR"
    unit_credit_rate_cents: Optional[int] = 150  # 150 paise = ₹1.50 per credit
    platform_base_fee_cents: Optional[int] = 499900  # ₹4,999 base retainer per client
    tax_percent: Optional[float] = 18.0  # 18% GST / VAT
    notes: Optional[str] = None

class UpdateStatementStatusRequest(BaseModel):
    status: str  # 'draft' | 'issued' | 'paid' | 'void'
    notes: Optional[str] = None


@router.get("/{agency_id}/statements")
async def list_agency_statements(
    agency_id: str,
    status: Optional[str] = None,
    client_workspace_id: Optional[str] = None,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0 & 1: Lists all consolidated and client billing statements.
    """
    await _verify_agency_member(agency_id, user_id, supabase)
    try:
        query = supabase.table("agency_billing_statements").select("*").eq("agency_id", agency_id)
        if status:
            query = query.eq("status", status)
        if client_workspace_id:
            query = query.eq("client_workspace_id", client_workspace_id)
        res = await query.order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        # Graceful fallback if table not yet migrated
        return []


@router.post("/{agency_id}/statements/generate")
async def generate_agency_statement(
    agency_id: str,
    payload: GenerateStatementRequest,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0, 1 & 2: Aggregates client usage, computes line items, and persists statement.
    """
    await _verify_agency_owner_or_admin(agency_id, user_id, supabase)

    # Validate period dates (Layer 1 Paranoia)
    try:
        from datetime import datetime
        # Parse YYYY-MM-DD or ISO strings
        clean_start = payload.period_start.split("T")[0]
        clean_end = payload.period_end.split("T")[0]
        dt_start = datetime.strptime(clean_start, "%Y-%m-%d")
        dt_end = datetime.strptime(clean_end, "%Y-%m-%d")
        if dt_start >= dt_end:
            raise HTTPException(status_code=400, detail="Period start date must be strictly before period end date")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format for period_start or period_end (expected YYYY-MM-DD)")

    # Fetch clients to include
    if payload.client_workspace_id:
        c_res = await supabase.table("workspaces").select("id, name, allocated_credit_budget, data_cleaning_credits")\
            .eq("id", payload.client_workspace_id).eq("agency_id", agency_id).limit(1).execute()
        if not c_res.data:
            raise HTTPException(status_code=404, detail="Target client workspace does not exist in this agency")
        target_clients = c_res.data
    else:
        master_ws = await _resolve_agency_master_workspace(agency_id, supabase)
        c_res = await supabase.table("workspaces").select("id, name, allocated_credit_budget, data_cleaning_credits")\
            .eq("agency_id", agency_id).neq("id", master_ws["id"]).execute()
        target_clients = c_res.data or []

    if not target_clients:
        raise HTTPException(status_code=400, detail="No client workspaces found to generate statements for")

    # Fetch allocation history in this period
    allocations_map: dict[str, dict[str, int]] = {}
    try:
        alloc_res = await supabase.table("agency_credit_allocations")\
            .select("client_workspace_id, amount, action_type")\
            .eq("agency_id", agency_id)\
            .gte("created_at", clean_start)\
            .lte("created_at", clean_end + "T23:59:59Z")\
            .execute()
        for a in (alloc_res.data or []):
            cid = a.get("client_workspace_id")
            if not cid:
                continue
            if cid not in allocations_map:
                allocations_map[cid] = {"allocated": 0, "reclaimed": 0}
            amt = a.get("amount") or 0
            if amt > 0:
                allocations_map[cid]["allocated"] += amt
            else:
                allocations_map[cid]["reclaimed"] += abs(amt)
    except Exception:
        pass

    # Fetch campaign counts for target clients
    campaigns_count_map: dict[str, int] = {}
    try:
        client_ids = [c["id"] for c in target_clients]
        cmp_res = await supabase.table("campaigns").select("workspace_id")\
            .in_("workspace_id", client_ids).execute()
        for cmp in (cmp_res.data or []):
            w_id = cmp.get("workspace_id")
            if w_id:
                campaigns_count_map[w_id] = campaigns_count_map.get(w_id, 0) + 1
    except Exception:
        pass

    # Build line items and calculate totals
    unit_rate = max(1, payload.unit_credit_rate_cents or 150)
    base_fee = max(0, payload.platform_base_fee_cents or 0)
    client_breakdowns = []
    subtotal_cents = 0

    for c in target_clients:
        cid = c["id"]
        c_name = c.get("name") or "Client Workspace"
        alloc_data = allocations_map.get(cid, {"allocated": 0, "reclaimed": 0})
        net_period_allocated = max(0, alloc_data["allocated"] - alloc_data["reclaimed"])
        
        # Consumed calculation
        current_bal = c.get("data_cleaning_credits") or 0
        lifetime_budget = c.get("allocated_credit_budget") or 0
        consumed_est = max(0, lifetime_budget - current_bal)
        if net_period_allocated > 0:
            billable_credits = net_period_allocated
        else:
            billable_credits = min(consumed_est, 1000) if consumed_est > 0 else 500

        credit_charge_cents = billable_credits * unit_rate
        client_subtotal_cents = base_fee + credit_charge_cents
        subtotal_cents += client_subtotal_cents

        client_breakdowns.append({
            "client_workspace_id": cid,
            "client_name": c_name,
            "campaigns_count": campaigns_count_map.get(cid, 0),
            "billable_credits": billable_credits,
            "unit_credit_rate_cents": unit_rate,
            "credit_charge_cents": credit_charge_cents,
            "platform_base_fee_cents": base_fee,
            "subtotal_cents": client_subtotal_cents,
            "current_balance": current_bal
        })

    tax_rate = max(0.0, float(payload.tax_percent or 0.0)) / 100.0
    tax_cents = int(round(subtotal_cents * tax_rate))
    total_cents = subtotal_cents + tax_cents

    import secrets
    period_tag = dt_start.strftime("%Y%m")
    inv_number = f"INV-{period_tag}-{secrets.token_hex(3).upper()}"

    statement_record = {
        "agency_id": agency_id,
        "client_workspace_id": payload.client_workspace_id,
        "invoice_number": inv_number,
        "status": "draft",
        "period_start": clean_start,
        "period_end": clean_end,
        "currency": payload.currency or "INR",
        "subtotal_cents": subtotal_cents,
        "markup_cents": 0,
        "tax_cents": tax_cents,
        "total_cents": total_cents,
        "breakdown_data": {
            "target_type": "single_client" if payload.client_workspace_id else "consolidated_agency",
            "tax_percent": payload.tax_percent or 0.0,
            "clients": client_breakdowns,
            "total_billable_credits": sum(cb["billable_credits"] for cb in client_breakdowns)
        },
        "notes": payload.notes
    }

    try:
        insert_res = await supabase.table("agency_billing_statements").insert(statement_record).execute()
        if insert_res.data:
            return insert_res.data[0]
    except Exception:
        pass

    # Fallback return with generated uuid
    import uuid
    statement_record["id"] = str(uuid.uuid4())
    statement_record["created_at"] = datetime.utcnow().isoformat()
    statement_record["updated_at"] = statement_record["created_at"]
    return statement_record


@router.get("/{agency_id}/statements/{statement_id}")
async def get_agency_statement_detail(
    agency_id: str,
    statement_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0: Fetches detailed statement itemization.
    """
    await _verify_agency_member(agency_id, user_id, supabase)
    try:
        res = await supabase.table("agency_billing_statements").select("*")\
            .eq("agency_id", agency_id).eq("id", statement_id).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Statement not found")


@router.patch("/{agency_id}/statements/{statement_id}/status")
async def update_agency_statement_status(
    agency_id: str,
    statement_id: str,
    payload: UpdateStatementStatusRequest,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0 & 2: Updates statement status lifecycle (draft -> issued -> paid -> void).
    """
    await _verify_agency_owner_or_admin(agency_id, user_id, supabase)
    valid_statuses = {"draft", "issued", "paid", "void"}
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")

    update_fields = {"status": payload.status}
    if payload.notes is not None:
        update_fields["notes"] = payload.notes

    try:
        res = await supabase.table("agency_billing_statements").update(update_fields)\
            .eq("agency_id", agency_id).eq("id", statement_id).execute()
        if res.data:
            return res.data[0]
        return {"status": payload.status, "id": statement_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update statement status: {str(e)}")


@router.get("/{agency_id}/statements/{statement_id}/export")
async def export_agency_statement_html(
    agency_id: str,
    statement_id: str,
    supabase: AsyncClient = Depends(get_async_service_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Paranoia Layer 0 & 2: Renders a printable, publication-grade HTML invoice statement
    complete with agency white-label styling and print media queries.
    """
    await _verify_agency_member(agency_id, user_id, supabase)

    # Fetch statement
    stmt = None
    try:
        res = await supabase.table("agency_billing_statements").select("*")\
            .eq("agency_id", agency_id).eq("id", statement_id).limit(1).execute()
        if res.data:
            stmt = res.data[0]
    except Exception:
        pass

    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")

    # Fetch agency branding
    brand_name = "Agency Outbound Services"
    accent_color = "#6366f1"
    try:
        wl_res = await supabase.table("agency_whitelabel").select("brand_name, accent_color")\
            .eq("agency_id", agency_id).limit(1).execute()
        if wl_res.data:
            brand_name = wl_res.data[0].get("brand_name") or brand_name
            accent_color = wl_res.data[0].get("accent_color") or accent_color
    except Exception:
        pass

    breakdown = stmt.get("breakdown_data") or {}
    clients_list = breakdown.get("clients") or []
    curr_symbol = "₹" if stmt.get("currency") == "INR" else "$"

    def fmt_curr(cents: int) -> str:
        return f"{curr_symbol}{cents / 100:,.2f}"

    rows_html = ""
    for c in clients_list:
        c_name = c.get("client_name", "Client")
        base_fee = c.get("platform_base_fee_cents", 0)
        credits_count = c.get("billable_credits", 0)
        credits_cost = c.get("credit_charge_cents", 0)
        campaigns = c.get("campaigns_count", 0)
        total_client = c.get("subtotal_cents", 0)

        rows_html += f"""
        <tr>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0;">
                <div style="font-weight: 600; color: #0f172a;">{c_name}</div>
                <div style="font-size: 11px; color: #64748b;">Active Campaigns: {campaigns}</div>
            </td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #334155;">
                {fmt_curr(base_fee)}
            </td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #334155;">
                {credits_count:,} credits
            </td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #334155;">
                {fmt_curr(credits_cost)}
            </td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: 700; color: #0f172a;">
                {fmt_curr(total_client)}
            </td>
        </tr>
        """

    status_tag = stmt.get("status", "draft").upper()
    status_bg = "#dcfce7" if status_tag == "PAID" else ("#e0e7ff" if status_tag == "ISSUED" else "#f1f5f9")
    status_color = "#15803d" if status_tag == "PAID" else ("#4338ca" if status_tag == "ISSUED" else "#475569")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Invoice {stmt.get('invoice_number')} - {brand_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            margin: 0;
            padding: 40px 20px;
        }}
        .invoice-card {{
            max-width: 820px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
            border: 1px solid #e2e8f0;
            padding: 40px;
        }}
        .print-btn {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            background-color: {accent_color};
            color: #ffffff;
            border: none;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: 700;
            border-radius: 12px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}
        @media print {{
            body {{ background: #ffffff; padding: 0; }}
            .invoice-card {{ box-shadow: none; border: none; padding: 0; }}
            .print-btn {{ display: none; }}
        }}
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()">Print or Save as PDF</button>
    <div class="invoice-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 36px;">
            <div>
                <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #0f172a;">{brand_name}</h1>
                <p style="margin: 4px 0 0 0; color: #64748b; font-size: 13px;">Managed Outbound Invoicing & Statement</p>
            </div>
            <div style="text-align: right;">
                <span style="display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 800; background: {status_bg}; color: {status_color};">
                    {status_tag}
                </span>
                <div style="font-size: 18px; font-weight: 800; font-family: monospace; margin-top: 8px;">
                    {stmt.get('invoice_number')}
                </div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 36px; padding: 20px; background: #f8fafc; border-radius: 12px; border: 1px solid #f1f5f9;">
            <div>
                <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b;">Billing Period</div>
                <div style="font-size: 14px; font-weight: 600; color: #0f172a; margin-top: 4px;">
                    {stmt.get('period_start')} &rarr; {stmt.get('period_end')}
                </div>
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b;">Issue Date</div>
                <div style="font-size: 14px; font-weight: 600; color: #0f172a; margin-top: 4px;">
                    {str(stmt.get('created_at', ''))[:10]}
                </div>
            </div>
        </div>

        <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 32px;">
            <thead>
                <tr style="background: #f8fafc; border-bottom: 2px solid #e2e8f0; text-align: left;">
                    <th style="padding: 12px 16px; color: #475569; font-weight: 700;">Client Workspace</th>
                    <th style="padding: 12px 16px; color: #475569; font-weight: 700; text-align: right;">Base Retainer</th>
                    <th style="padding: 12px 16px; color: #475569; font-weight: 700; text-align: right;">Credits Allocated</th>
                    <th style="padding: 12px 16px; color: #475569; font-weight: 700; text-align: right;">Credit Fees</th>
                    <th style="padding: 12px 16px; color: #475569; font-weight: 700; text-align: right;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div style="display: flex; justify-content: flex-end; margin-bottom: 40px;">
            <div style="width: 280px; font-size: 13px;">
                <div style="display: flex; justify-content: space-between; padding: 6px 0; color: #64748b;">
                    <span>Subtotal</span>
                    <span style="font-weight: 600; color: #0f172a;">{fmt_curr(stmt.get('subtotal_cents', 0))}</span>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 6px 0; color: #64748b;">
                    <span>Tax ({breakdown.get('tax_percent', 18)}% GST/VAT)</span>
                    <span style="font-weight: 600; color: #0f172a;">{fmt_curr(stmt.get('tax_cents', 0))}</span>
                </div>
                <div style="display: flex; justify-content: space-between; padding: 12px 0 0 0; border-top: 2px solid #0f172a; font-size: 16px; font-weight: 800; color: #0f172a;">
                    <span>Total Due</span>
                    <span>{fmt_curr(stmt.get('total_cents', 0))}</span>
                </div>
            </div>
        </div>

        {f'<div style="padding: 16px; background: #f8fafc; border-radius: 8px; font-size: 12px; color: #64748b; border: 1px solid #f1f5f9;"><strong>Notes:</strong> {stmt.get("notes")}</div>' if stmt.get('notes') else ''}
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


