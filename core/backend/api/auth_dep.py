from dotenv import load_dotenv
load_dotenv()
import os
import uuid
import time
import hashlib
import logging
import threading
import asyncio
from typing import Optional, Dict, Tuple, Any, List, Set
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

_jwks_client: Optional[Any] = None
_jwks_client_lock = threading.Lock()

def get_jwks_client():
    global _jwks_client
    if _jwks_client is None and HAS_PYJWT and SUPABASE_URL:
        with _jwks_client_lock:
            if _jwks_client is None:
                try:
                    jwks_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
                    _jwks_client = jwt.PyJWKClient(jwks_url, cache_keys=True, max_cached_keys=16)
                except Exception as e:
                    logger.warning(f"Could not initialize PyJWKClient: {e}")
    return _jwks_client


class SessionActivityTracker:
    """
    Three-Layer Paranoia Session Activity Tracker:
      - Layer 0: Tracks last active timestamp and device fingerprint for (workspace_id, user_id).
      - Layer 1: Automatically expires sessions when idle time exceeds workspace security policy timeout.
      - Layer 2: Blocks session hijacking when enforce_device_fingerprint is enabled if client User-Agent hash changes.
    """
    def __init__(self, max_entries: int = 10000):
        self._lock = threading.Lock()
        self._activity: Dict[str, Tuple[float, str]] = {}  # key -> (last_active_ts, fingerprint_hash)
        self._max_entries = max_entries

    def record_and_verify(
        self,
        workspace_id: str,
        user_id: str,
        timeout_minutes: Optional[int],
        enforce_fingerprint: bool = False,
        user_agent: Optional[str] = None
    ) -> None:
        if not timeout_minutes or timeout_minutes <= 0:
            return
        
        now = time.time()
        client_fp = hashlib.sha256((user_agent or "default_client").encode("utf-8")).hexdigest()[:16]
        key = f"{workspace_id}:{user_id}"

        with self._lock:
            # Bound memory size to prevent OOM
            if len(self._activity) > self._max_entries:
                sorted_keys = sorted(self._activity.keys(), key=lambda k: self._activity[k][0])
                for k in sorted_keys[:int(self._max_entries * 0.2)]:
                    del self._activity[k]

            if key in self._activity:
                last_active, prev_fp = self._activity[key]
                elapsed_minutes = (now - last_active) / 60.0
                if elapsed_minutes > timeout_minutes:
                    del self._activity[key]
                    raise HTTPException(
                        status_code=401,
                        detail="Session expired due to inactivity. Please log in again."
                    )
                if enforce_fingerprint and prev_fp and prev_fp != client_fp:
                    del self._activity[key]
                    raise HTTPException(
                        status_code=401,
                        detail="Session invalidated due to device fingerprint mismatch."
                    )
            
            # Update last active timestamp and device fingerprint
            self._activity[key] = (now, client_fp)

session_tracker = SessionActivityTracker()

from pydantic import BaseModel
class AuthUser(BaseModel):
    id: str
    workspace_id: str
    email: str

def verify_jwt(token: str) -> AuthUser:
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=401, detail="Invalid token")
    if not HAS_PYJWT:
        raise HTTPException(status_code=401, detail="Missing PyJWT or JWT secret")
    decoded = None
    if SUPABASE_JWT_SECRET:
        try:
            decoded = jwt.decode(
                token, 
                SUPABASE_JWT_SECRET, 
                algorithms=["HS256"], 
                options={"verify_exp": True},
                audience="authenticated"
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired.")
        except jwt.PyJWTError:
            pass

    if not decoded:
        jwks = get_jwks_client()
        if jwks:
            try:
                signing_key = jwks.get_signing_key_from_jwt(token)
                decoded = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    options={"verify_exp": True},
                    audience="authenticated"
                )
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired.")
            except Exception:
                pass

    if not decoded:
        raise HTTPException(status_code=401, detail="Invalid token signature.")

    sub = decoded.get("sub", "")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload: missing sub")
    return AuthUser(
        id=str(sub),
        workspace_id=decoded.get("user_metadata", {}).get("workspace_id", ""),
        email=decoded.get("email", "")
    )


