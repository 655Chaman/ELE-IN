import asyncio, os, sys
sys.path.insert(0, os.path.abspath('backend'))
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
res = sb.rpc("my_workspace_ids").execute()
print("RPC returned:", res.data)
