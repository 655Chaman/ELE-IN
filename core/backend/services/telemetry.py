import logging
import json
from datetime import datetime
import traceback
import sys

logger = logging.getLogger(__name__)

def capture_error(e: Exception, context: dict = None):
    """
    Captures an exception with Sentry (if configured) AND logs it as a structured JSON log.
    Ensures that silent background job crashes are always surfaced to observability tools.
    """
    if context is None:
        context = {}
        
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(e)
    except ImportError:
        pass
        
    error_type = type(e).__name__
    
    # We use a custom dictionary to emit a structured log.
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "CRITICAL",
        "message": f"Unhandled exception: {str(e)}",
        "service": context.get("service", "backend_worker"),
        "error_type": error_type,
        "traceback": "".join(traceback.format_exception(type(e), e, e.__traceback__))
    }
    
    if "workspace_id" in context:
        log_data["workspace_id"] = context["workspace_id"]
        
    # We dump it as JSON directly to ensure log aggregators parse it correctly.
    print(json.dumps(log_data), file=sys.stderr)
    logger.critical(f"CRITICAL ERROR ({error_type}): {str(e)}", exc_info=True)


def emit_heartbeat(service_name: str):
    """
    Emits a structured JSON heartbeat log for a background service.
    Allows external monitoring tools to alert if a heartbeat is missing.
    """
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "INFO",
        "event": "cron_heartbeat",
        "service": service_name,
        "message": f"Heartbeat from {service_name}"
    }
    print(json.dumps(log_data))
    logger.info(f"Heartbeat emitted for {service_name}")
