import os
import uuid
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

errors = []
print("1. Verifying Database Tables...")
supabase.table("campaign_node_executions").select("id, idempotency_key, status, node_id, workspace_id, enrollment_id, campaign_version_id, node_type, attempt, error_code, output_payload, created_at").limit(1).execute()
print("   campaign_node_executions: OK")
supabase.table("campaign_execution_states").select("id, lease_token, lease_expires_at").limit(1).execute()
print("   campaign_execution_states columns: OK")
supabase.table("accounts").select("id, session_lock_worker_id").limit(1).execute()
print("   accounts columns: OK")

ws_res = supabase.table("workspaces").select("id").limit(1).execute()
if not ws_res.data:
    ws_id = str(uuid.uuid4())
    supabase.table("workspaces").insert({"id": ws_id, "name": "Smoke Test WS"}).execute()
else:
    ws_id = ws_res.data[0]["id"]

test_account_id = str(uuid.uuid4())
test_campaign_id = str(uuid.uuid4())
test_lead_id = str(uuid.uuid4())
test_enrollment_id = str(uuid.uuid4())
test_state_id = str(uuid.uuid4())

worker_id = "test-worker-123"
bad_worker_id = "hacker-456"

try:
    print("\n2. Account Lock Smoke Test...")
    supabase.table("accounts").insert({
        "id": test_account_id,
        "workspace_id": ws_id,
        "name": "Smoke Test Acc",
        "status": "ACTIVE"
    }).execute()

    res = supabase.rpc("try_acquire_account_lock", {"p_account_id": test_account_id, "p_duration_seconds": 60, "p_worker_id": worker_id}).execute()
    print(f"   try_acquire_account_lock: {res.data}")
    if not res.data: errors.append("try_acquire_account_lock failed")
    
    res2 = supabase.rpc("renew_account_lock", {"p_account_id": test_account_id, "p_worker_id": bad_worker_id, "p_extra_seconds": 120}).execute()
    print(f"   renew_account_lock (bad worker): {res2.data}")
    if res2.data: errors.append("renew_account_lock allowed bad worker")

    res3 = supabase.rpc("renew_account_lock", {"p_account_id": test_account_id, "p_worker_id": worker_id, "p_extra_seconds": 120}).execute()
    print(f"   renew_account_lock (good worker): {res3.data}")
    if not res3.data: errors.append("renew_account_lock failed")
    
    res4 = supabase.rpc("release_account_lock", {"p_account_id": test_account_id, "p_worker_id": bad_worker_id}).execute()
    print(f"   release_account_lock (bad worker): {res4.data}")
    if res4.data: errors.append("release_account_lock allowed bad worker")
    
    res5 = supabase.rpc("release_account_lock", {"p_account_id": test_account_id, "p_worker_id": worker_id}).execute()
    print(f"   release_account_lock (good worker): {res5.data}")
    if not res5.data: errors.append("release_account_lock failed")

    print("\n3. Lease Smoke Test...")
    supabase.table("campaigns").insert({
        "id": test_campaign_id,
        "workspace_id": ws_id,
        "name": "Smoke Test Campaign",
        "status": "DRAFT"
    }).execute()
    
    supabase.table("leads").insert({
        "id": test_lead_id,
        "workspace_id": ws_id,
        "first_name": "Smoke",
        "last_name": "Test",
        "linkedin_url": "https://linkedin.com/in/smoketest"
    }).execute()
    
    supabase.table("campaign_enrollments").insert({
        "id": test_enrollment_id,
        "campaign_id": test_campaign_id,
        "lead_id": test_lead_id, "workspace_id": ws_id, "campaign_version_id": str(uuid.uuid4())
    }).execute()
    
    lease_token = str(uuid.uuid4())
    supabase.table("campaign_execution_states").insert({
        "id": test_state_id,
        "enrollment_id": test_enrollment_id,
        "status": "processing",
        "lease_token": lease_token,
        "lease_expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    }).execute()
    
    bad_token = str(uuid.uuid4())
    
    res6 = supabase.rpc("renew_lead_lease", {"p_state_id": test_state_id, "p_lease_token": bad_token, "p_extra_seconds": 60}).execute()
    print(f"   renew_lead_lease (bad token): {res6.data}")
    if res6.data: errors.append("renew_lead_lease allowed bad token")
    
    res7 = supabase.rpc("renew_lead_lease", {"p_state_id": test_state_id, "p_lease_token": lease_token, "p_extra_seconds": 60}).execute()
    print(f"   renew_lead_lease (good token): {res7.data}")
    if not res7.data: errors.append("renew_lead_lease failed")

    res8 = supabase.rpc("release_lead_claim", {
        "p_state_id": test_state_id, "p_lease_token": bad_token,
        "p_next_status": "pending", "p_next_node": None, "p_next_run": None,
        "p_variables": {}, "p_error_reason": None, "p_attempts": 0
    }).execute()
    print(f"   release_lead_claim (bad token): {res8.data}")
    if res8.data: errors.append("release_lead_claim allowed bad token")

    res9 = supabase.rpc("release_lead_claim", {
        "p_state_id": test_state_id, "p_lease_token": lease_token,
        "p_next_status": "pending", "p_next_node": None, "p_next_run": None,
        "p_variables": {}, "p_error_reason": None, "p_attempts": 0
    }).execute()
    print(f"   release_lead_claim (good token): {res9.data}")
    if not res9.data: errors.append("release_lead_claim failed")

except Exception as e:
    errors.append(str(e))
finally:
    supabase.table("campaign_execution_states").delete().eq("id", test_state_id).execute()
    supabase.table("campaign_enrollments").delete().eq("id", test_enrollment_id).execute()
    supabase.table("leads").delete().eq("id", test_lead_id).execute()
    supabase.table("campaigns").delete().eq("id", test_campaign_id).execute()
    supabase.table("accounts").delete().eq("id", test_account_id).execute()

if errors:
    print("\nERRORS:", errors)
else:
    print("\nALL PASSED")
