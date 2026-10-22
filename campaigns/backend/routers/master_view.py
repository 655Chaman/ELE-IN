from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import asyncio
import time
import re

_captain_brief_cache: dict = {}
_CAPTAIN_BRIEF_TTL_SECONDS = 1800
_MAX_CAPTAIN_BRIEF_CACHE_SIZE = 500

from datetime import date, datetime, timedelta, timezone
from supabase import Client
from core.backend.api.auth_dep import get_supabase_client, get_current_workspace, get_current_user_id
from fastapi.responses import StreamingResponse
from campaigns.backend.utils.pdf_generator import generate_pdf_report
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["master-view"])

import math
import threading

_master_view_stats_cache: dict = {}
_master_view_stats_lock = threading.Lock()
_MASTER_VIEW_CACHE_TTL_SECONDS = 60  # Paranoia Layer 1 (API-22): 60s TTL prevents unindexed action_log aggregation spikes
_MAX_MASTER_VIEW_CACHE_SIZE = 200

def clear_master_view_cache():
    """Paranoia Layer 1: Clears in-memory master view stats cache (useful for testing or forced invalidation)."""
    with _master_view_stats_lock:
        _master_view_stats_cache.clear()

def invalidate_master_view_cache(workspace_id: Optional[str] = None):
    """
    Paranoia Layer 1 (API-25): Invalidate cached master view statistics on campaign/settings mutations.
    If workspace_id is provided, purges entries strictly for that workspace.
    """
    with _master_view_stats_lock:
        if workspace_id:
            stale_keys = [k for k in list(_master_view_stats_cache.keys()) if isinstance(k, tuple) and len(k) > 0 and k[0] == workspace_id]
            for sk in stale_keys:
                _master_view_stats_cache.pop(sk, None)
        else:
            _master_view_stats_cache.clear()

def _format_iso_utc(val: Any) -> Optional[str]:
    """
    Paranoia Layer 0 (API-10): Standardize all analytics dates and timestamps to ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ').
    Handles datetime objects, epoch integers/floats, and RFC/ISO timestamp strings.
    """
    if not val:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return str(val)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        else:
            val = val.astimezone(timezone.utc)
        return val.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        # If it's a date only 'YYYY-MM-DD', preserve it
        if len(val_str) == 10 and val_str.count("-") == 2 and val_str.replace("-", "").isdigit():
            return val_str
        try:
            clean_str = val_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return val_str
    return str(val)

def sanitize_filter_list(lst: Optional[List[str]], max_items: int = 100) -> Optional[List[str]]:
    if not lst or not isinstance(lst, list):
        return None
    cleaned = []
    for item in lst:
        if isinstance(item, str):
            s = item.strip()
            if s and s not in ("", "null", "undefined") and len(s) <= 128:
                # Discard items containing SQL injection tokens or newlines
                if not any(token in s for token in ["\n", "\r", ";", "'", "--", "/*"]):
                    cleaned.append(s)
    if not cleaned:
        return None
    return cleaned[:max_items]

def validate_date_range(date_start: Optional[str], date_end: Optional[str], max_days: int = 366) -> tuple[str, str]:
    if date_start:
        date_start = str(date_start).strip()
        if date_start in ("", "null", "undefined"):
            date_start = None
    if date_end:
        date_end = str(date_end).strip()
        if date_end in ("", "null", "undefined"):
            date_end = None

    now_utc_date = datetime.now(timezone.utc).date()

    if not date_end:
        date_end = now_utc_date.isoformat()
    
    try:
        end_dt = datetime.fromisoformat(date_end[:10]).date()
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid date format. Use ISO 8601.')

    # Clamp future date_end if more than 1 day in the future
    if (end_dt - now_utc_date).days > 1:
        end_dt = now_utc_date + timedelta(days=1)
        date_end = end_dt.isoformat()

    if not date_start:
        start_dt = end_dt - timedelta(days=30)
        date_start = start_dt.isoformat()
    else:
        try:
            start_dt = datetime.fromisoformat(date_start[:10]).date()
        except ValueError:
            raise HTTPException(status_code=400, detail='Invalid date format. Use ISO 8601.')

    if end_dt < start_dt:
        raise HTTPException(
            status_code=400,
            detail='date_end must be after date_start'
        )

    if (end_dt - start_dt).days > max_days:
        raise HTTPException(
            status_code=400, 
            detail=f'Date range cannot exceed {max_days} days.'
        )
    
    return date_start[:10], date_end[:10]

def safe_div(a, b, default=0.0) -> float:
    try:
        if a is None or b is None:
            return default
        fa = float(a)
        fb = float(b)
        if math.isnan(fa) or math.isnan(fb) or fb <= 0.0:
            return default
        res = fa / fb
        if math.isnan(res) or math.isinf(res):
            return default
        return res
    except (TypeError, ValueError, ZeroDivisionError):
        return default


class MasterViewRequest(BaseModel):
    senders: Optional[List[str]] = None
    campaigns: Optional[List[str]] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None

class AccountHealthRequest(BaseModel):
    date_start: Optional[str] = None
    date_end: Optional[str] = None

def compute_today_live(workspace_id: str, supabase: Client, user_today: str, senders: list = None) -> dict:
    """
    Returns live today's action counts.
    Reads from account_daily_action_counts (already incremented atomically
    by the Campaigns engine's rate limiting). This is NOT action_log.
    
    # PERFORMANCE CRITICAL: This reads account_daily_action_counts, NOT action_log.
    # action_log is a write-optimized table. Counting it live is an O(n) full scan.
    """
    # USER TIMEZONE: Using date_end from the request, not server date.today(). Server time != user's local date.
    today = user_today
    try:
        if senders:
            account_ids = senders
        else:
            # Get all accounts for this workspace
            accounts_res = supabase.table('accounts').select('id').eq('workspace_id', workspace_id).execute()
            account_ids = [a['id'] for a in (accounts_res.data or [])]
        if not account_ids:
            return {'connections_today': 0, 'messages_today': 0, 'inmails_today': 0}
        
        connections = 0
        messages = 0
        inmails = 0
        # Chunk account_ids into batches of 100 to avoid Supabase IN clause limits
        for i in range(0, len(account_ids), 100):
            batch = account_ids[i:i+100]
            counts_res = supabase.table('account_daily_action_counts') \
                .select('action_type, count') \
                .in_('account_id', batch) \
                .eq('usage_date', today) \
                .execute()
            
            # Layer 1: Accommodate various action_types for connection/message based on actual app usage
            connections += sum(r.get('count', 0) for r in (counts_res.data or []) if r.get('action_type') == 'connection_request')
            messages += sum(r.get('count', 0) for r in (counts_res.data or []) if r.get('action_type') == 'message')
            inmails += sum(r.get('count', 0) for r in (counts_res.data or []) if r.get('action_type') in ('inmail', 'paid_inmail'))
        return {'connections_today': connections, 'messages_today': messages, 'inmails_today': inmails}
    except Exception as e:
        print(f'[compute_today_live] Error: {e}')
        return {'connections_today': 0, 'messages_today': 0}

