"""
envelope_encryption.py — Enterprise Envelope Encryption Engine with Workspace DEK Management
Pillar 7 (Phase 7.1) — Master Platform Hardening & Execution Plan

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational):
      * Two-tier envelope encryption: Master Key (KEK) in KMS/Env wraps per-workspace Data Encryption Key (DEK).
      * AES-256-GCM authenticated cipher with 96-bit random nonce and workspace-binding AAD.
      * Format: v2:env:<version>:<nonce_b64>:<ciphertext_b64>.
  - Layer 1 (Environmental Failure Analysis):
      * Ephemeral in-memory DEK caching with 300s (5-minute) TTL and explicit memory zeroing.
      * Rotation resilience: falls back through candidate KEKs if primary KEK is rotated.
      * Zero-migration fallback: maintains thread-safe in-memory store if DB is offline.
  - Layer 2 (Human Paranoia & Zero-Leakage Audit):
      * Cross-tenant tampering defense: AAD binds workspace_id so copying ciphertext across tenants fails tag check.
      * Zero secret leaks: audit log captures operation metadata, timestamps, and key version with zero plaintext/DEK exposure.
"""

import os
import time
import base64
import hashlib
import logging
import threading
from typing import Optional, Dict, Any, Tuple, List, Union
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

ENVELOPE_PREFIX = "v2:env:"
CURRENT_KEY_VERSION = 1
NONCE_LENGTH = 12  # 96-bit standard nonce for AES-GCM
DEK_CACHE_TTL_SECONDS = 300  # 5 minutes


class VaultDecryptionError(Exception):
    """Raised when envelope decryption fails due to tampering, wrong tenant, or invalid KEK."""
    pass


class MasterKeyMissingError(Exception):
    """Raised when no valid Master Key (KEK) can be resolved."""
    pass


# -----------------------------------------------------------------------------
# In-Memory Thread-Safe Stores
# -----------------------------------------------------------------------------
_dek_lock = threading.Lock()
# workspace_id -> (dek_bytes, expiry_time)
_DEK_CACHE: Dict[str, Tuple[bytearray, float]] = {}
# workspace_id -> {"wrapped_dek": str, "key_version": int, "created_at": str}
_IN_MEMORY_WORKSPACE_DEKS: Dict[str, Dict[str, Any]] = {}
# Audit log in-memory buffer
_IN_MEMORY_ENCRYPTION_AUDIT: List[Dict[str, Any]] = []


# =============================================================================
# 1. MASTER KEY (KEK) MANAGEMENT & ROTATION WATERFALL
# =============================================================================

def _derive_kek_from_secret(secret_str: str) -> bytes:
    """Domain-separated SHA-256 derivation ensures exact 32-byte 256-bit AES key."""
    return hashlib.sha256(f"elein:envelope:kek:{secret_str}".encode("utf-8")).digest()


def get_master_kek_candidates() -> List[bytes]:
    """
    Paranoia Layer 1: Gathers candidate Master KEKs in priority order.
    Protects against key rotation drift: if MASTER_KEK is rotated, historical secrets
    are checked to prevent bricking tenant data.
    """
    candidates: List[str] = []

    # 1. Primary explicit Master KEK
    primary = os.environ.get("MASTER_KEK")
    if primary:
        candidates.append(primary)

    # 2. Rotated previous KEK list
    prev = os.environ.get("MASTER_PREVIOUS_KEKS", "")
    if prev:
        for p in prev.split(","):
            if p.strip():
                candidates.append(p.strip())

    # 3. Fallbacks from system secrets
    byok = os.environ.get("BYOK_VAULT_SECRET")
    if byok:
        candidates.append(byok)

    jwt = os.environ.get("SUPABASE_JWT_SECRET")
    if jwt:
        candidates.append(jwt)

    sb_service = os.environ.get("SUPABASE_SERVICE_KEY")
    if sb_service:
        candidates.append(sb_service)

    # 4. Developer fallback seed
    candidates.append("elein_master_envelope_kek_seed_2026_dev_only")

    derived: List[bytes] = []
    seen = set()
    for c in candidates:
        k = _derive_kek_from_secret(c)
        if k not in seen:
            seen.add(k)
            derived.append(k)

    return derived


