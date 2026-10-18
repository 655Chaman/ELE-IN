import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
BATCH_SIZE = 10
MAX_ATTEMPTS = 3


def _compute_retry_deliver_at(attempts: int, jitter: bool = True) -> str:
    """
    Paranoia Layer 1: Exponential backoff with randomized jitter for failed outbox delivery.
    Prevents synchronized thundering herds when downstream notification providers recover.
    Attempt 1 -> ~60s
    Attempt 2 -> ~120s
    Attempt 3+ -> capped at 300s (5 min) + optional jitter
    """
    import random
    from datetime import timedelta
    eff_attempts = max(1, int(attempts))
    backoff_seconds = float(min(60 * (2 ** (eff_attempts - 1)), 300))
    if jitter:
        backoff_seconds += random.uniform(1.0, 15.0)
    return (datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)).isoformat()



def _process_in_app_notification(event: dict) -> bool:
    from core.backend.api.auth_dep import get_service_client
    supabase = get_service_client()
    
    envelope_payload = event.get('payload', {})
    if not isinstance(envelope_payload, dict):
        envelope_payload = {}
    payload = envelope_payload.get('payload', envelope_payload)
    if not isinstance(payload, dict):
        payload = {}
    
    event_type = envelope_payload.get('event_type') or payload.get('event_type') or event.get('event_type')
    title = payload.get("title") or envelope_payload.get("title")
    body = payload.get("body") or payload.get("message") or envelope_payload.get("body") or envelope_payload.get("message")
    
    if not title or not body or not event_type:
        return False
        
    workspace_id = event.get("workspace_id") or payload.get("workspace_id") or envelope_payload.get("workspace_id")
    if not workspace_id:
        return False
        
    target_user_ids = []
    if payload.get("user_id"):
        target_user_ids = [payload["user_id"]]
    elif envelope_payload.get("user_id"):
        target_user_ids = [envelope_payload["user_id"]]
    else:
        res = supabase.table("workspace_members").select("user_id").eq("workspace_id", workspace_id).execute()
        target_user_ids = [r["user_id"] for r in res.data] if res.data else []
        
    if not target_user_ids:
        raise ValueError("No workspace members found for delivery")
        
    res = supabase.table("notification_preferences").select("user_id, enabled").eq("workspace_id", workspace_id).eq("channel", "in_app").eq("event_type", event_type).in_("user_id", target_user_ids).execute()
    prefs = {r["user_id"]: r["enabled"] for r in res.data} if res.data else {}
    
    final_users = [u for u in target_user_ids if prefs.get(u, True)]
    
    if not final_users:
        return True
        
    inserts = [{
        "workspace_id": workspace_id,
        "user_id": uid,
        "title": title,
        "body": body,
        "link": payload.get("link") or envelope_payload.get("link"),
        "event_type": event_type,
        "outbox_event_id": event["id"]
    } for uid in final_users]
    
    existing = supabase.table("notifications").select("user_id").eq("outbox_event_id", event["id"]).in_("user_id", final_users).execute()
    existing_uids = [r["user_id"] for r in existing.data] if existing.data else []
    
    to_insert = [row for row in inserts if row["user_id"] not in existing_uids]
    if to_insert:
        supabase.table("notifications").insert(to_insert).execute()
        
    return True



