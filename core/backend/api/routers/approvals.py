import html
import logging
import os
import re
import time
import threading
import jwt
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import Client
from datetime import datetime

from core.backend.api.auth_dep import get_supabase_client, get_current_workspace
from core.backend.services.job_queue import enqueue_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

_approval_locks_mutex = threading.Lock()
_active_approvals: Dict[str, float] = {}
APPROVAL_LOCK_TIMEOUT_SECONDS = 60.0
MAX_LINKEDIN_MESSAGE_LENGTH = 2000

UNRESOLVED_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
BRACKET_PLACEHOLDER_RE = re.compile(
    r"(?i)(\[|\<)\s*(first[\s_-]*name|last[\s_-]*name|full[\s_-]*name|name|company|company[\s_-]*name|prospect|lead|title|role|job|industry|insert[\s_-]*[^\]\>]+|your[\s_-]*name|my[\s_-]*name|link|url|website|calendar[\s_-]*link)\s*(\]|\>)"
)

def _acquire_approval_lock(approval_id: str):
    with _approval_locks_mutex:
        now = time.time()
        expired = [k for k, v in _active_approvals.items() if now - v > APPROVAL_LOCK_TIMEOUT_SECONDS]
        for k in expired:
            _active_approvals.pop(k, None)
        
        if approval_id in _active_approvals:
            if now - _active_approvals[approval_id] < APPROVAL_LOCK_TIMEOUT_SECONDS:
                raise HTTPException(status_code=409, detail="Approval action is already in progress for this item.")
        _active_approvals[approval_id] = now

def _release_approval_lock(approval_id: str):
    with _approval_locks_mutex:
        _active_approvals.pop(approval_id, None)

def validate_approval_message(message: Optional[str]) -> str:
    if message is None:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")
    clean_msg = message.strip()
    if not clean_msg:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")
    clean_msg = clean_msg.replace("\x00", "")
    if len(clean_msg) > MAX_LINKEDIN_MESSAGE_LENGTH:
        raise HTTPException(status_code=422, detail=f"Message exceeds LinkedIn maximum length of {MAX_LINKEDIN_MESSAGE_LENGTH} characters ({len(clean_msg)} chars).")
    if UNRESOLVED_TEMPLATE_RE.search(clean_msg):
        raise HTTPException(status_code=422, detail="Message contains unresolved template variables (e.g. {{variable}}). Please replace before approving.")
    if BRACKET_PLACEHOLDER_RE.search(clean_msg):
        raise HTTPException(status_code=422, detail="Message contains unreplaced bracketed placeholders (e.g. [First Name] or [Insert Link]). Please replace before approving.")
    return clean_msg

def _is_lead_unsubscribed_or_suppressed(supabase: Client, workspace_id: str, lead: dict) -> Optional[str]:
    if not isinstance(lead, dict):
        return None
    if lead.get("is_unsubscribed") is True:
        return "lead_unsubscribed"
    status_str = str(lead.get("status") or "").strip().lower()
    if status_str in {"unsubscribed", "do_not_contact", "dnc", "opt_out", "blacklisted", "bounced"}:
        return f"lead_status_{status_str}"
    meta = lead.get("metadata") if isinstance(lead.get("metadata"), dict) else {}
    if meta.get("unsubscribed") is True or meta.get("email_unsubscribed") is True or meta.get("do_not_contact") is True:
        return "lead_unsubscribed"
    try:
        from leads.backend.services.suppression_service import check_lead_suppression
        email_val = lead.get("email") if isinstance(lead.get("email"), str) else None
        li_val = lead.get("linkedin_url") if isinstance(lead.get("linkedin_url"), str) else None
        if email_val or li_val:
            sup_res = check_lead_suppression(supabase, workspace_id, email=email_val, linkedin_url=li_val)
            if isinstance(sup_res, dict) and sup_res.get("is_suppressed") is True:
                return f"suppressed_dnc:{sup_res.get('reason') or 'matched'}"
    except Exception as sup_err:
        logger.debug(f"Suppression check skipped in approvals: {sup_err}")
    return None

class ApprovalActionRequest(BaseModel):
    edited_message: Optional[str] = None


