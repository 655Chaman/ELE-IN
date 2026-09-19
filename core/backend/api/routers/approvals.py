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





class UploadUrlsRequest(BaseModel):
    name: str
    urls: list[str]



class UploadSalesNavRequest(BaseModel):
    name: str
    url: str
    account_id: Optional[str] = None   # Which LinkedIn account to scrape from
    max_results: Optional[int] = 100   # Default cap: 100 profiles per import




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
