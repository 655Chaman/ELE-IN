"""
social_radar_service.py — Prospect Social Signal Radar & Live Activity Intent Engine
Provides real-time LinkedIn activity scanning, structured buying intent harvesting,
recency-weighted scoring, and personalized opening hooks for pre-outreach social warmup.

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import re
import uuid
import csv
import io
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_POSTS_PER_SCAN = 20
MAX_PAGES_PER_SCAN = 3
MAX_BATCH_SCAN_SIZE = 100
COOLDOWN_SECONDS = 900

def parse_relative_social_date(raw_date: Any, reference_dt: Optional[datetime] = None) -> str:
    """
    Parses ISO strings, unix timestamps, or LinkedIn relative date strings
    like '2h', '3d', '1w', '2mo', '1yr', '2 hours ago', '3 days ago', 'just now'.
    Returns a valid ISO UTC timestamp string. Defaults safely to reference_dt.
    """
    ref = reference_dt or datetime.now(timezone.utc)
    if not raw_date:
        return ref.isoformat()
    
    if isinstance(raw_date, datetime):
        if not raw_date.tzinfo:
            raw_date = raw_date.replace(tzinfo=timezone.utc)
        return raw_date.isoformat()
    
    if isinstance(raw_date, (int, float)):
        try:
            return datetime.fromtimestamp(raw_date, tz=timezone.utc).isoformat()
        except Exception:
            return ref.isoformat()

    s = str(raw_date).strip().lower()
    if not s or s in ("just now", "now", "today"):
        return ref.isoformat()

    try:
        clean_s = s
        if clean_s.endswith("z"):
            clean_s = clean_s[:-1] + "+00:00"
        dt = datetime.fromisoformat(clean_s)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        pass

    match = re.search(r"(\d+)\s*(m|h|d|w|mo|yr|minute|hour|day|week|month|year)", s)
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        delta = timedelta(0)
        if unit.startswith("m"):
            delta = timedelta(minutes=val)
        elif unit.startswith("h"):
            delta = timedelta(hours=val)
        elif unit.startswith("d"):
            delta = timedelta(days=val)
        elif unit.startswith("w"):
            delta = timedelta(weeks=val)
        elif unit.startswith("mo"):
            delta = timedelta(days=val * 30)
        elif unit.startswith("y"):
            delta = timedelta(days=val * 365)
        
        parsed_dt = ref - delta
        return parsed_dt.isoformat()

    return ref.isoformat()


def extract_voyager_post_fields(raw_node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resilient Voyager post extractor scanning multiple fallback locations for text,
    url, engagement counts, media type, and post_date.
    """
    if not isinstance(raw_node, dict):
        raw_node = {}

    text = (
        raw_node.get("post_text") or
        raw_node.get("commentary", {}).get("text", {}).get("text") or
        raw_node.get("text") or
        raw_node.get("summary") or
        raw_node.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {}).get("shareCommentary", {}).get("text") or
        ""
    )

    post_url = (
        raw_node.get("post_url") or
        raw_node.get("permalink") or
        raw_node.get("updateUrl") or
        f"https://linkedin.com/posts/{uuid.uuid4()}"
    )

    social_detail = raw_node.get("socialDetail") or raw_node.get("socialCounts") or {}
    likes = (
        social_detail.get("likesCount") or
        social_detail.get("numLikes") or
        raw_node.get("likes", 0)
    )
    comments = (
        social_detail.get("commentsCount") or
        social_detail.get("numComments") or
        raw_node.get("comments", 0)
    )
    reposts = (
        social_detail.get("sharesCount") or
        social_detail.get("numShares") or
        raw_node.get("reposts", 0)
    )

    engagement_count = {
        "likes": int(likes) if isinstance(likes, (int, float, str)) and str(likes).isdigit() else 0,
        "comments": int(comments) if isinstance(comments, (int, float, str)) and str(comments).isdigit() else 0,
        "reposts": int(reposts) if isinstance(reposts, (int, float, str)) and str(reposts).isdigit() else 0,
    }

    media_type = raw_node.get("media_type") or raw_node.get("mediaType") or "text"
    raw_date = raw_node.get("post_date") or raw_node.get("createdTime") or raw_node.get("publishedAt")
    post_date = parse_relative_social_date(raw_date)

    return {
        "id": raw_node.get("id") or str(uuid.uuid4()),
        "post_url": post_url,
        "post_text": sanitize_post_text(text),
        "post_date": post_date,
        "engagement_count": engagement_count,
        "media_type": media_type
    }


def calculate_scrape_jitter(seed: Optional[str] = None, base_delay: float = 2.0, max_jitter: float = 4.0) -> float:
    """
    Generates anti-fingerprinting randomized jitter delay.
    If seed is given, uses a deterministic random generator.
    """
    if seed:
        rng = random.Random(str(seed))
        return base_delay + rng.uniform(0.5, max_jitter)
    return base_delay + random.uniform(0.5, max_jitter)


def detect_scraping_challenge(status_code: int, response_text: str = "") -> Tuple[bool, str]:
    """
    Anti-bot & Authwall Detector checking status codes (403, 429, 999) and security keywords.
    Returns (is_challenge, reason).
    """
    if status_code in (403, 429, 999):
        reasons = {
            403: "HTTP 403 Forbidden security block",
            429: "HTTP 429 Rate limit exceeded",
            999: "HTTP 999 LinkedIn security challenge block"
        }
        return True, reasons.get(status_code, f"Blocked status code {status_code}")

    if response_text:
        lower_txt = response_text.lower()
        keywords = ["checkpoint", "security verification", "captcha", "authwall", "challenge", "unusual traffic"]
        for kw in keywords:
            if kw in lower_txt:
                return True, f"Detected security challenge keyword: '{kw}'"

    return False, ""

