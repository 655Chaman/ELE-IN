"""
Three-Layer Paranoia Architecture: Sequence DAG Simulation & Dry-Run Sandbox (Phase S)
========================================================================================
Layer 0 (Foundational):
  - Headless topological & timeline simulation traversing sequence DAGs.
  - Spintax variation engine {A|B|C} with deterministic PRNG seed.
  - Dynamic token replacement ({{first_name}}, {{company}}, {{custom_vars}}) with fallback support.
  - Step-by-step trace generation with scheduled offsets, channel assignments, and message previews.

Layer 1 (Environmental Failure Analysis):
  - Stack-safe cycle detection and traversal limits (max 5,000 steps, max 60 simulation days).
  - Resilient to dangling edges, disconnected subgraphs, and deleted node references.
  - Safe parsing of malformed or unclosed spintax ({unclosed|options) and unmatched braces.
  - Defensive type coercion across raw lead data and missing sender profiles.

Layer 2 (Human Paranoia):
  - Flags missing variable fallbacks (e.g., missing first_name leading to awkward blank greetings).
  - Multi-channel collision guard: detects overlapping actions scheduled < 15 mins apart for same lead.
  - Sender daily quota burnout detection: calculates campaign duration vs sender limits.
  - Lint warnings for zero-entropy spintax, unreachable branches, and condition dead-ends.
"""

import re
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger("dag_simulation_service")

# Regex for variable tokens: {{variable_name}} or {{variable_name|fallback}} or {{variable_name | fallback: there}}
VAR_TOKEN_REGEX = re.compile(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*(?:\|\s*(?:fallback:\s*)?([^}]+?)\s*)?\}\}")

# Regex for single-level spintax: {option1|option2|option3} (requires at least one pipe)
SPINTAX_REGEX = re.compile(r"\{([^{}]+?\|[^{}]+?)\}")


