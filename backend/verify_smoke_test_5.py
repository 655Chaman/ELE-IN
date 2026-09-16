import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)

cols = ["id", "email", "provider", "platform", "status"]
for c in cols:
    try:
        supabase.table("accounts").select(c).limit(1).execute()
        print(f"{c}: YES")
    except Exception as e:
        print(f"{c}: NO ({e})")
