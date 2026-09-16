import logging
from typing import List, Dict, Optional
from supabase import Client

logger = logging.getLogger(__name__)

class PersonaService:
    # --- Personas ---
    @staticmethod
    def get_personas(supabase: Client, workspace_id: str) -> List[Dict]:
        res = supabase.table("personas").select("*").eq("workspace_id", workspace_id).order("created_at", desc=False).execute()
        return res.data

    @staticmethod
    def create_persona(supabase: Client, workspace_id: str, data: dict) -> dict:
        new_persona = {
            "workspace_id": workspace_id,
            "title": data.get("title", "New Persona"),
            "pain_points": data.get("painPoints", []),
            "value_prop": data.get("value_prop", ""),
            "target_titles": data.get("target_titles", []),
            "tone_tweaks": data.get("tone_tweaks", "")
        }
        res = supabase.table("personas").insert(new_persona).execute()
        if not res.data:
            raise Exception("Failed to create persona")
        
        # Ensure we return painPoints as camelCase to match the frontend expectation if needed,
        # but the db is pain_points. SWR expects pain_points or painPoints?
        # Let's map it.
        created = res.data[0]
        created["painPoints"] = created.get("pain_points", [])
        return created

    @staticmethod
    def update_persona(supabase: Client, workspace_id: str, persona_id: str, data: dict) -> Optional[dict]:
        updates = {}
        if "title" in data:
            updates["title"] = data["title"]
        if "painPoints" in data:
            updates["pain_points"] = data["painPoints"]
            
        if not updates:
            return None
            
        res = supabase.table("personas").update(updates).eq("id", persona_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            return None
        updated = res.data[0]
        updated["painPoints"] = updated.get("pain_points", [])
        return updated

    @staticmethod
    def delete_persona(supabase: Client, workspace_id: str, persona_id: str) -> bool:
        res = supabase.table("personas").delete().eq("id", persona_id).eq("workspace_id", workspace_id).execute()
        return len(res.data) > 0

    # --- Objections ---
    @staticmethod
    def get_objections(supabase: Client, workspace_id: str) -> List[Dict]:
        res = supabase.table("objections").select("*").eq("workspace_id", workspace_id).order("created_at", desc=False).execute()
        return res.data

    @staticmethod
    def create_objection(supabase: Client, workspace_id: str, data: dict) -> dict:
        new_objection = {
            "workspace_id": workspace_id,
            "trigger": data.get("trigger", "New Objection"),
            "playbook": data.get("playbook", "")
        }
        res = supabase.table("objections").insert(new_objection).execute()
        if not res.data:
            raise Exception("Failed to create objection")
        return res.data[0]

    @staticmethod
    def update_objection(supabase: Client, workspace_id: str, objection_id: str, data: dict) -> Optional[dict]:
        updates = {}
        if "trigger" in data:
            updates["trigger"] = data["trigger"]
        if "playbook" in data:
            updates["playbook"] = data["playbook"]
            
        if not updates:
            return None

        res = supabase.table("objections").update(updates).eq("id", objection_id).eq("workspace_id", workspace_id).execute()
        if not res.data:
            return None
        return res.data[0]

    @staticmethod
    def delete_objection(supabase: Client, workspace_id: str, objection_id: str) -> bool:
        res = supabase.table("objections").delete().eq("id", objection_id).eq("workspace_id", workspace_id).execute()
        return len(res.data) > 0

