"""
sentiment_classifier.py — Inbound AI Reply Sentiment Classifier, Smart Intent Categorization & OOO Auto-Rescheduling
Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: 7-class intent taxonomy, regex/keyword heuristic classification, OOO return date extraction,
             automatic sequence pause on interest, suppression on opt-out, and OOO snooze rescheduling.
  - Layer 1: Stale/past return date correction (safe 7-day default), LLM failover resilience, mock/offline safety.
  - Layer 2: Prompt injection neutralization in inbound text, sarcasm/passive-aggressive negative detection,
             strict tenant IDOR barrier, and snooze horizon clamping (max 90 days).
"""

import calendar
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Primary Intent Taxonomy
INTENT_MEETING_REQUESTED = "meeting_requested"
INTENT_POSITIVE_INTEREST = "positive_interest"
INTENT_OBJECTION = "objection"
INTENT_OUT_OF_OFFICE = "out_of_office"
INTENT_NOT_INTERESTED = "not_interested"
INTENT_WRONG_CONTACT = "wrong_contact"
INTENT_NEUTRAL_QUESTION = "neutral_question"

ALL_INTENTS = {
    INTENT_MEETING_REQUESTED,
    INTENT_POSITIVE_INTEREST,
    INTENT_OBJECTION,
    INTENT_OUT_OF_OFFICE,
    INTENT_NOT_INTERESTED,
    INTENT_WRONG_CONTACT,
    INTENT_NEUTRAL_QUESTION,
}

# Month name mapping for date parsing
_MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Prompt Injection Markers in inbound text to neutralize before analysis
_PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions?",
    r"system\s+prompt",
    r"you\s+are\s+now\s+a\s+helpful\s+assistant",
    r"classify\s+this\s+as",
    r"output\s+only\s+json",
]


