-- 047_vector_dimension_fix.sql

-- 1. Fix the actual active storage table `knowledge_chunks`.
-- Drop the index first, clear incompatible 1536-dim data, alter column to 2048, and recreate as halfvec(2048) index.
DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;

-- Clear incompatible 1536-dim embeddings so the cast to 2048 doesn't fail.
-- These will be re-generated next time the asset is processed.
UPDATE public.knowledge_chunks SET embedding = NULL WHERE embedding IS NOT NULL;

-- Alter column to store 2048 dimensions to match nvidia/nemotron-3-embed-1b.
ALTER TABLE public.knowledge_chunks 
ALTER COLUMN embedding TYPE vector(2048);

-- Recreate index using halfvec for performance
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx 
ON public.knowledge_chunks USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);

-- 2. Fix the RPC function used for semantic search.
-- The signature must expect vector(2048), and the distance calculation MUST cast to halfvec
-- to correctly utilize the expression index created above.
CREATE OR REPLACE FUNCTION public.match_knowledge(
    query_embedding vector(2048),
    match_threshold float,
    match_count int,
    p_workspace_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    asset_id uuid,
    content text,
    similarity float
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT
        kc.id,
        kc.asset_id,
        kc.content,
        1 - ((kc.embedding::halfvec(2048)) <=> (query_embedding::halfvec(2048))) AS similarity
    FROM public.knowledge_chunks kc
    WHERE (p_workspace_id IS NULL OR kc.workspace_id = p_workspace_id)
      AND 1 - ((kc.embedding::halfvec(2048)) <=> (query_embedding::halfvec(2048))) > match_threshold
    ORDER BY (kc.embedding::halfvec(2048)) <=> (query_embedding::halfvec(2048))
    LIMIT match_count;
END;
$$;
