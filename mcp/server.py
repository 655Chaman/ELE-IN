import os
import sys
import hashlib
import uuid
from typing import Optional, List, Dict, Any

# Un-shadow third-party 'mcp' package if executed from inside an 'mcp' directory
_script_dir = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0]) == _script_dir:
    sys.path.pop(0)

# Ensure project root is in sys.path regardless of execution CWD
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)

# Paranoia Layer 1 & 2: Automatically load backend/.env if environment variables are missing
try:
    from dotenv import load_dotenv
    _backend_env = os.path.join(_PROJECT_ROOT, "backend", ".env")
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)
    else:
        load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP
from supabase import create_client, Client
import asyncio


mcp = FastMCP("Ele-in Campaign Engine")

def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables")
    return create_client(url, key)

def authenticate() -> str:
    """Validates ELEIN_API_KEY from environment and returns workspace_id."""
    api_key = os.environ.get("ELEIN_API_KEY")
    if not api_key:
        raise ValueError("Authentication failed: ELEIN_API_KEY environment variable is missing")
    
    key_hash = hashlib.sha256(api_key.encode('utf-8')).hexdigest()
    supabase = get_supabase()
    
    res = supabase.table("api_keys").select("workspace_id, is_active").eq("key_hash", key_hash).execute()
    if not res.data:
        raise ValueError("Authentication failed: Invalid API key")
    
    record = res.data[0]
    if not record.get("is_active"):
        raise ValueError("Authentication failed: API key is revoked or inactive")
        
    return record["workspace_id"]

