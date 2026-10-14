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
    latency_ms: Optional[int] = None
    exit_ip: Optional[str] = None
    last_checked_at: Optional[str] = None
    quarantined_until: Optional[str] = None
    quarantine_reason: Optional[str] = None

class ProxyTestRequest(BaseModel):
    provider: Optional[str] = "custom"
    host: str
    port: int
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None

class ProxyTestResponse(BaseModel):
    ok: bool
    latency_ms: int
    status: str
    exit_ip: Optional[str] = None
    country_code: Optional[str] = None
    error: Optional[str] = None

@router.get("", response_model=List[ProxyResponse])
def get_proxies(supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    try:
        try:
            res = supabase.table("proxies").select("id, provider, host, port, protocol, username, status, country_code, latency_ms, exit_ip, last_checked_at, quarantined_until, quarantine_reason").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        except Exception:
            res = supabase.table("proxies").select("id, provider, host, port, protocol, username, status, country_code").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error fetching proxies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch proxies")

@router.post("", response_model=ProxyResponse)
def create_proxy(payload: ProxyCreate, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    # Paranoia Layer 2: Input validation
    host = (payload.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="Proxy host cannot be empty")
    if payload.port < 1 or payload.port > 65535:
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")
    protocol = (payload.protocol or "http").lower().strip()
    if protocol not in ("http", "https", "socks4", "socks5"):
        raise HTTPException(status_code=400, detail="Invalid protocol. Allowed: http, https, socks4, socks5")

    # Paranoia Layer 1: Verify plan entitlement
    from core.backend.services.credit_service import TIER_LIMITS
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if ws_res.data else "FREE"
    can_proxy = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_use_custom_proxies", False)
    if not can_proxy:
        raise HTTPException(
            status_code=403,
            detail="Custom residential proxy pool configuration requires Growth Pro or Enterprise."
        )

    # Paranoia Layer 2: SSRF & Host Validation
    from core.backend.services.proxy_routing import validate_and_normalize_proxy_host
    try:
        host = validate_and_normalize_proxy_host(host)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    try:
        # Check duplicate (workspace_id, host, port)
        try:
            existing_res = supabase.table("proxies").select("id, host, port").eq("workspace_id", workspace_id).eq("host", host).eq("port", payload.port).execute()
            if existing_res and isinstance(existing_res.data, list) and len(existing_res.data) > 0:
                first_ex = existing_res.data[0]
                if isinstance(first_ex, dict) and first_ex.get("host") == host and first_ex.get("port") == payload.port:
                    raise HTTPException(status_code=409, detail=f"Proxy {host}:{payload.port} is already registered in this workspace.")
        except HTTPException:
            raise
        except Exception:
            pass

        proxy_id = str(uuid.uuid4())
        
        insert_data = {
            "id": proxy_id,
            "workspace_id": workspace_id,
            "provider": (payload.provider or "custom").strip(),
            "host": host,
            "port": payload.port,
            "protocol": protocol,
            "username": payload.username.strip() if payload.username else None,
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating proxy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create proxy")

@router.delete("/{proxy_id}")
def delete_proxy(
    proxy_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace),
    force: bool = False
):
    try:
        # Check if any active accounts are assigned to this proxy
        migrated_accounts = []
        try:
            acc_res = supabase.table("accounts").select("id, proxy_id, proxy_country").eq("workspace_id", workspace_id).eq("proxy_id", proxy_id).execute()
            bound_accounts = [
                a for a in (acc_res.data if (acc_res and isinstance(acc_res.data, list)) else [])
                if isinstance(a, dict) and a.get("proxy_id") == proxy_id and a.get("id")
            ]
        except Exception:
            bound_accounts = []

        if bound_accounts:
            from core.backend.services.proxy_routing import find_sticky_failover_proxy
            for acc in bound_accounts:
                target_country = acc.get("proxy_country")
                replacement = find_sticky_failover_proxy(
                    supabase,
                    workspace_id,
                    current_proxy_id=proxy_id,
                    target_country=target_country,
                    allow_cross_country_drift=False,
                    exclude_proxy_ids=[proxy_id]
                )
                if replacement and isinstance(replacement, dict) and replacement.get("id"):
                    supabase.table("accounts").update({"proxy_id": replacement["id"]}).eq("id", acc["id"]).eq("workspace_id", workspace_id).execute()
                    migrated_accounts.append({"account_id": acc["id"], "new_proxy_id": replacement["id"]})
                elif not force:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cannot delete proxy {proxy_id}: assigned to {len(bound_accounts)} active LinkedIn account(s) and no healthy failover proxy is available in the same country. Add a replacement proxy first or pass force=true."
                    )
                else:
                    supabase.table("accounts").update({"proxy_id": None}).eq("id", acc["id"]).eq("workspace_id", workspace_id).execute()

        res = supabase.table("proxies").delete().eq("id", proxy_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Proxy not found or unauthorized")
        return {"status": "success", "migrated_accounts": migrated_accounts}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting proxy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete proxy")

@router.post("/{proxy_id}/test", response_model=ProxyTestResponse)
def test_existing_proxy(proxy_id: str, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Tests an existing proxy from the workspace pool and updates its latency and status."""
    res = supabase.table("proxies").select("*").eq("id", proxy_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Proxy not found")
    proxy = res.data[0]
    from core.backend.services.proxy_routing import is_proxy_quarantined
    if is_proxy_quarantined(proxy):
        return {
            "ok": False,
            "latency_ms": proxy.get("latency_ms") or 5000,
            "status": "quarantined",
            "exit_ip": proxy.get("exit_ip"),
            "country_code": proxy.get("country_code"),
            "error": f"Proxy is quarantined: {proxy.get('quarantine_reason', 'security cooldown')}"
        }
    from accounts.backend.services.account_auto_heal_service import probe_proxy_health
    return probe_proxy_health(proxy, supabase=supabase)

@router.post("/test-config", response_model=ProxyTestResponse)
def test_raw_proxy_config(payload: ProxyTestRequest, supabase: Client = Depends(get_supabase_client), workspace_id: str = Depends(get_current_workspace)):
    """Tests a raw proxy configuration prior to saving."""
    host = (payload.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="Proxy host cannot be empty")
    if payload.port < 1 or payload.port > 65535:
        raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")
    protocol = (payload.protocol or "http").lower().strip()
    if protocol not in ("http", "https", "socks4", "socks5"):
        raise HTTPException(status_code=400, detail="Invalid protocol. Allowed: http, https, socks4, socks5")
    
    from core.backend.services.proxy_routing import validate_and_normalize_proxy_host
    try:
        host = validate_and_normalize_proxy_host(host)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    from accounts.backend.services.account_auto_heal_service import probe_proxy_health
    proxy_dict = {
        "host": host,
        "port": payload.port,
        "protocol": protocol,
        "username": payload.username,
        "password": payload.password
    }
    return probe_proxy_health(proxy_dict)

@router.post("/sync/webshare")
async def sync_webshare(
    workspace_id: str = Depends(get_current_workspace),
    supabase = Depends(get_supabase_client)
):
    try:
        from integrations.backend.services.webshare_sync import sync_webshare_proxies
        result = sync_webshare_proxies(workspace_id, supabase)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=502, detail=str(re))
    except Exception as e:
        logger.error(f"Error syncing webshare proxies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to sync proxies: {str(e)}")
