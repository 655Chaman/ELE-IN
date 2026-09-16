from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os

router = APIRouter()

class ApolloSearchRequest(BaseModel):
    api_key: str
    keywords: Optional[str] = None
    job_titles: Optional[List[str]] = []
    locations: Optional[List[str]] = []
    companies: Optional[List[str]] = []
    industries: Optional[List[str]] = []

@router.post("/search")
async def search_apollo(data: ApolloSearchRequest):
    if not data.api_key:
        raise HTTPException(status_code=400, detail="Apollo API Key is required")
        
    url = "https://api.apollo.io/v1/mixed_people/search"
    
    payload = {
        "api_key": data.api_key,
        "page": 1,
        "per_page": 100  # Pull up to 100 leads per request for MVP
    }
    
    if data.keywords:
        payload["q_keywords"] = data.keywords
        
    if data.job_titles and len(data.job_titles) > 0:
        payload["person_titles"] = data.job_titles
        
    if data.locations and len(data.locations) > 0:
        payload["person_locations"] = data.locations
        
    if data.companies and len(data.companies) > 0:
        payload["organization_names"] = data.companies
        
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache"
    }
    from core.backend.services.http_client import async_external_request
    
    # We remove try/except block catching all exceptions since async_external_request 
    # handles TimeoutException and RequestError properly. We can still catch others if needed, 
    # or let FastAPI handle it.
    
    resp = await async_external_request(
        method="POST", 
        url=url, 
        json_data=payload, 
        headers=headers,
        timeout=30.0
    )
    
    if resp.status_code != 200:
        # Don't return raw resp.text in case it has keys!
        raise HTTPException(status_code=resp.status_code, detail="Apollo API Error. Request failed.")
        
    result = resp.json()
    
    # Extract LinkedIn URLs and basic info to feed into Ele-in
    leads = []
    for person in result.get("people", []):
        leads.append({
            "name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
            "title": person.get("title", ""),
            "company": person.get("organization", {}).get("name", ""),
            "linkedin_url": person.get("linkedin_url", ""),
            "email": person.get("email", "")
        })
        
    return {
        "status": "success", 
        "total_matches": result.get("pagination", {}).get("total_entries", 0),
        "leads": leads
    }
