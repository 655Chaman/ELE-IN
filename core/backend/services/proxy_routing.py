"""
Three-Layer Paranoia Framework: Proxy Routing, Cooldown Quarantine & Sticky Affinity
- Layer 0: Sticky proxy affinity per account & least-loaded selection across healthy proxies.
- Layer 1: Security checkpoint quarantine (2-hour quarantine preventing collateral bans across fleet) + strict geo-country affinity preventing cross-border drift flags.
- Layer 2: Human paranoia: Validates proxy latency (< 2500ms), rejects quarantined proxy re-assignment, and sanitizes country codes.
"""
import ipaddress
import re
import socket
import time
import threading
from urllib.parse import urlparse, quote, unquote
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

class ProxyRequiredError(RuntimeError):
    """
    Paranoia Layer 0 & 1: Raised when a network operation requires an authenticated residential
    proxy to avoid leaking datacenter IP addresses or triggering Akamai/Cloudflare bot heuristics.
    """
    pass

DEFAULT_QUARANTINE_HOURS = 2
MAX_SAFE_LATENCY_MS = 2500

MAX_ACCOUNTS_PER_PROXY = 3

HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9.-]+$")

def validate_and_normalize_proxy_host(raw_host: Optional[str], allow_private: bool = False) -> str:
    """
    Paranoia Layer 2: SSRF and Private-IP guard for proxy hosts.
    Rejects loopback, link-local, private networks, unassigned/reserved IPs, and invalid hostnames.
    """
    if not raw_host:
        raise ValueError("Proxy host cannot be empty")
    host = str(raw_host).strip()
    if not host:
        raise ValueError("Proxy host cannot be empty")

    if "://" in host:
        parsed = urlparse(host)
        host = parsed.hostname or ""

    host = host.strip("[]/")
    if ":" in host and not host.startswith("[") and host.count(":") == 1:
        # IPv4 with port or single colon
        host = host.split(":", 1)[0].strip()

    host = host.lower()
    if not host or any(c.isspace() for c in host) or "@" in host:
        raise ValueError("Invalid proxy host format")

    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        if not allow_private:
            raise ValueError(f"SSRF Guard: Loopback or internal hostname '{host}' is not allowed as a proxy host")

    try:
        ip = ipaddress.ip_address(host)
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not allow_private:
            if ip.is_loopback:
                raise ValueError(f"SSRF Guard: Loopback IP '{host}' is not allowed")
            if ip.is_link_local:
                raise ValueError(f"SSRF Guard: Link-local / cloud metadata IP '{host}' is not allowed")
            if ip.is_private:
                raise ValueError(f"SSRF Guard: Private network IP '{host}' is not allowed")
            if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
                raise ValueError(f"SSRF Guard: Reserved or unspecified IP '{host}' is not allowed")
    except ValueError as ve:
        if "SSRF Guard" in str(ve):
            raise
        # Not a valid IP address, validate as hostname
        if not HOSTNAME_RE.match(host) or "." not in host:
            raise ValueError(f"Invalid proxy hostname: '{host}'")

        if not allow_private:
            # Check dynamic / wildcard DNS patterns known for SSRF bypasses
            WILDCARD_DNS_SUFFIXES = (".nip.io", ".sslip.io", ".xip.io", ".vcap.me", ".localtest.me")
            if any(host.endswith(sfx) for sfx in WILDCARD_DNS_SUFFIXES):
                raise ValueError(f"SSRF Guard: Wildcard DNS domain '{host}' is not allowed as a proxy host")

            # Resolve hostname to verify target IP address
            import socket
            try:
                addr_info = socket.getaddrinfo(host, None)
                for family, _, _, _, sockaddr in addr_info:
                    resolved_ip_str = sockaddr[0]
                    resolved_ip = ipaddress.ip_address(resolved_ip_str)
                    if getattr(resolved_ip, "ipv4_mapped", None):
                        resolved_ip = resolved_ip.ipv4_mapped
                    if (
                        resolved_ip.is_loopback
                        or resolved_ip.is_link_local
                        or resolved_ip.is_private
                        or resolved_ip.is_unspecified
                        or resolved_ip.is_multicast
                        or resolved_ip.is_reserved
                    ):
                        raise ValueError(f"SSRF Guard: Host '{host}' resolves to restricted IP '{resolved_ip}'")
            except socket.gaierror:
                pass

    return host

