from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import json
import time
from collections import defaultdict
from typing import Optional, Any

router = APIRouter()

class ErrorLog(BaseModel):
    message: Optional[str] = None
    filename: Optional[str] = None
    lineno: Optional[int] = None
    colno: Optional[int] = None
    error: Optional[str] = None

    class Config:
        extra = "forbid"

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

    # Truncate strings
    data = {
        "message": _truncate(payload.message),
        "filename": _truncate(payload.filename),
        "lineno": payload.lineno,
        "colno": payload.colno,
        "error": _truncate(payload.error),
    }

    print("FRONTEND ERROR:", json.dumps(data, indent=2))
    with open("frontend_errors.log", "a") as f:
        f.write(json.dumps(data) + "\n")
    return {"status": "ok"}
