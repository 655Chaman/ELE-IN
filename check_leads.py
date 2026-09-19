import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

res1 = supabase.table("leads").select("id", count="exact").not_.is_("location", "null").execute()
print(f"COUNT(*): {res1.count}")

res2 = supabase.table("leads").select("id, location, created_at").not_.is_("location", "null").limit(3).execute()
print("SAMPLES:")
for r in res2.data:
    print(r)
