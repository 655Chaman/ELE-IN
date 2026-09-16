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
    return True


def _process_email_notification(event: dict) -> bool:
    payload = event.get('payload', {})
    user_id = payload.get('user_id', 'unknown')
    event_type = payload.get('event_type', 'unknown')
    logger.warning(
        f'[EMAIL STUB] Email notification not yet delivered. '
        f'user_id={user_id} event_type={event_type} outbox_id={event["id"]}'
    )
    return True


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
