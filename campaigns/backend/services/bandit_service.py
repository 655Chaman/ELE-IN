import random
import math
import logging
import uuid
import csv
import io
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Paranoia Layer 1 & 2: UUID normalization and formula injection defense
def _normalize_uuid(val: Optional[str], namespace_prefix: str = "bandit") -> Optional[str]:
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


# Paranoia Layer 1: In-memory store for zero-migration resilience & sticky lead-to-arm locks
_IN_MEMORY_EXPERIMENTS: Dict[str, Dict[str, Any]] = {}
_IN_MEMORY_VARIANTS: Dict[str, List[Dict[str, Any]]] = {}
_LEAD_ARM_LOCKS: Dict[str, Dict[str, Any]] = {}

DEFAULT_SEED_VARIANTS = [
    {
        "id": "var-challenger-1",
        "name": "Challenger Angle (ROI/Metric Hook)",
        "arm_type": "full_message",
        "template_text": "Hey {{first_name}}, saw your team is expanding outbound. Most heads of revenue we speak with are burning 60% of their outreach budget on dead emails. We fixed this at scale for B2B teams. Open to seeing the benchmark?",
        "alpha_param": 6.0,
        "beta_param": 18.0,
        "impressions": 24,
        "positive_replies": 5,
        "objections": 2,
        "unsubscribes": 1,
        "status": "active",
        "generation": 1,
    },
    {
        "id": "var-consultative-2",
        "name": "Consultative Peer (Low-Friction Benchmark)",
        "arm_type": "full_message",
        "template_text": "Hi {{first_name}}, curious how {{company}} is handling LinkedIn connection saturation this quarter? We put together a short teardown on 3 messaging shifts that doubled acceptance rates. Thought it might be helpful—mind if I share it over?",
        "alpha_param": 9.0,
        "beta_param": 15.0,
        "impressions": 24,
        "positive_replies": 8,
        "objections": 1,
        "unsubscribes": 0,
        "status": "active",
        "generation": 1,
    },
    {
        "id": "var-direct-3",
        "name": "Direct Executive Brevity",
        "arm_type": "full_message",
        "template_text": "{{first_name}} — quick question: are you open to automated multi-channel sequences that pre-warm prospects on LinkedIn before emailing them? Happy to send a 2-min demo if timing is right.",
        "alpha_param": 3.0,
        "beta_param": 21.0,
        "impressions": 24,
        "positive_replies": 2,
        "objections": 4,
        "unsubscribes": 2,
        "status": "degraded",
        "generation": 1,
    }
]


def beta_sample(alpha: float, beta: float) -> float:
    """
    Paranoia Layer 0 & 1: Samples from Beta(alpha, beta) using random.betavariate.
    Guarantees alpha, beta >= 1.0 to prevent domain errors.
    """
    safe_alpha = max(1.0, float(alpha))
    safe_beta = max(1.0, float(beta))
    try:
        return random.betavariate(safe_alpha, safe_beta)
    except Exception:
        # Fallback to mean if sampling throws float exception
        return safe_alpha / (safe_alpha + safe_beta)


def calculate_beta_credible_interval(alpha: float, beta: float, confidence: float = 0.95) -> Tuple[float, float]:
    """
    Paranoia Layer 0: Calculates normal approximation of Beta credible interval.
    """
    safe_alpha = max(1.0, float(alpha))
    safe_beta = max(1.0, float(beta))
    mean = safe_alpha / (safe_alpha + safe_beta)
    variance = (safe_alpha * safe_beta) / (((safe_alpha + safe_beta) ** 2) * (safe_alpha + safe_beta + 1))
    std_dev = math.sqrt(variance)
    
    # 95% confidence z ~ 1.96
    z = 1.96 if confidence == 0.95 else 1.645
    lower = max(0.0, mean - (z * std_dev))
    upper = min(1.0, mean + (z * std_dev))
    return round(lower, 4), round(upper, 4)


