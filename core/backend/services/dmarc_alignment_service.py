"""
dmarc_alignment_service.py — Live DMARC/DKIM/SPF Alignment Auditor, DNS Drift Tripwire & Auto-Quarantine

Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer (Core Mechanics)
    - Full RFC 7489 DMARC record parsing (v, p, sp, aspf, adkim, pct, rua, ruf, fo, ri).
    - Authentic SPF & DKIM Alignment evaluation (Relaxed 'r' vs Strict 's' modes).
    - RFC 7489 Section 6.6.3 Organization Domain fallback (subdomain -> root domain DMARC record).
    - Mailbox-level DNS health audits (RFC 7208 SPF collisions, DKIM public key validity RFC 6376).
    - Workspace-wide DNS drift scanning with automated inbox quarantine & notification dispatch.
    - DMARCAlignmentService facade with complete static method interfaces.

  - Layer 1: Environmental Failure Analysis
    - Graceful dnspython timeout and exception handling (NXDOMAIN, NoAnswer, Timeout, SERVFAIL).
    - Resilient offline fallback and deterministic mock_dns routing for unit and integration testing.
    - Database outage resilience: Supabase failures fail safe without unhandled exceptions.
    - Notification dispatch failure isolation so alert errors never interrupt audit pipelines.

  - Layer 2: Human Paranoia & Security Defense
    - SSRF prevention: sanitizes all domains using sanitize_domain_input, blocking localhost, IPs, and internal TLDs.
    - Malformed DMARC syntax defense: handles quotes, spaces around '=', duplicate tags, and unknown tags.
    - Mandatory 'v=DMARC1' first-tag enforcement per RFC 7489 Section 6.6.1.
    - Clamped pct (0-100) and sanitized policy/mode normalization.
    - Multi-tenant IDOR protection: strictly scopes all inbox queries and updates to workspace_id.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.backend.services.deliverability_guard import sanitize_domain_input
from integrations.backend.services.email_sender_service import extract_root_domain

try:
    import dns.resolver
    import dns.exception
    HAS_DNS_RESOLVER = True
except ImportError:
    dns = None
    HAS_DNS_RESOLVER = False

try:
    from core.backend.services.notification_service import dispatch_notification
    HAS_NOTIFICATION_SERVICE = True
except ImportError:
    dispatch_notification = None
    HAS_NOTIFICATION_SERVICE = False

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class DMARCAlignmentMode(str, Enum):
    RELAXED = "r"
    STRICT = "s"


class DMARCPolicy(str, Enum):
    NONE = "none"
    QUARANTINE = "quarantine"
    REJECT = "reject"
    MISSING = "missing"


# ============================================================================
# Safe DNS Lookup Helper
# ============================================================================

def _dns_txt_lookup(
    qname: str,
    mock_dns: Optional[Dict[str, Any]] = None,
    timeout: float = 2.5,
) -> List[str]:
    """
    Paranoia Layer 0 & 1: Safe DNS TXT lookup.
    - When mock_dns is provided, resolves purely against normalized mock dictionary.
    - When mock_dns is None, uses dnspython with strict timeout and comprehensive error catching.
    """
    if not qname or not isinstance(qname, str):
        return []

    norm_qname = qname.strip().rstrip(".").lower()

    if mock_dns is not None:
        for key, val in mock_dns.items():
            if str(key).strip().rstrip(".").lower() == norm_qname:
                if val is None:
                    return []
                if isinstance(val, (list, tuple)):
                    return [str(item) for item in val if item is not None]
                return [str(val)]
        return []

    if not HAS_DNS_RESOLVER or not dns:
        logger.debug(f"[DMARCAlignmentService] dnspython not available for TXT lookup of {norm_qname}")
        return []

    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answers = resolver.resolve(norm_qname, "TXT")
        records: List[str] = []
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
        logger.debug(f"[DMARCAlignmentService] Live TXT lookup failed for {norm_qname}: {exc}")
        return []


# ============================================================================
# RFC 7489 DMARC Parser
# ============================================================================

def parse_dmarc_record(dmarc_raw: Optional[str]) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Parses RFC 7489 DMARC TXT record.
    Tags parsed:
      - v: must be DMARC1, and must be the FIRST tag (RFC 7489 Section 6.6.1).
      - p: policy (none | quarantine | reject). Required.
      - sp: subdomain policy (none | quarantine | reject). Defaults to p.
      - aspf: SPF alignment mode ('r' relaxed, 's' strict). Defaults to 'r'.
      - adkim: DKIM alignment mode ('r' relaxed, 's' strict). Defaults to 'r'.
      - pct: percentage of messages subjected to filtering (0-100). Defaults to 100.
      - rua: aggregate reporting URIs (e.g. mailto:dmarc@example.com).
      - ruf: forensic reporting URIs.
      - fo: forensic reporting options (defaults to "0").
      - ri: reporting interval in seconds (defaults to 86400).

    Paranoia Layer 2:
      - Sanitizes whitespace and quotes (e.g. p="reject").
      - Handles duplicate tags gracefully, logging warnings.
      - Preserves unknown tags in `tags` dict without failing.
      - Validates first tag is v=DMARC1. Returns valid=False if missing or invalid.
    """
    default_res: Dict[str, Any] = {
        "valid": False,
        "raw_record": dmarc_raw,
        "policy": DMARCPolicy.MISSING.value,
        "subdomain_policy": DMARCPolicy.MISSING.value,
        "aspf": DMARCAlignmentMode.RELAXED.value,
        "adkim": DMARCAlignmentMode.RELAXED.value,
        "pct": 100,
        "rua": None,
        "ruf": None,
        "tags": {},
        "warnings": [],
        "errors": [],
    }

    if not dmarc_raw or not isinstance(dmarc_raw, str) or not dmarc_raw.strip():
        default_res["errors"].append("DMARC record is empty or missing.")
        return default_res

    clean_raw = dmarc_raw.strip()
    raw_tokens = clean_raw.split(";")
    tags: Dict[str, str] = {}
    warnings: List[str] = []
    errors: List[str] = []
    first_tag_name: Optional[str] = None

    for token in raw_tokens:
        clean_tok = token.strip()
        if not clean_tok:
            continue

        if "=" not in clean_tok:
            warnings.append(f"Skipping malformed DMARC tag without '=': '{clean_tok}'")
            continue

        parts = clean_tok.split("=", 1)
        tag_name = parts[0].strip().lower()
        tag_val = parts[1].strip()

        # Strip surrounding quotes (double or single)
        if (tag_val.startswith('"') and tag_val.endswith('"')) or (tag_val.startswith("'") and tag_val.endswith("'")):
            tag_val = tag_val[1:-1].strip()

        if first_tag_name is None:
            first_tag_name = tag_name

        if tag_name in tags:
            warnings.append(f"Duplicate DMARC tag '{tag_name}' detected. Overwriting previous value.")

        tags[tag_name] = tag_val

    # RFC 7489 Section 6.6.1: v=DMARC1 must be the first tag
    if first_tag_name != "v":
        errors.append("First tag in DMARC record must be 'v=DMARC1' (RFC 7489 Section 6.6.1).")
        default_res["errors"] = errors
        default_res["warnings"] = warnings
        default_res["tags"] = tags
        return default_res

    v_val = tags.get("v", "").strip()
    if v_val.upper() != "DMARC1":
        errors.append(f"Invalid DMARC version '{v_val}'. Must be 'DMARC1'.")
        default_res["errors"] = errors
        default_res["warnings"] = warnings
        default_res["tags"] = tags
        return default_res

    # Validate required 'p' policy tag
    if "p" not in tags:
        errors.append("Missing required 'p' policy tag in DMARC record.")
        default_res["errors"] = errors
        default_res["warnings"] = warnings
        default_res["tags"] = tags
        return default_res

    p_raw = tags["p"].lower().strip()
    if p_raw not in ("none", "quarantine", "reject"):
        errors.append(f"Invalid policy tag value p='{p_raw}'. Must be 'none', 'quarantine', or 'reject'.")
        default_res["errors"] = errors
        default_res["warnings"] = warnings
        default_res["tags"] = tags
        return default_res

    policy = p_raw

    # Subdomain policy 'sp' (defaults to 'p' if omitted or invalid)
    sp_raw = tags.get("sp", "").lower().strip()
    if sp_raw in ("none", "quarantine", "reject"):
        subdomain_policy = sp_raw
    else:
        if "sp" in tags:
            warnings.append(f"Invalid subdomain policy sp='{sp_raw}'. Falling back to main policy '{policy}'.")
        subdomain_policy = policy

    # Alignment modes (aspf, adkim)
    aspf_raw = tags.get("aspf", "r").lower().strip()
    if aspf_raw in ("r", "s"):
        aspf = aspf_raw
    else:
        warnings.append(f"Invalid aspf='{aspf_raw}'. Defaulting to relaxed 'r'.")
        aspf = DMARCAlignmentMode.RELAXED.value

    adkim_raw = tags.get("adkim", "r").lower().strip()
    if adkim_raw in ("r", "s"):
        adkim = adkim_raw
    else:
        warnings.append(f"Invalid adkim='{adkim_raw}'. Defaulting to relaxed 'r'.")
        adkim = DMARCAlignmentMode.RELAXED.value

    # Percentage tag 'pct' (defaults to 100, clamped 0-100)
    pct_raw = tags.get("pct", "100").strip()
    try:
        pct_val = int(pct_raw)
        pct = max(0, min(100, pct_val))
    except (ValueError, TypeError):
        warnings.append(f"Invalid pct='{pct_raw}'. Defaulting to 100.")
        pct = 100

    # Reporting URIs
    rua = tags.get("rua")
    ruf = tags.get("ruf")

    return {
        "valid": True,
        "raw_record": clean_raw,
        "policy": policy,
        "subdomain_policy": subdomain_policy,
        "aspf": aspf,
        "adkim": adkim,
        "pct": pct,
        "rua": rua,
        "ruf": ruf,
        "fo": tags.get("fo", "0"),
        "ri": tags.get("ri", "86400"),
        "tags": tags,
        "warnings": warnings,
        "errors": errors,
    }


