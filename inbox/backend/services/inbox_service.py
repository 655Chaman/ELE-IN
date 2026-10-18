import uuid
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_sync_locks_mutex = threading.Lock()
_account_sync_locks: Dict[str, threading.Lock] = {}

def _get_account_sync_lock(workspace_id: str, account_id: str) -> threading.Lock:
    key = f"{workspace_id}:{account_id}"
    with _sync_locks_mutex:
        if key not in _account_sync_locks:
            _account_sync_locks[key] = threading.Lock()
        return _account_sync_locks[key]

ACTIVE_REPLY_STATUSES = [
    "waiting_for_reply",
    "pending",
    "running",
    "processing",
    "paused",
]

# Must include 'pending' and 'waiting_for_reply' to associate inbound replies to active nodes
REPLY_ASSOCIATION_STATUSES = [
    "waiting_for_reply",
    "pending",
    "running",
    "processing",
    "paused",
    "completed",
]


import re

def sanitize_ai_draft(draft: Optional[str], lead_name: Optional[str] = None) -> Optional[str]:
    """
    Paranoia Layer 2 (Human Paranoia & Prompt Leak Defense):
    Cleans and safeguards AI-generated drafts before storing or presenting in approval queue / inbox.
    - Strips meta prefixes (e.g. 'AI:', 'Draft:', 'Reply:', 'Response:')
    - Strips quotes and markdown code blocks
    - Detects and neutralizes prompt leakage ('as an ai language model', 'system prompt', etc.)
    - Bounds length to max 2000 characters
    """
    if not draft or not isinstance(draft, str):
        return None
    s = draft.strip()
    if not s:
        return None

    # 1. Strip surrounding markdown code blocks or quotes
    if (s.startswith("```") and s.endswith("```")) or (s.startswith("`") and s.endswith("`")):
        s = s.strip("`").strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()

    # 2. Strip standard model prefixes
    prefix_pattern = r'^(ai|assistant|draft|response|reply|output|suggested reply|message):\s*'
    s = re.sub(prefix_pattern, '', s, flags=re.IGNORECASE).strip()

    # 3. Detect and neutralize Prompt Leaks / Internal instructions
    leak_markers = [
        "as an ai language model",
        "as an ai,",
        "i am an ai",
        "system prompt",
        "system instructions",
        "internal instructions",
        "internal guidelines",
        "here is a draft reply:",
        "here is a proposed response:",
        "here is what you should say:",
        "sure! here is",
        "sure, here is",
        "certainly! here is",
        "certainly, here is",
        "i cannot fulfill this request",
    ]
    s_lower = s.lower()
    for marker in leak_markers:
        if marker in s_lower:
            idx = s_lower.find(marker)
            if idx < 60:
                after_marker = s[idx + len(marker):].strip()
                if after_marker.startswith(":") or after_marker.startswith("-"):
                    after_marker = after_marker[1:].strip()
                if len(after_marker) > 10:
                    s = after_marker
                    s_lower = s.lower()
                else:
                    first = (lead_name or "").split()[0] if lead_name else "there"
                    return f"Hi {first}, thanks for your note! Would you be open to a brief chat later this week to connect?"
            else:
                first = (lead_name or "").split()[0] if lead_name else "there"
                return f"Hi {first}, thanks for your note! Would you be open to a brief chat later this week to connect?"

    # 4. Length Bounds
    if len(s) > 2000:
        s = s[:1997] + "..."
    return s


