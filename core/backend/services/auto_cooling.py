import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional, Tuple, Dict, Any
from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_HOURS = 6

def calculate_backoff_cooldown(proxy: dict, base_hours: int = 2) -> int:
    """
    Paranoia Layer 1: Exponential backoff for degraded/failing proxies.
    - 0 prior failures: base_hours (default 2h)
    - 1 prior failure: 4h
    - 2 prior failures: 8h
    - 3+ prior failures: 24h cap
    - 'quota_exceeded': minimum 6h
    - 'auth_failed': minimum 12h
    """
    if not proxy or not isinstance(proxy, dict):
        return base_hours

    status = (proxy.get("status") or "").lower().strip()
    failure_count = proxy.get("failure_count") or 0
    try:
        failure_count = max(0, int(failure_count))
    except Exception:
        failure_count = 0

    if failure_count == 0:
        backoff = base_hours
    elif failure_count == 1:
        backoff = base_hours * 2
    elif failure_count == 2:
        backoff = base_hours * 4
    elif failure_count == 3:
        backoff = base_hours * 8
    else:
        backoff = 24

    if status == "quota_exceeded":
        backoff = max(backoff, 6)
    elif status == "auth_failed":
        backoff = max(backoff, 12)
    return min(24, backoff)

def resume_cooled_accounts(supabase_client, cooldown_hours: int = DEFAULT_COOLDOWN_HOURS) -> List[str]:
    """
    Paranoia Layer 0 & 1: Finds accounts with status 'RATE_LIMITED' whose status_changed_at
    is older than cooldown_hours. Transitions them back to 'ACTIVE' and queues in-app alert.
    """
    resumed_ids = []
    try:
        if not supabase_client:
            supabase_client = get_service_client()
        
        # Query accounts with status RATE_LIMITED
        response = supabase_client.table("accounts").select("id, name, status_changed_at, workspace_id").eq("status", "RATE_LIMITED").execute()
        accounts = response.data or []
        
        now = datetime.now(timezone.utc)
        for acc in accounts:
            changed_at_str = acc.get("status_changed_at")
            if not changed_at_str:
                continue
            
            try:
                # Handle ISO format strings potentially ending in Z with timezone awareness
                clean_changed = changed_at_str.replace("Z", "+00:00")
                changed_at = datetime.fromisoformat(clean_changed)
                if changed_at.tzinfo is None:
                    changed_at = changed_at.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.error(f"[AutoCooling] Failed to parse status_changed_at for account {acc.get('id')}: {e}")
                continue
                
            if now - changed_at >= timedelta(hours=cooldown_hours):
                acc_id = acc["id"]
                workspace_id = acc.get("workspace_id")
                name = acc.get("name", "Account")
                
                # Update status to ACTIVE
                supabase_client.table("accounts").update({
                    "status": "ACTIVE",
                    "status_changed_at": now.isoformat()
                }).eq("id", acc_id).execute()
                
                # Insert in-app notification in outbox_events if table exists, or notifications table
                try:
                    notification_data = {
                        "workspace_id": workspace_id,
                        "event_type": "outreach_resumed",
                        "payload": {
                            "title": "Outreach Resumed",
                            "message": f"Account '{name}' has completed its {cooldown_hours}-hour cooling period. Automated outreach has resumed."
                        },
                        "status": "pending",
                        "created_at": now.isoformat()
                    }
                    supabase_client.table("outbox_events").insert(notification_data).execute()
                except Exception as notif_err:
                    logger.warning(f"[AutoCooling] Could not insert notification for account {acc_id}: {notif_err}")
                
                logger.info(f"[AutoCooling] Account {acc_id} ({name}) completed cooling period. Resumed to ACTIVE.")
                resumed_ids.append(acc_id)
                
    except Exception as e:
        logger.error(f"[AutoCooling] Error in resume_cooled_accounts: {e}")
        
    return resumed_ids

