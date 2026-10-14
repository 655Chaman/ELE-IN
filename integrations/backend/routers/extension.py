from fastapi import APIRouter, Depends, HTTPException, Header, Request
from supabase import Client
from core.backend.api.auth_dep import get_service_client
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
import time
import uuid
from pydantic import BaseModel
from core.backend.core import crypto

router = APIRouter()

MIN_SUPPORTED_EXTENSION_VERSION = "1.2.0"
EXTENSION_TASK_LEASE_TTL_SECONDS = 300  # 5 minutes
CONCURRENT_TAB_LOCK_TTL_SECONDS = 60    # 60 seconds active tab exclusivity window

_tab_locks_mutex = threading.Lock()
_active_extension_tabs: Dict[str, Dict[str, Any]] = {}  # account_id -> {"tab_id": str, "last_seen": float, "workspace_id": str}

CHALLENGE_ERROR_KEYWORDS = (
    "checkpoint",
    "challenge",
    "captcha",
    "security verification",
    "restricted",
    "http 999",
    "status 999",
    "logged out",
    "li_at expired",
    "account restricted",
)


def _parse_semver(version_str: Any) -> tuple:
    """Safely parses '1.2.3' into (1, 2, 3) for version comparison."""
    if not isinstance(version_str, str) or not version_str.strip():
        return (0, 0, 0)
    clean = version_str.strip().lstrip("vV").split("-")[0]
    parts = []
    for p in clean.split(".")[:3]:
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def clear_extension_tab_locks() -> None:
    """Clears in-memory extension tab locks (used in test suites and resets)."""
    with _tab_locks_mutex:
        _active_extension_tabs.clear()

def verify_extension_api_key(x_api_key: str = Header(...), supabase: Client = Depends(get_service_client)) -> str:
    """Verifies the extension API key and returns the workspace_id"""
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    x_api_key_hash = hashlib.sha256(x_api_key.strip().encode('utf-8')).hexdigest()
    
    res = supabase.table("api_keys").select("workspace_id, is_active").eq("key_hash", x_api_key_hash).execute()
    if not res.data or not res.data[0]["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid or inactive API Key")
    
    # Update last_used_at
    supabase.table("api_keys").update({
        "last_used_at": datetime.utcnow().isoformat()
    }).eq("key_hash", x_api_key_hash).execute()
    
    return res.data[0]["workspace_id"]

class ExtensionSyncPayload(BaseModel):
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    cookies_json: str

