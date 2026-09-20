-- 046_knowledge_synthesis_schema.sql

-- The original 002_knowledge_base.sql migration missed these columns on the live table, 
-- but they were added to knowledge_synthesis_drafts. This syncs the schema so the 
-- pipeline can successfully copy drafts to live.

ALTER TABLE public.knowledge_synthesis 
ADD COLUMN IF NOT EXISTS target_customer_profile TEXT,
ADD COLUMN IF NOT EXISTS key_differentiators JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS proof_points JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS primary_pain_points_solved JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS generated_from_vector_count INT DEFAULT 0;

-- Also update knowledge_vectors to match the 2048 dimensions of nvidia/nemotron-3-embed-1b.
-- Note: If you have an existing HNSW or IVFFlat index on this column, you may need to DROP it first 
-- before altering the type, and then RECREATE it.
ALTER TABLE public.knowledge_vectors 
ALTER COLUMN embedding TYPE vector(2048);
