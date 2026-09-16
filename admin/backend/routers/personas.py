from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from supabase import Client
from admin.backend.services.persona_service import PersonaService
from knowledge.backend.services.knowledge_service import KnowledgeService
from core.backend.api.auth_dep import get_supabase_client
from core.backend.api.auth_dep import get_current_workspace

router = APIRouter(tags=["personas"])

class PersonaCreate(BaseModel):
    title: str
    painPoints: Optional[List[str]] = []
    value_prop: Optional[str] = ""
    target_titles: Optional[List[str]] = []
    tone_tweaks: Optional[str] = ""
    

class TestDriveRequest(BaseModel):
    message: str

# --- Docs API ---
@router.post("/test-drive")
async def test_drive_ai(
    payload: TestDriveRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Simulates how the AI will respond to a specific prospect message 
    using the current Knowledge Base, Personas, and Objections.
    """
    from knowledge.backend.services.elein_ai_service import generate_test_drive_response
    
    response_text = await generate_test_drive_response(
        supabase, workspace_id, message=payload.message
    )
    return {"response": response_text}

@router.get("/campaign-context")
async def get_campaign_context(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    BRIDGE TO CAMPAIGNS MODULE
    """
    from knowledge.backend.services.knowledge_service import KnowledgeService
    
    assets = KnowledgeService.get_assets(supabase, workspace_id)
    synthesis = KnowledgeService.get_synthesis(supabase, workspace_id)
    personas = PersonaService.get_personas(supabase, workspace_id)
    objections = PersonaService.get_objections(supabase, workspace_id)
    
    return {
        "is_ready": len(assets) > 0 and len(personas) > 0,
        "brain": {
            "synthesis": synthesis,
            "assets_count": len(assets),
            "personas": personas,
            "objection_playbook": objections
        }
    }

# --- Personas API ---

@router.get("/personas", response_model=List[Dict])
def get_personas(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    return PersonaService.get_personas(supabase, workspace_id)

@router.post("/personas", response_model=Dict)
def create_persona(
    payload: PersonaCreate,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    return PersonaService.create_persona(supabase, workspace_id, payload.dict())

@router.put("/personas/{persona_id}", response_model=Dict)
def update_persona(
    persona_id: str, 
    payload: PersonaCreate,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    updated = PersonaService.update_persona(supabase, workspace_id, persona_id, payload.dict())
    if not updated:
        raise HTTPException(status_code=404, detail="Persona not found")
    return updated

@router.delete("/personas/{persona_id}")
def delete_persona(
    persona_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    success = PersonaService.delete_persona(supabase, workspace_id, persona_id)
    if not success:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"status": "success"}

