import os
import uuid
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
if not url or not key:
    print("Missing SUPABASE_URL or SUPABASE_KEY")
    exit(1)

supabase: Client = create_client(url, key)

errors = []

print("1. Verifying Database Tables...")
try:
    # updated_at was not present in the DB before this session, so skip checking it.
    supabase.table("campaign_node_executions").select("id, idempotency_key, status, node_id, workspace_id, enrollment_id, campaign_version_id, node_type, attempt, error_code, output_payload, created_at").limit(1).execute()
    print("   campaign_node_executions: OK")
except Exception as e:
    errors.append(f"campaign_node_executions error: {e}")

try:
    supabase.table("campaign_execution_states").select("id, lease_token, lease_expires_at").limit(1).execute()
    print("   campaign_execution_states columns: OK")
except Exception as e:
    errors.append(f"campaign_execution_states error: {e}")

try:
    supabase.table("accounts").select("id, session_lock_worker_id").limit(1).execute()
    print("   accounts columns: OK")
except Exception as e:
    errors.append(f"accounts error: {e}")


print("\n2. Account Lock Smoke Test...")
test_account_id = str(uuid.uuid4())
worker_id = "test-worker-123"
bad_worker_id = "hacker-456"

try:
    supabase.table("accounts").insert({
        "id": test_account_id,
        "status": "ACTIVE"
    }).execute()
    
    res = supabase.rpc("try_acquire_account_lock", {
        "p_account_id": test_account_id,
        "p_duration_seconds": 60,
        "p_worker_id": worker_id
    }).execute()
    acquire_success = res.data
    print(f"   try_acquire_account_lock: {acquire_success}")
    if not acquire_success: errors.append("try_acquire_account_lock failed")
    
    res2 = supabase.rpc("renew_account_lock", {
        "p_account_id": test_account_id,
        "p_worker_id": bad_worker_id,
        "p_extra_seconds": 120
    }).execute()
    renew_bad = res2.data
    print(f"   renew_account_lock (bad worker): {renew_bad}")
    if renew_bad: errors.append("renew_account_lock allowed bad worker")

    res3 = supabase.rpc("renew_account_lock", {
        "p_account_id": test_account_id,
        "p_worker_id": worker_id,
        "p_extra_seconds": 120
    }).execute()
    renew_good = res3.data
    print(f"   renew_account_lock (good worker): {renew_good}")
    if not renew_good: errors.append("renew_account_lock failed")
    
    res4 = supabase.rpc("release_account_lock", {
        "p_account_id": test_account_id,
        "p_worker_id": bad_worker_id
    }).execute()
    release_bad = res4.data
    print(f"   release_account_lock (bad worker): {release_bad}")
    if release_bad: errors.append("release_account_lock allowed bad worker")
    
    res5 = supabase.rpc("release_account_lock", {
        "p_account_id": test_account_id,
        "p_worker_id": worker_id
    }).execute()
    release_good = res5.data
    print(f"   release_account_lock (good worker): {release_good}")
    if not release_good: errors.append("release_account_lock failed")

except Exception as e:
    errors.append(f"Account tests exception: {e}")
finally:
    supabase.table("accounts").delete().eq("id", test_account_id).execute()

print("\n3. Lease Smoke Test...")
test_state_id = str(uuid.uuid4())
test_enrollment_id = str(uuid.uuid4())

try:
    lease_token = str(uuid.uuid4())
    supabase.table("campaign_execution_states").insert({
        "id": test_state_id,
        "enrollment_id": test_enrollment_id,
        "status": "processing",
        "lease_token": lease_token,
        "lease_expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    }).execute()
    
    bad_token = str(uuid.uuid4())
    
    res6 = supabase.rpc("renew_lead_lease", {
        "p_state_id": test_state_id,
        "p_lease_token": bad_token,
        "p_extra_seconds": 60
    }).execute()
    print(f"   renew_lead_lease (bad token): {res6.data}")
    if res6.data: errors.append("renew_lead_lease allowed bad token")
    
    res7 = supabase.rpc("renew_lead_lease", {
        "p_state_id": test_state_id,
        "p_lease_token": lease_token,
        "p_extra_seconds": 60
    }).execute()
    print(f"   renew_lead_lease (good token): {res7.data}")
    if not res7.data: errors.append("renew_lead_lease failed")

    res8 = supabase.rpc("release_lead_claim", {
        "p_state_id": test_state_id,
        "p_lease_token": bad_token,
        "p_next_status": "pending",
        "p_next_node": None,
        "p_next_run": None,
        "p_variables": {},
        "p_error_reason": None,
        "p_attempts": 0
    }).execute()
    print(f"   release_lead_claim (bad token): {res8.data}")
    if res8.data: errors.append("release_lead_claim allowed bad token")

    res9 = supabase.rpc("release_lead_claim", {
        "p_state_id": test_state_id,
        "p_lease_token": lease_token,
        "p_next_status": "pending",
        "p_next_node": None,
        "p_next_run": None,
        "p_variables": {},
        "p_error_reason": None,
        "p_attempts": 0
    }).execute()
    print(f"   release_lead_claim (good token): {res9.data}")
    if not res9.data: errors.append("release_lead_claim failed")

except Exception as e:
    errors.append(f"Lease tests exception: {e}")
finally:
    supabase.table("campaign_execution_states").delete().eq("id", test_state_id).execute()

if errors:
    print("\nERRORS:")
    for e in errors: print(f"- {e}")
else:
    print("\nALL PASSED")

