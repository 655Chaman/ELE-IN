import requests, os, json
from dotenv import load_dotenv

load_dotenv("backend/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

headers = {"apikey": key, "Authorization": f"Bearer {key}"}
res = requests.get(f"{url}/rest/v1/", headers=headers)
schema = res.json()

if "definitions" in schema and "list_members" in schema["definitions"]:
    props = schema["definitions"]["list_members"]["properties"]
    print("column_name | data_type")
    print("------------------------")
    for col, info in props.items():
        print(f"{col} | {info.get('format', info.get('type'))}")
else:
    print("Could not find list_members in schema definitions")
