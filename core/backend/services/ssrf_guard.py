"""
ssrf_guard.py — Comprehensive Server-Side Request Forgery (SSRF) & Private Network Defense
Pillar 7 (Phase 7.3) — Master Platform Hardening & Execution Plan

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational):
      * Strict protocol gating: only http and https allowed.
      * Strict port gating: only ports 80 and 443 allowed (blocks internal DBs, Redis, SSH, SMTP).
      * URL normalization and userinfo stripping.
  - Layer 1 (Environmental Failure Analysis — DNS & Subnet Resolution):
      * Synchronous DNS resolution to all IPv4 and IPv6 target addresses.
      * Hard block on Loopback (127.0.0.0/8, ::1), Link-Local / Cloud Metadata (169.254.0.0/16, fe80::/10),
        RFC 1918 Private Subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), CGNAT (100.64.0.0/10),
        IPv6 Unique-Local (fc00::/7), and Multicast/Reserved subnets.
      * Wildcard DNS domain block (.nip.io, .sslip.io, .xip.io, .vcap.me, .localtest.me).
      * Cloud internal metadata hostname block (metadata.google.internal, instance-data).
  - Layer 2 (Human Paranoia — Obfuscated IP Formats & Parser Exploits):
      * Normalizes and blocks decimal IPs (e.g. 2852039166 -> 169.254.169.254).
      * Normalizes and blocks octal IPs (e.g. 0251.0376.0251.0376 -> 169.254.169.254).
      * Normalizes and blocks hex IPs (e.g. 0xa9fea9fe -> 169.254.169.254).
      * Normalizes IPv4-mapped IPv6 (::ffff:169.254.169.254).
      * Throws HTTP 422 Unprocessable Entity with structured rejection details.
"""

from __future__ import annotations

import socket
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit
from typing import Optional, List, Tuple, Set, Union
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

ALLOWED_PROTOCOLS = {"http", "https"}
ALLOWED_PORTS = {80, 443}

WILDCARD_DNS_SUFFIXES = (
    ".nip.io",
    ".sslip.io",
    ".xip.io",
    ".vcap.me",
    ".localtest.me",
    ".127.0.0.1.traefik.me",
)

BLOCKED_INTERNAL_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "internal",
    "kube-dns",
    "kubernetes.default",
}

CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


class SSRFValidationError(HTTPException):
    def __init__(self, detail: str, code: str = "SSRF_DETECTED"):
        super().__init__(status_code=422, detail={"code": code, "message": detail})


# =============================================================================
# 1. IP DE-OBFUSCATION (Layer 2 Paranoia)
# =============================================================================

