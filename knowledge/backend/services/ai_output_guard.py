"""
Three-Layer Paranoia Framework: Outbound AI Message & Connection Note Output Guard
- Layer 0 (Foundational): Strips conversational preamble, enclosures, zero-width characters,
  formula injection prefixes, and meta-commentary while safely preserving valid markdown links.
- Layer 1 (Environmental): Comprehensive circuit-breaker for hallucinated bracketed placeholders
  ([First Name], [Company], [Booking Link], [Metric]), unreplaced template tags ({{first_name}}),
  and AI refusal phrases, falling back safely to human templates or pro-rata failure reporting.
- Layer 2 (Human Paranoia): Enforces hard channel character bounds with word-boundary aware clamping
  (300 chars for LinkedIn notes, 2000 for DMs, 1900 for InMail, 100 for email subjects),
  formula injection neutralization, and AI slop detection.
"""
import re
from typing import Tuple, Any, Optional, List

# Pre-compiled placeholder and template patterns
PLACEHOLDER_PATTERN = re.compile(
    r'(?i)(\[|\<|\{\{)\s*(?:(?:first|last|full)[\s_-]*name|name|company(?:[\s_-]*name)?|(?:target|prospect|lead|recipient|sender|customer|account|client)[\s_-]*(?:company|name|title|role|first[\s_-]*name|last[\s_-]*name)?|title|job[\s_-]*title|role|industry|niche|sector|insert[\s_-]*\w+|add[\s_-]*\w+|replace[\s_-]*\w+|your[\s_-]*\w+|my[\s_-]*\w+|link|url|website|metric|roi|pain[\s_-]*point|value[\s_-]*prop|goal|statistic|result|competitor|solution|product|booking[\s_-]*link|calendar[\s_-]*link|cta|call[\s_-]*to[\s_-]*action)\s*(\]|\>|\}\})'
)
TEMPLATE_TAG_PATTERN = re.compile(r'\{\{[a-zA-Z0-9_]+\}\}')

REFUSAL_PATTERN = re.compile(
    r'(?i)(as an ai language model|as an ai assistant|as a language model|as a helpful assistant|i cannot fulfill|i cannot generate|i am unable to|i apologize, but|my programming prevents|my guidelines restrict|violates.*(?:policy|policies))'
)

PREAMBLE_PATTERNS = [
    re.compile(r'(?i)^(?:here (?:is|are)|sure,?(?: here (?:is|are))?|certainly,?(?: here (?:is|are))?|i\'d be happy to|here\'s (?:a|the)|below is (?:a|the)|draft message:|connection note:|message draft:)[^\n]*?(?:\n+|:\s*)'),
    re.compile(r'(?i)^(?:as an ai|as an assistant|as a language model)[^\n]*?(?:\n+|:\s*)'),
    re.compile(r'(?i)^(?:subject:\s*|re:\s*)[^\n]*\n+'),
]

POSTAMBLE_PATTERNS = [
    re.compile(r'(?i)(?:\n+|^)(?:let me know if you(?:\'d like| want)|hope this helps|feel free to adjust|you can customize)[^\n]*$'),
]

AI_SLOP_PATTERNS = [
    re.compile(r'(?i)\b(?:i hope this (?:email|message) finds you well|i am reaching out (?:today|because)|allow me to introduce myself|in today\'s fast-paced (?:world|business|environment|market)|cutting-edge (?:solution|platform|tool)|game-changing (?:platform|solution|technology)|revolutionize your (?:workflow|sales|outbound)|it goes without saying|needless to say)\b'),
]

# Layer 2 Paranoia: Data Loss Prevention & PII Detection
PII_SSN_PATTERN = re.compile(r'\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b')
PII_CARD_PATTERN = re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b')

MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

ZERO_WIDTH_CHARS = re.compile(r'[\u200b\u200c\u200d\ufeff\u202a-\u202e]')

DEFAULT_FALLBACKS = {
    "connection_note": "I'd love to connect and follow your work.",
    "message": "I noticed your impressive background and wanted to reach out.",
    "inmail": "I noticed your impressive background and wanted to reach out.",
    "inmail_subject": "Quick question",
    "hook": "I noticed your impressive background on LinkedIn.",
    "icebreaker": "I noticed your impressive background on LinkedIn.",
    "email_subject": "Quick question",
    "email_body": "I noticed your team's recent momentum and wanted to reach out.",
}

MAX_LIMITS = {
    "connection_note": 300,
    "inmail_subject": 200,
    "inmail_body": 1900,
    "message": 2000,
    "hook": 280,
    "icebreaker": 280,
    "email_subject": 100,
    "email_body": 3000,
}


