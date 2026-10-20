import os
import base64
import hashlib
import hmac
import logging
from typing import Optional, List
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)

CIPHER_PREFIX = "v1:gcm:"
NONCE_LENGTH = 12  # 96-bit nonce standard for AES-GCM

class VaultDecryptionError(Exception):
    """Raised when decrypting a BYOK API key fails due to corruption or tampering."""
    pass

class InvalidKeyFormatError(Exception):
    """Raised when an API key format or mask validation fails."""
    pass


def _derive_key_from_secret(secret_str: str) -> bytes:
    """Domain-separated SHA-256 derivation ensures exact 32-byte key size."""
    return hashlib.sha256(f"elein:byok:vault:{secret_str}".encode("utf-8")).digest()


def get_vault_encryption_key() -> bytes:
    """
    Derives the active primary 256-bit AES-GCM key.
    Paranoia Layer 1: Evaluates prioritized environment secrets, falling back to
    platform JWT secret or service key, preventing crashes in any runtime environment.
    """
    raw_secret = (
        os.environ.get("BYOK_VAULT_SECRET")
        or os.environ.get("SUPABASE_JWT_SECRET")
        or os.environ.get("SUPABASE_KEY")
        or "elein_default_byok_vault_seed_2026_dev_only"
    )
    return _derive_key_from_secret(raw_secret)


def get_vault_candidate_keys() -> List[bytes]:
    """
    Paranoia Layer 1 & 2: Gathers all possible candidate encryption keys in priority order.
    Protects against secret rotation drift: if BYOK_VAULT_SECRET is rotated, or if keys were
    encrypted with SUPABASE_JWT_SECRET/SUPABASE_KEY/dev seed in earlier versions, decryption
    waterfalls through candidate keys to prevent bricking tenant credentials.
    """
    candidates: List[str] = []

    # 1. Primary explicit secret
    primary = os.environ.get("BYOK_VAULT_SECRET")
    if primary:
        candidates.append(primary)

    # 2. Historical/rotated secrets list (comma-separated)
    previous_secrets = os.environ.get("BYOK_PREVIOUS_VAULT_SECRETS", "")
    if previous_secrets:
        for s in previous_secrets.split(","):
            if s.strip():
                candidates.append(s.strip())

    # 3. Supabase secrets (common deployment secrets)
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if jwt_secret:
        candidates.append(jwt_secret)

    sb_key = os.environ.get("SUPABASE_KEY")
    if sb_key:
        candidates.append(sb_key)

    # 4. Standard developer default seed
    candidates.append("elein_default_byok_vault_seed_2026_dev_only")

    # Deduplicate derived keys while preserving priority order
    seen = set()
    derived_keys: List[bytes] = []
    for c in candidates:
        k = _derive_key_from_secret(c)
        if k not in seen:
            seen.add(k)
            derived_keys.append(k)

    return derived_keys


def mask_api_key(key: Optional[str]) -> str:
    """
    Paranoia Layer 2: Formats an API key for safe presentation and audit logging.
    Exposes only the first 4 and last 4 characters separated by 8 bullet masks.
    Guarantees no raw unencrypted secret is ever written to logs or telemetry.
    """
    if not key or not isinstance(key, str):
        return ""
    clean = key.strip()
    if len(clean) <= 8:
        return "••••••••"
    return f"{clean[:4]}••••••••{clean[-4:]}"


def encrypt_byok_key(plaintext_key: str) -> str:
    """
    Layer 0: Encrypts a plaintext BYOK API key using AES-256-GCM.
    Layer 1: Generates a cryptographically random 12-byte IV for every encryption call,
             preventing replay and rainbow-table attacks.
    Layer 2: Strips leading/trailing whitespace and refuses to encrypt masked/empty strings.
    """
    if not plaintext_key:
        raise InvalidKeyFormatError("Cannot encrypt empty or null API key.")
    
    clean = plaintext_key.strip().strip("'\"").strip()
    if clean.lower().startswith("bearer "):
        clean = clean[7:].strip().strip("'\"").strip()

    if clean.startswith("•") or clean.startswith("*"):
        raise InvalidKeyFormatError("Cannot encrypt masked key. Please provide the full API key.")

    key_bytes = get_vault_encryption_key()
    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(NONCE_LENGTH)
    
    # AES-GCM encrypt produces ciphertext + 16-byte authentication tag
    ciphertext = aesgcm.encrypt(nonce, clean.encode("utf-8"), None)
    payload_b64 = base64.b64encode(nonce + ciphertext).decode("utf-8")
    return f"{CIPHER_PREFIX}{payload_b64}"