def get_active_master_kek() -> bytes:
    """Returns the primary active 256-bit AES-GCM Key Encryption Key (KEK)."""
    candidates = get_master_kek_candidates()
    if not candidates:
        raise MasterKeyMissingError("No active Master Key (KEK) could be derived.")
    return candidates[0]


# =============================================================================
# 2. WORKSPACE DEK RESOLUTION & EPHEMERAL CACHING
# =============================================================================

def _wrap_dek(dek_bytes: bytes, kek_bytes: bytes) -> str:
    """Wraps a 32-byte workspace DEK with Master KEK using AES-256-GCM."""
    aesgcm = AESGCM(kek_bytes)
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, dek_bytes, None)
    nonce_b64 = base64.b64encode(nonce).decode("utf-8")
    ct_b64 = base64.b64encode(ciphertext).decode("utf-8")
    return f"v2:wrapped:{nonce_b64}:{ct_b64}"


def _unwrap_dek(wrapped_dek_str: str) -> bytes:
    """
    Unwraps wrapped DEK using active Master KEK, waterfalling through candidate KEKs
    if rotation has occurred.
    """
    if not wrapped_dek_str.startswith("v2:wrapped:"):
        raise VaultDecryptionError("Invalid wrapped DEK envelope header.")

    parts = wrapped_dek_str.split(":")
    if len(parts) != 4:
        raise VaultDecryptionError("Malformed wrapped DEK envelope payload.")

    try:
        nonce = base64.b64decode(parts[2])
        ciphertext = base64.b64decode(parts[3])
    except Exception as b64_err:
        raise VaultDecryptionError(f"Base64 decoding failed for wrapped DEK: {b64_err}")

    for candidate_kek in get_master_kek_candidates():
        try:
            aesgcm = AESGCM(candidate_kek)
            dek_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            if len(dek_bytes) == 32:
                return dek_bytes
        except (InvalidTag, Exception):
            continue

    raise VaultDecryptionError("Failed to unwrap workspace DEK with all candidate Master KEKs.")


def get_or_provision_workspace_dek(
    workspace_id: str,
    supabase: Optional[Any] = None,
    force_rotate: bool = False
) -> bytes:
    """
    Paranoia Layer 0 & 1: Resolves or provisions workspace Data Encryption Key (DEK).
    - Checks ephemeral in-memory cache first (TTL = 300s).
    - If missing or expired, unwraps from DB / in-memory store.
    - If workspace has no DEK, generates 32 random bytes, wraps with KEK, and persists.
    """
    clean_ws = str(workspace_id or "").strip()
    if not clean_ws:
        raise ValueError("workspace_id cannot be empty for DEK management")

    now = time.time()

    # 1. Check in-memory cache (Layer 1 Paranoia)
    if not force_rotate:
        with _dek_lock:
            if clean_ws in _DEK_CACHE:
                cached_arr, expire_at = _DEK_CACHE[clean_ws]
                if now < expire_at:
                    return bytes(cached_arr)
                else:
                    # Explicit memory zeroing on expiration
                    _zero_and_evict_dek(clean_ws)

    # 2. Lookup existing wrapped DEK from Supabase
    wrapped_dek: Optional[str] = None
    if supabase and not force_rotate:
        try:
            res = supabase.table("workspace_deks").select("wrapped_dek, key_version").eq("workspace_id", clean_ws).limit(1).execute()
            rows = getattr(res, "data", []) or []
            if rows and isinstance(rows[0], dict) and rows[0].get("wrapped_dek"):
                wrapped_dek = rows[0]["wrapped_dek"]
        except Exception as e:
            logger.debug(f"[EnvelopeEncryption] DB lookup notice for workspace {clean_ws}: {e}")

    # Fallback to in-memory store
    if not wrapped_dek and not force_rotate:
        with _dek_lock:
            if clean_ws in _IN_MEMORY_WORKSPACE_DEKS:
                wrapped_dek = _IN_MEMORY_WORKSPACE_DEKS[clean_ws]["wrapped_dek"]

    # 3. If exists, unwrap and cache
    if wrapped_dek and not force_rotate:
        dek_bytes = _unwrap_dek(wrapped_dek)
        with _dek_lock:
            _DEK_CACHE[clean_ws] = (bytearray(dek_bytes), now + DEK_CACHE_TTL_SECONDS)
        log_encryption_audit(clean_ws, "unwrap_dek", CURRENT_KEY_VERSION, "success", supabase)
        return dek_bytes

    # 4. Generate new DEK
    new_dek = os.urandom(32)
    active_kek = get_active_master_kek()
    new_wrapped = _wrap_dek(new_dek, active_kek)
    now_iso = datetime.now(timezone.utc).isoformat()

    record = {
        "workspace_id": clean_ws,
        "wrapped_dek": new_wrapped,
        "key_version": CURRENT_KEY_VERSION,
        "created_at": now_iso,
        "rotated_at": now_iso if force_rotate else None
    }

    if supabase:
        try:
            supabase.table("workspace_deks").upsert(record).execute()
        except Exception as e:
            logger.debug(f"[EnvelopeEncryption] DB upsert notice for workspace {clean_ws}: {e}")

    with _dek_lock:
        _IN_MEMORY_WORKSPACE_DEKS[clean_ws] = record
        _DEK_CACHE[clean_ws] = (bytearray(new_dek), now + DEK_CACHE_TTL_SECONDS)

    log_encryption_audit(
        clean_ws,
        "rotate_dek" if force_rotate else "provision_dek",
        CURRENT_KEY_VERSION,
        "success",
        supabase
    )
    return new_dek


