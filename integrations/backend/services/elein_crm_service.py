from typing import Optional, Dict, Any, List, Set, Union, Tuple
import os
import requests
import logging

class RateLimitExceeded(Exception):
    pass

logger = logging.getLogger(__name__)

def _safe_refund_credits(workspace_id: str, amount: int, idempotency_key: str, supabase_client=None, reason: str = "system_refund") -> bool:
    """
    Paranoia Layer 0, 1 & 2: Idempotent credit refund helper on external failure.
    Ensures deducted credits are restored whenever a 3rd-party integration fails,
    rate-limits (429), drops connections, or encounters poison pill payloads.
    """
    if not workspace_id or not idempotency_key:
        return False
    clean_key = str(idempotency_key).strip()
    if str(workspace_id) not in clean_key:
        event_id = f"refund_{workspace_id}_{clean_key}"
    else:
        event_id = clean_key if clean_key.startswith("refund_") else f"refund_{clean_key}"
    safe_amount = max(1, int(amount or 1))

    # 1. Direct call on passed supabase_client if present
    if supabase_client:
        try:
            supabase_client.rpc('add_credits_safely', {
                'p_workspace_id': workspace_id,
                'p_credits': safe_amount,
                'p_event_id': event_id,
                'p_provider': reason
            }).execute()
            return True
        except Exception as e:
            logger.error(f"[CRM] Refund via passed supabase_client failed: {e}")

    # 2. Call credit_service.refund_credits
    try:
        from core.backend.services.credit_service import refund_credits
        res = refund_credits(workspace_id=workspace_id, amount=safe_amount, idempotency_key=event_id, reason=reason)
        if isinstance(res, dict) and res.get("success"):
            return True
    except Exception as e:
        logger.warning(f"[CRM] refund_credits helper failed: {e}")

    # 3. Direct RPC fallback via get_service_client
    try:
        from core.backend.api.auth_dep import get_service_client
        client = get_service_client()
        if client:
            client.rpc('add_credits_safely', {
                'p_workspace_id': workspace_id,
                'p_credits': safe_amount,
                'p_event_id': event_id,
                'p_provider': reason
            }).execute()
            return True
    except Exception as e:
        logger.error(f"[CRM] Direct RPC refund failed for {workspace_id} ({event_id}): {e}")

    return False

