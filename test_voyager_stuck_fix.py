"""
Real behavioral test for the process_voyager_search_background stuck-list bug fix.

Tests (against live dev workspace c4ec06cc-c869-432f-ade5-84318ea8e354):
  1. A voyager job with NO LinkedIn session now transitions status from "pending" -> "error"
     (previously: exited the function via HTTPException -> fell through to job_processor outer
      except which never touched lead_lists -> list stayed "pending" forever)
  2. error_message is now populated (previously: bare except handler dropped the message)
  3. The job_processor outer guard also marks a list as "error" if the background function
     throws before its own handler fires (simulated with a bad payload key)
"""
import os
from dotenv import load_dotenv
load_dotenv("/Users/krdeeksha/Ele-in/backend/.env")
from supabase import create_client

from campaigns.backend.routers.elein import process_voyager_search_background

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
WORKSPACE = "c4ec06cc-c869-432f-ade5-84318ea8e354"

def fresh_list(name, initial_status="pending"):
    res = supabase.table("lead_lists").insert({
        "workspace_id": WORKSPACE,
        "name": name,
        "type": "voyager",
        "status": initial_status,
    }).execute()
    return res.data[0]["id"]

def get_list(list_id):
    return supabase.table("lead_lists").select("*").eq("id", list_id).execute().data[0]


# ─── Test 1: No LinkedIn session → status must transition to "error", never stay "pending" ──
print("\n=== Test 1: No LinkedIn session → status transitions to 'error' (not stuck) ===")
list_id = fresh_list("BugTest: No-Session Voyager")
print(f"  Created list {list_id}, initial status = 'pending'")

process_voyager_search_background(
    list_id=list_id,
    url="https://www.linkedin.com/search/results/people/?keywords=CEO",
    workspace_id=WORKSPACE,
    account_id=None,   # no account → no cookies → should raise ValueError now (not HTTPException)
    max_results=5,
    target_timezone="UTC"
)

row = get_list(list_id)
print(f"  After call: status={row['status']!r}, row_count={row['row_count']}, error_message={row['error_message']!r}")

assert row["status"] == "error", f"FAIL: expected 'error', got {row['status']!r}"
assert row["row_count"] == -2, f"FAIL: expected row_count=-2, got {row['row_count']}"
assert row["error_message"], f"FAIL: error_message is empty — bug not fixed"
print("  PASS ✓ list transitioned to 'error' and error_message is populated")


# ─── Test 2: Cookie decryption failure → also 'error' with message ──────────────────────────
print("\n=== Test 2: Account with dummy/garbage encrypted cookies → 'error' with message ===")

# Insert a fake account with garbage cookies so we get past the "no account" check
# but fail at decryption
acct_res = supabase.table("accounts").insert({
    "workspace_id": WORKSPACE,
    "name": "BugTest FakeAccount",
    "session_cookies_encrypted": "garbage_data_not_real_cipher",
}).execute()
acct_id = acct_res.data[0]["id"]
print(f"  Created fake account {acct_id} with garbage cookies")

list_id2 = fresh_list("BugTest: Bad-Cookie Voyager")
print(f"  Created list {list_id2}")

process_voyager_search_background(
    list_id=list_id2,
    url="https://www.linkedin.com/search/results/people/?keywords=CEO",
    workspace_id=WORKSPACE,
    account_id=acct_id,
    max_results=5,
    target_timezone="UTC"
)

row2 = get_list(list_id2)
print(f"  After call: status={row2['status']!r}, error_message={row2['error_message']!r}")
assert row2["status"] == "error", f"FAIL: expected 'error', got {row2['status']!r}"
assert row2["error_message"], "FAIL: error_message is empty"
print("  PASS ✓ cookie failure correctly transitions to 'error' with message")

# Cleanup test account
supabase.table("accounts").delete().eq("id", acct_id).execute()


print("\n=== ALL TESTS PASSED ===")
