"""
Three-Layer Paranoia Framework: Template Variable Sanitization, Pipe-Fallback & Spintax Guard
- Layer 0 (Foundational): Supports {{variable | fallback}} pipe syntax, lead.<field> namespaces,
  and {option1|option2} (including nested) spintax resolution.
- Layer 1 (Environmental): Scrubs poison enrichment literals ("None", "null", "undefined", "N/A",
  "nan", "[object Object]") so missing scraper fields trigger clean fallbacks instead of sending
  "Hi None, saw you work at null".
- Layer 2 (Human Paranoia): Pre-activation validator detects unclosed '{{' or '}}', mismatched
  '{var}}' / '{{var}', unbalanced spintax braces '{a|b', empty spintax options '{|}', and
  recursive self-referencing fallbacks.
"""
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

POISON_ENRICHMENT_VALUES: Set[str] = {
    "none",
    "null",
    "undefined",
    "nan",
    "n/a",
    "na",
    "nil",
    "[object object]",
    "-",
    "--",
    "---",
    "unknown",
    "not available",
    "not found",
}

MAX_SPINTAX_DEPTH = 5
MAX_TEMPLATE_CHARS = 10000
MAX_SPINTAX_COMBINATIONS = 100_000_000

import logging
logger = logging.getLogger(__name__)


def clean_enrichment_value(val: Any, field_type: Optional[str] = None) -> str:
    """
    Paranoia Layer 1: Scrubs poison strings ('None', 'null', 'undefined', 'N/A', 'nan')
    and control characters from scraped/imported lead fields.
    If field_type is specified ('first_name' or 'company'), passes value through specialized
    DataHygieneService sanitization routines.
    Returns empty string '' if value is nullish or a poison literal.
    """
    if val is None or isinstance(val, bool):
        return ""
    s = str(val).strip()
    # Strip control characters
    s = re.sub(r"[\x00-\x1f\x7f]", "", s).strip()
    if not s:
        return ""
    if s.lower() in POISON_ENRICHMENT_VALUES:
        return ""

    if field_type:
        from leads.backend.services.data_hygiene import DataHygieneService
        ft = str(field_type).lower().strip()
        if ft in ("first_name", "firstname", "first"):
            s = DataHygieneService.clean_first_name(s)
        elif ft in ("company", "company_name", "account"):
            s = DataHygieneService.clean_company(s)

        if not s or s.lower() in POISON_ENRICHMENT_VALUES:
            return ""

    return s


