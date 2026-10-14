-- Migration: 085_lead_list_dynamic_segmentation
-- Description: Add metadata and dynamic segmentation configuration support to lead_lists table.
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework).

ALTER TABLE public.lead_lists
ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';

COMMENT ON COLUMN public.lead_lists.metadata IS 'Stores dynamic rule AST criteria, auto-enrollment campaign bindings, and segment audit history.';
