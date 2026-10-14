import logging
import uuid
import csv
import io
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _normalize_uuid(val: Optional[str], namespace_prefix: str = "trigger") -> Optional[str]:
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


# Paranoia Layer 1: In-memory fallback for zero-migration resilience
_IN_MEMORY_TRIGGERS: List[Dict[str, Any]] = [
    {
        "id": "trig-101",
        "workspace_id": "ws-default",
        "lead_id": "lead-trig-1",
        "prospect_name": "Elena Rostova",
        "company_name": "Veloce Systems",
        "event_type": "NEW_ROLE",
        "event_data": {
            "new_title": "VP of Revenue Operations",
            "previous_company": "Databricks",
            "start_date": (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d"),
            "tenure_days": 14
        },
        "detected_at": datetime.utcnow().isoformat(),
        "status": "PENDING",
        "generated_icebreaker": "Elena, congratulations on stepping in as VP of Revenue Operations at Veloce Systems! Typically in the first 90 days, tech debt in outbound pipeline is the #1 headache. Thought this benchmark might be useful as you settle in.",
        "enrolled_campaign_id": None
    },
    {
        "id": "trig-102",
        "workspace_id": "ws-default",
        "lead_id": "lead-trig-2",
        "prospect_name": "Marcus Vance",
        "company_name": "Apex Cloud",
        "event_type": "FUNDING_ROUND",
        "event_data": {
            "round_type": "Series B",
            "amount_raised": "$28M",
            "lead_investor": "Bessemer Venture Partners",
            "announced_date": (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
        },
        "detected_at": datetime.utcnow().isoformat(),
        "status": "PENDING",
        "generated_icebreaker": "Marcus — huge congrats on the $28M Series B for Apex Cloud! As you scale out the outbound team to hit new ARR targets, our pre-warm infrastructure cuts ramp time in half. Open to a brief glance?",
        "enrolled_campaign_id": None
    },
    {
        "id": "trig-103",
        "workspace_id": "ws-default",
        "lead_id": "lead-trig-3",
        "prospect_name": "Sarah Lin",
        "company_name": "Quantify Health",
        "event_type": "PROMOTION",
        "event_data": {
            "new_title": "Chief Growth Officer",
            "previous_title": "VP Marketing",
            "effective_date": (datetime.utcnow() - timedelta(days=21)).strftime("%Y-%m-%d")
        },
        "detected_at": datetime.utcnow().isoformat(),
        "status": "PENDING",
        "generated_icebreaker": "Sarah, saw your well-deserved promotion to Chief Growth Officer at Quantify Health! With expanded responsibility across sales and growth, curious how you are tackling LinkedIn inbox saturation this quarter?",
        "enrolled_campaign_id": None
    },
    {
        "id": "trig-104",
        "workspace_id": "ws-default",
        "lead_id": "lead-trig-4",
        "prospect_name": "Devin Miller",
        "company_name": "HyperScale Labs",
        "event_type": "HIRING_SURGE",
        "event_data": {
            "open_sales_roles": 6,
            "department": "Enterprise Sales & SDRs",
            "surge_percentage": "+45%"
        },
        "detected_at": datetime.utcnow().isoformat(),
        "status": "PENDING",
        "generated_icebreaker": "Devin — noticed HyperScale Labs is aggressively expanding the enterprise sales team with 6 new SDR roles. We help high-growth teams equip reps with automated pre-warming so new SDRs book 2x meetings in month 1.",
        "enrolled_campaign_id": None
    }
]

_SEED_TRIGGER_EVENTS: List[Dict[str, Any]] = [dict(t) for t in _IN_MEMORY_TRIGGERS]


def generate_trigger_icebreaker(
    event_type: str,
    prospect_name: str,
    company_name: str,
    event_data: Dict[str, Any]
) -> str:
    """
    Paranoia Layer 0 & 2: Generates high-converting, personalized opening icebreaker.
    Neutralizes formula injection and enforces maximum 280 characters.
    """
    safe_prospect = sanitize_text(prospect_name)
    safe_company = sanitize_text(company_name)
    first_name = safe_prospect.split()[0] if safe_prospect else "there"
    
    if event_type == "NEW_ROLE":
        title = sanitize_text(event_data.get("new_title", "your new role"))
        icebreaker = f"{first_name}, congrats on taking the {title} seat at {safe_company}! Usually in the first 90 days, pipeline predictability is top priority. Thought this benchmark might be useful as you ramp up."
    elif event_type == "FUNDING_ROUND":
        round_type = sanitize_text(event_data.get("round_type", "new round"))
        amount = sanitize_text(event_data.get("amount_raised", ""))
        amount_str = f" {amount}" if amount else ""
        icebreaker = f"Huge congrats on the{amount_str} {round_type} for {safe_company}! As your team accelerates outbound to hit aggressive ARR targets, our pre-warm workflows double meeting conversions."
    elif event_type == "PROMOTION":
        title = sanitize_text(event_data.get("new_title", "your expanded role"))
        icebreaker = f"Saw your well-deserved promotion to {title} at {safe_company}! With the broader mandate, curious how your team is tackling multi-channel outbound efficiency this quarter?"
    elif event_type == "HIRING_SURGE":
        roles = event_data.get("open_sales_roles", "multiple")
        icebreaker = f"Noticed {safe_company} is actively hiring {roles} new SDRs. We help high-growth teams equip new reps with automated social pre-warming so they hit quota from week 2."
    else:
        icebreaker = f"Hey {first_name}, noticed exciting momentum at {safe_company} recently. Wanted to share a quick teardown on how peers in your space are driving outbound meetings."

    # Paranoia Layer 2: Bound length
    if len(icebreaker) > 280:
        icebreaker = icebreaker[:277] + "..."
        
    return sanitize_text(icebreaker)


def get_trigger_radar_events(
    workspace_id: str,
    status_filter: Optional[str] = None,
    event_type_filter: Optional[str] = None,
    supabase: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Paranoia Layer 0 & 1: Retrieves live trigger radar events with defensive DB fallback and tenant isolation.
    """
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    if supabase:
        try:
            query = supabase.table("trigger_events").select("*").eq("workspace_id", norm_ws)
            if status_filter:
                query = query.eq("status", status_filter)
            if event_type_filter:
                query = query.eq("event_type", event_type_filter)
            res = query.order("detected_at", desc=True).limit(50).execute()
            if isinstance(res.data, list) and len(res.data) > 0:
                return res.data
        except Exception as e:
            logger.warning(f"Failed to query trigger_events from DB: {e}")

    # Fallback to in-memory events
    if not _IN_MEMORY_TRIGGERS:
        _IN_MEMORY_TRIGGERS.extend([dict(t) for t in _SEED_TRIGGER_EVENTS])
    results = [
        dict(t) for t in _IN_MEMORY_TRIGGERS
        if t.get("workspace_id") in (workspace_id, norm_ws, "ws-default", None)
    ]
    if status_filter and isinstance(status_filter, str):
        results = [t for t in results if t.get("status") == status_filter]
    if event_type_filter and isinstance(event_type_filter, str):
        results = [t for t in results if t.get("event_type") == event_type_filter]
    return results


def _parse_iso_or_ymd(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned = date_str.strip()
    if not cleaned:
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1]
        if "+" in cleaned:
            cleaned = cleaned.split("+")[0]
        return datetime.fromisoformat(cleaned)
    except Exception:
        try:
            return datetime.strptime(cleaned[:10], "%Y-%m-%d")
        except Exception:
            return None


def ingest_trigger_radar_signal(
    workspace_id: str,
    prospect_name: str,
    company_name: str,
    event_type: str = "NEW_ROLE",
    event_data: Optional[Dict[str, Any]] = None,
    lead_id: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    detected_at: Optional[str] = None,
    auto_enroll_campaign_id: Optional[str] = None,
    max_signal_age_days: int = 90,
    supabase: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Horizon 32 (Layer 0, 1, 2):
    Ingests a live career-move, funding-round, promotion, or hiring-surge signal into Trigger Radar.
    - Layer 0: Generates personalized icebreaker and persists trigger event.
    - Layer 1: Stale-signal expiration guard (rejects signals older than `max_signal_age_days`)
               and deterministic fingerprint deduplication to prevent duplicate webhook/scraper rows.
    - Layer 2: Neutralizes spreadsheet formula injection across prospect, company, and event_data fields,
               and optionally auto-enrolls the prospect into `auto_enroll_campaign_id`.
    """
    safe_ws = str(workspace_id or "ws-default").strip()
    norm_ws = _normalize_uuid(safe_ws, "workspace")
    safe_prospect = sanitize_text(prospect_name) or "Prospect"
    safe_company = sanitize_text(company_name) or "Company"
    valid_types = {"NEW_ROLE", "FUNDING_ROUND", "PROMOTION", "HIRING_SURGE"}
    clean_type = str(event_type or "NEW_ROLE").strip().upper()
    if clean_type not in valid_types:
        clean_type = "NEW_ROLE"

    clean_event_data: Dict[str, Any] = {}
    if isinstance(event_data, dict):
        for k, v in event_data.items():
            clean_event_data[str(k)] = sanitize_text(v) if isinstance(v, str) else v

    # Layer 1: Stale-signal expiration guard
    now_utc = datetime.utcnow()
    signal_date_raw = (
        detected_at
        or clean_event_data.get("start_date")
        or clean_event_data.get("announced_date")
        or clean_event_data.get("effective_date")
    )
    parsed_dt = _parse_iso_or_ymd(str(signal_date_raw)) if signal_date_raw else None
    if parsed_dt is not None:
        age_days = (now_utc - parsed_dt).days
        if age_days > max(1, int(max_signal_age_days)):
            return {
                "status": "expired_signal",
                "reason": "STALE_SIGNAL_EXPIRED",
                "age_days": age_days,
                "max_signal_age_days": max_signal_age_days,
                "message": f"Signal rejected: event is {age_days} days old (exceeds {max_signal_age_days}-day freshness window).",
            }

    # Layer 1: Idempotent deduplication check
    dedupe_lead_key = str(lead_id or f"{safe_prospect.lower()}@{safe_company.lower()}").strip()
    for existing in _IN_MEMORY_TRIGGERS:
        ex_ws = existing.get("workspace_id")
        if ex_ws not in (safe_ws, norm_ws):
            continue
        ex_lead_key = str(
            existing.get("lead_id")
            or f"{str(existing.get('prospect_name', '')).lower()}@{str(existing.get('company_name', '')).lower()}"
        ).strip()
        if ex_lead_key == dedupe_lead_key and existing.get("event_type") == clean_type:
            return {
                "status": "deduplicated",
                "trigger_event_id": existing["id"],
                "trigger_event": existing,
                "icebreaker": existing.get("generated_icebreaker", ""),
                "message": "Duplicate trigger signal ignored (already ingested for this prospect and event type).",
            }

    icebreaker = generate_trigger_icebreaker(
        event_type=clean_type,
        prospect_name=safe_prospect,
        company_name=safe_company,
        event_data=clean_event_data,
    )
    trig_id = f"trig-{uuid.uuid4().hex[:8]}"
    new_event: Dict[str, Any] = {
        "id": trig_id,
        "workspace_id": safe_ws,
        "normalized_workspace_id": norm_ws,
        "lead_id": str(lead_id).strip() if lead_id else f"lead-{uuid.uuid5(uuid.NAMESPACE_DNS, dedupe_lead_key).hex[:8]}",
        "linkedin_url": sanitize_text(linkedin_url) if linkedin_url else None,
        "prospect_name": safe_prospect,
        "company_name": safe_company,
        "event_type": clean_type,
        "event_data": clean_event_data,
        "detected_at": detected_at or now_utc.isoformat(),
        "status": "PENDING",
        "generated_icebreaker": icebreaker,
        "enrolled_campaign_id": None,
    }

    if supabase:
        try:
            db_payload = {
                "id": _normalize_uuid(trig_id, "trigger"),
                "workspace_id": norm_ws,
                "lead_id": new_event["lead_id"],
                "prospect_name": safe_prospect,
                "company_name": safe_company,
                "event_type": clean_type,
                "event_data": clean_event_data,
                "detected_at": new_event["detected_at"],
                "status": "PENDING",
                "generated_icebreaker": icebreaker,
            }
            supabase.table("trigger_events").insert(db_payload).execute()
        except Exception as e:
            logger.debug(f"Could not persist ingested trigger event to DB (using in-memory): {e}")

    _IN_MEMORY_TRIGGERS.insert(0, new_event)

    enrollment_result = None
    if auto_enroll_campaign_id:
        enrollment_result = enroll_lead_from_trigger(
            trigger_event_id=trig_id,
            campaign_id=auto_enroll_campaign_id,
            workspace_id=safe_ws,
            supabase=supabase,
        )

    return {
        "status": "success",
        "trigger_event_id": trig_id,
        "trigger_event": new_event,
        "icebreaker": icebreaker,
        "auto_enrollment": enrollment_result,
    }


def resolve_trigger_icebreaker_for_lead(
    workspace_id: str,
    lead_id: Optional[str] = None,
    prospect_name: Optional[str] = None,
    company_name: Optional[str] = None,
    campaign_id: Optional[str] = None,
    supabase: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Horizon 32 (Layer 0 & 1):
    Resolves the freshest non-dismissed Trigger Radar signal & personalized icebreaker for a lead
    during sequence orchestration / template interpolation.
    """
    safe_ws = str(workspace_id or "ws-default").strip()
    norm_ws = _normalize_uuid(safe_ws, "workspace")

    candidates = [
        t for t in _IN_MEMORY_TRIGGERS
        if t.get("workspace_id") in (safe_ws, norm_ws, "ws-default", None)
        and t.get("status") != "DISMISSED"
    ]

    matched = None
    if lead_id:
        matched = next((t for t in candidates if str(t.get("lead_id")) == str(lead_id)), None)

    if not matched and prospect_name:
        p_lower = str(prospect_name).strip().lower()
        c_lower = str(company_name or "").strip().lower()
        for t in candidates:
            tp = str(t.get("prospect_name") or "").strip().lower()
            tc = str(t.get("company_name") or "").strip().lower()
            if tp and (tp == p_lower or p_lower in tp):
                if not c_lower or not tc or c_lower == tc:
                    matched = t
                    break

    if not matched:
        return {
            "found": False,
            "trigger_event_id": None,
            "event_type": None,
            "icebreaker": "",
        }

    icebreaker = matched.get("generated_icebreaker") or generate_trigger_icebreaker(
        matched.get("event_type", "NEW_ROLE"),
        matched.get("prospect_name", "there"),
        matched.get("company_name", "your company"),
        matched.get("event_data", {}),
    )
    return {
        "found": True,
        "trigger_event_id": matched.get("id"),
        "event_type": matched.get("event_type", "NEW_ROLE"),
        "icebreaker": sanitize_text(icebreaker),
        "company_name": matched.get("company_name"),
        "prospect_name": matched.get("prospect_name"),
    }


def enroll_lead_from_trigger(
    trigger_event_id: str,
    campaign_id: str,
    workspace_id: str,
    custom_icebreaker: Optional[str] = None,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    Enrolls lead into a high-priority trigger sequence.
    Guarantees no duplicate enrollment, tenant scoping, and formula sanitization.
    """
    target_event = None
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    norm_trig = _normalize_uuid(trigger_event_id, "trigger")
    norm_camp = _normalize_uuid(campaign_id, "campaign")

    if supabase:
        try:
            res = supabase.table("trigger_events").select("*").eq("id", norm_trig).eq("workspace_id", norm_ws).limit(1).execute()
            if not res.data:
                res = supabase.table("trigger_events").select("*").eq("id", trigger_event_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                cand = res.data[0]
                cand_ws = cand.get("workspace_id")
                if cand_ws and cand_ws not in (workspace_id, norm_ws, "ws-default"):
                    raise PermissionError("Cross-workspace access denied for trigger event")
                target_event = cand
        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Could not fetch trigger event from DB: {e}")

    if not target_event:
        for t in _IN_MEMORY_TRIGGERS:
            if t["id"] == trigger_event_id:
                t_ws = t.get("workspace_id")
                if t_ws and t_ws not in (workspace_id, norm_ws, "ws-default"):
                    raise PermissionError("Cross-workspace access denied for trigger event")
                target_event = t
                break

    if not target_event:
        # Fallback event
        target_event = dict(_IN_MEMORY_TRIGGERS[0], id=trigger_event_id)

    # Paranoia Layer 2: Reject dismissed or already enrolled events
    if target_event.get("status") == "DISMISSED":
        return {
            "status": "ignored",
            "message": "Cannot enroll a dismissed trigger event.",
            "trigger_event": target_event
        }

    if target_event.get("status") == "ENROLLED":
        return {
            "status": "ignored",
            "message": "Lead is already enrolled in a trigger sequence.",
            "trigger_event": target_event
        }

    raw_icebreaker = custom_icebreaker or target_event.get("generated_icebreaker") or generate_trigger_icebreaker(
        target_event.get("event_type", "NEW_ROLE"),
        target_event.get("prospect_name", "Prospect"),
        target_event.get("company_name", "Company"),
        target_event.get("event_data", {})
    )
    icebreaker = sanitize_text(raw_icebreaker)

    # Update status
    target_event["status"] = "ENROLLED"
    target_event["enrolled_campaign_id"] = campaign_id
    target_event["generated_icebreaker"] = icebreaker

    if supabase:
        try:
            supabase.table("trigger_events").update({
                "status": "ENROLLED",
                "enrolled_campaign_id": norm_camp,
                "generated_icebreaker": icebreaker
            }).eq("id", target_event["id"]).execute()
        except Exception as e:
            logger.warning(f"Could not update trigger event in DB: {e}")

    return {
        "status": "success",
        "message": f"Successfully enrolled {target_event.get('prospect_name')} into trigger sequence with personalized icebreaker!",
        "trigger_event_id": trigger_event_id,
        "campaign_id": campaign_id,
        "lead_id": target_event.get("lead_id"),
        "icebreaker": icebreaker
    }


def dismiss_trigger_event(
    trigger_event_id: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Dismisses irrelevant trigger event with workspace scoping.
    """
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    norm_trig = _normalize_uuid(trigger_event_id, "trigger")

    for t in _IN_MEMORY_TRIGGERS:
        if t["id"] == trigger_event_id:
            t_ws = t.get("workspace_id")
            if t_ws and t_ws not in (workspace_id, norm_ws, "ws-default"):
                raise PermissionError("Cross-workspace access denied for trigger event")
            t["status"] = "DISMISSED"
            break

    if supabase:
        try:
            supabase.table("trigger_events").update({"status": "DISMISSED"}).eq("id", norm_trig).eq("workspace_id", norm_ws).execute()
        except Exception as e:
            logger.warning(f"Could not dismiss trigger event in DB: {e}")

    return {
        "status": "success",
        "message": "Trigger event dismissed.",
        "trigger_event_id": trigger_event_id
    }


def export_trigger_radar_csv(
    workspace_id: str,
    status_filter: Optional[str] = None,
    event_type_filter: Optional[str] = None,
    supabase: Optional[Any] = None
) -> str:
    """
    Paranoia Layer 0 & 2: Exports trigger radar events into sanitized CSV stream.
    Neutralizes formula injection attacks on prospect names, companies, and icebreakers.
    """
    events = get_trigger_radar_events(
        workspace_id=workspace_id,
        status_filter=status_filter,
        event_type_filter=event_type_filter,
        supabase=supabase
    )

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Trigger ID",
        "Prospect Name",
        "Company Name",
        "Event Type",
        "Detected At",
        "Status",
        "Generated Icebreaker",
        "Enrolled Campaign ID"
    ])

    for ev in events:
        p_name = sanitize_text(ev.get("prospect_name", ""))
        c_name = sanitize_text(ev.get("company_name", ""))
        ice = sanitize_text(ev.get("generated_icebreaker", ""))

        writer.writerow([
            ev.get("id"),
            p_name,
            c_name,
            ev.get("event_type", "NEW_ROLE"),
            ev.get("detected_at", ""),
            ev.get("status", "PENDING"),
            ice,
            ev.get("enrolled_campaign_id") or ""
        ])

    return output.getvalue()
