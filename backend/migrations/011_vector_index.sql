-- ==============================================================================
-- Migration: 011_vector_index
-- Description: Adds an HNSW vector index to the knowledge_chunks embedding column
-- to prevent full table scans and significantly speed up similarity search.
-- ==============================================================================

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx 
ON public.knowledge_chunks USING hnsw (embedding vector_cosine_ops);
