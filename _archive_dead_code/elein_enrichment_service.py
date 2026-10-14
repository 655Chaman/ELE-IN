import os
import requests
import logging

class RateLimitExceeded(Exception):
    pass
import time
import json
from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

def apollo_find_email(workspace_id: str, first_name: str, last_name: str, company: str) -> str:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return None
    
    supabase = get_service_client()
    idem_key = f"apollo_{workspace_id}_{first_name}_{last_name}_{company}_{time.time_ns()}"
    result = supabase.rpc('deduct_credits_safely', {
        'p_workspace_id': workspace_id,
        'p_amount': 5,
        'p_action_type': 'apollo_enrich',
        'p_idempotency_key': idem_key,
        'p_metadata': json.dumps({"first_name": first_name, "last_name": last_name, "company": company})
    }).execute()
    if result.data and not result.data.get('success'):
        logger.warning(f"Insufficient credits for Apollo enrich for workspace {workspace_id}")
        return None

    url = "https://api.apollo.io/v1/people/match"
    headers = {"Cache-Control": "no-cache", "Content-Type": "application/json"}
    payload = {"api_key": api_key, "first_name": first_name, "last_name": last_name, "organization_name": company}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 429:
            raise RateLimitExceeded(f"Apollo Rate Limit 429: {response.headers.get('Retry-After')}")
        response.raise_for_status()
        if response.status_code == 200:
            return response.json().get("person", {}).get("email")
    except requests.exceptions.Timeout:
        logger.error(f"[Enrichment] Apollo upstream_timeout")
        raise
    except Exception as e:
        logger.error(f"[Enrichment] Apollo error: {e}")
    return None

def clearbit_find_tech_stack(workspace_id: str, domain: str) -> list:
    api_key = os.environ.get("CLEARBIT_API_KEY")
    if not api_key or not domain: return []
    
    supabase = get_service_client()
    idem_key = f"clearbit_{workspace_id}_{domain}_{time.time_ns()}"
    result = supabase.rpc('deduct_credits_safely', {
        'p_workspace_id': workspace_id,
        'p_amount': 4,
        'p_action_type': 'clearbit_tech_stack',
        'p_idempotency_key': idem_key,
        'p_metadata': json.dumps({"domain": domain})
    }).execute()
    if result.data and not result.data.get('success'):
        logger.warning(f"Insufficient credits for Clearbit for workspace {workspace_id}")
        return []

    url = f"https://company.clearbit.com/v2/companies/find?domain={domain}"
    try:
        res = requests.get(url, auth=(api_key, ""), timeout=15)
        if res.status_code == 429:
            raise RateLimitExceeded(f"Clearbit Rate Limit 429: {res.headers.get('Retry-After')}")
        res.raise_for_status()
        if res.status_code == 200:
            tags = res.json().get("tech", [])
            return tags
    except requests.exceptions.Timeout:
        logger.error(f"[Enrichment] Clearbit upstream_timeout")
        raise
    except Exception as e:
        logger.error(f"[Enrichment] Clearbit error: {e}")
    return []

def crunchbase_find_funding(workspace_id: str, domain: str) -> dict:
    api_key = os.environ.get("CRUNCHBASE_API_KEY")
    if not api_key or not domain: return {}
    
    supabase = get_service_client()
    idem_key = f"crunchbase_{workspace_id}_{domain}_{time.time_ns()}"
    result = supabase.rpc('deduct_credits_safely', {
        'p_workspace_id': workspace_id,
        'p_amount': 3,
        'p_action_type': 'crunchbase_funding',
        'p_idempotency_key': idem_key,
        'p_metadata': json.dumps({"domain": domain})
    }).execute()
    if result.data and not result.data.get('success'):
        logger.warning(f"Insufficient credits for Crunchbase for workspace {workspace_id}")
        return {}

    url = f"https://api.crunchbase.com/api/v4/entities/organizations/{domain}?user_key={api_key}"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 429:
            raise RateLimitExceeded(f"Crunchbase Rate Limit 429")
        res.raise_for_status()
        if res.status_code == 200:
            props = res.json().get("properties", {})
            return {
                "last_funding_type": props.get("funding_total", {}).get("currency"),
                "total_funding": props.get("funding_total", {}).get("value")
            }
    except requests.exceptions.Timeout:
        logger.error(f"[Enrichment] Crunchbase upstream_timeout")
        raise
    except Exception as e:
        logger.error(f"[Enrichment] Crunchbase error: {e}")
    return {}

def zerobounce_verify_email(workspace_id: str, email: str) -> str:
    api_key = os.environ.get("ZEROBOUNCE_API_KEY")
    if not api_key or not email: return "unknown"
    
    supabase = get_service_client()
    idem_key = f"zerobounce_{workspace_id}_{email}_{time.time_ns()}"
    result = supabase.rpc('deduct_credits_safely', {
        'p_workspace_id': workspace_id,
        'p_amount': 1,
        'p_action_type': 'zerobounce_verify',
        'p_idempotency_key': idem_key,
        'p_metadata': json.dumps({"email": email})
    }).execute()
    if result.data and not result.data.get('success'):
        logger.warning(f"Insufficient credits for ZeroBounce for workspace {workspace_id}")
        return "skipped"

    url = f"https://api.zerobounce.net/v2/validate?api_key={api_key}&email={email}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            status = res.json().get("status", "")
            return status # valid, invalid, catch-all
    except Exception as e:
        logger.error(f"[Enrichment] ZeroBounce error: {e}")
    return "unknown"