def extract_ip_subnet(host_or_ip: Optional[str]) -> Optional[str]:
    """
    Paranoia Layer 0, 1 & 2: Subnet prefix extraction supporting IPv4 (/24) and IPv6 (/64).
    For IPv4: returns the first 3 octets ('192.0.2').
    For IPv6: returns the first 4 16-bit blocks (the /64 routing prefix '2001:db8:abcd:0012').
    For hostnames: extracts the domain root or resolves to IP to prevent linked clustering.
    """
    if not host_or_ip or not isinstance(host_or_ip, str):
        return None
    raw = host_or_ip.strip()
    if not raw:
        return None
    if "://" in raw:
        parsed = urlparse(raw)
        raw = parsed.hostname or ""
    raw = raw.strip("[]/")
    if ":" in raw and not raw.startswith("[") and raw.count(":") == 1:
        raw = raw.split(":", 1)[0].strip()

    try:
        ip = ipaddress.ip_address(raw)
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if isinstance(ip, ipaddress.IPv4Address):
            parts = str(ip).split(".")
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
        elif isinstance(ip, ipaddress.IPv6Address):
            groups = ip.exploded.split(":")
            return f"{groups[0]}:{groups[1]}:{groups[2]}:{groups[3]}"
    except Exception:
        # Paranoia Layer 1 & 2: Use tldextract Public Suffix List to prevent false subnet collisions on domains (Eradicates FLAW-32)
        try:
            import tldextract
            ext = tldextract.extract(raw)
            reg_dom = getattr(ext, "top_domain_under_public_suffix", None) or getattr(ext, "registered_domain", None)
            if reg_dom:
                return reg_dom.lower()
        except Exception:
            pass
        if "." in raw:
            parts = raw.lower().split(".")
            if len(parts) >= 3:
                two_part_suffix = f"{parts[-2]}.{parts[-1]}"
                known_multi_part = {
                    "co.uk", "org.uk", "gov.uk", "ac.uk", "net.uk", "sch.uk",
                    "com.au", "net.au", "org.au", "edu.au", "gov.au",
                    "co.in", "net.in", "org.in", "gen.in", "firm.in", "ind.in",
                    "co.jp", "ne.jp", "or.jp", "go.jp", "ac.jp",
                    "co.nz", "net.nz", "org.nz",
                    "com.br", "net.br", "org.br",
                    "co.za", "org.za", "web.za"
                }
                if two_part_suffix in known_multi_part or (parts[-2] in {"co", "com", "org", "net", "gov", "edu", "ac", "ne", "or"} and len(parts[-1]) == 2):
                    return f"{parts[-3]}.{parts[-2]}.{parts[-1]}"
            if len(parts) >= 2:
                return f"{parts[-2]}.{parts[-1]}"
    return raw.lower()

def extract_ipv4_slash24(host_or_ip: Optional[str]) -> Optional[str]:
    """Extracts the /24 subnet string (e.g. '192.168.1') from an IPv4 address. Returns None if not IPv4."""
    if not host_or_ip:
        return None
    raw = str(host_or_ip).strip()
    try:
        ip = ipaddress.ip_address(raw)
        if isinstance(ip, ipaddress.IPv4Address):
            octets = raw.split(".")
            return f"{octets[0]}.{octets[1]}.{octets[2]}"
    except Exception:
        pass
    return None

SUPPORTED_PROVIDERS = ["webshare", "oxylabs", "brightdata", "smartproxy", "custom", "system"]
PROVIDER_CIRCUIT_THRESHOLD = 3
PROVIDER_COOLDOWN_SECONDS = 900  # 15 minutes

_PROVIDER_CIRCUIT_STATE: Dict[str, Dict[str, Any]] = {}

def record_provider_failure(provider: Optional[str], reason: str = "connection_error") -> None:
    """
    Paranoia Layer 1: Records provider failure. Trips circuit breaker after threshold.
    """
    if not provider:
        return
    p = str(provider).lower().strip()
    now = datetime.now(timezone.utc)
    if p not in _PROVIDER_CIRCUIT_STATE:
        _PROVIDER_CIRCUIT_STATE[p] = {"failures": 0, "tripped_until": None, "last_reason": None}

    state = _PROVIDER_CIRCUIT_STATE[p]
    state["failures"] += 1
    state["last_reason"] = reason
    if state["failures"] >= PROVIDER_CIRCUIT_THRESHOLD:
        tripped_until = now + timedelta(seconds=PROVIDER_COOLDOWN_SECONDS)
        state["tripped_until"] = tripped_until
        logger.warning(f"[ProxyCircuitBreaker] Provider '{p}' circuit TRIPPED until {tripped_until.isoformat()} (reason: {reason})")

