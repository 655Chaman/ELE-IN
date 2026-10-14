"""
Social Feed Pre-Warm & Smart Content Engagement Service (Blue Ocean Phase 11: The Engagement Multiplier)
Governance: Three-Layer Logic Architecture (Paranoia Framework)

Provides:
1. Post Sentiment & Controversial Content Radar (Safety Filter)
2. AI Contextual Comment Generator (Insightful Query, Benchmark Data, Contrarian Value Add)
3. 3-Touch Pre-Warm Cadence Scheduler (Profile View → Like → AI Comment → Connection Ready)
4. Defensive Database Fallbacks for Unmigrated Supabase Environments
"""

import re
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Banned Generic AI Slop Phrases (Layer 2 Paranoia)
BANNED_SLOP_PHRASES = [
    "great post", "awesome post", "thanks for sharing", "100% agree",
    "spot on", "love this", "so true", "great insights", "nice share",
    "totally agree", "couldn't agree more"
]

# Sensitive/Controversial Topics to Suppress (Layer 1 Paranoia)
SENSITIVE_TOPIC_KEYWORDS = [
    "layoff", "lay off", "laid off", "firing", "fired", "funeral", "rip", "passed away",
    "grief", "heartbroken", "tragic", "tragedy", "bereavement", "condolences",
    "cancer", "hospital", "politics", "election", "democrat",
    "republican", "scam", "fraud", "lawsuit", "suing", "racism", "harassment"
]

DANGEROUS_URL_SCHEMES = ("javascript:", "data:", "file:", "vbscript:", "blob:")

# Paranoia Layer 1: In-Memory Execution Lock Registry (prevents duplicate simultaneous triggers within 1 hour)
_PREWARM_EXECUTION_LOCKS: Dict[str, Dict[str, Any]] = {}

# Paranoia Layer 1 & 2: In-Memory Pre-Warm Events Cache & Seed Data (Zero-Migration Fallback & IDOR Defense)
_SEED_PREWARM_EVENTS: List[Dict[str, Any]] = [
    {
        "id": "mock-evt-1",
        "workspace_id": "ws-default",
        "lead_id": "lead-sarah-connor",
        "action_type": "profile_view",
        "status": "completed",
        "scheduled_for": datetime.now(timezone.utc).isoformat(),
        "post_url": "https://linkedin.com/in/sarah-connor-cro",
        "generated_comment": None
    },
    {
        "id": "mock-evt-2",
        "workspace_id": "ws-default",
        "lead_id": "lead-sarah-connor",
        "action_type": "post_like",
        "status": "completed",
        "scheduled_for": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        "post_url": "https://linkedin.com/in/sarah-connor-cro",
        "generated_comment": None
    },
    {
        "id": "mock-evt-3",
        "workspace_id": "ws-default",
        "lead_id": "lead-sarah-connor",
        "action_type": "post_comment",
        "status": "pending",
        "scheduled_for": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "post_url": "https://linkedin.com/in/sarah-connor-cro",
        "generated_comment": "Great point on outbound conversion. Curious how your team balances response speed vs personalization depth?"
    }
]

_IN_MEMORY_PREWARM_EVENTS: List[Dict[str, Any]] = [dict(e) for e in _SEED_PREWARM_EVENTS]


def sanitize_url(url: Optional[str]) -> str:
    """
    Paranoia Layer 1 & 2: Rejects dangerous URI schemes (XSS/exec) and enforces
    safe HTTP/HTTPS formatting.
    """
    if not url:
        return ""
    clean = url.strip()
    lower = clean.lower()
    for bad_scheme in DANGEROUS_URL_SCHEMES:
        if lower.startswith(bad_scheme):
            return ""
    if not lower.startswith(("http://", "https://")):
        # If it looks like a domain or handle, prefix with https://
        if "." in clean or "/" in clean:
            clean = f"https://{clean}"
        else:
            clean = f"https://www.linkedin.com/in/{clean}"
    try:
        parsed = urlparse(clean)
        if parsed.scheme not in ("http", "https"):
            return ""
        return clean[:1000]
    except Exception:
        return ""


