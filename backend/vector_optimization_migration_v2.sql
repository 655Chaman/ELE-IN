-- ⚠️  ORPHAN MIGRATION FILE — NOT TRACKED BY apply_migrations.py
-- This file lives outside the migrations/ directory and will NOT be applied automatically.
-- If this schema change is required, move this file into backend/migrations/ with a proper
-- sequential name and add it to the ordered list in backend/scripts/apply_migrations.py.
-- File: vector_optimization_migration_v2.sql
-- Trigger function
CREATE OR REPLACE FUNCTION update_asset_chunk_count()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE public.knowledge_assets
    SET chunk_count = chunk_count + 1
    WHERE id = NEW.asset_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE public.knowledge_assets
    SET chunk_count = chunk_count - 1
    WHERE id = OLD.asset_id;
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS trg_update_asset_chunk_count ON public.knowledge_vectors;
CREATE TRIGGER trg_update_asset_chunk_count
AFTER INSERT OR DELETE ON public.knowledge_vectors
FOR EACH ROW EXECUTE FUNCTION update_asset_chunk_count();

-- Backfill: Reconcile chunk_count for all existing assets
UPDATE public.knowledge_assets ka
SET chunk_count = (
    SELECT COUNT(*) FROM public.knowledge_vectors kv WHERE kv.asset_id = ka.id
);
