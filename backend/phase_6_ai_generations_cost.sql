-- ⚠️  ORPHAN MIGRATION FILE — NOT TRACKED BY apply_migrations.py
-- This file lives outside the migrations/ directory and will NOT be applied automatically.
-- If this schema change is required, move this file into backend/migrations/ with a proper
-- sequential name and add it to the ordered list in backend/scripts/apply_migrations.py.
-- File: phase_6_ai_generations_cost.sql
ALTER TABLE public.ai_generations ADD COLUMN IF NOT EXISTS cost NUMERIC(10, 6) DEFAULT 0.0;
