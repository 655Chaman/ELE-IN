import logging
import json
import time
from datetime import datetime

from supabase import Client
from typing import List, Optional, Any, Dict

from core.backend.api.auth_dep import get_service_client
from integrations.backend.services.linkedin_worker import LinkedInWorker
from core.backend.services.telemetry import capture_error, emit_heartbeat
from accounts.backend.services.account_auto_heal_service import probe_proxy_health
from core.backend.services.proxy_routing import format_proxy_url, find_sticky_failover_proxy, quarantine_proxy, is_proxy_quarantined

logger = logging.getLogger(__name__)

def _try_proxy_failover(supabase, acc: dict, cookies_json: str, country_code: str = None) -> bool:
    """
    Paranoia Layer 0 & 1: Safely attempts proxy failover on network transport failure.
    - Scoped strictly to account's workspace or shared system pool.
    - Preserves geo-country affinity.
    - Probes candidate proxy health neutrally BEFORE attempting session use.
    - NEVER degrades a candidate proxy due to session cookie failures.
    """
    workspace_id = acc.get("workspace_id")
    current_proxy_id = acc.get("proxy_id")
    acc_id = acc["id"]

    replacement = find_sticky_failover_proxy(
        supabase,
        workspace_id=workspace_id,
        current_proxy_id=current_proxy_id,
        target_country=country_code,
        allow_cross_country_drift=False
    )

    if not replacement:
        logger.warning(f"No alternative failover proxies available in {country_code or 'workspace'} for account {acc_id}")
        return False

    # Paranoia Layer 1: Verify replacement proxy neutrally before attaching
    probe_res = probe_proxy_health(replacement, supabase=supabase, timeout_seconds=3.0)
    if not probe_res.get("ok"):
        fail_status = probe_res.get("status") or "degraded"
        logger.warning(f"Replacement proxy {replacement.get('id')} failed neutral probe ({fail_status}): {probe_res.get('error')}")
        supabase.table("proxies").update({
            "status": fail_status,
            "is_active": False,
            "last_checked_at": datetime.utcnow().isoformat()
        }).eq("id", replacement["id"]).execute()
        return False

    # Paranoia Layer 1: Degrade failing current proxy so it is not immediately re-routed to
    if current_proxy_id:
        try:
            supabase.table("proxies").update({
                "status": "degraded",
                "is_active": False,
                "last_checked_at": datetime.utcnow().isoformat()
            }).eq("id", current_proxy_id).execute()
        except Exception as cur_p_err:
            logger.debug(f"Failed to mark failing proxy {current_proxy_id} degraded: {cur_p_err}")

    # Decrypt replacement password if present
    password_plain = ""
    if replacement.get("username"):
        try:
            rpc_res = supabase.rpc("get_decrypted_proxy_payload", {"p_proxy_id": replacement['id']}).execute()
            if rpc_res.data and rpc_res.data.get("password_encrypted"):
                from core.backend.core import crypto
                import base64
                raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                dek_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt failover proxy {replacement['id']}: {e}")

    proxy_url = format_proxy_url(
        replacement.get("protocol", "http"),
        replacement["host"],
        replacement["port"],
        replacement.get("username"),
        password_plain if password_plain else None
    )

    logger.info(f"Trying failover proxy {replacement['host']} for account {acc_id}...")
    try:
        worker = LinkedInWorker(
            cookies_json=cookies_json,
            proxy_url=proxy_url,
            account_id=acc_id,
            country_code=replacement.get("country_code")
        )
        resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
        if resp.status_code == 200:
            logger.info(f"Proxy failover SUCCESS: account {acc_id} now using proxy {replacement['host']}")
            supabase.table("accounts").update({
                "proxy_id": replacement["id"],
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", acc_id).execute()
            return True
        else:
            logger.warning(f"Session probe on failover proxy returned status {resp.status_code}. Proxy {replacement['id']} remains healthy; account requires review.")
            return False
    except Exception as e:
        capture_error(e, context={"service": "health_check_cron", "message": f"Proxy failover probe error: {e}"})
        return False

def run_health_checks(supabase: Optional[Client] = None):
    """
    Cron job to ping LinkedIn for all ACTIVE accounts.
    If an account cookie is dead:
      1. Marks account as DISCONNECTED.
      2. Pauses any ACTIVE campaigns using that account.
    """
    logger.info("Starting LinkedIn session health checks and auto-cooling...")
    if supabase is None:
        supabase = get_service_client()
    
    # Run auto-cooling and proxy recovery first
    try:
        from core.backend.services.auto_cooling import resume_cooled_accounts, probe_and_recover_degraded_proxies
        resumed = resume_cooled_accounts(supabase)
        recovered = probe_and_recover_degraded_proxies(supabase)
        if resumed or recovered:
            logger.info(f"[AutoCooling/ProxyRecovery] Resumed {len(resumed)} accounts and recovered {len(recovered)} proxies.")
    except Exception as e:
        logger.error(f"[AutoCooling/ProxyRecovery] Error running auto-cooling or proxy recovery: {e}")
    
    # 1. Fetch stalest active accounts (Bounded batching: 50 accounts per cycle to scale to 10,000 customers without starvation)
    try:
        res = supabase.table("accounts").select(
            "id, name, session_cookies_encrypted, proxy_id, workspace_id, execution_channel, last_health_check_at"
        ).eq("status", "ACTIVE").order("last_health_check_at", desc=False).limit(50).execute()
    except Exception:
        res = supabase.table("accounts").select(
            "id, name, session_cookies_encrypted, proxy_id, workspace_id"
        ).eq("status", "ACTIVE").limit(50).execute()
    
    accounts = res.data or []
    if not accounts:
        logger.info("No active accounts to check.")
        return

    logger.info(f"Found {len(accounts)} active accounts. Pinging LinkedIn...")

    # Phase R: Autonomous Mailbox Reputation & Graceful Pausing Evaluation
    try:
        from accounts.backend.services.account_auto_heal_service import evaluate_and_gracefully_pause_mailbox
        for acc in accounts:
            ws_id = acc.get("workspace_id") or ""
            evaluate_and_gracefully_pause_mailbox(acc["id"], ws_id, supabase=supabase)
    except Exception as e:
        logger.debug(f"[AutoHealMailbox] Error evaluating mailboxes: {e}")

    # Fetch proxies to build map
    proxy_ids = [acc["proxy_id"] for acc in accounts if acc.get("proxy_id")]
    proxy_map = {}
    if proxy_ids:
        proxies_res = supabase.table("proxies").select("id, host, port, username, protocol, status, country_code").in_("id", proxy_ids).execute()
        proxy_map = {proxy["id"]: proxy for proxy in (proxies_res.data or [])}

    for acc in accounts:
        acc_id = acc["id"]
        acc_name = acc["name"]

        # Paranoia Layer 0 & 1: Extension accounts execute locally from the user's browser.
        # Do NOT ping LinkedIn from the cloud server's datacenter IP to prevent location checkpoints.
        if acc.get("execution_channel") == "EXTENSION":
            logger.info(f"Skipping server-side HTTP ping for account {acc_name}: execution_channel is EXTENSION.")
            try:
                supabase.table("accounts").update({
                    "last_health_check_at": datetime.utcnow().isoformat()
                }).eq("id", acc_id).execute()
            except Exception:
                pass
            continue

        encrypted_cookies = acc.get("session_cookies_encrypted")
        cookies_json = ""
        try:
            from core.backend.core import crypto
            rpc_res = supabase.rpc("get_decrypted_account_payload", {"p_account_id": acc_id}).execute()
            dek_bytes = None
            if rpc_res.data and rpc_res.data.get("dek"):
                import base64
                dek_bytes = base64.b64decode(rpc_res.data["dek"])
            raw_bytes = crypto.pg_hex_to_bytes(encrypted_cookies) if isinstance(encrypted_cookies, str) else encrypted_cookies
            cookies_json = crypto.decrypt_bytes(raw_bytes, dek=dek_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decrypt cookies for account {acc_id}: {e}")
            continue
        proxy_id = acc.get("proxy_id")
        
        proxy_url = None
        if proxy_id and proxy_id in proxy_map:
            p = proxy_map[proxy_id]
            protocol = p.get("protocol", "http")
            host = p.get("host")
            port = p.get("port")
            username = p.get("username")
            password_plain = ""
            if username:
                try:
                    rpc_res = supabase.rpc("get_decrypted_proxy_payload", {"p_proxy_id": proxy_id}).execute()
                    if rpc_res.data and rpc_res.data.get("password_encrypted"):
                        from core.backend.core import crypto
                        import base64
                        raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                        dek_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                        password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode('utf-8')
                except Exception as e:
                    logger.error(f"Failed to decrypt proxy {proxy_id}: {e}")
                proxy_url = format_proxy_url(protocol, host, port, username, password_plain if password_plain else None)
            else:
                proxy_url = format_proxy_url(protocol, host, port)
        
        if not cookies_json:
            logger.error(f"Account {acc_id} has no cookies. Marking DISCONNECTED.")
            _disconnect_account(supabase, acc_id, acc_name, acc.get('workspace_id'))
            continue

        # Paranoia Layer 1: Channel Mutex (Eradicates FLAW-03 - Dual-IP Flapping)
        from core.backend.services.impossible_travel_guard import should_mute_cloud_execution
        should_mute, mute_reason = should_mute_cloud_execution(acc)
        if should_mute:
            logger.info(f"[HealthCheckCron] Muting cloud health probe for account {acc_id}: {mute_reason}")
            continue
            
        # 2. Ping LinkedIn with status code awareness (Paranoia Layer 0: Decouple cookie auth from proxy health)
        worker = LinkedInWorker(
            cookies_json=cookies_json,
            proxy_url=proxy_url,
            account_id=acc_id,
            country_code=proxy_map.get(proxy_id, {}).get("country_code") if proxy_id else None
        )
        status_code = 0
        try:
            resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
            status_code = resp.status_code
        except Exception as e:
            capture_error(e, context={"service": "health_check_cron", "account_id": acc_id})

        if status_code == 401:
            # PURE COOKIE EXPIRY: Account is logged out / expired. Proxy is innocent!
            logger.warning(f"Account {acc_name} cookies expired (HTTP 401). Disconnecting account. Proxies remain intact.")
            _disconnect_account(supabase, acc_id, acc_name, acc.get('workspace_id'))
            continue
        elif status_code in (403, 999):
            logger.warning(f"Account {acc_name} encountered LinkedIn anti-bot/challenge ({status_code}).")
            if proxy_id:
                quarantine_proxy(supabase, proxy_id, reason="linkedin_challenge_999", cooldown_hours=24)
            supabase.table("accounts").update({
                "status": "CHALLENGE_REQUIRED",
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", acc_id).execute()
            continue

        is_valid = (status_code == 200)

        if is_valid:
            logger.info(f"Account {acc_name} ({acc_id}) session is VALID.")
            try:
                today_str = datetime.utcnow().date().isoformat()
                mc_res = supabase.table("account_daily_action_counts").select("count").eq("account_id", acc_id).eq("action_type", "connection_request").eq("usage_date", today_str).execute()
                machine_sent_today = mc_res.data[0]["count"] if mc_res.data else 0
                
                log_res = supabase.table("action_log").select("id", count="exact").eq("account_id", acc_id).ilike("action_type", "%connection%").gte("executed_at", today_str).execute()
                logged_actions_today = log_res.count if hasattr(log_res, 'count') and log_res.count is not None else len(log_res.data)
                
                if machine_sent_today >= 5 and logged_actions_today > machine_sent_today * 1.3:
                    logger.warning(f"[ANOMALY] Account {acc_id} shows possible manual sending: machine_sent={machine_sent_today}, logged={logged_actions_today}")
                    try:
                        supabase.table("accounts").update({
                            "manual_send_suspected": True,
                            "manual_send_suspected_at": datetime.utcnow().isoformat(),
                            "status": "MANUAL_MODE",
                            "updated_at": datetime.utcnow().isoformat()
                        }).eq("id", acc_id).execute()
                        
                        ws_id = acc.get("workspace_id")
                        # Log to audit trail
                        supabase.table("action_log").insert({
                            "workspace_id": ws_id,
                            "account_id": acc_id,
                            "action_type": "activity_check",
                            "result": "warn",
                            "metadata": {"machine_sent": machine_sent_today, "logged": logged_actions_today},
                            "error_detail": f"Automated campaigns paused for account: manual LinkedIn activity detected.",
                            "executed_at": datetime.utcnow().isoformat()
                        }).execute()
                        
                        # PARANOIA LAYER 2: Ensure users are visibly notified via dispatch_notification
                        from core.backend.services.notification_service import dispatch_notification
                        today_key = datetime.utcnow().date().isoformat()
                        dispatch_notification(
                            svc=supabase,
                            workspace_id=ws_id,
                            event_type="account_needs_attention",
                            payload={
                                "account_id": acc_id,
                                "title": "Account Paused: Manual Sending Detected",
                                "body": f"LinkedIn account {acc_name} was paused because manual messaging was detected outside of the system. This prevents ban risks.",
                                "link": "/elein/accounts",
                                "unique_key": f"manual_send:{acc_id}:{today_key}"
                            }
                        )
                    except Exception as inner_e:
                        capture_error(inner_e, context={"service": "health_check_cron"})
            except Exception as e:
                capture_error(e, context={"service": "health_check_cron"})

            supabase.table("accounts").update({
                "last_health_check_at": datetime.utcnow().isoformat()
            }).eq("id", acc_id).execute()
        else:
            logger.warning(f"Account {acc_name} network transport failed. Attempting proxy failover...")
            country = proxy_map.get(proxy_id, {}).get("country_code") if proxy_id else None
            recovered = _try_proxy_failover(supabase, acc, cookies_json, country_code=country)
            if not recovered:
                logger.warning(f"All proxies exhausted or down for {acc_name}. Marking NEEDS_ATTENTION.")
                supabase.table("accounts").update({
                    "status": "NEEDS_ATTENTION",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", acc_id).execute()
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
                "subject": f"Action Required: LinkedIn Account Disconnected",
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
    
    # c. Paranoia Layer 1 & 2: Targeted indexed lookup.
    # Never loop through all campaigns across all tenants (O(N^2) scale collapse at 10,000 customers).
    # Query ONLY campaigns that explicitly link this account_id.
    try:
        camp_links = supabase.table("campaign_accounts").select("campaign_id").eq("account_id", acc_id).execute()
        linked_campaign_ids = [r["campaign_id"] for r in (camp_links.data or []) if r.get("campaign_id")]
        
        if linked_campaign_ids:
            active_camps = supabase.table("campaigns").select("id, name").in_("id", linked_campaign_ids).eq("status", "ACTIVE").execute()
            for camp in (active_camps.data or []):
                # Check if there are any remaining ACTIVE senders for this specific campaign
                camp_senders_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", camp["id"]).execute()
                all_senders = [r["account_id"] for r in (camp_senders_res.data or []) if r.get("account_id")]
                
                if all_senders:
                    active_senders = supabase.table("accounts").select("id").in_("id", all_senders).eq("status", "ACTIVE").execute()
                    if not (active_senders.data or []):
                        logger.warning(f"Pausing Campaign '{camp['name']}' ({camp['id']}) because ALL senders disconnected.")
                        supabase.table("campaigns").update({
                            "status": "PAUSED",
                            "updated_at": datetime.utcnow().isoformat()
                        }).eq("id", camp["id"]).execute()
                    else:
                        logger.info(f"Campaign '{camp['name']}' continues using {len(active_senders.data)} remaining active senders.")
    except Exception as camp_pause_err:
        logger.error(f"Error checking active campaigns for disconnected account {acc_id}: {camp_pause_err}")

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