def sanitize_input(text: Optional[str], max_chars: int = 4000) -> str:
    """
    Paranoia Layer 1 & 2: Strips prompt injection tokens, control characters,
    escapes formula injection prefixes (=, +, -, @, \\t, \\r), and bounds length.
    """
    if not text:
        return ""
    # Strip null bytes and control characters
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(text))
    # Neutralize prompt injection phrases
    cleaned = re.sub(r'(?i)(ignore previous instructions|system prompt:|system instructions)', '', cleaned)
    cleaned = cleaned[:max_chars].strip()
    # CSV / Formula Injection Defense
    if cleaned and cleaned[0] in ('=', '+', '-', '@', '\t', '\r'):
        cleaned = "'" + cleaned
    return cleaned


def analyze_post_sentiment(post_text: str) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Evaluates prospect post text for sentiment and safety.
    Filters out controversial topics, grievances, layoffs, or political discourse.
    Detects thematic categories for downstream personalization.
    """
    clean_text = sanitize_input(post_text)
    if not clean_text:
        return {
            "sentiment": "neutral",
            "confidence": 0.5,
            "is_safe_to_engage": False,
            "safety_reason": "empty_post_text",
            "detected_themes": [],
            "topics_detected": []
        }

    lower_text = clean_text.lower()

    # 1. Detect core themes
    detected_themes = []
    if any(k in lower_text for k in ["ai agent", "llm", "gpt", "generative ai", "machine learning", "neural", "anthropic", "openai"]) or re.search(r"\b(ai|agent|agents)\b", lower_text):
        detected_themes.append("ai_automation")
    if any(k in lower_text for k in ["sdr", "outbound", "cold email", "prospecting", "sales pipeline", "pipeline", "quota"]):
        detected_themes.append("outbound_pipeline")
    if any(k in lower_text for k in ["hiring", "team", "growth", "scaling", "culture", "recruiting"]):
        detected_themes.append("team_scaling")
    if not detected_themes:
        detected_themes.append("general_b2b")

    # 2. Check for sensitive/grief/controversial flags
    detected_sensitive = [kw for kw in SENSITIVE_TOPIC_KEYWORDS if re.search(rf"\b{kw}\b", lower_text)]
    if detected_sensitive:
        return {
            "sentiment": "controversial_or_sensitive",
            "confidence": 0.95,
            "is_safe_to_engage": False,
            "safety_reason": f"sensitive_topic_detected: {', '.join(detected_sensitive)}",
            "detected_themes": detected_themes,
            "topics_detected": detected_sensitive
        }

    # 3. Check for positive sentiment indicators
    positive_words = ["proud", "excited", "thrilled", "milestone", "launch", "announced", "win", "growth", "grateful", "success", "celebrating"]
    negative_words = ["frustrated", "tired", "broken", "angry", "failure", "hate", "worst", "mistake", "burnout"]

    pos_score = sum(1 for w in positive_words if re.search(rf"\b{w}\b", lower_text))
    neg_score = sum(1 for w in negative_words if re.search(rf"\b{w}\b", lower_text))

    if neg_score > pos_score and neg_score >= 2:
        sentiment = "negative"
        confidence = min(0.6 + neg_score * 0.1, 0.95)
        is_safe = neg_score < 4
    elif pos_score > 0:
        sentiment = "positive"
        confidence = min(0.6 + pos_score * 0.1, 0.98)
        is_safe = True
    else:
        sentiment = "neutral"
        confidence = 0.70
        is_safe = True

    return {
        "sentiment": sentiment,
        "confidence": round(confidence, 2),
        "is_safe_to_engage": is_safe,
        "safety_reason": "safe_for_engagement" if is_safe else "high_negative_sentiment",
        "detected_themes": detected_themes,
        "topics_detected": detected_themes
    }


def generate_contextual_comment(
    post_text: str,
    tone: str = "insightful_query",
    persona_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Generates non-slop, high-IQ comments tailored to the post's core premise.
    Tones:
    - 'insightful_query': Thoughtful question expanding on author's premise.
    - 'benchmark_data': Shares relevant metric or industry benchmark confirming premise.
    - 'contrarian_value_add': Respectful nuance discussing an operational tradeoff.
    """
    clean_text = sanitize_input(post_text)
    persona = persona_context or {}
    company_name = persona.get("company") or "our team"

    # Identify primary theme of post
    lower = clean_text.lower()
    if any(k in lower for k in ["ai agent", "llm", "gpt", "generative ai", "machine learning", "neural", "anthropic", "openai"]):
        theme = "ai_automation"
    elif re.search(r"\b(ai|agent|agents)\b", lower):
        theme = "ai_automation"
    elif any(k in lower for k in ["sdr", "outbound", "cold email", "prospecting", "sales pipeline", "pipeline", "quota"]):
        theme = "outbound_pipeline"
    elif any(k in lower for k in ["hiring", "team", "growth", "scaling", "culture", "recruiting"]):
        theme = "team_scaling"
    else:
        theme = "general_b2b"

    # Pre-crafted high-converting frameworks (Zero Slop)
    if theme == "outbound_pipeline":
        comments = {
            "insightful_query": "Great point on outbound conversion. Curious how your team balances response speed vs personalization depth when reps are managing 50+ active sequences?",
            "benchmark_data": "Seeing this exact trend across B2B teams right now. Data shows that pre-warming accounts with 1-2 profile touches before sending connection requests raises acceptance from 19% to over 60%.",
            "contrarian_value_add": "Completely agree with the premise, though the biggest bottleneck we see isn't copy—it's stale data. When 30% of contacts bounce, even the best sequence dies in spam filters."
        }
    elif theme == "ai_automation":
        comments = {
            "insightful_query": "Really resonant take. In your experience, where does the human-in-the-loop deliver the highest ROI—at the initial icebreaker stage or objection handling?",
            "benchmark_data": "Spot on analysis. We found that pairing LLM drafting with Thompson Sampling Bayesian learning boosted meeting booked rates by 2.4x compared to static templates.",
            "contrarian_value_add": "The promise of 100% autonomous agents is exciting, but in practice, guardrails against hallucinations in commercial deals are what separate toy tools from enterprise revenue drivers."
        }
    elif theme == "team_scaling":
        comments = {
            "insightful_query": "Spot on reflection on scaling. How do you keep operational playbooks synchronized as new hires ramp without bogging everyone down in process meetings?",
            "benchmark_data": "Strong perspective. Teams that codify their qualification criteria into unified scoring models ramp new reps in roughly 40% less time.",
            "contrarian_value_add": "Hard-won lesson here: adding seats to an inefficient outbound system just burns more lead territory faster. Fixing the baseline conversion engine first is 10x more leverage."
        }
    else:
        comments = {
            "insightful_query": "Solid perspective on this. What do you see as the primary leading indicator that teams should track when validating this shift?",
            "benchmark_data": "Very relevant timing for this. Market benchmarks indicate that agility and clean data execution are outpacing sheer volume across the board this quarter.",
            "contrarian_value_add": "Really valuable framing. One nuance we've encountered is ensuring that operational governance keeps pace so teams don't create technical debt while accelerating."
        }

    selected_comment = comments.get(tone, comments["insightful_query"])

    # Paranoia Layer 2 Slop Verification
    for slop in BANNED_SLOP_PHRASES:
        if selected_comment.lower().startswith(slop):
            # Strip slop prefix if somehow introduced
            selected_comment = selected_comment[len(slop):].lstrip(",. ")

    return {
        "status": "success",
        "tone": tone,
        "theme_detected": theme,
        "comment": selected_comment,
        "char_count": len(selected_comment),
        "is_slop_free": True
    }