def compute_monte_carlo_win_probabilities(variants: List[Dict[str, Any]], num_draws: int = 1000) -> Dict[str, float]:
    """
    Paranoia Layer 0: Computes P(variant_i is optimal) using Monte Carlo sampling.
    """
    if not variants:
        return {}
    if len(variants) == 1:
        return {variants[0]["id"]: 1.0}
    
    win_counts = {v["id"]: 0 for v in variants}
    
    for _ in range(num_draws):
        best_id = None
        best_sample = -1.0
        for v in variants:
            sample = beta_sample(v.get("alpha_param", 1.0), v.get("beta_param", 1.0))
            if sample > best_sample:
                best_sample = sample
                best_id = v["id"]
        if best_id:
            win_counts[best_id] += 1
            
    return {v_id: round(wins / num_draws, 4) for v_id, wins in win_counts.items()}


def get_or_create_experiment(
    workspace_id: str,
    campaign_id: Optional[str] = None,
    node_id: Optional[str] = None,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 1: Fetches or lazily instantiates a bandit experiment with defensive DB fallback.
    """
    exp_key = f"{workspace_id}:{campaign_id or 'global'}" if not node_id else f"{workspace_id}:{campaign_id or 'global'}:{node_id}"
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    norm_camp = _normalize_uuid(campaign_id, "campaign") if campaign_id else None
    
    if supabase:
        try:
            query = supabase.table("bandit_experiments").select("*").eq("workspace_id", norm_ws)
            if norm_camp:
                query = query.eq("campaign_id", norm_camp)
            res = query.limit(1).execute()
            if res.data and len(res.data) > 0:
                exp = res.data[0]
                # Fetch variants with workspace scoping
                var_res = supabase.table("copy_variants").select("*").eq("experiment_id", exp["id"]).eq("workspace_id", norm_ws).execute()
                variants = var_res.data or []
                if not variants:
                    # Seed default variants with safe UUIDs and sanitized copy
                    for seed in DEFAULT_SEED_VARIANTS:
                        seed_copy = dict(seed)
                        seed_copy["id"] = _normalize_uuid(seed["id"], "variant")
                        seed_copy["experiment_id"] = exp["id"]
                        seed_copy["workspace_id"] = norm_ws
                        seed_copy["name"] = sanitize_text(seed["name"])
                        seed_copy["template_text"] = sanitize_text(seed["template_text"])
                        supabase.table("copy_variants").insert(seed_copy).execute()
                    variants = DEFAULT_SEED_VARIANTS
                return {"experiment": exp, "variants": variants}
        except Exception as e:
            logger.warning(f"Bandit DB query failed (falling back to memory): {e}")

    # In-memory fallback
    if exp_key not in _IN_MEMORY_EXPERIMENTS:
        exp_id = f"exp-{abs(hash(exp_key)) % 100000}"
        _IN_MEMORY_EXPERIMENTS[exp_key] = {
            "id": exp_id,
            "workspace_id": workspace_id,
            "campaign_id": campaign_id,
            "node_id": node_id or "node-send-1",
            "name": "Dynamic Copy Thompson Bandit",
            "status": "active",
            "exploration_factor": 1.0,
            "created_at": datetime.utcnow().isoformat()
        }
        _IN_MEMORY_VARIANTS[exp_id] = [dict(v, experiment_id=exp_id, workspace_id=workspace_id) for v in DEFAULT_SEED_VARIANTS]

    exp = _IN_MEMORY_EXPERIMENTS[exp_key]
    if exp["id"] not in _IN_MEMORY_VARIANTS or not _IN_MEMORY_VARIANTS[exp["id"]]:
        _IN_MEMORY_VARIANTS[exp["id"]] = [dict(v, experiment_id=exp["id"], workspace_id=workspace_id) for v in DEFAULT_SEED_VARIANTS]
    variants = _IN_MEMORY_VARIANTS.get(exp["id"], [])
    return {"experiment": exp, "variants": variants}


def select_variant_thompson_sampling(
    workspace_id: str,
    campaign_id: Optional[str] = None,
    supabase: Optional[Any] = None,
    node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    Executes Thompson Sampling across active arms.
    Returns chosen variant with full Bayesian telemetry.
    """
    exp_data = get_or_create_experiment(workspace_id, campaign_id, node_id=node_id, supabase=supabase)
    variants = exp_data.get("variants", [])
    
    # Filter for active or degraded (still explored with lower probability)
    active_variants = [v for v in variants if v.get("status") in ("active", "degraded")]
    if not active_variants:
        # Paranoia Layer 2: Safety guard - never leave arms empty
        active_variants = variants or DEFAULT_SEED_VARIANTS

    # Draw from Beta posteriors
    sampled_scores = {}
    for v in active_variants:
        sampled_scores[v["id"]] = beta_sample(v.get("alpha_param", 1.0), v.get("beta_param", 1.0))
        
    selected_id = max(sampled_scores, key=sampled_scores.get)
    selected_variant = next(v for v in active_variants if v["id"] == selected_id)
    
    # Monte Carlo winning probabilities
    win_probs = compute_monte_carlo_win_probabilities(active_variants)
    
    # Enrich variants with stats
    enriched_variants = []
    for v in active_variants:
        a = v.get("alpha_param", 1.0)
        b = v.get("beta_param", 1.0)
        mean_cvr = a / (a + b)
        ci_lower, ci_upper = calculate_beta_credible_interval(a, b)
        enriched_variants.append({
            **v,
            "sampled_theta": round(sampled_scores.get(v["id"], 0.0), 4),
            "expected_cvr": round(mean_cvr, 4),
            "credible_interval_95": [ci_lower, ci_upper],
            "win_probability": win_probs.get(v["id"], 0.0),
            "is_selected": v["id"] == selected_id
        })

    return {
        "status": "success",
        "experiment_id": exp_data["experiment"]["id"],
        "selected_variant_id": selected_id,
        "selected_variant": selected_variant,
        "template_text": selected_variant.get("template_text"),
        "all_arms": enriched_variants
    }


def resolve_bandit_arm_for_execution(
    workspace_id: str,
    campaign_id: Optional[str] = None,
    node_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    inline_variants: Optional[List[Dict[str, Any]]] = None,
    sticky: bool = True,
    supabase: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Horizon 31 (Layer 0, 1, 2):
    Resolves a copy variant arm for live sequence node execution via Thompson Sampling.
    - Supports inline node-configured `bandit_variants` (with formula-injection sanitization).
    - Enforces sticky lead-to-arm idempotency (`_LEAD_ARM_LOCKS`) so retries for the same lead
      on the same node never flip copy angles mid-flight or double-count impressions.
    """
    safe_ws = str(workspace_id or "ws-default").strip()
    norm_ws = _normalize_uuid(safe_ws, "workspace")
    lock_key = f"{safe_ws}:{campaign_id or 'global'}:{node_id or 'default'}:{lead_id}" if lead_id else None

    if sticky and lock_key and lock_key in _LEAD_ARM_LOCKS:
        cached = dict(_LEAD_ARM_LOCKS[lock_key])
        cached["sticky_hit"] = True
        return cached

    exp_data = get_or_create_experiment(safe_ws, campaign_id, node_id=node_id, supabase=supabase)
    exp_id = exp_data["experiment"]["id"]

    # If inline_variants are configured on the node, register/synchronize them safely
    if inline_variants and isinstance(inline_variants, list):
        sanitized_inline: List[Dict[str, Any]] = []
        existing_by_id = {v.get("id"): v for v in _IN_MEMORY_VARIANTS.get(exp_id, [])}
        for idx, raw_v in enumerate(inline_variants):
            if not isinstance(raw_v, dict):
                continue
            v_id = str(raw_v.get("id") or f"inline-{node_id or 'node'}-{idx + 1}").strip()
            if v_id in existing_by_id:
                sanitized_inline.append(existing_by_id[v_id])
                continue
            clean_name = sanitize_text(raw_v.get("name") or f"Variant {chr(65 + (idx % 26))}")
            clean_text = sanitize_text(raw_v.get("template_text") or raw_v.get("body") or raw_v.get("note") or "")
            clean_subj = sanitize_text(raw_v.get("subject") or "")
            if not clean_text and not clean_subj:
                continue
            arm_entry = {
                "id": v_id,
                "experiment_id": exp_id,
                "workspace_id": safe_ws,
                "normalized_workspace_id": norm_ws,
                "name": clean_name,
                "arm_type": raw_v.get("arm_type", "full_message"),
                "template_text": clean_text,
                "subject": clean_subj,
                "branch": raw_v.get("branch"),
                "alpha_param": max(1.0, float(raw_v.get("alpha_param", 2.0))),
                "beta_param": max(1.0, float(raw_v.get("beta_param", 2.0))),
                "impressions": int(raw_v.get("impressions", 0)),
                "positive_replies": int(raw_v.get("positive_replies", 0)),
                "objections": int(raw_v.get("objections", 0)),
                "unsubscribes": int(raw_v.get("unsubscribes", 0)),
                "status": raw_v.get("status", "active"),
                "generation": int(raw_v.get("generation", 1)),
            }
            sanitized_inline.append(arm_entry)
        if sanitized_inline:
            # Preserve any auto-mutated challenger arms already in this experiment
            existing_challengers = [
                v for v in _IN_MEMORY_VARIANTS.get(exp_id, [])
                if v.get("parent_variant_id") and v.get("id") not in {x["id"] for x in sanitized_inline}
            ]
            _IN_MEMORY_VARIANTS[exp_id] = sanitized_inline + existing_challengers

    selection = select_variant_thompson_sampling(safe_ws, campaign_id, supabase=supabase, node_id=node_id)
    selected_variant = selection["selected_variant"]
    selected_id = selection["selected_variant_id"]

    # Record impression on in-memory variant
    for v in _IN_MEMORY_VARIANTS.get(exp_id, []):
        if v.get("id") == selected_id:
            v["impressions"] = int(v.get("impressions", 0)) + 1
            break

    result = {
        "status": "success",
        "experiment_id": exp_id,
        "selected_variant_id": selected_id,
        "selected_variant": selected_variant,
        "template_text": selected_variant.get("template_text", ""),
        "subject": selected_variant.get("subject", ""),
        "arm_name": selected_variant.get("name", ""),
        "branch": selected_variant.get("branch"),
        "sticky_hit": False,
        "all_arms": selection.get("all_arms", []),
    }

    if sticky and lock_key:
        _LEAD_ARM_LOCKS[lock_key] = dict(result)

    return result


def record_variant_feedback(
    variant_id: str,
    outcome: str,  # 'positive_reply', 'meeting_booked', 'objection', 'unsubscribe', 'no_reply'
    workspace_id: str,
    decay_factor: float = 1.0,
    supabase: Optional[Any] = None,
    auto_heal: bool = True,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Updates Beta parameters upon lead interaction.
    Tenant-isolated by workspace_id.
    Positive replies/meetings -> alpha increment.
    Objections/unsubscribes/no_reply -> beta increment.
    When an arm degrades and `auto_heal=True`, automatically spawns a self-healing challenger arm.
    """
    valid_outcomes = {'positive_reply', 'meeting_booked', 'closed_won', 'closed_lost', 'objection', 'unsubscribe', 'no_reply'}
    if outcome not in valid_outcomes:
        outcome = 'no_reply'

    alpha_delta = 0.0
    beta_delta = 0.0
    
    if outcome in ('positive_reply', 'meeting_booked', 'closed_won'):
        alpha_delta = 3.0 if outcome == 'closed_won' else (2.0 if outcome == 'meeting_booked' else 1.0)
    elif outcome in ('objection', 'unsubscribe'):
        beta_delta = 1.5 if outcome == 'unsubscribe' else 1.0
    else:  # no_reply or closed_lost
        beta_delta = 0.5

    updated_variant = None
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    norm_var = _normalize_uuid(variant_id, "variant")

    if supabase:
        try:
            # Query existing variant with workspace check
            res = supabase.table("copy_variants").select("*").eq("id", norm_var).eq("workspace_id", norm_ws).limit(1).execute()
            if not res.data:
                res = supabase.table("copy_variants").select("*").eq("id", variant_id).limit(1).execute()

            if res.data and len(res.data) > 0:
                cur = res.data[0]
                cur_ws = cur.get("workspace_id")
                if cur_ws and cur_ws not in (workspace_id, norm_ws):
                    raise PermissionError("Cross-workspace access denied for bandit variant")
                new_alpha = max(1.0, (cur.get("alpha_param", 1.0) * decay_factor) + alpha_delta)
                new_beta = max(1.0, (cur.get("beta_param", 1.0) * decay_factor) + beta_delta)
                new_impressions = cur.get("impressions", 0) + 1
                pos_replies = cur.get("positive_replies", 0) + (1 if alpha_delta > 0 else 0)
                objs = cur.get("objections", 0) + (1 if outcome == 'objection' else 0)
                unsubs = cur.get("unsubscribes", 0) + (1 if outcome == 'unsubscribe' else 0)
                
                # Check degradation
                status = cur.get("status", "active")
                if new_impressions >= 10 and (pos_replies / new_impressions < 0.08 or objs / new_impressions > 0.25):
                    status = "degraded"

                up_res = supabase.table("copy_variants").update({
                    "alpha_param": new_alpha,
                    "beta_param": new_beta,
                    "impressions": new_impressions,
                    "positive_replies": pos_replies,
                    "objections": objs,
                    "unsubscribes": unsubs,
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", cur["id"]).execute()
                if up_res.data:
                    updated_variant = up_res.data[0]
        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Failed to record feedback to Supabase: {e}")

    # Update in-memory fallback (scoped to caller's workspace first)
    if not updated_variant:
        get_or_create_experiment(workspace_id)
        foreign_match = False
        for exp_id, v_list in _IN_MEMORY_VARIANTS.items():
            for v in v_list:
                if v["id"] == variant_id:
                    v_ws = v.get("workspace_id")
                    if v_ws and v_ws not in (workspace_id, norm_ws):
                        foreign_match = True
                        continue
                    v["alpha_param"] = max(1.0, (v.get("alpha_param", 1.0) * decay_factor) + alpha_delta)
                    v["beta_param"] = max(1.0, (v.get("beta_param", 1.0) * decay_factor) + beta_delta)
                    v["impressions"] = v.get("impressions", 0) + 1
                    if alpha_delta > 0:
                        v["positive_replies"] = v.get("positive_replies", 0) + 1
                    if outcome == 'objection':
                        v["objections"] = v.get("objections", 0) + 1
                    if outcome == 'unsubscribe':
                        v["unsubscribes"] = v.get("unsubscribes", 0) + 1
                    if v["impressions"] >= 10 and (v["positive_replies"] / v["impressions"] < 0.08 or v["objections"] / v["impressions"] > 0.25):
                        v["status"] = "degraded"
                    updated_variant = dict(v)
                    break
            if updated_variant:
                break

        if not updated_variant and foreign_match:
            raise PermissionError("Cross-workspace access denied for bandit variant")

    arm_status = updated_variant.get("status") if updated_variant else "active"
    response_payload: Dict[str, Any] = {
        "status": "success",
        "variant_id": variant_id,
        "outcome": outcome,
        "alpha_param": updated_variant.get("alpha_param") if updated_variant else 1.0,
        "beta_param": updated_variant.get("beta_param") if updated_variant else 1.0,
        "arm_status": arm_status,
    }

    # Horizon 31 Layer 1: Autonomous self-healing when an arm degrades
    if auto_heal and arm_status == "degraded":
        already_spawned = False
        for _, v_list in _IN_MEMORY_VARIANTS.items():
            for v in v_list:
                if v.get("parent_variant_id") == variant_id and v.get("workspace_id") in (workspace_id, norm_ws):
                    already_spawned = True
                    response_payload["auto_mutated_challenger"] = v
                    response_payload["auto_healed"] = True
                    break
        if not already_spawned:
            try:
                mut_res = mutate_self_healing_variant(
                    parent_variant_id=variant_id,
                    workspace_id=workspace_id,
                    mutation_theme="social_proof_metric",
                    supabase=supabase,
                    retire_parent=False,
                )
                if mut_res.get("challenger_variant"):
                    response_payload["auto_mutated_challenger"] = mut_res["challenger_variant"]
                    response_payload["auto_healed"] = True
            except Exception as mut_err:
                logger.warning(f"Auto self-healing mutation skipped: {mut_err}")

    return response_payload


def mutate_self_healing_variant(
    parent_variant_id: str,
    workspace_id: str,
    mutation_theme: Optional[str] = "social_proof_metric",
    supabase: Optional[Any] = None,
    retire_parent: bool = True,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Autonomous genetic copy mutation.
    Tenant-isolated by workspace_id.
    Retires degraded variant and synthesizes next-generation challenger arm.
    """
    parent = None
    exp_id = None
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    norm_parent = _normalize_uuid(parent_variant_id, "variant")
    safe_theme = sanitize_text(mutation_theme) or "social_proof_metric"

    if supabase:
        try:
            res = supabase.table("copy_variants").select("*").eq("id", norm_parent).eq("workspace_id", norm_ws).limit(1).execute()
            if not res.data:
                res = supabase.table("copy_variants").select("*").eq("id", parent_variant_id).limit(1).execute()
            if res.data:
                cand = res.data[0]
                cand_ws = cand.get("workspace_id")
                if cand_ws and cand_ws not in (workspace_id, norm_ws):
                    raise PermissionError("Cross-workspace access denied for bandit variant")
                parent = cand
                exp_id = parent.get("experiment_id")
        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Could not load parent variant from DB: {e}")

    foreign_match = False
    if not parent:
        for e_id, v_list in _IN_MEMORY_VARIANTS.items():
            for v in v_list:
                if v["id"] == parent_variant_id:
                    v_ws = v.get("workspace_id")
                    if v_ws and v_ws not in (workspace_id, norm_ws):
                        foreign_match = True
                        continue
                    parent = v
                    exp_id = e_id
                    break
            if parent:
                break

    if not parent and foreign_match:
        raise PermissionError("Cross-workspace access denied for bandit variant")

    if not parent:
        get_or_create_experiment(workspace_id)
        for e_id, v_list in _IN_MEMORY_VARIANTS.items():
            for v in v_list:
                if v["id"] == parent_variant_id and v.get("workspace_id") in (workspace_id, norm_ws, None):
                    parent = v
                    exp_id = e_id
                    break
            if parent:
                break

    if not parent:
        parent = DEFAULT_SEED_VARIANTS[0]
        exp_id = "exp-default"

    new_gen = parent.get("generation", 1) + 1
    # Prevent unbound generation count
    if new_gen > 10:
        new_gen = 10

    # Mutate copy
    challenger_templates = [
        "Hi {{first_name}}, rather than a generic pitch: we recently helped {{company}}'s peers reduce outreach bounce rates by 42% in 14 days. Thought this 2-page case summary might be relevant. Worth a brief look?",
        "{{first_name}} — saw your team's focus on revenue efficiency. We built a framework that pre-warms key accounts before sending email, driving a 3.4x reply lift. Would you be open to the teardown?",
        "Quick note {{first_name}}: we analyzed 1,000+ outreach sequences in your space and found 80% stall after step 2. We put together the exact fix that unblocks pipeline. Want the free breakdown?"
    ]
    mutated_text = challenger_templates[new_gen % len(challenger_templates)]
    challenger_name = f"Gen {new_gen} Challenger ({parent.get('name', 'Arm').split('(')[0].strip()})"
    new_variant_uuid = str(uuid.uuid4())

    challenger_arm = {
        "id": new_variant_uuid,
        "experiment_id": exp_id,
        "workspace_id": norm_ws,
        "name": challenger_name,
        "arm_type": parent.get("arm_type", "full_message"),
        "template_text": mutated_text,
        "alpha_param": 2.0,  # Warm exploratory prior
        "beta_param": 2.0,
        "impressions": 0,
        "positive_replies": 0,
        "objections": 0,
        "unsubscribes": 0,
        "status": "active",
        "parent_variant_id": parent.get("id"),
        "generation": new_gen,
        "mutation_notes": f"Mutated from {parent.get('name')} due to performance degradation. Angle pivoted toward {safe_theme}."
    }

    if supabase:
        try:
            if retire_parent:
                supabase.table("copy_variants").update({"status": "retired"}).eq("id", parent.get("id")).execute()
            # Insert challenger
            res = supabase.table("copy_variants").insert(challenger_arm).execute()
            if res.data:
                challenger_arm = res.data[0]
        except Exception as e:
            logger.warning(f"Could not persist mutated variant to DB: {e}")

    # Update in memory
    if exp_id in _IN_MEMORY_VARIANTS:
        if retire_parent:
            for v in _IN_MEMORY_VARIANTS[exp_id]:
                if v["id"] == parent_variant_id:
                    v["status"] = "retired"
        _IN_MEMORY_VARIANTS[exp_id].append(challenger_arm)

    return {
        "status": "success",
        "challenger_variant": challenger_arm,
        "retired_parent_id": parent_variant_id,
        "message": f"Successfully spawned Generation {new_gen} challenger variant!"
    }


def add_custom_variant(
    workspace_id: str,
    campaign_id: Optional[str] = None,
    name: str = "Custom Variant",
    template_text: str = "",
    arm_type: str = "full_message",
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Registers an operator-authored copy variant into the Thompson Bandit arm pool.
    Guarantees sanitized inputs, exploratory priors, and persistent storage with in-memory fallback.
    """
    clean_name = sanitize_text(name) or "Custom Challenger Arm"
    clean_text = sanitize_text(template_text)
    if not clean_text:
        clean_text = "Hi {{first_name}}, following up on our discussion—would you be open to reviewing our efficiency benchmark?"
    
    clean_arm_type = arm_type if arm_type in ("hook", "value_prop", "cta", "full_message") else "full_message"
    
    exp_data = get_or_create_experiment(workspace_id, campaign_id, supabase=supabase)
    exp = exp_data.get("experiment", {})
    exp_id = exp.get("id") or "exp-default"
    
    norm_ws = _normalize_uuid(workspace_id, "workspace")
    variant_id = str(uuid.uuid4())
    
    custom_arm = {
        "id": variant_id,
        "experiment_id": exp_id,
        "workspace_id": norm_ws,
        "name": clean_name[:120],
        "arm_type": clean_arm_type,
        "template_text": clean_text[:2000],
        "alpha_param": 2.0,
        "beta_param": 2.0,
        "impressions": 0,
        "positive_replies": 0,
        "objections": 0,
        "unsubscribes": 0,
        "status": "active",
        "generation": 1,
        "mutation_notes": "Operator-defined custom variant arm."
    }
    
    if supabase:
        try:
            res = supabase.table("copy_variants").insert(custom_arm).execute()
            if res.data and len(res.data) > 0:
                custom_arm = res.data[0]
        except Exception as e:
            logger.warning(f"Could not persist custom variant to DB: {e}")
            
    if exp_id in _IN_MEMORY_VARIANTS:
        _IN_MEMORY_VARIANTS[exp_id].append(custom_arm)
    else:
        _IN_MEMORY_VARIANTS[exp_id] = [custom_arm]
        
    return {
        "status": "success",
        "message": f"Added custom variant '{clean_name}' into Thompson Sampling pool.",
        "variant": custom_arm
    }


def export_bandit_telemetry_csv(
    workspace_id: str,
    campaign_id: Optional[str] = None,
    supabase: Optional[Any] = None
) -> str:
    """
    Paranoia Layer 0 & 2: Exports full Bayesian MAB arm performance and credible intervals to CSV.
    Enforces spreadsheet formula injection neutralization on all text fields.
    """
    telemetry = select_variant_thompson_sampling(workspace_id, campaign_id, supabase=supabase)
    arms = telemetry.get("all_arms", [])
    
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Variant ID",
        "Name",
        "Arm Type",
        "Status",
        "Generation",
        "Alpha",
        "Beta",
        "Impressions",
        "Positive Replies",
        "Objections",
        "Unsubscribes",
        "Expected CVR",
        "95% Credible Interval",
        "Win Probability",
        "Template Text"
    ])
    
    for arm in arms:
        name_safe = sanitize_text(arm.get("name", ""))
        text_safe = sanitize_text(arm.get("template_text", ""))
        
        cvr = round((arm.get("expected_cvr", 0.0) or 0.0) * 100, 2)
        win_p = round((arm.get("win_probability", 0.0) or 0.0) * 100, 2)
        ci = arm.get("credible_interval_95") or [0.0, 0.0]
        ci_str = f"[{round(ci[0] * 100, 1)}% - {round(ci[1] * 100, 1)}%]"
        
        writer.writerow([
            arm.get("id"),
            name_safe,
            arm.get("arm_type", "full_message"),
            arm.get("status", "active"),
            arm.get("generation", 1),
            arm.get("alpha_param", 1.0),
            arm.get("beta_param", 1.0),
            arm.get("impressions", 0),
            arm.get("positive_replies", 0),
            arm.get("objections", 0),
            arm.get("unsubscribes", 0),
            f"{cvr}%",
            ci_str,
            f"{win_p}%",
            text_safe
        ])
        
    return output.getvalue()
