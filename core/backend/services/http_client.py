import httpx
from fastapi import HTTPException
import structlog
from typing import Any, Optional, Dict
import time
import threading
import asyncio
import random
from urllib.parse import urlparse

logger = structlog.get_logger(__name__)

# ==============================================================================
# PARANOIA FRAMEWORK: ALL OUTBOUND HTTP CALLS TO THIRD PARTIES MUST GO THROUGH 
# async_external_request(). NEVER USE requests OR httpx DIRECTLY. 
# BYPASSING THIS WILL GET OUR SERVER IP BLACKLISTED.
# ==============================================================================

# PER-SERVICE RATE LIMIT CONFIGURATION (calls per minute)
# Future devs: Tune these values here or add new services as needed.
RATE_LIMIT_CONFIG = {
    "hubspot": 100,
    "apollo": 50,
    "ghl": 100
}

# Domain mapping to service name
DOMAIN_TO_SERVICE = {
    "api.hubapi.com": "hubspot",
    "api.apollo.io": "apollo",
    "services.leadconnectorhq.com": "ghl"
}

class ThirdPartyRateLimitError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=429, detail=detail)

class TokenBucketRateLimiter:
    def __init__(self, calls_per_minute: int):
        self.capacity = calls_per_minute
        self.tokens = calls_per_minute
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()
        
    def consume(self) -> float:
        """
        Consumes one token if available. 
        Returns the sleep time required if no tokens are available.
        """
        now = time.monotonic()
        with self.lock:
            # Refill tokens based on time passed
            time_passed = now - self.last_refill
            if time_passed >= 60.0:
                self.tokens = self.capacity
                self.last_refill = now
            elif self.tokens < self.capacity:
                refill_amount = int((time_passed / 60.0) * self.capacity)
                if refill_amount > 0:
                    self.tokens = min(self.capacity, self.tokens + refill_amount)
                    self.last_refill = now

            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0
            
            # Not enough tokens, calculate time until next full minute refill
            return 60.0 - (now - self.last_refill)

# Initialize token buckets for each service
rate_limiters = {
    service: TokenBucketRateLimiter(limit) 
    for service, limit in RATE_LIMIT_CONFIG.items()
}

def get_service_from_url(url: str) -> Optional[str]:
    domain = urlparse(url).netloc
    for known_domain, service in DOMAIN_TO_SERVICE.items():
        if known_domain in domain:
            return service
    return None

async def async_external_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
    **kwargs
) -> httpx.Response:
    """
    Central helper function to make external HTTP requests safely.
    Enforces a strict timeout and catches network/timeout exceptions.
    Prevents raw tracebacks and returns graceful 502/504 errors.
    """
    safe_url = url.split("?")[0]
    service = get_service_from_url(safe_url)
    
    # Layer 0 & 1: Rate limiting with Jitter
    if service and service in rate_limiters:
        limiter = rate_limiters[service]
        sleep_time = limiter.consume()
        if sleep_time > 0:
            jitter = random.uniform(0.1, 2.0)
            total_sleep = sleep_time + jitter
            logger.warning("external_api.rate_limit_throttle", service=service, sleep_time=total_sleep)
            await asyncio.sleep(total_sleep)

    max_retries = 3
    base_backoff = 2.0

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    **kwargs
                )
                
                # Layer 1: Exponential backoff on 429
                if response.status_code == 429:
                    if attempt < max_retries:
                        backoff = base_backoff * (2 ** attempt) + random.uniform(0.1, 1.0)
                        logger.warning("external_api.429_received", url=safe_url, attempt=attempt+1, backoff=backoff)
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        raise ThirdPartyRateLimitError(f"Third-party API rate limit exceeded ({safe_url}).")
                        
                return response
                
        except httpx.TimeoutException as e:
            if attempt < max_retries:
                backoff = base_backoff * (2 ** attempt) + random.uniform(0.1, 1.0)
                logger.warning("external_api.timeout_retry", url=safe_url, attempt=attempt+1, backoff=backoff)
                await asyncio.sleep(backoff)
                continue
            logger.error("external_api.timeout", url=safe_url, error=str(e))
            raise HTTPException(
                status_code=504,
                detail=f"Third-party API timeout ({safe_url}). The service is currently unreachable."
            )
        except httpx.RequestError as e:
            logger.error("external_api.request_error", url=safe_url, error=str(e))
            raise HTTPException(
                status_code=502,
                detail=f"Third-party API request failed ({safe_url}). The service is currently unreachable."
            )
        except ThirdPartyRateLimitError:
            raise
        except Exception as e:
            logger.error("external_api.unknown_error", url=safe_url, error=str(e))
            raise HTTPException(
                status_code=502,
                detail="An unexpected error occurred while communicating with a third-party API."
            )


def validate_outbound_url_for_ssrf(url: str) -> tuple[bool, str]:
    """
    Security Hardening (VULN-11 & VULN-12):
    Validates that an outbound URL does not resolve to loopback, link-local,
    private RFC1918, cloud metadata IPs, or invalid protocols to prevent SSRF.
    """
    try:
        from urllib.parse import urlparse
        import socket
        import ipaddress

        if not url or not isinstance(url, str):
            return False, "Invalid or empty URL"

        clean_url = url.strip().strip("\"'<>")
        parsed = urlparse(clean_url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Protocol '{parsed.scheme}' not allowed. Only HTTP and HTTPS are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "Missing destination hostname"

        lower_host = hostname.lower()
        blocked_hosts = {
            "localhost", "127.0.0.1", "::1", "0.0.0.0",
            "metadata.google.internal", "metadata.internal",
            "169.254.169.254", "169.254.169.253", "instance-data",
        }
        if lower_host in blocked_hosts or lower_host.endswith(".internal") or lower_host.endswith(".local"):
            return False, f"Access to internal host '{hostname}' is strictly prohibited"

        # Check for direct IP address literal
        try:
            direct_ip = ipaddress.ip_address(hostname)
            if direct_ip.is_private or direct_ip.is_loopback or direct_ip.is_link_local or direct_ip.is_reserved or direct_ip.is_multicast:
                return False, f"Direct access to private or internal IP ({direct_ip}) is strictly prohibited"
        except ValueError:
            pass

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except Exception as dns_err:
            return False, f"DNS resolution failed for '{hostname}': {dns_err}"

        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, f"Access to private or internal IP ({ip_str}) is strictly prohibited (SSRF defense)"

        return True, ""
    except Exception as e:
        return False, f"SSRF security validation error: {e}"
