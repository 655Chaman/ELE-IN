"""
Three-Layer Paranoia Framework: Outbound AI Message & Connection Note Output Guard
- Layer 0 (Foundational): Strips conversational preamble, enclosures, and meta-commentary.
- Layer 1 (Environmental): Circuit-breaker for hallucinated bracketed placeholders ([First Name], [Company]),
  unreplaced template tags, and AI refusal phrases, falling back safely to human templates.
- Layer 2 (Human Paranoia): Enforces hard LinkedIn character bounds (300 chars for notes, 2000 for DMs, 1900 for InMail).
"""
import re
from typing import Tuple, Any

PLACEHOLDER_PATTERN = re.compile(
    r'(?i)(\[|\<|\{\{)\s*(first[\s_-]*name|last[\s_-]*name|full[\s_-]*name|name|company|company[\s_-]*name|prospect|lead|title|role|job|industry|insert[\s_-]*\w+|your[\s_-]*name|my[\s_-]*name|link|url|website)\s*(\]|\>|\}\})'
)
TEMPLATE_TAG_PATTERN = re.compile(r'\{\{[a-zA-Z0-9_]+\}\}')

REFUSAL_PATTERN = re.compile(
    r'(?i)(as an ai language model|as an ai assistant|i cannot fulfill|i am unable to|i apologize, but|my programming prevents|violates.*(?:policy|policies))'
)

PREAMBLE_PATTERNS = [
    re.compile(r'(?i)^(?:here (?:is|are)|sure,?(?: here (?:is|are))?|certainly,?(?: here (?:is|are))?|i\'d be happy to|here\'s (?:a|the)|below is (?:a|the)|draft message:|connection note:|message draft:)[^\n]*?(?:\n+|:\s*)'),
    re.compile(r'(?i)^(?:as an ai|as an assistant|as a language model)[^\n]*?(?:\n+|:\s*)'),
]

POSTAMBLE_PATTERNS = [
    re.compile(r'(?i)(?:\n+|^)(?:let me know if you(?:\'d like| want)|hope this helps|feel free to adjust|you can customize)[^\n]*$'),
]

DEFAULT_FALLBACKS = {
    "connection_note": "I'd love to connect and follow your work.",
    "message": "I noticed your impressive background and wanted to reach out.",
    "inmail": "I noticed your impressive background and wanted to reach out.",
    "hook": "I noticed your impressive background on LinkedIn.",
    "icebreaker": "I noticed your impressive background on LinkedIn.",
}

MAX_LIMITS = {
    "connection_note": 300,
    "inmail_subject": 200,
    "inmail_body": 1900,
    "message": 2000,
    "hook": 280,
    "icebreaker": 280,
}


def sanitize_outbound_ai_message(
    text: Any,
    max_chars: int = None,
    fallback: str = "",
    context_type: str = "message"
) -> Tuple[str, bool, str]:
    """
    Sanitizes generated AI outreach text and guards against AI slop, hallucinations, and refusals.
    Returns: (cleaned_text, is_valid, reason)
    """
    limit = max_chars or MAX_LIMITS.get(context_type, 2000)
    raw_str = str(text or "").strip()

    # Empty check
    if not raw_str:
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, "Empty AI response"

    # Strip conversational preamble
    cleaned = raw_str
    for p in PREAMBLE_PATTERNS:
        cleaned = p.sub("", cleaned).strip()

    # Strip postamble commentary
    for p in POSTAMBLE_PATTERNS:
        cleaned = p.sub("", cleaned).strip()

    # Strip outer enclosing quotes
    while (cleaned.startswith('"') and cleaned.endswith('"')) or \
          (cleaned.startswith("'") and cleaned.endswith("'")) or \
          (cleaned.startswith("`") and cleaned.endswith("`")):
        if len(cleaned) <= 2:
            break
        cleaned = cleaned[1:-1].strip()

    # Layer 1: Refusal check
    if REFUSAL_PATTERN.search(cleaned):
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, "AI refusal detected"

    # Layer 1: Hallucinated placeholder check
    ph_match = PLACEHOLDER_PATTERN.search(cleaned)
    if ph_match:
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, f"Hallucinated placeholder detected: {ph_match.group(0)}"

    tt_match = TEMPLATE_TAG_PATTERN.search(cleaned)
    if tt_match:
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, f"Unresolved template tag detected: {tt_match.group(0)}"

    # Layer 2: Character limit clamp
    final_text = _clamp_text(cleaned, limit)
    return final_text, True, "OK"


def _clamp_text(text: str, limit: int) -> str:
    s = str(text).strip()
    if len(s) <= limit:
        return s
    return s[:limit - 3].rstrip() + "..."
