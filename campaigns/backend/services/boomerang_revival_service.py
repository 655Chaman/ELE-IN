import uuid
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Paranoia Layer 1: In-memory fallback datasets for zero-migration resilience
_IN_MEMORY_JOB_CHANGES: List[Dict[str, Any]] = [
    {
        "id": "jc-101",
        "workspace_id": "ws-default",
        "lead_id": "lead-jc-1",
        "prospect_name": "Sophia Reynolds",
        "linkedin_url": "https://linkedin.com/in/sophia-reynolds-cro",
        "previous_company": "Twilio",
        "previous_title": "Director of Sales Operations",
        "new_company": "Vercel",
        "new_title": "VP of Global Revenue Operations",
        "new_domain": "vercel.com",
        "relationship_type": "past_customer",
        "days_in_new_role": 28,
        "buying_window_score": 96,
        "is_internal_promotion": False,
        "playbook_message": (
            "Hi Sophia — huge congrats on stepping into the VP of Global Revenue Operations role at Vercel! "
            "Loved partnering with you during your time at Twilio when your team scaled outbound conversion by 3.2x.\n\n"
            "As you audit the GTM stack in your first 90 days at Vercel, I'd love to share our new ABM Buying Committee "
            "and Autonomous Multithreading playbook. Open to a quick 10-minute catch-up next week?"
        ),
        "status": "playbook_drafted",
        "detected_at": datetime.utcnow().isoformat()
    },
    {
        "id": "jc-102",
        "workspace_id": "ws-default",
        "lead_id": "lead-jc-2",
        "prospect_name": "Marcus Chen",
        "linkedin_url": "https://linkedin.com/in/marcus-chen-growth",
        "previous_company": "Plaid",
        "previous_title": "Head of Outbound SDRs",
        "new_company": "Ramp",
        "new_title": "VP of Enterprise Growth",
        "new_domain": "ramp.com",
        "relationship_type": "former_champion",
        "days_in_new_role": 42,
        "buying_window_score": 91,
        "is_internal_promotion": False,
        "playbook_message": (
            "Hi Marcus — thrilled to see your move from Plaid to VP of Enterprise Growth at Ramp! "
            "Since you championed our outbound workflows at Plaid, I wanted to put a quick blueprint on your radar "
            "for your first-quarter pipeline goals at Ramp.\n\n"
            "Whenever you're settled in, let's grab 10 minutes to replicate your Plaid playbook for the Ramp team!"
        ),
        "status": "detected",
        "detected_at": datetime.utcnow().isoformat()
    },
    {
        "id": "jc-103",
        "workspace_id": "ws-default",
        "lead_id": "lead-jc-3",
        "prospect_name": "Hannah Abbott",
        "linkedin_url": "https://linkedin.com/in/hannah-abbott-sales",
        "previous_company": "Figma",
        "previous_title": "Senior Sales Manager",
        "new_company": "Linear",
        "new_title": "Head of Commercial Sales",
        "new_domain": "linear.app",
        "relationship_type": "power_user",
        "days_in_new_role": 19,
        "buying_window_score": 88,
        "is_internal_promotion": False,
        "playbook_message": (
            "Hi Hannah — congrats on the new role as Head of Commercial Sales at Linear! "
            "You were one of our sharpest power users at Figma. We'd love to give you VIP sandbox access "
            "for your new team at Linear as you build out your outbound motion."
        ),
        "status": "detected",
        "detected_at": datetime.utcnow().isoformat()
    }
]

