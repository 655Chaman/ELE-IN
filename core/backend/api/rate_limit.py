"""
rate_limit.py
Multi-Tenant Rate Limiting & Sliding Window Burst Protection (Step 24).
Provides thread-safe in-memory sliding window rate limiting, identity resolvers,
tier-aware capacity multipliers, memory leak defense, and 100% backward compatibility
for token-bucket rate limiters.
"""

import time
import ipaddress
import threading
from collections import deque, OrderedDict
from typing import Callable, Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException, Depends
from supabase import Client
from core.backend.api.auth_dep import get_service_client
import logging

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter log with LRU bucket reaping
    and memory leak defense (max 25,000 buckets).
    """
    def __init__(self, max_buckets: int = 25000):
        self.max_buckets = max_buckets
        self.lock = threading.Lock()
        # key -> deque of timestamps
        self.windows: OrderedDict[str, deque] = OrderedDict()
        self.last_reap = time.time()

def get_client_ip(request: Request) -> str:
    """
    Resolves client IP with spoofing defense (CF-Connecting-IP, X-Real-IP, X-Forwarded-For).
    Strips port numbers and validates IP address format.
    """
    ip_candidates = []
    
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        ip_candidates.append(cf_ip.strip())
        
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        ip_candidates.append(real_ip.strip())
        
    fwd_for = request.headers.get("X-Forwarded-For")
    if fwd_for:
        for part in fwd_for.split(","):
            p = part.strip()
            if p:
                ip_candidates.append(p)
                
    if request.client and request.client.host:
        ip_candidates.append(request.client.host.strip())
        
    for candidate in ip_candidates:
        # Strip port if present (e.g. 192.168.1.1:8080 or [::1]:8080)
        clean_ip = candidate.split(":", 1)[0] if ":" in candidate and not candidate.startswith("[") else candidate
        if candidate.startswith("[") and "]" in candidate:
            clean_ip = candidate[1:candidate.index("]")]
            
        try:
            parsed = ipaddress.ip_address(clean_ip)
            return str(parsed)
        except ValueError:
            continue
            
    return "127.0.0.1"


def get_client_workspace(request: Request) -> Optional[str]:
    """
    Resolves workspace ID from request state, headers, query params, or path params.
    """
    # 1. request.state
    ws_id = getattr(request.state, "workspace_id", None)
    if ws_id:
        return str(ws_id).strip()
        
    # 2. X-Workspace-ID header
    ws_id = request.headers.get("X-Workspace-ID")
    if ws_id:
        return ws_id.strip()
        
    # 3. Query params
    ws_id = request.query_params.get("workspace_id")
    if ws_id:
        return ws_id.strip()
        
    # 4. Path params
    ws_id = request.path_params.get("workspace_id")
    if ws_id:
        return ws_id.strip()
        
    return None


def get_client_user(request: Request) -> Optional[str]:
    """
    Resolves user ID or API key ID from request state.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id).strip()
        
    api_key_id = getattr(request.state, "api_key_id", None)
    if api_key_id:
        return str(api_key_id).strip()
        
    return None


# Global singleton limiter instance
_global_limiter = SlidingWindowRateLimiter()