@mcp.tool()
def elein_list_campaigns(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List campaigns for the authenticated workspace. Optionally filter by status (active, paused, draft)."""
    workspace_id = authenticate()
    supabase = get_supabase()
    
    query = supabase.table("campaigns").select("*").eq("workspace_id", workspace_id)
    if status:
        query = query.eq("status", status.upper())
        
    res = query.execute()
    return res.data

@mcp.tool()
def elein_enroll_leads(campaign_id: str, leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Enroll leads into a campaign. Reuses Ele-in's bulk import and duplicate-check logic."""
    workspace_id = authenticate()
    
    # Layer 2 Paranoia: Limit to 500 leads per call
    if len(leads) > 500:
        raise ValueError("Cannot enroll more than 500 leads per call. Please batch your requests.")
        
    supabase = get_supabase()
    
    # Verify campaign belongs to workspace
    camp_res = supabase.table("campaigns").select("id").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    if not camp_res.data:
        raise ValueError("Campaign not found or does not belong to your workspace")
        
    # Phase 1: Use bulk_import_leads RPC to safely insert leads and handle duplicates
    list_id = str(uuid.uuid4())
    leads_to_insert = []
    for lead in leads:
        lead_data = {}
        if "linkedin_url" in lead: lead_data["linkedin_url"] = lead["linkedin_url"]
        if "email" in lead: lead_data["email"] = lead["email"]
        if "first_name" in lead: lead_data["first_name"] = lead["first_name"]
        if "last_name" in lead: lead_data["last_name"] = lead["last_name"]
        if "company" in lead: lead_data["company_name"] = lead["company"]
        leads_to_insert.append(lead_data)
        
    # We must insert a temporary list for the RPC to work, even if we don't use it later
    supabase.table("lead_lists").insert({
        "id": list_id,
        "name": "MCP Temp Enroll List",
        "type": "api",
        "workspace_id": workspace_id,
        "row_count": len(leads_to_insert)
    }).execute()
    
    # RPC handles duplicates across the workspace natively
    rpc_res = supabase.rpc("bulk_import_leads", {
        "p_list_id": list_id,
        "p_workspace_id": workspace_id,
        "p_leads": leads_to_insert,
        "p_timezone": "UTC"
    }).execute()
    
    # Phase 2: Now that leads are safely in the DB, query them by list membership
    members_res = supabase.table("lead_list_members").select("lead_id").eq("list_id", list_id).execute()
    opportunity_ids = [m["lead_id"] for m in (members_res.data or [])]
    
    if not opportunity_ids:
        return {"enrolled": 0, "skipped": len(leads), "collision_skipped": len(leads), "message": "All leads were skipped (likely duplicates)"}
        
    # Phase 3: Check global collision in active campaigns (Paranoia Layer)
    # VULNERABILITY FIXED: Do not permanently blacklist leads. Only block if they are currently ACTIVE in another campaign.
    # We also MUST check if they are already in THIS specific campaign (regardless of state) due to the unique constraint.
    existing_res = supabase.table("campaign_enrollments").select("lead_id, campaign_id, campaign_execution_states(status)").eq("workspace_id", workspace_id).in_("lead_id", opportunity_ids).execute()
    
    existing_opp_ids = set()
    for row in (existing_res.data or []):
        if row.get("campaign_id") == campaign_id:
            # Already in THIS campaign - always skip
            existing_opp_ids.add(row["lead_id"])
            continue
            
        states = row.get("campaign_execution_states", [])
        # In a 1:1 relationship, PostgREST might return a list or dict
        if isinstance(states, dict):
            states = [states]
        
        # If they are in ANOTHER campaign, only skip if that campaign is active
        is_active = any(s.get("status") in ("pending", "running", "waiting_for_reply", "awaiting_approval") for s in states if isinstance(s, dict))
        if is_active:
            existing_opp_ids.add(row["lead_id"])
    
    new_opp_ids = [opp_id for opp_id in opportunity_ids if opp_id not in existing_opp_ids]
    collision_skipped = len(opportunity_ids) - len(new_opp_ids)
    
    if not new_opp_ids:
         return {"enrolled": 0, "skipped": len(leads) - collision_skipped, "collision_skipped": collision_skipped}
         
    # Fetch campaign version and accounts for enrollment
    ver_res = supabase.table("campaign_versions").select("id").eq("campaign_id", campaign_id).order("version", desc=True).limit(1).execute()
    if not ver_res.data:
        raise ValueError("Campaign has no active versions to enroll into")
    version_id = ver_res.data[0]["id"]
    
    acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", campaign_id).execute()
    accounts = [row["account_id"] for row in (acc_res.data or [])]
    if not accounts:
        raise ValueError("Campaign has no linked sender accounts")
        
    enrollment_data = []
    execution_data = []
    action_log_data = []
    
    for i, opp_id in enumerate(new_opp_ids):
        assigned_account = accounts[i % len(accounts)]
        enrollment_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{campaign_id}_{opp_id}"))
        
        enrollment_data.append({
            "id": enrollment_id,
            "workspace_id": workspace_id,
            "campaign_id": campaign_id,
            "campaign_version_id": version_id,
            "lead_id": opp_id,
            "account_id": assigned_account
        })
        execution_data.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"exec_{enrollment_id}")),
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
        
    # Execute batch inserts
    supabase.table("campaign_enrollments").upsert(enrollment_data, ignore_duplicates=True, on_conflict="campaign_id,lead_id").execute()
    supabase.table("campaign_execution_states").upsert(execution_data, ignore_duplicates=True).execute()
    
    # Cleanup temp list
    supabase.table("lead_lists").delete().eq("id", list_id).execute()
    
    enrolled = len(new_opp_ids)
    skipped = len(leads) - enrolled
    
    return {
        "enrolled": enrolled,
        "skipped": skipped,
        "collision_skipped": collision_skipped
    }

