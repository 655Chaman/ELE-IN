from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import time

_captain_brief_cache: dict = {}
_CAPTAIN_BRIEF_TTL_SECONDS = 1800

from datetime import date, datetime, timedelta
from supabase import Client
from core.backend.api.auth_dep import get_supabase_client
from campaigns.backend.routers.elein import get_current_workspace
from fastapi.responses import StreamingResponse
from campaigns.backend.utils.pdf_generator import generate_pdf_report

# ==============================================================================
# 🚨 PARANOIA FRAMEWORK: SECURITY WARNING (LAYER 2) 🚨
# ==============================================================================
# The Python backend uses the Supabase service key, which BYPASSES Postgres 
# Row-Level Security (RLS). This means the database will NOT protect against 
# cross-tenant data spillage.
#
# CRITICAL RULES:
# 1. EVERY single `.select()`, `.update()`, or `.delete()` query MUST manually 
#    include `.eq("workspace_id", workspace_id)`.
# 2. If you forget this one line, you create a catastrophic IDOR vulnerability,
#    allowing users to steal or modify competitor data.
# 3. Before running ANY query, you MUST verify the `user_id` from the JWT 
#    exists in `workspace_members` for the requested `workspace_id`.
# ==============================================================================

# ==============================================================================
# DATA ARCHITECTURE MANDATE (PRE-AGGREGATION DISCIPLINE)
# ==============================================================================
# The dashboard must load INSTANTLY even at 10,000+ workspaces.
# To guarantee this, the dashboard API is FORBIDDEN from performing live
# aggregations over high-velocity tables like `messages` or `action_log`.
# 
# RULES:
# 1. You may ONLY query `daily_campaign_stats` and `daily_workspace_stats`.
# 2. These tables are populated asynchronously by the Postgres RPC `rollup_daily_stats`.
# 3. If the frontend needs a new metric, you MUST add it to the rollup job
#    and the stats tables. Do NOT write a live COUNT(*) query here.
# ==============================================================================
#
# ==================== DASHBOARD DATA CONTRACT ====================
# Widget                        | Grain   | Staleness    | Source Table
# Today's connections/messages  | Live    | NONE (live)  | account_daily_action_counts
# Campaign performance (trends) | Daily   | Hours        | daily_campaign_stats  
# Total leads / active campaigns| Daily   | Hours        | daily_workspace_stats
# Account health (status)       | Live    | NONE (live)  | accounts (direct)
# AI spend this month           | Daily   | Hours        | daily_campaign_stats / ai_generations
# =================================================================
# RULE: If you are writing a query against `action_log`, `messages`,
# or `lead_states` for dashboard cards, you are violating this contract.
# Those tables are WRITE paths. The dashboard is a READ path.
# Add your metric to the rollup job first, then read it here.
# =================================================================

router = APIRouter(tags=["master-view"])

def sanitize_filter_list(lst: Optional[List[str]]) -> Optional[List[str]]:
    if not lst:
        return None
    cleaned = [x for x in lst if x]
    return cleaned if len(cleaned) > 0 else None

def get_current_user_id(request: Request, supabase: Client = Depends(get_supabase_client)) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing auth header")
    token = auth_header.split(" ")[1]
    user_res = supabase.auth.get_user(token)
    if not user_res or not user_res.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_res.user.id