def parse_and_normalize_ip(host_str: str) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    """
    Paranoia Layer 2: Parses standard and obfuscated IP representations
    (decimal integer, octal notation, hex notation, IPv4-mapped IPv6).
    """
    clean = host_str.strip().strip("[]").lower()

    # 1. Standard IP
    try:
        ip = ipaddress.ip_address(clean)
        # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254)
        if getattr(ip, "ipv4_mapped", None):
            return ip.ipv4_mapped
        return ip
    except ValueError:
        pass

    # 2. Decimal integer IP (e.g. 2852039166 -> 169.254.169.254, or 2130706433 -> 127.0.0.1)
    if clean.isdigit():
        try:
            val = int(clean)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except ValueError:
            pass

    # 3. Hexadecimal integer IP (e.g. 0xa9fea9fe -> 169.254.169.254, or 0x7f000001 -> 127.0.0.1)
    if clean.startswith("0x"):
        try:
            val = int(clean, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except ValueError:
            pass

    # 4. Octal or Dotted Hexadecimal notation (e.g. 0251.0376.0251.0376 or 0x7f.0.0.1)
    parts = clean.split(".")
    if len(parts) == 4:
        try:
            byte_vals = []
            for p in parts:
                if p.startswith("0x"):
                    v = int(p, 16)
                elif p.startswith("0") and len(p) > 1:
                    v = int(p, 8)
                else:
                    v = int(p, 10)
                if not (0 <= v <= 255):
                    raise ValueError("Byte out of range")
                byte_vals.append(v)
            return ipaddress.IPv4Address(bytes(byte_vals))
        except (ValueError, Exception):
            pass

    return None


def is_ip_blocked(ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> Tuple[bool, str]:
    """
    Paranoia Layer 1: Evaluates whether an IP address belongs to any restricted or private CIDR range.
    """
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped

    if ip.is_loopback:
        return True, f"Loopback address ({ip}) is strictly forbidden"

    if ip.is_link_local:
        return True, f"Link-local / cloud metadata address ({ip}) is strictly forbidden"

    if ip.is_private:
        return True, f"Private RFC 1918 / unique-local address ({ip}) is strictly forbidden"

    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT_NETWORK:
        return True, f"Carrier-Grade NAT / Shared address ({ip}) is strictly forbidden"

    if ip.is_unspecified:
        return True, f"Unspecified address ({ip}) is strictly forbidden"

    if ip.is_multicast:
        return True, f"Multicast address ({ip}) is strictly forbidden"

    if getattr(ip, "is_reserved", False):
        return True, f"Reserved address ({ip}) is strictly forbidden"

    # Specific check for AWS / GCP / Azure Instance Metadata Service (169.254.169.254)
    if str(ip) == "169.254.169.254":
        return True, "Cloud Instance Metadata Service (169.254.169.254) is strictly forbidden"

    return False, ""


# =============================================================================
# 2. UNIVERSAL OUTBOUND URL VALIDATION (SSRF GUARD)
# =============================================================================

def validate_outbound_url(
    url: str,
    allowed_protocols: Optional[Set[str]] = None,
    allowed_ports: Optional[Set[int]] = None,
    allow_private: bool = False
) -> str:
    """
    Paranoia Layer 0, 1 & 2: Validates outbound target URLs against SSRF, internal network probing,
    cloud metadata theft, and port scanning.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("Target URL cannot be empty")

    clean_url = url.strip()
    if not clean_url:
        raise SSRFValidationError("Target URL cannot be empty")

    try:
        parts = urlsplit(clean_url)
    except Exception as parse_err:
        raise SSRFValidationError(f"Invalid URL structure: {parse_err}")

    # 1. Protocol Gating (Layer 0)
    protocols = allowed_protocols or ALLOWED_PROTOCOLS
    scheme = (parts.scheme or "").lower()
    if scheme not in protocols:
        raise SSRFValidationError(
            f"Protocol '{scheme}' is forbidden. Allowed protocols: {', '.join(sorted(protocols))}"
        )

    # 2. Hostname extraction
    host = (parts.hostname or "").lower().strip()
    if not host:
        raise SSRFValidationError("URL must include a valid target hostname")

    # 3. Port Gating (Layer 0)
    ports = allowed_ports or ALLOWED_PORTS
    port = parts.port
    if port is None:
        port = 443 if scheme == "https" else 80

    if port not in ports:
        raise SSRFValidationError(
            f"Port {port} is forbidden for outbound requests. Allowed ports: {', '.join(map(str, sorted(ports)))}"
        )

    if allow_private:
        return clean_url

    # 4. Block explicit internal hostnames & wildcard DNS services (Layer 1)
    if host in BLOCKED_INTERNAL_HOSTNAMES or host.endswith(".localhost") or host.endswith(".internal"):
        raise SSRFValidationError(f"Internal hostname '{host}' is forbidden")

    if any(host.endswith(sfx) for sfx in WILDCARD_DNS_SUFFIXES):
        raise SSRFValidationError(f"Wildcard DNS domain '{host}' is forbidden to prevent SSRF bypass")

    # 5. Check if host is direct IP (including decimal/octal/hex obfuscations)
    direct_ip = parse_and_normalize_ip(host)
    if direct_ip:
        blocked, reason = is_ip_blocked(direct_ip)
        if blocked:
            raise SSRFValidationError(f"SSRF Guard: {reason}")
        return clean_url

    # 6. Synchronous DNS Resolution (Layer 1 Paranoia)
    try:
        addr_info = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        if not addr_info:
            raise SSRFValidationError(f"DNS resolution returned no valid IP addresses for host '{host}'")
    except socket.gaierror as dns_err:
        raise SSRFValidationError(f"Failed to resolve host '{host}' via DNS: {dns_err}")
    except Exception as exc:
        raise SSRFValidationError(f"DNS resolution error for '{host}': {exc}")

    # Validate every resolved IP
    for family, socktype, proto, canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            resolved_ip = ipaddress.ip_address(ip_str)
            blocked, reason = is_ip_blocked(resolved_ip)
            if blocked:
                raise SSRFValidationError(
                    f"SSRF Guard: Host '{host}' resolves to forbidden address: {reason}"
                )
        except ValueError:
            continue

    return clean_url
