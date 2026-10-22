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


# =============================================================================
# PHASE 37: ADVANCED INBOUND REFERRAL & SNOOZE SERVICE BRIDGES
# =============================================================================
from inbox.backend.services.referral_and_snooze_service import (
    extract_referral_contact,
    detect_company_wide_opt_out,
    calculate_timezone_aware_ooo_snooze,
    process_advanced_inbound_reply,
    ReferralAndSnoozeService,
)


def classify_inbound_sentiment_and_intent(
    text: Optional[str],
    subject: Optional[str] = None,
    reference_date: Optional[datetime] = None,
    lead: Optional[Dict[str, Any]] = None,
    campaign: Optional[Dict[str, Any]] = None,
    referring_email: Optional[str] = None,
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

    # Pre-evaluate company-wide opt-out and referral discovery
    eff_email = referring_email or (lead.get("email") if isinstance(lead, dict) else None)
    comp_opt = detect_company_wide_opt_out(clean_body or clean_subj, email=eff_email)
    ref_contact = extract_referral_contact(clean_body or clean_subj, referring_email=eff_email)

    if not combined:
        return {
            "intent": INTENT_NEUTRAL_QUESTION,
            "confidence": 0.3,
            "sentiment": "neutral",
            "matched_rules": ["empty_message_neutral_fallback"],
            "requires_human_attention": False,
            "auto_action": "none",
            "ooo_details": None,
            "company_wide_opt_out": comp_opt,
            "referral_details": None,
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
        if lead and isinstance(lead, dict):
            try:
                ooo_tz = calculate_timezone_aware_ooo_snooze(
                    lead=lead,
                    campaign=campaign,
                    return_date_str=ooo_info.get("return_date"),
                    reference_date=reference_date,
                )
                ooo_info["timezone_aware_snooze"] = ooo_tz
                ooo_info["snooze_until_iso"] = ooo_tz.get("snooze_until_iso")
            except Exception as tz_err:
                logger.debug(f"[SentimentClassifier] Timezone OOO snooze fallback: {tz_err}")

        return {
            "intent": INTENT_OUT_OF_OFFICE,
            "confidence": 0.95,
            "sentiment": "neutral",
            "matched_rules": matched_rules,
            "requires_human_attention": False,
            "auto_action": "snooze_sequence",
            "ooo_details": ooo_info,
            "ooo_data": ooo_info,
            "company_wide_opt_out": comp_opt,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
        }

    # 2. NOT INTERESTED / UNSUBSCRIBE / PASSIVE-AGGRESSIVE SARCASM / COMPANY-WIDE OPT-OUT CHECK
    if comp_opt.get("is_company_wide"):
        return {
            "intent": INTENT_NOT_INTERESTED,
            "confidence": 0.99,
            "sentiment": "negative",
            "matched_rules": [f"company_wide_opt_out:{comp_opt.get('matched_phrase')}"],
            "requires_human_attention": False,
            "auto_action": "suppress_entire_domain",
            "company_wide_opt_out": comp_opt,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
            "ooo_details": None,
        }

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
            "company_wide_opt_out": comp_opt,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
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
            "company_wide_opt_out": comp_opt,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
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

    if ref_contact.get("has_referral") and ref_contact.get("is_valid_referral"):
        matched_rules.append(f"referral_discovered:{ref_contact.get('referral_email')}")

    if matched_rules:
        ref_conf = ref_contact.get("confidence", 0.88) if ref_contact.get("is_valid_referral") else 0.88
        return {
            "intent": INTENT_WRONG_CONTACT,
            "confidence": max(0.88, ref_conf),
            "sentiment": "neutral",
            "matched_rules": matched_rules,
            "requires_human_attention": True,
            "auto_action": "flag_referral",
            "ooo_details": None,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
            "company_wide_opt_out": comp_opt,
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
            "company_wide_opt_out": comp_opt,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
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
            "company_wide_opt_out": comp_opt,
            "referral_details": ref_contact if ref_contact.get("has_referral") else None,
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
        "company_wide_opt_out": comp_opt,
        "referral_details": ref_contact if ref_contact.get("has_referral") else None,
    }


def snooze_campaign_for_ooo_lead(
    supabase: Optional[Any],
    workspace_id: str,
    lead_id: str,
    snooze_until: Optional[str] = None,
    return_date_str: Optional[str] = None,
    campaign: Optional[Dict[str, Any]] = None,
    campaign_id: Optional[str] = None,
    lead: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2 (Phase 37):
    Autonomous Timezone-Aware OOO Snooze & Reschedule Engine.
    - Fetches recipient lead record to extract location/timezone.
    - Calls calculate_timezone_aware_ooo_snooze(lead, campaign, return_date_str=...)
      so the sequence snoozes until 09:xx AM in the recipient's local timezone with jitter,
      weekend rollover, and [1, 90] day horizon clamping.
    - Sets campaign_execution_states to 'snoozed_ooo' and updates next_run_at.
    - Updates leads table status to 'SNOOZED_OOO' with ooo_return_date metadata.
    """
    if not workspace_id or not lead_id:
        raise ValueError("workspace_id and lead_id are required")

    clean_ws = str(workspace_id).strip()
    clean_lead = str(lead_id).strip()

    # 1. Fetch lead record if not passed in
    lead_rec: Dict[str, Any] = lead if isinstance(lead, dict) else {"id": clean_lead, "workspace_id": clean_ws}
    if supabase and (not lead or not isinstance(lead, dict) or not lead.get("timezone")):
        try:
            l_res = (
                supabase.table("leads")
                .select("*")
                .eq("id", clean_lead)
                .eq("workspace_id", clean_ws)
                .execute()
            )
            l_rows = getattr(l_res, "data", None)
            if isinstance(l_rows, list) and len(l_rows) > 0 and isinstance(l_rows[0], dict):
                lead_rec = l_rows[0]
        except Exception as exc:
            logger.debug(f"[OOOSnooze] Lead fetch notice: {exc}")

    # 2. Fetch campaign if campaign_id is provided and campaign not passed
    campaign_rec: Dict[str, Any] = campaign or {}
    if not campaign_rec and campaign_id and supabase:
        try:
            c_res = (
                supabase.table("campaigns")
                .select("*")
                .eq("id", str(campaign_id).strip())
                .eq("workspace_id", clean_ws)
                .execute()
            )
            c_rows = getattr(c_res, "data", None)
            if isinstance(c_rows, list) and len(c_rows) > 0 and isinstance(c_rows[0], dict):
                campaign_rec = c_rows[0]
        except Exception as exc:
            logger.debug(f"[OOOSnooze] Campaign fetch notice: {exc}")

    # 3. Calculate timezone-aware OOO snooze
    tz_snooze = calculate_timezone_aware_ooo_snooze(
        lead=lead_rec,
        campaign=campaign_rec,
        return_date_str=return_date_str,
    )

    target_snooze_until = snooze_until or tz_snooze.get("snooze_until_iso") or (
        datetime.now(timezone.utc) + timedelta(days=7)
    ).isoformat()
    target_return_date = return_date_str or tz_snooze.get("return_date")

    updates_made = 0
    if supabase:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            # 1. Update leads table
            lead_up = {
                "status": "SNOOZED_OOO",
                "updated_at": now_iso,
            }
            if target_return_date:
                lead_up["ooo_return_date"] = target_return_date
            supabase.table("leads").update(lead_up).eq("id", clean_lead).eq(
                "workspace_id", clean_ws
            ).execute()
        except Exception as exc:
            logger.debug(f"[OOOSnooze] Lead update fallback: {exc}")

        try:
            # 2. Find and snooze active execution states via campaign_enrollments
            enr_res = (
                supabase.table("campaign_enrollments")
                .select("id")
                .eq("workspace_id", clean_ws)
                .eq("lead_id", clean_lead)
                .execute()
            )
            enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict) and e.get("id")]
            if enr_ids:
                states_res = (
                    supabase.table("campaign_execution_states")
                    .select("id, status")
                    .eq("workspace_id", clean_ws)
                    .in_("enrollment_id", enr_ids)
                    .in_("status", ["pending", "waiting_for_reply", "running", "active"])
                    .execute()
                )
                data = getattr(states_res, "data", []) or []
                if isinstance(data, list):
                    for st in data:
                        if isinstance(st, dict):
                            st_id = st.get("id")
                            if st_id:
                                supabase.table("campaign_execution_states").update({
                                    "status": "snoozed_ooo",
                                    "next_run_at": target_snooze_until,
                                    "updated_at": now_iso,
                                }).eq("id", st_id).execute()
                                updates_made += 1
        except Exception as exc:
            logger.debug(f"[OOOSnooze] Execution states snooze fallback: {exc}")

    return {
        "status": "snoozed",
        "lead_id": clean_lead,
        "workspace_id": clean_ws,
        "snoozed_until": target_snooze_until,
        "snooze_until_iso": target_snooze_until,
        "return_date": target_return_date,
        "states_snoozed_count": updates_made,
        "target_timezone": tz_snooze.get("target_timezone"),
        "next_run_local": tz_snooze.get("next_run_local"),
        "timezone_details": tz_snooze,
    }


def apply_inbound_sentiment_actions(
    supabase: Optional[Any],
    workspace_id: str,
    lead_id: str,
    classification: Dict[str, Any],
    campaign_id: Optional[str] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2 (Phase 37): Autonomous Intent Action Dispatcher.
    - POSITIVE_INTEREST / MEETING_REQUESTED: Pauses campaign sequence to stop cold spam, marks lead INTERESTED.
    - NOT_INTERESTED / COMPANY_WIDE_OPT_OUT: Halts sequence, unsubscribes and cascades suppression across corporate domain.
    - OUT_OF_OFFICE: Executes timezone-aware snooze_campaign_for_ooo_lead.
    - REFERRAL_DISCOVERED: Ingests new lead tagged with referral_source_lead_id and dispatches alert notification.
    """
    if not workspace_id or not lead_id:
        raise ValueError("workspace_id and lead_id are required")

    intent = classification.get("intent")
    clean_ws = str(workspace_id).strip()
    clean_lead = str(lead_id).strip()
    inbound_text = text or classification.get("raw_text") or ""
    if not inbound_text:
        ref_det = classification.get("referral_details") or {}
        inbound_text = ref_det.get("raw_snippet") or ""

    action_summary = {"lead_id": clean_lead, "intent": intent, "action_taken": "none"}

    # Fetch lead record for email and metadata
    lead: Dict[str, Any] = {"id": clean_lead, "workspace_id": clean_ws}
    if supabase:
        try:
            l_res = (
                supabase.table("leads")
                .select("*")
                .eq("id", clean_lead)
                .eq("workspace_id", clean_ws)
                .execute()
            )
            l_data = getattr(l_res, "data", None)
            if isinstance(l_data, list) and len(l_data) > 0 and isinstance(l_data[0], dict):
                lead = l_data[0]
        except Exception as exc:
            logger.debug(f"[IntentAction] Lead lookup fallback: {exc}")

    lead_email = lead.get("email")

    # -------------------------------------------------------------------------
    # 1. COMPANY-WIDE DOMAIN OPT-OUT CASCADE
    # -------------------------------------------------------------------------
    comp_opt = classification.get("company_wide_opt_out")
    if not comp_opt or not comp_opt.get("is_company_wide"):
        comp_opt = detect_company_wide_opt_out(inbound_text, email=lead_email)

    if comp_opt.get("is_company_wide") and comp_opt.get("domain"):
        corp_domain = comp_opt["domain"]
        now_iso = datetime.now(timezone.utc).isoformat()
        matched_lead_ids: List[str] = []
        states_halted = 0

        if supabase:
            # 1. Insert into suppression_list (DNC table)
            try:
                supabase.table("suppression_list").insert({
                    "workspace_id": clean_ws,
                    "domain": corp_domain,
                    "value": corp_domain,
                    "reason": "Company-wide prospect opt-out",
                    "created_at": now_iso,
                }).execute()
            except Exception as dnc_err:
                logger.debug(f"[IntentAction] Suppression insert notice: {dnc_err}")

            # 2. Try inserting into workspace_domain_suppressions
            try:
                supabase.table("workspace_domain_suppressions").insert({
                    "workspace_id": clean_ws,
                    "domain": corp_domain,
                    "reason": "Company-wide prospect opt-out",
                    "source_lead_id": clean_lead,
                    "created_at": now_iso,
                }).execute()
            except Exception:
                pass

            # 3. Company-wide cascade across all leads sharing that corporate domain
            try:
                leads_res = (
                    supabase.table("leads")
                    .select("id, email")
                    .eq("workspace_id", clean_ws)
                    .execute()
                )
                all_ws_leads = getattr(leads_res, "data", []) or []
                if isinstance(all_ws_leads, list):
                    for l_row in all_ws_leads:
                        if isinstance(l_row, dict) and l_row.get("id"):
                            em = str(l_row.get("email") or "").strip().lower()
                            if "@" in em and em.rsplit("@", 1)[-1].strip() == corp_domain:
                                matched_lead_ids.append(l_row["id"])

                if not matched_lead_ids and clean_lead:
                    matched_lead_ids = [clean_lead]

                if matched_lead_ids:
                    # Update all matching leads to status="UNSUBSCRIBED"
                    supabase.table("leads").update({
                        "status": "UNSUBSCRIBED",
                        "updated_at": now_iso,
                    }).eq("workspace_id", clean_ws).in_("id", matched_lead_ids).execute()

                    # Update all active execution states for that root domain to status="exited" via campaign_enrollments
                    enr_res = (
                        supabase.table("campaign_enrollments")
                        .select("id")
                        .eq("workspace_id", clean_ws)
                        .in_("lead_id", matched_lead_ids)
                        .execute()
                    )
                    enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict) and e.get("id")]
                    if enr_ids:
                        upd_states = (
                            supabase.table("campaign_execution_states")
                            .update({
                                "status": "exited",
                                "error_reason": "company_wide_domain_unsubscribed",
                                "updated_at": now_iso,
                            })
                            .eq("workspace_id", clean_ws)
                            .in_("enrollment_id", enr_ids)
                            .in_("status", [
                                "pending", "waiting_for_reply", "running", "active", "snoozed_ooo", "awaiting_approval", "paused"
                            ])
                            .execute()
                        )
                        states_halted = len(getattr(upd_states, "data", []) or enr_ids)
            except Exception as cascade_err:
                logger.debug(f"[IntentAction] Cascade error: {cascade_err}")

        return {
            "lead_id": clean_lead,
            "intent": INTENT_NOT_INTERESTED,
            "action_taken": "company_wide_domain_suppressed",
            "domain": corp_domain,
            "company_wide_opt_out": comp_opt,
            "cascaded_leads_count": len(matched_lead_ids),
            "states_halted_count": states_halted,
        }

    # -------------------------------------------------------------------------
    # 2. REFERRAL CONTACT DISCOVERY & AUTO-INGESTION
    # -------------------------------------------------------------------------
    ref_details = classification.get("referral_details")
    if not ref_details and (intent == INTENT_WRONG_CONTACT or any(p in inbound_text.lower() for p in ["reach out to", "speak with", "talk to", "contact", "email", "try"])):
        try:
            ref_details = extract_referral_contact(inbound_text, referring_email=lead_email)
        except Exception as ref_exc:
            logger.debug(f"[IntentAction] Referral extraction fallback: {ref_exc}")

    new_lead_id = None
    existing_id = None
    if ref_details and ref_details.get("has_referral") and ref_details.get("is_valid_referral"):
        ref_email = ref_details.get("referral_email")
        if ref_email and supabase:
            adv_res = process_advanced_inbound_reply(
                supabase=supabase,
                workspace_id=clean_ws,
                lead_id=clean_lead,
                text=ref_details.get("raw_snippet") or inbound_text,
                campaign_id=campaign_id,
            )
            new_lead_id = adv_res.get("new_lead_id")
            for act in adv_res.get("actions_taken", []):
                if act.startswith("referral_already_exists:"):
                    existing_id = act.split(":", 1)[1]

            # Dispatch alert notification: "New Referral Discovered: {referral_email} from {lead.get('email')}"
            try:
                from core.backend.services.notification_service import dispatch_notification
                referring_disp = lead_email or "prospect"
                notif_title = f"New Referral Discovered: {ref_email} from {referring_disp}"
                dispatch_notification(
                    svc=supabase,
                    workspace_id=clean_ws,
                    event_type="new_referral_discovered",
                    payload={
                        "title": notif_title,
                        "body": notif_title,
                        "referral_email": ref_email,
                        "referring_email": referring_disp,
                        "referral_source_lead_id": clean_lead,
                        "new_lead_id": new_lead_id or existing_id,
                        "campaign_id": campaign_id,
                    }
                )
            except Exception as notif_err:
                logger.debug(f"[IntentAction] Notification dispatch fallback: {notif_err}")

        if intent == INTENT_WRONG_CONTACT:
            return {
                "lead_id": clean_lead,
                "intent": INTENT_WRONG_CONTACT,
                "action_taken": "referral_created_and_alerted",
                "referral_details": ref_details,
                "new_lead_id": new_lead_id or existing_id,
            }

    # -------------------------------------------------------------------------
    # 3. EXISTING INTENT ROUTING
    # -------------------------------------------------------------------------
    if intent in (INTENT_MEETING_REQUESTED, INTENT_POSITIVE_INTEREST):
        if supabase:
            try:
                # Stop ongoing sequence touches for this engaged prospect via campaign_enrollments
                enr_res = (
                    supabase.table("campaign_enrollments")
                    .select("id")
                    .eq("workspace_id", clean_ws)
                    .eq("lead_id", clean_lead)
                    .execute()
                )
                enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict) and e.get("id")]
                if enr_ids:
                    supabase.table("campaign_execution_states").update({
                        "status": "paused",
                        "error_reason": "replied_positive_interest",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("workspace_id", clean_ws).in_("enrollment_id", enr_ids).in_("status", [
                        "pending", "waiting_for_reply", "running", "active"
                    ]).execute()

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
                # Halt sequence immediately and unsubscribe via campaign_enrollments
                enr_res = (
                    supabase.table("campaign_enrollments")
                    .select("id")
                    .eq("workspace_id", clean_ws)
                    .eq("lead_id", clean_lead)
                    .execute()
                )
                enr_ids = [e["id"] for e in (enr_res.data or []) if isinstance(e, dict) and e.get("id")]
                if enr_ids:
                    supabase.table("campaign_execution_states").update({
                        "status": "exited",
                        "error_reason": "prospect_unsubscribed",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("workspace_id", clean_ws).in_("enrollment_id", enr_ids).in_("status", [
                        "pending", "waiting_for_reply", "running", "active", "snoozed_ooo", "awaiting_approval", "paused"
                    ]).execute()

                supabase.table("leads").update({
                    "status": "UNSUBSCRIBED",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", clean_lead).eq("workspace_id", clean_ws).execute()
            except Exception as exc:
                logger.debug(f"[IntentAction] Opt-out update fallback: {exc}")
        action_summary["action_taken"] = "unsubscribed_halted_sequence"

    elif intent == INTENT_OUT_OF_OFFICE:
        ooo_info = classification.get("ooo_details") or extract_ooo_return_date(inbound_text)
        return_date_str = ooo_info.get("return_date")
        snooze_until = ooo_info.get("snooze_until_iso")
        snooze_res = snooze_campaign_for_ooo_lead(
            supabase=supabase,
            workspace_id=clean_ws,
            lead_id=clean_lead,
            snooze_until=snooze_until,
            return_date_str=return_date_str,
            campaign_id=campaign_id,
            lead=lead,
        )
        action_summary["action_taken"] = "snoozed_ooo"
        action_summary["snooze_details"] = snooze_res

    elif intent == INTENT_WRONG_CONTACT:
        action_summary["action_taken"] = "flagged_referral"

    return action_summary

