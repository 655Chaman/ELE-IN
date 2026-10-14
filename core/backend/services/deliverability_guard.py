"""
deliverability_guard.py — Outbox Cold-Email Deliverability Guard, SPF/DKIM/DMARC Inspector & Bounce Tripwire
Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: SPF, DKIM, DMARC, and Custom Tracking CNAME verification; Bounce & Spam complaint tripwires; safe tracking link rewriting.
  - Layer 1: DNS timeout resilience, small-sample false-positive protection, unverified SSL link-rewrite bypass.
  - Layer 2: Domain input sanitization, SSRF/internal-host rejection, multiple-SPF RFC 7208 collision detection, threshold clamping.
"""

import logging
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    import dns.resolver
    HAS_DNS_RESOLVER = True
except ImportError:
    dns = None
    HAS_DNS_RESOLVER = False

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_BOUNCE_THRESHOLD_PCT = 2.5
DEFAULT_SPAM_THRESHOLD_PCT = 0.1
DEFAULT_MIN_SAMPLE_SIZE = 20
ABSOLUTE_BOUNCE_FLOOR = 5
ABSOLUTE_SPAM_FLOOR = 2
DEFAULT_QUARANTINE_HOURS = 24

_FORBIDDEN_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",
    "::1",
}

_DOMAIN_REGEX = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)


def sanitize_domain_input(raw_domain: Optional[str]) -> Optional[str]:
    """
    Paranoia Layer 2: Sanitizes human-entered domain strings.
    Strips protocols, paths, query strings, ports, leading 'www.', and whitespace.
    Blocks localhost, private IPs, and SSRF targets.
    """
    if not raw_domain or not isinstance(raw_domain, str):
        return None

    cleaned = raw_domain.strip().lower()
    if not cleaned:
        return None

    # If user pasted an email address (e.g., "sales@acme.com"), extract domain part
    if "@" in cleaned and "://" not in cleaned:
        cleaned = cleaned.split("@")[-1].strip()

    # Strip protocol
    cleaned = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", cleaned)
    # Strip path, query, fragment
    cleaned = cleaned.split("/")[0].split("?")[0].split("#")[0]
    # Strip userinfo if present
    if "@" in cleaned:
        cleaned = cleaned.split("@")[-1]
    # Strip port
    cleaned = cleaned.split(":")[0].strip(".")

    # Strip leading www.
    if cleaned.startswith("www.") and cleaned.count(".") >= 2:
        cleaned = cleaned[4:]

    if not cleaned or cleaned in _FORBIDDEN_HOSTS:
        return None

    # Block private IP literals and internal TLDs
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", cleaned):
        return None
    if cleaned.endswith((".local", ".internal", ".localhost", ".lan", ".arpa")):
        return None

    if not _DOMAIN_REGEX.match(cleaned):
        return None

    return cleaned


def _lookup_txt_records(qname: str, timeout: float = 2.5) -> List[str]:
    """Layer 1: Safe DNS TXT lookup with strict timeout and fallback."""
    if not HAS_DNS_RESOLVER or not dns:
        return []
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answers = resolver.resolve(qname, "TXT")
        records = []
        for rdata in answers:
            txt_parts = [
                part.decode("utf-8", errors="ignore") if isinstance(part, bytes) else str(part)
                for part in getattr(rdata, "strings", [])
            ]
            if txt_parts:
                records.append("".join(txt_parts))
            else:
                records.append(rdata.to_text().strip('"'))
        return records
    except Exception as exc:
        logger.debug(f"[DeliverabilityGuard] TXT lookup failed for {qname}: {exc}")
        return []


def _lookup_cname_record(qname: str, timeout: float = 2.5) -> Optional[str]:
    """Layer 1: Safe DNS CNAME lookup with strict timeout and fallback."""
    if not HAS_DNS_RESOLVER or not dns:
        return None
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answers = resolver.resolve(qname, "CNAME")
        for rdata in answers:
            target = str(getattr(rdata, "target", rdata.to_text())).rstrip(".").lower()
            if target:
                return target
    except Exception as exc:
        logger.debug(f"[DeliverabilityGuard] CNAME lookup failed for {qname}: {exc}")
    return None


