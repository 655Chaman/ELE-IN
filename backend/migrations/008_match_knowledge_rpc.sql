CREATE OR REPLACE FUNCTION public.match_knowledge(
    query_embedding vector(1536),
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
        1 - (kc.embedding <=> query_embedding) AS similarity
    FROM public.knowledge_chunks kc
    WHERE (p_workspace_id IS NULL OR kc.workspace_id = p_workspace_id)
      AND 1 - (kc.embedding <=> query_embedding) > match_threshold
    ORDER BY kc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
