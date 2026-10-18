from datetime import datetime, timedelta, timezone
import logging
from typing import List
from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_HOURS = 6

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
        
        now = datetime.utcnow()
        for acc in accounts:
            changed_at_str = acc.get("status_changed_at")
            if not changed_at_str:
                continue
            
            try:
                # Handle ISO format strings potentially ending in Z
                if changed_at_str.endswith("Z"):
                    changed_at_str = changed_at_str[:-1]
                changed_at = datetime.fromisoformat(changed_at_str)
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
        try:
            response = supabase_client.table("proxies").select("id, status, last_checked_at, quarantined_until, quarantine_reason").in_("status", ["degraded", "quarantined"]).execute()
            if response and isinstance(response.data, list):
                proxies = response.data
        except Exception:
            pass

        if not proxies:
            try:
                response = supabase_client.table("proxies").select("id, status, last_checked_at, quarantined_until, quarantine_reason").eq("status", "degraded").execute()
                if response and isinstance(response.data, list):
                    proxies = response.data
            except Exception:
                pass

        if not proxies:
            try:
                response = supabase_client.table("proxies").select("*").execute()
                if response and isinstance(response.data, list):
                    proxies = [p for p in response.data if p.get("status") in ("degraded", "quarantined") or p.get("quarantined_until") or "last_checked_at" in p]
            except Exception:
                pass
        
        now = datetime.utcnow()
        for proxy in proxies:
            proxy_id = proxy["id"]
            is_quarantine = proxy.get("status") == "quarantined" or proxy.get("quarantined_until") is not None
            
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
                                should_recover = (now_tz - checked_at) >= timedelta(hours=cooldown_hours)
                            else:
                                should_recover = (now - checked_at) >= timedelta(hours=cooldown_hours)
                        except Exception:
                            should_recover = True
                    else:
                        should_recover = True

                if not should_recover:
                    # Do not un-quarantine early!
                    continue

                supabase_client.table("proxies").update({
                    "status": "healthy",
                    "is_active": True,
                    "quarantined_until": None,
                    "quarantine_reason": None,
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
                            should_recover = (now_tz - checked_at) >= timedelta(hours=cooldown_hours)
                        else:
                            should_recover = (now - checked_at) >= timedelta(hours=cooldown_hours)
                    except Exception:
                        should_recover = True

                if should_recover:
                    supabase_client.table("proxies").update({
                        "status": "healthy",
                        "is_active": True,
                        "last_checked_at": now.isoformat()
                    }).eq("id", proxy_id).execute()
                    logger.info(f"[ProxyAutoHeal] Proxy {proxy_id} recovered from degraded to healthy.")
                    recovered_ids.append(proxy_id)
                    
    except Exception as e:
        logger.error(f"[ProxyAutoHeal] Error in probe_and_recover_degraded_proxies: {e}")
        
    return recovered_ids