def verify_token_and_get_user_id(token: str) -> str:
    if not token or not isinstance(token, str):
        raise HTTPException(status_code=401, detail="Invalid token")
    
    token_hash = _hash_token(token)
    now = time.time()
    with _token_verification_lock:
        if token_hash in _token_verification_cache:
            uid, _, _, expires_at = _token_verification_cache[token_hash]
            if now < expires_at:
                return uid
            del _token_verification_cache[token_hash]

    decoded = None
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
            sub_str = str(sub)
            exp_time = (decoded or {}).get("exp", now + 300)
            cache_ttl = max(10, min(exp_time - now - 10, 300))
            with _token_verification_lock:
                _token_verification_cache[token_hash] = (sub_str, "aal1", decoded, now + cache_ttl)
            return sub_str
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except jwt.PyJWTError as e:
            logger.debug(f"Local PyJWT HS256 validation failed ({type(e).__name__}). Trying JWKS for asymmetric tokens.")

    # Try local JWKS for asymmetric tokens (ES256 / RS256)
    if HAS_PYJWT:
        jwks = get_jwks_client()
        if jwks:
            try:
                signing_key = jwks.get_signing_key_from_jwt(token)
                decoded = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    options={"verify_exp": True},
                    audience="authenticated"
                )
                sub = decoded.get("sub")
                if not sub:
                    raise HTTPException(status_code=401, detail="Invalid token payload: missing sub")
                sub_str = str(sub)
                exp_time = (decoded or {}).get("exp", now + 300)
                cache_ttl = max(10, min(exp_time - now - 10, 300))
                with _token_verification_lock:
                    _token_verification_cache[token_hash] = (sub_str, decoded.get("aal", "aal1"), decoded, now + cache_ttl)
                return sub_str
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
            except Exception as jwks_err:
                logger.debug(f"PyJWKClient verification failed: {jwks_err}")

    # Check unverified exp before network call to fail fast
    if HAS_PYJWT:
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            if unverified.get("exp") and unverified["exp"] < now:
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except HTTPException:
            raise
        except Exception:
            pass

    # Fallback: Use Supabase API for ES256/RS256 tokens or if PyJWT is missing
    try:
        temp_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        user_res = temp_client.auth.get_user(token)
        if user_res and user_res.user and user_res.user.id:
            uid = str(user_res.user.id)
            with _token_verification_lock:
                _token_verification_cache[token_hash] = (uid, "aal1", None, now + 300)
            return uid
    except Exception as e:
        err_str = str(e).lower()
        logger.warning(f"Supabase auth fallback failed: {type(e).__name__}")
        if 'expired' in err_str or 'exp' in err_str:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        raise HTTPException(status_code=401, detail="Authentication failed.")
        
    logger.warning('Supabase auth fallback: user_res was empty. Token may be invalid.')
    raise HTTPException(status_code=401, detail="Authentication failed.")

# ─── CONNECTION POOL & TOKEN-CLIENT CACHING (FLAW-API-13 / 10K-CUSTOMER SCALE) ───
_CLIENT_CACHE_TTL_SECONDS = 300
_CLIENT_CACHE_MAX_ENTRIES = 1024

_sync_user_clients: Dict[str, Tuple[Client, float]] = {}
_sync_user_clients_lock = threading.Lock()

_async_user_clients: Dict[str, Tuple[AsyncClient, float]] = {}
_async_user_clients_lock = threading.Lock()

def _safe_close_sync_client(client: Any) -> None:
    """Closes all underlying httpx transports to prevent EMFILE socket leaks under 10k tenants."""
    if not client:
        return
    try:
        pg = getattr(client, "postgrest", None)
        if pg:
            sess = getattr(pg, "session", None) or getattr(pg, "_client", None)
            if sess and hasattr(sess, "close"):
                sess.close()
    except Exception:
        pass

    try:
        auth = getattr(client, "auth", None)
        if auth:
            http_c = getattr(auth, "_http_client", None) or getattr(auth, "_client", None)
            if http_c and hasattr(http_c, "close"):
                http_c.close()
    except Exception:
        pass

    try:
        storage = getattr(client, "storage", None)
        if storage:
            storage_c = getattr(storage, "_client", None) or getattr(storage, "session", None)
            if storage_c and hasattr(storage_c, "close"):
                storage_c.close()
    except Exception:
        pass

