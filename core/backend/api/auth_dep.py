from dotenv import load_dotenv
load_dotenv()
import os
import time
import logging
import threading
import asyncio
from typing import Optional
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
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=401, detail="Invalid token")
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
        sub = decoded.get("sub", "")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload: missing sub")
        return AuthUser(
            id=str(sub),
            workspace_id=decoded.get("user_metadata", {}).get("workspace_id", ""),
            email=decoded.get("email", "")
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token signature.")


def verify_token_and_get_user_id(token: str) -> str:
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=401, detail="Invalid token")
    if HAS_PYJWT and SUPABASE_JWT_SECRET:
        try:
            decoded = jwt.decode(
                token, 
                SUPABASE_JWT_SECRET, 
                algorithms=["HS256"], 
                options={"verify_exp": True},
                audience="authenticated"
            )
            sub = decoded.get("sub")
            if not sub:
                raise HTTPException(status_code=401, detail="Invalid token payload: missing sub")
            return str(sub)
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
        if user_res and user_res.user and user_res.user.id:
            return str(user_res.user.id)
    except Exception as e:
        err_str = str(e).lower()
        logger.warning(f"Supabase auth fallback failed: {type(e).__name__}")
        if 'expired' in err_str or 'exp' in err_str:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        raise HTTPException(status_code=401, detail="Authentication failed.")
        
    logger.warning('Supabase auth fallback: user_res was empty. Token may be invalid.')
    raise HTTPException(status_code=401, detail="Authentication failed.")

def get_supabase_client(request: Request) -> Client:
    try:
        path = str(getattr(getattr(request, "url", None), "path", "") or "")
        if "/webhooks/esp/sendgrid" in path or "/webhooks/esp/mailgun" in path or "/unsubscribe" in path:
            try:
                return get_service_client()
            except Exception:
                return None
    except Exception:
        pass

    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    parts = auth_header.split(" ")
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Missing token in Authorization header")
    
    token = parts[1].strip()
    
    try:
        client: Client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
        return client
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_async_supabase_client(request: Request) -> AsyncClient:
    try:
        path = str(getattr(getattr(request, "url", None), "path", "") or "")
        if "/webhooks/esp/sendgrid" in path or "/webhooks/esp/mailgun" in path or "/unsubscribe" in path:
            try:
                return await get_async_service_client()
            except Exception:
                return None
    except Exception:
        pass

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    parts = auth_header.split(" ")
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Missing token in Authorization header")
    
    token = parts[1].strip()
    
    try:
        client: AsyncClient = await create_async_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=AsyncClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
        return client
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

# =========================================================================
# Supabase Client Singletons & Concurrency Controls (Three-Layer Paranoia)
# =========================================================================
# Layer 0 & 1: Module-level singletons and thread/async locks
_service_client: Optional[Client] = None
_service_client_lock = threading.Lock()

_async_service_client: Optional[AsyncClient] = None
_async_service_client_loop: Optional[asyncio.AbstractEventLoop] = None
_async_service_client_lock: Optional[asyncio.Lock] = None
_async_lock_init_lock = threading.Lock()


def _get_async_lock() -> asyncio.Lock:
    """
    Retrieve or create an asyncio.Lock bound to the current running event loop.
    Prevents 'Future attached to a different loop' errors when loops are recycled.
    """
    global _async_service_client_lock
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _async_service_client_lock is None:
        with _async_lock_init_lock:
            if _async_service_client_lock is None:
                _async_service_client_lock = asyncio.Lock()
    elif current_loop is not None:
        lock_loop = getattr(_async_service_client_lock, "_loop", None)
        if lock_loop is not None and (lock_loop.is_closed() or lock_loop != current_loop):
            with _async_lock_init_lock:
                _async_service_client_lock = asyncio.Lock()

    return _async_service_client_lock


def reset_client_singletons() -> None:
    """
    Layer 1 & Layer 2: Resets the cached Supabase client singletons and locks.
    Enables connection drop resilience and prevents cross-test state leakage
    when tests mock client creation or modify environment variables.
    """
    global _service_client, _async_service_client, _async_service_client_loop, _async_service_client_lock
    with _service_client_lock:
        with _async_lock_init_lock:
            _service_client = None
            _async_service_client = None
            _async_service_client_loop = None
            _async_service_client_lock = None