def probe_and_recover_degraded_proxies(supabase_client, cooldown_hours: int = 2) -> List[str]:
    """
    Paranoia Layer 1: Finds proxies marked 'degraded' or 'quarantined' whose cooldown or
    quarantine period has elapsed. Restores them to 'healthy'.
    """
    recovered_ids = []
    try:
        if not supabase_client:
            supabase_client = get_service_client()
            
        proxies = []
        proxy_select_cols = "id, host, port, protocol, username, password_encrypted, secret_ref, country_code, workspace_id, status, last_checked_at, quarantined_until, quarantine_reason, latency_ms, failure_count"
        try:
            response = supabase_client.table("proxies").select(proxy_select_cols).in_(
                "status", ["degraded", "quarantined", "auth_failed", "quota_exceeded", "rotating_flapping", "failed"]
            ).execute()
            if response and isinstance(response.data, list):
                proxies = response.data
        except Exception:
            pass

        if not proxies:
            try:
                response = supabase_client.table("proxies").select(proxy_select_cols).eq("status", "degraded").execute()
                if response and isinstance(response.data, list):
                    proxies = response.data
            except Exception:
                pass

        if not proxies:
            try:
                response = supabase_client.table("proxies").select("*").execute()
                if response and isinstance(response.data, list):
                    proxies = [p for p in response.data if p.get("status") in ("degraded", "quarantined", "auth_failed", "quota_exceeded", "rotating_flapping", "failed") or p.get("quarantined_until") or "last_checked_at" in p]
            except Exception:
                pass
        
        now = datetime.now(timezone.utc)
        for proxy in proxies:
            proxy_id = proxy["id"]
            current_failures = proxy.get("failure_count") or 0
            effective_cooldown = calculate_backoff_cooldown(proxy, base_hours=cooldown_hours)
            is_quarantine = proxy.get("status") == "quarantined" or proxy.get("quarantined_until") is not None
            
            # Layer 2 Paranoia: If auth_failed and missing credentials, never probe
            if proxy.get("status") == "auth_failed" and proxy.get("username") and not proxy.get("password_encrypted") and not proxy.get("secret_ref"):
                logger.debug(f"[ProxyAutoHeal] Proxy {proxy_id} has status auth_failed and no password ciphertext. Skipping probe.")
                continue

            if is_quarantine:
                q_until_str = proxy.get("quarantined_until")
                if q_until_str:
                    try:
                        clean_str = q_until_str.replace("Z", "+00:00")
                        q_until = datetime.fromisoformat(clean_str)
                        if q_until.tzinfo is not None:
                            now_tz = datetime.now(timezone.utc)
                            should_recover = now_tz >= q_until
                        else:
                            should_recover = now >= q_until
                    except Exception as parse_err:
                        logger.error(f"[ProxyAutoHeal] Failed to parse quarantined_until for proxy {proxy_id}: {parse_err}")
                        should_recover = False
                else:
                    checked_at_str = proxy.get("last_checked_at")
                    if checked_at_str:
                        try:
                            clean_checked = checked_at_str.replace("Z", "+00:00")
                            checked_at = datetime.fromisoformat(clean_checked)
                            if checked_at.tzinfo is not None:
                                now_tz = datetime.now(timezone.utc)
                                should_recover = (now_tz - checked_at) >= timedelta(hours=effective_cooldown)
                            else:
                                should_recover = (now - checked_at) >= timedelta(hours=effective_cooldown)
                        except Exception:
                            should_recover = True
                    else:
                        should_recover = True

                if not should_recover:
                    # Do not un-quarantine early!
                    continue

                if proxy.get("host") and proxy.get("port"):
                    from accounts.backend.services.account_auto_heal_service import probe_proxy_health
                    probe_res = probe_proxy_health(proxy, supabase=supabase_client, timeout_seconds=3.0)
                    if not probe_res.get("ok"):
                        fail_status = probe_res.get("status") or "quarantined"
                        logger.warning(f"[ProxyAutoHeal] Proxy {proxy_id} still failing neutral probe ({fail_status}: {probe_res.get('error')}). Preserving quarantine state.")
                        supabase_client.table("proxies").update({
                            "status": fail_status,
                            "failure_count": current_failures + 1,
                            "last_checked_at": now.isoformat()
                        }).eq("id", proxy_id).execute()
                        continue
                    lat = probe_res.get("latency_ms")
                else:
                    lat = proxy.get("latency_ms")

                supabase_client.table("proxies").update({
                    "status": "healthy",
                    "is_active": True,
                    "quarantined_until": None,
                    "quarantine_reason": None,
                    "failure_count": 0,
                    "latency_ms": lat,
                    "last_checked_at": now.isoformat()
                }).eq("id", proxy_id).execute()
                logger.info(f"[ProxyAutoHeal] Proxy {proxy_id} recovered from quarantine to healthy.")
                recovered_ids.append(proxy_id)

            else:
                checked_at_str = proxy.get("last_checked_at")
                if not checked_at_str:
                    should_recover = True
                else:
                    try:
                        clean_checked = checked_at_str.replace("Z", "+00:00")
                        checked_at = datetime.fromisoformat(clean_checked)
                        if checked_at.tzinfo is not None:
                            now_tz = datetime.now(timezone.utc)
                            should_recover = (now_tz - checked_at) >= timedelta(hours=effective_cooldown)
                        else:
                            should_recover = (now - checked_at) >= timedelta(hours=effective_cooldown)
                    except Exception:
                        should_recover = True

                if should_recover:
                    if proxy.get("host") and proxy.get("port"):
                        from accounts.backend.services.account_auto_heal_service import probe_proxy_health
                        probe_res = probe_proxy_health(proxy, supabase=supabase_client, timeout_seconds=3.0)
                        if not probe_res.get("ok"):
                            fail_status = probe_res.get("status") or proxy.get("status") or "degraded"
                            logger.warning(f"[ProxyAutoHeal] Proxy {proxy_id} still failing neutral probe ({fail_status}: {probe_res.get('error')}). Preserving failure state.")
                            supabase_client.table("proxies").update({
                                "status": fail_status,
                                "failure_count": current_failures + 1,
                                "last_checked_at": now.isoformat()
                            }).eq("id", proxy_id).execute()
                            continue
                        lat = probe_res.get("latency_ms")
                    else:
                        lat = proxy.get("latency_ms")

                    supabase_client.table("proxies").update({
                        "status": "healthy",
                        "is_active": True,
                        "failure_count": 0,
                        "latency_ms": lat,
                        "last_checked_at": now.isoformat()
                    }).eq("id", proxy_id).execute()
                    logger.info(f"[ProxyAutoHeal] Proxy {proxy_id} recovered from degraded to healthy.")
                    recovered_ids.append(proxy_id)
                    
    except Exception as e:
        logger.error(f"[ProxyAutoHeal] Error in probe_and_recover_degraded_proxies: {e}")
        
    return recovered_ids

