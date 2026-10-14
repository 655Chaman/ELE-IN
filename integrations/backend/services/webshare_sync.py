import os
import logging
import requests
from typing import Dict, Any

from core.backend.core import crypto

logger = logging.getLogger(__name__)

def sync_webshare_proxies(workspace_id: str, supabase) -> Dict[str, Any]:
    api_key = os.environ.get("WEBSHARE_API_KEY")
    try:
        res = supabase.table("system_api_keys").select("api_key").eq("action_type", "webshare").execute()
        if res.data and len(res.data) > 0:
            api_key = res.data[0].get("api_key") or api_key
    except Exception as e:
        logger.warning(f"Could not fetch webshare api key from system_api_keys: {e}")
        
    if not api_key:
        raise ValueError("Webshare API key not found in system_api_keys or environment")

    headers = {"Authorization": f"Token {api_key}"}
    url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"
    
    synced_count = 0
    errors = 0
    synced_labels = []

    while url:
        resp = requests.get(url, headers=headers, timeout=20)
        if not resp.ok:
            raise RuntimeError(f"Webshare API error {resp.status_code}: {resp.text}")
            
        data = resp.json()
        results = data.get("results", [])
        
        for result in results:
            try:
                # Build payload
                password_plain = result.get("password", "")
                password_encrypted_hex = None
                if password_plain:
                    enc_bytes = crypto.encrypt_bytes(password_plain.encode("utf-8"))
                    password_encrypted_hex = crypto.bytes_to_pg_hex(enc_bytes)
                
                label = f"webshare-{result.get('username')}"
                payload = {
                    "workspace_id": workspace_id,
                    "label": label,
                    "protocol": "http",
                    "host": result.get("proxy_address"),
                    "port": result.get("port"),
                    "username": result.get("username"),
                    "country_code": result.get("country_code", ""),
                    "is_active": result.get("valid", True),
                    "source": "webshare",
                    "provider": "webshare"
                }
                
                if password_encrypted_hex:
                    payload["password_encrypted"] = password_encrypted_hex
                
                supabase.table("proxies").upsert(
                    payload,
                    on_conflict="workspace_id,host,port"
                ).execute()
                
                synced_count += 1
                synced_labels.append(label)
                
            except Exception as e:
                logger.error(f"Error syncing proxy {result.get('proxy_address')}: {e}")
                errors += 1
                
        url = data.get("next")
        
    return {
        "synced": synced_count,
        "errors": errors,
        "proxies": synced_labels
    }
