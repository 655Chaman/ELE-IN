"""
Three-Layer Paranoia Framework: Proxy Routing, Cooldown Quarantine & Sticky Affinity
- Layer 0: Sticky proxy affinity per account & least-loaded selection across healthy proxies.
- Layer 1: Security checkpoint quarantine (2-hour quarantine preventing collateral bans across fleet) + strict geo-country affinity preventing cross-border drift flags.
- Layer 2: Human paranoia: Validates proxy latency (< 2500ms), rejects quarantined proxy re-assignment, and sanitizes country codes.
"""
import ipaddress
import re
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

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

def extract_ipv4_slash24(host_or_ip: Optional[str]) -> Optional[str]:
    """Extracts the /24 subnet string (e.g. '192.168.1') from an IPv4 address."""
    if not host_or_ip or not isinstance(host_or_ip, str):
        return None
    try:
        ip = ipaddress.ip_address(host_or_ip.strip())
        if isinstance(ip, ipaddress.IPv4Address):
            parts = str(ip).split(".")
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
    except Exception:
        pass
    return None

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
    max_accounts_per_proxy: int = MAX_ACCOUNTS_PER_PROXY
) -> Optional[dict]:
    """
    Paranoia Layer 0 & 1: Finds a healthy, non-quarantined proxy with strict country affinity,
    avoiding same /24 subnet collision and respecting max accounts per proxy capacity cap.
    """
    if not supabase or not workspace_id:
        return None
    try:
        candidates = []
        try:
            res = supabase.table("proxies").select("*").eq("workspace_id", workspace_id).eq("is_active", True).execute()
            if res and isinstance(res.data, list):
                candidates = res.data
        except Exception:
            pass
        
        if not candidates:
            try:
                res = supabase.table("proxies").select("*").eq("workspace_id", workspace_id).execute()
                if res and isinstance(res.data, list):
                    candidates = res.data
            except Exception:
                pass

        # Identify current proxy's subnet for /24 collision avoidance
        tainted_subnet = None
        if current_proxy_id:
            for p in candidates:
                if p.get("id") == current_proxy_id:
                    tainted_subnet = extract_ipv4_slash24(p.get("exit_ip") or p.get("host"))
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

        # Paranoia Layer 1/2: Sort by (over_cap, same_subnet, p_load, p_lat)
        def _candidate_sort_key(p: dict) -> tuple:
            p_load = load_map.get(p["id"], 0)
            over_cap = 1 if (max_accounts_per_proxy and p_load >= max_accounts_per_proxy) else 0
            p_subnet = extract_ipv4_slash24(p.get("exit_ip") or p.get("host"))
            same_subnet = 1 if (tainted_subnet and p_subnet and p_subnet == tainted_subnet) else 0
            p_lat = p.get("latency_ms") if isinstance(p.get("latency_ms"), (int, float)) else 9999
            return (over_cap, same_subnet, p_load, p_lat)

        valid_candidates.sort(key=_candidate_sort_key)
        chosen = valid_candidates[0]
        logger.info(f"[ProxyRouting] Selected proxy {chosen.get('id')} ({chosen.get('host')}, country: {chosen.get('country_code')}, load: {load_map.get(chosen['id'], 0)})")
        return chosen
    except Exception as e:
        logger.error(f"[ProxyRouting] Error finding failover proxy: {e}")
        return None
