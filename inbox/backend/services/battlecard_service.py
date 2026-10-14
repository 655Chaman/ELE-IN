"""
Battlecard Knowledge Engine & Deal Stage Pipeline (Blue Ocean Phase 10: The Conversation Closer)
Governance: Three-Layer Logic Architecture (Paranoia Framework)

Provides:
1. Dynamic Battlecard Strategies & Competitive Kill-Points (Apollo, Lemlist, ZoomInfo, Outreach, etc.)
2. Multi-Tone Counter-Pitches (Challenger, Consultative, Casual)
3. Timezone-Aware 1-Click Calendar Slot Suggester
4. Deal Pipeline Stage Transitions with Event Webhook Emission & Defensive DB Fallbacks
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
import pytz

logger = logging.getLogger(__name__)

# Standard Deal Pipeline Stages & Integer Ranks for Monotonicity
DEAL_STAGES = {
    "NEW_REPLY": {"rank": 1, "label": "New Reply", "color": "blue"},
    "OBJECTION_RAISED": {"rank": 2, "label": "Objection Raised", "color": "amber"},
    "BATTLECARD_ENGAGED": {"rank": 3, "label": "Battlecard Deployed", "color": "indigo"},
    "MEETING_PROPOSED": {"rank": 4, "label": "Meeting Proposed", "color": "purple"},
    "MEETING_CONFIRMED": {"rank": 5, "label": "Meeting Confirmed", "color": "emerald"},
    "CLOSED_WON": {"rank": 6, "label": "Closed Won", "color": "green"},
    "DISQUALIFIED": {"rank": -1, "label": "Disqualified", "color": "zinc"}
}

# Competitive Intel Repository (Kill Points & Differentiators)
COMPETITIVE_BATTLECARDS = {
    "Apollo.io": {
        "competitor": "Apollo.io",
        "strengths_acknowledged": "Broad database breadth and all-in-one feature bundle.",
        "kill_points": [
            "30%+ stale contact bounce rate due to static data scrapers.",
            "Shared SMTP sending pools that frequently trigger domain blacklisting and spam filtering.",
            "Lacks residential IP jitter and Bayesian ICP learning—blasts homogeneous templates."
        ],
        "pivot_angle": "Use Apollo for bulk scraping, but route delivery through Ele-in's 4G residential jitter for 3x higher inbox deliverability."
    },
    "Lemlist": {
        "competitor": "Lemlist",
        "strengths_acknowledged": "Pioneered image personalization and multichannel touches.",
        "kill_points": [
            "Frequent LinkedIn account suspensions due to un-jittered browser automation.",
            "Manual sequence assembly requires hours of SDR setup per campaign.",
            "Lacks autonomous Bayesian ICP optimization or live intent harvesting."
        ],
        "pivot_angle": "Ele-in runs native anti-detect Canvas/WebGL masking and auto-tunes copy variants with Thompson Sampling."
    },
    "ZoomInfo": {
        "competitor": "ZoomInfo",
        "strengths_acknowledged": "Massive legacy enterprise database.",
        "kill_points": [
            "Exorbitant 5-figure annual contracts with strict multi-year auto-renewals.",
            "Direct dials and work emails decay at 3% monthly—half the directory is outdated.",
            "No execution engine—you still need to pay for Outreach or Salesloft to actually send."
        ],
        "pivot_angle": "Pay-as-you-go live waterfall enrichment verified at runtime for a fraction of annual enterprise licenses."
    },
    "Outreach": {
        "competitor": "Outreach / Salesloft",
        "strengths_acknowledged": "Enterprise workflow governance and reporting.",
        "kill_points": [
            "Bloated admin overhead requiring full-time RevOps maintenance.",
            "Rigid linear sequences that fail to adapt when prospects show real-time social intent.",
            "High cost per SDR seat with slow setup time (months to value)."
        ],
        "pivot_angle": "Lightweight autonomous agent architecture that sets up in 10 minutes with built-in intent radar."
    },
    "Generic": {
        "competitor": "Current Stack",
        "strengths_acknowledged": "Established workflows.",
        "kill_points": [
            "Static cold emails and un-warmed LinkedIn connections burn valuable domain reputation.",
            "Zero pre-connection social warmup leads to sub-20% connection acceptance."
        ],
        "pivot_angle": "Pre-warmed social intent and multi-sender pod load balancing."
    }
}


def get_competitive_intel(competitor_name: Optional[str]) -> Dict[str, Any]:
    """
    Returns battlecard kill points and pivot angles for a named competitor.
    """
    if not competitor_name:
        return COMPETITIVE_BATTLECARDS["Generic"]
    
    comp_clean = competitor_name.strip()
    for key, card in COMPETITIVE_BATTLECARDS.items():
        if key.lower() in comp_clean.lower() or comp_clean.lower() in key.lower():
            return card
    return COMPETITIVE_BATTLECARDS["Generic"]


def generate_battlecard_responses(
    objection_type: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Layer 0 & Layer 2: Generates 3 multi-tone tactical responses (Challenger, Consultative, Casual)
    tailored to the specific objection type, prospect identity, and competitor intelligence.
    """
    lead_name = context.get("lead_name") or "there"
    first_name = lead_name.split()[0] if lead_name else "there"
    company = context.get("company") or "your team"
    competitor = context.get("detected_competitor")
    timing = context.get("detected_timing") or "next quarter"
    referral = context.get("detected_referral") or "your colleague"

    comp_intel = get_competitive_intel(competitor)
    comp_name = comp_intel["competitor"]

    # 1. COMPETITOR INCUMBENT
    if objection_type == "COMPETITOR_INCUMBENT":
        strategy = f"Acknowledge {comp_name}, avoid a direct product replacement battle, and propose a low-friction 25-lead benchmark pilot."
        responses = {
            "challenger": (
                f"Totally fair, {first_name} — {comp_name} is a solid staple. "
                f"The #1 reason growth teams run Ele-in alongside {comp_name} is deliverability: {comp_name}'s shared pools average 25%+ bounce rates, "
                f"while our 4G residential jitter guarantees 98%+ inbox landing. "
                f"Rather than switching, open to benchmarking 25 target leads through our engine to see the deliverability lift?"
            ),
            "consultative": (
                f"Completely understand, {first_name} — no intention to disrupt what's already working with {comp_name}. "
                f"Most leaders we partner with actually keep their current stack for general sourcing and use Ele-in specifically "
                f"for high-value tier-1 accounts where residential IP safety is mission-critical. "
                f"Would you be open to a 5-minute side-by-side benchmark next week to compare response rates?"
            ),
            "casual": (
                f"Appreciate the transparency, {first_name}! {comp_name} is great. "
                f"Curious though — are your reps seeing higher bounce rates or connection drop-offs lately? "
                f"If you're ever curious how our Bayesian ICP matching compares, happy to share real performance data. "
                f"No sales pitch, just practical numbers!"
            )
        }

    # 2. BUDGET FREEZE
    elif objection_type == "BUDGET_FREEZE":
        strategy = "Validate fiscal discipline, eliminate immediate financial risk, and pivot to a zero-spend data audit."
        responses = {
            "challenger": (
                f"Completely respect that, {first_name} — fiscal discipline makes total sense in this environment. "
                f"We actually don't want a budget commitment right now. If I ran a free 25-lead sample to show your leadership "
                f"how to cut SDR data acquisition costs by 40% when budgets reopen, would Thursday afternoon work for a 10-min breakdown?"
            ),
            "consultative": (
                f"Understood, {first_name} — totally respect the budget hold. Rather than a paid engagement, "
                f"would you be open to running a zero-cost benchmark on a small sample list? "
                f"That way you have concrete ROI and performance benchmarks ready on file whenever leadership unfreezes spend."
            ),
            "casual": (
                f"Got it, {first_name}! Makes complete sense with executive spending freezes right now. "
                f"I'll mark a tentative reminder for later in the year. If helpful, I can drop a 1-page summary of how teams benchmark "
                f"their outbound stack so you have it in your back pocket. Stay great!"
            )
        }

    # 3. TIMING LATER
    elif objection_type == "TIMING_LATER":
        strategy = f"Respect timing request for {timing}, offer a lightweight calendar placeholder, and share high-value asynchronous material."
        responses = {
            "challenger": (
                f"Makes sense, {first_name} — timing is everything. "
                f"Most teams reaching out in {timing} find their calendars swamped once planning kicks in. "
                f"Could we pencil in a tentative 10-min placeholder for the second week of {timing}? "
                f"If priorities shift by then, zero hard feelings if we need to adjust!"
            ),
            "consultative": (
                f"Totally respect that, {first_name}. I'll set a firm note on our side to reconnect in {timing}. "
                f"Before then, if you'd like, I can send our 1-page playbook on residential proxy warmup so your team "
                f"has actionable data ready when planning begins. Sound fair?"
            ),
            "casual": (
                f"Understood! Appreciate you letting me know rather than ghosting, {first_name}. "
                f"I'll circle back in {timing}. Have a great rest of the quarter!"
            )
        }

    # 4. SEND INFO DECK
    elif objection_type == "SEND_INFO_DECK":
        strategy = "Agree to send asynchronous materials, but pair it with a crisp micro-pitch proposing a 5-minute live screen share."
        responses = {
            "challenger": (
                f"Happy to send our 1-page architecture teardown, {first_name}! "
                f"Honestly though, a static PDF doesn't do justice to seeing live Bayesian ICP discovery in action. "
                f"I can walk you through the 3 core mechanics on screen in 4 minutes flat. "
                f"Open to a quick look Tuesday at 2pm, or would you prefer the PDF first?"
            ),
            "consultative": (
                f"You bet, {first_name}. I'll send our overview deck right over to your email. "
                f"To make sure I highlight the exact sections relevant to {company}, are you primarily looking "
                f"to solve contact deliverability or LinkedIn automation safety right now?"
            ),
            "casual": (
                f"Sending it right over! If you have 3 minutes after glancing through, I'd love to show you how our "
                f"social signal radar picks up live buying triggers. Let me know what you think!"
            )
        }

    # 5. WRONG PERSON REFERRAL
    elif objection_type == "WRONG_PERSON_REFERRAL":
        strategy = f"Thank prospect, request permission to mention their referral when contacting {referral}, and confirm contact info."
        responses = {
            "challenger": (
                f"Thanks for pointing me in the right direction, {first_name}! "
                f"Would you mind if I mention to {referral} that you suggested I connect with them? "
                f"And is LinkedIn or email better for reaching them?"
            ),
            "consultative": (
                f"Really appreciate the pointer, {first_name}. "
                f"I'll reach out to {referral} directly regarding {company}'s outbound infrastructure. "
                f"Thanks for taking a second out of your day to steer me right!"
            ),
            "casual": (
                f"Thanks a ton, {first_name}! Super helpful. "
                f"I'll drop {referral} a note and won't crowd your inbox. Have a great week!"
            )
        }

    # 6. SKEPTICISM / DATA PRIVACY / AUTHENTICITY
    elif objection_type == "SKEPTICISM_AUTHENTICITY":
        strategy = "De-escalate immediately with radical transparency, respect privacy preferences, and explain exact legitimate research trigger."
        responses = {
            "challenger": (
                f"Completely fair question, {first_name}. "
                f"I came across your profile while researching {company}'s recent team expansion on LinkedIn. "
                f"Zero automated scrapers or bought lists — I personally flagged your post on industry growth. "
                f"If this isn't relevant right now, I'm happy to mark your record and won't message again!"
            ),
            "consultative": (
                f"Understood and totally respect your vigilance, {first_name}. "
                f"We identify prospects exclusively via publicly available LinkedIn company updates and hiring signals. "
                f"That said, your privacy comes first. If you prefer no further outreach, just let me know and I will remove your contact immediately."
            ),
            "casual": (
                f"Fair pushback! Found your profile organically through LinkedIn's feed based on your role at {company}. "
                f"Definitely not a bot spamming contacts. But if you're not interested, no worries at all — I'll step aside!"
            )
        }

    # 7. FEATURE GAP / CUSTOM INQUIRY
    elif objection_type == "FEATURE_GAP":
        strategy = "Provide transparent capability breakdown and present current native integrations or API workarounds."
        responses = {
            "challenger": (
                f"Great question, {first_name}. Yes, we support that natively via our bi-directional webhook pipeline and REST API. "
                f"We can stream events directly into your destination in sub-200ms. "
                f"Would you be open to a 5-min look at the webhook studio to verify it fits your technical requirements?"
            ),
            "consultative": (
                f"Thanks for asking, {first_name}. We handle this through our automation hub and HubSpot / Zapier integrations. "
                f"If you have a custom stack, our team can show you the exact schema mapping. "
                f"Let me know if Thursday works for a technical walkthrough!"
            ),
            "casual": (
                f"We definitely do! It's one of our most popular setups. "
                f"Happy to send over the documentation link or jump on a quick 3-minute screen share to show you how it works. Let me know!"
            )
        }

    # Default / Soft No
    else:
        strategy = "Acknowledge bandwidth constraints, lower friction to zero, and leave an open door."
        responses = {
            "challenger": (
                f"Got it, {first_name} — totally understand you're swamped. "
                f"Before I let you go, is outbound efficiency something you're planning to tackle later this year, or completely off the radar?"
            ),
            "consultative": (
                f"Understood, {first_name}! Appreciate the candid response. "
                f"I'll take a step back and won't crowd your inbox. If outbound bottlenecks ever become a priority, feel free to reach back out."
            ),
            "casual": (
                f"No problem at all, {first_name}! Appreciate you letting me know. "
                f"Best of luck with everything on your plate right now!"
            )
        }

    return {
        "objection_type": objection_type,
        "competitor_intel": comp_intel,
        "strategy_summary": strategy,
        "responses": responses
    }


