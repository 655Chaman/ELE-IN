-- 1. Create the agencies table
CREATE TABLE public.agencies (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    name               TEXT NOT NULL,
    stripe_customer_id TEXT UNIQUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Create agency members
CREATE TABLE public.agency_members (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id  UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'member', -- 'owner' | 'admin' | 'member'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agency_member UNIQUE (agency_id, user_id)
);

-- 3. Create explicit client access for 'member' role
CREATE TABLE public.agency_client_access (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_member_id UUID NOT NULL REFERENCES public.agency_members(id) ON DELETE CASCADE,
    workspace_id     UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_client_access UNIQUE (agency_member_id, workspace_id)
);

-- 4. Link workspaces to an agency
ALTER TABLE public.workspaces 
ADD COLUMN IF NOT EXISTS agency_id UUID REFERENCES public.agencies(id) ON DELETE CASCADE;

-- 5. Update my_workspace_ids()
CREATE OR REPLACE FUNCTION public.my_workspace_ids()
RETURNS SETOF UUID LANGUAGE sql STABLE SECURITY DEFINER AS $$
    -- a) Direct workspace membership (standalone clients or explicitly invited users)
    SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
    
    UNION
    
    -- b) Agency inheritance (full access for owners and admins)
    SELECT w.id FROM public.workspaces w
    JOIN public.agency_members am ON w.agency_id = am.agency_id
    WHERE am.user_id = auth.uid() AND am.role IN ('owner', 'admin')

    UNION

    -- c) Explicit client access (for agency 'member' role)
    SELECT aca.workspace_id FROM public.agency_client_access aca
    JOIN public.agency_members am ON aca.agency_member_id = am.id
    WHERE am.user_id = auth.uid();
$$;

-- RLS for agencies
ALTER TABLE public.agencies ENABLE ROW LEVEL SECURITY;
CREATE POLICY agencies_access ON public.agencies FOR ALL USING (
    owner_id = auth.uid() 
    OR id IN (SELECT agency_id FROM public.agency_members WHERE user_id = auth.uid())
);

ALTER TABLE public.agency_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY agency_members_access ON public.agency_members FOR ALL USING (
    agency_id IN (SELECT id FROM public.agencies WHERE owner_id = auth.uid())
    OR user_id = auth.uid()
    OR agency_id IN (SELECT agency_id FROM public.agency_members WHERE user_id = auth.uid() AND role IN ('owner', 'admin'))
);

ALTER TABLE public.agency_client_access ENABLE ROW LEVEL SECURITY;
CREATE POLICY agency_client_access_policy ON public.agency_client_access FOR ALL USING (
    agency_member_id IN (
        SELECT am.id FROM public.agency_members am
        WHERE am.agency_id IN (SELECT agency_id FROM public.agency_members WHERE user_id = auth.uid() AND role IN ('owner', 'admin'))
        OR am.user_id = auth.uid()
    )
);
