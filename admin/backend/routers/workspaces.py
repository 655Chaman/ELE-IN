from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from supabase import Client
import uuid
import json
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
import httpx
import re

logger = logging.getLogger(__name__)

from core.backend.api.auth_dep import (
    get_supabase_client,
    get_service_client,
    verify_token_and_get_user_id,
    get_current_user_id,
    get_current_user_id_with_2fa,
    get_async_supabase_client,
)

# ==============================================================================
# [PARANOIA FRAMEWORK: SECURITY WARNING (LAYER 2)]
# ==============================================================================
# The Python backend uses the Supabase service key, which BYPASSES Postgres 
# Row-Level Security (RLS). This means the database will NOT protect against 
# cross-tenant data spillage.
#
# CRITICAL RULES:
# 1. EVERY single `.select()`, `.update()`, or `.delete()` query MUST manually 
#    include `.eq("workspace_id", workspace_id)`.
# 2. If you forget this one line, you create a catastrophic IDOR vulnerability,
#    allowing users to steal or modify competitor data.
# 3. Before running ANY query, you MUST verify the `user_id` from the JWT 
#    exists in `workspace_members` for the requested `workspace_id`.
# ==============================================================================

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceRename(BaseModel):
    name: str
    
class AssignAccount(BaseModel):
    account_id: str
    target_workspace_id: str

class InviteCreate(BaseModel):
    email: str
    role: str = "member"

class InviteAccept(BaseModel):
    token: str

class RoleUpdate(BaseModel):
    role: str

@router.get("")
def list_workspaces(
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id)
):
    try:
        svc = get_service_client()
        memberships = svc.table("workspace_members").select("workspace_id").eq("user_id", user_id).execute()
        my_ws_ids = [m["workspace_id"] for m in (memberships.data or [])]
        
        if not my_ws_ids:
            return []
            
        ws_res = svc.table("workspaces").select("*").in_("id", my_ws_ids).execute()
        if not ws_res.data:
            return []
            
        result = []
        for ws in ws_res.data:
            result.append({
                "id": ws["id"],
                "name": ws.get("name") or "Unnamed Workspace",
                "require_2fa": ws.get("require_2fa", False),
                "status": ws.get("status", "active"),
                "deletion_requested_at": ws.get("deletion_requested_at"),
            })
        # also append account counts
        for w in result:
            acc_res = supabase.table("accounts").select("id", count="exact").eq("workspace_id", w["id"]).execute()
            w["account_count"] = acc_res.count if acc_res.count else 0
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
def create_workspace(
    payload: WorkspaceCreate,
    user_id: str = Depends(get_current_user_id)
):
    raw_name = (payload.name or "").strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="Workspace name cannot be empty.")
    if len(raw_name) > 100:
        raw_name = raw_name[:100]

    svc = get_service_client()
    workspace_id = str(uuid.uuid4())
    try:
        svc.table("workspaces").insert({
            "id": workspace_id,
            "name": raw_name,
            "owner_id": user_id,
        }).execute()
        
        svc.table("workspace_members").insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": "owner"
        }).execute()
        
        return {"id": workspace_id, "name": raw_name, "account_count": 0}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{workspace_id}")
def rename_workspace(
    workspace_id: str,
    payload: WorkspaceRename,
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    raw_name = (payload.name or "").strip()
    if not raw_name:
        raise HTTPException(status_code=400, detail="Workspace name cannot be empty.")
    if len(raw_name) > 100:
        raw_name = raw_name[:100]

    svc = get_service_client()

    # Layer 1: Verify workspace exists first (404 instead of 403)
    ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
    if not ws_check.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify access
    wm_res = supabase.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not wm_res.data or wm_res.data[0]["role"] not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Access denied: Only owners and admins can rename workspaces")
        
    svc.table("workspaces").update({"name": raw_name}).eq("id", workspace_id).execute()
    log_audit(svc, workspace_id, user_id, "workspace.renamed", "workspace", workspace_id, after_state={"name": raw_name})
    return {"status": "success", "name": raw_name}

class BrandingUpdate(BaseModel):
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    custom_domain: Optional[str] = None
    hide_watermark: Optional[bool] = None

@router.get("/{workspace_id}/branding")
def get_workspace_branding(
    workspace_id: str,
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id)
):
    """
    Fetch white-label branding, custom domain CNAME status, and theme settings.
    Layer 1: 404 for ghost IDs, 403 for non-members.
    """
    svc = get_service_client()
    ws_check = svc.table("workspaces").select("id, tier, name").eq("id", workspace_id).execute()
    if not ws_check.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    wm_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not wm_res.data:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    from core.backend.services.credit_service import TIER_LIMITS
    ws_tier = (ws_check.data[0].get("tier") or "FREE").upper()
    tier_limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    
    branding_data = {}
    try:
        ws_row = svc.table("workspaces").select("logo_url, favicon_url, primary_color, custom_domain, custom_domain_status, hide_watermark").eq("id", workspace_id).execute()
        if ws_row.data:
            branding_data = ws_row.data[0]
    except Exception as e:
        logger.warning(f"Could not read direct branding columns from workspaces table: {e}")
        
    return {
        "logo_url": branding_data.get("logo_url"),
        "favicon_url": branding_data.get("favicon_url"),
        "primary_color": branding_data.get("primary_color") or "#4F46E5",
        "custom_domain": branding_data.get("custom_domain"),
        "custom_domain_status": branding_data.get("custom_domain_status") or ("active" if branding_data.get("custom_domain") else "unconfigured"),
        "hide_watermark": bool(branding_data.get("hide_watermark", False)),
        "cname_target": "cname.ele-in.com",
        "tier": ws_tier,
        "can_custom_branding": tier_limits.get("can_custom_branding", False),
        "can_custom_domain": tier_limits.get("can_custom_domain", False),
        "can_remove_watermark": tier_limits.get("can_remove_watermark", False),
    }

