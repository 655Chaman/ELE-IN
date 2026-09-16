import time
from fastapi import HTTPException, Depends
from core.backend.api.auth_dep import get_current_workspace

# In-memory rate limiter: workspace_id -> [timestamps]
_ai_rate_limits = {}

def enforce_ai_rate_limit(workspace_id: str = Depends(get_current_workspace)):
    now = time.time()
    # Clean up old timestamps (older than 60 seconds)
    if workspace_id not in _ai_rate_limits:
        _ai_rate_limits[workspace_id] = []
    
    _ai_rate_limits[workspace_id] = [t for t in _ai_rate_limits[workspace_id] if now - t < 60]
    
    if len(_ai_rate_limits[workspace_id]) >= 20:
        raise HTTPException(status_code=429, detail="Too Many Requests: AI rate limit exceeded (max 20 per minute)")
    
    _ai_rate_limits[workspace_id].append(now)
    return workspace_id
