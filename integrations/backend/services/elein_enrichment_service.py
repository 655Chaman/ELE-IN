import os
import requests
import logging

logger = logging.getLogger(__name__)

def apollo_find_email(first_name: str, last_name: str, company: str) -> str:
    api_key = os.environ.get("APOLLO_API_KEY")
    if not api_key:
        return None
    url = "https://api.apollo.io/v1/people/match"
    headers = {"Cache-Control": "no-cache", "Content-Type": "application/json"}
    payload = {"api_key": api_key, "first_name": first_name, "last_name": last_name, "organization_name": company}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("person", {}).get("email")
    except Exception as e:
        logger.error(f"[Enrichment] Apollo error: {e}")
    return None

def clearbit_find_tech_stack(domain: str) -> list:
    api_key = os.environ.get("CLEARBIT_API_KEY")
    if not api_key or not domain: return []
    url = f"https://company.clearbit.com/v2/companies/find?domain={domain}"
    try:
        res = requests.get(url, auth=(api_key, ""), timeout=10)
        if res.status_code == 200:
            tags = res.json().get("tech", [])
            return tags
    except Exception as e:
        logger.error(f"[Enrichment] Clearbit error: {e}")
    return []

def crunchbase_find_funding(domain: str) -> dict:
    api_key = os.environ.get("CRUNCHBASE_API_KEY")
    if not api_key or not domain: return {}
    url = f"https://api.crunchbase.com/api/v4/entities/organizations/{domain}?user_key={api_key}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            props = res.json().get("properties", {})
            return {
                "last_funding_type": props.get("funding_total", {}).get("currency"),
                "total_funding": props.get("funding_total", {}).get("value")
            }
    except Exception as e:
        logger.error(f"[Enrichment] Crunchbase error: {e}")
    return {}

def zerobounce_verify_email(email: str) -> str:
    api_key = os.environ.get("ZEROBOUNCE_API_KEY")
    if not api_key or not email: return "unknown"
    url = f"https://api.zerobounce.net/v2/validate?api_key={api_key}&email={email}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            status = res.json().get("status", "")
            return status # valid, invalid, catch-all
    except Exception as e:
        logger.error(f"[Enrichment] ZeroBounce error: {e}")
    return "unknown"