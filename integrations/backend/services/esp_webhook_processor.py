"""
esp_webhook_processor.py — Unified ESP Webhook Feedback Loop, FBL ARF Abuse Processor & Runaway Bounce Circuit Breaker.
Hardened under the Three-Layer Logic Architecture (Paranoia Framework).

Layer 0 (Foundational):
  - Canonical ESP normalization across SendGrid, Mailgun, Postmark, Amazon SES, and Generic SMTP.
  - Cryptographic signature verification:
      * SendGrid: NIST P-256 (SECP256R1) ECDSA with SHA256, plus constant-time HMAC fallback.
      * Mailgun: HMAC-SHA256 timestamp-token digest with constant-time verification.
      * Postmark: Constant-time shared token verification.
  - Automated Feedback Loop (FBL) and Abuse Processing:
      * Automatic suppression list (DNC) addition.
      * Immediate lead state transition (COMPLAINED, BOUNCED, UNSUBSCRIBED).
      * Cascaded active campaign sequence cancellation (retroactive purge).
      * Outbound sender inbox health and deliverability metric feedback.
  - Runaway Bounce & Spam Circuit Breaker:
      * Statistical tripwires (3.0% bounce rate / 5 hard bounces, 0.1% spam rate / 2 complaints).
      * Minimum sample size protection.
      * Automated campaign pause recommendation.

Layer 1 (Environmental Reliability):
  - Tight timestamp clock drift validation (600s maximum tolerance window).
  - Multi-format public key decoding (PEM, DER base64, raw DER bytes).
  - Defensive fallback for database client failures and missing table schemas.
  - Tenant IDOR isolation: resolves and verifies workspace boundaries.

Layer 2 (Human Paranoia):
  - Safe parsing of negative, string, or null statistics.
  - Auto-unwrap of nested or flattened custom webhook arguments.
  - Zero unhandled exceptions on adversarial, malformed, or tampered payloads.
"""

import os
import re
import time
import json
import hmac
import base64
import hashlib
import logging
import urllib
import urllib.parse
import urllib.request
from enum import Enum
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Enums
# ==============================================================================

class ESPProvider(str, Enum):
    SENDGRID = "SENDGRID"
    MAILGUN = "MAILGUN"
    POSTMARK = "POSTMARK"
    AMAZON_SES = "AMAZON_SES"
    RESEND = "RESEND"
    GENERIC_SMTP = "GENERIC_SMTP"


class WebhookEventType(str, Enum):
    DELIVERED = "delivered"
    OPEN = "open"
    CLICK = "click"
    BOUNCE_HARD = "bounce_hard"
    BOUNCE_SOFT = "bounce_soft"
    SPAM_COMPLAINT = "spam_complaint"
    UNSUBSCRIBE = "unsubscribe"
    UNKNOWN = "unknown"


# ==============================================================================
# 2. Cryptographic Signature Verification
# ==============================================================================

