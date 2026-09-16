import os
import requests

SUPABASE_URL = "https://cztwrosldjrichuwdpxu.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6dHdyb3NsZGpyaWNodXdkcHh1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzQ5NTUxOSwiZXhwIjoyMTAzMDcxNTE5fQ.9hBpJ21IyUXAnIGV97_GdYymUk-YdjVzjFmfVyeX57A"

headers = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

# Use postgrest to query information_schema or just execute SQL
# Wait, postgrest exposes views. There's an RPC endpoint if a function exists.
# We can't arbitrarily query pg_constraint. Let's try querying the tables directly via REST.
# If I fetch a row from campaign_enrollments, I might see the columns.

# Try to get campaign_enrollments columns by sending OPTIONS request
res = requests.options(f"{SUPABASE_URL}/rest/v1/campaign_enrollments", headers=headers)
print("campaign_enrollments OPTIONS:", res.status_code)
print(res.text[:500])