def resolve_inbound_lead_and_campaign_context(
    supabase: Any,
    workspace_id: str,
    account_id: Optional[str],
    message: Dict[str, Any]
) -> Dict[str, Optional[str]]:
    """
    Resolves the lead_id, node_id, enrollment_id, and campaign_id for an inbound message.
    Queries campaign_execution_states filtering by REPLY_ASSOCIATION_STATUSES (including
    'pending' and 'waiting_for_reply'). Active states take precedence over completed states.
    """
    lead_id = message.get("lead_id")
    enrollment_id = message.get("enrollment_id")
    node_id = message.get("node_id")
    campaign_id = message.get("campaign_id")

    # 0. If enrollment_id is provided directly but lead_id is missing, look up enrollment
    if not lead_id and enrollment_id:
        try:
            enr_res = supabase.table("campaign_enrollments").select("lead_id, campaign_id").eq("id", enrollment_id).limit(1).execute()
            if enr_res.data:
                lead_id = enr_res.data[0].get("lead_id")
                if not campaign_id:
                    campaign_id = enr_res.data[0].get("campaign_id")
        except Exception as e:
            logger.warning(f"Error resolving lead_id from enrollment_id: {e}")

    # 1. First try to get lead_id from previous messages in thread
    if not lead_id and account_id and message.get("sender_name"):
        try:
            msg_res = supabase.table("messages").select("lead_id").eq("account_id", account_id).eq("sender_name", message["sender_name"]).not_.is_("lead_id", "null").limit(1).execute()
            if msg_res.data and msg_res.data[0].get("lead_id"):
                lead_id = msg_res.data[0]["lead_id"]
        except Exception as e:
            logger.warning(f"Error resolving lead_id from thread with account_id: {e}")

    if not lead_id and workspace_id and message.get("sender_name"):
        try:
            msg_res = supabase.table("messages").select("lead_id").eq("workspace_id", workspace_id).eq("sender_name", message["sender_name"]).not_.is_("lead_id", "null").limit(1).execute()
            if msg_res.data and msg_res.data[0].get("lead_id"):
                lead_id = msg_res.data[0]["lead_id"]
        except Exception as e:
            logger.warning(f"Error resolving lead_id from thread with workspace_id: {e}")

    # 2. Fallback to profile_url / linkedin_url (Strictly Workspace-Scoped)
    profile_url = message.get("profile_url") or message.get("linkedin_url")
    if not lead_id and profile_url:
        try:
            from leads.backend.services.data_hygiene import DataHygieneService
            norm_url = DataHygieneService.normalize_linkedin_url(profile_url) or profile_url
            
            # Query strictly scoped to workspace_id using canonical and raw URL
            lead_q = supabase.table("leads").select("id").eq("workspace_id", workspace_id)
            if norm_url != profile_url:
                lead_direct = lead_q.or_(f"linkedin_url.eq.{norm_url},linkedin_url.eq.{profile_url}").limit(1).execute()
            else:
                lead_direct = lead_q.eq("linkedin_url", norm_url).limit(1).execute()

            if lead_direct.data:
                lead_id = lead_direct.data[0]["id"]
            # Paranoia Layer 1: Under no circumstances resolve across foreign workspaces!
        except Exception as e:
            logger.warning(f"Error resolving lead_id from profile_url: {e}")

    # Removed brittle sender_name fallback. Matching must rely on thread context or deterministic profile_url / URN.

    if lead_id:
        try:
            enroll_res = supabase.table("campaign_enrollments").select("id, campaign_id").eq("workspace_id", workspace_id).eq("lead_id", lead_id).execute()
            if enroll_res.data:
                enroll_ids = [e["id"] for e in enroll_res.data]
                # Filter campaign_execution_states by status including 'pending' and 'waiting_for_reply'
                # Prioritize active statuses (waiting_for_reply, pending, etc.) over completed
                state_res = supabase.table("campaign_execution_states").select("current_node_id, enrollment_id").in_("enrollment_id", enroll_ids).in_("status", ACTIVE_REPLY_STATUSES).order("updated_at", desc=True).limit(1).execute()
                if not state_res.data:
                    state_res = supabase.table("campaign_execution_states").select("current_node_id, enrollment_id").in_("enrollment_id", enroll_ids).in_("status", REPLY_ASSOCIATION_STATUSES).order("updated_at", desc=True).limit(1).execute()

                if state_res.data:
                    matched_state = state_res.data[0]
                    matched_node_id = matched_state.get("current_node_id")
                    matched_enrollment_id = matched_state.get("enrollment_id")
                    if matched_node_id:
                        node_id = matched_node_id
                    if matched_enrollment_id:
                        enrollment_id = matched_enrollment_id
                        enr_match = next((e for e in enroll_res.data if e["id"] == enrollment_id), None)
                        if enr_match and enr_match.get("campaign_id"):
                            campaign_id = enr_match["campaign_id"]

                if not enrollment_id and len(enroll_ids) == 1:
                    # Fallback to the single enrollment id if only one exists
                    enrollment_id = enroll_ids[0]
                    campaign_id = enroll_res.data[0].get("campaign_id")
        except Exception as e:
            logger.warning(f"Error resolving campaign node and enrollment for lead {lead_id}: {e}")

    return {
        "lead_id": lead_id,
        "node_id": node_id,
        "enrollment_id": enrollment_id,
        "campaign_id": campaign_id,
    }



