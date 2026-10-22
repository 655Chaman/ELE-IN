from core.backend.core import crypto
import json
import uuid
import csv
import asyncio
from io import StringIO
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
import os
from integrations.backend.services.voyager_scraper import VoyagerScraper, DailyLimitExceeded, VoyagerThrottled, SessionExpired
from pydantic import BaseModel
from supabase import Client, AsyncClient

from core.backend.api.auth_dep import get_supabase_client, verify_token_and_get_user_id, get_async_supabase_client
from core.backend.services.job_queue import enqueue_job
from campaigns.backend.schemas.elein import CampaignCreate, CampaignResponse, AccountCreate, AccountResponse
from inbox.backend.services.inbox_service import bulk_upsert_messages


from fastapi import Request

import logging
logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
if not SUPABASE_JWT_SECRET:
    logger.warning("SUPABASE_JWT_SECRET is not set — JWT verification will fail at runtime")

router = APIRouter(tags=["inbox"])
from core.backend.api.auth_dep import get_current_workspace

def provision_workspace(user_id: str, supabase: Client, company_name: str = "My Workspace") -> str:
    import uuid
    workspace_id = str(uuid.uuid4())
    try:
        supabase.table("workspaces").insert({
            "id": workspace_id,
            "name": company_name,
            "owner_id": user_id
        }).execute()
        
        supabase.table("workspace_members").insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": "owner"
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to provision workspace: " + str(e))
    return workspace_id





# ── C6: DAG cycle detection ────────────────────────────────────────────────────


def has_cycle(nodes: list, edges: list) -> bool:
    """
    C6: Returns True if the campaign graph contains any cycle (would cause
    the orchestrator to loop indefinitely). Uses DFS with colour-coding:
      white (0) = unvisited, grey (1) = in stack, black (2) = fully visited.
    Operates on the raw node/edge dicts from the request payload.
    """
    adj: dict = {n["id"]: [] for n in nodes}
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src in adj:
            adj[src].append(tgt)

    colour: dict = {n["id"]: 0 for n in nodes}

    def dfs(nid: str) -> bool:
        colour[nid] = 1  # grey — currently in stack
        for neighbour in adj.get(nid, []):
            if neighbour not in colour:
                continue  # dangling reference — ignore
            if colour[neighbour] == 1:
                return True  # back edge → cycle
            if colour[neighbour] == 0 and dfs(neighbour):
                return True
        colour[nid] = 2  # black — fully visited
        return False

    return any(dfs(n["id"]) for n in nodes if colour.get(n["id"]) == 0)




class SendReplyPayload(BaseModel):
    sender_name: str
    message_text: str
    account_id: Optional[str] = None
    ai_generated: Optional[bool] = False
    lead_id: Optional[str] = None

