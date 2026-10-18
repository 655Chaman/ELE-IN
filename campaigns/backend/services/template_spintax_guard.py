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
from typing import Any, Dict, List, Optional, Set

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
MAX_SPINTAX_COMBINATIONS = 10000

import logging
logger = logging.getLogger(__name__)


def clean_enrichment_value(val: Any) -> str:
    """
    Paranoia Layer 1: Scrubs poison strings ('None', 'null', 'undefined', 'N/A', 'nan')
    and control characters from scraped/imported lead fields.
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

    # 2. Mask valid '{{...}}' blocks and check for stray '{{', '}}', or mismatched '{var}}' / '{{var}'
    masked = re.sub(r"\{\{[^{}]*\}\}", "__ELEIN_VAR_MASK__", text)
    if "{{" in masked or "}}" in masked:
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


def resolve_spintax(text: str, seed: Optional[str] = None) -> str:
    """
    Paranoia Layer 0 & 1: Evaluates single-brace spintax '{Hi|Hello|Hey}' (including nested spintax)
    while leaving double-brace '{{variable}}' placeholders completely untouched.
    Uses a deterministic RNG when `seed` is provided so retries produce consistent phrasing.
    Bounded to MAX_SPINTAX_DEPTH and MAX_TEMPLATE_CHARS to prevent ReDoS / event loop hangs.
    """
    if not text or not isinstance(text, str) or "{" not in text:
        return text or ""

    if len(text) > MAX_TEMPLATE_CHARS:
        logger.warning(f"Template length ({len(text)}) exceeds safety cap ({MAX_TEMPLATE_CHARS}). Truncating for resolution.")
        text = text[:MAX_TEMPLATE_CHARS]

    rng = random.Random(seed) if seed is not None else random

    # Temporarily protect '{{...}}' blocks
    protected_tokens: List[str] = []

    def _protect(m: re.Match) -> str:
        idx = len(protected_tokens)
        protected_tokens.append(m.group(0))
        return f"__ELEIN_PROTECTED_VAR_{idx}__"

    working = re.sub(r"\{\{[^{}]*\}\}", _protect, text)

    # Resolve innermost '{opt1|opt2}' blocks that contain at least one '|'
    pattern = re.compile(r"\{([^{}|]+\|[^{}]*)\}")
    for _ in range(MAX_SPINTAX_DEPTH + 2):
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
