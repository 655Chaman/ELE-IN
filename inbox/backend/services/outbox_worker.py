import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
BATCH_SIZE = 10
MAX_ATTEMPTS = 3


def _process_in_app_notification(event: dict) -> bool:
    from core.backend.core.supabase_client import get_supabase
    supabase = get_supabase()
    
    payload = event.get('payload', {})
    if not payload.get("title") or not payload.get("body") or not payload.get("event_type"):
        return False
        
    workspace_id = event.get("workspace_id") or payload.get("workspace_id")
    if not workspace_id:
        return False
        
    target_user_ids = []
    if payload.get("user_id"):
        target_user_ids = [payload["user_id"]]
    else:
        res = supabase.table("workspace_members").select("user_id").eq("workspace_id", workspace_id).execute()
        target_user_ids = [r["user_id"] for r in res.data] if res.data else []
        
    if not target_user_ids:
        return True
        
    # Check preferences
    res = supabase.table("notification_preferences").select("user_id, enabled").eq("channel", "in_app").eq("workspace_id", workspace_id).in_("user_id", target_user_ids).execute()
    prefs = {r["user_id"]: r["enabled"] for r in res.data} if res.data else {}
    
    final_users = [u for u in target_user_ids if prefs.get(u, True)]
    
    if not final_users:
        return True
        
    try:
        inserts = [{
            "workspace_id": workspace_id,
            "user_id": uid,
            "title": payload["title"],
            "body": payload["body"],
            "link": payload.get("link"),
            "event_type": payload["event_type"],
            "outbox_event_id": event["id"]
        } for uid in final_users]
        
        existing = supabase.table("notifications").select("user_id").eq("outbox_event_id", event["id"]).in_("user_id", final_users).execute()
        existing_uids = [r["user_id"] for r in existing.data] if existing.data else []
        
        to_insert = [row for row in inserts if row["user_id"] not in existing_uids]
        if to_insert:
            supabase.table("notifications").insert(to_insert).execute()
            
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error inserting notification: {e}")
        return False



def _process_email_notification(event: dict) -> bool:
    raise NotImplementedError("Email notifications are not configured (stubbed).")


def poll_outbox_once() -> int:
    svc = get_service_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        res = svc.table('outbox_events') \
            .select('*') \
            .eq('status', 'pending') \
            .lte('deliver_at', now_iso) \
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
                if event_type == 'notification.in_app':
                    success = _process_in_app_notification(event)
                elif event_type == 'notification.email':
                    success = _process_email_notification(event)
                elif event_type == 'workspace.schedule_deletion':
                    logger.info(f'[DELETION SCHEDULED] workspace={event["workspace_id"]} payload={event["payload"]}')
                    success = True
                else:
                    logger.warning(f'Unknown outbox event type: {event_type} id={event_id}')
                    success = True
            except NotImplementedError as e:
                logger.error(f'Outbox event {event_id} is a stub and cannot be processed: {e}')
                success = False
                attempts = MAX_ATTEMPTS  # Force immediate failure, do not retry
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
                new_status = 'pending' if attempts < MAX_ATTEMPTS else 'failed'
                if new_status == 'failed':
                    logger.error(f'[DEAD LETTER] Outbox event {event_id} failed after {MAX_ATTEMPTS} attempts.')
                svc.table('outbox_events').update({
                    'status': new_status,
                    'attempts': attempts,
                    'last_error': f'Processing failed on attempt {attempts}',
                }).eq('id', event_id).execute()

        return processed

    except Exception as e:
        logger.error(f'Outbox poll failed: {e}')
        return 0


async def run_outbox_poller():
    logger.info(f'Outbox poller started. Polling every {POLL_INTERVAL_SECONDS}s.')
    while True:
        try:
            count = poll_outbox_once()
            if count > 0:
                logger.info(f'Outbox poller processed {count} event(s).')
        except Exception as e:
            logger.error(f'Outbox poller loop error: {e}')
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
