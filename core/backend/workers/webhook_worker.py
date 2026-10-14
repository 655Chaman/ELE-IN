import time
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
from supabase import create_client

from core.backend.core.crypto import decrypt_bytes
from integrations.backend.services.webhook_service import generate_webhook_signature

# Safe Supabase client retrieval (Layer 1 Paranoia)
def _get_supabase():
    try:
        from core.backend.api.auth_dep import get_service_client
        return get_service_client()
    except Exception:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if url and key:
            return create_client(url, key)
        return None

def process_delivery(delivery: Dict[str, Any], endpoint: Dict[str, Any], client: Any = None) -> Dict[str, Any]:
    """Processes a single webhook delivery using the hardened dispatcher service (Paranoia Layer 0, 1 & 2)."""
    sb = client or _get_supabase()
    if not sb:
        return {"status": "error", "message": "Supabase client unavailable"}
    from integrations.backend.services.webhook_service import dispatch_webhook_delivery
    return dispatch_webhook_delivery(delivery=delivery, endpoint=endpoint, supabase=sb)

def poll_webhooks():
    print("Starting Webhook Dispatch Worker (Sync with DLQ & Circuit Breaker)...")
    from integrations.backend.services.webhook_service import dispatch_pending_webhooks
    
    while True:
        try:
            sb = _get_supabase()
            if not sb:
                time.sleep(5)
                continue

            result = dispatch_pending_webhooks(batch_size=50, supabase=sb)
            if result.get("processed", 0) > 0:
                print(f"[Webhook Worker] Batch processed: {result}")
        except Exception as e:
            print(f"Error in webhook polling loop: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    poll_webhooks()