_IN_MEMORY_WARM_PATHS: List[Dict[str, Any]] = [
    {
        "id": "wp-201",
        "workspace_id": "ws-default",
        "target_prospect_name": "Victor Krum",
        "target_company": "Anthropic",
        "target_title": "Head of Enterprise GTM",
        "connector_name": "Elena Rostova",
        "connector_role": "VP of Revenue Operations at Stripe",
        "bridge_type": "shared_alumni",
        "overlap_context": "Overlapped at Stripe (2021–2024) on the Enterprise Revenue Leadership team",
        "warmth_score": 92,
        "intro_request_draft": (
            "Hi Elena — hope all is great at Stripe! Notice you overlapped closely with Victor Krum during your "
            "2021–2024 Enterprise Revenue run before he joined Anthropic as Head of Enterprise GTM.\n\n"
            "Would you feel comfortable making a quick 2-line email or LinkedIn intro? Happy to send a forwardable blurb!"
        ),
        "direct_bridge_draft": (
            "Hi Victor — Elena Rostova and I were recently discussing enterprise multithreading benchmarks from your shared "
            "Stripe Revenue days (2021–2024), and your name came up.\n\n"
            "Given how rapidly Anthropic's enterprise GTM is scaling, I'd love to share how top AI-native teams are "
            "automating buying-committee consensus. Open to a brief 10-minute chat?"
        ),
        "status": "available",
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "id": "wp-202",
        "workspace_id": "ws-default",
        "target_prospect_name": "Natalie Port",
        "target_company": "Scale AI",
        "target_title": "Chief Revenue Officer",
        "connector_name": "David Kim",
        "connector_role": "General Partner at Index Ventures",
        "bridge_type": "shared_investor",
        "overlap_context": "Shared Series B/C portfolio board advisor via Index Ventures GTM Network",
        "warmth_score": 95,
        "intro_request_draft": (
            "Hi David — we're seeing 3.4x pipeline velocity gains across several portfolio GTM teams. "
            "Would you mind connecting me with Natalie Port (CRO at Scale AI) so we can share the benchmark teardown?"
        ),
        "direct_bridge_draft": (
            "Hi Natalie — reaching out through the Index Ventures GTM network (connected via David Kim). "
            "We've been helping fellow portfolio CROs cut outbound CAC by 42% using autonomous buying committee orchestration. "
            "Worth a 10-minute look for Scale AI's Q4 push?"
        ),
        "status": "available",
        "created_at": datetime.utcnow().isoformat()
    }
]

_IN_MEMORY_REVIVALS: List[Dict[str, Any]] = [
    {
        "id": "rev-301",
        "workspace_id": "ws-default",
        "prospect_name": "lucas.g@Notion.so (Lucas Graham)",
        "company_name": "Notion",
        "title": "VP of Global Sales",
        "lost_reason": "missing_feature",
        "days_since_lost": 115,
        "original_deal_value": 48000,
        "revival_trigger": "Shipped Phase 14 ABM Buying Committee Orchestrator & Staggered Domain Protection",
        "revival_score": 94,
        "resurrection_message": (
            "Hi Lucas — when we paused conversations ~4 months ago at Notion, the key blocker was needing "
            "multi-contact ABM committee orchestration with domain-safe staggered sending.\n\n"
            "Wanted to circle back with good news: we just shipped our Autonomous ABM Buying Committee Studio "
            "(Phase 14) built around the exact workflow your team requested. Open to a 10-minute look this Thursday?"
        ),
        "status": "ready_to_revive",
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "id": "rev-302",
        "workspace_id": "ws-default",
        "prospect_name": "Rachel Zane",
        "company_name": "Airtable",
        "title": "Chief Financial Officer",
        "lost_reason": "budget_freeze",
        "days_since_lost": 140,
        "original_deal_value": 65000,
        "revival_trigger": "New Fiscal Half Budget Reset + Verified 42% CAC Reduction Certificate",
        "revival_score": 89,
        "resurrection_message": (
            "Hi Rachel — back when we spoke 4.5 months ago, Airtable was holding off on new GTM tooling due to a mid-year budget freeze.\n\n"
            "With the new fiscal planning window underway, we've rolled out a Self-Funding ROI Guarantee that consolidates 3 separate "
            "SDR subscriptions into one platform. Would love to share the 1-page CFO payback model if timing is better now?"
        ),
        "status": "ready_to_revive",
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "id": "rev-303",
        "workspace_id": "ws-default",
        "prospect_name": "Trevor Philips",
        "company_name": "Miro",
        "title": "Director of Outbound Pipeline",
        "lost_reason": "competitor_chosen",
        "days_since_lost": 165,
        "original_deal_value": 32000,
        "revival_trigger": "6-Month Competitor Renewal Checkpoint + Thompson Sampling MAB Copy Engine",
        "revival_score": 78,
        "resurrection_message": (
            "Hi Trevor — no agenda here, just checking in ~6 months after you went with another vendor for Miro's outbound sequences.\n\n"
            "Usually around the 6-month mark, teams either love their setup or run into LinkedIn rate-limit bans and flat reply rates. "
            "If you're evaluating options ahead of renewal, happy to show you our residential proxy pods and Bayesian bandit engine."
        ),
        "status": "ready_to_revive",
        "created_at": datetime.utcnow().isoformat()
    }
]


# Paranoia Layer 1: Idempotent duplicate-enrollment lock registry
_ENROLLED_BOOMERANG_LOCKS: Dict[str, Dict[str, Any]] = {}


