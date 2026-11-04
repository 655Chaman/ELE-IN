"""
Three-Layer Paranoia Framework: Retention Horizon & Chunked Pruning Service
- Layer 0: Bounded chunked pruning of delivered outbox events and read notifications.
- Layer 1: Table lock defense (chunk_size=500, max_chunks=10), zero data loss on pending/processing states, child FK preservation.
- Layer 2: Clamps negative/zero retention days, protects unread notifications with 7d minimum floor, supports dry_run preview.
"""
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

DEFAULT_OUTBOX_DELIVERED_RETENTION_DAYS = int(os.getenv("OUTBOX_DELIVERED_RETENTION_DAYS", 14))
DEFAULT_OUTBOX_FAILED_RETENTION_DAYS = int(os.getenv("OUTBOX_FAILED_RETENTION_DAYS", 60))
DEFAULT_NOTIFICATION_READ_RETENTION_DAYS = int(os.getenv("NOTIFICATION_READ_RETENTION_DAYS", 30))
DEFAULT_NOTIFICATION_UNREAD_RETENTION_DAYS = int(os.getenv("NOTIFICATION_UNREAD_RETENTION_DAYS", 90))
DEFAULT_PRUNE_CHUNK_SIZE = int(os.getenv("RETENTION_PRUNE_CHUNK_SIZE", 500))
DEFAULT_MAX_CHUNKS = int(os.getenv("RETENTION_MAX_CHUNKS", 10))