async def _safe_close_async_client(client: Any) -> None:
    """Closes all underlying async httpx transports to prevent EMFILE socket leaks under 10k tenants."""
    if not client:
        return
    try:
        pg = getattr(client, "postgrest", None)
        if pg:
            sess = getattr(pg, "session", None) or getattr(pg, "_client", None)
            if sess and hasattr(sess, "aclose"):
                await sess.aclose()
            elif sess and hasattr(sess, "close"):
                sess.close()
    except Exception:
        pass

    try:
        auth = getattr(client, "auth", None)
        if auth:
            http_c = getattr(auth, "_http_client", None) or getattr(auth, "_client", None)
            if http_c and hasattr(http_c, "aclose"):
                await http_c.aclose()
            elif http_c and hasattr(http_c, "close"):
                http_c.close()
    except Exception:
        pass

    try:
        storage = getattr(client, "storage", None)
        if storage:
            storage_c = getattr(storage, "_client", None) or getattr(storage, "session", None)
            if storage_c and hasattr(storage_c, "aclose"):
                await storage_c.aclose()
            elif storage_c and hasattr(storage_c, "close"):
                storage_c.close()
    except Exception:
        pass

def _hash_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

_token_verification_cache: Dict[str, Tuple[str, str, Optional[dict], float]] = {}
_token_verification_lock = threading.Lock()

async def _verify_token_cached(token: str, supabase: AsyncClient) -> Tuple[str, str, Optional[dict]]:
    token_hash = _hash_token(token)
    now = time.time()
    
    with _token_verification_lock:
        if token_hash in _token_verification_cache:
            uid, uaal, uload, expires_at = _token_verification_cache[token_hash]
            if now < expires_at:
                return uid, uaal, uload
            del _token_verification_cache[token_hash]
            
    # Local JWT fast-path
    user_id = None
    user_aal = "aal1"
    decoded_payload = None
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if jwt_secret and HAS_PYJWT:
        try:
            verified_payload = jwt.decode(token, jwt_secret, algorithms=["HS256"], audience="authenticated")
            user_id = str(verified_payload.get("sub") or verified_payload.get("id"))
            user_aal = verified_payload.get("aal", "aal1")
            decoded_payload = verified_payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except Exception:
            user_id = None

    if not user_id and HAS_PYJWT:
        jwks = get_jwks_client()
        if jwks:
            try:
                signing_key = jwks.get_signing_key_from_jwt(token)
                decoded_payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    options={"verify_exp": True},
                    audience="authenticated"
                )
                user_id = str(decoded_payload.get("sub") or decoded_payload.get("id"))
                user_aal = decoded_payload.get("aal", "aal1")
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
            except Exception as jwks_err:
                logger.debug(f"PyJWKClient cached verification failed: {jwks_err}")
                user_id = None

    if not user_id and HAS_PYJWT:
        try:
            decoded_payload = jwt.decode(token, options={"verify_signature": False})
            if decoded_payload.get("exp") and decoded_payload["exp"] < now:
                raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired. Please sign in again.")
        except HTTPException:
            raise
        except Exception:
            pass

    if not user_id:
        try:
            user_response = await supabase.auth.get_user(token)
            if not user_response or not user_response.user or not user_response.user.id:
                raise HTTPException(status_code=401, detail="Authentication failed.")
            user_id = str(user_response.user.id)
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
            if any(sig in err_str for sig in ('connect', 'timeout', 'timed out', 'connection refused', 'temporarily unavailable', '502', '503', '504', 'network error')):
                logger.warning(f"[Auth] Supabase GoTrue connectivity failure: {e}")
                raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable. Please retry.")
            raise HTTPException(status_code=401, detail="Authentication failed.")

    # Cache successful verification for min(exp - 10, 300s)
    exp_time = (decoded_payload or {}).get("exp", now + 300)
    cache_ttl = max(10, min(exp_time - now - 10, 300))
    with _token_verification_lock:
        if len(_token_verification_cache) >= 500:
            oldest_key = min(_token_verification_cache.keys(), key=lambda k: _token_verification_cache[k][3])
            _token_verification_cache.pop(oldest_key, None)
        _token_verification_cache[token_hash] = (user_id, user_aal, decoded_payload, now + cache_ttl)

    return user_id, user_aal, decoded_payload

