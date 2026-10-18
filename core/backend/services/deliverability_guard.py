"""
deliverability_guard.py — Outbox Cold-Email Deliverability Guard, SPF/DKIM/DMARC Inspector & Bounce Tripwire
Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: SPF, DKIM, DMARC, and Custom Tracking CNAME verification; Bounce & Spam complaint tripwires; safe tracking link rewriting.
  - Layer 1: DNS timeout resilience, small-sample false-positive protection, unverified SSL link-rewrite bypass.
  - Layer 2: Domain input sanitization, SSRF/internal-host rejection, multiple-SPF RFC 7208 collision detection, threshold clamping.
"""

import logging
import re
import socket
import ssl
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


def verify_ssl_handshake(
    hostname: str,
    port: int = 443,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: TLS/SSL Handshake & Certificate Verification Engine.
    - Layer 2: Sanitizes hostname against SSRF, internal hosts, local IPs, and malformed inputs.
               Returns {"ssl_valid": False, "error": "FORBIDDEN_OR_INVALID_HOST"} if invalid.
    - Layer 0: Establishes TLS socket, retrieves peer certificate, verifies expiration and SAN list.
    - Layer 1: Gracefully catches verification errors, timeouts, connection refused, and gaierrors without crashing.
    """
    clean_host = sanitize_domain_input(hostname)
    if not clean_host:
        return {
            "ssl_valid": False,
            "status": "FORBIDDEN_OR_INVALID_HOST",
            "error": "FORBIDDEN_OR_INVALID_HOST",
            "hostname": hostname,
        }

    try:
        context = ssl.create_default_context()
        with socket.create_connection((clean_host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=clean_host) as ssock:
                cert = ssock.getpeercert()

        if not cert:
            return {
                "ssl_valid": False,
                "status": "NO_CERTIFICATE_FOUND",
                "error": "No peer certificate returned by TLS handshake",
                "hostname": clean_host,
            }

        # Extract Subject Common Name (CN)
        subject_cn = None
        for rdn in cert.get("subject", ()):
            for key, value in rdn:
                if key == "commonName":
                    subject_cn = value
                    break

        # Extract Issuer dict/tuple
        issuer = cert.get("issuer")

        # Extract Subject Alternative Names (SANs)
        san_list = [val for typ, val in cert.get("subjectAltName", []) if typ == "DNS"]

        # Parse expiration date
        not_after_str = cert.get("notAfter")
        if not not_after_str:
            return {
                "ssl_valid": False,
                "status": "MISSING_EXPIRATION_DATE",
                "error": "Certificate missing notAfter expiration date",
                "hostname": clean_host,
            }

        try:
            exp_ts = ssl.cert_time_to_seconds(not_after_str)
            exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        except Exception:
            exp_dt = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        days_until_expiry = (exp_dt - now_utc).days

        if days_until_expiry <= 0:
            return {
                "ssl_valid": False,
                "status": "CERTIFICATE_EXPIRED",
                "hostname": clean_host,
                "days_until_expiry": days_until_expiry,
                "expires_at": exp_dt.isoformat(),
                "error": f"Certificate expired {abs(days_until_expiry)} days ago",
                "issuer": issuer,
                "subject": subject_cn or clean_host,
                "alt_names": san_list,
                "san_list": san_list,
            }

        return {
            "ssl_valid": True,
            "status": "ACTIVE_VALID",
            "hostname": clean_host,
            "days_until_expiry": days_until_expiry,
            "expires_at": exp_dt.isoformat(),
            "san_list": san_list,
            "alt_names": san_list,
            "issuer": issuer,
            "subject": subject_cn or clean_host,
        }

    except ssl.SSLCertVerificationError as e:
        return {
            "ssl_valid": False,
            "status": "SSL_CERT_VERIFICATION_FAILED",
            "error": str(e),
            "hostname": clean_host,
        }
    except ssl.SSLError as e:
        return {
            "ssl_valid": False,
            "status": "SSL_HANDSHAKE_ERROR",
            "error": str(e),
            "hostname": clean_host,
        }
    except (socket.timeout, TimeoutError) as e:
        return {
            "ssl_valid": False,
            "status": "CONNECTION_TIMEOUT",
            "error": "Connection timed out",
            "hostname": clean_host,
        }
    except ConnectionRefusedError as e:
        return {
            "ssl_valid": False,
            "status": "CONNECTION_REFUSED",
            "error": "Port 443 refused",
            "hostname": clean_host,
        }
    except (socket.gaierror, Exception) as e:
        return {
            "ssl_valid": False,
            "status": "SSL_CHECK_FAILED",
            "error": str(e),
            "hostname": clean_host,
        }


def verify_custom_tracking_domain(
    tracking_fqdn: str,
    expected_cname_target: str = "track.elein.ai",
    check_live_ssl: bool = True,
    timeout: float = 3.0,
    mock_cname: Optional[str] = None,
    mock_ssl_valid: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Custom Tracking Domain CNAME & SSL Handshake Verification.
    - Layer 0: Checks DNS CNAME pointing to expected_cname_target.
    - Layer 1: Validates live SSL handshake if CNAME matches, handling pending provisioning gracefully.
    - Layer 2: Sanitizes tracking_fqdn, prevents SSRF, and respects mock overrides for deterministic testability.
    """
    clean_fqdn = sanitize_domain_input(tracking_fqdn)
    clean_expected = (expected_cname_target or "track.elein.ai").strip().rstrip(".").lower()

    if not clean_fqdn:
        return {
            "valid": False,
            "status": "CNAME_MISSING_OR_MISMATCH",
            "cname_target": None,
            "expected_cname": clean_expected,
            "ssl_verified": False,
            "can_track_safely": False,
            "error": "FORBIDDEN_OR_INVALID_HOST",
        }

    # Resolve CNAME target
    if mock_cname is not None:
        cname_target = mock_cname.strip().rstrip(".").lower() if mock_cname else None
    else:
        raw_target = _lookup_cname_record(clean_fqdn, timeout=timeout)
        cname_target = raw_target.strip().rstrip(".").lower() if raw_target else None

    # Check if CNAME matches expected target
    cname_matches = bool(cname_target and cname_target == clean_expected)
    if not cname_matches:
        return {
            "valid": False,
            "status": "CNAME_MISSING_OR_MISMATCH",
            "cname_target": cname_target,
            "expected_cname": clean_expected,
            "ssl_verified": False,
            "can_track_safely": False,
        }

    # CNAME is valid: check live SSL
    if check_live_ssl:
        if mock_ssl_valid is not None:
            if mock_ssl_valid:
                ssl_res = {
                    "ssl_valid": True,
                    "status": "ACTIVE_VALID",
                    "hostname": clean_fqdn,
                    "days_until_expiry": 90,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
                    "san_list": [clean_fqdn],
                }
            else:
                ssl_res = {
                    "ssl_valid": False,
                    "status": "SSL_CERT_VERIFICATION_FAILED",
                    "error": "SSL certificate verification failed",
                    "hostname": clean_fqdn,
                }
        else:
            ssl_res = verify_ssl_handshake(clean_fqdn, timeout=timeout)

        if ssl_res.get("ssl_valid"):
            return {
                "valid": True,
                "status": "VERIFIED_ACTIVE",
                "cname_target": cname_target,
                "ssl_verified": True,
                "can_track_safely": True,
                "ssl_details": ssl_res,
            }
        else:
            return {
                "valid": False,
                "status": "SSL_PENDING_PROVISIONING",
                "cname_target": cname_target,
                "ssl_verified": False,
                "can_track_safely": False,
                "ssl_error": ssl_res.get("error"),
                "action_required": "CNAME is configured, but SSL certificate is still provisioning or invalid. Tracking links will remain plain until SSL is active.",
                "ssl_details": ssl_res,
            }
    else:
        return {
            "valid": True,
            "status": "CNAME_ONLY",
            "cname_target": cname_target,
            "ssl_verified": False,
            "can_track_safely": False,
        }


def verify_domain_dns_health(
    domain: str,
    tracking_subdomain: str = "track",
    expected_cname_target: str = "track.elein.ai",
    dkim_selector: str = "elein",
    mock_records: Optional[Dict[str, Any]] = None,
    check_live_ssl: bool = True,
    mock_ssl_valid: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Inspects SPF, DKIM, DMARC, and Custom Tracking CNAME records with live SSL handshake.
    Detects RFC 7208 multiple-SPF collisions, permissive '+all' SPF configurations,
    un-enforced DMARC 'p=none' policies, and unprovisioned or expired SSL certificates.
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

    # Authentic DNS resolution via dnspython
    root_txt = _lookup_txt_records(clean_domain)
    dkim_txt = _lookup_txt_records(f"{clean_selector}._domainkey.{clean_domain}")
    dmarc_txt = _lookup_txt_records(f"_dmarc.{clean_domain}")

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

    # 4. Evaluate Custom Tracking Domain CNAME & SSL Handshake (15 points)
    tracking_fqdn = f"{clean_sub}.{clean_domain}"
    mock_cname = None
    if mock_records:
        mock_cname = mock_records.get("cname") or mock_records.get("tracking_cname")
        if mock_ssl_valid is None:
            mock_ssl_valid = mock_records.get("ssl_valid") or mock_records.get("mock_ssl_valid")

    cname_check = verify_custom_tracking_domain(
        tracking_fqdn=tracking_fqdn,
        expected_cname_target=clean_cname_target,
        check_live_ssl=check_live_ssl,
        timeout=2.5,
        mock_cname=mock_cname,
        mock_ssl_valid=mock_ssl_valid,
    )

    cname_target = cname_check.get("cname_target")
    cname_valid = cname_check.get("status") in ("VERIFIED_ACTIVE", "SSL_PENDING_PROVISIONING", "CNAME_ONLY") or bool(
        cname_target and cname_target == clean_cname_target
    )
    ssl_verified = bool(cname_check.get("ssl_verified"))

    if cname_valid:
        score += 15
        if not ssl_verified:
            logger.warning(
                f"[DeliverabilityGuard] Custom tracking CNAME ({tracking_fqdn} -> {clean_cname_target}) is configured, "
                f"but SSL certificate is still provisioning or invalid. Status: {cname_check.get('status')}"
            )
            warnings.append(
                f"Custom tracking CNAME ({tracking_fqdn} -> {clean_cname_target}) is configured, but SSL certificate is still provisioning. "
                "Tracking links will remain plain until SSL is active."
            )
    else:
        warnings.append(
            f"Custom tracking CNAME ({tracking_fqdn} -> {clean_cname_target}) is not verified. "
            "Links will use direct unrewritten URLs to avoid SSL errors."
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
                "actual_target": cname_target,
                "ssl_verified": bool(cname_valid and ssl_verified),
                "status": cname_check.get("status"),
                "ssl_details": cname_check.get("ssl_details"),
                "can_track_safely": cname_check.get("can_track_safely", False),
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
    - Layer 2 Safety: Never rewrites links already pointing to tracking domain or containing /t/c/.
      Preserves trailing sentence punctuation (., !, ?, ;, ", ,).
    """
    if not body or not isinstance(body, str):
        return {"body": "", "rewritten_count": 0, "tracking_applied": False}

    clean_tracking = sanitize_domain_input(tracking_domain)
    if not clean_tracking:
        return {
            "body": body,
            "rewritten_count": 0,
            "tracking_applied": False,
            "fallback_reason": "NO_VALID_TRACKING_DOMAIN",
        }

    if not ssl_verified:
        return {
            "body": body,
            "rewritten_count": 0,
            "tracking_applied": False,
            "fallback_reason": "SSL_UNVERIFIED_PREVENTED_BROWSER_WARNING",
        }

    if not email_id:
        return {
            "body": body,
            "rewritten_count": 0,
            "tracking_applied": False,
            "fallback_reason": "MISSING_EMAIL_ID",
        }

    url_pattern = re.compile(r"(https?://[^\s\"'<>)\]]+)", re.IGNORECASE)
    rewritten_count = 0

    def _replace_match(match: re.Match) -> str:
        nonlocal rewritten_count
        original_url = match.group(1)
        # Strip trailing punctuation that is part of prose (e.g. period, comma, !, ?, ;, " at end of sentence)
        trailing = ""
        while original_url and original_url[-1] in (".", ",", ";", "!", "?", '"'):
            trailing = original_url[-1] + trailing
            original_url = original_url[:-1]

        if not original_url:
            return match.group(1)

        try:
            parsed = urllib.parse.urlparse(original_url)
            host = (parsed.hostname or "").lower()
            # Do not double-wrap links already pointing to the tracking domain
            if not host or host == clean_tracking or host.endswith(f".{clean_tracking}"):
                return original_url + trailing
            if "/t/c/" in parsed.path:
                return original_url + trailing
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