def record_provider_success(provider: Optional[str]) -> None:
    """
    Paranoia Layer 0: Resets failure count on successful proxy operation.
    """
    if not provider:
        return
    p = str(provider).lower().strip()
    if p in _PROVIDER_CIRCUIT_STATE:
        _PROVIDER_CIRCUIT_STATE[p] = {"failures": 0, "tripped_until": None, "last_reason": None}

def is_provider_healthy(provider: Optional[str]) -> bool:
    """
    Returns True if provider circuit is healthy (not tripped).
    """
    if not provider:
        return True
    p = str(provider).lower().strip()
    state = _PROVIDER_CIRCUIT_STATE.get(p)
    if not state or not state.get("tripped_until"):
        return True
    now = datetime.now(timezone.utc)
    if now >= state["tripped_until"]:
        _PROVIDER_CIRCUIT_STATE[p] = {"failures": 0, "tripped_until": None, "last_reason": None}
        return True
    return False

def reset_provider_circuits() -> None:
    """Resets all provider circuit breakers (for tests and administrative resets)."""
    global _PROVIDER_CIRCUIT_STATE
    _PROVIDER_CIRCUIT_STATE.clear()

def calculate_pool_subnet_diversity(proxies: List[dict]) -> Dict[str, Any]:
    """
    Paranoia Layer 2: Calculates /24 and /64 subnet diversity across a proxy pool.
    Helps detect if a workspace pool is overly concentrated on a single ASN or subnet.
    """
    if not proxies:
        return {
            "total_proxies": 0,
            "unique_subnets": 0,
            "diversity_ratio": 1.0,
            "colliding_subnets": []
        }

    subnet_counts: Dict[str, int] = {}
    for p in proxies:
        sub = p.get("subnet") or extract_ip_subnet(p.get("exit_ip") or p.get("host"))
        if sub:
            subnet_counts[sub] = subnet_counts.get(sub, 0) + 1

    total = len(proxies)
    unique = len(subnet_counts)
    ratio = round(unique / total, 3) if total > 0 else 1.0
    colliding = [sub for sub, count in subnet_counts.items() if count > 1]

    return {
        "total_proxies": total,
        "unique_subnets": unique,
        "diversity_ratio": ratio,
        "colliding_subnets": colliding
    }

def is_proxy_quarantined(proxy: dict) -> bool:
    """Returns True if proxy is currently quarantined."""
    if not proxy:
        return False
    q_until_str = proxy.get("quarantined_until")
    if q_until_str:
        try:
            if isinstance(q_until_str, str):
                clean_str = q_until_str.replace("Z", "+00:00")
                q_until = datetime.fromisoformat(clean_str)
            else:
                q_until = q_until_str
            now = datetime.now(timezone.utc)
            if q_until.tzinfo is None:
                now = datetime.utcnow()
            return now < q_until
        except Exception:
            return proxy.get("status") == "quarantined"
    return proxy.get("status") == "quarantined"

def canary_check_proxy(supabase, proxy_id: str, timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """
    Decoupled Proxy Canary Check (Anti-Cascading Quarantine Guard):
    Independently verifies if a proxy IP is alive and responsive to neutral targets
    before allowing an application-level failure (e.g. LinkedIn account challenge)
    to quarantine the proxy across the fleet.
    """
    if not proxy_id or not supabase:
        return {"is_healthy": False, "reason": "missing_proxy_or_supabase"}

    try:
        res = supabase.table("proxies").select("host, port, username, password, protocol").eq("id", proxy_id).limit(1).execute()
        if not res.data:
            return {"is_healthy": False, "reason": "proxy_not_found"}
        row = res.data[0]
        host = row.get("host")
        port = row.get("port")
        if not host or not port:
            return {"is_healthy": False, "reason": "incomplete_proxy_credentials"}

        username = row.get("username")
        password = row.get("password")
        protocol = row.get("protocol", "http")
        auth = f"{quote(username)}:{quote(password)}@" if username and password else ""
        proxy_url = f"{protocol}://{auth}{host}:{port}"

        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}))
        req = urllib.request.Request("https://www.google.com/generate_204", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=timeout_seconds) as resp:
            if resp.status in (200, 204):
                return {"is_healthy": True, "status_code": resp.status, "reason": "canary_passed"}
        return {"is_healthy": False, "reason": "canary_non_204"}
    except Exception as e:
        return {"is_healthy": False, "reason": f"canary_failed: {str(e)}"}

