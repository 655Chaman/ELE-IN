"""
email_shield_service.py — Cold Outreach Deliverability Shield, Spam Trap & Role Mailbox Inspector

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational): Comprehensive email syntax parsing, pristine spam-trap prefix matching,
    role-based department categorization, disposable domain identification, free webmail detection,
    and single/batch deliverability auditing.
  - Layer 1 (Environmental Failure Analysis): In-memory immutable frozensets preventing concurrency
    race conditions; strict batch size clamping (10,000 max) to prevent memory exhaustion; defensive
    handling of non-string/malformed batch inputs; bounded regex matching preventing ReDoS.
  - Layer 2 (Human Paranoia): Aggressive sanitization of human inputs (mailto: stripping, angle brackets,
    enclosing quotes, NUL-byte injection, whitespace, control characters); subaddressing/plus-tag
    normalization (e.g. abuse+test@domain -> abuse) to prevent evasion of spam-trap & role-based filters.
"""

from enum import Enum
import logging
import re
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class EmailClassification(str, Enum):
    CORPORATE = "CORPORATE"
    FREE_WEBMAIL = "FREE_WEBMAIL"
    ROLE_BASED = "ROLE_BASED"
    DISPOSABLE = "DISPOSABLE"
    SPAM_TRAP = "SPAM_TRAP"
    INVALID = "INVALID"


# RFC 5322 compliant simplified regex for standard email syntax
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Layer 1: Max batch size to prevent worker memory exhaustion (OOM)
MAX_BATCH_SIZE: int = 10000
MAX_BATCH_AUDIT_SIZE: int = MAX_BATCH_SIZE

# =============================================================================
# DATASETS (IMMUTABLE FROZENSETS FOR THREAD-SAFE CONCURRENT ACCESS)
# =============================================================================

SPAM_TRAP_PREFIXES: FrozenSet[str] = frozenset({
    "abuse",
    "postmaster",
    "spam",
    "spamtrap",
    "trap",
    "honeypot",
    "honey",
    "uce",
    "fbl",
    "noc",
    "security",
    "phish",
    "phishing",
    "anti-spam",
    "antispam",
    # Additional high-confidence spam trap / complaint prefixes
    "spamtrap01",
    "spamtrap02",
    "spam-trap",
    "spambox",
    "junk",
    "bounces",
    "mailer-daemon",
    "daemon",
    "root",
    "blackhole",
    "decoy",
    "sinkhole",
})

ROLE_BASED_PREFIXES: FrozenSet[str] = frozenset({
    "info",
    "admin",
    "administrator",
    "support",
    "help",
    "billing",
    "invoices",
    "accounting",
    "accounts",
    "sales",
    "marketing",
    "press",
    "media",
    "jobs",
    "careers",
    "hr",
    "office",
    "contact",
    "team",
    "general",
    "service",
    "legal",
    "compliance",
    "privacy",
    "operations",
    "ops",
    "devnull",
    "orders",
    "hello",
    "inquiries",
    "feedback",
    "reception",
    # Additional common role aliases
    "enquiries",
    "desk",
    "helpdesk",
    "it",
    "sysadmin",
    "webmaster",
    "hostmaster",
    "finance",
    "revenue",
})