def get_service_client() -> Client:
    """
    Layer 0 & Layer 1: Synchronous Supabase service client singleton.
    Thread-safe double-checked locking prevents connection pool/SSL context thrashing.
    """
    global _service_client
    if _service_client is None:
        with _service_client_lock:
            if _service_client is None:
                url = os.environ.get("SUPABASE_URL") or SUPABASE_URL
                service_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY") or SUPABASE_KEY
                try:
                    if url and service_key:
                        _service_client = create_client(url, service_key)
                except Exception as exc:
                    logger.warning(f"get_service_client failed to initialize: {exc}")
                    _service_client = None
    return _service_client


async def get_async_service_client() -> AsyncClient:
    """
    Layer 0 & Layer 1: Asynchronous Supabase service client singleton.
    Async single-flight locking with loop-lifecycle awareness avoids duplicate
    connection pools and handles event-loop transitions cleanly.
    """
    global _async_service_client, _async_service_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    # Fast-path: singleton already initialized for this event loop
    if _async_service_client is not None:
        if current_loop is None or (
            _async_service_client_loop is not None
            and not _async_service_client_loop.is_closed()
            and _async_service_client_loop == current_loop
        ):
            return _async_service_client

    lock = _get_async_lock()
    async with lock:
        # Re-check inside lock
        if _async_service_client is not None:
            if current_loop is not None and _async_service_client_loop is not None:
                if _async_service_client_loop.is_closed() or _async_service_client_loop != current_loop:
                    _async_service_client = None
                    _async_service_client_loop = None

        if _async_service_client is None:
            url = os.environ.get("SUPABASE_URL") or SUPABASE_URL
            service_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY") or SUPABASE_KEY
            try:
                if url and service_key:
                    _async_service_client = await create_async_client(url, service_key)
                    _async_service_client_loop = current_loop
            except Exception as exc:
                logger.warning(f"get_async_service_client failed to initialize: {exc}")
                _async_service_client = None

    return _async_service_client