def verify_domain_dns_health(
    domain: str,
    tracking_subdomain: str = "track",
    expected_cname_target: str = "track.elein.ai",
    dkim_selector: str = "elein",
    mock_records: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Inspects SPF, DKIM, DMARC, and Custom Tracking CNAME records.
    Detects RFC 7208 multiple-SPF collisions, permissive '+all' SPFconfigurations,
    and un-enforced DMARC 'p=none' policies.
    """
    clean_domain = sanitize_domain_input(domain)
    if not clean_domain:
        return {
            "valid": False,
            "domain": domain,
            "health_status": "INVALID_DOMAIN",
            "deliverability_score": 0,
            "can_send_safely": False,
            "errors": ["Invalid or unsafe domain name provided."],
            "warnings": [],
            "records": {},
        }

    # Sanitize selector and tracking subdomain
    clean_sub = re.sub(r"[^a-z0-9-]", "", str(tracking_subdomain or "track").lower().strip()) or "track"
    clean_selector = re.sub(r"[^a-z0-9._-]", "", str(dkim_selector or "elein").lower().strip()) or "elein"
    clean_cname_target = (expected_cname_target or "track.elein.ai").strip().rstrip(".").lower()

    if mock_records is not None and isinstance(mock_records, dict):
        root_txt = list(mock_records.get("spf", mock_records.get("root_txt", [])))
        dkim_txt = list(mock_records.get("dkim", []))
        dmarc_txt = list(mock_records.get("dmarc", []))
        cname_val = mock_records.get("cname")
        if isinstance(cname_val, str):
            cname_val = cname_val.strip().rstrip(".").lower()
        ssl_verified = bool(mock_records.get("ssl_verified", bool(cname_val == clean_cname_target)))
    else:
        root_txt = _lookup_txt_records(clean_domain)
        dkim_txt = _lookup_txt_records(f"{clean_selector}._domainkey.{clean_domain}")
        dmarc_txt = _lookup_txt_records(f"_dmarc.{clean_domain}")
        cname_val = _lookup_cname_record(f"{clean_sub}.{clean_domain}")
        ssl_verified = bool(cname_val == clean_cname_target)

    errors: List[str] = []
    warnings: List[str] = []
    score = 0

    # 1. Evaluate SPF (30 points)
    spf_matches = [r.strip() for r in root_txt if isinstance(r, str) and r.strip().lower().startswith("v=spf1")]
    spf_valid = False
    if len(spf_matches) == 0:
        errors.append("Missing SPF TXT record (v=spf1) on root domain.")
    elif len(spf_matches) > 1:
        # Layer 2 Paranoia: Multiple SPF records violate RFC 7208 and cause PermError!
        errors.append(
            f"Multiple SPF records detected ({len(spf_matches)} found). RFC 7208 requires merging into a single v=spf1 record."
        )
    else:
        spf_record = spf_matches[0]
        if "+all" in spf_record.lower():
            errors.append("SPF record contains '+all', which allows any server on the internet to spoof your domain.")
        else:
            spf_valid = True
            score += 30
            if "~all" not in spf_record.lower() and "-all" not in spf_record.lower():
                warnings.append("SPF record does not end with '~all' or '-all' enforcement mechanism.")

    # 2. Evaluate DKIM (30 points)
    dkim_matches = [
        r.strip() for r in dkim_txt
        if isinstance(r, str) and ("v=dkim1" in r.lower() or "k=rsa" in r.lower() or "p=" in r.lower())
    ]
    dkim_valid = False
    if not dkim_matches:
        errors.append(f"Missing DKIM TXT record at {clean_selector}._domainkey.{clean_domain}.")
    else:
        dkim_rec = dkim_matches[0]
        # Ensure public key p= is non-empty (empty p= means revoked key per RFC 6376)
        p_match = re.search(r"p=([A-Za-z0-9+/=]+)", dkim_rec)
        if not p_match or len(p_match.group(1)) < 16:
            errors.append(f"DKIM key at {clean_selector}._domainkey.{clean_domain} has an empty or revoked public key (p=).")
        else:
            dkim_valid = True
            score += 30

    # 3. Evaluate DMARC (25 points)
    dmarc_matches = [r.strip() for r in dmarc_txt if isinstance(r, str) and r.strip().lower().startswith("v=dmarc1")]
    dmarc_valid = False
    dmarc_policy = "missing"
    if not dmarc_matches:
        errors.append(f"Missing DMARC record at _dmarc.{clean_domain}.")
    else:
        dmarc_rec = dmarc_matches[0]
        p_tag = re.search(r"\bp\s*=\s*(none|quarantine|reject)\b", dmarc_rec, re.IGNORECASE)
        if not p_tag:
            errors.append("DMARC record is missing required policy tag (p=none|quarantine|reject).")
        else:
            dmarc_valid = True
            dmarc_policy = p_tag.group(1).lower()
            if dmarc_policy in ("quarantine", "reject"):
                score += 25
            else:
                score += 15
                warnings.append("DMARC policy is set to 'p=none' (monitoring only). Upgrade to 'p=quarantine' or 'p=reject' for inbox protection.")

    # 4. Evaluate Custom Tracking Domain CNAME (15 points)
    tracking_fqdn = f"{clean_sub}.{clean_domain}"
    cname_valid = bool(cname_val and cname_val == clean_cname_target)
    if cname_valid:
        score += 15
    else:
        warnings.append(
            f"Custom tracking CNAME ({tracking_fqdn} -> {clean_cname_target}) is not verified. Links will use direct unrewritten URLs to avoid SSL errors."
        )

    score = max(0, min(100, score))
    if score >= 85 and spf_valid and dkim_valid and dmarc_valid:
        health_status = "HEALTHY"
    elif score >= 60 and spf_valid and dkim_valid:
        health_status = "WARNING"
    else:
        health_status = "CRITICAL"

    return {
        "valid": True,
        "domain": clean_domain,
        "tracking_fqdn": tracking_fqdn,
        "health_status": health_status,
        "deliverability_score": score,
        "can_send_safely": bool(spf_valid and dkim_valid),
        "ssl_tracking_ready": bool(cname_valid and ssl_verified),
        "errors": errors,
        "warnings": warnings,
        "records": {
            "spf": {"valid": spf_valid, "found": spf_matches},
            "dkim": {"valid": dkim_valid, "selector": clean_selector, "found": dkim_matches},
            "dmarc": {"valid": dmarc_valid, "policy": dmarc_policy, "found": dmarc_matches},
            "tracking_cname": {
                "valid": cname_valid,
                "host": tracking_fqdn,
                "expected_target": clean_cname_target,
                "actual_target": cname_val,
                "ssl_verified": bool(cname_valid and ssl_verified),
            },
        },
    }


def evaluate_inbox_deliverability_tripwire(
    inbox_stats: Dict[str, Any],
    bounce_threshold_pct: float = DEFAULT_BOUNCE_THRESHOLD_PCT,
    spam_threshold_pct: float = DEFAULT_SPAM_THRESHOLD_PCT,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    cooldown_hours: int = DEFAULT_QUARANTINE_HOURS,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Evaluates an inbox's bounce and spam complaint rates
    against safety tripwires.
    - Clamps human-configured thresholds to safe operational bounds.
    - Applies sample-size floor to prevent false-positive quarantine on the first few emails,
      while enforcing an absolute hard-bounce/spam ceiling.
    """
    if not isinstance(inbox_stats, dict):
        inbox_stats = {}

    # Layer 2 Paranoia: Clamp thresholds to prevent 0% instant-quarantine or 100% disabled guard
    safe_bounce_threshold = max(0.5, min(25.0, float(bounce_threshold_pct or DEFAULT_BOUNCE_THRESHOLD_PCT)))
    safe_spam_threshold = max(0.01, min(5.0, float(spam_threshold_pct or DEFAULT_SPAM_THRESHOLD_PCT)))
    safe_min_sample = max(5, min(500, int(min_sample_size or DEFAULT_MIN_SAMPLE_SIZE)))
    safe_cooldown = max(1, min(168, int(cooldown_hours or DEFAULT_QUARANTINE_HOURS)))

    try:
        sent_count = max(0, int(inbox_stats.get("sent_count", inbox_stats.get("emails_sent", 0)) or 0))
    except (ValueError, TypeError):
        sent_count = 0

    try:
        bounce_count = max(0, int(inbox_stats.get("bounce_count", inbox_stats.get("bounces", 0)) or 0))
    except (ValueError, TypeError):
        bounce_count = 0

    try:
        spam_count = max(0, int(inbox_stats.get("spam_complaint_count", inbox_stats.get("spam_complaints", 0)) or 0))
    except (ValueError, TypeError):
        spam_count = 0

    # Ensure bounce_count / spam_count don't exceed sent_count when calculating percentage if sent_count > 0
    denominator = max(sent_count, bounce_count, spam_count)
    bounce_rate_pct = round((bounce_count / denominator) * 100.0, 2) if denominator > 0 else 0.0
    spam_rate_pct = round((spam_count / denominator) * 100.0, 3) if denominator > 0 else 0.0

    sample_reached = denominator >= safe_min_sample
    reasons: List[str] = []

    # Check Spam Complaint Tripwire (0.1% default, or absolute >= 2 spam complaints)
    if (sample_reached and spam_rate_pct >= safe_spam_threshold) or spam_count >= ABSOLUTE_SPAM_FLOOR:
        reasons.append(
            f"SPAM_COMPLAINT_THRESHOLD_EXCEEDED ({spam_rate_pct}% >= {safe_spam_threshold}%, count={spam_count})"
        )

    # Check Bounce Rate Tripwire (2.5% default, or absolute >= 5 bounces when below sample size)
    if (sample_reached and bounce_rate_pct >= safe_bounce_threshold) or (
        not sample_reached and bounce_count >= ABSOLUTE_BOUNCE_FLOOR
    ):
        reasons.append(
            f"BOUNCE_RATE_EXCEEDED ({bounce_rate_pct}% >= {safe_bounce_threshold}%, count={bounce_count}/{denominator})"
        )

    should_quarantine = len(reasons) > 0
    now_utc = datetime.now(timezone.utc)
    quarantined_until = (now_utc + timedelta(hours=safe_cooldown)).isoformat() if should_quarantine else None

    return {
        "should_quarantine": should_quarantine,
        "recommended_status": "QUARANTINED" if should_quarantine else "ACTIVE",
        "quarantine_reason": "; ".join(reasons) if reasons else None,
        "quarantined_until": quarantined_until,
        "metrics": {
            "sent_count": denominator,
            "bounce_count": bounce_count,
            "spam_complaint_count": spam_count,
            "bounce_rate_pct": bounce_rate_pct,
            "spam_rate_pct": spam_rate_pct,
            "sample_size_reached": sample_reached,
            "applied_bounce_threshold_pct": safe_bounce_threshold,
            "applied_spam_threshold_pct": safe_spam_threshold,
        },
    }


def rewrite_tracking_links(
    body: str,
    tracking_domain: Optional[str],
    email_id: str,
    workspace_id: str,
    ssl_verified: bool = True,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Rewrites http/https links in email body to use the workspace's
    verified custom tracking domain.
    - Layer 1 Fallback: If ssl_verified is False or tracking_domain is invalid/unsafe,
      returns the original body untouched so recipients NEVER hit SSL certificate errors.
    - Layer 2 Safety: Never rewrites mailto:, tel:, or unsubscribe links that already point to tracking domain.
    """
    if not body or not isinstance(body, str):
        return {"body": "", "rewritten_count": 0, "tracking_applied": False}

    clean_tracking = sanitize_domain_input(tracking_domain)
    if not clean_tracking or not ssl_verified or not email_id:
        return {
            "body": body,
            "rewritten_count": 0,
            "tracking_applied": False,
            "fallback_reason": "SSL_OR_DOMAIN_UNVERIFIED" if not ssl_verified else "NO_VALID_TRACKING_DOMAIN",
        }

    url_pattern = re.compile(r"(https?://[^\s\"'<>)\]]+)", re.IGNORECASE)
    rewritten_count = 0

    def _replace_match(match: re.Match) -> str:
        nonlocal rewritten_count
        original_url = match.group(1)
        # Strip trailing punctuation that is part of prose (e.g. period or comma at end of sentence)
        trailing = ""
        while original_url and original_url[-1] in (".", ",", ";", "!"):
            trailing = original_url[-1] + trailing
            original_url = original_url[:-1]

        try:
            parsed = urllib.parse.urlparse(original_url)
            host = (parsed.hostname or "").lower()
            # Do not double-wrap links already pointing to the tracking domain
            if not host or host == clean_tracking or host.endswith(f".{clean_tracking}"):
                return match.group(1)
        except Exception:
            return match.group(1)

        encoded_target = urllib.parse.quote(original_url, safe="")
        safe_email_id = urllib.parse.quote(str(email_id).strip(), safe="")
        safe_ws_id = urllib.parse.quote(str(workspace_id or "").strip(), safe="")
        tracked_url = f"https://{clean_tracking}/t/c/{safe_email_id}?u={encoded_target}&w={safe_ws_id}"
        rewritten_count += 1
        return tracked_url + trailing

    updated_body = url_pattern.sub(_replace_match, body)
    return {
        "body": updated_body,
        "rewritten_count": rewritten_count,
        "tracking_applied": rewritten_count > 0,
        "tracking_domain": clean_tracking,
    }
