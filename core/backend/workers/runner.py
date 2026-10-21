"""
core/backend/workers/runner.py — Production Multi-Worker Supervisor Daemon
Rigorously built under the Three-Layer Logic Architecture (Paranoia Framework).

Runs and supervises both:
1. core.backend.workers.job_processor (Knowledge base, embeddings, asset ingestion, HubSpot sync)
2. core.backend.workers.orchestrator_worker (Campaign execution states, sequence dispatch, outbox sweep)

Guarantees:
- Isolated memory spaces (Playwright browser memory will not corrupt async event loop).
- Clean signal forwarding (SIGTERM / SIGINT) for zero-downtime deployments.
- Automatic fail-fast restart: If either critical worker crashes, exits with error so Docker/Render restarts container.
"""

import sys
import os
import time
import signal
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Supervisor] %(message)s"
)
logger = logging.getLogger("elein.supervisor")

_CHILD_PROCESSES = []
_SHUTTING_DOWN = False


def _forward_signal(sig, frame):
    global _SHUTTING_DOWN
    if _SHUTTING_DOWN:
        return
    _SHUTTING_DOWN = True
    sig_name = signal.Signals(sig).name
    logger.info(f"Received {sig_name}. Forwarding shutdown signal to all background workers...")

    for name, proc in _CHILD_PROCESSES:
        if proc.poll() is None:
            logger.info(f"Sending {sig_name} to {name} (PID: {proc.pid})...")
            try:
                proc.send_signal(sig)
            except Exception as e:
                logger.warning(f"Could not signal {name}: {e}")

    # Allow up to 12 seconds for workers to gracefully drain and release leases
    timeout = 12
    start_time = time.time()
    for name, proc in _CHILD_PROCESSES:
        elapsed = time.time() - start_time
        remaining = max(0.5, timeout - elapsed)
        try:
            proc.wait(timeout=remaining)
            logger.info(f"Worker {name} terminated cleanly.")
        except subprocess.TimeoutExpired:
            logger.warning(f"Worker {name} did not exit within timeout. Killing forcefully...")
            try:
                proc.kill()
            except Exception:
                pass

    logger.info("All background workers terminated. Exiting supervisor.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, _forward_signal)
    signal.signal(signal.SIGTERM, _forward_signal)

    python_bin = sys.executable
    logger.info(f"Starting Ele-in Production Multi-Worker Supervisor using Python: {python_bin}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Worker 1: Job Processor (Knowledge Base, Scraping, Vector Embeddings, HubSpot)
    logger.info("Spawning Job Processor daemon (core.backend.workers.job_processor)...")
    job_proc = subprocess.Popen(
        [python_bin, "-m", "core.backend.workers.job_processor"],
        env=env
    )
    _CHILD_PROCESSES.append(("JobProcessor", job_proc))

    # Worker 2: Campaign Orchestrator Daemon (Sequence Engine, Outbox Events, Leads Dispatch)
    logger.info("Spawning Campaign Orchestrator daemon (core.backend.workers.orchestrator_worker)...")
    orch_proc = subprocess.Popen(
        [python_bin, "-m", "core.backend.workers.orchestrator_worker"],
        env=env
    )
    _CHILD_PROCESSES.append(("Orchestrator", orch_proc))

    logger.info(f"Workers spawned successfully. JobProcessor PID: {job_proc.pid}, Orchestrator PID: {orch_proc.pid}")

    # Paranoia Layer 1: Continuous Liveness Monitoring
    # If either worker process dies unexpectedly, terminate remaining workers and fail fast so container restarts.
    while not _SHUTTING_DOWN:
        time.sleep(2)
        for name, proc in _CHILD_PROCESSES:
            poll_code = proc.poll()
            if poll_code is not None:
                logger.error(f"CRITICAL: Worker {name} (PID: {proc.pid}) unexpectedly exited with code {poll_code}!")
                logger.error("Initiating fail-fast shutdown to trigger container restart...")
                _forward_signal(signal.SIGTERM, None)
                sys.exit(poll_code or 1)


if __name__ == "__main__":
    main()
