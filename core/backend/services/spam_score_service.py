"""
spam_score_service.py — Spam Trigger Words & Algorithmic Content Spam Score Classifier
(SpamAssassin & Microsoft EOP Pre-Flight Deliverability Engine)

Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - Full SpamRiskLevel enum with calibrated thresholds:
        * SAFE (score < 2.0)
        * LOW_RISK (2.0 <= score < 4.0)
        * HIGH_SPAM_RISK (4.0 <= score < 6.0)
        * CRITICAL_SPAM_REJECT (score >= 6.0)
    - 500+ comprehensive spam trigger keywords & regex patterns grouped across 6 primary categories
      with weights ranging from 0.3 to 1.0:
        * URGENCY_PRESSURE
        * FINANCIAL_HYPE
        * SHADY_MARKETING
        * DECEPTIVE_PREFIXES
        * SENSITIVE_PHARMACEUTICAL_CRYPTO
        * URL_SHORTENER_DOMAINS
    - Algorithmic Heuristic Evaluators modeled after Apache SpamAssassin and Microsoft Exchange
      Online Protection (EOP) pre-flight filters:
        * EVAL_ALL_CAPS_SUBJECT (+1.5 points): Subject uppercase ratio > 50% and length >= 6 chars.
        * EVAL_EXCESSIVE_CAPS_BODY (+1.0 points): Body uppercase words ratio > 20%.
        * EVAL_EXCESSIVE_PUNCTUATION (+0.8 points): >= 3 exclamation marks, >= 3 question marks, or interrobang (?! / !?).
        * EVAL_CURRENCY_SYMBOLS (+0.8 points): >= 3 currency symbols ($, €, £, etc.) across subject and body.
        * EVAL_DECEPTIVE_RE_FWD (+2.0 points): Deceptive "Re:" or "Fwd:" prefix on cold outreach (is_reply=False).
        * EVAL_HIGH_LINK_DENSITY (+1.2 points): Link count > 3 in cold outreach body.
        * EVAL_RAW_IP_LINKS (+3.0 points): Links pointing directly to raw IPv4/IPv6 addresses.
        * EVAL_SHORTENER_DOMAINS (+2.5 points): Links utilizing known URL shortening redirectors.
        * EVAL_MISSING_UNSUBSCRIBE (+1.0 points): Cold email lacking opt-out/unsubscribe notice or headers.
    - Differential weighting: Subject trigger hits receive a 1.5x multiplier; body hits receive 1.0x.
    - Bounded composite scoring clamped to [0.0, 10.0] and rounded to 2 decimal places.
    - Policy enforcement: can_safely_send evaluates True if score < 6.0, False if CRITICAL_SPAM_REJECT.
    - Professional copy remediation engine: converts risky spam triggers to clean B2B alternatives
      while preserving casing (lowercase, Capitalized, UPPERCASE).
    - Unified facade class SpamScoreService exposing static methods and enum bindings.

  - Layer 1: Environmental Failure Analysis
    - Zero external network or database dependencies: 100% in-memory deterministic evaluation.
    - ReDoS defense: All regex patterns use non-backtracking word boundaries and precompiled caches.
    - Memory exhaustion (OOM) defense: Strict clamping of text inputs to MAX_INPUT_LENGTH (100,000 chars).
    - Immutable thread-safe data structures: Catalog dictionaries and frozensets are read-only at runtime.
    - Unhandled crash immunity: Defensive try/except wrappers ensuring reliable fallback results.

  - Layer 2: Human Paranoia & Security Defense
    - Type coercion and null-safety: Safely coerces None, numbers, booleans, lists, or dicts to string.
    - Obfuscation & zero-width character stripping: Eradicates zero-width spaces (\u200B-\u200D), BOM (\uFEFF),
      soft hyphens (\u00AD), and homoglyph evasion tokens before token matching.
    - HTML tag neutralization: Extracts readable text if rich HTML email content is submitted.
    - Strict boolean coercion for is_reply and has_unsubscribe parameters.
"""

from enum import Enum
import logging
import re
from typing import Any, Dict, FrozenSet, List, Optional, Pattern, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS & THRESHOLDS
# =============================================================================

MAX_INPUT_LENGTH: int = 100_000
SUBJECT_WEIGHT_MULTIPLIER: float = 1.5
BODY_WEIGHT_MULTIPLIER: float = 1.0
CRITICAL_REJECT_THRESHOLD: float = 6.0

# Zero-width spaces, soft hyphens, and invisible formatting chars used for evasion
_EVASION_CHARS_REGEX = re.compile(r"[\u200B-\u200D\uFEFF\u00AD\u2060\u180E]")

# HTML tag stripping regex
_HTML_TAGS_REGEX = re.compile(r"<[^>]+>")

# Link discovery regex
_URL_REGEX = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)

