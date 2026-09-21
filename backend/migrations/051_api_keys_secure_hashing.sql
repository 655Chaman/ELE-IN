-- 1. Add scopes column and ensure key_hash is unique
ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS scopes jsonb DEFAULT '["extension:all"]'::jsonb;

-- 2. Data Migration: Hash existing plaintext keys in place
-- Using pgcrypto to hash the existing EXT_ plaintext hashes with SHA256
CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE public.api_keys
SET key_hash = encode(digest(key_hash, 'sha256'), 'hex')
WHERE key_hash LIKE 'EXT_%';

-- 3. Cleanup: Drop the dangerous plaintext column
ALTER TABLE public.api_keys DROP COLUMN IF EXISTS api_key;