def validate_date_range(date_start: Optional[str], date_end: Optional[str], max_days: int = 4000) -> tuple[str, str]:
    if not date_end:
        # PARANOIA: If date_end is missing, we fall back to UTC. This is wrong for users not in UTC. The frontend should ALWAYS send an explicit date_end.
        from datetime import timezone
        date_end = datetime.now(timezone.utc).date().isoformat()
    if not date_start:
        date_start = (datetime.fromisoformat(date_end[:10]) - timedelta(days=30)).date().isoformat()
        
    try:
        start_dt = datetime.fromisoformat(date_start[:10])
        end_dt = datetime.fromisoformat(date_end[:10])
        if (end_dt - start_dt).days > max_days:
            raise HTTPException(
                status_code=400, 
                detail=f'Date range cannot exceed {max_days} days. Requested: {(end_dt - start_dt).days} days.'
            )
        if end_dt < start_dt:
            raise HTTPException(
                status_code=400,
                detail='date_end must be after date_start'
            )
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid date format. Use ISO 8601.')
    
    return date_start, date_end

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
    
    # Layer 1: Check TTL cache first — avoid hammering LLM on every page load
    cached = _captain_brief_cache.get(workspace_id)
    if cached and (time.time() - cached["ts"]) < _CAPTAIN_BRIEF_TTL_SECONDS:
        return cached["insight"]
    
    try:
        from knowledge.backend.services.elein_ai_service import _get_async_client, _resolve_model, get_active_nvidia_keys
        
        keys = get_active_nvidia_keys("summarize")
        if not keys:
            return None
            
        client = _get_async_client(keys[0]["key"])
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
        
        # Store in cache
        _captain_brief_cache[workspace_id] = {"insight": insight, "ts": time.time()}
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
    
    # Layer 1: Workspace check
    if req.campaigns:
        valid_camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).in_("id", req.campaigns).execute()
        valid_campaign_ids = [r["id"] for r in valid_camp_res.data]
        req.campaigns = sanitize_filter_list(valid_campaign_ids)
        
    if req.senders:
        valid_sender_res = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).in_("id", req.senders).execute()
        valid_sender_ids = [r["id"] for r in valid_sender_res.data]
        req.senders = sanitize_filter_list(valid_sender_ids)

    def safe_div(a, b):
        return a / b if b > 0 else 0

    try:
        date_start = req.date_start
        date_end = req.date_end
        
        # 1. Fetch daily_campaign_stats for campaign-level aggregations
        daily_stats_query = supabase.table("daily_campaign_stats").select("*").eq("workspace_id", workspace_id).gte("stat_date", date_start).lte("stat_date", date_end)
        if req.campaigns:
            daily_stats_query = daily_stats_query.in_("campaign_id", req.campaigns)
        daily_res = daily_stats_query.execute()
        
        # 1b. Fetch workspace-level stats independently
        try:
            # PARANOIA: Wrapped the query in try/except. If the total_campaigns column is missing, the dashboard degrades gracefully instead of throwing 500.
            workspace_stats_res = supabase.table("daily_workspace_stats").select("stat_date, total_leads, active_campaigns, total_campaigns").eq("workspace_id", workspace_id).gte("stat_date", date_start).lte("stat_date", date_end).order("stat_date", desc=True).limit(1).execute()
        except Exception as e:
            print(f"[MasterView] Failed to fetch total_campaigns (migration pending?): {e}")
            workspace_stats_res = supabase.table("daily_workspace_stats").select("stat_date, total_leads, active_campaigns").eq("workspace_id", workspace_id).gte("stat_date", date_start).lte("stat_date", date_end).order("stat_date", desc=True).limit(1).execute()
        
        total_leads = workspace_stats_res.data[0].get("total_leads") or 0 if workspace_stats_res.data else 0
        active_campaigns = workspace_stats_res.data[0].get("active_campaigns") or 0 if workspace_stats_res.data else 0
        total_campaigns = workspace_stats_res.data[0].get("total_campaigns") or 0 if workspace_stats_res.data else 0

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
        
        for row in daily_res.data:
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
        for row in daily_res.data:
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

        time_series = []
        for dt_str in sorted(counts_by_date.keys()):
            time_series.append({
                "date": dt_str,
                "connections": counts_by_date[dt_str]["connections"],
                "messages": counts_by_date[dt_str]["messages"],
                "inmails": counts_by_date[dt_str]["inmails"],
                "replied": 0  # We don't have daily replies tracked right now, only cumulative.
            })

        # heatmap_data is computed from daily_res.data above. If you change the daily_res query, update this too.
        # PARANOIA: daily_res contains multiple rows per date (one per campaign). We MUST group by stat_date before generating heatmap_data, otherwise the frontend grid crashes with duplicate keys.
        heatmap_data_by_date = {}
        for row in daily_res.data:
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
            print(f"[MasterView] Time of day fetch failed: {e}")
        multi_campaign_data = []
        multi_campaign_labels = []
        
        lead_sources = []
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
                
                dt = act.get("executed_at")
                
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
            "Acceptance Rate": min(safe_div(connected_leads, enrolled_leads) * 100, 100) if enrolled_leads > 0 else 0,
            "Reply Rate": min(safe_div(replied_leads, connected_leads) * 100, 100) if connected_leads > 0 else 0,
            "Booking Rate": min(safe_div(booked_leads, replied_leads) * 100, 100) if replied_leads > 0 else 0,
            "Sentiment (Pos)": min(safe_div(positive_sentiment, period_replied) * 100, 100) if period_replied > 0 else 0,
            "Deliverability": min(safe_div(enrolled_leads - failed_count, enrolled_leads) * 100, 100) if enrolled_leads > 0 else 100,
            "Bounces": min(safe_div(failed_count, enrolled_leads) * 100, 100) if enrolled_leads > 0 else 0,
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
            last_rolled_up_at = last_rollup_res.data[0]['completed_at'] if last_rollup_res.data else None
        except Exception as e:
            print(f"Failed to fetch staleness indicator: {e}")
            last_rolled_up_at = None

        today_live_data = compute_today_live(workspace_id, supabase, req.date_end[:10] if req.date_end else datetime.utcnow().date().isoformat(), req.senders)
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
                    throttled_accounts=0,
                    total_accounts=0,
                ))
                ai_insight = future.result(timeout=10) or _fallback_insight
        except Exception as _brief_err:
            print(f"[CaptainsBrief] Unexpected error: {_brief_err}")
            ai_insight = _fallback_insight

        return {
            "summary": {
                "total_leads": total_leads,
                "active_campaigns": active_campaigns,
                "total_campaigns": total_campaigns,
                "account_health": account_health,
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
            "ai_insight": ai_insight,
            "lead_sources": lead_sources,
            "radar_stats": radar_stats,
            "live_feed": live_feed,
            "error_feed": error_feed,
            "live_feed_error": live_feed_error,
            "last_rolled_up_at": last_rolled_up_at
        }
    except Exception as e:
        print("Master View Error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/master-view/stats/export/pdf")
def export_master_view_stats_pdf(
    request: Request,
    req: MasterViewRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    stats_data = get_master_view_stats(request, req, supabase, workspace_id)
    
    date_range = "All Time"
    if req.date_start and req.date_end:
        date_range = f"{req.date_start[:10]} to {req.date_end[:10]}"
        
    pdf_buffer = generate_pdf_report(stats_data, date_range=date_range)
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf", 
        headers={"Content-Disposition": "attachment; filename=EleIn_Performance_Overview.pdf"}
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
        print("Filters Error:", e)
        raise HTTPException(status_code=500, detail=str(e))
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

    try:
        req.campaigns = sanitize_filter_list(req.campaigns)
        req.senders = sanitize_filter_list(req.senders)

        if req.campaigns:
            valid_camp_res = supabase.table("campaigns").select("id").eq("workspace_id", workspace_id).in_("id", req.campaigns).execute()
            valid_campaign_ids = [r["id"] for r in valid_camp_res.data]
            req.campaigns = sanitize_filter_list(valid_campaign_ids)
            
        if req.senders:
            valid_sender_res = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).in_("id", req.senders).execute()
            valid_sender_ids = [r["id"] for r in valid_sender_res.data]
            req.senders = sanitize_filter_list(valid_sender_ids)

        pass

        lead_ids = set()
        
        if req.step == "Extracted":
            lq = supabase.table("leads").select("id").eq("workspace_id", workspace_id)
            if req.date_start is not None and req.date_end is not None:
                lq = lq.gte("created_at", req.date_start).lte("created_at", req.date_end)
            res = lq.limit(20).execute()
            lead_ids = {r["id"] for r in res.data}
            
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
            if req.date_start is not None and req.date_end is not None:
                sq = sq.gte("updated_at", req.date_start).lte("updated_at", req.date_end)
            
            if req.step == "Connected":
                sq = sq.in_("status", ["running", "completed", "exited"])
            elif req.step == "Booked":
                sq = sq.eq("status", "exited").in_("error_reason", ["mark_converted", "hubspot_deal_won", "meeting_booked"])
                
            res = sq.order("updated_at", desc=True).limit(50).execute()
            
            lead_ids = set()
            for r in res.data:
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
            if req.date_start is not None and req.date_end is not None:
                mq = mq.gte("created_at", req.date_start).lte("created_at", req.date_end)
            res = mq.order("created_at", desc=True).limit(50).execute()
            lead_ids = {r["lead_id"] for r in res.data if r.get("lead_id")}

        if not lead_ids:
            return []
            
        # Now fetch the actual lead details
        leads_res = supabase.table("leads").select("id, first_name, last_name, job_title, company_name").eq("workspace_id", workspace_id).in_("id", list(lead_ids)[:20]).execute()
        
        result = []
        for r in leads_res.data:
            name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
            if not name: name = "Unknown Lead"
            result.append({
                "id": r["id"],
                "name": name,
                "title": r.get("job_title") or "",
                "company": r.get("company_name") or ""
            })
            
        return result
    except Exception as e:
        print("Funnel Leads Error:", e)
        raise HTTPException(status_code=500, detail=str(e))

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
        accounts_res = supabase.table("accounts") \
            .select("id, name, status, is_warmup, warmup_start_date, warmup_target_days, "
                    "last_health_check_at, cookie_expires_at") \
            .eq("workspace_id", workspace_id) \
            .execute()
        
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
        
        accounts_health = []
        total_throttled = 0
        
        for acc in accounts_res.data:
            acc_id = acc["id"]
            acc_usage = usage_by_account.get(acc_id, {})
            
            today_connection_count = sum(acc_usage.get(at, 0) for at in conn_action_types)
            today_message_count = sum(acc_usage.get(at, 0) for at in msg_action_types)
            
            # Layer 2 Human Paranoia Guard: Handle 0 explicitly vs None, fetch unified limits
            try:
                conn_res = supabase.rpc("get_account_action_limit", {"p_account_id": acc_id, "p_action_type": "connection_request"}).execute()
                conn_limit = conn_res.data if conn_res.data is not None else 20
            except Exception:
                conn_limit = 20
                
            try:
                msg_res = supabase.rpc("get_account_action_limit", {"p_account_id": acc_id, "p_action_type": "message"}).execute()
                msg_limit = msg_res.data if msg_res.data is not None else 40
            except Exception:
                msg_limit = 40
                
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
                        is_cookie_expired = exp_dt < now_dt
                    else:
                        now_dt_utc = datetime.now(exp_dt.tzinfo)
                        is_cookie_expired = exp_dt < now_dt_utc
                except ValueError:
                    pass

            accounts_health.append({
                "id": acc_id,
                "name": acc["name"],
                "status": acc["status"],
                "is_warmup": acc.get("is_warmup", False),
                "warmup_start_date": acc.get("warmup_start_date"),
                "warmup_target_days": acc.get("warmup_target_days"),
                "last_health_check_at": acc.get("last_health_check_at"),
                "cookie_expires_at": cookie_expires_at,
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
    except Exception as e:
        print("Account Health Error:", e)
        raise HTTPException(status_code=500, detail=str(e))
