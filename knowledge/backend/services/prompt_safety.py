"""
Prompt Safety Module — Paranoia Layer 2 Defense
================================================
Every piece of user-controlled text that is concatenated into an LLM prompt
MUST pass through `sanitize_for_prompt()` before use.

What this defends against:
- Prompt injection: malicious LinkedIn profiles containing "Ignore all previous instructions..."
- Jailbreak attempts via user-uploaded documents or lead data
- Data exfiltration via crafted instructions inside knowledge base content
"""

import re
import logging
from typing import Any, List, Union, Optional

logger = logging.getLogger(__name__)

# Patterns that indicate prompt injection attempts
# These are checked case-insensitively
INJECTION_PATTERNS = [
    r'(?i)(ignore|forget|disregard|override|bypass|cancel|stop\s+following)\s+(all\s+|any\s+)?(previous|above|prior|your|the|system)\s+(instructions?|prompts?|rules?|constraints?|guidelines?|directives?|commands?)',
    r'(?i)(you are now|act as|pretend to be|roleplay as|your new (role|persona|identity)|switch to|enter\s+(developer|jailbreak|god|dan)\s+mode)',
    r'(?i)(system\s*:\s*|\[system\]|<\/?system>|\[INST\]|<\/?INST>|\[\/INST\]|<s>|<\/s>|<\|.*?\|>|###\s*(instruction|system|human|assistant|user))',
    r'(?i)(reveal|expose|print|show|output|display|repeat|leak)\s+(your|the)?\s*(entire\s+)?(system\s*)?(prompt|instructions?|context|guidelines?)',
    r'(?i)(\\n|\\r|\n|\r)\s*(system|user|assistant|human|prospect)\s*:',
]

def sanitize_for_prompt(text: Any, source_label: str = "user_content") -> str:
    """
    Sanitize user-controlled text before injecting it into an LLM prompt.

    :param text: The raw user-controlled string, list of strings, or list of chunk dicts
    :param source_label: A label for logging (e.g. 'lead_about_section', 'uploaded_pdf')
    :returns: Safely delimited string for insertion into a prompt.

    Three-Layer Paranoia Framework:
    - Layer 0: Polymorphic extraction (handles str, list of strings, or list of dicts/chunks)
    - Layer 1: Context boundary enforcement & token budgeting
    - Layer 2: Assumes ALL user text is potentially adversarial (neutralizes injection patterns)
    """
    if text is None:
        return ""

    if isinstance(text, list):
        extracted_items = []
        for item in text:
            if isinstance(item, dict):
                content = item.get("content") or item.get("text") or str(item)
                if content:
                    extracted_items.append(content)
            elif isinstance(item, str):
                if item.strip():
                    extracted_items.append(item.strip())
            elif item is not None:
                extracted_items.append(str(item))
        text = "\n\n".join(extracted_items)
    elif not isinstance(text, str):
        text = str(text)

    if not text.strip():
        return ""

    # Defang internal boundary escape tokens to prevent delimiter breakout (Issue 6 resolution)
    text = re.sub(r'(?i)\[\/?USER_CONTENT_(?:START|END)\]', '[ESCAPED_DELIMITER]', text)

    # Check for injection patterns
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            logger.warning(
                f"[PromptSafety] INJECTION ATTEMPT DETECTED in '{source_label}'. "
                f"Pattern matched: '{pattern[:60]}'. "
                f"Text preview: '{text[:200]}'"
            )
            # Neutralize by replacing the matched portion with [REDACTED]
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)

    # Truncate extremely long inputs to prevent context stuffing
    MAX_USER_CONTENT_CHARS = 4000  # ~1000 tokens
    if len(text) > MAX_USER_CONTENT_CHARS:
        logger.warning(
            f"[PromptSafety] User content from '{source_label}' truncated from "
            f"{len(text)} to {MAX_USER_CONTENT_CHARS} chars."
        )
        text = text[:MAX_USER_CONTENT_CHARS] + "\n[Content truncated for safety]"

    # Wrap in delimiters so the LLM knows this is untrusted content
    return f"[USER_CONTENT_START]\n{text}\n[USER_CONTENT_END]"

def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncates a single string to fit approximately within max_tokens.
    Heuristic: 1 word ≈ 1.35 tokens.
    """
    if not isinstance(text, str):
        text = str(text) if text else ""
    if not text:
        return ""
    words = text.split()
    if len(words) * 1.35 <= max_tokens:
        return text
    limit = max(1, int(max_tokens / 1.35))
    return " ".join(words[:limit]) + " [Truncated]"

def truncate_to_context_limit(
    messages: list,
    max_tokens: int = 2000,
    chars_per_token: int = 4,
) -> list:
    """
    Truncate a messages list so the total estimated token count stays under max_tokens.
    
    Layer 1 Paranoia: Prevents API rejection (HTTP 400) from context-length overflow
    when unbounded knowledge chunks, lead history, or long documents are injected.

    Strategy:
    - System message is ALWAYS preserved (never truncated)
    - Oldest non-system messages are removed first
    - If a single message exceeds the limit, its content is truncated with a suffix

    :param messages: List of {role, content} dicts
    :param max_tokens: Hard token ceiling
    :param chars_per_token: Heuristic — 1 token ≈ 4 chars for English text
    :returns: Truncated messages list that fits within the limit
    """
    max_chars = max_tokens * chars_per_token

    def estimate_chars(msgs: list) -> int:
        return sum(len(m.get("content", "")) for m in msgs)

    # Layer 1 & 2 Paranoia (Issue 7 resolution): Clone messages so callers' dicts are never mutated in-place
    cloned_messages = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages]

    if estimate_chars(cloned_messages) <= max_chars:
        return cloned_messages  # Fast path — returns fresh clones

    # Separate system message(s) from the rest
    system_msgs = [m for m in cloned_messages if m.get("role") == "system"]
    other_msgs = [m for m in cloned_messages if m.get("role") != "system"]

    system_chars = estimate_chars(system_msgs)
    budget = max_chars - system_chars

    if budget <= 0:
        # System prompt alone exceeds budget — truncate the last system message
        logger.error(
            f"[ContextWindow] CRITICAL: System prompt alone exceeds {max_tokens} token limit. "
            f"System prompt length: {system_chars} chars. Truncating system message."
        )
        if system_msgs:
            system_msgs[-1]["content"] = system_msgs[-1]["content"][:max_chars] + "\n[TRUNCATED]"
        return system_msgs

    # Remove oldest non-system messages until we fit or until only 1 remains to be truncated
    while len(other_msgs) > 1 and estimate_chars(other_msgs) > budget:
        removed = other_msgs.pop(0)  # Remove oldest first
        logger.warning(
            f"[ContextWindow] Removed oldest message to fit context limit. "
            f"Role: {removed.get('role')}, Content preview: '{removed.get('content', '')[:80]}'"
        )

    # If a single remaining message is still too large, truncate its content
    for msg in other_msgs:
        if len(msg.get("content", "")) > budget:
            original_len = len(msg["content"])
            msg["content"] = msg["content"][:budget] + "\n[Content truncated to fit context limit]"
            logger.warning(
                f"[ContextWindow] Single message content truncated from {original_len} to {budget} chars."
            )

    return system_msgs + other_msgs
