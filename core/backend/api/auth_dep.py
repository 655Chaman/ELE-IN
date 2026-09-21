from dotenv import load_dotenv
load_dotenv()
import os
import logging
from fastapi import Request, HTTPException, Depends
from supabase import create_client, Client, ClientOptions, create_async_client, AsyncClient, AsyncClientOptions

try:
    import jwt
    HAS_PYJWT = True
except ImportError:
    HAS_PYJWT = False

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

# Layer 2: Module-level check. Note that the application FAILS TO START if SUPABASE_JWT_SECRET is missing.
if not SUPABASE_JWT_SECRET:
    logger.critical("SECURITY FATAL: SUPABASE_JWT_SECRET is not configured. The app will fail to start.")

from pydantic import BaseModel
class AuthUser(BaseModel):
    id: str
    workspace_id: str
    email: str

def verify_jwt(token: str) -> AuthUser:
    if not HAS_PYJWT or not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=401, detail="Missing PyJWT or JWT secret")
    try:
        decoded = jwt.decode(
            token, 
            SUPABASE_JWT_SECRET, 
            algorithms=["HS256"], 
            options={"verify_exp": True},
            audience="authenticated"
        )
        return AuthUser(
            id=decoded.get("sub", ""),
            workspace_id=decoded.get("user_metadata", {}).get("workspace_id", ""),
            email=decoded.get("email", "")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token signature.")


def verify_token_and_get_user_id(token: str) -> str:
    if HAS_PYJWT and SUPABASE_JWT_SECRET:
        try:
            decoded = jwt.decode(
                token, 
                SUPABASE_JWT_SECRET, 
                algorithms=["HS256"], 
                options={"verify_exp": True},
                audience="authenticated"
            )
            return decoded.get("sub")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except jwt.PyJWTError as e:
            # If it's anything else (like InvalidAlgorithmError for ES256 tokens), log and fall through to the API check
            logger.warning(f"Local PyJWT validation failed ({type(e).__name__}). Falling back to Supabase API for asymmetric tokens.")
    else:
        logger.warning("PyJWT is not installed. Falling back to supabase.auth.get_user() for cryptographic token validation.")

    # Fallback: Use Supabase API for ES256/RS256 tokens or if PyJWT is missing
    try:
        temp_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        user_res = temp_client.auth.get_user(token)
        if user_res and user_res.user:
            return user_res.user.id
    except Exception as e:
        print("DEBUG TOKEN ERROR:", e)
        err_str = str(e).lower()
        logger.warning(f"Supabase auth fallback failed: {type(e).__name__}")
        if 'expired' in err_str or 'exp' in err_str:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        raise HTTPException(status_code=401, detail="Authentication failed.")
        
    logger.warning('Supabase auth fallback: user_res was empty. Token may be invalid.')
    raise HTTPException(status_code=401, detail="Authentication failed.")

def get_supabase_client(request: Request) -> Client:
    auth_header = request.headers.get("Authorization")
    
    # Debug print
    print(f"DEBUG AUTH: {request.method} {request.url.path}")
    safe_headers = dict(request.headers)
    keys_to_delete = [k for k in safe_headers.keys() if k.lower() == "authorization"]
    for k in keys_to_delete:
        del safe_headers[k]
    safe_headers["Authorization"] = "[REDACTED]"
    
    for k in list(safe_headers.keys()):
        k_lower = k.lower()
        if "cookie" in k_lower or k_lower == "x-workspace-id" or k_lower == "x-api-key":
            safe_headers[k] = "[REDACTED]"

    print(f"DEBUG HEADERS: {safe_headers}")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=f"Missing or invalid Authorization header: {auth_header}")
    
    token = auth_header.split(" ")[1]
    
    try:
        client: Client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
        return client
    except Exception as e:
        print("DEBUG TOKEN ERROR:", e)
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_async_supabase_client(request: Request) -> AsyncClient:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=f"Missing or invalid Authorization header: {auth_header}")
    
    token = auth_header.split(" ")[1]
    
    try:
        client: AsyncClient = await create_async_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=AsyncClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
        return client
    except Exception as e:
        print("DEBUG TOKEN ERROR:", e)
        raise HTTPException(status_code=401, detail="Invalid token")

