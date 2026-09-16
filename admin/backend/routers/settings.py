import json
import os
import uuid
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from slowapi import Limiter
from slowapi.util import get_remote_address
from core.backend.api.auth_dep import get_service_client, get_current_user_id

router = APIRouter(prefix="", tags=["settings"])
limiter = Limiter(key_func=get_remote_address)

def require_superadmin(current_user_id: str = Depends(get_current_user_id)):
    supabase = get_service_client()
    res = supabase.table("admin_grants").select("id").eq("user_id", current_user_id).is_("revoked_at", "null").execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user_id

# -------- Admin API Key Pool --------

class NvidiaKeyCreate(BaseModel):
    api_key: str

@router.get("/admin/api-keys", response_model=List[Dict[str, Any]])
def get_nvidia_keys(_auth=Depends(require_superadmin)):
    supabase = get_service_client()
    res = supabase.table("system_api_keys").select("*").order("created_at").execute()
    
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

@router.post("/admin/api-keys")
def add_nvidia_key(payload: NvidiaKeyCreate, _auth=Depends(require_superadmin)):
    if not payload.api_key.startswith("nvapi-"):
        raise HTTPException(status_code=400, detail="Invalid NVIDIA API key format.")
        
    supabase = get_service_client()
    
    # Prevent exact duplicates
    existing = supabase.table("system_api_keys").select("id").eq("api_key", payload.api_key).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Key already exists in the pool.")
        
    res = supabase.table("system_api_keys").insert({
        "provider": "nvidia",
        "api_key": payload.api_key,
        "status": "active"
    }).execute()
    
    # force cache invalidation in ai service
    try:
        from knowledge.backend.services.elein_ai_service import _last_fetch_time
        _last_fetch_time = 0
    except:
        pass
        
    return res.data[0]

@router.delete("/admin/api-keys/{key_id}")
def delete_nvidia_key(key_id: str, _auth=Depends(require_superadmin)):
    supabase = get_service_client()
    supabase.table("system_api_keys").delete().eq("id", key_id).execute()
    
    try:
        from knowledge.backend.services.elein_ai_service import _last_fetch_time
        _last_fetch_time = 0
    except:
        pass
        
    return {"status": "success"}

@router.put("/admin/api-keys/{key_id}/reset")
def reset_nvidia_key(key_id: str, _auth=Depends(require_superadmin)):
    supabase = get_service_client()
    supabase.table("system_api_keys").update({
        "status": "active",
        "error_count": 0
    }).eq("id", key_id).execute()
    
    try:
        from knowledge.backend.services.elein_ai_service import _last_fetch_time
        _last_fetch_time = 0
    except:
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
async def get_settings(request: Request):
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
async def save_settings(request: Request, payload: APISettings):
    settings = _load_settings()
    update_data = payload.dict()
    for key, value in update_data.items():
        if value and not value.startswith("****"):
            settings[key] = value
            
    _save_settings(settings)
    return {"success": True, "message": "Settings saved successfully"}