def _process_email_notification(event: dict) -> bool:
    import os
    import requests
    from core.backend.api.auth_dep import get_service_client
    supabase = get_service_client()
    
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if not resend_api_key:
        import logging
        env = os.environ.get("ENVIRONMENT", "").lower().strip()
        if env in ("test", "development", "local") or os.environ.get("PYTEST_CURRENT_TEST"):
            logging.getLogger(__name__).warning("RESEND_API_KEY not set in non-prod environment. Skipping email dispatch safely.")
            return True
        logging.getLogger(__name__).error("RESEND_API_KEY not set. Cannot send email notification.")
        return False

    envelope = event.get('payload', {})
    if not isinstance(envelope, dict):
        envelope = {}
    payload = envelope.get('payload', envelope)
    if not isinstance(payload, dict):
        payload = {}
    
    title = payload.get("title") or envelope.get("title")
    body = payload.get("body") or payload.get("message") or envelope.get("body") or envelope.get("message")
    event_type = envelope.get("event_type") or payload.get("event_type") or event.get("event_type")
    workspace_id = event.get("workspace_id") or payload.get("workspace_id") or envelope.get("workspace_id")
    
    if not title or not body or not workspace_id:
        return False
        
    target_user_ids = [envelope["user_id"]] if envelope.get("user_id") else ([payload["user_id"]] if payload.get("user_id") else [])
    if not target_user_ids:
        res = supabase.table("workspace_members").select("user_id").eq("workspace_id", workspace_id).execute()
        target_user_ids = [r["user_id"] for r in res.data] if res.data else []
        
    if not target_user_ids:
        return True
        
    res = supabase.table("notification_preferences").select("user_id, enabled").eq("workspace_id", workspace_id).eq("channel", "email").eq("event_type", event_type).in_("user_id", target_user_ids).execute()
    prefs = {r["user_id"]: r["enabled"] for r in res.data} if res.data else {}
    
    final_users = [u for u in target_user_ids if prefs.get(u, True)]
    if not final_users:
        return True
        
    success_count = 0
    for uid in final_users:
        try:
            user_resp = supabase.auth.admin.get_user_by_id(uid)
            email = user_resp.user.email
            if not email:
                continue
                
            headers = {
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "from": "Ele-in Notifications <notifications@elein.ai>",
                "to": [email],
                "subject": title,
                "html": f"<p>{body}</p>"
            }
            link = payload.get("link") or envelope.get("link")
            if link:
                base_url = os.environ.get("FRONTEND_BASE_URL") or os.environ.get("APP_URL") or "https://app.elein.ai"
                clean_link = str(link).strip()
                if clean_link.startswith("/"):
                    full_link = f"{base_url.rstrip('/')}{clean_link}"
                elif clean_link.startswith("http://") or clean_link.startswith("https://"):
                    full_link = clean_link
                else:
                    full_link = f"{base_url.rstrip('/')}/{clean_link}"
                data["html"] += f'<p><a href="{full_link}" style="color: #6366f1; text-decoration: underline;">View in Ele-in &rarr;</a></p>'
                
            resp = requests.post("https://api.resend.com/emails", headers=headers, json=data, timeout=10)
            resp.raise_for_status()
            success_count += 1
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to send email to user {uid}: {e}")
            
    return success_count > 0 or len(final_users) == 0

def _process_slack_notification(event: dict) -> bool:
    import os
    import requests
    from core.backend.api.auth_dep import get_service_client
    from core.backend.core.validators import is_safe_ssrf_url
    from integrations.backend.services.circuit_breaker import get_circuit_breaker
    
    envelope = event.get('payload', {})
    payload = envelope.get('payload', envelope) if isinstance(envelope, dict) else {}
    
    ws_id = event.get('workspace_id') or payload.get('workspace_id') or 'global'
    cb = get_circuit_breaker(f"outbox_slack_{ws_id}", failure_threshold=5, recovery_timeout=60.0)
    if not cb.can_execute():
        logger.warning(f"[Outbox] Circuit breaker OPEN for Slack in workspace {ws_id}")
        return False

    text = payload.get('text') or payload.get('message')
    if not text:
        title = payload.get('title', 'Ele-in Notification')
        body = payload.get('body', '')
        text = f"*{title}*\n{body}"
        link = payload.get('link') or envelope.get('link')
        if link:
            base_url = os.environ.get("FRONTEND_BASE_URL") or os.environ.get("APP_URL") or "https://app.elein.ai"
            clean_link = str(link).strip()
            if clean_link.startswith("/"):
                full_link = f"{base_url.rstrip('/')}{clean_link}"
            elif clean_link.startswith("http://") or clean_link.startswith("https://"):
                full_link = clean_link
            else:
                full_link = f"{base_url.rstrip('/')}/{clean_link}"
            text = f"{text}\n<{full_link}|View in Ele-in>"
        
    webhook_url = payload.get('webhook_url') or envelope.get('webhook_url')
    if not webhook_url:
        if ws_id and ws_id != 'global':
            try:
                supabase = get_service_client()
                s_res = supabase.table('workspace_settings').select('slack_webhook_url').eq('workspace_id', ws_id).execute()
                if s_res.data and s_res.data[0].get('slack_webhook_url'):
                    webhook_url = s_res.data[0]['slack_webhook_url']
            except Exception:
                pass
                
    if not webhook_url:
        webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        
    if not webhook_url:
        logger.info(f"No webhook URL found for Slack notification event {event.get('id')} in workspace {ws_id}. Marking handled.")
        return True
        
    if not is_safe_ssrf_url(webhook_url):
        logger.error(f"SSRF violation: blocked unsafe Slack URL {webhook_url}")
        cb.record_failure()
        return False
        
    try:
        resp = requests.post(webhook_url, json={"text": text}, timeout=10.0, allow_redirects=False)
        if resp.status_code == 200:
            cb.record_success()
            return True
        else:
            cb.record_failure()
            return False
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        cb.record_failure()
        return False


