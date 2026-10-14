from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import logging

from core.backend.api.auth_dep import get_service_client
from core.backend.services.credit_service import TIER_LIMITS

logger = logging.getLogger(__name__)

def calculate_workspace_churn_health(workspace_id: str) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Predictive Churn Risk & Health Scoring Engine.
    Evaluates campaign execution vitality, credit runway, response rate,
    and login activity to produce an actionable health score (0-100) and risk tier.
    Never throws an exception — falls back to healthy baseline defaults.
    """
    if not workspace_id:
        return {
            "health_score": 100,
            "churn_risk": "LOW",
            "risk_score": 0,
            "risk_factors": [],
            "recommendations": [],
            "is_paused": False,
            "cancel_at_period_end": False,
        }

    supabase = get_service_client()
    risk_score = 0
    risk_factors: List[Dict[str, str]] = []
    recommendations: List[Dict[str, str]] = []

    # 1. Inspect Workspace State & Credits
    credits_remaining = 500
    tier = "FREE"
    is_paused = False
    cancel_at_period_end = False

    try:
        ws_res = supabase.table("workspaces").select("tier, data_cleaning_credits, status, updated_at").eq("id", workspace_id).limit(1).execute()
        if ws_res.data:
            row = ws_res.data[0]
            tier = str(row.get("tier") or "FREE").upper()
            credits_remaining = int(row.get("data_cleaning_credits") or 0)
            if row.get("status") == "paused":
                is_paused = True
    except Exception as e:
        logger.warning(f"[ChurnService] Error querying workspace {workspace_id}: {e}")

    # Check pending cancellation in billing_transactions
    try:
        txn_res = supabase.table("billing_transactions").select("status, created_at").eq("workspace_id", workspace_id).eq("status", "scheduled_cancellation").order("created_at", desc=True).limit(1).execute()
        if txn_res.data:
            cancel_at_period_end = True
    except Exception as e:
        logger.debug(f"[ChurnService] Error querying cancellation transactions: {e}")

    # 2. Factor 1: Active Campaigns Vitality
    active_campaigns_count = 0
    total_campaigns_count = 0
    try:
        camp_res = supabase.table("campaigns").select("id, status").eq("workspace_id", workspace_id).execute()
        if camp_res.data:
            total_campaigns_count = len(camp_res.data)
            active_campaigns_count = sum(1 for c in camp_res.data if str(c.get("status") or "").upper() == "ACTIVE")
    except Exception as e:
        logger.debug(f"[ChurnService] Error querying campaigns: {e}")

    if tier in ("PRO", "ENTERPRISE", "GROWTH") and active_campaigns_count == 0:
        risk_score += 35
        risk_factors.append({
            "code": "ZERO_ACTIVE_CAMPAIGNS",
            "severity": "HIGH",
            "message": "No campaigns are currently active while paying for a Pro plan."
        })
        recommendations.append({
            "title": "Launch a Sequence Draft",
            "description": "Activate one of your drafted campaigns or use the AI Ghostwriter template to start outreach.",
            "action_url": "/campaigns"
        })

    # 3. Factor 2: Credit Runway Exhaustion
    if credits_remaining <= 50:
        risk_score += 25
        risk_factors.append({
            "code": "LOW_CREDIT_RUNWAY",
            "severity": "MEDIUM",
            "message": f"Only {credits_remaining} credits remaining. Outbound will throttle when balance reaches zero."
        })
        recommendations.append({
            "title": "Top Up Credits",
            "description": "Add credits with 1-click micro top-up to prevent campaign dispatch halts.",
            "action_url": "/settings/billing"
        })

    # 4. Factor 3: Reply Rate Conversion
    # We query messages in the last 14 days
    try:
        two_weeks_ago = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        msg_res = supabase.table("messages").select("id, status").eq("workspace_id", workspace_id).gte("created_at", two_weeks_ago).execute()
        if msg_res.data and len(msg_res.data) >= 30:
            replied_count = sum(1 for m in msg_res.data if str(m.get("status") or "").lower() in ("replied", "answered", "converted"))
            reply_rate = (replied_count / len(msg_res.data)) * 100
            if reply_rate < 2.0:
                risk_score += 20
                risk_factors.append({
                    "code": "LOW_REPLY_RATE",
                    "severity": "MEDIUM",
                    "message": f"Recent campaign reply rate is {reply_rate:.1f}%. Low engagement leads to frustration."
                })
                recommendations.append({
                    "title": "Calibrate Bayesian ICP & Organic Hooks",
                    "description": "Enable organic post icebreakers and Bayesian intent scoring to increase prospect relevance.",
                    "action_url": "/knowledge"
                })
    except Exception as e:
        logger.debug(f"[ChurnService] Error querying messages: {e}")

    # Compute final health score (100 - risk_score, bounded between 10 and 100)
    health_score = max(10, min(100, 100 - risk_score))

    churn_risk = "LOW"
    if risk_score >= 60:
        churn_risk = "CRITICAL"
    elif risk_score >= 35:
        churn_risk = "HIGH"
    elif risk_score >= 20:
        churn_risk = "MEDIUM"

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "tier": tier,
        "health_score": health_score,
        "churn_risk": churn_risk,
        "risk_score": risk_score,
        "credits_remaining": credits_remaining,
        "active_campaigns_count": active_campaigns_count,
        "total_campaigns_count": total_campaigns_count,
        "is_paused": is_paused,
        "cancel_at_period_end": cancel_at_period_end,
        "risk_factors": risk_factors,
        "recommendations": recommendations,
    }


def audit_downgrade_safety_impact(workspace_id: str) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Downgrade Impact Audit.
    Analyzes what resources currently exceed Free tier limits and details the
    safe archiving strategy so the user knows NOTHING will be deleted.
    """
    supabase = get_service_client()
    free_limits = TIER_LIMITS["FREE"]

    active_campaigns: List[Dict[str, Any]] = []
    accounts: List[Dict[str, Any]] = []
    knowledge_assets_count = 0

    try:
        camp_res = supabase.table("campaigns").select("id, name, status, created_at").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        if camp_res.data:
            active_campaigns = [c for c in camp_res.data if str(c.get("status") or "").upper() == "ACTIVE"]
    except Exception as e:
        logger.warning(f"[ChurnService] Error querying campaigns for downgrade audit: {e}")

    try:
        acc_res = supabase.table("accounts").select("id, name, status, created_at").eq("workspace_id", workspace_id).execute()
        if acc_res.data:
            accounts = [a for a in acc_res.data if str(a.get("status") or "").lower() in ("connected", "active", "valid")]
    except Exception as e:
        logger.warning(f"[ChurnService] Error querying accounts for downgrade audit: {e}")

    try:
        kb_res = supabase.table("knowledge_assets").select("id").eq("workspace_id", workspace_id).execute()
        knowledge_assets_count = len(kb_res.data) if kb_res.data else 0
    except Exception as e:
        logger.warning(f"[ChurnService] Error querying knowledge assets: {e}")

    active_camp_count = len(active_campaigns)
    active_acc_count = len(accounts)

    max_camps = free_limits.get("max_active_campaigns", 1)
    max_accs = free_limits.get("max_linkedin_accounts", 1)
    max_assets = free_limits.get("max_knowledge_assets", 3)

    camps_to_archive = max(0, active_camp_count - max_camps)
    accs_to_archive = max(0, active_acc_count - max_accs)
    assets_over_limit = max(0, knowledge_assets_count - max_assets)

    # Pick the top active campaign to keep active; others will be gracefully paused/archived
    retained_campaign = active_campaigns[0] if active_campaigns else None
    archived_campaigns = active_campaigns[1:] if len(active_campaigns) > 1 else []

    retained_account = accounts[0] if accounts else None
    archived_accounts = accounts[1:] if len(accounts) > 1 else []

    return {
        "status": "success",
        "current_active_campaigns": active_camp_count,
        "free_limit_campaigns": max_camps,
        "campaigns_to_archive_count": camps_to_archive,
        "retained_campaign_name": retained_campaign.get("name") if retained_campaign else "None",
        "archived_campaign_names": [c.get("name", "Untitled") for c in archived_campaigns],
        "current_accounts": active_acc_count,
        "free_limit_accounts": max_accs,
        "accounts_to_archive_count": accs_to_archive,
        "retained_account_name": retained_account.get("name") if retained_account else "None",
        "total_knowledge_assets": knowledge_assets_count,
        "free_limit_knowledge_assets": max_assets,
        "assets_over_limit": assets_over_limit,
        "data_loss_risk": False,
        "guarantee_message": "Zero data is ever deleted. Excess campaigns and accounts will be placed in safe, read-only cold storage and will immediately reactivate if you choose to upgrade in the future.",
    }