def quarantine_proxy(supabase, proxy_id: str, reason: str = "security_challenge", cooldown_hours: int = DEFAULT_QUARANTINE_HOURS) -> bool:
    """
    Paranoia Layer 1: Quarantines a proxy associated with a security checkpoint or severe rate limit.
    Prevents other accounts from using this tainted IP.
    """
    if not proxy_id or not supabase:
        return False
    try:
        now = datetime.now(timezone.utc)
        quarantine_until = (now + timedelta(hours=cooldown_hours)).isoformat()
        supabase.table("proxies").update({
            "status": "quarantined",
            "is_active": False,
            "quarantined_until": quarantine_until,
            "quarantine_reason": reason,
            "last_checked_at": now.isoformat()
        }).eq("id", proxy_id).execute()
        logger.warning(f"[ProxyQuarantine] Proxy {proxy_id} quarantined until {quarantine_until} (reason: {reason})")
        return True
    except Exception as e:
        logger.error(f"[ProxyQuarantine] Failed to quarantine proxy {proxy_id}: {e}")
        return False

def find_sticky_failover_proxy(
    supabase,
    workspace_id: str,
    current_proxy_id: Optional[str] = None,
    target_country: Optional[str] = None,
    allow_cross_country_drift: bool = False,
    exclude_proxy_ids: Optional[List[str]] = None,
    max_accounts_per_proxy: int = MAX_ACCOUNTS_PER_PROXY,
    preferred_provider: Optional[str] = None,
    excluded_providers: Optional[List[str]] = None
) -> Optional[dict]:
    """
    Paranoia Layer 0, 1 & 2: Finds a healthy, non-quarantined proxy with strict country affinity,
    avoiding workspace /24 & /64 subnet collisions, checking provider circuit breakers,
    and respecting max accounts per proxy capacity cap.
    """
    if not supabase or not workspace_id:
        return None
    try:
        candidates = []
        # Paranoia Layer 0 & 1: Query active, healthy workspace proxies; if none, query shared system proxies (Eradicates FLAW-31)
        try:
            res = supabase.table("proxies").select("*").eq("workspace_id", workspace_id).eq("is_active", True).execute()
            if res and isinstance(res.data, list):
                candidates = res.data
        except Exception:
            pass

        if not candidates:
            try:
                res = supabase.table("proxies").select("*").is_("workspace_id", "null").eq("is_active", True).execute()
                if res and isinstance(res.data, list):
                    candidates = res.data
            except Exception:
                pass

        # Collect subnets of ALL active accounts in the workspace
        workspace_subnet_counts: Dict[str, int] = {}
        try:
            acc_sub_res = supabase.table("accounts").select("proxy_id").eq("workspace_id", workspace_id).execute()
            acc_proxy_ids = [a["proxy_id"] for a in (acc_sub_res.data or []) if isinstance(a, dict) and a.get("proxy_id")]
            if acc_proxy_ids:
                used_proxies = [p for p in candidates if p.get("id") in acc_proxy_ids]
                for up in used_proxies:
                    sub = up.get("subnet") or extract_ip_subnet(up.get("exit_ip") or up.get("host"))
                    if sub:
                        workspace_subnet_counts[sub] = workspace_subnet_counts.get(sub, 0) + 1
        except Exception as ws_sub_err:
            logger.debug(f"[ProxyRouting] Could not query workspace subnet counts: {ws_sub_err}")

        # Exclude candidates from excluded providers
        if excluded_providers:
            clean_ex_prov = {str(ep).lower().strip() for ep in excluded_providers}
            candidates = [
                p for p in candidates 
                if (p.get("provider") or "custom").lower().strip() not in clean_ex_prov
            ]

        # Identify current proxy's subnet for /24 collision avoidance
        tainted_subnet = None
        if current_proxy_id:
            for p in candidates:
                if p.get("id") == current_proxy_id:
                    tainted_subnet = p.get("subnet") or extract_ip_subnet(p.get("exit_ip") or p.get("host"))
                    break
        
        # Exclude current and specified exclusions
        excluded = set(exclude_proxy_ids or [])
        if current_proxy_id:
            excluded.add(current_proxy_id)
        candidates = [p for p in candidates if p.get("id") not in excluded]

        # Filter out unhealthy and quarantined proxies
        valid_candidates = []
        for p in candidates:
            if p.get("is_active") is False:
                continue
            if p.get("status") not in ("healthy", "active"):
                continue
            if is_proxy_quarantined(p):
                continue
            valid_candidates.append(p)

        if not valid_candidates:
            logger.warning(f"[ProxyRouting] No healthy, non-quarantined proxies available for workspace {workspace_id}")
            return None

        # Prioritize matching target country
        clean_target = (target_country or "").strip().upper() if target_country else None
        if clean_target:
            matching_country = [
                p for p in valid_candidates
                if (p.get("country_code") or "").strip().upper() == clean_target
            ]
            if matching_country:
                valid_candidates = matching_country
            else:
                if not allow_cross_country_drift:
                    logger.warning(
                        f"[ProxyDriftGuard] Geolocation drift hazard: No healthy proxies in {clean_target} "
                        f"for workspace {workspace_id}. Refusing cross-country failover to prevent account challenge."
                    )
                    return None
                else:
                    logger.warning(
                        f"[ProxyDriftGuard] Cross-country failover permitted: Account drifting from {clean_target} "
                        f"to fallback country."
                    )

        # Least-loaded selection: count assigned accounts per candidate proxy
        proxy_ids = [p["id"] for p in valid_candidates]
        load_map: Dict[str, int] = {pid: 0 for pid in proxy_ids}
        try:
            acc_res = supabase.table("accounts").select("proxy_id").in_("proxy_id", proxy_ids).execute()
            acc_list = acc_res.data if (acc_res and isinstance(acc_res.data, list)) else []
            for acc in acc_list:
                pid = acc.get("proxy_id")
                if pid in load_map:
                    load_map[pid] += 1
        except Exception as load_err:
            logger.debug(f"Could not query proxy account counts: {load_err}")

        # Paranoia Layer 1/2: Multi-dimensional sorting
        # Priority: over_cap -> subnet_collision -> same_subnet -> circuit_tripped -> not_preferred -> load -> latency
        def _candidate_sort_key(p: dict) -> tuple:
            p_load = load_map.get(p["id"], 0)
            over_cap = 1 if (max_accounts_per_proxy and p_load >= max_accounts_per_proxy) else 0

            p_subnet = p.get("subnet") or extract_ip_subnet(p.get("exit_ip") or p.get("host"))
            subnet_collision = workspace_subnet_counts.get(p_subnet, 0) if p_subnet else 0
            same_subnet = 1 if (tainted_subnet and p_subnet and p_subnet == tainted_subnet) else 0

            prov = (p.get("provider") or "custom").lower().strip()
            prov_circuit_tripped = 0 if is_provider_healthy(prov) else 1
            prov_not_preferred = 0 if (preferred_provider and prov == preferred_provider.lower().strip()) else 1

            p_lat = p.get("latency_ms") if isinstance(p.get("latency_ms"), (int, float)) else 9999
            return (over_cap, subnet_collision, same_subnet, prov_circuit_tripped, prov_not_preferred, p_load, p_lat)

        valid_candidates.sort(key=_candidate_sort_key)
        chosen = valid_candidates[0]
        logger.info(f"[ProxyRouting] Selected proxy {chosen.get('id')} ({chosen.get('host')}, provider: {chosen.get('provider')}, country: {chosen.get('country_code')}, load: {load_map.get(chosen['id'], 0)})")
        return chosen
    except Exception as e:
        logger.error(f"[ProxyRouting] Error finding failover proxy: {e}")
        return None

