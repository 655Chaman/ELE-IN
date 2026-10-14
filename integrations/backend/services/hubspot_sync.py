import logging
import os
from typing import Dict, Any, List
from core.backend.services.http_client import async_external_request
from campaigns.backend.routers.elein import _pause_lead_execution_core

logger = logging.getLogger(__name__)

BATCH_DEAL_LIMIT = 100

async def sync_hubspot_deals_job(async_supabase, sync_supabase):
    """
    Paranoia Layer 0, 1 & 2: HubSpot CRM Deal State Poller.
    - Layer 0: Uses HubSpot CRM v3 Batch Read API (POST /crm/v3/objects/deals/batch/read)
      reducing HTTP calls by 99% (up to 100 deals per call).
    - Layer 1: Only polls deals for leads with ACTIVE in-flight execution states
      ('pending', 'running', 'waiting_for_reply'), completely stopping zombie polling
      for already-exited/won leads.
    - Layer 1 & 2: Handles 401/403 (token revoked/expired) by queuing an outbox in-app
      alert and breaking cleanly. Handles 429 rate limits without crashing the worker.
    """
    try:
        # 1. Fetch workspaces configured for HubSpot deal won tracking
        ws_res = await async_supabase.table("workspaces") \
            .select("id, hubspot_token, hubspot_won_stage_id") \
            .neq("hubspot_won_stage_id", "null") \
            .neq("hubspot_token", "null") \
            .execute()
        if not ws_res.data:
            return

        for ws in ws_res.data:
            ws_id = ws["id"]
            token = ws.get("hubspot_token")
            won_stage_id = ws.get("hubspot_won_stage_id")

            if not token or not won_stage_id or token == "null":
                continue

            # Layer 1 Paranoia: Find leads in this workspace that actually have ACTIVE in-flight executions
            try:
                active_states = await async_supabase.table("campaign_execution_states") \
                    .select("opportunity_id") \
                    .eq("workspace_id", ws_id) \
                    .in_("status", ["pending", "running", "waiting_for_reply"]) \
                    .execute()
                active_lead_ids = {
                    r["opportunity_id"] for r in (active_states.data or [])
                    if isinstance(r, dict) and r.get("opportunity_id")
                }
            except Exception as active_err:
                logger.warning(f"Could not query active execution states for ws {ws_id}: {active_err}")
                active_lead_ids = None

            # If active states exist, filter leads; if query failed, fallback to querying all
            leads_query = async_supabase.table("leads") \
                .select("id, hubspot_deal_id") \
                .eq("workspace_id", ws_id) \
                .neq("hubspot_deal_id", "null")
            
            if active_lead_ids is not None:
                if not active_lead_ids:
                    # No active executions in this workspace — zero need to poll HubSpot!
                    continue
                leads_query = leads_query.in_("id", list(active_lead_ids))

            leads_res = await leads_query.execute()
            leads = leads_res.data or []
            if not leads:
                continue

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            # Map deal_id -> lead_id
            deal_to_lead: Dict[str, str] = {}
            for l in leads:
                did = str(l.get("hubspot_deal_id") or "").strip()
                if did and did != "null":
                    deal_to_lead[did] = l["id"]

            if not deal_to_lead:
                continue

            deal_ids = list(deal_to_lead.keys())
            
            # Batch process deals in chunks of BATCH_DEAL_LIMIT (100)
            for i in range(0, len(deal_ids), BATCH_DEAL_LIMIT):
                chunk_deal_ids = deal_ids[i:i + BATCH_DEAL_LIMIT]
                batch_url = "https://api.hubapi.com/crm/v3/objects/deals/batch/read"
                batch_body = {
                    "inputs": [{"id": did} for did in chunk_deal_ids],
                    "properties": ["dealstage"]
                }

                try:
                    resp = await async_external_request(
                        "POST",
                        batch_url,
                        headers=headers,
                        json_data=batch_body,
                        timeout=15.0
                    )

                    status_code = getattr(resp, "status_code", 200)

                    # Token expired / unauthorized
                    if status_code in (401, 403):
                        logger.error(f"[HubSpotSync] Unauthorized ({status_code}) for workspace {ws_id}. Token is expired or revoked.")
                        try:
                            sync_supabase.table("outbox_events").insert({
                                "workspace_id": ws_id,
                                "event_type": "notification.in_app",
                                "payload": {
                                    "title": "HubSpot Connection Expired",
                                    "message": "Your HubSpot integration token has expired or been revoked. Deal auto-pause is inactive. Please reconnect in Settings → Integrations."
                                },
                                "status": "pending"
                            }).execute()
                        except Exception as n_err:
                            logger.warning(f"Failed to queue outbox notification: {n_err}")
                        break  # Stop checking this workspace

                    if status_code == 429:
                        logger.warning(f"[HubSpotSync] Rate limit (429) hit for workspace {ws_id}. Backing off.")
                        break

                    if status_code != 200:
                        logger.warning(f"[HubSpotSync] Batch read failed ({status_code}): {getattr(resp, 'text', '')}")
                        continue

                    data = resp.json() if hasattr(resp, "json") else (resp if isinstance(resp, dict) else {})
                    results = data.get("results", [])

                    for deal in results:
                        did = str(deal.get("id", ""))
                        props = deal.get("properties", {})
                        current_stage = props.get("dealstage")

                        if current_stage == won_stage_id and did in deal_to_lead:
                            target_lead_id = deal_to_lead[did]
                            logger.info(f"Deal {did} for Lead {target_lead_id} reached won stage ({won_stage_id})! Halting outreach.")
                            try:
                                _pause_lead_execution_core(
                                    target_lead_id,
                                    ws_id,
                                    sync_supabase,
                                    status_override="exited",
                                    error_reason_override="hubspot_deal_won"
                                )
                            except Exception as pause_err:
                                logger.error(f"Failed to pause lead {target_lead_id}: {pause_err}")

                except Exception as chunk_err:
                    status_err = getattr(chunk_err, "status_code", None)
                    if status_err == 429:
                        logger.warning(f"[HubSpotSync] Rate limit (429) hit for workspace {ws_id}. Backing off.")
                        break
                    logger.error(f"Error processing HubSpot deal batch chunk: {chunk_err}")

    except Exception as e:
        logger.error(f"Error in sync_hubspot_deals_job: {e}")