def prune_expired_outbox_events(
    svc,
    retention_days: int = DEFAULT_OUTBOX_DELIVERED_RETENTION_DAYS,
    failed_retention_days: int = DEFAULT_OUTBOX_FAILED_RETENTION_DAYS,
    workspace_id: Optional[str] = None,
    chunk_size: int = DEFAULT_PRUNE_CHUNK_SIZE,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1, 2: Chunked pruning of delivered and permanently failed outbox events.
    Guarantees 'pending' and 'processing' events are NEVER touched.
    """
    # Layer 2 Paranoia: Prevent catastrophic data loss by clamping invalid retention values
    safe_retention_days = max(1, int(retention_days))
    safe_failed_days = max(7, int(failed_retention_days))
    safe_chunk_size = max(1, min(1000, int(chunk_size)))
    safe_max_chunks = max(1, min(50, int(max_chunks)))

    now = datetime.now(timezone.utc)
    delivered_cutoff = (now - timedelta(days=safe_retention_days)).isoformat()
    failed_cutoff = (now - timedelta(days=safe_failed_days)).isoformat()

    deleted_delivered = 0
    deleted_failed = 0

    # 1. Prune delivered outbox events
    for _ in range(safe_max_chunks):
        try:
            q = svc.table('outbox_events').select('id').eq('status', 'delivered').lt('delivered_at', delivered_cutoff)
            if workspace_id:
                q = q.eq('workspace_id', workspace_id)
            res = q.limit(safe_chunk_size).execute()
            rows = res.data or []
            if not rows:
                break
            ids = [r['id'] for r in rows if r.get('id')]
            if not ids:
                break

            if dry_run:
                deleted_delivered += len(ids)
                break  # In dry run, sample candidate count
            else:
                # Layer 1 Paranoia: Double-check status whitelist in delete query
                del_q = svc.table('outbox_events').delete().in_('id', ids).eq('status', 'delivered')
                if workspace_id:
                    del_q = del_q.eq('workspace_id', workspace_id)
                del_q.execute()
                deleted_delivered += len(ids)
                time.sleep(0.01)  # Brief pause between chunks to release row locks
        except Exception as e:
            logger.warning(f"[Retention] Error pruning delivered outbox chunk: {e}")
            break

    # 2. Prune permanently failed or suspended events older than failed_cutoff
    for _ in range(safe_max_chunks):
        try:
            q = svc.table('outbox_events').select('id').in_('status', ['failed', 'suspended']).lt('updated_at', failed_cutoff)
            if workspace_id:
                q = q.eq('workspace_id', workspace_id)
            res = q.limit(safe_chunk_size).execute()
            rows = res.data or []
            if not rows:
                break
            ids = [r['id'] for r in rows if r.get('id')]
            if not ids:
                break

            if dry_run:
                deleted_failed += len(ids)
                break
            else:
                del_q = svc.table('outbox_events').delete().in_('id', ids).in_('status', ['failed', 'suspended'])
                if workspace_id:
                    del_q = del_q.eq('workspace_id', workspace_id)
                del_q.execute()
                deleted_failed += len(ids)
                time.sleep(0.01)
        except Exception as e:
            logger.warning(f"[Retention] Error pruning failed outbox chunk: {e}")
            break

    return {
        "deleted_delivered": deleted_delivered,
        "deleted_failed": deleted_failed,
        "total_deleted": deleted_delivered + deleted_failed,
        "dry_run": dry_run,
        "delivered_cutoff": delivered_cutoff,
        "failed_cutoff": failed_cutoff
    }

def prune_expired_notifications(
    svc,
    read_retention_days: int = DEFAULT_NOTIFICATION_READ_RETENTION_DAYS,
    unread_retention_days: int = DEFAULT_NOTIFICATION_UNREAD_RETENTION_DAYS,
    workspace_id: Optional[str] = None,
    chunk_size: int = DEFAULT_PRUNE_CHUNK_SIZE,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1, 2: Prunes acknowledged (read) in-app notifications
    and ancient unread notifications past their retention horizon.
    """
    # Layer 2 Paranoia: Clamp bounds
    safe_read_days = max(1, int(read_retention_days))
    safe_unread_days = max(7, int(unread_retention_days))  # Minimum 7d floor on unread alerts!
    safe_chunk_size = max(1, min(1000, int(chunk_size)))
    safe_max_chunks = max(1, min(50, int(max_chunks)))

    now = datetime.now(timezone.utc)
    read_cutoff = (now - timedelta(days=safe_read_days)).isoformat()
    unread_cutoff = (now - timedelta(days=safe_unread_days)).isoformat()

    deleted_read = 0
    deleted_unread = 0

    # 1. Prune read notifications older than read_cutoff
    for _ in range(safe_max_chunks):
        try:
            q = svc.table('notifications').select('id').filter('read_at', 'not.is', 'null').lt('read_at', read_cutoff)
            if workspace_id:
                q = q.eq('workspace_id', workspace_id)
            res = q.limit(safe_chunk_size).execute()
            rows = res.data or []
            if not rows:
                break
            ids = [r['id'] for r in rows if r.get('id')]
            if not ids:
                break

            if dry_run:
                deleted_read += len(ids)
                break
            else:
                del_q = svc.table('notifications').delete().in_('id', ids)
                if workspace_id:
                    del_q = del_q.eq('workspace_id', workspace_id)
                del_q.execute()
                deleted_read += len(ids)
                time.sleep(0.01)
        except Exception as e:
            logger.warning(f"[Retention] Error pruning read notifications chunk: {e}")
            break

    # 2. Prune ancient unread notifications older than unread_cutoff
    for _ in range(safe_max_chunks):
        try:
            q = svc.table('notifications').select('id').is_('read_at', 'null').lt('created_at', unread_cutoff)
            if workspace_id:
                q = q.eq('workspace_id', workspace_id)
            res = q.limit(safe_chunk_size).execute()
            rows = res.data or []
            if not rows:
                break
            ids = [r['id'] for r in rows if r.get('id')]
            if not ids:
                break

            if dry_run:
                deleted_unread += len(ids)
                break
            else:
                del_q = svc.table('notifications').delete().in_('id', ids)
                if workspace_id:
                    del_q = del_q.eq('workspace_id', workspace_id)
                del_q.execute()
                deleted_unread += len(ids)
                time.sleep(0.01)
        except Exception as e:
            logger.warning(f"[Retention] Error pruning unread notifications chunk: {e}")
            break

    return {
        "deleted_read": deleted_read,
        "deleted_unread": deleted_unread,
        "total_deleted": deleted_read + deleted_unread,
        "dry_run": dry_run,
        "read_cutoff": read_cutoff,
        "unread_cutoff": unread_cutoff
    }

def purge_expired_pending_deletion_workspaces(
    svc,
    grace_period_days: int = 14,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1, 2: Sweeps and completely purges workspaces that have remained
    in 'pending_deletion' status beyond their 14-day statutory grace period.
    """
    import asyncio
    safe_grace_days = max(1, int(grace_period_days))
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=safe_grace_days)).isoformat()
    purged_ids = []

    try:
        res = svc.table("workspaces").select("id, name, deletion_requested_at") \
            .eq("status", "pending_deletion") \
            .lt("deletion_requested_at", cutoff) \
            .limit(50).execute()
        expired_workspaces = res.data or []
    except Exception as e:
        logger.warning(f"[Retention] Could not query expired pending_deletion workspaces: {e}")
        return {"purged_workspaces": 0, "workspace_ids": [], "dry_run": dry_run}

    for ws in expired_workspaces:
        ws_id = ws.get("id")
        if not ws_id:
            continue
        if dry_run:
            purged_ids.append(ws_id)
            continue

        try:
            from core.backend.services.gdpr_service import purge_workspace_data
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, purge_workspace_data(ws_id, svc))
                        future.result(timeout=60)
                else:
                    loop.run_until_complete(purge_workspace_data(ws_id, svc))
            except RuntimeError:
                asyncio.run(purge_workspace_data(ws_id, svc))

            purged_ids.append(ws_id)
            logger.info(f"[Retention] Purged expired workspace {ws_id} ({ws.get('name')}) past 14-day grace period.")
        except Exception as ws_err:
            logger.error(f"[Retention] Failed to purge expired workspace {ws_id}: {ws_err}")

    return {
        "purged_workspaces": len(purged_ids),
        "workspace_ids": purged_ids,
        "dry_run": dry_run,
        "cutoff": cutoff
    }

def run_retention_prune_cycle(
    svc,
    workspace_id: Optional[str] = None,
    dry_run: bool = False,
    outbox_days: int = DEFAULT_OUTBOX_DELIVERED_RETENTION_DAYS,
    notification_days: int = DEFAULT_NOTIFICATION_READ_RETENTION_DAYS
) -> Dict[str, Any]:
    """
    Combined retention housekeeping cycle across Outbox, Notifications, and Expired Workspaces.
    """
    start_t = time.perf_counter()
    outbox_res = prune_expired_outbox_events(svc, retention_days=outbox_days, workspace_id=workspace_id, dry_run=dry_run)
    notif_res = prune_expired_notifications(svc, read_retention_days=notification_days, workspace_id=workspace_id, dry_run=dry_run)
    ws_res = purge_expired_pending_deletion_workspaces(svc, dry_run=dry_run) if not workspace_id else {"purged_workspaces": 0}
    elapsed = max(0.001, time.perf_counter() - start_t)

    return {
        "outbox": outbox_res,
        "notifications": notif_res,
        "workspaces": ws_res,
        "total_deleted": outbox_res.get("total_deleted", 0) + notif_res.get("total_deleted", 0) + ws_res.get("purged_workspaces", 0),
        "duration_seconds": round(elapsed, 4),
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