def _zero_and_evict_dek(workspace_id: str):
    """Securely wipes and evicts DEK from in-memory cache in place."""
    if workspace_id in _DEK_CACHE:
        cached_arr, _ = _DEK_CACHE[workspace_id]
        # In-place heap memory wipe
        if isinstance(cached_arr, (bytearray, memoryview)):
            cached_arr[:] = b"\x00" * len(cached_arr)
        del _DEK_CACHE[workspace_id]


def clear_dek_cache_for_workspace(workspace_id: str):
    """Explicitly clears and wipes cached DEK for a workspace."""
    with _dek_lock:
        _zero_and_evict_dek(workspace_id)


# =============================================================================
# 3. ENCRYPTION & DECRYPTION ENVELOPE APIS
# =============================================================================

def encrypt_envelope(
    plaintext: Union[str, bytes],
    workspace_id: str,
    supabase: Optional[Any] = None
) -> str:
    """
    Paranoia Layer 0 & 2: Encrypts plaintext using workspace DEK via AES-256-GCM.
    - Plaintext is bound to workspace_id via Additional Authenticated Data (AAD).
    - Returns standardized envelope: v2:env:1:<nonce_b64>:<ciphertext_b64>.
    - Logs audit record without exposing plaintext.
    """
    if plaintext is None:
        raise ValueError("Plaintext cannot be None")

    clean_ws = str(workspace_id or "").strip()
    if not clean_ws:
        raise ValueError("workspace_id is required for envelope encryption")

    raw_bytes = plaintext.encode("utf-8") if isinstance(plaintext, str) else bytes(plaintext)
    dek_bytes = get_or_provision_workspace_dek(clean_ws, supabase=supabase)

    # 96-bit unique nonce per encryption
    nonce = os.urandom(NONCE_LENGTH)
    # AAD binds tenant identity to prevent cross-tenant ciphertext swapping
    aad = clean_ws.encode("utf-8")

    aesgcm = AESGCM(dek_bytes)
    ciphertext = aesgcm.encrypt(nonce, raw_bytes, aad)

    nonce_b64 = base64.b64encode(nonce).decode("utf-8")
    ct_b64 = base64.b64encode(ciphertext).decode("utf-8")

    envelope = f"{ENVELOPE_PREFIX}{CURRENT_KEY_VERSION}:{nonce_b64}:{ct_b64}"
    log_encryption_audit(clean_ws, "encrypt", CURRENT_KEY_VERSION, "success", supabase)
    return envelope


