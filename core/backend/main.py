from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from leads.backend.routers import leads
from admin.backend.routers import settings
from campaigns.backend.routers import elein
from inbox.backend.routers import inbox
from inbox.backend.routers import notifications
from core.backend.api.routers import approvals
from knowledge.backend.routers import assets
from core.backend.api.routers import infrastructure
from campaigns.backend.routers import master_view
from knowledge.backend.routers import ai_routes
from core.backend.core.exceptions import setup_exception_handlers
from core.backend.core.logging import setup_logging
from core.backend.core.security import setup_security

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi.responses import JSONResponse
import sentry_sdk

def _safe_float(val: Optional[str], default: float) -> float:
    if not val:
        return default
    try:
        parsed = float(val)
        return max(0.0, min(1.0, parsed))
    except (ValueError, TypeError):
        return default

def _sentry_before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Paranoia Layer 2: Scrub sensitive auth headers and tokens before transmitting to Sentry
    request_data = event.get("request")
    if request_data and isinstance(request_data, dict):
        headers = request_data.get("headers")
        if headers and isinstance(headers, dict):
            sensitive_keys = {"authorization", "cookie", "x-api-key", "set-cookie", "x-razorpay-signature"}
            for k in list(headers.keys()):
                if k.lower() in sensitive_keys:
                    headers[k] = "[SCRUBBED]"
    return event

SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    try:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.environ.get("ENVIRONMENT", "production"),
            release=os.environ.get("APP_VERSION", "3.0.0"),
            traces_sample_rate=_safe_float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE"), 0.2),
            profiles_sample_rate=_safe_float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE"), 0.1),
            send_default_pii=False,
            before_send=_sentry_before_send,
        )
        logging.getLogger(__name__).info("Sentry initialized with environment: %s", os.environ.get("ENVIRONMENT", "production"))
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to initialize Sentry: {e}")
else:
    logging.getLogger(__name__).warning("SENTRY_DSN not set, skipping Sentry initialization.")

# 1. Setup structured logging
setup_logging()

# 2. Initialize FastAPI app
app = FastAPI(
    title="Ele-in API",
    description="Backend API for Ele-in.",
    version="3.0.0"
)

# Paranoia Hardening (VULN-14): Authenticated Media Router for voice notes and attachments
from core.backend.routers import media as media_router
app.include_router(media_router.router)

# 3. Setup middlewares
app.add_middleware(CorrelationIdMiddleware)

# Paranoia Layer 1: Configurable CORS allow-list with credentials protection
raw_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "")
if raw_allowed_origins.strip():
    allowed_origins = [o.strip() for o in raw_allowed_origins.split(",") if o.strip()]
    allow_credentials = "*" not in allowed_origins
else:
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        allowed_origins = [
            "https://ele-in.com",
            "https://app.ele-in.com",
            "https://elein.in",
            "https://app.elein.in",
        ]
        allow_credentials = True
    else:
        allowed_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "*",
        ]
        allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Setup exception handlers & security (rate limiting, secure headers)
setup_exception_handlers(app)
setup_security(app)

from fastapi import Depends
from core.backend.api.auth_dep import get_current_user_id, get_current_workspace

# 5. Include API routers
app.include_router(settings.router, prefix="/api/settings", dependencies=[Depends(get_current_user_id)])
app.include_router(leads.router, prefix="/api/leads", tags=["leads"], dependencies=[Depends(get_current_workspace)])

