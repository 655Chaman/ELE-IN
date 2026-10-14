ALTER TABLE public.processing_jobs
ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX uq_processing_jobs_idempotency ON public.processing_jobs(idempotency_key);
