from dotenv import load_dotenv
load_dotenv()
import uuid
import threading


import json
import re
import math
from datetime import datetime, timedelta, date, time as dt_time
from typing import Dict, Any, List, Optional
import random
import pytz

from core.backend.api.auth_dep import get_service_client
from integrations.backend.services.linkedin_worker import LinkedInWorker

from core.backend.services.telemetry import capture_error
import logging
logger = logging.getLogger(__name__)


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
    if not template:
        return template

    mapping = {
        "first_name":    opportunity.get("kdm_first") or "",
        "last_name":     opportunity.get("kdm_last") or "",
        "company":       opportunity.get("company_name") or "",
        "job_title":     opportunity.get("job_title") or "",
        "location":      opportunity.get("location") or "",
        "industry":      opportunity.get("industry") or "",
        "mutual_connections": opportunity.get("mutual_connections") or "a mutual connection",
    }

    def replace_var(m: re.Match) -> str:
        var_content = m.group(1).strip()
        parts = [p.strip() for p in var_content.split("|")]
        key = parts[0]
        inline_fallback = parts[1] if len(parts) > 1 else ""
        
        # Sanitize specific variables to prevent spam/emojis leaking into messages
        raw_val = mapping.get(key)
        if raw_val and key in ["first_name", "last_name", "company", "job_title"]:
            raw_val = _sanitize_scraped_string(raw_val, key)
            mapping[key] = raw_val

        # 1. Graceful fallback for first_name
        if key == "first_name" and not mapping.get("first_name"):
            return inline_fallback if inline_fallback else "there"
            
        # 2. For other mapped variables, if they are empty, DO NOT REPLACE.
        # Unless an inline fallback is provided.
        if key in mapping and not mapping.get(key):
            if inline_fallback:
                return inline_fallback
            return m.group(0) 
            
        return mapping.get(key, m.group(0))   # keep original if unknown

    return re.sub(r"\{\{([^}]+)\}\}", replace_var, template)


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