ROLE_CATEGORY_MAP: Dict[str, str] = {
    "admin": "ADMINISTRATION",
    "administrator": "ADMINISTRATION",
    "sysadmin": "ADMINISTRATION",
    "webmaster": "ADMINISTRATION",
    "hostmaster": "ADMINISTRATION",
    "it": "ADMINISTRATION",
    "support": "SUPPORT",
    "help": "SUPPORT",
    "helpdesk": "SUPPORT",
    "desk": "SUPPORT",
    "service": "SUPPORT",
    "billing": "FINANCE_BILLING",
    "invoices": "FINANCE_BILLING",
    "accounting": "FINANCE_BILLING",
    "accounts": "FINANCE_BILLING",
    "finance": "FINANCE_BILLING",
    "revenue": "FINANCE_BILLING",
    "sales": "SALES",
    "orders": "SALES",
    "marketing": "MARKETING_PRESS",
    "press": "MARKETING_PRESS",
    "media": "MARKETING_PRESS",
    "jobs": "HUMAN_RESOURCES",
    "careers": "HUMAN_RESOURCES",
    "hr": "HUMAN_RESOURCES",
    "office": "OFFICE_MANAGEMENT",
    "reception": "OFFICE_MANAGEMENT",
    "contact": "GENERAL_INQUIRY",
    "info": "GENERAL_INQUIRY",
    "hello": "GENERAL_INQUIRY",
    "inquiries": "GENERAL_INQUIRY",
    "enquiries": "GENERAL_INQUIRY",
    "feedback": "GENERAL_INQUIRY",
    "general": "GENERAL_INQUIRY",
    "team": "GENERAL_INQUIRY",
    "legal": "LEGAL_COMPLIANCE",
    "compliance": "LEGAL_COMPLIANCE",
    "privacy": "LEGAL_COMPLIANCE",
    "operations": "OPERATIONS",
    "ops": "OPERATIONS",
    "devnull": "SYSTEM_DEVNULL",
}

ROLE_BASED_PREFIX_MAP: Dict[str, str] = ROLE_CATEGORY_MAP

DISPOSABLE_DOMAINS: FrozenSet[str] = frozenset({
    "0-mail.com",
    "0815.ru",
    "0clickemail.com",
    "10minutemail.be",
    "10minutemail.co.uk",
    "10minutemail.com",
    "10minutemail.de",
    "10minutemail.net",
    "10minutemail.org",
    "20minutemail.com",
    "anonymbox.com",
    "armyspy.com",
    "binkmail.com",
    "bobmail.info",
    "burneremail.net",
    "burnermail.io",
    "chammy.info",
    "cool.fr.nf",
    "courriel.fr.nf",
    "crazymail.com",
    "crazymailing.com",
    "cuvox.de",
    "dayrep.com",
    "deadaddress.com",
    "devnullmail.com",
    "discard.email",
    "discardmail.com",
    "disbox.net",
    "disposable-email.ml",
    "disposable.email",
    "disposablemail.com",
    "dispostable.com",
    "dropmail.me",
    "einrot.com",
    "email-temp.com",
    "emailfake.com",
    "emailfake.ml",
    "emailmiser.com",
    "emailondeck.com",
    "emailsensei.com",
    "emailtemporar.ro",
    "emailtemporario.com.br",
    "fakeinbox.com",
    "fakemail.net",
    "fakemail.org",
    "fakemailgenerator.com",
    "fakemailgenerator.net",
    "fastacash.com",
    "filzmail.com",
    "fleckens.hu",
    "generator.email",
    "getairmail.com",
    "getnada.com",
    "gishpuppy.com",
    "grr.la",
    "guerrillamail.biz",
    "guerrillamail.com",
    "guerrillamail.de",
    "guerrillamail.info",
    "guerrillamail.net",
    "guerrillamail.org",
    "guerrillamailblock.com",
    "gustr.com",
    "haltospam.com",
    "harakirimail.com",
    "hidebox.net",
    "inboxkitten.com",
    "incognitomail.org",
    "instantemailaddress.com",
    "jetable.org",
    "jourrapide.com",
    "kasmail.com",
    "mail-temporaire.fr",
    "mailcatch.com",
    "maildrop.cc",
    "mailinator.com",
    "mailnesia.com",
    "mailnull.com",
    "mailpoof.com",
    "mailsac.com",
    "mailslurp.com",
    "mailtothis.com",
    "mintemail.com",
    "mohmal.com",
    "moncourrier.fr.nf",
    "monemail.fr.nf",
    "monmail.fr.nf",
    "mytrashmail.com",
    "mytemp.email",
    "mytempemail.com",
    "nada.ltd",
    "noclickemail.com",
    "nomail.xl.cx",
    "nospam.ze.tc",
    "oneoffmail.com",
    "owlymail.com",
    "pookmail.com",
    "quickinbox.com",
    "rcpt.at",
    "rhyta.com",
    "safetymail.info",
    "sharklasers.com",
    "shortmail.net",
    "sofort-mail.de",
    "sogetthis.com",
    "spam4.me",
    "spamavert.com",
    "spambob.com",
    "spambog.com",
    "spambox.us",
    "spamcon.org",
    "spamevader.com",
    "spamfree24.org",
    "spamgourmet.com",
    "spamhole.com",
    "spaml.com",
    "spamspot.com",
    "superrito.com",
    "teleworm.us",
    "temp-mail.com",
    "temp-mail.io",
    "temp-mail.org",
    "tempail.com",
    "tempemail.co",
    "tempemail.net",
    "tempinbox.com",
    "tempinbox.net",
    "tempmail.com",
    "tempmail.net",
    "tempmailaddress.com",
    "tempmailer.com",
    "tempmailo.com",
    "temporary-mail.net",
    "temporarymail.com",
    "throwawayemailaddress.com",
    "throwawaymail.com",
    "tmail.com",
    "tmailor.com",
    "tmpmail.net",
    "tmpmail.org",
    "trash-mail.com",
    "trash-me.com",
    "trashcanmail.com",
    "trashmail.at",
    "trashmail.com",
    "trashmail.io",
    "trashmail.me",
    "trashmail.net",
    "trashmail.org",
    "urhen.com",
    "vmani.com",
    "warimpex.org",
    "wegwerfmail.de",
    "wegwerfmail.net",
    "wegwerfmail.org",
    "whyspam.me",
    "yopmail.com",
    "yopmail.fr",
    "yopmail.net",
    "zillamail.com",
    "zippymail.info",
    "zoemail.com",
})

