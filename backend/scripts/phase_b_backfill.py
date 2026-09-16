import os
import sys
import time
import logging
import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BACKFILL] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5000"))
MAX_STALL_POLLS = int(os.environ.get("MAX_STALL_POLLS", "20"))
SLEEP_SECONDS = float(os.environ.get("SLEEP_SECONDS", "0.25"))


if BATCH_SIZE <= 0:
    raise ValueError(f"Invalid BATCH_SIZE: {BATCH_SIZE}. Must be > 0.")
if MAX_STALL_POLLS <= 0:
    raise ValueError(f"Invalid MAX_STALL_POLLS: {MAX_STALL_POLLS}. Must be > 0.")
if SLEEP_SECONDS <= 0:
    raise ValueError(f"Invalid SLEEP_SECONDS: {SLEEP_SECONDS}. Must be > 0.")

def get_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is required")
    return psycopg2.connect(db_url)

def run_backfill(conn):
    total_updated = 0
    batch_number = 0
    consecutive_zero_polls = 0

    while True:
        batch_number += 1
        log.info(f"Batch {batch_number}: selecting up to {BATCH_SIZE} NULL rows...")
        
        with conn.cursor() as cur:
            # Select batch for update
            select_sql = """
                SELECT id 
                FROM public.campaign_execution_states 
                WHERE workspace_id IS NULL 
                ORDER BY id 
                LIMIT %s 
                FOR UPDATE SKIP LOCKED
            """
            cur.execute(select_sql, (BATCH_SIZE,))
            batch_records = cur.fetchall()
            batch_ids = [row[0] for row in batch_records]
            
            if not batch_ids:
                # No rows locked in this batch. Are there any left at all?
                cur.execute("SELECT count(*) FROM public.campaign_execution_states WHERE workspace_id IS NULL")
                remaining_nulls = cur.fetchone()[0]
                
                if remaining_nulls == 0:
                    log.info("SUCCESS: 0 NULL rows remain. Backfill complete.")
                    break
                else:
                    consecutive_zero_polls += 1
                    if consecutive_zero_polls >= MAX_STALL_POLLS:
                        msg = (f"ABORT: Backfill stalled. 0 rows updated for {MAX_STALL_POLLS} "
                               f"consecutive polls (total {MAX_STALL_POLLS * SLEEP_SECONDS}s), "
                               f"but {remaining_nulls} NULL rows remain in campaign_execution_states. "
                               "A long-running transaction or hung worker is holding row locks. "
                               "Resolve the lock holder and re-run the backfill.")
                        raise Exception(msg)
                    
                    log.info(f"  {remaining_nulls} NULL rows remain but all are currently locked. "
                             f"Sleeping {SLEEP_SECONDS}s and retrying (poll {consecutive_zero_polls}/{MAX_STALL_POLLS})...")
                    conn.rollback() # Release anything just in case
                    time.sleep(SLEEP_SECONDS)
                    continue

            # We have rows, reset stall counter
            consecutive_zero_polls = 0
            log.info(f"  Locked {len(batch_ids)} rows. Updating from campaign_enrollments...")
            
            update_sql = """
                UPDATE public.campaign_execution_states ces
                SET workspace_id = ce.workspace_id
                FROM public.campaign_enrollments ce
                WHERE ces.enrollment_id = ce.id
                  AND ces.id = ANY(%s)
            """
            cur.execute(update_sql, (batch_ids,))
            
            if cur.rowcount != len(batch_ids):
                msg = f"INVARIANT VIOLATION: Expected to update {len(batch_ids)} rows, but updated {cur.rowcount}. Rolling back batch."
                conn.rollback()
                raise Exception(msg)
                
            total_updated += cur.rowcount
            conn.commit()
            log.info(f"  Batch complete. Cumulative updated: {total_updated}")

if __name__ == "__main__":
    try:
        conn = get_connection()
        try:
            run_backfill(conn)
        finally:
            conn.close()
    except Exception as e:
        log.error(str(e))
        sys.exit(1)
