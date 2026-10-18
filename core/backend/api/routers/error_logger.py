from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import json
import time
from collections import defaultdict
from typing import Optional, Any
import logging
from logging.handlers import RotatingFileHandler

frontend_logger = logging.getLogger("frontend_error_logger")
frontend_logger.setLevel(logging.INFO)
# Max 5MB per file, keep 2 backups
handler = RotatingFileHandler("frontend_errors.log", maxBytes=5*1024*1024, backupCount=2)
frontend_logger.addHandler(handler)

router = APIRouter()

class ErrorLog(BaseModel):
    message: Optional[str] = None
    filename: Optional[str] = None
    lineno: Optional[int] = None
    colno: Optional[int] = None
    error: Optional[str] = None

    class Config:
        extra = "ignore"

# Simple in-memory rate limiting: max 10 requests per IP per minute
_rate_limit_records = defaultdict(list)

def _truncate(val: Any, max_len: int = 5000) -> Any:
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len]
    return val

@router.post("/log_error")
async def log_error(request: Request, payload: ErrorLog):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Rate limit check
    window_start = current_time - 60
    _rate_limit_records[client_ip] = [t for t in _rate_limit_records[client_ip] if t > window_start]
    if len(_rate_limit_records[client_ip]) >= 10:
        raise HTTPException(status_code=429, detail="Too many requests")
    
    _rate_limit_records[client_ip].append(current_time)

    # Paranoia Layer 1: Bound memory - evict stale IPs if tracked set exceeds 1000
    if len(_rate_limit_records) > 1000:
        stale_ips = [ip for ip, timestamps in _rate_limit_records.items() if not timestamps or timestamps[-1] < window_start]
        for ip in stale_ips:
            _rate_limit_records.pop(ip, None)

    # Truncate strings
    data = {
        "message": _truncate(payload.message),
        "filename": _truncate(payload.filename),
        "lineno": payload.lineno,
        "colno": payload.colno,
        "error": _truncate(payload.error),
    }

    print("FRONTEND ERROR:", json.dumps(data, indent=2))
    frontend_logger.info(json.dumps(data))

    # Paranoia Layer 1: Forward fallback errors to Sentry if initialized
    try:
        import sentry_sdk
        scope_manager = getattr(sentry_sdk, "new_scope", getattr(sentry_sdk, "push_scope", None))
        if scope_manager:
            with scope_manager() as scope:
                scope.set_tag("source", "frontend_fallback")
                if payload.filename:
                    scope.set_tag("frontend_file", payload.filename)
                if payload.lineno is not None:
                    scope.set_extra("lineno", payload.lineno)
                if payload.colno is not None:
                    scope.set_extra("colno", payload.colno)
                if payload.error:
                    scope.set_extra("raw_error", _truncate(payload.error, 1000))
                scope.set_extra("client_ip", client_ip)
                sentry_sdk.capture_message(
                    f"Frontend Fallback Error: {payload.message or 'Unknown frontend error'}",
                    level="error"
                )
    except Exception as e:
        frontend_logger.warning(f"Could not forward frontend error to Sentry: {e}")

    return {"status": "ok"}