def decrypt_envelope(
    envelope_str: str,
    workspace_id: str,
    supabase: Optional[Any] = None
) -> str:
    """
    Paranoia Layer 0, 1 & 2: Decrypts envelope using workspace DEK.
    - Verifies GCM authentication tag against workspace_id AAD.
    - If ciphertext was encrypted under another workspace, decryption fails with VaultDecryptionError.
    - Supports transparent fallback for legacy formats.
    """
    if not envelope_str or not isinstance(envelope_str, str):
        raise ValueError("Envelope string cannot be empty")

    clean_ws = str(workspace_id or "").strip()
    if not clean_ws:
        raise ValueError("workspace_id is required for envelope decryption")

    clean_env = envelope_str.strip()

    # 1. Modern Envelope v2
    if clean_env.startswith(ENVELOPE_PREFIX):
        parts = clean_env.split(":")
        # Format: ['v2', 'env', '1', nonce_b64, ct_b64]
        if len(parts) != 5:
            raise VaultDecryptionError("Malformed envelope string structure")

        key_ver = int(parts[2])
        try:
            nonce = base64.b64decode(parts[3])
            ciphertext = base64.b64decode(parts[4])
        except Exception as b64_err:
            raise VaultDecryptionError(f"Base64 decoding failed for envelope: {b64_err}")

        dek_bytes = get_or_provision_workspace_dek(clean_ws, supabase=supabase)
        aad = clean_ws.encode("utf-8")

        try:
            aesgcm = AESGCM(dek_bytes)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
            log_encryption_audit(clean_ws, "decrypt", key_ver, "success", supabase)
            return plaintext_bytes.decode("utf-8")
        except InvalidTag:
            log_encryption_audit(clean_ws, "decrypt", key_ver, "denied_invalid_tag", supabase)
            raise VaultDecryptionError(
                "Decryption failed: Authentication tag verification failed or cross-tenant tampering detected."
            )
        except Exception as dec_err:
            log_encryption_audit(clean_ws, "decrypt", key_ver, f"failed:{str(dec_err)[:30]}", supabase)
            raise VaultDecryptionError(f"Envelope decryption error: {dec_err}")

    # 2. Transparent fallback for BYOK v1 (v1:gcm:...)
    if clean_env.startswith("v1:gcm:"):
        try:
            from knowledge.backend.services.byok_vault import decrypt_byok_key
            dec = decrypt_byok_key(clean_env)
            if dec:
                return dec
        except Exception as e:
            logger.debug(f"[EnvelopeEncryption] BYOK v1 fallback notice: {e}")

    # 3. Transparent fallback for pg_hex (\x...)
    if clean_env.startswith("\\x"):
        try:
            from core.backend.core.crypto import pg_hex_to_bytes, decrypt_bytes
            b = pg_hex_to_bytes(clean_env)
            return decrypt_bytes(b).decode("utf-8")
        except Exception as e:
            logger.debug(f"[EnvelopeEncryption] pg_hex fallback notice: {e}")

    # If unencrypted raw string passed, return safely
    return clean_env


# =============================================================================
# 4. ZERO-LEAKAGE AUDIT LOGGING & MASKING
# =============================================================================

def log_encryption_audit(
    workspace_id: str,
    operation: str,
    key_version: int,
    status: str = "success",
    supabase: Optional[Any] = None
):
    """
    Paranoia Layer 2: Records cryptographic operations with zero secret leakage.
    Guarantees no plaintexts, nonces, or DEKs are ever stored in audit rows.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "workspace_id": str(workspace_id or "unknown"),
        "operation": str(operation),
        "key_version": int(key_version),
        "status": str(status),
        "created_at": now_iso
    }

    if supabase:
        try:
            supabase.table("encryption_audit_log").insert(record).execute()
        except Exception:
            pass

    with _dek_lock:
        _IN_MEMORY_ENCRYPTION_AUDIT.insert(0, record)
        if len(_IN_MEMORY_ENCRYPTION_AUDIT) > 500:
            del _IN_MEMORY_ENCRYPTION_AUDIT[500:]


def mask_secret(secret: Optional[str]) -> str:
    """
    Masks secrets for safe presentation in dashboards / logs:
    Exposes only first 3 and last 3 characters with middle bullets.
    """
    if not secret or not isinstance(secret, str):
        return ""
    clean = secret.strip()
    if len(clean) <= 6:
        return "••••••"
    return f"{clean[:3]}••••••••{clean[-3:]}"