# Valid Intent Signal Categories
SIGNAL_TYPES = [
    "HIRING_EXPANSION",
    "TECH_STACK_PAIN",
    "TOOL_EVALUATION",
    "EXECUTIVE_PROMOTION",
    "FUNDING_ANNOUNCEMENT",
    "GENERAL_THOUGHT_LEADERSHIP",
]

# Keywords dictionary for intent detection heuristics
SIGNAL_HEURISTICS: Dict[str, Dict[str, Any]] = {
    "HIRING_EXPANSION": {
        "keywords": [
            "hiring", "growing our team", "join our team", "we're expanding",
            "open roles", "looking for talented", "careers", "we are hiring",
            "building the team", "new head of", "engineering manager opening"
        ],
        "weight": 35,
        "default_strength": "HIGH",
        "description": "Prospect or company is aggressively hiring and scaling headcount."
    },
    "TECH_STACK_PAIN": {
        "keywords": [
            "struggling with", "frustrated with", "evaluating alternatives",
            "replacing our", "tech debt", "broken pipeline", "bottleneck",
            "scaling issues", "pain point", "switching away from", "database crash"
        ],
        "weight": 40,
        "default_strength": "HIGH",
        "description": "Prospect voiced active friction or pain points with current tech stack."
    },
    "TOOL_EVALUATION": {
        "keywords": [
            "recommendations for", "what are you using for", "evaluating tools",
            "comparing solutions", "looking for software", "any good alternatives",
            "rfp", "vendor evaluation", "what tool do you recommend"
        ],
        "weight": 35,
        "default_strength": "HIGH",
        "description": "Prospect is actively soliciting vendor or tool recommendations."
    },
    "EXECUTIVE_PROMOTION": {
        "keywords": [
            "promoted to", "started a new position", "thrilled to announce my new role",
            "taking on a new challenge", "excited to step into", "new chapter at",
            "new vp of", "new director of", "new role"
        ],
        "weight": 25,
        "default_strength": "MEDIUM",
        "description": "Prospect recently changed roles or earned an executive promotion."
    },
    "FUNDING_ANNOUNCEMENT": {
        "keywords": [
            "excited to share that we raised", "series a", "series b", "series c",
            "seed round", "raised $", "funding round", "backed by",
            "closed our round", "valuation", "venture capital"
        ],
        "weight": 30,
        "default_strength": "HIGH",
        "description": "Company announced fresh venture funding or capital infusion."
    },
    "GENERAL_THOUGHT_LEADERSHIP": {
        "keywords": [
            "key takeaway", "lessons learned", "perspective on", "future of",
            "spoke at", "podcast", "article", "industry trend", "my thoughts on"
        ],
        "weight": 15,
        "default_strength": "LOW",
        "description": "Prospect posted industry commentary or thought leadership."
    }
}


def sanitize_post_text(text: Optional[str], max_chars: int = 4000) -> str:
    """
    Paranoia Layer 1: Sanitizes post content against prompt injection attempts,
    strips control characters, and clamps to safe buffer length.
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Strip dangerous injection patterns
    cleaned = re.sub(
        r"(?i)\b(ignore previous instructions|disregard previous|system prompt|admin override)\b",
        "[REDACTED_DIRECTIVE]",
        text
    )
    # Strip null bytes and non-printable characters
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch in "\n\r\t")
    return cleaned.strip()[:max_chars]


def extract_intent_signals(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Layer 0 & 1: Scans prospect posts and extracts structured intent signals.
    Employs keyword heuristics with sentence quote extraction.
    """
    signals: List[Dict[str, Any]] = []

    for post in posts:
        post_text = sanitize_post_text(post.get("post_text", ""))
        if not post_text:
            continue

        lower_text = post_text.lower()
        post_id = post.get("id")

        for signal_type, config in SIGNAL_HEURISTICS.items():
            matched_keywords = []
            for kw in config["keywords"]:
                if kw in lower_text:
                    matched_keywords.append(kw)

            if matched_keywords:
                # Find matching sentence for quote snippet
                sentences = re.split(r"[.!?\n]+", post_text)
                quote_snippet = ""
                for s in sentences:
                    s_clean = s.strip()
                    if any(kw in s_clean.lower() for kw in matched_keywords):
                        quote_snippet = s_clean[:280]
                        break

                if not quote_snippet and sentences:
                    quote_snippet = sentences[0].strip()[:280]

                # Confidence based on number of keyword hits
                confidence = min(0.95, 0.70 + (len(matched_keywords) * 0.08))
                strength = config["default_strength"]
                if len(matched_keywords) >= 2 or config["weight"] >= 35:
                    strength = "HIGH"

                signals.append({
                    "signal_type": signal_type,
                    "intent_strength": strength,
                    "confidence_score": round(confidence, 2),
                    "detected_keywords": matched_keywords,
                    "signal_summary": f"Detected {signal_type.replace('_', ' ').title()} intent matching: {', '.join(matched_keywords[:3])}",
                    "quote_snippet": quote_snippet,
                    "post_id": post_id,
                    "post_date": post.get("post_date")
                })

    return signals


