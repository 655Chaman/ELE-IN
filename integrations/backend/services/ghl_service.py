"""
GoHighLevel (GHL) Service
Handles authentication and API calls to GoHighLevel CRM.
"""

import json
import os
from typing import Any

import structlog

logger = structlog.get_logger()

GHL_API_BASE = "https://services.leadconnectorhq.com"

def get_ghl_headers() -> dict[str, str]:
    """Returns headers required for GHL API v2."""
    api_key = os.getenv("GHL_API_KEY", "")
    return {
        "Authorization": f"Bearer {api_key}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

from core.backend.services.http_client import async_external_request

async def create_contact(location_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a contact in GHL."""
    url = f"{GHL_API_BASE}/contacts/"
    payload = {
        "locationId": location_id,
        **data
    }
    
    resp = await async_external_request(
        method="POST",
        url=url,
        json_data=payload,
        headers=get_ghl_headers(),
        timeout=10.0
    )
    
    if resp.status_code not in (200, 201):
        logger.error("ghl.create_contact.failed", status=resp.status_code)
        raise RuntimeError(f"GHL Create Contact Failed with status {resp.status_code}")
        
    return resp.json()

async def update_contact(contact_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Update an existing contact in GHL."""
    url = f"{GHL_API_BASE}/contacts/{contact_id}"
    
    resp = await async_external_request(
        method="PUT",
        url=url,
        json_data=data,
        headers=get_ghl_headers(),
        timeout=10.0
    )
    
    if resp.status_code not in (200, 201):
        logger.error("ghl.update_contact.failed", status=resp.status_code)
        raise RuntimeError(f"GHL Update Contact Failed with status {resp.status_code}")
        
    return resp.json()

async def add_contact_to_campaign(contact_id: str, campaign_id: str) -> dict[str, Any]:
    """Add a contact to a GHL campaign/workflow."""
    url = f"{GHL_API_BASE}/contacts/{contact_id}/campaigns/{campaign_id}"
    
    resp = await async_external_request(
        method="POST",
        url=url,
        headers=get_ghl_headers(),
        timeout=10.0
    )
    
    if resp.status_code not in (200, 201):
        logger.error("ghl.add_to_campaign.failed", status=resp.status_code)
        raise RuntimeError(f"GHL Add to Campaign Failed with status {resp.status_code}")
        
    return resp.json()
