import requests
import json

SUPABASE_URL = "https://cztwrosldjrichuwdpxu.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN6dHdyb3NsZGpyaWNodXdkcHh1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzQ5NTUxOSwiZXhwIjoyMTAzMDcxNTE5fQ.9hBpJ21IyUXAnIGV97_GdYymUk-YdjVzjFmfVyeX57A"

res = requests.get(f"{SUPABASE_URL}/rest/v1/", headers={"apikey": SUPABASE_SERVICE_KEY})
spec = res.json()

# Look for campaign_execution_states
if "campaign_execution_states" in spec.get("definitions", {}):
    print("Found execution states definition!")
    print(json.dumps(spec["definitions"]["campaign_execution_states"], indent=2))
    
if "campaign_enrollments" in spec.get("definitions", {}):
    print("\nFound enrollments definition!")
    print(json.dumps(spec["definitions"]["campaign_enrollments"], indent=2))

