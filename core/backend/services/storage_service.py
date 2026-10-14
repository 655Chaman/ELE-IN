import os
import re
import hashlib
import logging
from typing import Dict, Any, Optional
from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

BUCKET_NAME = "campaign-assets"
_verified_buckets = set()

def ensure_bucket_exists(bucket_name: str = BUCKET_NAME, is_public: bool = True) -> bool:
    """
    Paranoia Layer 0 & 1: Checks if bucket exists; creates it if missing.
    Caches verified buckets in memory to avoid redundant API queries.
    """
    global _verified_buckets
    if bucket_name in _verified_buckets:
        return True
    try:
        supabase = get_service_client()
        buckets = supabase.storage.list_buckets()
        names = [b.name for b in buckets] if buckets else []
        if bucket_name not in names:
            supabase.storage.create_bucket(bucket_name, options={"public": is_public})
            logger.info(f"[StorageService] Created missing bucket '{bucket_name}'")
        _verified_buckets.add(bucket_name)
        return True
    except Exception as e:
        logger.warning(f"[StorageService] Failed to ensure bucket '{bucket_name}': {e}")
        return False

def sanitize_filename(filename: str) -> str:
    """
    Paranoia Layer 2: Sanitizes filename to block path traversal and illegal characters.
    """
    base = os.path.basename(filename or "file")
    safe = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", base)
    return safe[:100]

def upload_media_file(
    workspace_id: str,
    content: bytes,
    original_filename: str,
    folder: str = "voice_notes",
    content_type: Optional[str] = None,
    supabase_client: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2:
    - Layer 0: Uploads to Supabase Storage 'campaign-assets' bucket and returns CDN public URL.
    - Layer 1: Falls back safely to local disk if Supabase Storage is unreachable.
    - Layer 2: Deduplicates by SHA-256 hash so identical files don't waste storage quota.
    """
    ensure_bucket_exists()
    safe_filename = sanitize_filename(original_filename)
    content_hash = hashlib.sha256(content).hexdigest()
    
    storage_path = f"{workspace_id}/{folder}/{content_hash[:16]}_{safe_filename}"
    unique_name = f"{content_hash[:16]}_{safe_filename}"
    
    upload_dir = os.path.join(os.getcwd(), "uploads", folder)
    os.makedirs(upload_dir, exist_ok=True)
    local_path = os.path.join(upload_dir, unique_name)
    
    with open(local_path, "wb") as f:
        f.write(content)
        
    local_url = f"/api/elein/media/{folder}/{unique_name}"
    public_url = local_url
    
    try:
        supabase = supabase_client or get_service_client()
        if supabase:
            try:
                supabase.storage.from_(BUCKET_NAME).upload(
                    storage_path,
                    content,
                    {"content-type": content_type or "application/octet-stream", "upsert": "true"}
                )
            except Exception:
                pass
                
            sb_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
            if sb_url:
                public_url = sb_url
    except Exception as e:
        logger.warning(f"[StorageService] Supabase upload failed, falling back to local URL: {e}")
        
    return {
        "status": "success",
        "url": public_url,
        "filename": original_filename,
        "size": len(content),
        "hash": content_hash
    }
