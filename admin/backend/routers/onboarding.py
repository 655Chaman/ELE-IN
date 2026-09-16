import json
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Dict, Any

from core.backend.api.auth_dep import get_supabase_client, verify_token_and_get_user_id
from fastapi import Request

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

@router.post("/seed-demo-data")
def seed_demo_data(request: Request) -> Dict[str, Any]:
    supabase = get_supabase_client(request)
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing auth header")
    token = auth_header.split(" ")[1]
    user_id = verify_token_and_get_user_id(token)
    
    # Check if user has a workspace
    ws_res = supabase.table("workspace_members").select("workspace_id").eq("user_id", user_id).limit(1).execute()
    if ws_res.data:
        workspace_id = ws_res.data[0]["workspace_id"]
    else:
        # Create workspace for user
        workspace_id = str(uuid.uuid4())
        supabase.table("workspaces").insert({
            "id": workspace_id,
            "name": "My Workspace",
            "owner_id": user_id
        }).execute()
        supabase.table("workspace_members").insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "role": "owner"
        }).execute()
    
    # Check if workspace already has campaigns
    camp_res = supabase.table("campaigns").select("id", count="exact").eq("workspace_id", workspace_id).execute()
    if camp_res.count and camp_res.count > 0:
        return {"status": "already_seeded", "workspace_id": workspace_id}
        
    list_id = str(uuid.uuid4())
    lead_id = str(uuid.uuid4())
    campaign_id = str(uuid.uuid4())
    
    # 1. Create Lead List
    supabase.table("lead_lists").insert({
        "id": list_id,
        "workspace_id": workspace_id,
        "name": "Demo Leads - Tech Founders",
        "type": "csv",
        "row_count": 1
    }).execute()
    
    # 2. Create Lead
    demo_lead = {
        "id": lead_id,
        "workspace_id": workspace_id,
        "first_name": "Alex",
        "last_name": "Rivera",
        "linkedin_url": "https://linkedin.com/in/demo-lead-alexrivera",
        "company_name": "Acme Corp",
        "job_title": "VP of Sales",
        "industry": "SaaS",
        "status": "extracted"
    }
    supabase.table("leads").insert(demo_lead).execute()
    
    # Link Lead to List
    supabase.table("list_members").insert({
        "list_id": list_id,
        "opportunity_id": lead_id
    }).execute()
    
    # 3. Create Campaign
    nodes = [
        {"id": "start", "type": "trigger_campaign_start", "data": {"label": "Campaign Start"}, "position": {"x": 100, "y": 100}}, 
        {"id": "msg1", "type": "action_send_connection_request", "data": {"label": "Send Connection Request", "body": "Hi {{first_name}}, I came across your profile and loved {{ai_hook}}. Would love to connect!", "note": ""}, "position": {"x": 100, "y": 250}}
    ]
    edges = [{"id": "e1", "source": "start", "target": "msg1"}]
    
    supabase.table("campaigns").insert({
        "id": campaign_id,
        "workspace_id": workspace_id,
        "name": "🚀 Demo: Cold Outreach to VP Sales",
        "status": "DRAFT",
        "nodes_json": nodes,
        "edges_json": edges
    }).execute()
    
    return {
        "status": "seeded",
        "workspace_id": workspace_id,
        "campaign_id": campaign_id,
        "list_id": list_id,
        "lead_id": lead_id
    }