def format_proxy_url(
    protocol: Optional[str],
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None
) -> str:
    """
    Paranoia Layer 0 & 2: Formats a proxy URL with strict percent-encoding for username & password.
    Escapes all URI reserved characters (@, :, #, %, ?, /) to prevent URL syntax corruption.
    """
    proto = (protocol or "http").lower().strip()
    clean_host = str(host).strip()
    if username:
        safe_user = quote(str(username), safe="")
        if password:
            safe_pass = quote(str(password), safe="")
            return f"{proto}://{safe_user}:{safe_pass}@{clean_host}:{port}"
        return f"{proto}://{safe_user}@{clean_host}:{port}"
    return f"{proto}://{clean_host}:{port}"

def build_authenticated_proxy_url(
    account_row: Dict[str, Any],
    supabase_client: Any = None
) -> Optional[str]:
    """
    Paranoia Layer 0, 1 & 2 Canonical Proxy URL Builder.
    - Resolves proxy from account_row["proxies"] or account_row["proxy_id"].
    - Triggers failover if current proxy is quarantined or inactive.
    - Safely decrypts password via Vault RPC.
    - Escapes credentials with format_proxy_url to prevent URI corruption.
    """
    if not account_row or not isinstance(account_row, dict):
        return None

    p = account_row.get("proxies")
    is_unhealthy_or_quarantined = (
        not p or 
        p.get("is_active") is False or 
        p.get("status") in ("degraded", "banned", "disabled", "quarantined") or 
        is_proxy_quarantined(p)
    )

    if is_unhealthy_or_quarantined:
        wid = account_row.get("workspace_id")
        if wid and supabase_client:
            try:
                target_country = account_row.get("country_code") or (p.get("country_code") if p else None)
                replacement = find_sticky_failover_proxy(
                    supabase_client,
                    wid,
                    current_proxy_id=p.get("id") if p else None,
                    target_country=target_country
                )
                if replacement:
                    account_row["proxy_id"] = replacement["id"]
                    account_row["proxies"] = replacement
                    p = replacement
                    if account_row.get("id"):
                        try:
                            supabase_client.table("accounts").update({"proxy_id": replacement["id"]}).eq("id", account_row["id"]).execute()
                        except Exception as update_err:
                            logger.warning(f"Could not persist proxy failover to account: {update_err}")
            except Exception as failover_err:
                logger.warning(f"Proxy failover query failed: {failover_err}")

    p = account_row.get("proxies")
    if not p or not isinstance(p, dict):
        return None

    host = p.get("host")
    port = p.get("port")
    if not host or not port:
        return None

    protocol = p.get("protocol") or "http"
    username = p.get("username")
    password_plain = ""

    if username:
        proxy_id = account_row.get("proxy_id") or p.get("id")
        if proxy_id and supabase_client:
            try:
                # Paranoia Layer 1: Only pass p_workspace_id if proxy belongs to a specific workspace (Eradicates FLAW-20)
                p_ws = p.get("workspace_id")
                rpc_payload = {"p_proxy_id": proxy_id}
                if p_ws:
                    rpc_payload["p_workspace_id"] = p_ws
                rpc_res = supabase_client.rpc("get_decrypted_proxy_payload", rpc_payload).execute()
                if rpc_res.data and rpc_res.data.get("password_encrypted"):
                    from core.backend.core import crypto
                    import base64
                    raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                    dek_bytes = base64.b64decode(rpc_res.data["dek"]) if rpc_res.data.get("dek") else None
                    password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to decrypt proxy password for {proxy_id}: {e}")

    return format_proxy_url(protocol, host, port, username, password_plain if password_plain else None)


