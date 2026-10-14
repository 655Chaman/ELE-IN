import json
import os
import uuid
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from slowapi import Limiter
from slowapi.util import get_remote_address
from core.backend.api.auth_dep import get_service_client, get_current_user_id, require_superadmin

router = APIRouter(prefix="", tags=["settings"])
limiter = Limiter(key_func=get_remote_address)


# -------- Admin API Key Pool --------



@router.get("/admin/api-keys", response_model=List[Dict[str, Any]])
def get_ai_keys(_auth=Depends(require_superadmin)):
    supabase = get_service_client()
    try:
        res = supabase.table("system_api_keys").select("*").order("created_at").execute()
    except Exception:
        return [{"configured": False, "message": "system_api_keys table not found. Run the pending migration to configure the LLM key pool."}]
    
    # Mask keys before sending to frontend
    keys = []
    for r in res.data:
        k = r["api_key"]
        masked = f"{k[:7]}...{k[-4:]}" if len(k) > 10 else "****"
        keys.append({
            "id": r["id"],
            "provider": r["provider"],
            "api_key": masked,
            "status": r["status"],
            "error_count": r["error_count"],
            "last_used_at": r["last_used_at"]
        })
    return keys

class APIKeyCreate(BaseModel):
    api_key: str
    provider: str = "auto" # default auto-detect

@router.post("/admin/api-keys")
def add_ai_key(payload: APIKeyCreate, _auth=Depends(require_superadmin)):
    # Paranoia Layer 1 & 2: Clean key input (strip quotes, Bearer prefix, whitespace)
    key = payload.api_key.strip().strip("'\"")
    if key.lower().startswith("bearer "):
        key = key[7:].strip().strip("'\"")
        
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    provider = payload.provider
    
    if provider == "auto":
        if key.startswith("nvapi-"):
            provider = "nvidia"
        elif key.startswith("sk-ant-"):
            provider = "anthropic"
        elif key.startswith("sk-proj-") or key.startswith("sk-"):
            provider = "openai"
        elif key.startswith("ollama") or key.startswith("lmstudio"):
            provider = "local"
        else:
            raise HTTPException(status_code=400, detail="Could not auto-detect provider. Must start with nvapi-, sk-, or sk-ant-")
            
    supabase = get_service_client()
    
    try:
        # Prevent exact duplicates
        existing = supabase.table("system_api_keys").select("id").eq("api_key", key).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Key already exists in the pool.")
            
        res = supabase.table("system_api_keys").insert({
            "provider": provider,
            "api_key": key,
            "status": "active"
        }).execute()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="system_api_keys table not found. Run the pending migration before adding keys.")
    
    # Force module-level cache invalidation in AI service
    try:
        import knowledge.backend.services.elein_ai_service as ai_svc
        ai_svc._last_fetch_time = 0
    except Exception:
        pass
        
    return res.data[0]

@router.delete("/admin/api-keys/{key_id}")
def delete_ai_key(key_id: str, _auth=Depends(require_superadmin)):
    supabase = get_service_client()
    try:
        supabase.table("system_api_keys").delete().eq("id", key_id).execute()
    except Exception:
        raise HTTPException(status_code=503, detail="system_api_keys table not found. Run the pending migration.")
    
    try:
        import knowledge.backend.services.elein_ai_service as ai_svc
        ai_svc._last_fetch_time = 0
    except Exception:
        pass
        
    return {"status": "success"}

@router.put("/admin/api-keys/{key_id}/reset")
def reset_ai_key(key_id: str, _auth=Depends(require_superadmin)):
    supabase = get_service_client()
    try:
        supabase.table("system_api_keys").update({
            "status": "active",
            "error_count": 0
        }).eq("id", key_id).execute()
    except Exception:
        raise HTTPException(status_code=503, detail="system_api_keys table not found. Run the pending migration.")
    
    try:
        import knowledge.backend.services.elein_ai_service as ai_svc
        ai_svc._last_fetch_time = 0
    except Exception:
        pass
        
    return {"status": "success"}

# -------- Legacy Settings --------

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app_settings.json")

class APISettings(BaseModel):
    api_key_apify: str = ""
    api_key_mailsso: str = ""
    api_key_openai: str = ""
    llm_provider: str = "openai"
    api_key_llm: str = ""
    llm_model: str = ""

def _load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

@router.get("/")
@limiter.limit("100/minute")
async def get_settings(request: Request, _auth: str = Depends(require_superadmin)):
    settings = _load_settings()
    masked_settings = {}
    for key, value in settings.items():
        if value:
            masked_settings[key] = f"****{value[-4:]}" if len(value) > 4 else "****"
        else:
            masked_settings[key] = ""
    return masked_settings

@router.post("/")
@limiter.limit("100/minute")
async def save_settings(request: Request, payload: APISettings, _auth: str = Depends(require_superadmin)):
    settings = _load_settings()
    update_data = payload.dict()
    for key, value in update_data.items():
        if value and not value.startswith("****"):
            settings[key] = value
            
    _save_settings(settings)
    return {"success": True, "message": "Settings saved successfully"}