@router.post("/sync", response_model=dict)
def sync_cookies(
    payload: ExtensionSyncPayload,
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    try:
        cookies = json.loads(payload.cookies_json)
        if not cookies or not isinstance(cookies, list):
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cookies payload: must be a non-empty JSON list of cookies")

    has_li_at = any(isinstance(c, dict) and c.get("name") == "li_at" for c in cookies)
    if not has_li_at:
        raise HTTPException(status_code=400, detail="li_at cookie missing from LinkedIn session")

    encrypted_cookies_bytes = crypto.encrypt_bytes(payload.cookies_json.encode('utf-8'))
    encrypted_cookies = crypto.bytes_to_pg_hex(encrypted_cookies_bytes)

    # Calculate cookie expiration timestamp
    now_dt = datetime.now(timezone.utc)
    expires_at_ts = min([c.get("expires", 0) for c in cookies if isinstance(c, dict) and c.get("expires", 0) > 0], default=0)
    cookie_expires_at = datetime.fromtimestamp(expires_at_ts, timezone.utc).isoformat() if expires_at_ts > 0 else (now_dt + timedelta(days=90)).isoformat()

    if payload.account_id:
        acc_check = supabase.table("accounts").select("id").eq("id", payload.account_id).eq("workspace_id", workspace_id).execute()
        if not acc_check.data:
            raise HTTPException(status_code=403, detail="Account does not belong to your workspace.")
        
        supabase.table("accounts").update({
            "session_cookies_encrypted": encrypted_cookies,
            "cookie_expires_at": cookie_expires_at,
            "status": "ACTIVE",
            "is_active": True,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", payload.account_id).execute()
        account_id = payload.account_id
    else:
        existing = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).eq("status", "DISCONNECTED").limit(1).execute()
        if existing.data:
            account_id = existing.data[0]["id"]
            supabase.table("accounts").update({
                "session_cookies_encrypted": encrypted_cookies,
                "cookie_expires_at": cookie_expires_at,
                "status": "ACTIVE",
                "is_active": True,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", account_id).execute()
        else:
            # Check tier limit for connected LinkedIn accounts (Paranoia Layer 1)
            from core.backend.services.credit_service import TIER_LIMITS
            ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
            ws_tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
            limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
            max_accounts = limits.get("max_linkedin_accounts", 1)

            count_res = supabase.table("accounts").select("id", count="exact").eq("workspace_id", workspace_id).execute()
            raw_count = getattr(count_res, "count", 0)
            current_accounts_count = int(raw_count) if isinstance(raw_count, (int, float)) else 0
            if current_accounts_count >= max_accounts:
                raise HTTPException(
                    status_code=403,
                    detail=f"LinkedIn account limit reached ({current_accounts_count}/{max_accounts}). Upgrade to Growth Tier to connect more accounts."
                )

            account_id = str(uuid.uuid4())
            supabase.table("accounts").insert({
                "id": account_id,
                "workspace_id": workspace_id,
                "account_name": payload.account_name or "LinkedIn Sender",
                "session_cookies_encrypted": encrypted_cookies,
                "cookie_expires_at": cookie_expires_at,
                "status": "ACTIVE",
                "is_active": True,
                "platform": "LINKEDIN"
            }).execute()

    return {"status": "ok", "account_id": account_id, "message": "LinkedIn account successfully synced and encrypted"}

@router.post("/heartbeat")
def extension_heartbeat(
    payload: Dict[str, Any],
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Called by the Chrome Extension every 5 minutes to report that the browser is alive.
    Paranoia Layer 1 & 2:
    - Validates account ownership (IDOR defense).
    - Checks minimum supported extension version when extension_version is provided.
    - Detects concurrent browser tabs/profiles controlling the same LinkedIn account.
    """
    if not isinstance(payload, dict):
        payload = {}

    account_id = payload.get("account_id")
    if account_id:
        # SECURITY HIGH-7a: Verify account_id belongs to the authenticated workspace
        acc_check = supabase.table("accounts").select("id") \
            .eq("id", account_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
        if not acc_check.data:
            raise HTTPException(status_code=403, detail="account_id does not belong to your workspace.")

    # Layer 2 Human Paranoia: Outdated extension version guard
    ext_version = payload.get("extension_version")
    if isinstance(ext_version, str) and ext_version.strip():
        if _parse_semver(ext_version) < _parse_semver(MIN_SUPPORTED_EXTENSION_VERSION):
            return {
                "status": "upgrade_required",
                "min_version": MIN_SUPPORTED_EXTENSION_VERSION,
                "current_version": ext_version.strip(),
                "message": f"Chrome Extension v{ext_version.strip()} is outdated. Minimum required version is v{MIN_SUPPORTED_EXTENSION_VERSION}."
            }

    # Layer 1 & 2: Concurrent Tab / Multi-Profile Collision Detection
    tab_id = payload.get("tab_id")
    force_takeover = bool(payload.get("force_takeover", False))
    if account_id and isinstance(tab_id, str) and tab_id.strip():
        clean_tab_id = tab_id.strip()
        now_mono = time.monotonic()
        with _tab_locks_mutex:
            existing_lock = _active_extension_tabs.get(account_id)
            if (
                existing_lock
                and existing_lock.get("tab_id") != clean_tab_id
                and (now_mono - existing_lock.get("last_seen", 0.0)) < CONCURRENT_TAB_LOCK_TTL_SECONDS
                and not force_takeover
            ):
                return {
                    "status": "conflict",
                    "concurrent_tab_detected": True,
                    "active_tab_id": existing_lock.get("tab_id"),
                    "message": "Another browser tab or Chrome profile is actively controlling this LinkedIn account."
                }
            _active_extension_tabs[account_id] = {
                "tab_id": clean_tab_id,
                "last_seen": now_mono,
                "workspace_id": workspace_id,
            }

    worker_id = f"ext-{account_id}" if account_id else f"ext-ws-{workspace_id}"

    try:
        supabase.table("worker_heartbeat").upsert({
            "worker_id": worker_id,
            "last_beat_at": datetime.utcnow().isoformat(),
            "status": "alive"
        }).execute()
    except Exception:
        # Layer 1 Environmental Guard: DB heartbeat table transient error
        pass

    return {"status": "ok"}

@router.get("/tasks")
def get_extension_tasks(
    account_id: str,
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client),
    tab_id: Optional[str] = None
):
    """
    Polls for tasks assigned to this account_id.
    Paranoia Layer 0, 1 & 2:
    - Enforces workspace ownership of account_id.
    - Blocks task polling if account is in a halted/quarantined state or locked by another browser tab.
    - Generates an atomic task lease token (lease_token + lease_expires_at) on CAS transition to 'running'.
    """
    acc_check = supabase.table("accounts").select("id, status, quarantined_until") \
        .eq("id", account_id) \
        .eq("workspace_id", workspace_id) \
        .execute()
    if not acc_check.data:
        raise HTTPException(status_code=403, detail="account_id does not belong to your workspace.")

    acc_row = acc_check.data[0] if isinstance(acc_check.data[0], dict) else {}
    acc_status = acc_row.get("status")
    if isinstance(acc_status, str) and acc_status.upper() in ("DISCONNECTED", "CHALLENGE_REQUIRED", "BANNED", "RESTRICTED"):
        return {
            "tasks": [],
            "account_halted": True,
            "reason": f"Account status is {acc_status.upper()}"
        }

    # Concurrent tab lock check when tab_id is provided
    if isinstance(tab_id, str) and tab_id.strip():
        clean_tab_id = tab_id.strip()
        now_mono = time.monotonic()
        with _tab_locks_mutex:
            existing_lock = _active_extension_tabs.get(account_id)
            if (
                existing_lock
                and existing_lock.get("tab_id") != clean_tab_id
                and (now_mono - existing_lock.get("last_seen", 0.0)) < CONCURRENT_TAB_LOCK_TTL_SECONDS
            ):
                return {
                    "tasks": [],
                    "concurrent_tab_blocked": True,
                    "active_tab_id": existing_lock.get("tab_id"),
                }
            _active_extension_tabs[account_id] = {
                "tab_id": clean_tab_id,
                "last_seen": now_mono,
                "workspace_id": workspace_id,
            }

    # 1. Get campaigns using this account_id
    camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).execute()
    valid_campaigns = []
    for c in (camp_res.data or []):
        try:
            acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", c["id"]).execute()
            senders = [r["account_id"] for r in (acc_res.data or [])]
        except Exception:
            senders = []
        if account_id in senders:
            valid_campaigns.append(c["id"])

    if not valid_campaigns:
        return {"tasks": []}

    # 2. Get pending execution states for this workspace
    states_res = supabase.table("campaign_execution_states") \
        .select("id, current_node_id, variables, enrollment_id, campaign_enrollments(campaign_id, lead_id, leads(linkedin_url, first_name))") \
        .eq("workspace_id", workspace_id) \
        .eq("status", "pending") \
        .lte("next_run_at", datetime.utcnow().isoformat()) \
        .limit(20) \
        .execute()

    state = None
    lead = None
    for s in (states_res.data or []):
        enr = s.get("campaign_enrollments")
        if enr and enr.get("campaign_id") in valid_campaigns:
            state = s
            lead = enr.get("leads")
            break

    if not state or not lead:
        return {"tasks": []}

    # Mark it as 'running' with a dedicated lease_token so no other worker or zombie tab conflicts
    lease_token = f"ext_{uuid.uuid4().hex}"
    now_utc = datetime.now(timezone.utc)
    lease_expires_at = (now_utc + timedelta(seconds=EXTENSION_TASK_LEASE_TTL_SECONDS)).isoformat()

    upd_res = supabase.table("campaign_execution_states") \
        .update({
            "status": "running",
            "lease_token": lease_token,
            "lease_expires_at": lease_expires_at,
            "updated_at": now_utc.isoformat()
        }) \
        .eq("id", state["id"]) \
        .eq("workspace_id", workspace_id) \
        .eq("status", "pending") \
        .execute()
    if not upd_res.data:
        return {"tasks": []}

    task = {
        "task_id": state["id"],
        "type": "linkedin_connect",
        "linkedin_url": lead.get("linkedin_url"),
        "first_name": lead.get("first_name"),
        "message": f"Hi {lead.get('first_name', '')}, I'd love to connect!",
        "lease_token": lease_token,
        "lease_expires_at": lease_expires_at,
    }

    return {"tasks": [task]}

@router.post("/tasks/{task_id}/result")
def report_task_result(
    task_id: str,
    payload: Dict[str, Any],
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Called by the Chrome Extension after executing a task.
    Paranoia Layer 0, 1 & 2:
    - Enforces workspace ownership (403 on foreign task_id).
    - Idempotent handling of duplicate result submissions ('already_completed').
    - Ignores zombie tab results if task was already paused or cancelled.
    - Validates lease_token when present to block stale/hijacked worker writes (409).
    - Auto-halts and alerts on LinkedIn security challenge / checkpoint errors.
    """
    if not isinstance(payload, dict):
        payload = {}

    ls_res = supabase.table("campaign_execution_states") \
        .select("workspace_id, status, lease_token, lease_expires_at") \
        .eq("id", task_id) \
        .execute()
    if not ls_res.data or ls_res.data[0].get("workspace_id") != workspace_id:
        raise HTTPException(status_code=403, detail="Task does not belong to your workspace.")

    task_row = ls_res.data[0] if isinstance(ls_res.data[0], dict) else {}
    current_status = task_row.get("status")

    # Layer 1 & 2: Idempotency & Terminal State Protection
    if isinstance(current_status, str):
        norm_curr = current_status.strip().lower()
        if norm_curr in ("completed", "exited"):
            return {"status": "already_completed", "idempotent": True}
        if norm_curr in ("paused", "cancelled"):
            return {"status": "ignored_terminal_state", "current_status": norm_curr}

    # Layer 1 & 2: Zombie Lease Token Verification
    db_lease = task_row.get("lease_token")
    req_lease = payload.get("lease_token")
    if isinstance(db_lease, str) and db_lease.strip() and req_lease is not None:
        if str(req_lease).strip() != db_lease.strip():
            raise HTTPException(
                status_code=409,
                detail="Stale or mismatched task lease token. Another worker or tab now owns this task."
            )

    status = payload.get("status", "error")
    error_detail = str(payload.get("error_detail") or "").strip()
    now_iso = datetime.utcnow().isoformat()

    if status == "success":
        new_status = "completed"
        supabase.table("campaign_execution_states").update({
            "status": new_status,
            "error_reason": None,
            "lease_token": None,
            "lease_expires_at": None,
            "updated_at": now_iso
        }).eq("id", task_id).eq("workspace_id", workspace_id).execute()

        supabase.table("action_log").insert({
            "workspace_id": workspace_id,
            "execution_state_id": task_id,
            "action_type": "extension_execution",
            "result": "success"
        }).execute()

    else:
        error_lower = error_detail.lower()
        is_security_challenge = any(kw in error_lower for kw in CHALLENGE_ERROR_KEYWORDS)
        if is_security_challenge:
            new_status = "paused"
            reason_msg = f"Security challenge detected by extension: {error_detail[:200]}"
        else:
            new_status = "error"
            reason_msg = error_detail

        supabase.table("campaign_execution_states").update({
            "status": new_status,
            "error_reason": reason_msg,
            "lease_token": None,
            "lease_expires_at": None,
            "updated_at": now_iso
        }).eq("id", task_id).eq("workspace_id", workspace_id).execute()

        supabase.table("action_log").insert({
            "workspace_id": workspace_id,
            "execution_state_id": task_id,
            "action_type": "extension_execution",
            "result": "failed",
            "error_detail": error_detail
        }).execute()

        if is_security_challenge:
            try:
                supabase.table("outbox_events").insert({
                    "workspace_id": workspace_id,
                    "event_type": "notification.in_app",
                    "payload": {
                        "title": "LinkedIn Extension Security Challenge Detected",
                        "body": f"Task {task_id} encountered a LinkedIn checkpoint/challenge ({error_detail[:120]}). Execution has been paused automatically.",
                        "message": f"Task {task_id} encountered a LinkedIn checkpoint/challenge ({error_detail[:120]}). Execution has been paused automatically.",
                        "event_type": "account.security_challenge"
                    },
                    "status": "pending"
                }).execute()
            except Exception:
                pass

    return {"status": "ok", "task_status": new_status}
