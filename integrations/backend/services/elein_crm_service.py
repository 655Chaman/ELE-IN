import os
import requests
import logging

logger = logging.getLogger(__name__)

def push_to_hubspot(lead_data: dict, lifecycle_stage: str = "lead", api_key: str = None, supabase=None) -> bool:
    """Pushes a lead to HubSpot Contacts API, creates a Deal, and associates them."""
    api_key = api_key or os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not api_key:
        logger.warning("[CRM] No HUBSPOT_ACCESS_TOKEN set. Skipping HubSpot push.")
        return False
        
    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 1. Create or Find Contact
    payload = {
        "properties": {
            "firstname": lead_data.get("first_name", ""),
            "lastname": lead_data.get("last_name", ""),
            "email": lead_data.get("email", ""),
            "company": lead_data.get("company") or lead_data.get("company_name", ""),
            "jobtitle": lead_data.get("title") or lead_data.get("job_title", ""),
            # linkedin_profile isn't a default hs_ property, omitting to prevent 400 errors
            "lifecyclestage": lifecycle_stage
        }
    }
    
    try:
        import re
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        contact_id = None
        
        if res.status_code in (200, 201):
            contact_id = res.json().get("id")
        elif res.status_code == 409:
            # Contact already exists
            match = re.search(r"Existing ID: (\d+)", res.json().get("message", ""))
            if match:
                contact_id = match.group(1)
                
        if not contact_id:
            logger.error(f"[CRM] Failed to get/create HubSpot contact. Response: {res.text}")
            return False
            
        # 2. Create Deal
        deal_url = "https://api.hubapi.com/crm/v3/objects/deals"
        name = f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip()
        company = lead_data.get("company") or lead_data.get("company_name")
        deal_name = f"{name} @ {company}" if company else name
        
        deal_payload = {
            "properties": {
                "dealname": deal_name
                # Omitting dealstage/pipeline to fallback to HubSpot defaults
            }
        }
        deal_res = requests.post(deal_url, headers=headers, json=deal_payload, timeout=10)
        if deal_res.status_code not in (200, 201):
            logger.error(f"[CRM] Failed to create HubSpot deal. Response: {deal_res.text}")
            return False
            
        deal_id = deal_res.json().get("id")
        
        # 3. Associate Deal with Contact
        assoc_url = f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact"
        assoc_res = requests.put(assoc_url, headers=headers, timeout=10)
        if assoc_res.status_code not in (200, 201, 204):
            logger.error(f"[CRM] Failed to associate deal {deal_id} with contact {contact_id}. Response: {assoc_res.text}")
        
        # 4. Save hubspot_deal_id to leads table
        lead_id = lead_data.get("id")
        if lead_id and supabase:
            try:
                supabase.table("leads").update({"hubspot_deal_id": str(deal_id)}).eq("id", lead_id).execute()
            except Exception as db_e:
                logger.error(f"[CRM] Failed to save hubspot_deal_id to DB for lead {lead_id}: {db_e}")
                
        return True
    except Exception as e:
        logger.error(f"[CRM] HubSpot API error: {e}")
        
    return False


def add_to_smartlead(lead_data: dict, campaign_id: str) -> bool:
    """Pushes a lead to Smartlead API."""
    api_key = os.environ.get("SMARTLEAD_API_KEY")
    if not api_key:
        logger.warning("[CRM] No SMARTLEAD_API_KEY set. Skipping Smartlead push.")
        return False
        
    if not campaign_id:
        logger.warning("[CRM] Smartlead push requires a campaign_id.")
        return False
        
    # Smartlead Lead Add API endpoint (Example structure)
    url = f"https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "api_key": api_key,
        "leadList": [
            {
                "firstName": lead_data.get("first_name", ""),
                "lastName": lead_data.get("last_name", ""),
                "email": lead_data.get("email", ""),
                "companyName": lead_data.get("company", ""),
                "customFields": {
                    "linkedin_url": lead_data.get("linkedin_url", ""),
                    "ai_icebreaker": lead_data.get("ai_hook", "")
                }
            }
        ]
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        return res.status_code in (200, 201)
    except Exception as e:
        logger.error(f"[CRM] Smartlead API error: {e}")
        
    return False



