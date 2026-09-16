import os
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# PARANOIA LAYER 2: DECRYPTION ISOLATION
# The Web API must NEVER have the COOKIE_PRIVATE_KEY. 
# If you are tempted to add it to the Web API .env to "fix" an endpoint that wants to spin up Playwright, STOP.
# All Playwright tasks MUST be pushed to the processing_jobs queue.
# Giving the Web API the private key compromises the entire security model.

pub_key_b64 = os.environ.get('COOKIE_PUBLIC_KEY')
priv_key_b64 = os.environ.get('COOKIE_PRIVATE_KEY')

if not pub_key_b64:
    raise RuntimeError("COOKIE_PUBLIC_KEY environment variable is missing")

pub_key_bytes = base64.b64decode(pub_key_b64)
_public_key = serialization.load_pem_public_key(pub_key_bytes)

_private_key = None
if priv_key_b64:
    priv_key_bytes = base64.b64decode(priv_key_b64)
    _private_key = serialization.load_pem_private_key(priv_key_bytes, password=None)

class SecureMemoryWrapper:
    def __init__(self, value: str):
        self._value = value
        
    def __str__(self):
        return "<REDACTED_SECRET>"
        
    def __repr__(self):
        return "<REDACTED_SECRET>"

class VaultDecryptionError(Exception):
    pass

def generate_dek() -> str:
    return base64.b64encode(os.urandom(32)).decode('utf-8')

def encrypt_bytes(plaintext: bytes, dek: bytes = None) -> bytes:
    aes_key = dek if dek else os.urandom(32)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    
    if dek:
        enc_key_len = (0).to_bytes(2, 'big')
        return enc_key_len + nonce + ciphertext
    else:
        enc_key = _public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        enc_key_len = len(enc_key).to_bytes(2, 'big')
        return enc_key_len + enc_key + nonce + ciphertext

def decrypt_bytes(ciphertext: bytes, dek: bytes = None) -> bytes:
    try:
        enc_key_len = int.from_bytes(ciphertext[:2], 'big')
        
        if dek:
            aes_key = dek
            nonce = ciphertext[2+enc_key_len : 2+enc_key_len+12]
            ct = ciphertext[2+enc_key_len+12:]
        else:
            if not _private_key:
                raise RuntimeError("Decryption is physically impossible on this node: Private key missing.")
            
            enc_key = ciphertext[2:2+enc_key_len]
            nonce = ciphertext[2+enc_key_len : 2+enc_key_len+12]
            ct = ciphertext[2+enc_key_len+12:]
            
            aes_key = _private_key.decrypt(
                enc_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
        aesgcm = AESGCM(aes_key)
        return aesgcm.decrypt(nonce, ct, None)
    except (ValueError, KeyError) as e:
        raise VaultDecryptionError(f"Decryption failed: {str(e)}") from e
