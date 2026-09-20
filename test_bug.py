import asyncio
import os
import uuid
import datetime
from dotenv import load_dotenv

load_dotenv("backend/.env")
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
sync_supabase = create_client(url, key)

WS_ID = "c4ec06cc-c869-432f-ade5-84318ea8e354"
CAMP_ID = str(uuid.uuid4())
VER_ID = str(uuid.uuid4())
LEAD_ID = str(uuid.uuid4())
ENR_ID = str(uuid.uuid4())
STATE_ID = str(uuid.uuid4())
TARGET_DATE = datetime.datetime.utcnow().strftime("%Y-%m-%d")

def run():
    print(f"--- USING WORKSPACE: {WS_ID} ---")
    print("--- CREATING TEST DATA ---")
    sync_supabase.table("campaigns").insert({
        "id": CAMP_ID, "workspace_id": WS_ID, "status": "ACTIVE", "name": "Test Rollup Bug Fix"
    }).execute()

    sync_supabase.table("campaign_versions").insert({
        "id": VER_ID, "campaign_id": CAMP_ID, "version": 1, "status": "published"
    }).execute()
    
    sync_supabase.table("leads").insert({
        "id": LEAD_ID, "workspace_id": WS_ID, "email": f"test_{uuid.uuid4()}@bugfix.com", 
        "first_name": "Test", "last_name": "BugFix", "linkedin_url": f"https://linkedin.com/in/{uuid.uuid4()}"
    }).execute()
    
    sync_supabase.table("campaign_enrollments").insert({
        "id": ENR_ID, "workspace_id": WS_ID, "campaign_id": CAMP_ID, "campaign_version_id": VER_ID, "lead_id": LEAD_ID
    }).execute()
    
    sync_supabase.table("campaign_execution_states").insert({
        "id": STATE_ID, "workspace_id": WS_ID, "enrollment_id": ENR_ID,
        "status": "exited", "current_node_id": None, "error_reason": "hubspot_deal_won"
    }).execute()
    
    sync_supabase.table("action_log").insert({
        "id": str(uuid.uuid4()), "workspace_id": WS_ID, "execution_state_id": STATE_ID,
        "action_type": "send_connection", "result": "success", "executed_at": datetime.datetime.utcnow().isoformat()
    }).execute()

    print("--- RUNNING ROLLUP (WITH STATES) ---")
    sync_supabase.rpc("rollup_daily_stats", {"p_target_date": TARGET_DATE, "p_workspace_id": WS_ID}).execute()
    
    stats_res = sync_supabase.table("daily_campaign_stats").select("*").eq("workspace_id", WS_ID).eq("campaign_id", CAMP_ID).eq("stat_date", TARGET_DATE).execute()
    if stats_res.data:
        print("Stats after running with states:")
        print(stats_res.data[0])
    else:
        print("No stats found.")

    print("\n--- DELETING STATES ---")
    sync_supabase.table("action_log").delete().eq("execution_state_id", STATE_ID).execute()
    sync_supabase.table("campaign_execution_states").delete().eq("id", STATE_ID).execute()

    print("--- RUNNING ROLLUP (WITHOUT STATES) ---")
    sync_supabase.rpc("rollup_daily_stats", {"p_target_date": TARGET_DATE, "p_workspace_id": WS_ID}).execute()
    
    stats_res = sync_supabase.table("daily_campaign_stats").select("*").eq("workspace_id", WS_ID).eq("campaign_id", CAMP_ID).eq("stat_date", TARGET_DATE).execute()
    if stats_res.data:
        print("Stats after running WITHOUT states (EXPECTED: 0 for all metrics):")
        print(stats_res.data[0])
    else:
        print("No stats found.")

    print("\n--- CLEANING UP TEST ROWS ---")
    sync_supabase.table("daily_campaign_stats").delete().eq("campaign_id", CAMP_ID).execute()
    sync_supabase.table("action_log").delete().eq("execution_state_id", STATE_ID).execute()
    sync_supabase.table("campaign_execution_states").delete().eq("id", STATE_ID).execute()
    sync_supabase.table("campaign_enrollments").delete().eq("id", ENR_ID).execute()
    sync_supabase.table("leads").delete().eq("id", LEAD_ID).execute()
    sync_supabase.table("campaign_versions").delete().eq("id", VER_ID).execute()
    sync_supabase.table("campaigns").delete().eq("id", CAMP_ID).execute()

run()
