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
    title: str = "New Persona"
    painPoints: Optional[List[str]] = None
    pain_points: Optional[List[str]] = None
    valueProp: Optional[str] = None
    value_prop: Optional[str] = ""
    targetTitles: Optional[List[str]] = None
    target_titles: Optional[List[str]] = []
    toneTweaks: Optional[str] = None
    tone_tweaks: Optional[str] = ""

    class Config:
        extra = "allow"
    

class TestDriveRequest(BaseModel):
    message: Optional[str] = None
    objection: Optional[str] = None

# --- Docs API ---
@router.post("/test-drive")
@router.post("/test-objection")
async def test_drive_ai(
    payload: TestDriveRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Simulates how the AI will respond to a specific prospect message or objection
    using the current Knowledge Base, Personas, and Objections.
    """
    input_text = (payload.message or payload.objection or "").strip()
    if not input_text:
        return {
            "response": "Please provide a prospect message or objection to test.",
            "reply": "Please provide a prospect message or objection to test."
        }

    from knowledge.backend.services.elein_ai_service import generate_test_drive_response
    
    response_text = await generate_test_drive_response(
        supabase, workspace_id, message=input_text
    )
    # Return both keys for full backward and forward compatibility with all UI components
    return {
        "response": response_text,
        "reply": response_text
    }

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
    # Paranoia Layer 1: Enforce Tier Buyer Persona Limits
    ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).execute()
    ws_tier = ws_res.data[0].get("tier", "FREE") if ws_res.data else "FREE"
    from core.backend.services.credit_service import TIER_LIMITS
    limits = TIER_LIMITS.get(ws_tier, TIER_LIMITS["FREE"])
    max_personas = limits.get("max_personas", 1)
    
    current_count = supabase.table("personas").select("id", count="exact").eq("workspace_id", workspace_id).execute().count or 0
    if current_count >= max_personas:
        raise HTTPException(
            status_code=403,
            detail=f"Persona limit reached: {ws_tier.capitalize()} Tier allows up to {max_personas} buyer persona{'s' if max_personas != 1 else ''}. Upgrade to Growth Pro to define up to 10 personas."
        )

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