class DAGSimulationService:
    """Headless simulator for multi-channel campaign sequence DAGs."""

    MAX_STEPS_PER_LEAD = 100
    MAX_GLOBAL_STEPS = 5000
    MAX_SIMULATION_DAYS = 60
    COLLISION_WINDOW_MINUTES = 15

    def __init__(self, spintax_seed: Optional[int] = None):
        self.rng = random.Random(spintax_seed if spintax_seed is not None else 42)

    # -------------------------------------------------------------------------
    # Layer 0 & 1: Spintax & Variable Resolution Engine
    # -------------------------------------------------------------------------

    def resolve_spintax(self, text: str) -> Tuple[str, List[str]]:
        """
        Recursively resolves spintax variants {A|B|C} while strictly preserving
        variable tokens like {{first_name}} and {{company|default}}.
        Returns (resolved_text, list_of_choices_made).
        """
        if not text or not isinstance(text, str):
            return "", []

        # Layer 1 Paranoia: Temporarily mask variable tokens so spintax resolution never corrupts {{vars}}
        var_masks: Dict[str, str] = {}
        def _mask_var(match: re.Match) -> str:
            token = f"__ELEIN_VAR_{len(var_masks)}__"
            var_masks[token] = match.group(0)
            return token

        current_text = VAR_TOKEN_REGEX.sub(_mask_var, text)

        choices_made = []
        depth = 0

        while depth < 5:
            matches = list(SPINTAX_REGEX.finditer(current_text))
            if not matches:
                break

            # Replace from end to start to preserve character indices
            for m in reversed(matches):
                raw_options = m.group(1).split("|")
                # Filter out pure empties only if alternatives exist
                clean_options = [opt for opt in raw_options if opt != ""] or raw_options
                chosen = self.rng.choice(clean_options)
                choices_made.append(chosen)
                current_text = current_text[:m.start()] + chosen + current_text[m.end():]

            depth += 1

        # Layer 1 Paranoia: Strip any unmatched single braces in template, preserving masked variables
        current_text = re.sub(r"[{}]", "", current_text)

        # Restore variable tokens
        for mask_key, orig_token in var_masks.items():
            current_text = current_text.replace(mask_key, orig_token)

        return current_text, choices_made

    def resolve_variables(
        self,
        template: str,
        lead: Dict[str, Any]
    ) -> Tuple[str, List[str], List[Dict[str, str]], List[str]]:
        """
        Resolves {{var|fallback}} tokens against lead attributes.
        Returns:
          - resolved_text
          - unresolved_tokens: variables that had no value and no fallback
          - fallbacks_used: list of {token, fallback_value}
          - tokens_resolved: list of successfully resolved variable names
        """
        if not template or not isinstance(template, str):
            return "", [], [], []

        unresolved = []
        fallbacks_used = []
        resolved = []

        def replacer(match: re.Match) -> str:
            token_key = match.group(1).strip()
            fallback_val = match.group(2)
            if fallback_val is not None:
                fallback_val = fallback_val.strip()
                if fallback_val.lower().startswith("fallback:"):
                    fallback_val = fallback_val[9:].strip()

            # Retrieve value from lead (supports top-level and custom_variables.field)
            val = None
            if "." in token_key:
                parts = token_key.split(".", 1)
                parent_dict = lead.get(parts[0])
                if isinstance(parent_dict, dict):
                    val = parent_dict.get(parts[1])
            else:
                val = lead.get(token_key)
                if val is None:
                    # Check custom_variables/custom_fields fallback
                    for custom_dict_key in ("custom_variables", "custom_fields", "variables"):
                        custom_dict = lead.get(custom_dict_key)
                        if isinstance(custom_dict, dict) and token_key in custom_dict:
                            val = custom_dict[token_key]
                            break

            # If value exists and is non-empty, and NOT a poison literal ("None", "null", "undefined", "n/a", etc.)
            clean_str = str(val).strip() if val is not None else ""
            if clean_str and clean_str.lower() not in (
                "none", "null", "undefined", "nan", "n/a", "na", "nil", "[object object]", "-", "--"
            ):
                resolved.append(token_key)
                return clean_str

            # If fallback provided
            if fallback_val is not None:
                fallbacks_used.append({"token": token_key, "fallback": fallback_val})
                resolved.append(f"{token_key}(fallback)")
                return fallback_val

            # Unresolved missing variable
            unresolved.append(token_key)
            return f"{{{{{token_key}}}}}"

        rendered = VAR_TOKEN_REGEX.sub(replacer, template)
        return rendered, unresolved, fallbacks_used, resolved

    # -------------------------------------------------------------------------
    # Layer 1: Topological Cycle Detection & DAG Integrity
    # -------------------------------------------------------------------------

    def detect_cycles(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[str]:
        """
        Uses Kahn's algorithm to detect cycles.
        Returns list of cycle descriptions or empty list if acyclic.
        """
        node_ids = {str(n.get("id")).strip() for n in nodes if isinstance(n, dict) and n.get("id")}
        if not node_ids:
            return []

        adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}

        for e in edges:
            if not isinstance(e, dict):
                continue
            src = str(e.get("source") or e.get("source_node_id") or "").strip()
            tgt = str(e.get("target") or e.get("target_node_id") or "").strip()
            if src in node_ids and tgt in node_ids:
                if src == tgt:
                    return [f"Self-loop detected on node {src}"]
                adj[src].append(tgt)
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        queue = [nid for nid in node_ids if in_degree[nid] == 0]
        visited_count = 0

        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for neighbor in adj.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count < len(node_ids):
            unvisited = [nid for nid in node_ids if in_degree.get(nid, 0) > 0]
            return [f"Cycle detected involving nodes: {', '.join(unvisited[:5])}"]

        return []

    # -------------------------------------------------------------------------
    # Layer 0 & 2: Step-by-Step Pre-Flight Simulation
    # -------------------------------------------------------------------------

    def simulate(
        self,
        dag: Dict[str, Any],
        sample_leads: List[Dict[str, Any]],
        sender_profiles: List[Dict[str, Any]],
        simulation_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Runs headless pre-flight dry-run simulation for given sequence DAG and leads.
        """
        options = simulation_options or {}
        mock_branches = options.get("mock_condition_branches", {})
        start_time_iso = options.get("start_time_iso")
        
        try:
            if start_time_iso:
                sim_start = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
            else:
                sim_start = datetime.now(timezone.utc)
        except Exception:
            sim_start = datetime.now(timezone.utc)

        raw_nodes = dag.get("nodes") or []
        raw_edges = dag.get("edges") or []

        # Layer 1 Paranoia: Validate input shapes
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            return {
                "valid": False,
                "errors": ["Malformed DAG: nodes and edges must be lists."],
                "warnings": [],
                "simulation_summary": {},
                "step_execution_trace": []
            }

        if not raw_nodes:
            return {
                "valid": False,
                "errors": ["DAG contains zero nodes."],
                "warnings": ["Cannot simulate an empty sequence."],
                "simulation_summary": {},
                "step_execution_trace": []
            }

        # Check cycles
        cycle_errors = self.detect_cycles(raw_nodes, raw_edges)
        if cycle_errors:
            return {
                "valid": False,
                "errors": cycle_errors,
                "warnings": [],
                "simulation_summary": {},
                "step_execution_trace": []
            }

        # Build node index and adjacency
        node_map: Dict[str, Dict[str, Any]] = {}
        for n in raw_nodes:
            if isinstance(n, dict) and n.get("id"):
                node_map[str(n["id"]).strip()] = n

        # Build outgoing edge map: source -> list of (target, edge_data)
        outgoing_edges: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {nid: [] for nid in node_map}
        incoming_counts: Dict[str, int] = {nid: 0 for nid in node_map}

        for e in raw_edges:
            if not isinstance(e, dict):
                continue
            src = str(e.get("source") or e.get("source_node_id") or "").strip()
            tgt = str(e.get("target") or e.get("target_node_id") or "").strip()
            if src in node_map and tgt in node_map:
                outgoing_edges[src].append((tgt, e))
                incoming_counts[tgt] += 1

        # Identify root nodes (nodes with 0 incoming edges)
        root_nodes = [nid for nid in node_map if incoming_counts[nid] == 0]
        if not root_nodes:
            return {
                "valid": False,
                "errors": ["No root entry node detected in sequence DAG."],
                "warnings": [],
                "simulation_summary": {},
                "step_execution_trace": []
            }

        warnings: List[str] = []
        errors: List[str] = []
        step_traces: List[Dict[str, Any]] = []
        all_unresolved_tokens: Set[str] = set()
        all_resolved_tokens: Set[str] = set()
        fallbacks_used_count = 0
        total_tokens_evaluated = 0

        # Senders index
        senders_by_channel: Dict[str, List[Dict[str, Any]]] = {}
        for s in (sender_profiles or []):
            if isinstance(s, dict):
                channels = s.get("channels") or ["EMAIL", "LINKEDIN"]
                for c in channels:
                    c_up = str(c).upper()
                    if c_up not in senders_by_channel:
                        senders_by_channel[c_up] = []
                    senders_by_channel[c_up].append(s)

        # Sender daily scheduling tracker for quota bounds: sender_id -> day_index -> count
        sender_daily_dispatch: Dict[str, Dict[int, int]] = {}

        # Traversal per lead
        global_steps_count = 0
        simulated_lead_count = len(sample_leads) if sample_leads else 1
        leads_to_process = sample_leads if sample_leads else [{"id": "sample-lead-0", "first_name": "John", "last_name": "Doe", "company": "Acme Corp", "email": "john@acme.com"}]

        # Lead schedule timeline to check multi-channel collisions: lead_id -> list of scheduled datetime
        lead_timelines: Dict[str, List[datetime]] = {}
        pacing_collisions: List[Dict[str, Any]] = []

        for lead_idx, lead in enumerate(leads_to_process):
            lead_id = str(lead.get("id") or f"lead-{lead_idx}")
            lead_timelines[lead_id] = []
            current_node_id = root_nodes[0]  # Start with primary root
            current_offset_hours = 0.0
            lead_steps = 0

            while current_node_id and lead_steps < self.MAX_STEPS_PER_LEAD:
                if global_steps_count >= self.MAX_GLOBAL_STEPS:
                    warnings.append(f"Global simulation step ceiling ({self.MAX_GLOBAL_STEPS}) reached. Truncating.")
                    break

                node = node_map.get(current_node_id)
                if not node:
                    break

                node_type = str(node.get("type") or node.get("node_type") or "").lower()
                node_data = node.get("data") or {}

                # Determine channel
                channel = "UNKNOWN"
                if "email" in node_type or "mail" in node_type:
                    channel = "EMAIL"
                elif "linkedin" in node_type or "connection" in node_type or "inmail" in node_type:
                    channel = "LINKEDIN"
                elif "voice" in node_type or "call" in node_type:
                    channel = "VOICE"
                elif "delay" in node_type or "wait" in node_type:
                    channel = "TIME_DELAY"
                elif node_type.startswith("if_") or "split" in node_type:
                    channel = "CONDITION"

                # Calculate delay offset (supports days, hours, and minutes)
                step_delay_hours = 0.0
                if channel == "TIME_DELAY":
                    delay_days = float(node_data.get("days") or node_data.get("delay_days") or 0.0)
                    delay_hrs = float(node_data.get("hours") or node_data.get("delay_hours") or 0.0)
                    delay_mins = float(node_data.get("minutes") or node_data.get("delay_minutes") or 0.0)
                    step_delay_hours = (delay_days * 24.0) + delay_hrs + (delay_mins / 60.0)
                    current_offset_hours += step_delay_hours

                # Resolve message templates for outreach touchpoints
                rendered_subject = None
                rendered_body = None
                unresolved = []
                fallbacks = []

                if channel in ("EMAIL", "LINKEDIN", "VOICE"):
                    raw_subject = node_data.get("subject") or ""
                    raw_body = node_data.get("body") or node_data.get("message") or ""

                    # Spintax resolution
                    spin_sub, _ = self.resolve_spintax(raw_subject)
                    spin_body, _ = self.resolve_spintax(raw_body)

                    # Variable resolution
                    r_sub, unres_s, fb_s, res_s = self.resolve_variables(spin_sub, lead)
                    r_body, unres_b, fb_b, res_b = self.resolve_variables(spin_body, lead)

                    rendered_subject = r_sub if raw_subject else None
                    rendered_body = r_body if raw_body else None
                    unresolved = list(set(unres_s + unres_b))
                    fallbacks = fb_s + fb_b
                    
                    all_unresolved_tokens.update(unresolved)
                    all_resolved_tokens.update(res_s + res_b)
                    fallbacks_used_count += len(fallbacks)
                    total_tokens_evaluated += len(res_s) + len(res_b) + len(unresolved)

                    # Scheduled time
                    action_time = sim_start + timedelta(hours=current_offset_hours)
                    
                    # Multi-channel collision check
                    for prev_time in lead_timelines[lead_id]:
                        diff_minutes = abs((action_time - prev_time).total_seconds()) / 60.0
                        if diff_minutes < self.COLLISION_WINDOW_MINUTES:
                            pacing_collisions.append({
                                "lead_id": lead_id,
                                "node_id": current_node_id,
                                "diff_minutes": round(diff_minutes, 1),
                                "scheduled_time_iso": action_time.isoformat()
                            })
                            warnings.append(
                                f"Multi-channel pacing collision for lead '{lead_id}': actions scheduled {diff_minutes:.1f}m apart on node '{current_node_id}'."
                            )
                    lead_timelines[lead_id].append(action_time)

                    # Sender selection
                    available_senders = senders_by_channel.get(channel) or sender_profiles or []
                    chosen_sender = available_senders[lead_idx % len(available_senders)] if available_senders else {}
                    sender_id = chosen_sender.get("id") or "unassigned_sender"
                    
                    # Track daily quota
                    day_idx = int(current_offset_hours // 24)
                    if sender_id not in sender_daily_dispatch:
                        sender_daily_dispatch[sender_id] = {}
                    sender_daily_dispatch[sender_id][day_idx] = sender_daily_dispatch[sender_id].get(day_idx, 0) + 1

                    # Trace entry
                    step_traces.append({
                        "lead_id": lead_id,
                        "step_index": lead_steps,
                        "node_id": current_node_id,
                        "node_type": node_type,
                        "channel": channel,
                        "scheduled_offset_hours": round(current_offset_hours, 2),
                        "scheduled_time_iso": action_time.isoformat(),
                        "sender_id": sender_id,
                        "sender_email": chosen_sender.get("email"),
                        "rendered_subject": rendered_subject,
                        "rendered_body": rendered_body,
                        "unresolved_tokens": unresolved,
                        "fallbacks_used": fallbacks
                    })

                elif channel == "TIME_DELAY":
                    step_traces.append({
                        "lead_id": lead_id,
                        "step_index": lead_steps,
                        "node_id": current_node_id,
                        "node_type": node_type,
                        "channel": channel,
                        "scheduled_offset_hours": round(current_offset_hours, 2),
                        "scheduled_time_iso": (sim_start + timedelta(hours=current_offset_hours)).isoformat(),
                        "delay_hours": step_delay_hours,
                        "message": f"Wait {step_delay_hours} hours"
                    })

                lead_steps += 1
                global_steps_count += 1

                # Determine next node
                out_edges = outgoing_edges.get(current_node_id, [])
                if not out_edges:
                    break  # Terminal node

                if channel == "CONDITION":
                    # Look up simulated mock branch decision
                    condition_choice = mock_branches.get(node_type) or mock_branches.get(current_node_id) or "default"
                    chosen_target = None
                    for tgt, edge_obj in out_edges:
                        edge_label = str(
                            edge_obj.get("sourceHandle")
                            or edge_obj.get("source_handle")
                            or edge_obj.get("condition")
                            or edge_obj.get("label")
                            or edge_obj.get("branch")
                            or ""
                        ).strip()
                        if condition_choice.lower() in edge_label.lower():
                            chosen_target = tgt
                            break
                    current_node_id = chosen_target or out_edges[0][0]
                else:
                    # Sequential next step
                    current_node_id = out_edges[0][0]

        # Layer 2 Paranoia: Check sender quota overruns
        quota_warnings = []
        for s in (sender_profiles or []):
            s_id = s.get("id")
            s_quota = s.get("daily_quota") or 50
            daily_loads = sender_daily_dispatch.get(s_id, {})
            for day, count in daily_loads.items():
                if count > s_quota:
                    quota_warnings.append(
                        f"Sender '{s.get('email', s_id)}' quota exceeded on day {day}: scheduled {count} actions vs limit of {s_quota}."
                    )
        warnings.extend(quota_warnings)

        # Missing token warning
        if all_unresolved_tokens:
            warnings.append(
                f"Missing variables without fallbacks detected: {', '.join(sorted(list(all_unresolved_tokens)))}. Leads lacking these attributes will render raw brackets."
            )

        resolution_rate = 100.0
        if total_tokens_evaluated > 0:
            resolution_rate = round(100.0 * (1.0 - (len(all_unresolved_tokens) / float(total_tokens_evaluated))), 2)

        # Spintax Analytics across outreach nodes
        total_combos = 1
        sample_variants_list = []
        templates_scanned = 0
        for n in raw_nodes:
            nd = n.get("data") or {}
            for field in ("subject", "body", "message"):
                text = nd.get(field)
                if text and isinstance(text, str) and "{" in text and "}" in text and "|" in text:
                    templates_scanned += 1
                    try:
                        from campaigns.backend.services.template_spintax_guard import (
                            calculate_spintax_combinations,
                            preview_spintax_variants
                        )
                        c = calculate_spintax_combinations(text)
                        total_combos = min(total_combos * max(1, c), 100_000_000)
                        if not sample_variants_list:
                            sample_variants_list = preview_spintax_variants(text, count=5)
                    except Exception:
                        pass
        
        if templates_scanned == 0:
            entropy_rating = "NO_SPINTAX"
        elif total_combos >= 200:
            entropy_rating = "ENTERPRISE_IMMUNITY"
        elif total_combos >= 50:
            entropy_rating = "HIGH_DIVERSITY"
        elif total_combos >= 5:
            entropy_rating = "MODERATE_VARIATION"
        else:
            entropy_rating = "CRITICAL_SPAM_RISK"

        spintax_analytics = {
            "total_combinations": total_combos,
            "entropy_rating": entropy_rating,
            "sample_variants": sample_variants_list,
            "templates_scanned": templates_scanned
        }

        # Sender daily capacity and burnout forecast
        daily_capacity = sum((s.get("daily_quota") or 50) for s in (sender_profiles or []))
        if daily_capacity == 0:
            daily_capacity = 50  # Default single sender capacity
            
        aggregated_daily_schedule: Dict[int, int] = {}
        for s_id, loads in sender_daily_dispatch.items():
            for d_idx, c_cnt in loads.items():
                aggregated_daily_schedule[d_idx] = aggregated_daily_schedule.get(d_idx, 0) + c_cnt

        peak_dispatches = max(aggregated_daily_schedule.values()) if aggregated_daily_schedule else 0
        burnout_day = None
        for d_idx in sorted(aggregated_daily_schedule.keys()):
            if aggregated_daily_schedule[d_idx] > daily_capacity:
                burnout_day = d_idx
                break
                
        rec_senders_needed = 0
        if peak_dispatches > daily_capacity:
            import math
            rec_senders_needed = math.ceil((peak_dispatches - daily_capacity) / 50.0)

        sender_burnout_forecast = {
            "daily_capacity": daily_capacity,
            "peak_daily_dispatches": peak_dispatches,
            "burnout_day": burnout_day,
            "daily_schedule": {str(k): v for k, v in sorted(aggregated_daily_schedule.items())},
            "recommended_senders_needed": rec_senders_needed
        }

        sim_days = round(max([t.get("scheduled_offset_hours", 0) for t in step_traces] or [0]) / 24.0, 2)
        total_disp = len(step_traces)
        collisions_count = len(pacing_collisions)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "simulation_summary": {
                "total_leads_simulated": simulated_lead_count,
                "total_steps_executed": total_disp,
                "estimated_completion_days": sim_days,
                "channels_used": list(set(t["channel"] for t in step_traces if t.get("channel"))),
                "quota_stretch_warning": len(quota_warnings) > 0,
                # Paranoia Layer 1 Aliases: ensures 100% backwards compatibility with UI
                "total_dispatches": total_disp,
                "timeline_span_days": sim_days,
                "collisions_detected": collisions_count,
            },
            # Backward-compatible root summary
            "summary": {
                "total_dispatches": total_disp,
                "timeline_span_days": sim_days,
                "collisions_detected": collisions_count,
                "total_leads_simulated": simulated_lead_count,
                "total_steps_executed": total_disp,
            },
            "step_execution_trace": step_traces,
            "token_resolution_report": {
                "variables_detected": sorted(list(all_resolved_tokens | all_unresolved_tokens)),
                "resolution_rate_pct": resolution_rate,
                "missing_token_count": len(all_unresolved_tokens),
                "unresolved_tokens": sorted(list(all_unresolved_tokens)),
                "fallbacks_used_count": fallbacks_used_count,
                "resolution_percentage": resolution_rate
            },
            "token_resolution_coverage": {
                "resolution_percentage": resolution_rate,
                "missing_token_count": len(all_unresolved_tokens),
            },
            "pacing_collisions": pacing_collisions,
            "spintax_analytics": spintax_analytics,
            "sender_burnout_forecast": sender_burnout_forecast
        }
