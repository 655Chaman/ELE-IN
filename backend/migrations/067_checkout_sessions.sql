CREATE TABLE IF NOT EXISTS public.checkout_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    package_id TEXT NOT NULL,
    credits INT NOT NULL DEFAULT 0,
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.checkout_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own checkout sessions" ON public.checkout_sessions FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));
