import secrets
import hashlib
import string
from supabase import Client

def generate_api_key() -> tuple[str, str, str]:
    """
    Generates a secure API key following Stripe's pattern.
    Returns (raw_secret_key, key_prefix, key_hash)
    """
    # 32 bytes of secure randomness, base62 encoded for readability
    alphabet = string.ascii_letters + string.digits
    secret_bytes = secrets.token_bytes(32)
    # Just a simple hex representation is fine, but let's do a clean alphanumeric string
    random_str = ''.join(secrets.choice(alphabet) for _ in range(40))
    
    raw_key = f"el_live_{random_str}"
    key_prefix = raw_key[:12] # e.g. el_live_aBcDe
    key_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
    
    return raw_key, key_prefix, key_hash

def issue_api_key(supabase: Client, workspace_id: str, name: str, scopes: list[str]) -> dict:
    raw_key, prefix, key_hash = generate_api_key()
    
    res = supabase.table("api_keys").insert({
        "workspace_id": workspace_id,
        "name": name,
        "key_prefix": prefix,
        "key_hash": key_hash,
        "scopes": scopes,
        "is_active": True
    }).execute()
    
    result = res.data[0]
    
    # Write to audit log
    supabase.table("api_key_audit_logs").insert({
        "workspace_id": workspace_id,
        "api_key_id": result["id"],
        "actor": "system", # In a real implementation this would be the current user's email/ID
        "action": "created"
    }).execute()
    
    # Return the raw key ONCE. It is never stored.
    result["secret_key"] = raw_key
    return result