def _process_webhook_notification(event: dict) -> bool:
    import requests
    from core.backend.core.validators import is_safe_ssrf_url
    from integrations.backend.services.webhook_service import (
        sanitize_webhook_payload,
        generate_webhook_signature,
    )
    
    envelope = event.get('payload', {})
    payload = envelope.get('payload', envelope) if isinstance(envelope, dict) else {}
    url = (payload.get('url') if isinstance(payload, dict) else None) or \
          (payload.get('webhook_url') if isinstance(payload, dict) else None) or \
          (envelope.get('url') if isinstance(envelope, dict) else None)
    
    if not url or not str(url).startswith(('http://', 'https://')):
        logger.warning(f"Invalid webhook URL in event {event.get('id')}")
        return False
        
    if not is_safe_ssrf_url(url):
        logger.error(f"SSRF violation: blocked unsafe webhook URL {url}")
        return False

    clean_payload = sanitize_webhook_payload(payload)
    
    signing_secret = (payload.get('secret') if isinstance(payload, dict) else None) or \
                     (envelope.get('secret') if isinstance(envelope, dict) else None)
    if not signing_secret:
        ws_id = event.get('workspace_id') or (payload.get('workspace_id') if isinstance(payload, dict) else None)
        if ws_id:
            try:
                from core.backend.api.auth_dep import get_service_client
                svc = get_service_client()
                ws_set = svc.table('workspace_settings').select('webhook_signing_secret').eq('workspace_id', ws_id).limit(1).execute()
                if ws_set.data and ws_set.data[0].get('webhook_signing_secret'):
                    signing_secret = ws_set.data[0]['webhook_signing_secret']
            except Exception:
                pass

    headers = {'Content-Type': 'application/json', 'User-Agent': 'EleIn-Outbox/1.0'}
    if signing_secret:
        ts, sig = generate_webhook_signature(
            clean_payload if isinstance(clean_payload, dict) else {"data": clean_payload},
            signing_secret
        )
        headers['EleIn-Signature'] = sig
        headers['EleIn-Timestamp'] = ts
        headers['X-Webhook-Signature'] = sig
        headers['X-Webhook-Timestamp'] = ts
        
    try:
        resp = requests.post(
            url,
            json=clean_payload,
            headers=headers,
            timeout=10.0,
            allow_redirects=False
        )
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.error(f"Failed to dispatch webhook: {e}")
        return False

def reap_stuck_outbox_events(svc, stuck_timeout_minutes: int = 15) -> int:
    """
    Paranoia Layer 1: Zombie Outbox Event Recovery.
    Resurrects events stuck in 'processing' status due to unexpected worker crashes.
    """
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stuck_timeout_minutes)).isoformat()
        try:
            res = svc.table('outbox_events') \
                .select('id, attempts') \
                .eq('status', 'processing') \
                .lt('updated_at', cutoff) \
                .execute()
            stuck_events = res.data or []
        except Exception as query_err:
            if 'outbox_event_status' in str(query_err) and 'processing' in str(query_err):
                # Paranoia Layer 1: Zero-migration fallback when DB enum lacks 'processing'
                return 0
            raise
        reaped_count = 0
        for ev in stuck_events:
            attempts = ev.get('attempts', 0)
            new_status = 'pending' if attempts < MAX_ATTEMPTS else 'failed'
            svc.table('outbox_events').update({
                'status': new_status,
                'last_error': 'Worker timed out during processing (auto-reaped)'
            }).eq('id', ev['id']).execute()
            reaped_count += 1
        return reaped_count
    except Exception as e:
        logger.warning(f"reap_stuck_outbox_events failed non-fatally: {e}")
        return 0


