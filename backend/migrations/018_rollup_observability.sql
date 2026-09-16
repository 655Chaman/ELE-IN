-- Migration 018: Rollup Job Observability

BEGIN;

-- 1. Add completed_at and metadata to processing_jobs if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='processing_jobs' AND column_name='completed_at') THEN
        ALTER TABLE processing_jobs ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='processing_jobs' AND column_name='metadata') THEN
        ALTER TABLE processing_jobs ADD COLUMN metadata JSONB;
    END IF;
END $$;

-- 3. Create daily_rollup_log
CREATE TABLE IF NOT EXISTS daily_rollup_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id UUID REFERENCES workspaces(id),
    stat_date DATE,
    rolled_up_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status TEXT,
    error_message TEXT
);

COMMIT;
