from fastapi import Request, HTTPException, Depends
from supabase import Client
from core.backend.api.auth_dep import get_service_client
from typing import Callable, Optional

def rate_limit(cost: int = 1, capacity: int = 100, refill_rate_per_second: float = 1.0):
    """
    Dependency to enforce token-bucket rate limiting for API keys.
    Uses Postgres RPC `consume_api_quota` instead of Redis.
    """
    def _rate_limit_dep(
        request: Request,
        supabase: Client = Depends(get_service_client)
    ):
        # We assume the auth middleware has already validated the key
        # and injected api_key_id into request.state
        api_key_id = getattr(request.state, "api_key_id", None)
        
        # If this isn't an API key request (e.g. session-based UI call), skip this limiter
        if not api_key_id:
            return True
            
        try:
            res = supabase.rpc("consume_api_quota", {
                "p_key_id": api_key_id,
                "p_cost": cost,
                "p_capacity": capacity,
                "p_refill_rate_per_second": refill_rate_per_second
            }).execute()
            
            allowed = res.data
            if not allowed:
                raise HTTPException(
                    status_code=429, 
                    detail="Too Many Requests. API quota exhausted."
                )
            return True
        except Exception as e:
            # If the RPC fails (e.g. migration not run), default to passing
            # to avoid hard breaking endpoints during transition.
            if isinstance(e, HTTPException):
                raise
            return True
            
    return _rate_limit_dep
enforce_ai_rate_limit = rate_limit(cost=1, capacity=50, refill_rate_per_second=0.5)