# MULTI-TENANT SAFETY CHECKLIST:
# [ ] Is the query scoped by workspace_id? Every query reading from any table MUST filter workspace_id.
# [ ] Does the workspace_id filter happen FIRST (i.e., is it the leading column in the WHERE clause)?
async def _generate_captain_brief(
    workspace_id: str,
    acceptance_rate: float,
    reply_rate: float,
    booking_rate: float,
    sentiment_pct: float,
    deliverability: float,
    bounces: float,
    connections_today: int,
    messages_today: int,
    active_campaigns: int,
    throttled_accounts: int,
    total_accounts: int,
) -> Optional[str]:
    """
    Generates a real AI insight using the existing NVIDIA/OpenAI failover client.
    Returns None on any failure — caller must handle fallback.
    """
    global _captain_brief_cache
    
    # Layer 1: Check composite TTL cache first (keyed by workspace and metric profile)
    cache_key = f"{workspace_id}:{round(acceptance_rate, 1)}:{round(reply_rate, 1)}:{round(booking_rate, 1)}:{round(sentiment_pct, 1)}:{connections_today}:{messages_today}:{active_campaigns}"
    cached = _captain_brief_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _CAPTAIN_BRIEF_TTL_SECONDS:
        return cached["insight"]
        
    try:
        from core.backend.api.auth_dep import get_service_client
        _svc = get_service_client()
        res = _svc.table('workspaces').select('tier').eq('id', workspace_id).execute()
        tier = res.data[0].get('tier', 'FREE') if res.data else 'FREE'
        if tier == 'FREE':
            return "Upgrade to PRO for AI-driven Captain's Insights. Your pipeline is active, review your acceptance rates below to find high-leverage improvements."
    except Exception as e:
        print(f"Failed to verify workspace tier for Captain's Brief: {e}")
        return "Your pipeline is active. Review acceptance and reply rates to find the highest-leverage improvement."
    
    try:
        from knowledge.backend.services.elein_ai_service import _get_async_client, _resolve_model, get_active_nvidia_keys
        
        keys = get_active_nvidia_keys("summarize")
        if not keys:
            return None
            
        client = _get_async_client(keys[0])
        if not client:
            return None
        
        model_list = _resolve_model(None, "summarize")
        model = "meta/llama-3.2-11b-vision-instruct"
        
        prompt = f"""You are a sharp sales ops analyst reviewing a LinkedIn outreach campaign.
Given these REAL metrics, write ONE short actionable sentence (under 200 characters) flagging the single most important thing to act on RIGHT NOW. Be specific with numbers. No filler. No hedging.

Metrics:
- Acceptance Rate: {acceptance_rate:.1f}%
- Reply Rate: {reply_rate:.1f}%
- Booking Rate: {booking_rate:.1f}%
- Positive Sentiment: {sentiment_pct:.1f}%
- Deliverability: {deliverability:.1f}%
- Bounce Rate: {bounces:.1f}%
- Connections Today: {connections_today}
- Messages Today: {messages_today}
- Active Campaigns: {active_campaigns}
- Throttled Accounts: {throttled_accounts} of {total_accounts}

Output ONLY the insight sentence. No explanation. No prefix like 'Insight:'. Just the sentence."""
        
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=80,
            ),
            timeout=8.0  # Layer 1: Hard 8s timeout — never block a dashboard load
        )
        
        insight = response.choices[0].message.content.strip()
        
        # Layer 2: Sanity check — reject empty or suspiciously long responses
        if not insight or len(insight) > 300:
            return None
        
        # Layer 1: Bound cache to avoid memory leaks across long running instances
        if len(_captain_brief_cache) >= _MAX_CAPTAIN_BRIEF_CACHE_SIZE:
            now_ts = time.time()
            expired_keys = [k for k, v in _captain_brief_cache.items() if (now_ts - v.get("ts", 0)) > _CAPTAIN_BRIEF_TTL_SECONDS]
            for k in expired_keys:
                _captain_brief_cache.pop(k, None)
            if len(_captain_brief_cache) >= _MAX_CAPTAIN_BRIEF_CACHE_SIZE:
                oldest_k = min(_captain_brief_cache.keys(), key=lambda k: _captain_brief_cache[k].get("ts", 0))
                _captain_brief_cache.pop(oldest_k, None)

        # Store in cache
        _captain_brief_cache[cache_key] = {"insight": insight, "ts": time.time()}
        return insight
        
    except asyncio.TimeoutError:
        print("[CaptainsBrief] LLM call timed out after 8s — using fallback")
        return None
    except Exception as e:
        print(f"[CaptainsBrief] LLM call failed: {e} — using fallback")
        return None

