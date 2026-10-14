-- Migration 078: Agency Credit Delegations & Sub-Account Quota Management
-- Paranoia Framework: Layer 0 (Foundational), Layer 1 (Deadlock-Free Locking & Atomicity)

-- 1. Ensure master_workspace_id exists on public.agencies
ALTER TABLE public.agencies 
ADD COLUMN IF NOT EXISTS master_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL;

-- 2. Add allocation tracking columns to public.workspaces
ALTER TABLE public.workspaces
ADD COLUMN IF NOT EXISTS allocated_credit_budget INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS monthly_credit_quota INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS exhaustion_alert_threshold INT NOT NULL DEFAULT 100;

-- 3. Create agency_credit_allocations audit ledger
CREATE TABLE IF NOT EXISTS public.agency_credit_allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    client_workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    from_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    amount INT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'manual_allocation', -- 'manual_allocation', 'reclaim', 'monthly_recurring'
    allocated_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agency_allocations_agency_id ON public.agency_credit_allocations(agency_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agency_allocations_client_ws ON public.agency_credit_allocations(client_workspace_id);

ALTER TABLE public.agency_credit_allocations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE tablename = 'agency_credit_allocations' 
    AND policyname = 'agency_credit_allocations_isolation'
  ) THEN
    CREATE POLICY agency_credit_allocations_isolation ON public.agency_credit_allocations
      FOR ALL USING (true);
  END IF;
END $$;

-- 4. Deadlock-free atomic transfer RPC for agency credit delegations
CREATE OR REPLACE FUNCTION public.transfer_agency_credits_safely(
    p_agency_id UUID,
    p_from_workspace_id UUID,
    p_to_workspace_id UUID,
    p_amount INT,
    p_action_type TEXT,
    p_allocated_by UUID,
    p_note TEXT DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_from_balance INT;
    v_to_balance INT;
    v_new_from_balance INT;
    v_new_to_balance INT;
BEGIN
    IF p_amount <= 0 THEN
        RETURN jsonb_build_object('success', false, 'reason', 'invalid_amount');
    END IF;

    -- Paranoia Layer 1: Enforce deterministic UUID lock order to eliminate deadlock risks
    IF p_from_workspace_id < p_to_workspace_id THEN
        SELECT data_cleaning_credits INTO v_from_balance FROM public.workspaces WHERE id = p_from_workspace_id FOR UPDATE;
        SELECT data_cleaning_credits INTO v_to_balance FROM public.workspaces WHERE id = p_to_workspace_id FOR UPDATE;
    ELSE
        SELECT data_cleaning_credits INTO v_to_balance FROM public.workspaces WHERE id = p_to_workspace_id FOR UPDATE;
        SELECT data_cleaning_credits INTO v_from_balance FROM public.workspaces WHERE id = p_from_workspace_id FOR UPDATE;
    END IF;

    IF v_from_balance IS NULL OR v_to_balance IS NULL THEN
        RETURN jsonb_build_object('success', false, 'reason', 'workspace_not_found');
    END IF;

    -- Check available balance in source workspace
    IF v_from_balance < p_amount THEN
        RETURN jsonb_build_object('success', false, 'reason', 'insufficient_balance', 'available', v_from_balance);
    END IF;

    v_new_from_balance := v_from_balance - p_amount;
    v_new_to_balance := v_to_balance + p_amount;

    -- Update balances
    UPDATE public.workspaces SET data_cleaning_credits = v_new_from_balance WHERE id = p_from_workspace_id;
    UPDATE public.workspaces SET data_cleaning_credits = v_new_to_balance WHERE id = p_to_workspace_id;

    -- Update allocated_credit_budget tracking on the recipient if this is an allocation
    IF p_action_type = 'manual_allocation' OR p_action_type = 'monthly_recurring' THEN
        UPDATE public.workspaces 
        SET allocated_credit_budget = allocated_credit_budget + p_amount 
        WHERE id = p_to_workspace_id;
    ELSIF p_action_type = 'reclaim' THEN
        UPDATE public.workspaces 
        SET allocated_credit_budget = GREATEST(0, allocated_credit_budget - p_amount) 
        WHERE id = p_from_workspace_id;
    END IF;

    -- Record in audit ledger
    INSERT INTO public.agency_credit_allocations (
        agency_id, client_workspace_id, from_workspace_id, amount, action_type, allocated_by, note
    ) VALUES (
        p_agency_id, 
        CASE WHEN p_action_type = 'reclaim' THEN p_from_workspace_id ELSE p_to_workspace_id END,
        p_from_workspace_id,
        CASE WHEN p_action_type = 'reclaim' THEN -p_amount ELSE p_amount END,
        p_action_type,
        p_allocated_by,
        p_note
    );

    RETURN jsonb_build_object(
        'success', true,
        'from_balance', v_new_from_balance,
        'to_balance', v_new_to_balance
    );
END;
$$;
