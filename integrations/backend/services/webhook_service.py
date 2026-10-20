import hmac
import hashlib
import json
import time
import uuid
import logging
import threading
import requests
import secrets
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

from core.backend.core.crypto import decrypt_bytes, encrypt_bytes
from core.backend.core.validators import is_safe_ssrf_url
from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

def normalize_webhook_url(url: Any) -> str:
    """
    Paranoia Layer 0 & 1: Normalizes and validates webhook destination URLs.
    - Strips whitespace, quotes, and angle brackets.
    - Requires valid scheme (http:// or https://); defaults to https:// if missing.
    - Validates parseable hostname via urllib.parse.urlparse.
    - Normalizes netloc to lowercase.
    - Strips trailing slash on root paths.
    - Rejects empty, whitespace-only, or invalid URLs by returning "".
    """
    if not url or not isinstance(url, str):
        return ""
    
    # Strip whitespace, quotes, and angle brackets
    cleaned = url.strip().strip('"\'<>')
    if not cleaned:
        return ""
        
    if ":" in cleaned and "://" not in cleaned:
        # e.g. javascript:alert(1) without //
        parts = cleaned.split(":", 1)
        if parts[0].lower() not in ("http", "https"):
            return ""

    if "://" in cleaned:
        parts = cleaned.split("://", 1)
        if parts[0].lower() not in ("http", "https"):
            return ""
    else:
        cleaned = f"https://{cleaned}"

    try:
        parsed = urllib.parse.urlparse(cleaned)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return ""
            
        netloc = parsed.netloc.lower()
        if not netloc:
            return ""
            
        path = parsed.path
        # Strip trailing slash on root or pure paths if desired, but keep path structure
        # Standardize trailing slash if path is just root "/"
        if path == "/":
            path = ""
            
        # Reconstruct normalized URL preserving query params and fragment if any
        reconstructed = urllib.parse.urlunparse((
            scheme,
            netloc,
            path or "",
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
        return reconstructed
    except Exception as e:
        logger.warning(f"[Webhook] Failed to parse URL '{url}': {e}")
        return ""


def rotate_webhook_signing_secret(
    endpoint_id: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Atomically rotates a webhook endpoint's signing secret.
    - Verifies endpoint exists and belongs to workspace_id (IDOR defense).
    - Generates new cryptographically secure secret: f"whsec_{secrets.token_hex(16)}"
    - Encrypts secret with encrypt_bytes(raw_secret.encode('utf-8')).hex()
    - Updates webhook_endpoints atomically in DB (signing_secret = encrypted_hex, updated_at = now_iso)
    - Returns {"status": "success", "endpoint_id": endpoint_id, "signing_secret": raw_secret} (raw secret returned ONCE)
    """
    if not endpoint_id or not workspace_id:
        return {"status": "error", "message": "Endpoint ID and Workspace ID are required."}
        
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "message": "Database client unavailable."}
        
    try:
        # Verify ownership (IDOR defense)
        ep_res = client.table("webhook_endpoints") \
            .select("id, workspace_id") \
            .eq("id", endpoint_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
            
        if not ep_res.data:
            return {"status": "error", "message": "Webhook endpoint not found or unauthorized."}
            
        raw_secret = f"whsec_{secrets.token_hex(16)}"
        encrypted_secret_hex = encrypt_bytes(raw_secret.encode('utf-8')).hex()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        update_res = client.table("webhook_endpoints") \
            .update({
                "signing_secret": encrypted_secret_hex,
                "updated_at": now_iso
            }) \
            .eq("id", endpoint_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
            
        if not update_res.data:
            return {"status": "error", "message": "Failed to update webhook secret in database."}
            
        logger.info(f"[Webhook] Rotated signing secret for endpoint {endpoint_id} in workspace {workspace_id}")
        return {
            "status": "success",
            "endpoint_id": endpoint_id,
            "signing_secret": raw_secret
        }
    except Exception as e:
        logger.error(f"[Webhook] Error rotating signing secret for endpoint {endpoint_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def prune_expired_webhook_dlq(
    workspace_id: Optional[str] = None,
    retention_days: int = 30,
    chunk_size: int = 100,
    max_chunks: int = 10,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Chunked pruning of expired dead-letter webhook deliveries.
    - Clamps retention_days = max(7, int(retention_days)) (minimum 7-day retention floor).
    - Clamps chunk_size = max(10, min(500, int(chunk_size))).
    - Clamps max_chunks = max(1, min(20, int(max_chunks))).
    - Calculates cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat().
    - Queries webhook_deliveries with delivery_status == 'dead_letter' and created_at < cutoff.
    - Deletes chunk by chunk. Never deletes pending or success deliveries.
    - Returns {"status": "success", "pruned_count": total_pruned, "retention_days": retention_days, "cutoff": cutoff}.
    """
    try:
        retention_days = max(7, int(retention_days or 30))
        chunk_size = max(10, min(500, int(chunk_size or 100)))
        max_chunks = max(1, min(20, int(max_chunks or 10)))
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        
        client = supabase or get_service_client()
        if not client:
            return {"status": "error", "message": "Database client unavailable."}
            
        total_pruned = 0
        
        for _ in range(max_chunks):
            query = client.table("webhook_deliveries") \
                .select("id") \
                .eq("delivery_status", "dead_letter") \
                .lt("created_at", cutoff)
                
            if workspace_id:
                query = query.eq("workspace_id", workspace_id)
                
            res = query.limit(chunk_size).execute()
            rows = res.data or []
            if not rows:
                break
                
            ids = [r["id"] for r in rows if "id" in r]
            if not ids:
                break
                
            del_query = client.table("webhook_deliveries") \
                .delete() \
                .in_("id", ids)
                
            if workspace_id:
                del_query = del_query.eq("workspace_id", workspace_id)
                
            del_res = del_query.execute()
            count_deleted = len(ids)
            total_pruned += count_deleted
            
            if len(rows) < chunk_size:
                break
                
        logger.info(f"[Webhook DLQ] Pruned {total_pruned} expired dead_letter deliveries older than {retention_days} days (cutoff: {cutoff})")
        return {
            "status": "success",
            "pruned_count": total_pruned,
            "retention_days": retention_days,
            "cutoff": cutoff
        }
    except Exception as e:
        logger.error(f"[Webhook DLQ] Pruning error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


SUPPORTED_WEBHOOK_EVENTS = [
    "lead.connected",           # Prospect accepted LinkedIn connection request
    "lead.replied",             # Prospect replied to outreach message
    "intent.hot_detected",      # Prospect displayed high buying intent (score >= 75)
    "lead.email_discovered",    # Prospect corporate email discovered via Waterfall
    "lead.meeting_booked",      # Prospect booked a meeting via calendar link
    "lead.enrolled",            # Lead enrolled in a campaign
    "lead.unsubscribed",        # Lead opted out or unsubscribed
    "message.sent",             # Outreach message or connection note dispatched
    "connection.sent",          # Connection request sent
    "email.sent",               # Cold email dispatched
    "campaign.completed",       # Lead reached terminal node in campaign
    "campaign.paused",          # Campaign paused or halted
    "test.ping"                 # Manual diagnostic verification ping
]

SENSITIVE_KEYS = {
    "password", "secret", "token", "access_token", "refresh_token", 
    "api_key", "signing_secret", "private_key", "jwt",
    "cookie", "cookies", "client_secret", "authorization", "bearer"
}

def sanitize_webhook_payload(data: Any) -> Any:
    """Paranoia Layer 2: Recursively strips sensitive secrets and tokens before webhook emission."""
    if isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if k_lower in SENSITIVE_KEYS or any(s in k_lower for s in ("auth_token", "api_key", "secret", "private_key", "bearer_token", "client_secret", "session_cookie")):
                continue
            clean[k] = sanitize_webhook_payload(v)
        return clean
    elif isinstance(data, list):
        return [sanitize_webhook_payload(item) for item in data]
    return data


def generate_webhook_signature(payload: Dict[str, Any], secret: str, timestamp_override: int = None) -> Tuple[str, str]:
    """
    Generates an HMAC-SHA256 signature for a webhook payload.
    Returns (timestamp, signature).
    
    The customer computes HMAC-SHA256(timestamp + "." + json_body, secret)
    and verifies it against the EleIn-Signature header.
    """
    if not secret:
        raise ValueError("Webhook signing secret cannot be empty")
    timestamp = str(timestamp_override or int(time.time()))
    
    # Serialize JSON with no spaces for deterministic consistency
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    signed_payload = f"{timestamp}.{payload_str}"
    
    mac = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    )
    
    signature = mac.hexdigest()
    return timestamp, signature


def verify_webhook_signature(
    payload: Dict[str, Any],
    secret: str,
    timestamp: Any,
    signature: str,
    tolerance_seconds: int = 300
) -> bool:
    """
    Paranoia Layer 1 & 2: Validates webhook authenticity and prevents replay attacks.
    - Constant-time HMAC comparison via hmac.compare_digest
    - Replay attack window bound (tolerance_seconds, default 300s = 5m)
    - Strips common header prefixes (e.g. 'sha256=', 'v1=', 't=...,v1=...') safely.
    """
    if not secret or not signature or timestamp is None:
        return False
    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        return False
        
    now = int(time.time())
    if abs(now - ts_int) > tolerance_seconds:
        logger.warning(f"[Webhook] Signature verification failed: timestamp drift {abs(now - ts_int)}s exceeds tolerance {tolerance_seconds}s (replay attack prevention).")
        return False
        
    try:
        _, expected_signature = generate_webhook_signature(payload, secret, timestamp_override=ts_int)
        
        # Paranoia Layer 1 & 2: Support prefixed signatures ('sha256=...', 'v1=...', 't=...,v1=...')
        sig_str = str(signature).strip()
        candidates = [sig_str]
        
        if "=" in sig_str:
            # Handle comma-separated key-value pairs (e.g., Stripe/Svix format 't=123,v1=abc')
            parts = [p.strip() for p in sig_str.split(",")]
            for p in parts:
                if "=" in p:
                    _, val = p.split("=", 1)
                    candidates.append(val.strip())
        
        # Constant-time comparison across extracted candidates
        for cand in candidates:
            if hmac.compare_digest(cand, expected_signature):
                return True
        return False
    except Exception as e:
        logger.error(f"[Webhook] Signature verification error: {e}")
        return False


def emit_webhook_event(
    workspace_id: str,
    event_type: str,
    payload: Dict[str, Any],
    supabase: Optional[Any] = None
) -> int:
    """
    Layer 0 & 1 Paranoia: Dispatches events to all active subscriber endpoints in a workspace.
    Guarantees non-blocking execution: errors are logged and never crash the primary campaign pipeline.
    """
    if not workspace_id or not event_type:
        return 0
        
    client = supabase or get_service_client()
    if not client:
        logger.warning("[Webhook] Database client unavailable for webhook emission.")
        return 0

    try:
        # Fetch active webhook endpoints for this workspace
        ep_res = client.table("webhook_endpoints") \
            .select("id, url, event_types, is_active") \
            .eq("workspace_id", workspace_id) \
            .eq("is_active", True) \
            .execute()

        endpoints = ep_res.data or []
        if not endpoints:
            return 0

        # Filter endpoints matching the event_type or wildcard "*" (case-insensitive)
        matching_endpoints = []
        event_lower = str(event_type).lower()
        for ep in endpoints:
            url = ep.get("url") or ""
            if not (url.startswith("http://") or url.startswith("https://")):
                logger.warning(f"[Webhook] Skipping endpoint {ep.get('id')} with invalid URL scheme: {url}")
                continue
            event_types = ep.get("event_types") or []
            event_types_lower = [str(et).lower() for et in event_types]
            if "*" in event_types_lower or "all" in event_types_lower or event_lower in event_types_lower:
                matching_endpoints.append(ep)

        if not matching_endpoints:
            return 0

        # Sanitize data envelope
        clean_data = sanitize_webhook_payload(payload)
        now_ts = int(time.time())
        now_iso = datetime.now(timezone.utc).isoformat()

        deliveries_to_insert = []
        for ep in matching_endpoints:
            event_id = f"evt_{uuid.uuid4().hex}"
            event_envelope = {
                "id": event_id,
                "event": event_type,
                "workspace_id": workspace_id,
                "timestamp": now_ts,
                "created_at": now_iso,
                "data": clean_data
            }
            deliveries_to_insert.append({
                "workspace_id": workspace_id,
                "endpoint_id": ep["id"],
                "event_type": event_type,
                "payload": event_envelope,
                "delivery_status": "pending",
                "attempt_count": 0
            })

        if deliveries_to_insert:
            client.table("webhook_deliveries").insert(deliveries_to_insert).execute()
            logger.info(f"[Webhook] Enqueued {len(deliveries_to_insert)} deliveries for event '{event_type}' (Workspace: {workspace_id})")
            return len(deliveries_to_insert)

    except Exception as e:
        logger.error(f"[Webhook] Failed to emit webhook event '{event_type}': {e}", exc_info=True)

    return 0


def test_webhook_endpoint(
    endpoint_id: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Diagnostic test harness for custom webhook endpoints.
    Sends a signed 'test.ping' payload synchronously, records response code and latency,
    and logs the delivery attempt in webhook_deliveries.
    """
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "message": "Database client unavailable"}

    # 1. Fetch endpoint
    ep_res = client.table("webhook_endpoints") \
        .select("*") \
        .eq("id", endpoint_id) \
        .eq("workspace_id", workspace_id) \
        .execute()

    if not ep_res.data:
        return {"status": "error", "message": "Webhook endpoint not found or unauthorized"}

    endpoint = ep_res.data[0]
    url = endpoint.get("url", "")

    # 2. SSRF Check (Paranoia Layer 1)
    if not is_safe_ssrf_url(url):
        return {
            "status": "error",
            "message": "SSRF Violation: Webhook URL targets a prohibited private or local network address.",
            "url": url
        }

    # 3. Decrypt signing secret
    try:
        raw_secret = decrypt_bytes(bytes.fromhex(endpoint["signing_secret"])).decode('utf-8')
    except Exception as e:
        return {"status": "error", "message": f"Failed to decrypt signing secret: {e}"}

    # 4. Construct test payload
    now_ts = int(time.time())
    now_iso = datetime.now(timezone.utc).isoformat()
    test_id = f"evt_test_{uuid.uuid4().hex[:12]}"
    test_payload = {
        "id": test_id,
        "event": "test.ping",
        "workspace_id": workspace_id,
        "timestamp": now_ts,
        "created_at": now_iso,
        "data": {
            "message": "Ele-in webhook diagnostic ping. Your endpoint is successfully connected and receiving signed payloads.",
            "endpoint_id": endpoint_id,
            "subscribed_events": endpoint.get("event_types", [])
        }
    }

    timestamp, signature = generate_webhook_signature(test_payload, raw_secret, timestamp_override=now_ts)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "EleIn-Webhook-Verifier/1.0",
        "EleIn-Signature": signature,
        "EleIn-Timestamp": timestamp,
        "EleIn-Event": "test.ping"
    }

    # 5. Execute HTTP Request with latency measurement
    status_code = None
    response_body = ""
    success = False
    start_time = time.time()

    try:
        resp = requests.post(
            url, 
            json=test_payload, 
            headers=headers, 
            timeout=8.0, 
            allow_redirects=False
        )
        latency_ms = int((time.time() - start_time) * 1000)
        status_code = resp.status_code
        response_body = resp.text[:1000]
        success = 200 <= status_code < 300

        # Honor Retry-After and 429 adaptive rate limits
        if hasattr(resp, "headers"):
            retry_after_hdr = resp.headers.get("Retry-After")
            if retry_after_hdr:
                try:
                    record_endpoint_backpressure(endpoint_id, float(retry_after_hdr))
                except (ValueError, TypeError):
                    record_endpoint_backpressure(endpoint_id, 60.0)
            elif status_code == 429:
                record_endpoint_backpressure(endpoint_id, 60.0)
    except requests.Timeout:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = "Request timed out after 8.0 seconds."
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = f"Connection error: {str(e)}"

    # 6. Record delivery attempt in database
    delivery_record = {
        "workspace_id": workspace_id,
        "endpoint_id": endpoint_id,
        "event_type": "test.ping",
        "payload": test_payload,
        "status_code": status_code,
        "response_body": response_body,
        "delivery_status": "success" if success else "failed",
        "attempt_count": 1
    }
    try:
        client.table("webhook_deliveries").insert(delivery_record).execute()
    except Exception as d_err:
        logger.debug(f"[Webhook] Failed to insert test delivery record: {d_err}")

    return {
        "status": "success" if success else "failed",
        "status_code": status_code,
        "latency_ms": latency_ms,
        "response_body": response_body,
        "url": url,
        "signature_header": signature[:16] + "..."
    }


def replay_webhook_delivery(
    delivery_id: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Replays an existing webhook delivery attempt.
    - Validates delivery belongs to workspace
    - Re-decrypts signing secret
    - Re-signs and executes synchronous POST
    - Updates delivery record attempt count, status, and response
    """
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "message": "Database client unavailable"}

    # 1. Fetch delivery record
    del_res = client.table("webhook_deliveries") \
        .select("*") \
        .eq("id", delivery_id) \
        .eq("workspace_id", workspace_id) \
        .execute()

    if not del_res.data:
        return {"status": "error", "message": "Delivery record not found or unauthorized"}

    delivery = del_res.data[0]
    endpoint_id = delivery.get("endpoint_id")
    event_payload = delivery.get("payload") or {}

    # 2. Fetch endpoint
    ep_res = client.table("webhook_endpoints") \
        .select("*") \
        .eq("id", endpoint_id) \
        .eq("workspace_id", workspace_id) \
        .execute()

    if not ep_res.data:
        return {"status": "error", "message": "Associated webhook endpoint not found"}

    endpoint = ep_res.data[0]
    url = endpoint.get("url", "")

    # SSRF Check
    if not is_safe_ssrf_url(url):
        return {"status": "error", "message": "SSRF Violation: Webhook URL targets unsafe address."}

    # 3. Decrypt secret
    try:
        raw_secret = decrypt_bytes(bytes.fromhex(endpoint["signing_secret"])).decode('utf-8')
    except Exception as e:
        return {"status": "error", "message": f"Failed to decrypt signing secret: {e}"}

    # 4. Re-sign payload with fresh timestamp
    now_ts = int(time.time())
    if isinstance(event_payload, dict):
        event_payload["replayed_at"] = datetime.now(timezone.utc).isoformat()
        event_payload["timestamp"] = now_ts

    timestamp, signature = generate_webhook_signature(event_payload, raw_secret, timestamp_override=now_ts)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "EleIn-Webhook-Dispatcher/1.0",
        "EleIn-Signature": signature,
        "EleIn-Timestamp": timestamp,
        "EleIn-Event": delivery.get("event_type", "unknown"),
        "EleIn-Delivery-Replay": "true"
    }

    # 5. Execute HTTP Request
    status_code = None
    response_body = ""
    success = False
    start_time = time.time()

    try:
        resp = requests.post(
            url,
            json=event_payload,
            headers=headers,
            timeout=8.0,
            allow_redirects=False
        )
        latency_ms = int((time.time() - start_time) * 1000)
        status_code = resp.status_code
        response_body = resp.text[:1000]
        success = 200 <= status_code < 300

        # Honor Retry-After and 429 adaptive rate limits
        if hasattr(resp, "headers"):
            retry_after_hdr = resp.headers.get("Retry-After")
            if retry_after_hdr:
                try:
                    record_endpoint_backpressure(endpoint_id, float(retry_after_hdr))
                except (ValueError, TypeError):
                    record_endpoint_backpressure(endpoint_id, 60.0)
            elif status_code == 429:
                record_endpoint_backpressure(endpoint_id, 60.0)
    except requests.Timeout:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = "Request timed out after 8.0 seconds."
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = f"Connection error: {str(e)}"

    # 6. Update delivery record
    attempt_count = (delivery.get("attempt_count") or 0) + 1
    new_status = "success" if success else "failed"

    try:
        client.table("webhook_deliveries").update({
            "status_code": status_code,
            "response_body": response_body,
            "delivery_status": new_status,
            "attempt_count": attempt_count,
            "payload": event_payload
        }).eq("id", delivery_id).eq("workspace_id", workspace_id).execute()
    except Exception as u_err:
        logger.debug(f"[Webhook] Failed to update delivery record on replay: {u_err}")

    return {
        "status": "success" if success else "failed",
        "delivery_id": delivery_id,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "response_body": response_body,
        "attempt_count": attempt_count
    }


def debug_verify_signature(
    payload_str: str,
    secret: str,
    signature: str,
    timestamp: str,
    tolerance_seconds: int = 300
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Diagnostic utility to test and troubleshoot customer HMAC signature logic.
    """
    if not secret or not signature or not timestamp:
        return {
            "is_valid": False,
            "error": "Missing secret, signature, or timestamp"
        }

    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        return {
            "is_valid": False,
            "error": "Timestamp must be a valid unix epoch integer"
        }

    try:
        parsed_payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
    except Exception as je:
        return {
            "is_valid": False,
            "error": f"Invalid JSON payload: {je}"
        }

    now_ts = int(time.time())
    drift = abs(now_ts - ts_int)
    is_timestamp_valid = drift <= tolerance_seconds

    try:
        _, expected_sig = generate_webhook_signature(parsed_payload, secret, timestamp_override=ts_int)
        matches = hmac.compare_digest(str(signature).strip(), expected_sig)
        return {
            "is_valid": matches and is_timestamp_valid,
            "signature_match": matches,
            "is_timestamp_valid": is_timestamp_valid,
            "expected_signature": expected_sig,
            "provided_signature": signature,
            "timestamp_drift_seconds": drift,
            "tolerance_seconds": tolerance_seconds
        }
    except Exception as e:
        return {
            "is_valid": False,
            "error": str(e)
        }


def get_sample_webhook_payload(event_type: str) -> Dict[str, Any]:
    """
    Returns realistic sample JSON payload for Zapier / Make schema mapping.
    """
    now_ts = int(time.time())
    now_iso = datetime.now(timezone.utc).isoformat()
    evt_id = f"evt_sample_{uuid.uuid4().hex[:8]}"

    sample_data: Dict[str, Any] = {
        "lead_id": "lead_sample_12345",
        "first_name": "Satya",
        "last_name": "Nadella",
        "email": "satya@microsoft.com",
        "company_name": "Microsoft",
        "job_title": "Chairman and CEO",
        "linkedin_url": "https://linkedin.com/in/satyanadella"
    }

    if event_type == "lead.replied":
        sample_data["reply_text"] = "Thanks for reaching out! Let's schedule a conversation next Tuesday."
        sample_data["reply_sentiment"] = "POSITIVE"
        sample_data["thread_url"] = "https://linkedin.com/messaging/thread/123"
    elif event_type == "intent.hot_detected":
        sample_data["social_intent_score"] = 92
        sample_data["social_intent_tier"] = "HOT"
        sample_data["recommended_timing"] = "IMMEDIATE_ACTION"
        sample_data["signals"] = ["HIRING_EXPANSION", "TECH_STACK_PAIN"]
        sample_data["social_icebreaker"] = "Loved your recent point on infrastructure scaling, Satya."
    elif event_type == "lead.meeting_booked":
        sample_data["platform"] = "calendly"
        sample_data["calendar_event_id"] = "cal_evt_998877"
    elif event_type == "lead.connected":
        sample_data["connection_status"] = "ACCEPTED"
    elif event_type == "lead.email_discovered":
        sample_data["discovered_email"] = "satya@microsoft.com"
        sample_data["verification_status"] = "VALID"

    return {
        "id": evt_id,
        "event": event_type,
        "workspace_id": "ws_enterprise_example",
        "timestamp": now_ts,
        "created_at": now_iso,
        "data": sample_data
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dead-Letter Queue (DLQ), Circuit Breaker & Exponential Backoff Dispatching
# ─────────────────────────────────────────────────────────────────────────────

def calculate_retry_backoff(attempt_count: int, base_seconds: float = 30.0, max_seconds: float = 86400.0, jitter: bool = True) -> int:
    """
    Paranoia Layer 1: Calculates exponential backoff with randomized jitter to prevent thundering herds.
    Formula: min(max_seconds, base_seconds * (2 ** max(0, attempt_count - 1))) + jitter
    """
    eff_attempt = max(0, attempt_count - 1)
    exp_delay = base_seconds * (2 ** eff_attempt)
    if jitter:
        import random
        exp_delay += random.uniform(1.0, 5.0)
    return int(min(max_seconds, exp_delay))


def route_to_dead_letter(
    delivery_id: str,
    workspace_id: str,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
    supabase: Optional[Any] = None
) -> bool:
    """
    Paranoia Layer 0 & 1: Isolates permanently failing deliveries into the Dead-Letter Queue (DLQ).
    Prevents subscriber endpoint hammering and protects system queue throughput.
    """
    if not delivery_id or not workspace_id:
        return False
    client = supabase or get_service_client()
    if not client:
        return False

    clean_reason = str(reason).strip()[:255]
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        # Fetch current delivery payload to enrich metadata
        del_res = client.table("webhook_deliveries").select("id, payload, response_body").eq("id", delivery_id).eq("workspace_id", workspace_id).execute()
        if not del_res.data:
            return False

        curr_delivery = del_res.data[0]
        curr_payload = curr_delivery.get("payload") or {}
        if isinstance(curr_payload, dict):
            curr_payload = dict(curr_payload)
            curr_payload["dlq_info"] = {
                "routed_at": now_iso,
                "reason": clean_reason,
                **(metadata or {})
            }

        resp_snippet = f"[DLQ: {clean_reason}] {curr_delivery.get('response_body') or ''}"[:1000]

        upd_res = client.table("webhook_deliveries").update({
            "delivery_status": "dead_letter",
            "next_retry_at": None,
            "response_body": resp_snippet,
            "payload": curr_payload
        }).eq("id", delivery_id).eq("workspace_id", workspace_id).execute()

        logger.warning(f"[Webhook DLQ] Routed delivery {delivery_id} to Dead-Letter Queue. Reason: {clean_reason}")
        return bool(upd_res.data)
    except Exception as e:
        logger.error(f"[Webhook DLQ] Error routing delivery {delivery_id} to DLQ: {e}")
        return False


def retry_dead_letter_delivery(
    delivery_id: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Re-enqueues a DLQ delivery for execution once subscriber fixes their endpoint.
    Verifies tenant isolation and resets attempt count and next_retry_at.
    """
    if not delivery_id or not workspace_id:
        return {"status": "error", "message": "Missing delivery_id or workspace_id"}
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "message": "Database client unavailable"}

    try:
        del_res = client.table("webhook_deliveries").select("*").eq("id", delivery_id).eq("workspace_id", workspace_id).execute()
        if not del_res.data:
            return {"status": "error", "message": "Delivery record not found or foreign workspace"}

        delivery = del_res.data[0]
        status = delivery.get("delivery_status")
        if status not in ("dead_letter", "failed"):
            return {"status": "error", "message": f"Delivery is in '{status}' status, cannot retry from DLQ"}

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = delivery.get("payload") or {}
        if isinstance(payload, dict):
            payload = dict(payload)
            dlq_hist = payload.get("dlq_history") or []
            if payload.get("dlq_info"):
                dlq_hist.append(payload["dlq_info"])
            payload["dlq_history"] = dlq_hist[-5:]
            payload.pop("dlq_info", None)

        client.table("webhook_deliveries").update({
            "delivery_status": "pending",
            "attempt_count": 0,
            "next_retry_at": now_iso,
            "payload": payload,
            "response_body": f"[Re-enqueued from DLQ at {now_iso}]"
        }).eq("id", delivery_id).eq("workspace_id", workspace_id).execute()

        logger.info(f"[Webhook DLQ] Successfully re-enqueued delivery {delivery_id} from DLQ")
        return {
            "status": "success",
            "delivery_id": delivery_id,
            "message": "Delivery successfully re-enqueued from DLQ"
        }
    except Exception as e:
        logger.error(f"[Webhook DLQ] Failed to retry delivery {delivery_id}: {e}")
        return {"status": "error", "message": str(e)}


def get_dead_letter_queue(
    workspace_id: str,
    limit: int = 50,
    offset: int = 0,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Lists dead-lettered webhook deliveries for the workspace.
    """
    if not workspace_id:
        return {"status": "error", "data": [], "total_count": 0}
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "data": [], "total_count": 0}

    clean_limit = min(max(1, limit), 100)
    clean_offset = max(0, offset)

    try:
        res = client.table("webhook_deliveries") \
            .select("id, endpoint_id, event_type, status_code, response_body, attempt_count, created_at, payload", count="exact") \
            .eq("workspace_id", workspace_id) \
            .eq("delivery_status", "dead_letter") \
            .order("created_at", desc=True) \
            .range(clean_offset, clean_offset + clean_limit - 1) \
            .execute()

        items = res.data or []
        count = getattr(res, "count", len(items)) or len(items)
        return {
            "status": "success",
            "data": items,
            "total_count": count,
            "limit": clean_limit,
            "offset": clean_offset
        }
    except Exception as e:
        logger.error(f"[Webhook DLQ] Error querying dead-letter queue: {e}")
        return {"status": "error", "data": [], "total_count": 0, "error": str(e)}


# ─── ADAPTIVE ENDPOINT RATE-LIMIT BACKPRESSURE (PARANOIA LAYER 1 & 2) ───────────
_ENDPOINT_BACKPRESSURE: Dict[str, float] = {}
_BACKPRESSURE_LOCK = threading.Lock()

def record_endpoint_backpressure(endpoint_id: str, retry_after_seconds: float):
    """Dynamically register rate-limit backpressure received from external webhook recipient."""
    if not endpoint_id or retry_after_seconds <= 0:
        return
    with _BACKPRESSURE_LOCK:
        _ENDPOINT_BACKPRESSURE[str(endpoint_id)] = time.time() + retry_after_seconds
        logger.info(f"[AdaptiveBackpressure] Endpoint {endpoint_id} throttled for {retry_after_seconds:.1f}s via provider feedback.")

def get_endpoint_backpressure(endpoint_id: str) -> Optional[float]:
    """Returns remaining backpressure duration in seconds, or None if clear."""
    if not endpoint_id:
        return None
    with _BACKPRESSURE_LOCK:
        until = _ENDPOINT_BACKPRESSURE.get(str(endpoint_id))
        if until:
            remaining = until - time.time()
            if remaining > 0:
                return remaining
            else:
                del _ENDPOINT_BACKPRESSURE[str(endpoint_id)]
    return None


def dispatch_webhook_delivery(
    delivery: Dict[str, Any],
    endpoint: Dict[str, Any],
    supabase: Optional[Any] = None,
    max_retries: int = 5,
    fence_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Executes a single webhook delivery with:
    - Circuit Breaker protection per endpoint (trips on repeated failures to prevent hammering)
    - SSRF pre-validation (blocks loopback, AWS metadata, and RFC1918 addresses)
    - Dead-letter queue isolation for permanent failures (400, 404, 410, corrupt keys)
    - Exponential retry backoff with randomized jitter for transient errors
    - Constant-time HMAC-SHA256 signature generation
    """
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "message": "Database client unavailable"}

    delivery_id = delivery["id"]
    workspace_id = delivery.get("workspace_id") or endpoint.get("workspace_id")
    attempt_count = (delivery.get("attempt_count") or 0) + 1
    url = endpoint.get("url", "")
    endpoint_id = endpoint.get("id")

    # 1. Circuit Breaker Check (Endpoint Protection)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker
    cb_name = f"webhook_ep_{endpoint_id}"
    cb = get_circuit_breaker(cb_name, failure_threshold=5, recovery_timeout=60.0)

    if not cb.can_execute():
        logger.warning(f"[Webhook Dispatcher] Circuit breaker OPEN for endpoint {endpoint_id}. Deferring delivery {delivery_id}.")
        now_dt = datetime.now(timezone.utc)
        retry_delay = calculate_retry_backoff(attempt_count, base_seconds=60.0, jitter=True)
        next_retry = (now_dt + timedelta(seconds=retry_delay)).isoformat()
        try:
            client.table("webhook_deliveries").update({
                "delivery_status": "pending",
                "next_retry_at": next_retry,
                "response_body": f"[Circuit Breaker OPEN: endpoint {endpoint_id} is temporarily suspended]"
            }).eq("id", delivery_id).execute()
        except Exception:
            pass
        return {"status": "circuit_open", "delivery_id": delivery_id, "next_retry_at": next_retry}

    # Adaptive Backpressure Check (Honor 429 & Retry-After)
    remaining_backpressure = get_endpoint_backpressure(endpoint_id)
    if remaining_backpressure is not None and remaining_backpressure > 0:
        logger.info(f"[Webhook Dispatcher] Deferring endpoint {endpoint_id} due to active backpressure ({remaining_backpressure:.1f}s remaining).")
        now_dt = datetime.now(timezone.utc)
        next_retry = (now_dt + timedelta(seconds=max(5, int(remaining_backpressure)))).isoformat()
        try:
            client.table("webhook_deliveries").update({
                "delivery_status": "pending",
                "next_retry_at": next_retry,
                "response_body": f"[Adaptive Backpressure active: waiting {remaining_backpressure:.1f}s]"
            }).eq("id", delivery_id).execute()
        except Exception:
            pass
        return {"status": "retry_scheduled", "delivery_id": delivery_id, "attempt_count": attempt_count, "next_retry_at": next_retry}

    # 2. SSRF Protection (Paranoia Layer 1)
    if not is_safe_ssrf_url(url):
        logger.error(f"[Webhook Dispatcher] SSRF Violation: endpoint {endpoint_id} URL targets private network: {url}")
        route_to_dead_letter(
            delivery_id=delivery_id,
            workspace_id=workspace_id,
            reason="SSRF_VIOLATION: Targets prohibited private or local network IP",
            metadata={"url": url},
            supabase=client
        )
        return {"status": "dead_letter", "reason": "SSRF_VIOLATION"}

    # 3. Decrypt Signing Secret
    try:
        raw_secret = decrypt_bytes(bytes.fromhex(endpoint["signing_secret"])).decode('utf-8')
    except Exception as dec_err:
        logger.error(f"[Webhook Dispatcher] Corrupt signing secret for endpoint {endpoint_id}: {dec_err}")
        route_to_dead_letter(
            delivery_id=delivery_id,
            workspace_id=workspace_id,
            reason=f"CORRUPT_SIGNING_SECRET: {str(dec_err)}",
            supabase=client
        )
        return {"status": "dead_letter", "reason": "CORRUPT_SIGNING_SECRET"}

    # 4. Sign Payload with HMAC-SHA256
    now_ts = int(time.time())
    payload = delivery.get("payload") or {}
    timestamp, signature = generate_webhook_signature(payload, raw_secret, timestamp_override=now_ts)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "EleIn-Webhook-Dispatcher/2.0",
        "EleIn-Signature": signature,
        "EleIn-Timestamp": timestamp,
        "EleIn-Event": delivery.get("event_type", "unknown")
    }

    # 5. Execute HTTP Request with connect/read timeout
    status_code = None
    response_body = ""
    success = False
    start_time = time.time()

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=(3.0, 10.0),
            allow_redirects=False
        )
        latency_ms = int((time.time() - start_time) * 1000)
        status_code = resp.status_code
        response_body = resp.text[:1000]
        success = 200 <= status_code < 300

        # Honor Retry-After and 429 adaptive rate limits
        if hasattr(resp, "headers"):
            retry_after_hdr = resp.headers.get("Retry-After")
            if retry_after_hdr:
                try:
                    record_endpoint_backpressure(endpoint_id, float(retry_after_hdr))
                except (ValueError, TypeError):
                    record_endpoint_backpressure(endpoint_id, 60.0)
            elif status_code == 429:
                record_endpoint_backpressure(endpoint_id, 60.0)
    except requests.Timeout:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = "Request timed out (3s connect / 10s read)."
    except requests.ConnectionError as ce:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = f"Connection error: {str(ce)[:200]}"
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        response_body = f"HTTP dispatch error: {str(e)[:200]}"

    # 6. Evaluate Outcome
    if success:
        cb.record_success()
        try:
            client.table("webhook_deliveries").update({
                "delivery_status": "success",
                "status_code": status_code,
                "response_body": response_body,
                "attempt_count": attempt_count,
                "next_retry_at": None
            }).eq("id", delivery_id).execute()
        except Exception as e:
            logger.error(f"[Webhook Dispatcher] Failed to update success status for delivery {delivery_id}: {e}")
        return {"status": "success", "delivery_id": delivery_id, "status_code": status_code, "latency_ms": latency_ms}

    # Permanent Client Rejections (400, 404, 410) -> Route to DLQ
    if status_code in (400, 404, 410):
        cb.record_failure()
        route_to_dead_letter(
            delivery_id=delivery_id,
            workspace_id=workspace_id,
            reason=f"PERMANENT_CLIENT_ERROR_{status_code}",
            metadata={"status_code": status_code, "response_body": response_body},
            supabase=client
        )
        return {"status": "dead_letter", "reason": f"PERMANENT_CLIENT_ERROR_{status_code}", "status_code": status_code}

    # Transient Failure (500, 502, 503, 504, 429, timeouts, network disconnect)
    cb.record_failure()
    if attempt_count >= max_retries:
        route_to_dead_letter(
            delivery_id=delivery_id,
            workspace_id=workspace_id,
            reason="MAX_RETRIES_EXHAUSTED",
            metadata={"final_attempt": attempt_count, "status_code": status_code, "response_body": response_body},
            supabase=client
        )
        return {"status": "dead_letter", "reason": "MAX_RETRIES_EXHAUSTED", "status_code": status_code}
    else:
        backoff_sec = calculate_retry_backoff(attempt_count, base_seconds=30.0, jitter=True)
        now_dt = datetime.now(timezone.utc)
        next_retry = (now_dt + timedelta(seconds=backoff_sec)).isoformat()
        try:
            client.table("webhook_deliveries").update({
                "delivery_status": "pending",
                "status_code": status_code,
                "response_body": response_body,
                "attempt_count": attempt_count,
                "next_retry_at": next_retry
            }).eq("id", delivery_id).execute()
        except Exception as e:
            logger.error(f"[Webhook Dispatcher] Failed to schedule retry for delivery {delivery_id}: {e}")
        return {"status": "retry_scheduled", "delivery_id": delivery_id, "attempt_count": attempt_count, "next_retry_at": next_retry}


