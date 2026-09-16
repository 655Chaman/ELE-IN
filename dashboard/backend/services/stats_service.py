"""
@deprecated
This file is orphaned and superseded by the master-view API routes and the dashboard backend logic.
It is entirely unused and a candidate for deletion.
"""
from typing import Any

import structlog

from core.backend.api.auth_dep import get_service_client

logger = structlog.get_logger()

def get_market_stats(market: str, side: str) -> dict[str, Any]:
    stats = {"total": 0, "enriched": 0, "verified_email": 0, "with_domain": 0}
    
    try:
        supabase = get_service_client()
        
        # Total extracted/enriched
        res = supabase.table("opportunities").select("id", count="exact").ilike("market", market).ilike("side", side).execute()
        stats["total"] = res.count or 0
        
        # Domain not null
        # We simulate "domain IS NOT NULL AND domain != ''" by getting everything and doing count (supabase ilike doesn't support basic not null and not empty very easily in one step for strings, but we can do not_eq('', domain))
        res = supabase.table("opportunities").select("id", count="exact").ilike("market", market).ilike("side", side).neq("domain", "").not_is("domain", "null").execute()
        stats["with_domain"] = res.count or 0

        # Enriched status
        res = supabase.table("opportunities").select("id", count="exact").ilike("market", market).ilike("side", side).in_("status", ['enriched', 'vetted_pass', 'vetted_fail', 'copy_ready']).execute()
        stats["enriched"] = res.count or 0
        
        # Verified email
        res = supabase.table("opportunities").select("id", count="exact").ilike("market", market).ilike("side", side).neq("verified_email", "").neq("verified_email", "none").not_is("verified_email", "null").execute()
        stats["verified_email"] = res.count or 0
    except Exception as e:
        logger.error("db_stats_failed", error=str(e), market=market, side=side)
        
    return stats
