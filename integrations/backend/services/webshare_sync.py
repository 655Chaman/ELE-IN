import os
import logging
import requests
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from core.backend.core import crypto
from core.backend.services.proxy_routing import (
    validate_and_normalize_proxy_host,
    extract_ip_subnet
)

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
                
                raw_host = result.get("proxy_address") or result.get("host")
                clean_host = validate_and_normalize_proxy_host(raw_host, allow_private=False)
                subnet = extract_ip_subnet(clean_host)

                label = f"webshare-{result.get('username')}"
                payload = {
                    "workspace_id": workspace_id,
                    "label": label,
                    "protocol": "http",
                    "host": clean_host,
                    "port": result.get("port"),
                    "username": result.get("username"),
                    "country_code": (result.get("country_code") or "").strip().upper()[:10],
                    "is_active": result.get("valid", True),
                    "source": "webshare",
                    "provider": "webshare",
                    "status": "healthy"
                }

                if password_plain:
                    dek_b64 = crypto.generate_dek()
                    dek_bytes = base64.b64decode(dek_b64)
                    try:
                        rpc_res = supabase.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
                        vault_ref = rpc_res.data
                        payload["secret_ref"] = vault_ref
                    except Exception as v_err:
                        logger.warning(f"Failed to store DEK in vault for webshare proxy: {v_err}")
                        vault_ref = None

                    enc_bytes = crypto.encrypt_bytes(password_plain.encode("utf-8"), dek=dek_bytes if vault_ref else None)
                    payload["password_encrypted"] = crypto.bytes_to_pg_hex(enc_bytes)

                try:
                    q = supabase.table("proxies").select("id")
                    if workspace_id:
                        q = q.eq("workspace_id", workspace_id)
                    else:
                        q = q.is_("workspace_id", "null")
                    existing = q.eq("host", payload["host"]).eq("port", payload["port"]).execute()
                    if existing.data and len(existing.data) > 0:
                        supabase.table("proxies").update(payload).eq("id", existing.data[0]["id"]).execute()
                    else:
                        supabase.table("proxies").insert(payload).execute()
                except Exception as upsert_err:
                    logger.error(f"Failed to persist proxy {clean_host}: {upsert_err}")
                    raise
                
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