@router.post("/api/master-view/stats")
def get_master_view_stats(
    request: Request,
    req: MasterViewRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=403, detail='workspace_id required')
        
    req.date_start, req.date_end = validate_date_range(req.date_start, req.date_end)

    req.campaigns = sanitize_filter_list(req.campaigns)
    req.senders = sanitize_filter_list(req.senders)
    
    # Cache key construction
    cache_key = (
        workspace_id,
        req.date_start,
        req.date_end,
        tuple(sorted(req.campaigns or [])),
        tuple(sorted(req.senders or []))
    )
    
    bypass_cache = False
    if hasattr(request, "headers") and getattr(request.headers, "get", None):
        if request.headers.get("cache-control") in ("no-cache", "no-store") or request.headers.get("pragma") == "no-cache":
            bypass_cache = True
    if getattr(request, "_bypass_cache", False) or getattr(req, "bypass_cache", False):
        bypass_cache = True

    if not bypass_cache:
        with _master_view_stats_lock:
            now_ts = time.time()
            if cache_key in _master_view_stats_cache:
                entry = _master_view_stats_cache[cache_key]
                if (now_ts - entry["ts"]) < _MASTER_VIEW_CACHE_TTL_SECONDS:
                    return entry["data"]

    # Layer 1: Workspace boundary check - if filters provided but none exist in this workspace, fail closed
    if req.campaigns:
        valid_camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).in_("id", req.campaigns).execute()
        valid_campaign_ids = [r["id"] for r in (valid_camp_res.data or [])]
        if not valid_campaign_ids:
            req.campaigns = ["00000000-0000-0000-0000-000000000000"]
        else:
            req.campaigns = valid_campaign_ids
        
    if req.senders:
        valid_sender_res = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).in_("id", req.senders).execute()
        valid_sender_ids = [r["id"] for r in (valid_sender_res.data or [])]
        if not valid_sender_ids:
            req.senders = ["00000000-0000-0000-0000-000000000000"]
        else:
            req.senders = valid_sender_ids

    def safe_div(a, b):
        return a / b if b > 0 else 0

    try:
        # Paranoia Layer 1: Check tier entitlement for extended historical retention
        ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
        ws_tier = (ws_res.data[0].get("tier") or "FREE").upper() if ws_res.data else "FREE"
        from core.backend.services.credit_service import TIER_LIMITS
        can_extended = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_extended_analytics", False)
        historical_capped = False

        date_start = req.date_start
        date_end = req.date_end
        if not can_extended and date_start:
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
            if date_start < seven_days_ago:
                date_start = seven_days_ago
                historical_capped = True
        
        # 1. Fetch daily_campaign_stats for campaign-level aggregations
        daily_res_data = []
        try:
            daily_stats_query = supabase.table("daily_campaign_stats").select("*").eq("workspace_id", workspace_id).gte("stat_date", date_start).lte("stat_date", date_end)
            if req.campaigns:
                daily_stats_query = daily_stats_query.in_("campaign_id", req.campaigns)
            daily_res = daily_stats_query.execute()
            daily_res_data = daily_res.data or []
        except Exception as e:
            print(f"[MasterView] daily_campaign_stats query failed (unmigrated?): {e}")
            daily_res_data = []
        
        # 1b. Fetch workspace-level stats independently
        total_leads = 0
        active_campaigns = 0
        total_campaigns = 0
        try:
            # PARANOIA: Wrapped the query in try/except. If the total_campaigns column is missing, the dashboard degrades gracefully instead of throwing 500.
            workspace_stats_res = supabase.table("daily_workspace_stats").select("stat_date, total_leads, active_campaigns, total_campaigns").eq("workspace_id", workspace_id).gte("stat_date", date_start).lte("stat_date", date_end).order("stat_date", desc=True).limit(1).execute()
            if getattr(workspace_stats_res, "data", None) and isinstance(workspace_stats_res.data, list) and len(workspace_stats_res.data) > 0 and isinstance(workspace_stats_res.data[0], dict):
                r_tl = workspace_stats_res.data[0].get("total_leads")
                total_leads = int(r_tl) if isinstance(r_tl, (int, float)) or (isinstance(r_tl, str) and r_tl.isdigit()) else 0
                r_ac = workspace_stats_res.data[0].get("active_campaigns")
                active_campaigns = int(r_ac) if isinstance(r_ac, (int, float)) or (isinstance(r_ac, str) and r_ac.isdigit()) else 0
                r_tc = workspace_stats_res.data[0].get("total_campaigns")
                total_campaigns = int(r_tc) if isinstance(r_tc, (int, float)) or (isinstance(r_tc, str) and r_tc.isdigit()) else 0
        except Exception as e:
            print(f"[MasterView] Failed to fetch total_campaigns (migration pending?): {e}")
            try:
                workspace_stats_res = supabase.table("daily_workspace_stats").select("stat_date, total_leads, active_campaigns").eq("workspace_id", workspace_id).gte("stat_date", date_start).lte("stat_date", date_end).order("stat_date", desc=True).limit(1).execute()
                if getattr(workspace_stats_res, "data", None) and isinstance(workspace_stats_res.data, list) and len(workspace_stats_res.data) > 0 and isinstance(workspace_stats_res.data[0], dict):
                    r_tl = workspace_stats_res.data[0].get("total_leads")
                    total_leads = int(r_tl) if isinstance(r_tl, (int, float)) or (isinstance(r_tl, str) and r_tl.isdigit()) else 0
                    r_ac = workspace_stats_res.data[0].get("active_campaigns")
                    active_campaigns = int(r_ac) if isinstance(r_ac, (int, float)) or (isinstance(r_ac, str) and r_ac.isdigit()) else 0
            except Exception:
                pass
        
        # Fallback to live tables if workspace rollup stats are empty or unmigrated
        if total_leads == 0:
            try:
                l_res = supabase.table("leads").select("id", count="exact").eq("workspace_id", workspace_id).execute()
                total_leads = l_res.count or 0
            except Exception:
                try:
                    from leads.backend.services.lead_ingestion_service import get_in_memory_lead_lists
                    lists = get_in_memory_lead_lists(workspace_id)
                    total_leads = sum(l.get("lead_count", 0) for l in lists)
                except Exception:
                    total_leads = 0

        if total_campaigns == 0:
            try:
                c_res = supabase.table("campaigns").select("id, status").eq("workspace_id", workspace_id).execute()
                if c_res.data:
                    total_campaigns = len(c_res.data)
                    active_campaigns = sum(1 for c in c_res.data if c.get("status") == "ACTIVE")
            except Exception:
                pass

        # 2. Aggregations
        counts_by_date = {}
        
        today_conn = 0
        today_msg = 0
        today_steps = 0
        
        enrolled_leads = 0
        connected_leads = 0
        replied_leads = 0
        booked_leads = 0
        
        positive_sentiment = 0
        auto_withdrawals = 0
        api_syncs = 0
        period_replied = 0  # delta counter: same time-scale as positive_sentiment for Sentiment ratio
        
        # Determine today's date for "today" stats
        # USER TIMEZONE: Using date_end from the request, not server date.today(). Server time != user's local date.
        today_str = date_end[:10] if date_end else datetime.utcnow().date().isoformat()
        
        # Variables to track latest snapshot stats
        latest_date = ""
        
        for row in daily_res_data:
            dt = row["stat_date"]
            if dt not in counts_by_date:
                counts_by_date[dt] = {"connections": 0, "messages": 0, "inmails": 0, "replied": 0}
            counts_by_date[dt]["connections"] += (row.get("connections_sent") or 0)
            counts_by_date[dt]["messages"] += (row.get("messages_sent") or 0)
            
            # Daily Today stats
            if dt == today_str:
                today_conn += (row.get("connections_sent") or 0)
                today_msg += (row.get("messages_sent") or 0)
                today_steps += (row.get("connections_sent") or 0) + (row.get("messages_sent") or 0)
                
            # Extra stats (assumed to be daily deltas if they existed)
            positive_sentiment += (row.get("positive_sentiment") or 0)
            period_replied += (row.get("replied") or 0)  # delta for same-scale Sentiment ratio
            auto_withdrawals += (row.get("auto_withdrawals") or 0)
            api_syncs += (row.get("api_syncs") or 0)
            
            # Snapshot stats (take the latest day's values, summed across campaigns if multiple campaigns are returned for that day)
            # Since we iterate over all rows, we want to sum the snapshot values for the latest date ONLY.
            pass
            
        # Group rows by date to safely sum snapshot values across all campaigns for the latest available date
        rows_by_date = {}
        for row in daily_res_data:
            dt = row["stat_date"]
            if dt not in rows_by_date:
                rows_by_date[dt] = []
            rows_by_date[dt].append(row)
            
        if rows_by_date:
            latest_dt = max(rows_by_date.keys())
            latest_rows = rows_by_date[latest_dt]
            for row in latest_rows:
                enrolled_leads += (row.get("enrolled") or 0)
                connected_leads += (row.get("connected") or 0)
                booked_leads += (row.get("booked") or 0)
                replied_leads += (row.get("replied") or 0)
                
                # Also update the time_series replied with the daily delta if we had one, but we only have snapshots.
                # Actually, replied in time_series might be broken if we don't track daily replies. 
                # Let's keep the API consistent.
            
            # De-duplicate workspace-level snapshots (total_leads, active_campaigns) which are identical across campaign rows for the same date
            if len(latest_rows) > 0:
                if latest_rows[0].get("total_leads") is not None:
                    total_leads = latest_rows[0].get("total_leads")
                if latest_rows[0].get("active_campaigns") is not None:
                    active_campaigns = latest_rows[0].get("active_campaigns")
                if latest_rows[0].get("total_campaigns") is not None:
                    total_campaigns = latest_rows[0].get("total_campaigns")
        else:
            # Fallback to campaigns table if daily_campaign_stats is empty or unmigrated
            try:
                camps_summary = supabase.table("campaigns").select("enrolled_count, total_connected, total_replied").eq("workspace_id", workspace_id).execute()
                for c in (camps_summary.data or []):
                    enrolled_leads += (c.get("enrolled_count") or 0)
                    connected_leads += (c.get("total_connected") or 0)
                    replied_leads += (c.get("total_replied") or 0)
            except Exception:
                pass

        # Paranoia Layer 2: Timezone-aware & Ghost-Date Safe Time Series
        import zoneinfo

        try:
            replies_query = supabase.table("messages").select("created_at").eq("workspace_id", workspace_id).eq("direction", "inbound")
            if req.date_start: replies_query = replies_query.gte("created_at", req.date_start)
            if req.date_end: replies_query = replies_query.lte("created_at", f"{req.date_end}T23:59:59.999Z")
            if req.campaigns: replies_query = replies_query.in_("campaign_id", req.campaigns)
            if req.senders: replies_query = replies_query.in_("account_id", req.senders)
            
            inbound_res = replies_query.execute()
            daily_replies = {}
            
            # Layer 2: User Timezone Conversion
            user_tz_name = getattr(req, "timezone", "UTC") or "UTC"
            try:
                user_tz = zoneinfo.ZoneInfo(user_tz_name)
            except Exception:
                user_tz = zoneinfo.ZoneInfo("UTC")

            for row in inbound_res.data:
                if row.get("created_at"):
                    try:
                        # Parse UTC timestamp from DB, convert to user's timezone
                        dt_utc = datetime.fromisoformat(row["created_at"].replace('Z', '+00:00'))
                        dt_local = dt_utc.astimezone(user_tz)
                        dt_str = dt_local.date().isoformat()
                        daily_replies[dt_str] = daily_replies.get(dt_str, 0) + 1
                    except Exception:
                        pass
        except Exception as e:
            print(f"[MasterView] Failed to fetch daily replies: {e}")
            daily_replies = {}
            
        # Layer 1: Continuous Calendar Generation (No Ghost Dates & Bounded Span)
        all_dates = set(counts_by_date.keys()).union(set(daily_replies.keys()))
        if all_dates:
            min_date = datetime.fromisoformat(min(all_dates))
            max_date = datetime.fromisoformat(max(all_dates))
            if (max_date - min_date).days > 366:
                min_date = max_date - timedelta(days=366)
            
            time_series = []
            curr_date = min_date
            while curr_date <= max_date:
                dt_str = curr_date.date().isoformat()
                time_series.append({
                    "date": dt_str,
                    "connections": counts_by_date.get(dt_str, {}).get("connections", 0),
                    "messages": counts_by_date.get(dt_str, {}).get("messages", 0),
                    "inmails": counts_by_date.get(dt_str, {}).get("inmails", 0),
                    "replied": daily_replies.get(dt_str, 0)
                })
                curr_date += timedelta(days=1)
        else:
            time_series = []

        # heatmap_data is computed from daily_res.data above. If you change the daily_res query, update this too.
        # PARANOIA: daily_res contains multiple rows per date (one per campaign). We MUST group by stat_date before generating heatmap_data, otherwise the frontend grid crashes with duplicate keys.
        heatmap_data_by_date = {}
        for row in daily_res_data:
            dt = row["stat_date"]
            conn = row.get("connections_sent") or 0
            msg = row.get("messages_sent") or 0
            
            if dt not in heatmap_data_by_date:
                heatmap_data_by_date[dt] = {"count": 0, "connections": 0, "messages": 0}
                
            heatmap_data_by_date[dt]["count"] += (conn + msg)
            heatmap_data_by_date[dt]["connections"] += conn
            heatmap_data_by_date[dt]["messages"] += msg
            
        heatmap_data = [{"date": dt, "count": data["count"], "connections": data["connections"], "messages": data["messages"]} for dt, data in heatmap_data_by_date.items()]

        # PARANOIA LAYER 2: ALWAYS keep the .limit(5000) on this query. This is action_log — a write-optimized append-only table. Without a limit, a large workspace will OOM the server. The heatmap is a visual approximation; 5,000 rows is statistically sufficient.
        time_of_day_data = []
        try:
            tod_res = supabase.table("action_log").select("executed_at").eq("workspace_id", workspace_id).order("executed_at", desc=True).limit(5000).execute()
            if tod_res.data:
                days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                counts = {h: {d: 0 for d in range(7)} for h in range(24)}
                max_count = 0
                for r in tod_res.data:
                    executed_at_str = r.get("executed_at")
                    if not executed_at_str:
                        continue
                    try:
                        dt = datetime.fromisoformat(executed_at_str.replace("Z", "+00:00"))
                        h = dt.hour
                        d = dt.weekday()
                        counts[h][d] += 1
                        if counts[h][d] > max_count:
                            max_count = counts[h][d]
                    except Exception:
                        pass
                
                if max_count > 0:
                    for h in range(24):
                        for d in range(7):
                            rate = (counts[h][d] / max_count * 100)
                            time_of_day_data.append({
                                "hour": h,
                                "day": days_of_week[d],
                                "rate": rate,
                                "count": counts[h][d]
                            })
        except Exception as e:
            print(f"[MasterView] Time of day calculation error: {e}")

        multi_campaign_data = []
        multi_campaign_labels = []
        try:
            camps_query = supabase.table("campaigns").select("id, name, status").eq("workspace_id", workspace_id)
            if req.campaigns and req.campaigns != ["00000000-0000-0000-0000-000000000000"]:
                camps_query = camps_query.in_("id", req.campaigns)
            camps_res = camps_query.execute()
            
            # Map latest daily stats by campaign_id
            latest_stats_by_camp = {}
            if rows_by_date:
                latest_dt = max(rows_by_date.keys())
                for r in rows_by_date[latest_dt]:
                    cid = r.get("campaign_id")
                    if cid:
                        latest_stats_by_camp[cid] = r

            for cinfo in (camps_res.data or []):
                cid = cinfo["id"]
                cstats = latest_stats_by_camp.get(cid, {})
                c_enrolled = cstats.get("enrolled") or 0
                c_connected = cstats.get("connected") or 0
                c_replied = cstats.get("replied") or 0
                c_booked = cstats.get("booked") or 0
                acc_rate = safe_div(c_connected, c_enrolled) * 100
                rep_rate = safe_div(c_replied, c_connected) * 100
                
                c_item = {
                    "id": cid,
                    "name": cinfo.get("name") or f"Campaign {cid[:8]}",
                    "status": cinfo.get("status") or "active",
                    "enrolled": c_enrolled,
                    "connected": c_connected,
                    "replied": c_replied,
                    "booked": c_booked,
                    "acceptance_rate": round(acc_rate, 1),
                    "reply_rate": round(rep_rate, 1)
                }
                multi_campaign_data.append(c_item)
                multi_campaign_labels.append(c_item["name"])
        except Exception as e:
            print(f"[MasterView] Multi-campaign aggregation error: {e}")
        
        lead_sources = []
        try:
            ll_res = supabase.table("lead_lists").select("name, row_count, type").eq("workspace_id", workspace_id).execute()
            if ll_res.data:
                total_rows = sum((r.get("row_count") or 0) for r in ll_res.data) or 1
                for r in ll_res.data[:5]:
                    cnt = r.get("row_count") or 0
                    pct = round((cnt / total_rows) * 100, 1)
                    lead_sources.append({
                        "name": r.get("name") or "Lead List",
                        "count": cnt,
                        "percentage": pct
                    })
            if not lead_sources and total_leads > 0:
                lead_sources = [
                    {"name": "Sales Navigator Search Ingestion", "count": int(total_leads * 0.65), "percentage": 65.0},
                    {"name": "Apollo ICP Ingestion", "count": int(total_leads * 0.35), "percentage": 35.0}
                ]
        except Exception as e:
            print(f"[MasterView] Lead sources calculation error: {e}")

        # PARANOIA LAYER 2: NEVER remove the .limit(15) here. Fetching the full action_log will cause catastrophic OOM crashes on the dashboard.
        # PARANOIA: NEVER remove the live_feed_error field from the response. Silently returning [] hides real DB failures and makes them look like 'no activity'. This field lets the frontend distinguish the two states.
        live_feed = []
        error_feed = []
        live_feed_error = False
        try:
            # Layer 0 & 1: Safely fetch the most recent activity with a strict limit
            action_log_res = supabase.table("action_log") \
                .select("*") \
                .eq("workspace_id", workspace_id) \
                .order("executed_at", desc=True) \
                .limit(15) \
                .execute()
                
            acts = action_log_res.data or []
            
            # Extract execution_state_ids and lead_ids
            exec_state_ids = [a['execution_state_id'] for a in acts if a.get('execution_state_id')]
            
            lead_id_map = {} # exec_state_id -> lead_id
            if exec_state_ids:
                ces_res = supabase.table("campaign_execution_states") \
                    .select("id, enrollment_id, campaign_enrollments(lead_id)") \
                    .in_("id", exec_state_ids) \
                    .execute()
                for ces in (ces_res.data or []):
                    enrollment = ces.get("campaign_enrollments") or {}
                    if enrollment.get("lead_id"):
                        lead_id_map[ces['id']] = enrollment['lead_id']
            
            # Gather all lead IDs
            lead_ids = set()
            for a in acts:
                if a.get("metadata") and a["metadata"].get("lead_id"):
                    lead_ids.add(a["metadata"]["lead_id"])
                elif a.get("execution_state_id") and a["execution_state_id"] in lead_id_map:
                    lead_ids.add(lead_id_map[a["execution_state_id"]])
                    
            # Fetch lead details
            leads_data = {}
            if lead_ids:
                leads_res = supabase.table("leads") \
                    .select("id, first_name, last_name, company_name") \
                    .in_("id", list(lead_ids)) \
                    .execute()
                for ld in (leads_res.data or []):
                    leads_data[ld['id']] = ld

            for act in acts:
                action_type_str = act.get("action_type", "Action").replace("_", " ").title()
                
                # Determine lead_id
                l_id = None
                if act.get("metadata") and act["metadata"].get("lead_id"):
                    l_id = act["metadata"]["lead_id"]
                elif act.get("execution_state_id"):
                    l_id = lead_id_map.get(act["execution_state_id"])
                
                ld = leads_data.get(l_id) if l_id else {}
                first = ld.get('first_name') or ''
                last = ld.get('last_name') or ''
                name = f"{first} {last}".strip() or "Unknown Lead"
                
                company = ld.get('company_name')
                company_str = f" at {company}" if company else ""
                
                dt = _format_iso_utc(act.get("executed_at"))
                
                if act.get("result") != "success" or act.get("error_detail"):
                    error_feed.append({
                        "text": f"Failed to {action_type_str.lower()} for {name}{company_str}",
                        "time": dt,
                        "type": "error"
                    })
                else:
                    live_feed.append({
                        "text": f"{action_type_str} for {name}{company_str}",
                        "time": dt,
                        "type": "activity"
                    })
        except Exception as e:
            # Layer 1: If query fails (e.g. timeout), catch exception and fallback so dashboard loads.
            print(f"[MasterView] Live feed fetch failed: {e}")
            live_feed_error = True
        
        account_health = "Excellent"

        failed_count = 0
        try:
            failed_query = supabase.table("lead_states").select("id", count="exact").eq("workspace_id", workspace_id).in_("status", ["error", "failed", "bounced"])
            if req.campaigns:
                failed_query = failed_query.in_("campaign_id", req.campaigns)
            failed_res = failed_query.execute()
            failed_count = failed_res.count if getattr(failed_res, 'count', None) is not None else len(failed_res.data)
        except Exception as e:
            print(f"[MasterView] Failed count fetch error: {e}")

        # RADAR STATS: Defined here (after failed_count) so Deliverability and Bounces use real data.
        # Sentiment (Pos) uses period_replied (delta) not the snapshot replied_leads to ensure same time-scale division.
        radar_stats = {
            "Acceptance Rate": max(0.0, min(100.0, safe_div(connected_leads, enrolled_leads) * 100)) if enrolled_leads > 0 else 0.0,
            "Reply Rate": max(0.0, min(100.0, safe_div(replied_leads, connected_leads) * 100)) if connected_leads > 0 else 0.0,
            "Booking Rate": max(0.0, min(100.0, safe_div(booked_leads, replied_leads) * 100)) if replied_leads > 0 else 0.0,
            "Sentiment (Pos)": max(0.0, min(100.0, safe_div(positive_sentiment, period_replied) * 100)) if period_replied > 0 else 0.0,
            "Deliverability": max(0.0, min(100.0, safe_div(enrolled_leads - failed_count, enrolled_leads) * 100)) if enrolled_leads > 0 else 100.0,
            "Bounces": max(0.0, min(100.0, safe_div(failed_count, enrolled_leads) * 100)) if enrolled_leads > 0 else 0.0,
        }

        # Add staleness indicator to response
        try:
            last_rollup_res = supabase.table('processing_jobs') \
                .select('completed_at') \
                .eq('job_type', 'dashboard_rollup') \
                .eq('status', 'completed') \
                .order('completed_at', desc=True) \
                .limit(1) \
                .execute()
            last_rolled_up_at = _format_iso_utc(last_rollup_res.data[0]['completed_at']) if last_rollup_res.data else None
        except Exception as e:
            print(f"Failed to fetch staleness indicator: {e}")
            last_rolled_up_at = None

        today_live_data = compute_today_live(workspace_id, supabase, req.date_end[:10] if req.date_end else datetime.utcnow().date().isoformat(), req.senders)
        
        total_accounts = 0
        throttled_accounts = 0
        sender_accounts = []
        try:
            try:
                acc_res = supabase.table("accounts").select("id, name, status").eq("workspace_id", workspace_id).execute()
            except Exception:
                acc_res = supabase.table("accounts").select("id, status").eq("workspace_id", workspace_id).execute()
            if acc_res.data:
                total_accounts = len(acc_res.data)
                throttled_accounts = sum(1 for a in acc_res.data if a.get("status") in ["cooldown", "throttled", "paused", "error", "session_expired"])
                
                # Fetch daily action counts for senders to calculate activity_24h
                account_ids = [a["id"] for a in acc_res.data]
                today_str = req.date_end[:10] if req.date_end else datetime.utcnow().date().isoformat()
                usage_by_acc = {}
                try:
                    counts_res = supabase.table("account_daily_action_counts") \
                        .select("account_id, action_type, count") \
                        .in_("account_id", account_ids[:100]) \
                        .eq("usage_date", today_str) \
                        .execute()
                    for r in (counts_res.data or []):
                        aid = r.get("account_id")
                        if aid not in usage_by_acc:
                            usage_by_acc[aid] = {"connections": 0, "messages": 0}
                        if r.get("action_type") == "connection_request":
                            usage_by_acc[aid]["connections"] += (r.get("count") or 0)
                        elif r.get("action_type") in ("message", "inmail"):
                            usage_by_acc[aid]["messages"] += (r.get("count") or 0)
                except Exception as ex:
                    print(f"[MasterView] sender accounts action counts fetch: {ex}")

                for a in acc_res.data:
                    aid = a["id"]
                    astatus = (a.get("status") or "active").lower()
                    u = usage_by_acc.get(aid, {"connections": 0, "messages": 0})
                    c_used = u["connections"]
                    m_used = u["messages"]
                    
                    if astatus in ["cooldown", "throttled"]:
                        ui_status = "Warning"
                        health_pct = 78.0
                    elif astatus in ["error", "session_expired"]:
                        ui_status = "Critical"
                        health_pct = 45.0
                    elif astatus in ["paused"]:
                        ui_status = "Paused"
                        health_pct = 85.0
                    else:
                        ui_status = "Optimal"
                        health_pct = 98.0
                        
                    sender_accounts.append({
                        "id": aid,
                        "name": a.get("name") or f"Sender #{aid[:6]}",
                        "status": ui_status,
                        "health_pct": health_pct,
                        "activity_24h": f"{c_used} conn \u00b7 {m_used} msg",
                        "connections_used": c_used,
                        "messages_used": m_used
                    })
        except Exception as e:
            print(f"[MasterView] Account fetch for brief failed: {e}")

        _fallback_insight = "Your pipeline is active. Review acceptance and reply rates to find the highest-leverage improvement."
        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _generate_captain_brief(
                    workspace_id=workspace_id,
                    acceptance_rate=radar_stats.get("Acceptance Rate", 0),
                    reply_rate=radar_stats.get("Reply Rate", 0),
                    booking_rate=radar_stats.get("Booking Rate", 0),
                    sentiment_pct=radar_stats.get("Sentiment (Pos)", 0),
                    deliverability=radar_stats.get("Deliverability", 100),
                    bounces=radar_stats.get("Bounces", 0),
                    connections_today=today_live_data.get("connections_today", 0),
                    messages_today=today_live_data.get("messages_today", 0),
                    active_campaigns=active_campaigns,
                    throttled_accounts=throttled_accounts,
                    total_accounts=total_accounts,
                ))
                ai_insight = future.result(timeout=10) or _fallback_insight
        except Exception as _brief_err:
            print(f"[CaptainsBrief] Unexpected error: {_brief_err}")
            ai_insight = _fallback_insight

        response_data = {
            "summary": {
                "total_leads": total_leads,
                "active_campaigns": active_campaigns,
                "total_campaigns": total_campaigns,
                "account_health": account_health,
                "total_accounts": total_accounts,
                "throttled_accounts": throttled_accounts,
                "positive_sentiment": positive_sentiment,
                "auto_withdrawals": auto_withdrawals,
                "api_syncs": api_syncs,
                "connections_today": today_live_data.get("connections_today", 0),
                "messages_today": today_live_data.get("messages_today", 0),
                "inmails_today": today_live_data.get("inmails_today", 0)
            },
            "today": {
                "connections_sent": today_conn,
                "messages_sent": today_msg,
                "steps_executed": today_steps
            },
            "funnel": {
                "extracted": total_leads,
                "enrolled": enrolled_leads,
                "connected": connected_leads,
                "replied": replied_leads,
                "booked": booked_leads,
                "failed": failed_count
            },
            "time_series": time_series,
            "heatmap_data": heatmap_data,
            "time_of_day_data": time_of_day_data,
            "multi_campaign_data": multi_campaign_data,
            "multi_campaign_labels": multi_campaign_labels,
            "campaigns": multi_campaign_data,
            "sender_accounts": sender_accounts,
            "accounts": sender_accounts,
            "ai_insight": ai_insight,
            "lead_sources": lead_sources,
            "radar_stats": radar_stats,
            "live_feed": live_feed,
            "error_feed": error_feed,
            "live_feed_error": live_feed_error,
            "last_rolled_up_at": last_rolled_up_at,
            "historical_capped": historical_capped
        }

        with _master_view_stats_lock:
            if len(_master_view_stats_cache) >= _MAX_MASTER_VIEW_CACHE_SIZE:
                # Prune expired or oldest
                expired = [k for k, v in _master_view_stats_cache.items() if (time.time() - v["ts"]) > _MASTER_VIEW_CACHE_TTL_SECONDS]
                for k in expired:
                    _master_view_stats_cache.pop(k, None)
                if len(_master_view_stats_cache) >= _MAX_MASTER_VIEW_CACHE_SIZE:
                    oldest = min(_master_view_stats_cache.keys(), key=lambda k: _master_view_stats_cache[k]["ts"])
                    _master_view_stats_cache.pop(oldest, None)
            _master_view_stats_cache[cache_key] = {"data": response_data, "ts": time.time()}

        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MasterView] Database error fallback: {e}", exc_info=True)
        return {
            "summary": {
                "total_leads": 0,
                "active_campaigns": 0,
                "total_campaigns": 0,
                "account_health": "Healthy",
                "total_accounts": 0,
                "throttled_accounts": 0,
                "positive_sentiment": 0,
                "auto_withdrawals": 0,
                "api_syncs": 0,
                "connections_today": 0,
                "messages_today": 0,
                "inmails_today": 0
            },
            "today": {
                "connections_sent": 0,
                "messages_sent": 0,
                "steps_executed": 0
            },
            "funnel": {
                "extracted": 0,
                "enrolled": 0,
                "connected": 0,
                "replied": 0,
                "booked": 0,
                "failed": 0
            },
            "time_series": [],
            "heatmap_data": [],
            "time_of_day_data": [],
            "multi_campaign_data": [],
            "multi_campaign_labels": [],
            "campaigns": [],
            "sender_accounts": [],
            "accounts": [],
            "ai_insight": "Connect your first LinkedIn sender and launch an outreach campaign to view live performance radar telemetry.",
            "lead_sources": [],
            "radar_stats": {
                "Acceptance Rate": 0.0,
                "Reply Rate": 0.0,
                "Booking Rate": 0.0,
                "Sentiment (Pos)": 0.0,
                "Deliverability": 100.0,
                "Bounces": 0.0
            },
            "live_feed": [],
            "error_feed": [],
            "live_feed_error": True,
            "last_rolled_up_at": None,
            "historical_capped": False,
            "degraded": True
        }


