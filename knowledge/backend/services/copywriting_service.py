from knowledge.backend.services.prompt_safety import sanitize_for_prompt, truncate_to_context_limit
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
    
    # Fetch workspace_id from pipeline
    pipeline_res = supabase.table("pipelines").select("workspace_id").eq("id", pipeline_id).limit(1).execute()
    if not pipeline_res.data:
        logger.error(f"Could not find workspace_id for pipeline {pipeline_id}")
        return
    workspace_id = pipeline_res.data[0]["workspace_id"]
    
    # Fetch leads that passed vetting
    res = supabase.table("leads").select("id, company_name, company_description, kdm_first, kdm_last, job_title").eq("pipeline_id", pipeline_id).eq("status", "vetted_pass").execute()
    leads = res.data
    
    lead_count = len(leads) if leads else 0
    if lead_count == 0:
        logger.info(f"No vetted leads found for pipeline {pipeline_id}.")
        return

    import time, json, hashlib
    from core.backend.services.credit_service import refund_credits

    lead_ids_sorted = sorted(str(lead.get('id')) for lead in leads if lead.get('id'))
    batch_digest = hashlib.sha256(",".join(lead_ids_sorted).encode("utf-8")).hexdigest()[:16]
    idempotency_key = f"copy_{workspace_id}_{pipeline_id}_{batch_digest}"
    
    deducted = False
    _deduct_res = supabase.rpc('deduct_credits_safely', {
        'p_workspace_id': workspace_id,
        'p_amount': lead_count,
        'p_action_type': 'ai_copywriting',
        'p_idempotency_key': idempotency_key,
        'p_metadata': json.dumps({"leads_count": lead_count})
    }).execute()
    if _deduct_res.data and not _deduct_res.data.get('success', False):
        logger.error(f"Insufficient credits for copywriting in workspace {workspace_id}")
        return
    deducted = True

    logger.info(f"Generating copy for {len(leads)} vetted leads for pipeline {pipeline_id}...")

    successful_count = 0
    try:
        for lead in leads:
            lead_id = lead['id']
            company_name = lead.get('company_name', '')
            description = lead.get('company_description', '')
            kdm_first = lead.get('kdm_first') or "there"
            job_title = lead.get('job_title', '')
            
            prompt = f"""
            You are an elite B2B copywriter.
            Write a short, highly personalized cold email to this prospect.
            
            Target Person: {sanitize_for_prompt(kdm_first, 'kdm_first')} (Title: {sanitize_for_prompt(job_title, 'job_title')})
            Company Name: {sanitize_for_prompt(company_name, 'company_name')}
            Context/Breach Info: {sanitize_for_prompt(description, 'company_description')}
            
            RULES:
            1. Subject line should be under 5 words, lowercase, intriguing.
            2. Body should be under 100 words.
            3. Do NOT use buzzwords. Be conversational, direct, and mention their specific context.
            4. End with a soft call to action.
            """
            
            try:
                # Using native OpenAI structured outputs
                msgs = [{"role": "system", "content": "You are an elite copywriter AI. Respond with the requested JSON schema."}, {"role": "user", "content": prompt}]
                completion = client.beta.chat.completions.parse(
                    model=model,
                    messages=truncate_to_context_limit(msgs),
                    response_format=CopywritingResult
                )
                result = completion.choices[0].message.parsed
                
                # Save the copy to the copies table and update the lead status
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
                successful_count += 1
                logger.info(f"[COPY GENERATED] {company_name} -> {kdm_first}")
                
            except Exception as e:
                logger.error(f"Copywriting failed for {company_name}: {e}")
    finally:
        # Paranoia Layer 0, 1 & 2: Pro-rata refund for any failed leads in batch
        failed_count = lead_count - successful_count
        if deducted and failed_count > 0:
            try:
                refund_idem = f"refund_{idempotency_key}_fail_{failed_count}"
                logger.info(f"[Copywriting] Refunding {failed_count} credits for failed leads (Workspace: {workspace_id})")
                refund_credits(
                    workspace_id=workspace_id,
                    amount=failed_count,
                    idempotency_key=refund_idem,
                    reason="copywriting_partial_failure",
                    supabase_client=supabase
                )
            except Exception as ref_err:
                logger.warning(f"[Copywriting] Pro-rata refund failed for workspace {workspace_id}: {ref_err}")

    logger.info(f"Copywriting complete: {successful_count}/{lead_count} succeeded, {lead_count - successful_count} refunded.")
