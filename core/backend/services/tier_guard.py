"""
Institutional Tier-1 Feature & Subscription Gating Guard.
Enforces Three-Layer Paranoia access control across all API routers.
"""
from typing import Optional, Callable
from fastapi import Depends, HTTPException
from supabase import Client
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from core.backend.services.credit_service import TIER_LIMITS, normalize_tier


def require_tier(feature_flag: str, min_tier: str = "PRO") -> Callable:
    """
    FastAPI endpoint dependency enforcing workspace tier entitlements.
    Raises structured 402 FEATURE_TIER_GATED on tier mismatches.
    """
    def dependency(
        workspace_id: str = Depends(get_current_workspace),
        supabase: Client = Depends(get_service_client)
    ) -> bool:
        if not workspace_id:
            raise HTTPException(status_code=401, detail="Workspace context required")
            
        clean_ws = str(workspace_id).strip()
        try:
            ws_res = supabase.table("workspaces").select("tier").eq("id", clean_ws).execute()
            tier_raw = ws_res.data[0].get("tier") if ws_res.data else "FREE"
        except Exception:
            tier_raw = "FREE"
            
        tier = normalize_tier(tier_raw)
        tier_cfg = TIER_LIMITS.get(tier, TIER_LIMITS.get("FREE", {}))
        
        has_access = bool(tier_cfg.get(feature_flag, False))
        
        # Enterprise supersedes Pro
        if not has_access and tier == "ENTERPRISE":
            has_access = True
            
        if not has_access:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "FEATURE_TIER_GATED",
                    "code": "FEATURE_TIER_GATED",
                    "feature": feature_flag,
                    "required_tier": min_tier.upper(),
                    "current_tier": tier,
                    "message": f"Access to {feature_flag} requires an active {min_tier.upper()} subscription."
                }
            )
        return True

    return dependency
