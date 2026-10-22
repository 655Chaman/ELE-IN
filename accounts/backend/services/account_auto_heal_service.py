import json
import logging
import time
import base64
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import httpx

from supabase import Client
from core.backend.core import crypto
from integrations.backend.services.linkedin_worker import LinkedInWorker, SecurityChallengeError

logger = logging.getLogger(__name__)

# ── CONCURRENCY & PARANOIA LATCH GUARD ────────────────────────────────────────
_heal_locks_mutex = threading.Lock()
_active_heals: Dict[str, float] = {}  # account_id -> start_timestamp
AUTO_HEAL_LOCK_TIMEOUT_SECONDS = 300  # 5 minutes
MAX_AUTO_HEAL_ATTEMPTS_PER_24H = 3


# ── LAYER 1 PARANOIA: PROXY PROBE WITH STRICT TIMEOUTS ────────────────────────

def probe_proxy_health(
    proxy: dict,
    supabase: Optional[Client] = None,
    timeout_seconds: float = 5.0
) -> Dict[str, Any]:
    """
    Probes proxy connectivity and measures latency in milliseconds.
    Three-Layer Paranoia:
      - Layer 0: Sends HTTP GET via proxy, measures elapsed time, detects exit IP.
      - Layer 1: 5.0s hard socket timeout, handles DNS failure, SSL errors, proxy auth failure.
      - Layer 2: Sanitizes inputs and formats proxy URL safely.
    """
    if proxy.get("status") == "quarantined" or proxy.get("quarantined_until"):
        from core.backend.services.proxy_routing import is_proxy_quarantined
        if is_proxy_quarantined(proxy):
            return {
                "ok": False,
                "latency_ms": 5000,
                "status": "quarantined",
                "exit_ip": None,
                "country_code": proxy.get("country_code"),
                "error": f"Proxy is quarantined: {proxy.get('quarantine_reason', 'security cooldown')}"
            }

    host = (proxy.get("host") or "").strip()
    port = proxy.get("port")
    protocol = (proxy.get("protocol") or "http").lower().strip()
    username = proxy.get("username")
    proxy_id = proxy.get("id")

    if not host or not port:
        return {
            "ok": False,
            "latency_ms": 5000,
            "status": "failed",
            "exit_ip": None,
            "country_code": proxy.get("country_code"),
            "error": "Missing host or port in proxy configuration"
        }

    # Resolve plaintext password if encrypted
    password_plain = ""
    if username and proxy_id:
        try:
            from core.backend.api.auth_dep import get_service_client
            svc = get_service_client() or supabase
            rpc_payload = {"p_proxy_id": proxy_id}
            p_ws = proxy.get("workspace_id")
            if p_ws:
                rpc_payload["p_workspace_id"] = p_ws
            rpc_res = svc.rpc("get_decrypted_proxy_payload", rpc_payload).execute()
            if rpc_res.data and rpc_res.data.get("password_encrypted"):
                raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                dek_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Could not decrypt password for proxy {proxy_id}: {e}")

    # Build proxy URL
    if username and password_plain:
        proxy_url = f"{protocol}://{username}:{password_plain}@{host}:{port}"
    elif username and proxy.get("password"):
        proxy_url = f"{protocol}://{username}:{proxy['password']}@{host}:{port}"
    else:
        proxy_url = f"{protocol}://{host}:{port}"

    start_time = time.perf_counter()
    exit_ip = None
    detected_country = proxy.get("country_code")

    try:
        mounts = {"all://": httpx.HTTPTransport(proxy=proxy_url)}
        with httpx.Client(mounts=mounts, timeout=timeout_seconds, follow_redirects=True) as client:
            # First probe: LinkedIn robots.txt (fast, lightweight, domain-aligned)
            probe_resp = client.get("https://www.linkedin.com/robots.txt")
            elapsed = time.perf_counter() - start_time
            latency_ms = max(1, int(elapsed * 1000))

            if probe_resp.status_code in (200, 301, 302):
                if latency_ms > 2500:
                    status = "degraded"
                    err_msg = f"High latency detected ({latency_ms}ms > 2500ms). Proxy may cause timeouts."
                elif latency_ms < 800:
                    status = "healthy"
                    err_msg = None
                else:
                    status = "degraded"
                    err_msg = None
                
                try:
                    ip_resp = client.get("https://api.ipify.org?format=json", timeout=2.0)
                    if ip_resp.status_code == 200:
                        exit_ip = ip_resp.json().get("ip")
                except Exception:
                    pass

                result = {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "status": status,
                    "exit_ip": exit_ip or host,
                    "country_code": detected_country,
                    "error": err_msg
                }
            elif probe_resp.status_code in (403, 999):
                # Paranoia Layer 1: Treat anti-bot challenge codes as banned, not healthy
                result = {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "status": "banned",
                    "exit_ip": exit_ip or host,
                    "country_code": detected_country,
                    "error": f"LinkedIn blocked proxy with HTTP {probe_resp.status_code} (Anti-Bot Challenge)"
                }
            else:
                err_msg = f"HTTP status {probe_resp.status_code}"
                if latency_ms > 2500:
                    err_msg = f"High latency detected ({latency_ms}ms > 2500ms). Proxy may cause timeouts."
                result = {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "status": "degraded",
                    "exit_ip": host,
                    "country_code": detected_country,
                    "error": err_msg
                }
    except httpx.ConnectTimeout:
        latency_ms = int(timeout_seconds * 1000)
        result = {"ok": False, "latency_ms": latency_ms, "status": "failed", "exit_ip": None, "country_code": detected_country, "error": f"Connection timed out after {timeout_seconds}s"}
    except httpx.ProxyError as pe:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        result = {"ok": False, "latency_ms": latency_ms, "status": "failed", "exit_ip": None, "country_code": detected_country, "error": f"Proxy authentication or connection error: {pe}"}
    except Exception as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        result = {"ok": False, "latency_ms": latency_ms, "status": "failed", "exit_ip": None, "country_code": detected_country, "error": str(e)}

    if supabase and proxy_id:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            update_payload: Dict[str, Any] = {
                "status": result["status"],
                "last_checked_at": now_iso
            }
            try:
                update_payload["latency_ms"] = result["latency_ms"]
                if result.get("exit_ip"):
                    update_payload["exit_ip"] = result["exit_ip"]
                supabase.table("proxies").update(update_payload).eq("id", proxy_id).execute()
            except Exception:
                supabase.table("proxies").update({
                    "status": result["status"],
                    "last_checked_at": now_iso
                }).eq("id", proxy_id).execute()
        except Exception as db_err:
            logger.warning(f"Failed to update proxy status in DB: {db_err}")

    return result


