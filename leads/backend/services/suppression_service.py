"""
Three-Layer Paranoia Framework: Suppression List (DNC) Canonical Normalization,
Wildcard Domain Blocking & Retroactive In-Flight Purge Guard.
- Layer 0 (Foundational): Canonicalizes LinkedIn URLs, emails, and company domains
  ('@competitor.com', 'https://www.competitor.com/about' -> 'competitor.com') and checks leads
  against exact LinkedIn URL, exact email, and wildcard email domain.
- Layer 1 (Environmental): Retroactive in-flight purge — adding a LinkedIn URL, email, or
  company domain to the workspace suppression list immediately scans and exits any active
  in-flight campaign_execution_states ('pending', 'waiting_for_reply', 'running',
  'awaiting_approval', 'snoozed_ooo') for matching prospects in that workspace.
- Layer 2 (Human Paranoia): Blocks accidental wildcard suppression of public freemail domains
  ('gmail.com', 'yahoo.com', 'outlook.com', etc.) unless allow_freemail_domain=True is explicitly
  passed; deduplicates intra-batch entries; enforces batch size ceiling (5,000).
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from leads.backend.services.data_hygiene import DataHygieneService

logger = logging.getLogger(__name__)

MAX_SUPPRESSION_BATCH_SIZE = 5000
CHUNK_SIZE = 200

PUBLIC_FREEMAIL_DOMAINS: Set[str] = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.in",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "protonmail.com",
    "proton.me",
    "zoho.com",
    "gmx.com",
    "mail.com",
    "yandex.com",
}

ACTIVE_EXECUTION_STATUSES = [
    "pending",
    "waiting_for_reply",
    "running",
    "awaiting_approval",
    "snoozed_ooo",
]


def normalize_suppression_domain(raw_domain: Optional[str]) -> Optional[str]:
    """
    Paranoia Layer 0 & 2: Normalizes a domain string or URL into a canonical lowercase domain
    (e.g., '*@Competitor.com', 'https://www.competitor.com/pricing?x=1' -> 'competitor.com').
    Returns None if not a valid domain or if it is a LinkedIn domain.
    """
    if not raw_domain or not isinstance(raw_domain, str):
        return None
    s = raw_domain.strip().lower()
    if not s:
        return None

    # Strip leading wildcard / '@' prefixes like '*@domain.com' or '@domain.com'
    s = re.sub(r"^[\*\s@]+", "", s)

    # If it contains '://' or starts with 'www.', parse hostname
    if "://" in s or "/" in s:
        if "://" not in s:
            s = "https://" + s
        try:
            parsed = urlparse(s)
            s = parsed.hostname or ""
        except Exception:
            return None

    # If someone passed an email address into domain field, do NOT treat as domain unless no local part
    if "@" in s:
        return None

    # Strip port and 'www.'
    s = s.split(":")[0].strip().strip(".")
    if s.startswith("www."):
        s = s[4:]

    # Reject linkedin.com itself as a company suppression domain
    if s in ("linkedin.com", "sales.linkedin.com") or s.endswith(".linkedin.com"):
        return None

    # Validate domain format: labels separated by dots, TLD >= 2 letters
    if not re.match(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", s):
        return None
    tld = s.rsplit(".", 1)[-1]
    if len(tld) < 2 or tld.isdigit():
        return None

    return s


def normalize_suppression_entry(raw_entry: Any, allow_freemail_domain: bool = False) -> Dict[str, Any]:
    """
    Normalizes a suppression entry dict (or raw string) into canonical linkedin_url, email, and/or domain.
    Returns:
      {
        "valid": bool,
        "linkedin_url": Optional[str],
        "email": Optional[str],
        "domain": Optional[str],
        "reason": str,
        "error": Optional[str],
      }
    """
    if isinstance(raw_entry, str):
        raw_entry = {"value": raw_entry}
    if not isinstance(raw_entry, dict):
        return {"valid": False, "linkedin_url": None, "email": None, "domain": None, "reason": "", "error": "Invalid entry format"}

    raw_li = raw_entry.get("linkedin_url")
    raw_email = raw_entry.get("email")
    raw_domain = raw_entry.get("domain")
    raw_value = raw_entry.get("value")
    reason = DataHygieneService.sanitize_text(raw_entry.get("reason") or "manual_dnc", 200) or "manual_dnc"

    # Auto-classify generic 'value' if provided
    if isinstance(raw_value, str) and raw_value.strip():
        v_clean = raw_value.strip()
        if "linkedin.com/" in v_clean.lower():
            raw_li = raw_li or v_clean
        elif "@" in v_clean and not v_clean.startswith("@") and not v_clean.startswith("*@"):
            raw_email = raw_email or v_clean
        else:
            raw_domain = raw_domain or v_clean

    clean_li = (DataHygieneService.normalize_linkedin_url(str(raw_li)) or None) if raw_li else None
    clean_em = (DataHygieneService.clean_email(str(raw_email)) or None) if raw_email else None
    clean_dom = normalize_suppression_domain(str(raw_domain)) if raw_domain else None

    # Paranoia Layer 2: Block freemail wildcard domain suppression unless explicitly overridden
    if clean_dom and clean_dom in PUBLIC_FREEMAIL_DOMAINS and not allow_freemail_domain:
        return {
            "valid": False,
            "linkedin_url": clean_li,
            "email": clean_em,
            "domain": clean_dom,
            "reason": reason,
            "error": (
                f"Blocked wildcard domain suppression for public freemail provider '{clean_dom}'. "
                f"Suppressing '{clean_dom}' would block all personal emails across your workspace. "
                f"Suppress specific email addresses instead, or pass allow_freemail_domain=true."
            ),
        }

    if not clean_li and not clean_em and not clean_dom:
        return {
            "valid": False,
            "linkedin_url": None,
            "email": None,
            "domain": None,
            "reason": reason,
            "error": "Entry must contain at least one valid LinkedIn profile URL, email address, or company domain.",
        }

    return {
        "valid": True,
        "linkedin_url": clean_li,
        "email": clean_em,
        "domain": clean_dom,
        "reason": reason,
        "error": None,
    }


def retroactive_purge_suppressed_leads(
    supabase: Any,
    workspace_id: str,
    linkedin_urls: Optional[List[str]] = None,
    emails: Optional[List[str]] = None,
    domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 1: Retroactively halts in-flight campaign executions for any existing leads
    in the workspace matching the newly suppressed LinkedIn URLs, emails, or company domains.
    """
    li_set = {u.strip().lower() for u in (linkedin_urls or []) if isinstance(u, str) and u.strip()}
    em_set = {e.strip().lower() for e in (emails or []) if isinstance(e, str) and e.strip()}
    dom_set = {d.strip().lower() for d in (domains or []) if isinstance(d, str) and d.strip()}

    if not li_set and not em_set and not dom_set:
        return {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": []}

    matched_lead_ids: Set[str] = set()

    # 1. Match by LinkedIn URL in chunks
    li_list = sorted(list(li_set))
    for i in range(0, len(li_list), CHUNK_SIZE):
        chunk = li_list[i : i + CHUNK_SIZE]
        try:
            res = (
                supabase.table("leads")
                .select("id")
                .eq("workspace_id", workspace_id)
                .in_("linkedin_url", chunk)
                .execute()
            )
            for row in (res.data or []):
                if isinstance(row, dict) and row.get("id"):
                    matched_lead_ids.add(row["id"])
        except Exception as e:
            logger.warning(f"[SuppressionPurge] LinkedIn URL lookup failed: {e}")

    # 2. Match by exact Email in chunks
    em_list = sorted(list(em_set))
    for i in range(0, len(em_list), CHUNK_SIZE):
        chunk = em_list[i : i + CHUNK_SIZE]
        try:
            res = (
                supabase.table("leads")
                .select("id")
                .eq("workspace_id", workspace_id)
                .in_("email", chunk)
                .execute()
            )
            for row in (res.data or []):
                if isinstance(row, dict) and row.get("id"):
                    matched_lead_ids.add(row["id"])
        except Exception as e:
            logger.warning(f"[SuppressionPurge] Email lookup failed: {e}")

    # 3. Match by Wildcard Domain (@domain.com) across all paginated workspace leads
    if dom_set:
        try:
            start_row = 0
            while True:
                res = (
                    supabase.table("leads")
                    .select("id, email, domain")
                    .eq("workspace_id", workspace_id)
                    .range(start_row, start_row + 999)
                    .execute()
                )
                batch = res.data or []
                if not batch:
                    break
                for row in batch:
                    if not isinstance(row, dict) or not row.get("id"):
                        continue
                    lead_dom = str(row.get("domain") or "").strip().lower()
                    if not lead_dom:
                        lead_em = str(row.get("email") or "").strip().lower()
                        if "@" in lead_em:
                            lead_dom = lead_em.rsplit("@", 1)[-1].strip()
                    if lead_dom and lead_dom in dom_set:
                        matched_lead_ids.add(row["id"])
                if len(batch) < 1000:
                    break
                start_row += 1000
        except Exception as e:
            logger.warning(f"[SuppressionPurge] Domain scan lookup failed: {e}")

    if not matched_lead_ids:
        return {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": []}

    lead_id_list = sorted(list(matched_lead_ids))
    now_iso = datetime.now(timezone.utc).isoformat()

    # Mark leads as Suppressed
    for i in range(0, len(lead_id_list), CHUNK_SIZE):
        chunk = lead_id_list[i : i + CHUNK_SIZE]
        try:
            supabase.table("leads").update({"status": "suppressed"}).eq("workspace_id", workspace_id).in_("id", chunk).execute()
        except Exception as e:
            logger.debug(f"[SuppressionPurge] Lead status update ignored: {e}")

    # Find enrollments for matched leads and exit active execution states
    enrollment_ids: List[str] = []
    for i in range(0, len(lead_id_list), CHUNK_SIZE):
        chunk = lead_id_list[i : i + CHUNK_SIZE]
        try:
            enr_res = (
                supabase.table("campaign_enrollments")
                .select("id")
                .eq("workspace_id", workspace_id)
                .in_("lead_id", chunk)
                .execute()
            )
            for row in (enr_res.data or []):
                if isinstance(row, dict) and row.get("id"):
                    enrollment_ids.append(row["id"])
        except Exception as e:
            logger.warning(f"[SuppressionPurge] Enrollment lookup failed: {e}")

    halted_states_count = 0
    for i in range(0, len(enrollment_ids), CHUNK_SIZE):
        chunk = enrollment_ids[i : i + CHUNK_SIZE]
        try:
            upd_res = (
                supabase.table("campaign_execution_states")
                .update({
                    "status": "exited",
                    "error_reason": "Retroactively halted: prospect or domain added to workspace Suppression List (DNC)",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "updated_at": now_iso,
                })
                .eq("workspace_id", workspace_id)
                .in_("enrollment_id", chunk)
                .in_("status", ACTIVE_EXECUTION_STATUSES)
                .execute()
            )
            halted_states_count += len(upd_res.data or [])
        except Exception as e:
            logger.warning(f"[SuppressionPurge] Execution state halt failed: {e}")

    # 4. Paranoia Layer 1: Cancel pending and queued outbox_events for matched leads
    for i in range(0, len(lead_id_list), CHUNK_SIZE):
        chunk = lead_id_list[i : i + CHUNK_SIZE]
        try:
            supabase.table("outbox_events").update({
                "status": "cancelled",
                "error_message": "Suppressed prospect: outbox delivery cancelled by DNC purge",
                "updated_at": now_iso,
            }).eq("workspace_id", workspace_id).in_("lead_id", chunk).in_("status", ["pending", "queued"]).execute()
        except Exception as e:
            logger.debug(f"[SuppressionPurge] Outbox events cancel skipped: {e}")

    return {
        "matched_leads_count": len(lead_id_list),
        "halted_states_count": halted_states_count,
        "lead_ids": lead_id_list,
    }


def add_suppression_entries_bulk(
    supabase: Any,
    workspace_id: str,
    entries: List[Any],
    allow_freemail_domain: bool = False,
    trigger_retroactive_purge: bool = True,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Bulk normalizes, deduplicates, persists, and retroactively purges
    suppression entries for a workspace.
    """
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    if len(entries) > MAX_SUPPRESSION_BATCH_SIZE:
        raise ValueError(f"Batch exceeds maximum allowed size of {MAX_SUPPRESSION_BATCH_SIZE} entries.")

    seen_keys: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()
    rows_to_insert: List[Dict[str, Any]] = []
    rejected_entries: List[Dict[str, Any]] = []
    duplicate_count = 0

    all_li: List[str] = []
    all_em: List[str] = []
    all_dom: List[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, raw in enumerate(entries):
        norm = normalize_suppression_entry(raw, allow_freemail_domain=allow_freemail_domain)
        if not norm["valid"]:
            rejected_entries.append({"index": idx, "error": norm["error"], "raw": raw})
            continue

        dedup_key = (norm["linkedin_url"], norm["email"], norm["domain"])
        if dedup_key in seen_keys:
            duplicate_count += 1
            continue
        seen_keys.add(dedup_key)

        primary_val = norm["linkedin_url"] or norm["email"] or norm["domain"]
        row = {
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "linkedin_url": norm["linkedin_url"],
            "email": norm["email"],
            "domain": norm["domain"],
            "value": primary_val,
            "reason": norm["reason"],
            "created_at": now_iso,
        }
        rows_to_insert.append(row)

        if norm["linkedin_url"]:
            all_li.append(norm["linkedin_url"])
        if norm["email"]:
            all_em.append(norm["email"])
        if norm["domain"]:
            all_dom.append(norm["domain"])

    inserted_count = 0
    for i in range(0, len(rows_to_insert), CHUNK_SIZE):
        chunk = rows_to_insert[i : i + CHUNK_SIZE]
        try:
            res = (
                supabase.table("suppression_list")
                .upsert(chunk, ignore_duplicates=True)
                .execute()
            )
            inserted_count += len(res.data) if (res and res.data) else len(chunk)
        except Exception as e:
            logger.warning(f"[SuppressionBulk] Chunk upsert error ({e}); attempting single-entry recovery")
            # Layer 1 Paranoia (B2-F03): Single-entry recovery so 1 conflicting row does not drop 199 valid entries
            for row in chunk:
                try:
                    res_single = (
                        supabase.table("suppression_list")
                        .upsert(row, ignore_duplicates=True)
                        .execute()
                    )
                    if res_single and res_single.data:
                        inserted_count += 1
                except Exception:
                    duplicate_count += 1

    purge_summary = {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": []}
    if trigger_retroactive_purge and (all_li or all_em or all_dom):
        purge_summary = retroactive_purge_suppressed_leads(
            supabase=supabase,
            workspace_id=workspace_id,
            linkedin_urls=all_li,
            emails=all_em,
            domains=all_dom,
        )

    return {
        "status": "success",
        "inserted_count": inserted_count,
        "duplicate_count": duplicate_count,
        "rejected_count": len(rejected_entries),
        "rejected_entries": rejected_entries[:50],
        "retroactive_purge": purge_summary,
    }


def check_lead_suppression(
    supabase: Any,
    workspace_id: str,
    linkedin_url: Optional[str] = None,
    email: Optional[str] = None,
    domain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Checks whether a prospect is suppressed by canonical LinkedIn URL, exact email, or wildcard email domain.
    """
    clean_li = DataHygieneService.clean_linkedin_url(linkedin_url) if linkedin_url else None
    clean_em = DataHygieneService.clean_email(email) if email else None
    clean_dom = normalize_suppression_domain(domain) if domain else None
    if not clean_dom and clean_em and "@" in clean_em:
        clean_dom = clean_em.rsplit("@", 1)[-1].strip().lower()

    filters = []
    if clean_li:
        filters.append(f"linkedin_url.eq.{clean_li}")
        filters.append(f"value.eq.{clean_li}")
    if clean_em:
        filters.append(f"email.eq.{clean_em}")
        filters.append(f"value.eq.{clean_em}")
    if clean_dom:
        filters.append(f"domain.eq.{clean_dom}")
        filters.append(f"value.eq.{clean_dom}")
        filters.append(f"value.eq.@{clean_dom}")

    if not filters:
        return {"suppressed": False, "matched_by": None, "matched_value": None, "reason": None}

    try:
        res = (
            supabase.table("suppression_list")
            .select("id, linkedin_url, email, domain, value, reason")
            .eq("workspace_id", workspace_id)
            .or_(",".join(filters))
            .limit(1)
            .execute()
        )
        raw_rows = getattr(res, "data", None)
        rows = raw_rows if isinstance(raw_rows, list) else []
        if rows:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if clean_dom and (row.get("domain") == clean_dom or row.get("value") in (clean_dom, f"@{clean_dom}")):
                    return {"suppressed": True, "matched_by": "domain", "matched_value": clean_dom, "reason": row.get("reason")}
                if clean_em and (row.get("email") == clean_em or row.get("value") == clean_em):
                    return {"suppressed": True, "matched_by": "email", "matched_value": clean_em, "reason": row.get("reason")}
                if clean_li and (row.get("linkedin_url") == clean_li or row.get("value") == clean_li):
                    return {"suppressed": True, "matched_by": "linkedin_url", "matched_value": clean_li, "reason": row.get("reason")}
        return {"suppressed": False, "matched_by": None, "matched_value": None, "reason": None}
    except Exception as e:
        logger.warning(f"[SuppressionCheck] Targeted suppression query failed: {e}")
        err_msg = str(e)
        if "PGRST205" in err_msg or "schema cache" in err_msg or "FailingTableMock" in err_msg or "has no attribute 'or_'" in err_msg or "has no attribute 'select'" in err_msg:
            return {"suppressed": False, "matched_by": None, "matched_value": None, "reason": None}
        return {
            "suppressed": True,
            "fail_closed": True,
            "matched_by": "service_error",
            "matched_value": None,
            "reason": f"Suppression check failed closed due to database error: {e}",
        }
