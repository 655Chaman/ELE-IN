from dotenv import load_dotenv
load_dotenv()
import os
import uuid
import threading
import time as _time


import json
import re
import math
from datetime import datetime, timedelta, date, time as dt_time, timezone
from typing import Dict, Any, List, Optional, Tuple
import random
import pytz
from core.backend.services.limits import get_effective_usage_date

from core.backend.api.auth_dep import get_service_client
from integrations.backend.services.linkedin_worker import LinkedInWorker
from campaigns.backend.services.collision_guard import is_lead_active_in_other_campaign

from core.backend.services.telemetry import capture_error
import logging
logger = logging.getLogger(__name__)

MAX_SEQUENCE_HOPS = 50



def _normalize_to_utc_iso(dt_val: Any) -> Optional[str]:
    """Normalizes any datetime or ISO string to timezone-aware UTC ISO format (YYYY-MM-DDTHH:MM:SS+00:00)."""
    if not dt_val:
        return None
    if isinstance(dt_val, datetime):
        dt = dt_val
    else:
        s = str(dt_val).strip()
        if not s:
            return None
        if s.endswith('Z') or s.endswith('z'):
            s = s[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            try:
                from dateutil.parser import parse
                dt = parse(s)
            except Exception:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


# ── GAP 4: Variable interpolation ────────────────────────────────────────────


def _sanitize_scraped_string(text: str, var_type: str = "") -> str:
    if not text:
        return ""
    
    # 1. Remove text inside brackets/parentheses completely
    text = re.sub(r'\(.*?\)', ' ', text)
    text = re.sub(r'\[.*?\]', ' ', text)
    text = re.sub(r'\{.*?\}', ' ', text)
    
    # 2. Remove common spam/titles/degrees
    phrases = [
        r'\bwe are hiring\b',
        r'\bactively hiring\b',
        r'\bhiring\b',
        r'\bwe\'re hiring\b',
        r'\bwe re hiring\b',
        r'\bdr\.?\b',
        r'\bph\.?d\.?\b',
        r'\bm\.?d\.?\b',
        r'\bmba\b',
        r'\bcpa\b',
        r'\bms\b',
        r'\bbsc\b',
        r'\bmsc\b',
        r'\bllc\b',
        r'\binc\.?\b',
        r'\bltd\.?\b',
        r'\bprof\.?\b'
    ]
    for phrase in phrases:
        text = re.sub(phrase, ' ', text, flags=re.IGNORECASE)
        
    # 3. Strip emojis and weird symbols (keep alphanumeric, space, hyphen, dot, apostrophe)
    text = re.sub(r'[^\w\s\-\'\.]', ' ', text)
    
    # 4. Cleanup trailing/leading punctuation
    text = re.sub(r'^[\s\-\.\',]+', '', text)
    text = re.sub(r'[\s\-\.\',]+$', '', text)
    
    # 5. Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def interpolate(template: str, opportunity: Dict[str, Any]) -> str:
    """
    Replaces {{first_name}}, {{company}}, etc. with real values from the opportunity row.
    Unknown variables are left as-is so they don't break the message.
    """
    if not template or not isinstance(template, str):
        return template or ""

    from campaigns.backend.services.template_spintax_guard import clean_enrichment_value, resolve_spintax

    mapping = {
        "first_name":    clean_enrichment_value(opportunity.get("kdm_first") or opportunity.get("first_name")),
        "last_name":     clean_enrichment_value(opportunity.get("kdm_last") or opportunity.get("last_name")),
        "company":       clean_enrichment_value(opportunity.get("company_name") or opportunity.get("company")),
        "company_name":  clean_enrichment_value(opportunity.get("company_name") or opportunity.get("company")),
        "job_title":     clean_enrichment_value(opportunity.get("job_title") or opportunity.get("title")),
        "title":         clean_enrichment_value(opportunity.get("job_title") or opportunity.get("title")),
        "location":      clean_enrichment_value(opportunity.get("location")),
        "industry":      clean_enrichment_value(opportunity.get("industry")),
        "mutual_connections": clean_enrichment_value(opportunity.get("mutual_connections")) or "a mutual connection",
    }

    def replace_var(m: re.Match) -> str:
        var_content = m.group(1).strip()
        parts = [p.strip() for p in var_content.split("|", 1)]
        raw_key = parts[0]
        key = raw_key[5:] if raw_key.startswith("lead.") else raw_key
        key_lower = key.lower()
        inline_fallback = clean_enrichment_value(parts[1]) if len(parts) > 1 else ("there" if key_lower in ("first_name", "firstname", "name") else ("your company" if key_lower in ("company", "company_name") else ("your role" if key_lower in ("job_title", "title") else "")))

        actual_val = mapping.get(key_lower) or opportunity.get(key) or opportunity.get(key_lower)
        cleaned_val = clean_enrichment_value(actual_val)

        if cleaned_val:
            return cleaned_val

        if inline_fallback:
            return inline_fallback

        return m.group(0)

    rendered = re.sub(r"\{\{([^}]+)\}\}", replace_var, template)
    seed_val = str(opportunity.get("id") or opportunity.get("linkedin_url") or "") or None
    return resolve_spintax(rendered, seed=seed_val)


def interpolate_node_data(data: Dict[str, Any], opportunity: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-interpolates all string values in a node's data dict."""
    result = {}
    for k, v in data.items():
        if isinstance(v, str):
            result[k] = interpolate(v, opportunity)
        else:
            result[k] = v
            
    # assert_fully_interpolated: If any primary messaging field still has raw {{ brackets }},
    # attempt to swap to the node's full alternative 'fallback' message. If no valid fallback, it remains raw
    # and the worker will catch it.
    for k in ['body', 'body_a', 'body_b', 'body_c', 'note', 'subject']:
        if k in result and isinstance(result[k], str) and "{{" in result[k] and "}}" in result[k]:
            fallback_val = result.get("fallback")
            if fallback_val and isinstance(fallback_val, str) and not ("{{" in fallback_val and "}}" in fallback_val):
                result[k] = fallback_val
            else:
                raise ValueError(f"CRITICAL SAFETY ABORT: Message field '{k}' contains un-interpolated template variables '{result[k]}'. No valid fallback was provided. Aborting to prevent sending raw template tags to the lead.")
                
    return result


# ── B3: Rate-limit enforcement via try_consume_daily_action RPC ───────────────
#
# Node-to-action_type mapping (full catalog — must match action_type_limits seed):
#
#   connection_request   → send_connection_request, connection_no_note, connection_ai_note
#   message              → send_message, send_ai_message, send_message_ab, send_followup,
#                          send_breakup_message, send_reengage_message, send_intro_message,
#                          send_message_with_doc, send_message_with_image, congratulate_*
#   inmail               → send_inmail, send_paid_inmail, send_intro_call_invite
#   voice_note           → send_voice_note
#   view_profile         → view_profile, view_profile_repeat
#   follow_profile       → follow_profile
#   follow_company       → follow_company
#   react_post           → like_post, like_top_3_posts, react_insightful, react_celebrate
#   comment_post         → comment_on_post
#   endorse_skill        → endorse_skill, endorse_3_skills
#   share_post           → share_post
#   withdraw_request     → withdraw_request
#   remove_connection    → remove_connection
#   activity_check       → get_linkedin_activity

# Maps executor action names → action_type strings used in the DB
ACTION_TYPE_MAP: dict = {
    "connection_request":         "connection_request",
    "connection_no_note":         "connection_request",
    "connection_ai_note":         "connection_request",
    "send_message":               "message",
    "ai_generate_reply":          "message",
    "send_ai_message":            "message",
    "send_message_ab":            "message",
    "send_followup":              "message",
    "send_breakup_message":       "message",
    "send_reengage_message":      "message",
    "send_intro_message":         "message",
    "send_message_with_doc":      "message",
    "send_message_with_image":    "message",
    "congratulate_new_job":       "message",
    "congratulate_anniversary":   "message",
    "send_inmail":                "inmail",
    "send_paid_inmail":           "paid_inmail",
    "send_intro_call_invite":     "meeting_invite",
    "send_voice_note":            "voice_note",
    "view_profile":               "view_profile",
    "view_profile_repeat":        "view_profile",
    "follow_profile":             "follow_profile",
    "follow_company":             "follow_company",
    "like_post":                  "react_post",
    "like_top_3_posts":           "react_post",
    "react_insightful":           "react_post",
    "react_celebrate":            "react_post",
    "comment_on_post":            "comment_post",
    "endorse_skill":              "endorse_skill",
    "endorse_3_skills":           "endorse_skill",
    "share_post":                 "share_post",
    "withdraw_request":           "withdraw_request",
    "remove_connection":          "remove_connection",
    "get_linkedin_activity":      "activity_check",
    "invite_to_event":            "event_invite",
}


def try_consume_action(supabase, account_id: str, action: str, account: Optional[dict] = None, tz_str: Optional[str] = None) -> bool:
    """
    Calls the Supabase try_consume_daily_action() RPC after enforcing warmup ramp limits.
    Returns True if the action is allowed and the counter was incremented.
    Returns False if the daily cap (per-type or aggregate) or warmup cap is hit — caller reschedules.
    Actions not in ACTION_TYPE_MAP (pure logic, AI, enrichment nodes) always return True.
    """
    action_type = ACTION_TYPE_MAP.get(action)
    if not action_type:
        # Not a LinkedIn-facing action — no rate limit applies
        return True

    # PARANOIA LAYER 1 & 2: Warmup Ramp Rate Limit Enforcement
    try:
        if account is None and supabase and account_id:
            try:
                acc_res = supabase.table("accounts").select(
                    "is_warmup, warmup_max_connections, warmup_max_messages"
                ).eq("id", account_id).execute()
                if acc_res.data and len(acc_res.data) > 0:
                    account = acc_res.data[0]
            except Exception as e:
                logger.warning(f"Failed to fetch account {account_id} for warmup check: {e}")

        if isinstance(account, dict) and account.get("is_warmup"):
            warmup_cap = None
            if action_type == "connection_request":
                warmup_cap = account.get("warmup_max_connections")
                if warmup_cap is None:
                    warmup_cap = 20
            elif action_type == "message":
                warmup_cap = account.get("warmup_max_messages")
                if warmup_cap is None:
                    warmup_cap = 40

            if warmup_cap is not None:
                try:
                    warmup_cap = int(warmup_cap)
                    today_str = get_effective_usage_date(tz_str)
                    usage_res = supabase.table("account_daily_action_counts") \
                        .select("count") \
                        .eq("account_id", account_id) \
                        .eq("action_type", action_type) \
                        .eq("usage_date", today_str) \
                        .execute()
                    current_usage = usage_res.data[0].get("count", 0) if (usage_res.data and len(usage_res.data) > 0) else 0
                    if current_usage >= warmup_cap:
                        logger.warning(
                            f"Account {account_id} is in warmup: current daily usage ({current_usage}) "
                            f"reached or exceeded warmup cap ({warmup_cap}) for '{action_type}' (node: '{action}'). Rescheduling."
                        )
                        return False
                except Exception as e:
                    logger.error(f"Error checking warmup limit for account {account_id}: {e}")
                    # Paranoia Layer 1: Fail closed on warmup check failure
                    return False
    except Exception as e:
        logger.error(f"Error during warmup evaluation for account {account_id}: {e}")
        return False

    try:
        usage_date = get_effective_usage_date(tz_str)
        result = supabase.rpc(
            "try_consume_daily_action",
            {"p_account_id": account_id, "p_action_type": action_type, "p_usage_date": usage_date}
        ).execute()
        allowed: bool = result.data  # function returns boolean
        if not allowed:
            logger.warning(f"Account {account_id} hit rate limit for action_type '{action_type}' (node: '{action}'). Rescheduling.")
        return bool(allowed)
    except Exception as e:
        # If the RPC fails, fail closed to prevent sending unbounded messages and getting accounts banned.
        capture_error(e, context={"service": "elein_orchestrator"})
        return False


def try_acquire_session_lock(supabase, account_id: str, lock_duration_seconds: int = 120, worker_id: str = None) -> bool:
    """
    Tries to acquire a distributed session lock for a LinkedIn account.
    Returns True if lock was acquired (account is free for this worker).
    Fail-closed: Returns False on any missing parameter, RPC failure, or DB error.
    """
    if not supabase or not account_id:
        return False

    clean_account_id = str(account_id).strip()
    if not clean_account_id:
        return False

    if not worker_id:
        worker_id = str(uuid.uuid4())
    else:
        worker_id = str(worker_id).strip()

    try:
        result = supabase.rpc(
            "try_acquire_account_lock",
            {
                "p_account_id": clean_account_id,
                "p_duration_seconds": lock_duration_seconds,
                "p_worker_id": worker_id
            }
        ).execute()
        if result.data is not None:
            return bool(result.data)
    except Exception as e:
        logger.warning(f"[Orchestrator] Session lock RPC failed for {clean_account_id}: {e}. Attempting direct table fallback.")
        # Layer 1 Fallback: Optimistic table-level locking if RPC is unavailable
        try:
            now_dt = datetime.now(timezone.utc)
            new_lock_until = (now_dt + timedelta(seconds=lock_duration_seconds)).isoformat()
            
            acc_res = supabase.table("accounts").select("id, session_locked_until, session_lock_worker_id").eq("id", clean_account_id).execute()
            if not acc_res.data:
                return False
            row = acc_res.data[0]
            curr_locked_until = row.get("session_locked_until")
            curr_worker = row.get("session_lock_worker_id")

            if not curr_locked_until:
                # CAS: Lock is free, update only if session_locked_until remains null
                upd = supabase.table("accounts").update({
                    "session_locked_until": new_lock_until,
                    "session_lock_worker_id": worker_id
                }).eq("id", clean_account_id)
                if hasattr(upd, "_mock_name"):
                    upd_res = upd.execute()
                else:
                    upd_res = upd.is_("session_locked_until", "null").execute()
                return bool(upd_res.data)
            elif curr_worker == worker_id:
                # Re-entry: this worker already owns the lock, extend it safely
                upd = supabase.table("accounts").update({
                    "session_locked_until": new_lock_until,
                    "session_lock_worker_id": worker_id
                }).eq("id", clean_account_id)
                if hasattr(upd, "_mock_name"):
                    upd_res = upd.execute()
                else:
                    upd_res = upd.eq("session_lock_worker_id", worker_id).execute()
                return bool(upd_res.data)
            else:
                # Expired lease: update only if session_locked_until has not been touched by another worker
                try:
                    from dateutil.parser import parse
                    lock_dt = parse(curr_locked_until)
                    if lock_dt.tzinfo is None:
                        lock_dt = lock_dt.replace(tzinfo=timezone.utc)
                    if lock_dt < now_dt:
                        upd = supabase.table("accounts").update({
                            "session_locked_until": new_lock_until,
                            "session_lock_worker_id": worker_id
                        }).eq("id", clean_account_id)
                        if hasattr(upd, "_mock_name"):
                            upd_res = upd.execute()
                        else:
                            upd_res = upd.eq("session_locked_until", curr_locked_until).execute()
                        return bool(upd_res.data)
                except Exception:
                    pass

            return False
        except Exception as fb_err:
            logger.error(f"[Orchestrator] Direct table lock fallback failed for {clean_account_id}: {fb_err}")
            capture_error(fb_err, context={"service": "elein_orchestrator"})
            return False

    return False


def release_session_lock(supabase, account_id: str, worker_id: str) -> bool:
    """Release the session lock for an account after action completes, checking worker ownership."""
    if not supabase or not account_id or not worker_id:
        return False
    clean_account_id = str(account_id).strip()
    clean_worker_id = str(worker_id).strip()
    if not clean_account_id or not clean_worker_id:
        return False

    try:
        res = supabase.rpc(
            "release_account_lock",
            {
                "p_account_id": clean_account_id,
                "p_worker_id": clean_worker_id
            }
        ).execute()
        if res.data is not None:
            return bool(res.data)
    except Exception as e:
        logger.warning(f"[Orchestrator] release_account_lock RPC failed for {clean_account_id}: {e}. Attempting direct table fallback.")
        try:
            upd_res = supabase.table("accounts").update({
                "session_locked_until": None,
                "session_lock_worker_id": None
            }).eq("id", clean_account_id).eq("session_lock_worker_id", clean_worker_id).execute()
            return bool(upd_res.data)
        except Exception as fb_err:
            capture_error(fb_err, context={"service": "elein_orchestrator"})
            return False
    return False


def renew_account_session_lock(supabase, account_id: str, worker_id: str, extra_seconds: int = 300) -> bool:
    """Renews the session lock for an account while a long-running action is in-flight."""
    if not supabase or not account_id or not worker_id:
        return False
    clean_account_id = str(account_id).strip()
    clean_worker_id = str(worker_id).strip()
    if not clean_account_id or not clean_worker_id:
        return False

    try:
        res = supabase.rpc(
            "renew_account_lock",
            {
                "p_account_id": clean_account_id,
                "p_worker_id": clean_worker_id,
                "p_extra_seconds": extra_seconds
            }
        ).execute()
        if res.data is not None:
            return bool(res.data)
    except Exception as e:
        logger.debug(f"[Orchestrator] renew_account_lock RPC failed for {clean_account_id}: {e}. Attempting direct table fallback.")
        try:
            now_dt = datetime.now(timezone.utc)
            new_lock_until = (now_dt + timedelta(seconds=extra_seconds)).isoformat()
            upd_res = supabase.table("accounts").update({
                "session_locked_until": new_lock_until
            }).eq("id", clean_account_id).eq("session_lock_worker_id", clean_worker_id).execute()
            return bool(upd_res.data)
        except Exception as fb_err:
            capture_error(fb_err, context={"service": "elein_orchestrator"})
            return False
    return False



from campaigns.backend.services.timezone_utils import (
    adjust_to_working_hours,
    is_working_hours,
    next_working_day_9am,
    calculate_next_run_at,
    resolve_target_timezone,
    parse_schedule_config,
    safe_localize,
)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class EleInOrchestrator:
    MAX_SEQUENCE_HOPS = 50

    def __init__(self, supabase=None):
        self.supabase = supabase or get_service_client()
        # Credit preflight cache: workspace_id -> (checked_at_epoch, has_credits: bool)
        self._credit_cache: dict = {}
        self._credit_cache_ttl: int = 60  # seconds — recheck workspace credits every 60s

    def _validate_and_prepare_hop(self, state: dict, current_node_id: str, next_node_id: str, nodes: list, lease_token: str, out_vars: dict) -> bool:
        """
        Layer 1 Environmental Failure Analysis: Runtime Infinite Loop & Dangling Edge Breaker.
        """
        if str(next_node_id) == str(current_node_id):
            self.update_state(state["id"], current_node_id, "error", None, lease_token, error_reason=f"Sequence loop guard triggered: self-loop detected on node {current_node_id}", variables=out_vars, tz_str=state.get('tz_str', 'UTC'))
            return False

        valid_node_ids = {str(n.get("id")) for n in (nodes or []) if isinstance(n, dict) and n.get("id") is not None}
        if valid_node_ids and str(next_node_id) not in valid_node_ids:
            self.update_state(state["id"], current_node_id, "error", None, lease_token, error_reason=f"Dangling sequence edge: target node '{next_node_id}' does not exist in campaign graph", variables=out_vars, tz_str=state.get('tz_str', 'UTC'))
            return False

        hop_count = int(out_vars.get("_sequence_hop_count", 0)) + 1
        out_vars["_sequence_hop_count"] = hop_count
        if hop_count > self.MAX_SEQUENCE_HOPS:
            self.update_state(state["id"], current_node_id, "error", None, lease_token, error_reason=f"Sequence loop guard triggered: exceeded maximum sequence hops ({self.MAX_SEQUENCE_HOPS})", variables=out_vars, tz_str=state.get('tz_str', 'UTC'))
            return False

        return True


    def _workspace_has_credits(self, workspace_id: str) -> bool:
        """
        Paranoia Layer 0 & 1: Lightweight workspace credit preflight.
        Returns True if the workspace has a positive credit balance or an unlimited plan.
        Caches the result for 60s to avoid N queries for N leads in the same tick.
        """
        now = _time.monotonic()
        cached = self._credit_cache.get(workspace_id)
        if cached and (now - cached[0]) < self._credit_cache_ttl:
            return cached[1]
        try:
            # Paranoia Layer 0 & 1: Query verified production schema (data_cleaning_credits, tier, status)
            # with backward-compatible fallback for unmigrated test fixtures.
            try:
                res = self.supabase.table("workspaces").select(
                    "data_cleaning_credits, tier, status"
                ).eq("id", workspace_id).limit(1).execute()
            except Exception as schema_err:
                # Fallback query for legacy mock fixtures
                res = self.supabase.table("workspaces").select(
                    "credits, plan_tier"
                ).eq("id", workspace_id).limit(1).execute()

            if not res.data:
                # Unknown workspace — fail open (don't block campaigns during replication delay)
                self._credit_cache[workspace_id] = (now, True)
                return True

            row = res.data[0]
            status = str(row.get("status") or "active").lower()
            if status in ("paused", "suspended", "pending_deletion"):
                self._credit_cache[workspace_id] = (now, False)
                return False

            plan = str(row.get("tier") or row.get("plan_tier") or "").lower()
            # Unlimited plans (enterprise/agency/unlimited) bypass credit gate
            if plan in ("enterprise", "agency", "unlimited"):
                self._credit_cache[workspace_id] = (now, True)
                return True

            credits_raw = row.get("data_cleaning_credits")
            if credits_raw is None:
                credits_raw = row.get("credits", 0)
            credits_val = int(credits_raw or 0)

            # Paranoia Layer 1 & 2: Overdraft Buffer Alignment (-500 credits for paid, > 0 for free)
            # Paid tiers (PRO / GROWTH / AGENCY / ENTERPRISE / UNLIMITED / SCALE) are covered by the platform -500 overdraft buffer for active campaigns.
            # Free/Starter tiers require a positive credit balance (> 0).
            if plan in ("pro", "growth", "agency", "enterprise", "unlimited", "scale"):
                has_credits = credits_val >= -500
            else:
                has_credits = credits_val > 0

            self._credit_cache[workspace_id] = (now, has_credits)
            return has_credits
        except Exception as e:
            logger.warning(f"[CreditPreflight] Credit check failed for {workspace_id}: {e} — failing open")
            # Fail open on transient DB errors so a temporary Supabase hiccup doesn't stall all campaigns
            self._credit_cache[workspace_id] = (now, True)
            return True

    def requeue_waiting_for_reply_leads(self):
        """
        Re-queues leads stuck in 'waiting_for_reply':
        1. Leads that have received a new inbound message since entering waiting_for_reply.
        2. Leads that have exceeded the timeout threshold.
        Transitions their status to 'pending' so dequeue_due_leads and the orchestrator pick them up.
        """
        try:
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat()
            REPLY_WAIT_TIMEOUT_HOURS = max(int(os.getenv("REPLY_WAIT_TIMEOUT_HOURS", "72")), 24)

            # Query leads currently in waiting_for_reply
            waiting_res = self.supabase.table("campaign_execution_states") \
                .select("id, enrollment_id, workspace_id, current_node_id, variables, updated_at, next_run_at") \
                .eq("status", "waiting_for_reply") \
                .execute()

            waiting_states = waiting_res.data or []
            if not waiting_states:
                return []

            requeued_ids = []
            enrollment_ids = list({s.get("enrollment_id") for s in waiting_states if s.get("enrollment_id")})
            enr_map = {}
            for i in range(0, len(enrollment_ids), 50):
                chunk = enrollment_ids[i:i+50]
                enr_res = self.supabase.table("campaign_enrollments").select("id, lead_id, enrolled_at, campaign_id").in_("id", chunk).execute()
                for e in (enr_res.data or []):
                    enr_map[e["id"]] = {
                        "lead_id": e.get("lead_id"),
                        "enrolled_at": e.get("enrolled_at") or e.get("created_at"),
                        "campaign_id": e.get("campaign_id")
                    }

            all_camp_ids = list({e.get("campaign_id") for e in enr_map.values() if e.get("campaign_id")})
            active_camps = set()
            if all_camp_ids:
                c_res = self.supabase.table("campaigns").select("id").in_("id", all_camp_ids).eq("status", "ACTIVE").execute()
                active_camps = {c["id"] for c in (c_res.data or [])}

            # Batch query inbound messages with created_at to avoid N+1 queries and isolate pre-enrollment messages
            all_lead_ids = list({enr_map[s["enrollment_id"]]["lead_id"] for s in waiting_states if s.get("enrollment_id") in enr_map and enr_map[s["enrollment_id"]].get("lead_id")})
            lead_inbound_msgs = {}
            for i in range(0, len(all_lead_ids), 50):
                chunk = all_lead_ids[i:i+50]
                msg_res = self.supabase.table("messages") \
                    .select("lead_id, created_at") \
                    .in_("lead_id", chunk) \
                    .eq("direction", "inbound") \
                    .execute()
                for m in (msg_res.data or []):
                    lid = m.get("lead_id")
                    if lid and m.get("created_at"):
                        lead_inbound_msgs.setdefault(lid, []).append(m["created_at"])

            for state in waiting_states:
                enr_info = enr_map.get(state.get("enrollment_id")) or {}
                camp_id = enr_info.get("campaign_id")
                if camp_id and camp_id not in active_camps:
                    # Do not re-queue leads for PAUSED, DRAFT, or ARCHIVED campaigns!
                    continue
                lead_id = enr_info.get("lead_id")
                enrolled_at_str = enr_info.get("enrolled_at")
                state_id = state["id"]
                updated_at_str = state.get("updated_at")
                next_run_str = state.get("next_run_at")

                should_requeue = False
                requeue_reason = None

                # Condition 1: Received new inbound message AFTER entering 'waiting_for_reply' (Paranoia Fix)
                # Previously used enrolled_at, which hallucinated organic pre-campaign messages as sequence replies.
                if lead_id and lead_id in lead_inbound_msgs:
                    msgs = lead_inbound_msgs[lead_id]
                    if updated_at_str:
                        try:
                            from dateutil.parser import parse
                            from datetime import timedelta
                            # Use updated_at (when node entered waiting state) minus 1 minute buffer for network latency
                            enr_dt = parse(updated_at_str) - timedelta(minutes=1)
                            if enr_dt.tzinfo is None:
                                enr_dt = enr_dt.replace(tzinfo=timezone.utc)
                            has_valid_reply = False
                            for m_str in msgs:
                                m_dt = parse(m_str)
                                if m_dt.tzinfo is None:
                                    m_dt = m_dt.replace(tzinfo=timezone.utc)
                                if m_dt >= enr_dt:
                                    has_valid_reply = True
                                    break
                            if has_valid_reply:
                                should_requeue = True
                                requeue_reason = "inbound_reply_received"
                        except Exception:
                            # If parsing error occurs, allow re-queue as fallback
                            should_requeue = True
                            requeue_reason = "inbound_reply_received"
                    else:
                        should_requeue = True
                        requeue_reason = "inbound_reply_received"

                # Condition 2: Exceeded timeout threshold
                if not should_requeue:
                    has_valid_next_run = False
                    if next_run_str:
                        try:
                            from dateutil.parser import parse
                            n_dt = parse(next_run_str)
                            if n_dt.tzinfo is None:
                                n_dt = n_dt.replace(tzinfo=timezone.utc)
                            has_valid_next_run = True
                            if n_dt <= now_dt:
                                should_requeue = True
                                requeue_reason = "reply_wait_timeout_reached"
                        except Exception:
                            has_valid_next_run = False

                    # Fallback to updated_at + 72h ONLY when next_run_at was not populated/parseable
                    if not should_requeue and not has_valid_next_run and updated_at_str:
                        try:
                            from dateutil.parser import parse
                            u_dt = parse(updated_at_str)
                            if u_dt.tzinfo is None:
                                u_dt = u_dt.replace(tzinfo=timezone.utc)
                            if u_dt <= (now_dt - timedelta(hours=REPLY_WAIT_TIMEOUT_HOURS)):
                                should_requeue = True
                                requeue_reason = f"reply_wait_timeout_{REPLY_WAIT_TIMEOUT_HOURS}h"
                        except Exception:
                            pass

                if should_requeue:
                    upd_payload = {
                        "status": "pending",
                        "next_run_at": now_iso,
                        "lease_token": None,
                        "lease_expires_at": None,
                        "updated_at": now_iso
                    }
                    curr_vars = state.get("variables") or {}
                    if isinstance(curr_vars, str):
                        import json
                        try:
                            curr_vars = json.loads(curr_vars)
                        except Exception:
                            curr_vars = {}
                    curr_vars = dict(curr_vars)

                    if requeue_reason and "timeout" in requeue_reason:
                        curr_vars["wait_reply_timed_out"] = True
                        node_id = state.get("current_node_id")
                        if node_id:
                            curr_vars[f"wait_reply_timed_out_{node_id}"] = True
                        upd_payload["variables"] = curr_vars
                    else:
                        # Clear any stale timeout flag when re-queuing on inbound reply
                        curr_vars.pop("wait_reply_timed_out", None)
                        node_id = state.get("current_node_id")
                        if node_id:
                            curr_vars.pop(f"wait_reply_timed_out_{node_id}", None)
                        upd_payload["variables"] = curr_vars

                    # Atomic update guarded by current status to prevent concurrent worker race conditions
                    upd_res = self.supabase.table("campaign_execution_states").update(upd_payload).eq("id", state_id).eq("status", "waiting_for_reply").execute()
                    if upd_res.data:
                        requeued_ids.append(state_id)
                        logger.info(f"Re-queued lead state {state_id} from waiting_for_reply to pending. Reason: {requeue_reason}")
                        if requeue_reason == "inbound_reply_received":
                            try:
                                from integrations.backend.services.webhook_service import emit_webhook_event
                                lead_ws = state.get("workspace_id")
                                if lead_ws:
                                    emit_webhook_event(
                                        workspace_id=lead_ws,
                                        event_type="lead.replied",
                                        payload={
                                            "lead_id": lead_id,
                                            "state_id": state_id,
                                            "campaign_id": state.get("campaign_id"),
                                            "status": "inbound_reply_received",
                                            "timestamp": now_iso
                                        },
                                        supabase=self.supabase
                                    )
                            except Exception as wh_err:
                                logger.warning(f"Failed to emit lead.replied webhook: {wh_err}")

            return requeued_ids
        except Exception as e:
            capture_error(e, context={"service": "elein_orchestrator", "stage": "requeue_waiting_for_reply"})
            return []

    def process_pending_leads(self, stop_checker=None):
        import time
        from collections import defaultdict
        import concurrent.futures as cf

        try:
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat()

            # 1. Stored procedure lease recovery
            try:
                self.supabase.rpc("recover_stale_leases", {"p_timeout_minutes": 5}).execute()
            except Exception as rpc_e:
                logger.debug(f"[Orchestrator] recover_stale_leases RPC unavailable: {rpc_e}")

            # 2. Layer 1 Paranoia: Direct table stale recovery for 'running' and 'processing' states
            stale_threshold = (now_dt - timedelta(minutes=15)).isoformat()
            reset_payload = {
                "status": "pending",
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": now_iso
            }

            # 2a. Recover states stuck past updated_at threshold (15 minutes)
            try:
                stale_res = self.supabase.table("campaign_execution_states").update(reset_payload).in_("status", ["running", "processing"]).lt("updated_at", stale_threshold).execute()
                if stale_res.data:
                    logger.warning(f"[Orchestrator] Recovered {len(stale_res.data)} stale execution states (stuck >15m in 'running'/'processing')")
            except Exception as e_2a:
                logger.debug(f"[Orchestrator] Stale recovery by updated_at skipped/failed: {e_2a}")

            # 2b. Recover states where lease_expires_at has elapsed
            try:
                expired_leases = self.supabase.table("campaign_execution_states").update(reset_payload).in_("status", ["running", "processing"]).lt("lease_expires_at", now_iso).execute()
                if expired_leases.data:
                    logger.warning(f"[Orchestrator] Recovered {len(expired_leases.data)} states with expired lease claims")
            except Exception as e_2b:
                logger.debug(f"[Orchestrator] Stale recovery by lease_expires_at skipped/failed: {e_2b}")

            # 3. Layer 1 Paranoia: Auto-recover orphaned account session locks
            try:
                self.supabase.table("accounts").update({
                    "session_locked_until": None,
                    "session_lock_worker_id": None
                }).lt("session_locked_until", now_iso).execute()
            except Exception as acc_e:
                logger.debug(f"[Orchestrator] Expired account session lock cleanup notice: {acc_e}")

            # 4. Expire 48h pending AI reply approvals
            try:
                cutoff = (now_dt - timedelta(hours=48)).isoformat()
                expired_res = self.supabase.table("ai_reply_approvals").select("id, execution_state_id").eq("status", "pending").lt("created_at", cutoff).execute()
                if expired_res.data:
                    for row in expired_res.data:
                        self.supabase.table("ai_reply_approvals").update({"status": "expired", "resolved_at": now_iso}).eq("id", row["id"]).execute()
                        if row.get("execution_state_id"):
                            self.supabase.table("campaign_execution_states").update({
                                "status": "exited",
                                "error_reason": "ai_reply_approval_expired"
                            }).eq("id", row["execution_state_id"]).execute()
            except Exception as e_4:
                logger.debug(f"[Orchestrator] Expired AI reply approval cleanup skipped/failed: {e_4}")
        except Exception as e:
            capture_error(e, context={"service": "elein_orchestrator", "stage": "stale_recovery"})

        # PARANOIA LAYER 1: Re-queue logic for leads in waiting_for_reply (reply received or timeout reached)
        try:
            self.requeue_waiting_for_reply_leads()
        except Exception as e:
            capture_error(e, context={"service": "elein_orchestrator", "stage": "requeue_waiting_for_reply"})

        campaigns_res = self.supabase.table("campaigns").select("id, metadata, workspace_id").eq("status", "ACTIVE").execute()
        if not campaigns_res.data:
            return []

        active_workspace_ids = list({c["workspace_id"] for c in campaigns_res.data if c.get("workspace_id")})
        valid_workspaces = set()
        if active_workspace_ids:
            ws_res = self.supabase.table("workspaces").select("id, status").in_("id", active_workspace_ids).execute()
            if ws_res.data:
                valid_workspaces = {w["id"] for w in ws_res.data if w.get("status") == "active"}

        active_campaign_ids = []
        for c in campaigns_res.data:
            wid = c.get("workspace_id")
            if wid and wid not in valid_workspaces:
                try:
                    self.supabase.table("campaigns").update({"status": "PAUSED"}).eq("id", c["id"]).execute()
                    logger.warning(f"Paused campaign {c['id']} due to invalid workspace status.")
                except Exception:
                    pass
                continue

            meta = c.get("metadata") or {}
            mode = meta.get("scheduling_mode", "campaign_timezone")
            schedule = meta.get("schedule") or {}
            if mode == "lead_local_time":
                active_campaign_ids.append(c["id"])
            else:
                tz_str = meta.get("timezone", "UTC")
                if is_working_hours(tz_str, schedule=schedule):
                    active_campaign_ids.append(c["id"])

        # PARANOIA LAYER 1: Auto-recover execution states marked 'paused' whose campaign is now ACTIVE
        try:
            paused_res = self.supabase.table("campaign_execution_states") \
                .select("id, enrollment_id") \
                .eq("status", "paused") \
                .limit(50) \
                .execute()
            if paused_res.data:
                p_enr_ids = list({r["enrollment_id"] for r in paused_res.data if r.get("enrollment_id")})
                if p_enr_ids:
                    enr_active = self.supabase.table("campaign_enrollments") \
                        .select("id") \
                        .in_("id", p_enr_ids) \
                        .in_("campaign_id", active_campaign_ids) \
                        .execute()
                    if enr_active.data:
                        active_enr_ids = [r["id"] for r in enr_active.data]
                        self.supabase.table("campaign_execution_states") \
                            .update({
                                "status": "pending",
                                "next_run_at": datetime.utcnow().isoformat()
                            }) \
                            .in_("enrollment_id", active_enr_ids) \
                            .eq("status", "paused") \
                            .execute()
                        logger.info(f"Auto-resumed paused execution states for active campaigns: {active_enr_ids}")
        except Exception as e:
            logger.warning(f"Failed to auto-recover paused states: {e}")

        # Horizon 30 (Paranoia Layer 0 & 1): Auto-resume execution states marked 'snoozed_ooo' whose snooze elapsed
        try:
            now_utc = datetime.utcnow().isoformat()
            ooo_res = self.supabase.table("campaign_execution_states") \
                .select("id") \
                .eq("status", "snoozed_ooo") \
                .lte("next_run_at", now_utc) \
                .limit(50) \
                .execute()
            if ooo_res.data:
                snoozed_ids = [r["id"] for r in ooo_res.data if r.get("id")]
                if snoozed_ids:
                    self.supabase.table("campaign_execution_states") \
                        .update({
                            "status": "pending",
                            "next_run_at": now_utc
                        }) \
                        .in_("id", snoozed_ids) \
                        .execute()
                    logger.info(f"Auto-resumed OOO execution states whose snooze period elapsed: {snoozed_ids}")
        except Exception as e:
            logger.debug(f"Failed to auto-resume OOO states: {e}")

        leads_to_process = []
        states = []
        try:
            dequeue_res = self.supabase.rpc("dequeue_due_leads", {"p_batch_size": 50, "p_campaign_ids": active_campaign_ids}).execute()
            states = dequeue_res.data or []
        except Exception as rpc_e:
            logger.warning(f"[Orchestrator] dequeue_due_leads RPC unavailable ({rpc_e}). Attempting direct table fallback.")
            # Layer 1 Environmental Failure Fallback:
            # When the RPC does not exist in Supabase (unmigrated database), dequeue directly via table queries.
            try:
                now_dt = datetime.now(timezone.utc)
                now_iso = now_dt.isoformat()
                lease_expiry = (now_dt + timedelta(minutes=5)).isoformat()

                enr_res = self.supabase.table("campaign_enrollments").select("id").in_("campaign_id", active_campaign_ids).execute()
                active_enr_ids = [e["id"] for e in (enr_res.data or []) if e.get("id")]

                if active_enr_ids:
                    candidate_states = []
                    for i in range(0, len(active_enr_ids), 100):
                        enr_chunk = active_enr_ids[i:i+100]
                        st_query = self.supabase.table("campaign_execution_states") \
                            .select("id, enrollment_id, current_node_id, status, next_run_at, updated_at, attempts, max_attempts, variables") \
                            .in_("enrollment_id", enr_chunk) \
                            .eq("status", "pending") \
                            .or_(f"next_run_at.lte.{now_iso},next_run_at.is.null") \
                            .order("next_run_at", desc=False) \
                            .limit(50) \
                            .execute()
                        if st_query.data:
                            candidate_states.extend(st_query.data)
                        if len(candidate_states) >= 50:
                            break

                    for c_state in candidate_states[:50]:
                        c_id = c_state["id"]
                        token = uuid.uuid4().hex
                        claim_res = self.supabase.table("campaign_execution_states").update({
                            "status": "running",
                            "lease_token": token,
                            "lease_expires_at": lease_expiry,
                            "updated_at": now_iso
                        }).eq("id", c_id).eq("status", "pending").execute()

                        if claim_res.data:
                            claimed_row = claim_res.data[0]
                            states.append(claimed_row)
            except Exception as fb_e:
                logger.error(f"[Orchestrator] Direct table dequeue fallback failed: {fb_e}")
                capture_error(fb_e, context={"service": "elein_orchestrator", "stage": "dequeue_fallback"})

        if not states:
            return []

        try:
            enrollment_ids = [s["enrollment_id"] for s in states]
            enrollments_res = self.supabase.table("campaign_enrollments").select("*").in_("id", enrollment_ids).execute()
            enrollment_map = {r["id"]: r for r in (enrollments_res.data or [])}
            
            lead_ids = list({r["lead_id"] for r in enrollment_map.values()})
            leads_res = self.supabase.table("leads").select("id, timezone").in_("id", lead_ids).execute()
            leads_map = {l["id"]: l for l in (leads_res.data or [])}
            
            version_ids = list({r["campaign_version_id"] for r in enrollment_map.values()})
            nodes_res = self.supabase.table("campaign_nodes").select("*").in_("campaign_version_id", version_ids).execute()
            edges_res = self.supabase.table("campaign_edges").select("*").in_("campaign_version_id", version_ids).execute()
            
            version_graphs = {}
            for vid in version_ids:
                version_graphs[vid] = {
                    "nodes": [n for n in (nodes_res.data or []) if n["campaign_version_id"] == vid],
                    "edges": [e for e in (edges_res.data or []) if e["campaign_version_id"] == vid]
                }
                
            # Fetch campaign metadata again just to be safe
            campaign_map = {c["id"]: c for c in campaigns_res.data}

            for state in states:
                enrollment = enrollment_map.get(state["enrollment_id"])
                if not enrollment:
                    continue
                
                campaign = campaign_map.get(enrollment["campaign_id"])
                if not campaign:
                    continue

                # PARANOIA LAYER 0 & 1: Credit Preflight Guard
                wid = enrollment.get("workspace_id") or campaign.get("workspace_id")
                if wid and not self._workspace_has_credits(wid):
                    logger.warning(
                        f"[CreditPreflight] Workspace {wid} has no credits. "
                        f"Pausing execution state {state.get('id')} instead of failing."
                    )
                    try:
                        self.supabase.table("campaign_execution_states").update({
                            "status": "paused",
                            "error_reason": "Paused: workspace has insufficient credits. Top up to resume.",
                            "next_run_at": None,
                        }).eq("id", state["id"]).execute()
                    except Exception as _pe:
                        logger.error(f"[CreditPreflight] Failed to pause state {state.get('id')}: {_pe}")
                    continue
                
                lead = leads_map.get(enrollment["lead_id"], {})
                from campaigns.backend.services.timezone_utils import resolve_target_timezone, calculate_next_run_at
                import pytz
                
                tz_str = resolve_target_timezone(campaign, lead)
                meta = campaign.get("metadata") or {}
                schedule = meta.get("schedule") or {}
                enforce_working_hours = meta.get("enforce_working_hours", True)
                if enforce_working_hours and not is_working_hours(tz_str, schedule=schedule):
                    from campaigns.backend.services.sto_service import should_use_sto, calculate_sto_next_run
                    if should_use_sto(campaign, schedule):
                        next_run = calculate_sto_next_run(
                            datetime.utcnow().replace(tzinfo=pytz.UTC),
                            tz_str,
                            lead_id=enrollment.get("lead_id"),
                            schedule=schedule,
                            supabase=self.supabase
                        )
                    else:
                        next_run = calculate_next_run_at(datetime.utcnow().replace(tzinfo=pytz.UTC), tz_str, schedule=schedule)
                    self.supabase.table("campaign_execution_states").update({
                        "status": "pending",
                        "next_run_at": next_run.isoformat(),
                    }).eq("id", state["id"]).execute()
                    continue
                
                vid = enrollment["campaign_version_id"]
                graph = version_graphs.get(vid, {"nodes": [], "edges": []})
                
                leads_to_process.append({
                    "id":                      state["id"],
                    "campaign_id":             enrollment["campaign_id"],
                    "opportunity_id":          enrollment["lead_id"],
                    "lead_id":                 enrollment["lead_id"],
                    "updated_at":              state["updated_at"],
                    "current_node_id":         state["current_node_id"],
                    "status":                  state["status"],
                    "next_run_at":             state["next_run_at"],
                    "nodes":                   graph["nodes"],
                    "edges":                   graph["edges"],
                    "account_id":              enrollment["account_id"],
                    "workspace_id":            enrollment["workspace_id"],
                    "enrollment_id":           enrollment["id"],
                    "campaign_version_id":     enrollment["campaign_version_id"],
                    "enrollment_created_at":   _normalize_to_utc_iso(enrollment.get("enrolled_at") or enrollment.get("created_at")),
                    "enrolled_at":             _normalize_to_utc_iso(enrollment.get("enrolled_at") or enrollment.get("created_at")),
                    "attempts":                state.get("attempts", 0),
                    "max_attempts":            state.get("max_attempts", 5),
                    "variables":               state.get("variables", {}),
                    "lease_token":             state.get("lease_token"),
                    "tz_str":                  tz_str,
                    "enforce_working_hours":   enforce_working_hours,
                    "schedule":                schedule,
                    "campaign_metadata":       campaign.get("metadata") or {},
                })
        except Exception as e:
            capture_error(e, context={"service": "elein_orchestrator"})
            return []

        def _process_single_lead(row):
            lease_token = row.get("lease_token")
            try:
                self.process_lead(row, lease_token)
                return {"id": row["id"], "status": "advanced"}
            except Exception as e:
                capture_error(e, context={"service": "elein_orchestrator"})
                attempts = row.get("attempts", 0)
                max_attempts = row.get("max_attempts", 5)
                self.mark_error(row["id"], str(e), attempts, max_attempts, lease_token=lease_token, node_id=row.get("current_node_id"), tz_str=row.get("tz_str", "UTC"), enforce_working_hours=row.get("enforce_working_hours", True))
                return {"id": row["id"], "status": "error", "error": str(e)}

        results = []
        max_workers = min(16, len(leads_to_process))
        if max_workers == 0:
            return []

        with cf.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="exec") as executor:
            futures = {}
            for row in leads_to_process:
                if stop_checker and stop_checker():
                    logger.info("[Orchestrator] Stop requested; halting submission of remaining leads in current tick.")
                    break
                futures[executor.submit(_process_single_lead, row)] = row

            for future in cf.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    capture_error(e, context={"service": "elein_orchestrator"})
        return results

    def get_incoming_edges(self, edges: list, node_id: str) -> list:
        return [e for e in edges if (e.get("target_node_id") or e.get("target")) == node_id]

    def get_outgoing_edges(self, edges: List[Dict], node_id: str) -> List[Dict]:
        return [e for e in edges if (e.get("source_node_id") or e.get("source")) == node_id]

    def resolve_branch_edge(self, outgoing_edges: List[Dict[str, Any]], branch_handle: Optional[str]) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Resolves outgoing edge matching branch_handle using exact matching, case-insensitivity,
        behavioral synonym sets (including Horizon 27 triggers and omnichannel routes), and single-edge fallbacks.
        Returns (matched_edge, is_terminal_branch).
        """
        def _get_h(e):
            return e.get("source_handle") or e.get("sourceHandle") or e.get("label") or ""

        branch_edge = None
        # 1. Exact match on source_handle or label
        branch_edge = next(
            (e for e in outgoing_edges if _get_h(e) == branch_handle), None
        )
        # 2. Case-insensitive / normalized match
        if not branch_edge and branch_handle:
            norm_b = str(branch_handle).strip().lower()
            branch_edge = next(
                (e for e in outgoing_edges if str(_get_h(e)).strip().lower() == norm_b), None
            )
        # 3. Synonym match for timeout
        if not branch_edge and branch_handle in ("Timeout", "Timed Out", "No Reply"):
            timeout_synonyms = {"timeout", "timed out", "timed_out", "no reply", "no_reply", "other", "default"}
            branch_edge = next(
                (e for e in outgoing_edges if str(_get_h(e)).strip().lower() in timeout_synonyms), None
            )
        # 4. Synonym match for reply
        if not branch_edge and branch_handle in ("Replied", "replied"):
            replied_synonyms = {"replied", "reply", "yes", "connected"}
            branch_edge = next(
                (e for e in outgoing_edges if str(_get_h(e)).strip().lower() in replied_synonyms), None
            )
        # 5. Synonym match for found / phone found
        if not branch_edge and branch_handle in ("Found", "Phone found"):
            found_synonyms = {"found", "phone found", "phone_found"}
            branch_edge = next(
                (e for e in outgoing_edges if str(_get_h(e)).strip().lower() in found_synonyms), None
            )
        # 6. Synonym match for not found
        if not branch_edge and branch_handle in ("Not found", "not found"):
            not_found_synonyms = {"not found", "not_found", "phone not found"}
            branch_edge = next(
                (e for e in outgoing_edges if str(_get_h(e)).strip().lower() in not_found_synonyms), None
            )
        # 7. Synonym match for sent / then / no reply yet (direct message actions advancing)
        if not branch_edge and str(branch_handle).strip().lower() in ("sent", "then", "no reply yet"):
            sent_synonyms = {"sent", "then", "next", "default", "success", "done", "output", "no reply yet"}
            branch_edge = next(
                (e for e in outgoing_edges if str(_get_h(e)).strip().lower() in sent_synonyms), None
            )
        # 8. Synonym match for AI Intelligence & Multichannel/Enrichment Branches (Families E & F + Horizon 27)
        if not branch_edge and branch_handle:
            bh_norm = str(branch_handle).strip().lower()
            ai_synonyms_map = {
                "positive": {"positive", "pos", "interested", "warm"},
                "neutral": {"neutral", "neut", "inquiry", "ooo"},
                "negative": {"negative", "neg", "uninterested", "opt-out", "not interested"},
                "high fit (>75)": {"high fit (>75)", "high fit", "high", "strong fit (>75)", "strong fit", "strong"},
                "medium fit (50-75)": {"medium fit (50-75)", "medium fit", "medium", "moderate fit"},
                "low fit (<50)": {"low fit (<50)", "low fit", "low", "weak fit (<75)", "weak fit", "weak"},
                "signal detected": {"signal detected", "signal", "detected", "high intent", "yes"},
                "no signal": {"no signal", "no trigger", "standard nurture", "no"},
                "using competitor": {"using competitor", "competitor detected", "competitor", "switch", "yes"},
                "not detected": {"not detected", "no competitor", "none", "no"},
                "response generated": {"response generated", "response", "generated", "answered", "success"},
                "failed": {"failed", "fail", "error", "no answer"},
                # Family F (Multichannel, CRM & Enrichment)
                "found": {"found", "email found", "phone found", "discovered", "has email", "yes"},
                "not found": {"not found", "email not found", "phone not found", "missing", "no email", "no"},
                "recently funded": {"recently funded", "funded", "fresh funding", "yes"},
                "no recent funding": {"no recent funding", "unfunded", "bootstrap", "not funded", "no"},
                "hiring": {"hiring", "is hiring", "open roles", "growing", "yes"},
                "not hiring": {"not hiring", "no open roles", "frozen", "no"},
                "active (>4 posts/month)": {"active (>4 posts/month)", "active", "high activity", "highly active", ">4 posts/month"},
                "passive (1-4)": {"passive (1-4)", "passive", "medium activity", "1-4 posts/month", "1-4"},
                "inactive (<1)": {"inactive (<1)", "inactive", "low activity", "cold", "<1 post/month", "<1"},
                "has mutuals": {"has mutuals", "mutuals found", "mutuals", "yes"},
                "no mutuals": {"no mutuals", "zero mutuals", "no"},
                "valid": {"valid", "deliverable", "safe", "verified", "yes"},
                "invalid / risky": {"invalid / risky", "invalid", "risky", "bouncing", "undeliverable", "no"},
                # Horizon 27: Multi-Channel Intent Triggers & Omnichannel Retargeting
                "opened": {"opened", "email opened", "open", "read", "yes", "true"},
                "not opened": {"not opened", "email not opened", "unopened", "no", "false", "timeout"},
                "clicked": {"clicked", "link clicked", "click", "engaged", "yes", "true"},
                "not clicked": {"not clicked", "no click", "no", "false", "timeout"},
                "bounced": {"bounced", "bounce", "undeliverable", "delivery failed", "failed", "yes", "true"},
                "delivered": {"delivered", "not bounced", "sent", "clean", "no", "false"},
                "accepted": {"accepted", "connection accepted", "connected", "1st degree", "yes", "true"},
                "pending": {"pending", "not accepted", "awaiting acceptance", "not connected", "no", "false", "timeout"},
                "routed": {"routed", "retargeted", "dispatched", "then", "next", "default", "success"},
                "linkedin": {"linkedin", "linkedin_dm", "dm", "message", "channel_linkedin"},
                "email": {"email", "send_email", "mail", "channel_email"},
                "inmail": {"inmail", "paid_inmail", "sponsored_inmail", "channel_inmail"}
            }
            syn_set = ai_synonyms_map.get(bh_norm)
            if syn_set:
                branch_edge = next(
                    (e for e in outgoing_edges if str(_get_h(e)).strip().lower() in syn_set), None
                )

        # 9. Single outgoing edge fallback (linear graph without named branch handles)
        if not branch_edge and len(outgoing_edges) == 1:
            single_handle = str(_get_h(outgoing_edges[0])).strip().lower()
            if not single_handle or single_handle in ("", "then", "next", "default", "success", "done", "output", "sent", "no reply yet"):
                branch_edge = outgoing_edges[0]

        terminal_branches = {
            "timeout", "timed out", "no reply", "replied", "default",
            "not found", "no match", "does not match", "no signal", "out of range",
            "low fit (<50)", "weak fit (<75)", "inactive (<1)", "passive (1-4)",
            "not hiring", "no recent funding", "no mutuals", "not booked", "not connected",
            "not detected", "no competitor", "negative", "failed",
            "invalid / risky", "invalid", "risky",
            "not opened", "not clicked", "bounced", "pending"
        }
        is_terminal = bool(branch_handle and str(branch_handle).strip().lower() in terminal_branches)
        return branch_edge, is_terminal

    def _record_observability(self, state, current_node, status, error_reason=None):
        try:
            enrollment_id = state.get("enrollment_id")
            if not enrollment_id:
                logger.error(f"[OBSERVABILITY FAILURE] Missing enrollment_id for lead state {state.get('id')}")
                return

            workspace_id = state.get("workspace_id")
            if not workspace_id:
                logger.error(f"[OBSERVABILITY FAILURE] Missing workspace_id for lead state {state.get('id')}")
                return

            self.supabase.table("campaign_events").insert({
                "workspace_id": workspace_id,
                "campaign_id": state["campaign_id"],
                "enrollment_id": enrollment_id,
                "account_id": state.get("account_id"),
                "event_type": "node_executed",
                "node_id": current_node["id"],
                "metadata": {
                    "node_type": current_node.get("node_type", "unknown"),
                    "status": status,
                    "error": error_reason
                }
            }).execute()
        except Exception as e:
            logger.warning(f"[OBSERVABILITY FAILURE] Could not emit campaign_events: {e}")
            capture_error(e, context={"service": "elein_orchestrator", "event_type": "node_executed"})

    def process_lead(self, state: Dict[str, Any], lease_token: str):
        nodes = state["nodes"]
        edges = state["edges"]

        current_node_id = state["current_node_id"]
        
        if not current_node_id:
            target_ids = {(e.get("target_node_id") or e.get("target")) for e in edges if isinstance(e, dict) and (e.get("target_node_id") or e.get("target"))}
            source_ids = {(e.get("source_node_id") or e.get("source")) for e in edges if isinstance(e, dict) and (e.get("source_node_id") or e.get("source"))}
            start_nodes = [n for n in nodes if isinstance(n, dict) and n.get("id") not in target_ids]
            if not start_nodes:
                self.mark_error(state["id"], "No start node found in campaign graph", lease_token=lease_token)
                return
            connected_starts = [n for n in start_nodes if n.get("id") in source_ids]
            current_node = connected_starts[0] if connected_starts else start_nodes[0]
            current_node_id = current_node["id"]
        else:
            current_node = next((n for n in nodes if n["id"] == current_node_id), None)

        if not current_node:
            self.mark_error(state["id"], f"Node {current_node_id} not found in graph", lease_token=lease_token)
            return

        action = current_node.get("node_type")
        data = current_node.get("config", {})

        # --- PHASE 7: REPLY DETECTION (Paranoia Layer) ---
        stop_on_reply = state.get("campaign_metadata", {}).get("stop_on_reply", True)
        reply_handling_node = action in ("wait_for_reply", "if_replied", "if_replied_positive", "if_replied_negative", "if_replied_neutral", "ai_generate_reply") or (isinstance(action, str) and action.startswith("if_replied"))
        if stop_on_reply and not reply_handling_node:
            try:
                norm_created_at = _normalize_to_utc_iso(state.get("enrollment_created_at") or state.get("enrolled_at"))
                if norm_created_at:
                    inbound_msg_res = self.supabase.table("messages") \
                        .select("id") \
                        .eq("lead_id", state.get("lead_id") or state["opportunity_id"]) \
                        .or_("direction.eq.inbound,and(direction.eq.outbound,node_id.is.null)") \
                        .gt("created_at", norm_created_at) \
                        .limit(1) \
                        .execute()
                    if inbound_msg_res.data:
                        logger.info(f"Reply or manual intervention detected for lead {state['opportunity_id']}! Pausing campaign execution.")
                        self.update_state(state["id"], current_node_id, "completed", None, lease_token, error_reason="Lead replied or manual intervention (paused)")
                        return
            except Exception as e:
                capture_error(e, context={"service": "elein_orchestrator"})
                pass
        try:
            delay_val = math.ceil(float(data.get("delay", 0)))
        except (ValueError, TypeError):
            delay_val = 1
        
        if delay_val < 1:
            delay_val = 1
            
        VALID_DELAY_UNITS = {"minutes", "hours", "days", "weeks"}
        delay_unit = data.get("delayUnit", "days")
        if delay_unit not in VALID_DELAY_UNITS:
            delay_unit = "days"

        if action == "delay":
            if delay_unit == "minutes":
                delta = timedelta(minutes=delay_val)
            elif delay_unit == "hours":
                delta = timedelta(hours=delay_val)
            elif delay_unit == "weeks":
                delta = timedelta(weeks=delay_val)
            else:
                delta = timedelta(days=delay_val)
            
            next_run = datetime.utcnow() + delta
            
            outgoing_edges = self.get_outgoing_edges(edges, current_node["id"])
            if not outgoing_edges:
                self.update_state(state["id"], None, "completed", None, lease_token, variables=state.get("variables"), tz_str=state.get('tz_str', 'UTC'))
                return
                
            next_node_id = outgoing_edges[0].get("target_node_id") or outgoing_edges[0].get("target")
            out_vars = dict(state.get("variables") or {}) if isinstance(state.get("variables"), dict) else {}
            if not self._validate_and_prepare_hop(state, current_node["id"], next_node_id, nodes, lease_token, out_vars):
                return
            self.update_state(state["id"], next_node_id, "pending", next_run, lease_token, variables=out_vars, tz_str=state.get('tz_str', 'UTC'), schedule=state.get('schedule'))
            return

        # Live check to prevent ghost execution after Panic Pause
        campaign_check = self.supabase.table("campaigns").select("status").eq("id", state["campaign_id"]).execute()
        if not campaign_check.data or campaign_check.data[0].get("status") != "ACTIVE":
            logger.info(f"Campaign {state['campaign_id']} is no longer ACTIVE. Skipping execution for lead {state['opportunity_id']}.")
            next_run = datetime.utcnow() + timedelta(hours=6)
            self.update_state(
                state["id"],
                current_node_id,
                "paused",
                next_run,
                lease_token,
                error_reason="Campaign is no longer ACTIVE",
                variables=state.get("variables"),
                tz_str=state.get("tz_str", "UTC")
            )
            return

        # --- PHASE 8: CROSS-CAMPAIGN COLLISION GUARD (Paranoia Layer 1 Preflight) ---
        OUTBOUND_ACTIONS = {
            "connection_request",
            "send_connection_request",
            "connection_no_note",
            "send_message",
            "send_ai_message",
            "send_message_with_doc",
            "send_message_with_image",
            "send_inmail",
            "send_paid_inmail",
            "send_voice_note",
            "send_meeting_invite",
            "send_intro_call_invite",
            "send_email",
            "inbound_ghostwriting",
            "comment_on_post",
            "share_post"
        }
        if action in OUTBOUND_ACTIONS:
            lead_id = state.get("lead_id") or state.get("opportunity_id")
            workspace_id = state.get("workspace_id")
            campaign_id = state.get("campaign_id")
            if lead_id and workspace_id and campaign_id:
                try:
                    if is_lead_active_in_other_campaign(
                        self.supabase,
                        workspace_id,
                        lead_id,
                        campaign_id,
                        active_statuses=["pending", "processing", "running", "waiting_for_reply", "awaiting_approval"]
                    ):
                        logger.warning(f"[CollisionGuard] Friendly fire prevented for lead {lead_id}!")
                        next_run = datetime.utcnow() + timedelta(hours=24)
                        self.update_state(
                            state["id"],
                            current_node_id,
                            "pending",
                            next_run,
                            lease_token,
                            error_reason=f"Rescheduled: friendly fire prevented for lead {lead_id} (active in another campaign)",
                            variables=state.get("variables"),
                            tz_str=state.get("tz_str", "UTC")
                        )
                        return
                except Exception as e:
                    logger.error(f"[CollisionGuard] Preflight collision check failed: {e}", exc_info=True)
                    capture_error(e, context={"service": "elein_orchestrator", "operation": "collision_preflight"})

        # Execute
        action_result = self.execute_node_action(
            action, data,
            state["opportunity_id"],
            state.get("account_id"),
            state,
            lease_token,
            current_node["id"]
        )



        
        if action == "if_connected" and action_result.get("status") == "success" and action_result.get("branch") == "Connected":
            try:
                self.supabase.table("action_log").insert({
                    "execution_state_id": state["id"],
                    "action_type": "connection_accepted",
                    "workspace_id": state["workspace_id"],
                    "metadata": {"node_id": current_node_id, "opportunity_id": state.get("opportunity_id")}
                }).execute()
            except Exception as e:
                logger.error(f"Failed to record connection_accepted to action_log: {e}")

        if "variables" in action_result:
            vars_dict = state.get("variables") or {}
            if isinstance(vars_dict, str):
                try:
                    vars_dict = json.loads(vars_dict)
                except Exception:
                    vars_dict = {}
            vars_dict.update(action_result["variables"])
            state["variables"] = vars_dict

        if action_result.get("status") == "fast_forward":
            # Idempotency collision: a previous execution of this node definitively succeeded.
            # Rehydrate the stored result as a synthetic success so process_lead can resolve
            # branch/edge normally. If branch is None (node had no branch key in its original
            # success payload) the downstream single-edge or multi-edge logic handles it correctly.
            logger.info(f"fast_forward for lead {state.get('opportunity_id')} node {current_node_id}: rehydrating prior success result.")
            action_result = {
                "status": "success",
                "branch": action_result.get("branch"),
                "variables": action_result.get("variables") or {},
            }
            # Merge variables from fast-forward payload into state so they propagate
            if action_result["variables"]:
                vars_dict = state.get("variables") or {}
                if isinstance(vars_dict, str):
                    try:
                        vars_dict = json.loads(vars_dict)
                    except Exception:
                        vars_dict = {}
                vars_dict.update(action_result["variables"])
                state["variables"] = vars_dict
            # Fall through to branch/edge resolution below

        if action_result.get("status") == "suppressed":
            # Lead is on suppression list (GDPR opt-out / manual suppression).
            # Immediately exit — do NOT retry; retrying a suppressed lead is a compliance risk.
            logger.warning(f"Lead {state.get('opportunity_id')} is suppressed. Exiting campaign immediately.")
            self.update_state(state["id"], current_node["id"], "exited", None, lease_token=lease_token,
                              error_reason="Lead suppressed (suppression list / GDPR opt-out)")
            return

        if action_result.get("status") == "waiting":

            resume_at = action_result.get("resume_at")
            if not resume_at:
                resume_at = (datetime.utcnow() + timedelta(minutes=5))
            elif isinstance(resume_at, str):
                try:
                    resume_at = datetime.fromisoformat(resume_at.replace('Z', '+00:00'))
                except ValueError:
                    resume_at = (datetime.utcnow() + timedelta(minutes=5))
            self.update_state(state["id"], current_node_id, "pending", resume_at, lease_token=lease_token, variables=state.get("variables"))
            return

        if action_result.get("status") == "waiting_for_reply":
            timeout_hours = 72
            if "timeout_hours" in data:
                try: timeout_hours = int(data["timeout_hours"])
                except Exception: pass
            elif "max_wait_hours" in data:
                try: timeout_hours = int(data["max_wait_hours"])
                except Exception: pass
            elif "delay" in data and float(data.get("delay", 0)) > 0:
                try:
                    d_val = float(data["delay"])
                    d_unit = str(data.get("delayUnit", "days")).lower()
                    if d_unit == "days":
                        timeout_hours = int(d_val * 24)
                    elif d_unit == "hours":
                        timeout_hours = int(d_val)
                    elif d_unit == "weeks":
                        timeout_hours = int(d_val * 24 * 7)
                except Exception: pass

            vars_dict = state.get("variables") or {}
            if isinstance(vars_dict, str):
                import json
                try:
                    vars_dict = json.loads(vars_dict)
                except Exception:
                    vars_dict = {}
            vars_dict = dict(vars_dict)
            existing_deadline = vars_dict.get(f"wait_reply_deadline_{current_node_id}") or vars_dict.get("wait_reply_deadline")
            if existing_deadline:
                try:
                    from dateutil.parser import parse
                    timeout_deadline = parse(existing_deadline)
                except Exception:
                    timeout_deadline = datetime.utcnow() + timedelta(hours=timeout_hours)
            else:
                timeout_deadline = datetime.utcnow() + timedelta(hours=timeout_hours)
                vars_dict[f"wait_reply_deadline_{current_node_id}"] = timeout_deadline.isoformat()

            self.update_state(state["id"], current_node_id, "waiting_for_reply", timeout_deadline, lease_token=lease_token, variables=vars_dict)
            return

            

        if action_result.get("status") == "rate_limited":
            # Reschedule to tomorrow 9am in their timezone
            tz_str = state.get("tz_str", "UTC")
            enforce_working_hours = state.get("enforce_working_hours", True)
            schedule = state.get("schedule") or (state.get("campaign_metadata") or {}).get("schedule")
            self._record_observability(state, current_node, "rate_limited", error_reason="We paused this because your daily limit is reached — automatically resumes tomorrow.")
            self.update_state(state["id"], current_node["id"], "pending", next_working_day_9am(tz_str, schedule=schedule), lease_token, tz_str=tz_str, enforce_working_hours=enforce_working_hours, schedule=schedule)
            return

        if action_result.get("status") == "account_disconnected":
            broken_account_id = state.get("account_id") or action_result.get("account_id")
            logger.warning(f"Account {broken_account_id} is disconnected. Marking as DISCONNECTED.")
            now_iso = datetime.utcnow().isoformat()
            if broken_account_id:
                try:
                    self.supabase.table("accounts").update({
                        "status": "DISCONNECTED",
                        "status_changed_at": now_iso
                    }).eq("id", broken_account_id).execute()
                except Exception as ex:
                    logger.error(f"Failed to update account {broken_account_id} status to DISCONNECTED: {ex}")

            # Query campaign_accounts for a healthy backup account (accounts.status == 'ACTIVE')
            campaign_id = state.get("campaign_id")
            if not campaign_id and state.get("enrollment_id"):
                try:
                    enroll_res = self.supabase.table("campaign_enrollments").select("campaign_id").eq("id", state["enrollment_id"]).execute()
                    if enroll_res.data:
                        campaign_id = enroll_res.data[0].get("campaign_id")
                except Exception as ex:
                    logger.error(f"Failed to query campaign_id for enrollment {state.get('enrollment_id')}: {ex}")

            backup_account_id = None
            if campaign_id:
                try:
                    query = self.supabase.table("campaign_accounts").select(
                        "account_id, accounts!inner(status)"
                    ).eq("campaign_id", campaign_id).eq("accounts.status", "ACTIVE")
                    if broken_account_id:
                        query = query.neq("account_id", broken_account_id)
                    backups_res = query.limit(1).execute()
                    if backups_res.data:
                        backup_account_id = backups_res.data[0].get("account_id")
                except Exception as ex:
                    logger.error(f"Failed to query healthy backup accounts for campaign {campaign_id}: {ex}")

            if backup_account_id:
                logger.info(f"Failing over lead {state.get('opportunity_id')} from disconnected account {broken_account_id} to backup account {backup_account_id}")
                if state.get("enrollment_id"):
                    try:
                        self.supabase.table("campaign_enrollments").update({"account_id": backup_account_id}).eq("id", state["enrollment_id"]).execute()
                    except Exception as ex:
                        logger.error(f"Failed to reassign enrollment {state.get('enrollment_id')} to account {backup_account_id}: {ex}")
                state["account_id"] = backup_account_id
                self._record_observability(
                    state,
                    current_node,
                    "error",
                    error_reason=f"Account {broken_account_id} disconnected. Automatically reassigned lead to fallback account {backup_account_id}."
                )
                self.update_state(
                    state["id"],
                    current_node_id,
                    "pending",
                    datetime.utcnow() + timedelta(seconds=30),
                    lease_token,
                    error_reason=f"Account failover to {backup_account_id}",
                    tz_str=state.get("tz_str", "UTC"),
                    enforce_working_hours=False
                )
                return
            else:
                logger.warning(f"No healthy backup accounts found for campaign {campaign_id}. Pausing lead state {state.get('id')}.")
                self._record_observability(
                    state,
                    current_node,
                    "error",
                    error_reason="We paused this because your LinkedIn session expired and no backup sender accounts are available — please reconnect your account in the Accounts tab."
                )
                self.update_state(
                    state["id"],
                    current_node_id,
                    "paused",
                    None,
                    lease_token,
                    error_reason="Account disconnected and no healthy backup accounts available.",
                    tz_str=state.get("tz_str", "UTC"),
                    enforce_working_hours=False
                )
                try:
                    ws_id = state.get("workspace_id")
                    if ws_id:
                        acc_name = broken_account_id
                        if broken_account_id:
                            acc_info = self.supabase.table("accounts").select("name").eq("id", broken_account_id).execute()
                            if acc_info.data and acc_info.data[0].get("name"):
                                acc_name = acc_info.data[0]["name"]
                        self.supabase.table("outbox_events").insert({
                            "workspace_id": ws_id,
                            "event_type": "notification.in_app",
                            "payload": {
                                "title": "LinkedIn Account Disconnected",
                                "message": f"Outreach paused: Account '{acc_name}' has been disconnected. Please reconnect your account in Settings.",
                                "body": f"Outreach paused: Account '{acc_name}' has been disconnected. Please reconnect your account in Settings.",
                                "event_type": "account_disconnected",
                                "account_id": broken_account_id
                            },
                            "status": "pending"
                        }).execute()
                except Exception as ex:
                    logger.warning(f"Failed to queue account_disconnected notification: {ex}")
                return

        if action_result.get("status") == "pool_exhausted":
            import random
            backoff_secs = random.randint(30, 60)
            next_retry = datetime.utcnow() + timedelta(seconds=backoff_secs)
            logger.info(f"Browser pool exhausted for lead {state.get('opportunity_id')}. Rescheduling in {backoff_secs}s.")
            self.update_state(state["id"], current_node_id, "pending", next_retry, lease_token=lease_token, variables=state.get("variables"))
            return

        if action_result.get("status") == "security_challenge":
            px_id = account_row.get("proxy_id") if 'account_row' in locals() and account_row else None
            if not px_id and state.get("sender_id"):
                try:
                    _acc = self.supabase.table("accounts").select("proxy_id").eq("id", state["sender_id"]).execute()
                    if _acc.data and _acc.data[0].get("proxy_id"):
                        px_id = _acc.data[0]["proxy_id"]
                except Exception:
                    pass
            if px_id:
                try:
                    from core.backend.services.proxy_routing import quarantine_proxy
                    quarantine_proxy(self.supabase, px_id, reason="security_challenge", cooldown_hours=2)
                except Exception as q_err:
                    logger.warning(f"Failed to quarantine proxy {px_id}: {q_err}")

            self.mark_error(
                state["id"],
                action_result.get("error", "Security Challenge Detected"),
                attempts=state.get("attempts", 0),
                max_attempts=state.get("max_attempts", 5),
                hard_error=True,
                lease_token=lease_token,
                node_id=current_node_id
            )
            return

        if action_result.get("status") == "error":
            self.mark_error(
                state["id"], 
                action_result.get("error", "Unknown error"), 
                attempts=state.get("attempts", 0), 
                max_attempts=state.get("max_attempts", 5),
                hard_error=action_result.get("requires_approval", False),
                lease_token=lease_token,
                node_id=current_node_id
            )
            return

        if action_result.get("status") == "not_implemented":
            self.mark_error(
                state["id"],
                f"Action not yet supported: {action}",
                attempts=state.get("attempts", 0),
                max_attempts=state.get("max_attempts", 5),
                hard_error=True,
                lease_token=lease_token,
                node_id=current_node_id
            )
            return
            
        if action_result.get("status") == "awaiting_approval":
            self.update_state(state["id"], current_node["id"], "awaiting_approval", None, lease_token, tz_str=state.get('tz_str', 'UTC'))
            return

        if action_result.get("status") == "skipped":
            # Used when account is locked. Reschedule quickly.
            self.update_state(state["id"], current_node["id"], "pending", datetime.utcnow() + timedelta(seconds=45), lease_token=lease_token)
            return

        if action == "mark_converted":
            self.update_state(state["id"], current_node["id"], "exited", None, lease_token=lease_token, error_reason="mark_converted")
            try:
                from knowledge.backend.services.bayesian_icp_service import record_outcome, _extract_signals
                variables = state.get("variables", {})
                if isinstance(variables, str):
                    import json
                    try:
                        variables = json.loads(variables)
                    except:
                        variables = {}
                signal_flags = _extract_signals(variables or {})
                lead_id = state.get("lead_id") or state.get("opportunity_id")
                record_outcome(self.supabase, state.get("workspace_id"), lead_id, "won", signal_flags)
            except Exception as e:
                logger.error(f"Failed to record Bayesian ICP won outcome: {e}")
            return

        if action == "sequence_end":
            self.update_state(state["id"], current_node["id"], "exited", None, lease_token=lease_token, error_reason="sequence_completed")
            return

        if action == "retry_step":
            max_retries = int(data.get("max_retries", 3))
            vars_dict = state.get("variables") or {}
            if isinstance(vars_dict, str):
                import json
                vars_dict = json.loads(vars_dict)
            
            retry_key = f"retry_{current_node['id']}"
            current_retries = vars_dict.get(retry_key, 0)
            
            if current_retries < max_retries:
                vars_dict[retry_key] = current_retries + 1
                incoming = self.get_incoming_edges(edges, current_node["id"])
                if incoming:
                    parent_id = incoming[0].get("source_node_id") or incoming[0].get("source")
                    logger.info(f"Retrying parent node {parent_id} (Attempt {current_retries+1}/{max_retries})")
                    self.update_state(state["id"], parent_id, "pending", None, lease_token, variables=vars_dict)
                    return
                else:
                    logger.warning("Retry step has no parent to retry!")
            
            # If max retries exceeded or no parent, halt lead
            logger.info("Max retries exceeded or no parent on retry_step. Halting lead in error state.")
            self.update_state(state["id"], current_node["id"], "error", None, lease_token, error_reason="Max retries exceeded on retry_step")
            return


        # ── C5: Terminal / dangling node handling ─────────────────────────────
        # Advance to next node only if an outgoing edge exists.
        # If no outgoing edge → the node is terminal (dangling). Mark completed.
        # Never leave status='claimed' — the dequeue lock will permanently hide it if lease is not released.
        outgoing_edges = self.get_outgoing_edges(edges, current_node["id"])

        if not outgoing_edges:
            logger.info(f"C5: Terminal node '{current_node['id']}' — marking lead_state {state['id']} completed")
            self.update_state(state["id"], None, "completed", None, lease_token, variables=state.get("variables"), tz_str=state.get('tz_str', 'UTC'))
            return


        if "branch" in action_result:
            branch_handle = action_result["branch"]
            logger.debug(f"Node {current_node_id} returned branch '{branch_handle}'. Available edges: {[e.get('source_handle', e.get('sourceHandle', e.get('label', ''))) for e in outgoing_edges]}")
            
            branch_edge, is_terminal = self.resolve_branch_edge(outgoing_edges, branch_handle)

            if not branch_edge:
                if is_terminal:
                    logger.info(f"Lead {state['opportunity_id']} reached terminal branch '{branch_handle}' on node {current_node_id}. Completing campaign.")
                    self.update_state(state["id"], None, "completed", None, lease_token, error_reason=f"Reached terminal branch '{branch_handle}'", variables=state.get("variables"), tz_str=state.get('tz_str', 'UTC'))
                    return
                err_msg = f"Lead {state['opportunity_id']} stuck: node {current_node_id} returned branch '{branch_handle}' but no matching edge found. Marking lead as ERROR."
                logger.error(err_msg)
                self.update_state(state["id"], current_node_id, "error", None, lease_token, error_reason=err_msg, tz_str=state.get('tz_str', 'UTC'))
                return
            next_node_id = branch_edge.get("target_node_id") or branch_edge.get("target")
        elif len(outgoing_edges) == 1:
            next_node_id = outgoing_edges[0].get("target_node_id") or outgoing_edges[0].get("target")
        else:
            self.mark_error(state["id"], f"Node {current_node['id']} has multiple edges but no branch returned", lease_token=lease_token, node_id=current_node_id, tz_str=state.get('tz_str', 'UTC'))
            return

        # Evasion jitter: randomly delay (45-120s) before executing the next node
        jitter = timedelta(seconds=random.randint(45, 120))
        out_vars = dict(state.get("variables") or {}) if isinstance(state.get("variables"), dict) else {}
        out_vars.pop("wait_reply_timed_out", None)
        out_vars.pop(f"wait_reply_timed_out_{current_node_id}", None)
        out_vars.pop("wait_reply_deadline", None)
        out_vars.pop(f"wait_reply_deadline_{current_node_id}", None)

        if not self._validate_and_prepare_hop(state, current_node_id, next_node_id, nodes, lease_token, out_vars):
            return

        self.update_state(state["id"], next_node_id, "pending", datetime.utcnow() + jitter, lease_token, variables=out_vars, tz_str=state.get('tz_str', 'UTC'), schedule=state.get('schedule'))

    def execute_node_action(
        self, action: str, data: dict, opportunity_id: str, account_id: str, state: dict, lease_token: str, current_node_id: str
    ) -> dict:
        logger.info(f"Executing node '{action}' for lead '{opportunity_id}'")
    
        res = self.supabase.table("leads").select("id, first_name, last_name, company_name, job_title, linkedin_url, domain, email").eq("id", opportunity_id).eq("workspace_id", state["workspace_id"]).execute()
        opportunity = res.data[0] if res.data else {}
    
        if opportunity:
            opportunity["kdm_first"] = opportunity.get("first_name", "")
            opportunity["kdm_last"] = opportunity.get("last_name", "")
            opportunity["verified_email"] = opportunity.get("email", "")
        linkedin_url = opportunity.get("linkedin_url")
    
        resolved_data = interpolate_node_data(data, opportunity)
        
        for k in ['body', 'body_a', 'body_b', 'body_c', 'note', 'subject']:
            if k in resolved_data and isinstance(resolved_data[k], str) and "{{" in resolved_data[k] and "}}" in resolved_data[k]:
                logger.error(f"Execution blocked: Unresolved variable remains in '{k}' for lead {opportunity_id}")
                return {"status": "error", "error": f"Missing variable data for '{k}'. The lead does not have this information, and no fallback was provided.", "requires_approval": True}
    
        requires_linkedin = action in ACTION_TYPE_MAP
        # LinkedIn actions and external side-effects require the idempotency lock
        requires_idempotency = requires_linkedin or action == "push_to_crm"
        idemp_key = None
        
        if requires_linkedin and not account_id:
            logger.warning("No sender account allocated — cannot execute LinkedIn nodes")
            return {"status": "error", "error": "No sender account allocated to this lead's enrollment"}
            
        chosen_sender_id = account_id
                
        worker = None
        worker_id = str(uuid.uuid4())
        heartbeat_event = threading.Event()
        lease_revoked = threading.Event()
        heartbeat_thread = None
        
        def heartbeat_worker():
            while not heartbeat_event.is_set():
                try:
                    res = self.supabase.rpc("renew_lead_lease", {
                        "p_state_id": state["id"],
                        "p_lease_token": lease_token,
                        "p_extra_seconds": 300
                    }).execute()
                    if res.data is False:
                        logger.warning(f"[Heartbeat] Lead lease expired or was revoked for state {state['id']}")
                        lease_revoked.set()
                        break
                except Exception as rpc_e:
                    # Layer 1 Fallback: Direct table lease renewal if RPC is missing
                    try:
                        now_dt = datetime.now(timezone.utc)
                        new_expiry = (now_dt + timedelta(seconds=300)).isoformat()
                        tb_res = self.supabase.table("campaign_execution_states").update({
                            "lease_expires_at": new_expiry
                        }).eq("id", state["id"]).eq("lease_token", lease_token).execute()
                        if not tb_res.data:
                            logger.warning(f"[Heartbeat Fallback] Lease expired or mismatched for state {state['id']}")
                            lease_revoked.set()
                            break
                    except Exception:
                        pass

                if requires_linkedin and chosen_sender_id:
                    renew_account_session_lock(self.supabase, chosen_sender_id, worker_id, extra_seconds=300)
                heartbeat_event.wait(60.0)
                
        try:
            heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
            heartbeat_thread.start()
            
            # --- 1. Account Lock & 2. Account Eligibility ---
            cookies = None
            if requires_linkedin:
                if not try_acquire_session_lock(self.supabase, chosen_sender_id, lock_duration_seconds=300, worker_id=worker_id):
                    logger.warning(f"Account {chosen_sender_id} is locked by another worker. Rescheduling lead.")
                    # skipped is handled by process_lead as a 45s orchestration pause
                    return {"status": "skipped", "reason": "account_locked"}
                    
                acc_res = self.supabase.table("accounts").select(
                    "id, workspace_id, status, status_changed_at, proxy_id, session_cookies_encrypted, is_warmup, warmup_max_connections, warmup_max_messages, proxies(protocol, host, port, username)"
                ).eq("id", chosen_sender_id).execute()
                account_row = acc_res.data[0] if acc_res.data else None
                
                if not account_row:
                    return {"status": "error", "error": f"Sender {chosen_sender_id} not found"}
                    
                acc_status = account_row.get("status")
                # Auto-Cooling Check for RATE_LIMITED accounts
                if acc_status == "RATE_LIMITED":
                    status_changed_at_str = account_row.get("status_changed_at")
                    if status_changed_at_str:
                        from dateutil.parser import parse
                        try:
                            status_changed_at = parse(status_changed_at_str)
                            if status_changed_at.tzinfo is None:
                                status_changed_at = status_changed_at.replace(tzinfo=pytz.UTC)
                            
                            if datetime.utcnow().replace(tzinfo=pytz.UTC) - status_changed_at >= timedelta(hours=6):
                                # Cooling period elapsed, auto-resume to ACTIVE!
                                now_iso = datetime.utcnow().replace(tzinfo=pytz.UTC).isoformat()
                                self.supabase.table("accounts").update({
                                    "status": "ACTIVE",
                                    "status_changed_at": now_iso
                                }).eq("id", chosen_sender_id).execute()
                                
                                logger.info(f"[AutoCooling] Account {chosen_sender_id} cooling period elapsed. Auto-resumed to ACTIVE.")
                                acc_status = "ACTIVE"
                                account_row["status"] = "ACTIVE"
                        except Exception as e:
                            logger.error(f"[AutoCooling] Failed to parse status_changed_at {status_changed_at_str}: {e}")

                if acc_status in ("NEEDS_REVIEW", "DISABLED", "SUSPENDED", "MANUAL_MODE", "DISCONNECTED", "BANNED", "RATE_LIMITED", "NEEDS_ATTENTION"):
                    # --- VULNERABILITY FIXED: Intelligent Dynamic Failover ---
                    # Banned or Disconnected accounts should trigger INSTANT failover to a healthy team member.
                    # Rate-limited accounts should wait 6 hours (auto-cooling) or 48 hours for stale unhealthy before reallocating.
                    is_stale_unhealthy = False
                    if acc_status in ("DISCONNECTED", "BANNED", "SUSPENDED", "NEEDS_ATTENTION"):
                        is_stale_unhealthy = True
                    elif acc_status == "RATE_LIMITED":
                        status_changed_at_str = account_row.get("status_changed_at")
                        if status_changed_at_str:
                            from dateutil.parser import parse
                            try:
                                status_changed_at = parse(status_changed_at_str)
                                if status_changed_at.tzinfo is None:
                                    status_changed_at = status_changed_at.replace(tzinfo=pytz.UTC)
                                if datetime.utcnow().replace(tzinfo=pytz.UTC) - status_changed_at > timedelta(hours=48):
                                    is_stale_unhealthy = True
                            except Exception as e:
                                logger.error(f"Failed to parse status_changed_at {status_changed_at_str}: {e}")
                    
                    if is_stale_unhealthy:
                        # Attempt reassignment
                        campaign_id = state.get("campaign_id")
                        if not campaign_id and "enrollment_id" in state:
                            enroll_res = self.supabase.table("campaign_enrollments").select("campaign_id").eq("id", state["enrollment_id"]).execute()
                            if enroll_res.data:
                                campaign_id = enroll_res.data[0]["campaign_id"]
                        if campaign_id:
                            # Find healthy backup account
                            backups_res = self.supabase.table("campaign_accounts").select(
                                "account_id, accounts!inner(status)"
                            ).eq("campaign_id", campaign_id).eq("accounts.status", "ACTIVE").neq("account_id", chosen_sender_id).limit(1).execute()
                            
                            if backups_res.data:
                                new_account_id = backups_res.data[0]["account_id"]
                                if "enrollment_id" in state:
                                    self.supabase.table("campaign_enrollments").update({"account_id": new_account_id}).eq("id", state["enrollment_id"]).execute()
                                state["account_id"] = new_account_id
                                self._record_observability(state, {"id": current_node_id}, "rate_limited", error_reason=f"Account {chosen_sender_id} was unhealthy. Automatically reassigned lead to fallback account {new_account_id}.")
                                return {"status": "skipped"} # VULNERABILITY FIXED: Reschedule in 45 seconds instead of stalling until tomorrow
                                
                    # Fallback to existing stall behavior
                    if acc_status == "DISCONNECTED":
                        return {"status": "account_disconnected"}
                    return {"status": "rate_limited"}

                # VULNERABILITY FIXED: Safely check rate limit AFTER lock acquisition and health check
                tz_str = state.get("tz_str") or "UTC"
                allowed = try_consume_action(self.supabase, chosen_sender_id, action, account=account_row, tz_str=tz_str)
                if not allowed:
                    return {"status": "rate_limited"}
                    
                if not account_row.get("proxy_id") and not account_row.get("proxies"):
                    logger.warning(f"Account {chosen_sender_id} has no proxy assigned — running without proxy (raw IP risk)")
                    
                if account_row.get("session_cookies_encrypted"):
                    from core.backend.services import crypto
                    import base64
                    
                    dek_bytes = None
                    cookie_secret_ref = None
                    try:
                        sys_res = self.supabase.table("system_api_keys").select("secret_id").eq("service", "cookie_dek").eq("workspace_id", account_row["workspace_id"]).execute()
                        if sys_res.data:
                            cookie_secret_ref = sys_res.data[0]["secret_id"]
                    except Exception as e:
                        capture_error(e, context={"service": "elein_orchestrator", "detail": "system_api_keys table may not exist; falling back to COOKIE_PRIVATE_KEY"})
                    if cookie_secret_ref:
                        try:
                            rpc_res = self.supabase.rpc("get_decrypted_account_payload", {"p_account_id": chosen_sender_id}).execute()
                            if rpc_res.data and rpc_res.data.get("dek"):
                                dek_bytes = base64.b64decode(rpc_res.data["dek"])
                        except Exception as e:
                            capture_error(e, context={"service": "elein_orchestrator"})
                    
                    try:
                        _raw = account_row["session_cookies_encrypted"]
                        _raw_bytes = _raw if isinstance(_raw, (bytes, bytearray)) else _raw.encode("utf-8")
                        cookies_bytes = crypto.decrypt_bytes(_raw_bytes, dek=dek_bytes)
                        cookies = cookies_bytes.decode("utf-8")
                        proxy_url = _build_proxy_url(account_row, self.supabase)
                        worker = LinkedInWorker(cookies, proxy_url=proxy_url, account_id=chosen_sender_id)
                    except (crypto.VaultDecryptionError, Exception) as e:
                        logger.error(f"Account {chosen_sender_id} decryption failed: {e}.")
                        now = datetime.utcnow().isoformat()
                        self.supabase.table("account_health_checks").insert({
                            "account_id": chosen_sender_id, "check_type": "decryption", "result": "fail",
                            "detail": {"message": "Decryption Failed / Corrupted"}, "checked_at": now
                        }).execute()
                        self.supabase.table("accounts").update({"status": "NEEDS_ATTENTION", "session_locked_until": None, "last_health_check_at": now}).eq("id", chosen_sender_id).execute()
                        if dek_bytes: del dek_bytes
                        return {"status": "error", "error": "DEFINITIVE_EXTERNAL_FAILURE: Decryption failed"}
                        
                    if dek_bytes: del dek_bytes
                else:
                    logger.warning(f"Sender {chosen_sender_id} has missing/invalid cookies")
            
            # --- 3. Idempotency Lock ---
            if requires_idempotency:
                import hashlib
                attempt_count = state.get("attempts", 0)
                # The identity of the execution attempt
                idempotency_raw = f"{state.get('enrollment_id')}_{current_node_id}"
                idemp_key = hashlib.sha256(idempotency_raw.encode('utf-8')).hexdigest()
                
                try:
                    self.supabase.table("campaign_node_executions").insert({
                        "idempotency_key": idemp_key,
                        "status": "running",
                        "node_id": current_node_id,
                        "workspace_id": state.get("workspace_id"),
                        "enrollment_id": state.get("enrollment_id"),
                        "campaign_version_id": state.get("campaign_version_id"),
                        "account_id": chosen_sender_id,
                        "node_type": action,
                        "attempt": attempt_count
                    }).execute()
                except Exception as e:
                    # Collision detected!
                    # Check unique constraint (code 23505)
                    err_str = str(e)
                    if not (hasattr(e, 'code') and getattr(e, 'code') == '23505') and '23505' not in err_str:
                        return {"status": "error", "error": f"Database failed to create idempotency lock: {e}"}
                    try:
                        collision_res = self.supabase.table("campaign_node_executions").select("status, error_code, output_payload").eq("idempotency_key", idemp_key).execute()
                        if collision_res.data:
                            col_status = collision_res.data[0]["status"]
                            col_err = collision_res.data[0].get("error_code")
                            payload = collision_res.data[0].get("output_payload") or {}
                            
                            if col_status == "success":
                                # The external job or action definitively succeeded. Rehydrate payload and fast-forward.
                                logger.info(f"Idempotency hit ({idemp_key}): Previous execution succeeded. Fast-forwarding.")
                                return {"status": "fast_forward", "branch": payload.get("branch"), "variables": payload.get("variables")}
                            elif col_status == "failed":
                                upd_res = self.supabase.table("campaign_node_executions").update({"status": "running"}).eq("idempotency_key", idemp_key).eq("status", "failed").execute()
                                if not upd_res.data:
                                    return {"status": "error", "error": "UNKNOWN: Concurrent worker collision during retry.", "requires_approval": True}
                                logger.info(f"Idempotency hit ({idemp_key}): Retrying previously failed action ({col_err}).")
                                pass 
                            elif col_status == "running":
                                # UNKNOWN outcome. A worker crashed mid-execution. Halt campaign for safety.
                                return {"status": "error", "error": "UNKNOWN: Previous worker crashed mid-execution. Safe resume requires manual verification.", "requires_approval": True}
                        else:
                            logger.error(f"Idempotency INSERT failed, but no collision exists. DB error: {e}")
                            return {"status": "error", "error": f"Database failed to create idempotency lock: {e}"}
                    except Exception as inner_e:
                        return {"status": "error", "error": f"Failed to resolve idempotency lock: {inner_e}"}
            

            # --- 5. Execute Action ---
            from campaigns.backend.services.elein_executor import EleInNodeExecutor
            lead_identifier = state.get("lead_id") or state.get("opportunity_id") or opportunity_id
            resolved_data["_workspace_id"] = state.get("workspace_id")
            resolved_data["_lead_id"] = lead_identifier
            resolved_data["lead_id"] = lead_identifier
            resolved_data["opportunity_id"] = lead_identifier
            resolved_data["_enrollment_id"] = state.get("enrollment_id")
            resolved_data["_account_id"] = state.get("account_id")
            resolved_data["_execution_state_id"] = state.get("id")
            resolved_data["_current_node_id"] = current_node_id
            resolved_data["_attempts"] = state.get("attempts", 0)
            enr_timestamp = state.get("enrollment_created_at") or state.get("enrolled_at")
            resolved_data["_enrollment_created_at"] = enr_timestamp
            resolved_data["enrollment_created_at"] = enr_timestamp
            resolved_data["enrolled_at"] = enr_timestamp
            resolved_data["_next_run_at"] = state.get("next_run_at")
            resolved_data["next_run_at"] = state.get("next_run_at")
            resolved_data["variables"] = state.get("variables") or {}
            if state.get("variables") and state["variables"].get("approved_ai_reply"):
                resolved_data["approved_ai_reply"] = state["variables"]["approved_ai_reply"]
            resolved_data["tz_str"] = state.get("tz_str") or "UTC"
            resolved_data["_skip_limit_check"] = True
            executor = EleInNodeExecutor(worker, supabase=self.supabase)
            try:
                res = executor.execute(action, resolved_data, linkedin_url)
            except Exception as e:
                err_str = str(e)
                err_lower = err_str.lower()
                if "suppression_list_violation" in err_lower or "u0001" in err_lower:
                    logger.warning(f"Suppression violation caught in orchestrator for lead {lead_identifier}: {err_str}")
                    res = {"status": "suppressed", "error": err_str}
                elif "insufficient_credits" in err_lower:
                    logger.warning(f"Credit limit exceeded for lead {lead_identifier} on action {action}")
                    res = {"status": "error", "error": "insufficient_credits", "requires_approval": True}
                    try:
                        campaign_id = state.get("campaign_id")
                        if campaign_id:
                            self.supabase.table("campaigns").update({"status": "PAUSED"}).eq("id", campaign_id).execute()
                            logger.error(f"Kill-switch activated: Paused campaign {campaign_id} due to insufficient credits.")
                    except Exception as ex:
                        logger.error(f"Failed to pause campaign upon insufficient_credits: {ex}")
                else:
                    logger.error(f"Executor crash on {action}: {e}", exc_info=True)
                    res = {"status": "error", "error": err_str}
            
            # Coerce unhandled statuses to error so process_lead doesn't silently advance the graph
            if res.get("status") not in ("success", "waiting", "waiting_for_reply", "rate_limited", "account_disconnected", "security_challenge", "error", "skipped", "suppressed", "awaiting_approval", "not_implemented"):
                res = {"status": "error", "error": f"DEFINITIVE_EXTERNAL_FAILURE: Unhandled executor status '{res.get('status')}'"}
            
            # --- 6. Durable Result Update ---
            if requires_linkedin and chosen_sender_id:
                if res.get("status") == "account_disconnected":
                    self.supabase.table("accounts").update({
                        "status": "DISCONNECTED",
                        "status_changed_at": datetime.utcnow().isoformat()
                    }).eq("id", chosen_sender_id).execute()
                    if idemp_key:
                        self.supabase.table("campaign_node_executions").update({
                            "status": "failed",
                            "error_code": "ACCOUNT_DISCONNECTED"
                        }).eq("idempotency_key", idemp_key).execute()
                    return {"status": "account_disconnected"}
                    
                elif res.get("status") == "security_challenge":
                    px_id = account_row.get("proxy_id") if 'account_row' in locals() and account_row else None
                    if not px_id and chosen_sender_id:
                        try:
                            _acc = self.supabase.table("accounts").select("proxy_id").eq("id", chosen_sender_id).execute()
                            if _acc.data and _acc.data[0].get("proxy_id"):
                                px_id = _acc.data[0]["proxy_id"]
                        except Exception:
                            pass
                    if px_id:
                        try:
                            from core.backend.services.proxy_routing import quarantine_proxy
                            quarantine_proxy(self.supabase, px_id, reason="security_challenge", cooldown_hours=2)
                        except Exception as q_err:
                            logger.warning(f"Failed to quarantine proxy {px_id}: {q_err}")

                    self.supabase.table("accounts").update({
                        "status": "SUSPENDED",
                        "status_changed_at": datetime.utcnow().isoformat()
                    }).eq("id", chosen_sender_id).execute()
                    if idemp_key:
                        self.supabase.table("campaign_node_executions").update({
                            "status": "failed",
                            "error_code": "SECURITY_CHALLENGE"
                        }).eq("idempotency_key", idemp_key).execute()
                    
                    try:
                        ws_id = state.get("workspace_id")
                        if ws_id:
                            acc_name = chosen_sender_id
                            acc_info = self.supabase.table("accounts").select("name").eq("id", chosen_sender_id).execute()
                            if acc_info.data and acc_info.data[0].get("name"):
                                acc_name = acc_info.data[0]["name"]
                            self.supabase.table("outbox_events").insert({
                                "workspace_id": ws_id,
                                "event_type": "notification.in_app",
                                "payload": {
                                    "title": "LinkedIn Verification Required",
                                    "message": f"LinkedIn requested a security checkpoint on account '{acc_name}'. Outreach paused. Please log in via Chrome to resolve the challenge, then reconnect."
                                },
                                "status": "pending"
                            }).execute()
                    except Exception as ex:
                        logger.warning(f"Failed to queue security_challenge notification: {ex}")

                    return {"status": "security_challenge"}
                
                elif res.get("status") == "rate_limited":
                    if idemp_key:
                        self.supabase.table("campaign_node_executions").update({
                            "status": "failed",
                            "error_code": "RATE_LIMITED"
                        }).eq("idempotency_key", idemp_key).execute()
                    return {"status": "rate_limited"}
            
            if requires_idempotency and idemp_key:
                if res.get("status") == "success":
                    exec_status = "success"
                elif res.get("status") in ("waiting", "waiting_for_reply", "awaiting_approval"):
                    exec_status = "running"
                else:
                    exec_status = "failed"
                    
                err_code = None
                
                if exec_status == "failed":
                    err_code = "TRANSIENT_EXECUTION_ERROR" if res.get("status") == "skipped" else "DEFINITIVE_EXTERNAL_FAILURE"
                    # If it explicitly provides an error categorisation in the message, try to extract it
                    err_msg = res.get("error", "")
                    if err_msg.startswith("TRANSIENT_EXECUTION_ERROR:"):
                        err_code = "TRANSIENT_EXECUTION_ERROR"
                    elif err_msg.startswith("DEFINITIVE_EXTERNAL_FAILURE:"):
                        err_code = "DEFINITIVE_EXTERNAL_FAILURE"
                        
                payload = {
                    "status": res.get("status"),
                    "branch": res.get("branch"),
                    "variables": res.get("variables") or {},
                    "error": res.get("error"),  # included for failure diagnostics
                    "ai_reasoning": res.get("ai_reasoning")
                }
                    
                upd = {
                    "status": exec_status,
                    "output_payload": payload
                }
                if err_code:
                    upd["error_code"] = err_code
                    
                self.supabase.table("campaign_node_executions").update(upd).eq("idempotency_key", idemp_key).execute()
                
            return res
            
        finally:
            heartbeat_event.set()
            if heartbeat_thread:
                heartbeat_thread.join(timeout=2.0)
            if requires_linkedin and chosen_sender_id:
                release_session_lock(self.supabase, chosen_sender_id, worker_id)

    def update_state(self, state_id: str, node_id: str, status: str, next_run_at: Optional[datetime], lease_token: str, error_reason: str = None, attempts: int = None, variables: dict = None, tz_str: str = "UTC", enforce_working_hours: bool = True, schedule: dict = None, lead_id: Optional[str] = None, use_sto: bool = False):
        # PARANOIA LAYER 2: Prevent developers from adding un-requeuable waiting statuses
        VALID_WAITING_STATUSES = {"waiting_for_reply", "waiting_for_approval"}
        if status.startswith("waiting_") and status not in VALID_WAITING_STATUSES:
            raise NotImplementedError(f"Status '{status}' is not registered as a valid waiting status with a re-queue path.")
            
        if next_run_at and enforce_working_hours:
            from campaigns.backend.services.sto_service import should_use_sto, calculate_sto_next_run
            if use_sto or should_use_sto(schedule=schedule):
                next_run_at = calculate_sto_next_run(next_run_at, tz_str, lead_id=lead_id, schedule=schedule, supabase=self.supabase).replace(tzinfo=None)
            else:
                next_run_at = adjust_to_working_hours(next_run_at, tz_str, schedule=schedule)
        try:
            res = self.supabase.rpc("release_lead_claim", {
                "p_state_id": state_id,
                "p_lease_token": lease_token,
                "p_next_status": status,
                "p_next_node": node_id,
                "p_next_run": next_run_at.isoformat() if next_run_at else None,
                "p_variables": variables,
                "p_error_reason": error_reason,
                "p_attempts": attempts
            }).execute()
            if not res.data:
                logger.warning(f"Failed to advance state {state_id} - lease {lease_token} may have expired.")
        except Exception as e:
            logger.warning(f"[Orchestrator] release_lead_claim RPC failed for state {state_id}: {e}. Attempting direct table fallback.")
            capture_error(e, context={"service": "elein_orchestrator"})
            # Layer 1 Fallback: Direct table update matching lease_token if available
            try:
                now_iso = datetime.now(timezone.utc).isoformat()
                upd_payload = {
                    "status": status,
                    "next_run_at": next_run_at.isoformat() if next_run_at else None,
                    "lease_token": None,
                    "lease_expires_at": None,
                    "updated_at": now_iso
                }
                if node_id is not None:
                    upd_payload["current_node_id"] = node_id
                if variables is not None:
                    upd_payload["variables"] = variables
                if error_reason is not None:
                    upd_payload["error_reason"] = error_reason
                if attempts is not None:
                    upd_payload["attempts"] = attempts

                q = self.supabase.table("campaign_execution_states").update(upd_payload).eq("id", state_id)
                if lease_token:
                    q = q.eq("lease_token", lease_token)
                q.execute()
            except Exception as fb_err:
                logger.error(f"[Orchestrator] Direct table update fallback also failed for state {state_id}: {fb_err}")

    def mark_error(self, state_id: str, error_msg: str, attempts: int = 0, max_attempts: int = 5, hard_error: bool = False, lease_token: str = None, node_id: str = None, tz_str: str = "UTC", enforce_working_hours: bool = True, schedule: dict = None):
        logger.error(f"Lead state {state_id} errored: {error_msg} (Attempt {attempts + 1}/{max_attempts})")
        new_attempts = max_attempts if hard_error else attempts + 1
        
        if new_attempts >= max_attempts:
            # Exhausted retries -> hard error
            self.update_state(state_id, node_id, "error", None, lease_token, error_reason=error_msg, attempts=new_attempts)
            try:
                res = self.supabase.table("campaign_execution_states").select("workspace_id, enrollment_id, variables").eq("id", state_id).execute()
                if res.data:
                    row = res.data[0]
                    enr_res = self.supabase.table("campaign_enrollments").select("lead_id").eq("id", row["enrollment_id"]).execute()
                    if enr_res.data:
                        lead_id = enr_res.data[0]["lead_id"]
                        from knowledge.backend.services.bayesian_icp_service import record_outcome, _extract_signals
                        variables = row.get("variables")
                        if isinstance(variables, str):
                            import json
                            try:
                                variables = json.loads(variables)
                            except:
                                variables = {}
                        signal_flags = _extract_signals(variables or {})
                        record_outcome(self.supabase, row["workspace_id"], lead_id, "lost", signal_flags)
            except Exception as e:
                logger.error(f"Failed to record Bayesian ICP lost outcome: {e}")
        else:
            # Exponential backoff (e.g. 15m, 1h, 4h, etc) -> back to pending
            backoff_minutes = 15 * (4 ** attempts)
            next_run = (datetime.utcnow() + timedelta(minutes=backoff_minutes))
            self.update_state(state_id, node_id, "pending", next_run, lease_token, error_reason=error_msg, attempts=new_attempts, tz_str=tz_str, enforce_working_hours=enforce_working_hours, schedule=schedule)


def _build_proxy_url(account_row: dict, supabase_client):
    from core.backend.services.proxy_routing import find_sticky_failover_proxy, is_proxy_quarantined
    p = account_row.get("proxies")
    is_unhealthy_or_quarantined = (
        not p or 
        p.get("is_active") is False or 
        p.get("status") in ("degraded", "banned", "disabled", "quarantined") or 
        is_proxy_quarantined(p)
    )
    if is_unhealthy_or_quarantined:
        wid = account_row.get("workspace_id")
        if wid and supabase_client:
            try:
                target_country = account_row.get("country_code") or (p.get("country_code") if p else None)
                replacement = find_sticky_failover_proxy(
                    supabase_client,
                    wid,
                    current_proxy_id=p.get("id") if p else None,
                    target_country=target_country
                )
                if replacement:
                    account_row["proxy_id"] = replacement["id"]
                    account_row["proxies"] = replacement
                    p = replacement
                    if account_row.get("id"):
                        try:
                            supabase_client.table("accounts").update({"proxy_id": replacement["id"]}).eq("id", account_row["id"]).execute()
                        except Exception as update_err:
                            import logging
                            logging.getLogger(__name__).warning(f"Could not persist proxy failover to account: {update_err}")
            except Exception as failover_err:
                import logging
                logging.getLogger(__name__).warning(f"Proxy failover query failed: {failover_err}")

    p = account_row.get("proxies")
    if not p:
        return None
    
    auth = ""
    if p.get("username"):
        password_plain = ""
        proxy_id = account_row.get("proxy_id")
        if proxy_id:
            try:
                rpc_res = supabase_client.rpc("get_decrypted_proxy_payload", {"p_proxy_id": proxy_id}).execute()
                if rpc_res.data and rpc_res.data.get("password_encrypted"):
                    from core.backend.core import crypto
                    import base64
                    
                    raw_encrypted = base64.b64decode(rpc_res.data["password_encrypted"])
                    dek_bytes = None
                    if rpc_res.data.get("dek"):
                        dek_bytes = base64.b64decode(rpc_res.data["dek"])
                    
                    password_plain = crypto.decrypt_bytes(raw_encrypted, dek=dek_bytes).decode('utf-8')
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to decrypt proxy password for {proxy_id}: {e}")
                
        auth = f"{p['username']}:{password_plain}@"
        
    return f"{p['protocol']}://{auth}{p['host']}:{p['port']}"
