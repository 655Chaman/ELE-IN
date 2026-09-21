import time
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any
from supabase import create_client

from core.backend.core.crypto import decrypt_bytes
from integrations.backend.services.webhook_service import generate_webhook_signature

# Setup Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def process_delivery(delivery: Dict[str, Any], endpoint: Dict[str, Any]):
    """Processes a single webhook delivery (Synchronous)"""
    delivery_id = delivery["id"]
    attempt_count = delivery.get("attempt_count", 0) + 1
    url = endpoint["url"]
    
    # Decrypt signing secret
    try:
        raw_secret = decrypt_bytes(bytes.fromhex(endpoint["signing_secret"])).decode('utf-8')
    except Exception as e:
        supabase.table("webhook_deliveries").update({
            "delivery_status": "failed",
            "attempt_count": attempt_count,
            "response_body": f"Failed to decrypt signing secret: {str(e)}"
        }).eq("id", delivery_id).execute()
        return

    timestamp, signature = generate_webhook_signature(delivery["payload"], raw_secret)
    
    headers = {
        "Content-Type": "application/json",
        "EleIn-Signature": signature,
        "EleIn-Timestamp": timestamp,
        "EleIn-Event": delivery["event_type"]
    }
    
    status_code = None
    response_body = ""
    success = False
    
    try:
        resp = requests.post(url, json=delivery["payload"], headers=headers, timeout=10.0)
        status_code = resp.status_code
        response_body = resp.text[:1000]
        success = 200 <= status_code < 300
    except Exception as e:
        response_body = f"Network error: {str(e)}"
        
    if success:
        supabase.table("webhook_deliveries").update({
            "delivery_status": "success",
            "status_code": status_code,
            "response_body": response_body,
            "attempt_count": attempt_count
        }).eq("id", delivery_id).execute()
    else:
        if attempt_count >= 5:
            supabase.table("webhook_deliveries").update({
                "delivery_status": "failed",
                "status_code": status_code,
                "response_body": response_body,
                "attempt_count": attempt_count
            }).eq("id", delivery_id).execute()
        else:
            delay_minutes = 2 ** attempt_count
            next_retry_at = (datetime.utcnow() + timedelta(minutes=delay_minutes)).isoformat()
            supabase.table("webhook_deliveries").update({
                "delivery_status": "pending",
                "status_code": status_code,
                "response_body": response_body,
                "attempt_count": attempt_count,
                "next_retry_at": next_retry_at
            }).eq("id", delivery_id).execute()

def poll_webhooks():
    print("Starting Webhook Dispatch Worker (Sync)...")
    
    while True:
        try:
            now_iso = datetime.utcnow().isoformat()
            filter_str = f"next_retry_at.lte.{now_iso},next_retry_at.is.null"
            
            res = supabase.table("webhook_deliveries") \
                .select("*") \
                .eq("delivery_status", "pending") \
                .or_(filter_str) \
                .order("created_at") \
                .limit(50) \
                .execute()
                
            deliveries = res.data
            
            if deliveries:
                endpoint_ids = list(set([d["endpoint_id"] for d in deliveries]))
                endpoints_res = supabase.table("webhook_endpoints") \
                    .select("*") \
                    .in_("id", endpoint_ids) \
                    .execute()
                
                endpoints_map = {e["id"]: e for e in endpoints_res.data}
                
                for delivery in deliveries:
                    endpoint = endpoints_map.get(delivery["endpoint_id"])
                    if endpoint and endpoint.get("is_active"):
                        process_delivery(delivery, endpoint)
                    else:
                        supabase.table("webhook_deliveries").update({
                            "delivery_status": "failed",
                            "response_body": "Endpoint inactive or deleted"
                        }).eq("id", delivery["id"]).execute()
                        
        except Exception as e:
            print(f"Error in webhook polling loop: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    poll_webhooks()
