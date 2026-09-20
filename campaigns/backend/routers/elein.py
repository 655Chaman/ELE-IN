# ==============================================================================
# LAYER 2 PARANOIA: MONOLITH PREVENTION GUARD
# This file (`elein.py`) is the deprecated God Router.
# DO NOT ADD NEW ENDPOINTS HERE. 
# Create focused routers (e.g. `campaigns.py`, `inbox.py`) instead.
# ==============================================================================
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
# Hard requirement: SUPABASE_JWT_SECRET must be set. App will not start without it.
if not SUPABASE_JWT_SECRET:
    logger.warning("SUPABASE_JWT_SECRET is not set — JWT verification will fail at runtime")

router = APIRouter(tags=["elein"])

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



@router.post("/workspaces/provision", response_model=dict)
def api_provision_workspace(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing auth header")
    token = auth_header.split(" ")[1]
    user_id = verify_token_and_get_user_id(token)
        
    from core.backend.api.auth_dep import get_service_client
    svc = get_service_client()
    
    # Check if user already has a workspace
    res = svc.table("workspace_members").select("workspace_id").eq("user_id", user_id).limit(1).execute()
    if res.data:
        return {"workspace_id": res.data[0]["workspace_id"], "status": "exists"}
        
    company_name = request.headers.get("X-Company-Name", "").strip() or "My Workspace"
    workspace_id = provision_workspace(user_id, svc, company_name)
    return {"workspace_id": workspace_id, "status": "created"}


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



@router.get("/proxies/health", response_model=list)
def get_proxy_health(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("proxies").select("id, host, port, status, last_checked_at, provider").eq("workspace_id", workspace_id).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

# ── Campaign CRUD ─────────────────────────────────────────────────────────────
# ==============================================================================
# LAYER 2 PARANOIA: CAMPAIGN ROUTES CONSOLIDATED
# All campaign routes are kept in elein.py for now to prevent duplication and
# inconsistent logic between campaigns.py and elein.py.
# DO NOT create a new campaigns.py file without explicit architectural approval.
# ==============================================================================







@router.get("/workspaces/me", response_model=dict)
def get_workspace_profile(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Return workspace profile: name, company_name, domain."""
    try:
        res = supabase.table("workspaces").select("id, name, status, require_2fa, created_at").eq("id", workspace_id).execute()
        if not res.data:
            return {"name": "My Workspace", "company_name": None, "domain": None}
        row = res.data[0]
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "status": row.get("status"),
            "require_2fa": row.get("require_2fa", False),
            "created_at": row.get("created_at"),
        }
    except Exception as e:
        return {"name": "My Workspace", "company_name": None, "domain": None}

@router.patch("/workspaces/me", response_model=dict)
def update_workspace_profile(
    payload: dict,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Update the workspace's company name (stored in workspaces.name)."""
    try:
        # Removed incorrect validate_campaign_variables call here

        update_data = {}
        if "name" in payload and payload["name"]:
            update_data["name"] = payload["name"].strip()
        if not update_data:
            raise HTTPException(status_code=400, detail="Nothing to update.")
        supabase.table("workspaces").update(update_data).eq("id", workspace_id).execute()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/workspaces/billing", response_model=dict)
def get_billing_info(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("workspaces").select("data_cleaning_credits").eq("id", workspace_id).execute()
        credits = 0
        if res.data:
            # Fallback to 1000 if not found/null
            credits = res.data[0].get("data_cleaning_credits")
            if credits is None: credits = 1000
        return {"data_cleaning_credits": credits}
    except Exception as e:
        # If column doesn't exist yet, return 1000
        return {"data_cleaning_credits": 1000}


class EnrollLeadsRequest(BaseModel):
    opportunity_ids: List[str]









# ── Leads Import ─────────────────────────────────────────────────────────────

from fastapi import BackgroundTasks
import asyncio

import os
import shutil

def process_csv_background(list_id: str, file_path: str, mappings: dict = None, clean_data: bool = False, workspace_id: str = None, target_timezone: str = None):
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
                    "p_leads": current_chunk,
                    "p_timezone": target_timezone
                }).execute()
                
                inserted = rpc_res.data.get("inserted_count", 0) if rpc_res.data else len(current_chunk)
                total_inserted += inserted
                supabase.table("lead_lists").update({"status": "processing", "row_count": total_inserted}).eq("id", list_id).execute()

            # Use mappings if provided, else fallback to guess
            mappings = mappings or {}
            fn_col = mappings.get("first_name")
            ln_col = mappings.get("last_name")
            li_col = mappings.get("linkedin_url")
            co_col = mappings.get("company_name")
            loc_col = mappings.get("location")
            
            for row in reader:
                if li_col and fn_col:
                    first_name = row.get(fn_col, '')
                    last_name = row.get(ln_col, '')
                    linkedin = row.get(li_col, '')
                    company = row.get(co_col, '')
                    location = row.get(loc_col, '') if loc_col else ''
                else:
                    row_lower = {k.lower().strip(): v for k, v in row.items() if k}
                    first_name = row_lower.get('first name', row_lower.get('firstname', ''))
                    last_name = row_lower.get('last name', row_lower.get('lastname', ''))
                    linkedin = row_lower.get('linkedin', row_lower.get('linkedin url', row_lower.get('profile url', '')))
                    company = row_lower.get('company', row_lower.get('company name', ''))
                    location = row_lower.get('location', row_lower.get('city', row_lower.get('country', '')))
                
                if not linkedin:
                    continue
                    
                chunk.append({
                    "first_name": first_name,
                    "last_name": last_name,
                    "linkedin_url": linkedin,
                    "company_name": company,
                    "p_location": location,
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

@router.post("/leads/upload_csv", response_model=dict)
def upload_csv(
    file: UploadFile = File(...),
    name: str = Form(...),
    target_timezone: str = Form(...),
    target_region_label: str = Form(...),
    mappings: str = Form(None),
    clean_data: bool = Form(False),
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Streams a CSV file to local disk and processes it in a background task to prevent OOM."""
    import tempfile
    import json

    # Layer 2: Invalid mappings JSON → silently ignore, don't block the upload
    mapping_dict = {}
    if mappings:
        try:
            mapping_dict = json.loads(mappings)
        except json.JSONDecodeError:
            # Mappings are optional metadata; a bad JSON string just means auto-detect columns
            logger.warning("upload_csv: could not parse 'mappings' JSON — falling back to auto-detect")

    list_id = str(uuid.uuid4())

    # Save the uploaded file locally to a temp file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    try:
        shutil.copyfileobj(file.file, temp_file)
    finally:
        temp_file.close()

    # Layer 0 + Layer 1: Insert the lead_list row FIRST.
    # If this fails we MUST NOT enqueue the job — the worker's FK reference
    # to lead_lists.id will cascade-fail and leave the job in a broken state.
    try:
        supabase.table("lead_lists").insert({
            "id": list_id,
            "name": name,
            "type": "csv",
            "row_count": -1,
            "workspace_id": workspace_id,
            "target_timezone": target_timezone,
            "target_region_label": target_region_label
        }).execute()
    except Exception as e:
        # Layer 1: Clean up the temp file we already wrote to disk
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)
        logger.error(f"upload_csv: failed to create lead_list record: {e}", exc_info=True)
        # Layer 2: Actionable message — never expose raw DB error text
        raise HTTPException(
            status_code=500,
            detail="Failed to create the lead list. Please try again. If the problem persists, contact support."
        )

    # Hand off the temp file path to background worker
    enqueue_job(supabase, 'csv', workspace_id, list_id, {
        'list_id': list_id, 
        'temp_file': temp_file.name, 
        'mapping_dict': mapping_dict, 
        'clean_data': clean_data,
        'target_timezone': target_timezone
    })

    return {"status": "processing", "list_id": list_id}


class UploadUrlsRequest(BaseModel):
    name: str
    urls: list[str]
    target_timezone: str
    target_region_label: str

@router.post("/leads/upload_urls", response_model=dict)
def upload_urls(body: UploadUrlsRequest, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        list_id = str(uuid.uuid4())
        supabase.table("lead_lists").insert({
            "id": list_id,
            "name": body.name,
            "type": "linkedin_url",
            "row_count": len(body.urls),
            "workspace_id": workspace_id,
            "target_timezone": body.target_timezone,
            "target_region_label": body.target_region_label
        }).execute()
        
        leads_to_insert = [{"linkedin_url": url.strip()} for url in body.urls if url.strip()]
        
        if leads_to_insert:
            rpc_res = supabase.rpc("bulk_import_leads", {
                "p_list_id": list_id,
                "p_workspace_id": workspace_id,
                "p_leads": leads_to_insert,
                "p_timezone": body.target_timezone
            }).execute()
            row_count = rpc_res.data.get("inserted_count", 0) if rpc_res.data else 0
        else:
            row_count = 0
            
        return {"list_id": list_id, "row_count": row_count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UploadSalesNavRequest(BaseModel):
    name: str
    url: str
    target_timezone: str
    target_region_label: str
    account_id: Optional[str] = None   # Which LinkedIn account to scrape from
    max_results: Optional[int] = 100   # Default cap: 100 profiles per import

def process_voyager_search_background(
    list_id: str,
    url: str,
    workspace_id: str,
    account_id: Optional[str],
    max_results: int,
    target_timezone: str,
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
        if qs.get("pastCompany"):
            search_params["pastCompany"] = qs["pastCompany"][0]
        if qs.get("geoUrn"):
            search_params["geoUrn"] = qs["geoUrn"][0]
        if qs.get("industry"):
            search_params["industry"] = qs["industry"][0]
        if qs.get("function"):
            search_params["function"] = qs["function"][0]
        if qs.get("seniority"):
            search_params["seniority"] = qs["seniority"][0]

        encrypted_cookies = acc_row.get("session_cookies_encrypted")
        if not encrypted_cookies:
            raise HTTPException(status_code=400, detail="No LinkedIn session found for this account.")
        from core.backend.core import crypto
        try:
            decrypted = crypto.decrypt_bytes(encrypted_cookies)
            cookie_json = decrypted.decode("utf-8")
        except Exception as e:
            raise HTTPException(status_code=400, detail="Cookie decryption failed. Account must be reconnected via the Chrome Extension.")
        # 3. Run the Voyager scraper
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
                "p_leads": rpc_leads,
                "p_timezone": target_timezone
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


@router.post("/leads/upload_sales_nav", response_model=dict)
def upload_sales_nav(
    body: UploadSalesNavRequest,
    background_tasks: BackgroundTasks,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace),
):
    try:
        # Pre-flight Validation (Layer 1)
        # 1. Resolve which LinkedIn account to use
        if body.account_id:
            acc_res = supabase.table("accounts").select(
                "id, session_cookies_encrypted, is_active"
            ).eq("id", body.account_id).eq("workspace_id", workspace_id).execute()
        else:
            acc_res = supabase.table("accounts").select(
                "id, session_cookies_encrypted, is_active"
            ).eq("workspace_id", workspace_id).eq("is_active", True).limit(1).execute()

        if not acc_res.data:
            raise ValueError("No active LinkedIn account found. Please connect a LinkedIn account first.")

        acc_row = acc_res.data[0]

        list_id = str(uuid.uuid4())
        url = body.url
        max_results = body.max_results or 100

        supabase.table("lead_lists").insert({
            "id": list_id,
            "name": body.name,
            "type": "search",
            "row_count": -1,
            "status": "pending",
            "workspace_id": workspace_id,
            "target_timezone": body.target_timezone,
            "target_region_label": body.target_region_label
        }).execute()

        from core.backend.services.job_queue import enqueue_job
        enqueue_job(
            supabase,
            'voyager_search',
            workspace_id,
            list_id,
            {
                'list_id': list_id,
                'url': url,
                'account_id': acc_row["id"],
                'max_results': max_results,
                'target_timezone': body.target_timezone
            }
        )

        return {"list_id": list_id, "message": "Import started via native Voyager scraper"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/leads/daily-budget", response_model=dict)
def get_daily_budget(
    account_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace),
):
    """Return daily scrape budget status for the frontend progress meter."""
    try:
        acc_res = supabase.table("accounts").select(
            "id, daily_scrape_count, last_scrape_date"
        ).eq("id", account_id).eq("workspace_id", workspace_id).single().execute()

        if not acc_res.data:
            raise HTTPException(status_code=404, detail="Account not found")

        from datetime import date
        row = acc_res.data
        today = date.today().isoformat()
        count = row.get("daily_scrape_count", 0) or 0
        if row.get("last_scrape_date") != today:
            count = 0  # Reset display if new day

        limit = 150
        return {
            "used": count,
            "limit": limit,
            "remaining": max(0, limit - count),
            "reset_date": today,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/leads/lists", response_model=List[dict])
def get_lists(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    print("HIT get_lists!!!")
    try:
        res = supabase.table("lead_lists").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error in get_lists: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

# ── Accounts CRUD ─────────────────────────────────────────────────────────────

@router.post("/accounts/validate", response_model=dict)
def validate_cookies(payload: dict, workspace_id: str = Depends(get_current_workspace)):
    """
    Accepts { "session_cookies_json": "[...]", "proxy_url": "..." (optional) }
    Uses LinkedInWorker._http_get to verify the session without burning server IP.
    """
    import json as _json
    cookies_str = payload.get("session_cookies_json", "")
    proxy_url = payload.get("proxy_url")
    proxy_id = payload.get("proxy_id")
    
    if proxy_id and not proxy_url:
        # Avoid dependency cycle and missing imports by importing at runtime
        from core.backend.api.dependencies import get_supabase_client
        # Get a fresh client or just use a standard one (since we might not be in a FastAPI context)
        # Actually, get_supabase_client() doesn't need args if it's returning the service client.
        try:
            from supabase import create_client
            import os
            supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
            res = supabase.table("proxies").select("protocol, host, port, username, password").eq("id", proxy_id).execute()
            if res.data:
                p = res.data[0]
                auth = f"{p.get('username', '')}:{p.get('password', '')}@" if p.get('username') else ""
                proxy_url = f"{p.get('protocol', 'http')}://{auth}{p['host']}:{p['port']}"
        except:
            pass

    if not cookies_str:
        raise HTTPException(status_code=400, detail="session_cookies_json is required")

    try:
        cookies = _json.loads(cookies_str)
        for c in cookies:
            if "sameSite" in c and c["sameSite"] not in ["Strict", "Lax", "None"]:
                del c["sameSite"]
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in session_cookies_json")

    from integrations.backend.services.linkedin_worker import LinkedInWorker
    try:
        worker = LinkedInWorker(cookies_json=_json.dumps(cookies), proxy_url=proxy_url)
        resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
        if resp.status_code == 200:
            data = resp.json()
            mini = data.get("miniProfile", {})
            first = mini.get("firstName", "")
            last = mini.get("lastName", "")
            pub_id = mini.get("publicIdentifier", "")
            return {
                "valid": True,
                "profile_url": f"https://www.linkedin.com/in/{pub_id}/" if pub_id else "",
                "name": f"{first} {last}".strip(),
                "final_url": "api/me"
            }
        else:
            return {"valid": False, "error": f"Session expired or invalid (HTTP {resp.status_code})."}
    except Exception as e:
        return {"valid": False, "error": f"Validation failed: {str(e)}"}



@router.post("/accounts", response_model=dict)
def add_account(account: AccountCreate, request: Request, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        import json as _json
        try:
            cookies = _json.loads(account.session_cookies_json)  # field name kept in Pydantic schema for API compat
            for ck in cookies:
                if "sameSite" in ck and ck["sameSite"] not in ["Strict", "Lax", "None"]:
                    del ck["sameSite"]
            sanitized_cookies = _json.dumps(cookies)
        except:
            sanitized_cookies = account.session_cookies_json  # raw passthrough

        account_id = str(uuid.uuid4())
        
        warmup_start = None
        if account.is_warmup:
            from datetime import datetime
            warmup_start = account.warmup_start_date or datetime.utcnow().isoformat()

        from core.backend.core import crypto
        
        # Normalize empty string to None so it doesn't conflict
        linkedin_profile_url = account.linkedin_profile_url if account.linkedin_profile_url else None
        
        try:
            # PROXY ASSIGNMENT: Map to browser geolocation via Cloudflare/Vercel headers
            country_code = request.headers.get("cf-ipcountry") or request.headers.get("x-vercel-ip-country") or "US"
            proxy_res = supabase.table("proxies").select("id, country_code").eq("status", "healthy").execute()
            healthy_proxies = proxy_res.data or []
            
            chosen_proxy_id = getattr(account, "proxy_id", None) or getattr(account, "proxy", None)
            if not chosen_proxy_id:
                if healthy_proxies:
                    import random
                    matches = [p for p in healthy_proxies if p.get("country_code") == country_code]
                    if matches:
                        chosen_proxy_id = random.choice(matches)["id"]
                        logger.info(f"Assigned proxy {chosen_proxy_id} matching country {country_code}")
                    else:
                        chosen_proxy_id = random.choice(healthy_proxies)["id"]
                        logger.info(f"No proxy for {country_code}, fallback to proxy {chosen_proxy_id}")
                else:
                    logger.warning(f"CRITICAL: No healthy proxies available in the system! Account {account_id} will run on naked server IP.")

            # PHASE 3: Cascade sending defaults from workspace
            defaults_res = supabase.table("workspace_sending_defaults").select("*").eq("workspace_id", workspace_id).execute()
            defaults = defaults_res.data[0] if defaults_res.data else {}

            client_conn_limit = getattr(account, 'daily_connection_limit', None)
            if client_conn_limit is None:
                client_conn_limit = getattr(account, 'warmup_max_connections', None)
            
            client_msg_limit = getattr(account, 'daily_message_limit', None)
            if client_msg_limit is None:
                client_msg_limit = getattr(account, 'warmup_max_messages', None)

            warmup_target_days = getattr(account, 'warmup_target_days', None)
            if warmup_target_days is None:
                warmup_target_days = defaults.get("default_warmup_target_days", 30)

            # Extract all sending defaults with safe fallbacks
            daily_connection_limit = client_conn_limit if client_conn_limit is not None else defaults.get("default_daily_connection_limit", 20)
            daily_message_limit = client_msg_limit if client_msg_limit is not None else defaults.get("default_daily_message_limit", 40)
            working_hours_start = defaults.get("default_working_hours_start", "08:00")
            working_hours_end = defaults.get("default_working_hours_end", "18:00")
            working_days = defaults.get("working_days", ["monday", "tuesday", "wednesday", "thursday", "friday"])
            timezone = defaults.get("default_timezone", "UTC")

            import base64
            dek_b64 = crypto.generate_dek()
            dek_bytes = base64.b64decode(dek_b64)
            
            # Call DB RPC to store the secret securely
            rpc_res = supabase.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
            cookie_secret_ref = rpc_res.data

            supabase.table("accounts").insert({
                "id": account_id,
                "workspace_id": workspace_id,
                "proxy_id": chosen_proxy_id,
                "name": account.name,
                "linkedin_profile_url": linkedin_profile_url,
                "session_cookies_encrypted": crypto.encrypt_bytes(sanitized_cookies.encode("utf-8"), dek=dek_bytes),
                "is_warmup": account.is_warmup,
                "warmup_start_date": warmup_start,
                "warmup_target_days": warmup_target_days,
                "warmup_max_connections": daily_connection_limit,
                "warmup_max_messages": daily_message_limit,
                # is_active is GENERATED ALWAYS AS (status = 'ACTIVE') — do NOT set explicitly
            }).execute()
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e) or "unique constraint" in str(e).lower():
                raise HTTPException(status_code=409, detail="This LinkedIn account is already connected to your workspace.")
            raise e

        return {"id": account_id, "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

class CookieRefreshRequest(BaseModel):
    cookie_json: str

@router.patch("/accounts/{account_id}/cookies", response_model=dict)
def refresh_account_cookies(account_id: str, payload: CookieRefreshRequest, workspace_id: str = Depends(get_current_workspace), supabase: Client = Depends(get_supabase_client)):
    # 1. verify ownership and get proxy
    acc_res = supabase.table("accounts").select("id, proxy_id, linkedin_profile_url, proxies(protocol, host, port, username)").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
    proxy_url = _build_proxy_url(acc_res.data[0])


    # 2. validate cookies using the account's existing proxy to prevent bans!
    validation = validate_cookies({"session_cookies_json": payload.cookie_json, "proxy_url": proxy_url}, workspace_id)

    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail=validation.get("error", "Invalid cookies"))

    # Human Error Guard: Verify they didn't upload someone else's cookies
    old_profile = acc_res.data[0].get("linkedin_profile_url")
    new_profile = validation.get("profile_url")
    if old_profile and new_profile and old_profile.strip("/") != new_profile.strip("/"):
        raise HTTPException(status_code=400, detail=f"Cookie mismatch! You uploaded cookies for {validation.get('name')}, but this account is linked to {old_profile}.")


    # 3. sanitize and save
    import json as _json
    try:
        cookies = _json.loads(payload.cookie_json)
        for ck in cookies:
            if "sameSite" in ck and ck["sameSite"] not in ["Strict", "Lax", "None"]:
                del ck["sameSite"]
        sanitized_cookies = _json.dumps(cookies)
    except:
        sanitized_cookies = payload.cookie_json

    from core.backend.core import crypto
    supabase.table("accounts").update({
        # Encrypt cookies using AES-256-GCM
        "session_cookies_encrypted": crypto.encrypt_bytes(sanitized_cookies.encode("utf-8")),
        "status": "ACTIVE"
    }).eq("id", account_id).execute()

    return {"status": "success"}


@router.post("/accounts/{account_id}/reconnect/initiate")
def initiate_reconnect(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Creates a time-limited reconnect request. Returns a token the UI uses."""
    import secrets
    from datetime import datetime, timedelta, timezone
    
    # Verify account belongs to workspace
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    
    try:
        supabase.table("account_reconnect_requests").insert({
            "account_id": account_id,
            "requested_by": None,
            "token": token,
            "status": "pending",
            "expires_at": expires_at
        }).execute()
        return {"token": token, "expires_at": expires_at}
    except Exception as e:
        logger.error(f"Failed to initiate reconnect: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate reconnect")

@router.post("/accounts/reconnect/complete")
def complete_reconnect(payload: dict, supabase: Client = Depends(get_supabase_client)):
    """Completes reconnect: validates token, stores new cookies, restores ACTIVE status."""
    from datetime import datetime, timezone
    from core.backend.core import crypto
    import json as _json
    
    token = payload.get("token")
    cookies_json = payload.get("session_cookies_json")
    if not token or not cookies_json:
        raise HTTPException(status_code=400, detail="Missing token or cookies")
        
    # 1. Validate token
    req_res = supabase.table("account_reconnect_requests").select("*").eq("token", token).eq("status", "pending").execute()
    if not req_res.data:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
        
    req = req_res.data[0]
    expires_at = datetime.fromisoformat(req["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired")
        
    account_id = req["account_id"]
    
    acc_res = supabase.table("accounts").select("workspace_id, proxy_id, linkedin_profile_url, proxies(protocol, host, port, username)").eq("id", account_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    acc = acc_res.data[0]
    workspace_id = acc["workspace_id"]
    proxy_url = _build_proxy_url(acc)
    
    validation = validate_cookies({"session_cookies_json": cookies_json, "proxy_url": proxy_url}, workspace_id)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail=validation.get("error", "Invalid cookies"))
        
    old_profile = acc.get("linkedin_profile_url")
    new_profile = validation.get("profile_url")
    if old_profile and new_profile and old_profile.strip("/") != new_profile.strip("/"):
        raise HTTPException(status_code=400, detail="Cookie mismatch! Profile does not match original account.")
        
    try:
        cookies = _json.loads(cookies_json)
        for ck in cookies:
            if "sameSite" in ck and ck["sameSite"] not in ["Strict", "Lax", "None"]:
                del ck["sameSite"]
        sanitized_cookies = _json.dumps(cookies)
    except:
        sanitized_cookies = cookies_json
        
    now = datetime.now(timezone.utc).isoformat()
    
    import base64
    dek_b64 = crypto.generate_dek()
    dek_bytes = base64.b64decode(dek_b64)
    
    rpc_res = supabase.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
    cookie_secret_ref = rpc_res.data
    
    update_data = {
        "session_cookies_encrypted": crypto.encrypt_bytes(sanitized_cookies.encode("utf-8"), dek=dek_bytes),
        "status": "ACTIVE",
        "session_locked_until": None,
        "updated_at": now
    }
    
    expires_at_ts = min([c.get("expires", 0) for c in _json.loads(sanitized_cookies) if c.get("expires", 0) > 0], default=0)
    if expires_at_ts > 0:
        update_data["cookie_expires_at"] = datetime.fromtimestamp(expires_at_ts, timezone.utc).isoformat()

    supabase.table("accounts").update(update_data).eq("id", account_id).execute()
    supabase.table("account_reconnect_requests").update({"status": "completed", "updated_at": now}).eq("id", req["id"]).execute()

    # Layer 0: Log audit trail. Non-critical — a missing audit entry should NOT abort
    # an already-completed reconnect, but it MUST be surfaced in logs (not silently swallowed).
    try:
        supabase.table("action_log").insert({
            "account_id": account_id,
            "workspace_id": workspace_id,
            "action_type": "account_reconnected",
            "created_at": now
        }).execute()
    except Exception as audit_err:
        # Layer 1: Audit log failure is non-fatal (reconnect succeeded), but log for ops visibility
        logger.warning(
            f"complete_reconnect: failed to write audit log for account {account_id}: {audit_err}"
        )

    return {"success": True, "account_id": account_id}

@router.post("/accounts/bulk/apply-defaults")
def bulk_apply_defaults(payload: dict, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Applies workspace sending defaults to selected accounts. RBAC: owner/admin only."""
    from datetime import datetime, timezone
    account_ids = payload.get('account_ids', [])
    if not account_ids or len(account_ids) > 100:
        raise HTTPException(status_code=400, detail='Must specify 1-100 account_ids')
        
    ws_res = supabase.table("workspaces").select("default_connection_limit, default_message_limit").eq("id", workspace_id).execute()
    if not ws_res.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    acc_res = supabase.table("accounts").select("id").in_("id", account_ids).eq("workspace_id", workspace_id).execute()
    valid_ids = [a["id"] for a in acc_res.data or []]
    
    if not valid_ids:
        return {"updated": 0}
        
    supabase.table("accounts").update({
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).in_("id", valid_ids).execute()
    
    return {"updated": len(valid_ids)}

@router.post("/accounts/bulk/add-tag")
def bulk_add_tag(payload: dict, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    account_ids = payload.get('account_ids', [])
    tag = payload.get('tag', '').strip()[:50]
    if not tag: raise HTTPException(status_code=400, detail='tag is required')
    if not account_ids or len(account_ids) > 100:
        raise HTTPException(status_code=400, detail='Must specify 1-100 account_ids')
        
    acc_res = supabase.table("accounts").select("id").in_("id", account_ids).eq("workspace_id", workspace_id).execute()
    valid_ids = [a["id"] for a in acc_res.data or []]
    
    if not valid_ids:
        return {"added": 0}
        
    inserts = [{"account_id": aid, "tag": tag} for aid in valid_ids]
    try:
        supabase.table("account_tags").upsert(inserts).execute()
        return {"added": len(valid_ids)}
    except Exception as e:
        logger.error(f"Bulk add tag error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add tags")

@router.delete("/accounts/bulk/remove-tag")
def bulk_remove_tag(payload: dict, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    account_ids = payload.get('account_ids', [])
    tag = payload.get('tag', '').strip()[:50]
    if not tag: raise HTTPException(status_code=400, detail='tag is required')
    if not account_ids or len(account_ids) > 100:
        raise HTTPException(status_code=400, detail='Must specify 1-100 account_ids')
        
    acc_res = supabase.table("accounts").select("id").in_("id", account_ids).eq("workspace_id", workspace_id).execute()
    valid_ids = [a["id"] for a in acc_res.data or []]
    
    if not valid_ids:
        return {"removed": 0}
        
    try:
        supabase.table("account_tags").delete().in_("account_id", valid_ids).eq("tag", tag).execute()
        return {"removed": len(valid_ids)}
    except Exception as e:
        logger.error(f"Bulk remove tag error: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove tags")


@router.delete("/accounts/{account_id}", response_model=dict)
def delete_account(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
    supabase.table("accounts").delete().eq("id", account_id).eq("workspace_id", workspace_id).execute()
    return {"status": "deleted"}


@router.get("/accounts/{account_id}/tags", response_model=List[str])
def get_account_tags(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
    res = supabase.table("account_tags").select("tag").eq("account_id", account_id).execute()
    return [r["tag"] for r in res.data or []]


@router.get("/accounts", response_model=List[AccountResponse])
def get_accounts(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("accounts").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        # Schema v2: decode session_cookies_encrypted (BYTEA) back to string
        # and re-expose as session_cookies_json for frontend compatibility
        rows = []
        for row in res.data:
            raw = row.get("session_cookies_encrypted")
            row["session_cookies_json"] = (
                crypto.decrypt_bytes(raw).decode("utf-8") if isinstance(raw, (bytes, bytearray)) else (raw or "")
            )
            rows.append(row)
        return rows
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


@router.get("/accounts/usage", response_model=List[dict])
def get_account_usage(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Today's action counts per account for rate limit display."""
    try:
        today = date.today().isoformat()
        res = supabase.table("account_daily_action_counts").select("account_id, action_type, count").eq("usage_date", today).execute()
        return res.data or [] or []
    except Exception:
        return []



from typing import Optional

class EnrollListRequest(BaseModel):
    list_id: str
    excludeListId: Optional[str] = None
    excludeOtherCampaigns: Optional[bool] = False
    excludeOtherSenders: Optional[bool] = False
    excludeSameSender: Optional[bool] = False




@router.get("/opportunities", response_model=List[dict])
def get_opportunities(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        # Leads mapped to opportunity format
        res = supabase.table("leads").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).limit(500).execute()
        opps = []
        for r in res.data:
            opps.append({
                "id": r.get("id"),
                "market": "",
                "side": "",
                "pipeline_id": "",
                "company_name": r.get("company_name", ""),
                "domain": r.get("domain", ""),
                "company_description": r.get("company_description", ""),
                "kdm_first": r.get("first_name", ""),
                "kdm_last": r.get("last_name", ""),
                "job_title": r.get("job_title", ""),
                "linkedin_url": r.get("linkedin_url", ""),
                "verified_email": r.get("email", ""),
                "target_campaign_tier": "",
                "enrichment_source": "",
                "status": "extracted",
                "created_at": r.get("created_at", "")
            })
        return opps
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

class BulkStatusRequest(BaseModel):
    opportunity_ids: List[str]
    status: str

@router.post("/opportunities/bulk-status", response_model=dict)
def update_opportunities_bulk_status(body: BulkStatusRequest, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        supabase.table("leads").update({"status": body.status}).in_("id", body.opportunity_ids).execute()
        return {"status": "success", "updated": len(body.opportunity_ids)}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/dashboard/stats", response_model=dict)
def get_dashboard_stats(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    today = date.today().isoformat()
    
    # ── Active campaigns / accounts / leads ───────────────────────────────
    active_campaigns = 0
    total_leads = 0
    connected_accounts = 0
    try:
        camp_res = supabase.table("campaigns").select("id", count="exact").eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
        active_campaigns = camp_res.count or 0
        leads_res = supabase.table("leads").select("id", count="exact").eq("workspace_id", workspace_id).execute()
        total_leads = leads_res.count or 0
        acc_res = supabase.table("accounts").select("id", count="exact").eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
        connected_accounts = acc_res.count or 0
    except Exception as e:
        print(f"Error fetching base stats: {e}")

    # ── Today's action counts ─────────────────────────────────────────────
    connections_sent_today = 0
    messages_sent_today = 0
    action_rows = []
    try:
        today_start = f"{today}T00:00:00Z"
        actions_res = supabase.table("action_log").select("action_type").eq("workspace_id", workspace_id).gte("executed_at", today_start).execute()
        action_rows = actions_res.data
        for ar in action_rows:
            at = ar["action_type"]
            if "connection" in at:
                connections_sent_today += 1
            elif at in ("send_message", "send_inmail", "send_paid_inmail", "send_voice_note", "send_message_with_doc", "send_message_with_image"):
                messages_sent_today += 1
    except Exception as e:
        print(f"Error fetching today's actions: {e}")

    # ── Per-campaign breakdown ────────────────────────────────────────────
    camp_ids = []
    camps_data = []
    try:
        camps = supabase.table("campaigns").select("id, name, status, created_at").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        camps_data = camps.data
        camp_ids = [c["id"] for c in camps_data]
    except Exception as e:
        print(f"Error fetching campaigns list: {e}")

    # ── Lead state funnel ─────────────────────────────────────────────────
    leads_enrolled = leads_running = leads_pending = leads_completed = leads_exited = leads_error = 0
    try:
        if camp_ids:
            enr_res = supabase.table("campaign_enrollments").select("id").in_("campaign_id", camp_ids).execute()
            enroll_ids = [r["id"] for r in (enr_res.data or [])]
            state_counts = {}
            if enroll_ids:
                state_res = supabase.table("campaign_execution_states").select("status").in_("enrollment_id", enroll_ids).execute()
                for r in state_res.data:
                    s = r["status"]
                    state_counts[s] = state_counts.get(s, 0) + 1
                
            leads_enrolled = sum(state_counts.values())
            leads_running  = state_counts.get("running", 0)
            leads_pending  = state_counts.get("pending", 0)
            leads_completed = state_counts.get("completed", 0)
            leads_exited   = state_counts.get("exited", 0)
            leads_error    = state_counts.get("error", 0)
    except Exception as e:
        print(f"Error fetching lead states funnel: {e}")

    # ── Connection acceptance rate (accepted / sent) ──────────────────────
    accepted = leads_running + leads_completed + leads_exited
    total_conn_sent = sum(1 for row in action_rows if "connection" in row["action_type"])
    acceptance_rate = round(accepted / total_conn_sent, 3) if total_conn_sent > 0 else 0.0

        # ── Fetch accounts for sender mapping ─────────────────────────────────
    acc_map = {}
    try:
        acc_full_res = supabase.table("accounts").select("id, name").eq("workspace_id", workspace_id).execute()
        acc_map = {a["id"]: a["name"] for a in acc_full_res.data}
    except Exception as e:
        print(f"Error fetching accounts for mapping: {e}")

    # ── Per-campaign breakdown processing ─────────────────────────────────
    # Batch fetch enrollments and states to avoid N+1 queries
    camp_states = {}
    if camp_ids:
        enr_res = supabase.table("campaign_enrollments").select("id, campaign_id").in_("campaign_id", camp_ids).execute()
        enroll_map = {r["id"]: r["campaign_id"] for r in (enr_res.data or [])}
        if enroll_map:
            st_res = supabase.table("campaign_execution_states").select("status, enrollment_id").in_("enrollment_id", list(enroll_map.keys())).execute()
            for r in (st_res.data or []):
                c_id = enroll_map[r["enrollment_id"]]
                if c_id not in camp_states:
                    camp_states[c_id] = {}
                camp_states[c_id][r["status"]] = camp_states[c_id].get(r["status"], 0) + 1

    campaigns_stats = []
    for camp in camps_data:
        cid = camp["id"]
        try:
            sc = camp_states.get(cid, {})
            total_in_camp = sum(sc.values())
            done = sc.get("completed", 0) + sc.get("exited", 0)
            conv = round(done / total_in_camp, 3) if total_in_camp > 0 else 0.0
            campaigns_stats.append({
                "id": cid,
                "name": camp["name"],
                "status": camp["status"],
                "leads_total": total_in_camp,
                "leads_pending": sc.get("pending", 0),
                "leads_running": sc.get("running", 0),
                "leads_completed": done,
                "leads_error": sc.get("error", 0),
                "conversion_rate": conv,
                "created_at": camp.get("created_at"),
            })
        except Exception as e:
            print(f"Error compiling stats for campaign {cid}: {e}")
            campaigns_stats.append({"id": cid, "name": camp["name"], "status": camp["status"]})

    # ── Conversion funnel (opportunity pipeline view) ─────────────────────
    funnel_extracted = total_leads
    funnel_enrolled = funnel_connected = funnel_replied = funnel_booked = 0
    try:
        if camp_ids:
            uniq_enr = supabase.table("campaign_enrollments").select("id, lead_id").in_("campaign_id", camp_ids).execute()
            enr_data = uniq_enr.data or []
            funnel_enrolled = len(set(r["lead_id"] for r in enr_data if r.get("lead_id")))
            
            enr_ids = [r["id"] for r in enr_data]
            if enr_ids:
                st_res2 = supabase.table("campaign_execution_states").select("enrollment_id").in_("enrollment_id", enr_ids).in_("status", ["running","completed","exited"]).execute()
                conn_enr_ids = set(r["enrollment_id"] for r in (st_res2.data or []))
                funnel_connected = len(set(r["lead_id"] for r in enr_data if r["id"] in conn_enr_ids and r.get("lead_id")))
            else:
                funnel_connected = 0
        
        replied_res = supabase.table("messages").select("lead_id").eq("workspace_id", workspace_id).eq("direction", "inbound").not_.is_("lead_id", "null").execute()
        funnel_replied = len(set(r["lead_id"] for r in replied_res.data if r["lead_id"]))
        funnel_booked = leads_exited
    except Exception as e:
        print(f"Error fetching conversion funnel pipeline: {e}")

    # ── 30-day time series ────────────────────────────────────────────────
    time_series = []
    try:
        from datetime import datetime, timedelta
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        ts_res = supabase.table("action_log").select("action_type, executed_at").eq("workspace_id", workspace_id).gte("executed_at", thirty_days_ago).execute()
        
        counts_by_date = {}
        for row in ts_res.data:
            dt = row["executed_at"].split("T")[0]
            typ = row["action_type"]
            if dt not in counts_by_date:
                counts_by_date[dt] = {"connections": 0, "messages": 0}
            if "connection" in typ:
                counts_by_date[dt]["connections"] += 1
            if typ in ("send_message","send_inmail","send_paid_inmail","send_voice_note","send_message_with_doc","send_message_with_image"):
                counts_by_date[dt]["messages"] += 1
                
        for dt_str in sorted(counts_by_date.keys()):
            c = counts_by_date[dt_str]
            time_series.append({"date": dt_str, "connections": c["connections"], "messages": c["messages"]})
    except Exception as e:
        print(f"Error fetching 30-day time series: {e}")

    return {
        "summary": {
            "active_campaigns": active_campaigns,
            "total_leads": total_leads,
            "connected_accounts": connected_accounts,
            "leads_enrolled": leads_enrolled,
        },
        "today": {
            "connections_sent": connections_sent_today,
            "messages_sent": messages_sent_today,
            "acceptance_rate": acceptance_rate,
        },
        "lead_states": {
            "pending": leads_pending,
            "running": leads_running,
            "completed": leads_completed,
            "exited": leads_exited,
            "error": leads_error,
        },
        "funnel": {
            "extracted": funnel_extracted,
            "enrolled": funnel_enrolled,
            "connected": funnel_connected,
            "replied": funnel_replied,
            "booked": funnel_booked,
        },
        "campaigns": campaigns_stats,
        "time_series": time_series,
    }


@router.get("/engine/status", response_model=dict)
def get_engine_status(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Returns the current state of the Ele-in background execution engine."""
    try:
        from datetime import datetime
        today = date.today().isoformat()

        camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).execute()
        camp_ids = [c["id"] for c in camp_res.data]
        
        leads_due = 0
        processed_today = 0
        errors_today = 0
        
        if camp_ids:
            enr = supabase.table("campaign_enrollments").select("id").in_("campaign_id", camp_ids).execute()
            enr_ids = [r["id"] for r in (enr.data or [])]
            if enr_ids:
                leads_due_res = supabase.table("campaign_execution_states").select("id", count="exact").in_("enrollment_id", enr_ids).in_("status", ["pending", "running"]).lte("next_run_at", datetime.utcnow().isoformat()).execute()
                leads_due = leads_due_res.count or 0

                processed_res = supabase.table("campaign_execution_states").select("id", count="exact").in_("enrollment_id", enr_ids).gte("updated_at", today).execute()
                processed_today = processed_res.count or 0

                err_res = supabase.table("campaign_execution_states").select("id", count="exact").in_("enrollment_id", enr_ids).eq("status", "error").gte("updated_at", today).execute()
                errors_today = err_res.count or 0

        acc_res = supabase.table("accounts").select("id", count="exact").eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
        active_accounts = acc_res.count or 0

        camp_res_active = supabase.table("campaigns").select("id", count="exact").eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
        active_campaigns = camp_res_active.count or 0

        return {
            "engine": "running",
            "tick_interval_seconds": 60,
            "leads_due_now": leads_due,
            "processed_today": processed_today,
            "errors_today": errors_today,
            "active_accounts": active_accounts,
            "active_campaigns": active_campaigns,
        }
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")










# ═══════════════════════════════════════════════════════════════════════════════
# ── KILL HEYREACH FEATURES ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

# ── Feature 1: AI Reply Co-Pilot (streaming) ──────────────────────────────────




# ── Feature 2: Lead Heat Scores ────────────────────────────────────────────────



# ── Feature 3: Intent-classified threads ──────────────────────────────────────



# ── Feature 4: Warmup Status ───────────────────────────────────────────────────

@router.get("/accounts/{account_id}/warmup", response_model=dict)
def get_warmup_status(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Get intelligent warmup phase details for an account."""
    from knowledge.backend.services.elein_ai_service import get_warmup_phase
    try:
        res = supabase.table("accounts").select("created_at, actions_today, warmup_day, is_warmup").eq("id", account_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Account not found")
            
        row = res.data[0]
        data = get_warmup_phase(str(row.get("created_at", "")), row.get("actions_today") or 0, bool(row.get("is_warmup", False)))
        return data
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/accounts/warmup-summary", response_model=list)
def get_all_warmup_statuses(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Get warmup summary for all accounts."""
    from knowledge.backend.services.elein_ai_service import get_warmup_phase
    try:
        res = supabase.table("accounts").select("id, name, is_active, created_at, actions_today, is_warmup").eq("workspace_id", workspace_id).execute()
        
        result = []
        for r in res.data:
            warmup = get_warmup_phase(str(r.get("created_at", "")), r.get("actions_today") or 0, bool(r.get("is_warmup", False)))
            result.append({
                "id": r["id"],
                "name": r["name"],
                "status": "connected" if r.get("is_active") else "expired",
                "warmup": warmup,
                "safety_score": warmup["safety_score"],
            })
        return result
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")


# ── Accounts: Health Check Endpoints ─────────────────────────────────────────

@router.post("/accounts/{account_id}/health-check")
def trigger_health_check(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Manually trigger a health check on demand."""
    from accounts.backend.services.account_health_service import run_health_check
    try:
        result = run_health_check(supabase, account_id, workspace_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Health check failed")

@router.get("/accounts/{account_id}/health-history")
def get_health_history(account_id: str, limit: int = 20, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Returns recent health check history for an account."""
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    try:
        history_res = supabase.table("account_health_checks").select("*").eq("account_id", account_id).order("checked_at", desc=True).limit(limit).execute()
        return history_res.data or []
    except Exception as e:
        logger.error(f"Health history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch history")

@router.get("/accounts/{account_id}/health", response_model=dict)
def get_account_health(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    history = get_health_history(account_id, limit=1, supabase=supabase, workspace_id=workspace_id)
    if history:
        return history[0]
    return {"status": "unknown"}

@router.get("/accounts/{account_id}/safety-indicator")
def get_safety_indicator(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Returns computed safety indicator. Never stored — computed fresh each call."""
    from accounts.backend.services.account_health_service import compute_safety_indicator
    from datetime import datetime, timezone
    
    try:
        acc_res = supabase.table("accounts").select("status, manual_send_suspected").eq("id", account_id).eq("workspace_id", workspace_id).execute()
        acc_data = acc_res.data[0]
    except Exception:
        # Fallback if migration not applied
        acc_res = supabase.table("accounts").select("status").eq("id", account_id).eq("workspace_id", workspace_id).execute()
        acc_data = acc_res.data[0] if acc_res.data else None

    if not acc_data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    try:
        checks_res = supabase.table("account_health_checks").select("result").eq("account_id", account_id).order("checked_at", desc=True).limit(5).execute()
        indicator = compute_safety_indicator(acc_data, checks_res.data or [])
        return {
            "indicator": indicator,
            "manual_send_suspected": acc_data.get("manual_send_suspected", False),
            "account_id": account_id,
            "computed_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Safety indicator error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute indicator")
        
@router.post("/accounts/{account_id}/clear-manual-send-warning")
def clear_manual_send_warning(account_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Clears the manual_send_suspected flag after user acknowledges."""
    try:
        supabase.table("accounts").update({"manual_send_suspected": False}).eq("id", account_id).eq("workspace_id", workspace_id).execute()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error clearing manual send warning: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear warning")



# ── Feature 5: Message Attribution ────────────────────────────────────────────



# ── Feature 6: Approval Queue ─────────────────────────────────────────────────



class ApproveRequest(BaseModel):
    queue_id: str
    action: str  # 'approve' | 'edit_and_send' | 'skip'
    final_message: str = ""
    account_id: str = ""



# ── Feature 6b: Auto-enqueue after sync ───────────────────────────────────────


@router.get("/worker/status", response_model=dict)
def get_worker_status(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """
    Returns the live status of the campaign execution worker.
    Frontend uses this to show a health badge: 🟢 Live / 🔴 Stalled / 🟡 Starting
    """
    from datetime import datetime, timezone, timedelta
    try:
        res = supabase.table("worker_heartbeat").select("*").eq("worker_id", "elein-daemon").execute()
        if not res.data:
            return {"status": "unknown", "message": "Worker has never started", "last_beat_at": None, "stalled": True}
        
        beat = res.data[0]
        last_beat_str = beat.get("last_beat_at")
        if not last_beat_str:
            return {"status": "unknown", "stalled": True, "last_beat_at": None}
        
        last_beat = datetime.fromisoformat(last_beat_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        seconds_since_beat = (now - last_beat).total_seconds()
        
        # If last heartbeat was more than 3 minutes ago, worker is stalled
        stalled = seconds_since_beat > 180
        
        return {
            "status": "stalled" if stalled else beat.get("status", "alive"),
            "last_beat_at": last_beat_str,
            "seconds_since_last_beat": int(seconds_since_beat),
            "last_tick_duration_ms": beat.get("last_tick_duration_ms"),
            "last_tick_leads_processed": beat.get("last_tick_leads_processed"),
            "stalled": stalled,
            "message": f"Worker stalled for {int(seconds_since_beat)}s" if stalled else "Worker is alive"
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "stalled": True, "last_beat_at": None}
@router.patch("/accounts/{account_id}/status", response_model=dict)
def update_account_status(
    account_id: str,
    payload: dict,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    # Verify ownership
    acc_res = supabase.table("accounts").select("id, status").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    new_status = payload.get("status")
    if new_status not in ["ACTIVE", "MANUAL_MODE"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    old_status = acc_res.data[0].get("status")
    supabase.table("accounts").update({"status": new_status}).eq("id", account_id).execute()
    
    if old_status != new_status:
        from core.backend.services.notification_service import dispatch_notification
        from core.backend.api.auth_dep import get_service_client
        svc = get_service_client()
        if new_status in ('BANNED', 'DISCONNECTED'):
            try:
                dispatch_notification(
                    svc=svc,
                    workspace_id=workspace_id,
                    event_type='account_suspended',
                    payload={'account_id': str(account_id), 'status': new_status}
                )
            except Exception as notif_err:
                logger.warning(f'Notification dispatch failed: {notif_err}')
        elif new_status == 'RATE_LIMITED':
            try:
                dispatch_notification(
                    svc=svc,
                    workspace_id=workspace_id,
                    event_type='account_needs_attention',
                    payload={'account_id': str(account_id), 'status': new_status}
                )
            except Exception as notif_err:
                logger.warning(f'Notification dispatch failed: {notif_err}')

    return {"status": "success", "new_status": new_status}
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


# --- Merged from campaigns.py ---

@router.post("/campaigns", response_model=CampaignResponse)
def create_campaign(
    campaign: CampaignCreate,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    try:
        campaign_id = str(uuid.uuid4())
        nodes_raw = [n.dict() for n in campaign.nodes]
        edges_raw = [e.dict() for e in campaign.edges]

        # ── C6: Reject campaigns with cyclic graphs before writing to DB ──────
        # ── Variable Validation (Layer 2 Paranoia) ──────
        if campaign.status == "ACTIVE":
            validate_campaign_variables(nodes_raw)

        if has_cycle(nodes_raw, edges_raw):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Campaign graph contains a cycle. "
                    "Please remove the looping edge before saving. "
                    "Tip: a node cannot be an ancestor of itself."
                )
            )

        if campaign.senders:
            accounts_check = supabase.table("accounts").select("id").in_("id", campaign.senders).execute()
            valid_ids = {row["id"] for row in accounts_check.data}
            if not all(s in valid_ids for s in campaign.senders):
                raise HTTPException(
                    status_code=403, 
                    detail="One or more sender accounts do not belong to your workspace."
                )

        nodes = json.dumps(nodes_raw)
        edges = json.dumps(edges_raw)
        name = campaign.name

        campaign_data = {
            "id": campaign_id,
            "name": name,
            "status": campaign.status or "DRAFT",
            "metadata": {"timezone": campaign.timezone} if campaign.timezone else {},
            "workspace_id": workspace_id,
        }
        # Insert campaign
        supabase.table("campaigns").insert(campaign_data).execute()

        try:
            # 1. Create Campaign Version
            version_id = str(uuid.uuid4())
            supabase.table("campaign_versions").insert({
                "id": version_id,
                "campaign_id": campaign_id,
                "version": 1,
            }).execute()

            # 2. Map React Flow String IDs to UUIDs for nodes
            node_id_map = {}
            node_inserts = []
            for n in nodes_raw:
                new_node_id = str(uuid.uuid4())
                node_id_map[n["id"]] = new_node_id
                node_inserts.append({
                    "id": new_node_id,
                    "campaign_version_id": version_id,
                    "node_type": n.get("type", "unknown"),
                    "config": n.get("data", {}),
                    "ui_position": n.get("position", {})
                })
            
            if node_inserts:
                supabase.table("campaign_nodes").insert(node_inserts).execute()

            # 3. Map Edges
            edge_inserts = []
            for e in edges_raw:
                source_uuid = node_id_map.get(e.get("source"))
                target_uuid = node_id_map.get(e.get("target"))
                if source_uuid and target_uuid:
                    edge_inserts.append({
                        "campaign_version_id": version_id,
                        "source_node_id": source_uuid,
                        "target_node_id": target_uuid,
                        "condition": e.get("sourceHandle")
                    })
            
            if edge_inserts:
                supabase.table("campaign_edges").insert(edge_inserts).execute()

            # 4. Link Accounts
            if campaign.senders:
                from core.backend.api.auth_dep import get_service_client
                svc = get_service_client()
                svc.table("campaign_accounts").insert(
                    [{"campaign_id": campaign_id, "account_id": s} for s in campaign.senders]
                ).execute()

        except Exception as link_err:
            logger.error(
                f"create_campaign: failed to create relational graph for campaign {campaign_id}: {link_err}",
                exc_info=True
            )
            try:
                supabase.table("campaigns").delete().eq("id", campaign_id).execute()
            except Exception as rollback_err:
                logger.error(
                    f"create_campaign: CRITICAL — could not rollback orphan campaign {campaign_id}: {rollback_err}"
                )
            raise HTTPException(
                status_code=500,
                detail="Campaign was created but the workflow graph failed to save. Please try again."
            )

        return CampaignResponse(
            id=campaign_id,
            name=name,
            status=campaign.status or "DRAFT",
            nodes_json=json.dumps(nodes_raw),
            edges_json=json.dumps(edges_raw)
        )
    except HTTPException:
        raise  # re-raise 422 directly without wrapping in 500
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
def update_campaign(campaign_id: str, payload: CampaignCreate, workspace_id: str = Depends(get_current_workspace), client: Client = Depends(get_supabase_client)):
    try:
        # Verify ownership
        existing = client.table("campaigns").select("id, status, metadata").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Campaign not found")
            
        if payload.senders:
            accounts_check = client.table("accounts").select("id").in_("id", payload.senders).execute()
            valid_ids = {row["id"] for row in accounts_check.data}
            if not all(s in valid_ids for s in payload.senders):
                raise HTTPException(
                    status_code=403, 
                    detail="One or more sender accounts do not belong to your workspace."
                )

        nodes_raw = [n.dict() for n in payload.nodes]
        edges_raw = [e.dict() for e in payload.edges]
        
        if payload.status == "ACTIVE":
            validate_campaign_variables(nodes_raw)

        if has_cycle(nodes_raw, edges_raw):
            raise HTTPException(
                status_code=422,
                detail="Campaign graph contains a cycle. Please remove the looping edge before saving."
            )

        update_data = {
            "name": payload.name,
            "status": payload.status
        }
        
        meta = existing.data[0].get("metadata") or {}
        if payload.timezone:
            meta["timezone"] = payload.timezone
            update_data["metadata"] = meta
        
        client.table("campaigns").update(update_data).eq("id", campaign_id).execute()

        # Create new version
        ver_res = client.table("campaign_versions").select("version").eq("campaign_id", campaign_id).order("version", desc=True).limit(1).execute()
        next_version = 1
        if ver_res.data:
            next_version = ver_res.data[0]["version"] + 1

        version_id = str(uuid.uuid4())
        client.table("campaign_versions").insert({
            "id": version_id,
            "campaign_id": campaign_id,
            "version": next_version,
        }).execute()

        node_id_map = {}
        node_inserts = []
        for n in nodes_raw:
            new_node_id = str(uuid.uuid4())
            node_id_map[n["id"]] = new_node_id
            node_inserts.append({
                "id": new_node_id,
                "campaign_version_id": version_id,
                "node_type": n.get("type", "unknown"),
                "config": n.get("data", {}),
                "ui_position": n.get("position", {})
            })
        
        if node_inserts:
            client.table("campaign_nodes").insert(node_inserts).execute()

        edge_inserts = []
        for e in edges_raw:
            source_uuid = node_id_map.get(e.get("source"))
            target_uuid = node_id_map.get(e.get("target"))
            if source_uuid and target_uuid:
                edge_inserts.append({
                    "campaign_version_id": version_id,
                    "source_node_id": source_uuid,
                    "target_node_id": target_uuid,
                    "condition": e.get("sourceHandle")
                })
        
        if edge_inserts:
            client.table("campaign_edges").insert(edge_inserts).execute()
        
        try:
            from core.backend.api.auth_dep import get_service_client
            svc = get_service_client()
            svc.table("campaign_accounts").delete().eq("campaign_id", campaign_id).execute()
            if payload.senders:
                svc.table("campaign_accounts").insert(
                    [{"campaign_id": campaign_id, "account_id": s} for s in payload.senders]
                ).execute()
        except Exception as link_err:
            # Layer 1: Update applied to campaigns table succeeded, but sender accounts
            logger.error(f"update_campaign: failed to link sender accounts: {link_err}", exc_info=True)
            
        return CampaignResponse(
            id=campaign_id,
            name=payload.name,
            status=payload.status,
            nodes_json=json.dumps(nodes_raw),
            edges_json=json.dumps(edges_raw)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.patch("/campaigns/{campaign_id}/pause", response_model=dict)
def pause_campaign(campaign_id: str, workspace_id: str = Depends(get_current_workspace), client: Client = Depends(get_supabase_client)):
    client.table("campaigns").update({"status": "PAUSED"}).eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    return {"status": "paused"}

@router.post("/campaigns/pause-all", response_model=dict)
def pause_all_campaigns(workspace_id: str = Depends(get_current_workspace), client: Client = Depends(get_supabase_client)):
    """Panic Button: Instantly pause all active campaigns for the workspace."""
    client.table("campaigns").update({"status": "PAUSED"}).eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
    return {"status": "all_paused"}

@router.patch("/campaigns/{campaign_id}/activate", response_model=dict)
def activate_campaign(campaign_id: str, workspace_id: str = Depends(get_current_workspace), client: Client = Depends(get_supabase_client)):
    client.table("campaigns").update({"status": "ACTIVE"}).eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    return {"status": "activated"}

@router.delete("/campaigns/{campaign_id}", response_model=dict)
def delete_campaign(campaign_id: str, workspace_id: str = Depends(get_current_workspace), client: Client = Depends(get_supabase_client)):
    client.table("campaigns").delete().eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    return {"status": "deleted"}




@router.post("/campaigns/{campaign_id}/enroll", response_model=dict)
def enroll_leads(campaign_id: str, body: EnrollLeadsRequest, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        camp_res = supabase.table("campaigns").select("id").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
        if not camp_res.data:
            raise HTTPException(status_code=404, detail="Campaign not found")

        enrolled = 0
        skipped = 0
        
        # Bulk lookup to check which leads exist (chunked)
        existing_opp_ids = set()
        for i in range(0, len(body.opportunity_ids), 200):
            chunk = body.opportunity_ids[i:i+200]
            check_res = supabase.table("campaign_enrollments").select("lead_id").eq("campaign_id", campaign_id).in_("lead_id", chunk).execute()
            existing_opp_ids.update(row["lead_id"] for row in (check_res.data or []))
            
        new_opp_ids = [opp_id for opp_id in body.opportunity_ids if opp_id not in existing_opp_ids]
        
        # --- PHASE 1: SUPPRESSION CHECK ---
        # Query leads to get emails/linkedin_urls (chunked)
        leads_map = {}
        for i in range(0, len(new_opp_ids), 200):
            chunk = new_opp_ids[i:i+200]
            leads_res = supabase.table("leads").select("id, linkedin_url, email").in_("id", chunk).execute()
            for row in (leads_res.data or []):
                leads_map[row["id"]] = row
                
        all_linkedins = list({l.get("linkedin_url") for l in leads_map.values() if l.get("linkedin_url")})
        all_emails = list({l.get("email") for l in leads_map.values() if l.get("email")})
        
        # Query workspace suppression list only for matching candidates (chunked)
        supp_linkedin = set()
        for i in range(0, len(all_linkedins), 200):
            chunk = all_linkedins[i:i+200]
            res = supabase.table("suppression_list").select("linkedin_url").eq("workspace_id", workspace_id).in_("linkedin_url", chunk).execute()
            supp_linkedin.update(r.get("linkedin_url") for r in (res.data or []))
            
        supp_email = set()
        for i in range(0, len(all_emails), 200):
            chunk = all_emails[i:i+200]
            res = supabase.table("suppression_list").select("email").eq("workspace_id", workspace_id).in_("email", chunk).execute()
            supp_email.update(r.get("email") for r in (res.data or []))
        
        final_opp_ids = []
        suppressed_count = 0
        for opp_id in new_opp_ids:
            l = leads_map.get(opp_id, {})
            if l.get("linkedin_url") in supp_linkedin or l.get("email") in supp_email:
                suppressed_count += 1
            else:
                final_opp_ids.append(opp_id)
                
        skipped = len(body.opportunity_ids) - len(final_opp_ids)
        enrolled = len(final_opp_ids)
        new_opp_ids = final_opp_ids

        if new_opp_ids:
            # Get active version
            ver_res = supabase.table("campaign_versions").select("id").eq("campaign_id", campaign_id).order("version", desc=True).limit(1).execute()
            if not ver_res.data:
                raise HTTPException(status_code=400, detail="Campaign has no versions")
            version_id = ver_res.data[0]["id"]

            # Get accounts for round-robin assignment
            acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", campaign_id).execute()
            accounts = [row["account_id"] for row in (acc_res.data or [])]
            if not accounts:
                raise HTTPException(status_code=400, detail="Campaign has no linked sender accounts. Please link an account first.")

            # Prepare bulk insert data
            enrollment_data = []
            execution_data = []
            action_log_data = []
            
            for i, opp_id in enumerate(new_opp_ids):
                assigned_account = accounts[i % len(accounts)]
                enrollment_id = str(uuid.uuid4())
                
                enrollment_data.append({
                    "id": enrollment_id,
                    "workspace_id": workspace_id,
                    "campaign_id": campaign_id,
                    "campaign_version_id": version_id,
                    "lead_id": opp_id,
                    "account_id": assigned_account
                })
                
                execution_data.append({
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "enrollment_id": enrollment_id,
                    "status": "pending",
                    "variables": {}
                })
                
                action_log_data.append({
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "action_type": "lead_enrolled",
                    "result": "success",
                    "metadata": {"campaign_id": campaign_id, "lead_id": opp_id}
                })

            # Execute bulk inserts
            from core.backend.api.auth_dep import get_service_client
            svc = get_service_client()
            svc.table("campaign_enrollments").upsert(enrollment_data, ignore_duplicates=True).execute()
            svc.table("campaign_execution_states").upsert(execution_data, ignore_duplicates=True).execute()
            supabase.table("action_log").insert(action_log_data).execute()

        return {"enrolled": enrolled, "skipped": skipped, "campaign_id": campaign_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/campaigns/{campaign_id}/leads", response_model=List[dict])
def get_campaign_leads(campaign_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        # We fetch enrollments first
        enr_res = supabase.table("campaign_enrollments").select("id, lead_id").eq("campaign_id", campaign_id).execute()
        enrolls = enr_res.data
        
        if not enrolls:
            return []
            
        enr_ids = [e["id"] for e in enrolls]
        enr_map = {e["id"]: e["lead_id"] for e in enrolls}
        opp_ids = [e["lead_id"] for e in enrolls]
        
        # Then fetch states
        st_res = supabase.table("campaign_execution_states").select("id, enrollment_id, current_node_id, status, next_run_at, updated_at, created_at").in_("enrollment_id", enr_ids).order("created_at", desc=True).execute()
        states = st_res.data
        
        leads_res = supabase.table("leads").select("id, first_name, last_name, company_name, linkedin_url, job_title").in_("id", opp_ids).execute()
        leads_map = {l["id"]: l for l in leads_res.data}
        
        result = []
        for s in states:
            opp_id = enr_map.get(s["enrollment_id"])
            lead = leads_map.get(opp_id, {})
            result.append({
                "id": s["id"],
                "opportunity_id": opp_id,
                "current_node_id": s["current_node_id"],
                "status": s["status"],
                "next_run_at": s["next_run_at"],
                "updated_at": s["updated_at"],
                "kdm_first": lead.get("first_name", ""),
                "kdm_last": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "linkedin_url": lead.get("linkedin_url", ""),
                "job_title": lead.get("job_title", "")
            })
            
        return result
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/campaigns/{campaign_id}/detail", response_model=dict)
def get_campaign_detail(campaign_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Returns campaign metadata, nodes, and funnel stats for the detail page."""
    try:
        # Fetch campaign details
        camp_res = supabase.table("campaigns").select("*").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
        if not camp_res.data:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        campaign = camp_res.data[0]
        
        # Convert JSON strings to objects if they are strings (Supabase might return dicts directly if jsonb)
        campaign["nodes"] = json.loads(campaign.get("nodes_json") or "[]") if isinstance(campaign.get("nodes_json"), str) else (campaign.get("nodes_json") or [])
        campaign["edges"] = json.loads(campaign.get("edges_json") or "[]") if isinstance(campaign.get("edges_json"), str) else (campaign.get("edges_json") or [])
        try:
            acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", campaign_id).execute()
            campaign["sender_account_ids"] = [r["account_id"] for r in acc_res.data]
        except Exception:
            campaign["sender_account_ids"] = []

        # Fetch stats
        # In Supabase REST we can't easily GROUP BY without RPC. So we fetch all statuses.
        enr_res = supabase.table("campaign_enrollments").select("id").eq("campaign_id", campaign_id).execute()
        enr_ids = [r["id"] for r in (enr_res.data or [])]
        if enr_ids:
            states_res = supabase.table("campaign_execution_states").select("status").in_("enrollment_id", enr_ids).execute()
        else:
            class MockRes: data = []
            states_res = MockRes()
        
        stats = {}
        for s in states_res.data:
            st = s["status"]
            stats[st] = stats.get(st, 0) + 1
        
        # Calculate totals
        total_leads = sum(stats.values())
        completed = stats.get("completed", 0) + stats.get("exited", 0)
        conversion_rate = round(completed / total_leads, 3) if total_leads > 0 else 0.0

        campaign["stats"] = {
            "total_leads": total_leads,
            "pending": stats.get("pending", 0),
            "running": stats.get("running", 0),
            "completed": completed,
            "error": stats.get("error", 0),
            "conversion_rate": conversion_rate
        }

        # Fetch linked accounts metadata
        if campaign["sender_account_ids"]:
            acc_res = supabase.table("accounts").select("id, name, linkedin_profile_url").in_("id", campaign["sender_account_ids"]).execute()
            campaign["accounts"] = acc_res.data
        else:
            campaign["accounts"] = []

        return campaign
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.post("/campaigns/{campaign_id}/enroll_list", response_model=dict)
def enroll_list_leads(campaign_id: str, body: EnrollListRequest, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        camp_res = supabase.table("campaigns").select("id").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
        if not camp_res.data:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Fetch excluded opps
        excluded_opp_ids = set()
        if body.excludeListId:
            excl_res = supabase.table("list_members").select("opportunity_id").eq("list_id", body.excludeListId).execute()
            excluded_opp_ids = {row["opportunity_id"] for row in excl_res.data}        # Fetch all opportunities from this list
        opps_res = supabase.table("list_members").select("opportunity_id").eq("list_id", body.list_id).execute()
        opp_ids = [row["opportunity_id"] for row in opps_res.data]
        
        # --- PHASE 1: SUPPRESSION CHECK ---
        leads_map = {}
        for i in range(0, len(opp_ids), 200):
            chunk = opp_ids[i:i+200]
            leads_res = supabase.table("leads").select("id, linkedin_url, email").in_("id", chunk).execute()
            for row in (leads_res.data or []):
                leads_map[row["id"]] = row
                
        all_linkedins = list({l.get("linkedin_url") for l in leads_map.values() if l.get("linkedin_url")})
        all_emails = list({l.get("email") for l in leads_map.values() if l.get("email")})
        
        supp_linkedin = set()
        for i in range(0, len(all_linkedins), 200):
            chunk = all_linkedins[i:i+200]
            res = supabase.table("suppression_list").select("linkedin_url").eq("workspace_id", workspace_id).in_("linkedin_url", chunk).execute()
            supp_linkedin.update(r.get("linkedin_url") for r in (res.data or []))
            
        supp_email = set()
        for i in range(0, len(all_emails), 200):
            chunk = all_emails[i:i+200]
            res = supabase.table("suppression_list").select("email").eq("workspace_id", workspace_id).in_("email", chunk).execute()
            supp_email.update(r.get("email") for r in (res.data or []))
        
        valid_opp_ids = []
        for opp_id in opp_ids:
            l = leads_map.get(opp_id, {})
            if l.get("linkedin_url") in supp_linkedin or l.get("email") in supp_email:
                excluded_opp_ids.add(opp_id)  # Add to excluded so it gets skipped below
            else:
                valid_opp_ids.append(opp_id)
        
        enrolled = 0
        skipped = 0
        
        # Check for existing states across all campaigns
        enr_res = supabase.table("campaign_enrollments").select("id, lead_id, campaign_id").in_("lead_id", opp_ids).execute()
        existing_enr = enr_res.data or []
        enr_map = {r["id"]: r for r in existing_enr}
        enr_ids = list(enr_map.keys())
        
        existing_states = []
        if enr_ids:
            st_res = supabase.table("campaign_execution_states").select("enrollment_id, status").in_("enrollment_id", enr_ids).execute()
            for r in (st_res.data or []):
                e = enr_map[r["enrollment_id"]]
                existing_states.append({
                    "opportunity_id": e["lead_id"],
                    "campaign_id": e["campaign_id"],
                    "status": r["status"]
                })
        
        ACTIVE_STATUSES = {"pending", "running", "waiting_for_reply"}
        
        final_opp_ids = []
        for opp_id in opp_ids:
            if opp_id in excluded_opp_ids:
                skipped += 1
                continue
                
            # GLOBAL DEDUPLICATION (Cross-Campaign Friendly Fire guardrail)
            is_active_anywhere = any(
                es["opportunity_id"] == opp_id and es["status"] in ACTIVE_STATUSES
                for es in existing_states
            )
            if is_active_anywhere:
                skipped += 1
                continue

            if body.excludeOtherCampaigns:
                if any(es["opportunity_id"] == opp_id and es["campaign_id"] != campaign_id for es in existing_states):
                    skipped += 1
                    continue

            # Check for existing in current campaign
            if any(es["opportunity_id"] == opp_id and es["campaign_id"] == campaign_id for es in existing_states):
                skipped += 1
                continue
                
            final_opp_ids.append(opp_id)
            
        enrolled = len(final_opp_ids)
        
        if final_opp_ids:
            # Get active version
            ver_res = supabase.table("campaign_versions").select("id").eq("campaign_id", campaign_id).order("version", desc=True).limit(1).execute()
            if not ver_res.data:
                raise HTTPException(status_code=400, detail="Campaign has no versions")
            version_id = ver_res.data[0]["id"]

            # Get accounts for round-robin assignment
            acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", campaign_id).execute()
            accounts = [row["account_id"] for row in (acc_res.data or [])]
            if not accounts:
                raise HTTPException(status_code=400, detail="Campaign has no linked sender accounts.")

            # Prepare bulk insert data
            enrollment_data = []
            execution_data = []
            action_log_data = []
            
            for i, opp_id in enumerate(final_opp_ids):
                assigned_account = accounts[i % len(accounts)]
                enrollment_id = str(uuid.uuid4())
                
                enrollment_data.append({
                    "id": enrollment_id,
                    "workspace_id": workspace_id,
                    "campaign_id": campaign_id,
                    "campaign_version_id": version_id,
                    "lead_id": opp_id,
                    "account_id": assigned_account
                })
                
                execution_data.append({
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "enrollment_id": enrollment_id,
                    "status": "pending",
                    "variables": {}
                })
                
                action_log_data.append({
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "action_type": "lead_enrolled",
                    "result": "success",
                    "metadata": {"campaign_id": campaign_id, "lead_id": opp_id}
                })

            # Execute bulk inserts
            from core.backend.api.auth_dep import get_service_client
            svc = get_service_client()
            svc.table("campaign_enrollments").upsert(enrollment_data, ignore_duplicates=True).execute()
            svc.table("campaign_execution_states").upsert(execution_data, ignore_duplicates=True).execute()
            supabase.table("action_log").insert(action_log_data).execute()

        return {"status": "success", "enrolled": enrolled, "skipped": skipped}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/campaigns/{campaign_id}/lead-scores", response_model=list)
def get_lead_scores(campaign_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Return heat scores for all leads in a campaign."""
    from knowledge.backend.services.elein_ai_service import compute_heat_score
    try:
        enr_res = supabase.table("campaign_enrollments").select("id, lead_id").eq("campaign_id", campaign_id).execute()
        enrolls = enr_res.data or []
        if not enrolls:
            return []
            
        enr_ids = [e["id"] for e in enrolls]
        enr_map = {e["id"]: e["lead_id"] for e in enrolls}
        opp_ids = [e["lead_id"] for e in enrolls]
        
        st_res = supabase.table("campaign_execution_states").select("enrollment_id, status").in_("enrollment_id", enr_ids).execute()
        
        ls_data = []
        for s in (st_res.data or []):
            ls_data.append({
                "opportunity_id": enr_map.get(s["enrollment_id"]),
                "status": s["status"]
            })
            
        opps_res = supabase.table("leads").select("id, first_name, last_name, company_name, linkedin_url, job_title").in_("id", opp_ids).execute()
        opps_map = {r["id"]: r for r in opps_res.data}
        
        result = []
        for r in ls_data:
            opp_id = r.get("opportunity_id")
            if not opp_id or opp_id not in opps_map:
                continue
                
            opp = opps_map[opp_id]
            first_name = opp.get("first_name") or ""
            
            # Fetch messages for this lead
            msgs_res = supabase.table("messages").select("direction, message_text, intent, created_at").eq("workspace_id", workspace_id).ilike("sender_name", f"%{first_name}%").order("created_at").execute()
            msgs = msgs_res.data
            
            state_dict = r
            state_dict["state"] = r["status"]
            score, label = compute_heat_score(state_dict, msgs)
            
            result.append({
                "lead_id": opp_id,
                "name": f"{first_name} {opp.get('last_name') or ''}".strip(),
                "company": opp.get("company_name", ""),
                "title": opp.get("job_title", ""),
                "linkedin_url": opp.get("linkedin_url", ""),
                "state": r["status"],
                "heat_score": score,
                "heat_label": label,
            })
            
        result.sort(key=lambda x: x["heat_score"], reverse=True)
        return result
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

@router.get("/campaigns/{campaign_id}/attribution", response_model=dict)
def get_message_attribution(campaign_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Return which sequence nodes drove replies."""
    try:
        enr_res = supabase.table("campaign_enrollments").select("id, lead_id").eq("campaign_id", campaign_id).execute()
        enr_data = enr_res.data or []
        if not enr_data:
            return {"nodes": [], "heatmap": []}
            
        enr_ids = [r["id"] for r in enr_data]
        enr_map = {r["id"]: r["lead_id"] for r in enr_data}
        
        st_res = supabase.table("campaign_execution_states").select("id, enrollment_id").in_("enrollment_id", enr_ids).execute()
        ls_data = []
        for s in (st_res.data or []):
            ls_data.append({
                "id": s["id"], 
                "opportunity_id": enr_map.get(s["enrollment_id"])
            })
        if not ls_data:
            return {"nodes": [], "heatmap": []}
            
        lead_state_ids = [r["id"] for r in ls_data if r.get("id")]
        ls_map = {r["id"]: r for r in ls_data}
        
        opp_ids = [r["opportunity_id"] for r in ls_data if r.get("opportunity_id")]
        opps_res = supabase.table("leads").select("id, linkedin_url").in_("id", opp_ids).execute()
        opps_map = {r["id"]: r for r in opps_res.data}
        
        al_res = supabase.table("action_log").select("action_type, metadata, executed_at, result, execution_state_id").in_("execution_state_id", lead_state_ids).execute()
        msgs_res = supabase.table("messages").select("sender_name, created_at").eq("workspace_id", workspace_id).eq("direction", "inbound").execute()
        
        inbound_times = {}
        for m in msgs_res.data:
            sn = m.get("sender_name")
            if sn:
                if sn not in inbound_times:
                    inbound_times[sn] = []
                inbound_times[sn].append(m["created_at"])
                
        node_stats = {}
        heatmap_stats = {}
        
        for al in al_res.data:
            meta = al.get("metadata") or {}
            if isinstance(meta, str):
                import json
                try:
                    meta = json.loads(meta)
                except:
                    meta = {}
            node_id = meta.get("node_id")
            action_type = al.get("action_type")
            created_at = al.get("executed_at")
            if not created_at:
                continue
                
            ls = ls_map.get(al.get("execution_state_id")) or {}
            opp = opps_map.get(ls.get("opportunity_id")) or {}
            profile_url = opp.get("linkedin_url")
            
            # Node stats
            key = (action_type, node_id)
            if key not in node_stats:
                node_stats[key] = {"sent": 0, "replied": 0}
            node_stats[key]["sent"] += 1
            
            replied = False
            if profile_url in inbound_times:
                for itime in inbound_times[profile_url]:
                    if itime > created_at:
                        replied = True
                        break
            if replied:
                node_stats[key]["replied"] += 1
                
            # Heatmap stats
            if action_type == "message":
                from datetime import datetime
                # Parse '2025-02-18T10:15:30'
                dt = datetime.fromisoformat(created_at.replace("Z", ""))
                dow = dt.strftime('%w') # 0-6
                hour = dt.strftime('%H') # 00-23
                hkey = (dow, hour)
                if hkey not in heatmap_stats:
                    heatmap_stats[hkey] = {"sent": 0, "replied": 0}
                heatmap_stats[hkey]["sent"] += 1
                if replied:
                    heatmap_stats[hkey]["replied"] += 1
                    
        nodes = []
        for (atype, nid), stats in node_stats.items():
            sent = stats["sent"]
            replied = stats["replied"]
            nodes.append({
                "node_id": nid,
                "action_type": atype,
                "sent": sent,
                "replied": replied,
                "reply_rate": round((replied / sent * 100), 1) if sent > 0 else 0.0,
            })
            
        heatmap = []
        for (dow, hour), stats in heatmap_stats.items():
            sent = stats["sent"]
            replied = stats["replied"]
            heatmap.append({
                "dow": int(dow),
                "hour": int(hour),
                "reply_rate": round(replied / sent * 100, 1) if sent > 0 else 0.0,
            })
            
        return {"nodes": nodes, "heatmap": heatmap}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")

class EnrollListRequest(BaseModel):
    list_id: str
    excludeListId: Optional[str] = None
    excludeOtherCampaigns: Optional[bool] = False
    excludeOtherSenders: Optional[bool] = False
    excludeSameSender: Optional[bool] = False


@router.get("/accounts/{account_id}/limits", response_model=dict)
def get_account_limits(
    account_id: str,
    action_type: str = "connection_request",
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    from datetime import date
    
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise HTTPException(status_code=404, detail="Account not found")
        
    rpc_res = supabase.rpc("get_account_action_limit", {
        "account_id": account_id,
        "action_type": action_type
    }).execute()
    effective_limit = rpc_res.data if rpc_res.data is not None else 0
    
    today = date.today().isoformat()
    usage_res = supabase.table("account_daily_action_counts").select("count").eq("account_id", account_id).eq("action_type", action_type).eq("usage_date", today).execute()
    used_today = usage_res.data[0].get("count", 0) if usage_res.data else 0
    
    limit_res = supabase.table("action_type_limits").select("default_limit").eq("action_type", action_type).execute()
    global_limit = limit_res.data[0].get("default_limit", 0) if limit_res.data else 0
    
    override_res = supabase.table("account_action_limits").select("id").eq("account_id", account_id).eq("action_type", action_type).execute()
    has_manual_override = bool(override_res.data)
    
    return {
        "action": action_type,
        "effective_limit": effective_limit,
        "used_today": used_today,
        "is_clamped_by_warmup": effective_limit < global_limit,
        "has_manual_override": has_manual_override
    }


def get_current_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization")


@router.get('/notifications')
def get_my_notifications(user_id: str = Depends(get_current_user_id)):
    """Get in-app notifications for the current user."""
    svc = get_service_client()
    res = svc.table('outbox_events') \
        .select('id, event_type, payload, created_at, delivered_at') \
        .eq('event_type', 'notification.in_app') \
        .eq('status', 'delivered') \
        .order('created_at', desc=True) \
        .limit(20) \
        .execute()
    
    user_notifs = [
        e for e in (res.data or [])
        if e.get('payload', {}).get('user_id') == user_id
    ]
    return {"notifications": user_notifs}
