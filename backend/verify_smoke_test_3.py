import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

cols = ["id", "idempotency_key", "status", "node_id", "workspace_id", "enrollment_id", "campaign_version_id", "node_type", "attempt", "error_code", "output_payload", "created_at", "updated_at"]

for c in cols:
    try:
        supabase.table("campaign_node_executions").select(c).limit(1).execute()
        print(f"{c}: YES")
    except Exception as e:
        print(f"{c}: NO ({e})")

