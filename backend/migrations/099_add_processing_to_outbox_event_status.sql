-- ==============================================================================
-- MIGRATION: 099_add_processing_to_outbox_event_status
-- PARANOIA FRAMEWORK: Layer 1 (Environmental Failure Analysis)
-- Adds 'processing' value to outbox_event_status enum if not already present.
-- Prevents 22P02 invalid input value errors when worker claims outbox events.
-- ==============================================================================

DO $$
BEGIN
    ALTER TYPE public.outbox_event_status ADD VALUE IF NOT EXISTS 'processing';
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
    WHEN undefined_object THEN
        -- If outbox_event_status enum doesn't exist, create it with all statuses
        CREATE TYPE public.outbox_event_status AS ENUM (
            'pending',
            'processing',
            'delivered',
            'failed',
            'skipped',
            'suspended'
        );
END $$;
