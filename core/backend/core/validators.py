from urllib.parse import urlparse
import socket, ipaddress

def is_safe_ssrf_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]: return False
        hostname = parsed.hostname
        if not hostname: return False
        
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                    return False
        except socket.gaierror:
            return False # Domain doesn't resolve
            
        # Note: Resolving the hostname once at validation time cannot fully close 
        # a DNS-rebinding race where the name resolves differently a few milliseconds 
        # later at actual connect time. That is an accepted residual risk.
        return True
    except Exception:
        return False