def _sanitize_boomerang_text(val: Optional[str], max_len: int = 240) -> str:
    """
    Paranoia Layer 2: Strips control characters and neutralizes leading spreadsheet
    formula injection characters (=, +, -, @, \t, \r) to prevent CSV/CRM export execution.
    """
    if not val:
        return ""
    cleaned = "".join(ch for ch in str(val) if ch >= " " or ch in ("\n",)).strip()
    while cleaned and cleaned[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
        cleaned = cleaned[1:].strip()
    return cleaned[:max_len]


def calculate_boomerang_buying_window(
    prospect_name: str,
    previous_company: str,
    previous_title: str,
    new_company: str,
    new_title: str,
    days_in_new_role: int = 21,
    relationship_type: str = "former_champion"
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Computes the Executive First-90-Days Buying Window Score (0-100)
    and synthesizes a tailored Boomerang Playbook Message.
    Layer 2 Human Paranoia: Detects internal company promotions (previous_company == new_company)
    so the outreach never embarrassingly says "Congrats on leaving X to join X!".
    """
    safe_days = max(1, int(days_in_new_role or 14))
    clean_prev_co = _sanitize_boomerang_text(previous_company) or "your previous company"
    clean_new_co = _sanitize_boomerang_text(new_company) or "your new company"
    clean_prev_title = _sanitize_boomerang_text(previous_title) or "Leader"
    clean_new_title = _sanitize_boomerang_text(new_title) or "Executive"
    clean_prospect = _sanitize_boomerang_text(prospect_name) or "there"
    clean_first = clean_prospect.split()[0]

    is_internal = clean_prev_co.lower() == clean_new_co.lower()

    # 1. Tenure window score (First 15-60 days is peak executive budget allocation)
    if 15 <= safe_days <= 60:
        window_pts = 40
    elif 1 <= safe_days < 15:
        window_pts = 32
    elif 61 <= safe_days <= 90:
        window_pts = 26
    else:
        window_pts = 12

    # 2. Past relationship strength
    rel_weights = {
        "past_customer": 35,
        "former_champion": 30,
        "power_user": 25,
        "closed_lost_contact": 18
    }
    rel_pts = rel_weights.get(relationship_type, 25)

    # 3. Executive seniority authority in new title
    t_lower = clean_new_title.lower()
    if any(k in t_lower for k in ["chief", "cro", "cfo", "ceo", "coo", "vp", "vice president", "head", "president"]):
        seniority_pts = 25
    elif any(k in t_lower for k in ["director", "lead", "principal"]):
        seniority_pts = 18
    else:
        seniority_pts = 10

    total_score = min(100, max(10, window_pts + rel_pts + seniority_pts))

    # Generate Playbook Copy
    if is_internal:
        playbook_msg = (
            f"Hi {clean_first} — huge congrats on your internal promotion from {clean_prev_title} to {clean_new_title} at {clean_new_co}! "
            f"Well-deserved recognition of the impact you've driven.\n\n"
            f"With your expanded scope in the new role, I'd love to share how we can support your broader Q3/Q4 pipeline goals "
            f"at {clean_new_co}. Open to a quick 10-minute strategy sync next week?"
        )
    elif relationship_type == "past_customer":
        playbook_msg = (
            f"Hi {clean_first} — huge congrats on stepping into the {clean_new_title} role at {clean_new_co}! "
            f"Loved partnering with you during your time at {clean_prev_co}.\n\n"
            f"As you audit the GTM stack in your first 90 days at {clean_new_co}, I'd love to offer VIP alumni onboarding "
            f"and walk through our newest autonomous multithreading capabilities. Open to a quick 10-minute catch-up?"
        )
    elif relationship_type == "closed_lost_contact":
        playbook_msg = (
            f"Hi {clean_first} — congrats on the move from {clean_prev_co} to {clean_new_title} at {clean_new_co}! "
            f"We crossed paths back at {clean_prev_co} when timing wasn't quite right.\n\n"
            f"Now that you're building out your playbook at {clean_new_co}, would love to show you what's new "
            f"and see if we can help accelerate your early wins."
        )
    else:
        playbook_msg = (
            f"Hi {clean_first} — thrilled to see your move from {clean_prev_co} to {clean_new_title} at {clean_new_co}! "
            f"Since you championed modern outbound workflows at {clean_prev_co}, I wanted to put a quick 90-day quick-win blueprint "
            f"on your radar for {clean_new_co}.\n\n"
            f"Whenever you're settled in, let's grab 10 minutes!"
        )

    return {
        "buying_window_score": total_score,
        "is_internal_promotion": is_internal,
        "days_in_new_role": safe_days,
        "relationship_type": relationship_type,
        "playbook_message": playbook_msg,
        "window_tier": "PEAK_90_DAY" if safe_days <= 90 else "ESTABLISHED"
    }


def generate_warm_intro_bridge(
    target_prospect_name: str,
    target_company: str,
    target_title: str,
    connector_name: str,
    connector_role: str,
    bridge_type: str = "shared_alumni",
    overlap_context: str = "Shared executive tenure"
) -> Dict[str, Any]:
    """
    Paranoia Layer 0: Synthesizes dual warm-introduction scripts:
    1) intro_request_draft (Sent to the Mutual Connector to ask for a forwardable intro)
    2) direct_bridge_draft (Sent directly to the Target Prospect referencing the shared bridge)
    """
    clean_target_name = _sanitize_boomerang_text(target_prospect_name) or "there"
    clean_target_co = _sanitize_boomerang_text(target_company) or "their company"
    clean_target_title = _sanitize_boomerang_text(target_title) or "Executive"
    clean_conn_name = _sanitize_boomerang_text(connector_name) or "there"
    clean_conn_role = _sanitize_boomerang_text(connector_role) or "Leader"
    clean_overlap = _sanitize_boomerang_text(overlap_context, max_len=300) or "Shared executive tenure"

    target_first = clean_target_name.split()[0]
    connector_first = clean_conn_name.split()[0]

    type_scores = {
        "board_member": 96,
        "shared_investor": 93,
        "mutual_connection": 88,
        "shared_alumni": 84
    }
    warmth_score = type_scores.get(bridge_type, 85)

    intro_request_draft = (
        f"Hi {connector_first} — hope all is going great! I noticed you and {clean_target_name} "
        f"({clean_target_title} at {clean_target_co}) share a strong connection ({clean_overlap}).\n\n"
        f"We're helping peer {clean_target_co} teams accelerate enterprise pipeline by 3.4x. "
        f"Would you feel comfortable making a quick 2-line intro to {target_first}? Happy to send a forwardable blurb so it takes 10 seconds!"
    )

    direct_bridge_draft = (
        f"Hi {target_first} — noticed your shared background with {clean_conn_name} ({clean_conn_role}) via {clean_overlap}.\n\n"
        f"Given your focus as {clean_target_title} at {clean_target_co}, I wanted to share how fellow GTM leaders in our network "
        f"are orchestrating multithreaded outbound without adding SDR headcount. Open to a brief 10-minute exchange?"
    )

    return {
        "warmth_score": warmth_score,
        "bridge_type": bridge_type,
        "intro_request_draft": intro_request_draft,
        "direct_bridge_draft": direct_bridge_draft
    }


def evaluate_closed_lost_revival(
    prospect_name: str,
    company_name: str,
    title: str,
    lost_reason: str = "bad_timing",
    days_since_lost: int = 120,
    original_deal_value: float = 25000.0,
    revival_trigger: Optional[str] = None,
    force_override: bool = False
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Evaluates Closed-Lost Deal Resurrection readiness and crafts a No-Guilt Revival Message.
    Layer 2 Anti-Pestering Guard: Blocks reviving deals lost fewer than 14 days ago unless force_override=True.
    """
    safe_days = int(days_since_lost if days_since_lost is not None else 120)
    if safe_days < 14 and not force_override:
        raise ValueError(
            "Anti-Pestering Guard: Deal was marked Closed-Lost fewer than 14 days ago. "
            "Premature revival risks permanent prospect churn and domain complaints."
        )

    clean_prospect = _sanitize_boomerang_text(prospect_name) or "there"
    clean_first = clean_prospect.split()[0]
    clean_company = _sanitize_boomerang_text(company_name) or "your company"
    trigger_text = _sanitize_boomerang_text(revival_trigger, max_len=300) or "Major Platform Capability & ROI Payback Update"

    # Calculate revival score
    if 75 <= safe_days <= 180:
        timing_pts = 45
    elif safe_days > 180:
        timing_pts = 32
    else:
        timing_pts = 20

    reason_weights = {
        "missing_feature": 45,
        "budget_freeze": 42,
        "bad_timing": 40,
        "ghosted_no_decision": 32,
        "competitor_chosen": 28
    }
    reason_pts = reason_weights.get(lost_reason, 35)
    revival_score = min(99, max(15, timing_pts + reason_pts))

    months_ago = max(1, round(safe_days / 30))

    if lost_reason == "missing_feature":
        msg = (
            f"Hi {clean_first} — when we paused conversations ~{months_ago} months ago at {clean_company}, "
            f"we were missing a key capability on your checklist.\n\n"
            f"Wanted to circle back with good news: we just shipped [{trigger_text}], built around the exact workflow "
            f"your team asked for. Open to a 10-minute look this week?"
        )
    elif lost_reason == "budget_freeze":
        msg = (
            f"Hi {clean_first} — when we spoke ~{months_ago} months ago, {clean_company} was navigating a temporary budget freeze.\n\n"
            f"With the new planning window open and [{trigger_text}], we're helping teams consolidate 3 legacy GTM tools "
            f"to cut net spend while boosting pipeline 3.4x. Worth a quick 10-minute revisit?"
        )
    elif lost_reason == "competitor_chosen":
        msg = (
            f"Hi {clean_first} — no agenda here, just checking in ~{months_ago} months after {clean_company} selected another tool.\n\n"
            f"Usually at this milestone, teams either love their setup or hit deliverability ceilings. "
            f"With [{trigger_text}], we're offering a zero-cost side-by-side benchmark ahead of your renewal window."
        )
    else:  # bad_timing or ghosted_no_decision
        msg = (
            f"Hi {clean_first} — we spoke ~{months_ago} months ago about scaling {clean_company}'s outbound pipeline, "
            f"but timing wasn't ideal given competing priorities.\n\n"
            f"Since then, we launched [{trigger_text}] and helped peer teams double their meeting conversion rates. "
            f"Is this back on your radar for this quarter?"
        )

    return {
        "revival_score": revival_score,
        "days_since_lost": safe_days,
        "lost_reason": lost_reason,
        "original_deal_value": float(original_deal_value),
        "revival_trigger": trigger_text,
        "resurrection_message": msg
    }