def poll_outbox_once() -> int:
    svc = get_service_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        reap_stuck_outbox_events(svc)

        filter_str = f"deliver_at.lte.{now_iso},deliver_at.is.null"
        res = svc.table('outbox_events') \
            .select('*') \
            .eq('status', 'pending') \
            .or_(filter_str) \
            .order('created_at') \
            .limit(BATCH_SIZE) \
            .execute()
        
        events = res.data or []
        if not events:
            return 0

        processed = 0
        for event in events:
            event_id = event['id']
            event_type = event.get('event_type', '')
            attempts = event.get('attempts', 0) + 1
            success = False

            try:
                claim_res = svc.table('outbox_events') \
                    .update({'status': 'processing', 'attempts': attempts}) \
                    .eq('id', event_id) \
                    .eq('status', 'pending') \
                    .execute()
            except Exception as claim_err:
                if 'outbox_event_status' in str(claim_err) and 'processing' in str(claim_err):
                    # Paranoia Layer 1: Zero-migration fallback when DB enum lacks 'processing'
                    claim_res = svc.table('outbox_events') \
                        .update({'attempts': attempts}) \
                        .eq('id', event_id) \
                        .eq('status', 'pending') \
                        .execute()
                else:
                    raise
            if not getattr(claim_res, 'data', None):
                continue

            try:
                if event_type == 'notification.in_app':
                    success = _process_in_app_notification(event)
                elif event_type == 'notification.email':
                    success = _process_email_notification(event)
                elif event_type in ('notification.slack', 'slack'):
                    success = _process_slack_notification(event)
                elif event_type in ('notification.webhook', 'webhook'):
                    success = _process_webhook_notification(event)
                elif event_type in ('workspace.schedule_deletion', 'campaign.deleted', 'lead_list.deleted', 'audit.event'):
                    logger.info(f'[AUDIT OUTBOX] event_type={event_type} workspace={event.get("workspace_id")} id={event_id}')
                    success = True
                else:
                    raise NotImplementedError(f"Channel {event_type} is not implemented")
            except NotImplementedError as e:
                logger.warning(f'Outbox event {event_id} channel unimplemented. Suspending: {e}')
                svc.table('outbox_events').update({
                    'status': 'suspended',
                    'attempts': attempts
                }).eq('id', event_id).execute()
                continue
            except Exception as e:
                logger.error(f'Error processing outbox event {event_id}: {e}')
                success = False

            if success:
                svc.table('outbox_events').update({
                    'status': 'delivered',
                    'delivered_at': datetime.now(timezone.utc).isoformat(),
                    'attempts': attempts,
                }).eq('id', event_id).execute()
                processed += 1
            else:
                if attempts < MAX_ATTEMPTS:
                    next_deliver_at = _compute_retry_deliver_at(attempts)
                    svc.table('outbox_events').update({
                        'status': 'pending',
                        'attempts': attempts,
                        'last_error': f'Processing failed on attempt {attempts}, retrying at {next_deliver_at}',
                        'deliver_at': next_deliver_at,
                    }).eq('id', event_id).execute()
                    logger.warning(
                        f'[Outbox] Event {event_id} ({event_type}) failed attempt {attempts}/{MAX_ATTEMPTS}. '
                        f'Retrying after backoff at {next_deliver_at}.'
                    )
                else:
                    svc.table('outbox_events').update({
                        'status': 'failed',
                        'attempts': attempts,
                        'last_error': f'Permanently failed after {MAX_ATTEMPTS} attempts',
                    }).eq('id', event_id).execute()
                    logger.error(
                        f'[DEAD LETTER] Outbox event {event_id} ({event_type}) '
                        f'permanently failed after {MAX_ATTEMPTS} attempts.'
                    )
                    try:
                        ws_id = event.get('workspace_id')
                        raw_payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
                        is_already_dlq_alert = bool(
                            event_type == 'notification.in_app'
                            or raw_payload.get('is_dlq_alert')
                            or (isinstance(raw_payload.get('payload'), dict) and raw_payload['payload'].get('is_dlq_alert'))
                        )
                        if ws_id and not is_already_dlq_alert:
                            alert_msg = (
                                f"A '{event_type}' notification permanently failed delivery "
                                f"after {MAX_ATTEMPTS} attempts. Check your Slack webhook URL "
                                f"or webhook endpoint configuration in Settings."
                            )
                            svc.table('outbox_events').insert({
                                'workspace_id': ws_id,
                                'event_type': 'notification.in_app',
                                'payload': {
                                    'event_type': 'system.dlq_alert',
                                    'is_dlq_alert': True,
                                    'title': 'Notification Delivery Failed',
                                    'body': alert_msg,
                                    'message': alert_msg,
                                },
                                'status': 'pending'
                            }).execute()
                    except Exception as _alert_err:
                        logger.error(f'[Outbox] Failed to queue dead-letter alert: {_alert_err}')

        return processed

    except Exception as e:
        logger.error(f'Outbox poll failed: {e}')
        return 0


