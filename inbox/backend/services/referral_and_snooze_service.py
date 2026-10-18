"""
referral_and_snooze_service.py — Advanced Inbound Referral Discovery, Working-Hours OOO Rescheduler
& Company-Wide Domain Suppression Engine for Ele-in (Phase 37).

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational):
      * Natural-language referral contact extraction (name, first/last name, email, title/department).
      * Company-wide opt-out detection phrases.
      * Timezone-aware OOO rescheduling targeting the next active morning (09:15 AM local time) with jitter.
      * End-to-end inbound reply action orchestrator creating leads and suppressing domains.
  - Layer 1 (Environmental Failure Analysis):
      * Deliverability Shield verification via EmailShieldService (detecting and blocking pristine spam traps,
        disposable domains, RFC invalid emails).
      * Bounded snooze horizon [1, 90] days to prevent indefinite stalling.
      * Timezone resolution fallbacks (valid IANA timezone validation, safe localization across DST shifts).
      * Retroactive purge across all leads and in-flight campaign executions for company-wide opt-out.
  - Layer 2 (Human Paranoia & Self-Referral Defense):
      * Self-referral blocker: prevents lead from referring their own email address.
      * Webmail protection: prevents accidental company-wide domain suppression of free consumer providers
        (gmail.com, yahoo.com, outlook.com, etc.).
      * Prompt injection neutralization and XSS / control character sanitization on extracted names and snippets.
      * Weekend rollover: when return date is Friday, rolls to Monday morning with jitter, never Saturday/Sunday.
"""

import logging
import re
import uuid
from datetime import datetime, date, time as dt_time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import pytz

from core.backend.services.email_shield_service import (
    EmailShieldService,
    FREE_WEBMAIL_DOMAINS,
)
from leads.backend.services.suppression_service import (
    PUBLIC_FREEMAIL_DOMAINS,
    normalize_suppression_domain,
    retroactive_purge_suppressed_leads,
)
from campaigns.backend.services.timezone_utils import (
    resolve_target_timezone,
    calculate_next_run_with_jitter,
    parse_schedule_config,
    safe_localize,
    is_valid_iana_timezone,
)

logger = logging.getLogger(__name__)

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

# Combined immutable set of all free consumer email domains
ALL_FREE_WEBMAIL_DOMAINS: Set[str] = set(FREE_WEBMAIL_DOMAINS) | set(PUBLIC_FREEMAIL_DOMAINS)

# Company-wide opt-out detection patterns
COMPANY_WIDE_OPT_OUT_PATTERNS = [
    r"remove\s+(?:our\s+)?(?:entire\s+|whole\s+)?(?:company|team|organization|domain)\b",
    r"do\s+not\s+contact\s+(?:anyone|anybody)\s+at\b",
    r"unsubscribe\s+(?:all\s+)?(?:of\s+us|everyone|our\s+domain)\b",
    r"take\s+(?:our\s+whole\s+organization|everyone\s+at(?:\s+[A-Za-z0-9\s.]+?)?)\s+off\b",
    r"take\s+(?:our\s+)?(?:entire\s+|whole\s+)?(?:company|team|organization|domain)\s+off\b",
    r"stop\s+(?:emailing|contacting)\s+(?:anyone|anybody|everyone)\s+(?:at|in)\b",
    r"stop\s+(?:emailing|contacting)\s+(?:our\s+)?(?:entire\s+|whole\s+)?(?:company|team|organization)\b",
    r"block\s+(?:our\s+)?(?:entire\s+|whole\s+)?(?:company|domain)\b",
    r"remove\s+(?:everyone|all\s+of\s+us)\s+at\b",
    r"(?:please\s+)?remove\s+us\s+all\b",
    r"do\s+not\s+email\s+(?:anyone|anybody)\s+else\s+at\b",
]


# =============================================================================
# 1. REFERRAL CONTACT EXTRACTION
# =============================================================================