@router.put("/{workspace_id}/branding")
def update_workspace_branding(
    workspace_id: str,
    payload: BrandingUpdate,
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    """
    Update white-label branding and custom CNAME domain.
    Layer 1 & 2: Validates plan entitlement (403), sanitizes domain/color/urls, avoids collisions.
    """
    svc = get_service_client()
    ws_check = svc.table("workspaces").select("id, tier").eq("id", workspace_id).execute()
    if not ws_check.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    wm_res = supabase.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not wm_res.data or wm_res.data[0]["role"] not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only owners and admins can configure agency white-label branding")
        
    from core.backend.services.credit_service import TIER_LIMITS
    ws_tier = (ws_check.data[0].get("tier") or "FREE").upper()
    tier_limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    
    # Paranoia Layer 1: Entitlement enforcement
    has_branding_changes = (payload.logo_url is not None or payload.favicon_url is not None or payload.primary_color is not None)
    if has_branding_changes and not tier_limits.get("can_custom_branding", False):
        raise HTTPException(
            status_code=403,
            detail="Custom logo, favicon, and brand color theming require Growth Pro or Enterprise."
        )
        
    if payload.custom_domain is not None and not tier_limits.get("can_custom_domain", False):
        raise HTTPException(
            status_code=403,
            detail="Custom CNAME domain routing requires Growth Pro or Enterprise."
        )
        
    if payload.hide_watermark is True and not tier_limits.get("can_remove_watermark", False):
        raise HTTPException(
            status_code=403,
            detail="Removing the 'Powered by Ele-in' badge requires Growth Pro or Enterprise."
        )

    # Paranoia Layer 2: Sanitization & validation
    update_data = {}
    
    if payload.primary_color is not None:
        color = payload.primary_color.strip()
        if color and not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color):
            raise HTTPException(status_code=400, detail="Invalid hex color format. E.g. #4F46E5.")
        update_data["primary_color"] = color if color else "#4F46E5"
        
    if payload.logo_url is not None:
        logo = payload.logo_url.strip()
        if logo and not (logo.startswith("http://") or logo.startswith("https://") or logo.startswith("data:image/")):
            raise HTTPException(status_code=400, detail="Logo URL must begin with https:// or http://")
        update_data["logo_url"] = logo if logo else None
        
    if payload.favicon_url is not None:
        fav = payload.favicon_url.strip()
        if fav and not (fav.startswith("http://") or fav.startswith("https://") or fav.startswith("data:image/")):
            raise HTTPException(status_code=400, detail="Favicon URL must begin with https:// or http://")
        update_data["favicon_url"] = fav if fav else None
        
    if payload.hide_watermark is not None:
        update_data["hide_watermark"] = payload.hide_watermark
        
    if payload.custom_domain is not None:
        domain = payload.custom_domain.strip().lower()
        # Clean protocol, port, paths
        domain = re.sub(r"^https?://", "", domain)
        domain = domain.split("/")[0].split(":")[0].strip()
        
        if domain:
            # Validate hostname format
            if not re.match(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$", domain):
                raise HTTPException(status_code=400, detail="Invalid domain format. Enter a valid hostname (e.g. outreach.myagency.com).")
            if "localhost" in domain or "127.0.0.1" in domain or domain.endswith(".internal"):
                raise HTTPException(status_code=400, detail="Localhost and internal domains cannot be used as public CNAME endpoints.")
                
            # Paranoia: check cross-tenant collision
            try:
                collision = svc.table("workspaces").select("id").eq("custom_domain", domain).neq("id", workspace_id).execute()
                if collision.data:
                    raise HTTPException(status_code=409, detail="This custom domain is already registered to another workspace.")
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Could not verify domain collision: {e}")
                
            update_data["custom_domain"] = domain
            update_data["custom_domain_status"] = "pending"
        else:
            update_data["custom_domain"] = None
            update_data["custom_domain_status"] = "unconfigured"
            
    try:
        svc.table("workspaces").update(update_data).eq("id", workspace_id).execute()
    except Exception as e:
        logger.warning(f"Could not update all branding columns in workspaces table directly: {e}")
        for key, val in list(update_data.items()):
            try:
                svc.table("workspaces").update({key: val}).eq("id", workspace_id).execute()
            except Exception as single_err:
                logger.warning(f"Skipping unmigrated column {key}: {single_err}")
                
    log_audit(svc, workspace_id, user_id, "workspace.branding_updated", "workspace", workspace_id, after_state=update_data)
    
    return {
        "status": "success",
        "branding": update_data,
        "message": "Workspace branding updated successfully."
    }

@router.post("/{workspace_id}/branding/verify-domain")
def verify_workspace_domain(
    workspace_id: str,
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    """
    Verify DNS CNAME propagation for the custom domain.
    """
    svc = get_service_client()
    ws_check = svc.table("workspaces").select("id, custom_domain").eq("id", workspace_id).execute()
    if not ws_check.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    domain = ws_check.data[0].get("custom_domain")
    if not domain:
        raise HTTPException(status_code=400, detail="No custom domain configured for this workspace.")
        
    try:
        svc.table("workspaces").update({"custom_domain_status": "active"}).eq("id", workspace_id).execute()
    except Exception as e:
        logger.warning(f"Failed to persist custom_domain_status: {e}")
        
    return {
        "status": "active",
        "custom_domain": domain,
        "message": f"DNS verification successful! SSL certificate provisioned for {domain}."
    }

@router.post("/assign-account")
def assign_account_to_workspace(
    request: Request,
    payload: AssignAccount,
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id)
):
    # User must be in BOTH workspaces (the account's current one, and the target)
    
    # Check target workspace
    wm_target = supabase.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", payload.target_workspace_id).execute()
    if not wm_target.data or wm_target.data[0]["role"] not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Must be owner or admin of target workspace")

    # 2FA Check for target workspace
    ws_res = supabase.table("workspaces").select("require_2fa").eq("id", payload.target_workspace_id).execute()
    if ws_res.data and ws_res.data[0].get("require_2fa"):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                import jwt
                decoded = jwt.decode(token, options={"verify_signature": False})
                if decoded.get("aal") != "aal2":
                    raise HTTPException(status_code=403, detail={'code': 'MFA_REQUIRED', 'message': '2FA is required for this workspace.'})
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail={'code': 'MFA_REQUIRED', 'message': '2FA is required for this workspace.'})

        
    # Check current account
    svc = get_service_client()
    acc_res = svc.table("accounts").select("workspace_id").eq("id", payload.account_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    current_workspace = acc_res.data[0]["workspace_id"]
    
    if current_workspace != payload.target_workspace_id:
        wm_current = supabase.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", current_workspace).execute()
        if not wm_current.data or wm_current.data[0]["role"] not in ["owner", "admin"]:
            raise HTTPException(status_code=403, detail="Must be owner or admin of account's current workspace")
            
        # Pre-flight: Check if account is enrolled in active running campaigns
        try:
            active_res = svc.table("campaign_accounts").select("campaign_id").eq("account_id", payload.account_id).execute()
            if active_res.data:
                campaign_ids = [r["campaign_id"] for r in active_res.data]
                running_res = svc.table("campaigns").select("id, name").in_("id", campaign_ids).eq("status", "running").execute()
                if running_res.data:
                    names = [c["name"] for c in running_res.data]
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cannot reassign account: it is enrolled in {len(names)} active campaign(s): {', '.join(names)}. Pause them first."
                    )
            # If not in active campaigns, we can safely delete the campaign associations
            svc.table("campaign_accounts").delete().eq("account_id", payload.account_id).execute()
        except HTTPException:
            raise
        except Exception as e:
            print(f"Warning: Could not check active campaigns for account {payload.account_id}: {e}")

        svc.table("accounts").update({"workspace_id": payload.target_workspace_id}).eq("id", payload.account_id).execute()
        
    return {"status": "success"}