import json

def sync_inbox_messages(supabase, workspace_id: str, account_id: str, messages: list):
    """
    Paranoia Layer 2: Abstract raw DB operations to prevent N+1 loop regressions.
    Synchronizes messages, handles approval queue for intents, and advances waiting_for_reply states.
    """
    with _get_account_sync_lock(workspace_id, account_id):
        if not messages:
            return {"new_saved": 0, "updated": 0, "queued": 0}
            
        saved = 0
        updated = 0
        queued = 0
        
        # Layer 1: chunking to prevent Supabase payload limits
        CHUNK_SIZE = 500
        
        for i in range(0, len(messages), CHUNK_SIZE):
            chunk = messages[i:i + CHUNK_SIZE]
            
            # Layer 0: bulk fetch to check existence
            message_texts = list(set(m["message_text"] for m in chunk))
            existing_res = supabase.table("messages").select("id, sender_name, message_text, direction, thread_url").eq("account_id", account_id).in_("message_text", message_texts).execute()
            existing_records = existing_res.data if existing_res.data else []
            
            existing_map = {}
            for r in existing_records:
                key = (r.get("sender_name"), r.get("message_text"), r.get("direction"), r.get("thread_url") or "")
                existing_map[key] = r["id"]
                
            upsert_payload = []
            seen_in_chunk = {}
            to_enqueue = []
            lead_ids_to_advance = set()
            
            for m in chunk:
                raw_text = m.get("message_text")
                if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
                    continue
                clean_text = raw_text.strip()[:10000]
                clean_sender = (m.get("sender_name") or "Unknown").strip()
                clean_thread_url = (m.get("thread_url") or "").strip()
                direction = m.get("direction") or "inbound"
                m["message_text"] = clean_text
                m["sender_name"] = clean_sender
                m["thread_url"] = clean_thread_url

                key = (clean_sender, clean_text, direction, clean_thread_url)
                if key in seen_in_chunk:
                    continue
                    
                is_existing = key in existing_map
                hash_seed = f"{workspace_id}:{account_id}:{clean_sender}:{clean_text}:{direction}:{clean_thread_url}"
                msg_id = m.get("id") or (existing_map[key] if is_existing else str(uuid.uuid5(uuid.NAMESPACE_URL, hash_seed)))
                m["id"] = msg_id
                
                record = {
                    "id": msg_id,
                    "workspace_id": workspace_id,
                    "account_id": account_id,
                    "sender_name": clean_sender,
                    "message_text": clean_text,
                    "direction": direction,
                }
                if clean_thread_url:
                    record["thread_url"] = clean_thread_url
                
                # Resolve lead_id, node_id, enrollment_id for inbound messages
                if m.get("direction") == "inbound":
                    ctx = resolve_inbound_lead_and_campaign_context(supabase, workspace_id, account_id, m)
                    if ctx.get("lead_id"):
                        record["lead_id"] = ctx["lead_id"]
                        m["lead_id"] = ctx["lead_id"]
                        # Only queue leads to advance if this is a NEW inbound message (not historical/existing replay)
                        if not is_existing:
                            lead_ids_to_advance.add(ctx["lead_id"])
                    if ctx.get("node_id"):
                        record["node_id"] = ctx["node_id"]
                        m["node_id"] = ctx["node_id"]
                    if ctx.get("enrollment_id"):
                        record["enrollment_id"] = ctx["enrollment_id"]
                        m["enrollment_id"] = ctx["enrollment_id"]
                    if ctx.get("campaign_id"):
                        record["campaign_id"] = ctx["campaign_id"]
                        m["campaign_id"] = ctx["campaign_id"]

                if m.get("direction") == "inbound":
                    from inbox.backend.services.sentiment_classifier import (
                        classify_inbound_sentiment_and_intent,
                        apply_inbound_sentiment_actions,
                    )
                    sender_email = m.get("sender_email") or m.get("from_address") or m.get("email")
                    classification = classify_inbound_sentiment_and_intent(
                        clean_text,
                        subject=m.get("subject"),
                        referring_email=sender_email,
                    )
                    m["intent"] = m.get("intent") or classification.get("intent")
                    m["intent_confidence"] = m.get("intent_confidence") or classification.get("confidence")
                    record["intent"] = m["intent"]
                    record["intent_confidence"] = m["intent_confidence"]

                    # Only execute sentiment side-effects (pausing campaigns, creating outbox notifications, setting responded status)
                    # for NEW messages, NOT for existing/re-synced historical messages!
                    if not is_existing and record.get("lead_id"):
                        try:
                            apply_inbound_sentiment_actions(
                                supabase,
                                workspace_id,
                                record["lead_id"],
                                classification,
                                campaign_id=record.get("campaign_id"),
                                text=clean_text,
                            )
                        except Exception as act_err:
                            logger.debug(f"Could not apply inbound sentiment actions: {act_err}")

                    # Real-time alert dispatch for inbound prospect reply (0s Realtime push + audio + outbox)
                    if not is_existing:
                        try:
                            from core.backend.services.notification_service import dispatch_notification
                            sender_display = m.get("sender_name") or "Prospect"
                            snippet = clean_text[:120] + ("..." if len(clean_text) > 120 else "")
                            lead_ref = record.get("lead_id")
                            notif_link = f"/elein/inbox?lead_id={lead_ref}" if lead_ref else "/elein/inbox"
                            msg_key = str(record.get("id") or m.get("id") or f"{sender_display}:{clean_text[:40]}")

                            dispatch_notification(
                                svc=supabase,
                                workspace_id=workspace_id,
                                event_type="lead_replied_instant",
                                payload={
                                    "title": f"{sender_display} replied",
                                    "body": snippet or "A lead has responded to your outreach sequence.",
                                    "link": notif_link,
                                    "lead_id": lead_ref,
                                    "campaign_id": record.get("campaign_id"),
                                    "intent": record.get("intent"),
                                    "account_id": account_id,
                                    "unique_key": msg_key
                                }
                            )
                        except Exception as notif_err:
                            logger.debug(f"Could not dispatch inbound reply notification: {notif_err}")

                    # Horizon 31: Closed-loop Thompson Sampling Bandit feedback on new inbound replies
                    bandit_var_id = m.get("bandit_variant_id") or (m.get("variables") or {}).get("_last_bandit_variant_id")
                    if not is_existing and bandit_var_id:
                        intent_to_bandit_outcome = {
                            "meeting_requested": "meeting_booked",
                            "positive_interest": "positive_reply",
                            "referral_forwarded": "positive_reply",
                            "objection": "objection",
                            "not_interested": "unsubscribe",
                        }
                        bandit_outcome = intent_to_bandit_outcome.get(str(m.get("intent") or ""), None)
                        if bandit_outcome:
                            try:
                                from campaigns.backend.services.bandit_service import record_variant_feedback
                                fb_res = record_variant_feedback(
                                    variant_id=str(bandit_var_id),
                                    outcome=bandit_outcome,
                                    workspace_id=workspace_id,
                                    supabase=supabase,
                                    auto_heal=True,
                                )
                                m["bandit_feedback"] = fb_res
                            except Exception as bf_err:
                                logger.debug(f"Could not record bandit feedback for {bandit_var_id}: {bf_err}")
                else:
                    if "intent" in m:
                        record["intent"] = m["intent"]
                    if "intent_confidence" in m:
                        record["intent_confidence"] = m["intent_confidence"]
                    
                upsert_payload.append(record)
                seen_in_chunk[key] = True
                
                if is_existing:
                    updated += 1
                else:
                    saved += 1
                    intent = m.get("intent", "unknown")
                    if m.get("direction") == "inbound" and intent not in ("not_interested", "negative", "unknown"):
                        to_enqueue.append(m)
                    
            # Bulk Upsert
            if upsert_payload:
                try:
                    supabase.table("messages").upsert(upsert_payload).execute()
                except Exception as e:
                    logger.error(f"Error bulk upserting messages: {e}")
                
            # Bulk handle approval queue
            if to_enqueue:
                try:
                    # Create composite keys to prevent name collisions (e.g. two John Smiths)
                    keys = list(set(f"{m.get('sender_name')}_{m.get('lead_id', 'unknown')}_{m.get('thread_url') or ''}" for m in to_enqueue))
                    sender_names = list(set(m.get("sender_name") for m in to_enqueue if m.get("sender_name")))[:100]
                    
                    # We pull all pending queues for these sender_names, then filter by lead_id & thread_url in memory
                    q_res = supabase.table("approval_queue").select("sender_name, lead_id, thread_url").eq("workspace_id", workspace_id).eq("status", "pending").in_("sender_name", sender_names).execute()
                    existing_queues = set(f"{r['sender_name']}_{r.get('lead_id', 'unknown')}_{r.get('thread_url') or ''}" for r in (q_res.data or []))
                    
                    # Bulk thread query
                    thread_res = supabase.table("messages").select("direction, message_text, created_at, sender_name, lead_id, thread_url").eq("account_id", account_id).in_("sender_name", sender_names).order("created_at").execute()
                    threads_by_key = {}
                    for r in (thread_res.data or []):
                        k = f"{r['sender_name']}_{r.get('lead_id', 'unknown')}_{r.get('thread_url') or ''}"
                        if k not in threads_by_key:
                            threads_by_key[k] = []
                        threads_by_key[k].append({"direction": r["direction"], "message_text": r["message_text"]})
                    
                    queue_inserts = []

                    for m in to_enqueue:
                        sn = m.get("sender_name")
                        lid = m.get("lead_id", "unknown")
                        t_url = m.get("thread_url") or ""
                        msg_id = m.get("id", "")
                        k = f"{sn}_{lid}_{t_url}"
                        if k not in existing_queues:
                            q_seed = f"queue:{workspace_id}:{account_id}:{sn}:{lid}:{t_url}:{msg_id}"
                            q_item = {
                                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, q_seed)),
                                "workspace_id": workspace_id,
                                "account_id": account_id,
                                "sender_name": sn,
                                "thread_messages_json": json.dumps(threads_by_key.get(k, []) or threads_by_key.get(f"{sn}_{lid}_", [])),
                                "intent": m.get("intent"),
                                "heat_score": 50.0,
                                "status": "pending",
                            }
                            if m.get("thread_url"): q_item["thread_url"] = m["thread_url"]
                            if m.get("lead_id"): q_item["lead_id"] = m["lead_id"]
                            if m.get("node_id"): q_item["node_id"] = m["node_id"]
                            if m.get("enrollment_id"): q_item["enrollment_id"] = m["enrollment_id"]
                            if m.get("campaign_id"): q_item["campaign_id"] = m["campaign_id"]
                            if m.get("ai_draft"): q_item["ai_draft"] = sanitize_ai_draft(m["ai_draft"], sn)
                            queue_inserts.append(q_item)
                            existing_queues.add(k)

                    if queue_inserts:
                        supabase.table("approval_queue").insert(queue_inserts).execute()
                        queued += len(queue_inserts)
                except Exception as e:
                    logger.error(f"Error processing approval queue: {e}")
                    
            # Bulk advance leads stuck in waiting_for_reply
            if lead_ids_to_advance:
                try:
                    enroll_res = supabase.table("campaign_enrollments").select("id").in_("lead_id", list(lead_ids_to_advance)).execute()
                    if enroll_res.data:
                        e_ids = [e["id"] for e in enroll_res.data]
                        now_iso = datetime.now(timezone.utc).isoformat()
                        # Batch update states
                        supabase.table("campaign_execution_states").update({
                            "status": "pending",
                            "next_run_at": now_iso,
                            "lease_token": None,
                            "lease_expires_at": None,
                            "updated_at": now_iso
                        }).in_("enrollment_id", e_ids).eq("status", "waiting_for_reply").execute()
                except Exception as fallback_e:
                    logger.warning(f"Failed to advance reply waiting leads via direct update: {fallback_e}")

                # Paranoia Layer 0 & 1: Cascade LinkedIn reply unsubscribe to outbound email sequencers
                for lid in lead_ids_to_advance:
                    try:
                        l_res = supabase.table("leads").select("email").eq("id", lid).eq("workspace_id", workspace_id).limit(1).execute()
                        if l_res.data and isinstance(l_res.data, list) and len(l_res.data) > 0 and l_res.data[0].get("email"):
                            p_email = l_res.data[0]["email"]
                            from integrations.backend.services.elein_crm_service import unsubscribe_from_smartlead, unsubscribe_from_instantly
                            unsubscribe_from_smartlead(workspace_id, p_email)
                            unsubscribe_from_instantly(workspace_id, p_email)
                    except Exception as c_err:
                        logger.warning(f"Failed cascading LinkedIn reply unsubscribe to email sequencers for lead {lid}: {c_err}")

        return {"new_saved": saved, "updated": updated, "queued": queued}

process_inbox_messages = sync_inbox_messages
bulk_upsert_messages = sync_inbox_messages
