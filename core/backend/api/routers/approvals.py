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

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET environment variable is missing")

router = APIRouter(tags=["approvals"])
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

async def process_voyager_search_background(
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
    raise HTTPException(status_code=501, detail="Not implemented")


# ── Feature 6b: Auto-enqueue after sync ───────────────────────────────────────


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