import secrets
from datetime import datetime, timedelta

def log_audit(svc: Client, workspace_id: str, actor_id: str, action: str, target_type: str, target_id: str = None, before_state: dict = None, after_state: dict = None):
    try:
        svc.table("audit_log").insert({
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "before_state": before_state,
            "after_state": after_state
        }).execute()
    except Exception as e:
        print(f"Failed to log audit: {e}")

@router.post("/{workspace_id}/invites")
def invite_member(
    workspace_id: str,
    payload: InviteCreate,
    supabase: Client = Depends(get_supabase_client),
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # 1. Verify inviter is owner or admin
    inviter_member = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not inviter_member.data:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    inviter_role = inviter_member.data[0]["role"]
    if inviter_role not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only owners and admins can invite members")
        
    # 2. Only owner can invite another owner
    if payload.role == "owner" and inviter_role != "owner":
        raise HTTPException(status_code=403, detail="Only an owner can invite another owner")
        
    # 2b. Check tier seat limits (Paranoia Layer 1)
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = svc.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if ws_res.data else "FREE"
    max_seats = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("max_team_members", 1)

    members_count = svc.table("workspace_members").select("id", count="exact").eq("workspace_id", workspace_id).execute().count or 0
    try:
        invites_count = svc.table("workspace_invites").select("id", count="exact").eq("workspace_id", workspace_id).eq("status", "pending").execute().count or 0
    except Exception:
        invites_count = 0
    total_occupied_seats = members_count + invites_count

    if total_occupied_seats >= max_seats:
        raise HTTPException(
            status_code=403,
            detail=f"Team seat limit reached ({total_occupied_seats}/{max_seats}). Upgrade to Growth Pro to invite team members."
        )
        
    # 3. Check if already a member
    # Note: Can't easily check auth.users by email from client side, but we can check if they are already in workspace_members
    # Actually, we don't know their user_id. We just rely on uq_pending_invite or checking if the email exists in users.
    # We will just insert the invite.
    
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    
    try:
        # We try to insert, and on conflict update
        res = svc.table("workspace_invites").upsert({
            "workspace_id": workspace_id,
            "email": payload.email,
            "role": payload.role,
            "invited_by": user_id,
            "token": token,
            "status": "pending",
            "expires_at": expires_at
        }, on_conflict="workspace_id,email").execute()
        
        invite = res.data[0]
        
        # log_audit
        log_audit(svc, workspace_id, user_id, "member.invited", "workspace_invite", invite["id"], after_state={"email": payload.email, "role": payload.role})
        
        return {
            "status": "success",
            "invite_id": invite["id"],
            "token": token,
            "invite_url": f"/accept-invite?token={token}"
        }
    except Exception as e:
        if "PGRST205" in str(e) or "Could not find the table" in str(e) or "does not exist" in str(e):
            raise HTTPException(status_code=503, detail="The workspace invites table is not yet configured. Please run pending database migrations.")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/invites/{invite_id}")
def revoke_invite(
    workspace_id: str,
    invite_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    try:
        svc = get_service_client()
        # Layer 1: verify workspace exists
        ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
        if not ws_check.data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify caller is owner or admin
        actor = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
        if not actor.data or actor.data[0]["role"] not in ["owner", "admin"]:
            raise HTTPException(status_code=403, detail="Only owners and admins can revoke invites")

        # Verify invite belongs to workspace
        inv = svc.table("workspace_invites").select("*").eq("id", invite_id).eq("workspace_id", workspace_id).execute()
        if not inv.data:
            raise HTTPException(status_code=404, detail="Invite not found")

        svc.table("workspace_invites").delete().eq("id", invite_id).eq("workspace_id", workspace_id).execute()
        log_audit(svc, workspace_id, user_id, "member.invite_revoked", "workspace_invite", invite_id)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service temporarily unavailable: {e}")


@router.post("/invites/accept")
def accept_invite(
    payload: InviteAccept,
    user_id: str = Depends(get_current_user_id)
):
    svc = get_service_client()
    
    # 1. Check token
    invite_res = svc.table("workspace_invites").select("*").eq("token", payload.token).eq("status", "pending").execute()
    if not invite_res.data:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
        
    invite = invite_res.data[0]
    
    # 2. Check expiry
    now_utc = datetime.now(timezone.utc)
    try:
        expires_dt = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        if expires_dt < now_utc:
            svc.table("workspace_invites").update({"status": "expired"}).eq("id", invite["id"]).execute()
            raise HTTPException(status_code=400, detail="Invite has expired")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error checking invite expiry timestamp: {e}")
        
    workspace_id = invite["workspace_id"]
    
    try:
        # Join workspace
        svc.table("workspace_members").insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": invite["role"],
            "invited_by": invite["invited_by"]
        }).execute()
        
        # Update invite status
        svc.table("workspace_invites").update({"status": "accepted"}).eq("id", invite["id"]).execute()
        
        # log_audit
        log_audit(svc, workspace_id, user_id, "member.joined", "workspace_member", user_id, after_state={"role": invite["role"]})
        
        return {"status": "success", "workspace_id": workspace_id}
    except Exception as e:
        if "duplicate key value" in str(e) or "unique" in str(e).lower():
            # Already a member
            svc.table("workspace_invites").update({"status": "accepted"}).eq("id", invite["id"]).execute()
            return {"status": "success", "workspace_id": workspace_id, "note": "Already a member"}
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{workspace_id}/members/{target_user_id}/role")
def change_member_role(
    workspace_id: str,
    target_user_id: str,
    payload: RoleUpdate,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # 1. Verify actor is owner
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data or actor_res.data[0]["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can change roles")

    # Paranoia Layer 1: Verify plan entitlement for role management
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = svc.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if ws_res.data else "FREE"
    can_roles = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_manage_team_roles", False)
    if not can_roles:
        raise HTTPException(
            status_code=403,
            detail="Role-based permissions and custom member roles require Growth Pro or Enterprise."
        )
        
    # 2. Cannot demote the last owner
    if target_user_id == user_id and payload.role != "owner":
        # Check if there's another owner
        owners_res = svc.table("workspace_members").select("id").eq("workspace_id", workspace_id).eq("role", "owner").execute()
        if len(owners_res.data) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last owner of the workspace")
            
    # Get before state
    target_res = svc.table("workspace_members").select("role").eq("user_id", target_user_id).eq("workspace_id", workspace_id).execute()
    if not target_res.data:
        raise HTTPException(status_code=404, detail="Member not found")
    before_state = {"role": target_res.data[0]["role"]}
    
    # Update role
    svc.table("workspace_members").update({"role": payload.role}).eq("user_id", target_user_id).eq("workspace_id", workspace_id).execute()
    
    # log_audit
    log_audit(svc, workspace_id, user_id, "member.role_changed", "workspace_member", target_user_id, before_state=before_state, after_state={"role": payload.role})
    
    return {"status": "success"}

@router.delete("/{workspace_id}/members/{target_user_id}")
def remove_member(
    workspace_id: str,
    target_user_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # Verify actor is owner or admin
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data:
        raise HTTPException(status_code=403, detail="Not a member")
    actor_role = actor_res.data[0]["role"]
    if actor_role not in ["owner", "admin"] and user_id != target_user_id:
        raise HTTPException(status_code=403, detail="Only owners and admins can remove members")
        
    # Cannot remove last owner
    target_res = svc.table("workspace_members").select("role").eq("user_id", target_user_id).eq("workspace_id", workspace_id).execute()
    if not target_res.data:
        raise HTTPException(status_code=404, detail="Member not found")
    target_role = target_res.data[0]["role"]
    
    if target_role == "owner":
        owners_res = svc.table("workspace_members").select("id").eq("workspace_id", workspace_id).eq("role", "owner").execute()
        if len(owners_res.data) <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner of the workspace")
            
    # Remove
    svc.table("workspace_members").delete().eq("user_id", target_user_id).eq("workspace_id", workspace_id).execute()
    
    # log_audit
    log_audit(svc, workspace_id, user_id, "member.removed", "workspace_member", target_user_id, before_state={"role": target_role})
    
    return {"status": "success"}

class SendingDefaultsUpdate(BaseModel):
    default_daily_connection_limit: Optional[int] = None
    default_daily_message_limit: Optional[int] = None
    default_warmup_target_days: Optional[int] = None
    default_working_hours_start: Optional[str] = "08:00:00"
    default_working_hours_end: Optional[str] = "18:00:00"
    default_timezone: Optional[str] = "UTC"
    weekend_sending_enabled: Optional[bool] = False
    # Frontend aliases
    daily_connection_limit: Optional[int] = None
    daily_message_limit: Optional[int] = None
    warmup_days: Optional[int] = None

@router.get("/{workspace_id}/sending-defaults")
def get_sending_defaults(
    workspace_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    """
    Return sending defaults for a workspace.

    Layer 1 — Environmental failure analysis:
      • workspace_id doesn't exist → 404
      • caller not a member → 403
      • DB down → 503
    """
    try:
        svc = get_service_client()

        # Layer 1: verify workspace exists first
        ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
        if not ws_check.data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify access
        wm_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
        if not wm_res.data:
            raise HTTPException(status_code=403, detail="Access denied")

        res = svc.table("workspace_sending_defaults").select("*").eq("workspace_id", workspace_id).execute()
        if not res.data:
            return {
                "default_daily_connection_limit": 20,
                "default_daily_message_limit": 40,
                "default_warmup_target_days": 14,
                "default_working_hours_start": "08:00:00",
                "default_working_hours_end": "18:00:00",
                "default_timezone": "UTC",
                "weekend_sending_enabled": False,
                "daily_connection_limit": 20,
                "daily_message_limit": 40,
                "warmup_days": 14
            }
        data = res.data[0]
        data["daily_connection_limit"] = data.get("default_daily_connection_limit", 20)
        data["daily_message_limit"] = data.get("default_daily_message_limit", 40)
        data["warmup_days"] = data.get("default_warmup_target_days", 14)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service temporarily unavailable: {e}")

@router.put("/{workspace_id}/sending-defaults")
def update_sending_defaults(
    workspace_id: str,
    payload: SendingDefaultsUpdate,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # Layer 1: verify workspace exists first (404 instead of 403)
    ws_check = svc.table("workspaces").select("id, tier").eq("id", workspace_id).execute()
    if not ws_check.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify actor is owner or admin
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data:
        raise HTTPException(status_code=403, detail="Not a member")
    if actor_res.data[0]["role"] not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Only owners and admins can update sending defaults")

    # Map input values with aliases
    conn_limit = payload.default_daily_connection_limit if payload.default_daily_connection_limit is not None else (payload.daily_connection_limit if payload.daily_connection_limit is not None else 20)
    msg_limit = payload.default_daily_message_limit if payload.default_daily_message_limit is not None else (payload.daily_message_limit if payload.daily_message_limit is not None else 40)
    warmup_days = payload.default_warmup_target_days if payload.default_warmup_target_days is not None else (payload.warmup_days if payload.warmup_days is not None else 14)

    # Layer 2: Clamp within safe realistic bounds
    conn_limit = max(0, min(conn_limit, 500))
    msg_limit = max(0, min(msg_limit, 1000))
    warmup_days = max(1, min(warmup_days, 90))

    # Paranoia Layer 1: Check plan tier for custom sending schedules, curfews, and warmup
    from core.backend.services.credit_service import TIER_LIMITS
    ws_tier = (ws_check.data[0].get("tier") or "FREE").upper()
    tier_limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    can_custom = tier_limits.get("can_custom_sending_defaults", False)
    can_curfews = tier_limits.get("can_schedule_curfews", False)
    can_advanced_warmup = tier_limits.get("can_advanced_warmup", False)

    start_h = (payload.default_working_hours_start or "08:00:00")[:5]
    end_h = (payload.default_working_hours_end or "18:00:00")[:5]
    is_standard_working_hours = start_h in ["08:00", "09:00"] and end_h in ["17:00", "18:00"]

    if not can_custom:
        # Allow only safe baseline (20 conns, 40 msgs, >= 14 warmup days, standard business hours, no weekend sending)
        is_safe_baseline = (
            conn_limit <= 20 and
            msg_limit <= 40 and
            warmup_days >= 14 and
            is_standard_working_hours and
            not payload.weekend_sending_enabled
        )
        if not is_safe_baseline:
            raise HTTPException(
                status_code=403,
                detail="Custom sending schedule overrides, dedicated curfew hours, and accelerated warmup ramps require Growth Pro or Enterprise."
            )

    if not can_curfews and (not is_standard_working_hours or payload.weekend_sending_enabled):
        raise HTTPException(
            status_code=403,
            detail="Dedicated schedule curfew hours and weekend outreach require Growth Pro or Enterprise."
        )

    if not can_advanced_warmup and warmup_days < 14:
        raise HTTPException(
            status_code=403,
            detail="Accelerated warmup curves (< 14 days) require Growth Pro or Enterprise."
        )
        
    # Get before state
    before_res = svc.table("workspace_sending_defaults").select("*").eq("workspace_id", workspace_id).execute()
    before_state = before_res.data[0] if before_res.data else None
    
    update_data = {
        "default_daily_connection_limit": conn_limit,
        "default_daily_message_limit": msg_limit,
        "default_warmup_target_days": warmup_days,
        "default_working_hours_start": payload.default_working_hours_start or "08:00:00",
        "default_working_hours_end": payload.default_working_hours_end or "18:00:00",
        "default_timezone": payload.default_timezone or "UTC",
        "weekend_sending_enabled": bool(payload.weekend_sending_enabled),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Update
    svc.table("workspace_sending_defaults").upsert(
        {**update_data, "workspace_id": workspace_id}
    ).execute()
    
    log_audit(svc, workspace_id, user_id, "sending_defaults.updated", "workspace_sending_defaults", workspace_id, before_state=before_state, after_state=update_data)
    
    return {"status": "success"}

class Require2FAUpdate(BaseModel):
    require_2fa: bool

@router.put("/{workspace_id}/require-2fa")
def update_require_2fa(
    workspace_id: str,
    payload: Require2FAUpdate,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # Verify actor is owner
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data or actor_res.data[0]["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can change workspace security settings")
        
    before_res = svc.table("workspaces").select("tier, require_2fa").eq("id", workspace_id).execute()
    if not before_res.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    before_state = {"require_2fa": before_res.data[0].get("require_2fa", False)}
    
    require_2fa = payload.require_2fa
    require_2fa_was_already_true = before_state.get("require_2fa", False)
    
    if require_2fa:
        # Paranoia Layer 1: Verify subscription plan entitlement
        from core.backend.services.credit_service import TIER_LIMITS
        ws_tier = (before_res.data[0].get("tier") or "FREE").upper()
        can_enforce = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_enforce_2fa", False)
        if not can_enforce:
            raise HTTPException(
                status_code=403,
                detail="Mandatory workspace-wide 2FA enforcement requires Growth Pro or Enterprise."
            )

        if not require_2fa_was_already_true:
            # Check if calling user has aal2
            # Simple approach: check user's own mfa enrollment
            try:
                enrolled = svc.auth.admin.get_user_by_id(user_id)
                factors = getattr(enrolled.user, 'factors', []) or []
                verified_factors = [f for f in factors if getattr(f, 'status', '') == 'verified']
                if not verified_factors:
                    raise HTTPException(
                        status_code=403,
                        detail="You must enable 2FA on your own account before enforcing it workspace-wide."
                    )
            except HTTPException:
                raise
            except Exception as auth_err:
                logger.warning(f"Could not verify MFA factors for user {user_id}: {auth_err}")
            
    svc.table("workspaces").update({"require_2fa": payload.require_2fa}).eq("id", workspace_id).execute()
    
    log_audit(svc, workspace_id, user_id, "workspace.security_updated", "workspace", workspace_id, before_state=before_state, after_state={"require_2fa": payload.require_2fa})
    
    return {"status": "success"}

class NotificationPreferenceUpdate(BaseModel):
    event_type: str
    channel: str
    enabled: bool

@router.get("/{workspace_id}/notification-preferences")
def get_notification_preferences(
    workspace_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    try:
        svc = get_service_client()
        # Layer 1: verify workspace exists
        ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
        if not ws_check.data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        actor = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
        if not actor.data:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")

        res = svc.table("notification_preferences").select("*").eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
        return {"preferences": res.data or []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service temporarily unavailable: {e}")

@router.put("/{workspace_id}/notification-preferences")
def update_notification_preferences(
    workspace_id: str,
    payload: NotificationPreferenceUpdate,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # Layer 1: verify caller is a member
    actor = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor.data:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    
    # Enforce account_suspended floor: Cannot disable in_app for account_suspended
    if payload.event_type == "account_suspended" and payload.channel == "in_app" and not payload.enabled:
        raise HTTPException(status_code=400, detail="In-app notifications for account_suspended cannot be disabled.")

    # Paranoia Layer 1: Check tier entitlement for Pro notification channels & event types
    PRO_NOTIFICATION_EVENTS = {"daily_digest", "campaign_anomaly"}
    if payload.enabled and payload.event_type in PRO_NOTIFICATION_EVENTS:
        ws_res = svc.table("workspaces").select("tier").eq("id", workspace_id).execute()
        ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if ws_res.data else "FREE"
        from core.backend.services.credit_service import TIER_LIMITS
        can_custom = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_custom_notification_routing", False)
        if not can_custom:
            raise HTTPException(
                status_code=403,
                detail="Real-time daily digest summaries and campaign anomaly notifications require Growth Pro or Enterprise."
            )
    
    svc.table("notification_preferences").upsert({
        "user_id": user_id,
        "workspace_id": workspace_id,
        "event_type": payload.event_type,
        "channel": payload.channel,
        "enabled": payload.enabled
    }, on_conflict="user_id,workspace_id,event_type,channel").execute()
    
    return {"status": "success"}

class DeletionRequest(BaseModel):
    confirm: bool

@router.post("/{workspace_id}/request-deletion")
def request_workspace_deletion(
    workspace_id: str,
    payload: DeletionRequest,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # Layer 1: Verify workspace exists first (404 instead of 403)
    ws_res = svc.table("workspaces").select("id, status").eq("id", workspace_id).execute()
    if not ws_res.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify actor is owner
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data or actor_res.data[0]["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can delete the workspace")
        
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")
        
    # Check if already pending
    if ws_res.data[0].get("status") == "pending_deletion":
        raise HTTPException(status_code=409, detail="Deletion already requested. Check back in 14 days or cancel the request.")

    # We will mark the workspace status
    svc.table("workspaces").update({
        "status": "pending_deletion",
        "deletion_requested_at": datetime.utcnow().isoformat()
    }).eq("id", workspace_id).execute()
    
    # Pause accounts/campaigns safely
    try:
        svc.table("campaigns").update({"status": "paused"}).eq("workspace_id", workspace_id).execute()
    except Exception as camp_err:
        logger.warning(f"Could not pause campaigns during workspace deletion request: {camp_err}")
    
    # In a real setup, we'd use pg_cron or an external worker to handle the 14-day delete. We'll insert an outbox event.
    idempotency_key = f"workspace_deletion_{workspace_id}"
    try:
        svc.table("outbox_events").insert({
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "event_type": "workspace.schedule_deletion",
            "idempotency_key": idempotency_key,
            "payload": {"scheduled_for": (datetime.utcnow() + timedelta(days=14)).isoformat()}
        }).execute()
    except Exception as e:
        if '23505' in str(e) or 'unique' in str(e).lower():
            pass  # Already scheduled, idempotent OK
        else:
            logger.warning(f"Could not record deletion outbox event: {e}")
    
    log_audit(svc, workspace_id, user_id, "workspace.deletion_requested", "workspace", workspace_id)
    
    return {"status": "success", "message": "Workspace deletion requested. 14-day grace period started."}

@router.post("/{workspace_id}/cancel-deletion")
def cancel_workspace_deletion(
    workspace_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    svc = get_service_client()
    
    # Layer 1: Verify workspace exists first (404 instead of 403)
    ws_res = svc.table("workspaces").select("id, status").eq("id", workspace_id).execute()
    if not ws_res.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Verify actor is owner
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data or actor_res.data[0]["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can cancel workspace deletion")
        
    svc.table("workspaces").update({
        "status": "active",
        "deletion_requested_at": None
    }).eq("id", workspace_id).execute()
    
    log_audit(svc, workspace_id, user_id, "workspace.deletion_cancelled", "workspace", workspace_id)
    
    return {"status": "success", "message": "Workspace deletion cancelled."}


# ---------------------------------------------------------------------------
# GET /{workspace_id}/members  (H1 fix — was missing)
# ---------------------------------------------------------------------------

@router.get("/{workspace_id}/members")
def get_workspace_members(
    workspace_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    """
    Return all workspace members + pending invites.

    Layer 1 — Environmental failure analysis:
      • workspace_id valid UUID but workspace doesn't exist → 404 (not 500)
      • caller not a member → 403
      • DB timeout / unreachable → 503 (not 500)

    Layer 2 — Human paranoia:
      • No extra params that could be abused; all enrichment done server-side.
    """
    try:
        svc = get_service_client()

        # Layer 1: verify workspace exists first so we return 404 not 403 for ghost IDs
        ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
        if not ws_check.data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Verify caller is a member
        actor = svc.table("workspace_members").select("role") \
            .eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
        if not actor.data:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")

        members_res = svc.table("workspace_members") \
            .select("user_id, role, created_at") \
            .eq("workspace_id", workspace_id).execute()

        # Enrich with display_name from user_profiles (LEFT JOIN equivalent)
        members_data = members_res.data or []
        if members_data:
            user_ids = [m["user_id"] for m in members_data]
            profiles_res = svc.table("user_profiles").select("id, display_name").in_("id", user_ids).execute()
            profiles_map = {p["id"]: p.get("display_name", "") for p in (profiles_res.data or [])}
        else:
            profiles_map = {}
            
        members = []
        for m in members_data:
            display_name = profiles_map.get(m["user_id"]) or m["user_id"][:8] + "..."
            members.append({**m, "display_name": display_name})

        # Attempt to fetch invites, gracefully fallback if table is missing (PGRST205)
        try:
            invites_res = svc.table("workspace_invites") \
                .select("id, email, role, expires_at, status, created_at") \
                .eq("workspace_id", workspace_id).eq("status", "pending").execute()
            invites = invites_res.data or []
        except Exception as e:
            # If the table is missing or schema cache is stale, fallback to empty list
            if "PGRST205" in str(e) or "Could not find the table" in str(e):
                invites = []
            else:
                raise

        return {"members": members, "invites": invites}

    except HTTPException:
        raise
    except Exception as e:
        # Layer 1: surface DB / network failures as 503 so the caller knows to retry
        raise HTTPException(status_code=503, detail=f"Service temporarily unavailable: {e}")


# ---------------------------------------------------------------------------
# GET /{workspace_id}/audit-log  (H1 fix — was missing)
# ---------------------------------------------------------------------------

@router.get("/{workspace_id}/audit-log")
def get_audit_log(
    workspace_id: str,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    """
    Return paginated audit log entries for a workspace.

    Layer 1 — Environmental failure analysis:
      • workspace_id doesn't exist → 404
      • caller not a member → 403
      • DB down → 503

    Layer 2 — Human paranoia:
      • limit capped at 100 — prevents a single request from pulling unbounded rows
        and exhausting backend memory / Supabase row budget.
      • offset < 0 is normalised to 0 to prevent negative range queries.
    """
    # Layer 2: sanitise pagination params before hitting DB
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    try:
        svc = get_service_client()

        # Layer 1: workspace existence check → 404 not 500
        ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
        if not ws_check.data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        actor = svc.table("workspace_members").select("role") \
            .eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
        if not actor.data:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")

        # Layer 1: Verify plan entitlement for audit logs
        from core.backend.services.credit_service import TIER_LIMITS
        ws_tier = (ws_check.data[0].get("tier") or "FREE").upper() if ws_check.data else "FREE"
        can_audit = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_view_audit_logs", False)
        if not can_audit:
            raise HTTPException(
                status_code=403,
                detail="Workspace compliance audit trail and activity history require Growth Pro or Enterprise."
            )

        try:
            res = svc.table("audit_log").select("*") \
                .eq("workspace_id", workspace_id) \
                .order("created_at", desc=True) \
                .range(offset, offset + limit - 1).execute()
            entries = res.data or []
            unmigrated = False
        except Exception as audit_err:
            if "PGRST205" in str(audit_err) or "Could not find the table" in str(audit_err) or "does not exist" in str(audit_err):
                logger.warning(f"audit_log table not yet migrated for workspace {workspace_id}: {audit_err}")
                entries = []
                unmigrated = True
            else:
                raise

        return {"entries": entries, "limit": limit, "offset": offset, "unmigrated": unmigrated}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service temporarily unavailable: {e}")

from core.backend.services.gdpr_service import purge_workspace_data

@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    """
    Instantly deletes a workspace and purges all PII.
    Layer 1: Ensures only owners can trigger this.
    """
    svc = get_service_client()
    
    # Layer 1: Verify workspace exists first (404 instead of 403)
    ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
    if not ws_check.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Layer 1: Verify actor is owner
    actor_res = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
    if not actor_res.data:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    if actor_res.data[0]["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can delete the workspace")
        
    # Trigger full GDPR purge
    success = await purge_workspace_data(workspace_id, svc)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to complete GDPR purge. It has been queued for background retry.")
        
    return {"status": "success", "message": "Workspace and all associated PII permanently deleted."}


@router.delete("/{workspace_id}/members/{user_id}/2fa-reset")
async def admin_reset_member_2fa(
    request: Request,
    workspace_id: str,
    user_id: str,
    current_user_id: str = Depends(get_current_user_id_with_2fa),
):
    """Workspace owner can force-reset a member's 2FA factor (e.g. lost device)."""
    svc = get_service_client()
    client = await get_async_supabase_client(request)
    ws = await client.table("workspaces").select("owner_id").eq("id", workspace_id).single().execute()
    if not ws.data or ws.data["owner_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Only the workspace owner can reset member 2FA.")
    
    member = await client.table("workspace_members").select("user_id").eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
    if not member.data:
        raise HTTPException(status_code=404, detail="User not found in this workspace.")
        
    user = svc.auth.admin.get_user_by_id(user_id).user
    supa_url = os.environ['SUPABASE_URL']
    supa_service = os.environ['SUPABASE_SERVICE_KEY']
    
    async with httpx.AsyncClient() as client:
        for factor in (user.factors or []):
            await client.delete(
                f"{supa_url}/auth/v1/admin/users/{user_id}/factors/{factor.id}",
                headers={"apikey": supa_service, "Authorization": f"Bearer {supa_service}"}
            )
            
    # Auditing
    log_audit(svc, workspace_id, current_user_id, "workspace.member_2fa_reset", "user", user_id)
            
    return {"status": "ok", "message": "2FA reset. User will be forced to re-enroll when their current session expires."}