# ── COMPOSITE HEALTH SCORE ENGINE ─────────────────────────────────────────────

def calculate_composite_health_score(
    session_valid: bool,
    proxy_latency_ms: Optional[int],
    cookie_expires_at_str: Optional[str],
    status: str
) -> int:
    score = 0
    if session_valid:
        score += 40

    if proxy_latency_ms is not None:
        if proxy_latency_ms < 250:
            score += 30
        elif proxy_latency_ms < 600:
            score += 22
        elif proxy_latency_ms < 1200:
            score += 14
        elif proxy_latency_ms < 3000:
            score += 5
    else:
        score += 15

    if cookie_expires_at_str:
        try:
            exp = datetime.fromisoformat(cookie_expires_at_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_remaining = (exp - now).total_seconds() / 86400.0
            if days_remaining > 14:
                score += 20
            elif days_remaining > 7:
                score += 15
            elif days_remaining > 2:
                score += 8
            elif days_remaining > 0:
                score += 3
        except Exception:
            score += 10
    else:
        score += 10

    if status == "ACTIVE":
        score += 10
    elif status == "MANUAL_MODE":
        score += 7
    elif status == "RATE_LIMITED":
        score += 3
    else:
        score += 0

    return min(100, max(0, score))


# ── PROXY RESOLUTION HELPER ───────────────────────────────────────────────────

def _build_account_proxy_url(acc: dict, supabase: Client) -> Optional[str]:
    proxy_id = acc.get("proxy_id")
    if not proxy_id:
        return None
    try:
        p_res = supabase.table("proxies").select("id, host, port, protocol, username, password, password_encrypted, workspace_id").eq("id", proxy_id).execute()
        if not p_res.data:
            return None
        proxy = p_res.data[0]
        acc_ws = acc.get("workspace_id")
        p_ws = proxy.get("workspace_id")
        if acc_ws and p_ws and str(acc_ws).strip() != str(p_ws).strip():
            logger.warning(f"Proxy {proxy_id} workspace {p_ws} does not match account workspace {acc_ws}")
            return None
        
        password_plain = ""
        username = proxy.get("username")
        if username:
            if proxy.get("password_encrypted"):
                try:
                    rpc_res = supabase.rpc("get_decrypted_proxy_payload", {"p_proxy_id": proxy_id, "p_workspace_id": p_ws}).execute()
                    if rpc_res.data and rpc_res.data.get("password_encrypted"):
                        raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                        dek_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                        password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode("utf-8")
                except Exception as e:
                    logger.warning(f"Could not decrypt proxy password for {proxy_id}: {e}")
            elif proxy.get("password"):
                password_plain = proxy["password"]

        protocol = (proxy.get("protocol") or "http").lower().strip()
        host = proxy.get("host")
        port = proxy.get("port")
        if not host or not port:
            return None
        auth = f"{username}:{password_plain}@" if username and password_plain else f"{username}@" if username else ""
        return f"{protocol}://{auth}{host}:{port}"
    except Exception as e:
        logger.error(f"Failed to build proxy url for proxy {proxy_id}: {e}")
        return None


# ── AUTONOMOUS SINGLE-ACCOUNT AUTO-HEAL ───────────────────────────────────────

def auto_heal_account(
    account_id: str,
    workspace_id: str,
    supabase: Client,
    force: bool = False
) -> Dict[str, Any]:
    """
    Main diagnostic and auto-healing workflow for a LinkedIn account with concurrency and challenge guards.
    """
    now_t = time.time()
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    with _heal_locks_mutex:
        if account_id in _active_heals:
            lock_age = now_t - _active_heals[account_id]
            if lock_age < AUTO_HEAL_LOCK_TIMEOUT_SECONDS:
                return {
                    "account_id": account_id,
                    "healed": False,
                    "locked": True,
                    "actions_taken": ["Auto-heal skipped: Another auto-heal operation is currently in progress for this account."],
                    "recommendation": "LOCKED_IN_PROGRESS",
                    "timestamp": now_iso
                }
        _active_heals[account_id] = now_t

    try:
        actions_taken: List[str] = []
        
        # 1. Fetch account
        acc_res = supabase.table("accounts").select("*").eq("id", account_id).eq("workspace_id", workspace_id).execute()
        if not acc_res.data:
            raise ValueError("Account not found or access denied")
        account = acc_res.data[0]
        previous_status = account.get("status", "ACTIVE")
        new_status = previous_status
        healed = False
        recommendation = "ALL_CLEAR"

        # Multi-worker DB lease check
        session_locked_until = account.get("session_locked_until")
        if session_locked_until and not force:
            try:
                locked_dt = datetime.fromisoformat(session_locked_until.replace("Z", "+00:00"))
                if locked_dt > now_utc:
                    return {
                        "account_id": account_id,
                        "healed": False,
                        "locked": True,
                        "actions_taken": ["Auto-heal skipped: Another worker holds an active database lock for this account."],
                        "recommendation": "LOCKED_IN_PROGRESS",
                        "timestamp": now_iso
                    }
            except Exception:
                pass

        # Set database distributed lock for this account
        lock_until_iso = (now_utc + timedelta(seconds=AUTO_HEAL_LOCK_TIMEOUT_SECONDS)).isoformat()
        try:
            supabase.table("accounts").update({"session_locked_until": lock_until_iso}).eq("id", account_id).execute()
        except Exception as lock_err:
            logger.warning(f"Could not set session_locked_until on account {account_id}: {lock_err}")

        # Quarantine & Force handling
        if force:
            if account.get("quarantined_until"):
                try:
                    supabase.table("accounts").update({"quarantined_until": None, "quarantine_reason": None}).eq("id", account_id).execute()
                    account["quarantined_until"] = None
                    account["quarantine_reason"] = None
                    actions_taken.append("Quarantine cleared manually via force=True.")
                except Exception as q_clear_err:
                    logger.warning(f"Could not clear quarantine in DB: {q_clear_err}")
        else:
            q_str = account.get("quarantined_until")
            if q_str:
                try:
                    q_dt = datetime.fromisoformat(q_str.replace("Z", "+00:00"))
                    if now_utc < q_dt:
                        return {
                            "account_id": account_id,
                            "previous_status": account.get("status", "ACTIVE"),
                            "new_status": account.get("status", "ACTIVE"),
                            "healed": False,
                            "quarantined": True,
                            "health_score": account.get("health_score", 10),
                            "actions_taken": [f"Auto-heal rejected: Account is quarantined until {q_str} ({account.get('quarantine_reason', 'challenge cooldown')}). Manual intervention required."],
                            "recommendation": "CHALLENGE_QUARANTINED",
                            "timestamp": now_iso
                        }
                    else:
                        # Quarantine timer expired
                        if account.get("status") == "CHALLENGE_REQUIRED" or account.get("quarantine_reason") in ("security_challenge", "challenge cooldown"):
                            # Layer 1 & 2: Quarantine expired but manual challenge resolution has not been confirmed.
                            # Automated background checks must NOT probe LinkedIn to prevent turning soft checkpoints into hard bans.
                            actions_taken.append("Quarantine cooldown period expired, but account was quarantined for a security challenge. Automated background probes blocked until manual browser login is verified.")
                            return {
                                "account_id": account_id,
                                "previous_status": "CHALLENGE_REQUIRED",
                                "new_status": "NEEDS_ATTENTION",
                                "healed": False,
                                "quarantined": False,
                                "health_score": 20,
                                "actions_taken": actions_taken,
                                "recommendation": "MANUAL_CHALLENGE_RESOLUTION_REQUIRED",
                                "timestamp": now_iso
                            }
                except Exception:
                    pass

            # Rate limit check (max attempts in 24h, filtering out passing routine scans)
            since_24h = (now_utc - timedelta(hours=24)).isoformat()
            try:
                checks_res = (
                    supabase.table("account_health_checks")
                    .select("id, result")
                    .eq("account_id", account_id)
                    .eq("check_type", "auto_heal")
                    .gte("checked_at", since_24h)
                    .execute()
                )
                raw_checks = checks_res.data or []
                attempts_today = len([c for c in raw_checks if c.get("result") != "pass"])
                if attempts_today >= MAX_AUTO_HEAL_ATTEMPTS_PER_24H:
                    return {
                        "account_id": account_id,
                        "previous_status": account.get("status", "ACTIVE"),
                        "new_status": "NEEDS_ATTENTION",
                        "healed": False,
                        "rate_limited": True,
                        "health_score": account.get("health_score", 15),
                        "actions_taken": [f"Auto-heal rate limited: Reached maximum attempts ({attempts_today}/{MAX_AUTO_HEAL_ATTEMPTS_PER_24H} in 24h). Requires manual session renewal."],
                        "recommendation": "MAX_ATTEMPTS_EXCEEDED",
                        "timestamp": now_iso
                    }
            except Exception as count_err:
                logger.warning(f"Could not check 24h auto-heal attempts: {count_err}")

        # 2. Decrypt cookies
        raw_cookies = account.get("session_cookies_encrypted")
        if not raw_cookies:
            return {
                "account_id": account_id,
                "previous_status": previous_status,
                "new_status": "NEEDS_ATTENTION",
                "healed": False,
                "health_score": 10,
                "actions_taken": ["No session cookies configured on account."],
                "recommendation": "RENEWAL_REQUIRED",
                "timestamp": now_iso
            }

        dek_bytes = None
        cookie_secret_ref = account.get("cookie_secret_ref")
        if cookie_secret_ref:
            try:
                rpc_res = supabase.rpc("get_decrypted_account_payload", {"p_account_id": account_id}).execute()
                if rpc_res.data and rpc_res.data.get("dek"):
                    dek_bytes = base64.b64decode(rpc_res.data["dek"])
            except Exception as e:
                logger.warning(f"Could not load DEK for account {account_id}: {e}")

        try:
            raw_bytes = crypto.pg_hex_to_bytes(raw_cookies) if isinstance(raw_cookies, str) else raw_cookies
            decrypted = crypto.decrypt_bytes(raw_bytes, dek=dek_bytes)
            cookies_json = decrypted.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decrypt cookies for account {account_id}: {e}")
            return {
                "account_id": account_id,
                "previous_status": previous_status,
                "new_status": "NEEDS_ATTENTION",
                "healed": False,
                "health_score": 15,
                "actions_taken": [f"Decryption error: {str(e)}"],
                "recommendation": "RENEWAL_REQUIRED",
                "timestamp": now_iso
            }

        # 3. Check and probe assigned proxy
        proxy_id = account.get("proxy_id")
        active_proxy_url = None
        proxy_latency_ms = None
        proxy_status = "none"

        if proxy_id:
            px_res = supabase.table("proxies").select("*").eq("id", proxy_id).execute()
            if px_res.data:
                current_proxy = px_res.data[0]
                probe_res = probe_proxy_health(current_proxy, supabase=supabase)
                proxy_latency_ms = probe_res.get("latency_ms")
                proxy_status = probe_res.get("status")

                if not probe_res.get("ok") or proxy_status in ("failed", "quarantined"):
                    actions_taken.append(f"Assigned proxy {current_proxy.get('host')} failed health check ({probe_res.get('error')}). Initiating auto-rotation.")
                    from core.backend.services.proxy_routing import find_sticky_failover_proxy
                    target_country = current_proxy.get("country_code")
                    replacement = find_sticky_failover_proxy(
                        supabase,
                        workspace_id,
                        current_proxy_id=proxy_id,
                        target_country=target_country
                    )

                    if replacement:
                        rep_probe = probe_proxy_health(replacement, supabase=supabase)
                        if rep_probe.get("ok"):
                            supabase.table("accounts").update({
                                "proxy_id": replacement["id"],
                                "updated_at": now_iso
                            }).eq("id", account_id).execute()
                            proxy_id = replacement["id"]
                            proxy_latency_ms = rep_probe.get("latency_ms")
                            proxy_status = "healthy"
                            actions_taken.append(f"Auto-rotated account to healthy proxy {replacement.get('host')}:{replacement.get('port')} (Latency: {proxy_latency_ms}ms).")
                        else:
                            actions_taken.append(f"Candidate backup proxy {replacement.get('host')} also failed. Falling back to direct connection.")
                    else:
                        actions_taken.append("No healthy backup residential proxies available in workspace pool.")
                else:
                    actions_taken.append(f"Current proxy {current_proxy.get('host')} verified healthy (Latency: {proxy_latency_ms}ms).")

        if proxy_id:
            px_res = supabase.table("proxies").select("*").eq("id", proxy_id).execute()
            if px_res.data:
                px = px_res.data[0]
                pwd = ""
                if px.get("username"):
                    try:
                        from core.backend.api.auth_dep import get_service_client
                        svc = get_service_client() or supabase
                        rpc_payload = {"p_proxy_id": proxy_id}
                        px_ws = px.get("workspace_id") or account.get("workspace_id")
                        if px_ws:
                            rpc_payload["p_workspace_id"] = px_ws
                        rpc_res = svc.rpc("get_decrypted_proxy_payload", rpc_payload).execute()
                        if rpc_res.data and rpc_res.data.get("password_encrypted"):
                            raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                            d_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                            pwd = crypto.decrypt_bytes(raw_encrypted, dek=d_bytes).decode("utf-8")
                    except Exception:
                        pass
                proto = px.get("protocol", "http")
                if px.get("username") and pwd:
                    active_proxy_url = f"{proto}://{px['username']}:{pwd}@{px['host']}:{px['port']}"
                else:
                    active_proxy_url = f"{proto}://{px['host']}:{px['port']}"

        # Paranoia Layer 1: If account is configured to use a proxy, NEVER leak datacenter IP
        if account.get("proxy_id") and not active_proxy_url:
            actions_taken.append("Assigned proxy and all backup candidates are unavailable. Direct connection to LinkedIn blocked to protect account from datacenter IP flag.")
            return {
                "account_id": account_id,
                "previous_status": previous_status,
                "new_status": "NEEDS_ATTENTION",
                "healed": False,
                "health_score": 20,
                "actions_taken": actions_taken,
                "recommendation": "PROXY_FAILURE",
                "timestamp": now_iso
            }

        # 4. Probe LinkedIn Voyager API session with Security Challenge Detection
        session_valid = False
        is_rate_limited = False
        is_challenge = False
        challenge_detail = ""

        try:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=active_proxy_url, account_id=account_id)
            resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
            if resp.status_code == 200:
                resp_text = resp.text or ""
                if "checkpoint/challenge" in resp_text or "security-check" in resp_text:
                    is_challenge = True
                    challenge_detail = "Redirected to LinkedIn security challenge"
                else:
                    session_valid = True
                    actions_taken.append("LinkedIn Voyager API session probe succeeded (HTTP 200 OK).")
            elif resp.status_code == 999:
                is_challenge = True
                challenge_detail = "HTTP 999 anti-bot challenge"
                actions_taken.append("LinkedIn returned HTTP 999 anti-bot challenge.")
            elif resp.status_code == 429:
                is_rate_limited = True
                actions_taken.append("LinkedIn Voyager returned 429 Too Many Requests. Rate limit triggered.")
            elif resp.status_code == 401:
                session_valid = False
                actions_taken.append("LinkedIn Voyager returned 401 Unauthorized. Session has expired or logged out.")
            elif resp.status_code == 403:
                resp_text = resp.text or ""
                if "checkpoint" in resp_text.lower() or "challenge" in resp_text.lower():
                    is_challenge = True
                    challenge_detail = "HTTP 403 checkpoint challenge"
                    actions_taken.append("LinkedIn Voyager returned 403 checkpoint challenge.")
                else:
                    session_valid = False
                    actions_taken.append("LinkedIn Voyager returned 403 Forbidden.")
            else:
                session_valid = False
                actions_taken.append(f"LinkedIn Voyager returned unexpected status code: {resp.status_code}.")
        except SecurityChallengeError as sce:
            is_challenge = True
            challenge_detail = str(sce)
            actions_taken.append(f"SecurityChallengeError caught: {sce}")
        except Exception as e:
            err_lower = str(e).lower()
            if "challenge" in err_lower or "checkpoint" in err_lower or "captcha" in err_lower:
                is_challenge = True
                challenge_detail = str(e)
                actions_taken.append(f"Security challenge in probe: {e}")
            else:
                actions_taken.append(f"Session probe error: {str(e)}")

        # 5. Challenge Resolution & Campaign Quarantine
        if is_challenge:
            new_status = "CHALLENGE_REQUIRED"
            recommendation = "CHALLENGE_QUARANTINED"
            quarantine_until_iso = (now_utc + timedelta(hours=24)).isoformat()
            actions_taken.append(f"CRITICAL: Account entered CHALLENGE_REQUIRED. Quarantined until {quarantine_until_iso} to prevent ban.")
            
            if proxy_id:
                try:
                    from core.backend.services.proxy_routing import quarantine_proxy
                    quarantine_proxy(supabase, proxy_id, reason="account_security_challenge", cooldown_hours=24)
                    actions_taken.append(f"Quarantined proxy {proxy_id} for 24h to prevent cross-account challenge contamination.")
                except Exception as q_err:
                    logger.warning(f"Could not quarantine proxy: {q_err}")
            
            try:
                camp_accs = supabase.table("campaign_accounts").select("campaign_id").eq("account_id", account_id).execute()
                camp_ids = [r["campaign_id"] for r in (camp_accs.data or []) if r.get("campaign_id")]
                if camp_ids:
                    supabase.table("campaigns").update({
                        "status": "PAUSED",
                        "updated_at": now_iso
                    }).in_("id", camp_ids).eq("status", "ACTIVE").execute()
                    actions_taken.append(f"Auto-paused {len(camp_ids)} campaign(s) to protect sender reputation.")
            except Exception as camp_pause_err:
                logger.warning(f"Could not auto-pause campaigns for challenged account: {camp_pause_err}")

            try:
                supabase.table("outbox_events").insert({
                    "workspace_id": workspace_id,
                    "event_type": "account.security_challenge",
                    "payload": {
                        "account_id": account_id,
                        "reason": challenge_detail,
                        "quarantined_until": quarantine_until_iso,
                        "timestamp": now_iso
                    },
                    "status": "pending"
                }).execute()
            except Exception as outbox_err:
                logger.warning(f"Could not queue outbox event: {outbox_err}")
        elif session_valid:
            if previous_status == "CHALLENGE_REQUIRED" and not force:
                new_status = "NEEDS_ATTENTION"
                healed = False
                recommendation = "MANUAL_CHALLENGE_RESOLUTION_REQUIRED"
                actions_taken.append("Account was in CHALLENGE_REQUIRED. Automated background healing blocked from activating account without manual user verification.")
            elif previous_status in ("DISCONNECTED", "NEEDS_ATTENTION", "RATE_LIMITED", "PENDING", "CHALLENGE_REQUIRED"):
                new_status = "ACTIVE"
                healed = True
                actions_taken.append(f"Auto-healed account status from {previous_status} -> ACTIVE.")

                try:
                    camps_res = (
                        supabase.table("campaigns")
                        .select("id, name, status, pod_emergency_paused, pod_pause_reason, metadata")
                        .eq("workspace_id", workspace_id)
                        .eq("status", "PAUSED")
                        .execute()
                    )
                    for camp in (camps_res.data or []):
                        meta = camp.get("metadata") or {}
                        is_auto_paused = (
                            camp.get("pod_emergency_paused") is True
                            or camp.get("pod_pause_reason") is not None
                            or meta.get("paused_reason") in ("ACCOUNT_DISCONNECTED", "POD_SENDER_QUARANTINED", "ALL_SENDERS_UNAVAILABLE")
                        )
                        if not is_auto_paused:
                            continue

                        camp_accs = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", camp["id"]).execute()
                        acc_ids = [row["account_id"] for row in (camp_accs.data or [])]
                        if account_id in acc_ids:
                            supabase.table("campaigns").update({
                                "status": "ACTIVE",
                                "pod_emergency_paused": False,
                                "pod_pause_reason": None,
                                "updated_at": now_iso
                            }).eq("id", camp["id"]).execute()
                            actions_taken.append(f"Automatically resumed account-paused campaign '{camp['name']}'.")
                except Exception as camp_err:
                    logger.warning(f"Could not check/resume paused campaigns: {camp_err}")
            else:
                new_status = "ACTIVE"
                actions_taken.append("Account session is fully verified and active.")
        elif is_rate_limited:
            new_status = "RATE_LIMITED"
            recommendation = "COOLING_ACTIVE"
            actions_taken.append("Account transitioned to RATE_LIMITED. Outreach throttled for 2 hours to avoid account penalties.")
        else:
            new_status = "DISCONNECTED"
            recommendation = "RENEWAL_REQUIRED"
            actions_taken.append("Session is dead. User intervention required to refresh session cookies.")

        # 6. Compute composite health score
        health_score = calculate_composite_health_score(
            session_valid=session_valid,
            proxy_latency_ms=proxy_latency_ms,
            cookie_expires_at_str=account.get("cookie_expires_at"),
            status=new_status
        )

        # 7. Persist updated account record
        update_data: Dict[str, Any] = {
            "status": new_status,
            "last_health_check_at": now_iso,
            "updated_at": now_iso
        }
        if session_valid:
            update_data["manual_send_suspected"] = False

        if is_challenge:
            update_data["quarantined_until"] = (now_utc + timedelta(hours=24)).isoformat()
            update_data["quarantine_reason"] = f"Security challenge: {challenge_detail}"
        elif session_valid:
            update_data["quarantined_until"] = None
            update_data["quarantine_reason"] = None

        try:
            update_data["health_score"] = health_score
            update_data["auto_heal_status"] = recommendation
            update_data["auto_heal_actions"] = json.dumps(actions_taken)
            supabase.table("accounts").update(update_data).eq("id", account_id).execute()
        except Exception:
            supabase.table("accounts").update({
                "status": new_status,
                "last_health_check_at": now_iso,
                "updated_at": now_iso
            }).eq("id", account_id).execute()

        try:
            supabase.table("account_health_checks").insert({
                "account_id": account_id,
                "check_type": "auto_heal",
                "result": "pass" if session_valid else ("warn" if is_rate_limited else ("challenge" if is_challenge else "fail")),
                "detail": {"actions": actions_taken, "health_score": health_score, "healed": healed},
                "checked_at": now_iso
            }).execute()
        except Exception as log_err:
            logger.warning(f"Failed to record health check event: {log_err}")

        return {
            "account_id": account_id,
            "previous_status": previous_status,
            "new_status": new_status,
            "healed": healed,
            "health_score": health_score,
            "proxy_status": proxy_status,
            "proxy_latency_ms": proxy_latency_ms,
            "actions_taken": actions_taken,
            "recommendation": recommendation,
            "timestamp": now_iso
        }
    finally:
        try:
            supabase.table("accounts").update({"session_locked_until": None}).eq("id", account_id).execute()
        except Exception:
            pass
        with _heal_locks_mutex:
            _active_heals.pop(account_id, None)


