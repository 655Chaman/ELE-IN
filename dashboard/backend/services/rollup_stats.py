"""
@deprecated
This file is orphaned and superseded by the master-view API routes and corresponding backend workers. 
It is entirely unused and a candidate for deletion.
"""
import logging
from datetime import date, timedelta, datetime
from dotenv import load_dotenv

load_dotenv("../../.env")
from core.backend.api.auth_dep import get_service_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elein.rollup")

def run_rollup_tracked(supabase, target_date: str):
    """
    Wrapper around the rollup RPC that tracks execution in processing_jobs.
    Implements a locking mechanism to prevent overlapping runs.
    """
    job_type = 'dashboard_rollup'
    
    # PARANOIA LAYER 2: ROLLUP LOCK - The old SELECT-then-INSERT pattern had a TOCTOU race.
    # We now use a stateless-safe atomic lock via a check-and-set RPC.
    lock_acquired = False
    try:
        lock_res = supabase.rpc('try_acquire_rollup_lock').execute()
        if not lock_res.data:
            logger.info(f'[rollup] Skipping: another rollup job is already running.')
            return
        lock_acquired = True
    except Exception as e:
        logger.warning(f"[rollup] Failed to acquire lock, assuming safe to run: {e}")
        # Proceed if check fails
    
    try:
        job_id = None
        try:
            job_res = supabase.table('processing_jobs').insert({
                'job_type': job_type,
                'status': 'running',
                'started_at': datetime.utcnow().isoformat(),
                'metadata': {'target_date': target_date}
            }).execute()
            job_id = job_res.data[0]['id'] if job_res.data else None
        except Exception as e:
            logger.warning(f"[rollup] Failed to insert tracking record: {e}")
            # Proceed with rollup even if tracking insert fails
        
        try:
            supabase.rpc('rollup_daily_stats', {'p_target_date': target_date}).execute()
            
            if job_id:
                try:
                    supabase.table('processing_jobs').update({
                        'status': 'completed',
                        'completed_at': datetime.utcnow().isoformat(),
                        'metadata': {'target_date': target_date, 'rolled_up_at': datetime.utcnow().isoformat()}
                    }).eq('id', job_id).execute()
                except Exception as update_e:
                    logger.warning(f"[rollup] Failed to update tracking to completed: {update_e}")
                    
            logger.info(f'[rollup] Completed for {target_date}')
        except Exception as e:
            if job_id:
                try:
                    supabase.table('processing_jobs').update({
                        'status': 'failed',
                        'completed_at': datetime.utcnow().isoformat(),
                        'metadata': {'target_date': target_date, 'error': str(e)}
                    }).eq('id', job_id).execute()
                except Exception as update_e:
                    logger.warning(f"[rollup] Failed to update tracking to failed: {update_e}")
                    
            logger.error(f'[rollup] FAILED for {target_date}: {e}')
            raise
    finally:
        if lock_acquired:
            try:
                supabase.rpc('release_rollup_lock').execute()
            except Exception as e:
                logger.error(f"[rollup] CRITICAL: Failed to release rollup lock: {e}")

def run_rollup():
    logger.info("Starting Daily Stats Rollup...")
    supabase = get_service_client()
    
    # We roll up stats for today and yesterday to ensure we don't miss late events
    # DAEMON OK: This is intentionally server UTC. The rollup daemon is not user-facing.
    today_str = date.today().isoformat()
    # DAEMON OK: This is intentionally server UTC. The rollup daemon is not user-facing.
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    dates_to_process = [yesterday_str, today_str]

    for target_date in dates_to_process:
        logger.info(f"Rolling up stats for {target_date}...")
        try:
            run_rollup_tracked(supabase, target_date)
        except Exception as e:
            logger.error(f"Error rolling up stats for {target_date}: {e}")

def backfill_rollups(workspace_id: str, start_date: str, end_date: str, supabase=None):
    """
    Backfill rollup stats for a specific workspace across a date range.
    
    WARNING: This function MUST call rollup_daily_stats() RPC, not re-implement
    the aggregation logic. A separate backfill script that duplicates aggregation
    WILL drift from the scheduled job and produce different numbers for the same date.
    
    Args:
        workspace_id: The workspace UUID to backfill
        start_date: ISO date string 'YYYY-MM-DD'
        end_date: ISO date string 'YYYY-MM-DD' (inclusive)
        supabase: Optional Supabase client; creates one if not provided
    """
    from datetime import date, timedelta
    
    if supabase is None:
        supabase = get_service_client()  # Use whatever pattern exists in the file
    
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    
    if end < start:
        raise ValueError(f'end_date ({end_date}) must be >= start_date ({start_date})')
    
    total_days = (end - start).days + 1
    success_count = 0
    fail_count = 0
    
    print(f'[backfill] Starting backfill for workspace {workspace_id}: {start_date} -> {end_date} ({total_days} days)')
    
    current = start
    while current <= end:
        target_date = current.isoformat()
        try:
            # CRITICAL: Call the same RPC as the scheduled job. Do NOT re-implement.
            supabase.rpc('rollup_daily_stats', {
                'p_target_date': target_date,
                'p_workspace_id': workspace_id
            }).execute()
            print(f'[backfill] SUCCESS: {target_date}')
            success_count += 1
        except Exception as e:
            # Per-date failure MUST NOT abort the entire backfill
            print(f'[backfill] FAILED: {target_date} - {e}')
            fail_count += 1
        
        current += timedelta(days=1)
    
    print(f'[backfill] Complete. Success: {success_count}/{total_days}, Failed: {fail_count}/{total_days}')
    return {'success': success_count, 'failed': fail_count, 'total': total_days}

if __name__ == "__main__":
    run_rollup()