def sanitize_outbound_ai_message(
    text: Any,
    max_chars: int = None,
    fallback: str = "",
    context_type: str = "message",
    banned_phrases: Optional[str] = None,
    strict_slop_mode: bool = False
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

    # Strip zero-width & bidirectional override characters
    cleaned = ZERO_WIDTH_CHARS.sub("", raw_str).strip()

    # Strip conversational preamble
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

    # Layer 2: Strip CSV / Formula Injection Prefixes, while preserving valid markdown bullet lists ("- ")
    while cleaned and (cleaned[0] in ("=", "+", "@", "\t", "\r") or (cleaned.startswith("-") and not cleaned.startswith("- "))):
        cleaned = cleaned[1:].strip()

    # Layer 1: Refusal check
    if REFUSAL_PATTERN.search(cleaned):
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, "AI refusal detected"

    # Layer 1 Paranoia (Issue 8 resolution): Verify that markdown links themselves do not conceal
    # unpopulated placeholders or unresolved template tags (e.g. [Click Here]({{booking_link}}))
    for m in MARKDOWN_LINK_PATTERN.finditer(cleaned):
        link_anchor = m.group(1)
        link_url = m.group(2)
        if PLACEHOLDER_PATTERN.search(link_anchor) or PLACEHOLDER_PATTERN.search(link_url):
            fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
            clean_fb = _clamp_text(fb, limit)
            return clean_fb, False, f"Hallucinated placeholder detected: {m.group(0)}"
        if TEMPLATE_TAG_PATTERN.search(link_anchor) or TEMPLATE_TAG_PATTERN.search(link_url):
            fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
            clean_fb = _clamp_text(fb, limit)
            return clean_fb, False, f"Unresolved template tag detected: {m.group(0)}"

    # Protect valid markdown links before checking for placeholders
    saved_markdown_links: List[str] = []
    def _mask_link(m):
        idx = len(saved_markdown_links)
        saved_markdown_links.append(m.group(0))
        return f"__MD_LINK_TOKEN_{idx}__"

    text_to_scan = MARKDOWN_LINK_PATTERN.sub(_mask_link, cleaned)

    # Layer 1: Hallucinated placeholder check
    ph_match = PLACEHOLDER_PATTERN.search(text_to_scan)
    if ph_match:
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, f"Hallucinated placeholder detected: {ph_match.group(0)}"

    tt_match = TEMPLATE_TAG_PATTERN.search(text_to_scan)
    if tt_match:
        fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
        clean_fb = _clamp_text(fb, limit)
        return clean_fb, False, f"Unresolved template tag detected: {tt_match.group(0)}"

    # Restore masked markdown links into cleaned text
    cleaned = text_to_scan
    for idx, link_str in enumerate(saved_markdown_links):
        cleaned = cleaned.replace(f"__MD_LINK_TOKEN_{idx}__", link_str)

    # Layer 1 & 2: Banned phrases scrubbing
    if banned_phrases and isinstance(banned_phrases, str):
        for bp in [p.strip() for p in banned_phrases.split(",") if p.strip()]:
            cleaned = re.sub(rf'(?i)\b{re.escape(bp)}\b', '', cleaned)
        cleaned = re.sub(r' {2,}', ' ', cleaned).strip()

    # Layer 1: AI Slop removal or detection
    for slop_pattern in AI_SLOP_PATTERNS:
        if slop_pattern.search(cleaned):
            if strict_slop_mode:
                fb = str(fallback or "").strip() or DEFAULT_FALLBACKS.get(context_type, "I would love to connect.")
                clean_fb = _clamp_text(fb, limit)
                return clean_fb, False, "AI slop phrase detected"
            cleaned = slop_pattern.sub("", cleaned)
            cleaned = re.sub(r' {2,}', ' ', cleaned).strip()

    # Layer 2 Paranoia: Data Loss Prevention & PII Scrubbing
    cleaned = PII_SSN_PATTERN.sub("[REDACTED_SSN]", cleaned)
    cleaned = PII_CARD_PATTERN.sub("[REDACTED_CARD]", cleaned)

    # Layer 2: Character limit clamp with word-boundary awareness
    final_text = _clamp_text(cleaned, limit)
    return final_text, True, "OK"


def _clamp_text(text: str, limit: int) -> str:
    s = str(text).strip()
    if len(s) <= limit:
        return s
    target = limit - 3
    if target <= 0:
        return s[:limit]
    truncated = s[:target]
    last_space = truncated.rfind(" ")
    if last_space > int(target * 0.75):
        return truncated[:last_space].rstrip() + "..."
    return truncated.rstrip() + "..."