FREE_WEBMAIL_DOMAINS: FrozenSet[str] = frozenset({
    # Primary Free Webmail Providers
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "ymail.com",
    "rocketmail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "aol.com",
    "aim.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
    "yandex.ru",
    "mail.ru",
    "tutanota.com",
    "fastmail.com",
    # Common International & Regional Free Webmail
    "yahoo.co.uk",
    "yahoo.fr",
    "yahoo.de",
    "yahoo.co.jp",
    "yahoo.es",
    "yahoo.it",
    "yahoo.ca",
    "yahoo.com.au",
    "yahoo.in",
    "hotmail.co.uk",
    "hotmail.fr",
    "hotmail.de",
    "hotmail.es",
    "hotmail.it",
    "outlook.fr",
    "outlook.de",
    "outlook.es",
    "gmx.de",
    "gmx.net",
    "gmx.at",
    "gmx.ch",
    "web.de",
    "libero.it",
    "virgilio.it",
    "orange.fr",
    "wanadoo.fr",
    "free.fr",
    "sfr.fr",
    "laposte.net",
    "t-online.de",
    "freenet.de",
    "comcast.net",
    "sbcglobal.net",
    "att.net",
    "verizon.net",
    "cox.net",
    "charter.net",
    "bell.net",
    "shaw.ca",
    "sympatico.ca",
    "rogers.com",
})


# =============================================================================
# CORE PARSING & INSPECTION LOGIC
# =============================================================================

