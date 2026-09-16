from typing import Optional, Any, Dict, List

from pydantic import BaseModel


class LeadBase(BaseModel):
    market: str
    side: str
    pipeline_id: str
    company_name: str
    domain:Optional[ str ] = ""
    company_description:Optional[ str ] = ""
    kdm_first:Optional[ str ] = ""
    kdm_last:Optional[ str ] = ""
    job_title:Optional[ str ] = ""
    linkedin_url:Optional[ str ] = ""
    verified_email:Optional[ str ] = ""
    target_campaign_tier:Optional[ str ] = ""
    enrichment_source:Optional[ str ] = ""
    status:Optional[ str ] = "extracted"

class LeadCreate(LeadBase):
    id:Optional[ str ] = None # Generated if None

class LeadResponse(LeadBase):
    id: str
    created_at: str

    class Config:
        from_attributes = True