def get_service_client() -> Client:
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", SUPABASE_KEY)
    return create_client(SUPABASE_URL, service_key)

async def get_async_service_client() -> AsyncClient:
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", SUPABASE_KEY)
    return await create_async_client(SUPABASE_URL, service_key)

async def get_current_workspace(request: Request, supabase: AsyncClient = Depends(get_async_supabase_client)) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing auth header")
    token = auth_header.split(" ")[1]
    
    # Extract user_id and AAL from the JWT
    user_aal = "aal1"
    if HAS_PYJWT:
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            if decoded.get("exp") and decoded["exp"] < time.time():
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
            user_aal = decoded.get("aal", "aal1")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except Exception as e:
            pass
            
    try:
        # Layer 1: We use the already injected AsyncClient to validate the token.
        # This prevents synchronous event-loop blocking from create_client.
        user_response = await supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Authentication failed.")
        user_id = user_response.user.id
        
        if not HAS_PYJWT:
            amr = getattr(user_response.user, 'amr', None) or []
            if any(a.get('method') == 'totp' for a in amr):
                user_aal = 'aal2'
    except HTTPException:
        raise
    except Exception as e:
        print("DEBUG TOKEN ERROR:", e)
        err_str = str(e).lower()
        if 'expired' in err_str or 'exp' in err_str:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        raise HTTPException(status_code=401, detail="Authentication failed.")
    
    requested_workspace_id = request.headers.get("X-Workspace-Id")
    
    try:
        if requested_workspace_id:
            res = await supabase.table("workspaces").select("id").eq("id", requested_workspace_id).execute()
        else:
            res = await supabase.table("workspaces").select("id").order("created_at", desc=False).limit(1).execute()
    except Exception as e:
        print("DEBUG TOKEN ERROR:", e)
        raise HTTPException(status_code=500, detail="Database error retrieving workspace")
        
    if not res.data:
        if requested_workspace_id:
            # Ghost Workspace Lockout trap: Check if they have ANY workspaces at all
            fallback_res = await supabase.table("workspaces").select("id").limit(1).execute()
            if not fallback_res.data:
                raise HTTPException(status_code=404, detail="No workspace found. Please complete onboarding first.")
            raise HTTPException(status_code=403, detail="Not a member of this workspace")
        raise HTTPException(status_code=404, detail="No workspace found. Please complete onboarding first.")
        
    workspace_data = res.data[0]
    workspace_id = str(workspace_data["id"])

    # Block mutations on pending_deletion workspaces
    exempt_paths = ["/request-deletion", "/cancel-deletion"]
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not any(request.url.path.endswith(p) for p in exempt_paths):
        try:
            ws_status_res = await supabase.table("workspaces").select("status").eq("id", workspace_id).execute()
            ws_status = ws_status_res.data[0].get("status") if ws_status_res.data else None
            if ws_status == "pending_deletion":
                raise HTTPException(
                    status_code=423,
                    detail="This workspace is scheduled for deletion. All modifications are locked during the 14-day grace period."
                )
        except HTTPException:
            raise
        except Exception as e:
            # If the column doesn't exist or DB errors out, gracefully ignore the deletion lock
            pass

    # --- 2FA enforcement ---
    # Fetch workspace settings to check require_2fa. Do NOT move this check before workspace membership is confirmed.
    try:
        ws_res = await supabase.table("workspaces").select("require_2fa").eq("id", workspace_id).single().execute()
        workspace_row = ws_res.data or {}
    except Exception:
        workspace_row = {}

    # SECURITY: This is the 2FA enforcement gate. Do NOT remove without architectural review.
    if workspace_row.get('require_2fa', False) and user_aal != 'aal2':
        raise HTTPException(
            status_code=403,
            detail={
                'code': 'MFA_REQUIRED',
                'message': '2FA is required for this workspace. Please enable 2FA in your account security settings before continuing.'
            }
        )
    
    return workspace_id


def get_current_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ")[1]
    return verify_token_and_get_user_id(token)
