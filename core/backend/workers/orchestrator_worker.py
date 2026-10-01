import sys
import time
import logging
import datetime
import signal
import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current, parent, and project root locations
search_paths = [
    Path(__file__).resolve().parents[3] / "backend" / ".env",
    Path(__file__).resolve().parents[3] / ".env",
    Path(__file__).resolve().parents[2] / ".env",
    Path.cwd() / "backend" / ".env",
    Path.cwd() / ".env"
]
for p in search_paths:
    if p.is_file():
        load_dotenv(p)
        break

# Now we can import the orchestrator and auth_dep
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from core.backend.api.auth_dep import get_service_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("elein.worker")

_WORKER_ID = "elein-daemon"
_SLEEP_SECONDS = 30
_running = True

def handle_sigterm(signum, frame):
    global _running
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    _running = False

def run():
    global _running
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    db_host = os.getenv("SUPABASE_URL", "unknown")
    logger.info(f"Startup Config - Worker ID: {_WORKER_ID}, Sleep Interval: {_SLEEP_SECONDS}s, Database: {db_host}")
    logger.info("Starting Ele-in Orchestrator Daemon...")
    supabase = get_service_client()

    while _running:
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

        if not _running:
            break

        logger.info(f"Tick complete. Sleeping for {_SLEEP_SECONDS} seconds...")
        # Sleep in small chunks so we can interrupt quickly
        for _ in range(_SLEEP_SECONDS):
            if not _running:
                break
            time.sleep(1)

    try:
        supabase.table("worker_heartbeat").upsert({
            "worker_id": _WORKER_ID,
            "last_beat_at": datetime.datetime.utcnow().isoformat(),
            "status": "stopped"
        }).execute()
        logger.info("Worker stopped successfully.")
    except Exception:
        logger.debug("Final heartbeat write failed", exc_info=True)

if __name__ == "__main__":
    run()