def list_champion_job_changes(
    workspace_id: str,
    supabase: Optional[Any] = None,
    relationship_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Paranoia Layer 1 & 2: Lists tracked champion job changes with zero-migration fallback
    and Cross-Tenant IDOR isolation.
    """
    records = []
    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            q = supabase.table("champion_job_changes").select("*").eq("workspace_id", workspace_id)
            if relationship_filter:
                q = q.eq("relationship_type", relationship_filter)
            res = q.order("buying_window_score", desc=True).execute()
            if res.data:
                records = res.data
        except Exception as e:
            logger.warning("Supabase champion_job_changes query failed (using in-memory fallback): %s", e)

    if not records:
        records = [
            dict(r) for r in _IN_MEMORY_JOB_CHANGES
            if r.get("workspace_id") in (None, "ws-default", workspace_id)
        ]
        if relationship_filter:
            records = [r for r in records if r.get("relationship_type") == relationship_filter]

    return sorted(records, key=lambda x: x.get("buying_window_score", 0), reverse=True)


def create_champion_job_change(
    workspace_id: str,
    prospect_name: str,
    previous_company: str,
    previous_title: str,
    new_company: str,
    new_title: str,
    relationship_type: str = "former_champion",
    days_in_new_role: int = 21,
    linkedin_url: Optional[str] = None,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Registers a champion job change, computes the First-90-Days Buying Window score, and persists with fallback.
    """
    clean_prospect = _sanitize_boomerang_text(prospect_name)
    clean_prev_co = _sanitize_boomerang_text(previous_company)
    clean_prev_title = _sanitize_boomerang_text(previous_title)
    clean_new_co = _sanitize_boomerang_text(new_company)
    clean_new_title = _sanitize_boomerang_text(new_title)

    calc = calculate_boomerang_buying_window(
        prospect_name=clean_prospect,
        previous_company=clean_prev_co,
        previous_title=clean_prev_title,
        new_company=clean_new_co,
        new_title=clean_new_title,
        days_in_new_role=days_in_new_role,
        relationship_type=relationship_type
    )

    record = {
        "id": f"jc-{uuid.uuid4().hex[:8]}",
        "workspace_id": workspace_id,
        "prospect_name": clean_prospect,
        "linkedin_url": _sanitize_boomerang_text(linkedin_url) or f"https://linkedin.com/in/{clean_prospect.lower().replace(' ', '-')}",
        "previous_company": clean_prev_co,
        "previous_title": clean_prev_title,
        "new_company": clean_new_co,
        "new_title": clean_new_title,
        "new_domain": f"{clean_new_co.lower().replace(' ', '')}.com",
        "relationship_type": calc["relationship_type"],
        "days_in_new_role": calc["days_in_new_role"],
        "buying_window_score": calc["buying_window_score"],
        "is_internal_promotion": calc["is_internal_promotion"],
        "playbook_message": calc["playbook_message"],
        "status": "playbook_drafted",
        "detected_at": datetime.utcnow().isoformat()
    }

    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            res = supabase.table("champion_job_changes").insert(record).execute()
            if res.data and len(res.data) > 0:
                record = res.data[0]
        except Exception as e:
            logger.warning("Supabase champion_job_changes insert failed (storing in-memory): %s", e)

    _IN_MEMORY_JOB_CHANGES.insert(0, record)
    return record


def list_warm_intro_paths(
    workspace_id: str,
    supabase: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Lists mutual connection and shared-alumni warm introduction paths with Cross-Tenant IDOR isolation.
    """
    records = []
    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            res = supabase.table("warm_intro_paths").select("*").eq("workspace_id", workspace_id).order("warmth_score", desc=True).execute()
            if res.data:
                records = res.data
        except Exception as e:
            logger.warning("Supabase warm_intro_paths query failed (using in-memory fallback): %s", e)

    if not records:
        records = [
            dict(r) for r in _IN_MEMORY_WARM_PATHS
            if r.get("workspace_id") in (None, "ws-default", workspace_id)
        ]

    return sorted(records, key=lambda x: x.get("warmth_score", 0), reverse=True)


def create_warm_intro_path(
    workspace_id: str,
    target_prospect_name: str,
    target_company: str,
    target_title: str,
    connector_name: str,
    connector_role: str,
    bridge_type: str = "shared_alumni",
    overlap_context: str = "Shared executive tenure",
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Creates a new warm intro path with dual scripts (connector request vs. direct shared-alumni outreach).
    """
    clean_target_name = _sanitize_boomerang_text(target_prospect_name)
    clean_target_co = _sanitize_boomerang_text(target_company)
    clean_target_title = _sanitize_boomerang_text(target_title)
    clean_conn_name = _sanitize_boomerang_text(connector_name)
    clean_conn_role = _sanitize_boomerang_text(connector_role)
    clean_overlap = _sanitize_boomerang_text(overlap_context, max_len=300)

    bridge = generate_warm_intro_bridge(
        target_prospect_name=clean_target_name,
        target_company=clean_target_co,
        target_title=clean_target_title,
        connector_name=clean_conn_name,
        connector_role=clean_conn_role,
        bridge_type=bridge_type,
        overlap_context=clean_overlap
    )

    record = {
        "id": f"wp-{uuid.uuid4().hex[:8]}",
        "workspace_id": workspace_id,
        "target_prospect_name": clean_target_name,
        "target_company": clean_target_co,
        "target_title": clean_target_title,
        "connector_name": clean_conn_name,
        "connector_role": clean_conn_role,
        "bridge_type": bridge["bridge_type"],
        "overlap_context": clean_overlap,
        "warmth_score": bridge["warmth_score"],
        "intro_request_draft": bridge["intro_request_draft"],
        "direct_bridge_draft": bridge["direct_bridge_draft"],
        "status": "available",
        "created_at": datetime.utcnow().isoformat()
    }

    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            res = supabase.table("warm_intro_paths").insert(record).execute()
            if res.data and len(res.data) > 0:
                record = res.data[0]
        except Exception as e:
            logger.warning("Supabase warm_intro_paths insert failed (storing in-memory): %s", e)

    _IN_MEMORY_WARM_PATHS.insert(0, record)
    return record


def list_closed_lost_revivals(
    workspace_id: str,
    supabase: Optional[Any] = None,
    reason_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Lists Closed-Lost deal revival opportunities sorted by revival readiness score with Cross-Tenant IDOR isolation.
    """
    records = []
    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            q = supabase.table("closed_lost_revivals").select("*").eq("workspace_id", workspace_id)
            if reason_filter:
                q = q.eq("lost_reason", reason_filter)
            res = q.order("revival_score", desc=True).execute()
            if res.data:
                records = res.data
        except Exception as e:
            logger.warning("Supabase closed_lost_revivals query failed (using in-memory fallback): %s", e)

    if not records:
        records = [
            dict(r) for r in _IN_MEMORY_REVIVALS
            if r.get("workspace_id") in (None, "ws-default", workspace_id)
        ]
        if reason_filter:
            records = [r for r in records if r.get("lost_reason") == reason_filter]

    return sorted(records, key=lambda x: x.get("revival_score", 0), reverse=True)


def create_closed_lost_revival(
    workspace_id: str,
    prospect_name: str,
    company_name: str,
    title: str,
    lost_reason: str = "bad_timing",
    days_since_lost: int = 120,
    original_deal_value: float = 25000.0,
    revival_trigger: Optional[str] = None,
    force_override: bool = False,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Creates a Closed-Lost revival opportunity after passing the Anti-Pestering Cooldown Guard.
    """
    clean_prospect = _sanitize_boomerang_text(prospect_name)
    clean_company = _sanitize_boomerang_text(company_name)
    clean_title = _sanitize_boomerang_text(title)
    clean_trigger = _sanitize_boomerang_text(revival_trigger, max_len=300) if revival_trigger else None

    eval_res = evaluate_closed_lost_revival(
        prospect_name=clean_prospect,
        company_name=clean_company,
        title=clean_title,
        lost_reason=lost_reason,
        days_since_lost=days_since_lost,
        original_deal_value=original_deal_value,
        revival_trigger=clean_trigger,
        force_override=force_override
    )

    record = {
        "id": f"rev-{uuid.uuid4().hex[:8]}",
        "workspace_id": workspace_id,
        "prospect_name": clean_prospect,
        "company_name": clean_company,
        "title": clean_title,
        "lost_reason": eval_res["lost_reason"],
        "days_since_lost": eval_res["days_since_lost"],
        "original_deal_value": eval_res["original_deal_value"],
        "revival_trigger": eval_res["revival_trigger"],
        "revival_score": eval_res["revival_score"],
        "resurrection_message": eval_res["resurrection_message"],
        "status": "ready_to_revive",
        "created_at": datetime.utcnow().isoformat()
    }

    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            res = supabase.table("closed_lost_revivals").insert(record).execute()
            if res.data and len(res.data) > 0:
                record = res.data[0]
        except Exception as e:
            logger.warning("Supabase closed_lost_revivals insert failed (storing in-memory): %s", e)

    _IN_MEMORY_REVIVALS.insert(0, record)
    return record


def enroll_boomerang_or_revival(
    workspace_id: str,
    item_id: str,
    item_type: str = "job_change",
    campaign_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enrolls a job-change boomerang, warm intro, or closed-lost deal revival into an active outreach sequence.
    Enforces Layer 2 Cross-Tenant IDOR Isolation and Layer 1 Idempotent Duplicate-Enrollment Lock.
    """
    target_campaign = campaign_id or f"camp-boomerang-{item_id}"
    lock_key = f"{workspace_id}:{item_id}:{target_campaign}"

    # Locate item and enforce Layer 2 Cross-Tenant IDOR Isolation
    matched_item = None
    if item_type == "job_change":
        for jc in _IN_MEMORY_JOB_CHANGES:
            if jc["id"] == item_id:
                matched_item = jc
                break
    elif item_type == "warm_intro":
        for wp in _IN_MEMORY_WARM_PATHS:
            if wp["id"] == item_id:
                matched_item = wp
                break
    elif item_type in ("revival", "closed_lost_revival"):
        for rev in _IN_MEMORY_REVIVALS:
            if rev["id"] == item_id:
                matched_item = rev
                break

    if matched_item is not None:
        item_ws = matched_item.get("workspace_id")
        if item_ws not in (None, "ws-default", workspace_id):
            raise PermissionError("Cross-workspace access denied for Boomerang item")

    # Layer 1: Idempotent Duplicate-Enrollment Lock
    tuple_key = (workspace_id, item_id, target_campaign)
    if lock_key in _ENROLLED_BOOMERANG_LOCKS or tuple_key in _ENROLLED_BOOMERANG_LOCKS:
        existing = dict(_ENROLLED_BOOMERANG_LOCKS.get(lock_key) or _ENROLLED_BOOMERANG_LOCKS.get(tuple_key))
        existing["duplicate_prevented"] = True
        return existing

    updated = False
    if matched_item is not None:
        if item_type == "job_change":
            matched_item["status"] = "enrolled"
        elif item_type == "warm_intro":
            matched_item["status"] = "requested"
        elif item_type == "revival":
            matched_item["status"] = "revival_sent"
        updated = True

    enrollment_record = {
        "item_id": item_id,
        "item_type": item_type,
        "campaign_id": target_campaign,
        "status": "enrolled" if item_type == "job_change" else "revival_sent" if item_type == "revival" else "requested",
        "updated_in_memory": updated,
        "duplicate_prevented": False,
        "enrolled_at": datetime.utcnow().isoformat()
    }
    _ENROLLED_BOOMERANG_LOCKS[lock_key] = enrollment_record
    return dict(enrollment_record)


def resolve_boomerang_hook_for_execution(
    workspace_id: str,
    prospect_name: str,
    mode: str = "job_change",  # "job_change", "closed_lost_revival", or "warm_intro"
    previous_company: Optional[str] = None,
    previous_title: Optional[str] = None,
    new_company: Optional[str] = None,
    new_title: Optional[str] = None,
    days_in_new_role: int = 21,
    relationship_type: str = "former_champion",
    lost_reason: str = "bad_timing",
    days_since_lost: int = 120,
    original_deal_value: float = 25000.0,
    revival_trigger: Optional[str] = None,
    connector_name: Optional[str] = None,
    connector_role: Optional[str] = None,
    bridge_type: str = "shared_alumni",
    overlap_context: str = "Shared executive tenure",
    is_opted_out: bool = False,
    email: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    force_override: bool = False,
    supabase: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Horizon 34B Execution Orchestrator: Resolves a Boomerang Job-Change, Closed-Lost Revival,
    or Warm-Intro Bridge hook for sequence execution.
    - Layer 1 (Environmental): Enforces Opt-Out & workspace suppression_list check before generating outreach.
    - Layer 2 (Human Paranoia): Sanitizes formula injection and enforces 14-day Anti-Pestering Cooldown on revivals.
    """
    # Layer 1: Opt-Out & Suppression List Guard
    if is_opted_out:
        return {
            "status": "suppressed",
            "suppressed": True,
            "mode": mode,
            "hook_message": "",
            "score": 0,
            "reason": "Prospect is marked as opted out"
        }

    if supabase and (email or linkedin_url):
        try:
            q = supabase.table("suppression_list").select("*").eq("workspace_id", workspace_id)
            if email:
                q = q.eq("email", email.strip().lower())
            elif linkedin_url:
                q = q.eq("linkedin_url", linkedin_url.strip())
            sup_res = q.execute()
            if getattr(sup_res, "data", None):
                return {
                    "status": "suppressed",
                    "suppressed": True,
                    "mode": mode,
                    "hook_message": "",
                    "score": 0,
                    "reason": "Prospect matched workspace suppression_list"
                }
        except Exception as e:
            logger.warning("Suppression list lookup failed during boomerang execution hook resolution: %s", e)

    clean_prospect = _sanitize_boomerang_text(prospect_name) or "there"
    clean_prev_co = _sanitize_boomerang_text(previous_company)
    clean_prev_title = _sanitize_boomerang_text(previous_title)
    clean_new_co = _sanitize_boomerang_text(new_company)
    clean_new_title = _sanitize_boomerang_text(new_title)

    if mode == "job_change":
        calc = calculate_boomerang_buying_window(
            prospect_name=clean_prospect,
            previous_company=clean_prev_co or "your previous company",
            previous_title=clean_prev_title or "Leader",
            new_company=clean_new_co or "your new company",
            new_title=clean_new_title or "Executive",
            days_in_new_role=days_in_new_role,
            relationship_type=relationship_type,
        )
        return {
            "status": "ready",
            "suppressed": False,
            "mode": "job_change",
            "hook_message": calc["playbook_message"],
            "score": calc["buying_window_score"],
            "metadata": calc,
        }

    if mode in ("closed_lost_revival", "revival"):
        eval_res = evaluate_closed_lost_revival(
            prospect_name=clean_prospect,
            company_name=clean_new_co or clean_prev_co or "your company",
            title=clean_new_title or clean_prev_title or "Executive",
            lost_reason=lost_reason,
            days_since_lost=days_since_lost,
            original_deal_value=original_deal_value,
            revival_trigger=_sanitize_boomerang_text(revival_trigger, max_len=300) if revival_trigger else None,
            force_override=force_override,
        )
        return {
            "status": "ready",
            "suppressed": False,
            "mode": "closed_lost_revival",
            "hook_message": eval_res["resurrection_message"],
            "score": eval_res["revival_score"],
            "metadata": eval_res,
        }

    if mode == "warm_intro":
        bridge = generate_warm_intro_bridge(
            target_prospect_name=clean_prospect,
            target_company=clean_new_co or clean_prev_co or "your company",
            target_title=clean_new_title or clean_prev_title or "Executive",
            connector_name=_sanitize_boomerang_text(connector_name) or "Mutual Connection",
            connector_role=_sanitize_boomerang_text(connector_role) or "Executive Advisor",
            bridge_type=bridge_type,
            overlap_context=_sanitize_boomerang_text(overlap_context, max_len=300) or "Shared executive tenure",
        )
        return {
            "status": "ready",
            "suppressed": False,
            "mode": "warm_intro",
            "hook_message": bridge["direct_bridge_draft"],
            "intro_request_draft": bridge["intro_request_draft"],
            "score": bridge["warmth_score"],
            "metadata": bridge,
        }

    raise ValueError(f"Unsupported boomerang execution mode: {mode}")