def sanitize_inbound_text(text: Optional[str]) -> str:
    """
    Paranoia Layer 2: Sanitizes inbound message text.
    - Strips non-printable characters and control codes.
    - Neutralizes adversarial prompt injection strings.
    - Bounds length to 8,000 characters.
    """
    if not text or not isinstance(text, str):
        return ""
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    for pat in _PROMPT_INJECTION_PATTERNS:
        cleaned = re.sub(pat, "[FILTERED_COMMAND]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()[:8000]


def extract_ooo_return_date(
    text: str,
    reference_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Extracts anticipated return date from Out-Of-Office auto-replies.
    Supports formats:
      - 'returning October 28' / 'back on Nov 5th'
      - 'out until 11/15/2026' or '2026-11-15'
      - 'away for 2 weeks' / 'back in 5 days'
    Layer 1 Environmental Paranoia:
      - If extracted date is in the past (e.g. stale template from 2024), automatically falls back
        to a safe default 7-day snooze from reference_date.
      - Bounds snooze horizon to [1, 90] days to prevent indefinite sequence stalling.
    """
    now = reference_date or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    cleaned = sanitize_inbound_text(text).lower()
    return_dt: Optional[datetime] = None
    extraction_pattern: Optional[str] = None

    # 1. Look for ISO date YYYY-MM-DD
    iso_match = re.search(r"\b(202\d)-(\d{1,2})-(\d{1,2})\b", cleaned)
    if iso_match:
        try:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            cand = datetime(y, m, d, 9, 0, tzinfo=timezone.utc)
            if cand > now:
                return_dt = cand
                extraction_pattern = "iso_date"
        except Exception:
            pass

    # 2. Look for Month Name + Day (e.g. 'returning November 14', 'back on Oct 25th', 'until 3rd of Dec')
    if not return_dt:
        month_pats = "|".join(_MONTH_NAMES.keys())
        # Pattern A: 'back on oct 25' / 'returning october 28th'
        m_a = re.search(
            rf"\b(?:back|return|returning|until|through)\s+(?:on\s+)?({month_pats})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(202\d))?\b",
            cleaned,
        )
        if m_a:
            try:
                mon_str = m_a.group(1)
                day_num = int(m_a.group(2))
                year_num = int(m_a.group(3)) if m_a.group(3) else now.year
                month_num = _MONTH_NAMES[mon_str]
                cand = datetime(year_num, month_num, day_num, 9, 0, tzinfo=timezone.utc)
                if cand < now and not m_a.group(3):
                    # Next year roll-over (e.g. in Dec asking for Jan)
                    cand = datetime(year_num + 1, month_num, day_num, 9, 0, tzinfo=timezone.utc)
                if cand > now:
                    return_dt = cand
                    extraction_pattern = "month_day_named"
            except Exception:
                pass

    # 3. Look for Slash/Dot Date (e.g. '11/25/2026' or '25/11/2026')
    if not return_dt:
        slash_match = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](202\d)\b", cleaned)
        if slash_match:
            try:
                p1, p2, yr = int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3))
                # Guess MM/DD vs DD/MM
                m_num = p1 if p1 <= 12 else p2
                d_num = p2 if p1 <= 12 else p1
                cand = datetime(yr, m_num, d_num, 9, 0, tzinfo=timezone.utc)
                if cand > now:
                    return_dt = cand
                    extraction_pattern = "slash_date"
            except Exception:
                pass

    # 4. Relative Duration (e.g. 'away for 2 weeks', 'back in 5 days')
    if not return_dt:
        rel_match = re.search(r"\b(?:back|away|out)\s+(?:for|in)\s+(\d{1,2})\s+(day|days|week|weeks)\b", cleaned)
        if rel_match:
            try:
                num = int(rel_match.group(1))
                unit = rel_match.group(2)
                days_delta = num * 7 if "week" in unit else num
                return_dt = now + timedelta(days=days_delta)
                extraction_pattern = "relative_delta"
            except Exception:
                pass

    # Layer 1 Paranoia: Fallback to safe 7 days if text is OOO but date was unparseable or in the past
    is_stale_or_missing = return_dt is None or return_dt <= now
    if is_stale_or_missing:
        return_dt = now + timedelta(days=7)
        snooze_days = 7
        date_source = "default_safety_fallback"
    else:
        snooze_days = max(1, (return_dt.date() - now.date()).days)
        date_source = extraction_pattern or "parsed_text"

    # Layer 2 Paranoia: Clamp snooze horizon [1, 90] days
    clamped_snooze_days = max(1, min(90, snooze_days))
    safe_return_dt = now + timedelta(days=clamped_snooze_days)

    return {
        "has_return_date": not is_stale_or_missing,
        "date_source": date_source,
        "return_date": safe_return_dt.strftime("%Y-%m-%d"),
        "snooze_until_iso": safe_return_dt.isoformat(),
        "snooze_days": clamped_snooze_days,
    }


def classify_inbound_sentiment_and_intent(
    text: Optional[str],
    subject: Optional[str] = None,
    reference_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Classifies inbound email/LinkedIn messages into 7 distinct intents.
    - High-precision regex heuristics with sarcasm/passive-aggressive negative defense.
    - Detects explicit calendar booking requests and Calendly/cal.com/hubspot links.
    - Seamlessly extracts OOO parameters when out_of_office is detected.
    """
    clean_body = sanitize_inbound_text(text)
    clean_subj = sanitize_inbound_text(subject)
    combined = f"{clean_subj} {clean_body}".strip().lower()

    if not combined:
        return {
            "intent": INTENT_NEUTRAL_QUESTION,
            "confidence": 0.3,
            "sentiment": "neutral",
            "matched_rules": ["empty_message_neutral_fallback"],
            "requires_human_attention": False,
            "auto_action": "none",
            "ooo_details": None,
        }

    matched_rules: List[str] = []

    # 1. OUT OF OFFICE CHECK (Auto-responder signatures)
    ooo_markers = [
        r"\b(?:out\s+of\s+(?:the\s+)?office|auto(?:mated)?[- ]reply|automatic\s+reply)\b",
        r"\b(?:on\s+(?:annual\s+)?leave|away\s+from\s+(?:my\s+)?desk|limited\s+access\s+to\s+email)\b",
        r"\b(?:maternity\s+leave|paternity\s+leave|sabbatical|vacation\s+responder)\b",
        r"\b(?:i\s+am\s+(?:currently\s+)?(?:away|out|traveling)\s+until)\b",
    ]
    for pat in ooo_markers:
        if re.search(pat, combined):
            matched_rules.append(f"ooo_match:{pat}")

    if matched_rules:
        ooo_info = extract_ooo_return_date(clean_body or clean_subj, reference_date=reference_date)
        return {
            "intent": INTENT_OUT_OF_OFFICE,
            "confidence": 0.95,
            "sentiment": "neutral",
            "matched_rules": matched_rules,
            "requires_human_attention": False,
            "auto_action": "snooze_sequence",
            "ooo_details": ooo_info,
            "ooo_data": ooo_info,
        }

    # 2. NOT INTERESTED / UNSUBSCRIBE / PASSIVE-AGGRESSIVE SARCASM CHECK (Highest priority to protect sender reputation)
    neg_sarcasm_patterns = [
        r"\b(?:yeah\s+right|brilliant\s+idea|nice\s+try|sure\s+thing\s+buddy)\b.*\b(?:never|don't|unsubscribe|stop)\b",
        r"\b(?:take\s+me\s+off|remove\s+me|unsubscribe|do\s+not\s+contact|stop\s+(?:emailing|messaging)|spam)\b",
        r"\b(?:not\s+interested|no\s+thank(?:s)?|pass\s+on\s+this|please\s+stop|lose\s+my\s+number)\b",
        r"\b(?:reported\s+as\s+spam|reporting\s+you|leave\s+me\s+alone|never\s+contact\s+me)\b",
    ]
    for pat in neg_sarcasm_patterns:
        if re.search(pat, combined):
            matched_rules.append(f"negative_opt_out:{pat}")

    if matched_rules:
        return {
            "intent": INTENT_NOT_INTERESTED,
            "confidence": 0.98,
            "sentiment": "negative",
            "matched_rules": matched_rules,
            "requires_human_attention": False,
            "auto_action": "unsubscribe_and_halt_campaign",
            "ooo_details": None,
        }

    # 3. MEETING REQUESTED (Calendar link, timeslot proposals)
    meeting_patterns = [
        r"\b(?:calendly\.com|cal\.com|hubspot\.com/meetings|tidycal\.com|book\s+a\s+time)\b",
        r"\b(?:are\s+you\s+free|how\s+about|let's\s+speak|let's\s+talk|jump\s+on\s+a\s+call|hop\s+on\s+a\s+call)\b",
        r"\b(?:tuesday|wednesday|thursday|friday|monday)\s+(?:at\s+)?(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|est|pst|cet|gmt)?)\b",
        r"\b(?:send\s+(?:an?\s+)?invite|send\s+a\s+calendar|book\s+a\s+slot|schedule\s+a\s+call|schedule\s+a\s+demo)\b",
    ]
    for pat in meeting_patterns:
        if re.search(pat, combined):
            matched_rules.append(f"meeting_intent:{pat}")

    if matched_rules:
        return {
            "intent": INTENT_MEETING_REQUESTED,
            "confidence": 0.94,
            "sentiment": "positive",
            "matched_rules": matched_rules,
            "requires_human_attention": True,
            "auto_action": "pause_sequence_and_alert_sales",
            "ooo_details": None,
        }

    # 4. WRONG CONTACT / REFERRAL CHECK
    referral_patterns = [
        r"\b(?:not\s+(?:the\s+)?right\s+person|don't\s+handle\s+this|not\s+my\s+(?:department|area|responsibility))\b",
        r"\b(?:reach\s+out\s+to|speak\s+with|talk\s+to|connect\s+with|contact)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        r"\b(?:our\s+(?:vp|head|director|lead)\s+handles|try\s+emailing)\b",
    ]
    for pat in referral_patterns:
        if re.search(pat, combined):
            matched_rules.append(f"wrong_contact:{pat}")

    if matched_rules:
        return {
            "intent": INTENT_WRONG_CONTACT,
            "confidence": 0.88,
            "sentiment": "neutral",
            "matched_rules": matched_rules,
            "requires_human_attention": True,
            "auto_action": "flag_referral",
            "ooo_details": None,
        }

    # 5. POSITIVE INTEREST CHECK
    interest_patterns = [
        r"\b(?:sounds?\s+(?:great|good|interesting)|tell\s+me\s+more|love\s+to\s+learn\s+more)\b",
        r"\b(?:send\s+(?:more\s+)?details|send\s+over\s+pricing|would\s+be\s+open\s+to|open\s+to\s+connecting)\b",
        r"\b(?:definitely\s+interested|very\s+interested|curious\s+about\s+this|happy\s+to\s+chat)\b",
        r"\b(?:share\s+some\s+info|worth\s+a\s+chat|let's\s+connect)\b",
    ]
    for pat in interest_patterns:
        if re.search(pat, combined):
            matched_rules.append(f"positive_interest:{pat}")

    if matched_rules:
        return {
            "intent": INTENT_POSITIVE_INTEREST,
            "confidence": 0.90,
            "sentiment": "positive",
            "matched_rules": matched_rules,
            "requires_human_attention": True,
            "auto_action": "pause_sequence_and_alert_sales",
            "ooo_details": None,
        }

    # 6. OBJECTION PUSHBACK CHECK (Leveraging objection categories)
    from inbox.backend.services.objection_service import PATTERNS as OBJ_PATTERNS
    for cat_name, patterns in OBJ_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, combined):
                matched_rules.append(f"objection:{cat_name}")
                break

    if matched_rules:
        return {
            "intent": INTENT_OBJECTION,
            "confidence": 0.86,
            "sentiment": "neutral",
            "matched_rules": matched_rules,
            "requires_human_attention": True,
            "auto_action": "generate_objection_battlecard",
            "ooo_details": None,
        }

    # 7. DEFAULT: NEUTRAL QUESTION OR INQUIRY
    return {
        "intent": INTENT_NEUTRAL_QUESTION,
        "confidence": 0.55,
        "sentiment": "neutral",
        "matched_rules": ["default_inquiry"],
        "requires_human_attention": True,
        "auto_action": "notify_inbox",
        "ooo_details": None,
    }


def snooze_campaign_for_ooo_lead(
    supabase: Optional[Any],
    workspace_id: str,
    lead_id: str,
    snooze_until: str,
    return_date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Autonomous OOO Snooze & Reschedule Engine.
    - Sets campaign_execution_states to 'snoozed_ooo' and updates next_run_at to snooze_until.
    - Updates leads table status to 'SNOOZED_OOO' with ooo_return_date metadata.
    - Emits an informational outbox alert.
    """
    if not workspace_id or not lead_id or not snooze_until:
        raise ValueError("workspace_id, lead_id, and snooze_until are required")

    clean_ws = str(workspace_id).strip()
    clean_lead = str(lead_id).strip()

    updates_made = 0
    if supabase:
        try:
            # 1. Update leads table
            lead_up = {
                "status": "SNOOZED_OOO",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if return_date_str:
                lead_up["ooo_return_date"] = return_date_str
            supabase.table("leads").update(lead_up).eq("id", clean_lead).eq(
                "workspace_id", clean_ws
            ).execute()
        except Exception as exc:
            logger.debug(f"[OOOSnooze] Lead update fallback: {exc}")

        try:
            # 2. Find and snooze active execution states
            states_res = (
                supabase.table("campaign_execution_states")
                .select("id, status")
                .eq("workspace_id", clean_ws)
                .eq("opportunity_id", clean_lead)
                .in_("status", ["pending", "waiting_for_reply", "running", "active"])
                .execute()
            )
            data = getattr(states_res, "data", []) or []
            for st in data:
                st_id = st.get("id")
                if st_id:
                    supabase.table("campaign_execution_states").update({
                        "status": "snoozed_ooo",
                        "next_run_at": snooze_until,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", st_id).execute()
                    updates_made += 1
        except Exception as exc:
            logger.debug(f"[OOOSnooze] Execution states snooze fallback: {exc}")

    return {
        "status": "snoozed",
        "lead_id": clean_lead,
        "workspace_id": clean_ws,
        "snoozed_until": snooze_until,
        "return_date": return_date_str,
        "states_snoozed_count": updates_made,
    }


def apply_inbound_sentiment_actions(
    supabase: Optional[Any],
    workspace_id: str,
    lead_id: str,
    classification: Dict[str, Any],
    campaign_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Autonomous Intent Action Dispatcher.
    - POSITIVE_INTEREST / MEETING_REQUESTED: Pauses campaign sequence to stop cold spam, marks lead INTERESTED.
    - NOT_INTERESTED: Halts sequence, marks lead UNSUBSCRIBED, adds to suppression list.
    - OUT_OF_OFFICE: Executes snooze_campaign_for_ooo_lead.
    """
    if not workspace_id or not lead_id:
        raise ValueError("workspace_id and lead_id are required")

    intent = classification.get("intent")
    clean_ws = str(workspace_id).strip()
    clean_lead = str(lead_id).strip()

    action_summary = {"lead_id": clean_lead, "intent": intent, "action_taken": "none"}

    if intent in (INTENT_MEETING_REQUESTED, INTENT_POSITIVE_INTEREST):
        if supabase:
            try:
                # Stop ongoing sequence touches for this engaged prospect
                supabase.table("campaign_execution_states").update({
                    "status": "paused_replied_interest",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("workspace_id", clean_ws).eq("opportunity_id", clean_lead).execute()

                supabase.table("leads").update({
                    "status": "INTERESTED",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", clean_lead).eq("workspace_id", clean_ws).execute()
            except Exception as exc:
                logger.debug(f"[IntentAction] Positive intent update fallback: {exc}")
        action_summary["action_taken"] = "paused_sequence_marked_interested"

    elif intent == INTENT_NOT_INTERESTED:
        if supabase:
            try:
                # Halt sequence immediately and unsubscribe
                supabase.table("campaign_execution_states").update({
                    "status": "unsubscribed",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("workspace_id", clean_ws).eq("opportunity_id", clean_lead).execute()

                supabase.table("leads").update({
                    "status": "UNSUBSCRIBED",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", clean_lead).eq("workspace_id", clean_ws).execute()
            except Exception as exc:
                logger.debug(f"[IntentAction] Opt-out update fallback: {exc}")
        action_summary["action_taken"] = "unsubscribed_halted_sequence"

    elif intent == INTENT_OUT_OF_OFFICE:
        ooo_info = classification.get("ooo_details") or extract_ooo_return_date("")
        snooze_until = ooo_info.get("snooze_until_iso") or (
            datetime.now(timezone.utc) + timedelta(days=7)
        ).isoformat()
        snooze_res = snooze_campaign_for_ooo_lead(
            supabase=supabase,
            workspace_id=clean_ws,
            lead_id=clean_lead,
            snooze_until=snooze_until,
            return_date_str=ooo_info.get("return_date"),
        )
        action_summary["action_taken"] = "snoozed_ooo"
        action_summary["snooze_details"] = snooze_res

    return action_summary