# ============================================================================
# Core Alignment Evaluator
# ============================================================================

def evaluate_dmarc_alignment(
    from_header_domain: str,
    return_path_domain: Optional[str] = None,
    dkim_domain: Optional[str] = None,
    dmarc_record: Optional[str] = None,
    dkim_selector: str = "elein",
    mock_dns: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Comprehensive DMARC Alignment Evaluation.
    - Sanitizes From domain using sanitize_domain_input and extracts root domain.
    - Resolves DMARC record:
      - Uses provided dmarc_record or mock_dns if present.
      - Looks up _dmarc.{clean_from}.
      - Fallback: If missing and clean_from is a subdomain, looks up _dmarc.{from_root}
        per RFC 7489 Section 6.6.3.
    - Evaluates SPF Alignment:
      - aspf == 's': return_path_domain == clean_from
      - aspf == 'r': root(return_path_domain) == root(clean_from)
    - Evaluates DKIM Alignment:
      - adkim == 's': dkim_domain == clean_from
      - adkim == 'r': root(dkim_domain) == root(clean_from)
    - DMARC Alignment: dmarc_aligned = bool(spf_aligned or dkim_aligned)
    - Deliverability Risk & Safety:
      - Aligned: "SAFE", can_safely_send = True
      - Unaligned + reject: "CRITICAL_REJECT_RISK", can_safely_send = False, reason = "DMARC_REJECT_UNALIGNED"
      - Unaligned + quarantine: "HIGH_SPAM_RISK", can_safely_send = False, reason = "DMARC_QUARANTINE_UNALIGNED"
      - Unaligned + none: "MODERATE_RISK", can_safely_send = True
      - Missing: "HIGH_RISK", can_safely_send = True
    """
    raw_from = str(from_header_domain or "").strip()
    angle_match = re.search(r"<([^>]+)>", raw_from)
    if angle_match:
        raw_from = angle_match.group(1).strip()
    clean_from = sanitize_domain_input(raw_from)
    if not clean_from:
        return {
            "valid": False,
            "from_header_domain": from_header_domain,
            "from_header_root": None,
            "return_path_domain": return_path_domain,
            "return_path_root": None,
            "dkim_domain": dkim_domain,
            "dkim_root": None,
            "dmarc_record": None,
            "dmarc_record_location": None,
            "is_org_domain_fallback": False,
            "policy": DMARCPolicy.MISSING.value,
            "dmarc_policy": DMARCPolicy.MISSING.value,
            "aspf": DMARCAlignmentMode.RELAXED.value,
            "adkim": DMARCAlignmentMode.RELAXED.value,
            "pct": 100,
            "spf_aligned": False,
            "dkim_aligned": False,
            "dmarc_aligned": False,
            "deliverability_risk": "CRITICAL_REJECT_RISK",
            "can_safely_send": False,
            "rejection_reason": "INVALID_FROM_HEADER_DOMAIN",
            "recommendations": ["Provide a valid RFC-compliant domain name for the From header."],
            "remediation_records": [],
            "warnings": [],
            "errors": ["Invalid or unsafe From header domain provided."],
        }

    from_root = extract_root_domain(clean_from) or clean_from

    # Resolve DMARC Record
    raw_dmarc: Optional[str] = None
    record_location: Optional[str] = None
    is_org_domain_fallback = False

    if dmarc_record:
        raw_dmarc = dmarc_record
        record_location = f"_dmarc.{clean_from}"
    else:
        # Check subdomain or exact host
        sub_records = _dns_txt_lookup(f"_dmarc.{clean_from}", mock_dns=mock_dns)
        sub_matches = [
            r.strip() for r in sub_records
            if isinstance(r, str) and r.strip().lower().startswith("v=dmarc1")
        ]
        if sub_matches:
            raw_dmarc = sub_matches[0]
            record_location = f"_dmarc.{clean_from}"
        elif from_root and clean_from != from_root:
            # RFC 7489 Section 6.6.3: Fallback to Organization Domain
            org_records = _dns_txt_lookup(f"_dmarc.{from_root}", mock_dns=mock_dns)
            org_matches = [
                r.strip() for r in org_records
                if isinstance(r, str) and r.strip().lower().startswith("v=dmarc1")
            ]
            if org_matches:
                raw_dmarc = org_matches[0]
                record_location = f"_dmarc.{from_root}"
                is_org_domain_fallback = True

    parsed_dmarc = parse_dmarc_record(raw_dmarc)
    errors: List[str] = list(parsed_dmarc.get("errors", []))
    warnings: List[str] = list(parsed_dmarc.get("warnings", []))
    recommendations: List[str] = []
    remediation_records: List[Dict[str, str]] = []

    # Determine effective policy per RFC 7489 Section 6.6.3
    if not parsed_dmarc.get("valid"):
        effective_policy = DMARCPolicy.MISSING.value
        aspf_mode = DMARCAlignmentMode.RELAXED.value
        adkim_mode = DMARCAlignmentMode.RELAXED.value
        pct_val = 100
    else:
        if is_org_domain_fallback:
            # When evaluating a subdomain against an org domain record, 'sp' governs
            effective_policy = parsed_dmarc.get("subdomain_policy") or parsed_dmarc.get("policy")
        else:
            effective_policy = parsed_dmarc.get("policy")

        aspf_mode = parsed_dmarc.get("aspf", DMARCAlignmentMode.RELAXED.value)
        adkim_mode = parsed_dmarc.get("adkim", DMARCAlignmentMode.RELAXED.value)
        pct_val = parsed_dmarc.get("pct", 100)

    # Evaluate SPF Alignment
    if return_path_domain:
        raw_rp = str(return_path_domain).strip()
        angle_rp = re.search(r"<([^>]+)>", raw_rp)
        if angle_rp:
            raw_rp = angle_rp.group(1).strip()
        clean_rp = sanitize_domain_input(raw_rp)
    else:
        clean_rp = None
    rp_root = extract_root_domain(clean_rp) if clean_rp else None

    if clean_rp:
        if aspf_mode == DMARCAlignmentMode.STRICT.value:
            spf_aligned = bool(clean_rp.lower() == clean_from.lower())
        else:
            spf_aligned = bool(rp_root and from_root and rp_root.lower() == from_root.lower())
    else:
        spf_aligned = False

    # Evaluate DKIM Alignment
    if dkim_domain:
        raw_dkim = str(dkim_domain).strip()
        angle_dkim = re.search(r"<([^>]+)>", raw_dkim)
        if angle_dkim:
            raw_dkim = angle_dkim.group(1).strip()
        clean_dkim = sanitize_domain_input(raw_dkim)
    else:
        clean_dkim = None
    dkim_root = extract_root_domain(clean_dkim) if clean_dkim else None

    if clean_dkim:
        if adkim_mode == DMARCAlignmentMode.STRICT.value:
            dkim_aligned = bool(clean_dkim.lower() == clean_from.lower())
        else:
            dkim_aligned = bool(dkim_root and from_root and dkim_root.lower() == from_root.lower())
    else:
        dkim_aligned = False

    # Overall DMARC Alignment (RFC 7489 Section 3.1: DMARC requires discovered DMARC policy)
    has_valid_dmarc = bool(parsed_dmarc.get("valid") and effective_policy != DMARCPolicy.MISSING.value)
    dmarc_aligned = bool((spf_aligned or dkim_aligned) and has_valid_dmarc)

    rejection_reason: Optional[str] = None
    if dmarc_aligned:
        deliverability_risk = "SAFE"
        can_safely_send = True
        if not spf_aligned:
            warnings.append(
                f"SPF unaligned (Return-Path '{clean_rp}' vs From '{clean_from}'), "
                f"but DMARC passes safely via aligned DKIM ('{clean_dkim}')."
            )
        if not dkim_aligned:
            warnings.append(
                f"DKIM unaligned (d='{clean_dkim}' vs From '{clean_from}'), "
                f"but DMARC passes safely via aligned SPF ('{clean_rp}')."
            )
    else:
        if effective_policy == DMARCPolicy.REJECT.value:
            deliverability_risk = "CRITICAL_REJECT_RISK"
            can_safely_send = False
            rejection_reason = "DMARC_REJECT_UNALIGNED"
            errors.append(
                f"DMARC policy is 'p=reject' and neither SPF nor DKIM is aligned with From header '{clean_from}'. "
                "Major ESPs (Google, Yahoo, Apple) will bounce or reject messages outright."
            )
        elif effective_policy == DMARCPolicy.QUARANTINE.value:
            deliverability_risk = "HIGH_SPAM_RISK"
            can_safely_send = False
            rejection_reason = "DMARC_QUARANTINE_UNALIGNED"
            errors.append(
                f"DMARC policy is 'p=quarantine' and alignment failed. ESPs will route messages directly to spam/junk."
            )
        elif effective_policy == DMARCPolicy.NONE.value:
            deliverability_risk = "MODERATE_RISK"
            can_safely_send = True
            warnings.append(
                f"DMARC policy is 'p=none' (monitoring mode). Emails will be accepted, but domain lacks alignment protection."
            )
        else:
            deliverability_risk = "HIGH_RISK"
            can_safely_send = True
            warnings.append(
                f"No DMARC record found for '{clean_from}'. Google and Yahoo enforce DMARC requirements for bulk outreach."
            )

    # Remediation Suggestions
    clean_sel = re.sub(r"[^a-z0-9._-]", "", str(dkim_selector or "elein").lower()) or "elein"

    if effective_policy == DMARCPolicy.MISSING.value:
        recommendations.append(f"Publish a DMARC TXT record at _dmarc.{from_root or clean_from}")
        remediation_records.append({
            "type": "TXT",
            "host": f"_dmarc.{from_root or clean_from}",
            "value": f"v=DMARC1; p=none; sp=none; rua=mailto:dmarc@{from_root or clean_from}",
            "description": "Baseline DMARC monitoring policy record",
        })

    if not spf_aligned:
        recommendations.append(f"Align Return-Path envelope domain with {clean_from} (or root {from_root})")
        remediation_records.append({
            "type": "TXT",
            "host": clean_from,
            "value": "v=spf1 include:_spf.elein.ai ~all",
            "description": "SPF authorization record aligned with From header",
        })

    if not dkim_aligned:
        recommendations.append(f"Configure DKIM signing matching From domain {clean_from} (or root {from_root})")
        remediation_records.append({
            "type": "TXT",
            "host": f"{clean_sel}._domainkey.{clean_from}",
            "value": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ...",
            "description": "DKIM public key TXT record matching From domain",
        })

    return {
        "valid": bool(parsed_dmarc.get("valid", False)),
        "from_header_domain": clean_from,
        "from_header_root": from_root,
        "return_path_domain": clean_rp,
        "return_path_root": rp_root,
        "dkim_domain": clean_dkim,
        "dkim_root": dkim_root,
        "dmarc_record": raw_dmarc,
        "dmarc_record_location": record_location,
        "is_org_domain_fallback": is_org_domain_fallback,
        "parsed_dmarc": parsed_dmarc,
        "policy": effective_policy,
        "dmarc_policy": effective_policy,
        "aspf": aspf_mode,
        "adkim": adkim_mode,
        "pct": pct_val,
        "spf_aligned": spf_aligned,
        "dkim_aligned": dkim_aligned,
        "dmarc_aligned": dmarc_aligned,
        "deliverability_risk": deliverability_risk,
        "can_safely_send": can_safely_send,
        "rejection_reason": rejection_reason,
        "recommendations": recommendations,
        "remediation_records": remediation_records,
        "warnings": warnings,
        "errors": errors,
    }


# ============================================================================
# Sender Inbox DNS Health Auditor & Drift Tripwires
# ============================================================================

def audit_sender_inbox_dns_health(
    inbox: Dict[str, Any],
    mock_dns: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Sender Mailbox DNS Health Auditor.
    Extracts sender email & domain and executes comprehensive DNS audit:
      1. SPF presence, single-record compliance (RFC 7208), no permissive '+all'.
      2. DKIM presence and non-revoked public key (RFC 6376).
      3. DMARC presence, policy, and SPF/DKIM alignment.
    Detects critical DNS drift tripwires:
      - SPF_MISSING_DRIFT
      - MULTIPLE_SPF_RFC7208_COLLISION
      - SPF_PERMISSIVE_PLUS_ALL
      - DKIM_MISSING_DRIFT
      - DKIM_REVOKED_KEY
      - DMARC_REJECT_UNALIGNED
      - DMARC_QUARANTINE_UNALIGNED
    Returns composite deliverability score (0-100), tripwire status, and quarantine recommendation.
    """
    if not isinstance(inbox, dict):
        return {
            "healthy": False,
            "should_quarantine": True,
            "quarantine_reason": "INVALID_INBOX_RECORD",
            "deliverability_score": 0,
            "domain": None,
            "tripwires_tripped": ["INVALID_INBOX_RECORD"],
            "alignment": {},
            "remediation_records": [],
        }

    email_addr = (inbox.get("email") or inbox.get("from_email") or "").strip()
    raw_domain = inbox.get("domain") or inbox.get("sender_domain")
    if not raw_domain and "@" in email_addr:
        raw_domain = email_addr.split("@")[-1].strip()

    clean_domain = sanitize_domain_input(raw_domain)
    if not clean_domain:
        return {
            "healthy": False,
            "should_quarantine": True,
            "quarantine_reason": "INVALID_OR_UNSAFE_DOMAIN",
            "deliverability_score": 0,
            "domain": raw_domain,
            "email": email_addr,
            "tripwires_tripped": ["INVALID_OR_UNSAFE_DOMAIN"],
            "alignment": {},
            "remediation_records": [],
        }

    clean_selector = re.sub(r"[^a-z0-9._-]", "", str(inbox.get("dkim_selector") or "elein").lower()) or "elein"
    tripwires_tripped: List[str] = []
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Audit SPF
    if inbox.get("spf_record"):
        spf_txt = [str(inbox["spf_record"])]
    else:
        spf_txt = _dns_txt_lookup(clean_domain, mock_dns=mock_dns)

    spf_records = [
        r.strip() for r in spf_txt
        if isinstance(r, str) and r.strip().lower().startswith("v=spf1")
    ]

    spf_valid = False
    spf_score = 0
    spf_active_rec: Optional[str] = None

    if len(spf_records) == 0:
        tripwires_tripped.append("SPF_MISSING_DRIFT")
        errors.append(f"No SPF (v=spf1) record published for domain '{clean_domain}'.")
    elif len(spf_records) > 1:
        tripwires_tripped.append("MULTIPLE_SPF_RFC7208_COLLISION")
        errors.append(
            f"Multiple SPF records ({len(spf_records)}) found on '{clean_domain}'. RFC 7208 requires a single merged record."
        )
    else:
        spf_active_rec = spf_records[0]
        if "+all" in spf_active_rec.lower():
            tripwires_tripped.append("SPF_PERMISSIVE_PLUS_ALL")
            errors.append("SPF record contains '+all', allowing any IP on the internet to spoof this domain.")
        else:
            spf_valid = True
            if "~all" in spf_active_rec.lower() or "-all" in spf_active_rec.lower():
                spf_score = 30
            else:
                spf_score = 20
                warnings.append("SPF record does not specify standard ~all or -all enforcement.")

    # 2. Audit DKIM
    if inbox.get("dkim_record"):
        dkim_txt = [str(inbox["dkim_record"])]
    else:
        dkim_txt = _dns_txt_lookup(f"{clean_selector}._domainkey.{clean_domain}", mock_dns=mock_dns)

    dkim_records = [
        r.strip() for r in dkim_txt
        if isinstance(r, str) and ("v=dkim1" in r.lower() or "k=rsa" in r.lower() or "p=" in r.lower())
    ]

    dkim_valid = False
    dkim_score = 0
    dkim_active_rec: Optional[str] = None

    if len(dkim_records) == 0:
        tripwires_tripped.append("DKIM_MISSING_DRIFT")
        errors.append(f"Missing DKIM record at selector '{clean_selector}._domainkey.{clean_domain}'.")
    else:
        dkim_active_rec = dkim_records[0]
        p_match = re.search(r"\bp\s*=\s*([A-Za-z0-9+/=]+)", dkim_active_rec)
        if not p_match or len(p_match.group(1)) < 16:
            tripwires_tripped.append("DKIM_REVOKED_KEY")
            errors.append(
                f"DKIM public key at '{clean_selector}._domainkey.{clean_domain}' is empty or revoked (RFC 6376)."
            )
        else:
            dkim_valid = True
            dkim_score = 30

    # 3. Audit DMARC Alignment
    return_path_candidate = inbox.get("return_path_domain") or clean_domain
    dkim_domain_candidate = inbox.get("dkim_domain") or clean_domain

    alignment_res = evaluate_dmarc_alignment(
        from_header_domain=clean_domain,
        return_path_domain=return_path_candidate,
        dkim_domain=dkim_domain_candidate,
        dmarc_record=inbox.get("dmarc_record"),
        dkim_selector=clean_selector,
        mock_dns=mock_dns,
    )

    dmarc_score = 0
    if alignment_res.get("dmarc_aligned"):
        if alignment_res.get("policy") in ("reject", "quarantine"):
            dmarc_score = 40
        else:
            dmarc_score = 30
    else:
        rej_reason = alignment_res.get("rejection_reason")
        if rej_reason == "DMARC_REJECT_UNALIGNED":
            tripwires_tripped.append("DMARC_REJECT_UNALIGNED")
            errors.append("DMARC alignment failed under strict p=reject policy.")
        elif rej_reason == "DMARC_QUARANTINE_UNALIGNED":
            tripwires_tripped.append("DMARC_QUARANTINE_UNALIGNED")
            errors.append("DMARC alignment failed under p=quarantine policy.")
        elif alignment_res.get("policy") == DMARCPolicy.NONE.value:
            dmarc_score = 15
        else:
            dmarc_score = 5

    deliverability_score = max(0, min(100, spf_score + dkim_score + dmarc_score))
    should_quarantine = len(tripwires_tripped) > 0
    primary_quarantine_reason = tripwires_tripped[0] if tripwires_tripped else None
    healthy = bool(not should_quarantine and deliverability_score >= 80)

    remediation = list(alignment_res.get("remediation_records", []))
    if not spf_valid and not any(r.get("host") == clean_domain and r.get("type") == "TXT" for r in remediation):
        remediation.append({
            "type": "TXT",
            "host": clean_domain,
            "value": "v=spf1 include:_spf.elein.ai ~all",
            "description": "Unified RFC 7208 SPF record",
        })
    if not dkim_valid and not any(f"{clean_selector}._domainkey" in r.get("host", "") for r in remediation):
        remediation.append({
            "type": "TXT",
            "host": f"{clean_selector}._domainkey.{clean_domain}",
            "value": "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ...",
            "description": "DKIM public key record",
        })

    return {
        "inbox_id": inbox.get("id"),
        "email": email_addr,
        "domain": clean_domain,
        "healthy": healthy,
        "should_quarantine": should_quarantine,
        "quarantine_reason": primary_quarantine_reason,
        "tripwires_tripped": tripwires_tripped,
        "deliverability_score": deliverability_score,
        "spf": {
            "valid": spf_valid,
            "record": spf_active_rec,
            "score": spf_score,
        },
        "dkim": {
            "valid": dkim_valid,
            "selector": clean_selector,
            "record": dkim_active_rec,
            "score": dkim_score,
        },
        "dmarc": {
            "policy": alignment_res.get("policy"),
            "aligned": alignment_res.get("dmarc_aligned"),
            "score": dmarc_score,
        },
        "alignment": alignment_res,
        "remediation_records": remediation,
        "warnings": warnings + alignment_res.get("warnings", []),
        "errors": errors + alignment_res.get("errors", []),
    }


# ============================================================================
# Workspace DNS Drift Scanner & Auto-Quarantine
# ============================================================================

def scan_workspace_dns_drift(
    supabase: Optional[Any],
    workspace_id: str,
    auto_quarantine: bool = True,
    mock_inboxes: Optional[List[Dict[str, Any]]] = None,
    mock_dns: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Workspace DNS Drift Scanner.
    - Scans all active and warming inboxes within workspace_id.
    - Audits SPF, DKIM, and DMARC alignment via audit_sender_inbox_dns_health.
    - If auto_quarantine is True and tripwire triggers:
      - Quarantines inbox in Supabase with status="QUARANTINED", quarantine_reason=reason,
        quarantined_until=(now + 24h).isoformat().
      - Dispatches workspace notification via notification_service.
    - Returns aggregate report with counts and detailed audit records.
    """
    if not workspace_id or not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("workspace_id is required and cannot be empty")

    clean_ws = workspace_id.strip()

    # Retrieve Inboxes
    inboxes: List[Dict[str, Any]] = []
    if mock_inboxes is not None:
        inboxes = [dict(inb) for inb in mock_inboxes if isinstance(inb, dict)]
    elif supabase:
        try:
            res = (
                supabase.table("email_sender_inboxes")
                .select("*")
                .eq("workspace_id", clean_ws)
                .execute()
            )
            raw_data = getattr(res, "data", None)
            if isinstance(raw_data, list):
                inboxes = [dict(r) for r in raw_data if isinstance(r, dict)]
        except Exception as exc:
            logger.error(f"[DMARCAlignmentService] Error querying inboxes for workspace {clean_ws}: {exc}")
            inboxes = []

    now_utc = datetime.now(timezone.utc)
    healthy_count = 0
    quarantined_count = 0
    drift_detected_count = 0
    inboxes_audit: List[Dict[str, Any]] = []

    for inb in inboxes:
        audit = audit_sender_inbox_dns_health(inb, mock_dns=mock_dns)
        inb_id = inb.get("id")

        if audit.get("should_quarantine"):
            drift_detected_count += 1
            if auto_quarantine:
                quarantined_count += 1
                q_reason = audit.get("quarantine_reason") or "DNS_DRIFT_DETECTED"
                q_until = (now_utc + timedelta(hours=24)).isoformat()

                audit["status_applied"] = "QUARANTINED"
                audit["quarantined_until"] = q_until

                # Update Supabase if available and valid ID present
                if supabase and inb_id:
                    try:
                        update_payload = {
                            "status": "QUARANTINED",
                            "quarantine_reason": q_reason,
                            "quarantined_until": q_until,
                            "deliverability_score": audit.get("deliverability_score", 0),
                            "updated_at": now_utc.isoformat(),
                        }
                        supabase.table("email_sender_inboxes").update(update_payload).eq(
                            "id", str(inb_id)
                        ).eq("workspace_id", clean_ws).execute()
                    except Exception as db_exc:
                        logger.error(
                            f"[DMARCAlignmentService] Failed to quarantine inbox {inb_id} in Supabase: {db_exc}"
                        )

                    # Dispatch notification
                    if HAS_NOTIFICATION_SERVICE and dispatch_notification:
                        try:
                            dispatch_notification(
                                svc=supabase,
                                workspace_id=clean_ws,
                                event_type="account_needs_attention",
                                payload={
                                    "title": "DNS Drift Alert: Mailbox Quarantined",
                                    "body": (
                                        f"Mailbox {inb.get('email', inb_id)} was automatically quarantined due to DNS drift: "
                                        f"{q_reason}. Deliverability score: {audit.get('deliverability_score', 0)}/100."
                                    ),
                                    "inbox_id": str(inb_id),
                                    "quarantine_reason": q_reason,
                                    "deliverability_score": audit.get("deliverability_score", 0),
                                    "unique_key": f"dns_drift_{inb_id}_{now_utc.strftime('%Y%m%d%H')}",
                                },
                            )
                        except Exception as n_exc:
                            logger.debug(f"[DMARCAlignmentService] Notification dispatch failed: {n_exc}")
            else:
                audit["status_applied"] = inb.get("status", "ACTIVE")
        else:
            healthy_count += 1
            audit["status_applied"] = inb.get("status", "ACTIVE")

        inboxes_audit.append(audit)

    return {
        "workspace_id": clean_ws,
        "total_inboxes": len(inboxes),
        "healthy_count": healthy_count,
        "quarantined_count": quarantined_count,
        "drift_detected_count": drift_detected_count,
        "inboxes_audit": inboxes_audit,
        "scanned_at": now_utc.isoformat(),
    }


# ============================================================================
# Facade Class
# ============================================================================

class DMARCAlignmentService:
    """
    Facade class exposing DMARC Alignment, DNS health auditing, and DNS drift auto-quarantine.
    """
    DMARCAlignmentMode = DMARCAlignmentMode
    DMARCPolicy = DMARCPolicy

    @staticmethod
    def parse_dmarc_record(dmarc_raw: Optional[str]) -> Dict[str, Any]:
        return parse_dmarc_record(dmarc_raw)

    @staticmethod
    def evaluate_dmarc_alignment(
        from_header_domain: str,
        return_path_domain: Optional[str] = None,
        dkim_domain: Optional[str] = None,
        dmarc_record: Optional[str] = None,
        dkim_selector: str = "elein",
        mock_dns: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return evaluate_dmarc_alignment(
            from_header_domain=from_header_domain,
            return_path_domain=return_path_domain,
            dkim_domain=dkim_domain,
            dmarc_record=dmarc_record,
            dkim_selector=dkim_selector,
            mock_dns=mock_dns,
        )

    @staticmethod
    def audit_sender_inbox_dns_health(
        inbox: Dict[str, Any],
        mock_dns: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return audit_sender_inbox_dns_health(inbox=inbox, mock_dns=mock_dns)

    @staticmethod
    def scan_workspace_dns_drift(
        supabase: Optional[Any],
        workspace_id: str,
        auto_quarantine: bool = True,
        mock_inboxes: Optional[List[Dict[str, Any]]] = None,
        mock_dns: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return scan_workspace_dns_drift(
            supabase=supabase,
            workspace_id=workspace_id,
            auto_quarantine=auto_quarantine,
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )
