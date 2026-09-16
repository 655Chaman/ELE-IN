import logging
import os

from openai import OpenAI
from pydantic import BaseModel, Field

from core.backend.api.auth_dep import get_service_client
from core.backend.services.key_service import get_current_keys

logger = logging.getLogger(__name__)

class CopywritingResult(BaseModel):
    subject_line: str = Field(description="A highly personalized, attention-grabbing subject line.")
    email_body: str = Field(description="The body of the cold email, formatted with line breaks, leveraging the context of the lead.")

def get_llm_client():
    keys = get_current_keys()
    provider = keys.get("llm_provider", "openai")
    api_key = (
        keys.get("api_key_llm") or 
        keys.get("api_key_openai") or 
        os.getenv("OPENAI_API_KEY")
    )
    configured_model = keys.get("llm_model", "gpt-4o-mini")

    if not api_key:
        return None, configured_model
        
    client = OpenAI(api_key=api_key, max_retries=2)
    return client, configured_model

def write_copy_for_pipeline(pipeline_id: str):
    """
    Generates personalized email copy for all 'vetted_pass' leads in the DB for a given pipeline.
    """
    client, model = get_llm_client()
    if not client:
        logger.error("No LLM API key configured for copywriting.")
        return
        
    supabase = get_service_client()
    # Fetch leads that passed vetting
    res = supabase.table("leads").select("id, company_name, company_description, kdm_first, kdm_last, job_title").eq("pipeline_id", pipeline_id).eq("status", "vetted_pass").execute()
    leads = res.data
    
    logger.info(f"Generating copy for {len(leads)} vetted leads for pipeline {pipeline_id}...")
    
    for lead in leads:
        lead_id = lead['id']
        company_name = lead.get('company_name', '')
        description = lead.get('company_description', '')
        kdm_first = lead.get('kdm_first') or "there"
        job_title = lead.get('job_title', '')
        
        prompt = f"""
        You are an elite B2B copywriter.
        Write a short, highly personalized cold email to this prospect.
        
        Target Person: {kdm_first} (Title: {job_title})
        Company Name: {company_name}
        Context/Breach Info: {description}
        
        RULES:
        1. Subject line should be under 5 words, lowercase, intriguing.
        2. Body should be under 100 words.
        3. Do NOT use buzzwords. Be conversational, direct, and mention their specific context.
        4. End with a soft call to action.
        """
        
        try:
            # Using native OpenAI structured outputs
            completion = client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an elite copywriter AI. Respond with the requested JSON schema."},
                    {"role": "user", "content": prompt}
                ],
                response_format=CopywritingResult
            )
            result = completion.choices[0].message.parsed
            
            # Save the copy to the copies table and update the lead status
            # Wait, the copies table is linked via match_id.
            # I will just create a basic UUID for the copy entry for now or alter the schema if needed.
            import uuid
            copy_id = str(uuid.uuid4())
            supabase.table("copies").insert({
                "id": copy_id,
                "match_id": lead_id,
                "variation_type": "email_v1",
                "supply_to_demand_copy": f"Subject: {result.subject_line}\n\n{result.email_body}",
                "status": "generated"
            }).execute()
            
            supabase.table("leads").update({"status": "copy_ready"}).eq("id", lead_id).execute()
            
            logger.info(f"[COPY GENERATED] {company_name} -> {kdm_first}")
            
        except Exception as e:
            logger.error(f"Copywriting failed for {company_name}: {e}")
            
    logger.info("Copywriting complete.")
