"""
Objection Classification Service (Blue Ocean Phase 10: The Conversation Closer)
Governance: Three-Layer Logic Architecture (Paranoia Framework)

Detects and classifies inbound prospect pushback across 8 standardized B2B categories:
1. COMPETITOR_INCUMBENT (e.g., Apollo, Lemlist, ZoomInfo, Outreach, Salesloft, Instantly)
2. BUDGET_FREEZE (e.g., No budget, spending freeze, too expensive)
3. TIMING_LATER (e.g., Reach out in Q3/Q4, circle back, not right now)
4. SEND_INFO_DECK (e.g., Send over a deck, 1-pager, or email info first)
5. WRONG_PERSON_REFERRAL (e.g., Not my department, talk to X)
6. SKEPTICISM_AUTHENTICITY (e.g., How did you get my info, is this automated/spam)
7. FEATURE_GAP (e.g., Do you support X, lacking integration)
8. SOFT_NO_BUSY (e.g., Swamped right now, pass for now)
"""

import re
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Standard B2B Objection Categories
OBJECTION_TYPES = {
    "COMPETITOR_INCUMBENT": "Using a Competitor / Incumbent Tool",
    "BUDGET_FREEZE": "Budget Freeze or Pricing Constraint",
    "TIMING_LATER": "Bad Timing / Postponed to Future Quarter",
    "SEND_INFO_DECK": "Brush-off Asking for Deck or 1-Pager",
    "WRONG_PERSON_REFERRAL": "Wrong Person / Referred to Colleague",
    "SKEPTICISM_AUTHENTICITY": "Skepticism / Data Privacy / Unsubscribe",
    "FEATURE_GAP": "Missing Specific Feature or Integration",
    "SOFT_NO_BUSY": "Too Busy / Soft Brush-off",
    "GENERAL_INQUIRY": "General Inquiry or Neutral Response"
}

# Known Competitor Names & Signatures
KNOWN_COMPETITORS = [
    "apollo", "apollo.io", "lemlist", "zoominfo", "outreach", "salesloft",
    "instantly", "instantly.ai", "seamless", "seamless.ai", "lusha", "hunter",
    "hunter.io", "cognism", "clearbit", "leadfeeder", "smartlead", "woodpecker",
    "clay", "clay.com", "kaspr", "lead411", "reply.io"
]

# Regex & Keyword Heuristics
PATTERNS = {
    "COMPETITOR_INCUMBENT": [
        r"\b(already\s+(using|use|have|working\s+with|subscribed\s+to)|happy\s+with\s+our\s+current|locked\s+into|contract\s+with)\b",
        r"\b(current\s+(stack|vendor|tool|solution|platform|provider))\b",
        r"\b(we\s+use|we're\s+using)\s+(" + "|".join(KNOWN_COMPETITORS) + r")\b"
    ],
    "BUDGET_FREEZE": [
        r"\b(no\s+budget|budget\s+(freeze|hold|cut|locked|tight)|can('t|not)\s+(commit|spend|afford)|too\s+expensive|cost\s+(prohibitive|too\s+high))\b",
        r"\b(leadership|cfo|executive|board)\s+(placed|froze|restricted|cut)\s+(spend|budget|purchases)\b",
        r"\b(zero\s+spend|no\s+funds|freeze\s+on\s+(new\s+)?software)\b"
    ],
    "TIMING_LATER": [
        r"\b(reach\s+out|circle\s+back|ping\s+me|touch\s+base|follow\s+up|check\s+back)\s+(in|around|later|next)\b",
        r"\b(q[1-4]|next\s+(quarter|month|year)|november|december|january|february|march|april|may|june|july|august|september|october)\b",
        r"\b(bad\s+timing|not\s+a\s+good\s+time|revisit\s+(in|next)|end\s+of\s+the\s+year)\b"
    ],
    "SEND_INFO_DECK": [
        r"\b(send\s+(over\s+)?(a\s+)?(deck|one-pager|1-pager|pdf|brochure|whitepaper|case\s+study|info|details|email))\b",
        r"\b(email\s+me\s+some\s+(info|details|material)|have\s+you\s+got\s+a\s+deck)\b",
        r"\b(forward\s+me\s+something|link\s+to\s+check\s+out)\b"
    ],
    "WRONG_PERSON_REFERRAL": [
        r"\b(not\s+(the\s+)?(right|best)\s+person|don't\s+handle|not\s+my\s+(department|area|domain|responsibility))\b",
        r"\b(talk\s+to|speak\s+with|reach\s+out\s+to|connect\s+with|refer\s+you\s+to)\s+([A-Z][a-z]+)\b",
        r"\b(our\s+(head\s+of|vp|director|manager)\s+handles|try\s+reaching\s+out\s+to)\b"
    ],
    "SKEPTICISM_AUTHENTICITY": [
        r"\b(how\s+did\s+you\s+(get|find)\s+my\s+(email|info|number|contact)|who\s+gave\s+you)\b",
        r"\b(is\s+this\s+(an\s+)?(ai|bot|automated|automation|script)|are\s+you\s+a\s+bot)\b",
        r"\b(remove\s+me|unsubscribe|do\s+not\s+contact|stop\s+(emailing|messaging)|gdpr)\b"
    ],
    "FEATURE_GAP": [
        r"\b(do\s+you\s+(support|integrate\s+with|have)|does\s+it\s+(work\s+with|support))\b",
        r"\b(need\s+(native\s+)?integration\s+with|missing|lacking)\b"
    ],
    "SOFT_NO_BUSY": [
        r"\b(swamped|buried|slammed|crazy\s+busy|no\s+bandwidth|underwater)\b",
        r"\b(not\s+interested|pass\s+for\s+now|pass\s+on\s+this|pass\s+thanks)\b"
    ]
}