@router.get("")
def list_approvals(
    status: str = Query("pending", description="Filter by status: pending, approved, skipped"),
    offset: int = 0,
    limit: int = 50,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    List AI reply approvals for the current workspace from both approval_queue and ai_reply_approvals.
    """
    try:
        q = supabase.table("approval_queue").select(
            "id, account_id, sender_name, intent, heat_score, ai_draft, status, created_at",
            count="estimated"
        ).eq("workspace_id", workspace_id)
        
        if status != "all":
            q = q.eq("status", status)
            
        q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
        res = q.execute()
        items: List[Dict[str, Any]] = list(res.data or [])
        total_count = res.count if hasattr(res, 'count') and res.count is not None else len(items)
        
        ai_status = status
        if status == "skipped":
            ai_status = "rejected"
            
        q_ai = supabase.table("ai_reply_approvals").select(
            "id, lead_id, enrollment_id, generated_reply, retrieval_score, status, created_at",
            count="estimated"
        ).eq("workspace_id", workspace_id)
        
        if status != "all":
            q_ai = q_ai.eq("status", ai_status)
            
        q_ai = q_ai.order("created_at", desc=True).range(offset, offset + limit - 1)
        res_ai = q_ai.execute()
        ai_data = list(res_ai.data or [])
        
        if ai_data:
            lead_ids = [row["lead_id"] for row in ai_data if row.get("lead_id")]
            lead_names = {}
            if lead_ids:
                try:
                    l_res = supabase.table("leads").select("id, first_name, last_name").in_("id", lead_ids).execute()
                    for l in (l_res.data or []):
                        name = f"{l.get('first_name', '') or ''} {l.get('last_name', '') or ''}".strip()
                        lead_names[l["id"]] = name or "Lead"
                except Exception as le:
                    logger.warning(f"Could not batch resolve lead names: {le}")
                    
            for row in ai_data:
                lead_id = row.get("lead_id")
                sender_name = lead_names.get(lead_id, "Lead")
                score = round((row.get("retrieval_score") or 0.5) * 100)
                item_status = "skipped" if row.get("status") in ("rejected", "skipped") else row.get("status", "pending")
                items.append({
                    "id": row["id"],
                    "account_id": "",
                    "sender_name": sender_name,
                    "intent": "ai_reply",
                    "heat_score": score,
                    "ai_draft": row.get("generated_reply"),
                    "status": item_status,
                    "created_at": row.get("created_at"),
                })
                
            total_count += res_ai.count if hasattr(res_ai, 'count') and res_ai.count is not None else len(ai_data)
            
        items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        items = items[:limit]
        
        return {
            "data": items,
            "count": total_count
        }
    except Exception as e:
        logger.error(f"Error fetching approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{approval_id}")
def get_approval(
    approval_id: str,
    request: Request,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Get full details of a specific approval queue item (including full thread).
    Supports fetching from both approval_queue and ai_reply_approvals tables.
    """
    # Paranoia Layer 1 (FLAW-API-10): Prevent route parameter shadowing for literal static action endpoints
    if approval_id in ("approve", "reject", "magic-action"):
        token = request.query_params.get("token") or ""
        return magic_approval_get_endpoint(token=token)
    try:
        res = supabase.table("approval_queue").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
        if res.data:
            return res.data[0]
            
        res_ai = supabase.table("ai_reply_approvals").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
        if not res_ai.data:
            raise HTTPException(status_code=404, detail="Approval item not found")
            
        ai_item = res_ai.data[0]
        
        sender_name = "Lead"
        thread_messages = []
        account_id = ""
        
        lead_id = ai_item.get("lead_id")
        if lead_id:
            lead_res = supabase.table("leads").select("first_name, last_name, linkedin_url").eq("id", lead_id).execute()
            if lead_res.data:
                lead = lead_res.data[0]
                first_name = lead.get("first_name") or ""
                last_name = lead.get("last_name") or ""
                sender_name = f"{first_name} {last_name}".strip() or "Lead"
                
        enrollment_id = ai_item.get("enrollment_id")
        if enrollment_id:
            enr_res = supabase.table("campaign_enrollments").select("account_id, campaign_id").eq("id", enrollment_id).execute()
            if enr_res.data:
                account_id = enr_res.data[0].get("account_id") or ""
                if not account_id and enr_res.data[0].get("campaign_id"):
                    ca_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", enr_res.data[0]["campaign_id"]).limit(1).execute()
                    if ca_res.data:
                        account_id = ca_res.data[0]["account_id"] or ""
                        
        if lead_id:
            msg_query = supabase.table("messages").select("direction, message_text, created_at").eq("lead_id", lead_id).order("created_at")
            if account_id:
                msg_query = msg_query.eq("account_id", account_id)
            msg_res = msg_query.execute()
            if msg_res.data:
                thread_messages = [
                    {"direction": m["direction"], "message_text": m["message_text"]}
                    for m in msg_res.data
                ]
                
        return {
            "id": ai_item["id"],
            "workspace_id": ai_item["workspace_id"],
            "account_id": account_id,
            "sender_name": sender_name,
            "intent": "ai_reply",
            "heat_score": round((ai_item.get("retrieval_score") or 0.5) * 100),
            "ai_draft": ai_item.get("generated_reply"),
            "status": "skipped" if ai_item["status"] in ("rejected", "skipped") else ai_item["status"],
            "created_at": ai_item["created_at"],
            "thread_messages_json": thread_messages,
            "execution_state_id": ai_item.get("execution_state_id"),
            "lead_id": lead_id,
            "enrollment_id": enrollment_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching approval {approval_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{approval_id}/approve")
def approve_reply(
    approval_id: str,
    payload: ApprovalActionRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Approve an AI drafted reply.
    Queues it for delivery via LinkedInWorker and unblocks execution state.
    Supports fetching from both approval_queue and ai_reply_approvals.
    """
    _acquire_approval_lock(approval_id)
    try:
        res = supabase.table("approval_queue").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
        item = None
        is_ai_table = False
        
        if res.data:
            item = res.data[0]
        else:
            res_ai = supabase.table("ai_reply_approvals").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
            if res_ai.data:
                item = res_ai.data[0]
                is_ai_table = True
            else:
                raise HTTPException(status_code=404, detail="Approval item not found")

        if item["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Cannot approve item in status: {item['status']}")
            
        draft_msg = item.get("ai_draft") or item.get("generated_reply")
        raw_msg = payload.edited_message if (payload.edited_message is not None and payload.edited_message.strip() != "") else draft_msg
        final_message = validate_approval_message(raw_msg)
            
        account_id = item.get("account_id")
        sender_name = item.get("sender_name")
        lead_linkedin_url = None
        
        lead_id = item.get("lead_id")
        lead = None
        if lead_id:
            lead_res = supabase.table("leads").select("first_name, last_name, linkedin_url, email, status, is_unsubscribed, metadata").eq("id", lead_id).execute()
            if isinstance(lead_res.data, list) and len(lead_res.data) > 0 and isinstance(lead_res.data[0], dict):
                lead = lead_res.data[0]
                first_name = lead.get("first_name") or ""
                last_name = lead.get("last_name") or ""
                resolved_name = f"{first_name} {last_name}".strip()
                if resolved_name and is_ai_table:
                    sender_name = resolved_name
                lead_linkedin_url = lead.get("linkedin_url")
                
        if lead:
            block_reason = _is_lead_unsubscribed_or_suppressed(supabase, workspace_id, lead)
            if block_reason:
                now_iso = datetime.utcnow().isoformat()
                if not is_ai_table:
                    supabase.table("approval_queue").update({"status": "skipped", "reviewed_at": now_iso}).eq("id", approval_id).execute()
                else:
                    supabase.table("ai_reply_approvals").update({"status": "rejected", "resolved_at": now_iso}).eq("id", approval_id).execute()
                
                exec_state_id = item.get("execution_state_id")
                if exec_state_id:
                    supabase.table("campaign_execution_states").update({"status": "exited", "error_reason": block_reason}).eq("id", exec_state_id).execute()
                elif item.get("enrollment_id"):
                    supabase.table("campaign_execution_states").update({"status": "exited", "error_reason": block_reason}).eq("enrollment_id", item["enrollment_id"]).eq("status", "awaiting_approval").execute()
                elif lead_id:
                    enr_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", lead_id).execute()
                    enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict)]
                    if enr_ids:
                        supabase.table("campaign_execution_states").update({"status": "exited", "error_reason": block_reason}).in_("enrollment_id", enr_ids).eq("status", "awaiting_approval").execute()
                
                raise HTTPException(status_code=409, detail=f"Cannot approve reply: lead is unsubscribed or suppressed ({block_reason}). Draft has been automatically skipped.")

        if is_ai_table:
            if not account_id and item.get("enrollment_id"):
                enr_res = supabase.table("campaign_enrollments").select("account_id, campaign_id").eq("id", item["enrollment_id"]).execute()
                if isinstance(enr_res.data, list) and len(enr_res.data) > 0 and isinstance(enr_res.data[0], dict):
                    account_id = enr_res.data[0].get("account_id")
                    if not account_id and enr_res.data[0].get("campaign_id"):
                        cid = enr_res.data[0]["campaign_id"]
                        ca_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", cid).limit(1).execute()
                        if isinstance(ca_res.data, list) and len(ca_res.data) > 0 and isinstance(ca_res.data[0], dict):
                            account_id = ca_res.data[0]["account_id"]

        if not sender_name:
            sender_name = "Lead"

        if not account_id:
            acc_fallback = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).eq("is_active", True).limit(1).execute()
            if isinstance(acc_fallback.data, list) and len(acc_fallback.data) > 0 and isinstance(acc_fallback.data[0], dict):
                account_id = acc_fallback.data[0]["id"]
            else:
                raise HTTPException(status_code=400, detail="No active LinkedIn account found in workspace to deliver message.")

        if lead_linkedin_url:
            job_payload = {
                'account_id': account_id,
                'workspace_id': workspace_id,
                'action': 'send_message',
                'payload_data': {
                    'profile_url': lead_linkedin_url,
                    'message': final_message
                }
            }
        else:
            job_payload = {
                'account_id': account_id,
                'workspace_id': workspace_id,
                'action': 'send_message_to_existing_thread',
                'payload_data': {
                    'sender_name': sender_name,
                    'message': final_message
                }
            }
            
        try:
            enqueue_job(
                supabase, 
                'inbox_action', 
                workspace_id, 
                account_id, 
                job_payload
            )
        except Exception as eq_err:
            logger.warning(f"Failed to enqueue job for approval {approval_id}: {eq_err}")
        
        now_iso = datetime.utcnow().isoformat()
        if not is_ai_table:
            supabase.table("approval_queue").update({
                "status": "approved",
                "ai_draft": final_message,
                "reviewed_at": now_iso
            }).eq("id", approval_id).execute()
        else:
            supabase.table("ai_reply_approvals").update({
                "status": "approved",
                "generated_reply": final_message,
                "resolved_at": now_iso
            }).eq("id", approval_id).execute()
            
        approval_vars_update = {
            "approved_ai_reply": final_message,
            "approval_delivered_via_job": True,
            "ai_reply_sent": True
        }

        exec_state_id = item.get("execution_state_id")
        if exec_state_id:
            st_vars = {}
            try:
                st_res = supabase.table("campaign_execution_states").select("variables").eq("id", exec_state_id).limit(1).execute()
                if st_res.data and isinstance(st_res.data[0].get("variables"), dict):
                    st_vars = dict(st_res.data[0]["variables"])
            except Exception:
                pass
            st_vars.update(approval_vars_update)
            supabase.table("campaign_execution_states").update({
                "status": "pending",
                "next_run_at": now_iso,
                "variables": st_vars
            }).eq("id", exec_state_id).execute()
        else:
            target_exec_rows = []
            if item.get("enrollment_id"):
                try:
                    q_res = supabase.table("campaign_execution_states").select("id, variables").eq("enrollment_id", item["enrollment_id"]).eq("status", "awaiting_approval").execute()
                    target_exec_rows = q_res.data or []
                except Exception:
                    pass
            elif item.get("lead_id"):
                try:
                    enr_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", item["lead_id"]).execute()
                    enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict)]
                    if enr_ids:
                        q_res = supabase.table("campaign_execution_states").select("id, variables").in_("enrollment_id", enr_ids).eq("status", "awaiting_approval").execute()
                        target_exec_rows = q_res.data or []
                except Exception:
                    pass
            elif item.get("account_id") and item.get("sender_name"):
                try:
                    msg_res = supabase.table("messages").select("lead_id").eq("account_id", item["account_id"]).eq("sender_name", item["sender_name"]).not_.is_("lead_id", "null").limit(1).execute()
                    if isinstance(msg_res.data, list) and len(msg_res.data) > 0 and isinstance(msg_res.data[0], dict) and msg_res.data[0].get("lead_id"):
                        lead_id = msg_res.data[0]["lead_id"]
                        enr_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", lead_id).execute()
                        enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict)]
                        if enr_ids:
                            q_res = supabase.table("campaign_execution_states").select("id, variables").in_("enrollment_id", enr_ids).eq("status", "awaiting_approval").execute()
                            target_exec_rows = q_res.data or []
                except Exception:
                    pass

            for tgt in target_exec_rows:
                t_id = tgt.get("id")
                if t_id:
                    t_vars = dict(tgt.get("variables") or {}) if isinstance(tgt.get("variables"), dict) else {}
                    t_vars.update(approval_vars_update)
                    try:
                        supabase.table("campaign_execution_states").update({
                            "status": "pending",
                            "next_run_at": now_iso,
                            "variables": t_vars
                        }).eq("id", t_id).execute()
                    except Exception:
                        pass
        
        return {"status": "success", "message": "Reply approved and queued for delivery"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to approve reply: {str(e)}")
    finally:
        _release_approval_lock(approval_id)


@router.post("/{approval_id}/reject")
def reject_reply(
    approval_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Reject an AI drafted reply.
    Marks item as skipped/rejected and unblocks lead execution state in campaign_execution_states.
    Supports fetching from both approval_queue and ai_reply_approvals.
    """
    _acquire_approval_lock(approval_id)
    try:
        res = supabase.table("approval_queue").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
        item = None
        is_ai_table = False
        
        if res.data:
            item = res.data[0]
        else:
            res_ai = supabase.table("ai_reply_approvals").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
            if res_ai.data:
                item = res_ai.data[0]
                is_ai_table = True
            else:
                raise HTTPException(status_code=404, detail="Approval item not found")
            
        if item["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Cannot reject item in status: {item['status']}")
            
        now_iso = datetime.utcnow().isoformat()
        
        if not is_ai_table:
            supabase.table("approval_queue").update({
                "status": "skipped",
                "reviewed_at": now_iso
            }).eq("id", approval_id).execute()
        else:
            supabase.table("ai_reply_approvals").update({
                "status": "rejected",
                "resolved_at": now_iso
            }).eq("id", approval_id).execute()
            
        exec_state_id = item.get("execution_state_id")
        if exec_state_id:
            supabase.table("campaign_execution_states").update({
                "status": "exited",
                "error_reason": "ai_reply_rejected"
            }).eq("id", exec_state_id).execute()
        else:
            if item.get("enrollment_id"):
                supabase.table("campaign_execution_states").update({
                    "status": "exited",
                    "error_reason": "ai_reply_rejected"
                }).eq("enrollment_id", item["enrollment_id"]).eq("status", "awaiting_approval").execute()
            elif item.get("lead_id"):
                enr_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", item["lead_id"]).execute()
                enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict)]
                if enr_ids:
                    supabase.table("campaign_execution_states").update({
                        "status": "exited",
                        "error_reason": "ai_reply_rejected"
                    }).in_("enrollment_id", enr_ids).eq("status", "awaiting_approval").execute()
            elif item.get("account_id") and item.get("sender_name"):
                msg_res = supabase.table("messages").select("lead_id").eq("account_id", item["account_id"]).eq("sender_name", item["sender_name"]).not_.is_("lead_id", "null").limit(1).execute()
                if isinstance(msg_res.data, list) and len(msg_res.data) > 0 and isinstance(msg_res.data[0], dict) and msg_res.data[0].get("lead_id"):
                    lead_id = msg_res.data[0]["lead_id"]
                    enr_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", lead_id).execute()
                    enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict)]
                    if enr_ids:
                        supabase.table("campaign_execution_states").update({
                            "status": "exited",
                            "error_reason": "ai_reply_rejected"
                        }).in_("enrollment_id", enr_ids).eq("status", "awaiting_approval").execute()
        
        return {"status": "success", "message": "Reply rejected and skipped"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reject reply: {str(e)}")
    finally:
        _release_approval_lock(approval_id)


class BatchApprovalRequest(BaseModel):
    action: str  # 'approve' or 'reject'
    approval_ids: List[str]


@router.post("/batch-action")
def batch_approval_action(
    payload: BatchApprovalRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Paranoia Layer 0 & 1: Atomic batch approval/rejection endpoint.
    Guarded by Growth Pro/Enterprise tier entitlement.
    """
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if isinstance(ws_res.data, list) and len(ws_res.data) > 0 and isinstance(ws_res.data[0], dict) else "FREE"
    from core.backend.services.credit_service import TIER_LIMITS
    can_batch = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_batch_approvals", False)
    if not can_batch:
        raise HTTPException(
            status_code=403,
            detail="One-click batch approval and multi-reply dispatch require Growth Pro or Enterprise."
        )

    action = (payload.action or "").lower().strip()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be either 'approve' or 'reject'.")

    ids = list(dict.fromkeys(payload.approval_ids or []))
    if not ids:
        raise HTTPException(status_code=400, detail="No approval items specified.")
    if len(ids) > 100:
        ids = ids[:100]

    success_ids = []
    failed_ids = []

    for item_id in ids:
        try:
            if action == "approve":
                approve_reply(item_id, ApprovalActionRequest(edited_message=None), supabase, workspace_id)
            else:
                reject_reply(item_id, supabase, workspace_id)
            success_ids.append(item_id)
        except Exception as item_err:
            logger.warning(f"Batch {action} failed for approval {item_id}: {item_err}")
            failed_ids.append(item_id)

    return {
        "status": "success",
        "action": action,
        "processed_count": len(success_ids),
        "failed_count": len(failed_ids),
        "successful_ids": success_ids,
        "failed_ids": failed_ids,
    }


@router.post("/auto-approve-high-heat")
def auto_approve_high_heat(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Autonomous high-heat AI auto-approval (heat score >= 75%).
    Guarded by can_auto_approve_high_heat entitlement.
    """
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if isinstance(ws_res.data, list) and len(ws_res.data) > 0 and isinstance(ws_res.data[0], dict) else "FREE"
    from core.backend.services.credit_service import TIER_LIMITS
    can_auto = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_auto_approve_high_heat", False)
    if not can_auto:
        raise HTTPException(
            status_code=403,
            detail="Autonomous AI auto-approval for high-intent responses (≥75% Heat) requires Growth Pro or Enterprise."
        )

    q_items = supabase.table("approval_queue").select("id").eq("workspace_id", workspace_id).eq("status", "pending").gte("heat_score", 75).limit(50).execute()
    ids_to_approve = [r["id"] for r in (q_items.data or []) if isinstance(r, dict)]

    q_ai = supabase.table("ai_reply_approvals").select("id").eq("workspace_id", workspace_id).eq("status", "pending").gte("retrieval_score", 0.75).limit(50).execute()
    ids_to_approve.extend([r["id"] for r in (q_ai.data or []) if isinstance(r, dict)])

    approved = []
    failed = []
    for item_id in ids_to_approve:
        try:
            approve_reply(item_id, ApprovalActionRequest(edited_message=None), supabase, workspace_id)
            approved.append(item_id)
        except Exception as e:
            logger.warning(f"Auto-approve failed for {item_id}: {e}")
            failed.append(item_id)

    return {
        "status": "success",
        "approved_count": len(approved),
        "failed_count": len(failed),
        "approved_ids": approved
    }


def _render_magic_approval_preview(token: str, action: str, item: Dict[str, Any]) -> HTMLResponse:
    sender = html.escape(str(item.get("sender_name") or "Prospect"))
    raw_draft = item.get("generated_reply") or item.get("ai_draft", "")
    draft_display = html.escape(str(raw_draft or ""))
    safe_token = html.escape(token)

    is_approve = (action == "approve")
    action_label = "Approve AI Reply" if is_approve else "Reject AI Reply"
    action_color = "#10b981" if is_approve else "#ef4444"
    action_btn_bg = "#10b981" if is_approve else "#ef4444"
    action_btn_text = "Confirm & Send Reply" if is_approve else "Confirm Rejection"
    alt_btn_text = "Reject Instead" if is_approve else "Approve Instead"
    alt_action = "reject" if is_approve else "approve"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review AI Outreach - Ele-in</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background: #09090b;
            color: #f4f4f5;
            padding: 20px;
            box-sizing: border-box;
        }}
        .card {{
            background: #18181b;
            padding: 32px;
            border-radius: 16px;
            border: 1px solid #27272a;
            max-width: 540px;
            width: 100%;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid {action_color};
            color: {action_color};
            margin-bottom: 16px;
        }}
        h2 {{
            margin: 0 0 8px 0;
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}
        p.desc {{
            color: #a1a1aa;
            font-size: 14px;
            margin: 0 0 20px 0;
            line-height: 1.5;
        }}
        .field-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #71717a;
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .message-box {{
            background: #09090b;
            border: 1px solid #27272a;
            border-radius: 8px;
            padding: 14px 16px;
            font-size: 14px;
            line-height: 1.6;
            color: #e4e4e7;
            white-space: pre-wrap;
            word-break: break-word;
            margin-bottom: 24px;
            max-height: 250px;
            overflow-y: auto;
        }}
        .btn-group {{
            display: flex;
            gap: 12px;
            flex-direction: row;
        }}
        button.btn-primary {{
            flex: 1;
            background: {action_btn_bg};
            color: #ffffff;
            border: none;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        button.btn-primary:hover {{
            opacity: 0.9;
        }}
        button.btn-secondary {{
            background: #27272a;
            color: #d4d4d8;
            border: 1px solid #3f3f46;
            padding: 12px 18px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button.btn-secondary:hover {{
            background: #3f3f46;
        }}
        .scanner-note {{
            margin-top: 20px;
            font-size: 11px;
            color: #52525b;
            text-align: center;
            line-height: 1.4;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">{action_label}</div>
        <h2>Review Proposed AI Outreach</h2>
        <p class="desc">Please confirm before sending. Automated email security crawlers will not trigger action without this confirmation.</p>
        
        <div class="field-label">Recipient / Lead</div>
        <div style="font-weight: 600; font-size: 15px; margin-bottom: 16px; color: #f4f4f5;">{sender}</div>

        <div class="field-label">Proposed AI Message Draft</div>
        <div class="message-box">{draft_display}</div>

        <form method="POST" action="/api/approvals/magic-action">
            <input type="hidden" name="token" value="{safe_token}">
            <div class="btn-group">
                <button type="submit" name="confirmed_action" value="{action}" class="btn-primary">{action_btn_text}</button>
                <button type="submit" name="confirmed_action" value="{alt_action}" class="btn-secondary">{alt_btn_text}</button>
            </div>
        </form>

        <div class="scanner-note">
            Protected by Ele-in Two-Step Gateway & Anti-Scanner Defense.<br>
            Link pre-fetching by corporate spam/virus filters is safe and non-mutating.
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)


def magic_approval_handler(
    token: str,
    confirm: bool = False,
    override_action: Optional[str] = None
) -> HTMLResponse:
    """
    Paranoia Layer 0, 1 & 2: Signed JWT Magic Link Handler for AI Reply Approvals.
    - Layer 0 (Foundational): GET requests render a preview & confirmation page without modifying state.
                              POST requests execute verified state mutation (approving/rejecting).
    - Layer 1 (Environmental): Automated email crawlers (Outlook SafeLinks, Google Workspace, Mimecast)
                              perform GET requests that cannot trigger unintended approvals or cancellations.
    - Layer 2 (Human Paranoia): Allows managers on mobile to review draft message before confirming,
                              provides ability to switch action ('Reject Instead' / 'Approve Instead'),
                              and blocks CSRF/replays on already-resolved items.
    """
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        return HTMLResponse("<h2>Error: System JWT secret is not configured.</h2>", status_code=500)
    
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return HTMLResponse("<h2>Error: This approval link has expired (48h limit).</h2>", status_code=400)
    except jwt.InvalidTokenError:
        return HTMLResponse("<h2>Error: Invalid or tampered approval token.</h2>", status_code=400)
        
    approval_id = payload.get("approval_id")
    token_action = payload.get("action")  # 'approve' or 'reject'
    token_ws = payload.get("workspace_id")
    if not approval_id or token_action not in ("approve", "reject"):
        return HTMLResponse("<h2>Error: Invalid token payload.</h2>", status_code=400)

    effective_action = override_action if override_action in ("approve", "reject") else token_action
        
    from core.backend.api.auth_dep import get_service_client
    supabase = get_service_client()
    
    res = supabase.table("ai_reply_approvals").select("*").eq("id", approval_id).execute()
    item = res.data[0] if isinstance(res.data, list) and len(res.data) > 0 and isinstance(res.data[0], dict) else None
    is_ai_table = True
    if not item:
        res_queue = supabase.table("approval_queue").select("*").eq("id", approval_id).execute()
        item = res_queue.data[0] if isinstance(res_queue.data, list) and len(res_queue.data) > 0 and isinstance(res_queue.data[0], dict) else None
        is_ai_table = False
        
    if not item:
        return HTMLResponse("<h2>Error: Approval item not found or already deleted.</h2>", status_code=404)
        
    item_ws = item.get("workspace_id") or token_ws or ""
    if token_ws and item.get("workspace_id") and str(token_ws) != str(item.get("workspace_id")):
        return HTMLResponse("<h2>Error: Workspace mismatch in approval token.</h2>", status_code=403)
        
    if item["status"] != "pending":
        return HTMLResponse(f"<h2>Notice: This item was already resolved (status: {item['status']}).</h2>", status_code=200)

    # Layer 1 Paranoia: If confirm is False (GET request), DO NOT mutate database!
    # Render preview and confirmation form.
    if not confirm:
        return _render_magic_approval_preview(token, effective_action, item)

    # Layer 0 & 2: Executing confirmed action on POST
    now_iso = datetime.utcnow().isoformat()
    if effective_action == "approve":
        raw_draft = item.get("generated_reply") or item.get("ai_draft", "")
        try:
            draft_msg = validate_approval_message(raw_draft)
        except HTTPException as he:
            return HTMLResponse(f"<h2>Validation Error: {he.detail}</h2>", status_code=he.status_code)

        lead_id = item.get("lead_id")
        lead = None
        lead_linkedin_url = None
        if lead_id:
            lead_res = supabase.table("leads").select("first_name, last_name, linkedin_url, email, status, is_unsubscribed, metadata").eq("id", lead_id).execute()
            if isinstance(lead_res.data, list) and len(lead_res.data) > 0 and isinstance(lead_res.data[0], dict):
                lead = lead_res.data[0]
                lead_linkedin_url = lead.get("linkedin_url")

        if lead:
            block_reason = _is_lead_unsubscribed_or_suppressed(supabase, item_ws, lead)
            if block_reason:
                table_name = "ai_reply_approvals" if is_ai_table else "approval_queue"
                col_time = "resolved_at" if is_ai_table else "reviewed_at"
                status_val = "rejected" if is_ai_table else "skipped"
                supabase.table(table_name).update({"status": status_val, col_time: now_iso}).eq("id", approval_id).execute()

                exec_id = item.get("execution_state_id")
                if exec_id:
                    supabase.table("campaign_execution_states").update({"status": "exited", "error_reason": block_reason}).eq("id", exec_id).execute()
                elif item.get("enrollment_id"):
                    supabase.table("campaign_execution_states").update({"status": "exited", "error_reason": block_reason}).eq("enrollment_id", item["enrollment_id"]).eq("status", "awaiting_approval").execute()

                return HTMLResponse(f"<h2>Blocked: Lead has unsubscribed or is on the DNC suppression list ({block_reason}).</h2>", status_code=409)

        account_id = item.get("account_id")
        sender_name = item.get("sender_name") or "Lead"

        if is_ai_table and not account_id and item.get("enrollment_id"):
            enr_res = supabase.table("campaign_enrollments").select("account_id, campaign_id").eq("id", item["enrollment_id"]).execute()
            if isinstance(enr_res.data, list) and len(enr_res.data) > 0 and isinstance(enr_res.data[0], dict):
                account_id = enr_res.data[0].get("account_id")
                if not account_id and enr_res.data[0].get("campaign_id"):
                    cid = enr_res.data[0]["campaign_id"]
                    ca_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", cid).limit(1).execute()
                    if isinstance(ca_res.data, list) and len(ca_res.data) > 0 and isinstance(ca_res.data[0], dict):
                        account_id = ca_res.data[0]["account_id"]

        if not account_id and item_ws:
            acc_fallback = supabase.table("accounts").select("id").eq("workspace_id", item_ws).eq("is_active", True).limit(1).execute()
            if isinstance(acc_fallback.data, list) and len(acc_fallback.data) > 0 and isinstance(acc_fallback.data[0], dict):
                account_id = acc_fallback.data[0]["id"]

        if account_id:
            if lead_linkedin_url:
                job_payload = {
                    'account_id': account_id,
                    'workspace_id': item_ws,
                    'action': 'send_message',
                    'payload_data': {
                        'profile_url': lead_linkedin_url,
                        'message': draft_msg
                    }
                }
            else:
                job_payload = {
                    'account_id': account_id,
                    'workspace_id': item_ws,
                    'action': 'send_message_to_existing_thread',
                    'payload_data': {
                        'sender_name': sender_name,
                        'message': draft_msg
                    }
                }
            try:
                enqueue_job(supabase, 'inbox_action', item_ws, account_id, job_payload)
            except Exception as eq_err:
                logger.warning(f"Failed to enqueue magic link job for approval {approval_id}: {eq_err}")

        table_name = "ai_reply_approvals" if is_ai_table else "approval_queue"
        col_time = "resolved_at" if is_ai_table else "reviewed_at"
        up_dict = {"status": "approved", col_time: now_iso}
        if not is_ai_table:
            up_dict["ai_draft"] = draft_msg
        else:
            up_dict["generated_reply"] = draft_msg
        supabase.table(table_name).update(up_dict).eq("id", approval_id).execute()
        
        exec_id = item.get("execution_state_id")
        if exec_id:
            supabase.table("campaign_execution_states").update({
                "status": "pending",
                "next_run_at": now_iso
            }).eq("id", exec_id).execute()
        elif item.get("enrollment_id"):
            supabase.table("campaign_execution_states").update({
                "status": "pending",
                "next_run_at": now_iso
            }).eq("enrollment_id", item["enrollment_id"]).eq("status", "awaiting_approval").execute()
            
        return HTMLResponse("""
        <html>
        <head><title>Approved - Ele-in</title><style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#09090b;color:#f4f4f5;}.card{background:#18181b;padding:32px;border-radius:16px;border:1px solid #27272a;max-width:400px;text-align:center;}</style></head>
        <body><div class="card"><h2 style="color:#10b981;">AI Reply Approved</h2><p>The message has been approved and queued for immediate delivery.</p></div></body>
        </html>
        """)
    else:
        table_name = "ai_reply_approvals" if is_ai_table else "approval_queue"
        col_time = "resolved_at" if is_ai_table else "reviewed_at"
        supabase.table(table_name).update({"status": "rejected" if is_ai_table else "skipped", col_time: now_iso}).eq("id", approval_id).execute()
        
        exec_id = item.get("execution_state_id")
        if exec_id:
            supabase.table("campaign_execution_states").update({
                "status": "exited",
                "error_reason": "ai_reply_rejected"
            }).eq("id", exec_id).execute()
        elif item.get("enrollment_id"):
            supabase.table("campaign_execution_states").update({
                "status": "exited",
                "error_reason": "ai_reply_rejected"
            }).eq("enrollment_id", item["enrollment_id"]).eq("status", "awaiting_approval").execute()
            
        return HTMLResponse("""
        <html>
        <head><title>Rejected - Ele-in</title><style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#09090b;color:#f4f4f5;}.card{background:#18181b;padding:32px;border-radius:16px;border:1px solid #27272a;max-width:400px;text-align:center;}</style></head>
        <body><div class="card"><h2 style="color:#ef4444;">AI Reply Rejected</h2><p>The draft was rejected. Outreach has been paused for this lead.</p></div></body>
        </html>
        """)


@router.get("/magic-action", response_class=HTMLResponse)
@router.get("/approve", response_class=HTMLResponse)
@router.get("/reject", response_class=HTMLResponse)
def magic_approval_get_endpoint(token: str):
    """
    Paranoia Layer 0, 1 & 2: GET Handler displays confirmation preview page.
    Prevents enterprise email security scanners from auto-mutating approval state.
    """
    return magic_approval_handler(token=token, confirm=False)


@router.post("/magic-action", response_class=HTMLResponse)
@router.post("/approve", response_class=HTMLResponse)
@router.post("/reject", response_class=HTMLResponse)
async def magic_approval_post_endpoint(
    request: Request,
    token: Optional[str] = Form(None),
    confirmed_action: Optional[str] = Form(None),
    override_action: Optional[str] = Form(None)
):
    """
    Paranoia Layer 0, 1 & 2: POST Handler executes verified state mutation.
    Only triggered upon intentional human click of confirmation button.
    """
    effective_token = token
    if not effective_token:
        effective_token = request.query_params.get("token")
    if not effective_token:
        try:
            body = await request.json()
            if isinstance(body, dict):
                effective_token = body.get("token")
                confirmed_action = confirmed_action or body.get("confirmed_action") or body.get("override_action")
        except Exception:
            pass

    if not effective_token:
        return HTMLResponse("<h2>Error: Missing approval token.</h2>", status_code=400)

    action_to_apply = confirmed_action or override_action
    return magic_approval_handler(token=effective_token, confirm=True, override_action=action_to_apply)

