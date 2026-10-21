import json
import logging
from datetime import datetime, timedelta, timezone

from typing import Optional, List, Dict, Any, Tuple
from supabase import Client
from core.backend.core import crypto
from integrations.backend.services.linkedin_worker import LinkedInWorker

logger = logging.getLogger(__name__)

def get_next_check_interval(account: dict, recent_checks: list) -> int:
    """Returns seconds until next check. Risk-scaled: 2 hours if warmup or recent fails, 24 hours if stable."""
    if account.get('is_warmup') or any(c.get('result') == 'fail' for c in recent_checks):
        return 2 * 60 * 60  # 2 hours
    return 24 * 60 * 60  # 24 hours

def check_session_validity(account_id: str, cookies_json: str, proxy_url: Optional[str] = None) -> dict:
    """Returns {check_type: 'session_valid', result: 'pass'|'warn'|'fail', detail: {}}"""
    try:
        if proxy_url:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=proxy_url, account_id=account_id)
        else:
            worker = LinkedInWorker(cookies_json=cookies_json, account_id=account_id)
        resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
        if resp.status_code == 200:
            return {'check_type': 'session_valid', 'result': 'pass', 'detail': {'status_code': 200}}
        elif resp.status_code == 401:
            return {'check_type': 'session_valid', 'result': 'fail', 'detail': {'status_code': 401, 'message': 'Session expired'}}
        elif resp.status_code == 999:
            return {'check_type': 'session_valid', 'result': 'fail', 'detail': {'status_code': 999, 'message': 'Bot detection / 999'}}
        else:
            return {'check_type': 'session_valid', 'result': 'warn', 'detail': {'status_code': resp.status_code}}
    except Exception as e:
        return {'check_type': 'session_valid', 'result': 'fail', 'detail': {'error': str(e)}}

def check_cookie_freshness(account: dict) -> dict:
    """Returns warn if cookie_expires_at is within 7 days, fail if expired"""
    expires_at_str = account.get('cookie_expires_at')
    if not expires_at_str:
        return {'check_type': 'cookie_freshness', 'result': 'warn', 'detail': {'message': 'No expiry date found'}}
    
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if expires_at < now:
            return {'check_type': 'cookie_freshness', 'result': 'fail', 'detail': {'message': 'Cookie expired'}}
        elif expires_at < now + timedelta(days=7):
            return {'check_type': 'cookie_freshness', 'result': 'warn', 'detail': {'message': 'Cookie expires within 7 days'}}
        return {'check_type': 'cookie_freshness', 'result': 'pass', 'detail': {'message': 'Cookie fresh'}}
    except Exception as e:
        return {'check_type': 'cookie_freshness', 'result': 'warn', 'detail': {'error': str(e)}}

def check_profile_reachable(cookies_json: str, linkedin_profile_url: str, account_id: str = "health_check", proxy_url: Optional[str] = None) -> dict:
    """Fetches the profile page and checks for restriction interstitials"""
    if not linkedin_profile_url:
        return {'check_type': 'profile_reachable', 'result': 'pass', 'detail': {'message': 'No profile url to check'}}
    
    try:
        if proxy_url:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=proxy_url, account_id=account_id)
        else:
            worker = LinkedInWorker(cookies_json=cookies_json, account_id=account_id)
        resp = worker._http_get(linkedin_profile_url)
        if resp.status_code == 200:
            html = resp.text
            if "checkpoint/challenge" in html or "restricted" in html.lower():
                return {'check_type': 'profile_reachable', 'result': 'fail', 'detail': {'message': 'Restriction found'}}
            return {'check_type': 'profile_reachable', 'result': 'pass', 'detail': {'status_code': 200}}
        else:
             return {'check_type': 'profile_reachable', 'result': 'warn', 'detail': {'status_code': resp.status_code}}
    except Exception as e:
        return {'check_type': 'profile_reachable', 'result': 'fail', 'detail': {'error': str(e)}}

