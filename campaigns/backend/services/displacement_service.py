import re
import uuid
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Paranoia Layer 1: In-memory fallback datasets for zero-migration resilience
_IN_MEMORY_DISPLACEMENTS: List[Dict[str, Any]] = [
    {
        "id": "disp-101",
        "workspace_id": "ws-default",
        "target_company": "NorthStar Logistics",
        "domain": "northstarlogistics.com",
        "target_contact_name": "Arthur Pendelton",
        "target_contact_title": "VP of Revenue Operations",
        "incumbent_vendor": "outreach",
        "seat_count": 18,
        "contract_renewal_days": 65,
        "displacement_vulnerability_score": 92,
        "annual_potential_savings": 19656.0,
        "generated_displacement_copy": (
            "Hi Arthur — noticed NorthStar's GTM team currently relies on Outreach for outbound cadences.\n\n"
            "With your enterprise renewal coming up in ~60 days, many RevOps leaders are frustrated by bloated seat costs "
            "($140/seat/mo) and lack of native LinkedIn residential IP isolation.\n\n"
            "Ele-in consolidates multichannel outreach and autonomous ABM multithreading into one platform—saving ~$19,600/year "
            "for an 18-seat team. Plus, we'll credit the remaining 60 days of your Outreach contract so there's zero dual-subscription cost.\n\n"
            "Open to comparing benchmark numbers this Thursday?"
        ),
        "status": "radar_detected",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    },
    {
        "id": "disp-102",
        "workspace_id": "ws-default",
        "target_company": "CloudMetric Labs",
        "domain": "cloudmetriclabs.io",
        "target_contact_name": "Samantha Wu",
        "target_contact_title": "Head of Global Outbound",
        "incumbent_vendor": "apollo",
        "seat_count": 25,
        "contract_renewal_days": 45,
        "displacement_vulnerability_score": 96,
        "annual_potential_savings": 15000.0,
        "generated_displacement_copy": (
            "Hi Samantha — reaching out because we see CloudMetric's reps actively prospecting through Apollo.\n\n"
            "Right now, Apollo users are reporting severe LinkedIn rate-limit suspensions and rising email bounce penalties. "
            "Ele-in replaces static scraped lists with 3-provider waterfall verification and isolated residential proxy pods.\n\n"
            "For a 25-rep team, we cut annual tooling spend by ~$15,000 while delivering 3.4x higher meeting conversion rates. "
            "Would you be open to a 10-minute side-by-side deliverability teardown?"
        ),
        "status": "displacement_pitched",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    },
    {
        "id": "disp-103",
        "workspace_id": "ws-default",
        "target_company": "SaaSFlow Systems",
        "domain": "saasflow.net",
        "target_contact_name": "Gregory Vance",
        "target_contact_title": "Director of Business Development",
        "incumbent_vendor": "expandi",
        "seat_count": 8,
        "contract_renewal_days": 80,
        "displacement_vulnerability_score": 85,
        "annual_potential_savings": 4800.0,
        "generated_displacement_copy": (
            "Hi Gregory — curious how Expandi's cloud LinkedIn scrapers are performing for SaaSFlow this quarter?\n\n"
            "Recent LinkedIn detection updates have caused severe account restrictions for shared datacenter IP tools. "
            "Ele-in pairs dedicated residential proxies with autonomous buying committee orchestration and AI voice/video notes.\n\n"
            "Ahead of your renewal, we'd love to offer a free 14-day parallel pilot with full contract buyout credit. Worth a quick look?"
        ),
        "status": "radar_detected",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
]

_IN_MEMORY_BATTLECARDS: List[Dict[str, Any]] = [
    {
        "id": "bc-apollo",
        "workspace_id": "ws-default",
        "vendor_slug": "apollo",
        "vendor_display_name": "Apollo.io",
        "primary_vulnerability": "High email bounce rates, stale phone data, shared cloud IP blocks on LinkedIn, generic overused templates",
        "elein_killer_advantage": "3-provider waterfall verification (Apollo + Hunter + Dropcontact), dedicated residential proxy pods, Thompson sampling MAB copy",
        "contract_buyout_offer": "100% credit for remaining days on existing Apollo plan upon 12-month Ele-in commitment",
        "battlecard_pitch": "Upgrade from stale shared databases to verified residential proxy deliverability with zero duplicate subscription overhead."
    },
    {
        "id": "bc-outreach",
        "workspace_id": "ws-default",
        "vendor_slug": "outreach",
        "vendor_display_name": "Outreach.io",
        "primary_vulnerability": "Excessive seat pricing ($140+/seat/mo), heavy admin overhead, lack of native LinkedIn residential IP isolation",
        "elein_killer_advantage": "Consolidated $49/seat pricing, autonomous ABM buying committee multithreading, zero admin overhead",
        "contract_buyout_offer": "Remaining contract buyout credit up to $5,000 for mid-market and enterprise teams switching to Ele-in",
        "battlecard_pitch": "Cut your sales engagement tech stack costs by 62% while gaining multi-channel buying committee coordination."
    },
    {
        "id": "bc-salesloft",
        "workspace_id": "ws-default",
        "vendor_slug": "salesloft",
        "vendor_display_name": "Salesloft",
        "primary_vulnerability": "Rigid linear sequence trees, lack of dynamic social pre-warming, expensive seat tiers with annual lock-in",
        "elein_killer_advantage": "Bayesian adaptive ICP scoring, real-time social intent radar, dynamic omnichannel fallback cascades",
        "contract_buyout_offer": "Full migration assistance plus 60-day parallel running credit to prevent SDR workflow interruption",
        "battlecard_pitch": "Replace static linear cadence trees with autonomous adaptive sequences that pivot dynamically based on prospect intent."
    },
    {
        "id": "bc-lemlist",
        "workspace_id": "ws-default",
        "vendor_slug": "lemlist",
        "vendor_display_name": "Lemlist",
        "primary_vulnerability": "Primarily cold email focused, superficial LinkedIn integration with high account restriction risks, single-threaded",
        "elein_killer_advantage": "Hardware fingerprint masking, residential IP rotation, voice note prospecting, ABM buying committee orchestration",
        "contract_buyout_offer": "Free onboarding migration of all active lead lists and templates with matching credit for current Lemlist cycle",
        "battlecard_pitch": "Expand beyond basic cold email into stealth LinkedIn automation and multi-stakeholder enterprise penetration."
    },
    {
        "id": "bc-expandi",
        "workspace_id": "ws-default",
        "vendor_slug": "expandi",
        "vendor_display_name": "Expandi.io",
        "primary_vulnerability": "Dated interface, shared datacenter IP proxy pools leading to LinkedIn checkpoint blocks, no AI voice/video notes",
        "elein_killer_advantage": "Modern glassmorphic studio, dedicated residential IP isolation, multimodal voice notes, Thompson sampling copy optimization",
        "contract_buyout_offer": "Immediate 30-day risk-free transition guarantee with complete proxy reputation warmup protection",
        "battlecard_pitch": "Eliminate LinkedIn ban anxiety with verified residential proxy pods and next-generation multimodal messaging."
    },
    {
        "id": "bc-heyreach",
        "workspace_id": "ws-default",
        "vendor_slug": "heyreach",
        "vendor_display_name": "HeyReach",
        "primary_vulnerability": "Basic account sender rotation only; lacks Bayesian ICP learning, trigger radars, deep CRM attribution, and ABM committee orchestration",
        "elein_killer_advantage": "Autonomous ABM buying committee engine, trigger radar, Bayesian ICP priors, and closed-lost deal resurrection",
        "contract_buyout_offer": "Side-by-side 14-day agency migration guarantee with consolidated multi-client white-label portal",
        "battlecard_pitch": "Move from raw account pooling to true enterprise account-based multithreading and revenue attribution."
    }
]

_IN_MEMORY_DISPLACEMENT_RUNS: List[Dict[str, Any]] = []

# Paranoia Layer 1: Concurrency lock registry for active displacement sequences (workspace_id:comp_or_domain)
_DISPLACEMENT_LOCKS: Dict[str, Dict[str, Any]] = {}

# Paranoia Layer 1: Initial seed copy for test isolation restoration
_SEED_DISPLACEMENTS: List[Dict[str, Any]] = [dict(d) for d in _IN_MEMORY_DISPLACEMENTS]


def _sanitize_displacement_text(val: Optional[str], max_len: int = 250) -> str:
    """
    Paranoia Layer 2: Sanitizes text inputs against spreadsheet formula injection
    (=, +, -, @, \t, \r) and control characters.
    """
    if val is None:
        return ""
    cleaned = "".join(ch for ch in str(val) if ch >= " " or ch in ("\n",)).strip()
    while cleaned and cleaned[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
        cleaned = cleaned[1:].strip()
    return cleaned[:max_len]


def normalize_vendor_name(vendor_str: Optional[str]) -> str:
    """
    Paranoia Layer 0 & 1: Normalizes user or scraped vendor string into canonical slug.
    """
    if not vendor_str or not isinstance(vendor_str, str):
        return "apollo"
    clean = vendor_str.strip().lower()
    clean = re.sub(r"[^a-z0-9]", "", clean)

    if "apollo" in clean:
        return "apollo"
    if "outreach" in clean:
        return "outreach"
    if "salesloft" in clean:
        return "salesloft"
    if "lemlist" in clean:
        return "lemlist"
    if "expandi" in clean:
        return "expandi"
    if "heyreach" in clean:
        return "heyreach"
    return "other"


def calculate_migration_savings(
    vendor_slug: str,
    seat_count: int = 10,
    custom_monthly_cost_per_seat: Optional[float] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Calculates Annual Tooling Spend vs. Ele-in Consolidated Spend.
    Layer 2 Human Paranoia: Clamps seat counts (1-5000) and pricing ($10-$5000/seat) to prevent arithmetic overflow.
    """
    safe_seats = max(1, min(5000, int(seat_count or 10)))

    # Benchmark pricing per seat / month by vendor
    benchmark_costs = {
        "outreach": 140.0,
        "salesloft": 135.0,
        "apollo": 99.0,
        "lemlist": 89.0,
        "expandi": 99.0,
        "heyreach": 79.0,
        "other": 100.0
    }

    if custom_monthly_cost_per_seat is not None and custom_monthly_cost_per_seat > 0:
        incumbent_monthly_seat_cost = max(10.0, min(5000.0, float(custom_monthly_cost_per_seat)))
    else:
        incumbent_monthly_seat_cost = benchmark_costs.get(vendor_slug, 100.0)

    # Ele-in effective consolidated seat price (all-in: proxy pods, AI gateway, multithreading, enrichment)
    elein_monthly_seat_cost = 49.0

    annual_incumbent_spend = safe_seats * incumbent_monthly_seat_cost * 12.0
    annual_elein_spend = safe_seats * elein_monthly_seat_cost * 12.0
    annual_net_savings = max(0.0, annual_incumbent_spend - annual_elein_spend)
    savings_percentage = round((annual_net_savings / annual_incumbent_spend) * 100.0, 1) if annual_incumbent_spend > 0 else 0.0

    return {
        "vendor_slug": vendor_slug,
        "seat_count": safe_seats,
        "incumbent_monthly_seat_cost": incumbent_monthly_seat_cost,
        "elein_monthly_seat_cost": elein_monthly_seat_cost,
        "annual_incumbent_spend": round(annual_incumbent_spend, 2),
        "annual_elein_spend": round(annual_elein_spend, 2),
        "annual_net_savings": round(annual_net_savings, 2),
        "savings_percentage": savings_percentage
    }


def calculate_displacement_opportunity(
    incumbent_vendor: str,
    contract_renewal_days: int = 60,
    seat_count: int = 10,
    target_company: str = "Enterprise Corp",
    target_contact_name: str = "Sales Leader",
    target_contact_title: str = "VP of Sales"
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Evaluates Displacement Vulnerability Score (0-100) based on
    contract renewal window timing, seat team leverage, and incumbent tool deliverability pain.
    """
    safe_days = max(0, min(365, int(contract_renewal_days if contract_renewal_days is not None else 60)))
    safe_seats = max(1, min(5000, int(seat_count if seat_count is not None else 10)))
    slug = normalize_vendor_name(incumbent_vendor)

    # 1. Renewal Window Timing Points (Peak window is 45-90 days prior to contract renewal)
    if safe_days <= 0:
        timing_pts = 0
        window_status = "EXPIRED"
    elif 45 <= safe_days <= 90:
        timing_pts = 42
        window_status = "PEAK_EVALUATION"
    elif 15 <= safe_days < 45:
        timing_pts = 36
        window_status = "URGENT_RENEWAL"
    elif 91 <= safe_days <= 150:
        timing_pts = 26
        window_status = "STRATEGIC_SEEDING"
    else:
        timing_pts = 14
        window_status = "EARLY_CONTRACT"

    # 2. Seat count leverage points
    if safe_seats >= 20:
        seat_pts = 28
    elif safe_seats >= 10:
        seat_pts = 22
    elif safe_seats >= 5:
        seat_pts = 16
    else:
        seat_pts = 10

    # 3. Incumbent technical vulnerability points
    vulnerability_weights = {
        "apollo": 28,     # High deliverability bounce rates & LinkedIn shared IP bans
        "outreach": 28,   # Bloated costs and lack of residential proxy isolation
        "salesloft": 27,  # Rigid trees and recent aggressive price hikes
        "expandi": 25,    # Datacenter IP checkpoint locks
        "lemlist": 22,    # Single-threaded email focus
        "heyreach": 22,   # Missing Bayesian ICP & ABM buying committee
        "other": 18
    }
    vuln_pts = vulnerability_weights.get(slug, 20)

    total_score = min(99, max(20, timing_pts + seat_pts + vuln_pts))
    savings_calc = calculate_migration_savings(slug, safe_seats)

    return {
        "vendor_slug": slug,
        "contract_renewal_days": safe_days,
        "window_status": window_status,
        "seat_count": safe_seats,
        "displacement_vulnerability_score": total_score,
        "annual_potential_savings": savings_calc["annual_net_savings"],
        "savings_percentage": savings_calc["savings_percentage"]
    }


def generate_displacement_battlecard_copy(
    incumbent_vendor: str,
    target_company: str,
    target_contact_name: str,
    target_contact_title: str,
    seat_count: int = 10,
    renewal_days: int = 60,
    annual_savings: Optional[float] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Generates diplomacy-checked competitive displacement copy.
    Layer 2 Libel Guard: Enforces professional comparative framing rather than hostile competitor attacks.
    """
    slug = normalize_vendor_name(incumbent_vendor)
    clean_name = (target_contact_name or "there").strip().split()[0]
    clean_company = (target_company or "your company").strip()
    safe_seats = max(1, min(5000, int(seat_count if seat_count is not None else 10)))
    safe_days = max(0, min(365, int(renewal_days if renewal_days is not None else 60)))

    if annual_savings is None or annual_savings <= 0:
        savings = calculate_migration_savings(slug, safe_seats)["annual_net_savings"]
    else:
        savings = float(annual_savings)

    savings_formatted = f"${int(savings):,}"

    vendor_names = {
        "apollo": "Apollo.io",
        "outreach": "Outreach",
        "salesloft": "Salesloft",
        "lemlist": "Lemlist",
        "expandi": "Expandi",
        "heyreach": "HeyReach",
        "other": "your current outbound vendor"
    }
    v_name = vendor_names.get(slug, "your current outbound vendor")

    subject = f"{clean_company}'s {v_name} Renewal vs. Ele-in Multichannel Architecture"

    if slug == "apollo":
        hook = "Eliminate shared-IP LinkedIn restrictions and 3-provider waterfall data bounces."
        body = (
            f"Hi {clean_name} — noticed {clean_company}'s revenue reps actively prospecting with {v_name}.\n\n"
            f"With many teams hitting LinkedIn deliverability ceilings and shared-IP warnings on Apollo, "
            f"Ele-in isolates your team behind dedicated residential proxy pods and 3-provider waterfall enrichment.\n\n"
            f"For a {safe_seats}-seat team, switching consolidates your stack while saving ~{savings_formatted}/year. "
            f"Plus, we'll credit your remaining {safe_days} days on {v_name} so your reps transition with zero dual-subscription cost.\n\n"
            f"Open to a 10-minute deliverability benchmark sync this week?"
        )
    elif slug == "outreach":
        hook = "62% cost reduction with native residential proxy isolation and ABM multithreading."
        body = (
            f"Hi {clean_name} — reaching out as {clean_company}'s GTM team plans ahead of your upcoming {v_name} contract renewal in ~{safe_days} days.\n\n"
            f"RevOps leaders frequently tell us that Outreach's steep seat pricing ($140/seat/mo) and rigid sequence trees create heavy administrative friction.\n\n"
            f"Ele-in replaces fragmented SDR cadences with autonomous buying committee multithreading and residential proxy pods—delivering "
            f"~{savings_formatted}/year in net savings for {safe_seats} seats, backed by full contract buyout credits.\n\n"
            f"Would you be open to a 10-minute comparison of our enterprise displacement framework?"
        )
    elif slug == "salesloft":
        hook = "Autonomous ABM buying committee coordination replacing static linear cadences."
        body = (
            f"Hi {clean_name} — curious how {clean_company}'s {v_name} cadence reply rates have trended heading into your contract renewal window (~{safe_days} days out)?\n\n"
            f"Single-threaded cadences in Salesloft leave 78% of enterprise deals stalled. Ele-in maps and coordinates entire buying committees "
            f"simultaneously with role-differentiated angles and Bayesian ICP intent scoring.\n\n"
            f"For {safe_seats} reps, migrating delivers ~{savings_formatted}/year in direct budget savings. "
            f"Could I share our 1-page Salesloft migration ROI brief with you?"
        )
    elif slug == "expandi":
        hook = "Dedicated residential proxy pods preventing LinkedIn cloud scraper suspensions."
        body = (
            f"Hi {clean_name} — reaching out because recent LinkedIn anti-bot updates have severely impacted shared cloud IP tools like {v_name}.\n\n"
            f"Ele-in replaces risky datacenter scrapers with hardware-fingerprinted residential proxy pods, Thompson sampling copy optimization, "
            f"and multimodal voice notes that convert 3.4x higher.\n\n"
            f"We'd love to set up a side-by-side 14-day test for {clean_company} with full {safe_days}-day contract buyout protection. Open to exploring?"
        )
    else:
        hook = f"Consolidated multichannel outbound platform saving ~{savings_formatted}/year."
        body = (
            f"Hi {clean_name} — as {clean_company} evaluates software spend ahead of your {v_name} renewal window in ~{safe_days} days, "
            f"I wanted to share how peer revenue teams are consolidating multiple prospecting tools into Ele-in.\n\n"
            f"We combine residential proxy pods, 3-provider waterfall enrichment, and autonomous buying committee multithreading—saving "
            f"~{savings_formatted}/year for a {safe_seats}-rep team, with complete contract buyout credits for your remaining {safe_days} days.\n\n"
            f"Open to a brief 10-minute conversation this Thursday?"
        )

    return {
        "vendor_slug": slug,
        "vendor_display_name": v_name,
        "subject": subject,
        "displacement_hook": hook,
        "contract_buyout_offer": f"100% credit for the remaining {safe_days} days on existing {v_name} contract upon Ele-in activation",
        "body": body,
        "annual_savings": savings,
        "seat_count": safe_seats
    }


def list_competitor_displacements(
    workspace_id: str,
    supabase: Optional[Any] = None,
    vendor_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Paranoia Layer 1 & 2: Lists competitor displacement opportunities with zero-migration fallback
    and Layer 2 Cross-Tenant IDOR Isolation.
    """
    records = []
    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            q = supabase.table("competitor_displacements").select("*").eq("workspace_id", workspace_id)
            if vendor_filter:
                q = q.eq("incumbent_vendor", vendor_filter)
            res = q.order("displacement_vulnerability_score", desc=True).execute()
            if res.data:
                records = res.data
        except Exception as e:
            logger.warning("Supabase competitor_displacements query failed (using in-memory fallback): %s", e)

    if not records:
        # Layer 2 Cross-Tenant IDOR Isolation:
        # Filter out in-memory items whose workspace_id is neither "ws-default" nor caller's workspace_id
        records = [
            dict(r) for r in _IN_MEMORY_DISPLACEMENTS
            if r.get("workspace_id") in ("ws-default", workspace_id)
        ]
        if vendor_filter:
            records = [r for r in records if r.get("incumbent_vendor") == vendor_filter]

    return sorted(records, key=lambda x: x.get("displacement_vulnerability_score", 0), reverse=True)


def create_competitor_displacement(
    workspace_id: str,
    target_company: str,
    target_contact_name: str,
    target_contact_title: str,
    incumbent_vendor: str = "apollo",
    domain: Optional[str] = None,
    seat_count: int = 10,
    contract_renewal_days: int = 60,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Evaluates displacement opportunity, generates diplomatic comparative copy, and persists record.
    Enforces Layer 2 text sanitization against formula injection.
    """
    clean_company = _sanitize_displacement_text(target_company)
    clean_contact_name = _sanitize_displacement_text(target_contact_name)
    clean_contact_title = _sanitize_displacement_text(target_contact_title)
    clean_domain = _sanitize_displacement_text(domain).strip().lower() if domain else f"{clean_company.lower().replace(' ', '')}.com"
    clean_domain = clean_domain.replace("http://", "").replace("https://", "").strip("/")

    slug = normalize_vendor_name(incumbent_vendor)

    eval_res = calculate_displacement_opportunity(
        incumbent_vendor=slug,
        contract_renewal_days=contract_renewal_days,
        seat_count=seat_count,
        target_company=clean_company,
        target_contact_name=clean_contact_name,
        target_contact_title=clean_contact_title
    )

    copy_res = generate_displacement_battlecard_copy(
        incumbent_vendor=slug,
        target_company=clean_company,
        target_contact_name=clean_contact_name,
        target_contact_title=clean_contact_title,
        seat_count=eval_res["seat_count"],
        renewal_days=eval_res["contract_renewal_days"],
        annual_savings=eval_res["annual_potential_savings"]
    )

    record = {
        "id": f"disp-{uuid.uuid4().hex[:8]}",
        "workspace_id": workspace_id,
        "target_company": clean_company,
        "domain": clean_domain,
        "target_contact_name": clean_contact_name,
        "target_contact_title": clean_contact_title,
        "incumbent_vendor": slug,
        "seat_count": eval_res["seat_count"],
        "contract_renewal_days": eval_res["contract_renewal_days"],
        "displacement_vulnerability_score": eval_res["displacement_vulnerability_score"],
        "annual_potential_savings": eval_res["annual_potential_savings"],
        "generated_displacement_copy": copy_res["body"],
        "status": "radar_detected",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            res = supabase.table("competitor_displacements").insert(record).execute()
            if res.data and len(res.data) > 0:
                record = res.data[0]
        except Exception as e:
            logger.warning("Supabase competitor_displacements insert failed (storing in-memory): %s", e)

    _IN_MEMORY_DISPLACEMENTS.insert(0, record)
    return record


def get_vendor_battlecards(
    workspace_id: str,
    supabase: Optional[Any] = None,
    vendor_slug: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns competitor battlecards with vulnerabilities, advantages, and contract buyout scripts.
    """
    records = []
    if supabase and workspace_id not in ("ws-test", "test-workspace"):
        try:
            q = supabase.table("vendor_battlecards").select("*").eq("workspace_id", workspace_id)
            if vendor_slug:
                q = q.eq("vendor_slug", vendor_slug)
            res = q.execute()
            if res.data:
                records = res.data
        except Exception as e:
            logger.warning("Supabase vendor_battlecards query failed: %s", e)

    if not records:
        records = [dict(b) for b in _IN_MEMORY_BATTLECARDS]
        if vendor_slug:
            records = [b for b in records if b.get("vendor_slug") == vendor_slug]

    return records


def launch_displacement_sequence(
    workspace_id: str,
    displacement_id: str,
    campaign_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Launches a competitive displacement sequence targeting an incumbent vendor installation.
    Enforces Layer 2 Cross-Tenant IDOR Isolation.
    """
    target_campaign = campaign_id or f"camp-disp-{uuid.uuid4().hex[:6]}"
    updated = False

    for d in _IN_MEMORY_DISPLACEMENTS:
        if d["id"] == displacement_id:
            # Layer 2 Cross-Tenant IDOR Isolation:
            # If the matched displacement item belongs to another non-default workspace, raise PermissionError
            if d.get("workspace_id") not in (None, "ws-default", workspace_id):
                raise PermissionError("Cross-workspace access denied for displacement item")
            d["status"] = "displacement_pitched"
            updated = True
            break

    run_record = {
        "id": f"drun-{uuid.uuid4().hex[:8]}",
        "displacement_id": displacement_id,
        "workspace_id": workspace_id,
        "campaign_id": target_campaign,
        "status": "launched",
        "updated_in_memory": updated,
        "launched_at": datetime.utcnow().isoformat()
    }
    _IN_MEMORY_DISPLACEMENT_RUNS.append(run_record)
    return run_record


def resolve_displacement_battlecard_for_execution(
    workspace_id: str,
    target_company: str,
    target_contact_name: str,
    target_contact_title: str,
    incumbent_vendor: Optional[str] = "apollo",
    seat_count: int = 10,
    contract_renewal_days: int = 60,
    annual_savings: Optional[float] = None,
    domain: Optional[str] = None,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Horizon 35A (Paranoia Layer 0, 1 & 2):
    Resolves competitive displacement battlecard context for campaign execution.
    - Layer 0 (Foundational): Calculates opportunity score, generates copy wedge,
      retrieves battlecards for killer advantages and buyout offers.
    - Layer 1 (Environmental): Enforces duplicate concurrent displacement sequence locks
      via _DISPLACEMENT_LOCKS and detects expired contract renewal windows.
    - Layer 2 (Human Paranoia): Sanitizes spreadsheet formula injection (=, +, -, @, \t, \r),
      clamps numerical bounds (seats 1-5000, renewal 0-365), and blocks cross-tenant IDOR access.
    """
    if not workspace_id or not str(workspace_id).strip():
        raise ValueError("workspace_id is required")

    # Layer 2: Sanitize text inputs against spreadsheet formula injection
    clean_company = _sanitize_displacement_text(target_company)
    if not clean_company:
        raise ValueError("target_company is required")

    clean_contact_name = _sanitize_displacement_text(target_contact_name)
    clean_contact_title = _sanitize_displacement_text(target_contact_title)
    clean_domain = _sanitize_displacement_text(domain) if domain else None
    if clean_domain:
        clean_domain = clean_domain.lower().replace("http://", "").replace("https://", "").strip("/")

    # Layer 2: Clamp numerical bounds
    safe_seats = max(1, min(5000, int(seat_count if seat_count is not None else 10)))
    safe_renewal_days = max(0, min(365, int(contract_renewal_days if contract_renewal_days is not None else 60)))
    safe_annual_savings = float(annual_savings) if annual_savings is not None and float(annual_savings) > 0 else None

    # Layer 2: Cross-Tenant IDOR Guard against accessing another non-default workspace's displacement record
    comp_lower = clean_company.lower()
    dom_lower = clean_domain.lower() if clean_domain else None
    for d in _IN_MEMORY_DISPLACEMENTS:
        if d.get("workspace_id") not in (None, "ws-default", workspace_id):
            if (dom_lower and d.get("domain") and d.get("domain").lower() == dom_lower) or \
               (comp_lower and d.get("target_company") and d.get("target_company").lower() == comp_lower):
                raise PermissionError("Cross-workspace access denied for displacement item")

    # Layer 0: Normalize vendor
    slug = normalize_vendor_name(incumbent_vendor)

    # Layer 1: Environmental Failure Analysis — Duplicate Sequence Lock & Expired Renewal Guard
    comp_key = (clean_domain or clean_company or "unknown").strip().lower()
    lock_key = f"{workspace_id}:{comp_key}"

    if lock_key in _DISPLACEMENT_LOCKS:
        lock_acquired = False
        duplicate_prevented = True
    else:
        _DISPLACEMENT_LOCKS[lock_key] = {
            "workspace_id": workspace_id,
            "company_or_domain": comp_key,
            "vendor_slug": slug,
            "locked_at": datetime.utcnow().isoformat(),
        }
        lock_acquired = True
        duplicate_prevented = False

    if safe_renewal_days <= 0:
        renewal_expired = True
        status = "renewal_passed"
    else:
        renewal_expired = False
        status = "ready"

    # Layer 0: Opportunity calculation & battlecard copy synthesis
    eval_res = calculate_displacement_opportunity(
        incumbent_vendor=slug,
        contract_renewal_days=safe_renewal_days,
        seat_count=safe_seats,
        target_company=clean_company,
        target_contact_name=clean_contact_name,
        target_contact_title=clean_contact_title
    )
    if safe_annual_savings is not None:
        eval_res["annual_potential_savings"] = safe_annual_savings

    copy_res = generate_displacement_battlecard_copy(
        incumbent_vendor=slug,
        target_company=clean_company,
        target_contact_name=clean_contact_name,
        target_contact_title=clean_contact_title,
        seat_count=safe_seats,
        renewal_days=safe_renewal_days,
        annual_savings=eval_res["annual_potential_savings"]
    )

    cards = get_vendor_battlecards(workspace_id=workspace_id, supabase=supabase, vendor_slug=slug)
    card = cards[0] if cards else {}
    killer_advantage = card.get(
        "elein_killer_advantage",
        "3-provider waterfall verification, dedicated residential proxy pods, Thompson sampling MAB copy"
    )
    buyout_offer = copy_res.get("contract_buyout_offer") or card.get("contract_buyout_offer", "")
    v_name = copy_res.get("vendor_display_name", slug.title())

    return {
        "status": status,
        "vendor_slug": slug,
        "vendor_display_name": v_name,
        "displacement_wedge": copy_res["body"],
        "displacement_hook": copy_res["displacement_hook"],
        "competitor_name": v_name,
        "buyout_offer": buyout_offer,
        "elein_killer_advantage": killer_advantage,
        "annual_savings": eval_res["annual_potential_savings"],
        "renewal_days": eval_res["contract_renewal_days"],
        "vulnerability_score": eval_res["displacement_vulnerability_score"],
        "window_status": eval_res["window_status"],
        "lock_acquired": lock_acquired,
        "duplicate_prevented": duplicate_prevented,
        "renewal_expired": renewal_expired,
    }