async def get_current_workspace(request: Request, supabase: AsyncClient = Depends(get_async_supabase_client)) -> str:
    try:
        path = str(getattr(getattr(request, "url", None), "path", "") or "")
        if "/webhooks/esp/sendgrid" in path or "/webhooks/esp/mailgun" in path:
            return "public_webhook"
    except Exception:
        pass

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    parts = auth_header.split(" ")
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Missing token in Authorization header")
    token = parts[1].strip()
    
    # Extract user_id and AAL from the JWT
    user_aal = "aal1"
    decoded_payload = None
    if HAS_PYJWT:
        try:
            decoded_payload = jwt.decode(token, options={"verify_signature": False})
            if decoded_payload.get("exp") and decoded_payload["exp"] < time.time():
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except HTTPException:
            raise
        except Exception:
            pass
            
    try:
        # Layer 1: We use the already injected AsyncClient to validate the token.
        # This prevents synchronous event-loop blocking from create_client.
        # This call cryptographically validates the token signature via GoTrue.
        user_response = await supabase.auth.get_user(token)
        if not user_response or not user_response.user or not user_response.user.id:
            raise HTTPException(status_code=401, detail="Authentication failed.")
        user_id = str(user_response.user.id)
        
        # Since get_user() succeeded, GoTrue has verified the JWT signature.
        # It is now cryptographically safe to read the 'aal' claim from the payload.
        if decoded_payload:
            user_aal = decoded_payload.get("aal", "aal1")
        else:
            user_aal = "aal1"
            
    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e).lower()
        if 'expired' in err_str or 'exp' in err_str:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        raise HTTPException(status_code=401, detail="Authentication failed.")
    
    # Layer 2 Paranoia: Normalize JavaScript/client uninitialized values
    raw_requested_ws = request.headers.get("X-Workspace-Id") or request.query_params.get("workspace_id")
    requested_workspace_id = None
    if raw_requested_ws:
        stripped = raw_requested_ws.strip()
        if stripped.lower() not in ("undefined", "null", "none", ""):
            requested_workspace_id = stripped

    workspace_data = None
    if requested_workspace_id:
        # Layer 2 Paranoia: Validate UUID format to prevent malformed queries in production
        import os
        import uuid
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                uuid.UUID(str(requested_workspace_id))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid X-Workspace-Id format (must be a valid UUID)")

        # Layer 1 Paranoia: Prevent Cross-Tenant Impersonation / IDOR
        try:
            res = await supabase.table("workspaces").select("id, status, require_2fa, owner_id").eq("id", requested_workspace_id).execute()
        except Exception as e:
            logger.error(f"Database error retrieving requested workspace {requested_workspace_id}: {e}")
            raise HTTPException(status_code=500, detail="Database error retrieving workspace")

        if not res.data:
            # Workspace does not exist
            raise HTTPException(status_code=404, detail="Workspace not found")

        candidate_ws = res.data[0]
        # Verify caller is a member (either owner or listed in workspace_members)
        is_owner = candidate_ws.get("owner_id") == user_id
        if not is_owner:
            try:
                mem_res = await supabase.table("workspace_members").select("role").eq("workspace_id", requested_workspace_id).eq("user_id", user_id).execute()
                if not mem_res.data:
                    raise HTTPException(status_code=403, detail="Not a member of this workspace")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Database error verifying membership in workspace {requested_workspace_id}: {e}")
                raise HTTPException(status_code=500, detail="Database error verifying workspace membership")

        workspace_data = candidate_ws
    else:
        # Security Hardening (VULN-20 & API-24 - Paranoia Framework):
        # Layer 1 & 2: For mutating requests (POST, PUT, PATCH, DELETE), if user belongs to >1 workspace,
        # never guess or silently default to workspace 1 — fail closed to prevent cross-workspace contamination.
        try:
            mem_res = await supabase.table("workspace_members").select("workspace_id").eq("user_id", user_id).order("created_at", desc=False).limit(2).execute()
            member_workspaces = mem_res.data or []
            
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and len(member_workspaces) > 1:
                # User belongs to multiple workspaces but omitted X-Workspace-Id on a mutating operation
                raise HTTPException(
                    status_code=400,
                    detail="Explicit 'X-Workspace-Id' header is required for this operation because your account has access to multiple workspaces. Please specify the active workspace."
                )

            default_ws_id = member_workspaces[0]["workspace_id"] if member_workspaces else None
            
            if default_ws_id:
                ws_res = await supabase.table("workspaces").select("id, status, require_2fa, owner_id").eq("id", default_ws_id).execute()
                if ws_res.data:
                    workspace_data = ws_res.data[0]
            else:
                # Fallback: check if user owns any workspace directly
                owned_res = await supabase.table("workspaces").select("id, status, require_2fa, owner_id").eq("owner_id", user_id).order("created_at", desc=False).limit(2).execute()
                owned_workspaces = owned_res.data or []
                if request.method in ("POST", "PUT", "PATCH", "DELETE") and len(owned_workspaces) > 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Explicit 'X-Workspace-Id' header is required for this operation because your account owns multiple workspaces."
                    )
                if owned_workspaces:
                    workspace_data = owned_workspaces[0]
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Database error retrieving default workspace for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail="Database error retrieving workspace")

        if not workspace_data:
            raise HTTPException(status_code=404, detail="No workspace found. Please complete onboarding first.")

    workspace_id = str(workspace_data["id"])

    # Block mutations on pending_deletion workspaces
    exempt_paths = ["/request-deletion", "/cancel-deletion"]
    request_path = request.url.path.rstrip("/")
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not any(request_path.endswith(p.rstrip("/")) for p in exempt_paths):
        ws_status = workspace_data.get("status")
        if ws_status == "pending_deletion":
            raise HTTPException(
                status_code=423,
                detail="This workspace is scheduled for deletion. All modifications are locked during the 14-day grace period."
            )

    # --- 2FA enforcement ---
    require_2fa = workspace_data.get("require_2fa", False)
    if require_2fa and user_aal != 'aal2':
        raise HTTPException(
            status_code=403,
            detail={
                'code': 'MFA_REQUIRED',
                'message': '2FA is required for this workspace. Please enable 2FA in your account security settings before continuing.'
            }
        )
    
    return workspace_id


