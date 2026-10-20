import logging
from typing import List, Dict, Optional, Any
from supabase import Client

logger = logging.getLogger(__name__)

class PersonaService:
    # ──────────────────────────────────────────────────────────────────────────
    # Internal Helpers (Normalization & Paranoia Guards)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_string_list(val: Any) -> List[str]:
        """Layer 2 Paranoia: Safely normalizes list or string inputs into a clean list of strings."""
        if not val:
            return []
        if isinstance(val, str):
            # Split comma or newline delimited strings
            items = [item.strip() for line in val.split("\n") for item in line.split(",") if item.strip()]
            return items
        if isinstance(val, (list, tuple)):
            clean = []
            for item in val:
                if item and isinstance(item, str):
                    s = item.strip()
                    if s and s not in clean:
                        clean.append(s)
                elif item:
                    s = str(item).strip()
                    if s and s not in clean:
                        clean.append(s)
            return clean
        return []

    @staticmethod
    def _format_persona_output(row: Dict[str, Any]) -> Dict[str, Any]:
        """Provides dual snake_case and camelCase output so all frontends work without translation errors."""
        res = dict(row)
        res["painPoints"] = res.get("pain_points") or []
        res["targetTitles"] = res.get("target_titles") or []
        res["valueProp"] = res.get("value_prop") or ""
        res["toneTweaks"] = res.get("tone_tweaks") or ""
        return res

    @staticmethod
    def _invalidate_brain_cache(workspace_id: str):
        try:
            from campaigns.backend.services.elein_executor import invalidate_brain_cache
            invalidate_brain_cache(workspace_id)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # Personas
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_personas(supabase: Client, workspace_id: str) -> List[Dict]:
        try:
            res = supabase.table("personas").select("*").eq("workspace_id", workspace_id).order("created_at", desc=False).execute()
            rows = res.data or []
            return [PersonaService._format_persona_output(r) for r in rows]
        except Exception as e:
            logger.error(f"[PersonaService] Error fetching personas: {e}")
            return []

    @staticmethod
    def create_persona(supabase: Client, workspace_id: str, data: dict) -> dict:
        title = (data.get("title") or "New Persona").strip()[:255] or "New Persona"
        pain_points = PersonaService._normalize_string_list(data.get("painPoints") if "painPoints" in data else data.get("pain_points"))
        value_prop = (data.get("valueProp") if "valueProp" in data else data.get("value_prop") or "").strip()[:5000]
        target_titles = PersonaService._normalize_string_list(data.get("targetTitles") if "targetTitles" in data else data.get("target_titles"))
        tone_tweaks = (data.get("toneTweaks") if "toneTweaks" in data else data.get("tone_tweaks") or "").strip()[:5000]

        full_payload = {
            "workspace_id": workspace_id,
            "title": title,
            "pain_points": pain_points,
            "value_prop": value_prop,
            "target_titles": target_titles,
            "tone_tweaks": tone_tweaks
        }

        # Layer 1 Paranoia: Handle un-migrated databases gracefully if new columns are missing
        try:
            res = supabase.table("personas").insert(full_payload).execute()
        except Exception as e:
            err_msg = str(e).lower()
            if "column" in err_msg and ("does not exist" in err_msg or "pgrst204" in err_msg or "42703" in err_msg):
                logger.warning(f"[PersonaService] Missing extended persona columns in DB, falling back to base columns: {e}")
                base_payload = {
                    "workspace_id": workspace_id,
                    "title": title,
                    "pain_points": pain_points
                }
                res = supabase.table("personas").insert(base_payload).execute()
            else:
                raise

        if not res.data:
            raise Exception("Failed to create persona")

        created = res.data[0]
        PersonaService._invalidate_brain_cache(workspace_id)
        return PersonaService._format_persona_output(created)

    @staticmethod
    def update_persona(supabase: Client, workspace_id: str, persona_id: str, data: dict) -> Optional[dict]:
        updates = {}
        if "title" in data:
            updates["title"] = (data["title"] or "Untitled Persona").strip()[:255] or "Untitled Persona"
        if "painPoints" in data or "pain_points" in data:
            updates["pain_points"] = PersonaService._normalize_string_list(data.get("painPoints") if "painPoints" in data else data.get("pain_points"))
        if "valueProp" in data or "value_prop" in data:
            updates["value_prop"] = (data.get("valueProp") if "valueProp" in data else data.get("value_prop") or "").strip()[:5000]
        if "targetTitles" in data or "target_titles" in data:
            updates["target_titles"] = PersonaService._normalize_string_list(data.get("targetTitles") if "targetTitles" in data else data.get("target_titles"))
        if "toneTweaks" in data or "tone_tweaks" in data:
            updates["tone_tweaks"] = (data.get("toneTweaks") if "toneTweaks" in data else data.get("tone_tweaks") or "").strip()[:5000]

        if not updates:
            # If no updates were supplied, return existing record
            existing = supabase.table("personas").select("*").eq("id", persona_id).eq("workspace_id", workspace_id).maybe_single().execute()
            return PersonaService._format_persona_output(existing.data) if existing and existing.data else None

        # Layer 1 Paranoia: Handle un-migrated DB gracefully on update
        try:
            res = supabase.table("personas").update(updates).eq("id", persona_id).eq("workspace_id", workspace_id).execute()
        except Exception as e:
            err_msg = str(e).lower()
            if "column" in err_msg and ("does not exist" in err_msg or "pgrst204" in err_msg or "42703" in err_msg):
                logger.warning(f"[PersonaService] Missing extended persona columns on update, stripping them: {e}")
                fallback_updates = {k: v for k, v in updates.items() if k in ["title", "pain_points"]}
                if fallback_updates:
                    res = supabase.table("personas").update(fallback_updates).eq("id", persona_id).eq("workspace_id", workspace_id).execute()
                else:
                    existing = supabase.table("personas").select("*").eq("id", persona_id).eq("workspace_id", workspace_id).maybe_single().execute()
                    return PersonaService._format_persona_output(existing.data) if existing and existing.data else None
            else:
                raise

        if not res.data:
            return None
        updated = res.data[0]
        PersonaService._invalidate_brain_cache(workspace_id)
        return PersonaService._format_persona_output(updated)

    @staticmethod
    def delete_persona(supabase: Client, workspace_id: str, persona_id: str) -> bool:
        try:
            res = supabase.table("personas").delete().eq("id", persona_id).eq("workspace_id", workspace_id).execute()
            deleted = bool(res and res.data and len(res.data) > 0)
            if deleted:
                PersonaService._invalidate_brain_cache(workspace_id)
            return deleted
        except Exception as e:
            logger.error(f"[PersonaService] Error deleting persona {persona_id}: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Objections (Dual-Table Resiliency & Auto-Sync)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_primary_objection_table(supabase: Client, workspace_id: str) -> str:
        """Determines whether knowledge_objections or objections is active in this environment."""
        try:
            # Try knowledge_objections first
            supabase.table("knowledge_objections").select("id").limit(1).execute()
            return "knowledge_objections"
        except Exception:
            return "objections"

    @staticmethod
    def get_objections(supabase: Client, workspace_id: str) -> List[Dict]:
        """
        Layer 0 & 1 Paranoia (Flaw 4): Fetches objections across both knowledge_objections and legacy objections tables.
        Merges results seamlessly, deduplicating by ID and normalized trigger to prevent data blindness
        when migrating or having historical rows in both tables.
        """
        combined = []
        seen_ids = set()
        seen_triggers = set()

        # 1. Query modern table first (canonical precedence)
        try:
            res_modern = supabase.table("knowledge_objections").select("*").eq("workspace_id", workspace_id).order("created_at", desc=False).execute()
            for row in (res_modern.data or []):
                rid = str(row.get("id") or "")
                trig = str(row.get("trigger") or row.get("name") or "").strip().lower()
                if rid:
                    seen_ids.add(rid)
                if trig:
                    seen_triggers.add(trig)
                combined.append(row)
        except Exception as e:
            logger.debug(f"[PersonaService] knowledge_objections query failed (schema/table might be pending): {e}")

        # 2. Query legacy objections table and merge non-duplicate historical rows
        try:
            res_legacy = supabase.table("objections").select("*").eq("workspace_id", workspace_id).order("created_at", desc=False).execute()
            for row in (res_legacy.data or []):
                rid = str(row.get("id") or "")
                trig = str(row.get("trigger") or row.get("name") or "").strip().lower()
                # Skip if already present from canonical knowledge_objections
                if rid and rid in seen_ids:
                    continue
                if trig and trig in seen_triggers:
                    continue
                if rid:
                    seen_ids.add(rid)
                if trig:
                    seen_triggers.add(trig)
                combined.append(row)
        except Exception as e:
            logger.debug(f"[PersonaService] legacy objections query failed (table might be absent): {e}")

        return combined

    @staticmethod
    def create_objection(supabase: Client, workspace_id: str, data: dict) -> dict:
        trigger = (data.get("trigger") or "General Objection").strip()[:500] or "General Objection"
        playbook = (data.get("playbook") or "").strip()[:5000]

        # Layer 2 Paranoia: Check for duplicate trigger in same workspace
        for tbl in ["knowledge_objections", "objections"]:
            try:
                existing = supabase.table(tbl).select("*").eq("workspace_id", workspace_id).eq("trigger", trigger).maybe_single().execute()
                if existing and existing.data:
                    # Layer 1 & 2 Paranoia (Flaw 17): Update existing objection instead of creating duplicate
                    # and immediately invalidate brain cache so in-memory nodes don't serve stale playbooks.
                    upd = supabase.table(tbl).update({"playbook": playbook}).eq("id", existing.data["id"]).eq("workspace_id", workspace_id).execute()
                    PersonaService._invalidate_brain_cache(workspace_id)
                    return upd.data[0] if upd.data else existing.data
            except Exception:
                pass

        primary_table = PersonaService._get_primary_objection_table(supabase, workspace_id)
        new_objection = {
            "workspace_id": workspace_id,
            "trigger": trigger,
            "playbook": playbook
        }

        try:
            res = supabase.table(primary_table).insert(new_objection).execute()
            created = res.data[0]
        except Exception as e:
            # Fallback to secondary table
            sec_table = "objections" if primary_table == "knowledge_objections" else "knowledge_objections"
            try:
                res = supabase.table(sec_table).insert(new_objection).execute()
                created = res.data[0]
            except Exception:
                raise e

        # Layer 1 Paranoia: Best-effort dual-write sync
        alt_table = "objections" if primary_table == "knowledge_objections" else "knowledge_objections"
        try:
            sync_payload = dict(new_objection)
            if "id" in created:
                sync_payload["id"] = created["id"]
            supabase.table(alt_table).insert(sync_payload).execute()
        except Exception:
            pass

        PersonaService._invalidate_brain_cache(workspace_id)
        return created

    @staticmethod
    def update_objection(supabase: Client, workspace_id: str, objection_id: str, data: dict) -> Optional[dict]:
        updates = {}
        if "trigger" in data:
            updates["trigger"] = (data["trigger"] or "").strip()[:500]
        if "playbook" in data:
            updates["playbook"] = (data["playbook"] or "").strip()[:5000]

        if not updates:
            return None

        updated_row = None
        # Try both tables to ensure whatever table contains the ID gets updated
        for tbl in ["knowledge_objections", "objections"]:
            try:
                res = supabase.table(tbl).update(updates).eq("id", objection_id).eq("workspace_id", workspace_id).execute()
                if res.data and not updated_row:
                    updated_row = res.data[0]
            except Exception:
                pass

        if updated_row:
            PersonaService._invalidate_brain_cache(workspace_id)
        return updated_row

    @staticmethod
    def delete_objection(supabase: Client, workspace_id: str, objection_id: str) -> bool:
        deleted = False
        for tbl in ["knowledge_objections", "objections"]:
            try:
                res = supabase.table(tbl).delete().eq("id", objection_id).eq("workspace_id", workspace_id).execute()
                if res.data and len(res.data) > 0:
                    deleted = True
            except Exception:
                pass
        if deleted:
            PersonaService._invalidate_brain_cache(workspace_id)
        return deleted