def extract_referral_contact(
    text: str,
    referring_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Extracts referred colleague's contact details from inbound natural language.

    Layer 0 (Foundational):
      Matches common B2B referral syntax:
        1. Reach out / speak with / talk to / contact [Name] at/on/via [email]
        2. [email] is our / handles / leads [department/title]
        3. [Name] ([email])
        4. Reach out / email / contact [email] directly
      Extracts: referral_email, referral_name, referral_first_name, referral_last_name, referral_title.

    Layer 1 (Environmental Failure Analysis):
      Validates extracted referral_email using EmailShieldService.audit_email_address:
        - Rejects pristine spam traps (is_spam_trap=True).
        - Rejects disposable domains (is_disposable=True).
        - Rejects malformed / RFC invalid syntax.

    Layer 2 (Human Paranoia & Self-Referral Protection):
      - Self-referral blocker: rejects if referral_email.lower() == referring_email.lower().
      - Neutralizes prompt injections and strips control characters.
      - Strips bounding brackets, quotes, and trailing punctuation from email strings.
    """
    clean_text = sanitize_inbound_text(text)
    clean_ref_email = (referring_email or "").strip().lower()

    empty_result = {
        "has_referral": False,
        "is_valid_referral": False,
        "referral_email": None,
        "referral_name": None,
        "referral_first_name": None,
        "referral_last_name": None,
        "referral_title": None,
        "confidence": 0.0,
        "raw_snippet": "",
        "rejection_reason": None,
        "shield_audit": None,
    }

    if not clean_text:
        return empty_result

    raw_name: Optional[str] = None
    raw_email: Optional[str] = None
    raw_title: Optional[str] = None
    raw_snippet: str = ""

    # Pattern 1: Verb + [optional name/role + at/on/via] + [candidate email]
    # Matches:
    # "Please reach out to Sarah Connor at sconnor@cyberdyne.com"
    # "Reach out to our security admin at abuse@target.com"
    # "Please reach out to abuse@target.com"
    # "Speak with Bob at bob@@invalid..com"
    verb = r"(?:(?:try(?:ing)?\s+(?:to\s+)?)?(?:reach(?:ing)?\s+out\s+to|speak(?:ing)?\s+with|talk(?:ing)?\s+to|contact(?:ing)?|email(?:ing)?)|try(?:ing)?)"
    pat1 = re.compile(
        verb + r"\s+(?:([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s+(?:at|on|via)\s+|([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s+|(?:at|on|via)\s+)?([^\s<>\(\),;]+@[^\s<>\(\),;]+)",
        re.IGNORECASE,
    )

    # Pattern 2: [candidate email] + is our / handles / leads + Title
    # E.g. "dmiller@acme.com is our VP of Sales" or "dmiller@acme.com leads infrastructure"
    pat2 = re.compile(
        r"([^\s<>\(\),;]+@[^\s<>\(\),;]+)\s*(?:is\s+our|handles|leads)\s*([A-Za-z\s]+)?",
        re.IGNORECASE,
    )

    # Pattern 3: Name + (Email)
    # E.g. "Jane Doe (jane.doe@enterprise.com)" or "Dave Miller <dmiller@acme.com>"
    pat3 = re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[\(<]([^\s<>\(\),;]+@[^\s<>\(\),;]+)[\)>]",
    )

    # Pattern 5: Loop in / connect with / forward to [Name] at [Email]
    pat5 = re.compile(
        r"(?:referring\s+you\s+to|loop(?:ing)?\s+in|forward(?:ing)?\s+(?:this\s+)?to|connect\s+with)\s+(?:([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s+(?:at|on|via)?\s*)?([^\s<>\(\),;]+@[^\s<>\(\),;]+)",
        re.IGNORECASE,
    )

    # 1. Try Pattern 1
    m1 = pat1.search(clean_text)
    if m1:
        raw_name = (m1.group(1) or m1.group(2) or "").strip() or None
        raw_email = m1.group(3).strip()
        raw_snippet = m1.group(0).strip()
        after_text = clean_text[m1.end():]
        title_m = re.search(
            r"(?:who\s+(?:is\s+(?:our\s+)?|handles|leads)|(?:is\s+(?:our\s+)?|handles|leads))\s*([A-Za-z0-9\s/-]+?)(?:\.|\n|$|,|;)",
            after_text,
            re.IGNORECASE,
        )
        if title_m:
            raw_title = title_m.group(1).strip()
    else:
        # 2. Try Pattern 3, Pattern 5
        m3 = pat3.search(clean_text)
        m5 = pat5.search(clean_text)
        matched = m3 or m5
        if matched:
            raw_name = matched.group(1).strip() if matched.group(1) else None
            raw_email = matched.group(2).strip()
            raw_snippet = matched.group(0).strip()
            after_text = clean_text[matched.end():]
            title_m = re.search(
                r"(?:who\s+(?:is\s+(?:our\s+)?|handles|leads)|(?:is\s+(?:our\s+)?|handles|leads))\s*([A-Za-z0-9\s/-]+?)(?:\.|\n|$|,|;)",
                after_text,
                re.IGNORECASE,
            )
            if title_m:
                raw_title = title_m.group(1).strip()
        else:
            # 3. Try Pattern 2 (Email + Title)
            m2 = pat2.search(clean_text)
            if m2:
                raw_email = m2.group(1).strip()
                raw_title = (m2.group(2) or "").strip()
                raw_snippet = m2.group(0).strip()
                before_text = clean_text[:m2.start()]
                name_m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*$", before_text)
                if name_m:
                    raw_name = name_m.group(1).strip()

    if not raw_email:
        return empty_result

    # Clean raw_name of leading prepositions and check for role description
    if raw_name:
        raw_name = re.sub(
            r"^(?:reach(?:ing)?\s+out\s+to|speak(?:ing)?\s+with|talk(?:ing)?\s+to|contact(?:ing)?|email(?:ing)?|try(?:ing)?|with|to|for|at|on)\s+",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()
        raw_name = re.sub(
            r"^(?:my|our)\s+(?:successor|colleague|partner|manager|teammate|director|lead)\s+",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()
        if raw_name.lower().startswith("our ") or raw_name.lower().startswith("the ") or any(
            role in raw_name.lower() for role in ("security", "admin", "team", "support", "sales", "marketing")
        ):
            if not raw_title:
                raw_title = raw_name
            raw_name = None

    # Layer 2 Sanitization: Clean email string
    raw_email = re.sub(r"^[<\"'\s]+", "", raw_email)
    raw_email = re.sub(r"[\.,;:>\)\"'\s]+$", "", raw_email).strip().lower()

    # Clean extracted name
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None

    if raw_name:
        clean_n = sanitize_inbound_text(raw_name).strip()
        parts = clean_n.split()
        if parts:
            first_name = parts[0].capitalize()
            last_name = " ".join(p.capitalize() for p in parts[1:]) if len(parts) > 1 else None
            full_name = f"{first_name} {last_name}" if last_name else first_name
    elif "@" in raw_email:
        # Fall back to deriving name from email local-part (e.g. john.smith@company.com -> John Smith)
        local_part = raw_email.split("@")[0].split("+")[0]
        if "." in local_part or "_" in local_part or "-" in local_part:
            parts = re.split(r"[._-]", local_part)
            if parts and parts[0].isalpha():
                first_name = parts[0].capitalize()
                if len(parts) > 1 and parts[1].isalpha():
                    last_name = parts[1].capitalize()
                full_name = f"{first_name} {last_name}" if last_name else first_name

    # Clean title
    clean_title: Optional[str] = None
    if raw_title:
        t_cleaned = sanitize_inbound_text(raw_title).strip()
        t_cleaned = re.sub(r"^(?:our|the)\s+", "", t_cleaned, flags=re.IGNORECASE).strip()
        t_cleaned = re.sub(r"[\.,;:!\s]+$", "", t_cleaned).strip()
        if len(t_cleaned) >= 2:
            clean_title = t_cleaned[:80]

    # Layer 1 Paranoia: Deliverability Shield Validation
    audit = EmailShieldService.audit_email_address(raw_email, allow_role_based=True)
    is_valid_referral = True
    rejection_reason: Optional[str] = None

    if not audit.get("valid") or audit.get("classification") == EmailShieldService.EmailClassification.INVALID.value:
        is_valid_referral = False
        rejection_reason = "INVALID_EMAIL_FORMAT"
    elif audit.get("is_spam_trap"):
        is_valid_referral = False
        rejection_reason = audit.get("rejection_reason") or "PRISTINE_SPAM_TRAP_PREFIX"
    elif audit.get("is_disposable"):
        is_valid_referral = False
        rejection_reason = "DISPOSABLE_EMAIL_DOMAIN"

    # Layer 2 Paranoia: Self-Referral Defense
    if is_valid_referral and clean_ref_email and raw_email == clean_ref_email:
        is_valid_referral = False
        rejection_reason = "SELF_REFERRAL_DETECTED"

    # Confidence scoring
    if is_valid_referral:
        if full_name and clean_title:
            confidence = 0.95
        elif full_name:
            confidence = 0.90
        elif clean_title:
            confidence = 0.85
        else:
            confidence = 0.75
    else:
        confidence = 0.20

    return {
        "has_referral": True,
        "is_valid_referral": is_valid_referral,
        "referral_email": raw_email,
        "referral_name": full_name,
        "referral_first_name": first_name,
        "referral_last_name": last_name,
        "referral_title": clean_title,
        "confidence": confidence,
        "raw_snippet": raw_snippet,
        "rejection_reason": rejection_reason,
        "shield_audit": audit,
    }


# =============================================================================
# 2. COMPANY-WIDE DOMAIN SUPPRESSION DETECTION
# =============================================================================

def detect_company_wide_opt_out(
    text: str,
    email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Identifies broad organizational opt-out intent and safeguards free webmail.

    Layer 0 (Foundational):
      Detects organizational opt-out phrases:
        - "remove our entire company / whole team / organization / domain"
        - "do not contact anyone / anybody at"
        - "unsubscribe all of us / everyone / our domain"
        - "take our whole organization / everyone at off"
        - "stop emailing / contacting our company"

    Layer 1 (Environmental):
      Extracts and canonicalizes the company domain using normalize_suppression_domain.

    Layer 2 (Human Paranoia — Webmail Protection):
      Extracts domain from sender email. If domain is a public webmail provider (gmail.com,
      yahoo.com, outlook.com, proton.me, etc.), BLOCKS company-wide domain suppression!
      Returns is_company_wide=False with reason="FREE_WEBMAIL_DOMAIN_CANNOT_BE_COMPANY_SUPPRESSED"
      to physically protect the workspace from blanket-suppressing all consumer leads.
    """
    clean_text = sanitize_inbound_text(text)
    if not clean_text:
        return {
            "is_company_wide": False,
            "domain": None,
            "action": "none",
            "reason": "EMPTY_TEXT",
            "matched_phrase": None,
        }

    matched_phrase: Optional[str] = None
    for pattern in COMPANY_WIDE_OPT_OUT_PATTERNS:
        m = re.search(pattern, clean_text, re.IGNORECASE)
        if m:
            matched_phrase = m.group(0).strip()
            break

    if not matched_phrase:
        return {
            "is_company_wide": False,
            "domain": None,
            "action": "none",
            "reason": "NO_COMPANY_WIDE_PHRASE_DETECTED",
            "matched_phrase": None,
        }

    # Extract target domain
    raw_domain: Optional[str] = None
    if email and isinstance(email, str) and "@" in email:
        raw_domain = email.split("@")[-1].strip().lower()
    else:
        # Attempt domain extraction from text (e.g. "at acme.corp" or "our domain acme.com")
        dom_match = re.search(r"\b(?:at|domain)\s+([a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b", clean_text, re.IGNORECASE)
        if dom_match:
            raw_domain = dom_match.group(1).strip().lower()

    clean_domain = normalize_suppression_domain(raw_domain) if raw_domain else None
    if not clean_domain and raw_domain:
        clean_domain = raw_domain.strip().lower()

    if not clean_domain:
        return {
            "is_company_wide": False,
            "domain": None,
            "action": "none",
            "reason": "MISSING_DOMAIN_FOR_COMPANY_WIDE_SUPPRESSION",
            "matched_phrase": matched_phrase,
        }

    # Paranoia Layer 2: Free Webmail Protection
    is_freemail = (
        clean_domain in ALL_FREE_WEBMAIL_DOMAINS
        or any(clean_domain.endswith("." + d) for d in ALL_FREE_WEBMAIL_DOMAINS)
    )

    if is_freemail:
        logger.warning(
            f"[CompanySuppressionShield] Blocked company-wide suppression for free webmail domain: {clean_domain}"
        )
        return {
            "is_company_wide": False,
            "domain": clean_domain,
            "action": "none",
            "reason": "FREE_WEBMAIL_DOMAIN_CANNOT_BE_COMPANY_SUPPRESSED",
            "matched_phrase": matched_phrase,
        }

    return {
        "is_company_wide": True,
        "domain": clean_domain,
        "action": "suppress_entire_domain",
        "matched_phrase": matched_phrase,
        "reason": "COMPANY_WIDE_OPT_OUT_DETECTED",
    }


# =============================================================================
# 3. TIMEZONE-AWARE OOO RESCHEDULER
# =============================================================================

def calculate_timezone_aware_ooo_snooze(
    lead: Dict[str, Any],
    campaign: Optional[Dict[str, Any]] = None,
    return_date_str: Optional[str] = None,
    reference_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Calculates precise, recipient-timezone-aware OOO snooze target.

    Layer 0 (Foundational):
      - Resolves recipient timezone using timezone_utils.resolve_target_timezone.
      - Targets the morning AFTER the return date at 09:15 AM recipient local time.
      - Uses calculate_next_run_with_jitter to prevent thundering-herd email bursts.

    Layer 1 (Environmental Failure Analysis):
      - Stale/past return date correction: if return date is missing, unparseable, or <= reference_date,
        safely defaults to reference_date + 7 days.
      - Clamps snooze horizon strictly within [1, 90] days to prevent indefinite sequence stalling.

    Layer 2 (Human Paranoia — Weekend Rollover):
      - If return date is Friday (so next morning is Saturday), automatically rolls to Monday morning
        with jitter, NEVER scheduling on Saturday or Sunday (unless weekend_sending is explicitly enabled).
    """
    lead = lead if isinstance(lead, dict) else {}
    campaign = campaign if isinstance(campaign, dict) else {}

    ref_dt = reference_date or datetime.now(timezone.utc)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)

    # 1. Resolve target timezone
    target_tz = resolve_target_timezone(campaign, lead)
    # Prefer lead explicit timezone if campaign default fell back to UTC
    if target_tz == "UTC":
        lead_tz = lead.get("timezone")
        if lead_tz and is_valid_iana_timezone(lead_tz):
            target_tz = lead_tz

    if not is_valid_iana_timezone(target_tz):
        target_tz = "UTC"

    tz = pytz.timezone(target_tz)
    ref_local_date = ref_dt.astimezone(tz).date()

    # 2. Parse return date or safely fall back to +7 days
    parsed_date: Optional[date] = None
    if return_date_str and isinstance(return_date_str, str):
        cleaned_str = return_date_str.strip()
        try:
            parsed_date = datetime.strptime(cleaned_str, "%Y-%m-%d").date()
        except Exception:
            try:
                from inbox.backend.services.sentiment_classifier import extract_ooo_return_date
                extracted = extract_ooo_return_date(cleaned_str, reference_date=ref_dt)
            except Exception:
                extracted = {}
            if extracted.get("has_return_date") and extracted.get("return_date"):
                try:
                    parsed_date = datetime.strptime(extracted["return_date"], "%Y-%m-%d").date()
                except Exception:
                    parsed_date = None

    # Stale/past date correction: must be strictly in the future relative to ref_local_date
    if not parsed_date or parsed_date <= ref_local_date:
        parsed_date = ref_local_date + timedelta(days=7)

    effective_return_date_str = parsed_date.strftime("%Y-%m-%d")

    # 3. Target next working morning after return date (return_date + 1 day at 09:15 AM local time)
    target_morning_date = parsed_date + timedelta(days=1)
    naive_slot = datetime.combine(target_morning_date, dt_time(hour=9, minute=15, second=0, microsecond=0))
    local_base = safe_localize(tz, naive_slot)
    base_utc = local_base.astimezone(pytz.UTC)

    # 4. Campaign schedule & jitter
    schedule = campaign.get("schedule") or (campaign.get("metadata", {}) or {}).get("schedule")
    lead_id_seed = lead.get("id") or lead.get("email")

    next_run_utc = calculate_next_run_with_jitter(
        base_time=base_utc,
        target_tz=target_tz,
        schedule=schedule,
        jitter_range=(10, 30),
        seed_key=str(lead_id_seed or "ooo_reschedule"),
    )

    # 5. Paranoia Layer 1: Snooze horizon clamping [1, 90] days from ref_dt
    min_allowed_utc = ref_dt + timedelta(days=1)
    max_allowed_utc = ref_dt + timedelta(days=90)

    if next_run_utc < min_allowed_utc:
        next_run_utc = calculate_next_run_with_jitter(
            min_allowed_utc,
            target_tz,
            schedule=schedule,
            jitter_range=(10, 30),
            seed_key=str(lead_id_seed or "ooo_reschedule"),
        )
    elif next_run_utc > max_allowed_utc:
        max_naive = (ref_dt.astimezone(tz) + timedelta(days=90)).replace(
            hour=9, minute=15, second=0, microsecond=0
        ).replace(tzinfo=None)
        max_local = safe_localize(tz, max_naive)
        next_run_utc = calculate_next_run_with_jitter(
            max_local.astimezone(pytz.UTC),
            target_tz,
            schedule=schedule,
            jitter_range=(10, 30),
            seed_key=str(lead_id_seed or "ooo_reschedule"),
        )

    # 6. Local representation & Weekend Rollover audit
    next_run_local = next_run_utc.astimezone(tz)
    next_run_local_str = next_run_local.strftime("%Y-%m-%d %H:%M:%S %Z")

    is_weekend_rollover = (
        target_morning_date.weekday() in (5, 6)
        and next_run_local.weekday() not in (5, 6)
    )
    snooze_days = (next_run_local.date() - ref_local_date).days
    if snooze_days > 90:
        target_clamped_date = ref_local_date + timedelta(days=90)
        if target_clamped_date.weekday() == 5:
            target_clamped_date -= timedelta(days=1)
        elif target_clamped_date.weekday() == 6:
            target_clamped_date -= timedelta(days=2)
        max_naive = datetime.combine(target_clamped_date, dt_time(hour=9, minute=15, second=0, microsecond=0))
        local_clamped = safe_localize(tz, max_naive)
        next_run_utc = local_clamped.astimezone(pytz.UTC)
        next_run_local = next_run_utc.astimezone(tz)
        next_run_local_str = next_run_local.strftime("%Y-%m-%d %H:%M:%S %Z")
        snooze_days = max(1, (next_run_local.date() - ref_local_date).days)
    elif snooze_days < 1:
        snooze_days = 1

    return {
        "target_timezone": target_tz,
        "snooze_until_iso": next_run_utc.isoformat(),
        "next_run_local": next_run_local_str,
        "return_date": effective_return_date_str,
        "snooze_days": snooze_days,
        "is_weekend_rollover": is_weekend_rollover,
    }


# =============================================================================
# 4. PROCESS INBOUND ACTIONS ORCHESTRATOR
# =============================================================================

def process_advanced_inbound_reply(
    supabase: Any,
    workspace_id: str,
    lead_id: str,
    text: str,
    subject: Optional[str] = None,
    campaign_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Comprehensive Inbound Action Dispatcher.

    Executes:
      1. Referral Contact Discovery:
         - Extracts referred colleague's contact data.
         - Validates against deliverability spam traps, disposable domains, and self-referrals.
         - If valid and not already in workspace leads, inserts a new Lead with
           referral_source_lead_id=lead_id and status="NEW".
      2. Company-Wide Domain Suppression:
         - Detects domain-wide opt-outs while blocking consumer webmail suppression.
         - Adds corporate domain to workspace suppression lists (suppression_list / workspace_domain_suppressions).
         - Cascades cancellation across all existing leads sharing that domain in the workspace.
      3. Timezone-Aware OOO Snoozing:
         - Detects OOO replies, calculates working-hours return slot with jitter,
           and puts campaign execution states into snoozed_ooo.
    """
    clean_ws = str(workspace_id or "").strip()
    clean_lead = str(lead_id or "").strip()
    clean_text = sanitize_inbound_text(text)
    clean_subj = sanitize_inbound_text(subject)

    summary: Dict[str, Any] = {
        "workspace_id": clean_ws,
        "lead_id": clean_lead,
        "campaign_id": campaign_id,
        "referral": None,
        "company_suppression": None,
        "ooo_snooze": None,
        "actions_taken": [],
    }

    if not clean_ws or not clean_lead:
        logger.warning("[InboundReply] Missing workspace_id or lead_id")
        return summary

    # Load lead record if supabase is available
    lead_data: Dict[str, Any] = {}
    campaign_data: Dict[str, Any] = {}
    lead_email: Optional[str] = None

    if supabase:
        try:
            lead_res = (
                supabase.table("leads")
                .select("*")
                .eq("id", clean_lead)
                .eq("workspace_id", clean_ws)
                .execute()
            )
            rows = getattr(lead_res, "data", []) or []
            if rows and isinstance(rows[0], dict):
                lead_data = rows[0]
                lead_email = lead_data.get("email")
        except Exception as exc:
            logger.debug(f"[InboundReply] Lead fetch notice: {exc}")

        if campaign_id:
            try:
                camp_res = (
                    supabase.table("campaigns")
                    .select("*")
                    .eq("id", str(campaign_id).strip())
                    .eq("workspace_id", clean_ws)
                    .execute()
                )
                c_rows = getattr(camp_res, "data", []) or []
                if c_rows and isinstance(c_rows[0], dict):
                    campaign_data = c_rows[0]
            except Exception as exc:
                logger.debug(f"[InboundReply] Campaign fetch notice: {exc}")

    # -------------------------------------------------------------------------
    # A. REFERRAL EXTRACTION & NEW PROSPECT INGESTION
    # -------------------------------------------------------------------------
    ref_result = extract_referral_contact(clean_text, referring_email=lead_email)
    summary["referral"] = ref_result

    if ref_result.get("has_referral") and ref_result.get("is_valid_referral"):
        ref_email = ref_result["referral_email"]
        if supabase:
            try:
                # Check for existing lead with this email in the workspace
                existing_res = (
                    supabase.table("leads")
                    .select("id")
                    .eq("workspace_id", clean_ws)
                    .ilike("email", ref_email)
                    .execute()
                )
                existing_rows = getattr(existing_res, "data", []) or []
                if existing_rows and existing_rows[0].get("id"):
                    existing_id = existing_rows[0]["id"]
                    summary["actions_taken"].append(f"referral_already_exists:{existing_id}")
                else:
                    new_lead_id = str(uuid.uuid4())
                    now_iso = datetime.now(timezone.utc).isoformat()
                    new_lead_payload = {
                        "id": new_lead_id,
                        "workspace_id": clean_ws,
                        "email": ref_email,
                        "first_name": ref_result.get("referral_first_name") or "",
                        "last_name": ref_result.get("referral_last_name") or "",
                        "job_title": ref_result.get("referral_title") or "",
                        "company_name": lead_data.get("company_name") or lead_data.get("company") or "",
                        "status": "NEW",
                        "referral_source_lead_id": clean_lead,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                    try:
                        supabase.table("leads").insert(new_lead_payload).execute()
                    except Exception:
                        # Fallback with minimal columns if schema has strict constraints
                        supabase.table("leads").insert({
                            "id": new_lead_id,
                            "workspace_id": clean_ws,
                            "email": ref_email,
                            "first_name": ref_result.get("referral_first_name") or "",
                            "last_name": ref_result.get("referral_last_name") or "",
                            "status": "NEW",
                            "referral_source_lead_id": clean_lead,
                        }).execute()

                    summary["actions_taken"].append(f"created_referred_lead:{new_lead_id}")
                    summary["new_lead_id"] = new_lead_id
            except Exception as ref_err:
                logger.warning(f"[InboundReply] Error saving referred lead: {ref_err}")
                summary["actions_taken"].append(f"referral_save_failed:{str(ref_err)}")

    # -------------------------------------------------------------------------
    # B. COMPANY-WIDE DOMAIN SUPPRESSION
    # -------------------------------------------------------------------------
    company_opt = detect_company_wide_opt_out(clean_text, email=lead_email)
    summary["company_suppression"] = company_opt

    if company_opt.get("is_company_wide"):
        suppress_domain = company_opt["domain"]
        if supabase:
            now_iso = datetime.now(timezone.utc).isoformat()
            # 1. Insert into suppression_list (DNC table)
            try:
                supabase.table("suppression_list").insert({
                    "workspace_id": clean_ws,
                    "domain": suppress_domain,
                    "value": suppress_domain,
                    "reason": f"Company-wide opt-out request from lead {clean_lead}",
                    "created_at": now_iso,
                }).execute()
                summary["actions_taken"].append(f"inserted_suppression_list:{suppress_domain}")
            except Exception as dnc_err:
                logger.debug(f"[InboundReply] suppression_list insert notice: {dnc_err}")

            # 2. Insert into workspace_domain_suppressions table if available
            try:
                supabase.table("workspace_domain_suppressions").insert({
                    "workspace_id": clean_ws,
                    "domain": suppress_domain,
                    "reason": f"Company-wide opt-out from lead {clean_lead}",
                    "source_lead_id": clean_lead,
                    "created_at": now_iso,
                }).execute()
                summary["actions_taken"].append(f"inserted_workspace_domain_suppressions:{suppress_domain}")
            except Exception:
                pass

            # 3. Cascade cancellation across all leads with that domain in workspace
            try:
                leads_res = (
                    supabase.table("leads")
                    .select("id, email")
                    .eq("workspace_id", clean_ws)
                    .execute()
                )
                all_leads = getattr(leads_res, "data", []) or []
                matched_lead_ids: List[str] = []
                for row in all_leads:
                    if not isinstance(row, dict) or not row.get("id"):
                        continue
                    row_em = str(row.get("email") or "").strip().lower()
                    if "@" in row_em and row_em.rsplit("@", 1)[-1].strip() == suppress_domain:
                        matched_lead_ids.append(row["id"])

                if matched_lead_ids:
                    # Mark leads suppressed
                    supabase.table("leads").update({
                        "status": "suppressed",
                        "updated_at": now_iso,
                    }).eq("workspace_id", clean_ws).in_("id", matched_lead_ids).execute()

                    # Halt active executions
                    supabase.table("campaign_execution_states").update({
                        "status": "unsubscribed_domain",
                        "error_reason": f"Retroactive domain suppression for {suppress_domain}",
                        "updated_at": now_iso,
                    }).eq("workspace_id", clean_ws).in_("opportunity_id", matched_lead_ids).in_("status", [
                        "pending", "waiting_for_reply", "running", "active", "snoozed_ooo", "awaiting_approval"
                    ]).execute()

                    summary["actions_taken"].append(
                        f"cascaded_domain_suppression:{len(matched_lead_ids)}_leads_purged"
                    )
                    summary["purged_lead_count"] = len(matched_lead_ids)
            except Exception as cascade_err:
                logger.warning(f"[InboundReply] Domain cascade purge notice: {cascade_err}")
                summary["actions_taken"].append(f"domain_cascade_failed:{str(cascade_err)}")

    # -------------------------------------------------------------------------
    # C. TIMEZONE-AWARE OOO RESCHEDULING
    # -------------------------------------------------------------------------
    combined_msg = f"{clean_subj} {clean_text}".lower()
    ooo_markers = [
        "out of the office",
        "out of office",
        "auto-reply",
        "automated reply",
        "automatic reply",
        "on leave",
        "annual leave",
        "away from my desk",
    ]
    is_ooo_reply = any(marker in combined_msg for marker in ooo_markers)
    try:
        from inbox.backend.services.sentiment_classifier import extract_ooo_return_date
        extracted_ooo = extract_ooo_return_date(clean_text or clean_subj)
    except Exception:
        extracted_ooo = {}

    if is_ooo_reply or extracted_ooo.get("has_return_date"):
        snooze_res = calculate_timezone_aware_ooo_snooze(
            lead=lead_data,
            campaign=campaign_data,
            return_date_str=extracted_ooo.get("return_date"),
        )
        summary["ooo_snooze"] = snooze_res
        if supabase:
            try:
                snooze_iso = snooze_res["snooze_until_iso"]
                supabase.table("campaign_execution_states").update({
                    "status": "snoozed_ooo",
                    "next_run_at": snooze_iso,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("workspace_id", clean_ws).eq("opportunity_id", clean_lead).in_("status", [
                    "pending", "waiting_for_reply", "running", "active"
                ]).execute()
                summary["actions_taken"].append(f"snoozed_campaign_ooo:{snooze_iso}")
            except Exception as ooo_err:
                logger.warning(f"[InboundReply] OOO execution state update error: {ooo_err}")

    return summary


# =============================================================================
# 5. CLASS-BASED FACADE
# =============================================================================

class ReferralAndSnoozeService:
    """
    Object-oriented facade exposing inbound referral contact extraction,
    company-wide domain suppression detection, timezone-aware OOO rescheduling,
    and end-to-end reply orchestration.
    """
    extract_referral_contact = staticmethod(extract_referral_contact)
    detect_company_wide_opt_out = staticmethod(detect_company_wide_opt_out)
    calculate_timezone_aware_ooo_snooze = staticmethod(calculate_timezone_aware_ooo_snooze)
    process_advanced_inbound_reply = staticmethod(process_advanced_inbound_reply)