from campaigns.backend.routers import inbound_webhooks, sender_pods, roi_certificates, social_prewarm, bandit_router, event_multimodal_router, abm_router, boomerang_router, displacement_router, calendar_concierge_router, waterfall_enrichment_router, warmup_router, crm_attribution_router, advocacy_pod_router, unsubscribe
app.include_router(inbound_webhooks.router, prefix="/api")
app.include_router(sender_pods.router, dependencies=[Depends(get_current_workspace)])
app.include_router(roi_certificates.router)
# RFC 8058 One-Click Unsubscribe (Public / Unauthenticated)
app.include_router(unsubscribe.router, prefix="/api/elein")
app.include_router(unsubscribe.router, prefix="/api")
app.include_router(unsubscribe.router)
app.include_router(social_prewarm.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(bandit_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(event_multimodal_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(abm_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(boomerang_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(displacement_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(calendar_concierge_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(waterfall_enrichment_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(warmup_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(crm_attribution_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(advocacy_pod_router.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(elein.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(inbox.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(notifications.router, prefix="/api/elein")

from core.backend.api.routers import billing
app.include_router(billing.router, prefix="/api/elein/billing")

from core.backend.api.rate_limit import enforce_ai_rate_limit
app.include_router(ai_routes.router, prefix="/api/elein/inbox", dependencies=[Depends(get_current_workspace), Depends(enforce_ai_rate_limit)])

app.include_router(approvals.router, prefix="/api")

app.include_router(master_view.router, dependencies=[Depends(get_current_workspace)])
from core.backend.api.routers import proxies
app.include_router(proxies.router, prefix="/api/proxies", dependencies=[Depends(get_current_workspace)])
app.include_router(assets.router, prefix="/api/assets", dependencies=[Depends(get_current_workspace)])
# Mounted at /api/system — matches frontend useDeepgram.ts expectation
app.include_router(infrastructure.router, prefix="/api/system", dependencies=[Depends(get_current_workspace)])
from admin.backend.routers import personas
from integrations.backend.routers import hubspot
from integrations.backend.routers import extension
from admin.backend.routers import workspaces
app.include_router(personas.router, prefix="/api/knowledge", dependencies=[Depends(get_current_workspace)])
from knowledge.backend.routers import bayesian_icp
app.include_router(bayesian_icp.router)
from knowledge.backend.routers import ai_gateway
app.include_router(ai_gateway.router, dependencies=[Depends(get_current_workspace)])
from integrations.backend.routers import api_keys, webhooks
app.include_router(api_keys.router, prefix="/api/integrations/api-keys", dependencies=[Depends(get_current_workspace)])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"], dependencies=[Depends(get_current_workspace)])
app.include_router(hubspot.router, prefix="/api/elein/hubspot", dependencies=[Depends(get_current_workspace)])
app.include_router(extension.router, prefix="/api/extension")
app.include_router(workspaces.router, dependencies=[Depends(get_current_user_id)])


from core.backend.api.routers import agencies
app.include_router(agencies.router, prefix="/api/agencies", dependencies=[Depends(get_current_user_id)])
from core.backend.api.routers import error_logger
app.include_router(error_logger.router, prefix="/api/elein")
from admin.backend.routers.onboarding import router as onboarding_router
app.include_router(onboarding_router, prefix="/api", dependencies=[Depends(get_current_user_id)])
import sys

# ── Unauthenticated Liveness & Readiness Probes (Paranoia Layer 0 & 1) ───────────
@app.get("/health", tags=["system"], summary="Liveness probe for container orchestrators")
@app.get("/api/health", tags=["system"], summary="Liveness probe for API reverse proxy")
def liveness_probe():
    """
    Paranoia Layer 0 & 1: Fast unauthenticated liveness probe for container orchestrators,
    load balancers, and external uptime monitors. Never throws or performs blocking I/O.
    """
    return {
        "status": "healthy",
        "service": "ele-in-backend",
        "version": app.version,
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/ready", tags=["system"], summary="Readiness probe verifying DB connectivity")
@app.get("/api/ready", tags=["system"], summary="Readiness probe for API reverse proxy")
def readiness_probe():
    """
    Paranoia Layer 0 & 1: Unauthenticated readiness probe verifying database connectivity
    and essential services before routing traffic. Returns HTTP 200 if connected, or
    HTTP 503 with degraded status if unreachable.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from core.backend.api.auth_dep import get_service_client
        svc = get_service_client()
        if not svc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "database": "unconfigured",
                    "service": "ele-in-backend",
                    "version": app.version,
                    "error": "Database service client is unconfigured",
                    "timestamp": now_iso
                }
            )
        # Fast query with minimal overhead to verify PostgREST connection
        svc.table("workspaces").select("id").limit(1).execute()
        return {
            "status": "ready",
            "database": "connected",
            "service": "ele-in-backend",
            "version": app.version,
            "timestamp": now_iso
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("Readiness probe check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "database": "unreachable",
                "service": "ele-in-backend",
                "version": app.version,
                "error": str(exc),
                "timestamp": now_iso
            }
        )

@app.on_event("startup")
def detect_route_collisions():
    seen_routes = {}
    collisions = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                key = f"{method} {route.path}"
                if key in seen_routes:
                    collisions.append(f"Collision detected: {key} is registered by {seen_routes[key].name} and {route.name}")
                else:
                    seen_routes[key] = route
    if collisions:
        print("\n".join(collisions))
        print("CRITICAL: Route collisions detected. Shutting down to prevent silent overwrites.")
        sys.exit(1)

# NOTE: The campaign execution engine runs as a separate process: run 'python -m core.backend.workers.orchestrator_worker'

# 6. Instrument with Prometheus metrics
import os
import secrets
from fastapi import Request, Depends, HTTPException

def verify_metrics_token(request: Request):
    expected_token = os.environ.get("METRICS_TOKEN")
    if not expected_token:
        raise HTTPException(status_code=403, detail="Metrics token not configured")
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Invalid or missing Authorization header")
    
    token = auth_header.split(" ")[1]
    if not secrets.compare_digest(token, expected_token):
        raise HTTPException(status_code=403, detail="Invalid token")

Instrumentator().instrument(app).expose(app, dependencies=[Depends(verify_metrics_token)])

import asyncio

@app.on_event("startup")
async def start_outbox_poller():
    try:
        from inbox.backend.services.outbox_worker import run_outbox_poller
        asyncio.create_task(run_outbox_poller())
    except ImportError:
        print("Warning: outbox_worker module not found, skipping poller.")

@app.on_event("startup")
def start_webhook_poller():
    try:
        import threading
        from core.backend.workers.webhook_worker import poll_webhooks
        # Using a daemon thread since the webhook worker is currently synchronous 
        # to avoid the macOS AsyncClient SSL bug.
        threading.Thread(target=poll_webhooks, daemon=True).start()
    except Exception as e:
        print(f"Warning: Failed to start webhook poller: {e}")

@app.on_event("startup")
def startup_ensure_storage_bucket():
    try:
        from core.backend.services.storage_service import ensure_bucket_exists
        ensure_bucket_exists()
    except Exception as e:
        print(f"Warning: Failed to ensure storage bucket on startup: {e}")

