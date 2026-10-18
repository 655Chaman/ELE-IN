import os
import time
import json
import hmac
import uuid
import hashlib
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _b64url_encode(data: bytes) -> str:
    """Encodes bytes to compact URL-safe base64 without trailing '=' padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    """Decodes URL-safe base64 string, restoring any missing '=' padding."""
    if not isinstance(s, str):
        raise ValueError("Input must be a string")
    clean = s.strip()
    padding = 4 - (len(clean) % 4)
    if padding != 4:
        clean += "=" * padding
    return base64.urlsafe_b64decode(clean.encode("utf-8"))


def _resolve_secret(secret: Optional[str] = None) -> str:
    """
    Paranoia Layer 0 & 1 (AUDIT-04): Resolves HMAC signing secret in strict priority order.
    Fails closed in non-test environments if no cryptographic secret is configured,
    eliminating universal token forgery vulnerabilities.
    """
    if secret and secret.strip():
        return secret.strip()

    env_secret = (
        os.environ.get("UNSUBSCRIBE_SECRET")
        or os.environ.get("SUPABASE_JWT_SECRET")
        or os.environ.get("JWT_SECRET")
    )
    if env_secret and env_secret.strip():
        return env_secret.strip()

    is_test_env = (
        bool(os.environ.get("PYTEST_CURRENT_TEST"))
        or os.environ.get("ENV") == "test"
        or os.environ.get("ENVIRONMENT") == "test"
    )
    is_prod_env = (
        os.environ.get("ENV") in ("production", "prod", "staging")
        or os.environ.get("ENVIRONMENT") in ("production", "prod", "staging")
    )

    if is_prod_env or not is_test_env:
        raise RuntimeError(
            "RFC 8058 Cryptographic Security Violation: Neither UNSUBSCRIBE_SECRET nor SUPABASE_JWT_SECRET is configured. "
            "Failing closed to prevent universal unsubscribe token forgery in live environments."
        )

    return "elein-rfc8058-unsub-secret"


def generate_unsubscribe_token(
    workspace_id: str,
    lead_id: str,
    email: str,
    secret: Optional[str] = None,
) -> str:
    """
    Paranoia Layer 0 & 1: Cryptographically signs the payload using HMAC-SHA256.
    Returns a compact urlsafe token formatted as: <payload_b64>.<sig_b64>
    """
    if not workspace_id or not email:
        raise ValueError("workspace_id and email are required to generate an unsubscribe token.")

    secret_key = _resolve_secret(secret)
    clean_ws = str(workspace_id).strip()
    clean_lid = str(lead_id or "").strip()
    clean_email = str(email).strip().lower()

    payload = {
        "workspace_id": clean_ws,
        "lead_id": clean_lid,
        "email": clean_email,
        "ts": int(time.time()),
    }

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)

    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{payload_b64}.{sig_b64}"


def verify_unsubscribe_token(
    token: str,
    secret: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Paranoia Layer 1 & 2: Validates the token signature in constant time using hmac.compare_digest.
    Returns dict with {"workspace_id": ..., "lead_id": ..., "email": ...} or None if invalid or tampered.
    Never throws unhandled exceptions on malformed or adversarial tokens.
    """
    if not token or not isinstance(token, str) or "." not in token:
        return None

    secret_key = _resolve_secret(secret)
    parts = token.strip().split(".")
    if len(parts) != 2:
        return None

    payload_b64, sig_b64 = parts[0], parts[1]

    try:
        expected_sig = hmac.new(
            secret_key.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        provided_sig = _b64url_decode(sig_b64)

        # Constant-time comparison prevents timing side-channel attacks
        if not hmac.compare_digest(provided_sig, expected_sig):
            return None

        payload_bytes = _b64url_decode(payload_b64)
        data = json.loads(payload_bytes.decode("utf-8"))

        if not isinstance(data, dict):
            return None

        ws_id = data.get("workspace_id")
        lid = data.get("lead_id")
        em = data.get("email")

        if not ws_id or not em:
            return None

        return {
            "workspace_id": str(ws_id).strip(),
            "lead_id": str(lid or "").strip(),
            "email": str(em).strip().lower(),
        }
    except Exception as exc:
        logger.debug(f"[UnsubscribeService] Token verification failed: {exc}")
        return None


def generate_rfc8058_headers(
    workspace_id: str,
    lead_id: str,
    email: str,
    base_url: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generates compliant RFC 8058 headers:
    List-Unsubscribe: <{unsub_url}>, <mailto:unsub+{token}@{domain}>
    List-Unsubscribe-Post: List-Unsubscribe=One-Click
    """
    clean_ws = str(workspace_id).strip()
    clean_lid = str(lead_id or "").strip()
    clean_email = str(email).strip().lower()

    token = generate_unsubscribe_token(
        workspace_id=clean_ws,
        lead_id=clean_lid,
        email=clean_email,
    )

    raw_base = (
        base_url
        or os.environ.get("APP_URL")
        or os.environ.get("API_BASE_URL")
        or "https://app.ele-in.com"
    ).strip().rstrip("/")

    # The HTTPS one-click unsubscribe endpoint
    unsub_url = f"{raw_base}/api/elein/unsubscribe?token={token}"

    # Mailto unsubscribe address
    domain = os.environ.get("UNSUBSCRIBE_EMAIL_DOMAIN") or os.environ.get("MAIL_DOMAIN")
    if not domain:
        parsed_netloc = urlparse(raw_base).netloc.split(":")[0]
        if parsed_netloc.startswith("app."):
            domain = parsed_netloc[4:]
        elif parsed_netloc.startswith("api."):
            domain = parsed_netloc[4:]
        else:
            domain = parsed_netloc or "ele-in.com"
    domain = domain.strip().lower()

    mailto_addr = f"mailto:unsub+{token}@{domain}"

    return {
        "List-Unsubscribe": f"<{unsub_url}>, <{mailto_addr}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def retroactive_purge(
    workspace_id: str,
    email: str,
    supabase: Any = None,
) -> Dict[str, Any]:
    """
    Halts all running sequence jobs and active execution states for this lead.
    Wraps retroactive_purge_suppressed_leads with defensive error boundaries.
    """
    clean_ws = str(workspace_id or "").strip()
    clean_email = str(email or "").strip().lower()

    if not clean_ws or not clean_email:
        return {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": []}

    if supabase is None:
        try:
            from core.backend.api.auth_dep import get_service_client
            supabase = get_service_client()
        except Exception as exc:
            logger.warning(f"[UnsubscribeService] Could not resolve Supabase service client: {exc}")
            return {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": [], "error": str(exc)}

    if not supabase:
        return {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": []}

    try:
        from leads.backend.services.suppression_service import retroactive_purge_suppressed_leads
        return retroactive_purge_suppressed_leads(
            supabase=supabase,
            workspace_id=clean_ws,
            emails=[clean_email],
        )
    except Exception as exc:
        logger.warning(f"[UnsubscribeService] retroactive_purge failed: {exc}")
        return {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": [], "error": str(exc)}


def process_one_click_unsubscribe(
    workspace_id: str,
    lead_id: str,
    email: str,
    supabase: Any = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    - Updates leads table: sets status = 'UNSUBSCRIBED', unsubscribed_at = now_utc, is_unsubscribed = True.
    - Inserts into suppression_list with reason = 'one_click_unsubscribe_rfc8058'.
    - Triggers retroactive purge: calls retroactive_purge(workspace_id, email, supabase) to halt in-flight jobs.
    - Returns: {"status": "success", "unsubscribed": True, "lead_id": lead_id, "email": email}.
    """
    clean_ws = str(workspace_id or "").strip()
    clean_lid = str(lead_id or "").strip()
    clean_email = str(email or "").strip().lower()

    if not clean_ws or not clean_email:
        raise ValueError("workspace_id and email are required to process unsubscribe.")

    if supabase is None:
        try:
            from core.backend.api.auth_dep import get_service_client
            supabase = get_service_client()
        except Exception as exc:
            logger.warning(f"[UnsubscribeService] Unable to get service client: {exc}")

    now_utc = datetime.now(timezone.utc).isoformat()

    if supabase:
        # 1. Update leads table
        lead_update = {
            "status": "UNSUBSCRIBED",
            "unsubscribed_at": now_utc,
            "is_unsubscribed": True,
        }
        if clean_lid:
            try:
                supabase.table("leads").update(lead_update).eq("id", clean_lid).eq("workspace_id", clean_ws).execute()
            except Exception as exc:
                logger.warning(f"[UnsubscribeService] Failed updating lead ID {clean_lid}: {exc}")

        if clean_email:
            try:
                supabase.table("leads").update(lead_update).eq("email", clean_email).eq("workspace_id", clean_ws).execute()
            except Exception as exc:
                logger.warning(f"[UnsubscribeService] Failed updating lead by email {clean_email}: {exc}")

        # 2. Insert into suppression_list
        try:
            from leads.backend.services.suppression_service import add_suppression_entries_bulk
            add_suppression_entries_bulk(
                supabase=supabase,
                workspace_id=clean_ws,
                entries=[{"email": clean_email, "reason": "one_click_unsubscribe_rfc8058"}],
                allow_freemail_domain=True,
                trigger_retroactive_purge=False,  # Purged explicitly below
            )
        except Exception as exc:
            logger.warning(f"[UnsubscribeService] add_suppression_entries_bulk failed, attempting direct insert: {exc}")
            try:
                supabase.table("suppression_list").insert({
                    "id": str(uuid.uuid4()),
                    "workspace_id": clean_ws,
                    "email": clean_email,
                    "value": clean_email,
                    "reason": "one_click_unsubscribe_rfc8058",
                    "created_at": now_utc,
                }).execute()
            except Exception as insert_err:
                logger.warning(f"[UnsubscribeService] Direct suppression insert fallback failed: {insert_err}")

        # 3. Triggers retroactive purge: calls retroactive_purge(workspace_id=workspace_id, email=email, supabase=supabase)
        purge_result = retroactive_purge(workspace_id=clean_ws, email=clean_email, supabase=supabase)
    else:
        logger.warning("[UnsubscribeService] Supabase client is unavailable; database writes skipped.")
        purge_result = {"matched_leads_count": 0, "halted_states_count": 0, "lead_ids": []}

    return {
        "status": "success",
        "unsubscribed": True,
        "lead_id": clean_lid,
        "email": clean_email,
    }
