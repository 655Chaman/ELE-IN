CREATE TABLE IF NOT EXISTS public.notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  user_id uuid NOT NULL,
  title text NOT NULL,
  body text NOT NULL,
  link text NULL,
  event_type text NOT NULL,
  read_at timestamptz NULL,
  outbox_event_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_ws_user_created ON public.notifications(workspace_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON public.notifications(user_id, read_at);

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS notifications_ws_read ON public.notifications;
CREATE POLICY notifications_ws_read ON public.notifications FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()) AND user_id = auth.uid());

DROP POLICY IF EXISTS notifications_ws_update ON public.notifications;
CREATE POLICY notifications_ws_update ON public.notifications FOR UPDATE USING (workspace_id IN (SELECT public.my_workspace_ids()) AND user_id = auth.uid()) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) AND user_id = auth.uid());

NOTIFY pgrst, 'reload schema';
