from core.backend.api.auth_dep import get_service_client

def enqueue_job(supabase, job_type: str, workspace_id: str, asset_id: str, payload: dict) -> dict:
    """
    Inserts a new job into the processing_jobs table using service_role to bypass RLS.
    Returns the created job record.
    """
    service_client = get_service_client()
    job_data = {
        "workspace_id": workspace_id,
        "asset_id": asset_id,
        "job_type": job_type,
        "status": "pending",
        "payload": payload
    }
    
    response = service_client.table("processing_jobs").insert(job_data).execute()
    return response.data[0] if response.data else None
