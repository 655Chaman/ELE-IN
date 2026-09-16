import logging
import json
import time
from datetime import datetime

from supabase import Client
from typing import List

from core.backend.core.config import config
from core.backend.api.auth_dep import get_service_client
from integrations.backend.services.linkedin_worker import LinkedInWorker

logger = logging.getLogger(__name__)

def _try_proxy_failover(supabase, acc: dict, cookies_json: str, country_code: str = None) -> bool:
    """
    If an account session appears dead, it might just be the assigned proxy is blacklisted.
    Find another healthy proxy IN THE SAME COUNTRY (or fallback to any healthy proxy) and try again.
    """
    workspace_id = acc.get("workspace_id")
    current_proxy_id = acc.get("proxy_id")
    acc_id = acc["id"]
    
    # Fetch all OTHER healthy proxies
    proxies_res = supabase.table("proxies").select(
        "id, host, port, username, protocol, country_code"
    ).eq("status", "healthy").execute()
    
    candidates = [p for p in (proxies_res.data or []) if p["id"] != current_proxy_id]
    
    if not candidates:
        logger.warning(f"No alternative proxies available for account {acc_id}")
        return False
        
    # Prioritize same country!
    if country_code:
        same_country = [p for p in candidates if p.get("country_code") == country_code]
        if same_country:
            candidates = same_country
            logger.info(f"Found {len(candidates)} failover proxies matching country {country_code}")
    
    for proxy in candidates:

        proxy_url = f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"
        if proxy.get("username"):
            proxy_url = f"{proxy['protocol']}://{proxy['username']}@{proxy['host']}:{proxy['port']}"
        
        logger.info(f"Trying failover proxy {proxy['host']} for account {acc_id}...")
        try:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=proxy_url)
            is_valid = worker.check_session_valid()
        except Exception as e:
            capture_error(e, context={"service": "health_check_cron", "message": f"Proxy {proxy['host']} also failed"})
            # Mark this proxy as unhealthy
            supabase.table("proxies").update({
                "status": "unhealthy",
                "last_checked_at": datetime.utcnow().isoformat()
            }).eq("id", proxy["id"]).execute()
            continue
        
        if is_valid:
            logger.info(f"Proxy failover SUCCESS: account {acc_id} now using proxy {proxy['host']}")
            # Update the account to use the new working proxy
            supabase.table("accounts").update({
                "proxy_id": proxy["id"],
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", acc_id).execute()
            # Mark the old proxy as unhealthy
            if current_proxy_id:
                supabase.table("proxies").update({
                    "status": "unhealthy",
                    "last_checked_at": datetime.utcnow().isoformat()
                }).eq("id", current_proxy_id).execute()
            return True
        else:
            # This proxy is also bad
            supabase.table("proxies").update({
                "status": "unhealthy",
                "last_checked_at": datetime.utcnow().isoformat()
            }).eq("id", proxy["id"]).execute()
    
    return False  # All proxies exhausted

def run_health_checks():
    """
    Cron job to ping LinkedIn for all ACTIVE accounts.
    If an account cookie is dead:
      1. Marks account as DISCONNECTED.
      2. Pauses any ACTIVE campaigns using that account.
    """
    logger.info("Starting LinkedIn session health checks...")
    supabase: Client = get_service_client()
    
    # 1. Fetch all active accounts
    res = supabase.table("accounts").select(
        "id, name, session_cookies_encrypted, proxy_id, workspace_id"
    ).eq("status", "ACTIVE").execute()
    
    accounts = res.data or []
    if not accounts:
        logger.info("No active accounts to check.")
        return

    logger.info(f"Found {len(accounts)} active accounts. Pinging LinkedIn...")

    # Fetch proxies to build map
    proxy_ids = [acc["proxy_id"] for acc in accounts if acc.get("proxy_id")]
    proxy_map = {}
    if proxy_ids:
        proxies_res = supabase.table("proxies").select("id, host, port, username, protocol, status, country_code").in_("id", proxy_ids).execute()
        proxy_map = {proxy["id"]: proxy for proxy in (proxies_res.data or [])}

    for acc in accounts:
        acc_id = acc["id"]
        acc_name = acc["name"]
        cookies_json = acc.get("session_cookies_encrypted")
        proxy_id = acc.get("proxy_id")
        
        proxy_url = None
        if proxy_id and proxy_id in proxy_map:
            p = proxy_map[proxy_id]
            protocol = p.get("protocol", "http")
            host = p.get("host")
            port = p.get("port")
            username = p.get("username")
            if username:
                proxy_url = f"{protocol}://{username}@{host}:{port}"
            else:
                proxy_url = f"{protocol}://{host}:{port}"
        
        if not cookies_json:
            logger.error(f"Account {acc_id} has no cookies. Marking DISCONNECTED.")
            _disconnect_account(supabase, acc_id, acc_name, acc.get('workspace_id'))
            continue
            
        # 2. Ping LinkedIn
        try:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=proxy_url)
            is_valid = worker.check_session_valid()
        except Exception as e:
            capture_error(e, context={"service": "health_check_cron", "account_id": acc_id})
            is_valid = False
            
        if is_valid:
            logger.info(f"Account {acc_name} ({acc_id}) session is VALID.")
            try:
                today_str = datetime.utcnow().date().isoformat()
                mc_res = supabase.table("account_daily_action_counts").select("count").eq("account_id", acc_id).eq("action_type", "connection_request").eq("usage_date", today_str).execute()
                machine_sent_today = mc_res.data[0]["count"] if mc_res.data else 0
                
                log_res = supabase.table("action_log").select("id", count="exact").eq("account_id", acc_id).ilike("action_type", "%connection%").gte("executed_at", today_str).execute()
                logged_actions_today = log_res.count if hasattr(log_res, 'count') and log_res.count is not None else len(log_res.data)
                
                if logged_actions_today > machine_sent_today * 1.3:
                    logger.warning(f"[ANOMALY] Account {acc_id} shows possible manual sending: machine_sent={machine_sent_today}, logged={logged_actions_today}")
                    try:
                        supabase.table("accounts").update({
                            "manual_send_suspected": True,
                            "manual_send_suspected_at": datetime.utcnow().isoformat()
                        }).eq("id", acc_id).execute()
                    except Exception as inner_e:
                        capture_error(inner_e, context={"service": "health_check_cron"})
            except Exception as e:
                capture_error(e, context={"service": "health_check_cron"})

            supabase.table("accounts").update({
                "last_health_check_at": datetime.utcnow().isoformat()
            }).eq("id", acc_id).execute()
        else:
            logger.warning(f"Account {acc_name} session dead. Attempting proxy failover...")
            country = proxy_map.get(proxy_id, {}).get("country_code") if proxy_id else None
            recovered = _try_proxy_failover(supabase, acc, cookies_json, country_code=country)
            if not recovered:
                logger.warning(f"All proxies exhausted for {acc_name}. Marking DISCONNECTED.")
                _disconnect_account(supabase, acc_id, acc_name, acc.get('workspace_id'))
            else:
                logger.info(f"Account {acc_name} recovered via proxy failover. Staying ACTIVE.")


import os, requests

def _send_disconnect_email(owner_id: str, account_name: str, supabase):
    """Send a transactional alert email when a LinkedIn account is disconnected."""
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_key:
        logger.warning(f"[EmailAlert] RESEND_API_KEY not configured. Cannot send disconnect alert for account '{account_name}'.")
        return
    
    # Look up the user's email from auth
    try:
        user_res = supabase.auth.admin.get_user(owner_id)
        user_email = user_res.user.email if user_res and user_res.user else None
    except Exception as e:
        capture_error(e, context={"service": "health_check_cron"})
        return
    
    if not user_email:
        logger.warning(f"[EmailAlert] No email found for owner {owner_id}")
        return
    
    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json={
                "from": "Ele-in Alerts <alerts@ele-in.com>",
                "to": [user_email],
                "subject": f"⚠️ Action Required: LinkedIn Account Disconnected",
                "html": f"""<div style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px'>
                    <h2 style='color:#e85d04'>Your LinkedIn account needs attention</h2>
                    <p>Your connected LinkedIn account <strong>'{account_name}'</strong> has been automatically disconnected because its session expired.</p>
                    <p><strong>What this means:</strong> Any active campaigns using this account have been paused to prevent sending failures.</p>
                    <p><strong>What to do:</strong> Log into Ele-in, go to <strong>Accounts</strong>, and reconnect this account by refreshing your session cookies.</p>
                    <p>If you have questions, reply to this email.</p>
                    <hr style='margin:24px 0;border:none;border-top:1px solid #e5e7eb'/>
                    <p style='color:#9ca3af;font-size:12px'>This is an automated alert from Ele-in. You are receiving this because you own a LinkedIn account connected to the platform.</p>
                </div>"""
            },
            timeout=10
        )
        if res.status_code in [200, 201, 202]:
            logger.info(f"[EmailAlert] Disconnect alert sent to {user_email} for account '{account_name}'")
        else:
            logger.error(f"[EmailAlert] Resend returned {res.status_code}: {res.text}")
    except Exception as e:
        capture_error(e, context={"service": "health_check_cron"})