def generate_suggested_meeting_slots(
    lead_tz: Optional[str] = None,
    sender_tz: Optional[str] = "UTC",
    num_slots: int = 3
) -> List[Dict[str, Any]]:
    """
    Layer 0 & Layer 1: Timezone-Aware Calendar Slot Generator.
    Computes realistic business-hour proposal slots over the next 2-4 business days.
    Skips weekends and formats slots in both lead local time and UTC ISO strings.
    """
    target_tz_str = "UTC"
    if lead_tz:
        try:
            pytz.timezone(lead_tz.strip())
            target_tz_str = lead_tz.strip()
        except Exception:
            target_tz_str = sender_tz or "UTC"

    try:
        tz = pytz.timezone(target_tz_str)
    except Exception:
        tz = pytz.UTC
        target_tz_str = "UTC"

    now_local = datetime.now(tz)
    slots: List[Dict[str, Any]] = []

    # Candidate times: 10:00 AM, 2:00 PM, 3:30 PM
    candidate_hours = [(10, 0), (14, 0), (15, 30)]
    days_checked = 1

    while len(slots) < num_slots and days_checked <= 7:
        candidate_date = now_local + timedelta(days=days_checked)
        weekday = candidate_date.weekday()

        # Monday=0 ... Friday=4, skip Saturday(5) and Sunday(6)
        if weekday < 5:
            hour, minute = candidate_hours[len(slots) % len(candidate_hours)]
            slot_dt = candidate_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            day_name = slot_dt.strftime("%A")
            month_name = slot_dt.strftime("%b")
            day_num = slot_dt.strftime("%d").lstrip("0")
            time_str = slot_dt.strftime("%I:%M %p").lstrip("0")

            formatted_label = f"{day_name}, {month_name} {day_num} at {time_str} {tz.zone}"
            short_label = f"{day_name} at {time_str} ({tz.zone})"

            slots.append({
                "slot_index": len(slots) + 1,
                "formatted_label": formatted_label,
                "short_label": short_label,
                "local_time_str": time_str,
                "iso_utc": slot_dt.astimezone(pytz.UTC).isoformat(),
                "timezone": tz.zone
            })

        days_checked += 1

    return slots


