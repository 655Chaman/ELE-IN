from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from leads.backend.routers import leads
from admin.backend.routers import settings
from campaigns.backend.routers import elein
from inbox.backend.routers import inbox
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
import sentry_sdk

SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=1.0)
else:
    logging.getLogger(__name__).warning("SENTRY_DSN not set, skipping Sentry initialization.")

# 1. Setup structured logging
setup_logging()

# 2. Initialize FastAPI app
app = FastAPI(
    title="LeadGen OS API - Production",
    description="Backend API for the HIPAA Lead Generation Dashboard, hardened with agent skills.",
    version="3.0.0"
)

# 3. Setup middlewares
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174", "*"],
    allow_credentials=False, # Must be false if origins is *
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

app.include_router(elein.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
app.include_router(inbox.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])
from core.backend.api.rate_limit import enforce_ai_rate_limit
app.include_router(ai_routes.router, prefix="/api/elein/inbox", dependencies=[Depends(get_current_workspace), Depends(enforce_ai_rate_limit)])

# TODO: approvals.py contains no routes yet — mount commented out until implemented
# app.include_router(approvals.router, prefix="/api/elein", dependencies=[Depends(get_current_workspace)])

app.include_router(master_view.router, dependencies=[Depends(get_current_workspace)])
app.include_router(assets.router, prefix="/api/assets", dependencies=[Depends(get_current_workspace)])
# Mounted at /api/system — matches frontend useDeepgram.ts expectation
app.include_router(infrastructure.router, prefix="/api/system", dependencies=[Depends(get_current_workspace)])
from admin.backend.routers import personas
from integrations.backend.routers import hubspot
from integrations.backend.routers import apollo
from integrations.backend.routers import extension
from admin.backend.routers import workspaces
app.include_router(personas.router, prefix="/api/knowledge", dependencies=[Depends(get_current_workspace)])
app.include_router(hubspot.router, prefix="/api/elein/hubspot", dependencies=[Depends(get_current_workspace)])
app.include_router(apollo.router, prefix="/api/elein/apollo", dependencies=[Depends(get_current_workspace)])
app.include_router(extension.router, prefix="/api/extension")
app.include_router(workspaces.router, dependencies=[Depends(get_current_user_id)])

from core.backend.api.routers import agencies
from core.backend.api.routers import error_logger
app.include_router(error_logger.router, prefix="/api/elein")
from admin.backend.routers.onboarding import router as onboarding_router
app.include_router(onboarding_router, prefix="/api", dependencies=[Depends(get_current_user_id)])
import sys


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
Instrumentator().instrument(app).expose(app)

import asyncio

@app.on_event("startup")
async def start_outbox_poller():
    try:
        from inbox.backend.services.outbox_worker import run_outbox_poller
        asyncio.create_task(run_outbox_poller())
    except ImportError:
        print("Warning: outbox_worker module not found, skipping poller.")