async def run_auto_cooling_daemon(
    supabase_client=None,
    interval_seconds: int = 300,
    stop_event: Optional[asyncio.Event] = None,
    probe_jitter_seconds: float = 0.5
) -> None:
    """
    Paranoia Layer 0, 1 & 2: Background Auto-Cooling & Proxy Healing Daemon.
    - Continuously evaluates RATE_LIMITED accounts and degraded/quarantined proxies.
    - Uses jittered probing to avoid thundering-herd load on proxy providers.
    - Runs in non-blocking asyncio loop, catches all exceptions gracefully, and stops cleanly on stop_event.
    """
    logger.info(f"[AutoCoolingDaemon] Started daemon (interval: {interval_seconds}s)")
    while True:
        if stop_event and stop_event.is_set():
            logger.info("[AutoCoolingDaemon] Stop event set. Exiting cleanly.")
            break
        try:
            # Paranoia Layer 1: Offload synchronous DB & socket I/O to background thread pool (Eradicates FLAW-27)
            resumed_accs = await asyncio.to_thread(resume_cooled_accounts, supabase_client)
            if resumed_accs:
                logger.info(f"[AutoCoolingDaemon] Resumed {len(resumed_accs)} cooled account(s)")

            # Jitter pause
            if probe_jitter_seconds > 0:
                await asyncio.sleep(probe_jitter_seconds)

            # 2. Probe and recover degraded proxies with backoff in background thread pool
            recovered_proxies = await asyncio.to_thread(probe_and_recover_degraded_proxies, supabase_client)
            if recovered_proxies:
                logger.info(f"[AutoCoolingDaemon] Recovered {len(recovered_proxies)} proxy/proxies to healthy")

        except Exception as e:
            logger.error(f"[AutoCoolingDaemon] Unexpected error in cooling tick: {e}", exc_info=True)

        # Sleep interval or wait for stop_event
        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                break
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(interval_seconds)