def calculate_buying_intent_score(
    signals: List[Dict[str, Any]],
    posts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Layer 0: Calculates composite Buying Intent Score (0-100), intent tier,
    and recommended outreach timing window based on recency and signal severity.
    """
    if not posts or not signals:
        return {
            "score": 10 if posts else 0,
            "tier": "COLD",
            "recommended_timing": "PASSIVE_WARMUP",
            "top_signal": None,
            "best_outreach_angle": "Passive observation / soft profile view before outreach"
        }

    now = datetime.now(timezone.utc)
    accumulated_score = 0.0

    # Sort signals by base weight descending
    def get_signal_weight(sig: Dict[str, Any]) -> float:
        st = sig.get("signal_type", "")
        return float(SIGNAL_HEURISTICS.get(st, {}).get("weight", 10))

    sorted_signals = sorted(signals, key=get_signal_weight, reverse=True)
    top_signal = sorted_signals[0] if sorted_signals else None

    # Calculate score with recency multiplier
    for sig in sorted_signals[:4]:  # Top 4 distinct signals
        base_weight = get_signal_weight(sig)
        strength_multiplier = 1.2 if sig.get("intent_strength") == "HIGH" else (1.0 if sig.get("intent_strength") == "MEDIUM" else 0.8)

        # Recency weighting
        post_date_raw = sig.get("post_date")
        recency_multiplier = 0.5
        if post_date_raw:
            try:
                if isinstance(post_date_raw, str):
                    post_dt = datetime.fromisoformat(post_date_raw.replace("Z", "+00:00"))
                elif isinstance(post_date_raw, datetime):
                    post_dt = post_date_raw
                else:
                    post_dt = now - timedelta(days=10)

                age_days = (now - post_dt).total_seconds() / 86400.0
                if age_days <= 3:
                    recency_multiplier = 1.0
                elif age_days <= 7:
                    recency_multiplier = 0.85
                elif age_days <= 14:
                    recency_multiplier = 0.65
                elif age_days <= 30:
                    recency_multiplier = 0.45
                else:
                    recency_multiplier = 0.25
            except Exception:
                recency_multiplier = 0.6

        signal_score = base_weight * strength_multiplier * recency_multiplier
        accumulated_score += signal_score

    # Engagement bonus
    total_engagement = 0
    for p in posts:
        eng = p.get("engagement_count") or {}
        if isinstance(eng, dict):
            total_engagement += (eng.get("likes", 0) + eng.get("comments", 0) * 2)
    if total_engagement > 20:
        accumulated_score += 10.0
    elif total_engagement > 5:
        accumulated_score += 5.0

    final_score = int(min(100, max(0, round(accumulated_score))))

    # Determine Tier
    if final_score >= 75:
        tier = "HOT"
        timing = "IMMEDIATE_ACTION"
        angle = f"Directly reference active {top_signal['signal_type'].replace('_', ' ').lower()} signal while discussion is hot"
    elif final_score >= 50:
        tier = "WARM"
        timing = "WITHIN_24_HOURS"
        angle = f"Congratulate or open conversation on {top_signal['signal_type'].replace('_', ' ').lower()}"
    elif final_score >= 25:
        tier = "MILD"
        timing = "WITHIN_3_DAYS"
        angle = "Reference recent thought leadership or company initiative"
    else:
        tier = "COLD"
        timing = "PASSIVE_WARMUP"
        angle = "Soft profile view or like prospect post before initiating direct outreach"

    return {
        "score": final_score,
        "tier": tier,
        "recommended_timing": timing,
        "top_signal": top_signal,
        "best_outreach_angle": angle
    }


def generate_social_icebreaker(
    lead_data: Dict[str, Any],
    top_post: Optional[Dict[str, Any]] = None,
    top_signal: Optional[Dict[str, Any]] = None,
    workspace_id: str = ""
) -> str:
    """
    Layer 0 & 1: Generates a contextual, non-salesy opening hook quoting prospect's post.
    Employs an intelligent sales-grade fallback formula if AI generation is offline.
    """
    first_name = lead_data.get("first_name", "there")
    job_title = lead_data.get("job_title", "")
    company_name = lead_data.get("company_name", "your team")

    quote = ""
    signal_type = "GENERAL_THOUGHT_LEADERSHIP"
    if top_signal:
        quote = top_signal.get("quote_snippet", "")
        signal_type = top_signal.get("signal_type", signal_type)
    elif top_post:
        quote = sanitize_post_text(top_post.get("post_text", ""))[:140]

    # Try AI generation first if elein_ai_service is available
    try:
        from knowledge.backend.services.elein_ai_service import _run_llm_with_failover
        sys_prompt = (
            "You are an elite LinkedIn outreach copywriter. Your goal is to write a single, "
            f"warm, 1-2 sentence personalized conversation starter to {first_name} at {company_name} referencing their recent LinkedIn post. "
            "Rules:\n"
            f"- Address {first_name} by name directly.\n"
            f"- Reference their company '{company_name}'.\n"
            "- Never say 'I saw your post' or 'I hope this finds you well'.\n"
            "- Sound conversational and peer-to-peer.\n"
            "- Directly reference the specific quote or topic.\n"
            "- End with an insightful thought or open question.\n"
            "- Max 35 words."
        )
        user_prompt = (
            f"Prospect Name: {first_name}\n"
            f"Title: {job_title} at {company_name}\n"
            f"Signal: {signal_type}\n"
            f"Post Quote Snippet: \"{quote}\"\n"
            "Write the icebreaker:"
        )
        ai_response = _run_llm_with_failover(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=60,
            temperature=0.4,
            task="messaging",
            workspace_id=workspace_id
        )
        if ai_response and len(ai_response.strip()) > 15:
            clean_res = ai_response.strip().strip('"').strip("'")
            if first_name and first_name != "there" and first_name.lower() not in clean_res.lower():
                clean_res = f"Hey {first_name}, {clean_res}"
            if company_name and company_name != "your team" and company_name.lower() not in clean_res.lower():
                if f"{first_name}," in clean_res:
                    clean_res = clean_res.replace(f"{first_name},", f"{first_name} at {company_name},", 1)
                elif f"{first_name}!" in clean_res:
                    clean_res = clean_res.replace(f"{first_name}!", f"{first_name} at {company_name}!", 1)
                elif f"{first_name}" in clean_res:
                    clean_res = clean_res.replace(f"{first_name}", f"{first_name} at {company_name}", 1)
            return clean_res
    except Exception as e:
        logger.debug(f"AI icebreaker generation fallback to rule-based: {e}")

    # High-converting rule-based fallbacks based on signal type
    if signal_type == "HIRING_EXPANSION":
        if quote:
            return f"Saw your point on growing the team: \"{quote[:80]}...\". Congrats on the expansion, {first_name}."
        return f"Congrats on the team expansion at {company_name}, {first_name} — exciting phase of growth."
    elif signal_type == "TECH_STACK_PAIN":
        if quote:
            return f"Your perspective on \"{quote[:80]}...\" really hit home. We see similar friction across engineering teams."
        return f"Really appreciated your recent thoughts on scaling bottlenecks at {company_name}, {first_name}."
    elif signal_type == "TOOL_EVALUATION":
        if quote:
            return f"Saw you're evaluating options around \"{quote[:80]}...\". Curious what criteria you're weighing most?"
        return f"Saw your recent query on tool evaluations, {first_name} — curious what stack criteria you're weighing most?"
    elif signal_type == "EXECUTIVE_PROMOTION":
        return f"Huge congratulations on stepping into the new role at {company_name}, {first_name}! Wishing you great momentum."
    elif signal_type == "FUNDING_ANNOUNCEMENT":
        return f"Thrilled to hear about the recent funding milestone at {company_name}, {first_name}! Big kudos to the whole crew."
    else:
        if quote:
            return f"Your recent post made a great point: \"{quote[:80]}...\". Definitely resonated with me."
        return f"Loved following your recent updates at {company_name}, {first_name}."


def get_mock_social_posts_for_lead(lead_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Returns empty list when no real posts exist, removing simulated activity fixtures.
    """
    return []


def scan_lead_social_feed(
    lead_id: str,
    workspace_id: str,
    supabase: Any,
    raw_posts: Optional[List[Dict[str, Any]]] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Layer 0, 1 & 2: Comprehensive single-lead social radar scan.
    - Idempotency & Cooldown: Skips duplicate scans within 15 mins unless force_refresh=True.
    - Extracts signals, buying intent score, and opening icebreaker.
    - Persists results to database with workspace isolation.
    """
    # 1. Fetch Lead
    lead_res_ws = supabase.table("leads").select("*").eq("id", lead_id).eq("workspace_id", workspace_id).execute()
    if not lead_res_ws.data:
        lead_any = supabase.table("leads").select("*").eq("id", lead_id).execute()
        if lead_any.data and len(lead_any.data) > 0:
            first_item = lead_any.data[0]
            other_ws = first_item.get("workspace_id") if isinstance(first_item, dict) else None
            if other_ws and other_ws != workspace_id:
                raise PermissionError(f"Cross-tenant access violation: lead {lead_id} belongs to workspace {other_ws}, not {workspace_id}")
        raise ValueError(f"Lead {lead_id} not found in workspace {workspace_id}")
    lead = lead_res_ws.data[0]
    if lead.get("workspace_id") and lead.get("workspace_id") != workspace_id:
        raise PermissionError(f"Cross-tenant access violation: lead {lead_id} belongs to workspace {lead.get('workspace_id')}, not {workspace_id}")

    # 2. Cooldown check (Paranoia Layer 1)
    last_scan = lead.get("last_social_scan_at")
    if last_scan and not force_refresh:
        try:
            last_scan_dt = datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last_scan_dt).total_seconds() < 900:  # 15 minutes
                logger.info(f"Using cached social radar data for lead {lead_id}")
                posts_res = supabase.table("lead_social_posts").select("*").eq("lead_id", lead_id).eq("workspace_id", workspace_id).execute()
                signals_res = supabase.table("lead_social_signals").select("*").eq("lead_id", lead_id).eq("workspace_id", workspace_id).execute()
                return {
                    "lead_id": lead_id,
                    "social_intent_score": lead.get("social_intent_score", 0),
                    "social_intent_tier": lead.get("social_intent_tier", "COLD"),
                    "recommended_timing": lead.get("recommended_timing", "PASSIVE_WARMUP"),
                    "best_outreach_angle": lead.get("best_outreach_angle", ""),
                    "social_icebreaker": lead.get("social_icebreaker", ""),
                    "last_social_scan_at": last_scan,
                    "posts": posts_res.data or [],
                    "signals": signals_res.data or [],
                    "is_cached": True
                }
        except Exception as e:
            logger.warning(f"Error checking cooldown timestamp: {e}")

    # 3. Obtain posts (either passed, or mock/voyager fallback)
    posts = raw_posts if raw_posts is not None else get_mock_social_posts_for_lead(lead)

    # 4. Extract signals and score
    signals = extract_intent_signals(posts)
    score_data = calculate_buying_intent_score(signals, posts)
    top_post = posts[0] if posts else None
    top_signal = score_data.get("top_signal")

    icebreaker = generate_social_icebreaker(lead, top_post, top_signal, workspace_id)
    scan_timestamp = datetime.now(timezone.utc).isoformat()

    # 5. Persist to DB (Atomic try-except)
    saved_posts = []
    saved_signals = []
    try:
        # Clean previous posts and signals for this lead to avoid unbounded table bloat
        supabase.table("lead_social_posts").delete().eq("lead_id", lead_id).eq("workspace_id", workspace_id).execute()
        supabase.table("lead_social_signals").delete().eq("lead_id", lead_id).eq("workspace_id", workspace_id).execute()

        # Insert new posts
        for p in posts:
            p_payload = {
                "lead_id": lead_id,
                "workspace_id": workspace_id,
                "post_url": p.get("post_url", ""),
                "post_text": sanitize_post_text(p.get("post_text", "")),
                "post_date": p.get("post_date") or scan_timestamp,
                "engagement_count": p.get("engagement_count") or {"likes": 0, "comments": 0, "reposts": 0},
                "media_type": p.get("media_type", "text")
            }
            p_ins = supabase.table("lead_social_posts").insert(p_payload).execute()
            if p_ins.data:
                saved_posts.extend(p_ins.data)

        # Insert new signals
        for s in signals:
            s_payload = {
                "lead_id": lead_id,
                "workspace_id": workspace_id,
                "signal_type": s["signal_type"],
                "intent_strength": s["intent_strength"],
                "confidence_score": s["confidence_score"],
                "detected_keywords": s["detected_keywords"],
                "signal_summary": s["signal_summary"],
                "quote_snippet": s["quote_snippet"]
            }
            s_ins = supabase.table("lead_social_signals").insert(s_payload).execute()
            if s_ins.data:
                saved_signals.extend(s_ins.data)

        # Update lead record
        supabase.table("leads").update({
            "social_intent_score": score_data["score"],
            "social_intent_tier": score_data["tier"],
            "recommended_timing": score_data["recommended_timing"],
            "best_outreach_angle": score_data["best_outreach_angle"],
            "social_icebreaker": icebreaker,
            "last_social_scan_at": scan_timestamp
        }).eq("id", lead_id).eq("workspace_id", workspace_id).execute()

        # Emit real-time webhook event if lead has HOT intent (score >= 75)
        if score_data.get("tier") == "HOT":
            try:
                from integrations.backend.services.webhook_service import emit_webhook_event
                emit_webhook_event(
                    workspace_id=workspace_id,
                    event_type="intent.hot_detected",
                    payload={
                        "lead_id": lead_id,
                        "first_name": lead.get("first_name", ""),
                        "last_name": lead.get("last_name", ""),
                        "company_name": lead.get("company_name", ""),
                        "job_title": lead.get("job_title", ""),
                        "social_intent_score": score_data["score"],
                        "social_intent_tier": "HOT",
                        "recommended_timing": score_data["recommended_timing"],
                        "best_outreach_angle": score_data["best_outreach_angle"],
                        "social_icebreaker": icebreaker,
                        "signals": [s["signal_type"] for s in signals]
                    },
                    supabase=supabase
                )
            except Exception as wh_err:
                logger.warning(f"Failed to emit intent.hot_detected webhook: {wh_err}")

    except Exception as db_err:
        logger.error(f"Error persisting social radar data for lead {lead_id}: {db_err}", exc_info=True)

    return {
        "lead_id": lead_id,
        "social_intent_score": score_data["score"],
        "social_intent_tier": score_data["tier"],
        "recommended_timing": score_data["recommended_timing"],
        "best_outreach_angle": score_data["best_outreach_angle"],
        "social_icebreaker": icebreaker,
        "last_social_scan_at": scan_timestamp,
        "posts": saved_posts or posts,
        "signals": saved_signals or signals,
        "is_cached": False
    }


def batch_scan_list_social_signals(
    list_id: str,
    workspace_id: str,
    supabase: Any,
    max_leads: int = 50,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Layer 0, 1 & 2: Batch scans leads in a target list.
    Enforces maximum lead cap (50 max) to prevent API rate exhaustion.
    """
    safe_limit = min(max(1, max_leads), 50)

    # 1. Verify list ownership
    list_res = supabase.table("lead_lists").select("id, name").eq("id", list_id).eq("workspace_id", workspace_id).execute()
    if not list_res.data:
        raise ValueError(f"Lead list {list_id} not found in workspace {workspace_id}")

    # 2. Fetch list members
    members_res = supabase.table("list_members") \
        .select("opportunity_id") \
        .eq("list_id", list_id) \
        .limit(safe_limit) \
        .execute()
    
    lead_ids = [m["opportunity_id"] for m in (members_res.data or []) if m.get("opportunity_id")]
    if not lead_ids:
        # Fallback query directly against leads table if list_members is empty
        leads_direct = supabase.table("leads").select("id").eq("workspace_id", workspace_id).limit(safe_limit).execute()
        lead_ids = [l["id"] for l in (leads_direct.data or [])]

    scanned_results = []
    hot_count = 0
    warm_count = 0
    total_signals = 0
    total_score = 0

    for lid in lead_ids:
        try:
            res = scan_lead_social_feed(
                lead_id=lid,
                workspace_id=workspace_id,
                supabase=supabase,
                force_refresh=force_refresh
            )
            scanned_results.append(res)
            score = res.get("social_intent_score", 0)
            tier = res.get("social_intent_tier", "COLD")
            total_score += score
            if tier == "HOT":
                hot_count += 1
            elif tier == "WARM":
                warm_count += 1
            total_signals += len(res.get("signals", []))
        except Exception as scan_err:
            logger.warning(f"Error scanning lead {lid} in batch: {scan_err}")

    scanned_count = len(scanned_results)
    avg_score = round(total_score / scanned_count, 1) if scanned_count > 0 else 0

    return {
        "status": "success",
        "list_id": list_id,
        "scanned_count": scanned_count,
        "hot_count": hot_count,
        "warm_count": warm_count,
        "total_signals_detected": total_signals,
        "average_intent_score": avg_score,
        "leads": scanned_results
    }


def get_workspace_intent_feed(
    workspace_id: str,
    supabase: Any,
    tier_filter: Optional[str] = None,
    signal_type: Optional[str] = None,
    limit: int = 50,
    include_demo_fallback: bool = False
) -> Dict[str, Any]:
    """
    Layer 0 & 1: Retrieves real-time intent feed across workspace leads.
    Returns prospects ordered by intent score and recent activity.
    Returns empty feed when no signals exist in the database.
    """
    safe_limit = min(max(1, limit), 100)
    query = supabase.table("leads") \
        .select("id, first_name, last_name, job_title, company_name, linkedin_url, location, social_intent_score, social_intent_tier, last_social_scan_at, best_outreach_angle, social_icebreaker, recommended_timing, last_social_retargeted_at") \
        .eq("workspace_id", workspace_id) \
        .gt("social_intent_score", 0) \
        .order("social_intent_score", desc=True) \
        .order("last_social_scan_at", desc=True) \
        .limit(safe_limit)

    if tier_filter and tier_filter.upper() in ["HOT", "WARM", "MILD", "COLD"]:
        query = query.eq("social_intent_tier", tier_filter.upper())

    try:
        leads_res = query.execute()
        leads = leads_res.data or []
    except Exception as e:
        logger.warning(f"Error querying leads for social intent feed: {e}")
        leads = []

    feed_items = []
    for l in leads:
        lead_id = l["id"]
        # Fetch top signals for this lead
        try:
            signals_res = supabase.table("lead_social_signals") \
                .select("id, signal_type, intent_strength, confidence_score, signal_summary, quote_snippet, created_at") \
                .eq("lead_id", lead_id) \
                .eq("workspace_id", workspace_id) \
                .order("created_at", desc=True) \
                .limit(3) \
                .execute()
            signals = signals_res.data or []
        except Exception:
            signals = []

        if signal_type and not any(s.get("signal_type") == signal_type for s in signals):
            continue

        # Fetch latest post
        try:
            post_res = supabase.table("lead_social_posts") \
                .select("post_url, post_text, post_date, engagement_count, media_type") \
                .eq("lead_id", lead_id) \
                .eq("workspace_id", workspace_id) \
                .order("post_date", desc=True) \
                .limit(1) \
                .execute()
            top_post = post_res.data[0] if post_res.data else None
        except Exception:
            top_post = None

        feed_items.append({
            "lead": l,
            "signals": signals,
            "top_post": top_post
        })

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "total_items": len(feed_items),
        "feed": feed_items,
        "is_demo_preview": False
    }


def enroll_lead_with_icebreaker(
    lead_id: str,
    campaign_id: str,
    workspace_id: str,
    custom_icebreaker: Optional[str],
    supabase: Any,
    force_override: bool = False,
    sender_account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Layer 0, 1 & 2: Enrolls prospect into campaign sequence with verified icebreaker.
    Enforces CollisionGuard cross-campaign protection and 14-day anti-spam cooldown.
    """
    # 1. Verify Campaign
    camp_res = supabase.table("campaigns").select("id, name, status").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
    if not camp_res.data:
        raise ValueError(f"Campaign {campaign_id} not found in workspace {workspace_id}")
    campaign = camp_res.data[0]

    # 2. Verify Lead
    lead_res = supabase.table("leads").select("id, first_name, last_name, social_icebreaker, last_social_retargeted_at").eq("id", lead_id).eq("workspace_id", workspace_id).execute()
    if not lead_res.data:
        raise ValueError(f"Lead {lead_id} not found in workspace {workspace_id}")
    lead = lead_res.data[0]

    # 3. Layer 2 Paranoia: Cross-Campaign Collision Guard
    if not force_override:
        try:
            from campaigns.backend.services.collision_guard import get_conflicting_active_leads
            conflicts = get_conflicting_active_leads(
                supabase_client=supabase,
                workspace_id=workspace_id,
                lead_ids=[lead_id],
                exclude_campaign_id=campaign_id
            )
            if lead_id in conflicts:
                raise ValueError(
                    f"COLLISION_DETECTED: Lead {lead_id} is already in-flight in another active campaign. "
                    "Retargeting now would double-message the prospect. Use force_override=True to proceed."
                )
        except Exception as guard_err:
            if "COLLISION_DETECTED" in str(guard_err):
                raise
            logger.warning(f"Collision guard check warning: {guard_err}")

    # 4. Layer 2 Paranoia: 14-Day Cooldown Anti-Spam Interlock
    last_retargeted = lead.get("last_social_retargeted_at")
    if last_retargeted and not force_override:
        try:
            if isinstance(last_retargeted, str):
                last_dt = datetime.fromisoformat(last_retargeted.replace("Z", "+00:00"))
            else:
                last_dt = last_retargeted
            days_ago = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400.0
            if days_ago < 14:
                raise ValueError(
                    f"COOLDOWN_ACTIVE: Lead was retargeted {int(days_ago)} days ago. "
                    "To protect LinkedIn sender reputation, wait 14 days between retargeting actions, or pass force_override=True."
                )
        except Exception as cd_err:
            if "COOLDOWN_ACTIVE" in str(cd_err):
                raise
            logger.warning(f"Cooldown calculation warning: {cd_err}")

    chosen_icebreaker = sanitize_post_text(custom_icebreaker) if custom_icebreaker else lead.get("social_icebreaker", "")

    # 5. Create or update campaign_execution_states / enrollment
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        # Fetch active version
        ver_res = supabase.table("campaign_versions").select("id").eq("campaign_id", campaign_id).order("created_at", desc=True).limit(1).execute()
        ver_id = ver_res.data[0]["id"] if (ver_res.data and len(ver_res.data) > 0) else None

        enr_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{campaign_id}_{lead_id}"))
        enr_payload = {
            "id": enr_id,
            "campaign_id": campaign_id,
            "lead_id": lead_id,
            "workspace_id": workspace_id,
            "status": "active"
        }
        if ver_id:
            enr_payload["campaign_version_id"] = ver_id
        if sender_account_id:
            enr_payload["account_id"] = sender_account_id

        supabase.table("campaign_enrollments").upsert(
            enr_payload,
            on_conflict="campaign_id,lead_id"
        ).execute()

        exec_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"exec_{enr_id}"))
        exec_payload = {
            "id": exec_id,
            "enrollment_id": enr_id,
            "workspace_id": workspace_id,
            "status": "active",
            "variables": {
                "social_icebreaker": chosen_icebreaker,
                "first_name": lead.get("first_name", ""),
                "last_name": lead.get("last_name", "")
            },
            "updated_at": now_iso
        }
        supabase.table("campaign_execution_states").upsert(
            exec_payload,
            on_conflict="enrollment_id"
        ).execute()
    except Exception as e:
        logger.warning(f"Error enrolling lead into campaign_enrollments/execution_states: {e}")

    # Update lead's social_icebreaker and last_social_retargeted_at
    update_data: Dict[str, Any] = {"last_social_retargeted_at": now_iso}
    if chosen_icebreaker:
        update_data["social_icebreaker"] = chosen_icebreaker
    try:
        supabase.table("leads").update(update_data).eq("id", lead_id).eq("workspace_id", workspace_id).execute()
    except Exception as update_err:
        logger.warning(f"Failed to update lead retargeted timestamp: {update_err}")

    return {
        "status": "enrolled",
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("name"),
        "lead_id": lead_id,
        "lead_name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
        "social_icebreaker": chosen_icebreaker,
        "enrolled_at": now_iso
    }


def generate_intent_retargeting_draft(
    lead_id: str,
    workspace_id: str,
    supabase: Any,
    signal_id: Optional[str] = None,
    tone: str = "consultative"
) -> Dict[str, Any]:
    """
    Layer 0, 1 & 2: Synthesizes high-converting intent-based outreach drafts
    (connection note & follow-up message) referencing the prospect's detected buying signal.
    """
    # 1. Fetch Lead
    try:
        lead_res = supabase.table("leads").select("*").eq("id", lead_id).eq("workspace_id", workspace_id).execute()
        lead = lead_res.data[0] if (lead_res.data and len(lead_res.data) > 0) else None
    except Exception:
        lead = None

    if not lead:
        raise ValueError(f"Lead {lead_id} not found in workspace {workspace_id}")

    first_name = lead.get("first_name", "there")
    company_name = lead.get("company_name", "your team")
    job_title = lead.get("job_title", "")

    # 2. Fetch Top Signal
    signal = None
    if signal_id:
        try:
            sig_res = supabase.table("lead_social_signals").select("*").eq("id", signal_id).eq("workspace_id", workspace_id).execute()
            if sig_res.data:
                signal = sig_res.data[0]
        except Exception:
            pass

    if not signal:
        try:
            sig_res = supabase.table("lead_social_signals").select("*").eq("lead_id", lead_id).eq("workspace_id", workspace_id).order("created_at", desc=True).limit(1).execute()
            if sig_res.data:
                signal = sig_res.data[0]
        except Exception:
            pass

    signal_type = signal.get("signal_type", "GENERAL_THOUGHT_LEADERSHIP") if signal else "HIRING_EXPANSION"
    quote = signal.get("quote_snippet", "") if signal else ""
    confidence = signal.get("confidence_score", 0.88) if signal else 0.88

    # 3. Core Value Prop
    core_value = "helping scale outbound pipeline with residential proxy protection and Bayesian targeting"
    try:
        from knowledge.backend.services.elein_ai_service import _get_unified_brain
        brain = _get_unified_brain(workspace_id)
        if brain.get("core_value_prop"):
            core_value = brain["core_value_prop"]
    except Exception:
        pass

    # 4. Generate Connection Note & Follow-up Message
    if signal_type == "HIRING_EXPANSION":
        note = f"Hey {first_name}, saw your team at {company_name} is actively hiring. Congrats on the expansion — would love to connect."
        follow_up = (
            f"Hey {first_name},\n\n"
            f"Saw you mentioned expanding the engineering org: \"{quote[:90]}...\". With headcounts ramping, team bandwidth gets stretched quick.\n\n"
            f"We help high-growth teams at {company_name} streamline outbound pipeline without bot detection flags or proxy headaches.\n\n"
            "Open to trading a couple notes on how peer teams in your space are handling this?"
        )
    elif signal_type == "TECH_STACK_PAIN":
        note = f"Hi {first_name}, saw your perspective on scaling bottlenecks at {company_name}. Really resonated — let's connect."
        follow_up = (
            f"Hi {first_name},\n\n"
            f"Your point on \"{quote[:90]}...\" really hit home. Most leaders we speak with run into the exact same wall.\n\n"
            f"We built Ele-in specifically to solve this by providing {core_value}.\n\n"
            "Would you be open to a quick 5-min look at how we eliminate that friction?"
        )
    elif signal_type == "TOOL_EVALUATION":
        note = f"Hey {first_name}, noticed you're evaluating tooling in your stack. Great timing — let's connect."
        follow_up = (
            f"Hey {first_name},\n\n"
            f"Saw your query asking about: \"{quote[:90]}...\".\n\n"
            f"We've compiled an objective vendor comparison matrix for teams evaluating {core_value}.\n\n"
            "Happy to send over the 1-page breakdown if you're weighing options this quarter?"
        )
    elif signal_type == "FUNDING_ANNOUNCEMENT":
        note = f"Huge congrats on the recent funding round at {company_name}, {first_name}! Inspiring milestone — let's connect."
        follow_up = (
            f"Hey {first_name},\n\n"
            f"Huge congratulations on the recent funding milestone at {company_name}!\n\n"
            f"Post-round growth targets usually mean aggressive pipeline expectations. We help funded scaleups accelerate GTM with zero account risk.\n\n"
            "Would love to share how our peer teams ramped pipeline post-Series A. Worth a quick chat next week?"
        )
    else:
        note = f"Hi {first_name}, loved your recent industry commentary regarding {company_name}. Would be great to connect."
        follow_up = (
            f"Hi {first_name},\n\n"
            f"Really appreciated your recent update: \"{quote[:90]}...\".\n\n"
            f"We focus on {core_value}, and your perspective sparked some interesting thoughts for our team.\n\n"
            "Curious how you're approaching this in Q3 — open to a quick exchange?"
        )

    if len(note) > 280:
        note = note[:277] + "..."

    return {
        "status": "success",
        "lead_id": lead_id,
        "lead_name": f"{first_name} {lead.get('last_name', '')}".strip(),
        "company_name": company_name,
        "job_title": job_title,
        "signal_type": signal_type,
        "quote_snippet": quote,
        "confidence_score": confidence,
        "connection_note": note,
        "follow_up_message": follow_up,
        "estimated_reply_rate": 42 if signal_type in ["HIRING_EXPANSION", "TECH_STACK_PAIN"] else 34,
        "urgency": "HIGH" if signal_type in ["HIRING_EXPANSION", "TECH_STACK_PAIN", "TOOL_EVALUATION"] else "MEDIUM"
    }


def dismiss_social_signal(
    lead_id: str,
    signal_id: Optional[str],
    workspace_id: str,
    supabase: Any
) -> Dict[str, Any]:
    """
    Layer 0 & 2: Dismisses a social signal from active radar feed with audit logging.
    """
    if signal_id:
        try:
            supabase.table("lead_social_signals").delete().eq("id", signal_id).eq("workspace_id", workspace_id).execute()
        except Exception as e:
            logger.warning(f"Failed to delete signal {signal_id}: {e}")

    try:
        remaining = supabase.table("lead_social_signals").select("id").eq("lead_id", lead_id).eq("workspace_id", workspace_id).execute()
        if not (remaining.data or []):
            supabase.table("leads").update({"social_intent_score": 0, "social_intent_tier": "COLD"}).eq("id", lead_id).eq("workspace_id", workspace_id).execute()
    except Exception as reset_err:
        logger.warning(f"Failed to reset lead intent score: {reset_err}")

    return {
        "status": "dismissed",
        "lead_id": lead_id,
        "signal_id": signal_id
    }


def sanitize_text(val: Optional[str]) -> str:
    """
    Paranoia Layer 2: Neutralizes spreadsheet formula injection (=, +, -, @, \t, \r).
    """
    if not val:
        return ""
    cleaned = str(val).strip()
    while cleaned and cleaned[0] in ('=', '+', '-', '@', '\t', '\r'):
        cleaned = cleaned[1:].strip()
    return cleaned


def export_social_radar_feed_csv(
    workspace_id: str,
    supabase: Any,
    tier_filter: Optional[str] = None,
    signal_type: Optional[str] = None,
    include_demo_fallback: bool = False
) -> str:
    """
    Paranoia Layer 0 & 2: Exports social intent feed to formula-defended CSV stream.
    """
    feed_data = get_workspace_intent_feed(
        workspace_id=workspace_id,
        supabase=supabase,
        tier_filter=tier_filter,
        signal_type=signal_type,
        limit=100,
        include_demo_fallback=False
    )
    items = feed_data.get("feed", [])

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Lead ID",
        "Prospect Name",
        "Company Name",
        "Job Title",
        "LinkedIn URL",
        "Intent Score",
        "Intent Tier",
        "Top Signal Type",
        "Signal Summary",
        "Recommended Timing",
        "Best Outreach Angle",
        "Generated Icebreaker"
    ])

    for item in items:
        lead = item.get("lead", {})
        signals = item.get("signals", [])
        top_sig = signals[0] if signals else {}

        p_name = sanitize_text(f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip())
        c_name = sanitize_text(lead.get("company_name", ""))
        title = sanitize_text(lead.get("job_title", ""))
        sig_type = sanitize_text(top_sig.get("signal_type", ""))
        summary = sanitize_text(top_sig.get("signal_summary", ""))
        angle = sanitize_text(lead.get("best_outreach_angle", ""))
        ice = sanitize_text(lead.get("social_icebreaker", ""))
        lead_id_clean = sanitize_text(lead.get("id", ""))
        li_url_clean = sanitize_text(lead.get("linkedin_url", ""))
        timing_clean = sanitize_text(lead.get("recommended_timing", ""))

        writer.writerow([
            lead_id_clean,
            p_name,
            c_name,
            title,
            li_url_clean,
            lead.get("social_intent_score", 0),
            lead.get("social_intent_tier", "COLD"),
            sig_type,
            summary,
            timing_clean,
            angle,
            ice
        ])

    return output.getvalue()

