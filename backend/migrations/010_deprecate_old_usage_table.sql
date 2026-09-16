DROP TRIGGER IF EXISTS action_log_increment_daily_usage ON public.action_log;
DROP FUNCTION IF EXISTS public.increment_daily_usage();

COMMENT ON TABLE public.account_daily_usage IS 'DEPRECATED: Use account_daily_action_counts instead. This table is kept for historical data only.';