def add_to_instantly(lead_data: dict, campaign_id: str) -> bool:
    api_key = os.environ.get("INSTANTLY_API_KEY")
    if not api_key or not campaign_id: return False
    url = f"https://api.instantly.ai/api/v1/lead/add"
    payload = {
        "api_key": api_key,
        "campaign_id": campaign_id,
        "skip_if_in_workspace": True,
        "leads": [{
            "email": lead_data.get("email", ""),
            "first_name": lead_data.get("first_name", ""),
            "last_name": lead_data.get("last_name", ""),
            "company_name": lead_data.get("company", ""),
            "personalization": lead_data.get("ai_hook", "")
        }]
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code in (200, 201)
    except: return False

def add_to_lemlist(lead_data: dict, campaign_id: str) -> bool:
    api_key = os.environ.get("LEMLIST_API_KEY")
    if not api_key or not campaign_id: return False
    url = f"https://api.lemlist.com/api/campaigns/{campaign_id}/leads"
    try:
        res = requests.post(url, auth=("", api_key), json=lead_data, timeout=10)
        return res.status_code in (200, 201)
    except: return False

def push_to_salesforce(lead_data: dict) -> bool:
    # Requires OAuth/Bearer token which usually rotates. Assuming static for now via integration user.
    access_token = os.environ.get("SALESFORCE_ACCESS_TOKEN")
    instance_url = os.environ.get("SALESFORCE_INSTANCE_URL")
    if not access_token or not instance_url: return False
    
    url = f"{instance_url}/services/data/v58.0/sobjects/Lead/"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "FirstName": lead_data.get("first_name", ""),
        "LastName": lead_data.get("last_name", "Unknown"),
        "Company": lead_data.get("company", "Unknown"),
        "Email": lead_data.get("email", ""),
        "LeadSource": "EleIn LinkedIn Automation"
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        return res.status_code in (200, 201, 204)
    except: return False

def push_to_pipedrive(lead_data: dict) -> bool:
    api_key = os.environ.get("PIPEDRIVE_API_KEY")
    if not api_key: return False
    url = f"https://api.pipedrive.com/v1/persons?api_token={api_key}"
    payload = {
        "name": f"{lead_data.get('first_name','')} {lead_data.get('last_name','')}".strip(),
        "email": [{"value": lead_data.get("email", ""), "primary": True}],
        "org_name": lead_data.get("company", "")
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code in (200, 201)
    except: return False

def send_slack_alert(message: str, webhook_url: str = None) -> bool:
    webhook = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook: return False
    try:
        res = requests.post(webhook, json={"text": message}, timeout=10)
        return res.status_code == 200
    except: return False

def push_to_notion(lead_data: dict, database_id: str) -> bool:
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key or not database_id: return False
    url = "https://api.notion.com/v1/pages"
    headers = {"Authorization": f"Bearer {api_key}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": [{"text": {"content": f"{lead_data.get('first_name','')} {lead_data.get('last_name','')}".strip()}}]},
            "Email": {"email": lead_data.get("email", "")},
            "Company": {"rich_text": [{"text": {"content": lead_data.get("company", "")}}]},
            "LinkedIn": {"url": lead_data.get("linkedin_url", "")}
        }
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        return res.status_code == 200
    except: return False

def push_to_airtable(lead_data: dict, base_id: str, table_name: str) -> bool:
    api_key = os.environ.get("AIRTABLE_API_KEY")
    if not api_key or not base_id or not table_name: return False
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "records": [{
            "fields": {
                "First Name": lead_data.get("first_name", ""),
                "Last Name": lead_data.get("last_name", ""),
                "Email": lead_data.get("email", ""),
                "Company": lead_data.get("company", ""),
                "LinkedIn": lead_data.get("linkedin_url", "")
            }
        }]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        return res.status_code == 200
    except: return False

def send_webhook(lead_data: dict, webhook_url: str) -> bool:
    if not webhook_url: return False
    try:
        res = requests.post(webhook_url, json=lead_data, timeout=10)
        return res.status_code in (200, 201, 204)
    except: return False

def add_to_emailbison(lead_data: dict, campaign_id: str) -> bool:
    api_key = os.environ.get("EMAILBISON_API_KEY")
    if not api_key: return False
    url = f"https://api.emailbison.com/v1/campaigns/{campaign_id}/leads"
    try:
        res = requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=lead_data, timeout=10)
        return res.status_code in (200, 201)
    except: return False

def add_to_apollo(lead_data: dict, sequence_id: str) -> bool:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key: return False
    url = "https://api.apollo.io/v1/contacts"
    payload = {"api_key": api_key, "first_name": lead_data.get("first_name"), "last_name": lead_data.get("last_name"), "email": lead_data.get("email")}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code in (200, 201)
    except: return False
