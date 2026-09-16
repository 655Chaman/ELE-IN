import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

try:
    res = supabase.table("accounts").select("*").limit(1).execute()
    print("accounts columns:", list(res.data[0].keys()) if res.data else "Empty")
except Exception as e:
    print(e)
