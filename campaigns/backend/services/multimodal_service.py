import logging
import uuid
import csv
import io
import re
import urllib.parse
import hashlib
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Paranoia Layer 1: Deterministic hash resisting process restarts and PYTHONHASHSEED randomization
def _deterministic_hex(text: str, length: int = 12) -> str:
    """Paranoia Layer 1: Returns deterministic SHA256 hex digest slice."""
    if not text:
        return "000000000000"[:length]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _normalize_uuid(val: Optional[str], namespace_prefix: str = "multimodal") -> Optional[str]:
    """
    Paranoia Layer 1: Normalizes string identifiers into RFC-compliant UUIDs.
    Prevents PostgreSQL syntax errors (22P02: invalid input syntax for type uuid).
    """
    if not val:
        return None
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace_prefix}:{val}"))


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


def sanitize_prompt_injection(val: Optional[str]) -> str:
    """
    Paranoia Layer 2: Neutralizes LLM prompt injection, system role hijacking, and delimiter escapes.
    """
    if not val:
        return ""
    cleaned = str(val).strip()
    cleaned = re.sub(
        r'(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|system\s*:|assistant\s*:|human\s*:|\[INST\]|\[\/INST\]|<\/?system>)',
        '',
        cleaned
    )
    return cleaned.strip()


def sanitize_url(url: Optional[str]) -> str:
    """
    Paranoia Layer 1 & 2: Validates URL against dangerous schemes (javascript:, data:, etc.).
    """
    if not url:
        return ""
    clean = str(url).strip()
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme.lower() not in ("http", "https"):
        return ""
    return clean


# Paranoia Layer 1: Thread concurrency re-entrant lock and bounded deduplication cache
_multimodal_lock = threading.RLock()
_ASSET_SYNTHESIS_LOCKS: Dict[str, Dict[str, Any]] = {}
_ASSET_SYNTHESIS_LOCK_TTL_SECONDS = 3600
_MAX_SYNTHESIS_LOCKS = 1000