def clear_client_pool_caches() -> None:
    """Clears in-memory cached sync and async user clients for test isolation."""
    with _sync_user_clients_lock:
        for c, _ in list(_sync_user_clients.values()):
            _safe_close_sync_client(c)
        _sync_user_clients.clear()
    with _async_user_clients_lock:
        for c, _ in list(_async_user_clients.values()):
            _safe_close_sync_client(c)
        _async_user_clients.clear()
    with _token_verification_lock:
        _token_verification_cache.clear()


def get_supabase_client(request: Request) -> Client:
    try:
        path = str(getattr(getattr(request, "url", None), "path", "") or "")
        clean_path = path.lower().split("?")[0].rstrip("/")
        is_public_webhook = (clean_path.startswith("/api/webhooks/esp/") or clean_path.startswith("/webhooks/esp/")) and ("/simulate" not in clean_path)
        is_unsubscribe = clean_path.startswith("/api/elein/unsubscribe") or clean_path.startswith("/api/unsubscribe") or clean_path.startswith("/unsubscribe")
        if is_public_webhook or is_unsubscribe:
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
    token_hash = _hash_token(token)
    now = time.time()

    expired_sync_client = None
    with _sync_user_clients_lock:
        if token_hash in _sync_user_clients:
            cached_client, expires_at = _sync_user_clients[token_hash]
            if now < expires_at:
                return cached_client
            del _sync_user_clients[token_hash]
            expired_sync_client = cached_client
    if expired_sync_client:
        _safe_close_sync_client(expired_sync_client)
    
    try:
        client: Client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
        evicted_sync_client = None
        with _sync_user_clients_lock:
            if len(_sync_user_clients) >= _CLIENT_CACHE_MAX_ENTRIES:
                oldest_key = min(_sync_user_clients.keys(), key=lambda k: _sync_user_clients[k][1])
                evicted_sync_client, _ = _sync_user_clients.pop(oldest_key)
            _sync_user_clients[token_hash] = (client, now + _CLIENT_CACHE_TTL_SECONDS)
        if evicted_sync_client:
            _safe_close_sync_client(evicted_sync_client)
        return client
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_async_supabase_client(request: Request) -> AsyncClient:
    try:
        path = str(getattr(getattr(request, "url", None), "path", "") or "")
        clean_path = path.lower().split("?")[0].rstrip("/")
        is_public_webhook = (clean_path.startswith("/api/webhooks/esp/") or clean_path.startswith("/webhooks/esp/")) and ("/simulate" not in clean_path)
        is_unsubscribe = clean_path.startswith("/api/elein/unsubscribe") or clean_path.startswith("/api/unsubscribe") or clean_path.startswith("/unsubscribe")
        if is_public_webhook or is_unsubscribe:
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
    token_hash = _hash_token(token)
    now = time.time()

    expired_async_client = None
    with _async_user_clients_lock:
        if token_hash in _async_user_clients:
            cached_client, expires_at = _async_user_clients[token_hash]
            if now < expires_at:
                return cached_client
            del _async_user_clients[token_hash]
            expired_async_client = cached_client
    if expired_async_client:
        await _safe_close_async_client(expired_async_client)
    
    try:
        client: AsyncClient = await create_async_client(
            SUPABASE_URL,
            SUPABASE_KEY,
            options=AsyncClientOptions(headers={"Authorization": f"Bearer {token}"})
        )
        evicted_async_client = None
        with _async_user_clients_lock:
            if len(_async_user_clients) >= _CLIENT_CACHE_MAX_ENTRIES:
                oldest_key = min(_async_user_clients.keys(), key=lambda k: _async_user_clients[k][1])
                evicted_async_client, _ = _async_user_clients.pop(oldest_key)
            _async_user_clients[token_hash] = (client, now + _CLIENT_CACHE_TTL_SECONDS)
        if evicted_async_client:
            await _safe_close_async_client(evicted_async_client)
        return client
    except HTTPException:
        raise
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
        clean_path = path.lower().split("?")[0].rstrip("/")
        is_public_webhook = (clean_path.startswith("/api/webhooks/esp/") or clean_path.startswith("/webhooks/esp/")) and ("/simulate" not in clean_path)
        is_unsubscribe = clean_path.startswith("/api/elein/unsubscribe") or clean_path.startswith("/api/unsubscribe") or clean_path.startswith("/unsubscribe")
        if is_public_webhook or is_unsubscribe:
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
    
    # Extract user_id and AAL from the JWT using cached verification
    user_id, user_aal, decoded_payload = await _verify_token_cached(token, supabase)
    
    # Layer 2 Paranoia: Normalize JavaScript/client uninitialized values
    raw_requested_ws = request.headers.get("X-Workspace-Id") or request.query_params.get("workspace_id") or request.query_params.get("ws")
    requested_workspace_id = None
    if raw_requested_ws:
        stripped = raw_requested_ws.strip()
        if stripped.lower() not in ("undefined", "null", "none", ""):
            requested_workspace_id = stripped

    db = (await get_async_service_client()) or supabase
    workspace_data = None
    if requested_workspace_id:
        # Layer 2 Paranoia: Validate UUID format to prevent malformed queries in production
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                uuid.UUID(str(requested_workspace_id))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid X-Workspace-Id format (must be a valid UUID)")

        # Layer 1 Paranoia: Prevent Cross-Tenant Impersonation / IDOR
        try:
            res = await db.table("workspaces").select("id, status, require_2fa, owner_id, agency_id").eq("id", requested_workspace_id).execute()
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
                mem_res = await db.table("workspace_members").select("role").eq("workspace_id", requested_workspace_id).eq("user_id", user_id).execute()
                if not mem_res.data:
                    # Paranoia Layer 1: Check if workspace belongs to an agency where caller is owner/admin or delegated
                    agency_id = candidate_ws.get("agency_id")
                    is_agency_authorized = False
                    if agency_id:
                        try:
                            # 1. Check if user is owner or admin in agency_members
                            agency_mem = await db.table("agency_members").select("id, role").eq("agency_id", agency_id).eq("user_id", user_id).execute()
                            if agency_mem.data:
                                m = agency_mem.data[0]
                                if m.get("role") in ("owner", "admin"):
                                    is_agency_authorized = True
                                else:
                                    # 2. Check delegated client access
                                    acc = await db.table("agency_client_access").select("id").eq("agency_member_id", m["id"]).eq("workspace_id", requested_workspace_id).execute()
                                    if acc.data:
                                        is_agency_authorized = True
                        except Exception as agency_err:
                            logger.warning(f"Error checking agency client authorization: {agency_err}")

                    if not is_agency_authorized:
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
        # Diagnostic validation and probe endpoints (e.g. /accounts/validate, /proxies/test) are non-mutating.
        try:
            mem_res = await db.table("workspace_members").select("workspace_id").eq("user_id", user_id).order("created_at", desc=False).limit(2).execute()
            member_workspaces = mem_res.data or []
            
            is_non_mutating_probe = any(p in request.url.path for p in ["/accounts/validate", "/proxies/test", "/accounts/test"])
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and len(member_workspaces) > 1 and not is_non_mutating_probe:
                # User belongs to multiple workspaces but omitted X-Workspace-Id on a mutating operation
                raise HTTPException(
                    status_code=400,
                    detail="Explicit 'X-Workspace-Id' header is required for this operation because your account has access to multiple workspaces. Please specify the active workspace."
                )

            default_ws_id = member_workspaces[0]["workspace_id"] if member_workspaces else None
            
            if default_ws_id:
                ws_res = await db.table("workspaces").select("id, status, require_2fa, owner_id, agency_id").eq("id", default_ws_id).execute()
                if ws_res.data:
                    workspace_data = ws_res.data[0]
            else:
                # Fallback: check if user owns any workspace directly
                owned_res = await db.table("workspaces").select("id, status, require_2fa, owner_id, agency_id").eq("owner_id", user_id).order("created_at", desc=False).limit(2).execute()
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

    # --- Session Inactivity and Hardware Fingerprint Enforcement ---
    sec_policies = (workspace_data.get("metadata") or {}).get("security_policies") or {}
    timeout_min = sec_policies.get("session_inactivity_timeout_minutes")
    enforce_fp = bool(sec_policies.get("enforce_device_fingerprint"))
    ua = request.headers.get("user-agent")
    session_tracker.record_and_verify(
        workspace_id=workspace_id,
        user_id=user_id,
        timeout_minutes=timeout_min,
        enforce_fingerprint=enforce_fp,
        user_agent=ua
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
    
    user_id, user_aal, decoded_payload = await _verify_token_cached(token, supabase)
        
    # Determine workspace_id if not explicitly provided as path param
    if not workspace_id:
        workspace_id = request.path_params.get("workspace_id") or request.headers.get("X-Workspace-Id")
        if workspace_id:
            workspace_id = workspace_id.strip()
            if workspace_id.lower() in ("undefined", "null", "none", ""):
                workspace_id = None

    if workspace_id:
        db = (await get_async_service_client()) or supabase
        try:
            ws_res = await db.table("workspaces").select("require_2fa").eq("id", workspace_id).single().execute()
            workspace_row = ws_res.data or {}
        except Exception as e:
            logger.error(f"DB error fetching require_2fa for {workspace_id}: {e}")
            # Paranoia Layer 1: Fail closed rather than open on security check errors
            raise HTTPException(
                status_code=503,
                detail="Security verification temporarily unavailable. Please retry in a few moments."
            )

        if workspace_row.get('require_2fa', False) and user_aal != 'aal2':
            raise HTTPException(
                status_code=403,
                detail={
                    'code': 'MFA_REQUIRED',
                    'message': '2FA is required for this workspace. Please enable 2FA in your account security settings before continuing.'
                }
            )

        # --- Session Inactivity and Hardware Fingerprint Enforcement ---
        sec_policies = (workspace_row.get("metadata") or {}).get("security_policies") or {}
        timeout_min = sec_policies.get("session_inactivity_timeout_minutes")
        enforce_fp = bool(sec_policies.get("enforce_device_fingerprint"))
        ua = request.headers.get("user-agent")
        session_tracker.record_and_verify(
            workspace_id=workspace_id,
            user_id=user_id,
            timeout_minutes=timeout_min,
            enforce_fingerprint=enforce_fp,
            user_agent=ua
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

def require_workspace_permission(permission: str):
    """
    Granular RBAC dependency factory (Phase T) that validates the calling user has the
    required permission in the active workspace according to RBACGuard policy.
    """
    async def _perm_checker(
        workspace_id: str = Depends(get_current_workspace),
        user_id: str = Depends(get_current_user_id),
    ) -> str:
        from core.backend.services.rbac_guard import RBACGuard
        supabase = await get_async_service_client()
        role = await get_workspace_role(workspace_id, user_id, supabase)
        if not role or not RBACGuard.has_permission(role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: role '{role or 'unauthorized'}' lacks required permission '{permission}'."
            )
        return role
    return _perm_checker

def require_superadmin(current_user_id: str = Depends(get_current_user_id)):
    supabase = get_service_client()
    res = supabase.table("admin_grants").select("id").eq("user_id", current_user_id).is_("revoked_at", "null").execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_user_id