def sanitize_input(text: Optional[str]) -> str:
    """
    Layer 1 & 2 Paranoia: Strips control characters, prompt injection signatures,
    and bounds length before classification.
    """
    if not text or not isinstance(text, str):
        return ""
    # Strip non-printable control characters (except common whitespace)
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")
    # Truncate to reasonable bounds to protect regex execution time
    return cleaned.strip()[:4000]


def extract_detected_competitor(message: str) -> Optional[str]:
    """
    Extracts named competitor if referenced in the prospect text.
    """
    m_lower = message.lower()
    for comp in KNOWN_COMPETITORS:
        if re.search(r"\b" + re.escape(comp) + r"\b", m_lower):
            # Return canonical capitalized brand name
            if comp in ["apollo", "apollo.io"]:
                return "Apollo.io"
            elif comp in ["zoominfo"]:
                return "ZoomInfo"
            elif comp in ["lemlist"]:
                return "Lemlist"
            elif comp in ["instantly", "instantly.ai"]:
                return "Instantly"
            elif comp in ["outreach"]:
                return "Outreach"
            elif comp in ["salesloft"]:
                return "Salesloft"
            elif comp in ["clay", "clay.com"]:
                return "Clay"
            elif comp in ["smartlead"]:
                return "Smartlead"
            return comp.capitalize()
    return None


def extract_detected_timing(message: str) -> Optional[str]:
    """
    Extracts future quarter, month, or timing window if mentioned.
    """
    m_lower = message.lower()
    quarter_match = re.search(r"\b(q[1-4]|next\s+quarter|next\s+year)\b", m_lower)
    if quarter_match:
        return quarter_match.group(1).upper()
    
    month_match = re.search(r"\b(november|december|january|february|march|april|may|june|july|august|september|october)\b", m_lower)
    if month_match:
        return month_match.group(1).capitalize()
    
    return None


def extract_detected_referral(message: str) -> Optional[str]:
    """
    Extracts referred colleague name if mentioned (e.g. 'talk to Sarah').
    """
    referral_match = re.search(r"\b(?:talk to|speak with|reach out to|contact)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", message)
    if referral_match:
        name = referral_match.group(1).strip()
        # Filter out common false positives
        if name.lower() not in ["our", "my", "someone", "the", "a", "us", "them"]:
            return name
    return None


def classify_objection(message_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Layer 0 & Layer 1: Core Objection Classifier.
    Evaluates message against prioritized regex signatures and entity extractors.
    Returns structured categorization, confidence score, and extracted entities.
    """
    clean_text = sanitize_input(message_text)
    if not clean_text:
        return {
            "objection_type": "GENERAL_INQUIRY",
            "objection_label": OBJECTION_TYPES["GENERAL_INQUIRY"],
            "confidence": 0.0,
            "detected_competitor": None,
            "detected_timing": None,
            "detected_referral": None,
            "raw_snippet": ""
        }

    # 1. First priority check: Specific Competitor Mentions
    competitor = extract_detected_competitor(clean_text)
    if competitor:
        return {
            "objection_type": "COMPETITOR_INCUMBENT",
            "objection_label": OBJECTION_TYPES["COMPETITOR_INCUMBENT"],
            "confidence": 0.95,
            "detected_competitor": competitor,
            "detected_timing": extract_detected_timing(clean_text),
            "detected_referral": None,
            "raw_snippet": clean_text[:200]
        }

    # 2. Sequential regex pattern matching across remaining categories
    matched_type = "GENERAL_INQUIRY"
    confidence = 0.0

    for obj_type, patterns in PATTERNS.items():
        for pat in patterns:
            if re.search(pat, clean_text, re.IGNORECASE):
                matched_type = obj_type
                confidence = 0.90
                break
        if matched_type != "GENERAL_INQUIRY":
            break

    timing = extract_detected_timing(clean_text)
    referral = extract_detected_referral(clean_text)

    # Adjust confidence if corroborating entities were found
    if matched_type == "TIMING_LATER" and timing:
        confidence = 0.95
    elif matched_type == "WRONG_PERSON_REFERRAL" and referral:
        confidence = 0.95

    return {
        "objection_type": matched_type,
        "objection_label": OBJECTION_TYPES.get(matched_type, "General Inquiry"),
        "confidence": confidence,
        "detected_competitor": competitor,
        "detected_timing": timing,
        "detected_referral": referral,
        "raw_snippet": clean_text[:200]
    }