@mcp.tool()
def elein_get_campaign_analytics(campaign_id: str) -> Dict[str, Any]:
    """Get aggregated stats for a campaign from campaign_events."""
    workspace_id = authenticate()
    supabase = get_supabase()
    
    # Paranoia Layer 2: Verify campaign belongs to workspace
    camp_res = supabase.table("campaigns").select("id").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    if not camp_res.data:
        raise ValueError("Campaign not found or does not belong to your workspace")
        
    events_res = supabase.table("campaign_events").select("event_type").eq("campaign_id", campaign_id).eq("workspace_id", workspace_id).execute()
    events = events_res.data or []
    
    # Layer 1: If empty, return zeros without error
    if not events:
        return {"total_enrolled": 0, "total_sent": 0, "replies": 0, "reply_rate": "0%", "conversion_rate": "0%"}
        
    enrolled = len([e for e in events if e.get("event_type") == "lead_enrolled"])
    sent = len([e for e in events if e.get("event_type") == "message_sent"])
    replies = len([e for e in events if e.get("event_type") == "reply_received"])
    conversions = len([e for e in events if e.get("event_type") == "meeting_booked"])
    
    reply_rate = f"{(replies / sent * 100):.1f}%" if sent > 0 else "0%"
    conversion_rate = f"{(conversions / enrolled * 100):.1f}%" if enrolled > 0 else "0%"
    
    return {
        "total_enrolled": enrolled,
        "total_sent": sent,
        "replies": replies,
        "reply_rate": reply_rate,
        "conversion_rate": conversion_rate
    }

@mcp.tool()
def elein_pause_campaign(campaign_id: str) -> Dict[str, Any]:
    """Pause an active campaign."""
    workspace_id = authenticate()
    supabase = get_supabase()
    
    # Layer 2 Paranoia: verify ownership
    res = supabase.table("campaigns").update({"status": "PAUSED"}).eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise ValueError("Campaign not found or does not belong to your workspace")
    return {"status": "success", "campaign_id": campaign_id, "new_state": "PAUSED"}

@mcp.tool()
def elein_resume_campaign(campaign_id: str) -> Dict[str, Any]:
    """Resume a paused campaign."""
    workspace_id = authenticate()
    supabase = get_supabase()
    
    # Layer 2 Paranoia: verify ownership
    res = supabase.table("campaigns").update({"status": "ACTIVE"}).eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise ValueError("Campaign not found or does not belong to your workspace")
    return {"status": "success", "campaign_id": campaign_id, "new_state": "ACTIVE"}