def _evict_expired_synthesis_locks_locked(now: Optional[datetime] = None) -> None:
    """
    Paranoia Layer 1: Bounded in-memory synthesis lock dictionary to prevent memory exhaustion.
    Must be called under _multimodal_lock.
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    def _safe_ts(val: Any) -> datetime:
        if isinstance(val, datetime):
            return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
        return current_time

    expired_keys = [
        k for k, v in _ASSET_SYNTHESIS_LOCKS.items()
        if (current_time - _safe_ts(v.get("timestamp", current_time))).total_seconds() >= _ASSET_SYNTHESIS_LOCK_TTL_SECONDS
    ]
    for k in expired_keys:
        _ASSET_SYNTHESIS_LOCKS.pop(k, None)

    if len(_ASSET_SYNTHESIS_LOCKS) > _MAX_SYNTHESIS_LOCKS:
        sorted_keys = sorted(
            _ASSET_SYNTHESIS_LOCKS.keys(),
            key=lambda k: _ASSET_SYNTHESIS_LOCKS[k].get("timestamp", datetime.min)
        )
        for k in sorted_keys[: len(_ASSET_SYNTHESIS_LOCKS) - _MAX_SYNTHESIS_LOCKS]:
            _ASSET_SYNTHESIS_LOCKS.pop(k, None)


def _is_cross_workspace_prohibited(item_ws: Optional[str], caller_ws: str, norm_caller_ws: Optional[str] = None) -> bool:
    """
    Paranoia Layer 2: IDOR cross-tenant isolation.
    Returns True if item belongs to a non-default workspace different from caller's workspace.
    """
    if not item_ws:
        return False
    default_workspaces = {"ws-default", "default"}
    if item_ws in default_workspaces:
        return False
    if item_ws in (caller_ws, norm_caller_ws):
        return False
    return True


# Paranoia Layer 1: In-memory fallback for zero-migration resilience
_IN_MEMORY_MULTIMODAL: List[Dict[str, Any]] = [
    {
        "id": "asset-voice-1",
        "workspace_id": "ws-default",
        "lead_id": "lead-voice-1",
        "asset_type": "voice_script",
        "script_text": "Hey Jessica [pause] — dropping you a quick 20-second audio note rather than another stiff email. Saw you're heading up revenue at Nexis. We just helped a team in your space cut outbound bounce rates by 40% using automated LinkedIn pre-warming. Curious if you're open to seeing the 2-minute benchmark breakdown? Either way, hope the week's off to a great start!",
        "estimated_duration_sec": 24,
        "media_url": None,
        "thumbnail_text": None,
        "status": "ready",
        "created_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "id": "asset-video-2",
        "workspace_id": "ws-default",
        "lead_id": "lead-video-2",
        "asset_type": "video_card",
        "script_text": "Hey Marcus — made a custom 60-second video teardown on how Apex Cloud can pre-warm prospects on LinkedIn before SDR email outreach.",
        "estimated_duration_sec": 58,
        "media_url": "https://elein.app/v/apex-cloud-teardown",
        "thumbnail_text": "Custom 60s Outbound Audit for Marcus @ Apex Cloud",
        "status": "ready",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
]


def generate_voice_script(
    lead_name: str,
    company: str,
    title: Optional[str] = None,
    tone: str = "casual_peer",
    custom_pain_point: Optional[str] = None,
    workspace_id: str = "ws-default",
    supabase: Optional[Any] = None,
    use_ai: bool = False,
    banned_phrases: Optional[str] = None,
    ai_model: str = "",
) -> Dict[str, Any]:
    """
    Paranoia Layer 0: Synthesizes high-impact 20-35 second conversational voice note script.
    Includes phonetic pauses [pause] and pacing cues.
    Layer 1: Deterministic UUID5/SHA256 identifiers; LLM failover to deterministic templates.
    Layer 2: Prompt injection stripping, formula injection neutralization, and brand safety phrase removal.
    """
    clean_name = sanitize_prompt_injection(sanitize_text(lead_name))
    first_name = clean_name.split()[0] if clean_name else "there"
    comp = sanitize_prompt_injection(sanitize_text(company)) or "your team"
    clean_title = sanitize_prompt_injection(sanitize_text(title))
    pain = sanitize_prompt_injection(sanitize_text(custom_pain_point)) or "outbound message deliverability"
    norm_ws = _normalize_uuid(workspace_id, "workspace") or workspace_id

    script: Optional[str] = None

    # Paranoia Layer 1: Optional LLM Synthesis with robust failover to deterministic templates
    if use_ai:
        try:
            from knowledge.backend.services.elein_ai_service import _run_llm_with_failover
            from knowledge.backend.services.prompt_safety import sanitize_for_prompt

            sys_prompt = (
                "You are an elite B2B sales development representative recording a concise 20-35 second voice note. "
                "Strict requirements:\n"
                "- Keep it strictly between 40 and 80 words.\n"
                "- Include natural conversational pacing and exactly 2 or 3 phonetic pause markers '[pause]'.\n"
                "- Match the requested tone.\n"
                "- Zero markdown, zero formatting, zero quotes. Output ONLY the raw spoken script."
            )
            safe_name = sanitize_for_prompt(clean_name, "lead_name")
            safe_comp = sanitize_for_prompt(comp, "company")
            safe_title = sanitize_for_prompt(clean_title or "Revenue Leader", "job_title")
            safe_pain = sanitize_for_prompt(pain, "pain_point")

            user_prompt = (
                f"Prospect: {safe_name}\n"
                f"Company: {safe_comp}\n"
                f"Title: {safe_title}\n"
                f"Tone: {tone}\n"
                f"Core Challenge/Pain Point: {safe_pain}\n\n"
                "Record the personalized voice drop script:"
            )

            ai_res = _run_llm_with_failover(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=200,
                temperature=0.3,
                task="voice_script",
                ai_model=ai_model,
                workspace_id=workspace_id,
            )
            if ai_res and len(ai_res.strip().split()) >= 15:
                cand_script = ai_res.strip().strip('"').strip("'")
                if "[pause]" not in cand_script.lower():
                    # Add natural pause between sentences
                    sentences = [s.strip() for s in re.split(r'([.?!])', cand_script) if s.strip()]
                    if len(sentences) >= 4:
                        cand_script = f"{sentences[0]}{sentences[1]} [pause] {''.join(sentences[2:])}"
                script = cand_script
        except Exception as ai_err:
            logger.warning(f"AI voice script generation failover to template: {ai_err}")

    # Fallback / Deterministic Template Synthesis
    if not script:
        if tone == "executive_brief":
            script = (
                f"{first_name} — dropping a brief 20-second audio note directly. [pause] "
                f"Noticed {comp} is aggressively expanding the GTM pipeline this quarter. "
                f"Most revenue leaders we speak with are seeing traditional cold email reply rates fall below 2%. "
                f"We built an autonomous pre-warm loop that doubles positive replies before your reps send an invite. "
                f"[pause] Open to taking a look at our 2-minute benchmark?"
            )
        elif tone == "provocative_observation":
            script = (
                f"Hey {first_name} — quick question for you. [pause] "
                f"I was looking at {comp}'s outbound footprint and noticed a big bottleneck with {pain}. "
                f"Almost everyone in your category is blasting generic connection requests and getting ignored. "
                f"We ran a study showing a 3.4x reply lift when you pre-warm leads with contextual feed comments first. "
                f"[pause] Mind if I send over the short case study?"
            )
        else:  # casual_peer
            script = (
                f"Hey {first_name}! [pause] Thought I'd send a quick voice note instead of crowding your inbox with another pitch. "
                f"Saw what you're building at {comp} — really impressive trajectory. "
                f"We put together a short teardown on how B2B teams are doubling meeting conversions without burning their domain reputation. "
                f"[pause] Would you be opposed if I sent it over to glance at?"
            )

    # Paranoia Layer 2: Enforce brand safety phrase removal
    if banned_phrases:
        try:
            from knowledge.backend.services.elein_ai_service import enforce_banned_phrases
            script = enforce_banned_phrases(script, banned_phrases)
        except Exception as bp_err:
            logger.warning(f"Could not enforce banned phrases on script: {bp_err}")

    # Calculate estimated duration (average speaking speed ~ 2.5 words per second)
    words = script.split()
    duration_sec = max(18, min(45, int(len(words) / 2.5)))

    # Paranoia Layer 1: Deterministic UUID5 identifier derived from SHA256 of payload
    script_hash = _deterministic_hex(script)
    asset_id = _normalize_uuid(f"asset_voice:{norm_ws}:{clean_name}:{comp}:{script_hash}", "asset_voice") or f"voice-{script_hash}"
    asset_record = {
        "id": asset_id,
        "workspace_id": norm_ws,
        "lead_id": None,
        "asset_type": "voice_script",
        "script_text": script,
        "estimated_duration_sec": duration_sec,
        "media_url": None,
        "thumbnail_text": None,
        "status": "ready",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    if supabase:
        try:
            supabase.table("multimodal_assets").insert(asset_record).execute()
        except Exception as e:
            logger.warning(f"Could not persist voice script to DB: {e}")

    with _multimodal_lock:
        _IN_MEMORY_MULTIMODAL.append(asset_record)

    return {
        "status": "success",
        "asset_id": asset_id,
        "lead_name": clean_name or lead_name,
        "company": comp,
        "tone": tone,
        "script": script,
        "estimated_duration_sec": duration_sec,
        "word_count": len(words),
        "message": f"Successfully generated {duration_sec}s voice script for {clean_name or lead_name}!"
    }


def generate_video_prospecting_card(
    lead_name: str,
    company: str,
    video_topic: Optional[str] = None,
    workspace_id: str = "ws-default",
    supabase: Optional[Any] = None,
    banned_phrases: Optional[str] = None,
    media_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0: Synthesizes Loom/video prospecting asset with custom thumbnail copy.
    Layer 1 & 2: UUID normalization, deterministic hashing, formula injection & brand safety defense.
    Flaw 4.4: Prioritizes explicit media_url to eliminate phantom 404 links.
    """
    clean_name = sanitize_prompt_injection(sanitize_text(lead_name))
    first_name = clean_name.split()[0] if clean_name else "there"
    comp = sanitize_prompt_injection(sanitize_text(company)) or "your team"
    topic = sanitize_prompt_injection(sanitize_text(video_topic)) or "Outbound Pipeline Teardown"
    norm_ws = _normalize_uuid(workspace_id, "workspace") or workspace_id

    thumbnail_title = f"Custom 60s {topic} for {first_name} @ {comp}"
    clean_slug = re.sub(r'[^a-zA-Z0-9_-]', '-', comp.lower()).strip('-') or 'custom'
    name_hash = _deterministic_hex(clean_name or lead_name, 6)
    
    if media_url:
        video_url = sanitize_url(media_url)
        is_rendered = True
    else:
        video_url = sanitize_url(f"https://elein.app/v/{clean_slug}-{name_hash}")
        is_rendered = False

    dm_copy = (
        f"Hey {first_name} — put together a personalized 60-second video walkthrough "
        f"showing how {comp} can unlock 2x more meetings from target accounts: {video_url}"
    )

    if banned_phrases:
        try:
            from knowledge.backend.services.elein_ai_service import enforce_banned_phrases
            dm_copy = enforce_banned_phrases(dm_copy, banned_phrases)
            thumbnail_title = enforce_banned_phrases(thumbnail_title, banned_phrases)
        except Exception as bp_err:
            logger.warning(f"Could not enforce banned phrases on video card: {bp_err}")

    title_hash = _deterministic_hex(thumbnail_title)
    asset_id = _normalize_uuid(f"asset_video:{norm_ws}:{clean_name}:{comp}:{title_hash}", "asset_video") or f"video-{title_hash}"
    asset_record = {
        "id": asset_id,
        "workspace_id": norm_ws,
        "lead_id": None,
        "asset_type": "video_card",
        "script_text": dm_copy,
        "estimated_duration_sec": 58,
        "media_url": video_url,
        "thumbnail_text": thumbnail_title,
        "status": "ready",
        "is_rendered": is_rendered,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    if supabase:
        try:
            supabase.table("multimodal_assets").insert(asset_record).execute()
        except Exception as e:
            logger.warning(f"Could not persist video card to DB: {e}")

    with _multimodal_lock:
        _IN_MEMORY_MULTIMODAL.append(asset_record)

    return {
        "status": "success",
        "asset_id": asset_id,
        "lead_name": clean_name or lead_name,
        "company": comp,
        "thumbnail_title": thumbnail_title,
        "video_url": video_url,
        "dm_copy": dm_copy,
        "estimated_duration_sec": 58,
        "message": f"Successfully created personalized video prospecting card for {first_name}!"
    }


def list_multimodal_assets(
    workspace_id: str,
    asset_type: Optional[str] = None,
    supabase: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Paranoia Layer 0 & 1: Retrieves generated multimodal voice & video assets.
    Enforces Layer 2 Cross-Tenant IDOR Isolation: filters out assets belonging to other non-default workspaces.
    Thread-safe access to in-memory store under _multimodal_lock.
    """
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    if supabase:
        try:
            query = supabase.table("multimodal_assets").select("*")
            if norm_ws:
                query = query.in_("workspace_id", [workspace_id, norm_ws])
            else:
                query = query.eq("workspace_id", workspace_id)
            if asset_type:
                query = query.eq("asset_type", asset_type)
            res = query.order("created_at", desc=True).limit(50).execute()
            if isinstance(res.data, list) and len(res.data) > 0:
                return [
                    a for a in res.data
                    if not _is_cross_workspace_prohibited(a.get("workspace_id"), workspace_id, norm_ws)
                ]
        except Exception as e:
            logger.warning(f"Failed to query multimodal_assets from DB: {e}")

    with _multimodal_lock:
        results = [
            dict(a) for a in _IN_MEMORY_MULTIMODAL
            if not _is_cross_workspace_prohibited(a.get("workspace_id"), workspace_id, norm_ws)
        ]
    if asset_type and isinstance(asset_type, str):
        results = [a for a in results if a.get("asset_type") == asset_type]
    return results


def delete_multimodal_asset(
    asset_id: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Safely deletes a generated multimodal asset with tenant isolation.
    Enforces Layer 2 Cross-Tenant IDOR Isolation: raises PermissionError if asset belongs to another non-default workspace.
    Guarantees thread-safe deletion under _multimodal_lock.
    """
    global _IN_MEMORY_MULTIMODAL
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    norm_asset_id = _normalize_uuid(asset_id, "asset_voice") or _normalize_uuid(asset_id, "asset_video") or asset_id

    # Paranoia Layer 2 IDOR check on in-memory store
    with _multimodal_lock:
        for a in _IN_MEMORY_MULTIMODAL:
            if a.get("id") in (asset_id, norm_asset_id):
                if _is_cross_workspace_prohibited(a.get("workspace_id"), workspace_id, norm_ws):
                    raise PermissionError("Cross-workspace access denied for multimodal asset")

    if supabase:
        try:
            chk = supabase.table("multimodal_assets").select("id, workspace_id").in_("id", [asset_id, norm_asset_id]).execute()
            if getattr(chk, "data", None):
                for row in chk.data:
                    if _is_cross_workspace_prohibited(row.get("workspace_id"), workspace_id, norm_ws):
                        raise PermissionError("Cross-workspace access denied for multimodal asset")
        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Could not verify asset ownership in DB: {e}")

    deleted_count = 0

    if supabase:
        try:
            res = supabase.table("multimodal_assets").delete().eq("id", norm_asset_id).execute()
            if getattr(res, "data", None):
                deleted_count += len(res.data)
        except Exception as e:
            logger.warning(f"Could not delete multimodal asset from DB: {e}")
            try:
                res = supabase.table("multimodal_assets").delete().eq("id", asset_id).execute()
                if getattr(res, "data", None):
                    deleted_count += len(res.data)
            except Exception:
                pass

    with _multimodal_lock:
        initial_len = len(_IN_MEMORY_MULTIMODAL)
        _IN_MEMORY_MULTIMODAL = [
            a for a in _IN_MEMORY_MULTIMODAL
            if a.get("id") not in (asset_id, norm_asset_id)
        ]
        if len(_IN_MEMORY_MULTIMODAL) < initial_len:
            deleted_count += (initial_len - len(_IN_MEMORY_MULTIMODAL))

        # Evict any matching synthesis locks
        for k in list(_ASSET_SYNTHESIS_LOCKS.keys()):
            if (_ASSET_SYNTHESIS_LOCKS[k].get("result") or {}).get("asset_id") in (asset_id, norm_asset_id):
                _ASSET_SYNTHESIS_LOCKS.pop(k, None)

    return {
        "status": "success",
        "asset_id": asset_id,
        "deleted": deleted_count > 0,
        "message": f"Successfully deleted multimodal asset {asset_id}."
    }


def resolve_multimodal_asset_for_execution(
    workspace_id: str,
    lead_name: str,
    company: str,
    title: Optional[str] = None,
    asset_type: str = "voice_script",  # "voice_script" or "video_card"
    tone: str = "casual_peer",
    event_name: Optional[str] = None,
    custom_pain_point: Optional[str] = None,
    video_topic: Optional[str] = None,
    supabase: Optional[Any] = None,
    media_url: Optional[str] = None,
    use_ai: bool = False,
    banned_phrases: Optional[str] = None,
    ai_model: str = "",
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Resolves multimodal personalized asset for sequence execution.
    - Layer 0: Synthesizes voice script or video card, generates event icebreaker if event_name provided.
    - Layer 1: Clamps duration (voice: 15-45s, video: 30-90s), enforces 1-hour bounded synthesis deduplication lock.
    - Layer 2: Sanitizes inputs against formula & prompt injection, enforces strict https:// URL schemes, strips banned phrases.
    """
    if asset_type not in ("voice_script", "video_card"):
        raise ValueError(f"Invalid asset_type: '{asset_type}'. Must be 'voice_script' or 'video_card'.")

    # Layer 2: Formula & prompt injection neutralization
    clean_lead = sanitize_prompt_injection(sanitize_text(lead_name))
    clean_comp = sanitize_prompt_injection(sanitize_text(company))
    clean_title = sanitize_prompt_injection(sanitize_text(title)) if title else None
    clean_event = sanitize_prompt_injection(sanitize_text(event_name)) if event_name else None
    clean_pain = sanitize_prompt_injection(sanitize_text(custom_pain_point)) if custom_pain_point else None
    clean_topic = sanitize_prompt_injection(sanitize_text(video_topic)) if video_topic else None

    if not clean_lead or not clean_comp:
        raise ValueError("Lead name and company cannot be empty.")

    # Layer 1 (Flaw 4.3): Thread-safe deduplication lock check (1 hour) incorporating asset_type
    lock_key = f"{workspace_id}:{lead_name}:{company}:{asset_type}"
    clean_lock_key = f"{workspace_id}:{clean_lead}:{clean_comp}:{asset_type}"
    now = datetime.now(timezone.utc)
    with _multimodal_lock:
        _evict_expired_synthesis_locks_locked(now)
        for k in (lock_key, clean_lock_key):
            if k in _ASSET_SYNTHESIS_LOCKS:
                lock_entry = _ASSET_SYNTHESIS_LOCKS[k]
                ts = lock_entry.get("timestamp", now)
                if isinstance(ts, datetime) and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if (now - ts).total_seconds() < 3600:
                    cached = dict(lock_entry["result"])
                    cached["duplicate_prevented"] = True
                    return cached

    # Layer 2: Validate explicit media_url if provided
    if media_url:
        clean_m = str(media_url).strip()
        parsed_m = urllib.parse.urlparse(clean_m)
        if parsed_m.scheme.lower() != "https" or any(clean_m.lower().startswith(bad) for bad in ("javascript:", "data:", "file:", "http:")):
            raise ValueError(f"Invalid media URL scheme. Strict https:// protocol required (rejected dangerous or unencrypted scheme '{parsed_m.scheme}').")

    # Layer 0 & 1: Synthesis with AI / template failover
    if asset_type == "voice_script":
        res = generate_voice_script(
            lead_name=clean_lead,
            company=clean_comp,
            title=clean_title,
            tone=tone or "casual_peer",
            custom_pain_point=clean_pain,
            workspace_id=workspace_id,
            supabase=supabase,
            use_ai=use_ai,
            banned_phrases=banned_phrases,
            ai_model=ai_model,
        )
        script_or_dm = res.get("script", "")
        raw_duration = res.get("estimated_duration_sec", 24)
        # Layer 1: Duration Clamping: 15–45s
        duration_sec = max(15, min(45, int(raw_duration)))
        final_media_url = media_url or res.get("media_url")
    else:  # video_card
        res = generate_video_prospecting_card(
            lead_name=clean_lead,
            company=clean_comp,
            video_topic=clean_topic or "Outbound Pipeline Teardown",
            workspace_id=workspace_id,
            supabase=supabase,
            banned_phrases=banned_phrases,
            media_url=clean_m if media_url else None,
        )
        script_or_dm = res.get("dm_copy", "")
        raw_duration = res.get("estimated_duration_sec", 58)
        # Layer 1: Duration Clamping: 30–90s
        duration_sec = max(30, min(90, int(raw_duration)))
        final_media_url = media_url or res.get("video_url") or res.get("media_url")

    # Layer 2: Validate final media URL scheme strictly
    if final_media_url:
        clean_f = str(final_media_url).strip()
        parsed_f = urllib.parse.urlparse(clean_f)
        if parsed_f.scheme.lower() != "https" or any(clean_f.lower().startswith(bad) for bad in ("javascript:", "data:", "file:", "http:")):
            raise ValueError(f"Invalid media URL: strict https:// required (rejected dangerous scheme '{parsed_f.scheme}').")

    # Layer 0: Event icebreaker
    clean_first = clean_lead.split()[0] if clean_lead else "there"
    if clean_event:
        icebreaker = f"{clean_first}, noticed you were also registered for {clean_event}! Would love to connect and share notes."
        if banned_phrases:
            try:
                from knowledge.backend.services.elein_ai_service import enforce_banned_phrases
                icebreaker = enforce_banned_phrases(icebreaker, banned_phrases)
            except Exception as bp_err:
                logger.warning(f"Could not enforce banned phrases on icebreaker: {bp_err}")
    else:
        icebreaker = None

    standardized_result = {
        "status": "ready",
        "asset_type": asset_type,
        "asset_id": res["asset_id"],
        "multimodal_script": script_or_dm,
        "multimodal_duration": duration_sec,
        "multimodal_asset_url": final_media_url,
        "event_icebreaker": icebreaker,
        "lock_acquired": True,
        "duplicate_prevented": False
    }

    # Store in deduplication locks under concurrency lock
    with _multimodal_lock:
        _ASSET_SYNTHESIS_LOCKS[lock_key] = {
            "timestamp": datetime.now(timezone.utc),
            "result": dict(standardized_result)
        }
        _ASSET_SYNTHESIS_LOCKS[clean_lock_key] = {
            "timestamp": datetime.now(timezone.utc),
            "result": dict(standardized_result)
        }
        _evict_expired_synthesis_locks_locked()

    return standardized_result


def export_multimodal_assets_csv(
    workspace_id: str,
    asset_type: Optional[str] = None,
    supabase: Optional[Any] = None
) -> str:
    """
    Paranoia Layer 0 & 2: Exports multimodal assets to formula-defended CSV stream.
    """
    assets = list_multimodal_assets(
        workspace_id=workspace_id,
        asset_type=asset_type,
        supabase=supabase
    )
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Asset ID",
        "Asset Type",
        "Status",
        "Estimated Duration (sec)",
        "Thumbnail / Title",
        "Media URL",
        "Script / Copy",
        "Created At"
    ])

    for a in assets:
        t_title = sanitize_text(a.get("thumbnail_text", ""))
        script = sanitize_text(a.get("script_text", ""))
        writer.writerow([
            a.get("id"),
            a.get("asset_type"),
            a.get("status", "ready"),
            a.get("estimated_duration_sec", 0),
            t_title,
            a.get("media_url") or "",
            script,
            a.get("created_at", "")
        ])

    return output.getvalue()