# ── FLEET-WIDE BATCH AUTO-HEAL ────────────────────────────────────────────────

def fleet_auto_heal(workspace_id: str, supabase: Client) -> Dict[str, Any]:
    """
    Sweeps through all accounts in a workspace, skipping quarantined accounts.
    """
    acc_res = supabase.table("accounts").select("id, name, status, quarantined_until").eq("workspace_id", workspace_id).execute()
    accounts = acc_res.data or []
    
    total_scanned = len(accounts)
    healed_count = 0
    attention_count = 0
    details: List[Dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)

    for acc in accounts:
        try:
            q_str = acc.get("quarantined_until")
            if q_str:
                try:
                    q_dt = datetime.fromisoformat(q_str.replace("Z", "+00:00"))
                    if now_utc < q_dt:
                        attention_count += 1
                        details.append({
                            "account_id": acc.get("id"),
                            "skipped": True,
                            "reason": "quarantined",
                            "new_status": acc.get("status", "CHALLENGE_REQUIRED")
                        })
                        continue
                except Exception:
                    pass

            res = auto_heal_account(acc["id"], workspace_id, supabase)
            details.append(res)
            if res.get("healed"):
                healed_count += 1
            if res.get("new_status") in ("DISCONNECTED", "NEEDS_ATTENTION", "RATE_LIMITED", "CHALLENGE_REQUIRED"):
                attention_count += 1
        except Exception as e:
            logger.error(f"Error healing account {acc.get('id')}: {e}")
            details.append({
                "account_id": acc.get("id"),
                "error": str(e),
                "healed": False
            })

    return {
        "workspace_id": workspace_id,
        "total_scanned": total_scanned,
        "healed_count": healed_count,
        "attention_count": attention_count,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ── FLEET HEALTH SUMMARY ──────────────────────────────────────────────────────

def get_fleet_health_summary(workspace_id: str, supabase: Client) -> Dict[str, Any]:
    acc_res = supabase.table("accounts").select("id, name, status, cookie_expires_at, health_score, proxy_id").eq("workspace_id", workspace_id).execute()
    accounts = acc_res.data or []

    px_res = supabase.table("proxies").select("id, status, latency_ms").eq("workspace_id", workspace_id).execute()
    proxies = px_res.data or []

    total_senders = len(accounts)
    active_senders = sum(1 for a in accounts if a.get("status") == "ACTIVE")
    degraded_senders = sum(1 for a in accounts if a.get("status") in ("DISCONNECTED", "NEEDS_ATTENTION", "RATE_LIMITED", "CHALLENGE_REQUIRED"))

    now = datetime.now(timezone.utc)
    expiring_cookies_count = 0
    for a in accounts:
        exp_str = a.get("cookie_expires_at")
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                if now < exp_dt < now + timedelta(days=7):
                    expiring_cookies_count += 1
            except Exception:
                pass

    latencies = [p["latency_ms"] for p in proxies if p.get("latency_ms") and p.get("status") == "healthy"]
    avg_proxy_latency_ms = int(sum(latencies) / len(latencies)) if latencies else None

    scores = [a.get("health_score", 100) for a in accounts if a.get("health_score") is not None]
    fleet_health_score = int(sum(scores) / len(scores)) if scores else 100

    return {
        "fleet_health_score": fleet_health_score,
        "total_senders": total_senders,
        "active_senders": active_senders,
        "degraded_senders": degraded_senders,
        "expiring_cookies_count": expiring_cookies_count,
        "avg_proxy_latency_ms": avg_proxy_latency_ms,
        "total_proxies": len(proxies),
        "healthy_proxies": sum(1 for p in proxies if p.get("status") == "healthy"),
        "timestamp": now.isoformat()
    }


# ── SEAMLESS SESSION RENEWAL ──────────────────────────────────────────────────

def renew_account_session(
    account_id: str,
    workspace_id: str,
    new_cookies_json: str,
    supabase: Client
) -> Dict[str, Any]:
    from campaigns.backend.routers.elein import normalize_linkedin_cookies_payload
    parsed_cookies = normalize_linkedin_cookies_payload(new_cookies_json)
    if not parsed_cookies:
        cleaned = (new_cookies_json or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        try:
            parsed_cookies = json.loads(cleaned)
        except Exception:
            raise ValueError("Invalid JSON format. Please export as a JSON array from your browser cookie editor.")

    if not isinstance(parsed_cookies, list):
        raise ValueError("Cookies must be a JSON array ([{...}]).")

    li_at = next((c.get("value") for c in parsed_cookies if c.get("name") == "li_at"), None)
    if not li_at:
        raise ValueError("Missing 'li_at' cookie. Make sure you are logged into linkedin.com when exporting cookies.")

    acc_res = supabase.table("accounts").select("id, workspace_id, proxy_id, linkedin_profile_url, name").eq("id", account_id).eq("workspace_id", workspace_id).execute()
    if not acc_res.data:
        raise ValueError("Account not found or access denied")
    acc = acc_res.data[0]

    proxy_url = _build_account_proxy_url(acc, supabase)
    worker = LinkedInWorker(cookies_json=json.dumps(parsed_cookies), account_id=account_id, proxy_url=proxy_url)
    detected_profile_url = ""
    try:
        resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
        if resp.status_code != 200:
            raise ValueError(f"LinkedIn rejected the provided session (HTTP {resp.status_code}). Please log into LinkedIn and re-export.")

        # Paranoia Layer 0 & 2: Human Error & Identity Guard
        try:
            me_data = resp.json() if callable(getattr(resp, "json", None)) else {}
            if isinstance(me_data, dict):
                mini = me_data.get("miniProfile") or {}
                if isinstance(mini, dict):
                    first = str(mini.get("firstName") or "")
                    last = str(mini.get("lastName") or "")
                    pub_id = str(mini.get("publicIdentifier") or "").strip().lower()
                    detected_name = f"{first} {last}".strip() or "LinkedIn Account"
                    if pub_id:
                        detected_profile_url = f"https://www.linkedin.com/in/{pub_id}/"

                    existing_profile = str(acc.get("linkedin_profile_url") or "").strip()
                    if existing_profile and pub_id:
                        clean_existing = existing_profile.split("?")[0].split("#")[0].rstrip("/").strip().lower()
                        existing_parts = [p for p in clean_existing.split("/") if p]
                        existing_pub_id = ""
                        if "in" in existing_parts:
                            idx = existing_parts.index("in")
                            if idx + 1 < len(existing_parts):
                                existing_pub_id = existing_parts[idx + 1]
                        else:
                            existing_pub_id = existing_parts[-1] if existing_parts else ""

                        if existing_pub_id and existing_pub_id != pub_id:
                            raise ValueError(
                                f"Identity mismatch! You provided session cookies for '{detected_name}' ({detected_profile_url}), "
                                f"but this sender account is linked to '{acc.get('name') or 'Existing Sender'}' ({existing_profile}). "
                                f"Please log into the matching LinkedIn profile and re-export."
                            )
        except ValueError:
            raise
        except Exception as parse_err:
            logger.warning(f"Could not parse voyager /me response for identity match: {parse_err}")
    except ValueError:
        raise
    except Exception as e:
        logger.warning(f"Pre-flight HTTP check encountered exception (proceeding with cookie format): {e}")

    for ck in parsed_cookies:
        if "sameSite" in ck and ck["sameSite"] not in ["Strict", "Lax", "None"]:
            del ck["sameSite"]
    sanitized_json = json.dumps(parsed_cookies)

    dek_b64 = crypto.generate_dek()
    dek_bytes = base64.b64decode(dek_b64)
    from core.backend.api.auth_dep import get_service_client
    svc = get_service_client() or supabase
    rpc_res = svc.rpc("store_account_secret", {"p_secret": dek_b64}).execute()
    cookie_secret_ref = rpc_res.data

    encrypted_bytes = crypto.encrypt_bytes(sanitized_json.encode("utf-8"), dek=dek_bytes)
    pg_hex = crypto.bytes_to_pg_hex(encrypted_bytes)

    now_dt = datetime.now(timezone.utc)
    expires_at_ts = min([c.get("expires", 0) for c in parsed_cookies if c.get("expires", 0) > 0], default=0)
    cookie_expires_at = datetime.fromtimestamp(expires_at_ts, timezone.utc).isoformat() if expires_at_ts > 0 else (now_dt + timedelta(days=90)).isoformat()

    now_iso = now_dt.isoformat()
    update_data: Dict[str, Any] = {
        "cookie_secret_ref": cookie_secret_ref,
        "session_cookies_encrypted": pg_hex,
        "cookie_expires_at": cookie_expires_at,
        "status": "ACTIVE",
        "manual_send_suspected": False,
        "session_locked_until": None,
        "quarantined_until": None,
        "quarantine_reason": None,
        "last_health_check_at": now_iso,
        "updated_at": now_iso
    }
    if not acc.get("linkedin_profile_url") and detected_profile_url:
        update_data["linkedin_profile_url"] = detected_profile_url

    try:
        update_data["health_score"] = 95
        update_data["auto_heal_status"] = "ALL_CLEAR"
        supabase.table("accounts").update(update_data).eq("id", account_id).execute()
    except Exception:
        supabase.table("accounts").update({
            "cookie_secret_ref": cookie_secret_ref,
            "session_cookies_encrypted": pg_hex,
            "cookie_expires_at": cookie_expires_at,
            "status": "ACTIVE",
            "manual_send_suspected": False,
            "session_locked_until": None,
            "quarantined_until": None,
            "quarantine_reason": None,
            "last_health_check_at": now_iso,
            "updated_at": now_iso
        }).eq("id", account_id).execute()

    try:
        camps_res = (
            supabase.table("campaigns")
            .select("id, name, status, pod_emergency_paused, pod_pause_reason, metadata")
            .eq("workspace_id", workspace_id)
            .eq("status", "PAUSED")
            .execute()
        )
        for camp in (camps_res.data or []):
            meta = camp.get("metadata") or {}
            is_auto_paused = (
                camp.get("pod_emergency_paused") is True
                or camp.get("pod_pause_reason") is not None
                or meta.get("paused_reason") in ("ACCOUNT_DISCONNECTED", "POD_SENDER_QUARANTINED", "ALL_SENDERS_UNAVAILABLE")
            )
            if not is_auto_paused:
                continue

            camp_accs = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", camp["id"]).execute()
            acc_ids = [row["account_id"] for row in (camp_accs.data or [])]
            if account_id in acc_ids:
                supabase.table("campaigns").update({
                    "status": "ACTIVE",
                    "pod_emergency_paused": False,
                    "pod_pause_reason": None,
                    "updated_at": now_iso
                }).eq("id", camp["id"]).execute()
    except Exception as e:
        logger.warning(f"Could not unpause campaigns: {e}")

    try:
        supabase.table("account_health_checks").insert({
            "account_id": account_id,
            "check_type": "session_renewed",
            "result": "pass",
            "detail": {"message": "Session cookies renewed and verified", "cookie_expires_at": cookie_expires_at},
            "checked_at": now_iso
        }).execute()
    except Exception:
        pass

    return {
        "success": True,
        "account_id": account_id,
        "status": "ACTIVE",
        "cookie_expires_at": cookie_expires_at,
        "message": "Session successfully renewed and verified. Outreach campaigns active."
    }
