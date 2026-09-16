import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath('backend'))
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("NO SUPABASE CREDS")
    sys.exit(1)

sb = create_client(url, key)
res = sb.table("campaign_execution_states").select("id").limit(1).execute()
print("CES works:", len(res.data) >= 0)

# But I need to run raw SQL. Supabase REST API doesn't support arbitrary SQL queries (unless via RPC).
