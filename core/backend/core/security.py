import os
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from core.backend.api.rate_limit import get_client_ip

logger = structlog.get_logger()

# Limit requests per client IP with spoofing defense (CF-Connecting-IP, X-Real-IP, X-Forwarded-For)
# Paranoia Layer 1: Configurable default rate limit with safe SaaS SPA floor
default_rate_limit = os.environ.get("RATE_LIMIT_DEFAULT", "300/minute")
limiter = Limiter(key_func=get_client_ip, default_limits=[default_rate_limit])

def setup_security(app: FastAPI):
    # Setup SlowAPI rate limiting middleware
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        client_ip = get_client_ip(request)
        logger.warning("rate_limit_exceeded", client=client_ip, path=request.url.path)
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please slow down and try again later.",
                    "details": exc.detail
                }
            }
        )

    # Setup Comprehensive Enterprise Security Headers Middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        # HSTS, X-Content-Type-Options, Frame Guard, Anti-MIME Sniffing, Referrer Policy
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(self), payment=(self), usb=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