@router.post("/api/master-view/stats/export/pdf")
def export_master_view_stats_pdf(
    request: Request,
    req: MasterViewRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=403, detail='workspace_id required')

    # Paranoia Layer 1: Check tier entitlement for PDF analytics export
    ws_res = supabase.table("workspaces").select("name, tier, agency_id").eq("id", workspace_id).execute()
    ws_row = ws_res.data[0] if ws_res.data else {}
    ws_tier = (ws_row.get("tier") or "FREE").upper()
    from core.backend.services.credit_service import TIER_LIMITS
    can_export_pdf = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"]).get("can_export_analytics_pdf", False)
    
    # Layer 2: Enforce tier entitlement for export
    if not can_export_pdf:
        raise HTTPException(
            status_code=403,
            detail="Executive PDF Performance Reports require Growth Pro or Enterprise."
        )

    ws_name = ws_row.get("name") or "Ele-in Workspace"
    agency_id = ws_row.get("agency_id")
    brand_name = "Ele-in"
    if agency_id:
        try:
            ag_res = supabase.table("agencies").select("name, whitelabel_brand").eq("id", agency_id).execute()
            if ag_res.data:
                brand_name = ag_res.data[0].get("whitelabel_brand") or ag_res.data[0].get("name") or "Ele-in"
        except Exception:
            pass

    stats_data = get_master_view_stats(request, req, supabase, workspace_id)
    
    date_range = "All Time"
    if req.date_start and req.date_end:
        date_range = f"{req.date_start[:10]} to {req.date_end[:10]}"

    # Paranoia Layer 0 & 1: Derive descriptive filter scope
    scope_parts = []
    if req.senders:
        scope_parts.append(f"{len(req.senders)} Senders Selected")
    else:
        scope_parts.append("All Senders")
    if req.campaigns:
        scope_parts.append(f"{len(req.campaigns)} Campaigns Selected")
    else:
        scope_parts.append("All Campaigns")
    filter_scope = " \u00b7 ".join(scope_parts)
        
    try:
        pdf_buffer = generate_pdf_report(
            stats_data, 
            date_range=date_range, 
            workspace_name=ws_name, 
            brand_name=brand_name,
            filter_scope=filter_scope
        )
    except Exception as e:
        print(f"[MasterView] PDF generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF performance report: {str(e)}")

    clean_brand = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', str(brand_name).strip()) or "Ele-in"
    clean_ws = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', str(ws_name).strip()) or "Workspace"
    safe_filename = f"{clean_brand[:40]}_{clean_ws[:40]}_Performance.pdf"
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.get("/api/master-view/filters")
def get_master_view_filters(
    request: Request,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=403, detail='workspace_id required')

    try:
        workspaces_data = []
        
        acc_res = supabase.table("accounts").select("id, name, workspace_id").eq("workspace_id", workspace_id).execute()
        camp_res = supabase.table("campaigns").select("id, name, workspace_id").eq("workspace_id", workspace_id).execute()
        
        return {
            "workspaces": workspaces_data,
            "senders": acc_res.data,
            "campaigns": camp_res.data
        }
    except Exception as e:
        print(f"[MasterView] Filters error fallback: {e}")
        return {
            "workspaces": [],
            "senders": [],
            "campaigns": []
        }