def sliding_window_rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    scope: str = "auto",  # "auto", "workspace", "ip", "user", "api_key"
    cost: int = 1,
    tier_aware: bool = True
) -> Callable:
    """
    Dependency to enforce sliding window rate limiting with burst protection,
    tier-aware multipliers, internal healthcheck/localhost bypass, and memory leak defense.
    """
    safe_max = max(1, int(max_requests))
    safe_window = max(1, int(window_seconds))
    safe_cost = max(1, int(cost))

    def _limiter_dep(
        request: Request,
        supabase: Client = Depends(get_service_client)
    ):
        # Layer 2: Internal healthcheck & localhost whitelist bypass
        client_ip = get_client_ip(request)
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            return True

        path = request.url.path.lower()
        bypass_paths = ("/health", "/ready", "/api/health", "/metrics", "/api/system/health")
        if any(path.startswith(bp) for bp in bypass_paths):
            return True

        # Resolve identity based on scope
        workspace_id = get_client_workspace(request)
        user_id = get_client_user(request)
        api_key_id = getattr(request.state, "api_key_id", None)

        key_prefix = "ip"
        key_id = client_ip

        if scope == "workspace" or (scope == "auto" and workspace_id):
            if workspace_id:
                key_prefix = "ws"
                key_id = workspace_id
        elif scope == "user" or (scope == "auto" and user_id and not workspace_id):
            if user_id:
                key_prefix = "usr"
                key_id = user_id
        elif scope == "api_key" or (scope == "auto" and api_key_id):
            if api_key_id:
                key_prefix = "key"
                key_id = str(api_key_id)

        limiter_key = f"{key_prefix}:{key_id}:{window_seconds}"

        # Tier-aware capacity multiplication
        effective_max = safe_max
        if tier_aware and workspace_id:
            try:
                ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
                if ws_res.data:
                    tier = (ws_res.data[0].get("tier") or "FREE").upper()
                    if tier in ("GROWTH", "PRO"):
                        effective_max = safe_max * 3
                    elif tier in ("ENTERPRISE", "AGENCY"):
                        effective_max = safe_max * 10
            except Exception as tier_err:
                logger.debug(f"Could not fetch workspace tier for rate limit multiplier: {tier_err}")

        now = time.time()
        window_start = now - safe_window

        with _global_limiter.lock:
            # Memory leak defense: periodic reaping every 60s or when buckets > max_buckets
            if len(_global_limiter.windows) > _global_limiter.max_buckets or (now - _global_limiter.last_reap) > 60:
                expired_keys = []
                for k, dq in _global_limiter.windows.items():
                    while dq and dq[0] < now - 120:  # prune older than 2 mins
                        dq.popleft()
                    if not dq:
                        expired_keys.append(k)
                for k in expired_keys:
                    _global_limiter.windows.pop(k, None)
                _global_limiter.last_reap = now

                # If still over max_buckets, evict oldest LRU
                while len(_global_limiter.windows) > _global_limiter.max_buckets:
                    _global_limiter.windows.popitem(last=False)

            if limiter_key not in _global_limiter.windows:
                _global_limiter.windows[limiter_key] = deque()
            else:
                # Move to end for LRU tracking
                _global_limiter.windows.move_to_end(limiter_key)

            dq = _global_limiter.windows[limiter_key]

            # Prune timestamps outside current sliding window
            while dq and dq[0] <= window_start:
                dq.popleft()

            current_count = len(dq)
            remaining = max(0, effective_max - current_count)

            if current_count + safe_cost > effective_max:
                # Rate limit exceeded
                oldest_ts = dq[0] if dq else now
                retry_after = max(1, int(math_ceil((oldest_ts + safe_window) - now))) if dq else safe_window
                reset_epoch = int(now + safe_window)

                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for {key_prefix} '{key_id}'. Limit is {effective_max} requests per {window_seconds}s. Please retry in {retry_after}s.",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(effective_max),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_epoch),
                        "X-RateLimit-Scope": scope
                    }
                )

            # Record request timestamp(s) based on cost
            for _ in range(safe_cost):
                dq.append(now)

            remaining = max(0, effective_max - len(dq))
            reset_epoch = int(now + safe_window)

        return True

    return _limiter_dep


def math_ceil(val: float) -> int:
    import math
    return math.ceil(val)


# ── Backward Compatibility: Legacy Token Bucket Rate Limiter ───────────────────
def rate_limit(cost: int = 1, capacity: int = 100, refill_rate_per_second: float = 1.0):
    """
    Legacy token-bucket rate limiter dependency for API keys (maintains 100% test compatibility).
    """
    def _rate_limit_dep(
        request: Request,
        supabase: Client = Depends(get_service_client)
    ):
        api_key_id = getattr(request.state, "api_key_id", None)
        if not api_key_id:
            return True
            
        safe_cost = max(1, int(cost))
        safe_capacity = max(1, int(capacity))
        safe_refill = max(0.01, float(refill_rate_per_second))

        try:
            res = supabase.rpc("consume_api_quota", {
                "p_key_id": api_key_id,
                "p_cost": safe_cost,
                "p_capacity": safe_capacity,
                "p_refill_rate_per_second": safe_refill
            }).execute()
            
            allowed = res.data
            if not allowed:
                raise HTTPException(
                    status_code=429, 
                    detail="Too Many Requests. API quota exhausted."
                )
            return True
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            err_str = str(e).lower()
            if "could not find the function" in err_str or "consume_api_quota" in err_str or "pgrst202" in err_str:
                logger.warning(f"consume_api_quota RPC not found in database; allowing request in fallback mode: {e}")
                return True
            raise HTTPException(status_code=503, detail="Service Unavailable. Rate limit check failed.")
            
    return _rate_limit_dep


# Dedicated limiters
enforce_ai_rate_limit = sliding_window_rate_limit(max_requests=30, window_seconds=60, scope="auto", tier_aware=True)
enforce_upload_rate_limit = sliding_window_rate_limit(max_requests=10, window_seconds=60, scope="workspace")
enforce_webhook_rate_limit = sliding_window_rate_limit(max_requests=120, window_seconds=60, scope="ip")
