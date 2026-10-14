import uuid
import logging
from typing import Optional
from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

def enqueue_job(
    supabase=None,
    job_type: str = "general",
    workspace_id: str = None,
    asset_id: Optional[str] = None,
    payload: Optional[dict] = None,
    priority: int = 0,
    idempotency_key: Optional[str] = None
) -> Optional[dict]:
    """
    Inserts a new job into the processing_jobs table using service_role to bypass RLS.
    Returns the created job record or None on failure.
    """
    service_client = supabase if supabase is not None else get_service_client()
    job_data = {
        "workspace_id": workspace_id,
        "asset_id": asset_id,
        "job_type": job_type,
        "status": "pending",
        "payload": payload or {},
        "idempotency_key": idempotency_key or str(uuid.uuid4())
    }
    
    try:
        response = service_client.table("processing_jobs").upsert(
            job_data,
            ignore_duplicates=True,
            on_conflict="idempotency_key"
        ).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Failed to enqueue job {job_type} for workspace {workspace_id}: {e}")
        return None
