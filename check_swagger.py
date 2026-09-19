import requests
import os
from dotenv import load_dotenv

load_dotenv("backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

headers = {"apikey": key, "Authorization": f"Bearer {key}"}
res = requests.get(f"{url}/rest/v1/", headers=headers)
schema = res.json()

# Look for lead_lists in definitions
if "definitions" in schema and "lead_lists" in schema["definitions"]:
    props = schema["definitions"]["lead_lists"]["properties"]
    print("lead_lists actual columns:")
    for col, info in props.items():
        print(f"- {col}: {info.get('type')} ({info.get('format')})")
else:
    print("Could not find lead_lists in schema definitions")
