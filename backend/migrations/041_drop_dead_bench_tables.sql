BEGIN;

-- Roadmap Item #5: Drop completely unreferenced benchmark tables
DROP TABLE IF EXISTS public.bench_accounts CASCADE;
DROP TABLE IF EXISTS public.bench_campaigns CASCADE;
DROP TABLE IF EXISTS public.bench_ces CASCADE;
DROP TABLE IF EXISTS public.bench_conc_accounts CASCADE;
DROP TABLE IF EXISTS public.bench_conc_campaigns CASCADE;
DROP TABLE IF EXISTS public.bench_conc_ces CASCADE;
DROP TABLE IF EXISTS public.bench_conc_enrollments CASCADE;
DROP TABLE IF EXISTS public.bench_conc_workspaces CASCADE;
DROP TABLE IF EXISTS public.bench_enrollments CASCADE;
DROP TABLE IF EXISTS public.bench_results CASCADE;
DROP TABLE IF EXISTS public.bench_workspaces CASCADE;

COMMIT;
