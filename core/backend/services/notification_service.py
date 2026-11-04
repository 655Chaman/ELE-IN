import uuid
import logging
from typing import Dict, List, Tuple, Optional, Any
from supabase import Client

logger = logging.getLogger(__name__)

# Default channel rules per event type: {event_type: {channel: default_enabled}}
DEFAULT_CHANNELS: Dict[str, Dict[str, bool]] = {
    'lead_replied_instant':    {'in_app': True,  'email': True},
    'account_suspended':       {'in_app': True,  'email': True},   # in_app cannot be disabled
    'account_needs_attention': {'in_app': True,  'email': True},
    'approval_queue_pending':  {'in_app': True,  'email': False},
    'campaign_completed':      {'in_app': True,  'email': False},
    'campaign_needs_attention':{'in_app': True,  'email': True},
    'campaign_anomaly':        {'in_app': True,  'email': True},
    'daily_digest':            {'in_app': False, 'email': False},
}

# Aliases between backend orchestrator event types and frontend settings labels
EVENT_TYPE_ALIASES: Dict[str, str] = {
    'campaign_needs_attention': 'campaign_anomaly',
    'campaign_anomaly': 'campaign_needs_attention',
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
    defaults = DEFAULT_CHANNELS.get(event_type, {'in_app': True, 'email': True})
    locked = LOCKED_ON_CHANNELS.get(event_type, set())
    active = []
    alias_type = EVENT_TYPE_ALIASES.get(event_type)
    for channel, default_enabled in defaults.items():
        if channel in locked:
            active.append(channel)  # Always on regardless of preference
        else:
            # Check primary event_type then alias
            user_pref = prefs_map.get((user_id, channel))
            if user_pref is None and alias_type:
                user_pref = prefs_map.get((user_id, f"{alias_type}:{channel}"))
            if user_pref if user_pref is not None else default_enabled:
                active.append(channel)
    return active


def dispatch_notification(
    svc: Client,
    workspace_id: str,
    event_type: str,
    payload: dict,
    immediate_in_app: bool = True
) -> None:
    """
    Dispatch a workspace notification across active channels (in_app, email, slack).
    Paranoia Architecture:
    - Layer 0: Inserts into outbox_events with deterministic idempotency.
    - Layer 1: Fast-tracks in_app directly into public.notifications for 0ms WebSocket Realtime delivery.
    - Layer 2: Entity-specific idempotency keys prevent cross-lead collision or duplicate spam.
    """
    try:
        # QUERY 1: All workspace members
        members_res = svc.table('workspace_members').select('user_id').eq('workspace_id', workspace_id).execute()
        if not members_res.data:
            return
        
        user_ids = [m['user_id'] for m in members_res.data if m.get('user_id')]
        if not user_ids:
            return
        
        # If specific target user is designated in payload, narrow down
        target_override = payload.get('target_user_id') or payload.get('user_id')
        if target_override and target_override in user_ids:
            user_ids = [target_override]
        
        # QUERY 2: All preferences for this event_type in this workspace (ONE batch query)
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
        entity_key = str(
            payload.get('unique_key') 
            or payload.get('message_id') 
            or payload.get('lead_id') 
            or payload.get('account_id') 
            or uuid.uuid4()
        )
        
        events = []
        immediate_in_app_rows = []
        CHUNK_SIZE = 50
        
        title = payload.get("title") or "Ele-in Alert"
        body = payload.get("body") or payload.get("message") or "You have a new alert in Ele-in."
        link = payload.get("link")

        for i in range(0, len(user_ids), CHUNK_SIZE):
            chunk = user_ids[i:i + CHUNK_SIZE]
            for user_id in chunk:
                channels = _resolve_channels_for_user(event_type, user_id, prefs_map)
                for channel in channels:
                    event_id = str(uuid.uuid4())
                    idempotency_key = f'{workspace_id}:{user_id}:{channel}:{event_type}:{entity_key}'
                    events.append({
                        'id': event_id,
                        'workspace_id': workspace_id,
                        'event_type': f'notification.{channel}',
                        'payload': {'user_id': user_id, 'event_type': event_type, 'payload': payload},
                        'idempotency_key': idempotency_key,
                    })

                    if channel == 'in_app' and immediate_in_app:
                        immediate_in_app_rows.append({
                            'workspace_id': workspace_id,
                            'user_id': user_id,
                            'title': title,
                            'body': body,
                            'link': link,
                            'event_type': event_type,
                            'outbox_event_id': event_id
                        })
        
        # Fast-track immediate In-App delivery for 0s Realtime WebSocket push
        if immediate_in_app_rows:
            try:
                svc.table('notifications').insert(immediate_in_app_rows).execute()
            except Exception as in_app_err:
                logger.debug(f'Immediate in-app insert handled or skipped: {in_app_err}')

        # QUERY 3: ONE batch upsert to outbox_events (idempotency_key prevents duplicates)
        if events:
            svc.table('outbox_events').upsert(events, on_conflict='idempotency_key').execute()
            logger.info(f'Dispatched {len(events)} notification event(s) for {event_type} in workspace {workspace_id}')
    
    except Exception as e:
        # Notification failure MUST NOT propagate — it must never block the calling business operation
        logger.error(f'Failed to dispatch notification {event_type} for workspace {workspace_id}: {e}')


def dispatch_workspace_alert_webhooks(
    svc: Client,
    workspace_id: str,
    event_type: str,
    title: str,
    description: str,
    data: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Dispatches unified workspace alerts to configured Slack, Discord, and custom webhooks
    according to the workspace's channel routing matrix.
    
    Paranoia Layer 1 (Environmental failure analysis):
      - Webhook requests use strict 5.0s timeout to never hang callers.
      - Exceptions are caught and logged; delivery failures never fail the caller.
      
    Paranoia Layer 2 (Human paranoia):
      - SSRF verification ensures targets are valid public HTTPS URLs.
      - Slack block and Discord embeds formatted cleanly with markdown.
    """
    import os
    import requests
    from core.backend.core.validators import is_safe_ssrf_url

    results = {"slack": "skipped", "discord": "skipped", "custom": "skipped"}
    if not workspace_id:
        return results

    try:
        ws_res = svc.table("workspaces").select("metadata").eq("id", workspace_id).limit(1).execute()
        if not ws_res.data:
            return results
        
        meta = ws_res.data[0].get("metadata") or {}
        wh = meta.get("webhooks", {})
        if not wh:
            return results

        channel_routing = wh.get("channel_routing", {})
        routing_for_event = channel_routing.get(event_type, {"slack": True, "discord": True})

        slack_url = wh.get("slack_webhook_url")
        discord_url = wh.get("discord_webhook_url")
        custom_url = wh.get("custom_webhook_url")

        # 1. Slack Dispatch
        if slack_url and routing_for_event.get("slack", True):
            if is_safe_ssrf_url(slack_url):
                try:
                    payload = {
                        "text": f"*{title}*\n{description}",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"*{title}*\n{description}"}
                            }
                        ]
                    }
                    resp = requests.post(slack_url, json=payload, timeout=5.0)
                    results["slack"] = "sent" if resp.status_code < 400 else f"failed_{resp.status_code}"
                except Exception as slack_err:
                    logger.warning(f"[WebhookDispatch] Slack error for workspace {workspace_id}: {slack_err}")
                    results["slack"] = f"error: {slack_err}"
            else:
                results["slack"] = "blocked_ssrf"

        # 2. Discord Dispatch
        if discord_url and routing_for_event.get("discord", True):
            if is_safe_ssrf_url(discord_url):
                try:
                    payload = {
                        "content": f"**{title}**\n{description}"
                    }
                    resp = requests.post(discord_url, json=payload, timeout=5.0)
                    results["discord"] = "sent" if resp.status_code < 400 else f"failed_{resp.status_code}"
                except Exception as discord_err:
                    logger.warning(f"[WebhookDispatch] Discord error for workspace {workspace_id}: {discord_err}")
                    results["discord"] = f"error: {discord_err}"
            else:
                results["discord"] = "blocked_ssrf"

        # 3. Custom Webhook Dispatch
        if custom_url:
            if is_safe_ssrf_url(custom_url):
                try:
                    payload = {
                        "event": event_type,
                        "workspace_id": workspace_id,
                        "title": title,
                        "description": description,
                        "data": data or {}
                    }
                    resp = requests.post(custom_url, json=payload, timeout=5.0)
                    results["custom"] = "sent" if resp.status_code < 400 else f"failed_{resp.status_code}"
                except Exception as custom_err:
                    logger.warning(f"[WebhookDispatch] Custom webhook error for workspace {workspace_id}: {custom_err}")
                    results["custom"] = f"error: {custom_err}"
            else:
                results["custom"] = "blocked_ssrf"

    except Exception as e:
        logger.error(f"[WebhookDispatch] General error for workspace {workspace_id}: {e}")

    return results


def dispatch_invitation_email(
    svc: Client,
    workspace_id: str,
    email: str,
    role: str,
    token: str,
    inviter_email: Optional[str] = None
) -> bool:
    """
    Enqueues transactional invitation email into outbox_events with idempotency key.
    """
    import os
    try:
        app_url = os.environ.get("APP_URL", "http://localhost:5173").rstrip("/")
        invite_link = f"{app_url}/accept-invite?token={token}"
        idempotency_key = f"invite:{workspace_id}:{email}:{token}"

        event_payload = {
            "workspace_id": workspace_id,
            "event_type": "notification.email",
            "payload": {
                "recipient_email": email,
                "subject": "You have been invited to join a workspace on Ele-in",
                "body": f"You've been invited to join an Ele-in workspace as a {role}.\n\nClick the link below to accept:\n{invite_link}\n\nThis invitation expires in 7 days.",
                "link": invite_link,
                "role": role,
                "token": token
            },
            "idempotency_key": idempotency_key
        }
        svc.table("outbox_events").upsert(event_payload, on_conflict="idempotency_key").execute()
        return True
    except Exception as e:
        logger.warning(f"[InvitationEmail] Failed to enqueue invite email for {email}: {e}")
        return False
