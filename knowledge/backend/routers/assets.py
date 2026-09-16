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
    import uuid
    content = await file.read()
    
    # SAAS SAFETY: 10MB file size limit to prevent memory/sync blocking
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")
        
    # MIME check before upload
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF is allowed.")
        
    asset_id = str(uuid.uuid4())
    
    storage_path = f"{workspace_id}/{asset_id}.pdf"
    
    try:
        # LAYER 0: Upload to Supabase Storage
        supabase.storage.from_('knowledge-files').upload(storage_path, content, {'content-type': 'application/pdf'})
    except Exception as e:
        # LAYER 1: Catch upload exception, return 500
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    asset = {
        "id": asset_id,
        "workspace_id": workspace_id,
        "name": file.filename, 
        "type": "pdf", 
        "status": "queued"
    }
    supabase.table("knowledge_assets").insert(asset).execute()
    
    # NEVER pass file content directly to enqueue_job(). Files go to Supabase Storage, only the path goes to the queue.
    # Note: If enqueue_job fails here, the file is orphaned in Storage. Cleanup debt.
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
    return {"status": "success", "asset": asset}
    
@router.post("/knowledge/upload/url", response_model=Optional[Dict])
async def add_knowledge_url(
    payload: UrlUpload,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """Endpoint for scraping and vectorizing a URL in the background."""
    import uuid
    
    # LAYER 2 (Human Paranoia): Prevent duplicate clicks queuing the exact same URL multiple times
    existing = supabase.table("knowledge_assets").select("*").eq("workspace_id", workspace_id).eq("source_url", payload.url).eq("status", "processing").execute()
    if existing.data:
        return existing.data[0]
        
    asset_id = str(uuid.uuid4())
    asset = {
        "id": asset_id, 
        "workspace_id": workspace_id,
        "name": payload.url, 
        "type": "url",
        "source_url": payload.url,  # stored for retry
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
    
    # Reset status to processing
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
        enqueue_job(
            supabase, 
            'text', 
            workspace_id, 
            asset_id, 
            {'name': asset.get("name", ""), 'text': asset.get("raw_text", "")}
        )
    else:
        # PDF retry requires re-upload — just give a clear error
        supabase.table("knowledge_assets").update({"status": "failed"}).eq("id", asset_id).execute()
        raise HTTPException(status_code=400, detail="PDF assets must be re-uploaded to retry")
    
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
    # Ensure they can only set it to private or pending, not directly to public
    safe_status = "pending" if template.status == "pending" else "private"
    
    data = {
        "workspace_id": workspace_id,
        "name": template.name,
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
    
    # 2. Increment download count
    supabase.table("templates").update({"downloads": original_data["downloads"] + 1}).eq("id", template_id).execute()
    
    # 3. Create a private copy for the user
    clone_data = {
        "workspace_id": workspace_id,
        "name": f"Clone: {original_data['name']}",
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
    upsert_data = {
        "workspace_id": workspace_id,
        "core_value_prop": payload.get("core_value_prop", ""),
        "identified_tone": payload.get("identified_tone", []),
        "target_customer_profile": payload.get("target_customer_profile", ""),
        "key_differentiators": payload.get("key_differentiators", []),
        "proof_points": payload.get("proof_points", []),
        "primary_pain_points_solved": payload.get("primary_pain_points_solved", []),
        "banned_phrases": payload.get("banned_phrases", ""),
        "objection_playbook": payload.get("objection_playbook", ""),
        "buyer_personas": payload.get("buyer_personas", [])
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
    import uuid
    import hashlib
    
    if not payload.text or len(payload.text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Text is too short.")
        
    # LAYER 2 (Human Paranoia): Hash the text to prevent users from mashing 'Upload' 50 times
    text_hash = hashlib.md5(payload.text.encode()).hexdigest()
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
        "name": payload.title, 
        "type": "text", 
        "status": "queued"
    }
    supabase.table("knowledge_assets").insert(asset).execute()
    
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
    vec_res = supabase.table("knowledge_vectors").select("id", count="exact").eq("workspace_id", workspace_id).limit(1).execute()
    if not vec_res.count:
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
