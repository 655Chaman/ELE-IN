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









def bulk_upsert_messages(supabase: Client, workspace_id: str, account_id: str, messages: list):
    """
    Paranoia Layer 2: Abstract raw DB operations to prevent N+1 loop regressions.
    """
    if not messages:
        return {"new_saved": 0, "updated": 0, "queued": 0}
        
    saved = 0
    updated = 0
    queued = 0
    
    # Layer 1: chunking to prevent Supabase payload limits
    CHUNK_SIZE = 500
    
    for i in range(0, len(messages), CHUNK_SIZE):
        chunk = messages[i:i + CHUNK_SIZE]
        
        # Layer 0: bulk fetch to check existence
        message_texts = list(set(m["message_text"] for m in chunk))
        existing_res = supabase.table("messages").select("id, sender_name, message_text, direction").eq("account_id", account_id).in_("message_text", message_texts).execute()
        existing_records = existing_res.data if existing_res.data else []
        
        existing_map = {}
        for r in existing_records:
            key = (r.get("sender_name"), r.get("message_text"), r.get("direction"))
            existing_map[key] = r["id"]
            
        upsert_payload = []
        seen_in_chunk = {}
        to_enqueue = []
        
        for m in chunk:
            key = (m.get("sender_name"), m.get("message_text"), m.get("direction"))
            if key in seen_in_chunk:
                continue
                
            is_existing = key in existing_map
            msg_id = existing_map[key] if is_existing else str(uuid.uuid4())
            
            record = {
                "id": msg_id,
                "workspace_id": workspace_id,
                "account_id": account_id,
                "sender_name": m.get("sender_name"),
                "message_text": m.get("message_text"),
                "direction": m.get("direction"),
            }
            
            # --- Change 1: Resolve node_id for inbound messages ---
            if m.get("direction") == "inbound":
                lead_id = None
                # First try to get lead_id from previous messages in thread
                msg_res = supabase.table("messages").select("lead_id").eq("account_id", account_id).eq("sender_name", m.get("sender_name")).not_.is_("lead_id", "null").limit(1).execute()
                if msg_res.data and msg_res.data[0].get("lead_id"):
                    lead_id = msg_res.data[0]["lead_id"]
                    
                if lead_id:
                    record["lead_id"] = lead_id
                    # Now get the current node_id
                    enroll_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", lead_id).execute()
                    if enroll_res.data:
                        enroll_ids = [e["id"] for e in enroll_res.data]
                        state_res = supabase.table("campaign_execution_states").select("current_node_id").in_("enrollment_id", enroll_ids).in_("status", ["running", "paused", "completed"]).order("updated_at", desc=True).limit(1).execute()
                        if state_res.data and state_res.data[0].get("current_node_id"):
                            record["node_id"] = state_res.data[0]["current_node_id"]

            if "intent" in m:
                record["intent"] = m["intent"]
            if "intent_confidence" in m:
                record["intent_confidence"] = m["intent_confidence"]
                
            upsert_payload.append(record)
            seen_in_chunk[key] = True
            
            if is_existing:
                updated += 1
            else:
                saved += 1
                intent = m.get("intent", "unknown")
                if m.get("direction") == "inbound" and intent not in ("negative", "unknown"):
                    to_enqueue.append(m)
                
        # Bulk Upsert
        if upsert_payload:
            supabase.table("messages").upsert(upsert_payload).execute()
            
        # Bulk handle approval queue
        if to_enqueue:
            sender_names = list(set(m.get("sender_name") for m in to_enqueue))
            q_res = supabase.table("approval_queue").select("sender_name").eq("workspace_id", workspace_id).eq("status", "pending").in_("sender_name", sender_names).execute()
            existing_queues = set(r["sender_name"] for r in (q_res.data or []))
            
            # Bulk thread query
            thread_res = supabase.table("messages").select("direction, message_text, created_at, sender_name").eq("account_id", account_id).in_("sender_name", sender_names).order("created_at").execute()
            threads_by_sender = {}
            for r in (thread_res.data or []):
                sn = r["sender_name"]
                if sn not in threads_by_sender:
                    threads_by_sender[sn] = []
                threads_by_sender[sn].append({"direction": r["direction"], "message_text": r["message_text"]})
            
            queue_inserts = []
            for m in to_enqueue:
                sn = m.get("sender_name")
                if sn not in existing_queues:
                    queue_inserts.append({
                        "id": str(uuid.uuid4()),
                        "workspace_id": workspace_id,
                        "account_id": account_id,
                        "sender_name": sn,
                        "thread_messages_json": json.dumps(threads_by_sender.get(sn, [])),
                        "intent": m.get("intent"),
                        "heat_score": 50.0,
                        "status": "pending",
                    })
                    existing_queues.add(sn)
            
            if queue_inserts:
                supabase.table("approval_queue").insert(queue_inserts).execute()
                queued += len(queue_inserts)
            
    return {"new_saved": saved, "updated": updated, "queued": queued}


@router.post("/inbox/sync", response_model=dict)
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
def get_inbox_threads(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("messages").select("sender_name, message_text, direction, created_at").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        
        # Group by sender_name to get latest
        threads_dict = {}
        for r in res.data:
            sn = r["sender_name"]
            if sn not in threads_dict:
                threads_dict[sn] = {
                    "sender_name": sn,
                    "last_message": r["message_text"],
                    "direction": r["direction"],
                    "created_at": r["created_at"]
                }
                
        threads = list(threads_dict.values())
        return threads
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/inbox/threads/{sender_name}", response_model=List[dict])
def get_thread_messages(sender_name: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("messages").select("id, message_text, direction, created_at").eq("workspace_id", workspace_id).eq("sender_name", sender_name).order("created_at").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")



# ═══════════════════════════════════════════════════════════════════════════════
# ── KILL HEYREACH FEATURES ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

# ── Feature 1: AI Reply Co-Pilot (streaming) ──────────────────────────────────



# ── Feature 2: Lead Heat Scores ────────────────────────────────────────────────



# ── Feature 3: Intent-classified threads ──────────────────────────────────────

@router.get("/inbox/threads-with-intent", response_model=list)
def get_threads_with_intent(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Return thread list enriched with intent label from last inbound message."""
    try:
        res = supabase.table("messages").select("sender_name, message_text, direction, created_at, intent").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        
        threads_dict = {}
        for r in res.data:
            sn = r["sender_name"]
            if sn not in threads_dict:
                threads_dict[sn] = {
                    "sender_name": sn,
                    "message_text": r["message_text"],
                    "direction": r["direction"],
                    "created_at": r["created_at"],
                    "intent": "unknown",
                    "_seen_inbound": False
                }
                
            # Grab intent of latest inbound
            if r["direction"] == "inbound" and not threads_dict[sn]["_seen_inbound"]:
                threads_dict[sn]["intent"] = r.get("intent") or "unknown"
                threads_dict[sn]["_seen_inbound"] = True
                
        for t in threads_dict.values():
            del t["_seen_inbound"]
            
        return list(threads_dict.values())
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


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