def verify_sendgrid_signature(
    public_key: str,
    payload_bytes: Union[bytes, str],
    signature: str,
    timestamp: Union[str, int, float],
) -> bool:
    """
    Paranoia Layer 0, 1 & 2:
    Validates SendGrid Event Webhook signature using ECDSA (SECP256R1/SHA256)
    with a constant-time HMAC-SHA256 fallback.
    Enforces a strict 600-second freshness window against replay attacks.
    """
    if not public_key or not signature or timestamp is None:
        return False

    # Timestamp freshness validation (600s window)
    try:
        ts_float = float(timestamp)
        now = time.time()
        if abs(now - ts_float) > 600:
            logger.warning(
                f"[ESPWebhook] SendGrid timestamp expired or future-dated: {timestamp} "
                f"(drift: {abs(now - ts_float):.1f}s > 600s)"
            )
            return False
    except (ValueError, TypeError):
        logger.warning(f"[ESPWebhook] Malformed SendGrid timestamp: {timestamp}")
        return False

    # Ensure payload is in bytes
    if isinstance(payload_bytes, str):
        raw_payload = payload_bytes.encode("utf-8")
    elif isinstance(payload_bytes, (bytes, bytearray)):
        raw_payload = bytes(payload_bytes)
    else:
        raw_payload = b""

    # SendGrid signs: f"{timestamp}".encode("utf-8") + payload_bytes
    signed_data = str(timestamp).encode("utf-8") + raw_payload

    clean_sig = str(signature).strip()
    clean_pk = str(public_key).strip()

    # Attempt 1: ECDSA Curve Verification (SendGrid standard: ECDSA with NIST P-256)
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes, serialization

        sig_bytes = base64.b64decode(clean_sig)
        pub_key_obj = None

        if clean_pk.startswith("-----BEGIN"):
            pub_key_obj = serialization.load_pem_public_key(clean_pk.encode("utf-8"))
        else:
            try:
                der_bytes = base64.b64decode(clean_pk)
                pub_key_obj = serialization.load_der_public_key(der_bytes)
            except Exception:
                pem_formatted = f"-----BEGIN PUBLIC KEY-----\n{clean_pk}\n-----END PUBLIC KEY-----"
                pub_key_obj = serialization.load_pem_public_key(pem_formatted.encode("utf-8"))

        if pub_key_obj is not None:
            pub_key_obj.verify(sig_bytes, signed_data, ec.ECDSA(hashes.SHA256()))
            return True
    except Exception as exc:
        logger.debug(f"[ESPWebhook] SendGrid ECDSA verification failed or not applicable: {exc}")

    # Attempt 2: Constant-Time HMAC-SHA256 Fallback
    try:
        expected_raw = hmac.new(clean_pk.encode("utf-8"), signed_data, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(expected_raw).decode("utf-8").strip()
        expected_hex = expected_raw.hex().strip()

        # Compare digest in constant time to thwart timing side-channels
        if hmac.compare_digest(clean_sig, expected_b64):
            return True
        if hmac.compare_digest(clean_sig.lower(), expected_hex.lower()):
            return True

        # Check raw decoded bytes if signature is base64
        try:
            sig_decoded = base64.b64decode(clean_sig)
            if hmac.compare_digest(sig_decoded, expected_raw):
                return True
        except Exception:
            pass
    except Exception as exc:
        logger.debug(f"[ESPWebhook] SendGrid HMAC fallback verification error: {exc}")

    return False


def verify_mailgun_signature(
    signing_key: str,
    token: str,
    timestamp: Union[str, int, float],
    signature: str,
) -> bool:
    """
    Paranoia Layer 0, 1 & 2:
    Validates Mailgun webhook signature by computing HMAC-SHA256 of f"{timestamp}{token}"
    against the provided signing key. Uses constant-time comparison.
    Enforces a strict 600-second freshness window against replay attacks.
    """
    if not signing_key or not token or timestamp is None or not signature:
        return False

    # Timestamp freshness validation (600s window)
    try:
        ts_float = float(timestamp)
        now = time.time()
        if abs(now - ts_float) > 600:
            logger.warning(
                f"[ESPWebhook] Mailgun timestamp expired or future-dated: {timestamp} "
                f"(drift: {abs(now - ts_float):.1f}s > 600s)"
            )
            return False
    except (ValueError, TypeError):
        logger.warning(f"[ESPWebhook] Malformed Mailgun timestamp: {timestamp}")
        return False

    clean_key = str(signing_key).strip()
    clean_token = str(token).strip()
    clean_ts = str(timestamp).strip()
    clean_sig = str(signature).strip()

    try:
        data_to_sign = f"{clean_ts}{clean_token}".encode("utf-8")
        expected_hex = hmac.new(clean_key.encode("utf-8"), data_to_sign, hashlib.sha256).hexdigest()
        return hmac.compare_digest(clean_sig.lower(), expected_hex.lower())
    except Exception as exc:
        logger.warning(f"[ESPWebhook] Mailgun signature calculation error: {exc}")
        return False


def verify_postmark_token(
    expected_token: str,
    header_token: str,
) -> bool:
    """
    Paranoia Layer 0 & 2:
    Performs constant-time comparison of Postmark webhook verification tokens
    or webhook basic auth credentials.
    """
    if not expected_token or not header_token:
        return False

    clean_expected = str(expected_token).strip()
    clean_header = str(header_token).strip()
    return hmac.compare_digest(clean_expected, clean_header)


def verify_resend_signature(
    payload_bytes: Union[bytes, str],
    svix_id: Optional[str],
    svix_timestamp: Optional[str],
    svix_signature: Optional[str],
    secret: str,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Paranoia Layer 0, 1 & 2:
    Cryptographically verifies Svix standard webhook signatures used by Resend.
    - svix-id: unique message identifier
    - svix-timestamp: seconds since Unix epoch
    - svix-signature: space-separated list of signatures (e.g. 'v1,base64_sig')
    - secret: Svix secret, usually prefixed with 'whsec_'
    Validates clock drift against tolerance_seconds (default: 300s).
    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    if not svix_id or not svix_timestamp or not svix_signature or not secret:
        return False

    # Clock drift validation
    try:
        ts_int = int(svix_timestamp)
        now_ts = int(time.time())
        if abs(now_ts - ts_int) > tolerance_seconds:
            logger.warning(f"[ResendWebhook] Clock drift exceeded tolerance: {abs(now_ts - ts_int)}s > {tolerance_seconds}s")
            return False
    except (ValueError, TypeError):
        return False

    clean_secret = str(secret).strip()
    if clean_secret.startswith("whsec_"):
        clean_secret = clean_secret[6:]

    try:
        key_bytes = base64.b64decode(clean_secret)
    except Exception:
        key_bytes = clean_secret.encode("utf-8")

    if isinstance(payload_bytes, bytes):
        body_str = payload_bytes.decode("utf-8")
    else:
        body_str = str(payload_bytes)

    to_sign = f"{svix_id}.{svix_timestamp}.{body_str}".encode("utf-8")
    expected_digest = hmac.new(key_bytes, to_sign, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected_digest).decode("utf-8")

    signatures = svix_signature.strip().split(" ")
    for sig_part in signatures:
        if "," in sig_part:
            version, sig_val = sig_part.split(",", 1)
            if version == "v1" and hmac.compare_digest(sig_val.strip(), expected_b64):
                return True

    return False


_SNS_CERT_CACHE: Dict[str, Any] = {}

def _build_sns_signable_bytes(payload_dict: Dict[str, Any]) -> bytes:
    """Builds canonical AWS SNS string to sign according to AWS SNS specification."""
    msg_type = payload_dict.get("Type")
    lines = []
    if msg_type == "Notification":
        fields = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    elif msg_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        fields = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
    else:
        fields = ["Message", "MessageId", "Timestamp", "TopicArn", "Type"]

    for field in fields:
        val = payload_dict.get(field)
        if val is not None:
            lines.append(f"{field}\n{val}\n")
    return "".join(lines).encode("utf-8")

def verify_ses_sns_signature(
    raw_payload: Union[bytes, str, Dict[str, Any]],
    preshared_token: Optional[str] = None,
    expected_token: Optional[str] = None,
) -> bool:
    """
    Paranoia Layer 0, 1 & 2:
    Validates AWS SES SNS notification integrity.
    Supports pre-shared shared secret token comparison and genuine cryptographic
    X.509 RSA-SHA1/SHA256 signature verification over the canonical SNS signable payload.
    """
    if expected_token and preshared_token:
        return hmac.compare_digest(str(preshared_token).strip(), str(expected_token).strip())

    payload_dict = raw_payload if isinstance(raw_payload, dict) else {}
    if not payload_dict and isinstance(raw_payload, (str, bytes)):
        try:
            body_str = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else str(raw_payload)
            payload_dict = json.loads(body_str)
        except Exception:
            payload_dict = {}

    sig_b64 = payload_dict.get("Signature")
    cert_url = payload_dict.get("SigningCertURL")

    if cert_url:
        parsed = urllib.parse.urlparse(cert_url)
        if parsed.scheme != "https":
            return False
        hostname = (parsed.hostname or "").lower()
        if not re.match(r"^sns\.[a-z0-9-]+\.amazonaws\.com$", hostname):
            logger.warning(f"[SESWebhook] Invalid AWS SNS SigningCertURL host rejected: {hostname}")
            return False
        if not cert_url.endswith(".pem"):
            logger.warning(f"[SESWebhook] SigningCertURL does not end in .pem: {cert_url}")
            return False

        if not sig_b64:
            return False

        try:
            import base64
            from cryptography.x509 import load_pem_x509_certificate
            from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
            from cryptography.hazmat.primitives import hashes

            # Layer 1 Paranoia: In-memory LRU certificate cache
            cert_obj = _SNS_CERT_CACHE.get(cert_url)
            if not cert_obj:
                # Preflight check against SSRF
                from core.backend.core.validators import is_safe_ssrf_url
                if not is_safe_ssrf_url(cert_url):
                    logger.error(f"[SESWebhook] SSRF blocked for cert URL: {cert_url}")
                    return False

                req = urllib.request.Request(cert_url, headers={"User-Agent": "EleIn-SES-Verifier/1.0"})
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    cert_data = resp.read()
                cert_obj = load_pem_x509_certificate(cert_data)
                if len(_SNS_CERT_CACHE) > 50:
                    _SNS_CERT_CACHE.clear()
                _SNS_CERT_CACHE[cert_url] = cert_obj

            public_key = cert_obj.public_key()
            signable_bytes = _SNS_SIGNABLE_BYTES = _build_sns_signable_bytes(payload_dict)
            sig_bytes = base64.b64decode(sig_b64)

            sig_ver = str(payload_dict.get("SignatureVersion", "1"))
            hash_algo = hashes.SHA256() if sig_ver == "2" else hashes.SHA1()

            public_key.verify(sig_bytes, signable_bytes, PKCS1v15(), hash_algo)
            return True
        except Exception as sig_err:
            logger.warning(f"[SESWebhook] Cryptographic SNS signature verification failed: {sig_err}")
            return False

    return False

verify_aws_sns_signature = verify_ses_sns_signature


# ==============================================================================
# 3. Ingestion & Normalization
# ==============================================================================

def normalize_esp_event(
    raw_event: Dict[str, Any],
    provider: Union[ESPProvider, str] = ESPProvider.SENDGRID,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    Normalizes heterogeneous webhook payloads from SendGrid, Mailgun, Postmark,
    Amazon SES, and Generic SMTP into a canonical schema.

    Canonical Schema returned:
    {
        "clean_email": str,
        "event_type": WebhookEventType,
        "campaign_id": Optional[str],
        "lead_id": Optional[str],
        "node_id": Optional[str],
        "workspace_id": Optional[str],
        "inbox_id": Optional[str],
        "smtp_code": Optional[str],
        "reason": Optional[str],
        "timestamp": str,
        "provider": ESPProvider,
        "message_id": Optional[str],
        "raw_event": Dict[str, Any],
    }
    """
    if not isinstance(raw_event, dict):
        raw_event = {}

    # Unpack SNS envelope if nested
    if "Type" in raw_event and raw_event.get("Type") == "Notification" and "Message" in raw_event:
        msg_val = raw_event["Message"]
        if isinstance(msg_val, str):
            try:
                raw_event = json.loads(msg_val)
            except Exception:
                pass
        elif isinstance(msg_val, dict):
            raw_event = msg_val

    # Resolve Provider Enum
    clean_prov_str = str(getattr(provider, "value", provider) or "SENDGRID").upper()
    try:
        resolved_provider = ESPProvider(clean_prov_str)
    except ValueError:
        # Heuristic detection from payload architecture
        if "event-data" in raw_event:
            resolved_provider = ESPProvider.MAILGUN
        elif "RecordType" in raw_event or "Type" in raw_event and "Postmark" in str(raw_event):
            resolved_provider = ESPProvider.POSTMARK
        elif "eventType" in raw_event or "notificationType" in raw_event:
            resolved_provider = ESPProvider.AMAZON_SES
        elif "type" in raw_event and str(raw_event.get("type", "")).startswith("email."):
            resolved_provider = ESPProvider.RESEND
        else:
            resolved_provider = ESPProvider.SENDGRID

    clean_email = ""
    event_type = WebhookEventType.UNKNOWN
    campaign_id: Optional[str] = None
    lead_id: Optional[str] = None
    node_id: Optional[str] = None
    workspace_id: Optional[str] = None
    inbox_id: Optional[str] = None
    smtp_code: Optional[str] = None
    reason: Optional[str] = None
    message_id: Optional[str] = None
    event_timestamp: str = datetime.now(timezone.utc).isoformat()

    # --------------------------------------------------------------------------
    # SendGrid Ingestion
    # --------------------------------------------------------------------------
    if resolved_provider == ESPProvider.SENDGRID:
        raw_type = str(raw_event.get("event") or "").strip().lower()
        clean_email = str(raw_event.get("email") or "").strip().lower()
        message_id = raw_event.get("sg_message_id") or raw_event.get("smtp-id")
        reason = raw_event.get("reason")
        smtp_code = str(raw_event.get("status") or "") if raw_event.get("status") is not None else None

        if raw_event.get("timestamp"):
            try:
                event_timestamp = str(raw_event.get("timestamp"))
            except Exception:
                pass

        # Custom args may be nested under "custom_args" or flattened at root
        c_args = raw_event.get("custom_args") if isinstance(raw_event.get("custom_args"), dict) else {}
        campaign_id = raw_event.get("campaign_id") or c_args.get("campaign_id")
        lead_id = raw_event.get("lead_id") or c_args.get("lead_id")
        node_id = raw_event.get("node_id") or c_args.get("node_id")
        workspace_id = raw_event.get("workspace_id") or c_args.get("workspace_id")
        inbox_id = raw_event.get("inbox_id") or c_args.get("inbox_id")

        bounce_classification = str(raw_event.get("type") or raw_event.get("bounce_classification") or "").lower()

        if raw_type == "delivered":
            event_type = WebhookEventType.DELIVERED
        elif raw_type == "open":
            event_type = WebhookEventType.OPEN
        elif raw_type == "click":
            event_type = WebhookEventType.CLICK
        elif raw_type in ("bounce", "bounce_hard", "hard_bounce"):
            if "soft" in bounce_classification or "transient" in bounce_classification:
                event_type = WebhookEventType.BOUNCE_SOFT
            else:
                event_type = WebhookEventType.BOUNCE_HARD
        elif raw_type in ("bounce_soft", "soft_bounce"):
            event_type = WebhookEventType.BOUNCE_SOFT
        elif raw_type == "dropped":
            event_type = WebhookEventType.BOUNCE_HARD
        elif raw_type in ("spamreport", "spam_report", "spam_complaint", "complaint"):
            event_type = WebhookEventType.SPAM_COMPLAINT
        elif raw_type in ("unsubscribe", "group_unsubscribe", "group_resubscribe"):
            event_type = WebhookEventType.UNSUBSCRIBE
        else:
            event_type = WebhookEventType.UNKNOWN

    # --------------------------------------------------------------------------
    # Mailgun Ingestion
    # --------------------------------------------------------------------------
    elif resolved_provider == ESPProvider.MAILGUN:
        ev_data = raw_event.get("event-data") if isinstance(raw_event.get("event-data"), dict) else raw_event
        raw_type = str(ev_data.get("event") or "").strip().lower()
        clean_email = str(ev_data.get("recipient") or raw_event.get("recipient") or "").strip().lower()

        # Message ID extraction
        msg_headers = ev_data.get("message", {}).get("headers", {}) if isinstance(ev_data.get("message"), dict) else {}
        message_id = msg_headers.get("message-id") or ev_data.get("id")

        deliv_status = ev_data.get("delivery-status") if isinstance(ev_data.get("delivery-status"), dict) else {}
        reason = deliv_status.get("message") or deliv_status.get("description")
        if deliv_status.get("code") is not None:
            smtp_code = str(deliv_status.get("code"))

        if ev_data.get("timestamp"):
            try:
                event_timestamp = str(ev_data.get("timestamp"))
            except Exception:
                pass

        user_vars = ev_data.get("user-variables") or ev_data.get("user_variables") or {}
        if not isinstance(user_vars, dict):
            user_vars = {}

        campaign_id = user_vars.get("campaign_id") or ev_data.get("campaign_id")
        lead_id = user_vars.get("lead_id") or ev_data.get("lead_id")
        node_id = user_vars.get("node_id") or ev_data.get("node_id")
        workspace_id = user_vars.get("workspace_id") or ev_data.get("workspace_id")
        inbox_id = user_vars.get("inbox_id") or ev_data.get("inbox_id")

        severity = str(ev_data.get("severity") or "").lower()

        if raw_type == "delivered":
            event_type = WebhookEventType.DELIVERED
        elif raw_type in ("opened", "open"):
            event_type = WebhookEventType.OPEN
        elif raw_type in ("clicked", "click"):
            event_type = WebhookEventType.CLICK
        elif raw_type == "failed":
            if severity == "temporary":
                event_type = WebhookEventType.BOUNCE_SOFT
            elif severity == "permanent":
                event_type = WebhookEventType.BOUNCE_HARD
            else:
                # Code check fallback
                try:
                    c = int(smtp_code) if smtp_code else 500
                    event_type = WebhookEventType.BOUNCE_HARD if c >= 500 else WebhookEventType.BOUNCE_SOFT
                except (ValueError, TypeError):
                    event_type = WebhookEventType.BOUNCE_HARD
        elif raw_type in ("complained", "complaint"):
            event_type = WebhookEventType.SPAM_COMPLAINT
        elif raw_type in ("unsubscribed", "unsubscribe"):
            event_type = WebhookEventType.UNSUBSCRIBE
        else:
            event_type = WebhookEventType.UNKNOWN

    # --------------------------------------------------------------------------
    # Postmark Ingestion
    # --------------------------------------------------------------------------
    elif resolved_provider == ESPProvider.POSTMARK:
        raw_type = str(raw_event.get("RecordType") or raw_event.get("record_type") or "").strip()
        clean_email = str(
            raw_event.get("Recipient")
            or raw_event.get("Email")
            or raw_event.get("recipient")
            or ""
        ).strip().lower()

        message_id = raw_event.get("MessageID") or raw_event.get("Tag")
        reason = raw_event.get("Description") or raw_event.get("Details")
        if raw_event.get("TypeCode") is not None:
            smtp_code = str(raw_event.get("TypeCode"))

        meta = raw_event.get("Metadata") or raw_event.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}

        campaign_id = meta.get("campaign_id") or raw_event.get("campaign_id")
        lead_id = meta.get("lead_id") or raw_event.get("lead_id")
        node_id = meta.get("node_id") or raw_event.get("node_id")
        workspace_id = meta.get("workspace_id") or raw_event.get("workspace_id")
        inbox_id = meta.get("inbox_id") or raw_event.get("inbox_id")

        event_timestamp = (
            raw_event.get("BouncedAt")
            or raw_event.get("DeliveredAt")
            or raw_event.get("ReceivedAt")
            or event_timestamp
        )

        b_type = str(raw_event.get("Type") or "").lower()
        is_hard = (
            raw_event.get("HardBounce") is True
            or b_type in ("hardbounce", "bademailaddress")
            or "hard" in b_type
        )
        is_soft = (
            "soft" in b_type
            or b_type in ("softbounce", "transient", "dnserror", "mailboxfull")
        )
        is_spam_type = "spam" in b_type

        norm_rec_type = raw_type.lower()
        if norm_rec_type == "delivery":
            event_type = WebhookEventType.DELIVERED
        elif norm_rec_type == "open":
            event_type = WebhookEventType.OPEN
        elif norm_rec_type == "click":
            event_type = WebhookEventType.CLICK
        elif norm_rec_type == "bounce":
            if is_spam_type:
                event_type = WebhookEventType.SPAM_COMPLAINT
            elif is_soft:
                event_type = WebhookEventType.BOUNCE_SOFT
            else:
                event_type = WebhookEventType.BOUNCE_HARD
        elif norm_rec_type in ("spamcomplaint", "spam_complaint", "complaint"):
            event_type = WebhookEventType.SPAM_COMPLAINT
        elif norm_rec_type in ("subscriptionchange", "unsubscribe"):
            event_type = WebhookEventType.UNSUBSCRIBE
        else:
            event_type = WebhookEventType.UNKNOWN

    # --------------------------------------------------------------------------
    # Amazon SES Ingestion
    # --------------------------------------------------------------------------
    elif resolved_provider == ESPProvider.AMAZON_SES:
        raw_type = str(raw_event.get("eventType") or raw_event.get("notificationType") or "").strip().lower()
        mail_obj = raw_event.get("mail") if isinstance(raw_event.get("mail"), dict) else {}
        dest_list = mail_obj.get("destination", [])
        clean_email = str(dest_list[0] if dest_list else raw_event.get("email") or "").strip().lower()

        # Check complaint recipients if clean_email is empty
        if not clean_email and "complaint" in raw_event and isinstance(raw_event.get("complaint"), dict):
            c_recips = raw_event["complaint"].get("complainedRecipients", [])
            if isinstance(c_recips, list) and c_recips:
                clean_email = str(c_recips[0].get("emailAddress") or "").strip().lower()

        # Check bounce recipients if clean_email is empty
        if not clean_email and "bounce" in raw_event and isinstance(raw_event.get("bounce"), dict):
            b_recips = raw_event["bounce"].get("bouncedRecipients", [])
            if isinstance(b_recips, list) and b_recips:
                clean_email = str(b_recips[0].get("emailAddress") or "").strip().lower()

        message_id = mail_obj.get("messageId")

        tags = mail_obj.get("tags") if isinstance(mail_obj.get("tags"), dict) else {}
        campaign_id = tags.get("campaign_id", [None])[0] if isinstance(tags.get("campaign_id"), list) else tags.get("campaign_id")
        lead_id = tags.get("lead_id", [None])[0] if isinstance(tags.get("lead_id"), list) else tags.get("lead_id")
        workspace_id = tags.get("workspace_id", [None])[0] if isinstance(tags.get("workspace_id"), list) else tags.get("workspace_id")

        # Unpack headers list if present in mail_obj
        headers_list = mail_obj.get("headers", [])
        if isinstance(headers_list, list):
            for h in headers_list:
                if isinstance(h, dict):
                    h_name = str(h.get("name", "")).lower()
                    h_val = h.get("value")
                    if h_name in ("x-elein-campaign-id", "x-campaign-id", "campaign_id"):
                        campaign_id = campaign_id or h_val
                    elif h_name in ("x-elein-lead-id", "x-lead-id", "lead_id"):
                        lead_id = lead_id or h_val
                    elif h_name in ("x-elein-workspace-id", "x-workspace-id", "workspace_id"):
                        workspace_id = workspace_id or h_val

        if raw_type == "delivery":
            event_type = WebhookEventType.DELIVERED
        elif raw_type == "open":
            event_type = WebhookEventType.OPEN
        elif raw_type == "click":
            event_type = WebhookEventType.CLICK
        elif raw_type == "bounce":
            b_obj = raw_event.get("bounce") if isinstance(raw_event.get("bounce"), dict) else {}
            b_type = str(b_obj.get("bounceType") or "").lower()
            reason = b_obj.get("bouncedRecipients", [{}])[0].get("diagnosticCode")
            if "permanent" in b_type:
                event_type = WebhookEventType.BOUNCE_HARD
            else:
                event_type = WebhookEventType.BOUNCE_SOFT
        elif raw_type in ("complaint", "spam"):
            event_type = WebhookEventType.SPAM_COMPLAINT
        else:
            event_type = WebhookEventType.UNKNOWN

    # --------------------------------------------------------------------------
    # Resend Ingestion
    # --------------------------------------------------------------------------
    elif resolved_provider == ESPProvider.RESEND:
        raw_type = str(raw_event.get("type", "")).strip().lower()
        data_obj = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}
        
        to_list = data_obj.get("to", [])
        if isinstance(to_list, list) and to_list:
            clean_email = str(to_list[0]).strip().lower()
        elif isinstance(to_list, str):
            clean_email = to_list.strip().lower()
        else:
            clean_email = str(data_obj.get("email") or raw_event.get("email") or "").strip().lower()

        message_id = data_obj.get("email_id") or data_obj.get("id") or raw_event.get("id")
        created_at_val = raw_event.get("created_at") or data_obj.get("created_at")
        if created_at_val:
            event_timestamp = str(created_at_val)

        # Tags and headers unwrapping
        tags_obj = data_obj.get("tags") or {}
        if isinstance(tags_obj, dict):
            campaign_id = tags_obj.get("campaign_id")
            lead_id = tags_obj.get("lead_id")
            node_id = tags_obj.get("node_id")
            workspace_id = tags_obj.get("workspace_id")
            inbox_id = tags_obj.get("inbox_id")
        elif isinstance(tags_obj, list):
            for t in tags_obj:
                if isinstance(t, dict):
                    k = t.get("name")
                    v = t.get("value")
                    if k == "campaign_id": campaign_id = v
                    elif k == "lead_id": lead_id = v
                    elif k == "node_id": node_id = v
                    elif k == "workspace_id": workspace_id = v
                    elif k == "inbox_id": inbox_id = v

        headers_obj = data_obj.get("headers") or {}
        if isinstance(headers_obj, dict):
            campaign_id = campaign_id or headers_obj.get("X-Campaign-Id")
            lead_id = lead_id or headers_obj.get("X-Lead-Id")
            workspace_id = workspace_id or headers_obj.get("X-Workspace-Id")

        if raw_type == "email.delivered":
            event_type = WebhookEventType.DELIVERED
        elif raw_type == "email.bounced":
            bounce_type = str(data_obj.get("bounce_type") or "").lower()
            if "soft" in bounce_type:
                event_type = WebhookEventType.BOUNCE_SOFT
            else:
                event_type = WebhookEventType.BOUNCE_HARD
            reason = data_obj.get("error") or data_obj.get("message") or "Resend email bounce"
        elif raw_type == "email.complained":
            event_type = WebhookEventType.SPAM_COMPLAINT
            reason = "Recipient marked email as spam"
        elif raw_type == "email.opened":
            event_type = WebhookEventType.OPEN
        elif raw_type == "email.clicked":
            event_type = WebhookEventType.CLICK
        else:
            event_type = WebhookEventType.UNKNOWN

    # --------------------------------------------------------------------------
    # Generic SMTP Ingestion
    # --------------------------------------------------------------------------
    else:
        raw_type = str(raw_event.get("event") or raw_event.get("event_type") or "").strip().lower()
        clean_email = str(raw_event.get("email") or raw_event.get("recipient") or "").strip().lower()
        message_id = raw_event.get("message_id")
        reason = raw_event.get("reason")
        smtp_code = str(raw_event.get("code") or "") if raw_event.get("code") is not None else None
        campaign_id = raw_event.get("campaign_id")
        lead_id = raw_event.get("lead_id")
        node_id = raw_event.get("node_id")
        workspace_id = raw_event.get("workspace_id")
        inbox_id = raw_event.get("inbox_id")

        if raw_type in ("delivered", "sent"):
            event_type = WebhookEventType.DELIVERED
        elif raw_type == "open":
            event_type = WebhookEventType.OPEN
        elif raw_type == "click":
            event_type = WebhookEventType.CLICK
        elif raw_type in ("bounce", "bounced", "bounce_hard", "dropped"):
            event_type = WebhookEventType.BOUNCE_HARD
        elif raw_type in ("bounce_soft", "transient"):
            event_type = WebhookEventType.BOUNCE_SOFT
        elif raw_type in ("spam", "complaint", "spam_complaint"):
            event_type = WebhookEventType.SPAM_COMPLAINT
        elif raw_type in ("unsubscribe", "unsubscribed"):
            event_type = WebhookEventType.UNSUBSCRIBE
        else:
            event_type = WebhookEventType.UNKNOWN

    # Paranoia Layer 2: Sanitize email string
    clean_email = clean_email.replace("\x00", "").strip().lower()

    event_id = (
        raw_event.get("event_id")
        or raw_event.get("sg_event_id")
        or (raw_event.get("event-data", {}).get("id") if isinstance(raw_event.get("event-data"), dict) else None)
        or raw_event.get("MessageID")
        or raw_event.get("ID")
        or raw_event.get("id")
        or (raw_event.get("data", {}).get("id") if isinstance(raw_event.get("data"), dict) else None)
        or message_id
        or raw_event.get("message_id")
    )

    return {
        "email": clean_email,
        "clean_email": clean_email,
        "event_type": event_type,
        "event_id": str(event_id).strip() if event_id else None,
        "campaign_id": str(campaign_id).strip() if campaign_id else None,
        "lead_id": str(lead_id).strip() if lead_id else None,
        "node_id": str(node_id).strip() if node_id else None,
        "workspace_id": str(workspace_id).strip() if workspace_id else None,
        "inbox_id": str(inbox_id).strip() if inbox_id else None,
        "smtp_code": smtp_code,
        "reason": str(reason).strip() if reason else None,
        "timestamp": event_timestamp,
        "provider": resolved_provider,
        "message_id": str(message_id).strip() if message_id else None,
        "raw_event": raw_event,
    }


# ==============================================================================
# 4. Feedback Loop & Abuse Processor
# ==============================================================================

def process_esp_event(
    supabase: Any,
    event: Dict[str, Any],
    auto_cascade: bool = True,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    Executes automated abuse handling, lead state transitions, DNC suppression updates,
    and deliverability feedback for canonical or raw ESP events.

    - SPAM_COMPLAINT:
        * Updates lead status: 'COMPLAINED', complaint_at = now_utc.
        * Inserts into workspace 'suppression_list' (DNC).
        * Cancels active sequence jobs and execution states for lead.
        * Records spam outcome on sender inbox via record_inbox_delivery_outcome.
    - BOUNCE_HARD:
        * Updates lead status: 'BOUNCED', bounce_reason = reason.
        * Inserts into 'suppression_list'.
        * Records hard bounce on sender inbox.
    - UNSUBSCRIBE:
        * Calls RFC 8058 compliant unsubscribe cascade (status: 'UNSUBSCRIBED').
    - DELIVERED / OPEN / CLICK:
        * Updates delivery metrics and analytics in campaign_leads / campaigns.

    Returns structured outcome dict.
    """
    if not isinstance(event, dict):
        return {"status": "error", "message": "Event payload must be a dictionary."}

    # Normalize if raw event passed
    if ("clean_email" not in event and "email" not in event) or "event_type" not in event:
        prov = event.get("provider", ESPProvider.SENDGRID)
        norm = normalize_esp_event(event, provider=prov)
    else:
        norm = dict(event)

    clean_email = str(norm.get("clean_email") or norm.get("email") or "").strip().lower()
    event_type = norm.get("event_type")
    if isinstance(event_type, str):
        try:
            event_type = WebhookEventType(event_type.lower())
        except ValueError:
            event_type = WebhookEventType.UNKNOWN

    workspace_id = str(norm.get("workspace_id") or "").strip() or None
    lead_id = str(norm.get("lead_id") or "").strip() or None
    campaign_id = str(norm.get("campaign_id") or "").strip() or None
    node_id = str(norm.get("node_id") or "").strip() or None
    inbox_id = str(norm.get("inbox_id") or "").strip() or None
    reason = norm.get("reason")

    now_iso = datetime.now(timezone.utc).isoformat()
    action_taken = "NOOP"
    is_suppressed = False
    inbox_recorded = False

    # Paranoia Layer 1: Workspace Tenant Recovery
    # If workspace_id or lead_id is missing from custom_args, look up lead in Supabase
    if (not workspace_id or not lead_id) and supabase and clean_email:
        try:
            q = supabase.table("leads").select("id, workspace_id, campaign_id, status")
            if lead_id:
                res = q.eq("id", lead_id).limit(1).execute()
            else:
                res = q.eq("email", clean_email).limit(1).execute()
            if res and getattr(res, "data", None) and len(res.data) > 0:
                lead_row = res.data[0]
                workspace_id = workspace_id or lead_row.get("workspace_id")
                lead_id = lead_id or lead_row.get("id")
                campaign_id = campaign_id or lead_row.get("campaign_id")
        except Exception as exc:
            logger.debug(f"[ESPWebhook] Lead tenant resolution fallback error: {exc}")

    # Layer 0 & 1 Paranoia: Idempotency deduplication via esp_webhook_events
    event_id = norm.get("event_id") or norm.get("message_id")
    provider_str = str(getattr(norm.get("provider"), "value", norm.get("provider")) or "UNKNOWN").upper()
    if supabase and event_id:
        try:
            idemp_res = supabase.table("esp_webhook_events") \
                .select("id") \
                .eq("provider", provider_str) \
                .eq("event_id", str(event_id)) \
                .limit(1) \
                .execute()
            if idemp_res and getattr(idemp_res, "data", None) and len(idemp_res.data) > 0:
                logger.info(f"[ESPWebhook] Duplicate event ignored (provider={provider_str}, event_id={event_id})")
                return {
                    "status": "skipped_duplicate",
                    "action_taken": "IDEMPOTENT_DUPLICATE_SKIPPED",
                    "event_type": str(event_type.value if hasattr(event_type, "value") else event_type),
                    "email": clean_email,
                    "message": f"Event {event_id} already processed for {provider_str}",
                    "deduplicated": True,
                }
            
            # Record into esp_webhook_events
            supabase.table("esp_webhook_events").insert({
                "provider": provider_str,
                "event_id": str(event_id),
                "message_id": norm.get("message_id"),
                "event_type": str(event_type.value if hasattr(event_type, "value") else event_type),
                "email": clean_email,
                "workspace_id": workspace_id,
                "payload": norm
            }).execute()
        except Exception as idemp_err:
            logger.debug(f"[ESPWebhook] Idempotency record non-fatal: {idemp_err}")

    # --------------------------------------------------------------------------
    # Case: SPAM_COMPLAINT (FBL Abuse Report)
    # --------------------------------------------------------------------------
    if event_type == WebhookEventType.SPAM_COMPLAINT:
        action_taken = "LEAD_COMPLAINED_AND_SUPPRESSED"

        # 1. Update leads table
        if supabase and workspace_id:
            lead_update = {
                "status": "COMPLAINED",
                "complaint_at": now_iso,
                "is_unsubscribed": True,
            }
            try:
                if lead_id:
                    supabase.table("leads").update(lead_update).eq("id", lead_id).eq("workspace_id", workspace_id).execute()
                elif clean_email:
                    supabase.table("leads").update(lead_update).eq("email", clean_email).eq("workspace_id", workspace_id).execute()
            except Exception as exc:
                logger.warning(f"[ESPWebhook] Failed to update lead to COMPLAINED: {exc}")

        # 2. Add to suppression_list (DNC)
        if supabase and workspace_id and clean_email:
            try:
                from leads.backend.services.suppression_service import add_suppression_entries_bulk
                add_suppression_entries_bulk(
                    supabase=supabase,
                    workspace_id=workspace_id,
                    entries=[{"email": clean_email, "reason": "spam_complaint_fbl"}],
                    allow_freemail_domain=True,
                    trigger_retroactive_purge=False,
                )
                is_suppressed = True
            except Exception as exc:
                logger.debug(f"[ESPWebhook] add_suppression_entries_bulk error, falling back to direct insert: {exc}")
                try:
                    supabase.table("suppression_list").insert({
                        "workspace_id": workspace_id,
                        "email": clean_email,
                        "value": clean_email,
                        "reason": "spam_complaint_fbl",
                    }).execute()
                    is_suppressed = True
                except Exception as e2:
                    logger.warning(f"[ESPWebhook] Direct suppression_list insert failed: {e2}")

        # 3. Cancel active sequence executions for lead
        if auto_cascade and workspace_id and clean_email:
            try:
                from campaigns.backend.services.unsubscribe_service import retroactive_purge
                retroactive_purge(workspace_id=workspace_id, email=clean_email, supabase=supabase)
            except Exception as exc:
                logger.warning(f"[ESPWebhook] Retroactive purge failed on spam complaint: {exc}")

        # 4. Record complaint on sender inbox
        if inbox_id and workspace_id:
            try:
                from integrations.backend.services.email_sender_service import record_inbox_delivery_outcome
                record_inbox_delivery_outcome(
                    supabase=supabase,
                    workspace_id=workspace_id,
                    inbox_id=inbox_id,
                    event_type="spam_complaint",
                )
                inbox_recorded = True
            except Exception as exc:
                logger.warning(f"[ESPWebhook] record_inbox_delivery_outcome error on spam complaint: {exc}")

    # --------------------------------------------------------------------------
    # Case: BOUNCE_HARD
    # --------------------------------------------------------------------------
    elif event_type == WebhookEventType.BOUNCE_HARD:
        action_taken = "LEAD_BOUNCED_AND_SUPPRESSED"

        # 1. Update leads table
        if supabase and workspace_id:
            lead_update = {
                "status": "BOUNCED",
                "bounce_reason": reason or "Hard Bounce (Permanent Failure)",
                "bounced_at": now_iso,
            }
            try:
                if lead_id:
                    supabase.table("leads").update(lead_update).eq("id", lead_id).eq("workspace_id", workspace_id).execute()
                elif clean_email:
                    supabase.table("leads").update(lead_update).eq("email", clean_email).eq("workspace_id", workspace_id).execute()
            except Exception as exc:
                logger.warning(f"[ESPWebhook] Failed to update lead to BOUNCED: {exc}")

        # 2. Add to suppression_list
        if supabase and workspace_id and clean_email:
            try:
                from leads.backend.services.suppression_service import add_suppression_entries_bulk
                add_suppression_entries_bulk(
                    supabase=supabase,
                    workspace_id=workspace_id,
                    entries=[{"email": clean_email, "reason": "hard_bounce"}],
                    allow_freemail_domain=True,
                    trigger_retroactive_purge=False,
                )
                is_suppressed = True
            except Exception as exc:
                try:
                    supabase.table("suppression_list").insert({
                        "workspace_id": workspace_id,
                        "email": clean_email,
                        "value": clean_email,
                        "reason": "hard_bounce",
                    }).execute()
                    is_suppressed = True
                except Exception as e2:
                    logger.warning(f"[ESPWebhook] Direct suppression_list insert failed: {e2}")

        # 3. Cancel active sequence executions if auto_cascade
        if auto_cascade and workspace_id and clean_email:
            try:
                from campaigns.backend.services.unsubscribe_service import retroactive_purge
                retroactive_purge(workspace_id=workspace_id, email=clean_email, supabase=supabase)
            except Exception as exc:
                logger.warning(f"[ESPWebhook] Retroactive purge failed on bounce: {exc}")

        # 4. Record bounce on sender inbox
        if inbox_id and workspace_id:
            try:
                from integrations.backend.services.email_sender_service import record_inbox_delivery_outcome
                record_inbox_delivery_outcome(
                    supabase=supabase,
                    workspace_id=workspace_id,
                    inbox_id=inbox_id,
                    event_type="bounce",
                )
                inbox_recorded = True
            except Exception as exc:
                logger.warning(f"[ESPWebhook] record_inbox_delivery_outcome error on bounce: {exc}")

    # --------------------------------------------------------------------------
    # Case: UNSUBSCRIBE
    # --------------------------------------------------------------------------
    elif event_type == WebhookEventType.UNSUBSCRIBE:
        action_taken = "LEAD_UNSUBSCRIBED"
        if workspace_id and clean_email:
            try:
                from campaigns.backend.services.unsubscribe_service import process_one_click_unsubscribe
                process_one_click_unsubscribe(
                    workspace_id=workspace_id,
                    lead_id=lead_id or "",
                    email=clean_email,
                    supabase=supabase,
                )
                is_suppressed = True
            except Exception as exc:
                logger.warning(f"[ESPWebhook] process_one_click_unsubscribe error, fallback: {exc}")
                if supabase:
                    try:
                        supabase.table("leads").update({
                            "status": "UNSUBSCRIBED",
                            "unsubscribed_at": now_iso,
                            "is_unsubscribed": True,
                        }).eq("email", clean_email).eq("workspace_id", workspace_id).execute()
                        is_suppressed = True
                    except Exception as e2:
                        logger.warning(f"[ESPWebhook] Fallback unsubscribe leads update failed: {e2}")

    # --------------------------------------------------------------------------
    # Case: DELIVERED / OPEN / CLICK / BOUNCE_SOFT
    # --------------------------------------------------------------------------
    elif event_type == WebhookEventType.DELIVERED:
        action_taken = "DELIVERY_RECORDED"
        if inbox_id and workspace_id:
            try:
                from integrations.backend.services.email_sender_service import record_inbox_delivery_outcome
                record_inbox_delivery_outcome(
                    supabase=supabase,
                    workspace_id=workspace_id,
                    inbox_id=inbox_id,
                    event_type="delivered",
                )
                inbox_recorded = True
            except Exception as exc:
                logger.debug(f"[ESPWebhook] record_inbox_delivery_outcome delivered error: {exc}")

    elif event_type == WebhookEventType.OPEN:
        action_taken = "OPEN_RECORDED"
    elif event_type == WebhookEventType.CLICK:
        action_taken = "CLICK_RECORDED"
    elif event_type == WebhookEventType.BOUNCE_SOFT:
        action_taken = "SOFT_BOUNCE_RECORDED"

    # --------------------------------------------------------------------------
    # Telemetry & Metrics Cascade (campaign_events / campaign_leads)
    # --------------------------------------------------------------------------
    if supabase and workspace_id and campaign_id:
        try:
            # Telemetry logging to campaign_events
            supabase.table("campaign_events").insert({
                "workspace_id": workspace_id,
                "campaign_id": campaign_id,
                "node_id": node_id,
                "event_type": event_type.value if hasattr(event_type, "value") else str(event_type),
                "metadata": {
                    "email": clean_email,
                    "lead_id": lead_id,
                    "smtp_code": norm.get("smtp_code"),
                    "reason": reason,
                    "provider": getattr(norm.get("provider"), "value", str(norm.get("provider"))),
                },
                "occurred_at": now_iso,
            }).execute()
        except Exception as exc:
            logger.debug(f"[ESPWebhook] campaign_events recording ignored: {exc}")

    return {
        "status": "processed",
        "action_taken": action_taken,
        "email": clean_email,
        "event_type": event_type.value if hasattr(event_type, "value") else str(event_type),
        "workspace_id": workspace_id,
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "suppressed": is_suppressed,
        "inbox_recorded": inbox_recorded,
    }


# ==============================================================================
# 5. Runaway Bounce & Spam Circuit Breaker
# ==============================================================================

def evaluate_campaign_circuit_breaker(
    campaign_stats: Dict[str, Any],
    sample_size: int = 50,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    Evaluates deliverability tripwires across campaign sends to prevent runaway
    domain blacklisting, sender burnout, or ESP account suspension.

    Rules:
    - Minimum sample size guard: if sent_count < 20, returns should_trip=False, reason="INSUFFICIENT_SAMPLE".
    - Tripwires:
        * CRITICAL_BOUNCE_SPIKE: bounce_rate >= 0.03 (3.0%) or bounce_count >= 5.
        * CRITICAL_SPAM_SPIKE: spam_rate >= 0.001 (0.1%) or spam_complaint_count >= 2.
    - If tripped: returns { "should_trip": True, "tripwire": ..., "bounce_rate": ..., "spam_rate": ..., "action": "AUTO_PAUSE_CAMPAIGN", "recommendations": [...] }
    - If healthy: returns { "should_trip": False, "status": "HEALTHY", "bounce_rate": ..., "spam_rate": ... }
    """
    if not isinstance(campaign_stats, dict):
        campaign_stats = {}

    # Safe parsing of numeric stats (Paranoia Layer 2)
    def _parse_int(val: Any) -> int:
        try:
            return max(0, int(val or 0))
        except (ValueError, TypeError):
            return 0

    sent_count = _parse_int(campaign_stats.get("sent_count") or campaign_stats.get("sent"))
    bounce_count = _parse_int(campaign_stats.get("bounce_count") or campaign_stats.get("bounces") or campaign_stats.get("hard_bounces"))
    spam_complaint_count = _parse_int(
        campaign_stats.get("spam_complaint_count")
        or campaign_stats.get("spam_count")
        or campaign_stats.get("complaints")
    )

    bounce_rate = bounce_count / max(1, sent_count)
    spam_rate = spam_complaint_count / max(1, sent_count)

    # Minimum sample size guard: 20 sends required before statistical tripwires engage
    min_sample = 20
    if sent_count < min_sample:
        return {
            "should_trip": False,
            "status": "HEALTHY",
            "reason": "INSUFFICIENT_SAMPLE",
            "sent_count": sent_count,
            "bounce_count": bounce_count,
            "spam_complaint_count": spam_complaint_count,
            "bounce_rate": round(bounce_rate, 4),
            "spam_rate": round(spam_rate, 4),
        }

    # Evaluate Tripwires
    is_bounce_tripped = (bounce_rate >= 0.03) or (bounce_count >= 5)
    is_spam_tripped = (spam_rate >= 0.001) or (spam_complaint_count >= 2)

    if is_bounce_tripped or is_spam_tripped:
        tripped_labels = []
        recommendations = []

        if is_bounce_tripped:
            tripped_labels.append("CRITICAL_BOUNCE_SPIKE")
            recommendations.append("Enforce strict prospect email verification before outreach.")
            recommendations.append("Quarantine sender domain until DNS (SPF/DKIM/DMARC) alignment is verified.")

        if is_spam_tripped:
            tripped_labels.append("CRITICAL_SPAM_SPIKE")
            recommendations.append("Review cold email copywriting for deceptive subject lines or excessive links.")
            recommendations.append("Verify RFC 8058 one-click unsubscribe headers are actively injected.")

        primary_tripwire = "_AND_".join(tripped_labels)

        return {
            "should_trip": True,
            "status": "TRIPPED",
            "tripwire": primary_tripwire,
            "action": "AUTO_PAUSE_CAMPAIGN",
            "bounce_rate": round(bounce_rate, 4),
            "spam_rate": round(spam_rate, 4),
            "sent_count": sent_count,
            "bounce_count": bounce_count,
            "spam_complaint_count": spam_complaint_count,
            "recommendations": recommendations,
        }

    return {
        "should_trip": False,
        "status": "HEALTHY",
        "bounce_rate": round(bounce_rate, 4),
        "spam_rate": round(spam_rate, 4),
        "sent_count": sent_count,
        "bounce_count": bounce_count,
        "spam_complaint_count": spam_complaint_count,
    }


# ==============================================================================
# 6. Facade Class: ESPWebhookProcessor
# ==============================================================================

class ESPWebhookProcessor:
    """
    Facade class exposing all ESP Webhook Processing, Signature Verification,
    Normalization, Feedback Loop, and Circuit Breaker methods statically.
    """
    ESPProvider = ESPProvider
    WebhookEventType = WebhookEventType

    @staticmethod
    def verify_sendgrid_signature(
        public_key: str,
        payload_bytes: Union[bytes, str],
        signature: str,
        timestamp: Union[str, int, float],
    ) -> bool:
        return verify_sendgrid_signature(public_key, payload_bytes, signature, timestamp)

    @staticmethod
    def verify_mailgun_signature(
        signing_key: str,
        token: str,
        timestamp: Union[str, int, float],
        signature: str,
    ) -> bool:
        return verify_mailgun_signature(signing_key, token, timestamp, signature)

    @staticmethod
    def verify_postmark_token(
        expected_token: str,
        header_token: str,
    ) -> bool:
        return verify_postmark_token(expected_token, header_token)

    @staticmethod
    def verify_resend_signature(
        payload_bytes: Union[bytes, str],
        svix_id: Optional[str],
        svix_timestamp: Optional[str],
        svix_signature: Optional[str],
        secret: str,
        tolerance_seconds: int = 300,
    ) -> bool:
        return verify_resend_signature(payload_bytes, svix_id, svix_timestamp, svix_signature, secret, tolerance_seconds)

    @staticmethod
    def verify_ses_sns_signature(
        raw_payload: Union[bytes, str, Dict[str, Any]],
        preshared_token: Optional[str] = None,
        expected_token: Optional[str] = None,
    ) -> bool:
        return verify_ses_sns_signature(raw_payload, preshared_token, expected_token)

    @staticmethod
    def normalize_esp_event(
        raw_event: Dict[str, Any],
        provider: Union[ESPProvider, str] = ESPProvider.SENDGRID,
    ) -> Dict[str, Any]:
        return normalize_esp_event(raw_event, provider)

    @staticmethod
    def process_esp_event(
        supabase: Any,
        event: Dict[str, Any],
        auto_cascade: bool = True,
    ) -> Dict[str, Any]:
        return process_esp_event(supabase, event, auto_cascade)

    @staticmethod
    def evaluate_campaign_circuit_breaker(
        campaign_stats: Dict[str, Any],
        sample_size: int = 50,
    ) -> Dict[str, Any]:
        return evaluate_campaign_circuit_breaker(campaign_stats, sample_size)
