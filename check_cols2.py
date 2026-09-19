import os, uuid
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

try:
    res = supabase.table("lead_lists").insert({
        "id": str(uuid.uuid4()),
        "name": "Test",
        "type": "csv",
        "row_count": 0,
        "workspace_id": "c4ec06cc-c869-432f-ade5-84318ea8e354",
        "status": "pending",
        "error_message": "test"
    }).execute()
    print("SUCCESS, inserted row with status:", res.data)
except Exception as e:
    print("ERROR:", e)
