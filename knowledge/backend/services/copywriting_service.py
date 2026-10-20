import os
import re
import uuid
import time
import json
import hashlib
import logging
import threading
from typing import Optional, Any, Dict, List

from openai import OpenAI
from pydantic import BaseModel, Field

from core.backend.api.auth_dep import get_service_client
from core.backend.services.key_service import get_current_keys
from knowledge.backend.services.prompt_safety import (
    sanitize_for_prompt,
    truncate_to_context_limit,
    truncate_to_tokens
)
from knowledge.backend.services.ai_output_guard import sanitize_outbound_ai_message

logger = logging.getLogger(__name__)

_copywriting_lock = threading.RLock()


class CopywritingResult(BaseModel):
    subject_line: str = Field(description="A highly personalized, attention-grabbing subject line.")
    email_body: str = Field(description="The body of the cold email, formatted with line breaks, leveraging the context of the lead.")


def get_llm_client(workspace_id: Optional[str] = None, supabase_client: Any = None):
    from integrations.backend.services.credential_vault import vault

    keys = get_current_keys()
    provider = keys.get("llm_provider", "openai")
    configured_model = keys.get("llm_model", "gpt-4o-mini") or "gpt-4o-mini"

    # Paranoia Layer 0 & 1 (Issue 31 resolution): Prefer tenant-scoped decrypted BYOK credential from AI Gateway vault
    api_key = None
    if workspace_id:
        try:
            from knowledge.backend.routers.ai_gateway import get_decrypted_workspace_byok_key
            sb = supabase_client or get_service_client()
            byok_tuple = get_decrypted_workspace_byok_key(sb, workspace_id)
            if byok_tuple and byok_tuple[1]:
                provider, api_key = byok_tuple
        except Exception as e:
            logger.debug(f"[Copywriting] AI Gateway BYOK key resolution fallback: {e}")

        if not api_key:
            api_key = vault.resolve_credential(workspace_id, "openai", supabase_client=supabase_client)
            if not api_key:
                api_key = vault.resolve_credential(workspace_id, "nvidia", supabase_client=supabase_client)

    if not api_key:
        api_key = (
            keys.get("api_key_llm") or 
            keys.get("api_key_openai") or 
            keys.get("api_key_nvidia") or
            os.getenv("OPENAI_API_KEY") or
            os.getenv("NVIDIA_API_KEY")
        )

    if not api_key:
        return None, configured_model
        
    clean_api_key = str(api_key).strip().strip("'\"")
    if not clean_api_key:
        return None, configured_model

    # Support NVIDIA API base URL if key starts with nvapi- or provider is nvidia
    is_nvidia = clean_api_key.startswith("nvapi-") or provider == "nvidia"
    if is_nvidia:
        base_url = "https://integrate.api.nvidia.com/v1"
        model_name = configured_model if configured_model and "llama" in configured_model.lower() else "meta/llama-3.3-70b-instruct"
        client = OpenAI(api_key=clean_api_key, base_url=base_url, max_retries=2)
        return client, model_name

    client = OpenAI(api_key=clean_api_key, max_retries=2)
    return client, configured_model


