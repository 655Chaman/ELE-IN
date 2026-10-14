import os
import base64
import hashlib
import logging
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

CIPHER_PREFIX = "v1:gcm:"
NONCE_LENGTH = 12  # 96-bit nonce standard for AES-GCM

class VaultDecryptionError(Exception):
    """Raised when decrypting a BYOK API key fails due to corruption or tampering."""
    pass

class InvalidKeyFormatError(Exception):
    """Raised when an API key format or mask validation fails."""
    pass


def get_vault_encryption_key() -> bytes:
    """
    Derives a deterministic 256-bit AES-GCM key.
    Paranoia Layer 1: Evaluates prioritized environment secrets, falling back to
    platform JWT secret or service key, preventing crashes in any runtime environment.
    """
    raw_secret = (
        os.environ.get("BYOK_VAULT_SECRET")
        or os.environ.get("SUPABASE_JWT_SECRET")
        or os.environ.get("SUPABASE_KEY")
        or "elein_default_byok_vault_seed_2026_dev_only"
    )
    # Domain-separated SHA-256 derivation ensures 32-byte key size
    return hashlib.sha256(f"elein:byok:vault:{raw_secret}".encode("utf-8")).digest()


def encrypt_byok_key(plaintext_key: str) -> str:
    """
    Layer 0: Encrypts a plaintext BYOK API key using AES-256-GCM.
    Layer 1: Generates a cryptographically random 12-byte IV for every encryption call,
             preventing replay and rainbow-table attacks.
    Layer 2: Strips leading/trailing whitespace and refuses to encrypt masked/empty strings.
    """
    if not plaintext_key:
        raise InvalidKeyFormatError("Cannot encrypt empty or null API key.")
    
    clean = plaintext_key.strip()
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
        if len(combined) <= NONCE_LENGTH + 16:
            raise VaultDecryptionError("Ciphertext payload is truncated or corrupted.")
        
        nonce = combined[:NONCE_LENGTH]
        ciphertext = combined[NONCE_LENGTH:]
        
        key_bytes = get_vault_encryption_key()
        aesgcm = AESGCM(key_bytes)
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"[BYOK Vault] Decryption failure: {e}")
        raise VaultDecryptionError(f"Failed to decrypt BYOK key: {str(e)}") from e


def is_encrypted_byok_key(val: Optional[str]) -> bool:
    """Checks whether a stored value has the vault encryption envelope."""
    if not val:
        return False
    return str(val).strip().startswith(CIPHER_PREFIX)


def validate_byok_key(provider: str, key: str) -> str:
    """
    Layer 2 Human Paranoia: Validates provider and formatting before encryption.
    Prevents accidental submission of masks, short snippets, or mismatched provider keys.
    """
    if not key or not isinstance(key, str):
        raise InvalidKeyFormatError("API key cannot be blank.")
    
    clean = key.strip()
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

    return clean
