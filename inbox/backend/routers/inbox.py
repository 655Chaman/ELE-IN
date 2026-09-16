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

def process_csv_background(list_id: str, file_path: str, mappings: dict = None, clean_data: bool = False, workspace_id: str = None):
    from core.backend.api.auth_dep import get_service_client
    import csv
    import uuid
    
    supabase = get_service_client()
    try:
        # Stream from disk line by line instead of loading to RAM!
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            leads_to_insert = []
            
            # Parse all valid rows first (this is still memory-intensive if CSV is HUGE, 
            # but much better than raw string. To be strictly memory-safe, we should chunk 
            # the parse loop directly.)
            
            # Let's do true chunking directly from the reader!
            CHUNK_SIZE = 500
            total_inserted = 0
            
            chunk = []
            
            def process_chunk(current_chunk):
                nonlocal total_inserted
                if not current_chunk: return
                
                # Apply data hygiene and deduct credits
                if clean_data and workspace_id:
                    # Check credits
                    credit_res = supabase.table("workspaces").select("data_cleaning_credits").eq("id", workspace_id).execute()
                    credits = credit_res.data[0].get("data_cleaning_credits") if credit_res.data else 0
                    if credits is None: credits = 1000
                    
                    cost = len(current_chunk) // 100
                    if cost == 0: cost = 1 # Minimum 1 credit per chunk if less than 100
                    
                    if credits >= cost:
                        from leads.backend.services.data_hygiene import DataHygieneService
                        for lead in current_chunk:
                            lead["first_name"] = DataHygieneService.clean_name(lead.get("first_name", ""))
                            lead["last_name"] = DataHygieneService.clean_name(lead.get("last_name", ""))
                            lead["company_name"] = DataHygieneService.clean_company(lead.get("company_name", ""))
                        
                        # Deduct credits
                        supabase.table("workspaces").update({"data_cleaning_credits": credits - cost}).eq("id", workspace_id).execute()

                # Paranoia Layer 1: Delegate ALL deduplication and insertion to the atomic Postgres RPC
                # This guarantees 0 duplicates even across concurrent background workers.
                rpc_res = supabase.rpc("bulk_import_leads", {
                    "p_list_id": list_id,
                    "p_workspace_id": workspace_id,
                    "p_leads": current_chunk
                }).execute()
                
                inserted = rpc_res.data.get("inserted_count", 0) if rpc_res.data else len(current_chunk)
                total_inserted += inserted
                supabase.table("lead_lists").update({"row_count": -total_inserted}).eq("id", list_id).execute()

            # Use mappings if provided, else fallback to guess
            mappings = mappings or {}
            fn_col = mappings.get("first_name")
            ln_col = mappings.get("last_name")
            li_col = mappings.get("linkedin_url")
            co_col = mappings.get("company_name")
            
            for row in reader:
                if li_col and fn_col:
                    first_name = row.get(fn_col, '')
                    last_name = row.get(ln_col, '')
                    linkedin = row.get(li_col, '')
                    company = row.get(co_col, '')
                else:
                    row_lower = {k.lower().strip(): v for k, v in row.items() if k}
                    first_name = row_lower.get('first name', row_lower.get('firstname', ''))
                    last_name = row_lower.get('last name', row_lower.get('lastname', ''))
                    linkedin = row_lower.get('linkedin', row_lower.get('linkedin url', row_lower.get('profile url', '')))
                    company = row_lower.get('company', row_lower.get('company name', ''))
                
                if not linkedin:
                    continue
                    
                chunk.append({
                    "first_name": first_name,
                    "last_name": last_name,
                    "linkedin_url": linkedin,
                    "company_name": company,
                })
                
                if len(chunk) >= CHUNK_SIZE:
                    process_chunk(chunk)
                    chunk = []
                    
            # Process remaining
            if chunk:
                process_chunk(chunk)
                
        # Final update to positive number to mark completion
        supabase.table("lead_lists").update({"row_count": total_inserted}).eq("id", list_id).execute()
        
    except Exception as e:
        print(f"CSV background processing error: {e}")
        supabase.table("lead_lists").update({"row_count": -2}).eq("id", list_id).execute()
    finally:
        # Clean up the local temp file!
        if os.path.exists(file_path):
            os.remove(file_path)



class UploadUrlsRequest(BaseModel):
    name: str
    urls: list[str]



class UploadSalesNavRequest(BaseModel):
    name: str
    url: str
    account_id: Optional[str] = None   # Which LinkedIn account to scrape from
    max_results: Optional[int] = 100   # Default cap: 100 profiles per import