def push_to_hubspot(workspace_id: str, lead_data: dict, lifecycle_stage: str = "lead", api_key: str = None, supabase=None) -> bool:
    """Pushes a lead to HubSpot Contacts API, creates a Deal, and associates them."""
    is_platform = False
    if not api_key:
        api_key = os.environ.get("HUBSPOT_ACCESS_TOKEN")
        is_platform = True
    if not api_key:
        logger.warning("[CRM] No HUBSPOT_ACCESS_TOKEN set. Skipping HubSpot push.")
        return False
        
    idempotency_key = None
    supabase_client = None
    deducted = False
    if is_platform and workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import time
        supabase_client = supabase or get_service_client()
        import uuid
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"hubspot_{workspace_id}_{lead_ident}"
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': 1,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True
        
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
        
        if res.status_code == 429:
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            raise RateLimitExceeded("HubSpot Rate Limit 429")
            
        if res.status_code in (200, 201):
            contact_id = res.json().get("id")
        elif res.status_code == 400:
            logger.error(f"[CRM] HubSpot 400 Bad Request (Poison Pill lead). Skipping lead: {res.text}")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            return False
        elif res.status_code == 409:
            # Contact already exists
            match = re.search(r"Existing ID: (\d+)", res.json().get("message", ""))
            if match:
                contact_id = match.group(1)
                
        if not contact_id:
            logger.error(f"[CRM] Failed to get/create HubSpot contact. Response: {res.text}")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
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
        if deal_res.status_code == 429:
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            raise RateLimitExceeded("HubSpot Deal Rate Limit 429")
        if deal_res.status_code not in (200, 201):
            logger.error(f"[CRM] Failed to create HubSpot deal. Response: {deal_res.text}")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            return False
            
        deal_id = deal_res.json().get("id")
        
        # 3. Associate Deal with Contact
        assoc_url = f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact"
        assoc_res = requests.put(assoc_url, headers=headers, timeout=10)
        if assoc_res.status_code not in (200, 201, 204):
            logger.error(f"[CRM] Failed to associate deal {deal_id} with contact {contact_id}. Response: {assoc_res.text}")
        
        # 4. Save hubspot_deal_id to leads table
        lead_id = lead_data.get("id")
        if lead_id and (supabase or supabase_client):
            db = supabase or supabase_client
            try:
                db.table("leads").update({"hubspot_deal_id": str(deal_id)}).eq("id", lead_id).execute()
            except Exception as db_e:
                logger.error(f"[CRM] Failed to save hubspot_deal_id to DB for lead {lead_id}: {db_e}")
                
        return True
    except RateLimitExceeded:
        raise
    except Exception as e:
        logger.error(f"[CRM] HubSpot API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        
    return False


def _clean_and_dedup_crm_leads(leads: list) -> list:
    """
    Paranoia Layer 0, 1 & 2:
    Filters out empty or invalid emails, deduplicates intra-batch records by canonical email,
    and sanitizes textual fields against CSV / spreadsheet formula injection.
    """
    if not isinstance(leads, list):
        return []
    import re
    seen_emails = set()
    cleaned = []
    email_regex = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for item in leads:
        if not isinstance(item, dict):
            continue
        raw_email = str(item.get("email") or "").strip().lower()
        if not raw_email or not email_regex.match(raw_email):
            continue
        if raw_email in seen_emails:
            continue
        seen_emails.add(raw_email)

        # Paranoia Layer 2: Formula injection protection on lead fields
        cleaned_lead = dict(item)
        cleaned_lead["email"] = raw_email
        for field in ("first_name", "last_name", "company", "title", "ai_hook"):
            if field in cleaned_lead and isinstance(cleaned_lead[field], str):
                val = cleaned_lead[field].strip()
                if val and val[0] in ("=", "+", "-", "@"):
                    cleaned_lead[field] = f"'{val}"
                else:
                    cleaned_lead[field] = val
        cleaned.append(cleaned_lead)
    return cleaned


def add_to_smartlead(workspace_id: str, leads: list, campaign_id: str) -> bool:
    """Pushes a batch of leads to Smartlead API with circuit breaking, deduplication, chunking and resilience."""
    import os, requests, logging
    logger = logging.getLogger(__name__)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("smartlead")
    if not cb.can_execute():
        logger.error("[CRM] Smartlead circuit breaker is OPEN. Skipping push.")
        return False

    api_key = os.environ.get("SMARTLEAD_API_KEY")
    if not api_key:
        logger.warning("[CRM] No SMARTLEAD_API_KEY set. Skipping Smartlead push.")
        return False
        
    if not leads:
        return True

    if not campaign_id:
        logger.warning("[CRM] Smartlead push requires a campaign_id.")
        return False

    # Paranoia Layer 0, 1 & 2: Filter invalid emails, intra-batch deduplicate, and formula-sanitize
    valid_leads = _clean_and_dedup_crm_leads(leads)
    if not valid_leads:
        logger.info("[CRM] No valid leads to push to Smartlead after deduplication and filtering.")
        return True

    idempotency_key = None
    supabase_client = None
    deducted_count = 0
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        supabase_client = get_service_client()
        import hashlib
        lead_ids_str = ",".join(str(l.get("id") or l.get("email") or l.get("linkedin_url") or i) for i, l in enumerate(valid_leads))
        batch_hash = hashlib.md5(lead_ids_str.encode("utf-8")).hexdigest()[:16]
        idempotency_key = f"smartlead_{workspace_id}_{campaign_id}_{batch_hash}"
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': len(valid_leads),
            'p_action_type': 'crm_push_bulk',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            logger.error(f"[CRM] Credit deduction failed for Smartlead: {result.data.get('reason')}")
            return False
        deducted_count = len(valid_leads)
        
    url = f"https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads"
    headers = {
        "Content-Type": "application/json"
    }

    CHUNK_SIZE = 100
    pushed_count = 0

    try:
        for i in range(0, len(valid_leads), CHUNK_SIZE):
            chunk = valid_leads[i:i + CHUNK_SIZE]
            lead_list = []
            for lead_data in chunk:
                lead_list.append({
                    "firstName": lead_data.get("first_name", ""),
                    "lastName": lead_data.get("last_name", ""),
                    "email": lead_data.get("email", ""),
                    "companyName": lead_data.get("company", ""),
                    "customFields": {
                        "linkedin_url": lead_data.get("linkedin_url", ""),
                        "ai_icebreaker": lead_data.get("ai_hook", "")
                    }
                })

            payload = {
                "api_key": api_key,
                "leadList": lead_list
            }

            def request_fn():
                return requests.post(url, headers=headers, json=payload, timeout=20)

            res = execute_with_resilience("smartlead", request_fn, max_retries=3, circuit_breaker=cb)
            if res.status_code not in (200, 201):
                unpushed = deducted_count - pushed_count
                if unpushed > 0 and workspace_id and idempotency_key and supabase_client:
                    try:
                        supabase_client.rpc('add_credits_safely', {
                            'p_workspace_id': workspace_id,
                            'p_credits': unpushed,
                            'p_event_id': f"refund_{idempotency_key}",
                            'p_provider': 'system_refund'
                        }).execute()
                        logger.info(f"[CRM] Refunded {unpushed} credits to workspace {workspace_id} due to Smartlead status {res.status_code}")
                    except Exception as ref_e:
                        logger.error(f"[CRM] Failed to refund credits for Smartlead: {ref_e}")
                return False

            pushed_count += len(chunk)

        return True
    except Exception as e:
        logger.error(f"[CRM] Smartlead API error / exception: {e}")
        unpushed = deducted_count - pushed_count
        if unpushed > 0 and workspace_id and idempotency_key and supabase_client:
            try:
                supabase_client.rpc('add_credits_safely', {
                    'p_workspace_id': workspace_id,
                    'p_credits': unpushed,
                    'p_event_id': f"refund_{idempotency_key}",
                    'p_provider': 'system_refund'
                }).execute()
                logger.info(f"[CRM] Refunded {unpushed} credits to workspace {workspace_id} due to Smartlead exception {e}")
            except Exception as ref_e:
                logger.error(f"[CRM] Failed to refund credits for Smartlead exception: {ref_e}")
        return False

def add_to_instantly(workspace_id: str, leads: list, campaign_id: str) -> bool:
    """Pushes a batch of leads to Instantly API with circuit breaking, deduplication, chunking and resilience."""
    import os, requests, logging
    logger = logging.getLogger(__name__)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("instantly")
    if not cb.can_execute():
        logger.error("[CRM] Instantly circuit breaker is OPEN. Skipping push.")
        return False

    api_key = os.environ.get("INSTANTLY_API_KEY")
    if not api_key or not campaign_id:
        return False
    
    if not leads:
        return True

    # Paranoia Layer 0, 1 & 2: Filter invalid emails, intra-batch deduplicate, and formula-sanitize
    valid_leads = _clean_and_dedup_crm_leads(leads)
    if not valid_leads:
        logger.info("[CRM] No valid leads to push to Instantly after deduplication and filtering.")
        return True
        
    idempotency_key = None
    supabase_client = None
    deducted_count = 0
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        supabase_client = get_service_client()
        import hashlib
        lead_ids_str = ",".join(str(l.get("id") or l.get("email") or l.get("linkedin_url") or i) for i, l in enumerate(valid_leads))
        batch_hash = hashlib.md5(lead_ids_str.encode("utf-8")).hexdigest()[:16]
        idempotency_key = f"instantly_{workspace_id}_{campaign_id}_{batch_hash}"
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': len(valid_leads),
            'p_action_type': 'crm_push_bulk',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            logger.error(f"[CRM] Credit deduction failed for Instantly: {result.data.get('reason')}")
            return False
        deducted_count = len(valid_leads)
            
    url = f"https://api.instantly.ai/api/v1/lead/add"

    CHUNK_SIZE = 100
    pushed_count = 0

    try:
        for i in range(0, len(valid_leads), CHUNK_SIZE):
            chunk = valid_leads[i:i + CHUNK_SIZE]
            formatted_leads = []
            for lead_data in chunk:
                formatted_leads.append({
                    "email": lead_data.get("email", ""),
                    "first_name": lead_data.get("first_name", ""),
                    "last_name": lead_data.get("last_name", ""),
                    "company_name": lead_data.get("company", ""),
                    "personalization": lead_data.get("ai_hook", "")
                })

            payload = {
                "api_key": api_key,
                "campaign_id": campaign_id,
                "skip_if_in_workspace": True,
                "leads": formatted_leads
            }

            def request_fn():
                return requests.post(url, json=payload, timeout=20)

            res = execute_with_resilience("instantly", request_fn, max_retries=3, circuit_breaker=cb)
            if res.status_code not in (200, 201):
                unpushed = deducted_count - pushed_count
                if unpushed > 0 and workspace_id and idempotency_key and supabase_client:
                    try:
                        supabase_client.rpc('add_credits_safely', {
                            'p_workspace_id': workspace_id,
                            'p_credits': unpushed,
                            'p_event_id': f"refund_{idempotency_key}",
                            'p_provider': 'system_refund'
                        }).execute()
                        logger.info(f"[CRM] Refunded {unpushed} credits to workspace {workspace_id} due to Instantly status {res.status_code}")
                    except Exception as ref_e:
                        logger.error(f"[CRM] Failed to refund credits for Instantly: {ref_e}")
                return False

            pushed_count += len(chunk)

        return True
    except Exception as e:
        logger.error(f"[CRM] Instantly API error / exception: {e}")
        unpushed = deducted_count - pushed_count
        if unpushed > 0 and workspace_id and idempotency_key and supabase_client:
            try:
                supabase_client.rpc('add_credits_safely', {
                    'p_workspace_id': workspace_id,
                    'p_credits': unpushed,
                    'p_event_id': f"refund_{idempotency_key}",
                    'p_provider': 'system_refund'
                }).execute()
                logger.info(f"[CRM] Refunded {unpushed} credits to workspace {workspace_id} due to Instantly exception {e}")
            except Exception as ref_e:
                logger.error(f"[CRM] Failed to refund credits for Instantly exception: {ref_e}")
        return False


def unsubscribe_from_smartlead(workspace_id: str, email: str, campaign_id: Optional[str] = None) -> bool:
    """
    Unsubscribes a lead from Smartlead globally or within a specific campaign with circuit breaking.
    """
    import os, requests, logging
    logger = logging.getLogger(__name__)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("smartlead")
    if not cb.can_execute():
        logger.warning("[CRM] Smartlead circuit breaker is OPEN. Skipping unsubscribe.")
        return False

    api_key = os.environ.get("SMARTLEAD_API_KEY")
    if not api_key:
        logger.warning("[CRM] No SMARTLEAD_API_KEY set. Skipping Smartlead unsubscribe.")
        return False

    if not email:
        return False

    url = f"https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads/unsubscribe" if campaign_id else "https://server.smartlead.ai/api/v1/leads/unsubscribe"
    payload = {"api_key": api_key, "email": email}
    headers = {"Content-Type": "application/json"}

    try:
        def request_fn():
            return requests.post(url, headers=headers, json=payload, timeout=12)

        res = execute_with_resilience("smartlead", request_fn, max_retries=2, circuit_breaker=cb)
        return getattr(res, "status_code", 0) in (200, 201, 204)
    except CircuitBreakerOpenException:
        logger.warning("[CRM] Smartlead circuit breaker opened during unsubscribe")
        return False
    except Exception as e:
        logger.error(f"[CRM] Smartlead unsubscribe API error: {e}")
        return False


def pause_lead_in_smartlead(workspace_id: str, email: str, campaign_id: str) -> bool:
    """
    Pauses a lead in a specific Smartlead campaign with circuit breaking.
    """
    import os, requests, logging
    logger = logging.getLogger(__name__)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("smartlead")
    if not cb.can_execute():
        logger.warning("[CRM] Smartlead circuit breaker is OPEN. Skipping pause.")
        return False

    api_key = os.environ.get("SMARTLEAD_API_KEY")
    if not api_key:
        logger.warning("[CRM] No SMARTLEAD_API_KEY set. Skipping Smartlead pause.")
        return False

    if not campaign_id or not email:
        return False

    url = f"https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads/pause"
    payload = {"api_key": api_key, "email": email}
    headers = {"Content-Type": "application/json"}

    try:
        def request_fn():
            return requests.post(url, headers=headers, json=payload, timeout=12)

        res = execute_with_resilience("smartlead", request_fn, max_retries=2, circuit_breaker=cb)
        return getattr(res, "status_code", 0) in (200, 201, 204)
    except CircuitBreakerOpenException:
        logger.warning("[CRM] Smartlead circuit breaker opened during pause")
        return False
    except Exception as e:
        logger.error(f"[CRM] Smartlead pause API error: {e}")
        return False


def unsubscribe_from_instantly(workspace_id: str, email: str) -> bool:
    """
    Unsubscribes a lead from Instantly with circuit breaking.
    """
    import os, requests, logging
    logger = logging.getLogger(__name__)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("instantly")
    if not cb.can_execute():
        logger.warning("[CRM] Instantly circuit breaker is OPEN. Skipping unsubscribe.")
        return False

    api_key = os.environ.get("INSTANTLY_API_KEY")
    if not api_key:
        logger.warning("[CRM] No INSTANTLY_API_KEY set. Skipping Instantly unsubscribe.")
        return False

    if not email:
        return False

    url = "https://api.instantly.ai/api/v1/lead/update"
    payload = {"api_key": api_key, "email": email, "status": "unsubscribed"}
    headers = {"Content-Type": "application/json"}

    try:
        def request_fn():
            return requests.post(url, headers=headers, json=payload, timeout=12)

        res = execute_with_resilience("instantly", request_fn, max_retries=2, circuit_breaker=cb)
        return getattr(res, "status_code", 0) in (200, 201, 204)
    except CircuitBreakerOpenException:
        logger.warning("[CRM] Instantly circuit breaker opened during unsubscribe")
        return False
    except Exception as e:
        logger.error(f"[CRM] Instantly unsubscribe API error: {e}")
        return False


def add_to_lemlist(workspace_id: str, lead_data: dict, campaign_id: str) -> bool:
    api_key = os.environ.get("LEMLIST_API_KEY")
    if not api_key or not campaign_id: return False
    
    idempotency_key = None
    supabase_client = None
    deducted = False
    cost = 1
    
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import uuid
        supabase_client = get_service_client()
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"lemlist_{workspace_id}_{lead_ident}"
        
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': cost,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True

    url = f"https://api.lemlist.com/api/campaigns/{campaign_id}/leads"
    try:
        res = requests.post(url, auth=("", api_key), json=lead_data, timeout=10)
        success = res.status_code in (200, 201)
        if not success and deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return success
    except Exception as e:
        logger.error(f"[CRM] Lemlist API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return False

def push_to_salesforce(workspace_id: str, lead_data: dict) -> bool:
    # Requires OAuth/Bearer token which usually rotates. Assuming static for now via integration user.
    access_token = os.environ.get("SALESFORCE_ACCESS_TOKEN")
    instance_url = os.environ.get("SALESFORCE_INSTANCE_URL")
    if not access_token or not instance_url: return False
    
    idempotency_key = None
    supabase_client = None
    deducted = False
    
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import time
        supabase_client = get_service_client()
        import uuid
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"salesforce_{workspace_id}_{lead_ident}"
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': 1,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True
    
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
        success = res.status_code in (200, 201, 204)
        if not success and deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        return success
    except Exception as e:
        logger.error(f"[CRM] Salesforce API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        return False

def push_to_pipedrive(workspace_id: str, lead_data: dict) -> bool:
    api_key = os.environ.get("PIPEDRIVE_API_KEY")
    if not api_key: return False
    
    idempotency_key = None
    supabase_client = None
    deducted = False
    cost = 1
    
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import uuid
        supabase_client = get_service_client()
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"pipedrive_{workspace_id}_{lead_ident}"
        
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': cost,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True

    url = f"https://api.pipedrive.com/v1/persons?api_token={api_key}"
    payload = {
        "name": f"{lead_data.get('first_name','')} {lead_data.get('last_name','')}".strip(),
        "email": [{"value": lead_data.get("email", ""), "primary": True}],
        "org_name": lead_data.get("company", "")
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        success = res.status_code in (200, 201)
        if not success and deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return success
    except Exception as e:
        logger.error(f"[CRM] Pipedrive API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return False

def send_slack_alert(message: str, webhook_url: str = None) -> bool:
    webhook = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook: return False
    from core.backend.core.validators import is_safe_ssrf_url
    if not is_safe_ssrf_url(webhook):
        logger.warning(f"[CRM] Blocked Slack alert to unsafe SSRF URL: {webhook}")
        return False
    try:
        res = requests.post(webhook, json={"text": message}, timeout=10, allow_redirects=False)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"[CRM] Slack alert error: {e}")
        return False

def push_to_notion(workspace_id: str, lead_data: dict, database_id: str) -> bool:
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key or not database_id: return False
    
    idempotency_key = None
    supabase_client = None
    deducted = False
    cost = 1
    
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import uuid
        supabase_client = get_service_client()
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"notion_{workspace_id}_{lead_ident}"
        
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': cost,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True

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
        success = res.status_code == 200
        if not success and deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return success
    except Exception as e:
        logger.error(f"[CRM] Notion API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return False

def push_to_airtable(workspace_id: str, lead_data: dict, base_id: str, table_name: str) -> bool:
    api_key = os.environ.get("AIRTABLE_API_KEY")
    if not api_key or not base_id or not table_name: return False
    
    idempotency_key = None
    supabase_client = None
    deducted = False
    cost = 1
    
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import uuid
        supabase_client = get_service_client()
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"airtable_{workspace_id}_{lead_ident}"
        
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': cost,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True

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
        success = res.status_code == 200
        if not success and deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return success
    except Exception as e:
        logger.error(f"[CRM] Airtable API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return False

def send_webhook(lead_data: dict, webhook_url: str) -> bool:
    """Paranoia Layer 0, 1 & 2: Dispatches webhook with SSRF defense and secret stripping."""
    if not webhook_url: return False
    from core.backend.core.validators import is_safe_ssrf_url
    if not is_safe_ssrf_url(webhook_url):
        logger.warning(f"[CRM] Blocked webhook dispatch to unsafe SSRF URL: {webhook_url}")
        return False
    from integrations.backend.services.webhook_service import sanitize_webhook_payload
    clean_data = sanitize_webhook_payload(lead_data)
    try:
        res = requests.post(webhook_url, json=clean_data, timeout=10, allow_redirects=False)
        return res.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"[CRM] Webhook post error: {e}")
        return False

def add_to_emailbison(workspace_id: str, lead_data: dict, campaign_id: str) -> bool:
    api_key = os.environ.get("EMAILBISON_API_KEY")
    if not api_key: return False
    
    idempotency_key = None
    supabase_client = None
    deducted = False
    cost = 1
    
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import uuid
        supabase_client = get_service_client()
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"emailbison_{workspace_id}_{lead_ident}"
        
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': cost,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True

    url = f"https://api.emailbison.com/v1/campaigns/{campaign_id}/leads"
    try:
        res = requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=lead_data, timeout=10)
        success = res.status_code in (200, 201)
        if not success and deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return success
    except Exception as e:
        logger.error(f"[CRM] EmailBison API error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, cost, idempotency_key, supabase_client)
        return False

class ApolloRateLimitException(Exception):
    pass

def add_to_apollo(workspace_id: str, lead_data: dict, sequence_id: str = None) -> bool:
    import requests
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("apollo")
    if not cb.can_execute():
        logger.warning("[Apollo] Circuit breaker is OPEN. Skipping Apollo sync to protect system.")
        return False

    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key: 
        logger.error("[Apollo] No API Key found.")
        return False
        
    idempotency_key = None
    supabase_client = None
    deducted = False
    if workspace_id:
        from core.backend.api.auth_dep import get_service_client
        import uuid
        supabase_client = get_service_client()
        lead_ident = lead_data.get('id') or lead_data.get('lead_id') or lead_data.get('linkedin_url') or lead_data.get('email') or uuid.uuid4().hex
        idempotency_key = f"apollo_{workspace_id}_{lead_ident}"
        
        result = supabase_client.rpc('deduct_credits_safely', {
            'p_workspace_id': workspace_id,
            'p_amount': 1,
            'p_action_type': 'crm_push',
            'p_idempotency_key': idempotency_key
        }).execute()
        if result.data and not result.data.get('success'):
            return False
        deducted = True

    url = "https://api.apollo.io/v1/contacts"
    payload = {
        "api_key": api_key, 
        "first_name": lead_data.get("first_name"), 
        "last_name": lead_data.get("last_name"), 
        "email": lead_data.get("email"),
        "organization_name": lead_data.get("company"),
        "title": lead_data.get("job_title")
    }
    
    # Paranoia Layer 1 & 2: Thread-safe failure, resilience & Idempotency
    contact_id = None
    try:
        def request_fn():
            return requests.post(url, json=payload, timeout=12)

        res = execute_with_resilience("apollo", request_fn, max_retries=3, circuit_breaker=cb)
        
        if res.status_code in (200, 201):
            contact_id = res.json().get("contact", {}).get("id")
        elif res.status_code == 422:
            # Duplicate email likely. Idempotency recovery: search the contact to get the ID.
            search_url = "https://api.apollo.io/v1/contacts/search"
            search_payload = {"api_key": api_key, "q_keywords": lead_data.get("email")}
            def search_fn():
                return requests.post(search_url, json=search_payload, timeout=10)
            search_res = execute_with_resilience("apollo", search_fn, max_retries=2, circuit_breaker=cb)
            if search_res.status_code == 200:
                contacts = search_res.json().get("contacts", [])
                if contacts:
                    contact_id = contacts[0].get("id")
            if not contact_id:
                logger.error("[Apollo] Failed 422 and could not recover contact ID.")
                if deducted:
                    _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
                return False
        elif res.status_code == 401:
            logger.error("[Apollo] Auth Failed (401). API key invalid.")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            return False
        else:
            logger.error(f"[Apollo] Failed to add contact. Status {res.status_code}: {res.text}")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            return False
            
    except CircuitBreakerOpenException as e:
        logger.warning(f"[Apollo] Circuit breaker opened during execution: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        return False
    except requests.RequestException as e:
        logger.error(f"[Apollo] Network error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        return False
    except Exception as e:
        logger.error(f"[Apollo] Unexpected error: {e}")
        if deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        return False
        
    if not contact_id:
        if deducted:
            _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
        return False
        
    # Sequence Sync (Idempotent)
    if sequence_id:
        seq_url = f"https://api.apollo.io/v1/emailer_campaigns/{sequence_id}/add_contact_ids"
        seq_payload = {"api_key": api_key, "contact_ids": [contact_id]}
        try:
            def seq_fn():
                return requests.post(seq_url, json=seq_payload, timeout=10)
            seq_res = execute_with_resilience("apollo", seq_fn, max_retries=2, circuit_breaker=cb)
            if seq_res.status_code in (200, 201):
                return True
            logger.error(f"[Apollo] Failed sequence {sequence_id}. Status: {seq_res.status_code}")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            return False
        except Exception as e:
            logger.warning(f"[Apollo] Sequence error: {e}")
            if deducted:
                _safe_refund_credits(workspace_id, 1, idempotency_key, supabase_client)
            return False
            
    return True


def enrich_with_apollo(
    workspace_id: Optional[str] = None,
    lead_data: Optional[Union[dict, str]] = None,
    linkedin_url: Optional[str] = None,
    **kwargs: Any
) -> Optional[dict]:
    """
    Calls Apollo's People Match API (/v1/people/match) to find verified contact info
    with circuit breaking and exponential backoff retry (Paranoia Layer 0, 1, 2).
    """
    import os, requests, logging, re
    logger = logging.getLogger(__name__)
    from integrations.backend.services.circuit_breaker import get_circuit_breaker, execute_with_resilience, CircuitBreakerOpenException

    cb = get_circuit_breaker("apollo")
    if not cb.can_execute():
        logger.warning("[Apollo] Circuit breaker is OPEN. Skipping Apollo enrichment.")
        return None

    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return None

    merged = {}
    if isinstance(lead_data, dict):
        merged.update(lead_data)
    elif isinstance(lead_data, str):
        if "@" in lead_data:
            merged["email"] = lead_data
        elif "linkedin.com" in lead_data:
            merged["linkedin_url"] = lead_data
        else:
            merged["first_name"] = lead_data

    merged.update(kwargs)

    target_linkedin = linkedin_url or merged.get("linkedin_url")
    first_name = merged.get("first_name")
    last_name = merged.get("last_name")
    domain = merged.get("domain") or merged.get("company_domain")
    org_name = merged.get("organization_name") or merged.get("company") or merged.get("company_name")

    match_url = "https://api.apollo.io/v1/people/match"
    payload = {
        "api_key": api_key,
        "first_name": first_name,
        "last_name": last_name,
        "domain": domain,
        "organization_name": org_name,
        "linkedin_url": target_linkedin
    }

    # Only invoke if we have at least one useful search vector
    if not (payload["linkedin_url"] or (payload["first_name"] and (payload["domain"] or payload["organization_name"]))):
        return None

    try:
        def request_fn():
            return requests.post(match_url, json=payload, timeout=12)

        res = execute_with_resilience("apollo", request_fn, max_retries=2, circuit_breaker=cb)
        if res.status_code != 200:
            logger.warning(f"[Apollo] Match returned status {res.status_code}")
            return None

        data = res.json()
        person = data.get("person") or {}
        if not person:
            return None

        email = person.get("email")
        if email and isinstance(email, str):
            clean_em = email.strip().lower()
            if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean_em) or "none@" in clean_em:
                email = None
            else:
                email = clean_em

        phone = None
        phones = person.get("phone_numbers") or []
        if phones and isinstance(phones, list):
            phone = phones[0].get("raw_number") or phones[0].get("sanitized_number")

        org = person.get("organization") or {}

        return {
            "email": email,
            "phone": phone,
            "first_name": person.get("first_name") or first_name,
            "last_name": person.get("last_name") or last_name,
            "job_title": person.get("title") or merged.get("job_title"),
            "company": org.get("name") or org_name,
            "domain": org.get("primary_domain") or domain,
            "seniority": person.get("seniority"),
            "city": person.get("city"),
            "state": person.get("state"),
            "country": person.get("country")
        }
    except CircuitBreakerOpenException:
        logger.warning("[Apollo] Circuit breaker opened during enrichment")
        return None
    except Exception as e:
        logger.warning(f"[Apollo] Enrichment error: {e}")
        return None


# ==============================================================================
# HORIZON 33: BI-DIRECTIONAL CRM DEAL-STAGE SYNC, REVENUE ATTRIBUTION &
#             AUTOMATIC SEQUENCE HALTING ON CLOSED-WON / CLOSED-LOST
# ==============================================================================

import re

_PROCESSED_DEAL_EVENTS: set = set()
_DEAL_STATE_LEDGER: Dict[ tuple, Dict[str, Any] ] = {}
_DEAL_WORKSPACE_OWNER: Dict[str, str] = {}

_CANONICAL_STAGE_MAP: Dict[str, str] = {
    # Discovery / Qualification
    "appointmentscheduled": "discovery",
    "qualifiedtobuy": "discovery",
    "discovery": "discovery",
    "qualification": "discovery",
    "prospecting": "discovery",
    "meeting_booked": "discovery",
    "sql": "discovery",
    "mql": "discovery",
    "lead": "discovery",
    "subscriber": "discovery",
    # Demo / Evaluation
    "presentationscheduled": "demo_completed",
    "demo": "demo_completed",
    "demo_completed": "demo_completed",
    "value_proposition": "demo_completed",
    "value proposition": "demo_completed",
    "needs analysis": "demo_completed",
    "evaluation": "demo_completed",
    "marketingqualifiedlead": "demo_completed",
    "mql": "demo_completed",
    # Proposal / Negotiation
    "decisionmakerboughtin": "proposal_sent",
    "contractsent": "proposal_sent",
    "proposal": "proposal_sent",
    "proposal_sent": "proposal_sent",
    "negotiation": "proposal_sent",
    "procurement": "proposal_sent",
    "salesqualifiedlead": "proposal_sent",
    "sql": "proposal_sent",
    "opportunity": "proposal_sent",
    "proposal/price quote": "proposal_sent",
    "proposalpricequote": "proposal_sent",
    "negotiation/review": "proposal_sent",
    "negotiationreview": "proposal_sent",
    # Closed Won
    "closedwon": "closed_won",
    "closed_won": "closed_won",
    "closed won": "closed_won",
    "won": "closed_won",
    "customer": "closed_won",
    "signed": "closed_won",
    # Closed Lost
    "closedlost": "closed_lost",
    "closed_lost": "closed_lost",
    "closed lost": "closed_lost",
    "lost": "closed_lost",
    "churned": "closed_lost",
    "disqualified": "closed_lost",
    "evangelist": "closed_lost",
}


def validate_crm_field_mappings(mappings: Any, allowed_source_fields: Optional[Set[str]] = None) -> Tuple[bool, List[str], Dict[str, str]]:
    """
    Layer 0: CRM Field Mapping Validator
    - Validates that mappings is a dict of strings.
    - Cleans/normalizes field names (lowercased, stripped).
    - If allowed_source_fields provided, checks that source fields belong to allowed set.
    - Rejects empty keys/values or circular mappings.
    - Returns (is_valid, errors, normalized_mappings).
    """
    errors: List[str] = []
    if not isinstance(mappings, dict):
        return False, ["Mappings must be a dictionary"], {}

    normalized: Dict[str, str] = {}
    seen_destinations: Set[str] = set()

    for k, v in mappings.items():
        if not isinstance(k, str) or not k.strip():
            errors.append(f"Invalid or empty mapping key: {k}")
            continue
        if not isinstance(v, str) or not v.strip():
            errors.append(f"Invalid or empty mapping value for key '{k}': {v}")
            continue

        src = k.strip().lower()
        dst = v.strip().lower()

        if src == dst or (dst in normalized and normalized[dst] == src):
            errors.append(f"Circular mapping detected between '{src}' and '{dst}'")
            continue

        if allowed_source_fields is not None:
            allowed_lower = {str(f).strip().lower() for f in allowed_source_fields}
            if src not in allowed_lower:
                errors.append(f"Source field '{src}' is not in allowed source fields")
                continue

        if dst in seen_destinations:
            errors.append(f"Duplicate mapping destination target: '{dst}'")
            continue

        normalized[src] = dst
        seen_destinations.add(dst)

    is_valid = len(errors) == 0
    return is_valid, errors, normalized


def map_canonical_to_provider_stage(canonical_stage: str, provider: str = "hubspot") -> str:
    """
    Maps canonical Ele-in stages back to external provider (HubSpot or Salesforce) stage names.
    """
    c = str(canonical_stage or "").strip().lower()
    prov = str(provider or "hubspot").strip().lower()

    if prov == "salesforce":
        if c == "discovery":
            return "Qualification"
        elif c == "demo_completed":
            return "Value Proposition"
        elif c == "proposal_sent":
            return "Proposal/Price Quote"
        elif c == "closed_won":
            return "Closed Won"
        elif c == "closed_lost":
            return "Closed Lost"
        return "Prospecting"
    else:
        # HubSpot default
        if c == "discovery":
            return "appointmentscheduled"
        elif c == "demo_completed":
            return "presentationscheduled"
        elif c == "proposal_sent":
            return "decisionmakerboughtin"
        elif c == "closed_won":
            return "closedwon"
        elif c == "closed_lost":
            return "closedlost"
        return "appointmentscheduled"


def _sanitize_crm_text(val: Any, max_len: int = 240) -> str:
    """
    Layer 2 Paranoia: Strips spreadsheet formula injection prefixes (=, +, -, @, \\t, \\r)
    and clamps length on CRM deal names and close reasons.
    """
    if val is None:
        return ""
    s = str(val).strip()
    while s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        s = s[1:].strip()
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s[:max_len]


def _sanitize_deal_amount(val: Any) -> float:
    """
    Layer 1: Amount & Currency Sanitization
    - Clamps negative numbers to 0.0.
    - Clamps extreme floats to 1,000,000,000.0.
    - Handles strings like '$1,500.50', '1500 USD', None, and NaN.
    """
    import math
    if val is None or isinstance(val, bool):
        return 0.0
    if isinstance(val, str):
        # Remove currency symbols/text, keeping digits, dot, minus
        s = val.strip()
        # Handle strings like "1500 USD" or "$1,500.50"
        cleaned = re.sub(r"[^0-9.\-]", "", s)
        if not cleaned or cleaned in ("-", ".", "-."):
            return 0.0
        try:
            num = float(cleaned)
        except Exception:
            return 0.0
    elif isinstance(val, (int, float)):
        num = float(val)
    else:
        return 0.0

    if math.isnan(num) or math.isinf(num) or num < 0.0:
        return 0.0
    return round(min(num, 1_000_000_000.0), 2)


def _sanitize_currency(curr: Any) -> str:
    """
    Layer 1: Normalizes to 3-letter uppercase ISO-4217 (e.g. 'USD', 'EUR', 'GBP').
    Defaults to 'USD' if invalid.
    """
    if not curr or not isinstance(curr, str):
        return "USD"
    clean = re.sub(r"[^A-Za-z]", "", curr.strip()).upper()
    valid_iso = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "CNY", "INR", "NZD", "SGD", "HKD", "SEK", "NOK", "DKK", "ZAR", "BRL", "MXN"}
    if len(clean) == 3 and clean in valid_iso:
        return clean
    return "USD"


def _parse_deal_timestamp(val: Any) -> float:
    from datetime import datetime, timezone
    if val is None:
        return datetime.now(timezone.utc).timestamp()
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        ts = float(val)
        # Convert millisecond timestamps to seconds
        if ts > 1e12:
            ts = ts / 1000.0
        return ts
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return datetime.now(timezone.utc).timestamp()
        if s.isdigit():
            ts = float(s)
            return ts / 1000.0 if ts > 1e12 else ts
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return datetime.now(timezone.utc).timestamp()
    return datetime.now(timezone.utc).timestamp()


def normalize_crm_deal_stage(raw_stage: Any, provider: str = "hubspot") -> str:
    """
    Layer 0: Normalizes HubSpot, Salesforce, Pipedrive, or custom CRM stage names
    into canonical pipeline stages:
      - discovery
      - demo_completed
      - proposal_sent
      - closed_won
      - closed_lost
    """
    if not raw_stage:
        return "discovery"
    clean = str(raw_stage).strip().lower()
    compact = re.sub(r"[\s\-_]+", "_", clean)
    no_sep = re.sub(r"[\s\-_]+", "", clean)

    if clean in _CANONICAL_STAGE_MAP:
        return _CANONICAL_STAGE_MAP[clean]
    if compact in _CANONICAL_STAGE_MAP:
        return _CANONICAL_STAGE_MAP[compact]
    if no_sep in _CANONICAL_STAGE_MAP:
        return _CANONICAL_STAGE_MAP[no_sep]

    if "won" in clean:
        return "closed_won"
    if "lost" in clean or "disqualif" in clean or "churn" in clean:
        return "closed_lost"
    if "proposal" in clean or "contract" in clean or "negotiat" in clean:
        return "proposal_sent"
    if "demo" in clean or "presentation" in clean or "evaluat" in clean:
        return "demo_completed"
    return "discovery"


def sync_crm_deal_stage_event(
    workspace_id: str,
    deal_id: str,
    raw_stage: str,
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    node_id: Optional[str] = None,
    bandit_variant_id: Optional[str] = None,
    deal_amount: Any = 0.0,
    currency: str = "USD",
    deal_name: str = "",
    close_reason: str = "",
    provider: str = "hubspot",
    event_id: Optional[str] = None,
    updated_at: Optional[Any] = None,
    supabase: Any = None,
    halt_sequences_on_terminal: bool = True,
) -> Dict[str, Any]:
    """
    Horizon 33 (Paranoia Layer 0, 1 & 2):
    Synchronizes inbound/outbound CRM deal-stage transitions, attributes pipeline/closed-won
    revenue back to campaigns & Thompson Sampling bandit variants, enforces idempotent
    webhook replay & out-of-order timestamp guards, and automatically halts active sequences
    when a deal moves to Closed Won or Closed Lost.
    """
    from datetime import datetime, timezone

    ws_id = str(workspace_id or "").strip()
    d_id = str(deal_id or "").strip()
    if not ws_id:
        raise ValueError("workspace_id is required for CRM deal sync")
    if not d_id:
        raise ValueError("deal_id is required for CRM deal sync")

    clean_lead_id = str(lead_id).strip() if lead_id and str(lead_id).strip() else None
    clean_camp_id = str(campaign_id).strip() if campaign_id and str(campaign_id).strip() else None
    clean_node_id = str(node_id).strip() if node_id and str(node_id).strip() else None
    clean_variant_id = str(bandit_variant_id).strip() if bandit_variant_id and str(bandit_variant_id).strip() else None
    clean_provider = str(provider or "hubspot").strip().lower()

    # Layer 2 Paranoia: Cross-Tenant IDOR Guard on deal_id, lead_id, and campaign_id
    existing_owner = _DEAL_WORKSPACE_OWNER.get(d_id)
    if existing_owner and existing_owner != ws_id:
        raise PermissionError("Cross-workspace access denied for CRM deal sync")

    lead_email = None
    if supabase:
        if clean_lead_id:
            try:
                l_res = supabase.table("leads").select("id, workspace_id, email").eq("id", clean_lead_id).limit(1).execute()
                rows = getattr(l_res, "data", None)
                if isinstance(rows, list) and len(rows) > 0:
                    row_ws = rows[0].get("workspace_id")
                    if row_ws and str(row_ws) != ws_id:
                        raise PermissionError("Cross-workspace access denied for CRM deal sync")
                    lead_email = rows[0].get("email")
            except PermissionError:
                raise
            except Exception as exc:
                logger.debug(f"[CRMDealSync] Lead lookup fallback: {exc}")

        if clean_camp_id:
            try:
                c_res = supabase.table("campaigns").select("id, workspace_id").eq("id", clean_camp_id).limit(1).execute()
                c_rows = getattr(c_res, "data", None)
                if isinstance(c_rows, list) and len(c_rows) > 0:
                    c_ws = c_rows[0].get("workspace_id")
                    if c_ws and str(c_ws) != ws_id:
                        raise PermissionError("Cross-workspace access denied for CRM deal sync")
            except PermissionError:
                raise
            except Exception as exc:
                logger.debug(f"[CRMDealSync] Campaign lookup fallback: {exc}")

    normalized_stage = normalize_crm_deal_stage(raw_stage, provider=clean_provider)
    sanitized_amount = _sanitize_deal_amount(deal_amount)
    sanitized_currency = _sanitize_currency(currency)
    sanitized_name = _sanitize_crm_text(deal_name, max_len=200) or f"Deal {d_id}"
    sanitized_reason = _sanitize_crm_text(close_reason, max_len=240)
    event_ts = _parse_deal_timestamp(updated_at)

    # Layer 1 Environmental: Idempotent Deal Webhook Replay Guard
    effective_event_id = str(event_id).strip() if event_id and str(event_id).strip() else f"{d_id}:{normalized_stage}:{sanitized_amount}"
    replay_key = (ws_id, d_id, normalized_stage, effective_event_id)
    if replay_key in _PROCESSED_DEAL_EVENTS:
        existing_record = _DEAL_STATE_LEDGER.get((ws_id, d_id), {})
        return {
            "status": "duplicate_ignored",
            "idempotent_replay": True,
            "stale_event": False,
            "workspace_id": ws_id,
            "deal_id": d_id,
            "normalized_stage": normalized_stage,
            "deal_amount": existing_record.get("deal_amount", sanitized_amount),
            "currency": existing_record.get("currency", sanitized_currency),
            "sequences_halted": 0,
            "bandit_feedback_recorded": False,
        }

    # Layer 1 Environmental: Out-of-Order / Stale Webhook Timestamp Guard
    ledger_key = (ws_id, d_id)
    prior_state = _DEAL_STATE_LEDGER.get(ledger_key)
    if prior_state:
        prior_ts = float(prior_state.get("updated_at_ts", 0.0))
        if event_ts < prior_ts:
            return {
                "status": "ignored_stale_event",
                "idempotent_replay": False,
                "stale_event": True,
                "workspace_id": ws_id,
                "deal_id": d_id,
                "normalized_stage": prior_state.get("normalized_stage", normalized_stage),
                "ignored_stage": normalized_stage,
                "deal_amount": prior_state.get("deal_amount", sanitized_amount),
                "currency": prior_state.get("currency", sanitized_currency),
                "sequences_halted": 0,
                "bandit_feedback_recorded": False,
            }

    # Resolve missing campaign_id / bandit_variant_id from prior state or lead's active enrollment
    if prior_state:
        if not clean_lead_id:
            clean_lead_id = prior_state.get("lead_id")
        if not clean_camp_id:
            clean_camp_id = prior_state.get("campaign_id")
        if not clean_node_id:
            clean_node_id = prior_state.get("node_id")
        if not clean_variant_id:
            clean_variant_id = prior_state.get("bandit_variant_id")
        if sanitized_amount == 0.0 and prior_state.get("deal_amount", 0.0) > 0.0:
            sanitized_amount = prior_state["deal_amount"]

    if not clean_variant_id and clean_lead_id:
        try:
            from campaigns.backend.services.bandit_service import _LEAD_ARM_LOCKS
            for lock_k, lock_val in list(_LEAD_ARM_LOCKS.items()):
                if lock_k.startswith(f"{ws_id}:") and lock_k.endswith(f":{clean_lead_id}"):
                    clean_variant_id = lock_val.get("selected_variant_id")
                    if not clean_camp_id:
                        parts = lock_k.split(":")
                        if len(parts) >= 2 and parts[1] != "global":
                            clean_camp_id = parts[1]
                    break
        except Exception:
            pass

    # Record ownership & processed event
    _DEAL_WORKSPACE_OWNER[d_id] = ws_id
    _PROCESSED_DEAL_EVENTS.add(replay_key)

    is_terminal = normalized_stage in ("closed_won", "closed_lost")
    sequences_halted = 0
    halted_enrollment_ids = []

    # Layer 0: Automatic Sequence Halting on Closed-Won / Closed-Lost
    if is_terminal and halt_sequences_on_terminal and clean_lead_id:
        target_enroll_status = "converted" if normalized_stage == "closed_won" else "completed"
        exit_reason = f"crm_{normalized_stage}"

        if supabase:
            try:
                enr_res = (
                    supabase.table("campaign_enrollments")
                    .select("id, campaign_id, status, workspace_id")
                    .eq("workspace_id", ws_id)
                    .eq("lead_id", clean_lead_id)
                    .execute()
                )
                enr_rows = getattr(enr_res, "data", None) or []
                for row in enr_rows:
                    if not isinstance(row, dict):
                        continue
                    row_ws = row.get("workspace_id")
                    if row_ws and str(row_ws) != ws_id:
                        continue
                    cur_st = str(row.get("status") or "active").lower()
                    if cur_st not in ("completed", "converted", "unsubscribed", "halted"):
                        enr_id = row.get("id")
                        halted_enrollment_ids.append(enr_id)
                        if not clean_camp_id and row.get("campaign_id"):
                            clean_camp_id = str(row.get("campaign_id"))
                        try:
                            supabase.table("campaign_enrollments").update({
                                "status": target_enroll_status,
                                "exit_reason": exit_reason,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }).eq("id", enr_id).eq("workspace_id", ws_id).execute()
                        except Exception:
                            pass
                        try:
                            supabase.table("campaign_execution_states").update({
                                "status": "completed",
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }).eq("enrollment_id", enr_id).eq("workspace_id", ws_id).execute()
                        except Exception:
                            pass
                sequences_halted = len(halted_enrollment_ids)
            except Exception as exc:
                logger.warning(f"[CRMDealSync] Enrollment halt fallback: {exc}")

            try:
                supabase.table("leads").update({
                    "status": "converted" if normalized_stage == "closed_won" else "closed_lost",
                    "lifecycle_stage": "Customer" if normalized_stage == "closed_won" else "Closed Lost",
                    "deal_stage": normalized_stage,
                    "deal_value": sanitized_amount,
                }).eq("id", clean_lead_id).eq("workspace_id", ws_id).execute()
            except Exception:
                pass

        # Best-effort external email sequencer pause if lead_email is present
        if lead_email:
            try:
                unsubscribe_from_smartlead(ws_id, lead_email)
                unsubscribe_from_instantly(ws_id, lead_email)
            except Exception:
                pass

    # Layer 0: Bandit feedback attribution when deal reaches terminal outcome
    bandit_feedback_recorded = False
    if is_terminal and clean_variant_id:
        try:
            from campaigns.backend.services.bandit_service import record_variant_feedback
            record_variant_feedback(
                variant_id=clean_variant_id,
                outcome=normalized_stage,
                workspace_id=ws_id,
                supabase=supabase,
            )
            bandit_feedback_recorded = True
        except Exception as exc:
            logger.warning(f"[CRMDealSync] Bandit feedback attribution warning: {exc}")

    deal_record = {
        "deal_id": d_id,
        "workspace_id": ws_id,
        "lead_id": clean_lead_id,
        "campaign_id": clean_camp_id,
        "node_id": clean_node_id,
        "bandit_variant_id": clean_variant_id,
        "provider": clean_provider,
        "raw_stage": str(raw_stage or ""),
        "normalized_stage": normalized_stage,
        "deal_amount": sanitized_amount,
        "currency": sanitized_currency,
        "deal_name": sanitized_name,
        "close_reason": sanitized_reason,
        "is_terminal": is_terminal,
        "sequences_halted": sequences_halted,
        "halted_enrollment_ids": halted_enrollment_ids,
        "bandit_feedback_recorded": bandit_feedback_recorded,
        "updated_at_ts": event_ts,
        "updated_at": datetime.fromtimestamp(event_ts, tz=timezone.utc).isoformat(),
    }
    _DEAL_STATE_LEDGER[ledger_key] = deal_record

    if supabase:
        try:
            supabase.table("crm_deals").upsert({
                "id": d_id,
                "workspace_id": ws_id,
                "lead_id": clean_lead_id,
                "campaign_id": clean_camp_id,
                "node_id": clean_node_id,
                "bandit_variant_id": clean_variant_id,
                "provider": clean_provider,
                "stage": normalized_stage,
                "amount": sanitized_amount,
                "currency": sanitized_currency,
                "deal_name": sanitized_name,
                "close_reason": sanitized_reason,
                "updated_at": deal_record["updated_at"],
            }).execute()
        except Exception as exc:
            logger.debug(f"[CRMDealSync] crm_deals table upsert fallback: {exc}")

    return {
        "status": "synced",
        "idempotent_replay": False,
        "stale_event": False,
        **deal_record,
    }


def get_campaign_revenue_attribution(
    workspace_id: str,
    campaign_id: Optional[str] = None,
    supabase: Any = None,
) -> Dict[str, Any]:
    """
    Horizon 33 (Paranoia Layer 0, 1 & 2):
    Computes multi-touch campaign & Thompson Sampling bandit revenue attribution
    for a workspace (or a specific campaign_id), enforcing strict tenant isolation.
    """
    ws_id = str(workspace_id or "").strip()
    if not ws_id:
        raise ValueError("workspace_id is required")

    clean_camp_id = str(campaign_id).strip() if campaign_id and str(campaign_id).strip() else None

    # Layer 2 Paranoia: Cross-tenant IDOR check if campaign_id is specified
    if clean_camp_id and supabase:
        try:
            c_res = supabase.table("campaigns").select("id, workspace_id").eq("id", clean_camp_id).limit(1).execute()
            c_rows = getattr(c_res, "data", None)
            if isinstance(c_rows, list) and len(c_rows) > 0:
                c_ws = c_rows[0].get("workspace_id")
                if c_ws and str(c_ws) != ws_id:
                    raise PermissionError("Cross-workspace access denied for revenue attribution")
        except PermissionError:
            raise
        except Exception:
            pass

    # Also check if in-memory ledger has this campaign owned by a different workspace
    if clean_camp_id:
        foreign_campaign_found = False
        own_campaign_found = False
        for (rec_ws, _), rec in _DEAL_STATE_LEDGER.items():
            if rec.get("campaign_id") == clean_camp_id:
                if rec_ws == ws_id:
                    own_campaign_found = True
                else:
                    foreign_campaign_found = True
        if foreign_campaign_found and not own_campaign_found:
            raise PermissionError("Cross-workspace access denied for revenue attribution")

    deals_by_id: Dict[str, Dict[str, Any]] = {}
    for (rec_ws, d_id), rec in _DEAL_STATE_LEDGER.items():
        if rec_ws != ws_id:
            continue
        if clean_camp_id and rec.get("campaign_id") != clean_camp_id:
            continue
        deals_by_id[d_id] = dict(rec)

    if supabase:
        try:
            query = supabase.table("crm_deals").select("*").eq("workspace_id", ws_id)
            if clean_camp_id:
                query = query.eq("campaign_id", clean_camp_id)
            db_res = query.execute()
            for row in (getattr(db_res, "data", None) or []):
                if not isinstance(row, dict):
                    continue
                if row.get("workspace_id") and str(row.get("workspace_id")) != ws_id:
                    continue
                d_id = str(row.get("id") or row.get("deal_id") or "")
                if d_id and d_id not in deals_by_id:
                    deals_by_id[d_id] = {
                        "deal_id": d_id,
                        "workspace_id": ws_id,
                        "lead_id": row.get("lead_id"),
                        "campaign_id": row.get("campaign_id"),
                        "node_id": row.get("node_id"),
                        "bandit_variant_id": row.get("bandit_variant_id"),
                        "normalized_stage": normalize_crm_deal_stage(row.get("stage")),
                        "deal_amount": _sanitize_deal_amount(row.get("amount")),
                        "currency": _sanitize_currency(row.get("currency")),
                    }
        except Exception:
            pass

    open_pipeline_value = 0.0
    closed_won_revenue = 0.0
    closed_lost_value = 0.0
    closed_won_count = 0
    closed_lost_count = 0
    by_campaign: Dict[str, Dict[str, Any]] = {}
    by_bandit_variant: Dict[str, Dict[str, Any]] = {}
    by_stage: Dict[str, int] = {
        "discovery": 0,
        "demo_completed": 0,
        "proposal_sent": 0,
        "closed_won": 0,
        "closed_lost": 0,
    }

    for d in deals_by_id.values():
        stg = d.get("normalized_stage") or "discovery"
        amt = _sanitize_deal_amount(d.get("deal_amount", 0.0))
        by_stage[stg] = by_stage.get(stg, 0) + 1

        if stg == "closed_won":
            closed_won_revenue = round(closed_won_revenue + amt, 2)
            closed_won_count += 1
        elif stg == "closed_lost":
            closed_lost_value = round(closed_lost_value + amt, 2)
            closed_lost_count += 1
        else:
            open_pipeline_value = round(open_pipeline_value + amt, 2)

        c_key = d.get("campaign_id") or "unattributed"
        if c_key not in by_campaign:
            by_campaign[c_key] = {
                "campaign_id": c_key,
                "deals_count": 0,
                "open_pipeline_value": 0.0,
                "closed_won_revenue": 0.0,
                "closed_won_count": 0,
            }
        by_campaign[c_key]["deals_count"] += 1
        if stg == "closed_won":
            by_campaign[c_key]["closed_won_revenue"] = round(by_campaign[c_key]["closed_won_revenue"] + amt, 2)
            by_campaign[c_key]["closed_won_count"] += 1
        elif stg != "closed_lost":
            by_campaign[c_key]["open_pipeline_value"] = round(by_campaign[c_key]["open_pipeline_value"] + amt, 2)

        v_key = d.get("bandit_variant_id")
        if v_key:
            if v_key not in by_bandit_variant:
                by_bandit_variant[v_key] = {
                    "bandit_variant_id": v_key,
                    "deals_count": 0,
                    "open_pipeline_value": 0.0,
                    "closed_won_revenue": 0.0,
                    "closed_won_count": 0,
                }
            by_bandit_variant[v_key]["deals_count"] += 1
            if stg == "closed_won":
                by_bandit_variant[v_key]["closed_won_revenue"] = round(by_bandit_variant[v_key]["closed_won_revenue"] + amt, 2)
                by_bandit_variant[v_key]["closed_won_count"] += 1
            elif stg != "closed_lost":
                by_bandit_variant[v_key]["open_pipeline_value"] = round(by_bandit_variant[v_key]["open_pipeline_value"] + amt, 2)

    closed_total = closed_won_count + closed_lost_count
    win_rate_pct = round((closed_won_count / closed_total) * 100.0, 2) if closed_total > 0 else 0.0

    return {
        "workspace_id": ws_id,
        "campaign_id": clean_camp_id,
        "total_deals": len(deals_by_id),
        "open_pipeline_value": open_pipeline_value,
        "closed_won_revenue": closed_won_revenue,
        "closed_lost_value": closed_lost_value,
        "closed_won_count": closed_won_count,
        "closed_lost_count": closed_lost_count,
        "win_rate_pct": win_rate_pct,
        "by_stage": by_stage,
        "by_campaign": list(by_campaign.values()),
        "by_bandit_variant": list(by_bandit_variant.values()),
    }

