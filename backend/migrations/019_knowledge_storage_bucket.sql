INSERT INTO storage.buckets (id, name, public)
VALUES ('knowledge-files', 'knowledge-files', false)
ON CONFLICT (id) DO NOTHING;
