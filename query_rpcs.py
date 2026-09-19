import os
import requests
from dotenv import load_dotenv

load_dotenv("backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

res = requests.get(f"{url}/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"})
schema = res.json()

print("RPCs:")
for path in schema.get("paths", {}):
    if path.startswith("/rpc/"):
        print(path)
