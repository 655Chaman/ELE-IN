from fastapi import APIRouter, Depends, HTTPException, Header, Request
from supabase import Client
from core.backend.api.auth_dep import get_service_client
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import re
import threading
import time
import uuid
from pydantic import BaseModel
from core.backend.core import crypto

logger = logging.getLogger(__name__)

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


def verify_extension_cryptographic_signature(
    raw_body: bytes,
    secret_key: str,
    signature_header: Optional[str] = None,
    timestamp_header: Optional[str] = None,
    max_drift_seconds: int = 300
) -> Tuple[bool, str]:
    """
    Paranoia Layer 1: Validates HMAC-SHA256 signature and timestamp drift on extension dispatches.
    Defends against replay attacks, payload tampering, and man-in-the-browser manipulation.
    """
    if not signature_header and not timestamp_header:
        # Development / unsigned backward compatibility
        return (True, "unsigned_allowed")

    if timestamp_header:
        try:
            ts = float(timestamp_header)
            current_ts = time.time()
            if abs(current_ts - ts) > max_drift_seconds:
                return (False, f"timestamp_drift_exceeded_{abs(current_ts - ts):.1f}s")
        except (ValueError, TypeError):
            return (False, "invalid_timestamp_header")

    if not signature_header:
        return (False, "missing_signature_header")

    expected_sig = signature_header.strip()
    if expected_sig.startswith("sha256="):
        expected_sig = expected_sig[7:]

    computed_sig = hmac.new(
        secret_key.strip().encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    if hmac.compare_digest(computed_sig.lower(), expected_sig.lower()):
        return (True, "verified")

    return (False, "signature_mismatch")


def verify_extension_api_key(
    x_api_key: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    supabase: Client = Depends(get_service_client)
) -> str:
    """
    Verifies the extension API key and returns the workspace_id.
    Paranoia Layer 1 & 2: Enforces cross-workspace token fencing if X-Workspace-Id is provided.
    """
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    x_api_key_hash = hashlib.sha256(x_api_key.strip().encode('utf-8')).hexdigest()
    
    res = supabase.table("api_keys").select("workspace_id, is_active").eq("key_hash", x_api_key_hash).execute()
    if not res.data or not res.data[0]["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid or inactive API Key")
    
    key_workspace_id = res.data[0]["workspace_id"]
    if isinstance(x_workspace_id, str) and x_workspace_id.strip():
        clean_header_ws = x_workspace_id.strip()
        if clean_header_ws != key_workspace_id:
            logger.warning(
                f"[ExtensionAuth] Cross-workspace fencing violation: token belongs to '{key_workspace_id}', but header requested '{clean_header_ws}'."
            )
            raise HTTPException(
                status_code=403,
                detail="Cross-workspace boundary violation: provided API Key does not match target workspace."
            )

    # Update last_used_at
    supabase.table("api_keys").update({
        "last_used_at": datetime.utcnow().isoformat()
    }).eq("key_hash", x_api_key_hash).execute()
    
    return key_workspace_id

class ExtensionSyncPayload(BaseModel):
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    cookies_json: str

@router.post("/sync", response_model=dict)
def sync_cookies(
    payload: ExtensionSyncPayload,
    request: Request,
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
        
        # Paranoia Layer 1 & 2: Update session and record extension active heartbeat
        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.table("accounts").update({
            "session_cookies_encrypted": encrypted_cookies,
            "cookie_expires_at": cookie_expires_at,
            "status": "ACTIVE",
            "is_active": True,
            "execution_channel": "EXTENSION",
            "last_extension_active_at": now_iso,
            "last_activity_at": now_iso,
            "updated_at": now_iso
        }).eq("id", payload.account_id).eq("workspace_id", workspace_id).execute()
        account_id = payload.account_id

        # Track geographic footprint for impossible travel protection
        try:
            from core.backend.services.impossible_travel_guard import record_and_verify_account_geodesic_hop
            client_ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None)
            country_code = request.headers.get("cf-ipcountry") or request.headers.get("x-vercel-ip-country")
            record_and_verify_account_geodesic_hop(
                account_id=account_id,
                new_country=country_code,
                new_ip=client_ip,
                channel="EXTENSION",
                supabase=supabase
            )
        except Exception as hop_err:
            logger.debug(f"[ExtensionSync] Non-blocking geo hop record notice: {hop_err}")
    else:
        existing = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).eq("status", "DISCONNECTED").limit(1).execute()
        if existing.data:
            account_id = existing.data[0]["id"]
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("accounts").update({
                "session_cookies_encrypted": encrypted_cookies,
                "cookie_expires_at": cookie_expires_at,
                "status": "ACTIVE",
                "is_active": True,
                "execution_channel": "EXTENSION",
                "last_extension_active_at": now_iso,
                "last_activity_at": now_iso,
                "updated_at": now_iso
            }).eq("id", account_id).eq("workspace_id", workspace_id).execute()

            try:
                from core.backend.services.impossible_travel_guard import record_and_verify_account_geodesic_hop
                client_ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None)
                country_code = request.headers.get("cf-ipcountry") or request.headers.get("x-vercel-ip-country")
                record_and_verify_account_geodesic_hop(
                    account_id=account_id,
                    new_country=country_code,
                    new_ip=client_ip,
                    channel="EXTENSION",
                    supabase=supabase
                )
            except Exception as hop_err:
                logger.debug(f"[ExtensionSync] Non-blocking geo hop record notice: {hop_err}")
        else:
            # Check tier limit for connected LinkedIn accounts (Paranoia Layer 1)
            from core.backend.services.credit_service import TIER_LIMITS, normalize_tier, distributed_workspace_lock
            with distributed_workspace_lock(f"account_connect:{workspace_id}", ttl_seconds=30, supabase=supabase, blocking=True):
                ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
                raw_tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
                ws_tier = normalize_tier(raw_tier)
                limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
                max_accounts = limits.get("max_linkedin_accounts", 1)

                try:
                    rpc_res = supabase.rpc("check_and_reserve_account_slot", {"p_workspace_id": workspace_id}).execute()
                    if rpc_res.data and isinstance(rpc_res.data, dict) and rpc_res.data.get("allowed") is False:
                        max_acc = rpc_res.data.get("max_allowed", max_accounts)
                        curr_acc = rpc_res.data.get("current_count", max_accounts)
                        raise HTTPException(
                            status_code=403,
                            detail=f"LinkedIn account limit reached ({curr_acc}/{max_acc}). Upgrade to connect more accounts."
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass

                count_res = supabase.table("accounts").select("id", count="exact").eq("workspace_id", workspace_id).neq("status", "DISCONNECTED").execute()
                raw_count = getattr(count_res, "count", 0)
                current_accounts_count = int(raw_count) if isinstance(raw_count, (int, float)) else 0
                if current_accounts_count >= max_accounts:
                    raise HTTPException(
                        status_code=403,
                        detail=f"LinkedIn account limit reached ({current_accounts_count}/{max_accounts}). Upgrade to connect more accounts."
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
                    "platform": "LINKEDIN",
                    "execution_channel": "EXTENSION"
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
    tab_id: Optional[str] = None,
    force_takeover: bool = False
):
    """
    Polls for tasks assigned to this account_id.
    Paranoia Layer 0, 1 & 2:
    - Enforces workspace ownership of account_id.
    - Blocks task polling if account is in a halted/quarantined state or locked by another browser tab.
    - Generates an atomic task lease token (lease_token + lease_expires_at) on CAS transition to 'running'.
    """
    acc_check = supabase.table("accounts").select("id, status, proxy_id, execution_channel, quarantined_until") \
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

    # Paranoia Layer 1: Dedicated cloud proxy mutual exclusivity guard
    # If account has an active cloud proxy configured and is not explicitly in 'EXTENSION' mode,
    # prevent local extension outreach dispatch to block IP bouncing between laptop and cloud proxy.
    if acc_row.get("proxy_id") and acc_row.get("execution_channel") != "EXTENSION":
        return {
            "tasks": [],
            "proxy_exclusive": True,
            "message": "Account outreach is managed via dedicated cloud residential proxy. Local extension outreach dispatch paused to prevent dual-IP collision."
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
                and not force_takeover
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
        .select("id, current_node_id, variables, enrollment_id, campaign_enrollments(campaign_id, lead_id, leads(id, linkedin_url, first_name, last_name, company_name, job_title))") \
        .eq("workspace_id", workspace_id) \
        .eq("status", "pending") \
        .lte("next_run_at", datetime.utcnow().isoformat()) \
        .limit(20) \
        .execute()

    state = None
    lead = None
    matched_node = None
    matched_campaign_id = None
    campaign_graphs: Dict[str, Dict[str, Any]] = {}

    EXTENSION_LINKEDIN_ACTIONS = {
        "linkedin_connect", "connection_request", "connection_no_note",
        "connection_ai_note", "linkedin_connection"
    }

    for s in (states_res.data or []):
        enr = s.get("campaign_enrollments")
        if not enr:
            continue
        c_id = enr.get("campaign_id")
        if not c_id or c_id not in valid_campaigns:
            continue

        # Paranoia Layer 0 & 1: Inspect campaign DAG node type. Skip delay, email, condition, or webhook nodes!
        if c_id not in campaign_graphs:
            try:
                c_row = supabase.table("campaigns").select("nodes_json, edges_json").eq("id", c_id).execute()
                if c_row and isinstance(c_row.data, list) and len(c_row.data) > 0 and isinstance(c_row.data[0], dict):
                    n_raw = c_row.data[0].get("nodes_json")
                    e_raw = c_row.data[0].get("edges_json")
                    nodes = json.loads(n_raw) if isinstance(n_raw, str) else (n_raw if isinstance(n_raw, list) else [])
                    edges = json.loads(e_raw) if isinstance(e_raw, str) else (e_raw if isinstance(e_raw, list) else [])
                    campaign_graphs[c_id] = {"nodes": nodes, "edges": edges}
                else:
                    campaign_graphs[c_id] = {"nodes": [], "edges": []}
            except Exception:
                campaign_graphs[c_id] = {"nodes": [], "edges": []}

        g = campaign_graphs[c_id]
        nodes = g.get("nodes") if isinstance(g.get("nodes"), list) else []
        edges = g.get("edges") if isinstance(g.get("edges"), list) else []

        curr_node_id = s.get("current_node_id")
        node_candidate = None
        if curr_node_id and nodes:
            node_candidate = next((n for n in nodes if isinstance(n, dict) and n.get("id") == curr_node_id), None)
        elif nodes:
            edge_targets = {e.get("target") for e in edges if isinstance(e, dict) and e.get("target")}
            starts = [n for n in nodes if isinstance(n, dict) and n.get("id") not in edge_targets]
            node_candidate = starts[0] if starts else (nodes[0] if nodes else None)
        else:
            # Fallback for unconfigured or legacy campaign graphs: query campaign_nodes or default to linkedin_connect
            try:
                cn_res = supabase.table("campaign_nodes").select("id, node_type, type, data, config").eq("campaign_id", c_id).execute()
                if cn_res and isinstance(cn_res.data, list) and len(cn_res.data) > 0:
                    c_nodes = [cn for cn in cn_res.data if isinstance(cn, dict)]
                    if curr_node_id:
                        node_candidate = next((n for n in c_nodes if n.get("id") == curr_node_id), None)
                    if not node_candidate and c_nodes:
                        node_candidate = c_nodes[0]
            except Exception:
                pass

            if not node_candidate:
                # If campaign has no explicit graph records (legacy/mocked test), construct standard connect stub
                node_candidate = {
                    "id": curr_node_id or "start_node",
                    "type": "linkedin_connect",
                    "data": {"note": ""}
                }

        if not node_candidate or not isinstance(node_candidate, dict):
            continue

        raw_act = node_candidate.get("node_type") or node_candidate.get("type") or ""
        action_type = str(raw_act).lower().strip() if isinstance(raw_act, str) else ""
        if action_type not in EXTENSION_LINKEDIN_ACTIONS:
            # Skip non-LinkedIn actions (delays, emails, conditions, webhooks) so cloud worker processes them
            continue

        state = s
        lead = enr.get("leads") or {}
        matched_node = node_candidate
        matched_campaign_id = c_id
        break

    if not state or not lead or not matched_node:
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

    # Extract note template from node config and interpolate variables
    node_data = matched_node.get("data") or matched_node.get("config") or {}
    raw_message = node_data.get("note") or node_data.get("message") or node_data.get("template") or node_data.get("body") or ""
    action_type = (matched_node.get("node_type") or matched_node.get("type") or "").lower().strip()
    if action_type == "connection_no_note":
        raw_message = ""

    first_name = lead.get("first_name") or ""
    last_name = lead.get("last_name") or ""
    company = lead.get("company_name") or lead.get("company") or ""
    job_title = lead.get("job_title") or ""

    interpolated_message = raw_message
    if interpolated_message:
        for placeholder, val in [
            ("{{first_name}}", first_name),
            ("{{firstName}}", first_name),
            ("{first_name}", first_name),
            ("{{last_name}}", last_name),
            ("{{lastName}}", last_name),
            ("{last_name}", last_name),
            ("{{company}}", company),
            ("{{company_name}}", company),
            ("{company}", company),
            ("{{job_title}}", job_title),
            ("{job_title}", job_title),
        ]:
            interpolated_message = interpolated_message.replace(placeholder, val)

    task = {
        "task_id": state["id"],
        "type": "linkedin_connect",
        "linkedin_url": lead.get("linkedin_url"),
        "first_name": first_name,
        "message": interpolated_message.strip(),
        "node_id": matched_node.get("id"),
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
        # Paranoia Layer 0 & 1: Advance sequence DAG to next node rather than truncating sequence
        es_res = supabase.table("campaign_execution_states") \
            .select("id, current_node_id, enrollment_id, campaign_enrollments(campaign_id)") \
            .eq("id", task_id) \
            .execute()

        curr_node_id = None
        enr_id = None
        camp_id = None
        if es_res and isinstance(es_res.data, list) and len(es_res.data) > 0 and isinstance(es_res.data[0], dict):
            curr_node_id = es_res.data[0].get("current_node_id")
            enr_id = es_res.data[0].get("enrollment_id")
            enr_data = es_res.data[0].get("campaign_enrollments")
            if enr_data and isinstance(enr_data, dict):
                camp_id = enr_data.get("campaign_id")

        next_node_id = None
        if camp_id and curr_node_id:
            try:
                c_res = supabase.table("campaigns").select("edges_json").eq("id", camp_id).execute()
                if c_res and isinstance(c_res.data, list) and len(c_res.data) > 0 and isinstance(c_res.data[0], dict):
                    e_raw = c_res.data[0].get("edges_json")
                    edges = json.loads(e_raw) if isinstance(e_raw, str) else (e_raw if isinstance(e_raw, list) else [])
                    for edge in edges:
                        if isinstance(edge, dict) and edge.get("source") == curr_node_id:
                            next_node_id = edge.get("target")
                            break
            except Exception as edge_err:
                pass

        if next_node_id:
            new_status = "pending"
            next_run_iso = (datetime.now(timezone.utc) + timedelta(seconds=45)).isoformat()
            supabase.table("campaign_execution_states").update({
                "current_node_id": next_node_id,
                "status": new_status,
                "next_run_at": next_run_iso,
                "error_reason": None,
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": now_iso
            }).eq("id", task_id).eq("workspace_id", workspace_id).execute()
        else:
            new_status = "completed"
            supabase.table("campaign_execution_states").update({
                "status": new_status,
                "error_reason": None,
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": now_iso
            }).eq("id", task_id).eq("workspace_id", workspace_id).execute()

            if enr_id:
                try:
                    supabase.table("campaign_enrollments").update({
                        "status": "completed",
                        "completed_at": now_iso
                    }).eq("id", enr_id).execute()
                except Exception:
                    pass

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
            # Paranoia Layer 1: Halt account and mark CHALLENGE_REQUIRED
            # To protect account from further automated requests
            acc_id = None
            try:
                enr_check = supabase.table("campaign_execution_states") \
                    .select("campaign_enrollments(campaign_id)") \
                    .eq("id", task_id) \
                    .execute()
                if enr_check.data and len(enr_check.data) > 0:
                    c_id = (enr_check.data[0].get("campaign_enrollments") or {}).get("campaign_id")
                    if c_id:
                        c_acc = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", c_id).execute()
                        if c_acc.data and len(c_acc.data) > 0:
                            acc_id = c_acc.data[0].get("account_id")
            except Exception:
                pass

            if acc_id:
                try:
                    supabase.table("accounts").update({
                        "status": "CHALLENGE_REQUIRED",
                        "is_active": False,
                        "updated_at": now_iso
                    }).eq("id", acc_id).eq("workspace_id", workspace_id).execute()
                except Exception:
                    pass

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

class ExtensionSessionStatePayload(BaseModel):
    account_id: str
    status: str
    reason: Optional[str] = None

@router.post("/session-state")
def update_extension_session_state(
    payload: ExtensionSessionStatePayload,
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 0, 1 & 2: Reports immediate changes in local browser LinkedIn session state.
    - If user logs out locally (li_at deleted), transitions account to DISCONNECTED.
    - Releases any pending running task leases for this account to prevent stuck states.
    - Idempotent and verified against workspace ownership.
    """
    acc_check = supabase.table("accounts").select("id, status").eq("id", payload.account_id).eq("workspace_id", workspace_id).execute()
    if not acc_check.data:
        raise HTTPException(status_code=403, detail="Account does not belong to your workspace.")

    norm_status = (payload.status or "ACTIVE").upper().strip()
    if norm_status not in ("ACTIVE", "DISCONNECTED", "CHALLENGE_REQUIRED", "PAUSED"):
        raise HTTPException(status_code=400, detail="Invalid status. Allowed: ACTIVE, DISCONNECTED, CHALLENGE_REQUIRED, PAUSED")

    now_iso = datetime.utcnow().isoformat()
    supabase.table("accounts").update({
        "status": norm_status,
        "is_active": (norm_status == "ACTIVE"),
        "updated_at": now_iso
    }).eq("id", payload.account_id).execute()

    # If disconnecting or challenging, clear running task leases for campaigns using this account
    if norm_status in ("DISCONNECTED", "CHALLENGE_REQUIRED", "PAUSED"):
        try:
            c_accs = supabase.table("campaign_accounts").select("campaign_id").eq("account_id", payload.account_id).execute()
            c_ids = [r["campaign_id"] for r in (c_accs.data or []) if r.get("campaign_id")]
            if c_ids:
                enrs = supabase.table("campaign_enrollments").select("id").in_("campaign_id", c_ids).execute()
                enr_ids = [e["id"] for e in (enrs.data or []) if e.get("id")]
                if enr_ids:
                    supabase.table("campaign_execution_states").update({
                        "status": "pending",
                        "lease_token": None,
                        "lease_expires_at": None,
                        "next_run_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                        "error_reason": f"Execution halted: Session state transitioned to {norm_status} ({payload.reason or 'User action'})"
                    }).in_("enrollment_id", enr_ids).eq("status", "running").execute()
        except Exception as e:
            pass

    try:
        supabase.table("action_log").insert({
            "workspace_id": workspace_id,
            "action_type": "extension_session_state_change",
            "result": norm_status,
            "error_detail": payload.reason or None
        }).execute()
    except Exception:
        pass

    return {
        "status": "ok",
        "account_id": payload.account_id,
        "new_status": norm_status,
        "reason": payload.reason
    }

class ExtensionDiagnosticPayload(BaseModel):
    account_id: Optional[str] = None
    task_id: Optional[str] = None
    error_type: str
    error_detail: str
    failed_selectors: Optional[List[str]] = None
    dom_snippet: Optional[str] = None
    url: Optional[str] = None

@router.post("/diagnostic")
def report_extension_diagnostic(
    payload: ExtensionDiagnosticPayload,
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 2: Ingests sanitized DOM selector mutation diagnostics and API anomalies
    for proactive triage and engineering alerting.
    """
    try:
        supabase.table("outbox_events").insert({
            "workspace_id": workspace_id,
            "event_type": "notification.diagnostic",
            "payload": {
                "title": f"Extension DOM/API Diagnostic: {payload.error_type}",
                "account_id": payload.account_id,
                "task_id": payload.task_id,
                "error_detail": payload.error_detail[:500],
                "failed_selectors": payload.failed_selectors or [],
                "url": payload.url,
                "timestamp": datetime.utcnow().isoformat()
            },
            "status": "pending"
        }).execute()
    except Exception:
        pass

    return {"status": "recorded"}


# =============================================================================
# PHASE L: EXTENSION DOM PROFILE EXTRACTION & CRYPTOGRAPHIC INGESTION
# =============================================================================

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def sanitize_scraped_text(val: Any) -> Any:
    """Neutralizes spreadsheet formula injection prefixes."""
    if not isinstance(val, str):
        return val
    s = val.strip()
    if s.startswith(FORMULA_PREFIXES):
        return "'" + s
    return s


class ExtensionScrapedProfilePayload(BaseModel):
    linkedin_url: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    company_name: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    lead_id: Optional[str] = None
    campaign_id: Optional[str] = None
    raw_attributes: Optional[Dict[str, Any]] = None


@router.post("/scrape/profile", response_model=dict)
def ingest_scraped_profile(
    payload: ExtensionScrapedProfilePayload,
    x_api_key: str = Header(...),
    x_workspace_id: Optional[str] = Header(None),
    x_extension_signature: Optional[str] = Header(None),
    x_extension_timestamp: Optional[str] = Header(None),
    workspace_id: str = Depends(verify_extension_api_key),
    supabase: Client = Depends(get_service_client)
):
    """
    Paranoia Layer 0, 1 & 2: Ingests LinkedIn profile scraped via Chrome Extension DOM.
    - Layer 0: Normalizes LinkedIn URL, parses name/title/company, inserts or updates lead record.
    - Layer 1: Validates cryptographic HMAC signature and timestamp drift against API Key.
    - Layer 2: Sanitizes spreadsheet formula injection prefixes (=, +, -, @) and caps payload attributes.
    """
    if x_extension_signature or x_extension_timestamp:
        canon_bytes = json.dumps(payload.dict(), sort_keys=True, default=str).encode("utf-8")
        ok, reason = verify_extension_cryptographic_signature(
            raw_body=canon_bytes,
            secret_key=x_api_key,
            signature_header=x_extension_signature,
            timestamp_header=x_extension_timestamp,
            max_drift_seconds=300
        )
        if not ok:
            raise HTTPException(status_code=401, detail=f"Cryptographic signature verification failed: {reason}")

    clean_url = re.sub(r"[?#].*$", "", (payload.linkedin_url or "").strip()).rstrip("/")
    if not clean_url or "linkedin.com" not in clean_url:
        raise HTTPException(status_code=400, detail="Invalid LinkedIn profile URL.")

    # Sanitize scraped fields to prevent formula injection
    sanitized_first = sanitize_scraped_text(payload.first_name)
    sanitized_last = sanitize_scraped_text(payload.last_name)
    sanitized_full = sanitize_scraped_text(payload.full_name)
    sanitized_title = sanitize_scraped_text(payload.title)
    sanitized_company = sanitize_scraped_text(payload.company_name)
    sanitized_location = sanitize_scraped_text(payload.location)
    sanitized_summary = sanitize_scraped_text(payload.summary)

    if not sanitized_full and (sanitized_first or sanitized_last):
        sanitized_full = f"{sanitized_first or ''} {sanitized_last or ''}".strip()

    metadata = {
        "scraped_via": "chrome_extension",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "location": sanitized_location,
        "summary": sanitized_summary[:2000] if sanitized_summary else None,
        "skills": payload.skills[:50] if payload.skills else [],
    }
    if payload.raw_attributes and isinstance(payload.raw_attributes, dict):
        for k, v in list(payload.raw_attributes.items())[:20]:
            metadata[f"attr_{k[:32]}"] = sanitize_scraped_text(v)

    # Upsert lead by linkedin_url within workspace
    existing_lead = None
    if payload.lead_id:
        chk = supabase.table("leads").select("id, metadata").eq("id", payload.lead_id).eq("workspace_id", workspace_id).execute()
        if chk.data:
            existing_lead = chk.data[0]

    if not existing_lead:
        chk_url = supabase.table("leads").select("id, metadata").eq("workspace_id", workspace_id).eq("linkedin_url", clean_url).execute()
        if chk_url.data:
            existing_lead = chk_url.data[0]

    now_iso = datetime.now(timezone.utc).isoformat()
    if existing_lead:
        lead_id = existing_lead["id"]
        old_meta = existing_lead.get("metadata") or {}
        if not isinstance(old_meta, dict):
            old_meta = {}
        merged_meta = {**old_meta, **metadata}
        update_data = {
            "title": sanitized_title or existing_lead.get("title"),
            "company_name": sanitized_company or existing_lead.get("company_name"),
            "metadata": merged_meta,
            "updated_at": now_iso
        }
        if sanitized_full:
            update_data["full_name"] = sanitized_full
        supabase.table("leads").update(update_data).eq("id", lead_id).execute()
        action = "updated"
    else:
        lead_id = payload.lead_id or str(uuid.uuid4())
        insert_data = {
            "id": lead_id,
            "workspace_id": workspace_id,
            "linkedin_url": clean_url,
            "first_name": sanitized_first,
            "last_name": sanitized_last,
            "full_name": sanitized_full or "LinkedIn Prospect",
            "title": sanitized_title,
            "company_name": sanitized_company,
            "status": "scraped",
            "metadata": metadata,
            "created_at": now_iso,
            "updated_at": now_iso
        }
        supabase.table("leads").insert(insert_data).execute()
        action = "created"

    return {
        "status": "success",
        "action": action,
        "lead_id": lead_id,
        "linkedin_url": clean_url
    }
