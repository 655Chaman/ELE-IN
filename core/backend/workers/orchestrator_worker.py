import sys
import time
import logging
import datetime
from dotenv import load_dotenv

# Load .env first
load_dotenv("../../.env")

# Now we can import the orchestrator and auth_dep
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from core.backend.api.auth_dep import get_service_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elein.worker")

_WORKER_ID = "elein-daemon"

def run():
    logger.info("Starting Ele-in Orchestrator Cron Worker (One-shot)...")
    supabase = get_service_client()
    start_ms = int(time.time() * 1000)

    # Write heartbeat BEFORE tick
    try:
        supabase.table("worker_heartbeat").upsert({
            "worker_id": _WORKER_ID,
            "last_beat_at": datetime.datetime.utcnow().isoformat(),
            "status": "ticking"
        }).execute()
    except Exception:
        logger.debug("Heartbeat write failed", exc_info=True)

    try:
        orchestrator = EleInOrchestrator()
        results = orchestrator.process_pending_leads()
        leads_processed = len(results) if results else 0
        duration_ms = int(time.time() * 1000) - start_ms

        if results:
            logger.info(f"Processed {leads_processed} leads: {results}")

        # Write success heartbeat AFTER tick
        try:
            supabase.table("worker_heartbeat").upsert({
                "worker_id": _WORKER_ID,
                "last_beat_at": datetime.datetime.utcnow().isoformat(),
                "status": "alive",
                "last_tick_duration_ms": duration_ms,
                "last_tick_leads_processed": leads_processed
            }).execute()
        except Exception:
            logger.debug("Heartbeat write failed", exc_info=True)

        logger.info("Orchestrator run complete. Exiting cleanly.")

    except Exception as e:
        logger.error("Error during orchestrator execution", exc_info=True)
        # Write error heartbeat
        try:
            supabase.table("worker_heartbeat").upsert({
                "worker_id": _WORKER_ID,
                "last_beat_at": datetime.datetime.utcnow().isoformat(),
                "status": "error",
                "last_tick_duration_ms": int(time.time() * 1000) - start_ms
            }).execute()
        except Exception:
            logger.debug("Heartbeat write failed", exc_info=True)

        logger.error("Orchestrator crashed. Exiting with status 1.")
        sys.exit(1)

if __name__ == "__main__":
    run()