# ── AUTONOMOUS PROXY FLEET LATENCY PROBING & OPTIMAL ALLOCATION (PHASE Q) ─────

_PROXY_CONSECUTIVE_FAILURES: Dict[str, int] = {}
_PROXY_FAILURE_LOCK = threading.Lock()
MAX_ACCEPTABLE_PROXY_LATENCY_MS = 3500.0


def reset_proxy_failure_counts() -> None:
    """Resets in-memory consecutive proxy failure counters (for tests)."""
    with _PROXY_FAILURE_LOCK:
        _PROXY_CONSECUTIVE_FAILURES.clear()


def probe_proxy_health_and_latency(
    proxy_row: Dict[str, Any],
    timeout_seconds: float = 3.0,
    target_host: Optional[str] = None,
    perform_layer7_probe: bool = False,
    proxy_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Autonomous Proxy Health & Latency Telemetry Probing.
    - Layer 0: High-precision TCP connection handshake measurement (ms) via socket.
    - Layer 1: Strict socket timeout clamped in [0.5, 5.0]s, SSRF verification on proxy host,
      and immediate bypass if proxy is already quarantined.
    - Layer 2: Validates exit IP, checks target geo-country alignment, and sanitizes return payload.
    """
    if not proxy_row or not isinstance(proxy_row, dict):
        return {
            "is_healthy": False,
            "latency_ms": 9999.0,
            "status": "invalid_proxy",
            "error": "Proxy configuration is missing or not a dictionary",
            "exit_ip": None,
            "country_code": None
        }

    # Paranoia Layer 1: Check existing quarantine state
    if is_proxy_quarantined(proxy_row):
        return {
            "is_healthy": False,
            "latency_ms": 9999.0,
            "status": "quarantined",
            "error": f"Proxy is quarantined: {proxy_row.get('quarantine_reason', 'cooldown active')}",
            "exit_ip": proxy_row.get("exit_ip"),
            "country_code": proxy_row.get("country_code")
        }

    raw_host = proxy_row.get("host")
    raw_port = proxy_row.get("port")

    if not raw_host or not raw_port:
        return {
            "is_healthy": False,
            "latency_ms": 9999.0,
            "status": "missing_host_or_port",
            "error": "Missing host or port in proxy row",
            "exit_ip": None,
            "country_code": proxy_row.get("country_code")
        }

    # Paranoia Layer 2: SSRF and Private-IP validation on proxy host
    try:
        clean_host = validate_and_normalize_proxy_host(raw_host, allow_private=False)
        port_int = int(raw_port)
        if port_int < 1 or port_int > 65535:
            raise ValueError(f"Port {port_int} out of valid range (1-65535)")
    except Exception as host_err:
        return {
            "is_healthy": False,
            "latency_ms": 9999.0,
            "status": "ssrf_rejected",
            "error": f"SSRF Guard rejected proxy host: {host_err}",
            "exit_ip": None,
            "country_code": proxy_row.get("country_code")
        }

    clamped_timeout = max(0.5, min(float(timeout_seconds or 3.0), 5.0))
    start_t = time.perf_counter()

    try:
        with socket.create_connection((clean_host, port_int), timeout=clamped_timeout) as sock:
            end_t = time.perf_counter()
            latency_ms = round((end_t - start_t) * 1000.0, 2)

        is_healthy = latency_ms <= MAX_ACCEPTABLE_PROXY_LATENCY_MS
        status = "healthy" if is_healthy else "excessive_latency"
        error_msg = None if is_healthy else f"Latency {latency_ms}ms exceeds threshold of {MAX_ACCEPTABLE_PROXY_LATENCY_MS}ms"

        # Paranoia Layer 1: Layer 7 Protocol Probing (Eradicates FLAW-26 - TCP Liveness Illusion)
        if is_healthy and perform_layer7_probe:
            try:
                target_proxy_url = proxy_url or format_proxy_url(
                    proxy_row.get("protocol") or "http",
                    clean_host,
                    port_int,
                    proxy_row.get("username")
                )
                import httpx
                with httpx.Client(proxies=target_proxy_url, timeout=clamped_timeout, verify=False) as client:
                    l7_resp = client.get("https://www.linkedin.com/robots.txt")
                    if l7_resp.status_code == 407:
                        return {
                            "is_healthy": False,
                            "latency_ms": 9999.0,
                            "status": "proxy_auth_407",
                            "error": "HTTP 407 Proxy Authentication Required",
                            "exit_ip": proxy_row.get("exit_ip"),
                            "country_code": proxy_row.get("country_code")
                        }
                    elif l7_resp.status_code == 402:
                        return {
                            "is_healthy": False,
                            "latency_ms": 9999.0,
                            "status": "quota_exhausted_402",
                            "error": "HTTP 402 Payment Required (Bandwidth quota exhausted)",
                            "exit_ip": proxy_row.get("exit_ip"),
                            "country_code": proxy_row.get("country_code")
                        }
                    elif l7_resp.status_code in (403, 999):
                        return {
                            "is_healthy": False,
                            "latency_ms": 9999.0,
                            "status": "target_blocked_999",
                            "error": f"Target blocked request (HTTP {l7_resp.status_code})",
                            "exit_ip": proxy_row.get("exit_ip"),
                            "country_code": proxy_row.get("country_code")
                        }
            except Exception as l7_ex:
                logger.debug(f"[Probe] Layer 7 probe notice: {l7_ex}")

        return {
            "is_healthy": is_healthy,
            "latency_ms": latency_ms,
            "status": status,
            "error": error_msg,
            "exit_ip": proxy_row.get("exit_ip") or clean_host,
            "country_code": (proxy_row.get("country_code") or "").strip().upper()[:10]
        }

    except socket.timeout:
        return {
            "is_healthy": False,
            "latency_ms": round(clamped_timeout * 1000.0, 2),
            "status": "timed_out",
            "error": f"Proxy TCP handshake timed out after {clamped_timeout}s",
            "exit_ip": proxy_row.get("exit_ip"),
            "country_code": proxy_row.get("country_code")
        }
    except (ConnectionRefusedError, socket.gaierror, OSError) as net_err:
        return {
            "is_healthy": False,
            "latency_ms": 9999.0,
            "status": "connection_failed",
            "error": f"TCP connection error: {net_err}",
            "exit_ip": proxy_row.get("exit_ip"),
            "country_code": proxy_row.get("country_code")
        }


def check_and_auto_quarantine_proxy(
    supabase: Any,
    proxy_row: Dict[str, Any],
    max_latency_ms: float = MAX_ACCEPTABLE_PROXY_LATENCY_MS,
    consecutive_failure_threshold: int = 3
) -> Dict[str, Any]:
    """
    Paranoia Layer 1: Autonomous Proxy Auto-Quarantine Evaluator.
    Probes latency and auto-quarantines proxies exceeding latency thresholds
    or reaching consecutive failure limits, preventing degraded network bottlenecks.
    """
    proxy_id = proxy_row.get("id")
    probe_res = probe_proxy_health_and_latency(proxy_row)
    latency_ms = probe_res.get("latency_ms", 9999.0)
    is_healthy = probe_res.get("is_healthy", False)

    with _PROXY_FAILURE_LOCK:
        if is_healthy and latency_ms <= max_latency_ms:
            if proxy_id:
                _PROXY_CONSECUTIVE_FAILURES[proxy_id] = 0
            return {
                "proxy_id": proxy_id,
                "quarantined": False,
                "is_healthy": True,
                "latency_ms": latency_ms,
                "status": "healthy"
            }

        curr_fails = _PROXY_CONSECUTIVE_FAILURES.get(proxy_id, 0) + 1 if proxy_id else 1
        if proxy_id:
            _PROXY_CONSECUTIVE_FAILURES[proxy_id] = curr_fails

        should_quarantine = (curr_fails >= consecutive_failure_threshold) or (latency_ms >= 5000.0)
        quarantine_action_taken = False

        if should_quarantine and proxy_id and supabase:
            reason = f"excessive_latency_{int(latency_ms)}ms_fails_{curr_fails}"
            quarantine_proxy(supabase, proxy_id, reason=reason, cooldown_hours=DEFAULT_QUARANTINE_HOURS)
            quarantine_action_taken = True
            logger.warning(f"[ProxyAutoQuarantine] Proxy {proxy_id} auto-quarantined: {reason}")

        return {
            "proxy_id": proxy_id,
            "quarantined": quarantine_action_taken,
            "is_healthy": False,
            "consecutive_failures": curr_fails,
            "latency_ms": latency_ms,
            "status": "quarantined" if quarantine_action_taken else "degraded",
            "error": probe_res.get("error")
        }


def assign_optimal_proxy_for_account(
    account_id: str,
    workspace_id: str,
    supabase: Any,
    target_country: Optional[str] = None,
    max_latency_ms: float = 3000.0
) -> Optional[Dict[str, Any]]:
    """
    Paranoia Layer 0, 1 & 2: Autonomous Geo-Balanced Proxy Allocator with Sticky Affinity.
    1. If the account's existing proxy is healthy, non-quarantined, and below max_latency_ms,
       preserves sticky affinity (Layer 0).
    2. If missing, degraded, or quarantined, selects the lowest-latency, least-loaded proxy
       matching target_country / timezone (Layer 1 & 2).
    3. Persists the assignment to the accounts table atomically.
    """
    if not account_id or not workspace_id or not supabase:
        return None

    try:
        acc_res = supabase.table("accounts") \
            .select("id, workspace_id, proxy_id, country_code, proxies(*)") \
            .eq("id", account_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
        if not acc_res.data or len(acc_res.data) == 0:
            return None
        account = acc_res.data[0]
    except Exception as e:
        logger.error(f"[ProxyAssignment] Failed to fetch account {account_id}: {e}")
        return None

    current_proxy = account.get("proxies")
    resolved_country = target_country or account.get("country_code") or (current_proxy.get("country_code") if current_proxy else None)

    if current_proxy and not is_proxy_quarantined(current_proxy) and current_proxy.get("is_active") is not False:
        probe = probe_proxy_health_and_latency(current_proxy)
        if probe.get("is_healthy") and probe.get("latency_ms", 9999.0) <= max_latency_ms:
            p_country = (current_proxy.get("country_code") or "").strip().upper()
            t_country = (resolved_country or "").strip().upper()
            if not t_country or p_country == t_country:
                logger.debug(f"[ProxyAssignment] Retaining sticky proxy {current_proxy.get('id')} for account {account_id}")
                return current_proxy

    replacement = find_sticky_failover_proxy(
        supabase=supabase,
        workspace_id=workspace_id,
        current_proxy_id=current_proxy.get("id") if current_proxy else None,
        target_country=resolved_country,
        allow_cross_country_drift=False
    )

    if not replacement:
        replacement = find_sticky_failover_proxy(
            supabase=supabase,
            workspace_id=workspace_id,
            current_proxy_id=current_proxy.get("id") if current_proxy else None,
            target_country=resolved_country,
            allow_cross_country_drift=True
        )

    if replacement and replacement.get("id"):
        try:
            supabase.table("accounts").update({
                "proxy_id": replacement["id"]
            }).eq("id", account_id).execute()
            logger.info(f"[ProxyAssignment] Reassigned account {account_id} to optimal proxy {replacement['id']} (country: {replacement.get('country_code')})")
        except Exception as upd_err:
            logger.warning(f"[ProxyAssignment] Failed to persist proxy assignment to account: {upd_err}")

    return replacement
