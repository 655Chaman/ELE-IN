-- PARANOIA FRAMEWORK: Layer 1 Environmental
-- Deduplicate knowledge_assets before applying the UNIQUE constraint.
-- If the bug was abused, there are duplicate (workspace_id, source_url) pairs.
-- We keep the most recent one. NULL source_urls are ignored (Postgres allows multiple NULLs in unique constraints).

DELETE FROM public.knowledge_assets a
USING (
    SELECT id,
           ROW_NUMBER() OVER(PARTITION BY workspace_id, source_url ORDER BY created_at DESC, id DESC) as rn
    FROM public.knowledge_assets
    WHERE source_url IS NOT NULL
) b
WHERE a.id = b.id AND b.rn > 1;

-- PARANOIA FRAMEWORK: Layer 0 Foundation
-- Add UNIQUE constraint to prevent double-click scrape sync race
ALTER TABLE public.knowledge_assets
  ADD CONSTRAINT unique_workspace_url UNIQUE (workspace_id, source_url);

-- Fix The Vector DB Meltdown (Missing Cascading Indexes on knowledge_chunks)
CREATE INDEX IF NOT EXISTS idx_kc_asset_id ON public.knowledge_chunks(asset_id);
CREATE INDEX IF NOT EXISTS idx_kc_workspace_id ON public.knowledge_chunks(workspace_id);

-- Fix The Ghost Job Processing Bug (Orphaned jobs)
-- Currently asset_id in processing_jobs has no FK. We add one with CASCADE.
ALTER TABLE public.processing_jobs 
  ADD CONSTRAINT fk_processing_jobs_asset 
  FOREIGN KEY (asset_id) 
  REFERENCES public.knowledge_assets(id) 
  ON DELETE CASCADE;

-- And per Paranoia framework, EVERY cascading key needs an index!
CREATE INDEX IF NOT EXISTS idx_pj_asset_id ON public.processing_jobs(asset_id);