def process_voyager_search_background(
    list_id: str,
    url: str,
    workspace_id: str,
    account_id: Optional[str],
    max_results: int,
):
    """
    Native Voyager scraper background task.
    Replaces Apify entirely — uses the user's own LinkedIn session cookies
    already stored in Supabase to call LinkedIn's internal Voyager search API.
    """
    from core.backend.api.auth_dep import get_service_client
    supabase = get_service_client()

    try:
        # 1. Resolve which LinkedIn account to use
        if account_id:
            acc_res = supabase.table("accounts").select(
                "id, session_cookies_encrypted, is_active"
            ).eq("id", account_id).eq("workspace_id", workspace_id).execute()
        else:
            # Fall back to first active account in this workspace
            acc_res = supabase.table("accounts").select(
                "id, session_cookies_encrypted, is_active"
            ).eq("workspace_id", workspace_id).eq("is_active", True).limit(1).execute()

        if not acc_res.data:
            raise ValueError(
                "No active LinkedIn account found for this workspace. "
                "Please connect a LinkedIn account first."
            )

        acc_row = acc_res.data[0]
        # PARANOIA LAYER 1: Enqueue job instead of executing locally
        supabase.table("processing_jobs").insert({
            'job_type': 'voyager_search',
            'status': 'pending',
            'metadata': {
                'account_id': acc_row["id"],
                'workspace_id': workspace_id,
                'list_id': list_id,
                'url': url,
                'max_results': max_results
            }
        }).execute()
        return

        # 2. Parse the LinkedIn search URL into Voyager-compatible params
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        search_params = {}
        if qs.get("keywords"):
            search_params["keywords"] = qs["keywords"][0]
        if qs.get("title"):
            search_params["title"] = qs["title"][0]
        if qs.get("company"):
            search_params["company"] = qs["company"][0]
        if qs.get("school"):
            search_params["school"] = qs["school"][0]
        if qs.get("network"):
            search_params["network"] = qs["network"][0]

        # 3. Run the Voyager scraper
        raw_cookies = acc_row.get("session_cookies_encrypted")
        cookie_json = crypto.decrypt_bytes(raw_cookies).decode('utf-8') if isinstance(raw_cookies, (bytes, bytearray)) else raw_cookies

        scraper = VoyagerScraper(
            cookies_json=cookie_json,
            account_id=acc_row["id"],
            supabase=supabase,
        )

        profiles = scraper.search_people(
            search_params=search_params,
            max_results=max_results,
        )

        # 4. Persist leads to Supabase using the RPC
        rpc_leads = []
        for profile in profiles:
            url = profile.get("linkedin_url")
            if not url:
                continue
                
            rpc_leads.append({
                "linkedin_url": url,
                "first_name": profile.get("first_name"),
                "last_name": profile.get("last_name"),
                "job_title": profile.get("headline")
            })

        skipped_dupes = 0
        if rpc_leads:
            rpc_res = supabase.rpc("bulk_import_leads", {
                "p_list_id": list_id,
                "p_workspace_id": workspace_id,
                "p_leads": rpc_leads
            }).execute()
            row_count = rpc_res.data.get("inserted_count", 0) if rpc_res.data else 0
            skipped_dupes = len(rpc_leads) - row_count
        else:
            row_count = 0

        completion_note = f"completed — {skipped_dupes} duplicates skipped" if skipped_dupes else "completed"
        supabase.table("lead_lists").update({
            "row_count": row_count,
            "status": completion_note,
        }).eq("id", list_id).execute()

    except DailyLimitExceeded as e:
        import logging
        logger = logging.getLogger(__name__)
        logging.getLogger(__name__).warning(f"[VoyagerSearch] Daily limit: {e}")
        supabase.table("lead_lists").update({
            "row_count": -3,
            "status": "daily_limit",
        }).eq("id", list_id).execute()

    except VoyagerThrottled as e:
        import logging
        logger = logging.getLogger(__name__)
        logging.getLogger(__name__).error(f"[VoyagerSearch] Throttled: {e}")
        supabase.table("lead_lists").update({
            "row_count": -4,
            "status": "throttled",
        }).eq("id", list_id).execute()

    except SessionExpired as e:
        import logging
        logger = logging.getLogger(__name__)
        logging.getLogger(__name__).error(f"[VoyagerSearch] Session expired: {e}")
        supabase.table("lead_lists").update({
            "row_count": -5,
            "status": "session_expired",
            "error_message": str(e),
        }).eq("id", list_id).execute()

    except ValueError as e:
        import logging
        logger = logging.getLogger(__name__)
        logging.getLogger(__name__).error(f"[VoyagerSearch] Config error: {e}")
        supabase.table("lead_lists").update({
            "row_count": -2,
            "status": "error",
            "error_message": str(e),
        }).eq("id", list_id).execute()

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logging.getLogger(__name__).error(f"[VoyagerSearch] Unexpected error: {e}")
        supabase.table("lead_lists").update({
            "row_count": -2,
            "status": "error",
        }).eq("id", list_id).execute()







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
        'metadata': {
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
        'metadata': {
            'account_id': account_id,
            'workspace_id': workspace_id
        }
    }).execute()
    
    messages = payload.get("messages", [])
    classified = 0
    
    if messages:
        try:
            from knowledge.backend.services.elein_ai_service import classify_intent
            for m in messages:
                if m.get("direction") == "inbound":
                    intent_data = await classify_intent(m["message_text"], workspace_id=workspace_id)
                    m["intent"] = intent_data.get("intent", "unknown")
                    m["intent_confidence"] = intent_data.get("confidence", 0.0)
                    classified += 1

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