def check_for_restriction_signals(cookies_json: str, account_id: str = "health_check", proxy_url: Optional[str] = None) -> dict:
    """Checks for LinkedIn checkpoint/restriction page patterns"""
    try:
        if proxy_url:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=proxy_url, account_id=account_id)
        else:
            worker = LinkedInWorker(cookies_json=cookies_json, account_id=account_id)
        resp = worker._http_get("https://www.linkedin.com/feed/")
        if resp.status_code == 200:
            html = resp.text
            if "checkpoint/challenge" in html or "restriction" in html.lower():
                return {'check_type': 'restriction_signals', 'result': 'fail', 'detail': {'message': 'Restriction found on feed'}}
            return {'check_type': 'restriction_signals', 'result': 'pass', 'detail': {}}
        return {'check_type': 'restriction_signals', 'result': 'warn', 'detail': {'status_code': resp.status_code}}
    except Exception as e:
        return {'check_type': 'restriction_signals', 'result': 'fail', 'detail': {'error': str(e)}}

def run_health_check(supabase: Client, account_id: str, workspace_id: str) -> dict:
    """Main entry point. Runs all checks, writes to account_health_checks, updates account.status if needed."""
    acc_res = supabase.table("accounts").select("*").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise ValueError("Account not found")
    account = acc_res.data[0]

    raw = account.get("session_cookies_encrypted")
    if not raw:
        return {"error": "No cookies found"}
        
    dek_bytes = None
    cookie_secret_ref = account.get("cookie_secret_ref")
    
    if cookie_secret_ref:
        try:
            rpc_res = supabase.rpc("get_decrypted_account_payload", {"p_account_id": account_id}).execute()
            if rpc_res.data and rpc_res.data.get("dek"):
                import base64
                dek_bytes = base64.b64decode(rpc_res.data["dek"])
        except Exception as e:
            logger.error(f"Failed to fetch DEK from Vault: {e}")
            
    try:
        raw_bytes = crypto.pg_hex_to_bytes(raw) if isinstance(raw, str) else raw
        decrypted = crypto.decrypt_bytes(raw_bytes, dek=dek_bytes)
        cookies_json = decrypted.decode("utf-8")
    except (crypto.VaultDecryptionError, Exception) as e:
        logger.error(f"Account {account_id} decryption failed. Needs attention.")
        
        # Safe logging, no secrets
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("account_health_checks").insert({
            "account_id": account_id,
            "check_type": "decryption",
            "result": "fail",
            "detail": {"message": "Decryption Failed / Corrupted"},
            "checked_at": now
        }).execute()
        
        supabase.table("accounts").update({
            "status": "NEEDS_ATTENTION",
            "session_locked_until": None,
            "last_health_check_at": now
        }).eq("id", account_id).execute()
        
        if dek_bytes:
            del dek_bytes
            
        return {"error": "Failed to decrypt cookies", "new_status": "NEEDS_ATTENTION"}
    
    if dek_bytes:
        del dek_bytes
        
    if not cookies_json:
        return {"error": "Failed to decrypt cookies"}

    recent_checks_res = supabase.table("account_health_checks").select("result").eq("account_id", account_id).order("checked_at", desc=True).limit(5).execute()
    recent_checks = recent_checks_res.data or []

    # Paranoia Layer 1: Resolve proxy before running health checks to avoid leaking bare datacenter IP
    proxy_id = account.get("proxy_id")
    active_proxy_url = None
    proxy_warn = None

    if proxy_id:
        try:
            px_res = supabase.table("proxies").select("*").eq("id", proxy_id).execute()
            if px_res.data:
                current_proxy = px_res.data[0]
                from core.backend.services.proxy_routing import is_proxy_quarantined, find_sticky_failover_proxy
                
                # Check if proxy is quarantined or inactive
                if is_proxy_quarantined(current_proxy) or not current_proxy.get("is_active", True) or current_proxy.get("status") in ("degraded", "banned", "disabled", "quarantined"):
                    # Attempt sticky failover
                    target_country = account.get("country_code") or current_proxy.get("country_code")
                    replacement = find_sticky_failover_proxy(
                        supabase,
                        workspace_id,
                        current_proxy_id=proxy_id,
                        target_country=target_country
                    )
                    if replacement:
                        current_proxy = replacement
                        proxy_id = replacement["id"]
                        account["proxy_id"] = proxy_id
                        account["proxies"] = replacement
                        try:
                            supabase.table("accounts").update({"proxy_id": proxy_id}).eq("id", account_id).execute()
                        except Exception as update_err:
                            logger.warning(f"Could not persist proxy failover to account: {update_err}")
                        logger.info(f"Health check proxy failover: switched account {account_id} to proxy {proxy_id}")
                    else:
                        proxy_warn = "Assigned proxy is inactive or quarantined, and no healthy replacement proxy is available. Direct connection blocked to protect account from datacenter IP detection."

                if not proxy_warn:
                    pwd = ""
                    if current_proxy.get("username"):
                        try:
                            rpc_res = supabase.rpc("get_decrypted_proxy_payload", {"p_proxy_id": proxy_id}).execute()
                            if rpc_res.data and rpc_res.data.get("password_encrypted"):
                                import base64
                                raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                                d_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                                pwd = crypto.decrypt_bytes(raw_encrypted, dek=d_bytes).decode("utf-8")
                        except Exception as dec_err:
                            logger.warning(f"Could not decrypt proxy password for {proxy_id}: {dec_err}")
                    
                    proto = current_proxy.get("protocol", "http")
                    if current_proxy.get("username") and pwd:
                        active_proxy_url = f"{proto}://{current_proxy['username']}:{pwd}@{current_proxy['host']}:{current_proxy['port']}"
                    else:
                        active_proxy_url = f"{proto}://{current_proxy['host']}:{current_proxy['port']}"
            else:
                proxy_warn = f"Assigned proxy {proxy_id} not found in database. Direct connection blocked."
        except Exception as e:
            logger.error(f"Error resolving proxy {proxy_id} for account {account_id}: {e}")
            proxy_warn = f"Failed to resolve proxy: {str(e)}"

    if proxy_warn:
        now = datetime.now(timezone.utc).isoformat()
        proxy_res = {
            "check_type": "proxy_availability",
            "result": "warn",
            "detail": {"message": proxy_warn}
        }
        supabase.table("account_health_checks").insert({
            "account_id": account_id,
            "check_type": "proxy_availability",
            "result": "warn",
            "detail": {"message": proxy_warn},
            "checked_at": now
        }).execute()
        
        results = [
            proxy_res,
            check_cookie_freshness(account)
        ]
        supabase.table("accounts").update({
            "last_health_check_at": now
        }).eq("id", account_id).execute()
        
        return {
            "account_id": account_id,
            "checked_at": now,
            "results": results,
            "new_status": account.get("status")
        }

    # Run checks
    if active_proxy_url:
        results = [
            check_session_validity(account_id, cookies_json, proxy_url=active_proxy_url),
            check_cookie_freshness(account),
            check_profile_reachable(cookies_json, account.get("linkedin_profile_url", ""), account_id=account_id, proxy_url=active_proxy_url),
            check_for_restriction_signals(cookies_json, account_id=account_id, proxy_url=active_proxy_url)
        ]
    else:
        results = [
            check_session_validity(account_id, cookies_json),
            check_cookie_freshness(account),
            check_profile_reachable(cookies_json, account.get("linkedin_profile_url", ""), account_id=account_id),
            check_for_restriction_signals(cookies_json, account_id=account_id)
        ]

    has_fail = any(r["result"] == "fail" for r in results)
    
    # Store results
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        supabase.table("account_health_checks").insert({
            "account_id": account_id,
            "check_type": r["check_type"],
            "result": r["result"],
            "detail": r.get("detail", {}),
            "checked_at": now
        }).execute()

    # Compute overall status
    new_status = account.get("status")
    if has_fail and new_status == "ACTIVE":
        new_status = "NEEDS_ATTENTION"

    supabase.table("accounts").update({
        "last_health_check_at": now,
        "status": new_status
    }).eq("id", account_id).execute()

    return {
        "account_id": account_id,
        "checked_at": now,
        "results": results,
        "new_status": new_status
    }

def compute_safety_indicator(account: dict, recent_checks: list) -> str:
    """Computed at read time only (never stored). Returns 'critical'|'warning'|'watch'|'healthy'"""
    if account.get('manual_send_suspected'): return 'critical'
    if account.get('status') == 'SUSPENDED': return 'critical'
    if account.get('status') == 'NEEDS_ATTENTION': return 'warning'
    if any(c.get('result') == 'fail' for c in recent_checks[-5:]): return 'warning'
    # If today_usage > 90% of limit: 'watch'
    # Simplified logic as requested
    return 'healthy'