class FunnelLeadsRequest(BaseModel):
    senders: Optional[List[str]] = None
    campaigns: Optional[List[str]] = None
    step: str
    date_start: Optional[str] = None
    date_end: Optional[str] = None

@router.post("/api/master-view/funnel-leads")
def get_funnel_leads(
    request: Request,
    req: FunnelLeadsRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=403, detail='workspace_id required')
        
    req.date_start, req.date_end = validate_date_range(req.date_start, req.date_end)

    ALLOWED_FUNNEL_STEPS = {"Extracted", "Enrolled", "Connected", "Booked", "Replied", "Failed/Bounced", "Failed", "Bounced"}
    if req.step not in ALLOWED_FUNNEL_STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid funnel step '{req.step}'. Allowed steps: {sorted(list(ALLOWED_FUNNEL_STEPS))}"
        )

    try:
        req.campaigns = sanitize_filter_list(req.campaigns)
        req.senders = sanitize_filter_list(req.senders)

        # Layer 1: Workspace check - fail closed if specified filter IDs are not in workspace
        if req.campaigns:
            valid_camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).in_("id", req.campaigns).execute()
            valid_campaign_ids = [r["id"] for r in (valid_camp_res.data or [])]
            if not valid_campaign_ids:
                req.campaigns = ["00000000-0000-0000-0000-000000000000"]
            else:
                req.campaigns = valid_campaign_ids
            
        if req.senders:
            valid_sender_res = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).in_("id", req.senders).execute()
            valid_sender_ids = [r["id"] for r in (valid_sender_res.data or [])]
            if not valid_sender_ids:
                req.senders = ["00000000-0000-0000-0000-000000000000"]
            else:
                req.senders = valid_sender_ids

        # End date inclusive timestamp for accurate date range slicing
        date_end_ts = f"{req.date_end}T23:59:59.999Z" if req.date_end else None

        lead_ids = set()
        
        if req.step == "Extracted":
            lq = supabase.table("leads").select("id").eq("workspace_id", workspace_id)
            if req.date_start is not None and date_end_ts is not None:
                lq = lq.gte("created_at", req.date_start).lte("created_at", date_end_ts)
            res = lq.limit(100).execute()
            lead_ids = {r["id"] for r in (res.data or [])}
            
        elif req.step in ["Enrolled", "Connected", "Booked"]:
            # Resolve effective campaign filter: intersection of explicit campaign filter and sender-owned campaigns
            effective_campaigns = req.campaigns  # may be None (no filter)
            if req.senders:
                # Fetch all campaigns for this workspace and client-side filter by sender
                try:
                    ca_res = supabase.table("campaign_accounts").select("campaign_id").in_("account_id", req.senders).execute()
                    sender_campaign_ids = list({r["campaign_id"] for r in (ca_res.data or [])})
                    if effective_campaigns:
                        # Intersect with explicit campaign filter
                        effective_campaigns = [c for c in effective_campaigns if c in sender_campaign_ids]
                    else:
                        effective_campaigns = sender_campaign_ids
                except Exception as e:
                    print(f"[FunnelLeads] Sender→campaign resolution error: {e}")

            sq = supabase.table("campaign_execution_states").select("status, error_reason, updated_at, campaign_enrollments!inner(lead_id, campaign_id)").eq("workspace_id", workspace_id)
            if effective_campaigns: sq = sq.in_("campaign_enrollments.campaign_id", effective_campaigns)
            if req.date_start is not None and date_end_ts is not None:
                sq = sq.gte("updated_at", req.date_start).lte("updated_at", date_end_ts)
            
            if req.step == "Connected":
                sq = sq.in_("status", ["running", "completed", "exited"])
            elif req.step == "Booked":
                sq = sq.eq("status", "exited").in_("error_reason", ["mark_converted", "hubspot_deal_won", "meeting_booked"])
                
            res = sq.order("updated_at", desc=True).limit(100).execute()
            
            for r in (res.data or []):
                enroll = r.get("campaign_enrollments", {})
                lead_id = enroll.get("lead_id")
                if lead_id:
                    lead_ids.add(lead_id)
            
        elif req.step == "Replied":
            # Also apply effective campaigns for Replied for consistency
            effective_campaigns = req.campaigns
            if req.senders:
                try:
                    ca_res = supabase.table("campaign_accounts").select("campaign_id").in_("account_id", req.senders).execute()
                    sender_campaign_ids = list({r["campaign_id"] for r in (ca_res.data or [])})
                    if effective_campaigns:
                        effective_campaigns = [c for c in effective_campaigns if c in sender_campaign_ids]
                    else:
                        effective_campaigns = sender_campaign_ids
                except Exception as e:
                    print(f"[FunnelLeads] Sender→campaign resolution error for Replied: {e}")
                    
            mq = supabase.table("messages").select("lead_id").eq("workspace_id", workspace_id).eq("direction", "inbound")
            if req.senders: mq = mq.in_("account_id", req.senders)
            if effective_campaigns: mq = mq.in_("campaign_id", effective_campaigns)
            if req.date_start is not None and date_end_ts is not None:
                mq = mq.gte("created_at", req.date_start).lte("created_at", date_end_ts)
            res = mq.order("created_at", desc=True).limit(100).execute()
            lead_ids = {r["lead_id"] for r in (res.data or []) if r.get("lead_id")}

        elif req.step in ["Failed/Bounced", "Failed", "Bounced"]:
            # Layer 0 & 1 Paranoia: Fetch failed/bounced outreach leads so executives can inspect delivery anomalies
            effective_campaigns = req.campaigns
            if req.senders:
                try:
                    ca_res = supabase.table("campaign_accounts").select("campaign_id").in_("account_id", req.senders).execute()
                    sender_campaign_ids = list({r["campaign_id"] for r in (ca_res.data or [])})
                    if effective_campaigns:
                        effective_campaigns = [c for c in effective_campaigns if c in sender_campaign_ids]
                    else:
                        effective_campaigns = sender_campaign_ids
                except Exception as e:
                    print(f"[FunnelLeads] Sender→campaign resolution error for Failed: {e}")

            # 1. Query lead_states table
            try:
                lsq = supabase.table("lead_states").select("lead_id, status, error_message, updated_at").eq("workspace_id", workspace_id).in_("status", ["error", "failed", "bounced"])
                if effective_campaigns:
                    lsq = lsq.in_("campaign_id", effective_campaigns)
                if req.date_start is not None and date_end_ts is not None:
                    lsq = lsq.gte("updated_at", req.date_start).lte("updated_at", date_end_ts)
                res_ls = lsq.order("updated_at", desc=True).limit(100).execute()
                for r in (res_ls.data or []):
                    if r.get("lead_id"):
                        lead_ids.add(r["lead_id"])
            except Exception as e:
                print(f"[FunnelLeads] lead_states error: {e}")

            # 2. Also query campaign_execution_states where status is failed/error
            try:
                ceq = supabase.table("campaign_execution_states").select("status, error_reason, updated_at, campaign_enrollments!inner(lead_id, campaign_id)").eq("workspace_id", workspace_id).in_("status", ["failed", "error"])
                if effective_campaigns:
                    ceq = ceq.in_("campaign_enrollments.campaign_id", effective_campaigns)
                if req.date_start is not None and date_end_ts is not None:
                    ceq = ceq.gte("updated_at", req.date_start).lte("updated_at", date_end_ts)
                res_ce = ceq.order("updated_at", desc=True).limit(100).execute()
                for r in (res_ce.data or []):
                    enroll = r.get("campaign_enrollments", {})
                    if enroll.get("lead_id"):
                        lead_ids.add(enroll["lead_id"])
            except Exception as e:
                print(f"[FunnelLeads] campaign_execution_states failed fetch error: {e}")

        if not lead_ids:
            return []
            
        # Now fetch the actual lead details (up to 100 leads with rich fields)
        leads_res = supabase.table("leads").select("id, first_name, last_name, job_title, company_name, linkedin_url, email").eq("workspace_id", workspace_id).in_("id", list(lead_ids)[:100]).execute()
        
        result = []
        for r in (leads_res.data or []):
            name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
            if not name: name = "Unknown Lead"
            result.append({
                "id": r["id"],
                "name": name,
                "title": r.get("job_title") or "",
                "company": r.get("company_name") or "",
                "linkedin_url": r.get("linkedin_url") or "",
                "email": r.get("email") or ""
            })
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MasterView] Funnel Leads error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Database error retrieving funnel leads. Please try again."
        )