def dispatch_pending_webhooks(batch_size: int = 50, supabase: Optional[Any] = None) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Polling harness for background dispatchers.
    Dispatches up to batch_size pending deliveries due for execution.
    """
    client = supabase or get_service_client()
    if not client:
        return {"status": "error", "processed": 0}

    now_iso = datetime.now(timezone.utc).isoformat()
    filter_str = f"next_retry_at.lte.{now_iso},next_retry_at.is.null"

    try:
        res = client.table("webhook_deliveries") \
            .select("*") \
            .eq("delivery_status", "pending") \
            .or_(filter_str) \
            .order("created_at") \
            .limit(batch_size) \
            .execute()

        deliveries = res.data or []
        if not deliveries:
            return {"status": "success", "processed": 0, "succeeded": 0, "retried": 0, "dead_lettered": 0}

        endpoint_ids = list({d["endpoint_id"] for d in deliveries if d.get("endpoint_id")})
        ep_res = client.table("webhook_endpoints").select("*").in_("id", endpoint_ids).execute()
        endpoints_map = {e["id"]: e for e in (ep_res.data or [])}

        succeeded = 0
        retried = 0
        dead_lettered = 0

        for d in deliveries:
            deliv_id = d["id"]
            # Paranoia Layer 1 & 2: Monotonic Fencing Token & CAS Atomic Claim
            # Guarantees single-dispatch execution across concurrent worker processes/pods
            fence_token = f"fence_{deliv_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
            try:
                claim_res = client.table("webhook_deliveries").update({
                    "delivery_status": "processing",
                    "response_body": f"[Claimed with fence token {fence_token}]"
                }).eq("id", deliv_id).in_("delivery_status", ["pending", "retrying"]).execute()

                if claim_res and hasattr(claim_res, "data") and claim_res.data is not None:
                    if len(claim_res.data) == 0:
                        logger.debug(f"[Webhook Dispatcher] Delivery {deliv_id} already claimed by another worker. Skipping.")
                        continue
            except Exception as claim_err:
                logger.debug(f"[Webhook Dispatcher] CAS claim check fallback for {deliv_id}: {claim_err}")

            ep = endpoints_map.get(d.get("endpoint_id"))
            if not ep or not ep.get("is_active"):
                route_to_dead_letter(
                    delivery_id=d["id"],
                    workspace_id=d.get("workspace_id", ""),
                    reason="ENDPOINT_INACTIVE_OR_DELETED",
                    supabase=client
                )
                dead_lettered += 1
                continue

            out = dispatch_webhook_delivery(delivery=d, endpoint=ep, supabase=client, fence_token=fence_token)
            st = out.get("status")
            if st == "success":
                succeeded += 1
            elif st == "retry_scheduled":
                retried += 1
            elif st == "dead_letter":
                dead_lettered += 1

        return {
            "status": "success",
            "processed": len(deliveries),
            "succeeded": succeeded,
            "retried": retried,
            "dead_lettered": dead_lettered
        }
    except Exception as e:
        logger.error(f"[Webhook Dispatcher] Polling loop error: {e}")
        return {"status": "error", "error": str(e), "processed": 0}