def update_lead_deal_stage(
    supabase: Any,
    lead_id: str,
    workspace_id: str,
    new_stage: str,
    estimated_value: Optional[float] = None,
    force_override: bool = False
) -> Dict[str, Any]:
    """
    Layer 0, 1 & 2: Updates a lead's deal stage with monotonicity enforcement,
    defensive database fallback (in case migration 081 hasn't been executed on Supabase yet),
    and webhook dispatch.
    """
    if new_stage not in DEAL_STAGES:
        new_stage = "NEW_REPLY"

    current_stage = "NEW_REPLY"
    lead_data: Dict[str, Any] = {}

    # 1. Fetch current lead state with defensive fallback
    try:
        res = supabase.table("leads").select("id, first_name, last_name, company, email, deal_stage").eq("id", lead_id).eq("workspace_id", workspace_id).limit(1).execute()
        if res.data and len(res.data) > 0:
            lead_data = res.data[0]
            current_stage = lead_data.get("deal_stage") or "NEW_REPLY"
    except Exception as ex:
        logger.warning(f"Failed to query deal_stage from leads table (column may not exist yet): {ex}")
        # Proceed with in-memory fallback

    # 2. Monotonicity Guard (Layer 2 Paranoia)
    # Never downgrade MEETING_CONFIRMED (5) or CLOSED_WON (6) back to earlier stages unless force_override is True
    current_rank = DEAL_STAGES.get(current_stage, {}).get("rank", 1)
    new_rank = DEAL_STAGES.get(new_stage, {}).get("rank", 1)

    if not force_override and current_rank in [5, 6] and new_rank < current_rank and new_rank != -1:
        logger.info(f"Monotonicity guard prevented downgrading lead {lead_id} from {current_stage} to {new_stage}")
        return {
            "status": "preserved",
            "deal_stage": current_stage,
            "message": f"Lead is already at higher stage '{current_stage}'. Downgrade prevented."
        }

    # 3. Update database with defensive try/except
    now_iso = datetime.now(timezone.utc).isoformat()
    update_payload: Dict[str, Any] = {
        "deal_stage": new_stage,
        "deal_stage_updated_at": now_iso
    }
    if estimated_value is not None:
        update_payload["deal_estimated_value"] = estimated_value

    try:
        supabase.table("leads").update(update_payload).eq("id", lead_id).eq("workspace_id", workspace_id).execute()
    except Exception as ex:
        logger.warning(f"Failed to update deal_stage in leads table (schema migration pending): {ex}")

    # 4. Dispatch outbound webhook event (Phase 9 integration)
    try:
        from integrations.backend.services.webhook_service import emit_webhook_event
        full_name = f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip() or "Prospect"
        emit_webhook_event(
            workspace_id=workspace_id,
            event_type="deal.stage_updated",
            payload={
                "lead_id": lead_id,
                "lead_name": full_name,
                "company": lead_data.get("company"),
                "email": lead_data.get("email"),
                "previous_stage": current_stage,
                "deal_stage": new_stage,
                "estimated_value": estimated_value or 0,
                "updated_at": now_iso
            },
            supabase=supabase
        )
    except Exception as ex:
        logger.warning(f"Failed to emit deal.stage_updated webhook event: {ex}")

    return {
        "status": "success",
        "lead_id": lead_id,
        "previous_stage": current_stage,
        "deal_stage": new_stage,
        "updated_at": now_iso
    }