def get_outbox_dead_letter_events(svc, workspace_id: str, limit: int = 50, offset: int = 0) -> dict:
    """
    Paranoia Layer 2: Retrieves quarantined ('failed' or 'suspended') outbox events for a workspace.
    """
    if not workspace_id or not svc:
        return {"status": "error", "data": [], "total_count": 0}
    clean_limit = min(max(1, int(limit)), 100)
    clean_offset = max(0, int(offset))
    try:
        res = svc.table("outbox_events") \
            .select("*", count="exact") \
            .eq("workspace_id", workspace_id) \
            .in_("status", ["failed", "suspended"]) \
            .order("created_at", desc=True) \
            .range(clean_offset, clean_offset + clean_limit - 1) \
            .execute()
        items = res.data or []
        total = getattr(res, "count", None)
        if total is None:
            total = len(items)
        return {
            "status": "success",
            "data": items,
            "total_count": total,
            "limit": clean_limit,
            "offset": clean_offset
        }
    except Exception as e:
        logger.error(f"[Outbox DLQ] Failed to list dead-letter events for workspace {workspace_id}: {e}")
        return {"status": "error", "data": [], "total_count": 0, "error": str(e)}


def retry_outbox_dead_letter_event(svc, event_id: str, workspace_id: str) -> dict:
    """
    Paranoia Layer 2: Safely re-drives a failed/suspended outbox event after validating tenant
    ownership and SSRF safety on any embedded webhook URLs.
    """
    if not event_id or not workspace_id or not svc:
        return {"status": "error", "message": "Missing event_id or workspace_id"}
    try:
        res = svc.table("outbox_events") \
            .select("*") \
            .eq("id", event_id) \
            .eq("workspace_id", workspace_id) \
            .execute()
        if not res.data:
            return {"status": "error", "message": "Outbox event not found or unauthorized"}
        
        event = res.data[0]
        curr_status = event.get("status")
        if curr_status not in ("failed", "suspended"):
            return {
                "status": "error",
                "message": f"Cannot retry event in '{curr_status}' status; only 'failed' or 'suspended' events can be re-driven."
            }

        from core.backend.core.validators import is_safe_ssrf_url
        envelope = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        inner = envelope.get("payload", envelope) if isinstance(envelope, dict) else {}
        candidate_url = (
            (inner.get("url") if isinstance(inner, dict) else None)
            or (inner.get("webhook_url") if isinstance(inner, dict) else None)
            or envelope.get("url")
            or envelope.get("webhook_url")
        )
        if candidate_url and not is_safe_ssrf_url(str(candidate_url)):
            return {
                "status": "error",
                "message": "SSRF Violation: Event contains an unsafe or private webhook URL and cannot be re-driven."
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        upd_res = svc.table("outbox_events").update({
            "status": "pending",
            "attempts": 0,
            "deliver_at": now_iso,
            "last_error": f"Re-queued from DLQ by operator at {now_iso}"
        }).eq("id", event_id).eq("workspace_id", workspace_id).execute()

        return {
            "status": "success",
            "event_id": event_id,
            "message": "Outbox event re-queued for delivery",
            "data": upd_res.data[0] if getattr(upd_res, "data", None) else {"id": event_id, "status": "pending"}
        }
    except Exception as e:
        logger.error(f"[Outbox DLQ] Failed to retry event {event_id}: {e}")
        return {"status": "error", "message": str(e)}


async def run_outbox_poller():
    logger.info(f'Outbox poller started. Polling every {POLL_INTERVAL_SECONDS}s.')
    poll_cycles = 0
    while True:
        try:
            count = poll_outbox_once()
            if count > 0:
                logger.info(f'Outbox poller processed {count} event(s).')
            
            poll_cycles += 1
            if poll_cycles >= 720:
                poll_cycles = 0
                try:
                    from core.backend.services.retention_service import run_retention_prune_cycle
                    svc = get_service_client()
                    p_res = run_retention_prune_cycle(svc)
                    if p_res.get("total_deleted", 0) > 0:
                        logger.info(f"[Retention] Periodic background prune cleared {p_res['total_deleted']} items in {p_res['duration_seconds']}s")
                except Exception as _prune_err:
                    logger.warning(f"[Retention] Periodic prune error non-fatal: {_prune_err}")
        except Exception as e:
            logger.error(f'Outbox poller loop error: {e}')
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