def clean_and_parse_email(
    email: Optional[str],
    strip_subaddress: bool = True
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Paranoia Layer 0 & 2: Cleans, parses, and validates an email string.
    
    Operations:
      - Strips NUL bytes and ASCII control characters.
      - Extracts address from mailto: protocol or angle brackets (e.g. 'John <john@corp.com>').
      - Strips enclosing quotes and leading/trailing whitespace.
      - Enforces RFC 5321 length limits (total <= 254, local <= 64, domain <= 253).
      - Strips subaddressing / plus-tags for categorization (e.g. 'abuse+campaign@domain.com' -> 'abuse').
      - Validates syntax against RFC regex.
      
    Returns:
      (full_clean_email, local_part, domain) if valid.
      (None, None, None) if invalid.
    """
    if not email or not isinstance(email, str):
        return (None, None, None)

    # Layer 2: Strip NUL bytes and control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", email).strip()
    if not cleaned:
        return (None, None, None)

    # Layer 2: Extract from angle brackets if present e.g. "Jane Doe <jane@acme.com>"
    angle_match = re.search(r"<([^>]+)>", cleaned)
    if angle_match:
        cleaned = angle_match.group(1).strip()

    # Layer 2: Strip mailto: prefix
    if cleaned.lower().startswith("mailto:"):
        cleaned = cleaned[7:].strip()

    # Strip enclosing quotes and whitespace
    cleaned = cleaned.strip(" '\"`")
    if not cleaned or re.search(r"\s", cleaned):
        return (None, None, None)

    # RFC length check before regex
    if len(cleaned) < 3 or len(cleaned) > 254:
        return (None, None, None)

    # Exactly one @ character allowed
    if cleaned.count("@") != 1:
        return (None, None, None)

    raw_local, raw_domain = cleaned.split("@")
    raw_local = raw_local.strip()
    raw_domain = raw_domain.strip().lower().rstrip(".")

    if not raw_local or not raw_domain:
        return (None, None, None)

    # RFC 5321 length limits
    if len(raw_local) > 64 or len(raw_domain) > 253:
        return (None, None, None)

    # Dot checks: no leading/trailing dots, no double dots
    if raw_local.startswith(".") or raw_local.endswith("."):
        return (None, None, None)
    if ".." in raw_local or ".." in raw_domain:
        return (None, None, None)

    # Domain structure check
    if "." not in raw_domain:
        return (None, None, None)
    tld = raw_domain.split(".")[-1]
    if len(tld) < 2 or not tld.isalpha():
        return (None, None, None)

    # Validate against RFC email pattern
    normalized_for_regex = f"{raw_local}@{raw_domain}"
    if not _EMAIL_REGEX.match(normalized_for_regex):
        return (None, None, None)

    # Subaddressing / plus-tag normalization
    if strip_subaddress and "+" in raw_local:
        local_part_normalized = raw_local.lower().split("+")[0].strip()
    else:
        local_part_normalized = raw_local.lower()

    full_clean_email = f"{raw_local.lower()}@{raw_domain}"
    return (full_clean_email, local_part_normalized, raw_domain)


def is_spam_trap(email: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if the email address corresponds to a pristine spam trap, honeypot,
    or abuse reporting mailbox.
    
    Returns:
      (True, "PRISTINE_SPAM_TRAP_PREFIX") if matched.
      (False, None) otherwise.
    """
    if not email or not isinstance(email, str):
        return (False, None)

    full_clean, local_part, _ = clean_and_parse_email(email)
    if not local_part:
        # Fallback if raw prefix passed without domain
        if "@" not in email:
            candidate = email.strip().lower().split("+")[0].strip()
            if candidate in SPAM_TRAP_PREFIXES:
                return (True, "PRISTINE_SPAM_TRAP_PREFIX")
        return (False, None)

    clean_prefix = local_part.lower()
    if clean_prefix in SPAM_TRAP_PREFIXES:
        return (True, "PRISTINE_SPAM_TRAP_PREFIX")

    # Check primary token before common separators (e.g. abuse.campaign, spam-test, spamtrap12)
    token = re.split(r"[._-]", clean_prefix)[0].rstrip("0123456789")
    if token in SPAM_TRAP_PREFIXES:
        return (True, "PRISTINE_SPAM_TRAP_PREFIX")

    return (False, None)


def is_role_based_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if the email local-part matches a generic or department role-based mailbox
    (e.g., info@, admin@, billing@, sales@).
    
    Returns:
      (True, role_category) if matched.
      (False, None) otherwise.
    """
    if not email or not isinstance(email, str):
        return (False, None)

    full_clean, local_part, _ = clean_and_parse_email(email)
    if not local_part:
        # Fallback if raw prefix passed without domain
        if "@" not in email:
            candidate = email.strip().lower().split("+")[0].strip()
            if candidate in ROLE_BASED_PREFIXES:
                category = ROLE_CATEGORY_MAP.get(candidate, "ROLE_BASED_GENERAL")
                return (True, category)
        return (False, None)

    clean_prefix = local_part.lower()
    if clean_prefix in ROLE_BASED_PREFIXES:
        category = ROLE_CATEGORY_MAP.get(clean_prefix, "ROLE_BASED_GENERAL")
        return (True, category)

    # Check first token before delimiters (e.g. support-team, info.us, sales_west)
    token = re.split(r"[._-]", clean_prefix)[0]
    if token in ROLE_BASED_PREFIXES:
        category = ROLE_CATEGORY_MAP.get(token, "ROLE_BASED_GENERAL")
        return (True, category)

    return (False, None)


def is_disposable_email(email: str) -> bool:
    """
    Checks if the email domain (or any parent domain) is a known disposable or
    temporary mailbox provider.
    """
    if not email or not isinstance(email, str):
        return False

    if "@" in email:
        _, _, domain = clean_and_parse_email(email)
        if not domain:
            domain = email.split("@")[-1].strip().lower()
    else:
        domain = email.strip().lower()

    if not domain:
        return False

    domain = domain.rstrip(".")
    domain_parts = domain.split(".")

    # Check exact domain and all subdomains (e.g., sub.mailinator.com -> mailinator.com)
    for i in range(len(domain_parts) - 1):
        candidate = ".".join(domain_parts[i:])
        if candidate in DISPOSABLE_DOMAINS:
            return True

    return False


def is_free_webmail(email: str) -> bool:
    """
    Checks if the email domain matches a known free consumer webmail provider
    (e.g., gmail.com, yahoo.com, outlook.com).
    """
    if not email or not isinstance(email, str):
        return False

    if "@" in email:
        _, _, domain = clean_and_parse_email(email)
        if not domain:
            domain = email.split("@")[-1].strip().lower()
    else:
        domain = email.strip().lower()

    if not domain:
        return False

    domain = domain.rstrip(".")
    domain_parts = domain.split(".")

    # Check exact domain and subdomains
    for i in range(len(domain_parts) - 1):
        candidate = ".".join(domain_parts[i:])
        if candidate in FREE_WEBMAIL_DOMAINS:
            return True

    return False


# =============================================================================
# DELIVERABILITY AUDIT ENGINES (SINGLE & BATCH)
# =============================================================================

def audit_email_address(
    email: str,
    allow_role_based: bool = False
) -> Dict[str, Any]:
    """
    Evaluates an email address against syntax validity, spam trap hazards,
    role-based mailbox status, disposable domain registries, and webmail providers.
    
    Classification Precedence:
      1. INVALID: Malformed syntax or illegal characters.
      2. SPAM_TRAP: Pristine spam trap prefix -> CRITICAL risk, non-sendable.
      3. DISPOSABLE: Temporary domain -> HIGH risk, non-sendable.
      4. ROLE_BASED: Shared department inbox -> HIGH risk (or LOW if allow_role_based=True).
      5. FREE_WEBMAIL: Consumer email -> LOW risk, sendable.
      6. CORPORATE: Custom business domain -> SAFE, sendable.
    """
    full_clean, local_part, domain = clean_and_parse_email(email)
    if not full_clean:
        display_email = "" if email is None else str(email).strip()
        return {
            "email": display_email,
            "valid": False,
            "classification": EmailClassification.INVALID.value,
            "is_spam_trap": False,
            "is_role_based": False,
            "role_category": None,
            "is_disposable": False,
            "is_free_webmail": False,
            "is_corporate": False,
            "deliverability_risk": "HIGH_RISK",
            "can_safely_send": False,
            "rejection_reason": "INVALID_EMAIL_FORMAT",
            "recommendations": [
                "Correct email address syntax (must adhere to RFC 5322 format: local_part@domain.tld)"
            ],
        }

    is_trap, trap_reason = is_spam_trap(full_clean)
    is_role, role_cat = is_role_based_email(full_clean)
    is_disp = is_disposable_email(full_clean)
    is_free = is_free_webmail(full_clean)

    # Classification & Deliverability Risk Resolution
    if is_trap:
        classification = EmailClassification.SPAM_TRAP
        deliverability_risk = "CRITICAL_SPAM_TRAP"
        can_safely_send = False
        rejection_reason = trap_reason or "PRISTINE_SPAM_TRAP_PREFIX"
        recommendations = [
            "CRITICAL: Pristine spam trap detected. Immediately purge this address from campaigns to prevent domain-wide blacklisting."
        ]
    elif is_disp:
        classification = EmailClassification.DISPOSABLE
        deliverability_risk = "HIGH_RISK"
        can_safely_send = False
        rejection_reason = "DISPOSABLE_EMAIL_DOMAIN"
        recommendations = [
            "Disposable/ephemeral domain detected. Discard lead to protect sender domain reputation from hard bounces."
        ]
    elif is_role:
        classification = EmailClassification.ROLE_BASED
        if allow_role_based:
            deliverability_risk = "LOW_RISK"
            can_safely_send = True
            rejection_reason = None
            recommendations = [
                f"Role-based mailbox ({role_cat or 'GENERAL'}) permitted by policy. Proceed with targeted B2B messaging."
            ]
        else:
            deliverability_risk = "HIGH_RISK"
            can_safely_send = False
            rejection_reason = "ROLE_BASED_MAILBOX_DETECTED"
            recommendations = [
                f"Role-based mailbox ({role_cat or 'GENERAL'}) rejected. Enable allow_role_based=True if reaching department inboxes is intended."
            ]
    elif is_free:
        classification = EmailClassification.FREE_WEBMAIL
        deliverability_risk = "LOW_RISK"
        can_safely_send = True
        rejection_reason = None
        recommendations = [
            "Free consumer webmail address detected. Confirm B2B suitability prior to cold sequencing."
        ]
    else:
        classification = EmailClassification.CORPORATE
        deliverability_risk = "SAFE"
        can_safely_send = True
        rejection_reason = None
        recommendations = [
            "Verified corporate domain address. Optimal cold outreach deliverability profile."
        ]

    is_corp = (classification == EmailClassification.CORPORATE)

    return {
        "email": full_clean,
        "valid": True,
        "classification": classification.value,
        "is_spam_trap": is_trap,
        "is_role_based": is_role,
        "role_category": role_cat if is_role else None,
        "is_disposable": is_disp,
        "is_free_webmail": is_free,
        "is_corporate": is_corp,
        "deliverability_risk": deliverability_risk,
        "can_safely_send": can_safely_send,
        "rejection_reason": rejection_reason,
        "recommendations": recommendations,
    }


def audit_email_batch(
    emails: List[str],
    allow_role_based: bool = False
) -> Dict[str, Any]:
    """
    Paranoia Layer 1 & 2: Batch audits a collection of emails up to MAX_BATCH_SIZE (10,000).
    Returns individual audit records and aggregate hygiene statistics.
    """
    if emails is None or isinstance(emails, (str, bytes)):
        raw_list: List[Any] = []
    elif isinstance(emails, list):
        raw_list = emails
    else:
        try:
            raw_list = list(emails)
        except Exception:
            raw_list = []

    batch_clamped = len(raw_list) > MAX_BATCH_SIZE
    processed_emails = raw_list[:MAX_BATCH_SIZE]

    total_emails = len(processed_emails)
    safe_count = 0
    corporate_count = 0
    free_webmail_count = 0
    role_based_count = 0
    disposable_count = 0
    spam_trap_count = 0
    invalid_count = 0

    results: List[Dict[str, Any]] = []

    for item in processed_emails:
        res = audit_email_address(item, allow_role_based=allow_role_based)
        results.append(res)

        if res["can_safely_send"]:
            safe_count += 1

        cls_val = res["classification"]
        if cls_val == EmailClassification.CORPORATE.value:
            corporate_count += 1
        elif cls_val == EmailClassification.FREE_WEBMAIL.value:
            free_webmail_count += 1
        elif cls_val == EmailClassification.ROLE_BASED.value:
            role_based_count += 1
        elif cls_val == EmailClassification.DISPOSABLE.value:
            disposable_count += 1
        elif cls_val == EmailClassification.SPAM_TRAP.value:
            spam_trap_count += 1
        elif cls_val == EmailClassification.INVALID.value:
            invalid_count += 1

    safe_to_send_ratio_pct = (
        round((safe_count / total_emails) * 100.0, 2) if total_emails > 0 else 0.0
    )

    return {
        "total_emails": total_emails,
        "safe_count": safe_count,
        "corporate_count": corporate_count,
        "free_webmail_count": free_webmail_count,
        "role_based_count": role_based_count,
        "disposable_count": disposable_count,
        "spam_trap_count": spam_trap_count,
        "invalid_count": invalid_count,
        "safe_to_send_ratio_pct": safe_to_send_ratio_pct,
        "results": results,
        "allow_role_based": allow_role_based,
        "batch_clamped": batch_clamped,
    }


# =============================================================================
# CLASS-BASED INTERFACE (FOR OOP-STYLE CALLERS)
# =============================================================================

class EmailShieldService:
    """
    Object-oriented facade exposing deliverability shield inspection,
    spam trap protection, role mailbox classification, and batch auditing.
    """
    EmailClassification = EmailClassification
    SPAM_TRAP_PREFIXES = SPAM_TRAP_PREFIXES
    ROLE_BASED_PREFIXES = ROLE_BASED_PREFIXES
    DISPOSABLE_DOMAINS = DISPOSABLE_DOMAINS
    FREE_WEBMAIL_DOMAINS = FREE_WEBMAIL_DOMAINS
    ROLE_CATEGORY_MAP = ROLE_CATEGORY_MAP
    ROLE_BASED_PREFIX_MAP = ROLE_CATEGORY_MAP
    MAX_BATCH_SIZE = MAX_BATCH_SIZE
    MAX_BATCH_AUDIT_SIZE = MAX_BATCH_SIZE

    @staticmethod
    def clean_and_parse_email(
        email: Optional[str],
        strip_subaddress: bool = True
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        return clean_and_parse_email(email, strip_subaddress=strip_subaddress)

    @staticmethod
    def is_spam_trap(email: str) -> Tuple[bool, Optional[str]]:
        return is_spam_trap(email)

    @staticmethod
    def is_role_based_email(email: str) -> Tuple[bool, Optional[str]]:
        return is_role_based_email(email)

    @staticmethod
    def is_disposable_email(email: str) -> bool:
        return is_disposable_email(email)

    @staticmethod
    def is_free_webmail(email: str) -> bool:
        return is_free_webmail(email)

    @staticmethod
    def audit_email_address(
        email: str,
        allow_role_based: bool = False
    ) -> Dict[str, Any]:
        return audit_email_address(email, allow_role_based=allow_role_based)

    @staticmethod
    def audit_email_batch(
        emails: List[str],
        allow_role_based: bool = False
    ) -> Dict[str, Any]:
        return audit_email_batch(emails, allow_role_based=allow_role_based)

