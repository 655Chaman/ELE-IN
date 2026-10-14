-- Migration 089: Autonomous Executive Calendar Concierge & Frictionless Meeting Booking Engine
-- Description: Creates tables for meeting booking records, rep availability profiles, timezone slot holds, and booking tokens.
-- Paranoia Framework: Idempotent DDL with IF NOT EXISTS, composite indexes, and workspace tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.meeting_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    lead_email TEXT NOT NULL,
    lead_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    assigned_rep_name TEXT NOT NULL DEFAULT 'Account Executive',
    assigned_rep_email TEXT NOT NULL,
    meeting_title TEXT NOT NULL DEFAULT 'Discovery & Strategy Session (30 min)',
    meeting_duration_minutes INT NOT NULL DEFAULT 30,
    prospect_timezone TEXT NOT NULL DEFAULT 'America/New_York',
    proposed_slots JSONB NOT NULL DEFAULT '[]'::jsonb,
    confirmed_slot TIMESTAMPTZ,
    meeting_link TEXT,
    calendar_provider TEXT NOT NULL DEFAULT 'google_calendar' CHECK (calendar_provider IN ('google_calendar', 'outlook', 'cal_com', 'calendly')),
    status TEXT NOT NULL DEFAULT 'slots_proposed' CHECK (status IN ('slots_proposed', 'confirmed', 'rescheduled', 'cancelled', 'completed')),
    confirmation_token TEXT UNIQUE NOT NULL,
    booking_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.rep_calendar_availability (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    rep_name TEXT NOT NULL,
    rep_email TEXT NOT NULL,
    working_hours_start TEXT NOT NULL DEFAULT '09:00',
    working_hours_end TEXT NOT NULL DEFAULT '17:00',
    working_days JSONB NOT NULL DEFAULT '[1, 2, 3, 4, 5]'::jsonb,
    rep_timezone TEXT NOT NULL DEFAULT 'America/New_York',
    buffer_minutes INT NOT NULL DEFAULT 15,
    max_meetings_per_day INT NOT NULL DEFAULT 6,
    custom_booking_link TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid calendar querying
CREATE INDEX IF NOT EXISTS idx_meeting_bookings_ws ON public.meeting_bookings(workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meeting_bookings_token ON public.meeting_bookings(confirmation_token);
CREATE INDEX IF NOT EXISTS idx_rep_availability_ws ON public.rep_calendar_availability(workspace_id, rep_email);

-- Enable Row-Level Security
ALTER TABLE public.meeting_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rep_calendar_availability ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'meeting_bookings' AND policyname = 'meeting_bookings_ws_policy') THEN
        CREATE POLICY meeting_bookings_ws_policy ON public.meeting_bookings FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'rep_calendar_availability' AND policyname = 'rep_calendar_availability_ws_policy') THEN
        CREATE POLICY rep_calendar_availability_ws_policy ON public.rep_calendar_availability FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
