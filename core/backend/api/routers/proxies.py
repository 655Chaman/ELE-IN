from fastapi import APIRouter, HTTPException, Depends, Header, Query, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from supabase import Client
import uuid
import logging
import base64
import hmac
import os

from core.backend.api.auth_dep import get_supabase_client, get_current_workspace, get_service_client
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
    is_system: Optional[bool] = False
    assigned_accounts_count: Optional[int] = 0

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
        # 1. Fetch workspace-dedicated proxies
        ws_proxies = []
        try:
            ws_res = supabase.table("proxies").select(
                "id, provider, host, port, protocol, username, status, country_code, latency_ms, exit_ip, last_checked_at, quarantined_until, quarantine_reason, workspace_id"
            ).eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
            ws_proxies = ws_res.data or []
        except Exception:
            try:
                ws_res = supabase.table("proxies").select("id, provider, host, port, protocol, username, status, country_code, workspace_id").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
                ws_proxies = ws_res.data or []
            except Exception:
                pass

        # 2. Fetch shared system proxies (workspace_id IS NULL)
        sys_proxies = []
        try:
            sys_res = supabase.table("proxies").select(
                "id, provider, host, port, protocol, username, status, country_code, latency_ms, exit_ip, last_checked_at, quarantined_until, quarantine_reason, workspace_id"
            ).is_("workspace_id", "null").order("created_at", desc=True).execute()
            sys_proxies = sys_res.data or []
        except Exception:
            pass

        all_proxies = ws_proxies + sys_proxies

        # 3. Compute assigned accounts per proxy
        proxy_ids = [p["id"] for p in all_proxies if isinstance(p, dict) and p.get("id")]
        acc_counts: Dict[str, int] = {pid: 0 for pid in proxy_ids}
        if proxy_ids:
            try:
                acc_res = supabase.table("accounts").select("proxy_id").in_("proxy_id", proxy_ids).execute()
                for row in (acc_res.data or []):
                    pid = row.get("proxy_id")
                    if pid in acc_counts:
                        acc_counts[pid] += 1
            except Exception as e:
                logger.debug(f"Could not compute proxy account counts: {e}")

        enriched: List[Dict[str, Any]] = []
        for p in all_proxies:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            p_ws = p.get("workspace_id")
            enriched.append({
                "id": pid,
                "provider": p.get("provider") or "custom",
                "host": p.get("host"),
                "port": p.get("port"),
                "protocol": p.get("protocol") or "http",
                "username": p.get("username"),
                "status": p.get("status") or "healthy",
                "country_code": p.get("country_code"),
                "latency_ms": p.get("latency_ms"),
                "exit_ip": p.get("exit_ip"),
                "last_checked_at": p.get("last_checked_at"),
                "quarantined_until": p.get("quarantined_until"),
                "quarantine_reason": p.get("quarantine_reason"),
                "is_system": (p_ws is None),
                "assigned_accounts_count": acc_counts.get(pid, 0)
            })

        return enriched
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
    """Tests an existing proxy from the workspace pool or system pool and updates its latency and status."""
    res = supabase.table("proxies").select("*").eq("id", proxy_id).eq("workspace_id", workspace_id).execute()
    proxy = res.data[0] if (res and res.data) else None
    if not proxy:
        sys_res = supabase.table("proxies").select("*").eq("id", proxy_id).is_("workspace_id", "null").execute()
        proxy = sys_res.data[0] if (sys_res and sys_res.data) else None

    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
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

def _verify_webshare_webhook_secret(
    authorization: Optional[str] = Header(None),
    x_webshare_signature: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    supabase: Client = Depends(get_service_client)
) -> bool:
    """
    Paranoia Layer 2: Constant-time authentication for Webshare webhooks.
    Validates token via Bearer header, X-Webshare-Signature, or query param.
    """
    candidates = []
    if isinstance(authorization, str) and authorization.strip():
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
            candidates.append(parts[1])
        else:
            candidates.append(authorization.strip())
    if isinstance(x_webshare_signature, str) and x_webshare_signature.strip():
        candidates.append(x_webshare_signature.strip())
    if isinstance(token, str) and token.strip():
        candidates.append(token.strip())

    if not candidates:
        raise HTTPException(status_code=401, detail="Missing webhook authorization token")

    expected_secrets = []
    if env_sec := os.environ.get("WEBSHARE_WEBHOOK_SECRET"):
        expected_secrets.append(env_sec)
    if env_key := os.environ.get("WEBSHARE_API_KEY"):
        expected_secrets.append(env_key)

    try:
        res = supabase.table("system_api_keys").select("api_key").in_("action_type", ["webshare_webhook", "webshare"]).execute()
        for row in (res.data or []):
            if row.get("api_key"):
                expected_secrets.append(row["api_key"])
    except Exception:
        pass

    # Paranoia Layer 1 & 2: Hard Fail-Closed Security (Eradicates FLAW-07)
    if not expected_secrets:
        logger.error("[WebshareWebhook] Rejection: Neither WEBSHARE_WEBHOOK_SECRET nor valid system API keys are configured.")
        raise HTTPException(
            status_code=500,
            detail="Webhook ingestion disabled: WEBSHARE_WEBHOOK_SECRET is unconfigured. Direct injection prohibited."
        )

    for cand in candidates:
        for exp in expected_secrets:
            if hmac.compare_digest(cand.encode("utf-8"), exp.encode("utf-8")):
                return True

    raise HTTPException(status_code=401, detail="Invalid webhook signature or token")

@router.post("/webshare/webhook")
async def webshare_webhook(
    request: Request,
    workspace_id: Optional[str] = Query(None),
    authorized: bool = Depends(_verify_webshare_webhook_secret),
    supabase: Client = Depends(get_service_client)
):
    # Paranoia Layer 1 & 2: Strict Multi-Tenant Scope Validation (Eradicates FLAW-12)
    if workspace_id:
        import uuid
        try:
            uuid.UUID(workspace_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid workspace_id format. UUID required.")
        try:
            ws_check = supabase.table("workspaces").select("id").eq("id", workspace_id).execute()
            if not ws_check.data:
                raise HTTPException(status_code=404, detail="Specified workspace does not exist.")
        except HTTPException:
            raise
        except Exception as ws_err:
            logger.warning(f"[WebshareWebhook] Workspace verification non-blocking warning: {ws_err}")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    from integrations.backend.services.webshare_sync import handle_webshare_webhook_payload
    try:
        result = handle_webshare_webhook_payload(body, supabase, workspace_id=workspace_id)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[WebshareWebhook] Error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")
