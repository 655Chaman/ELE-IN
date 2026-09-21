import hmac
import hashlib
import json
import time
from typing import Dict, Any

def generate_webhook_signature(payload: Dict[str, Any], secret: str, timestamp_override: int = None) -> tuple[str, str]:
    """
    Generates an HMAC-SHA256 signature for a webhook payload.
    Returns (timestamp, signature).
    
    The customer is expected to compute HMAC-SHA256(timestamp + "." + json_body, secret)
    and compare it to the signature in the header.
    """
    timestamp = str(timestamp_override or int(time.time()))
    
    # Serialize JSON with no spaces for consistency
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    signed_payload = f"{timestamp}.{payload_str}"
    
    mac = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    )
    
    signature = mac.hexdigest()
    return timestamp, signature