def _disconnect_account(supabase: Client, acc_id: str, acc_name: str, workspace_id: str = None):
    # a. Update account status
    supabase.table("accounts").update({
        "status": "DISCONNECTED",
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", acc_id).execute()
    
    # b. Notify the user
    if workspace_id:
        try:
            # Look up the user email associated with this workspace to send a notification
            user_res = supabase.table("workspaces").select("owner_id").eq("id", workspace_id).execute()
            if user_res.data:
                owner_id = user_res.data[0].get("owner_id")
                _send_disconnect_email(owner_id, acc_name, supabase)
                logger.info(f"DISPATCH EMAIL TO OWNER {owner_id}: Your LinkedIn account '{acc_name}' was disconnected. Please reconnect it immediately.")
                
                # Insert an alert into the UI notification center (if exists) or action_log
                supabase.table("action_log").insert({
                    "workspace_id": workspace_id,
                    "action_type": "activity_check",
                    "result": "error",
                    "metadata": {"alert_type": "account_disconnected", "account_name": acc_name, "account_id": acc_id},
                    "error_detail": f"Account {acc_name} disconnected. Reconnect required.",
                    "executed_at": datetime.utcnow().isoformat()
                }).execute()
        except Exception as e:
            capture_error(e, context={"service": "health_check_cron"})
    
    # c. Find campaigns using this account to see if they need pausing
    camps_res = supabase.table("campaigns").select(
        "id, name, sender_account_ids_json"
    ).eq("status", "ACTIVE").execute()
    
    for camp in (camps_res.data or []):
        try:
            acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", camp["id"]).execute()
            senders = [r["account_id"] for r in acc_res.data]
        except Exception:
            try:
                senders = json.loads(camp.get("sender_account_ids_json", "[]"))
            except:
                continue
            
        if acc_id in senders:
            # Check if there are any remaining ACTIVE senders for this campaign
            active_senders = supabase.table("accounts").select("id").in_("id", senders).eq("status", "ACTIVE").execute()
            if not active_senders.data:
                logger.warning(f"Pausing Campaign '{camp['name']}' because ALL senders disconnected.")
                supabase.table("campaigns").update({
                    "status": "PAUSED",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", camp["id"]).execute()
            else:
                logger.info(f"Campaign '{camp['name']}' continues using {len(active_senders.data)} remaining active senders.")

if __name__ == "__main__":
    import sys
    from core.backend.services.telemetry import capture_error, emit_heartbeat
    logging.basicConfig(level=logging.INFO)
    try:
        run_health_checks()
        emit_heartbeat("health_check_cron")
    except Exception as e:
        capture_error(e, context={"service": "health_check_cron"})
        sys.exit(1)