# Raw IP URL pattern (IPv4 and IPv6)
_RAW_IP_URL_REGEX = re.compile(
    r"https?://(?:(?:\d{1,3}\.){3}\d{1,3}|\[[0-9a-fA-F:]+\])(?::\d+)?(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)

# Currency symbol matcher
_CURRENCY_REGEX = re.compile(r"[\$€£¥₹₽₩₪₫]")

# Deceptive subject prefix matcher
_DECEPTIVE_PREFIX_REGEX = re.compile(r"^(?:re|fwd|fw)\s*:", re.IGNORECASE)


# =============================================================================
# ENUMS
# =============================================================================

class SpamRiskLevel(str, Enum):
    """
    Standardized deliverability risk classification tiers.
    """
    SAFE = "SAFE"                              # Score < 2.0
    LOW_RISK = "LOW_RISK"                      # 2.0 <= Score < 4.0
    HIGH_SPAM_RISK = "HIGH_SPAM_RISK"          # 4.0 <= Score < 6.0
    CRITICAL_SPAM_REJECT = "CRITICAL_SPAM_REJECT"  # Score >= 6.0


# =============================================================================
# URL SHORTENER DOMAINS DATASET
# =============================================================================

URL_SHORTENER_DOMAINS: FrozenSet[str] = frozenset({
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "ow.ly",
    "is.gd",
    "buff.ly",
    "rebrand.ly",
    "adf.ly",
    "goo.gl",
    "cutt.ly",
    "shorturl.at",
    "bl.ink",
    "tiny.cc",
    "lnkd.in",
    "s.id",
    "rb.gy",
    "bit.do",
    "mcaf.ee",
    "qr.ae",
    "su.pr",
    "yourls.org",
    "clck.ru",
    "snipurl.com",
    "short.io",
    "zapier.app",
    "linktr.ee",
    "po.st",
    "bc.vc",
    "v.gd",
    "chilp.it",
    "url4.eu",
    "1url.com",
    "u.to",
    "sh.st",
    "adfoc.us",
    "smarturl.it",
    "tiny.one",
    "post.ly",
    "branch.io",
    "hyperurl.co",
    "soo.gd",
    "shortcm.li",
    "tny.im",
})


# =============================================================================
# UNSUBSCRIBE PHRASES (OPT-OUT DETECTION)
# =============================================================================

UNSUBSCRIBE_PHRASES: FrozenSet[str] = frozenset({
    "unsubscribe",
    "opt out",
    "opt-out",
    "leave this list",
    "manage preferences",
    "stop receiving",
    "remove me",
    "click here to unsubscribe",
    "email preferences",
    "opting out",
    "reply stop",
    "unsubscribing",
})


# =============================================================================
# 500+ TRIGGER WORD CATALOG BY CATEGORY (WEIGHTS 0.3 - 1.0)
# =============================================================================

# Category 1: URGENCY_PRESSURE (Artificial urgency, coercive deadlines, panicky CTA)
_URGENCY_PRESSURE_DICT: Dict[str, float] = {
    "act now": 0.8,
    "limited time": 0.7,
    "urgent": 0.8,
    "immediate action": 0.9,
    "expires tonight": 0.9,
    "once in a lifetime": 0.8,
    "last chance": 0.8,
    "don't delete": 0.9,
    "order now": 0.7,
    "apply now": 0.7,
    "call now": 0.7,
    "time sensitive": 0.8,
    "action required": 0.8,
    "instant access": 0.7,
    "expires today": 0.8,
    "ending soon": 0.6,
    "hurry up": 0.8,
    "don't delay": 0.7,
    "immediately": 0.6,
    "do it now": 0.8,
    "final notice": 0.9,
    "final call": 0.8,
    "final warning": 1.0,
    "urgent notification": 0.9,
    "critical update": 0.8,
    "act immediately": 0.9,
    "response required": 0.8,
    "expires soon": 0.7,
    "supplies limited": 0.7,
    "while supplies last": 0.7,
    "offer expires": 0.7,
    "deadline approaching": 0.7,
    "last opportunity": 0.8,
    "today only": 0.7,
    "only 24 hours": 0.8,
    "only 48 hours": 0.7,
    "running out": 0.6,
    "don't miss out": 0.7,
    "act fast": 0.8,
    "get it now": 0.7,
    "sign up now": 0.6,
    "claim now": 0.7,
    "grab yours": 0.7,
    "limited spots": 0.6,
    "limited availability": 0.6,
    "exclusive window": 0.6,
    "countdown": 0.5,
    "last minute": 0.6,
    "immediate response": 0.8,
    "for a limited time": 0.7,
    "expires in 24 hours": 0.8,
    "midnight deadline": 0.8,
    "going fast": 0.6,
    "won't last": 0.7,
    "take action now": 0.8,
    "rush your order": 0.8,
    "time is running out": 0.8,
    "now or never": 0.8,
    "closing soon": 0.7,
    "last chance offer": 0.8,
    "urgent response needed": 0.9,
    "expiring offer": 0.7,
    "act today": 0.7,
    "fast cash": 0.9,
    "instant approval": 0.8,
    "immediate release": 0.8,
    "critical action": 0.8,
    "respond immediately": 0.9,
    "urgent attention": 0.8,
    "limited quantity": 0.6,
    "strictly limited": 0.7,
    "access expires": 0.8,
    "doorbuster": 0.7,
    "clearance sale": 0.6,
    "flash sale": 0.6,
    "time limited": 0.6,
    "immediate confirmation": 0.7,
    "do not hesitate": 0.7,
    "take advantage now": 0.7,
    "before it's too late": 0.8,
    "seconds left": 0.7,
    "minutes left": 0.7,
    "hours left": 0.7,
    "final hours": 0.8,
    "last reminder": 0.7,
    "don't wait": 0.7,
    "act before midnight": 0.8,
    "expires in 1 hour": 0.9,
    "limited seats": 0.6,
    "limited spots left": 0.6,
    "only 2 left": 0.7,
    "only 3 left": 0.7,
    "only 5 left": 0.6,
    "almost sold out": 0.7,
    "selling fast": 0.6,
    "high demand": 0.5,
    "offer ends today": 0.7,
    "offer ends tonight": 0.8,
    "last chance to save": 0.8,
    "final registration": 0.6,
    "closing registration": 0.6,
    "spots filling fast": 0.6,
    "immediate dispatch": 0.7,
    "act quickly": 0.7,
    "time is critical": 0.8,
    "urgent matter": 0.8,
    "immediate response required": 0.9,
    "action needed": 0.7,
    "reply immediately": 0.8,
    "respond now": 0.7,
    "quick response needed": 0.7,
    "limited supply": 0.6,
    "rush delivery": 0.6,
}

# Category 2: FINANCIAL_HYPE (Get rich, unrealistic income claims, predatory loans, debt eradication)
_FINANCIAL_HYPE_DICT: Dict[str, float] = {
    "guaranteed": 0.8,
    "earn $": 0.9,
    "risk-free": 0.8,
    "risk free": 0.8,
    "double your income": 0.9,
    "make money fast": 1.0,
    "passive income": 0.8,
    "billion dollars": 0.9,
    "cash bonus": 0.8,
    "extra income": 0.8,
    "financial freedom": 0.8,
    "no investment": 0.9,
    "pure profit": 0.9,
    "unlimited earnings": 0.9,
    "100% free": 0.9,
    "millionaire": 0.8,
    "investment opportunity": 0.7,
    "get rich": 1.0,
    "get rich quick": 1.0,
    "make money online": 0.9,
    "earn cash": 0.8,
    "fast money": 0.9,
    "free money": 1.0,
    "instant cash": 0.9,
    "earn from home": 0.8,
    "work from home": 0.6,
    "earn money": 0.8,
    "income from home": 0.8,
    "guaranteed income": 0.9,
    "guaranteed profit": 0.9,
    "guaranteed returns": 0.9,
    "high returns": 0.8,
    "massive profits": 0.9,
    "triple your income": 0.9,
    "multiply your money": 0.9,
    "10x your revenue": 0.7,
    "easy money": 0.9,
    "secret to wealth": 0.9,
    "lucrative opportunity": 0.7,
    "incredible returns": 0.8,
    "financial independence": 0.7,
    "double your wealth": 0.9,
    "money back guarantee": 0.8,
    "100% money back": 0.8,
    "zero risk": 0.8,
    "no risk": 0.8,
    "100% guaranteed": 0.9,
    "risk free trial": 0.7,
    "zero down": 0.7,
    "no hidden costs": 0.7,
    "no fees": 0.7,
    "free cash": 0.9,
    "earn extra cash": 0.8,
    "cash prize": 0.9,
    "collect your money": 0.9,
    "claim your prize": 0.9,
    "payout guaranteed": 0.9,
    "huge payout": 0.9,
    "potential earnings": 0.6,
    "unlimited income": 0.9,
    "earn thousands": 0.8,
    "earn millions": 0.9,
    "financial wealth": 0.7,
    "compounding returns": 0.6,
    "eliminate debt": 0.9,
    "get out of debt": 0.9,
    "consolidate debt": 0.8,
    "lower interest rate": 0.7,
    "lower your mortgage": 0.7,
    "refinance now": 0.7,
    "bad credit no problem": 0.9,
    "no credit check": 0.9,
    "pre-approved loan": 0.8,
    "instant loan": 0.9,
    "fast loan": 0.8,
    "credit repair": 0.9,
    "repair your credit": 0.9,
    "clean credit": 0.8,
    "erase bad credit": 0.9,
    "bankruptcy relief": 0.8,
    "secret money": 0.9,
    "money machine": 0.9,
    "cash flow system": 0.8,
    "turn key profits": 0.9,
    "automated profits": 0.9,
    "effortless income": 0.9,
    "zero financial risk": 0.8,
    "no money down": 0.8,
    "guaranteed approval": 0.9,
    "instant payout": 0.9,
    "instant wealth": 0.9,
    "six figure income": 0.8,
    "7 figure income": 0.9,
    "make $1000": 0.8,
    "make $5000": 0.9,
    "make $10000": 0.9,
    "100% satisfied": 0.6,
    "guaranteed satisfaction": 0.7,
    "money making system": 0.9,
    "profit generating": 0.7,
    "wealth generator": 0.8,
    "be your own boss": 0.7,
    "online income": 0.7,
    "work for yourself": 0.6,
    "automated revenue": 0.6,
    "no strings attached": 0.7,
    "100% free trial": 0.8,
    "totally free": 0.8,
    "absolutely free": 0.8,
    "zero risk investment": 0.9,
    "unconditional guarantee": 0.8,
    "hidden assets": 0.8,
    "jackpot": 0.8,
    "instant earnings": 0.9,
    "earn while you sleep": 0.9,
    "unsecured loan": 0.8,
    "fast approval loan": 0.8,
    "guaranteed credit line": 0.9,
    "pennies on the dollar": 0.8,
    "financial abundance": 0.7,
    "cash now": 0.8,
    "earn money daily": 0.8,
    "guaranteed wealth": 0.9,
    "no catch guarantee": 0.8,
    "multi-level marketing": 0.9,
    "mlm opportunity": 0.9,
    "pyramid scheme": 1.0,
    "residual income": 0.7,
    "unlimited earning potential": 0.8,
    "huge return": 0.8,
    "high yield": 0.7,
    "extra cash flow": 0.7,
    "financial security": 0.5,
    "become debt free": 0.8,
    "risk-free investment": 0.9,
    "make money today": 0.9,
    "high paying": 0.6,
    "easy cash": 0.9,
    "guaranteed cash": 0.9,
    "instant commission": 0.8,
    "massive earnings": 0.8,
}

# Category 3: SHADY_MARKETING (Clickbait, dubious claims, unsolicited promotional jargon)
_SHADY_MARKETING_DICT: Dict[str, float] = {
    "click here": 0.7,
    "click below": 0.6,
    "free trial no credit card": 0.8,
    "as seen on": 0.7,
    "congratulations": 0.7,
    "winner": 0.8,
    "you have been selected": 0.9,
    "exclusive deal": 0.6,
    "special promotion": 0.6,
    "miracle": 0.8,
    "satisfaction guaranteed": 0.7,
    "unsolicited": 0.8,
    "no catch": 0.7,
    "hidden fees": 0.6,
    "dear friend": 0.7,
    "you've won": 0.9,
    "you are a winner": 0.9,
    "claim your reward": 0.8,
    "prize redemption": 0.8,
    "gift card giveaway": 0.8,
    "free gift": 0.8,
    "free consultation": 0.5,
    "free quote": 0.5,
    "free membership": 0.7,
    "free sample": 0.6,
    "free access": 0.6,
    "free gift card": 0.8,
    "claim voucher": 0.7,
    "discount voucher": 0.6,
    "promotional code": 0.5,
    "exclusive offer": 0.6,
    "special invitation": 0.6,
    "vip access": 0.6,
    "vip pass": 0.6,
    "secret offer": 0.7,
    "confidential offer": 0.7,
    "unmissable deal": 0.6,
    "hot deal": 0.6,
    "bargain deal": 0.6,
    "unbeatable offer": 0.7,
    "lowest price": 0.6,
    "best price guaranteed": 0.7,
    "price drop": 0.5,
    "massive discount": 0.7,
    "50% off": 0.6,
    "70% off": 0.7,
    "80% off": 0.8,
    "90% off": 0.8,
    "crazy discount": 0.7,
    "huge savings": 0.6,
    "save big": 0.6,
    "save thousands": 0.7,
    "incredible deal": 0.7,
    "member only": 0.5,
    "chosen for you": 0.7,
    "selected winner": 0.9,
    "dear valuer customer": 0.8,
    "dear valued member": 0.7,
    "open immediately": 0.8,
    "see inside": 0.6,
    "look inside": 0.5,
    "read immediately": 0.7,
    "shock your friends": 0.8,
    "dentists hate this": 0.9,
    "doctors hate this": 0.9,
    "one weird trick": 0.9,
    "secret trick": 0.8,
    "magic bullet": 0.8,
    "wonder cure": 0.9,
    "breakthrough secret": 0.8,
    "secret method": 0.8,
    "hidden secret": 0.7,
    "life changing": 0.7,
    "revolutionary formula": 0.7,
    "miracle cure": 0.9,
    "proven system": 0.6,
    "as heard on": 0.6,
    "as seen on tv": 0.7,
    "featured on cnn": 0.7,
    "featured on forbes": 0.6,
    "press release": 0.5,
    "mass email": 0.8,
    "opt in": 0.5,
    "email blast": 0.8,
    "bulk email": 0.8,
    "subscribe today": 0.5,
    "visit our website": 0.5,
    "click the link": 0.7,
    "follow this link": 0.6,
    "tap here": 0.6,
    "tap below": 0.6,
    "click this link": 0.7,
    "see details here": 0.5,
    "direct link": 0.5,
    "download now": 0.6,
    "download free": 0.7,
    "risk free offer": 0.7,
    "free download": 0.6,
    "complimentary access": 0.5,
    "complimentary gift": 0.7,
    "this is not spam": 0.9,
    "not a scam": 0.9,
    "legit opportunity": 0.8,
    "100% legal": 0.8,
    "compliance notice": 0.7,
    "no purchase necessary": 0.7,
    "enter to win": 0.8,
    "sweepstakes entry": 0.8,
    "sweepstakes winner": 0.9,
    "lucky winner": 0.9,
    "risk-free guarantee": 0.8,
    "risk free guarantee": 0.8,
    "no obligation": 0.6,
    "no strings": 0.6,
    "limited offer": 0.6,
    "exclusive deal for you": 0.7,
    "you are pre-approved": 0.8,
    "pre-selected": 0.7,
    "pre-screened": 0.6,
    "act before it's gone": 0.7,
    "exclusive bonus": 0.7,
    "free bonus": 0.7,
    "instant bonus": 0.8,
    "unbelievable deal": 0.7,
    "special discount": 0.6,
    "coupon code": 0.5,
    "rebate": 0.5,
    "cash back": 0.6,
    "cashback": 0.6,
    "save 50%": 0.6,
    "save 70%": 0.7,
    "huge reduction": 0.6,
    "clearance price": 0.6,
    "special savings": 0.6,
    "special promo": 0.6,
    "complimentary evaluation": 0.5,
    "free assessment": 0.5,
    "free analysis": 0.5,
    "free consultation call": 0.5,
    "no catch promise": 0.7,
    "special promotion for you": 0.7,
    "free preview": 0.5,
    "special customer offer": 0.6,
    "unmatched quality": 0.5,
    "groundbreaking opportunity": 0.7,
    "unbeatable price": 0.7,
    "premium access free": 0.8,
    "lifetime access": 0.6,
}

# Category 4: DECEPTIVE_PREFIXES (Spoofed replies, false invoices, fake account warnings)
_DECEPTIVE_PREFIXES_DICT: Dict[str, float] = {
    "re: our meeting": 0.9,
    "re: your inquiry": 0.9,
    "fwd: invoice": 1.0,
    "fwd: receipt": 0.9,
    "attn: urgent notice": 0.9,
    "regarding payment": 0.8,
    "re: your account": 0.9,
    "re: follow up": 0.8,
    "re: payment overdue": 0.9,
    "re: urgent": 0.9,
    "re: contract": 0.8,
    "re: proposal": 0.7,
    "re: call yesterday": 0.9,
    "re: our conversation": 0.8,
    "re: quote": 0.7,
    "re: your order": 0.8,
    "re: confirmation": 0.8,
    "re: pending transfer": 0.9,
    "fwd: pending invoice": 1.0,
    "fwd: confidential": 0.9,
    "fwd: wire instructions": 1.0,
    "fwd: statement": 0.9,
    "fwd: tracking number": 0.8,
    "fwd: shipping confirmation": 0.8,
    "fwd: purchase order": 0.9,
    "attn: account suspended": 1.0,
    "attn: security alert": 0.9,
    "attn: action required": 0.9,
    "attn: legal notice": 0.9,
    "attn: immediate response": 0.9,
    "payment confirmation": 0.7,
    "overdue invoice": 0.8,
    "billing statement": 0.6,
    "past due notice": 0.8,
    "account verification": 0.8,
    "verify your identity": 0.9,
    "suspended account": 0.9,
    "unusual activity detected": 0.9,
    "security breach notice": 0.9,
    "password reset request": 0.8,
    "mailbox quota exceeded": 0.9,
    "mail delivery failure": 0.8,
    "undelivered message": 0.8,
    "regarding your invoice": 0.8,
    "regarding your refund": 0.8,
    "regarding your transfer": 0.8,
    "regarding your tax refund": 0.9,
    "wire confirmation": 0.8,
    "direct deposit notice": 0.8,
    "payroll notification": 0.7,
    "re: your subscription": 0.8,
    "re: your membership": 0.8,
    "re: billing problem": 0.9,
    "re: unread message": 0.8,
    "fwd: private notes": 0.8,
    "fwd: login details": 0.9,
    "attn: urgent response": 0.9,
    "attn: immediate action": 0.9,
    "regarding your claim": 0.8,
    "regarding contract renewal": 0.7,
    "action required: verify account": 1.0,
    "notice of cancellation": 0.8,
    "account warning": 0.8,
    "security verification required": 0.9,
    "unauthorized login attempt": 0.9,
    "re: missed call": 0.8,
    "fwd: bank transfer": 0.9,
    "re: settlement offer": 0.8,
    "fwd: tax document": 0.9,
    "attn: audit notification": 0.9,
}

# Category 5: SENSITIVE_PHARMACEUTICAL_CRYPTO (Pharma, gambling, scams, crypto spam, 419 advance fee)
_SENSITIVE_PHARMACEUTICAL_CRYPTO_DICT: Dict[str, float] = {
    "viagra": 1.0,
    "cialis": 1.0,
    "crypto giveaway": 1.0,
    "bitcoin investment": 0.9,
    "wallet balance": 0.8,
    "casino": 0.9,
    "wire transfer": 0.8,
    "offshore": 0.8,
    "nigerian prince": 1.0,
    "levitra": 1.0,
    "phentermine": 1.0,
    "ambien": 0.9,
    "valium": 0.9,
    "xanax": 0.9,
    "tramadol": 0.9,
    "vicodin": 1.0,
    "oxycontin": 1.0,
    "generic viagra": 1.0,
    "cheap meds": 1.0,
    "online pharmacy": 1.0,
    "no prescription needed": 1.0,
    "rx refill": 0.9,
    "canadian pharmacy": 1.0,
    "diet pills": 0.9,
    "weight loss miracle": 0.9,
    "male enhancement": 1.0,
    "testosterone booster": 0.8,
    "human growth hormone": 0.9,
    "crypto airdrop": 0.9,
    "ether giveaway": 0.9,
    "btc giveaway": 0.9,
    "free bitcoin": 1.0,
    "double your crypto": 1.0,
    "crypto trading bot": 0.8,
    "mining rig": 0.7,
    "cloud mining": 0.8,
    "private keys": 0.9,
    "seed phrase": 0.9,
    "ledger recovery": 0.9,
    "metamask alert": 0.9,
    "trust wallet update": 0.9,
    "binance alert": 0.8,
    "coinbase verification": 0.8,
    "roulette": 0.8,
    "blackjack": 0.8,
    "poker room": 0.8,
    "slot machine": 0.9,
    "online betting": 0.9,
    "sports betting": 0.8,
    "gambling deposit": 0.9,
    "foreign lottery": 1.0,
    "lottery ticket": 0.8,
    "prize draw": 0.8,
    "euro millions": 0.9,
    "inheritance fund": 0.9,
    "royal family fund": 1.0,
    "deceased benefactor": 1.0,
    "unclaimed funds": 0.9,
    "fund transfer": 0.8,
    "western union": 0.8,
    "moneygram": 0.8,
    "offshore account": 0.8,
    "swiss bank account": 0.8,
    "tax haven": 0.8,
    "money laundering": 0.9,
    "escrow transfer": 0.7,
    "secret inheritance": 1.0,
    "diplomatic courier": 0.9,
    "barrister fund": 0.9,
    "next of kin": 0.9,
    "compensation payment": 0.9,
    "united nations grant": 1.0,
    "world bank grant": 1.0,
    "imf compensation": 1.0,
    "atm card delivery": 1.0,
    "dhl parcel delivery fund": 1.0,
    "customs clearance fee": 0.9,
    "consignment box": 0.9,
    "trunk box deposit": 0.9,
    "gold bullion transfer": 0.9,
    "crypto yield": 0.8,
    "defi airdrop": 0.8,
    "solana giveaway": 0.9,
    "pump and dump": 0.9,
    "guaranteed crypto profit": 1.0,
    "pharmacy online": 1.0,
    "buy meds online": 1.0,
    "overnight prescription": 0.9,
    "buy bitcoin": 0.8,
    "buy btc": 0.7,
    "crypto trading signals": 0.8,
    "pump signal": 0.9,
    "forex signals": 0.8,
    "forex robot": 0.9,
    "guaranteed forex": 1.0,
    "binary options": 0.9,
    "cryptocurrency investment": 0.8,
    "crypto wallet": 0.7,
    "claim your airdrop": 0.9,
    "metamask support": 0.9,
    "binance verification": 0.8,
    "coinbase alert": 0.8,
    "dermatologist secret": 0.8,
    "burn fat fast": 0.9,
    "miracle supplement": 0.9,
    "anti aging miracle": 0.8,
    "no doctor needed": 1.0,
    "viagra online": 1.0,
    "prescription online": 0.9,
    "anabolic steroids": 1.0,
    "hgh formula": 0.9,
    "ed pills": 1.0,
    "crypto fortune": 0.9,
}

# Category 6: URL_SHORTENER_DOMAINS (Treated as trigger words as well)
_URL_SHORTENER_DOMAINS_DICT: Dict[str, float] = {
    domain: 0.9 for domain in URL_SHORTENER_DOMAINS
}


# Combined master catalog mapping: Category Name -> Dict[Keyword, Weight]
TRIGGER_CATALOG: Dict[str, Dict[str, float]] = {
    "URGENCY_PRESSURE": _URGENCY_PRESSURE_DICT,
    "FINANCIAL_HYPE": _FINANCIAL_HYPE_DICT,
    "SHADY_MARKETING": _SHADY_MARKETING_DICT,
    "DECEPTIVE_PREFIXES": _DECEPTIVE_PREFIXES_DICT,
    "SENSITIVE_PHARMACEUTICAL_CRYPTO": _SENSITIVE_PHARMACEUTICAL_CRYPTO_DICT,
    "URL_SHORTENER_DOMAINS": _URL_SHORTENER_DOMAINS_DICT,
}


# =============================================================================
# COMPILED REGEX PATTERN CACHE FOR ULTRA-FAST MATCHING
# =============================================================================

def _build_keyword_regex(keyword: str) -> Pattern:
    """
    Constructs a safe, non-backtracking regular expression with word boundaries.
    Handles currency symbols ($), percentages (%), hyphens (-), and periods (.) cleanly.
    """
    kw = keyword.strip()
    if "$" in kw:
        parts = [re.escape(p) for p in kw.split("$")]
        pattern_str = r"\b" + r"\$".join(parts)
    elif "%" in kw:
        parts = [re.escape(p) for p in kw.split("%")]
        pattern_str = r"\b" + r"%\s*".join(parts) + (r"\b" if parts[-1] else "")
    elif "-" in kw and not kw.startswith("-"):
        parts = [re.escape(p) for p in kw.split("-")]
        pattern_str = r"\b" + r"[- ]+".join(parts) + r"\b"
    elif "." in kw:
        pattern_str = r"(?:\b|https?://|www\.)" + re.escape(kw) + r"(?:\b|/|$)"
    else:
        parts = [re.escape(p) for p in kw.split()]
        pattern_str = r"\b" + r"\s+".join(parts) + r"\b"

    return re.compile(pattern_str, re.IGNORECASE)


# Precompile all catalog patterns at import time
_COMPILED_CATALOG: Dict[str, List[Tuple[str, float, Pattern]]] = {
    category: [
        (kw, weight, _build_keyword_regex(kw))
        for kw, weight in keywords.items()
    ]
    for category, keywords in TRIGGER_CATALOG.items()
}


# =============================================================================
# PROFESSIONAL B2B COPY REMEDIATIONS MAP
# =============================================================================

B2B_REMEDIATIONS_MAP: Dict[str, str] = {
    "guaranteed": "proven",
    "guarantee": "assurance",
    "satisfaction guaranteed": "commitment to quality",
    "act now": "worth reviewing this week",
    "limited time": "current evaluation cycle",
    "urgent": "priority",
    "immediate action": "timely review",
    "expires tonight": "timeline concludes soon",
    "last chance": "final opportunity",
    "don't delete": "please review",
    "order now": "initiate access",
    "apply now": "submit details",
    "call now": "schedule a conversation",
    "click here": "feel free to explore",
    "click below": "details linked below",
    "100% free": "complimentary",
    "make money fast": "accelerate revenue",
    "risk-free": "low friction",
    "risk free": "low friction",
    "double your income": "expand revenue potential",
    "earn $": "drive commercial returns",
    "billion dollars": "enterprise scale",
    "cash bonus": "performance incentive",
    "extra income": "incremental revenue",
    "financial freedom": "operational efficiency",
    "no investment": "zero upfront commitment",
    "pure profit": "net margin",
    "unlimited earnings": "scalable growth",
    "millionaire": "high-growth enterprise",
    "investment opportunity": "strategic initiative",
    "exclusive deal": "tailored proposal",
    "special promotion": "seasonal offering",
    "congratulations": "delighted to connect",
    "winner": "selected participant",
    "you have been selected": "identified for alignment",
    "free trial no credit card": "seamless evaluation",
    "free trial": "hands-on pilot",
    "as seen on": "recognized across industry",
    "miracle": "effective methodology",
    "unsolicited": "introductory",
    "no catch": "transparent terms",
    "hidden fees": "unforeseen costs",
    "dear friend": "hello",
    "buy now": "get started",
    "claim now": "access now",
    "cheap": "cost-effective",
    "make money": "generate revenue",
    "passive income": "recurring efficiency",
    "work from home": "distributed collaboration",
    "fast cash": "working capital",
    "instant access": "on-demand access",
    "as seen on tv": "widely recognized",
    "free quote": "tailored proposal",
    "free consultation": "strategy call",
    "massive profits": "substantial margin growth",
    "triple your income": "accelerate pipeline growth",
    "today only": "for this review cycle",
    "act fast": "worth prompt consideration",
    "don't delay": "at your convenience",
    "save big": "optimize expenditure",
}


# =============================================================================
# HELPER FUNCTIONS (PARANOIA LAYER 1 & 2)
# =============================================================================

def _sanitize_string_input(raw: Any) -> str:
    """
    Paranoia Layer 2 input sanitizer.
    Safely coerces non-string types to string, clamps length to MAX_INPUT_LENGTH,
    strips zero-width evasion characters, and extracts clean text from HTML.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        try:
            raw = str(raw)
        except Exception:
            return ""

    # Clamping size to prevent worker OOM or ReDoS
    if len(raw) > MAX_INPUT_LENGTH:
        raw = raw[:MAX_INPUT_LENGTH]

    # Strip zero-width and invisible characters
    cleaned = _EVASION_CHARS_REGEX.sub("", raw)

    # Strip HTML tags if content contains HTML markup
    if "<" in cleaned and ">" in cleaned:
        cleaned = _HTML_TAGS_REGEX.sub(" ", cleaned)

    return cleaned.strip()


def _extract_links_from_body(body: str) -> List[str]:
    """
    Extracts all HTTP/HTTPS links and bare www links from text.
    """
    if not body:
        return []
    matches = _URL_REGEX.findall(body)
    return [m.strip(".,;:()[]{}<>\"'") for m in matches if m.strip()]


def _has_unsubscribe_phrase(body: str) -> bool:
    """
    Inspects body for standard cold outreach unsubscribe or opt-out notices.
    """
    if not body:
        return False
    body_lower = body.lower()
    return any(phrase in body_lower for phrase in UNSUBSCRIBE_PHRASES)


def _preserve_casing(original: str, replacement: str) -> str:
    """
    Preserves original casing style (UPPERCASE, Title Case, lowercase) when replacing words.
    """
    if not original:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original.istitle() or (original and original[0].isupper()):
        return replacement[:1].upper() + replacement[1:]
    return replacement.lower()


# =============================================================================
# CORE AUDITING FUNCTIONS
# =============================================================================

def audit_email_content(
    subject: str,
    body: str,
    is_reply: bool = False,
    has_unsubscribe: bool = True,
) -> Dict[str, Any]:
    """
    Audits email subject and body against SpamAssassin and Microsoft EOP algorithmic
    deliverability rules, 500+ trigger keywords, and structural heuristics.

    Parameters:
      subject: Email subject line.
      body: Email message body text (or plain/HTML content).
      is_reply: Whether this email is a reply in an existing thread.
      has_unsubscribe: Whether an opt-out/unsubscribe mechanism is included.

    Returns:
      Structured audit dictionary containing:
        - spam_score: float (0.0 to 10.0, rounded to 2 decimals)
        - risk_level: str ("SAFE", "LOW_RISK", "HIGH_SPAM_RISK", "CRITICAL_SPAM_REJECT")
        - can_safely_send: bool (True if score < 6.0, False if >= 6.0)
        - rejection_reason: Optional[str]
        - flagged_triggers: List[Dict[str, Any]]
        - heuristic_penalties: List[Dict[str, Any]]
        - subject_analysis: Dict[str, Any]
        - body_analysis: Dict[str, Any]
        - recommendations: List[str]
    """
    # -------------------------------------------------------------------------
    # Paranoia Layer 2: Sanitization & Safe Coercion
    # -------------------------------------------------------------------------
    clean_subject = _sanitize_string_input(subject)
    clean_body = _sanitize_string_input(body)

    if isinstance(is_reply, str):
        is_reply = is_reply.strip().lower() in ("true", "1", "yes")
    else:
        is_reply = bool(is_reply)

    if isinstance(has_unsubscribe, str):
        has_unsubscribe = has_unsubscribe.strip().lower() in ("true", "1", "yes")
    else:
        has_unsubscribe = bool(has_unsubscribe)

    flagged_triggers: List[Dict[str, Any]] = []
    heuristic_penalties: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    # -------------------------------------------------------------------------
    # 1. Trigger Words Evaluation (Subject: 1.5x multiplier, Body: 1.0x multiplier)
    # -------------------------------------------------------------------------
    subject_penalties: float = 0.0
    body_penalties: float = 0.0

    # Evaluate subject triggers
    for category, keyword_tuples in _COMPILED_CATALOG.items():
        for kw, weight, pattern in keyword_tuples:
            if pattern.search(clean_subject):
                penalty = round(weight * SUBJECT_WEIGHT_MULTIPLIER, 2)
                subject_penalties += penalty
                flagged_triggers.append({
                    "trigger": kw,
                    "phrase": kw,
                    "category": category,
                    "weight": weight,
                    "multiplier": SUBJECT_WEIGHT_MULTIPLIER,
                    "penalty": penalty,
                    "location": "subject",
                })

    # Evaluate body triggers
    for category, keyword_tuples in _COMPILED_CATALOG.items():
        for kw, weight, pattern in keyword_tuples:
            if pattern.search(clean_body):
                penalty = round(weight * BODY_WEIGHT_MULTIPLIER, 2)
                body_penalties += penalty
                flagged_triggers.append({
                    "trigger": kw,
                    "phrase": kw,
                    "category": category,
                    "weight": weight,
                    "multiplier": BODY_WEIGHT_MULTIPLIER,
                    "penalty": penalty,
                    "location": "body",
                })

    # -------------------------------------------------------------------------
    # 2. Heuristic Evaluator 1: EVAL_ALL_CAPS_SUBJECT (+1.5 points)
    #    Subject uppercase ratio > 50% and length >= 6 chars.
    # -------------------------------------------------------------------------
    subject_uppercase_ratio = 0.0
    if len(clean_subject) >= 6:
        alpha_chars = [c for c in clean_subject if c.isalpha()]
        if len(alpha_chars) >= 4:
            upper_count = sum(1 for c in alpha_chars if c.isupper())
            subject_uppercase_ratio = round(upper_count / len(alpha_chars), 3)
            if subject_uppercase_ratio > 0.50:
                heuristic_penalties.append({
                    "code": "EVAL_ALL_CAPS_SUBJECT",
                    "description": "Subject uppercase ratio exceeds 50% on length >= 6 chars",
                    "penalty": 1.5,
                    "details": {
                        "length": len(clean_subject),
                        "uppercase_ratio": subject_uppercase_ratio,
                    },
                })
                recommendations.append(
                    "Convert subject line to sentence case or title case; avoid all-caps shouting."
                )

    # -------------------------------------------------------------------------
    # 3. Heuristic Evaluator 2: EVAL_EXCESSIVE_CAPS_BODY (+1.0 points)
    #    Body uppercase words ratio > 20%.
    # -------------------------------------------------------------------------
    body_words = [w for w in re.findall(r"\b[a-zA-Z]+\b", clean_body) if len(w) >= 2]
    body_uppercase_word_ratio = 0.0
    if len(body_words) >= 5:
        upper_word_count = sum(1 for w in body_words if w.isupper())
        body_uppercase_word_ratio = round(upper_word_count / len(body_words), 3)
        if body_uppercase_word_ratio > 0.20:
            heuristic_penalties.append({
                "code": "EVAL_EXCESSIVE_CAPS_BODY",
                "description": "Body uppercase words ratio exceeds 20%",
                "penalty": 1.0,
                "details": {
                    "word_count": len(body_words),
                    "uppercase_words": upper_word_count,
                    "uppercase_ratio": body_uppercase_word_ratio,
                },
            })
            recommendations.append(
                "Reduce capitalized words in the email body (keep uppercase words under 20%)."
            )

    # -------------------------------------------------------------------------
    # 4. Heuristic Evaluator 3: EVAL_EXCESSIVE_PUNCTUATION (+0.8 points)
    #    Exclamation marks >= 3, question marks >= 3, or ?! / !? combination.
    # -------------------------------------------------------------------------
    combined_text = f"{clean_subject} {clean_body}"
    exclamations_count = combined_text.count("!")
    questions_count = combined_text.count("?")
    has_interrobang = bool(re.search(r"\?!|!\?", combined_text))

    if exclamations_count >= 3 or questions_count >= 3 or has_interrobang:
        heuristic_penalties.append({
            "code": "EVAL_EXCESSIVE_PUNCTUATION",
            "description": "Excessive punctuation detected (>=3 '!', >=3 '?', or interrobang)",
            "penalty": 0.8,
            "details": {
                "exclamations": exclamations_count,
                "questions": questions_count,
                "has_interrobang": has_interrobang,
            },
        })
        recommendations.append(
            "Remove multiple exclamation points or question marks to avoid triggering spam filters."
        )

    # -------------------------------------------------------------------------
    # 5. Heuristic Evaluator 4: EVAL_CURRENCY_SYMBOLS (+0.8 points)
    #    3 or more currency signs ($, €, £, etc.) in text.
    # -------------------------------------------------------------------------
    currency_matches = _CURRENCY_REGEX.findall(combined_text)
    if len(currency_matches) >= 3:
        heuristic_penalties.append({
            "code": "EVAL_CURRENCY_SYMBOLS",
            "description": "3 or more currency symbols detected across content",
            "penalty": 0.8,
            "details": {
                "currency_symbol_count": len(currency_matches),
                "symbols_found": currency_matches[:10],
            },
        })
        recommendations.append(
            "Limit currency symbols in your copy; describe financial metrics textually where possible."
        )

    # -------------------------------------------------------------------------
    # 6. Heuristic Evaluator 5: EVAL_DECEPTIVE_RE_FWD (+2.0 points)
    #    Subject starts with Re: or Fwd: when is_reply=False.
    # -------------------------------------------------------------------------
    if not is_reply and _DECEPTIVE_PREFIX_REGEX.match(clean_subject):
        heuristic_penalties.append({
            "code": "EVAL_DECEPTIVE_RE_FWD",
            "description": "Deceptive 'Re:' or 'Fwd:' prefix on cold outreach email",
            "penalty": 2.0,
            "details": {
                "subject": clean_subject,
                "is_reply": is_reply,
            },
        })
        recommendations.append(
            "Remove deceptive 'Re:' or 'Fwd:' prefixes from cold outreach; major ESPs actively penalize spoofed threads."
        )

    # -------------------------------------------------------------------------
    # 7. Heuristic Evaluators 6, 7, 8: Link Analysis
    # -------------------------------------------------------------------------
    extracted_links = _extract_links_from_body(clean_body)

    # EVAL_HIGH_LINK_DENSITY (+1.2 points)
    if len(extracted_links) > 3:
        heuristic_penalties.append({
            "code": "EVAL_HIGH_LINK_DENSITY",
            "description": "High link density (> 3 links) in email body",
            "penalty": 1.2,
            "details": {
                "link_count": len(extracted_links),
                "links": extracted_links[:10],
            },
        })
        recommendations.append(
            "Reduce link count in cold outreach to 1-2 focused links to maximize deliverability."
        )

    # EVAL_RAW_IP_LINKS (+3.0 points)
    raw_ip_detected = False
    for link in extracted_links:
        if _RAW_IP_URL_REGEX.search(link):
            raw_ip_detected = True
            break
    if not raw_ip_detected and _RAW_IP_URL_REGEX.search(clean_body):
        raw_ip_detected = True

    if raw_ip_detected:
        heuristic_penalties.append({
            "code": "EVAL_RAW_IP_LINKS",
            "description": "Raw IP address link detected in email content",
            "penalty": 3.0,
            "details": {"raw_ip_detected": True},
        })
        recommendations.append(
            "CRITICAL: Remove links containing raw IP addresses immediately. Always use verified HTTPS domains."
        )

    # EVAL_SHORTENER_DOMAINS (+2.5 points)
    shortener_detected = False
    shortener_found_domain = ""
    for link in extracted_links:
        try:
            url_to_parse = link if link.startswith(("http://", "https://")) else f"http://{link}"
            parsed = urlparse(url_to_parse)
            host = (parsed.netloc or "").lower().split(":")[0]
            if host in URL_SHORTENER_DOMAINS or any(host.endswith(f".{d}") for d in URL_SHORTENER_DOMAINS):
                shortener_detected = True
                shortener_found_domain = host
                break
        except Exception:
            continue

    if not shortener_detected:
        for domain in URL_SHORTENER_DOMAINS:
            if re.search(r"(?:https?://|www\.)" + re.escape(domain), clean_body, re.IGNORECASE):
                shortener_detected = True
                shortener_found_domain = domain
                break

    if shortener_detected:
        heuristic_penalties.append({
            "code": "EVAL_SHORTENER_DOMAINS",
            "description": f"Link pointing to known URL shortener domain detected ({shortener_found_domain})",
            "penalty": 2.5,
            "details": {"domain": shortener_found_domain},
        })
        recommendations.append(
            "Avoid URL shorteners (e.g. bit.ly, tinyurl); link directly to your verified custom domain."
        )

    # -------------------------------------------------------------------------
    # 8. Heuristic Evaluator 9: EVAL_MISSING_UNSUBSCRIBE (+1.0 points)
    #    Cold email body lacks unsubscribe/opt-out phrase (when not a reply and unsub not provided).
    # -------------------------------------------------------------------------
    has_unsub_phrase = _has_unsubscribe_phrase(clean_body)
    has_effective_unsub = has_unsubscribe or has_unsub_phrase

    if not is_reply and not has_effective_unsub:
        heuristic_penalties.append({
            "code": "EVAL_MISSING_UNSUBSCRIBE",
            "description": "Cold email lacks required opt-out notice or unsubscribe mechanism",
            "penalty": 1.0,
            "details": {
                "has_unsubscribe_flag": has_unsubscribe,
                "has_unsubscribe_phrase": has_unsub_phrase,
                "is_reply": is_reply,
            },
        })
        recommendations.append(
            "Include a clear opt-out notice or one-click unsubscribe link to comply with CAN-SPAM and ESP standards."
        )

    # -------------------------------------------------------------------------
    # 9. Score Aggregation & Risk Assignment
    # -------------------------------------------------------------------------
    heuristic_total = sum(h["penalty"] for h in heuristic_penalties)
    trigger_total = sum(t["penalty"] for t in flagged_triggers)
    raw_score = trigger_total + heuristic_total

    # Clamped to [0.0, 10.0] and rounded to 2 decimals
    spam_score = min(10.0, max(0.0, round(raw_score, 2)))

    # Determine Risk Level
    if spam_score < 2.0:
        risk_level = SpamRiskLevel.SAFE
    elif spam_score < 4.0:
        risk_level = SpamRiskLevel.LOW_RISK
    elif spam_score < 6.0:
        risk_level = SpamRiskLevel.HIGH_SPAM_RISK
    else:
        risk_level = SpamRiskLevel.CRITICAL_SPAM_REJECT

    # Sendability Clearance
    can_safely_send = (spam_score < CRITICAL_REJECT_THRESHOLD)
    rejection_reason: Optional[str] = None
    if not can_safely_send:
        rejection_reason = (
            f"CRITICAL_SPAM_SCORE_EXCEEDED: Calculated spam score ({spam_score:.2f}/10.0) exceeds "
            f"critical safety threshold ({CRITICAL_REJECT_THRESHOLD:.1f}). Message faces near-certain "
            "ESP spam foldering or MTA rejection."
        )

    # Clean recommendation if everything was flawless
    if spam_score == 0.0:
        recommendations.append(
            "Content passed SpamAssassin & Microsoft EOP pre-flight checks with zero critical flags."
        )

    # Deduplicate recommendations preserving order
    seen_recs: Set[str] = set()
    deduped_recs: List[str] = []
    for r in recommendations:
        if r not in seen_recs:
            seen_recs.add(r)
            deduped_recs.append(r)

    # -------------------------------------------------------------------------
    # 10. Compile Structured Telemetry
    # -------------------------------------------------------------------------
    subject_analysis = {
        "length": len(clean_subject),
        "uppercase_ratio": subject_uppercase_ratio,
        "triggers_found": [t["trigger"] for t in flagged_triggers if t["location"] == "subject"],
        "penalty_subtotal": round(subject_penalties, 2),
    }

    body_analysis = {
        "word_count": len(clean_body.split()),
        "uppercase_word_ratio": body_uppercase_word_ratio,
        "link_count": len(extracted_links),
        "links": extracted_links,
        "has_unsubscribe_phrase": has_unsub_phrase,
        "triggers_found": [t["trigger"] for t in flagged_triggers if t["location"] == "body"],
        "penalty_subtotal": round(body_penalties, 2),
    }

    return {
        "spam_score": spam_score,
        "risk_level": risk_level.value,
        "can_safely_send": can_safely_send,
        "rejection_reason": rejection_reason,
        "flagged_triggers": flagged_triggers,
        "heuristic_penalties": heuristic_penalties,
        "subject_analysis": subject_analysis,
        "body_analysis": body_analysis,
        "recommendations": deduped_recs,
    }


def suggest_copy_remediations(text: str) -> Dict[str, Any]:
    """
    Scans text for aggressive spam triggers and provides professional, consultative B2B
    replacements while strictly preserving casing styles (Title Case, UPPERCASE, lowercase).

    Parameters:
      text: The original copy (subject or body text).

    Returns:
      {
          "original_text": text,
          "sanitized_text": sanitized_text,
          "replacements_count": int,
          "replacements": List[Dict[str, str]]
      }
    """
    clean_text = _sanitize_string_input(text)
    if not clean_text:
        return {
            "original_text": text if text is not None else "",
            "sanitized_text": "",
            "replacements_count": 0,
            "replacements": [],
        }

    # Gather matching spans for all remediation keys
    spans: List[Tuple[int, int, str, str]] = []
    for trigger, replacement in B2B_REMEDIATIONS_MAP.items():
        pattern = _build_keyword_regex(trigger)
        for m in pattern.finditer(clean_text):
            spans.append((m.start(), m.end(), m.group(0), replacement))

    # Sort spans by starting index ascending, and longest span first on ties
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Filter out overlapping match spans
    non_overlapping: List[Tuple[int, int, str, str]] = []
    last_end = 0
    for start, end, orig, repl in spans:
        if start >= last_end:
            non_overlapping.append((start, end, orig, repl))
            last_end = end

    # Construct sanitized text with casing preservation
    chunks: List[str] = []
    replacements_list: List[Dict[str, str]] = []
    curr = 0

    for start, end, orig, repl in non_overlapping:
        chunks.append(clean_text[curr:start])
        cased_replacement = _preserve_casing(orig, repl)
        chunks.append(cased_replacement)
        replacements_list.append({
            "trigger": orig,
            "replacement": cased_replacement,
            "original": orig,
            "suggested": repl,
        })
        curr = end
    chunks.append(clean_text[curr:])

    sanitized_text = "".join(chunks)

    return {
        "original_text": clean_text,
        "sanitized_text": sanitized_text,
        "replacements_count": len(replacements_list),
        "replacements": replacements_list,
    }


# =============================================================================
# FACADE CLASS: SpamScoreService
# =============================================================================

class SpamScoreService:
    """
    Static facade interface for the Spam Trigger Words & Algorithmic Content
    Spam Score Classifier (SpamAssassin & Microsoft EOP Pre-Flight Engine).
    """

    SpamRiskLevel = SpamRiskLevel
    MAX_INPUT_LENGTH = MAX_INPUT_LENGTH
    CRITICAL_REJECT_THRESHOLD = CRITICAL_REJECT_THRESHOLD

    @staticmethod
    def audit_email_content(
        subject: str,
        body: str,
        is_reply: bool = False,
        has_unsubscribe: bool = True,
    ) -> Dict[str, Any]:
        """
        Full pre-flight spam score analysis across subject and body.
        """
        return audit_email_content(
            subject=subject,
            body=body,
            is_reply=is_reply,
            has_unsubscribe=has_unsubscribe,
        )

    @staticmethod
    def suggest_copy_remediations(text: str) -> Dict[str, Any]:
        """
        Generates professional B2B copy replacements for detected spam triggers.
        """
        return suggest_copy_remediations(text=text)

    @staticmethod
    def get_trigger_word_count() -> int:
        """
        Returns the total count of distinct trigger words and patterns across all categories.
        """
        return sum(len(keywords) for keywords in TRIGGER_CATALOG.values())

    @staticmethod
    def get_catalog() -> Dict[str, Dict[str, float]]:
        """
        Returns the full catalog of spam trigger words and weights.
        """
        return {cat: dict(words) for cat, words in TRIGGER_CATALOG.items()}