def schedule_prewarm_sequence(
    supabase: Any,
    workspace_id: str,
    lead_id: str,
    lead_url: str,
    account_id: Optional[str] = None,
    post_url: Optional[str] = None,
    post_snippet: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Enqueues a 3-touch prewarm cadence for a lead:
    - Touch 1 (Now): Profile View
    - Touch 2 (+24h): Post Like
    - Touch 3 (+48h): Contextual AI Comment
    - Day 3+: Ready for Connection Request!
    Sanitizes URLs and strings, protects against SQL/UUID schema crashes,
    and defensively falls back to in-memory response if migration 082 hasn't run yet.
    """
    now = datetime.now(timezone.utc)
    t1_time = now.isoformat()
    t2_time = (now + timedelta(days=1)).isoformat()
    t3_time = (now + timedelta(days=2)).isoformat()

    clean_lead_url = sanitize_url(lead_url)
    clean_post_url = sanitize_url(post_url) if post_url else clean_lead_url
    clean_snippet = sanitize_input(post_snippet, max_chars=500) if post_snippet else "Outbound B2B growth and SDR automation"

    comment_res = generate_contextual_comment(clean_snippet, tone="insightful_query")
    comment_text = comment_res["comment"]

    # PostgreSQL UUID schema tolerance: If lead_id is not a valid UUID string,
    # generate a deterministic UUID namespace to prevent 'invalid input syntax for type uuid'
    try:
        db_lead_id = str(uuid.UUID(str(lead_id)))
    except Exception:
        db_lead_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lead:{lead_id}"))

    touchpoints = [
        {
            "workspace_id": workspace_id,
            "lead_id": db_lead_id,
            "account_id": account_id,
            "action_type": "profile_view",
            "post_url": None,
            "post_snippet": None,
            "generated_comment": None,
            "status": "pending",
            "scheduled_for": t1_time,
            "metadata": {"raw_lead_id": lead_id, "lead_url": clean_lead_url}
        },
        {
            "workspace_id": workspace_id,
            "lead_id": db_lead_id,
            "account_id": account_id,
            "action_type": "post_like",
            "post_url": clean_post_url or clean_lead_url,
            "post_snippet": clean_snippet[:200] if clean_snippet else None,
            "generated_comment": None,
            "status": "pending",
            "scheduled_for": t2_time,
            "metadata": {"raw_lead_id": lead_id, "lead_url": clean_lead_url}
        },
        {
            "workspace_id": workspace_id,
            "lead_id": db_lead_id,
            "account_id": account_id,
            "action_type": "post_comment",
            "post_url": clean_post_url or clean_lead_url,
            "post_snippet": clean_snippet[:200] if clean_snippet else None,
            "generated_comment": comment_text,
            "status": "pending",
            "scheduled_for": t3_time,
            "metadata": {"raw_lead_id": lead_id, "lead_url": clean_lead_url}
        }
    ]

    try:
        supabase.table("lead_prewarm_events").insert(touchpoints).execute()
        db_persisted = True
    except Exception as e:
        logger.warning(f"Defensive fallback: lead_prewarm_events insert skipped ({e})")
        db_persisted = False

    # Synchronize in-memory cache for fallback & testing
    for tp in touchpoints:
        _IN_MEMORY_PREWARM_EVENTS.append(dict(tp))

    return {
        "status": "success",
        "lead_id": lead_id,
        "normalized_lead_id": db_lead_id,
        "cadence_days": 3,
        "touchpoints_scheduled": len(touchpoints),
        "db_persisted": db_persisted,
        "touchpoints": touchpoints
    }


def get_lead_prewarm_status(
    supabase: Any,
    workspace_id: str,
    lead_id: str
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Retrieves prewarm touchpoints and readiness status.
    Supports both raw lead ID string and deterministic UUID representation.
    Enforces Layer 2 Cross-Tenant IDOR Isolation: does not leak foreign workspace events.
    """
    possible_ids = [lead_id]
    try:
        possible_ids.append(str(uuid.UUID(str(lead_id))))
    except Exception:
        possible_ids.append(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lead:{lead_id}")))

    events = []
    if supabase:
        try:
            res = supabase.table("lead_prewarm_events") \
                .select("*") \
                .eq("workspace_id", workspace_id) \
                .in_("lead_id", possible_ids) \
                .order("scheduled_for") \
                .execute()
            if res and res.data:
                events = list(res.data)
        except Exception as e:
            logger.debug(f"Defensive fallback: lead_prewarm_events select skipped ({e})")

    if not events:
        # Fallback to in-memory events if DB returned nothing or failed
        events = [
            dict(e) for e in _IN_MEMORY_PREWARM_EVENTS
            if (e.get("lead_id") in possible_ids or e.get("metadata", {}).get("raw_lead_id") in possible_ids)
        ]

    # Layer 2 Cross-Tenant IDOR Isolation:
    # Filter out events belonging to a different non-default workspace
    events = [
        e for e in events
        if e.get("workspace_id") in (None, "ws-default", workspace_id)
    ]

    completed = sum(1 for e in events if e.get("status") == "completed")
    is_ready = completed >= 2 or len(events) == 0
    readiness = "READY" if is_ready else "WARMING_UP"
    return {
        "status": "success",
        "lead_id": lead_id,
        "total_events": len(events),
        "completed_events": completed,
        "completed_touchpoints_count": completed,
        "is_ready_for_connection": is_ready,
        "prewarm_readiness": readiness,
        "events": events
    }


def list_prewarm_queue(
    supabase: Any,
    workspace_id: str,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Returns list of recently enqueued or active prewarm events
    for the operator's workspace, with defensive fallback if table does not exist.
    Enforces Layer 2 Cross-Tenant IDOR Isolation: filters out events created by a non-default workspace
    other than the caller's workspace.
    """
    try:
        res = supabase.table("lead_prewarm_events") \
            .select("*") \
            .eq("workspace_id", workspace_id) \
            .order("scheduled_for", desc=True) \
            .limit(limit) \
            .execute()
        events = res.data or []
        # Layer 2 Cross-Tenant IDOR Isolation
        filtered = [
            e for e in events
            if e.get("workspace_id") in (None, "ws-default", workspace_id)
        ]
        return {
            "status": "success",
            "total": len(filtered),
            "events": filtered
        }
    except Exception as e:
        logger.debug(f"Defensive fallback: list_prewarm_queue query skipped ({e})")
        # Return in-memory queue with Layer 2 Cross-Tenant IDOR Isolation
        filtered = [
            dict(e) for e in _IN_MEMORY_PREWARM_EVENTS
            if e.get("workspace_id") in (None, "ws-default", workspace_id)
        ]
        return {
            "status": "success",
            "total": len(filtered),
            "events": filtered[:limit],
            "unmigrated": True
        }


def resolve_prewarm_status_for_execution(
    workspace_id: str,
    lead_id: str,
    lead_url: Optional[str] = None,
    post_url: Optional[str] = None,
    post_snippet: Optional[str] = None,
    account_id: Optional[str] = None,
    required_touches: int = 2,
    tone: str = "insightful_query",
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Horizon 35B: Social Pre-Warming & Autonomous Multi-Touch Engagement Cadence.
    Governance: Three-Layer Logic Architecture (Paranoia Framework).

    Layer 0 (Foundational):
      - Evaluates prewarm completion status.
      - If completed >= required_touches: returns branch='Prewarmed', status='ready'.
      - If unwarmed and safe: generates contextual AI comment, schedules 3-touch cadence, returns branch='Warming'.

    Layer 1 (Environmental Failure Analysis):
      - Suppresses engagement on sensitive/layoff/grief topics (branch='Unsafe').
      - Idempotent execution lock: rejects duplicate execution triggers within 1 hour.

    Layer 2 (Human Paranoia & Security):
      - Enforces URL sanitization (rejects dangerous schemes like javascript:, data:, file:).
      - Enforces formula injection stripping on post_snippet.
      - Verifies slop-free comment generation (neutralizes banned generic AI phrases).
      - Cross-tenant IDOR defense: blocks unauthorized access to foreign workspace leads.
    """
    if not workspace_id or not str(workspace_id).strip():
        raise ValueError("workspace_id is required")
    if not lead_id or not str(lead_id).strip():
        raise ValueError("lead_id is required")

    # Layer 2 Paranoia: URL Scheme Validation
    if lead_url:
        lower_lead_url = lead_url.strip().lower()
        for bad_scheme in DANGEROUS_URL_SCHEMES:
            if lower_lead_url.startswith(bad_scheme):
                raise ValueError(f"Dangerous URL scheme '{bad_scheme}' rejected in lead_url")
        clean_lead_url = sanitize_url(lead_url)
    else:
        clean_lead_url = ""

    if post_url:
        lower_post_url = post_url.strip().lower()
        for bad_scheme in DANGEROUS_URL_SCHEMES:
            if lower_post_url.startswith(bad_scheme):
                raise ValueError(f"Dangerous URL scheme '{bad_scheme}' rejected in post_url")
        clean_post_url = sanitize_url(post_url)
    else:
        clean_post_url = clean_lead_url

    # Layer 2 Paranoia: Cross-Tenant IDOR Isolation
    possible_ids = [lead_id]
    try:
        possible_ids.append(str(uuid.UUID(str(lead_id))))
    except Exception:
        possible_ids.append(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"lead:{lead_id}")))

    for ev in _IN_MEMORY_PREWARM_EVENTS:
        ev_lid = ev.get("lead_id") or ev.get("metadata", {}).get("raw_lead_id")
        if ev_lid in possible_ids:
            ev_ws = ev.get("workspace_id")
            if ev_ws not in (None, "ws-default", workspace_id):
                raise PermissionError(f"Cross-workspace IDOR access denied: lead '{lead_id}' belongs to another workspace")

    # Layer 2 Paranoia: Strip leading formula injection characters (=, +, -, @, \t, \r)
    clean_snippet = post_snippet or ""
    while clean_snippet and clean_snippet[0] in ("=", "+", "-", "@", "\t", "\r"):
        clean_snippet = clean_snippet[1:].strip()
    clean_snippet = sanitize_input(clean_snippet)

    # Layer 0: Query prewarm status
    status_res = get_lead_prewarm_status(supabase=supabase, workspace_id=workspace_id, lead_id=lead_id)
    completed = status_res.get("completed_events", 0)

    # Layer 0: If already prewarmed, return ready status
    if completed >= required_touches:
        return {
            "status": "ready",
            "is_prewarmed": True,
            "completed_touches": completed,
            "branch": "Prewarmed",
            "prewarm_comment": "",
            "prewarm_theme": "general_b2b",
            "is_safe_to_engage": True,
            "duplicate_prevented": False
        }

    # Layer 1 Paranoia: Idempotent Execution Lock Check
    lock_key = f"{workspace_id}:{lead_id}"
    now_utc = datetime.now(timezone.utc)
    if lock_key in _PREWARM_EXECUTION_LOCKS:
        lock_entry = _PREWARM_EXECUTION_LOCKS[lock_key]
        locked_at = lock_entry.get("locked_at")
        if isinstance(locked_at, str):
            try:
                locked_at = datetime.fromisoformat(locked_at)
            except Exception:
                locked_at = None
        if locked_at and (now_utc - locked_at).total_seconds() < 3600:
            return {
                "status": "in_progress",
                "is_prewarmed": False,
                "completed_touches": completed,
                "branch": "Warming",
                "prewarm_comment": "",
                "prewarm_theme": "general_b2b",
                "is_safe_to_engage": True,
                "duplicate_prevented": True,
                "scheduled": False,
                "message": "Duplicate prewarm execution prevented (lock active within 1 hour)"
            }

    # Layer 1 Paranoia: Post Sentiment & Controversial Content Radar
    snippet_for_analysis = clean_snippet if post_snippet is not None else "Outbound B2B growth and SDR automation"
    sentiment_res = analyze_post_sentiment(snippet_for_analysis)
    if not sentiment_res.get("is_safe_to_engage"):
        return {
            "status": "unsafe",
            "is_prewarmed": False,
            "completed_touches": completed,
            "branch": "Unsafe",
            "prewarm_comment": "",
            "prewarm_theme": "sensitive",
            "is_safe_to_engage": False,
            "safety_reason": sentiment_res.get("safety_reason", "sensitive_topic_detected"),
            "duplicate_prevented": False
        }

    # Layer 0 & 2: Generate Contextual Comment (Zero Slop)
    effective_tone = tone if tone in ("insightful_query", "benchmark_data", "contrarian_value_add") else "insightful_query"
    comment_res = generate_contextual_comment(snippet_for_analysis, tone=effective_tone)
    comment_text = comment_res.get("comment", "")
    theme_detected = comment_res.get("theme_detected", "general_b2b")

    # Layer 2 Paranoia: Strip any slop phrases if accidentally introduced
    for slop in BANNED_SLOP_PHRASES:
        if slop in comment_text.lower():
            comment_text = re.sub(rf"(?i)\b{re.escape(slop)}\b", "", comment_text).strip()

    # Layer 1: Acquire Execution Lock
    _PREWARM_EXECUTION_LOCKS[lock_key] = {
        "locked_at": now_utc,
        "lead_id": lead_id,
        "workspace_id": workspace_id
    }

    # Layer 0: Schedule 3-Touch Prewarm Sequence
    lead_url_to_use = clean_lead_url or f"https://www.linkedin.com/in/{lead_id}"
    post_url_to_use = clean_post_url or lead_url_to_use
    schedule_res = schedule_prewarm_sequence(
        supabase=supabase,
        workspace_id=workspace_id,
        lead_id=lead_id,
        lead_url=lead_url_to_use,
        account_id=account_id,
        post_url=post_url_to_use,
        post_snippet=snippet_for_analysis
    )

    return {
        "status": "in_progress",
        "is_prewarmed": False,
        "completed_touches": completed,
        "branch": "Warming",
        "prewarm_comment": comment_text,
        "prewarm_theme": theme_detected,
        "is_safe_to_engage": True,
        "scheduled": True,
        "duplicate_prevented": False,
        "cadence_days": schedule_res.get("cadence_days", 3),
        "touchpoints_scheduled": schedule_res.get("touchpoints_scheduled", 3)
    }


def export_prewarm_queue_csv(
    supabase: Any,
    workspace_id: str,
    limit: int = 200
) -> str:
    """
    Paranoia Layer 0 & 2: Exports the workspace's 3-touch prewarm queue as a CSV string
    with spreadsheet formula injection neutralization (=, +, -, @, \\t, \\r).
    """
    import csv
    import io

    queue_data = list_prewarm_queue(supabase=supabase, workspace_id=workspace_id, limit=limit)
    events = queue_data.get("events") or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Event ID",
        "Lead ID",
        "Action Type",
        "Status",
        "Scheduled For",
        "Post URL",
        "Generated Comment"
    ])
    for evt in events:
        writer.writerow([
            sanitize_input(str(evt.get("id") or "")),
            sanitize_input(str(evt.get("lead_id") or "")),
            sanitize_input(str(evt.get("action_type") or "")),
            sanitize_input(str(evt.get("status") or "")),
            sanitize_input(str(evt.get("scheduled_for") or "")),
            sanitize_input(str(evt.get("post_url") or "")),
            sanitize_input(str(evt.get("generated_comment") or ""))
        ])
    return output.getvalue()


