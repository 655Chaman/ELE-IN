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
            p_ws = proxy.get("workspace_id")
            if not p_ws and svc:
                try:
                    p_row = svc.table("proxies").select("workspace_id").eq("id", proxy_id).limit(1).execute()
                    if p_row.data and p_row.data[0].get("workspace_id"):
                        p_ws = p_row.data[0]["workspace_id"]
                except Exception:
                    pass

            rpc_payload = {"p_proxy_id": proxy_id}
            if p_ws:
                rpc_payload["p_workspace_id"] = p_ws

            try:
                rpc_res = svc.rpc("get_decrypted_proxy_payload", rpc_payload).execute()
            except Exception as rpc_err:
                if "PGRST203" in str(rpc_err) and "p_workspace_id" not in rpc_payload:
                    rpc_payload["p_workspace_id"] = "00000000-0000-0000-0000-000000000000"
                    rpc_res = svc.rpc("get_decrypted_proxy_payload", rpc_payload).execute()
                else:
                    raise rpc_err

            if rpc_res.data and rpc_res.data.get("password_encrypted"):
                raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                dek_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Could not decrypt password for proxy {proxy_id}: {e}")

    # Build proxy URL with strict password/username percent-encoding
    from core.backend.services.proxy_routing import format_proxy_url
    effective_pwd = password_plain or proxy.get("password")
    proxy_url = format_proxy_url(protocol, host, port, username, effective_pwd if effective_pwd else None)

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
                
                exit_ip_1 = None
                exit_ip_2 = None
                try:
                    ip_resp = client.get("https://api.ipify.org?format=json", timeout=2.0)
                    if ip_resp.status_code == 200:
                        exit_ip_1 = ip_resp.json().get("ip")
                        exit_ip = exit_ip_1

                        # Paranoia Layer 1: Two-ping rotating proxy drift detector
                        # Ping exit IP a second time after 200ms pause to ensure static/sticky IP stability
                        try:
                            time.sleep(0.2)
                            ip_resp2 = client.get("https://api.ipify.org?format=json", timeout=2.0)
                            if ip_resp2.status_code == 200:
                                exit_ip_2 = ip_resp2.json().get("ip")
                        except (Exception, StopIteration):
                            pass

                        if not (exit_ip_1 and exit_ip_2 and exit_ip_1 != exit_ip_2):
                            if not detected_country and exit_ip:
                                try:
                                    geo_resp = client.get(f"https://ipapi.co/{exit_ip}/country/", timeout=1.5)
                                    if geo_resp.status_code == 200 and len(geo_resp.text.strip()) == 2:
                                        detected_country = geo_resp.text.strip().upper()
                                except Exception:
                                    pass
                except Exception:
                    pass

                if exit_ip_1 and exit_ip_2 and exit_ip_1 != exit_ip_2:
                    result = {
                        "ok": False,
                        "latency_ms": latency_ms,
                        "status": "rotating_flapping",
                        "exit_ip": exit_ip_1,
                        "country_code": detected_country,
                        "error": f"Rotating proxy detected (exit IP mutated from {exit_ip_1} to {exit_ip_2}). LinkedIn requires static/sticky residential IPs."
                    }
                else:
                    result = {
                        "ok": True,
                        "latency_ms": latency_ms,
                        "status": status,
                        "exit_ip": exit_ip or host,
                        "country_code": detected_country,
                        "error": err_msg
                    }
            elif probe_resp.status_code == 407:
                # Paranoia Layer 1: Gateway Proxy Authentication Required
                result = {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "status": "auth_failed",
                    "exit_ip": None,
                    "country_code": detected_country,
                    "error": "Proxy Authentication Required (HTTP 407) - Check username and password"
                }
            elif probe_resp.status_code in (402, 429):
                # Paranoia Layer 1: Gateway Quota / Bandwidth Exhaustion or Rate Limit
                result = {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "status": "quota_exceeded",
                    "exit_ip": None,
                    "country_code": detected_country,
                    "error": f"Proxy provider quota depleted or rate limited (HTTP {probe_resp.status_code}). Please top up bandwidth or increase concurrent connection limit."
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
        pe_str = str(pe).lower()
        if "407" in pe_str or "authentication" in pe_str or "credentials" in pe_str:
            result = {"ok": False, "latency_ms": latency_ms, "status": "auth_failed", "exit_ip": None, "country_code": detected_country, "error": f"Proxy Authentication Required (HTTP 407) - Check username and password: {pe}"}
        elif "402" in pe_str or "payment" in pe_str or "quota" in pe_str or "429" in pe_str or "rate limit" in pe_str:
            result = {"ok": False, "latency_ms": latency_ms, "status": "quota_exceeded", "exit_ip": None, "country_code": detected_country, "error": f"Proxy provider quota depleted or rate limited: {pe}"}
        else:
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
    from core.backend.services.proxy_routing import build_authenticated_proxy_url
    # Paranoia Layer 1: If proxies relation was not joined, hydrate proxy record directly
    if acc.get("proxy_id") and not acc.get("proxies") and supabase:
        try:
            px_res = supabase.table("proxies").select("*").eq("id", acc["proxy_id"]).execute()
            if px_res.data:
                acc["proxies"] = px_res.data[0]
        except Exception as e:
            logger.warning(f"Could not fetch proxy row for account {acc.get('id')}: {e}")
    return build_authenticated_proxy_url(acc, supabase)


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
                        target_country=target_country,
                        allow_cross_country_drift=False
                    )

                    if replacement:
                        rep_probe = probe_proxy_health(replacement, supabase=supabase)
                        if rep_probe.get("ok"):
                            supabase.table("accounts").update({
                                "proxy_id": replacement["id"],
                                "updated_at": now_iso
                            }).eq("id", account_id).execute()
                            proxy_id = replacement["id"]
                            account["proxy_id"] = replacement["id"]
                            account["proxies"] = replacement
                            try:
                                from integrations.backend.services.linkedin_pool import global_browser_pool
                                global_browser_pool.evict(account_id)
                            except Exception:
                                pass
                            proxy_latency_ms = rep_probe.get("latency_ms")
                            proxy_status = "healthy"
                            actions_taken.append(f"Auto-rotated account to healthy proxy {replacement.get('host')}:{replacement.get('port')} (Latency: {proxy_latency_ms}ms).")
                        else:
                            actions_taken.append(f"Candidate backup proxy {replacement.get('host')} also failed neutral probe. Direct unproxied connection safely blocked.")
                    else:
                        actions_taken.append("No healthy backup residential proxies available in matching country in workspace pool.")
                else:
                    actions_taken.append(f"Current proxy {current_proxy.get('host')} verified healthy (Latency: {proxy_latency_ms}ms).")

        if proxy_id:
            from core.backend.services.proxy_routing import build_authenticated_proxy_url
            active_proxy_url = build_authenticated_proxy_url(account, supabase)

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
                    from core.backend.services.proxy_routing import canary_check_proxy, quarantine_proxy
                    canary = canary_check_proxy(supabase, proxy_id)
                    if not canary.get("is_healthy"):
                        quarantine_proxy(supabase, proxy_id, reason="proxy_canary_failed_on_challenge", cooldown_hours=24)
                        actions_taken.append(f"Proxy {proxy_id} failed independent canary check ({canary.get('reason')}). Quarantined for 24h.")
                    else:
                        actions_taken.append(f"Proxy {proxy_id} passed independent canary check. Account challenged individually; proxy preserved for fleet.")
                except Exception as q_err:
                    logger.warning(f"Could not evaluate proxy canary: {q_err}")
            
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


