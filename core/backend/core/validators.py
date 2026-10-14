import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

DISALLOWED_NETWORKS = [
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT (RFC 6598)
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("169.254.0.0/16"),   # IPv4 Link-Local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local Address
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "metadata.azure.com",
    "metadata",
    "host.docker.internal",
}

BLOCKED_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
    ".onion",
    ".lan",
    ".home",
    ".corp",
)


NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _is_ip_disallowed(ip: ipaddress._BaseAddress) -> bool:
    """Paranoia Layer 1: Detect and reject private, loopback, link-local, multicast, or reserved IPs."""
    # Unwrap IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    elif ip.version == 6 and ip in NAT64_PREFIX:
        # Unwrap RFC 6052 NAT64 well-known prefix into underlying IPv4 address
        ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    for net in DISALLOWED_NETWORKS:
        if ip in net:
            return True

    return False


def is_safe_ssrf_url(url: str) -> bool:
    """
    Paranoia Framework: Three-Layer SSRF and Protocol Exploit Validator.
    - Layer 0: Schema and structure verification (http/https only, hostname required).
    - Layer 1: IP range containment, cloud metadata blocking, and DNS resolution validation.
    - Layer 2: Authority confusion prevention, user-info stripping, and CRLF / null-byte defense.
    """
    if not url or not isinstance(url, str):
        return False

    # Layer 2: Reject control character, CRLF or null-byte injections
    if any(c in url for c in ("\r", "\n", "\t", "\0")):
        return False

    try:
        clean_url = url.strip()
        parsed = urlparse(clean_url)

        # Layer 0: Enforce HTTP/HTTPS only
        if parsed.scheme not in ["http", "https"]:
            return False

        # Layer 2: Disallow credentials in authority (prevents user-info confusion attacks)
        if parsed.username or parsed.password:
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        host_clean = hostname.lower().strip("[]").rstrip(".")

        # Layer 1: Block known metadata endpoints and internal domain suffixes
        if host_clean in BLOCKED_HOSTNAMES:
            return False

        if any(host_clean.endswith(sfx) for sfx in BLOCKED_SUFFIXES):
            return False

        # Layer 1: Direct IP inspection (without requiring DNS)
        try:
            direct_ip = ipaddress.ip_address(host_clean)
            if _is_ip_disallowed(direct_ip):
                return False
        except ValueError:
            pass

        # Layer 1: DNS resolution validation
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip = ipaddress.ip_address(info[4][0])
                if _is_ip_disallowed(ip):
                    return False
        except socket.gaierror:
            return False  # Unresolvable domains rejected

        return True
    except Exception:
        return False