@router.post("/inbox/reply", response_model=dict)
def send_inbox_reply(
    payload: SendReplyPayload,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    from datetime import datetime, timezone, timedelta
    from leads.backend.services.data_hygiene import DataHygieneService
    
    sender = payload.sender_name.strip()
    msg = payload.message_text.strip()
    
    if not sender:
        raise HTTPException(status_code=400, detail="sender_name must not be empty")
    if not msg:
        raise HTTPException(status_code=400, detail="message_text must not be empty")
        
    if len(msg) > 4000:
        raise HTTPException(status_code=400, detail="Message exceeds maximum length of 4000 characters")
        
    try:
        # Layer 2: Idempotency Guard
        five_secs_ago = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        
        recent_check = supabase.table("messages").select("id").eq("workspace_id", workspace_id).eq("sender_name", sender).eq("message_text", msg).gte("created_at", five_secs_ago).execute()
        if recent_check.data:
            return {"status": "success", "message_id": recent_check.data[0]["id"], "deduplicated": True}
            
        msg_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Paranoia Layer 1 & 2: IDOR and Tenant Boundary Protection
        lead_id = payload.lead_id
        account_id = payload.account_id
        
        if account_id:
            chk_acc = supabase.table("accounts").select("id, status, quarantined_until").eq("id", account_id).eq("workspace_id", workspace_id).execute()
            if not chk_acc.data:
                raise HTTPException(status_code=403, detail="Specified account does not belong to this workspace")
            acc_status = (chk_acc.data[0].get("status") or "").upper()
            if acc_status and acc_status in ("DISCONNECTED", "RESTRICTED", "SUSPENDED", "QUARANTINED", "FAILED", "ERROR", "INACTIVE"):
                raise HTTPException(status_code=400, detail=f"Selected LinkedIn account is {acc_status.lower()}. Please reconnect an active account.")
                
        if lead_id and lead_id != "unknown":
            chk_lead = supabase.table("leads").select("id, linkedin_url, email, status, is_unsubscribed, metadata").eq("id", lead_id).eq("workspace_id", workspace_id).execute()
            if not chk_lead.data:
                raise HTTPException(status_code=403, detail="Specified lead does not belong to this workspace")
            lead_row = chk_lead.data[0]
            from core.backend.api.routers.approvals import _is_lead_unsubscribed_or_suppressed
            block_reason = _is_lead_unsubscribed_or_suppressed(supabase, workspace_id, lead_row)
            if block_reason:
                raise HTTPException(status_code=409, detail=f"Cannot send reply: lead is unsubscribed or suppressed ({block_reason}).")

        if payload.ai_generated:
            from inbox.backend.services.inbox_service import sanitize_ai_draft
            msg = sanitize_ai_draft(msg, sender) or msg
        
        if not lead_id or not account_id:
            query = supabase.table("messages").select("lead_id, account_id").eq("workspace_id", workspace_id).eq("sender_name", sender).neq("account_id", None)
            if lead_id and lead_id != "unknown":
                query = query.eq("lead_id", lead_id)
            elif lead_id == "unknown":
                query = query.is_("lead_id", "null")
                
            hist_check = query.limit(1).execute()
            
            if hist_check.data:
                if not lead_id or lead_id == "unknown": lead_id = hist_check.data[0].get("lead_id")
                if not account_id: account_id = hist_check.data[0].get("account_id")
                
        if not account_id:
            acc_res = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).eq("status", "ACTIVE").limit(1).execute()
            if acc_res.data:
                account_id = acc_res.data[0]["id"]
            else:
                raise HTTPException(status_code=400, detail="No active LinkedIn account found to send this message")
                
        linkedin_url = None
        if lead_id and lead_id != "unknown":
            lead_res = supabase.table("leads").select("linkedin_url").eq("id", lead_id).eq("workspace_id", workspace_id).limit(1).execute()
            if lead_res.data:
                raw_url = lead_res.data[0].get("linkedin_url")
                linkedin_url = DataHygieneService.normalize_linkedin_url(raw_url) if raw_url else None

        # Layer 0: Insert message
        msg_payload = {
            "id": msg_id,
            "workspace_id": workspace_id,
            "sender_name": sender,
            "message_text": msg,
            "direction": "outbound",
            "intent": "reply",
            "created_at": now_str,
            "updated_at": now_str,
            "account_id": account_id
        }
        if lead_id:
            msg_payload["lead_id"] = lead_id
            
        supabase.table("messages").insert(msg_payload).execute()
        
        # Layer 1: Enqueue the task for the background worker with normalized profile URL
        if linkedin_url:
            job_payload = {
                "account_id": account_id,
                "action": "send_message",
                "payload_data": {
                    "profile_url": linkedin_url,
                    "message": msg
                }
            }
        else:
            # Fallback to name search only if we have no CRM record
            job_payload = {
                "account_id": account_id,
                "action": "send_message_to_existing_thread",
                "payload_data": {
                    "sender_name": sender,
                    "message": msg
                }
            }
            
        try:
            from core.backend.services.job_queue import enqueue_job
            enqueue_job(
                supabase=supabase,
                job_type="inbox_action",
                workspace_id=workspace_id,
                asset_id=account_id,
                payload=job_payload,
                idempotency_key=f"inbox_reply_{msg_id}"
            )
        except Exception as e_pj:
            logger.warning(f"Failed to enqueue processing_job for inbox reply: {e_pj}")
        
        # Insert log
        try:
            supabase.table("action_log").insert({
                "workspace_id": workspace_id,
                "action_type": "inbox_reply_sent",
                "result": "success",
                "executed_at": now_str
            }).execute()
        except Exception as e_al:
            logger.warning(f"Failed to write action_log for inbox reply (unmigrated?): {e_al}")
        
        return {"status": "success", "message_id": msg_id, "message": "Reply sent successfully and enqueued for delivery"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send inbox reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to insert reply into database")

# ── Phase 10: AI Objection Battlecards & Deal Pipeline Endpoints ───────────────

class ClassifyObjectionPayload(BaseModel):
    message_text: str
    lead_id: Optional[str] = None

class GenerateBattlecardPayload(BaseModel):
    objection_type: str
    message_text: Optional[str] = None
    lead_id: Optional[str] = None
    lead_name: Optional[str] = None
    company: Optional[str] = None
    detected_competitor: Optional[str] = None
    detected_timing: Optional[str] = None
    detected_referral: Optional[str] = None

class UpdateDealStagePayload(BaseModel):
    deal_stage: str
    estimated_value: Optional[float] = None
    force_override: Optional[bool] = False

@router.post("/inbox/objection/classify", response_model=dict)
def classify_objection_endpoint(
    payload: ClassifyObjectionPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0 & 1: Classifies inbound prospect message into 8 B2B objection types,
    extracts named competitors, timing windows, and referral contacts.
    """
    from inbox.backend.services.objection_service import classify_objection
    from inbox.backend.services.battlecard_service import get_competitive_intel
    
    result = classify_objection(payload.message_text)
    comp_intel = get_competitive_intel(result.get("detected_competitor"))
    result["competitor_intel"] = comp_intel
    return {"status": "success", "data": result}

def _check_workspace_tier_permission(workspace_id: str, permission_flag: str, supabase: Client):
    """
    Paranoia Layer 0 & 1: Verifies workspace has the required tier feature enabled.
    Raises HTTPException(402) with structured metadata if locked on current tier.
    """
    try:
        rpc_result = supabase.rpc('get_credit_balance', {'p_workspace_id': workspace_id}).execute()
        raw_data = getattr(rpc_result, "data", None)
        tier = (raw_data.get("tier") if isinstance(raw_data, dict) else "FREE") or "FREE"
    except Exception:
        tier = "FREE"

    from core.backend.services.credit_service import TIER_LIMITS
    tier_conf = TIER_LIMITS.get(tier, TIER_LIMITS['FREE'])
    if not tier_conf.get(permission_flag, False):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "FEATURE_LOCKED",
                "feature": permission_flag,
                "current_tier": tier,
                "required_tier": "PRO",
                "message": "This capability requires a Professional or Enterprise tier upgrade."
            }
        )

@router.post("/inbox/battlecard/generate", response_model=dict)
def generate_battlecard_endpoint(
    payload: GenerateBattlecardPayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0 & 2: Returns 3 multi-tone counter-pitches (Challenger, Consultative, Casual)
    customized to the objection type, prospect identity, and competitive kill points.
    Gated by can_use_battlecards tier limit.
    """
    _check_workspace_tier_permission(workspace_id, "can_use_battlecards", supabase)

    from inbox.backend.services.battlecard_service import generate_battlecard_responses
    
    context = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    if payload.lead_id:
        try:
            lead_res = supabase.table("leads").select("first_name, last_name, company, timezone").eq("id", payload.lead_id).limit(1).execute()
            if lead_res.data:
                lead = lead_res.data[0]
                if not context.get("lead_name"):
                    context["lead_name"] = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                if not context.get("company"):
                    context["company"] = lead.get("company")
        except Exception as e:
            logger.warning(f"Error enriching battlecard context with lead info: {e}")
            
    battlecard = generate_battlecard_responses(payload.objection_type, context)
    return {"status": "success", "data": battlecard}

@router.get("/inbox/suggested-slots", response_model=dict)
def get_suggested_meeting_slots_endpoint(
    lead_id: Optional[str] = None,
    lead_tz: Optional[str] = None,
    num_slots: int = 3,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0 & 1: Generates 3 timezone-aware calendar proposal slots over
    the next 2-4 business days, skipping weekends.
    Gated by can_smart_calendar_slots tier limit.
    """
    _check_workspace_tier_permission(workspace_id, "can_smart_calendar_slots", supabase)

    from inbox.backend.services.battlecard_service import generate_suggested_meeting_slots
    target_tz = lead_tz
    if not target_tz and lead_id:
        try:
            lead_res = supabase.table("leads").select("timezone").eq("id", lead_id).limit(1).execute()
            if lead_res.data and lead_res.data[0].get("timezone"):
                target_tz = lead_res.data[0]["timezone"]
        except Exception as e:
            logger.warning(f"Error fetching lead timezone for slots: {e}")
            
    slots = generate_suggested_meeting_slots(lead_tz=target_tz, num_slots=num_slots)
    return {"status": "success", "slots": slots, "timezone": target_tz or "UTC"}

@router.patch("/inbox/threads/{lead_id}/deal-stage", response_model=dict)
def update_deal_stage_endpoint(
    lead_id: str,
    payload: UpdateDealStagePayload,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0, 1 & 2: Updates a lead's deal stage with monotonicity enforcement,
    defensive database fallback, and real-time deal.stage_updated webhook emission.
    Gated by can_deal_pipeline tier limit.
    """
    _check_workspace_tier_permission(workspace_id, "can_deal_pipeline", supabase)

    from inbox.backend.services.battlecard_service import update_lead_deal_stage
    res = update_lead_deal_stage(
        supabase=supabase,
        lead_id=lead_id,
        workspace_id=workspace_id,
        new_stage=payload.deal_stage,
        estimated_value=payload.estimated_value,
        force_override=payload.force_override or False
    )
    return res

# ── Campaign CRUD ─────────────────────────────────────────────────────────────










class EnrollLeadsRequest(BaseModel):
    opportunity_ids: List[str]









# ── Leads Import ─────────────────────────────────────────────────────────────

from fastapi import BackgroundTasks
import asyncio

import os
import shutil





class UploadUrlsRequest(BaseModel):
    name: str
    urls: list[str]



class UploadSalesNavRequest(BaseModel):
    name: str
    url: str
    account_id: Optional[str] = None   # Which LinkedIn account to scrape from
    max_results: Optional[int] = 100   # Default cap: 100 profiles per import


# ── Accounts CRUD ─────────────────────────────────────────────────────────────





class CookieRefreshRequest(BaseModel):
    cookie_json: str



















from typing import Optional

class EnrollListRequest(BaseModel):
    list_id: str
    excludeListId: Optional[str] = None
    excludeOtherCampaigns: Optional[bool] = False
    excludeOtherSenders: Optional[bool] = False
    excludeSameSender: Optional[bool] = False





class BulkStatusRequest(BaseModel):
    opportunity_ids: List[str]
    status: str









def sync_inbox_api(payload: dict, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id required")
        
    acc_res = supabase.table("accounts").select("session_cookies_encrypted, proxies(protocol, host, port, username)").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    # PARANOIA LAYER 1: Enqueue job instead of executing locally
    supabase.table("processing_jobs").insert({
        'job_type': 'inbox_sync',
        'status': 'pending',
        'workspace_id': workspace_id,
        'payload': {
            'account_id': account_id,
            'workspace_id': workspace_id
        }
    }).execute()
    
    # Process synchronous messages if provided
    messages = payload.get("messages", [])
    if messages:
        try:
            res = bulk_upsert_messages(supabase, workspace_id, account_id, messages)
            return {"status": "success", "scraped": len(messages), "new_saved": res["new_saved"]}
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

    return {"status": "enqueued"}

@router.get("/inbox/threads", response_model=List[dict])
def get_inbox_threads(
    limit: int = 50,
    offset: int = 0,
    account_id: Optional[str] = None,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    try:
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        
        q = supabase.table("messages").select("sender_name, message_text, direction, created_at, lead_id, account_id").eq("workspace_id", workspace_id)
        if account_id:
            q = q.eq("account_id", account_id)
        res = q.order("created_at", desc=True).limit(1000).execute()
        
        threads_dict = {}
        lead_ids_to_fetch = set()
        for r in (res.data or []):
            sn = r["sender_name"]
            lid = r.get("lead_id") or "unknown"
            if r.get("lead_id"):
                lead_ids_to_fetch.add(r.get("lead_id"))
            key = f"{sn}_{lid}"
            if key not in threads_dict:
                threads_dict[key] = {
                    "sender_name": sn,
                    "lead_id": r.get("lead_id"),
                    "account_id": r.get("account_id"),
                    "last_message": r["message_text"],
                    "direction": r["direction"],
                    "created_at": r["created_at"],
                    "type": "message",
                    "thread_key": key,
                    "unread_count": 0,
                    "deal_stage": "NEW_REPLY",
                    "objection_data": None,
                    "lead_timezone": None,
                    "_has_replied": False,
                    "_seen_inbound": False
                }
            elif not threads_dict[key].get("account_id") and r.get("account_id"):
                threads_dict[key]["account_id"] = r.get("account_id")
            
            # Track unread count (inbound messages before first outbound reply)
            t = threads_dict[key]
            if not t["_has_replied"]:
                if r.get("direction") == "inbound":
                    t["unread_count"] += 1
                elif r.get("direction") == "outbound":
                    t["_has_replied"] = True

            if r.get("direction") == "inbound" and not t.get("_seen_inbound"):
                t["_seen_inbound"] = True
                try:
                    from inbox.backend.services.objection_service import classify_objection
                    obj_info = classify_objection(r.get("message_text") or "")
                    if obj_info.get("objection_type") != "GENERAL_INQUIRY":
                        t["objection_data"] = obj_info
                        t["deal_stage"] = "OBJECTION_RAISED"
                except Exception:
                    pass

        # Defensive enrichment of deal_stage & timezone from leads table
        if lead_ids_to_fetch:
            try:
                leads_res = supabase.table("leads").select("id, deal_stage, timezone").in_("id", list(lead_ids_to_fetch)).execute()
                lead_map = {l["id"]: l for l in (leads_res.data or [])}
                for t in threads_dict.values():
                    if t.get("lead_id") and t["lead_id"] in lead_map:
                        l_data = lead_map[t["lead_id"]]
                        if l_data.get("deal_stage"):
                            t["deal_stage"] = l_data["deal_stage"]
                        if l_data.get("timezone"):
                            t["lead_timezone"] = l_data["timezone"]
            except Exception as ex:
                logger.debug(f"Defensive fallback: leads table query skipped ({ex})")

        for t in threads_dict.values():
            t.pop("_has_replied", None)
            t.pop("_seen_inbound", None)

        # Fetch connection_accepted events
        try:
            action_res = supabase.table("action_log") \
                .select("id, executed_at, campaign_execution_states(campaign_enrollments(leads(first_name, last_name)))") \
                .eq("workspace_id", workspace_id) \
                .eq("action_type", "connection_accepted") \
                .order("executed_at", desc=True) \
                .limit(100) \
                .execute()
                
            for a in action_res.data or []:
                first = ""
                last = ""
                try:
                    lead = a.get("campaign_execution_states", {}).get("campaign_enrollments", {}).get("leads", {})
                    if lead:
                        first = lead.get("first_name", "")
                        last = lead.get("last_name", "")
                except Exception:
                    pass
                    
                if first or last:
                    sn = f"{first} {last}".strip()
                    event_time = a.get("executed_at")
                    matching_thread = next((t for t in threads_dict.values() if t.get("sender_name") == sn), None)
                    if matching_thread:
                        if event_time > matching_thread["created_at"]:
                            matching_thread["last_message"] = "Connection Accepted"
                            matching_thread["direction"] = "inbound"
                            matching_thread["created_at"] = event_time
                            matching_thread["type"] = "connection_accepted"
                    else:
                        ca_key = f"{sn}_unknown"
                        threads_dict[ca_key] = {
                            "sender_name": sn,
                            "lead_id": None,
                            "account_id": None,
                            "last_message": "Connection Accepted",
                            "direction": "inbound",
                            "created_at": event_time,
                            "type": "connection_accepted",
                            "thread_key": ca_key,
                            "unread_count": 1,
                            "deal_stage": "NEW_REPLY",
                            "objection_data": None,
                            "lead_timezone": None,
                        }
        except Exception as ex_act:
            logger.debug(f"Action log connection_accepted fetch skipped: {ex_act}")
                
        threads = list(threads_dict.values())
        threads.sort(key=lambda x: x["created_at"], reverse=True)
        return threads[offset:offset + limit]
    except Exception as e:
        logger.error(f"Error fetching threads (unmigrated?): {e}", exc_info=True)
        return []

@router.get("/inbox/threads/{sender_name}", response_model=List[dict])
def get_thread_messages(sender_name: str, lead_id: Optional[str] = None, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        query = supabase.table("messages").select("id, message_text, direction, created_at, lead_id, account_id").eq("workspace_id", workspace_id).eq("sender_name", sender_name)
        if lead_id and lead_id != "unknown":
            query = query.eq("lead_id", lead_id)
        elif lead_id == "unknown":
            query = query.is_("lead_id", "null")
            
        res = query.order("created_at").execute()
        messages = res.data or []
        for m in messages:
            m["type"] = "message"
            
        try:
            action_res = supabase.table("action_log") \
                .select("id, executed_at, campaign_execution_states(campaign_enrollments(leads(id, first_name, last_name)))") \
                .eq("workspace_id", workspace_id) \
                .eq("action_type", "connection_accepted") \
                .order("executed_at", desc=True) \
                .limit(100) \
                .execute()
                
            for a in action_res.data or []:
                first = ""
                last = ""
                lid = None
                try:
                    lead = a.get("campaign_execution_states", {}).get("campaign_enrollments", {}).get("leads", {})
                    if lead:
                        lid = lead.get("id")
                        first = lead.get("first_name", "")
                        last = lead.get("last_name", "")
                except Exception:
                    pass
                    
                matches_lead = (lead_id and lead_id != "unknown" and lid == lead_id)
                sn = f"{first} {last}".strip() if (first or last) else ""
                matches_name = (sn == sender_name and (not lead_id or lead_id == "unknown" or lid == lead_id))
                
                if matches_lead or matches_name:
                    messages.append({
                        "id": a["id"],
                        "message_text": "Connection Accepted",
                        "direction": "inbound",
                        "created_at": a.get("executed_at"),
                        "type": "connection_accepted"
                    })
        except Exception as ex_act:
            logger.debug(f"Action log fetch skipped in get_thread_messages: {ex_act}")
                    
        messages.sort(key=lambda x: x.get("created_at") or "")
        return messages
    except Exception as e:
        logger.error(f"Error fetching thread messages: {e}", exc_info=True)
        return []



# ═══════════════════════════════════════════════════════════════════════════════
# ── KILL HEYREACH FEATURES ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

# ── Feature 1: AI Reply Co-Pilot (streaming) ──────────────────────────────────



# ── Feature 2: Lead Heat Scores ────────────────────────────────────────────────



# ── Feature 3: Intent-classified threads ──────────────────────────────────────

@router.get("/inbox/threads-with-intent", response_model=list)
def get_threads_with_intent(
    limit: int = 50,
    offset: int = 0,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Return thread list enriched with intent label, deal stage, and objection classification from last inbound message."""
    try:
        from inbox.backend.services.objection_service import classify_objection
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        
        res = supabase.table("messages").select("sender_name, message_text, direction, created_at, intent, lead_id, account_id").eq("workspace_id", workspace_id).order("created_at", desc=True).limit(1000).execute()
        
        threads_dict = {}
        lead_ids_to_fetch = set()

        for r in (res.data or []):
            sn = r["sender_name"]
            lid = r.get("lead_id")
            if lid:
                lead_ids_to_fetch.add(lid)

            key = f"{sn}_{lid or 'unknown'}"
            if key not in threads_dict:
                threads_dict[key] = {
                    "sender_name": sn,
                    "last_message": r["message_text"],
                    "message_text": r["message_text"],
                    "direction": r["direction"],
                    "created_at": r["created_at"],
                    "type": "message",
                    "thread_key": key,
                    "intent": "unknown",
                    "lead_id": lid,
                    "account_id": r.get("account_id"),
                    "deal_stage": "NEW_REPLY",
                    "objection_data": None,
                    "unread_count": 0,
                    "_seen_inbound": False
                }
            elif not threads_dict[key].get("account_id") and r.get("account_id"):
                threads_dict[key]["account_id"] = r.get("account_id")
                
            # Grab intent and objection info of latest inbound
            if r.get("direction") == "inbound" and not threads_dict[key]["_seen_inbound"]:
                raw_intent = r.get("intent") or "unknown"
                threads_dict[key]["intent"] = raw_intent
                threads_dict[key]["_seen_inbound"] = True
                
                # Check for objection classification
                obj_info = classify_objection(r.get("message_text") or "")
                if obj_info.get("objection_type") != "GENERAL_INQUIRY":
                    threads_dict[key]["objection_data"] = obj_info
                    if raw_intent in ["unknown", None]:
                        threads_dict[key]["intent"] = "objection"
                    threads_dict[key]["deal_stage"] = "OBJECTION_RAISED"

        # Defensive enrichment of deal_stage from leads table if columns exist
        if lead_ids_to_fetch:
            try:
                leads_res = supabase.table("leads").select("id, deal_stage, timezone").in_("id", list(lead_ids_to_fetch)).execute()
                lead_map = {l["id"]: l for l in (leads_res.data or [])}
                for t in threads_dict.values():
                    if t.get("lead_id") and t["lead_id"] in lead_map:
                        l_data = lead_map[t["lead_id"]]
                        if l_data.get("deal_stage"):
                            t["deal_stage"] = l_data["deal_stage"]
                        if l_data.get("timezone"):
                            t["lead_timezone"] = l_data["timezone"]
            except Exception as ex:
                logger.debug(f"Defensive fallback: leads table deal_stage query skipped ({ex})")

        for t in threads_dict.values():
            t.pop("_seen_inbound", None)
            
        threads = list(threads_dict.values())
        return threads[offset:offset + limit]
    except Exception as e:
        logger.error(f"Error fetching threads with intent (unmigrated?): {e}", exc_info=True)
        return []


# ── Feature 4: Warmup Status ───────────────────────────────────────────────────




# ── Accounts: Health Check Endpoints ─────────────────────────────────────────






# ── Feature 5: Message Attribution ────────────────────────────────────────────



# ── Feature 6: Approval Queue ─────────────────────────────────────────────────



class ApproveRequest(BaseModel):
    queue_id: str
    action: str  # 'approve' | 'edit_and_send' | 'skip'
    final_message: str = ""
    account_id: str = ""



# ── Feature 6b: Auto-enqueue after sync ───────────────────────────────────────

@router.post("/inbox/sync-and-classify", response_model=dict)
async def sync_inbox_with_classification(payload: dict, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Full inbox sync + intent classification + auto-enqueue hot/question replies."""
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id required")

    acc_res = supabase.table("accounts").select("session_cookies_encrypted, proxies(protocol, host, port, username)").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")

    # PARANOIA LAYER 1: Enqueue job instead of executing locally
    supabase.table("processing_jobs").insert({
        'job_type': 'inbox_sync',
        'status': 'pending',
        'workspace_id': workspace_id,
        'payload': {
            'account_id': account_id,
            'workspace_id': workspace_id
        }
    }).execute()
    
    messages = payload.get("messages", [])
    classified = 0
    
    if messages:
        try:
            from knowledge.backend.services.elein_ai_service import classify_intent
            from core.backend.services.calendar_adapter import get_calendar_adapter
            for m in messages:
                if m.get("direction") == "inbound":

                    # --- Phase 3: Resolve Lead Context First ---
                    matched_lead = None
                    target_lead_id = None
                    lead_tz = "UTC"
                    msg_res = supabase.table("messages").select("lead_id").eq("account_id", account_id).eq("sender_name", m.get("sender_name")).not_.is_("lead_id", "null").limit(1).execute()
                    if msg_res.data and msg_res.data[0].get("lead_id"):
                        target_lead_id = msg_res.data[0]["lead_id"]
                        lead_res = supabase.table("leads").select("id, email, first_name, last_name, timezone").eq("id", target_lead_id).execute()
                        if lead_res.data:
                            matched_lead = lead_res.data[0]
                            lead_tz = matched_lead.get("timezone") or "UTC"

                    intent_data = await classify_intent(m["message_text"], workspace_id=workspace_id, lead_timezone=lead_tz)
                    m["intent"] = intent_data.get("intent", "unknown")
                    m["intent_confidence"] = intent_data.get("confidence", 0.0)
                    classified += 1

                    if m["intent"] == "booking_confirmation" and intent_data.get("confirmed_time") and matched_lead:
                        try:
                            # 1. Intermediate Race Lock (Booking Pending)
                            enroll_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", matched_lead["id"]).execute()
                            if enroll_res.data:
                                enroll_ids = [e["id"] for e in enroll_res.data]
                                
                                # Lock the state so concurrent workers don't also attempt to book
                                update_res = supabase.table("campaign_execution_states").update({
                                    "status": "paused",
                                    "error_reason": "booking_pending"
                                }).in_("enrollment_id", enroll_ids).neq("status", "exited").neq("error_reason", "booking_pending").execute()
                                
                                if update_res.data:
                                    # We won the race. Execute the booking API call.
                                    acc_res = supabase.table("accounts").select("calendar_provider, calendar_token, calendar_link").eq("id", account_id).limit(1).execute()
                                    if acc_res.data and acc_res.data[0].get("calendar_provider"):
                                        adapter = get_calendar_adapter(acc_res.data[0])
                                        if adapter:
                                            full_name = f"{matched_lead.get('first_name', '')} {matched_lead.get('last_name', '')}".strip()
                                            booking_res = await adapter.create_booking(
                                                lead_email=matched_lead.get("email", "unknown@test.com"),
                                                lead_name=full_name,
                                                start_time=intent_data.get("confirmed_time"),
                                                end_time=intent_data.get("confirmed_time")
                                            )
                                            
                                            # If booking succeeded, finalize the state and save the booking_id
                                            if booking_res and booking_res.get("status") == "confirmed":
                                                booking_id = booking_res.get("booking_id")
                                                # Fetch existing variables to preserve them
                                                state_res = supabase.table("campaign_execution_states").select("id, variables").in_("enrollment_id", enroll_ids).execute()
                                                for st in state_res.data:
                                                    vars_dict = st.get("variables") or {}
                                                    vars_dict["booking_id"] = booking_id
                                                    supabase.table("campaign_execution_states").update({
                                                        "status": "exited",
                                                        "error_reason": "meeting_booked",
                                                        "variables": vars_dict
                                                    }).eq("id", st["id"]).execute()
                                            else:
                                                # Booking failed (e.g. API down, slot taken). Unlock to paused/booking_failed for manual review.
                                                supabase.table("campaign_execution_states").update({
                                                    "status": "paused",
                                                    "error_reason": "booking_failed"
                                                }).in_("enrollment_id", enroll_ids).execute()
                                else:
                                    logger.info(f"Duplicate booking confirmation for lead {matched_lead['id']} ignored (already booking or exited).")
                        except Exception as e:
                            logger.error(f"Failed to process booking confirmation: {e}")

                    elif m["intent"] in ["cancellation", "reschedule_request"] and matched_lead:
                        try:
                            enroll_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", matched_lead["id"]).execute()
                            if enroll_res.data:
                                enroll_ids = [e["id"] for e in enroll_res.data]
                                
                                # 1. Find the execution state to extract the booking_id
                                state_res = supabase.table("campaign_execution_states").select("id, variables").in_("enrollment_id", enroll_ids).eq("error_reason", "meeting_booked").execute()
                                
                                if state_res.data:
                                    acc_res = supabase.table("accounts").select("calendar_provider, calendar_token, calendar_link").eq("id", account_id).limit(1).execute()
                                    if acc_res.data and acc_res.data[0].get("calendar_provider"):
                                        adapter = get_calendar_adapter(acc_res.data[0])
                                        if adapter:
                                            # Execute cancellation for each state that has a booking_id
                                            for st in state_res.data:
                                                vars_dict = st.get("variables") or {}
                                                booking_id = vars_dict.get("booking_id")
                                                if booking_id:
                                                    await adapter.cancel_booking(booking_id)
                                                    
                                    # 2. Revert the state so they drop out of exited and enter manual review
                                    supabase.table("campaign_execution_states").update({
                                        "status": "paused", # Require manual intervention
                                        "error_reason": f"user_{m['intent']}"
                                    }).in_("enrollment_id", enroll_ids).eq("error_reason", "meeting_booked").execute()
                        except Exception as e:
                            logger.error(f"Failed to process cancellation/reschedule: {e}")


            res = bulk_upsert_messages(supabase, workspace_id, account_id, messages)
            return {"status": "success", "scraped": len(messages), "new_saved": res["new_saved"],
                    "classified": classified, "queued_for_approval": res["queued"]}
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

    return {"status": "enqueued"}

def _build_proxy_url(account_row: dict) -> str:
    p = account_row.get("proxies")
    if not p:
        return None
    if p.get("username"):
        return f"{p['protocol']}://{p['username']}@{p['host']}:{p['port']}"
    return f"{p['protocol']}://{p['host']}:{p['port']}"
import re
from fastapi import HTTPException
def validate_campaign_variables(nodes_raw: list):
    allowed_vars = {
        'first_name', 'last_name', 'company', 'job_title', 'location', 'industry', 'mutual_connections',
        'ai_icebreaker', 'ai_sentiment', 'ai_brain_reply', 'best_send_time', 'work_email', 'competitor_detected'
    }
    for node in nodes_raw:
        data = node.get("data", {})
        texts_to_check = []
        if node.get("type") in ['send_message']:
            texts_to_check.append(data.get("body", ""))
        elif node.get("type") == 'connection_request':
            texts_to_check.append(data.get("note", ""))
        elif node.get("type") == 'send_message_ab':
            texts_to_check.extend([data.get("body_a", ""), data.get("body_b", ""), data.get("body_c", "")])
        elif node.get("type") in ['send_inmail', 'send_paid_inmail']:
            texts_to_check.extend([data.get("subject", ""), data.get("body", "")])
        
        for text in texts_to_check:
            if not text: continue
            matches = re.findall(r"\{\{([^}]+)\}\}", text)
            for var in matches:
                clean_var = var.split("|")[0].strip()
                if clean_var not in allowed_vars:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Invalid template variable '{{{{{clean_var}}}}}' found. Allowed: {', '.join(allowed_vars)}"
                    )