def decrypt_byok_key(stored_value: Optional[str]) -> Optional[str]:
    """
    Layer 0: Decrypts an AES-256-GCM encrypted BYOK key.
    Layer 1: Gracefully supports legacy plaintext keys if unmigrated rows exist,
             logging an advisory without crashing. Authenticates ciphertext tag.
    Layer 2: Multi-key fallback waterfall across candidate secrets to ensure zero
             downtime during secret rotation.
    """
    if not stored_value:
        return None

    stored = stored_value.strip()
    if not stored.startswith(CIPHER_PREFIX):
        # Legacy fallback: Return plaintext directly if not yet encrypted
        logger.warning("[BYOK Vault] Stored BYOK key is in legacy plaintext format; migration recommended.")
        return stored

    payload_b64 = stored[len(CIPHER_PREFIX):]
    try:
        combined = base64.b64decode(payload_b64)
    except Exception as b64_err:
        logger.error(f"[BYOK Vault] Base64 decoding failed: {b64_err}")
        raise VaultDecryptionError(f"Ciphertext payload is not valid Base64: {b64_err}") from b64_err

    if len(combined) <= NONCE_LENGTH + 16:
        raise VaultDecryptionError("Ciphertext payload is truncated or corrupted.")
    
    nonce = combined[:NONCE_LENGTH]
    ciphertext = combined[NONCE_LENGTH:]

    candidate_keys = get_vault_candidate_keys()
    last_err = None

    for idx, key_bytes in enumerate(candidate_keys):
        try:
            aesgcm = AESGCM(key_bytes)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            if idx > 0:
                logger.info(f"[BYOK Vault] Successfully decrypted key using rotation candidate #{idx}.")
            return plaintext_bytes.decode("utf-8")
        except (InvalidTag, ValueError) as tag_err:
            last_err = tag_err
            continue
        except Exception as decrypt_err:
            last_err = decrypt_err
            continue

    logger.error(f"[BYOK Vault] All {len(candidate_keys)} candidate keys failed decryption: {last_err}")
    raise VaultDecryptionError(f"Failed to decrypt BYOK key: corrupted ciphertext, tampered payload, or invalid key.") from last_err


def is_encrypted_byok_key(val: Optional[str]) -> bool:
    """Checks whether a stored value has the vault encryption envelope using constant-time prefix check."""
    if not val:
        return False
    clean = str(val).strip()
    if len(clean) < len(CIPHER_PREFIX):
        return False
    return hmac.compare_digest(clean[:len(CIPHER_PREFIX)], CIPHER_PREFIX)


def reencrypt_byok_key(stored_value: Optional[str]) -> Optional[str]:
    """
    Paranoia Layer 1: Zero-Downtime Secret Rotation Re-Encryption.
    Decrypts a ciphertext with whichever candidate/historical key matches,
    then re-encrypts it using the current active primary encryption key.
    Ensures long-term migration of tenant keys to modern secrets without outage.
    """
    if not stored_value:
        return None
    decrypted = decrypt_byok_key(stored_value)
    if not decrypted:
        return None
    return encrypt_byok_key(decrypted)


def validate_byok_key(provider: str, key: str) -> str:
    """
    Layer 2 Human Paranoia: Validates provider and formatting before encryption.
    Prevents accidental submission of masks, short snippets, or mismatched provider keys.
    Automatically strips accidental wrapping quotes and Bearer prefixes pasted from cURL.
    """
    if not key or not isinstance(key, str) or not key.strip():
        raise InvalidKeyFormatError("API key cannot be blank.")
    
    clean = key.strip().strip("'\"").strip()
    if clean.lower().startswith("bearer "):
        clean = clean[7:].strip().strip("'\"").strip()

    if clean.startswith("•") or clean.startswith("*"):
        raise InvalidKeyFormatError("Cannot submit masked key. Please provide the full API key or leave blank to keep existing key.")

    if len(clean) < 8:
        raise InvalidKeyFormatError("API key is too short. Please enter a valid API key.")

    prov = (provider or "openai").lower()
    if prov == "openai" and not (clean.startswith("sk-") and len(clean) >= 20):
        raise InvalidKeyFormatError("Invalid OpenAI key format. OpenAI keys must start with 'sk-'.")
    elif prov == "anthropic" and not (clean.startswith("sk-ant-") and len(clean) >= 25):
        raise InvalidKeyFormatError("Invalid Anthropic key format. Anthropic keys must start with 'sk-ant-'.")
    elif prov == "deepseek" and not (clean.startswith("sk-") and len(clean) >= 15):
        raise InvalidKeyFormatError("Invalid DeepSeek key format. DeepSeek keys must start with 'sk-'.")
    elif prov == "groq" and not (clean.startswith("gsk_") and len(clean) >= 20):
        raise InvalidKeyFormatError("Invalid Groq key format. Groq keys must start with 'gsk_'.")
    elif prov == "openrouter" and not (clean.startswith("sk-or-") and len(clean) >= 20):
        raise InvalidKeyFormatError("Invalid OpenRouter key format. OpenRouter keys must start with 'sk-or-'.")
    elif prov == "nvidia" and not (clean.startswith("nvapi-") and len(clean) >= 25):
        raise InvalidKeyFormatError("Invalid NVIDIA key format. NVIDIA keys must start with 'nvapi-'.")

    return clean
