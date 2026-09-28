from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from supabase import Client
import uuid
import logging
import base64

from core.backend.api.auth_dep import get_supabase_client, get_current_workspace
from core.backend.core import crypto

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxies"])

class ProxyCreate(BaseModel):
    provider: str
    host: str
    port: int
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None

class ProxyResponse(BaseModel):
    id: str
    provider: str
    host: str
    port: int
    protocol: str
    username: Optional[str] = None
    status: str
    country_code: Optional[str] = None

@router.get("", response_model=List[ProxyResponse])
def get_proxies(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("proxies").select("id, provider, host, port, protocol, username, status, country_code").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error fetching proxies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch proxies")

@router.post("", response_model=ProxyResponse)
def create_proxy(payload: ProxyCreate, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        proxy_id = str(uuid.uuid4())
        
        insert_data = {
            "id": proxy_id,
            "workspace_id": workspace_id,
            "provider": payload.provider,
            "host": payload.host,
            "port": payload.port,
            "protocol": payload.protocol,
            "username": payload.username,
            "status": "healthy"
        }
        
        if payload.password:
            # 1. Generate DEK exactly like accounts table
            dek_b64 = crypto.generate_dek()
            dek_bytes = base64.b64decode(dek_b64)
            
            # 2. Store DEK in Supabase Vault via RPC
            rpc_res = supabase.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
            vault_ref = rpc_res.data
            
            # 3. Use secret_ref for the Vault reference (like cookie_secret_ref)
            insert_data["secret_ref"] = vault_ref
            
            # 4. Store the AES ciphertext in the new password_encrypted column (like session_cookies_encrypted)
            encrypted_bytes = crypto.encrypt_bytes(payload.password.encode('utf-8'), dek=dek_bytes)
            insert_data["password_encrypted"] = crypto.bytes_to_pg_hex(encrypted_bytes)
            
        res = supabase.table("proxies").insert(insert_data).execute()
        
        if not res.data:
            raise Exception("No data returned from insert")
            
        row = res.data[0]
        return {
            "id": row["id"],
            "provider": row["provider"],
            "host": row["host"],
            "port": row["port"],
            "protocol": row["protocol"],
            "username": row["username"],
            "status": row["status"],
            "country_code": row.get("country_code")
        }
    except Exception as e:
        logger.error(f"Error creating proxy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create proxy")

@router.delete("/{proxy_id}")
def delete_proxy(proxy_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        res = supabase.table("proxies").delete().eq("id", proxy_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Proxy not found or unauthorized")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting proxy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete proxy")
