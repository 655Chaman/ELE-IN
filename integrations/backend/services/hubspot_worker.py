import logging
from core.backend.services.http_client import async_external_request

logger = logging.getLogger(__name__)

async def import_hubspot_list_bg(supabase, workspace_id: str, hubspot_list_id: int, internal_list_id: str):
    # Fetch token
    res = supabase.table("workspaces").select("hubspot_token").eq("id", workspace_id).execute()
    if not res.data or not res.data[0].get("hubspot_token"):
        raise ValueError("HubSpot not connected")
    
    access_token = res.data[0]["hubspot_token"]
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    has_more = True
    vid_offset = 0
    all_leads = []
    
    while has_more:
        url = f"https://api.hubapi.com/contacts/v1/lists/{hubspot_list_id}/contacts/all?count=100&property=firstname&property=lastname&property=company&property=linkedin&property=city"
        if vid_offset > 0:
            url += f"&vidOffset={vid_offset}"
            
        resp = await async_external_request("GET", url, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"Failed to fetch HubSpot contacts: {resp.text}")
            
        data = resp.json()
        contacts = data.get("contacts", [])
        
        for contact in contacts:
            props = contact.get("properties", {})
            first_name = props.get("firstname", {}).get("value", "")
            last_name = props.get("lastname", {}).get("value", "")
            company = props.get("company", {}).get("value", "")
            linkedin = props.get("linkedin", {}).get("value", "")
            city = props.get("city", {}).get("value", "")
            
            # Map HubSpot fields to lead fields
            all_leads.append({
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company,
                "linkedin_url": linkedin,
                "p_location": city
            })
            
        has_more = data.get("has-more", False)
        vid_offset = data.get("vid-offset", 0)
        
        if not has_more:
            break
            
    # Now call bulk_import_leads
    if all_leads:
        rpc_res = supabase.rpc("bulk_import_leads", {
            "p_list_id": internal_list_id,
            "p_workspace_id": workspace_id,
            "p_leads": all_leads
        }).execute()
        
        inserted = rpc_res.data.get("inserted_count", 0) if rpc_res.data else len(all_leads)
        supabase.table("lead_lists").update({"status": "completed", "row_count": inserted}).eq("id", internal_list_id).execute()
    else:
        supabase.table("lead_lists").update({"status": "completed", "row_count": 0}).eq("id", internal_list_id).execute()
