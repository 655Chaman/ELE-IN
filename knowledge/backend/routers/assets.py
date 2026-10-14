from fastapi import APIRouter
from typing import List, Dict, Optional

router = APIRouter(tags=["assets"])

from fastapi import UploadFile, File, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from knowledge.backend.services.knowledge_service import KnowledgeService
from core.backend.services.job_queue import enqueue_job
import base64

class UrlUpload(BaseModel):
    url: str

class TextUpload(BaseModel):
    title: str
    text: str


# ── AI Knowledge Base ────────────────────────────────────────────────────────
from core.backend.api.auth_dep import get_supabase_client
from core.backend.api.auth_dep import get_current_workspace
from supabase import Client
from fastapi import Depends, HTTPException

@router.get("/knowledge/assets", response_model=List[Dict])
def get_knowledge_base(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Endpoint for getting AI knowledge documents."""
    return KnowledgeService.get_assets(supabase, workspace_id)
    
@router.get("/knowledge/synthesis", response_model=Optional[Dict])
def get_knowledge_synthesis(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Endpoint for getting AI synthesis (core value prop & tone)."""
    return KnowledgeService.get_synthesis(supabase, workspace_id) or {}

@router.post("/knowledge/upload/pdf", response_model=Optional[Dict])
async def add_knowledge_pdf(
    file: UploadFile = File(...),
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Endpoint for processing and vectorizing a PDF file."""
    # Paranoia Layer 1: Enforce Tier Knowledge Asset Limits
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
    from core.backend.services.credit_service import TIER_LIMITS
    limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    max_assets = limits.get("max_knowledge_assets", 3)
    
    current_count = supabase.table("knowledge_assets").select("id", count="exact").eq("workspace_id", workspace_id).execute().count or 0
    if current_count >= max_assets:
        raise HTTPException(
            status_code=403,
            detail=f"Knowledge Base limit reached: {ws_tier.capitalize()} Tier allows up to {max_assets} document{'s' if max_assets != 1 else ''}. Upgrade to Growth Pro to upload more."
        )

    import uuid
    content = await file.read()
    
    # Paranoia Layer 1 & 0: Minimum size & Magic bytes validation
    if len(content) < 64:
        raise HTTPException(status_code=400, detail="Uploaded PDF file is empty or corrupt (minimum 64 bytes required).")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid file contents. The uploaded file is not a valid PDF document (magic header %PDF- missing).")
    
    # SAAS SAFETY: 10MB file size limit to prevent memory/sync blocking
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")
        
    # MIME check before upload
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF is allowed.")
        
    asset_id = str(uuid.uuid4())
    
    storage_path = f"{workspace_id}/{asset_id}.pdf"
    
    uploaded_to_storage = False
    try:
        supabase.storage.from_('knowledge-files').upload(storage_path, content, {'content-type': 'application/pdf'})
        uploaded_to_storage = True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    asset = {
        "id": asset_id,
        "workspace_id": workspace_id,
        "name": file.filename, 
        "type": "pdf", 
        "status": "queued"
    }

    try:
        supabase.table("knowledge_assets").insert(asset).execute()
        enqueue_job(
            supabase, 
            'pdf', 
            workspace_id, 
            asset_id, 
            {
                'filename': file.filename, 
                'storage_path': storage_path
            }
        )
    except Exception as e:
        if uploaded_to_storage:
            try:
                supabase.storage.from_('knowledge-files').remove([storage_path])
            except Exception:
                pass
        try:
            supabase.table("knowledge_assets").delete().eq("id", asset_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to queue knowledge PDF job: {str(e)}")

    return {"status": "success", "asset": asset}
    
@router.post("/knowledge/upload/url", response_model=Optional[Dict])
async def add_knowledge_url(
    payload: UrlUpload,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Endpoint for scraping and vectorizing a URL in the background."""
    # Paranoia Layer 1: Enforce Tier Knowledge Asset Limits
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
    from core.backend.services.credit_service import TIER_LIMITS
    limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    max_assets = limits.get("max_knowledge_assets", 3)
    
    current_count = supabase.table("knowledge_assets").select("id", count="exact").eq("workspace_id", workspace_id).execute().count or 0
    if current_count >= max_assets:
        raise HTTPException(
            status_code=403,
            detail=f"Knowledge Base limit reached: {ws_tier.capitalize()} Tier allows up to {max_assets} document{'s' if max_assets != 1 else ''}. Upgrade to Growth Pro to add more."
        )

    # Paranoia Layer 2: Validate URL format and SSRF safety
    clean_url = (payload.url or "").strip()
    if not clean_url or not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid URL: must begin with http:// or https://")
    
    from core.backend.core.validators import is_safe_ssrf_url
    if not is_safe_ssrf_url(clean_url):
        raise HTTPException(status_code=400, detail="URL rejected due to security safety constraints (private or loopback IP).")

    import uuid
    
    # LAYER 2 (Human Paranoia): Prevent duplicate clicks queuing the exact same URL multiple times
    existing = supabase.table("knowledge_assets").select("*").eq("workspace_id", workspace_id).eq("source_url", clean_url).eq("status", "processing").execute()
    if existing.data:
        return existing.data[0]
        
    asset_id = str(uuid.uuid4())
    asset = {
        "id": asset_id, 
        "workspace_id": workspace_id,
        "name": clean_url, 
        "type": "url",
        "source_url": clean_url,  # stored for retry
        "status": "queued"
    }
    supabase.table("knowledge_assets").insert(asset).execute()
    
    enqueue_job(
        supabase, 
        'url', 
        workspace_id, 
        asset_id, 
        {'url': payload.url}
    )
    return {"status": "success", "asset": asset}

@router.delete("/knowledge/assets/{asset_id}")
def delete_knowledge_asset(
    asset_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Delete an asset and fully purge its vectors from pgvector."""
    success = KnowledgeService.delete_asset(supabase, workspace_id, asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    # Layer 0 Paranoia: Force a complete rebuild of the synthesis cache.
    # Without this, the AI will confidently hallucinate deleted features forever.
    enqueue_job(supabase, "synthesis", workspace_id, "sys_delete", {})
    return {"status": "success", "message": "Asset purged and synthesis rebuild queued."}

@router.post("/knowledge/assets/{asset_id}/retry")
async def retry_knowledge_asset(
    asset_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Retries processing a failed knowledge asset (re-scrapes URL or re-vectorizes text)."""
    # Fetch the asset
    res = supabase.table("knowledge_assets").select("*").eq("id", asset_id).eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    asset = res.data[0]
    if asset.get("status") not in ["failed", "error"]:
        raise HTTPException(status_code=400, detail="Only failed assets can be retried")
    
    # Reset status to queued
    supabase.table("knowledge_assets").update({"status": "queued"}).eq("id", asset_id).execute()
    
    asset_type = asset.get("type", "")
    if asset_type == "url":
        enqueue_job(
            supabase, 
            'url', 
            workspace_id, 
            asset_id, 
            {'url': asset.get("source_url", asset.get("name", ""))}
        )
    elif asset_type == "text":
        text_content = (asset.get("raw_text") or "").strip()
        if not text_content:
            # Layer 1 Paranoia: Attempt recovery from processing_jobs historical payload
            try:
                pj = supabase.table("processing_jobs").select("payload").eq("asset_id", asset_id).order("created_at", desc=True).limit(1).execute()
                if pj.data and isinstance(pj.data[0].get("payload"), dict):
                    text_content = pj.data[0]["payload"].get("text", "").strip()
            except Exception as pe:
                logger.debug(f"[KB] Could not recover text payload from processing_jobs: {pe}")

        if not text_content:
            supabase.table("knowledge_assets").update({"status": "failed"}).eq("id", asset_id).execute()
            raise HTTPException(
                status_code=400,
                detail="Original text is not available for retry. Please add the text snippet again."
            )

        enqueue_job(
            supabase, 
            'text', 
            workspace_id, 
            asset_id, 
            {'name': asset.get("name", "Text Snippet"), 'text': text_content}
        )
    elif asset_type == "pdf":
        storage_path = f"{workspace_id}/{asset_id}.pdf"
        file_exists = False
        try:
            files = supabase.storage.from_('knowledge-files').list(workspace_id)
            if any(f.get('name') == f"{asset_id}.pdf" for f in (files or [])):
                file_exists = True
        except Exception as se:
            logger.warning(f"[KB] Storage check failed for {asset_id}: {se}")
            # If bucket listing fails, optimistically attempt the job
            file_exists = True

        if file_exists:
            enqueue_job(
                supabase,
                'pdf',
                workspace_id,
                asset_id,
                {
                    'filename': asset.get("name", "document.pdf"),
                    'storage_path': storage_path
                }
            )
        else:
            supabase.table("knowledge_assets").update({"status": "failed"}).eq("id", asset_id).execute()
            raise HTTPException(
                status_code=400,
                detail="The original PDF file is no longer available in storage. Please upload the PDF again."
            )
    else:
        supabase.table("knowledge_assets").update({"status": "failed"}).eq("id", asset_id).execute()
        raise HTTPException(status_code=400, detail=f"Unsupported asset type '{asset_type}' for retry")
    
    return {"status": "retrying", "asset_id": asset_id}


from pydantic import BaseModel
from typing import Optional, Any

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    nodes_json: list
    edges_json: list
    tags: Optional[List[str]] = []
    status: str = "private" # "private" or "pending"

class TemplateResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    nodes_json: Any
    edges_json: Any
    status: str
    tags: List[str]
    downloads: int

# ── Templates ────────────────────────────────────────────────────────────────
@router.get("/templates/community", response_model=List[Dict])
def get_community_templates(supabase: Client = Depends(get_supabase_client)):
    """Fetch all public templates from the community."""
    res = supabase.table("templates").select("*").eq("status", "public").order("downloads", desc=True).execute()
    return res.data

@router.get("/templates/mine", response_model=List[Dict])
def get_my_templates(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Fetch user's private and pending templates."""
    res = supabase.table("templates").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
    return res.data

@router.post("/templates", response_model=Optional[Dict])
def create_template(
    template: TemplateCreate,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Create a new template. If status is 'pending', it goes to curation."""
    clean_name = (template.name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Template name cannot be empty.")
    
    if len(template.nodes_json or []) > 100:
        raise HTTPException(status_code=422, detail="Template exceeds maximum allowed nodes (100).")
    
    from campaigns.backend.services.dag_validator import validate_sequence_dag
    dag_rep = validate_sequence_dag(template.nodes_json or [], template.edges_json or [])
    if dag_rep.get("has_cycle"):
        raise HTTPException(status_code=422, detail="Invalid template: sequence graph contains an infinite cycle or loop.")
    if dag_rep.get("dangling_edges"):
        raise HTTPException(status_code=422, detail="Invalid template: sequence contains dangling edges pointing to non-existent nodes.")
    
    from campaigns.backend.services.template_spintax_guard import validate_campaign_nodes_templates
    syntax_issues = validate_campaign_nodes_templates(template.nodes_json or [])
    if syntax_issues:
        raise HTTPException(status_code=422, detail=f"Invalid template syntax: {'; '.join(syntax_issues)}")

    # Ensure they can only set it to private or pending, not directly to public
    safe_status = "pending" if template.status == "pending" else "private"
    
    data = {
        "workspace_id": workspace_id,
        "name": clean_name,
        "description": template.description,
        "nodes_json": template.nodes_json,
        "edges_json": template.edges_json,
        "tags": template.tags,
        "status": safe_status
    }
    res = supabase.table("templates").insert(data).execute()
    return res.data[0]

@router.post("/templates/{template_id}/clone", response_model=Optional[Dict])
def clone_community_template(
    template_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Clone a public template into the user's workspace."""
    # 1. Fetch the original
    original = supabase.table("templates").select("*").eq("id", template_id).eq("status", "public").single().execute()
    if not original.data:
        raise HTTPException(status_code=404, detail="Public template not found")
        
    original_data = original.data
    
    # 2. Increment download count (null-safe)
    downloads_count = int(original_data.get("downloads") or 0) + 1
    supabase.table("templates").update({"downloads": downloads_count}).eq("id", template_id).execute()
    
    # Prevent duplicate clones
    clone_name = f"Clone: {original_data['name']}"
    existing = supabase.table("templates").select("*").eq("workspace_id", workspace_id).eq("name", clone_name).execute()
    if existing and isinstance(existing.data, list) and len(existing.data) > 0:
        return existing.data[0]

    # 3. Create a private copy for the user
    clone_data = {
        "workspace_id": workspace_id,
        "name": clone_name,
        "description": original_data['description'],
        "nodes_json": original_data['nodes_json'],
        "edges_json": original_data['edges_json'],
        "tags": original_data['tags'],
        "status": "private"
    }
    clone_res = supabase.table("templates").insert(clone_data).execute()
    return clone_res.data[0]

# ── Admin (Templates Curation) ────────────────────────────────────────────────
from core.backend.api.auth_dep import get_service_client

@router.get("/templates/admin/pending", response_model=List[Dict])
def get_pending_templates(service_client: Client = Depends(get_service_client)):
    """Fetch all pending templates for review (Requires admin/service role in real app)."""
    res = service_client.table("templates").select("*").eq("status", "pending").order("created_at", desc=False).execute()
    return res.data

@router.post("/templates/admin/{template_id}/approve", response_model=Optional[Dict])
def approve_template(
    template_id: str,
    service_client: Client = Depends(get_service_client)
):
    """Approve a template (set status to 'public')."""
    res = service_client.table("templates").update({"status": "public"}).eq("id", template_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Template not found")
    return res.data[0]

@router.post("/templates/admin/{template_id}/reject", response_model=Optional[Dict])
def reject_template(
    template_id: str,
    service_client: Client = Depends(get_service_client)
):
    """Reject a template (set status to 'rejected')."""
    res = service_client.table("templates").update({"status": "rejected"}).eq("id", template_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Template not found")
    return res.data[0]

@router.put("/knowledge/synthesis")
def update_manual_synthesis(
    payload: dict,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Manual override for AI synthesis."""
    import re
    PROMPT_INJECTION_RE = re.compile(
        r"(?i)(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt\s+override|disregard\s+all\s+prior|you\s+are\s+now\s+dan|developer\s+mode\s+enabled)"
    )
    for field in ("core_value_prop", "target_customer_profile", "objection_playbook", "banned_phrases"):
        val_str = str(payload.get(field) or "")
        if PROMPT_INJECTION_RE.search(val_str):
            raise HTTPException(status_code=422, detail=f"Prompt injection directive detected in '{field}'.")

    def _coerce_list(val: Any) -> list:
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        elif isinstance(val, str) and val.strip():
            return [x.strip() for x in val.replace("\n", ",").split(",") if x.strip()]
        return []

    upsert_data = {
        "workspace_id": workspace_id,
        "core_value_prop": payload.get("core_value_prop", ""),
        "identified_tone": _coerce_list(payload.get("identified_tone")),
        "target_customer_profile": payload.get("target_customer_profile", ""),
        "key_differentiators": _coerce_list(payload.get("key_differentiators")),
        "proof_points": _coerce_list(payload.get("proof_points")),
        "primary_pain_points_solved": _coerce_list(payload.get("primary_pain_points_solved")),
        "banned_phrases": payload.get("banned_phrases", ""),
        "objection_playbook": payload.get("objection_playbook", ""),
        "buyer_personas": _coerce_list(payload.get("buyer_personas"))
    }
    supabase.table("knowledge_synthesis").upsert(upsert_data).execute()
    return {"status": "success"}

@router.post("/knowledge/upload/text", response_model=Optional[Dict])
async def add_knowledge_text(
    payload: TextUpload,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Endpoint for processing manually pasted text in the background."""
    # Paranoia Layer 1: Enforce Tier Knowledge Asset Limits
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
    from core.backend.services.credit_service import TIER_LIMITS
    limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    max_assets = limits.get("max_knowledge_assets", 3)
    
    current_count = supabase.table("knowledge_assets").select("id", count="exact").eq("workspace_id", workspace_id).execute().count or 0
    if current_count >= max_assets:
        raise HTTPException(
            status_code=403,
            detail=f"Knowledge Base limit reached: {ws_tier.capitalize()} Tier allows up to {max_assets} document{'s' if max_assets != 1 else ''}. Upgrade to Growth Pro to add more."
        )

    import uuid
    import hashlib
    
    clean_text = (payload.text or "").strip()
    if not clean_text or len(clean_text) < 10:
        raise HTTPException(status_code=400, detail="Text is too short.")
    if len(clean_text) > 500000:
        raise HTTPException(status_code=413, detail="Text snippet is too large. Maximum length is 500,000 characters.")
        
    clean_title = (payload.title or "Text Snippet").strip()[:255] or "Text Snippet"

    # LAYER 2 (Human Paranoia): Hash the text to prevent users from mashing 'Upload' 50 times
    text_hash = hashlib.md5(clean_text.encode()).hexdigest()
    # Check if a processing job for this exact text hash already exists in this workspace
    existing = supabase.table("processing_jobs").select("*").eq("workspace_id", workspace_id).eq("job_type", "text_process").eq("status", "pending").execute()
    for job in existing.data:
        if job.get("payload", {}).get("hash") == text_hash:
            # Found duplicate pending job, just return the existing asset
            existing_asset = supabase.table("knowledge_assets").select("*").eq("id", job.get("asset_id")).execute()
            if existing_asset.data:
                return existing_asset.data[0]

    asset_id = str(uuid.uuid4())
    asset = {
        "id": asset_id, 
        "workspace_id": workspace_id,
        "name": clean_title, 
        "type": "text", 
        "raw_text": clean_text,
        "status": "queued"
    }
    try:
        supabase.table("knowledge_assets").insert(asset).execute()
    except Exception as e:
        err_msg = str(e).lower()
        if "raw_text" in err_msg and ("does not exist" in err_msg or "pgrst204" in err_msg or "42703" in err_msg):
            # Fallback for DB where migration 070 has not been executed yet
            asset_fallback = {k: v for k, v in asset.items() if k != "raw_text"}
            supabase.table("knowledge_assets").insert(asset_fallback).execute()
        else:
            raise
    
    enqueue_job(
        supabase, 
        'text', 
        workspace_id, 
        asset_id, 
        {'name': payload.title, 'text': payload.text}
    )
    return {"status": "success", "asset": asset}

@router.post("/knowledge/synthesis/approve")
async def approve_knowledge_synthesis(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Phase 4 Paranoia: Promotes a draft synthesis to the active knowledge_synthesis table.
    This ensures synthesis is never auto-applied silently without human review.
    """
    # Check active knowledge_chunks table first, fall back to legacy knowledge_vectors table
    has_vectors = False
    try:
        vec_res = supabase.table("knowledge_chunks").select("id", count="exact").eq("workspace_id", workspace_id).limit(1).execute()
        if vec_res.count and vec_res.count > 0:
            has_vectors = True
    except Exception:
        pass

    if not has_vectors:
        try:
            vec_res_legacy = supabase.table("knowledge_vectors").select("id", count="exact").eq("workspace_id", workspace_id).limit(1).execute()
            if vec_res_legacy.count and vec_res_legacy.count > 0:
                has_vectors = True
        except Exception:
            pass

    if not has_vectors:
        raise HTTPException(status_code=409, detail="Cannot approve synthesis: this workspace has no indexed knowledge content. Please re-upload your documents first.")

    res = supabase.table("knowledge_synthesis_drafts").select("*").eq("workspace_id", workspace_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="No synthesis draft found to approve.")
        
    draft = res.data[0]
    draft.pop("status", None)
    
    # Upsert into active synthesis
    supabase.table("knowledge_synthesis").upsert(draft, on_conflict="workspace_id").execute()
    
    # Delete the draft
    supabase.table("knowledge_synthesis_drafts").delete().eq("workspace_id", workspace_id).execute()
    
    return {"status": "success", "message": "Synthesis approved and applied."}

# ── Objections / Playbooks ───────────────────────────────────────────────────

class ObjectionPayload(BaseModel):
    trigger: str
    playbook: str

@router.get("/knowledge/objections")
async def get_objections(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Workspace context required")
    try:
        res = supabase.table("knowledge_objections").select("*").eq("workspace_id", workspace_id).order("created_at", desc=False).execute()
        # Frontend expects { id, name, rebuttal }
        formatted = []
        for row in res.data:
            formatted.append({
                "id": row["id"],
                "name": row["trigger"],
                "rebuttal": row["playbook"],
                "created_at": row["created_at"]
            })
        return formatted
    except Exception as e:
        raise HTTPException(status_code=503, detail="Knowledge service temporarily unavailable")

@router.post("/knowledge/objections")
async def create_objection(
    payload: ObjectionPayload,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Workspace context required")
    
    trigger_clean = payload.trigger.strip() if payload.trigger else ""
    playbook_clean = payload.playbook.strip() if payload.playbook else ""
    
    if not trigger_clean or not playbook_clean:
        raise HTTPException(status_code=422, detail="Trigger and playbook cannot be empty")
    if len(trigger_clean) > 500 or len(playbook_clean) > 5000:
        raise HTTPException(status_code=422, detail="Payload length limits exceeded")

    try:
        existing = supabase.table("knowledge_objections").select("*").eq("workspace_id", workspace_id).eq("trigger", trigger_clean).maybe_single().execute()
        if existing and existing.data:
            return {"success": True, "objection": existing.data}
            
        res = supabase.table("knowledge_objections").insert({
            "workspace_id": workspace_id,
            "trigger": trigger_clean,
            "playbook": playbook_clean
        }).execute()
        return {"success": True, "objection": res.data[0] if res.data else None}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Knowledge service temporarily unavailable")

@router.put("/knowledge/objections/{objection_id}")
async def update_objection(
    objection_id: str,
    payload: ObjectionPayload,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Workspace context required")

    trigger_clean = payload.trigger.strip() if payload.trigger else ""
    playbook_clean = payload.playbook.strip() if payload.playbook else ""

    if not trigger_clean or not playbook_clean:
        raise HTTPException(status_code=422, detail="Trigger and playbook cannot be empty")
    if len(trigger_clean) > 500 or len(playbook_clean) > 5000:
        raise HTTPException(status_code=422, detail="Payload length limits exceeded")

    try:
        res = supabase.table("knowledge_objections").update({
            "trigger": trigger_clean,
            "playbook": playbook_clean
        }).eq("id", objection_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Objection not found")
        return {"success": True, "objection": res.data[0] if res.data else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail="Knowledge service temporarily unavailable")

@router.delete("/knowledge/objections/{objection_id}")
async def delete_objection(
    objection_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Workspace context required")
    try:
        res = supabase.table("knowledge_objections").delete().eq("id", objection_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Objection not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail="Knowledge service temporarily unavailable")

class TestObjectionRequest(BaseModel):
    objection: str
    
@router.post("/knowledge/test-objection")
async def test_objection(
    req: TestObjectionRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    from knowledge.backend.services.elein_ai_service import _run_llm_with_failover
    
    # Layer 1 Paranoia: Fallback to draft if live synthesis is missing due to schema desync
    synthesis = KnowledgeService.get_synthesis(supabase, workspace_id)
    if not synthesis or not synthesis.get('key_differentiators'):
        draft_res = supabase.table("knowledge_synthesis_drafts").select("*").eq("workspace_id", workspace_id).execute()
        if draft_res.data:
            synthesis = draft_res.data[0]
            
    if not synthesis:
        raise HTTPException(status_code=400, detail="No synthesis available. Please seed the workspace first.")
        
    synthesis_layer = f"CORE VALUE PROP:\n{synthesis.get('core_value_prop', '')}\n\n"
    if isinstance(synthesis.get('key_differentiators'), list):
        synthesis_layer += f"KEY DIFFERENTIATORS:\n{', '.join(synthesis.get('key_differentiators', []))}\n\n"
    if isinstance(synthesis.get('proof_points'), list):
        synthesis_layer += f"PROOF POINTS:\n{', '.join(synthesis.get('proof_points', []))}\n\n"
        
    system_prompt = f"""You are an elite Sales Development Representative handling objections.

--- LAYER 1: WORKSPACE CONSTITUTION ---
{synthesis_layer}

--- LAYER 2: EXECUTION RULES ---
GOAL: Write exactly ONE concise paragraph to handle the objection.
1. Acknowledge the objection professionally.
2. Pivot using our specific key differentiators or proof points.
3. Close with a soft question or call to action.
DO NOT use generic boilerplate. Use the exact proof points provided in the constitution."""

    user_prompt = f"LEAD OBJECTION:\n{req.objection}\n\nWrite the reply:"

    try:
        reply = _run_llm_with_failover(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=300,
            temperature=0.7,
            task="generation",
            workspace_id=workspace_id
        )
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