@mcp.tool()
def elein_get_lead_status(lead_id: Optional[str] = None, email: Optional[str] = None, linkedin_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get a lead's current enrollment state across ALL campaigns they are enrolled in."""
    workspace_id = authenticate()
    supabase = get_supabase()
    
    if not lead_id and not email and not linkedin_url:
        raise ValueError("Must provide at least one identifier: lead_id, email, or linkedin_url")
        
    query = supabase.table("leads").select("id").eq("workspace_id", workspace_id)
    if lead_id:
        query = query.eq("id", lead_id)
    elif email:
        query = query.eq("email", email)
    elif linkedin_url:
        query = query.eq("linkedin_url", linkedin_url)
        
    leads_res = query.limit(1).execute()
    if not leads_res.data:
        return [] # Lead not found in this workspace
        
    target_lead_id = leads_res.data[0]["id"]
    
    enrollments_res = supabase.table("campaign_enrollments").select("id, campaign_id, status").eq("lead_id", target_lead_id).eq("workspace_id", workspace_id).execute()
    enrollments = enrollments_res.data or []
    
    if not enrollments:
        return []
        
    enrollment_ids = [e["id"] for e in enrollments]
    states_res = supabase.table("campaign_execution_states").select("enrollment_id, status, current_node_id, next_run_at").in_("enrollment_id", enrollment_ids).execute()
    states_map = {s["enrollment_id"]: s for s in (states_res.data or [])}
    
    results = []
    for enr in enrollments:
        state = states_map.get(enr["id"], {})
        results.append({
            "campaign_id": enr["campaign_id"],
            "enrollment_id": enr["id"],
            "enrollment_status": enr.get("status", "unknown"),
            "execution_status": state.get("status", "unknown"),
            "current_node_id": state.get("current_node_id"),
            "next_run_at": state.get("next_run_at")
        })
        
    return results

@mcp.tool()
def elein_score_lead_icp(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Scores a lead profile against the Ideal Customer Profile using Ele-in's AI service."""
    workspace_id = authenticate()
    
    # VULNERABILITY FIXED: Sync function timeout handling and correct signature
    import concurrent.futures
    try:
        from knowledge.backend.services.elein_ai_service import score_icp_fit
    except ImportError:
        raise ValueError("score_icp_fit function not available in elein_ai_service.py")

    def _run_scoring():
        return score_icp_fit(profile_data=profile, workspace_id=workspace_id)
        
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_scoring)
            score = future.result(timeout=10.0)
            return {"score": score, "reasoning": "Numeric hybrid Bayesian + LLM score (0-100)"}
    except concurrent.futures.TimeoutError:
        raise ValueError("AI service timed out after 10 seconds")
    except Exception as e:
        raise ValueError(f"AI scoring failed: {str(e)}")

@mcp.tool()
def elein_get_person_profile(account_id: str, linkedin_url: str, max_scrolls: int = 5) -> Dict[str, Any]:
    """
    Fetch a full LinkedIn profile using the ele-in headless browser pool.
    Requires an active account_id that belongs to your workspace.
    """
    workspace_id = authenticate()
    supabase = get_supabase()
    
    # Layer 2 Paranoia: Account Ownership Validation
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise ValueError("Account not found or does not belong to your workspace.")
        
    from integrations.backend.services.linkedin_worker import _setup_browser_headless, BrowserPoolExhaustedError
    from integrations.backend.services.linkedin_pool import get_browser_pool
    
    pool = get_browser_pool()
    try:
        context = pool.acquire(account_id, _setup_browser_headless)
    except BrowserPoolExhaustedError as e:
        raise ValueError(f"Account {account_id} is currently busy processing another task. Please try again later.")
        
    page = None
    try:
        page = context.new_page()
        page.goto(linkedin_url, wait_until="domcontentloaded")
        
        from integrations.backend.services.voyager_scraper import VoyagerScraper
        scraper = VoyagerScraper(page)
        profile_data = scraper.scrape_profile(linkedin_url)
        return {"status": "success", "profile": profile_data}
    except Exception as e:
        raise ValueError(f"Failed to scrape profile: {e}")
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
        pool.release(account_id)

@mcp.tool()
def elein_send_linkedin_message(account_id: str, linkedin_url: str, message: str) -> Dict[str, Any]:
    """
    Send a LinkedIn message to a connection using the ele-in headless browser pool.
    Message will be validated against workspace safety guardrails.
    """
    workspace_id = authenticate()
    supabase = get_supabase()
    
    acc_res = supabase.table("accounts").select("id").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise ValueError("Account not found or does not belong to your workspace.")
        
    # Layer 2 Paranoia: Prevent AI from hallucinating banned phrases
    from knowledge.backend.services.elein_ai_service import enforce_banned_phrases
    safe_message = enforce_banned_phrases(message, workspace_id)
    if not safe_message:
        raise ValueError("Message contained banned phrases or failed safety checks.")
        
    from integrations.backend.services.linkedin_worker import _setup_browser_headless, BrowserPoolExhaustedError
    from integrations.backend.services.linkedin_pool import get_browser_pool
    
    pool = get_browser_pool()
    try:
        context = pool.acquire(account_id, _setup_browser_headless)
    except BrowserPoolExhaustedError as e:
        raise ValueError(f"Account {account_id} is currently busy. Please try again later.")
        
    page = None
    try:
        page = context.new_page()
        page.goto(linkedin_url, wait_until="domcontentloaded")
        
        from integrations.backend.services.voyager_scraper import VoyagerScraper
        scraper = VoyagerScraper(page)
        
        status = scraper.get_connection_status()
        if status != "CONNECTED":
            raise ValueError(f"Cannot send message. Target is not a 1st degree connection. Status: {status}")
            
        success = scraper.send_message(safe_message)
        return {"status": "success" if success else "failed", "message": safe_message}
    except Exception as e:
        raise ValueError(f"Failed to send message: {e}")
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
        pool.release(account_id)

if __name__ == "__main__":
    mcp.run()