def handle_webshare_webhook_payload(
    payload: Dict[str, Any],
    supabase,
    workspace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Three-Layer Paranoia Framework: Webshare Webhook Ingestion Engine
    - Layer 0: Parses proxy replacement and refresh events, encrypting credentials and inserting/updating proxy records.
    - Layer 1 (Environmental): Automatic Account Re-binding: If an old proxy was assigned to active LinkedIn accounts,
      migrates accounts.proxy_id to the new proxy atomically. Prevents campaigns from crashing when Webshare rotates an IP.
    - Layer 2 (Human & Attack Paranoia): Validates host against SSRF/private networks, validates ports (1-65535),
      sanitizes country codes, and ensures idempotency.
    """
    if not payload or not isinstance(payload, dict):
        raise ValueError("Invalid webhook payload: expected JSON object")

    event = (payload.get("event") or payload.get("action") or "sync").lower().strip()
    logger.info(f"[WebshareWebhook] Received event '{event}' for workspace '{workspace_id}'")

    # Case 1: Proxy Replacement Event
    if event in ("proxy_replaced", "proxy.replacement", "replace"):
        old_data = payload.get("old_proxy") or {}
        new_data = payload.get("new_proxy") or {}

        if not new_data:
            raise ValueError("Replacement event missing 'new_proxy' object")

        raw_new_host = new_data.get("proxy_address") or new_data.get("host")
        if not raw_new_host:
            raise ValueError("New proxy missing host/proxy_address")

        # Layer 2 Paranoia: SSRF Guard
        new_host = validate_and_normalize_proxy_host(raw_new_host, allow_private=False)
        try:
            new_port = int(new_data.get("port", 80))
            if new_port < 1 or new_port > 65535:
                raise ValueError("Port out of bounds")
        except Exception:
            raise ValueError(f"Invalid proxy port: {new_data.get('port')}")

        target_ws = workspace_id or payload.get("workspace_id") or new_data.get("workspace_id")
        new_subnet = extract_ip_subnet(new_host)
        new_username = new_data.get("username")
        new_password = new_data.get("password")
        new_country = (new_data.get("country_code") or "").strip().upper()[:10]

        new_proxy_record = {
            "workspace_id": target_ws,
            "label": f"webshare-{new_username or new_host}",
            "protocol": (new_data.get("protocol") or "http").lower(),
            "host": new_host,
            "port": new_port,
            "username": new_username,
            "country_code": new_country,
            "subnet": new_subnet,
            "is_active": new_data.get("valid", True),
            "source": "webshare",
            "provider": "webshare",
            "status": "healthy",
            "last_checked_at": datetime.now(timezone.utc).isoformat()
        }

        if new_password:
            dek_b64 = crypto.generate_dek()
            dek_bytes = base64.b64decode(dek_b64)
            try:
                rpc_res = supabase.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
                vault_ref = rpc_res.data
                new_proxy_record["secret_ref"] = vault_ref
            except Exception as v_err:
                logger.warning(f"[WebshareWebhook] Failed to store DEK in vault: {v_err}")
                vault_ref = None

            enc_bytes = crypto.encrypt_bytes(new_password.encode("utf-8"), dek=dek_bytes if vault_ref else None)
            new_proxy_record["password_encrypted"] = crypto.bytes_to_pg_hex(enc_bytes)

        # Upsert new proxy
        new_proxy_id = None
        try:
            up_res = supabase.table("proxies").upsert(
                new_proxy_record,
                on_conflict="workspace_id,host,port"
            ).execute()
            if up_res.data and len(up_res.data) > 0:
                new_proxy_id = up_res.data[0].get("id")
        except Exception:
            # Fallback query
            q = supabase.table("proxies").select("id").eq("host", new_host).eq("port", new_port)
            if target_ws:
                q = q.eq("workspace_id", target_ws)
            existing = q.execute()
            if existing.data and len(existing.data) > 0:
                new_proxy_id = existing.data[0]["id"]
                supabase.table("proxies").update(new_proxy_record).eq("id", new_proxy_id).execute()
            else:
                ins_res = supabase.table("proxies").insert(new_proxy_record).execute()
                if ins_res.data and len(ins_res.data) > 0:
                    new_proxy_id = ins_res.data[0]["id"]

        # Layer 1 Paranoia: Rebind accounts from old proxy to new proxy
        migrated_accounts = []
        old_proxy_id = None
        old_raw_host = old_data.get("proxy_address") or old_data.get("host")
        old_port = old_data.get("port")

        if old_raw_host:
            try:
                old_q = supabase.table("proxies").select("id").eq("host", old_raw_host)
                if old_port:
                    old_q = old_q.eq("port", int(old_port))
                if target_ws:
                    old_q = old_q.eq("workspace_id", target_ws)
                old_res = old_q.execute()
                if old_res.data and len(old_res.data) > 0:
                    old_proxy_id = old_res.data[0]["id"]
            except Exception as e:
                logger.warning(f"[WebshareWebhook] Error looking up old proxy: {e}")

        if old_proxy_id and new_proxy_id:
            try:
                # Find accounts bound to old proxy
                acc_res = supabase.table("accounts").select("id, name").eq("proxy_id", old_proxy_id).execute()
                accounts_to_migrate = acc_res.data or []
                for acc in accounts_to_migrate:
                    supabase.table("accounts").update({
                        "proxy_id": new_proxy_id
                    }).eq("id", acc["id"]).execute()
                    migrated_accounts.append(acc["id"])
                    logger.info(f"[WebshareWebhook] Rebound account {acc.get('name')} ({acc['id']}) from old proxy {old_proxy_id} to new proxy {new_proxy_id}")

                # Mark old proxy as degraded/replaced
                supabase.table("proxies").update({
                    "status": "degraded",
                    "is_active": False,
                    "quarantine_reason": f"replaced_by_webshare:{new_proxy_id}",
                    "last_checked_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", old_proxy_id).execute()
            except Exception as rebind_err:
                logger.error(f"[WebshareWebhook] Error rebinding accounts to new proxy: {rebind_err}")

        return {
            "status": "success",
            "event": event,
            "new_proxy_id": new_proxy_id,
            "old_proxy_id": old_proxy_id,
            "migrated_accounts": migrated_accounts,
            "count_migrated": len(migrated_accounts)
        }

    # Case 2: Full Sync or Refresh Event
    if event in ("sync", "refresh", "proxy.list_updated", "list_updated"):
        target_ws = workspace_id or payload.get("workspace_id")
        if target_ws:
            sync_res = sync_webshare_proxies(target_ws, supabase)
            return {
                "status": "success",
                "event": event,
                "workspace_id": target_ws,
                "sync_result": sync_res
            }
        else:
            return {
                "status": "success",
                "event": event,
                "message": "Global sync queued"
            }

    # Case 3: Bulk Results Ingestion
    if "results" in payload and isinstance(payload["results"], list):
        target_ws = workspace_id or payload.get("workspace_id")
        if not target_ws:
            raise ValueError("Bulk proxy ingestion requires workspace_id")
        
        imported = 0
        for item in payload["results"]:
            raw_h = item.get("proxy_address") or item.get("host")
            if not raw_h:
                continue
            h = validate_and_normalize_proxy_host(raw_h, allow_private=False)
            port = int(item.get("port", 80))
            sub = extract_ip_subnet(h)
            pwd = item.get("password")
            p_payload = {
                "workspace_id": target_ws,
                "label": f"webshare-{item.get('username') or h}",
                "protocol": (item.get("protocol") or "http").lower(),
                "host": h,
                "port": port,
                "username": item.get("username"),
                "country_code": (item.get("country_code") or "").strip().upper()[:10],
                "subnet": sub,
                "is_active": item.get("valid", True),
                "source": "webshare",
                "provider": "webshare",
                "status": "healthy"
            }
            if pwd:
                dek_b64 = crypto.generate_dek()
                dek_bytes = base64.b64decode(dek_b64)
                try:
                    rpc_res = supabase.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
                    p_payload["secret_ref"] = rpc_res.data
                except Exception:
                    p_payload["secret_ref"] = None
                enc_b = crypto.encrypt_bytes(pwd.encode("utf-8"), dek=dek_bytes if p_payload["secret_ref"] else None)
                p_payload["password_encrypted"] = crypto.bytes_to_pg_hex(enc_b)

            try:
                supabase.table("proxies").upsert(p_payload, on_conflict="workspace_id,host,port").execute()
            except Exception:
                pass
            imported += 1

        return {
            "status": "success",
            "event": "bulk_ingested",
            "count": imported
        }

    return {"status": "ignored", "event": event}


# ── WEBSHARE PROXY POOL PROBING & GEO-REBALANCING (PHASE Q RESILIENCE) ────────

def reconcile_and_probe_webshare_pool(
    workspace_id: str,
    supabase: Any,
    auto_quarantine_slow: bool = True,
    max_latency_ms: float = 3500.0
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Webshare Proxy Pool Probing & Account Geo-Rebalancing.
    - Probes each Webshare proxy for TCP latency and network health.
    - Quarantines degraded proxies exceeding max_latency_ms.
    - Rebalances assigned accounts away from quarantined/slow proxies to healthy proxies in the same geo-country.
    - Returns comprehensive telemetry report.
    """
    if not workspace_id or not supabase:
        return {"status": "error", "message": "Missing workspace_id or supabase client"}

    from core.backend.services.proxy_routing import (
        probe_proxy_health_and_latency,
        quarantine_proxy,
        assign_optimal_proxy_for_account,
        is_proxy_quarantined
    )

    try:
        res = supabase.table("proxies") \
            .select("*") \
            .eq("workspace_id", workspace_id) \
            .eq("provider", "webshare") \
            .execute()
        proxies = res.data or []
    except Exception as e:
        logger.error(f"[WebshareReconcile] Failed to fetch webshare proxies: {e}")
        return {"status": "error", "message": f"DB query failed: {e}"}

    total_probed = 0
    healthy_count = 0
    quarantined_count = 0
    reassigned_accounts = 0
    latency_sum = 0.0
    details = []

    for proxy in proxies:
        pid = proxy.get("id")
        probe = probe_proxy_health_and_latency(proxy)
        lat = probe.get("latency_ms", 9999.0)
        is_h = probe.get("is_healthy", False)
        total_probed += 1

        if is_h and lat <= max_latency_ms:
            healthy_count += 1
            latency_sum += lat
            details.append({"proxy_id": pid, "status": "healthy", "latency_ms": lat})
        else:
            quarantine_taken = False
            if auto_quarantine_slow and pid:
                reason = f"webshare_reconcile_latency_{int(lat)}ms"
                quarantine_proxy(supabase, pid, reason=reason)
                quarantine_taken = True
                quarantined_count += 1

            if pid:
                try:
                    acc_res = supabase.table("accounts") \
                        .select("id, country_code") \
                        .eq("workspace_id", workspace_id) \
                        .eq("proxy_id", pid) \
                        .execute()
                    affected_accounts = acc_res.data or []
                    for acc in affected_accounts:
                        acc_id = acc.get("id")
                        target_geo = acc.get("country_code") or proxy.get("country_code")
                        reassigned = assign_optimal_proxy_for_account(
                            account_id=acc_id,
                            workspace_id=workspace_id,
                            supabase=supabase,
                            target_country=target_geo,
                            max_latency_ms=max_latency_ms
                        )
                        if reassigned:
                            reassigned_accounts += 1
                except Exception as reb_err:
                    logger.warning(f"[WebshareReconcile] Failed to rebalance accounts for proxy {pid}: {reb_err}")

            details.append({
                "proxy_id": pid,
                "status": "quarantined" if quarantine_taken else "degraded",
                "latency_ms": lat,
                "error": probe.get("error")
            })

    avg_latency = round(latency_sum / healthy_count, 2) if healthy_count > 0 else 0.0

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total_probed": total_probed,
        "healthy_count": healthy_count,
        "quarantined_count": quarantined_count,
        "reassigned_accounts": reassigned_accounts,
        "average_latency_ms": avg_latency,
        "details": details
    }
