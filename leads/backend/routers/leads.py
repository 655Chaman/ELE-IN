from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client, AsyncClient
from typing import List, Optional
from core.backend.api.auth_dep import get_supabase_client, get_async_supabase_client
import uuid

router = APIRouter()

@router.get("/lists/{list_id}/leads", response_model=List[dict])
async def get_leads_in_list(list_id: str, supabase: AsyncClient = Depends(get_async_supabase_client)):
    try:
        # Avoid N+1: Use inner join over list_members to fetch leads directly in 1 query
        leads_res = await supabase.table("leads") \
            .select("*, list_members!inner(list_id)") \
            .eq("list_members.list_id", list_id) \
            .execute()
        return leads_res.data
    except Exception as e:
        import logging
        logging.error(f"Error in leads router: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred.")

@router.delete("/lists/{list_id}/leads/{lead_id}", response_model=dict)
async def remove_lead_from_list(list_id: str, lead_id: str, supabase: AsyncClient = Depends(get_async_supabase_client)):
    try:
        # Remove the mapping (trigger list_members_sync_count will automatically update lead_lists.row_count)
        await supabase.table("list_members").delete().eq("list_id", list_id).eq("opportunity_id", lead_id).execute()
            
        return {"success": True}
    except Exception as e:
        import logging
        logging.error(f"Error in leads router: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred.")
