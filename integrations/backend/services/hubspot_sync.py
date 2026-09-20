import logging
from core.backend.services.http_client import async_external_request
from campaigns.backend.routers.elein import _pause_lead_execution_core

logger = logging.getLogger(__name__)

async def sync_hubspot_deals_job(async_supabase, sync_supabase):
    """
    Polls HubSpot for all leads that have a hubspot_deal_id and checks 
    if the deal stage matches the workspace's configured hubspot_won_stage_id.
    If it matches, the lead's executions are paused.
    """
    try:
        # Fetch all workspaces that have a hubspot_won_stage_id configured and a token
        ws_res = await async_supabase.table("workspaces").select("id, hubspot_token, hubspot_won_stage_id").neq("hubspot_won_stage_id", "null").neq("hubspot_token", "null").execute()
        if not ws_res.data:
            return
            
        for ws in ws_res.data:
            ws_id = ws["id"]
            token = ws.get("hubspot_token")
            won_stage_id = ws.get("hubspot_won_stage_id")
            
            if not token or not won_stage_id:
                continue
                
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # Fetch leads for this workspace with an active deal
            leads_res = await async_supabase.table("leads").select("id, hubspot_deal_id").eq("workspace_id", ws_id).neq("hubspot_deal_id", "null").execute()
            if not leads_res.data:
                continue
                
            for lead in leads_res.data:
                deal_id = lead.get("hubspot_deal_id")
                if not deal_id:
                    continue
                    
                # Fetch deal from HubSpot
                deal_url = f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}"
                deal_resp = await async_external_request("GET", deal_url, headers=headers)
                
                # Check status via attributes or dict methods based on return type
                is_success = False
                if hasattr(deal_resp, "status_code"):
                    is_success = deal_resp.status_code == 200
                    deal_data = deal_resp.json() if is_success else {}
                elif isinstance(deal_resp, dict):
                    is_success = True
                    deal_data = deal_resp
                
                if is_success:
                    current_stage = deal_data.get("properties", {}).get("dealstage")
                    
                    if current_stage == won_stage_id:
                        logger.info(f"Deal {deal_id} for Lead {lead['id']} won! Pausing lead execution.")
                        try:
                            # Use sync client for pause_lead_execution
                            _pause_lead_execution_core(lead["id"], ws_id, sync_supabase, status_override="exited", error_reason_override="hubspot_deal_won")
                        except Exception as e:
                            logger.error(f"Failed to pause lead {lead['id']}: {e}")
                            
    except Exception as e:
        logger.error(f"Error in sync_hubspot_deals_job: {e}")
