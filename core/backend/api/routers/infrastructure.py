from fastapi import APIRouter
from typing import List, Dict

router = APIRouter(tags=["infrastructure"])

# ── Integrations ─────────────────────────────────────────────────────────────
@router.get("/integrations", response_model=List[Dict])
def get_integrations():
    """Mock endpoint for connected integrations."""
    return [
        {"id": "int_1", "provider": "hubspot", "status": "connected"},
        {"id": "int_2", "provider": "salesforce", "status": "disconnected"}
    ]

# ── Webhooks ─────────────────────────────────────────────────────────────────
@router.get("/webhooks", response_model=List[Dict])
def get_webhooks():
    """Mock endpoint for webhooks."""
    return [
        {"id": "wh_1", "url": "https://hook.site/elein", "events": ["lead.replied", "campaign.completed"]}
    ]

# ── Billing ──────────────────────────────────────────────────────────────────
@router.get("/billing", response_model=Dict)
def get_billing():
    """Mock endpoint for billing details."""
    return {
        "plan": "Pro",
        "billing_cycle": "monthly",
        "next_invoice_date": "2026-09-24",
        "credits_remaining": 12500
    }

# ── Workspace Settings ───────────────────────────────────────────────────────
@router.get("/workspace", response_model=Dict)
def get_workspace_settings():
    """Mock endpoint for workspace settings."""
    return {
        "name": "Ele-in Default Workspace",
        "timezone": "America/New_York",
        "team_size": 3
    }

# ── System Keys ──────────────────────────────────────────────────────────────
@router.get("/keys", response_model=Dict)
def get_system_keys():
    """Endpoint for returning system keys (e.g. Deepgram API)."""
    import os
    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key or key == "your_deepgram_api_key_here":
        import logging
        logging.getLogger(__name__).warning("DEEPGRAM_API_KEY is not configured in backend/.env")
    return {
        "DEEPGRAM_API_KEY": key
    }