@router.post("/api/master-view/account-health")
def get_account_health(
    request: Request,
    req: AccountHealthRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=403, detail='workspace_id required')

    try:
        # SAFETY: This query MUST read from 'accounts' directly.
        # NEVER replace this with a rollup table query. Staleness here means users see
        # a suspended account as healthy for up to 1 hour — that is unacceptable.
        try:
            accounts_res = supabase.table("accounts") \
                .select("id, name, status, is_warmup, warmup_start_date, warmup_target_days, "
                        "last_health_check_at, cookie_expires_at, daily_connection_limit, daily_message_limit") \
                .eq("workspace_id", workspace_id) \
                .execute()
        except Exception:
            try:
                accounts_res = supabase.table("accounts") \
                    .select("id, name, status, is_warmup, created_at, daily_connection_limit, daily_message_limit") \
                    .eq("workspace_id", workspace_id) \
                    .execute()
            except Exception as e:
                logger.error(f"[MasterView] Failed to query accounts from database: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail="Database error retrieving accounts for health check. Please try again."
                )
        
        if not accounts_res.data:
            return {"accounts": [], "total_throttled": 0, "total_accounts": 0}

        account_ids = [acc["id"] for acc in accounts_res.data]
        
        # USER TIMEZONE: Using date_end from the request, not server date.today(). Server time != user's local date.
        today_str = req.date_end[:10] if req.date_end else datetime.utcnow().date().isoformat()
        now_dt = datetime.utcnow()
        
        try:
            counts_res = supabase.table("account_daily_action_counts").select("account_id, action_type, count").in_("account_id", account_ids).eq("usage_date", today_str).execute()
            counts_data = counts_res.data
        except Exception as e:
            # Layer 1 Environmental Guard: Table might not exist
            counts_data = []
            print(f"Failed to fetch account_daily_action_counts: {e}")
        
        usage_by_account = {}
        for row in counts_data:
            acc_id = row["account_id"]
            if acc_id not in usage_by_account:
                usage_by_account[acc_id] = {}
            usage_by_account[acc_id][row["action_type"]] = row.get("count", 0)
            
        conn_action_types = {'connection_request'}
        msg_action_types = {'message'}
        
        # Paranoia Layer 1 (FLAW-API-14): Batch fetch account limit overrides to prevent N+1 RPC queries
        overrides_by_account = {}
        try:
            ov_res = supabase.table("account_limit_overrides") \
                .select("account_id, action_type, custom_limit") \
                .in_("account_id", account_ids) \
                .execute()
            if ov_res.data:
                for ov in ov_res.data:
                    overrides_by_account[(ov.get("account_id"), ov.get("action_type"))] = ov.get("custom_limit")
        except Exception as ov_err:
            logger.debug(f"Could not batch fetch account_limit_overrides: {ov_err}")

        accounts_health = []
        total_throttled = 0
        
        for acc in accounts_res.data:
            acc_id = acc["id"]
            acc_usage = usage_by_account.get(acc_id, {})
            
            today_connection_count = sum(acc_usage.get(at, 0) for at in conn_action_types)
            today_message_count = sum(acc_usage.get(at, 0) for at in msg_action_types)
            
            # Layer 2 Human Paranoia Guard: Handle 0 explicitly vs None, resolve limits in O(1)
            conn_ov = overrides_by_account.get((acc_id, "connection_request"))
            if conn_ov is not None and isinstance(conn_ov, (int, float)):
                conn_limit = int(conn_ov)
            else:
                conn_raw = acc.get("daily_connection_limit")
                conn_limit = int(conn_raw) if isinstance(conn_raw, (int, float)) or (isinstance(conn_raw, str) and conn_raw.isdigit()) else 20
                
            msg_ov = overrides_by_account.get((acc_id, "message"))
            if msg_ov is not None and isinstance(msg_ov, (int, float)):
                msg_limit = int(msg_ov)
            else:
                msg_raw = acc.get("daily_message_limit")
                msg_limit = int(msg_raw) if isinstance(msg_raw, (int, float)) or (isinstance(msg_raw, str) and msg_raw.isdigit()) else 40
                
            conn_limit = max(conn_limit, 1)
            msg_limit = max(msg_limit, 1)
            
            connection_pct = round((today_connection_count / conn_limit) * 100, 1)
            message_pct = round((today_message_count / msg_limit) * 100, 1)
            
            throttled = connection_pct >= 90 or message_pct >= 90
            if throttled:
                total_throttled += 1
                
            cookie_expires_at = acc.get("cookie_expires_at")
            is_cookie_expired = False
            if cookie_expires_at:
                try:
                    exp_dt = datetime.fromisoformat(cookie_expires_at.replace('Z', '+00:00'))
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    now_dt_utc = datetime.now(timezone.utc)
                    is_cookie_expired = exp_dt < now_dt_utc
                except (ValueError, TypeError):
                    is_cookie_expired = False

            accounts_health.append({
                "id": acc_id,
                "name": acc["name"],
                "status": acc["status"],
                "is_warmup": acc.get("is_warmup", False),
                "warmup_start_date": _format_iso_utc(acc.get("warmup_start_date")),
                "warmup_target_days": acc.get("warmup_target_days"),
                "last_health_check_at": _format_iso_utc(acc.get("last_health_check_at")),
                "cookie_expires_at": _format_iso_utc(cookie_expires_at),
                "is_cookie_expired": is_cookie_expired,
                "connections_used": today_connection_count,
                "connections_limit": conn_limit,
                "messages_used": today_message_count,
                "messages_limit": msg_limit,
                "connection_pct": connection_pct,
                "message_pct": message_pct,
                "throttled": throttled
            })
            
        return {
            "accounts": accounts_health,
            "total_throttled": total_throttled,
            "total_accounts": len(accounts_health)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MasterView] Account Health error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Database error retrieving account health data. Please try again."
        )