def write_copy_for_pipeline(pipeline_id: str):
    """
    Generates personalized email copy for all 'vetted_pass' leads in the DB for a given pipeline.
    Paranoia Layer 0, 1 & 2:
    - Layer 0: Generates structured, high-conversion copy using OpenAI structured outputs.
    - Layer 1: Context limit bounding, token clamping, and pro-rata refunding of unused credits on failure.
    - Layer 2: Sanitizes all prompt inputs against prompt injection and formula prefixes; uses deterministic
               UUID5 keys and conflict-tolerant persistence to prevent duplicate copy records.
    """
    supabase = get_service_client()
    
    # Fetch workspace_id from pipeline
    pipeline_res = supabase.table("pipelines").select("workspace_id").eq("id", pipeline_id).limit(1).execute()
    if not pipeline_res.data:
        logger.error(f"Could not find workspace_id for pipeline {pipeline_id}")
        return
    workspace_id = pipeline_res.data[0]["workspace_id"]

    client, model = get_llm_client(workspace_id=workspace_id, supabase_client=supabase)
    if not client:
        logger.error(f"No LLM API key configured for copywriting in workspace {workspace_id}.")
        return
    
    # Fetch leads that passed vetting
    res = supabase.table("leads").select("id, company_name, company_description, kdm_first, kdm_last, job_title").eq("pipeline_id", pipeline_id).eq("status", "vetted_pass").execute()
    leads = res.data
    
    lead_count = len(leads) if leads else 0
    if lead_count == 0:
        logger.info(f"No vetted leads found for pipeline {pipeline_id}.")
        return

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
            lead_id = lead.get('id')
            if not lead_id:
                continue

            company_name = str(lead.get('company_name') or '').strip()
            raw_description = str(lead.get('company_description') or '').strip()
            # Bound description tokens to prevent context stuffing and cost overrun
            description = truncate_to_tokens(raw_description, 250)

            raw_kdm = str(lead.get('kdm_first') or '').strip()
            kdm_first = raw_kdm if raw_kdm else "there"
            job_title = str(lead.get('job_title') or '').strip()
            
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
                # Using native OpenAI structured outputs with fallback for NVIDIA / OpenAI-compatible endpoints
                msgs = [
                    {"role": "system", "content": "You are an elite copywriter AI. Respond with the requested JSON schema."},
                    {"role": "user", "content": prompt}
                ]
                result = None
                try:
                    completion = client.beta.chat.completions.parse(
                        model=model,
                        messages=truncate_to_context_limit(msgs),
                        response_format=CopywritingResult
                    )
                    if completion and completion.choices:
                        result = completion.choices[0].message.parsed
                except (AttributeError, TypeError, Exception) as parse_err:
                    logger.debug(f"Structured parse failed or unsupported on endpoint, attempting JSON chat completion: {parse_err}")
                    raw_completion = client.chat.completions.create(
                        model=model,
                        messages=truncate_to_context_limit(msgs),
                        temperature=0.3
                    )
                    if raw_completion and raw_completion.choices:
                        content_str = raw_completion.choices[0].message.content or ""
                        # Layer 1 Paranoia (Issue 16 resolution): Resilient auto-repair parser instead of greedy regex
                        from knowledge.backend.services.knowledge_service import _repair_and_parse_json
                        parsed_json = _repair_and_parse_json(content_str)
                        if parsed_json and isinstance(parsed_json, dict):
                            result = CopywritingResult(
                                subject_line=str(parsed_json.get("subject_line") or "quick question"),
                                email_body=str(parsed_json.get("email_body") or content_str)
                            )
                        else:
                            # Fallback to direct text if no valid JSON structure recovered
                            result = CopywritingResult(
                                subject_line="quick question",
                                email_body=content_str
                            )

                if not result or not isinstance(result, CopywritingResult):
                    raise ValueError(f"Failed to parse valid CopywritingResult schema for lead {lead_id}")

                # Paranoia Layer 1 & 2: Output guard validation on subject line and email body
                clean_subject, subj_valid, subj_reason = sanitize_outbound_ai_message(
                    result.subject_line,
                    max_chars=100,
                    context_type="email_subject"
                )
                clean_body, body_valid, body_reason = sanitize_outbound_ai_message(
                    result.email_body,
                    max_chars=3000,
                    context_type="email_body"
                )

                if not subj_valid or not body_valid:
                    rejection_reason = subj_reason if not subj_valid else body_reason
                    raise ValueError(f"AI Output Guard rejected generated copy: {rejection_reason}")

                # Save the copy to the copies table and update the lead status
                copy_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"copy:{workspace_id}:{pipeline_id}:{lead_id}"))
                copy_record = {
                    "id": copy_id,
                    "match_id": lead_id,
                    "workspace_id": workspace_id,
                    "variation_type": "email_v1",
                    "supply_to_demand_copy": f"Subject: {clean_subject}\n\n{clean_body}",
                    "status": "generated"
                }
                try:
                    supabase.table("copies").upsert(copy_record, on_conflict="id").execute()
                except Exception:
                    supabase.table("copies").insert(copy_record).execute()
                
                supabase.table("leads").update({"status": "copy_ready"}).eq("id", lead_id).execute()
                successful_count += 1
                logger.info(f"[COPY GENERATED] {company_name} -> {kdm_first}")
                
            except Exception as e:
                logger.error(f"Copywriting failed for {company_name or lead_id}: {e}")
    finally:
        # Paranoia Layer 0, 1 & 2: Pro-rata refund for any failed leads in batch
        failed_count = lead_count - successful_count
        if deducted and failed_count > 0:
            try:
                from core.backend.services.credit_service import refund_credits
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