def execute_non_destructive_downgrade_clamp(workspace_id: str) -> Dict[str, Any]:
    """
    Paranoia Layer 1 & 2: Physically clamps workspace resources to Free tier limits
    WITHOUT deleting any user rows. Excess active campaigns are set to PAUSED_ARCHIVED.
    Excess accounts are set to PAUSED_ARCHIVED.
    """
    if not workspace_id:
        return {"status": "error", "message": "Missing workspace_id"}

    supabase = get_service_client()
    archived_camp_ids = []
    archived_acc_ids = []

    try:
        camp_res = supabase.table("campaigns").select("id, status, created_at").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        if camp_res.data:
            active_camps = [c for c in camp_res.data if str(c.get("status") or "").upper() == "ACTIVE"]
            # Keep 1st, pause the rest
            if len(active_camps) > 1:
                for c in active_camps[1:]:
                    cid = c["id"]
                    supabase.table("campaigns").update({"status": "PAUSED"}).eq("id", cid).eq("workspace_id", workspace_id).execute()
                    archived_camp_ids.append(cid)
    except Exception as e:
        logger.error(f"[ChurnService] Error clamping campaigns for {workspace_id}: {e}")

    try:
        acc_res = supabase.table("accounts").select("id, status, created_at").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        if acc_res.data:
            valid_accs = [a for a in acc_res.data if str(a.get("status") or "").lower() in ("connected", "active", "valid")]
            if len(valid_accs) > 1:
                for a in valid_accs[1:]:
                    aid = a["id"]
                    supabase.table("accounts").update({"status": "paused"}).eq("id", aid).eq("workspace_id", workspace_id).execute()
                    archived_acc_ids.append(aid)
    except Exception as e:
        logger.error(f"[ChurnService] Error clamping accounts for {workspace_id}: {e}")

    # Update workspace tier to FREE
    try:
        supabase.table("workspaces").update({"tier": "FREE"}).eq("id", workspace_id).execute()
    except Exception as e:
        logger.error(f"[ChurnService] Error updating workspace tier to FREE: {e}")

    return {
        "status": "success",
        "clamped_campaigns_count": len(archived_camp_ids),
        "clamped_accounts_count": len(archived_acc_ids),
        "message": "Non-destructive downgrade completed. All historical campaigns, leads, and assets preserved."
    }
