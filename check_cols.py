import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

try:
    res = supabase.rpc("execute_sql", {"sql_query": "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'lead_lists';"}).execute()
    print(res.data)
except Exception as e:
    print(e)
