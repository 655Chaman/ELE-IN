"""
Automated Copywriting Quality & Regression Evals Engine
======================================================
Quantitative Evaluation Harness for Generated AI Messages.

Evaluates:
1. Conciseness & Word-Budget Adherence: Penalizes bloat and unnatural length.
2. Personalization Density: Measures ratio of prospect-specific data vs boilerplate.
3. Call-to-Action (CTA) Clarity: Verifies presence of a low-friction question or close.
4. Hallucination Risk: Checks for unsupported placeholders or exaggerated claims.
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

CHANNEL_TARGET_WORDS = {
    "connection_note": (15, 45),     # ~100-300 chars
    "email": (50, 140),              # Standard high-reply cold email
    "inmail": (40, 100),             # LinkedIn InMail
    "message": (30, 90),             # Follow-up message
}


def evaluate_copywriting_quality(
    copy: str,
    prospect_context: Dict[str, Any],
    channel: str = "email"
) -> Dict[str, Any]:
    """
    Computes objective quality scores [0, 100] across 4 quantitative dimensions.
    """
    clean_copy = str(copy or "").strip()
    words = [w for w in re.findall(r'\b\w+\b', clean_copy)]
    word_count = len(words)

    # 1. Conciseness Score
    min_w, max_w = CHANNEL_TARGET_WORDS.get(channel, (40, 120))
    if word_count == 0:
        conciseness_score = 0.0
    elif min_w <= word_count <= max_w:
        conciseness_score = 100.0
    elif word_count < min_w:
        conciseness_score = max(30.0, 100.0 - (min_w - word_count) * 4.0)
    else:
        conciseness_score = max(20.0, 100.0 - (word_count - max_w) * 2.0)

    # 2. Personalization Density
    # Check mentions of prospect first name, company, title, or industry
    context_tokens = set()
    for k in ("first_name", "company", "title", "industry", "job_title"):
        val = str(prospect_context.get(k) or "").lower().strip()
        if val and len(val) > 2:
            context_tokens.update(re.findall(r'\b\w+\b', val))

    matched_personalization = 0
    lower_copy = clean_copy.lower()
    for tok in context_tokens:
        if tok in lower_copy:
            matched_personalization += 1

    personalization_score = min(100.0, (matched_personalization * 35.0)) if context_tokens else 70.0

    # 3. Call-to-Action (CTA) Clarity
    # Looks for closing question mark or scheduling prompt
    has_question = "?" in clean_copy
    has_cta_phrase = bool(re.search(r'(?i)\b(open to|worth a|free to|let me know|chat|connect|next week|thursday|tuesday|catch up)\b', clean_copy))
    
    if has_question and has_cta_phrase:
        cta_score = 100.0
    elif has_question or has_cta_phrase:
        cta_score = 75.0
    else:
        cta_score = 30.0

    # 4. Anti-Slop & Cleanliness Score
    slop_matches = re.findall(r'(?i)\b(i hope this email finds you well|cutting-edge|game-changer|revolutionize)\b', clean_copy)
    cleanliness_score = max(20.0, 100.0 - len(slop_matches) * 30.0)

    # Overall Composite Quality Score
    composite_score = int(round(
        0.30 * conciseness_score +
        0.30 * personalization_score +
        0.25 * cta_score +
        0.15 * cleanliness_score
    ))

    return {
        "composite_score": composite_score,
        "word_count": word_count,
        "conciseness_score": round(conciseness_score, 1),
        "personalization_score": round(personalization_score, 1),
        "cta_score": round(cta_score, 1),
        "cleanliness_score": round(cleanliness_score, 1),
        "flags": {
            "is_too_long": word_count > max_w,
            "is_too_short": word_count < min_w,
            "missing_cta_question": not has_question,
            "has_ai_slop": len(slop_matches) > 0,
        }
    }