def try_consume_action(supabase, account_id: str, action: str) -> bool:
    """
    Calls the Supabase try_consume_daily_action() RPC.
    Returns True if the action is allowed and the counter was incremented.
    Returns False if the daily cap (per-type or aggregate) is hit — caller reschedules.
    Actions not in ACTION_TYPE_MAP (pure logic, AI, enrichment nodes) always return True.
    """
    action_type = ACTION_TYPE_MAP.get(action)
    if not action_type:
        # Not a LinkedIn-facing action — no rate limit applies
        return True

    try:
        result = supabase.rpc(
            "try_consume_daily_action",
            {"p_account_id": account_id, "p_action_type": action_type}
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
    """
    if not worker_id:
        worker_id = str(uuid.uuid4())
        
    try:
        result = supabase.rpc(
            "try_acquire_account_lock",
            {
                "p_account_id": account_id,
                "p_duration_seconds": lock_duration_seconds,
                "p_worker_id": worker_id
            }
        ).execute()
        return bool(result.data)
    except Exception as e:
        logger.error(f"[Orchestrator] Session lock RPC failed for {account_id}. Refusing to proceed (fail-closed): {e}")
        capture_error(e, context={"service": "elein_orchestrator"})
        return False


def release_session_lock(supabase, account_id: str, worker_id: str):
    """Release the session lock for an account after action completes, checking worker ownership."""
    try:
        supabase.rpc(
            "release_account_lock",
            {
                "p_account_id": account_id,
                "p_worker_id": worker_id
            }
        ).execute()
    except Exception as e:
        capture_error(e, context={"service": "elein_orchestrator"})



def adjust_to_working_hours(dt_utc, tz_str: str):
    import pytz
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC
        
    dt_local = dt_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
    
    if dt_local.weekday() > 4:
        days_ahead = 7 - dt_local.weekday()
        dt_local = dt_local + timedelta(days=days_ahead)
        dt_local = dt_local.replace(hour=9, minute=0, second=0, microsecond=0)
    elif dt_local.hour < 9:
        dt_local = dt_local.replace(hour=9, minute=0, second=0, microsecond=0)
    elif dt_local.hour >= 17:
        if dt_local.weekday() == 4:
            dt_local = dt_local + timedelta(days=3)
        else:
            dt_local = dt_local + timedelta(days=1)
        dt_local = dt_local.replace(hour=9, minute=0, second=0, microsecond=0)
        
    return dt_local.astimezone(pytz.UTC).replace(tzinfo=None)

def is_working_hours(tz_str: str) -> bool:
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC
    now = datetime.now(tz)
    # Mon-Fri (0-4), 9 AM - 5 PM (9 - 16)
    if now.weekday() > 4:
        return False
    if not (9 <= now.hour < 17):
        return False
    return True

def next_working_day_9am(tz_str: str = "UTC") -> datetime:
    """Returns 9am tomorrow local time, converted back to UTC for the DB."""
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC
    now = datetime.now(tz)
    tomorrow = now.date() + timedelta(days=1)
    # If tomorrow is Saturday (5) or Sunday (6), move to Monday
    if tomorrow.weekday() == 5:
        tomorrow += timedelta(days=2)
    elif tomorrow.weekday() == 6:
        tomorrow += timedelta(days=1)
    local_9am = tz.localize(datetime.combine(tomorrow, dt_time(hour=9, minute=0)))
    return local_9am.astimezone(pytz.UTC).replace(tzinfo=None)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class EleInOrchestrator:
    def __init__(self, supabase=None):
        self.supabase = supabase or get_service_client()

    def process_pending_leads(self):
        import time
        from collections import defaultdict
        import concurrent.futures as cf

        try:
            self.supabase.rpc("recover_stale_leases", {"p_timeout_minutes": 5}).execute()
        except Exception as e:
            capture_error(e, context={"service": "elein_orchestrator", "stage": "stale_recovery"})

        campaigns_res = self.supabase.table("campaigns").select("id, metadata").eq("status", "ACTIVE").execute()
        if not campaigns_res.data:
            return []

        active_campaign_ids = []
        for c in campaigns_res.data:
            meta = c.get("metadata") or {}
            mode = meta.get("scheduling_mode", "campaign_timezone")
            if mode == "lead_local_time":
                active_campaign_ids.append(c["id"])
            else:
                tz_str = meta.get("timezone", "UTC")
                if is_working_hours(tz_str):
                    active_campaign_ids.append(c["id"])

        if not active_campaign_ids:
            return []

        leads_to_process = []
        try:
            dequeue_res = self.supabase.rpc("dequeue_due_leads", {"p_batch_size": 50, "p_campaign_ids": active_campaign_ids}).execute()
            
            states = dequeue_res.data or []
            if not states:
                return []
                
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
                
                lead = leads_map.get(enrollment["lead_id"], {})
                from campaigns.backend.services.timezone_utils import resolve_target_timezone, calculate_next_run_at
                import pytz
                
                tz_str = resolve_target_timezone(campaign, lead)
                enforce_working_hours = (campaign.get("metadata") or {}).get("enforce_working_hours", True)
                
                if enforce_working_hours and not is_working_hours(tz_str):
                    next_run = calculate_next_run_at(datetime.utcnow().replace(tzinfo=pytz.UTC), tz_str)
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
                    "attempts":                state.get("attempts", 0),
                    "max_attempts":            state.get("max_attempts", 5),
                    "variables":               state.get("variables", {}),
                                        "lease_token":             state.get("lease_token"),
                    "tz_str":                  tz_str,
                    "enforce_working_hours":   enforce_working_hours,
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
            futures = {executor.submit(_process_single_lead, row): row for row in leads_to_process}
            for future in cf.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    capture_error(e, context={"service": "elein_orchestrator"})
        return results

    def get_incoming_edges(self, edges: list, node_id: str) -> list:
        return [e for e in edges if e.get("target_node_id") == node_id]

    def get_outgoing_edges(self, edges: List[Dict], node_id: str) -> List[Dict]:
        return [e for e in edges if e.get("source_node_id") == node_id]

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
        
        # --- PHASE 7: REPLY DETECTION (Paranoia Layer) ---
        try:
            inbound_msg_res = self.supabase.table("messages").select("id").eq("lead_id", state["opportunity_id"]).eq("direction", "inbound").gt("created_at", state["updated_at"]).limit(1).execute()
            if inbound_msg_res.data:
                logger.info(f"Inbound reply detected for lead {state['opportunity_id']}! Pausing campaign execution.")
                self.update_state(state["id"], current_node_id, "completed", None, lease_token, error_reason="Lead replied (paused)")
                return
        except Exception as e:
            capture_error(e, context={"service": "elein_orchestrator"})
            pass

        if not current_node_id:
            target_ids = {e.get("target_node_id") for e in edges}
            start_nodes = [n for n in nodes if n["id"] not in target_ids]
            if not start_nodes:
                self.mark_error(state["id"], "No start node found in campaign graph", lease_token=lease_token)
                return
            current_node = start_nodes[0]
        else:
            current_node = next((n for n in nodes if n["id"] == current_node_id), None)

        if not current_node:
            self.mark_error(state["id"], f"Node {current_node_id} not found in graph", lease_token=lease_token)
            return

        action = current_node.get("node_type")
        data = current_node.get("config", {})
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
                
            next_node_id = outgoing_edges[0]["target_node_id"]
            self.update_state(state["id"], next_node_id, "pending", next_run, lease_token, variables=state.get("variables"), tz_str=state.get('tz_str', 'UTC'))
            return

        # Live check to prevent ghost execution after Panic Pause
        campaign_check = self.supabase.table("campaigns").select("status").eq("id", state["campaign_id"]).execute()
        if not campaign_check.data or campaign_check.data[0].get("status") != "ACTIVE":
            logger.info(f"Campaign {state['campaign_id']} is no longer ACTIVE. Skipping execution for lead {state['opportunity_id']}.")
            self.update_state(state["id"], current_node_id, "pending", None, lease_token, variables=state.get("variables"), tz_str=state.get("tz_str", "UTC"))
            return

        # Execute
        action_result = self.execute_node_action(
            action, data,
            state["opportunity_id"],
            state.get("account_id"),
            state,
            lease_token,
            current_node["id"]
        )

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
            
        if action_result.get("branch") == "Wait For Reply":
            # The node sent the message, but we must now pause and wait for the inbox sync to route the reply.
            # We set the status to 'waiting_for_reply'. The sync cron will advance it.
            self.update_state(state["id"], current_node["id"], "waiting_for_reply", None, lease_token, tz_str=state.get('tz_str', 'UTC'))
            return

        if action_result.get("status") == "rate_limited":
            # Reschedule to tomorrow 9am in their timezone
            tz_str = state.get("tz_str", "UTC")
            enforce_working_hours = state.get("enforce_working_hours", True)
            self._record_observability(state, current_node, "rate_limited", error_reason="We paused this because your daily limit is reached — automatically resumes tomorrow.")
            self.update_state(state["id"], current_node["id"], "pending", next_working_day_9am(tz_str), lease_token, tz_str=tz_str, enforce_working_hours=enforce_working_hours)
            return

        if action_result.get("status") == "account_disconnected":
            broken_account_id = state.get("account_id")
            logger.warning(f"Account {broken_account_id} is disconnected. Marking as error.")
            if broken_account_id:
                self.supabase.table("accounts").update({"status": "DISCONNECTED"}).eq("id", broken_account_id).execute()
            self._record_observability(state, current_node, "error", error_reason="We paused this because your LinkedIn session expired — please reconnect your account in the Accounts tab.")
            self.update_state(state["id"], current_node_id, "pending", datetime.utcnow(), lease_token, tz_str=state.get('tz_str', 'UTC'), enforce_working_hours=False)
            return


        if action_result.get("status") == "security_challenge":
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
            
        if action_result.get("status") == "skipped":
            # Used when account is locked. Reschedule quickly.
            self.update_state(state["id"], current_node["id"], "pending", datetime.utcnow() + timedelta(seconds=45), lease_token=lease_token)
            return

        if action in ("sequence_end", "mark_converted"):
            self.update_state(state["id"], current_node["id"], "exited", None, lease_token=lease_token)
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
                    parent_id = incoming[0]["source_node_id"]
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
            logger.debug(f"Node {current_node_id} returned branch '{branch_handle}'. Available edges: {[e.get('source_handle', e.get('label', '')) for e in outgoing_edges]}")
            branch_edge = next(
                (e for e in outgoing_edges if e.get("source_handle") == branch_handle), None
            )
            if not branch_edge:
                err_msg = f"Lead {state['opportunity_id']} stuck: node {current_node_id} returned branch '{branch_handle}' but no matching edge found. Marking lead as ERROR."
                logger.error(err_msg)
                self.update_state(state["id"], current_node_id, "error", None, lease_token, error_reason=err_msg, tz_str=state.get('tz_str', 'UTC'))
                return
            next_node_id = branch_edge["target_node_id"]
        elif len(outgoing_edges) == 1:
            next_node_id = outgoing_edges[0]["target_node_id"]
        else:
            self.mark_error(state["id"], f"Node {current_node['id']} has multiple edges but no branch returned", lease_token=lease_token, node_id=current_node_id, tz_str=state.get('tz_str', 'UTC'))
            return

        # Evasion jitter: randomly delay (45-120s) before executing the next node
        jitter = timedelta(seconds=random.randint(45, 120))
        self.update_state(state["id"], next_node_id, "pending", datetime.utcnow() + jitter, lease_token, variables=state.get("variables"), tz_str=state.get('tz_str', 'UTC'))

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
        heartbeat_thread = None
        
        def heartbeat_worker():
            while not heartbeat_event.is_set():
                try:
                    self.supabase.rpc("renew_lead_lease", {
                        "p_state_id": state["id"],
                        "p_lease_token": lease_token,
                        "p_extra_seconds": 300
                    }).execute()
                    if requires_linkedin and chosen_sender_id:
                        self.supabase.rpc("renew_account_lock", {
                            "p_account_id": chosen_sender_id,
                            "p_worker_id": worker_id,
                            "p_extra_seconds": 300
                        }).execute()
                except Exception:
                    pass
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
                    "id, workspace_id, status, status_changed_at, proxy_id, session_cookies_encrypted, proxies(protocol, host, port, username)"
                ).eq("id", chosen_sender_id).execute()
                account_row = acc_res.data[0] if acc_res.data else None
                
                if not account_row:
                    return {"status": "error", "error": f"Sender {chosen_sender_id} not found"}
                    
                if account_row.get("status") in ("NEEDS_REVIEW", "DISABLED", "SUSPENDED", "MANUAL_MODE"):
                    # --- 48h Static Allocation Failover ---
                    status_changed_at_str = account_row.get("status_changed_at")
                    is_stale_unhealthy = False
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
                    
                    if is_stale_unhealthy and "enrollment_id" in state:
                        # Attempt reassignment
                        enroll_res = self.supabase.table("campaign_enrollments").select("campaign_id").eq("id", state["enrollment_id"]).execute()
                        if enroll_res.data:
                            campaign_id = enroll_res.data[0]["campaign_id"]
                            # Find healthy backup account
                            backups_res = self.supabase.table("campaign_accounts").select(
                                "account_id, accounts!inner(status)"
                            ).eq("campaign_id", campaign_id).eq("accounts.status", "ACTIVE").neq("account_id", chosen_sender_id).limit(1).execute()
                            
                            if backups_res.data:
                                new_account_id = backups_res.data[0]["account_id"]
                                self.supabase.table("campaign_enrollments").update({"account_id": new_account_id}).eq("id", state["enrollment_id"]).execute()
                                self._record_observability(state, {"id": current_node_id}, "rate_limited", error_reason=f"Account {chosen_sender_id} was unhealthy for >48h. Automatically reassigned lead to fallback account {new_account_id}.")
                                return {"status": "rate_limited"}
                                
                    # Fallback to existing stall behavior
                    # Handled by process_lead as a 24h backoff without incrementing attempt
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
                            rpc_res = self.supabase.rpc("get_decrypted_account_payload", {"p_secret_id": cookie_secret_ref}).execute()
                            if rpc_res.data:
                                dek_bytes = base64.b64decode(rpc_res.data)
                        except Exception as e:
                            capture_error(e, context={"service": "elein_orchestrator"})
                    
                    try:
                        _raw = account_row["session_cookies_encrypted"]
                        _raw_bytes = _raw if isinstance(_raw, (bytes, bytearray)) else _raw.encode("utf-8")
                        cookies_bytes = crypto.decrypt_bytes(_raw_bytes, dek=dek_bytes)
                        cookies = cookies_bytes.decode("utf-8")
                        proxy_url = _build_proxy_url(account_row)
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
            
            # --- 4. Quota Gate ---
            if requires_linkedin:
                action_type = ACTION_TYPE_MAP.get(action)
                if action_type:
                    quota_ok = self.supabase.rpc("try_consume_daily_action", {
                        "p_account_id": chosen_sender_id,
                        "p_action_type": action_type
                    }).execute()
                    if not quota_ok.data:
                        logger.warning(f"Account {chosen_sender_id} reached limit for {action_type}.")
                        if idemp_key:
                            self.supabase.table("campaign_node_executions").update({
                                "status": "failed",
                                "error_code": "RATE_LIMITED"
                            }).eq("idempotency_key", idemp_key).execute()
                        return {"status": "rate_limited"}

            # --- 5. Execute Action ---
            from campaigns.backend.services.elein_executor import EleInNodeExecutor
            executor = EleInNodeExecutor(worker)
            res = executor.execute(action, resolved_data, linkedin_url)
            
            # Coerce unhandled statuses to error so process_lead doesn't silently advance the graph
            if res.get("status") not in ("success", "waiting", "rate_limited", "account_disconnected", "security_challenge", "error", "skipped", "suppressed"):
                res = {"status": "error", "error": f"DEFINITIVE_EXTERNAL_FAILURE: Unhandled executor status '{res.get('status')}'"}
            
            # --- 6. Durable Result Update ---
            if requires_linkedin and chosen_sender_id:
                if res.get("status") == "account_disconnected":
                    self.supabase.table("accounts").update({"status": "DISCONNECTED"}).eq("id", chosen_sender_id).execute()
                    if idemp_key:
                        self.supabase.table("campaign_node_executions").update({
                            "status": "failed",
                            "error_code": "ACCOUNT_DISCONNECTED"
                        }).eq("idempotency_key", idemp_key).execute()
                    return {"status": "account_disconnected"}
                    
                elif res.get("status") == "security_challenge":
                    self.supabase.table("accounts").update({"status": "SUSPENDED"}).eq("id", chosen_sender_id).execute()
                    if idemp_key:
                        self.supabase.table("campaign_node_executions").update({
                            "status": "failed",
                            "error_code": "SECURITY_CHALLENGE"
                        }).eq("idempotency_key", idemp_key).execute()
                    return {"status": "security_challenge"}
            
            if requires_idempotency and idemp_key:
                exec_status = "success" if res.get("status") == "success" else "failed"
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
                    "error": res.get("error")  # included for failure diagnostics
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

    def update_state(self, state_id: str, node_id: str, status: str, next_run_at: Optional[datetime], lease_token: str, error_reason: str = None, attempts: int = None, variables: dict = None, tz_str: str = "UTC", enforce_working_hours: bool = True):
        if next_run_at and enforce_working_hours:
            next_run_at = adjust_to_working_hours(next_run_at, tz_str)
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
            capture_error(e, context={"service": "elein_orchestrator"})

    def mark_error(self, state_id: str, error_msg: str, attempts: int = 0, max_attempts: int = 5, hard_error: bool = False, lease_token: str = None, node_id: str = None, tz_str: str = "UTC", enforce_working_hours: bool = True):
        logger.error(f"Lead state {state_id} errored: {error_msg} (Attempt {attempts + 1}/{max_attempts})")
        new_attempts = max_attempts if hard_error else attempts + 1
        
        if new_attempts >= max_attempts:
            # Exhausted retries -> hard error
            self.update_state(state_id, node_id, "error", None, lease_token, error_reason=error_msg, attempts=new_attempts)
        else:
            # Exponential backoff (e.g. 15m, 1h, 4h, etc) -> back to pending
            backoff_minutes = 15 * (4 ** attempts)
            next_run = (datetime.utcnow() + timedelta(minutes=backoff_minutes))
            self.update_state(state_id, node_id, "pending", next_run, lease_token, error_reason=error_msg, attempts=new_attempts, tz_str=tz_str, enforce_working_hours=enforce_working_hours)


def _build_proxy_url(account_row: dict):
    p = account_row.get("proxies")
    if not p:
        return None
    if p.get("username"):
        return f"{p['protocol']}://{p['username']}@{p['host']}:{p['port']}"
    return f"{p['protocol']}://{p['host']}:{p['port']}"
