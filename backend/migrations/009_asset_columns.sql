ALTER TABLE public.knowledge_assets
ADD COLUMN IF NOT EXISTS source_url TEXT,
ADD COLUMN IF NOT EXISTS error_msg TEXT;