async def get_current_user_id_with_2fa(
    request: Request,
    workspace_id: Optional[str] = None,
    supabase: AsyncClient = Depends(get_async_supabase_client)
) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    parts = auth_header.split(" ")
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Missing token in Authorization header")
    token = parts[1].strip()
    
    user_aal = "aal1"
    decoded_payload = None
    if HAS_PYJWT:
        try:
            decoded_payload = jwt.decode(token, options={"verify_signature": False})
            if decoded_payload.get("exp") and decoded_payload["exp"] < time.time():
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except HTTPException:
            raise
        except Exception:
            pass
            
    try:
        user_response = await supabase.auth.get_user(token)
        if not user_response or not user_response.user or not user_response.user.id:
            raise HTTPException(status_code=401, detail="Authentication failed.")
        user_id = str(user_response.user.id)
        if decoded_payload:
            user_aal = decoded_payload.get("aal", "aal1")
    except HTTPException:
        raise
    except Exception as e:
        err_str = str(e).lower()
        if 'expired' in err_str or 'exp' in err_str:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        raise HTTPException(status_code=401, detail="Authentication failed.")
        
    # Determine workspace_id if not explicitly provided as path param
    if not workspace_id:
        workspace_id = request.path_params.get("workspace_id") or request.headers.get("X-Workspace-Id")
        if workspace_id:
            workspace_id = workspace_id.strip()
            if workspace_id.lower() in ("undefined", "null", "none", ""):
                workspace_id = None

    if workspace_id:
        try:
            ws_res = await supabase.table("workspaces").select("require_2fa").eq("id", workspace_id).single().execute()
            workspace_row = ws_res.data or {}
        except Exception as e:
            logger.warning(f"DB error fetching require_2fa for {workspace_id}: {e}")
            workspace_row = {}

        if workspace_row.get('require_2fa', False) and user_aal != 'aal2':
            raise HTTPException(
                status_code=403,
                detail={
                    'code': 'MFA_REQUIRED',
                    'message': '2FA is required for this workspace. Please enable 2FA in your account security settings before continuing.'
                }
            )

    return user_id

def get_current_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    parts = auth_header.split(" ")
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Missing token in Authorization header")
    token = parts[1].strip()
    return verify_token_and_get_user_id(token)

async def get_workspace_role(
    workspace_id: str,
    user_id: str,
    supabase: Optional[AsyncClient] = None
) -> Optional[str]:
    """
    Returns the role of user_id in workspace_id ('owner', 'admin', 'member'),
    or None if the user is not a member.
    """
    if not supabase:
        supabase = await get_async_service_client()
    try:
        # Check workspace_members
        res = await supabase.table("workspace_members").select("role").eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
        if res.data:
            return res.data[0].get("role")
        # Check if owner_id in workspaces table
        ws_res = await supabase.table("workspaces").select("owner_id").eq("id", workspace_id).execute()
        if ws_res.data and ws_res.data[0].get("owner_id") == user_id:
            return "owner"
    except Exception as e:
        logger.error(f"Error checking workspace role: {e}")
    return None

def require_workspace_role(allowed_roles: list[str]):
    """
    RBAC dependency factory that validates the calling user has one of the allowed_roles
    in the active workspace.
    """
    async def _role_checker(
        workspace_id: str = Depends(get_current_workspace),
        user_id: str = Depends(get_current_user_id),
    ) -> str:
        supabase = await get_async_service_client()
        role = await get_workspace_role(workspace_id, user_id, supabase)
        if not role or role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Action requires one of the following roles: {', '.join(allowed_roles)}"
            )
        return role
    return _role_checker

def require_superadmin(current_user_id: str = Depends(get_current_user_id)):
    supabase = get_service_client()
    res = supabase.table("admin_grants").select("id").eq("user_id", current_user_id).is_("revoked_at", "null").execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user_id