def validate_template_and_spintax_syntax(text: str, allowed_vars: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    Paranoia Layer 2: Validates a template string for:
    1. Unclosed or mismatched double braces '{{' or '}}' (e.g. '{{first_name' or '{{first_name}').
    2. Disallowed template variable names (supports 'lead.<var>' and '{{var | fallback}}').
    3. Self-referencing fallback loops (e.g. '{{company | {{company}}}}').
    4. Unbalanced single-brace spintax '{opt1|opt2' or empty spintax '{}'.
    5. Combinatorial spintax bombs and excessive nesting depth (ENG-11).
    """
    if not text or not isinstance(text, str):
        return {"valid": True, "errors": [], "variables": []}

    errors: List[str] = []
    extracted_vars: List[str] = []

    # Paranoia Layer 1: Guard against massive inputs causing ReDoS / event-loop stalls
    if len(text) > MAX_TEMPLATE_CHARS:
        errors.append(f"Template text exceeds maximum allowed length of {MAX_TEMPLATE_CHARS} characters (received {len(text)}).")
        return {"valid": False, "errors": errors, "variables": []}

    # 1. Check for nested '{{' inside '{{ ... }}' before masking
    for raw_match in re.finditer(r"\{\{([\s\S]*?)\}\}", text):
        inner = raw_match.group(1)
        if "{{" in inner:
            errors.append(f"Nested or unclosed '{{{{' detected inside template tag: '{raw_match.group(0)}'")
            continue

        parts = [p.strip() for p in inner.split("|", 1)]
        var_part = parts[0].strip().lower()
        fallback_part = parts[1].strip() if len(parts) > 1 else None

        if not var_part:
            errors.append("Empty template variable '{{}}' is not allowed.")
            continue

        # Normalize optional 'lead.' prefix for validation
        canonical_var = var_part[5:] if var_part.startswith("lead.") else var_part
        extracted_vars.append(canonical_var)

        if allowed_vars is not None and canonical_var not in allowed_vars:
            errors.append(
                f"Invalid template variable '{{{{{canonical_var}}}}}' found. "
                f"Allowed: {', '.join(sorted(allowed_vars))}"
            )

        if fallback_part is not None:
            if fallback_part.lower() in POISON_ENRICHMENT_VALUES:
                errors.append(
                    f"Template variable '{{{{{var_part}}}}}' has an unsafe poison fallback '{fallback_part}'."
                )

    # 2. Mask valid '{{...}}' blocks and check for stray '{{' or mismatched '{{var}'
    masked = re.sub(r"\{\{[^{}]*\}\}", "__ELEIN_VAR_MASK__", text)
    if "{{" in masked:
        errors.append(
            "Malformed or unclosed template variable braces ('{{' or '}}'). "
            "Ensure every variable uses matching double curly braces like {{first_name}}."
        )

    # 3. Validate single-brace spintax balance on the masked string
    depth = 0
    max_seen_depth = 0
    for idx, ch in enumerate(masked):
        if ch == "{":
            depth += 1
            if depth > max_seen_depth:
                max_seen_depth = depth
            if depth > MAX_SPINTAX_DEPTH:
                errors.append(f"Spintax nesting depth exceeds maximum allowed ({MAX_SPINTAX_DEPTH}).")
                break
        elif ch == "}":
            depth -= 1
            if depth < 0:
                errors.append("Unmatched closing brace '}' found in template spintax.")
                break

    if depth > 0:
        errors.append("Unclosed opening brace '{' found in template spintax.")

    # Check for empty spintax blocks '{}' or blocks with only pipes '{|}' and count combinatorial variants
    total_combinations = 1
    for spin_match in re.finditer(r"\{([^{}]*)\}", masked):
        spin_inner = spin_match.group(1)
        if not spin_inner.strip():
            errors.append("Empty curly braces '{}' found in template.")
        elif "|" in spin_inner:
            options = [opt.strip() for opt in spin_inner.split("|")]
            if not any(options):
                errors.append(f"Spintax block '{{{spin_inner}}}' has no non-empty options.")
            else:
                non_empty_count = sum(1 for o in options if o)
                if non_empty_count > 1:
                    total_combinations *= non_empty_count
                    if total_combinations > MAX_SPINTAX_COMBINATIONS:
                        errors.append(
                            f"Spintax combinatorial possibilities exceed maximum safety cap of {MAX_SPINTAX_COMBINATIONS} variants."
                        )
                        break

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "variables": extracted_vars,
    }


def resolve_spintax(text: str, seed: Optional[str] = None, timeout_ms: int = 100) -> str:
    """
    Paranoia Layer 0 & 1 (ENG-11): Evaluates single-brace spintax '{Hi|Hello|Hey}' (including nested spintax)
    while leaving double-brace '{{variable}}' placeholders completely untouched.
    Uses a deterministic RNG when `seed` is provided so retries produce consistent phrasing.
    Bounded to MAX_SPINTAX_DEPTH (5) and a hard execution timeout (100ms) to prevent
    ReDoS and worker event loop hangs.
    """
    if not text or not isinstance(text, str) or "{" not in text:
        return text or ""

    if len(text) > MAX_TEMPLATE_CHARS:
        logger.warning(f"Template length ({len(text)}) exceeds safety cap ({MAX_TEMPLATE_CHARS}). Truncating for resolution.")
        text = text[:MAX_TEMPLATE_CHARS]

    rng = random.Random(seed) if seed is not None else random

    import time
    start_time = time.monotonic()

    # Temporarily protect '{{...}}' blocks
    protected_tokens: List[str] = []

    def _protect(m: re.Match) -> str:
        idx = len(protected_tokens)
        protected_tokens.append(m.group(0))
        return f"__ELEIN_PROTECTED_VAR_{idx}__"

    working = re.sub(r"\{\{[^{}]*\}\}", _protect, text)

    # Resolve innermost '{opt1|opt2}' blocks that contain at least one '|'
    pattern = re.compile(r"\{([^{}|]+\|[^{}]*)\}")
    for _ in range(MAX_SPINTAX_DEPTH):
        if (time.monotonic() - start_time) * 1000.0 > timeout_ms:
            logger.warning("Spintax resolution exceeded safety timeout threshold (%d ms). Halting resolution.", timeout_ms)
            break

        if not pattern.search(working):
            break

        def _spin_replace(m: re.Match) -> str:
            raw_opts = m.group(1).split("|")
            non_empty = [o for o in raw_opts if o.strip()]
            choices = non_empty if non_empty else raw_opts
            return rng.choice(choices) if choices else ""

        working = pattern.sub(_spin_replace, working)

    # Restore protected '{{...}}' blocks
    for idx, tok in enumerate(protected_tokens):
        working = working.replace(f"__ELEIN_PROTECTED_VAR_{idx}__", tok)

    return working


def _calculate_spintax_metrics(text: str) -> Tuple[int, int]:
    """
    Paranoia Layer 0 & 1: Evaluates combinatorial variations and maximum nesting depth
    for single-brace spintax while strictly masking {{variable}} tags.
    Returns (total_combinations, max_depth_detected).
    Clamped to MAX_SPINTAX_COMBINATIONS (100,000,000). Returns (1, 0) if no spintax is present.
    """
    if not text or not isinstance(text, str):
        return 1, 0

    # Mask double-brace Liquid/Mustache tags so they are never parsed as spintax
    cleaned = re.sub(r"\{\{[^{}]*\}\}", "", text)
    if "{" not in cleaned:
        return 1, 0

    class _Scope:
        def __init__(self, depth: int):
            self.depth = depth
            self.branches: List[int] = []
            self.current_product: int = 1
            self.has_pipe: bool = False
            self.has_nested_spintax: bool = False

    top = _Scope(0)
    stack = [top]
    max_depth = 0

    for ch in cleaned:
        if ch == "{":
            stack.append(_Scope(len(stack)))
        elif ch == "|":
            if len(stack) > 1:
                cur = stack[-1]
                cur.has_pipe = True
                cur.branches.append(cur.current_product)
                cur.current_product = 1
        elif ch == "}":
            if len(stack) > 1:
                cur = stack.pop()
                cur.branches.append(cur.current_product)
                if cur.has_pipe:
                    choices = sum(cur.branches)
                    is_spintax = True
                    max_depth = max(max_depth, cur.depth)
                else:
                    choices = cur.branches[0] if cur.branches else 1
                    is_spintax = cur.has_nested_spintax
                parent = stack[-1]
                parent.current_product = min(MAX_SPINTAX_COMBINATIONS, parent.current_product * choices)
                if is_spintax:
                    parent.has_nested_spintax = True
                    max_depth = max(max_depth, cur.depth)

    # Safe stack unwind for unclosed braces
    while len(stack) > 1:
        cur = stack.pop()
        cur.branches.append(cur.current_product)
        choices = sum(cur.branches) if cur.has_pipe else (cur.branches[0] if cur.branches else 1)
        parent = stack[-1]
        parent.current_product = min(MAX_SPINTAX_COMBINATIONS, parent.current_product * choices)
        if cur.has_pipe or cur.has_nested_spintax:
            parent.has_nested_spintax = True
            max_depth = max(max_depth, cur.depth)

    if not top.has_nested_spintax:
        return 1, 0

    total_combs = max(1, min(top.current_product, MAX_SPINTAX_COMBINATIONS))
    return total_combs, max_depth


def calculate_spintax_combinations(text: str) -> int:
    """
    Paranoia Layer 0 & 1: Computes the total number of unique combinatorial variations
    generated by single-brace spintax (e.g. {opt1|opt2|{opt3|opt4}}).
    Double-brace {{variable}} and {{var | fallback}} blocks are masked and never counted.
    Clamped to 100,000,000 to prevent overflow. Returns 1 if no spintax is present.
    """
    return _calculate_spintax_metrics(text)[0]


def calculate_spintax_entropy(text: str, campaign_lead_count: int = 1000) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Validates template syntax, computes total combinatorial combinations,
    calculates diversity ratio against campaign lead volume, assigns ESP spam resistance rating,
    and produces actionable optimization recommendations.
    Ratings:
      - CRITICAL_SPAM_RISK: total_combinations < 5 or diversity_ratio < 0.05
      - MODERATE_VARIATION: 5 <= total_combinations < 50
      - HIGH_DIVERSITY: 50 <= total_combinations < 200
      - ENTERPRISE_IMMUNITY: total_combinations >= 200
    """
    val_res = validate_template_and_spintax_syntax(text)
    if not val_res.get("valid"):
        return {
            "valid": False,
            "errors": val_res.get("errors", []),
            "entropy_rating": "INVALID",
            "total_combinations": 0,
            "diversity_ratio": 0.0,
            "recommendations": ["Fix template syntax errors before evaluating spintax entropy."],
            "max_depth_detected": 0,
        }

    try:
        lead_count = int(campaign_lead_count) if campaign_lead_count is not None else 1000
    except (ValueError, TypeError):
        lead_count = 1000
    lead_count = max(1, lead_count)

    total_combinations, max_depth = _calculate_spintax_metrics(text)
    diversity_ratio = round(total_combinations / lead_count, 3)

    if total_combinations < 5 or diversity_ratio < 0.05:
        entropy_rating = "CRITICAL_SPAM_RISK"
    elif total_combinations < 50:
        entropy_rating = "MODERATE_VARIATION"
    elif total_combinations < 200:
        entropy_rating = "HIGH_DIVERSITY"
    else:
        entropy_rating = "ENTERPRISE_IMMUNITY"

    recommendations: List[str] = []
    clean_text = text or ""

    if not re.search(r"\{[^{}]*(?:hi|hello|hey|good morning|greetings)[^{}]*\|[^{}]*\}", clean_text, re.IGNORECASE):
        recommendations.append("Add spintax to greeting `{Hi|Hello|Hey}`")

    if not re.search(r"\{[^{}]*(?:saw|noticed|came across|loved|impressed|updates|momentum)[^{}]*\|[^{}]*\}", clean_text, re.IGNORECASE):
        recommendations.append("Add variations to your opening hook (e.g. `{I saw|I noticed|came across}`)")

    if not re.search(r"\{[^{}]*(?:reach out|reaching out|connect|relevant|helpful|interesting)[^{}]*\|[^{}]*\}", clean_text, re.IGNORECASE):
        recommendations.append("Add variations to value connectors (e.g. `{wanted to connect|reaching out because}`)")

    if not re.search(r"\{[^{}]*(?:quick chat|10-minute|15-minute|open to|week work|call)[^{}]*\|[^{}]*\}", clean_text, re.IGNORECASE):
        recommendations.append("Add variations to your call-to-action (e.g. `{Are you free for a quick chat|Open to a brief call}`)")

    if not re.search(r"\{[^{}]*(?:best|thanks|cheers|regards)[^{}]*\|[^{}]*\}", clean_text, re.IGNORECASE):
        recommendations.append("Add spintax to your sign-off (e.g. `{Best,|Thanks,|Cheers,}`)")

    if entropy_rating == "CRITICAL_SPAM_RISK":
        recommendations.append(
            "Critical spam risk: ESPs (Google Workspace & Microsoft 365) detect identical content hash clusters. Add spintax to achieve at least 50+ variations."
        )
    elif diversity_ratio < 0.05 and total_combinations >= 5:
        recommendations.append(
            f"Campaign lead volume ({lead_count}) exceeds safe copy variation (diversity ratio {diversity_ratio}). Add more spintax so each lead receives unique copy."
        )
    elif entropy_rating == "ENTERPRISE_IMMUNITY":
        recommendations.append(
            "Enterprise immunity reached: superior content diversification guarantees unique content hashes across your campaign."
        )

    return {
        "valid": True,
        "total_combinations": total_combinations,
        "entropy_rating": entropy_rating,
        "diversity_ratio": diversity_ratio,
        "recommendations": recommendations,
        "max_depth_detected": max_depth,
    }


def generate_linguistic_spintax(plain_text: str, intensity: str = "balanced") -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Injects high-converting B2B cold outreach spintax variations into plain text
    while strictly protecting existing {{variable}} and {spintax|block} placeholders.
    Evaluates final entropy rating and returns enriched template.
    """
    if not plain_text or not isinstance(plain_text, str):
        plain_str = plain_text or ""
        entropy_res = calculate_spintax_entropy(plain_str)
        return {
            "original_text": plain_str,
            "spintax_text": plain_str,
            "entropy": entropy_res,
            "replacements_count": 0,
        }

    # Step 1: Protect existing {{...}} variable tags
    var_tokens: List[str] = []
    def _mask_var(m: re.Match) -> str:
        idx = len(var_tokens)
        var_tokens.append(m.group(0))
        return f"__ELEIN_VAR_MASK_{idx}__"

    working_text = re.sub(r"\{\{[^{}]*\}\}", _mask_var, plain_text)

    # Step 2: Protect existing single-brace spintax blocks (balanced braces)
    spintax_tokens: List[str] = []
    depth = 0
    start = -1
    result_chars: List[str] = []
    i = 0
    while i < len(working_text):
        ch = working_text[i]
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    block = working_text[start:i + 1]
                    if "|" in block:
                        idx = len(spintax_tokens)
                        spintax_tokens.append(block)
                        result_chars.append(f"__ELEIN_SPINTAX_MASK_{idx}__")
                    else:
                        result_chars.append(block)
                    start = -1
                    i += 1
                    continue
        if depth == 0:
            result_chars.append(ch)
        i += 1

    if depth > 0 and start != -1:
        result_chars.append(working_text[start:])

    working_text = "".join(result_chars)

    # Step 3: Define linguistic B2B cold outreach synonym patterns
    # Ordered from longer/more specific phrases to shorter words to prevent prefix collisions
    base_patterns: List[Tuple[re.Pattern, str]] = [
        # Call-to-Actions (CTAs)
        (
            re.compile(r"\b(?:[Aa]re you free for a (?:quick|brief|10-minute|15-minute)?\s*(?:call|chat))\b", re.IGNORECASE),
            "{Are you free for a quick chat|Open to a brief 10-minute call|Would you be open to connecting for a quick chat}",
        ),
        (
            re.compile(r"\b(?:let me know if you (?:are|'re) open to)\b", re.IGNORECASE),
            "{let me know if you're open to|worth a quick chat about|open to exploring}",
        ),
        (
            re.compile(r"\b(?:does next week work|would you have 10 mins this week)\b", re.IGNORECASE),
            "{does next week work|would you have 10 mins this week|open to connecting sometime next week}",
        ),

        # Value Connectors
        (
            re.compile(r"\b(?:wanted to reach out|reaching out because|wanted to connect)\b", re.IGNORECASE),
            "{wanted to reach out|reaching out because|wanted to connect}",
        ),
        (
            re.compile(r"\b(?:thought it might be relevant|thought this could be helpful|thought you might find this interesting)\b", re.IGNORECASE),
            "{thought it might be relevant|thought this could be helpful|thought you might find this interesting}",
        ),

        # Openers & Observational Hooks
        (
            re.compile(r"\b(?:recent updates|recent momentum|recent progress|recent announcements)\b", re.IGNORECASE),
            "{recent updates|recent momentum|recent progress}",
        ),
        (
            re.compile(r"\b(?:I\s+)?(?:saw|noticed|came across)\b", re.IGNORECASE),
            "{I saw|I noticed|came across}",
        ),
        (
            re.compile(r"\b(?:loved|impressed by|enjoyed)\b", re.IGNORECASE),
            "{loved|was impressed by|really enjoyed}",
        ),

        # Greetings
        (
            re.compile(r"\b(?:good morning)\b", re.IGNORECASE),
            "{Good morning|Hope your week is off to a great start|Good morning}",
        ),
        (
            re.compile(r"\b(?:[Hh]i|[Hh]ello|[Hh]ey)\b"),
            "{Hi|Hello|Hey}",
        ),

        # Sign-offs
        (
            re.compile(r"\b(?:Best|Thanks|Cheers|Regards),", re.IGNORECASE),
            "{Best,|Thanks,|Cheers,}",
        ),
        (
            re.compile(r"\b(?:Best|Thanks|Cheers|Regards)\b", re.IGNORECASE),
            "{Best|Thanks|Cheers}",
        ),
    ]

    aggressive_patterns: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"\bquick\b", re.IGNORECASE), "{quick|brief|short}"),
        (re.compile(r"\bdiscuss\b", re.IGNORECASE), "{discuss|explore|chat about}"),
        (re.compile(r"\bquestions\b", re.IGNORECASE), "{questions|thoughts|feedback}"),
        (re.compile(r"\bhelp\b", re.IGNORECASE), "{help|assist|support}"),
    ]

    active_patterns = list(base_patterns)
    if str(intensity).lower() in ("aggressive", "maximum", "high"):
        active_patterns.extend(aggressive_patterns)

    # Step 4: Apply substitutions with intermediate masking
    injected_tokens: List[str] = []
    def _make_injector(rep_str: str):
        def _sub(m: re.Match) -> str:
            tok_idx = len(injected_tokens)
            injected_tokens.append(rep_str)
            return f"__ELEIN_INJECTED_SPINTAX_{tok_idx}__"
        return _sub

    total_replacements = 0
    for pat, rep in active_patterns:
        injector = _make_injector(rep)
        working_text, n = pat.subn(injector, working_text)
        total_replacements += n

    # Step 5: Restore injected spintax tokens
    for idx, tok in enumerate(injected_tokens):
        working_text = working_text.replace(f"__ELEIN_INJECTED_SPINTAX_{idx}__", tok)

    # Step 6: Restore previously existing spintax blocks
    for idx, tok in enumerate(spintax_tokens):
        working_text = working_text.replace(f"__ELEIN_SPINTAX_MASK_{idx}__", tok)

    # Step 7: Restore protected variable blocks
    for idx, tok in enumerate(var_tokens):
        working_text = working_text.replace(f"__ELEIN_VAR_MASK_{idx}__", tok)

    entropy_dict = calculate_spintax_entropy(working_text)

    return {
        "original_text": plain_text,
        "spintax_text": working_text,
        "entropy": entropy_dict,
        "replacements_count": total_replacements,
    }


def preview_spintax_variants(text: str, count: int = 5, seed: Optional[str] = None) -> List[str]:
    """
    Paranoia Layer 0 & 2: Generates up to `count` (clamped between 1 and 20) distinct rendered text
    variations using `resolve_spintax`.
    If `seed` is provided, generates deterministic sequence of seeds f"{seed}_{i}".
    Deduplicates returned samples while preserving count up to available combinations.
    """
    if not text or not isinstance(text, str):
        return [text or ""]

    try:
        c = int(count) if count is not None else 5
    except (ValueError, TypeError):
        c = 5
    target_count = max(1, min(20, c))

    total_combs = calculate_spintax_combinations(text)
    effective_limit = min(target_count, total_combs)

    variants: List[str] = []
    seen: Set[str] = set()

    max_attempts = max(effective_limit * 15, 60)

    for i in range(max_attempts):
        current_seed = f"{seed}_{i}" if seed is not None else None
        rendered = resolve_spintax(text, seed=current_seed)
        if rendered not in seen:
            seen.add(rendered)
            variants.append(rendered)
            if len(variants) >= effective_limit:
                break

    if not variants:
        variants = [resolve_spintax(text, seed=f"{seed}_0" if seed is not None else None)]

    return variants


def validate_campaign_nodes_templates(nodes: list) -> List[str]:
    """
    Paranoia Layer 2: Validates template variable and spintax syntax across all nodes.
    Returns a list of error strings (empty if all valid).
    """
    errors: List[str] = []
    if not isinstance(nodes, list):
        return errors
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        data = node.get("data") or {}
        texts_to_check: List[str] = []
        for key in ("message", "template", "body", "subject", "text", "note", "content"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                texts_to_check.append(val)
        for t in texts_to_check:
            res = validate_template_and_spintax_syntax(t)
            if not res.get("valid"):
                for err in res.get("errors", []):
                    errors.append(f"Node {node.get('id', idx)}: {err}")
    return errors
