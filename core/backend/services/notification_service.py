import uuid
import logging
from typing import Dict, List, Tuple
from supabase import Client

logger = logging.getLogger(__name__)

# Default channel rules per event type: {event_type: {channel: default_enabled}}
DEFAULT_CHANNELS: Dict[str, Dict[str, bool]] = {
    'account_suspended':       {'in_app': True,  'email': True},   # in_app cannot be disabled
    'account_needs_attention': {'in_app': True,  'email': True},
    'approval_queue_pending':  {'in_app': True,  'email': False},
    'campaign_completed':      {'in_app': True,  'email': False},
    'daily_digest':            {'in_app': False, 'email': False},
}

# Channels that can NEVER be disabled (safety floor)
LOCKED_ON_CHANNELS: Dict[str, set] = {
    'account_suspended': {'in_app'},
}

def _resolve_channels_for_user(
    event_type: str,
    user_id: str,
    prefs_map: Dict[Tuple[str, str], bool]
) -> List[str]:
    """Pure function — no DB calls. Resolves active channels for a user."""
    defaults = DEFAULT_CHANNELS.get(event_type, {'in_app': True})
    locked = LOCKED_ON_CHANNELS.get(event_type, set())
    active = []
    for channel, default_enabled in defaults.items():
        if channel in locked:
            active.append(channel)  # Always on regardless of preference
        elif prefs_map.get((user_id, channel), default_enabled):
            active.append(channel)
    return active


def dispatch_notification(
    svc: Client,
    workspace_id: str,
    event_type: str,
    payload: dict
) -> None:
    """Dispatch a workspace notification. Uses batch queries, never N+1."""
    try:
        # QUERY 1: All workspace members
        members_res = svc.table('workspace_members').select('user_id').eq('workspace_id', workspace_id).execute()
        if not members_res.data:
            return
        
        user_ids = [m['user_id'] for m in members_res.data if m.get('user_id')]
        if not user_ids:
            return
        
        # QUERY 2: All preferences for this event_type in this workspace (ONE query)
        prefs_res = svc.table('notification_preferences') \
            .select('user_id,channel,enabled') \
            .eq('workspace_id', workspace_id) \
            .eq('event_type', event_type) \
            .execute()
        prefs_map: Dict[Tuple[str, str], bool] = {
            (p['user_id'], p['channel']): p['enabled']
            for p in (prefs_res.data or [])
        }
        
        # Build all events in memory (no DB calls in loop)
        account_id_for_key = str(payload.get('account_id', ''))
        events = []
        CHUNK_SIZE = 50
        for i in range(0, len(user_ids), CHUNK_SIZE):
            chunk = user_ids[i:i + CHUNK_SIZE]
            for user_id in chunk:
                channels = _resolve_channels_for_user(event_type, user_id, prefs_map)
                for channel in channels:
                    idempotency_key = f'{workspace_id}:{user_id}:{channel}:{event_type}:{account_id_for_key}'
                    events.append({
                        'id': str(uuid.uuid4()),
                        'workspace_id': workspace_id,
                        'event_type': f'notification.{channel}',
                        'payload': {'user_id': user_id, 'event_type': event_type, 'payload': payload},
                        'idempotency_key': idempotency_key,
                    })
        
        # QUERY 3: ONE batch upsert (idempotency_key prevents duplicates)
        if events:
            svc.table('outbox_events').upsert(events, on_conflict='idempotency_key').execute()
            logger.info(f'Dispatched {len(events)} notification event(s) for {event_type} in workspace {workspace_id}')
    
    except Exception as e:
        # Notification failure MUST NOT propagate — it must never block the calling operation
        logger.error(f'Failed to dispatch notification {event_type} for workspace {workspace_id}: {e}')