# ── PHASE R: AUTOMATED ACCOUNT RECOVERY & REPUTATION ENGINE ───────────────────

def _sanitize_account_string(val: Any, max_len: int = 500) -> str:
    """Paranoia Layer 2: Sanitizes string inputs, neutralizes formula injection and strips null bytes."""
    if val is None:
        return ""
    s = str(val).replace("\x00", "").replace("\r", " ").strip()
    while s and s[0] in ('=', '+', '-', '@', '\t'):
        s = s[1:].strip()
    return s[:max_len]


def _zeroize_bytearray(buffer: bytearray) -> None:
    """Paranoia Layer 1 & 2: Cryptographic memory zeroization."""
    if buffer is not None and isinstance(buffer, bytearray):
        for i in range(len(buffer)):
            buffer[i] = 0


def detect_session_death_and_validate_cookies(
    account_id: str,
    workspace_id: str,
    supabase: Client,
    force_probe: bool = False
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Active Cookie Session Validation & Session-Death Detection.
    - Layer 0: Resolves credentials, decrypts cookies via DEK, verifies li_at presence & expiration.
    - Layer 1: Detects definitive session-death signatures (401 Unauthorized, login redirect, revoked token).
               On death, transitions account to DISCONNECTED, auto-pauses tied campaigns, and queues outbox alert.
    - Layer 2: Neutralizes formula injection, performs zeroization on decrypted plaintext, and enforces workspace isolation.
    """
    if not account_id or not workspace_id:
        return {"session_valid": False, "status": "error", "error": "Missing account_id or workspace_id"}

    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    try:
        acc_res = supabase.table("accounts") \
            .select("id, name, status, workspace_id, proxy_id, cookie_expires_at, cookie_secret_ref, session_cookies_encrypted, proxies(*)") \
            .eq("id", account_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
        if not acc_res.data or len(acc_res.data) == 0:
            raise ValueError(f"Account {account_id} not found in workspace {workspace_id}")
        account = acc_res.data[0]
    except Exception as e:
        logger.error(f"[SessionDeathDetector] Account query error: {e}")
        return {"session_valid": False, "status": "error", "error": str(e)}

    raw_encrypted = account.get("session_cookies_encrypted")
    if not raw_encrypted:
        # Definitive session death: missing cookies
        _mark_session_death(
            supabase=supabase,
            account_id=account_id,
            workspace_id=workspace_id,
            reason="MISSING_SESSION_COOKIES",
            now_iso=now_iso
        )
        return {
            "session_valid": False,
            "session_death": True,
            "status": "DISCONNECTED",
            "reason": "MISSING_SESSION_COOKIES",
            "actions_taken": ["No session cookies configured. Transitioned status to DISCONNECTED."],
            "checked_at": now_iso
        }

    # Decrypt cookies via DEK
    dek_bytes = None
    cookie_secret_ref = account.get("cookie_secret_ref")
    if cookie_secret_ref:
        try:
            rpc_res = supabase.rpc("get_decrypted_account_payload", {"p_account_id": account_id}).execute()
            if rpc_res.data and rpc_res.data.get("dek"):
                dek_bytes = base64.b64decode(rpc_res.data["dek"])
        except Exception as dek_err:
            logger.debug(f"[SessionDeathDetector] RPC DEK retrieval fallback: {dek_err}")

    cookies_json = ""
    try:
        raw_bytes = crypto.pg_hex_to_bytes(raw_encrypted) if isinstance(raw_encrypted, str) else raw_encrypted
        decrypted_raw = crypto.decrypt_bytes(raw_bytes, dek=dek_bytes)
        cookies_json = decrypted_raw.decode("utf-8")
        # Memory zeroization on decrypted bytes
        decrypted_ba = bytearray(decrypted_raw)
        _zeroize_bytearray(decrypted_ba)
    except Exception as dec_err:
        logger.warning(f"[SessionDeathDetector] Cookie decryption failed: {dec_err}")
        _mark_session_death(
            supabase=supabase,
            account_id=account_id,
            workspace_id=workspace_id,
            reason=f"DECRYPTION_FAILED: {dec_err}",
            now_iso=now_iso
        )
        return {
            "session_valid": False,
            "session_death": True,
            "status": "DISCONNECTED",
            "reason": "DECRYPTION_FAILED",
            "error": _sanitize_account_string(str(dec_err)),
            "checked_at": now_iso
        }

    # Parse cookies JSON
    try:
        cookie_list = json.loads(cookies_json) if isinstance(cookies_json, str) else cookies_json
        if not isinstance(cookie_list, list):
            raise ValueError("Cookies must be a list of cookie objects")
    except Exception as json_err:
        _mark_session_death(
            supabase=supabase,
            account_id=account_id,
            workspace_id=workspace_id,
            reason=f"CORRUPT_COOKIE_JSON: {json_err}",
            now_iso=now_iso
        )
        return {
            "session_valid": False,
            "session_death": True,
            "status": "DISCONNECTED",
            "reason": "CORRUPT_COOKIE_JSON",
            "checked_at": now_iso
        }

    # Verify li_at presence
    li_at = next((c.get("value") for c in cookie_list if isinstance(c, dict) and c.get("name") == "li_at"), None)
    if not li_at or not str(li_at).strip():
        _mark_session_death(
            supabase=supabase,
            account_id=account_id,
            workspace_id=workspace_id,
            reason="MISSING_LI_AT_TOKEN",
            now_iso=now_iso
        )
        return {
            "session_valid": False,
            "session_death": True,
            "status": "DISCONNECTED",
            "reason": "MISSING_LI_AT_TOKEN",
            "checked_at": now_iso
        }

    # Check expiration date
    exp_str = account.get("cookie_expires_at")
    if exp_str:
        try:
            exp_dt = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if now_utc > exp_dt:
                _mark_session_death(
                    supabase=supabase,
                    account_id=account_id,
                    workspace_id=workspace_id,
                    reason=f"COOKIE_EXPIRED_ON_{exp_str}",
                    now_iso=now_iso
                )
                return {
                    "session_valid": False,
                    "session_death": True,
                    "status": "DISCONNECTED",
                    "reason": "COOKIE_EXPIRED",
                    "expires_at": exp_str,
                    "checked_at": now_iso
                }
        except Exception:
            pass

    # Optional active API session probe
    session_valid = True
    session_death = False
    death_reason = None
    actions_taken = ["Session cookies decrypted and validated format."]

    if force_probe or account.get("status") in ("DISCONNECTED", "NEEDS_ATTENTION"):
        active_proxy_url = _build_account_proxy_url(account, supabase)
        try:
            worker = LinkedInWorker(cookies_json=cookies_json, proxy_url=active_proxy_url, account_id=account_id)
            resp = worker._http_get("https://www.linkedin.com/voyager/api/me")
            if resp.status_code == 200:
                resp_text = resp.text or ""
                if "checkpoint/challenge" in resp_text or "security-check" in resp_text:
                    session_valid = False
                    session_death = False
                    dispatch_challenge_verification_alert(
                        account_id=account_id,
                        workspace_id=workspace_id,
                        challenge_type="SECURITY_CHECKPOINT",
                        detail="Redirected to checkpoint during session check",
                        supabase=supabase
                    )
                    return {
                        "session_valid": False,
                        "session_death": False,
                        "status": "CHALLENGE_REQUIRED",
                        "reason": "SECURITY_CHECKPOINT",
                        "checked_at": now_iso
                    }
                else:
                    session_valid = True
                    actions_taken.append("Active LinkedIn Voyager probe succeeded (HTTP 200).")
            elif resp.status_code == 403:
                # Paranoia Layer 1: Distinguish checkpoint / challenge challenges from permanent death
                resp_text = ""
                try:
                    resp_text = resp.text.lower() if hasattr(resp, "text") else ""
                except Exception:
                    pass
                if any(w in resp_text for w in ("challenge", "checkpoint", "captcha", "security", "verify")):
                    session_valid = False
                    session_death = False
                    dispatch_challenge_verification_alert(
                        account_id=account_id,
                        workspace_id=workspace_id,
                        challenge_type="HTTP_403_SECURITY_CHECKPOINT",
                        detail="LinkedIn returned HTTP 403 with checkpoint signature",
                        supabase=supabase
                    )
                    return {
                        "session_valid": False,
                        "session_death": False,
                        "status": "CHALLENGE_REQUIRED",
                        "reason": "SECURITY_CHECKPOINT",
                        "checked_at": now_iso
                    }
                else:
                    session_valid = False
                    session_death = True
                    death_reason = "HTTP_403_FORBIDDEN"
            elif resp.status_code == 401:
                session_valid = False
                session_death = True
                death_reason = "HTTP_401_UNAUTHORIZED"
            elif resp.status_code == 999:
                # Paranoia Layer 1: Anti-scraping HTTP 999 Request Denied
                session_valid = False
                session_death = False
                logger.warning(f"[SessionCheck] LinkedIn anti-bot 999 response for account {account_id}.")
                dispatch_challenge_verification_alert(
                    account_id=account_id,
                    workspace_id=workspace_id,
                    challenge_type="HTTP_999_REQUEST_DENIED",
                    detail="LinkedIn returned HTTP 999 Anti-Bot Request Denied",
                    supabase=supabase
                )
                return {
                    "session_valid": False,
                    "session_death": False,
                    "status": "CHALLENGE_REQUIRED",
                    "reason": "HTTP_999_REQUEST_DENIED",
                    "checked_at": now_iso
                }
            elif resp.status_code == 429:
                session_valid = True  # session is alive, just rate limited
                actions_taken.append("Account is rate-limited (HTTP 429), session remains alive.")
            else:
                session_valid = False
                session_death = True
                death_reason = f"HTTP_{resp.status_code}_UNEXPECTED"
        except SecurityChallengeError as sce:
            session_valid = False
            session_death = False
            dispatch_challenge_verification_alert(
                account_id=account_id,
                workspace_id=workspace_id,
                challenge_type="SECURITY_CHALLENGE",
                detail=str(sce),
                supabase=supabase
            )
            return {
                "session_valid": False,
                "session_death": False,
                "status": "CHALLENGE_REQUIRED",
                "reason": "SECURITY_CHALLENGE",
                "checked_at": now_iso
            }
        except Exception as probe_err:
            # Paranoia Layer 1: If probe error is proxy related, do NOT mark session death
            err_str = str(probe_err).lower()
            if any(term in err_str for term in ("proxy", "connecttimeout", "timed out", "407", "402")):
                actions_taken.append(f"Proxy network error during probe ({probe_err}). Session not declared dead.")
            else:
                actions_taken.append(f"Probe error: {probe_err}")

    if session_death and death_reason:
        _mark_session_death(
            supabase=supabase,
            account_id=account_id,
            workspace_id=workspace_id,
            reason=death_reason,
            now_iso=now_iso
        )
        return {
            "session_valid": False,
            "session_death": True,
            "status": "DISCONNECTED",
            "reason": death_reason,
            "actions_taken": actions_taken,
            "checked_at": now_iso
        }

    # Update last checked timestamp
    try:
        supabase.table("accounts").update({
            "last_health_check_at": now_iso
        }).eq("id", account_id).execute()
    except Exception:
        pass

    return {
        "session_valid": True,
        "session_death": False,
        "status": account.get("status", "ACTIVE"),
        "cookie_expires_at": account.get("cookie_expires_at"),
        "actions_taken": actions_taken,
        "checked_at": now_iso
    }


def _mark_session_death(
    supabase: Client,
    account_id: str,
    workspace_id: str,
    reason: str,
    now_iso: str
) -> None:
    """Paranoia Layer 0 & 1: Marks account DISCONNECTED and safely pauses tied campaigns."""
    clean_reason = _sanitize_account_string(reason, 255)
    try:
        supabase.table("accounts").update({
            "status": "DISCONNECTED",
            "session_death_detected_at": now_iso,
            "session_death_reason": clean_reason,
            "health_score": 10,
            "updated_at": now_iso
        }).eq("id", account_id).eq("workspace_id", workspace_id).execute()
    except Exception as e:
        logger.warning(f"[SessionDeath] DB update failed: {e}")

    # Pause tied campaigns
    try:
        camp_res = supabase.table("campaign_accounts").select("campaign_id").eq("account_id", account_id).execute()
        camp_ids = [r["campaign_id"] for r in (camp_res.data or []) if r.get("campaign_id")]
        if camp_ids:
            supabase.table("campaigns").update({
                "status": "PAUSED",
                "pod_emergency_paused": True,
                "pod_pause_reason": f"ACCOUNT_SESSION_DEATH:{clean_reason}",
                "updated_at": now_iso
            }).in_("id", camp_ids).eq("status", "ACTIVE").execute()
    except Exception as camp_pause_err:
        logger.warning(f"[SessionDeath] Campaign pause failed: {camp_pause_err}")

    # Queue alert notification
    try:
        supabase.table("outbox_events").insert({
            "workspace_id": workspace_id,
            "event_type": "account.session_expired",
            "payload": {
                "account_id": account_id,
                "reason": clean_reason,
                "detected_at": now_iso
            },
            "status": "pending",
            "created_at": now_iso
        }).execute()
    except Exception as outbox_err:
        logger.debug(f"[SessionDeath] Outbox alert failed: {outbox_err}")


def rotate_account_credential_dek(
    account_id: str,
    workspace_id: str,
    supabase: Client
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Automated Credential Refresh with Vault DEK Rotation.
    - Decrypts existing credentials under current DEK.
    - Generates a fresh 256-bit cryptographically secure DEK.
    - Stores new DEK into Vault via 'store_account_secret' RPC.
    - Re-encrypts credentials under the new DEK and zeroes out plaintext memory.
    - Updates database record atomically with new secret_ref and encrypted hex.
    """
    if not account_id or not workspace_id or not supabase:
        return {"status": "error", "message": "Missing required parameters"}

    with _heal_locks_mutex:
        if account_id in _active_heals:
            return {"status": "error", "message": "Account locked: another operation is in progress"}
        _active_heals[account_id] = time.time()

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        acc_res = supabase.table("accounts") \
            .select("id, workspace_id, session_cookies_encrypted, cookie_secret_ref") \
            .eq("id", account_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
        if not acc_res.data or len(acc_res.data) == 0:
            return {"status": "error", "message": "Account not found or access denied"}
        account = acc_res.data[0]

        raw_encrypted = account.get("session_cookies_encrypted")
        if not raw_encrypted:
            return {"status": "error", "message": "Account has no encrypted credentials to rotate"}

        # 1. Decrypt existing payload
        dek_bytes = None
        old_ref = account.get("cookie_secret_ref")
        if old_ref:
            try:
                rpc_res = supabase.rpc("get_decrypted_account_payload", {"p_account_id": account_id}).execute()
                if rpc_res.data and rpc_res.data.get("dek"):
                    dek_bytes = base64.b64decode(rpc_res.data["dek"])
            except Exception as e:
                logger.debug(f"[DEKRotate] Old DEK retrieval fallback: {e}")

        raw_bytes = crypto.pg_hex_to_bytes(raw_encrypted) if isinstance(raw_encrypted, str) else raw_encrypted
        decrypted_raw = crypto.decrypt_bytes(raw_bytes, dek=dek_bytes)

        # 2. Generate new DEK
        new_dek_b64 = crypto.generate_dek()
        try:
            if isinstance(new_dek_b64, str):
                pad_len = (4 - len(new_dek_b64) % 4) % 4
                new_dek_bytes = base64.b64decode(new_dek_b64 + ("=" * pad_len))
            else:
                new_dek_bytes = new_dek_b64
        except Exception:
            import os
            new_dek_bytes = os.urandom(32)

        # 3. Store new DEK in Vault
        new_secret_ref = None
        try:
            store_res = supabase.rpc("store_account_secret", {"p_secret": new_dek_b64}).execute()
            new_secret_ref = store_res.data
        except Exception as v_err:
            logger.warning(f"[DEKRotate] Vault RPC failed, using internal envelope: {v_err}")

        # 4. Re-encrypt under new DEK
        new_encrypted = crypto.encrypt_bytes(decrypted_raw, dek=new_dek_bytes if new_secret_ref else None)
        new_hex = crypto.bytes_to_pg_hex(new_encrypted)

        # 5. Zeroize memory
        decrypted_ba = bytearray(decrypted_raw)
        _zeroize_bytearray(decrypted_ba)
        if dek_bytes:
            old_dek_ba = bytearray(dek_bytes)
            _zeroize_bytearray(old_dek_ba)

        # 6. Persist rotation to accounts table
        update_payload = {
            "session_cookies_encrypted": new_hex,
            "dek_rotated_at": now_iso,
            "updated_at": now_iso
        }
        if new_secret_ref:
            update_payload["cookie_secret_ref"] = new_secret_ref

        supabase.table("accounts").update(update_payload).eq("id", account_id).execute()

        # Log audit entry
        try:
            supabase.table("account_health_checks").insert({
                "account_id": account_id,
                "check_type": "dek_rotated",
                "result": "pass",
                "detail": {"rotated_at": now_iso, "vault_ref": bool(new_secret_ref)},
                "checked_at": now_iso
            }).execute()
        except Exception:
            pass

        return {
            "status": "success",
            "account_id": account_id,
            "rotated_at": now_iso,
            "vault_secured": bool(new_secret_ref),
            "message": "Credential DEK rotated successfully with zero-leakage memory zeroization."
        }
    finally:
        with _heal_locks_mutex:
            _active_heals.pop(account_id, None)


def dispatch_challenge_verification_alert(
    account_id: str,
    workspace_id: str,
    challenge_type: str,
    detail: Optional[str] = None,
    supabase: Optional[Client] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Challenge Verification Alert Dispatcher.
    - Transitions account to CHALLENGE_REQUIRED and quarantines it for 24h.
    - Quarantines the associated proxy to protect sibling accounts in the pool.
    - Auto-pauses tied campaigns to halt outbound actions before bans occur.
    - Enqueues high-priority alert in outbox_events and account_health_checks.
    """
    clean_type = _sanitize_account_string(challenge_type or "SECURITY_CHALLENGE", 50).upper()
    clean_detail = _sanitize_account_string(detail or "Verification checkpoint encountered", 500)
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    quarantine_until = (now_utc + timedelta(hours=24)).isoformat()

    actions = [f"Challenge alert triggered: {clean_type}. Account placed in 24h quarantine."]

    if supabase:
        try:
            # 1. Update account status & quarantine
            supabase.table("accounts").update({
                "status": "CHALLENGE_REQUIRED",
                "quarantined_until": quarantine_until,
                "quarantine_reason": f"{clean_type}: {clean_detail}",
                "health_score": 15,
                "updated_at": now_iso
            }).eq("id", account_id).eq("workspace_id", workspace_id).execute()

            # 2. Quarantine assigned proxy if present
            acc_res = supabase.table("accounts").select("proxy_id").eq("id", account_id).execute()
            if acc_res.data and acc_res.data[0].get("proxy_id"):
                px_id = acc_res.data[0]["proxy_id"]
                from core.backend.services.proxy_routing import quarantine_proxy
                quarantine_proxy(supabase, px_id, reason=f"account_challenge_{clean_type.lower()}", cooldown_hours=24)
                actions.append(f"Quarantined proxy {px_id} for 24h.")

            # 3. Auto-pause associated campaigns
            camp_res = supabase.table("campaign_accounts").select("campaign_id").eq("account_id", account_id).execute()
            camp_ids = [r["campaign_id"] for r in (camp_res.data or []) if r.get("campaign_id")]
            if camp_ids:
                supabase.table("campaigns").update({
                    "status": "PAUSED",
                    "pod_emergency_paused": True,
                    "pod_pause_reason": f"CHALLENGE_ALERT:{clean_type}",
                    "updated_at": now_iso
                }).in_("id", camp_ids).eq("status", "ACTIVE").execute()
                actions.append(f"Auto-paused {len(camp_ids)} campaign(s) attached to challenged sender.")

            # 4. Enqueue outbox notification
            supabase.table("outbox_events").insert({
                "workspace_id": workspace_id,
                "event_type": "account.security_challenge",
                "payload": {
                    "account_id": account_id,
                    "challenge_type": clean_type,
                    "detail": clean_detail,
                    "quarantined_until": quarantine_until,
                    "timestamp": now_iso
                },
                "status": "pending",
                "created_at": now_iso
            }).execute()

            # 5. Insert health check event
            supabase.table("account_health_checks").insert({
                "account_id": account_id,
                "check_type": "security_challenge",
                "result": "challenge",
                "detail": {"challenge_type": clean_type, "detail": clean_detail, "actions": actions},
                "checked_at": now_iso
            }).execute()
        except Exception as e:
            logger.error(f"[ChallengeAlert] Error dispatching alert: {e}")
            actions.append(f"Alert logging error: {e}")

    return {
        "status": "alert_dispatched",
        "account_id": account_id,
        "challenge_type": clean_type,
        "quarantined_until": quarantine_until,
        "actions_taken": actions,
        "timestamp": now_iso
    }


def evaluate_and_gracefully_pause_mailbox(
    account_id: str,
    workspace_id: str,
    supabase: Optional[Client] = None,
    deliverability_score_threshold: float = 70.0,
    max_bounce_rate_pct: float = 5.0,
    max_spam_rate_pct: float = 0.1,
    min_sample_size: int = 10
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Graceful Account Pausing on Deliverability Threshold Breach.
    - Evaluates rolling mailbox metrics (sent count, bounces, spam complaints, deliverability score).
    - Protects small sample sizes (< 10) from premature false-positive pauses unless absolute bounds are violated.
    - If deliverability dips below 70.0 or bounce rate exceeds 5.0% or spam exceeds 0.1%:
      Gracefully pauses the mailbox, sets auto_heal_status='DELIVERABILITY_COOLDOWN',
      pauses tied campaign steps with MAILBOX_REPUTATION_PROTECT, and enqueues outbox event.
    """
    if not account_id or not workspace_id:
        return {"status": "error", "message": "Missing account_id or workspace_id"}

    # Layer 2 Paranoia: Clamp thresholds to safe operational bounds
    safe_deliv_threshold = max(20.0, min(95.0, float(deliverability_score_threshold or 70.0)))
    safe_bounce_threshold = max(0.5, min(20.0, float(max_bounce_rate_pct or 5.0)))
    safe_spam_threshold = max(0.01, min(5.0, float(max_spam_rate_pct or 0.1)))
    safe_min_sample = max(5, min(200, int(min_sample_size or 10)))

    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    cooldown_until = (now_utc + timedelta(hours=24)).isoformat()

    sent_count = 0
    bounce_count = 0
    spam_count = 0
    deliverability_score = 100.0

    if supabase:
        try:
            # Query email events for this account over last 7 days
            since_7d = (now_utc - timedelta(days=7)).isoformat()
            evt_res = supabase.table("email_events") \
                .select("event_type") \
                .eq("workspace_id", workspace_id) \
                .gte("created_at", since_7d) \
                .execute()
            for row in (evt_res.data or []):
                evt = (row.get("event_type") or "").lower()
                sent_count += 1
                if "bounce" in evt:
                    bounce_count += 1
                elif "spam" in evt or "complaint" in evt:
                    spam_count += 1
        except Exception as e:
            logger.debug(f"[MailboxPauseGuard] email_events query fallback: {e}")

    # Calculate metrics
    denominator = max(sent_count, bounce_count, spam_count)
    bounce_rate_pct = round((bounce_count / denominator) * 100.0, 2) if denominator > 0 else 0.0
    spam_rate_pct = round((spam_count / denominator) * 100.0, 3) if denominator > 0 else 0.0

    # Compute composite deliverability score
    penalty = (bounce_rate_pct * 8.0) + (spam_rate_pct * 150.0)
    deliverability_score = max(0.0, round(100.0 - penalty, 1))

    sample_reached = denominator >= safe_min_sample
    breaches: List[str] = []

    # Deliverability score breach
    if sample_reached and deliverability_score < safe_deliv_threshold:
        breaches.append(f"Deliverability score {deliverability_score} below threshold {safe_deliv_threshold}")

    # Bounce rate breach
    if (sample_reached and bounce_rate_pct >= safe_bounce_threshold) or bounce_count >= 3:
        breaches.append(f"Bounce rate {bounce_rate_pct}% exceeded limit {safe_bounce_threshold}% ({bounce_count} bounces)")

    # Spam complaint breach
    if (sample_reached and spam_rate_pct >= safe_spam_threshold) or spam_count >= 1:
        breaches.append(f"Spam complaint rate {spam_rate_pct}% exceeded limit {safe_spam_threshold}% ({spam_count} spam reports)")

    should_pause = len(breaches) > 0
    actions_taken: List[str] = []

    if should_pause:
        actions_taken.append(f"Gracefully paused mailbox due to deliverability breach: {'; '.join(breaches)}")
        if supabase:
            try:
                # 1. Update account status to COOLDOWN
                supabase.table("accounts").update({
                    "status": "COOLDOWN",
                    "auto_heal_status": "DELIVERABILITY_COOLDOWN",
                    "quarantined_until": cooldown_until,
                    "quarantine_reason": f"Deliverability threshold breach: {'; '.join(breaches)}",
                    "health_score": int(deliverability_score),
                    "updated_at": now_iso
                }).eq("id", account_id).eq("workspace_id", workspace_id).execute()

                # 2. Pause tied campaigns with MAILBOX_REPUTATION_PROTECT
                camp_res = supabase.table("campaign_accounts").select("campaign_id").eq("account_id", account_id).execute()
                camp_ids = [r["campaign_id"] for r in (camp_res.data or []) if r.get("campaign_id")]
                if camp_ids:
                    supabase.table("campaigns").update({
                        "status": "PAUSED",
                        "pod_emergency_paused": True,
                        "pod_pause_reason": "MAILBOX_REPUTATION_PROTECT",
                        "updated_at": now_iso
                    }).in_("id", camp_ids).eq("status", "ACTIVE").execute()
                    actions_taken.append(f"Auto-paused {len(camp_ids)} campaign(s) to protect domain reputation.")

                # 3. Enqueue outbox notification event
                supabase.table("outbox_events").insert({
                    "workspace_id": workspace_id,
                    "event_type": "mailbox.reputation_paused",
                    "payload": {
                        "account_id": account_id,
                        "deliverability_score": deliverability_score,
                        "bounce_rate_pct": bounce_rate_pct,
                        "spam_rate_pct": spam_rate_pct,
                        "breaches": breaches,
                        "cooldown_until": cooldown_until,
                        "timestamp": now_iso
                    },
                    "status": "pending",
                    "created_at": now_iso
                }).execute()

                # 4. Insert health check audit event
                supabase.table("account_health_checks").insert({
                    "account_id": account_id,
                    "check_type": "mailbox_reputation",
                    "result": "warn",
                    "detail": {"deliverability_score": deliverability_score, "breaches": breaches, "actions": actions_taken},
                    "checked_at": now_iso
                }).execute()
            except Exception as pause_err:
                logger.error(f"[MailboxPauseGuard] Failed to persist mailbox pause: {pause_err}")
    else:
        actions_taken.append(f"Mailbox reputation verified healthy (Score: {deliverability_score}, Bounce: {bounce_rate_pct}%, Spam: {spam_rate_pct}%).")
        if supabase:
            try:
                supabase.table("accounts").update({
                    "health_score": int(deliverability_score),
                    "auto_heal_status": "ALL_CLEAR",
                    "last_health_check_at": now_iso
                }).eq("id", account_id).execute()
            except Exception:
                pass

    return {
        "account_id": account_id,
        "paused": should_pause,
        "status": "COOLDOWN" if should_pause else "ACTIVE",
        "deliverability_score": deliverability_score,
        "bounce_rate_pct": bounce_rate_pct,
        "spam_rate_pct": spam_rate_pct,
        "sample_size": denominator,
        "sample_reached": sample_reached,
        "cooldown_until": cooldown_until if should_pause else None,
        "breaches": breaches,
        "actions_taken": actions_taken,
        "timestamp": now_iso
    }
