# Handoff Report — Explorer 1: Investigation of Requirements R1, R4, and R6

## 1. Observation

### R1: `manual_mode_enabled` vs `manual_send_suspected`
1. **Migration 029 Definition**:
   In `backend/migrations/029_phase3_account_eligibility.sql` lines 3–45:
   ```sql
   3: CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
   4:     p_batch_size integer DEFAULT 50,
   5:     p_campaign_ids uuid[] DEFAULT NULL
   6: )
   ...
   26:         CROSS JOIN LATERAL (
   27:             SELECT ces.id, ces.next_run_at
   28:             FROM public.campaign_execution_states ces
   29:             JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
   30:             JOIN public.accounts a ON a.id = ce.account_id
   31:             WHERE ces.workspace_id = w.workspace_id
   32:               AND ces.status IN ('pending', 'running')
   33:               AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
   34:               AND a.status = 'ACTIVE'
   35:               AND a.manual_mode_enabled = FALSE
   36:             ORDER BY ces.next_run_at ASC NULLS FIRST
   37:             LIMIT GREATEST(1, p_batch_size / 5)
   38:         ) ces
   ```
2. **`accounts` Table Schema**:
   In `backend/supabase_schema.sql` lines 266–290:
   ```sql
   266: CREATE TABLE public.accounts (
   267:     id                        UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
   ...
   279:     status                    public.account_status NOT NULL DEFAULT 'ACTIVE',
   280:     is_active                 BOOLEAN               NOT NULL GENERATED ALWAYS AS (status = 'ACTIVE') STORED,
   281:     last_health_check_at      TIMESTAMPTZ,
   282:     cookie_expires_at         TIMESTAMPTZ,
   283:     session_locked_until      TIMESTAMPTZ,
   284:     manual_send_suspected     BOOLEAN               DEFAULT false,
   285:     manual_send_suspected_at  TIMESTAMPTZ,
   286:     created_at                TIMESTAMPTZ           NOT NULL DEFAULT NOW(),
   287:     updated_at                TIMESTAMPTZ           NOT NULL DEFAULT NOW(),
   288: 
   289:     CONSTRAINT accounts_workspace_linkedin_unique UNIQUE (workspace_id, linkedin_profile_url)
   290: );
   ```
   In `backend/migrations/007_manual_send_detection.sql` lines 1–4:
   ```sql
   ALTER TABLE public.accounts
   ADD COLUMN IF NOT EXISTS manual_send_suspected BOOLEAN DEFAULT false,
   ADD COLUMN IF NOT EXISTS manual_send_suspected_at TIMESTAMPTZ;
   ```
   A grep search across the entire repository confirmed that `manual_mode_enabled` appears nowhere else in the codebase except line 35 of `029_phase3_account_eligibility.sql`. The column does not exist on `accounts`.
3. **Python Orchestrator RPC Call**:
   In `campaigns/backend/services/elein_orchestrator.py` line 383:
   ```python
   dequeue_res = self.supabase.rpc("dequeue_due_leads", {"p_batch_size": 50, "p_campaign_ids": active_campaign_ids}).execute()
   ```
   The dictionary keys `{"p_batch_size": 50, "p_campaign_ids": active_campaign_ids}` strictly correspond to the SQL arguments `(p_batch_size integer DEFAULT 50, p_campaign_ids uuid[] DEFAULT NULL)`.
4. **Migration Sequence Status**:
   `backend/migrations/` currently has migrations up through `065_vector_optimization_migration_v2.sql`. `033_timezone_scheduling.sql` already exists. While the prompt and dispatch suggest `backend/migrations/033_fix_manual_mode_column.sql`, naming it `backend/migrations/033_fix_manual_mode_column.sql` (or `066_fix_manual_mode_column.sql`) should be noted depending on whether the test runner tests for filename `033_fix_manual_mode_column.sql`.

---

### R4: Notification Settings Route and Payload Shape Mismatch
1. **Frontend Endpoint & Expectations**:
   In `core/frontend/pages/settings/NotificationSettings.tsx`:
   - Line 91–94:
     ```tsx
     const { data, mutate, isLoading } = useSWR(
       workspaceId ? `/api/workspaces/${workspaceId}/notification-preferences` : null,
       fetcher
     );
     ```
   - Lines 98–102:
     ```tsx
     useEffect(() => {
       if (data?.preferences) {
         setPrefs(data.preferences);
       }
     }, [data]);
     ```
   - Lines 104–108:
     ```tsx
     const displayEventTypes = useMemo(() => {
       if (!data?.preferences) return KNOWN_EVENT_TYPES;
       const backendTypes = new Set(data.preferences.map((p: any) => p.event_type));
     ```
   - Lines 146–153 (PUT body):
     ```tsx
     const updatePromise = fetchWithAuth(`/api/workspaces/${workspaceId}/notification-preferences`, {
       method: "PUT",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({
         event_type: eventType,
         channel: channel,
         enabled: !currentEnabled
       }),
     })
     ```
2. **Backend Route Definition & Response**:
   In `admin/backend/routers/workspaces.py`:
   - Line 28:
     ```python
     router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])
     ```
   - Lines 546–563:
     ```python
     @router.get("/{workspace_id}/notification-preferences")
     def get_notification_preferences(
         workspace_id: str,
         user_id: str = Depends(get_current_user_id_with_2fa)
     ):
         ...
         res = svc.table("notification_preferences").select("*").eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
         return res.data or []
     ```
   - Lines 569–594:
     ```python
     @router.put("/{workspace_id}/notification-preferences")
     def update_notification_preferences(
         workspace_id: str,
         payload: NotificationPreferenceUpdate,
         user_id: str = Depends(get_current_user_id_with_2fa)
     ):
         ...
         svc.table("notification_preferences").upsert({
             "user_id": user_id,
             "workspace_id": workspace_id,
             "event_type": payload.event_type,
             "channel": payload.channel,
             "enabled": payload.enabled
         }).execute()
         return {"status": "success"}
     ```
3. **Backend Mounting**:
   In `core/backend/main.py`:
   - Line 82: `from admin.backend.routers import workspaces`
   - Line 86: `app.include_router(workspaces.router, dependencies=[Depends(get_current_user_id)])`
   Because `workspaces.router` defines `prefix="/api/workspaces"`, mounting it in `main.py` without an additional prefix produces the exact path:
   `GET /api/workspaces/{workspace_id}/notification-preferences`
   `PUT /api/workspaces/{workspace_id}/notification-preferences`
   In `vite.config.ts` line 31, `/api` is proxied to `http://127.0.0.1:8000`.
4. **Authentication & User ID Extraction**:
   Both `get_notification_preferences` and `update_notification_preferences` depend on `user_id: str = Depends(get_current_user_id_with_2fa)`.
   In `core/backend/api/auth_dep.py` lines 238–289:
   `get_current_user_id_with_2fa` decodes the Supabase JWT token from `Authorization: Bearer <token>`, validates the user session via Supabase GoTrue, verifies 2FA compliance against the workspace's `require_2fa` setting, and returns `user_id`. It is dynamically resolved and not hardcoded.
5. **Database Schema**:
   In `backend/supabase_schema.sql` lines 189–196:
   ```sql
   CREATE TABLE public.notification_preferences (
       user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
       workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
       event_type text NOT NULL,
       channel text NOT NULL,
       enabled boolean NOT NULL DEFAULT true,
       PRIMARY KEY (user_id, workspace_id, event_type, channel)
   );
   ```
   The payload fields `{ event_type, channel, enabled }` match the database schema.
6. **The Defect Identified**:
   `get_notification_preferences` returns `res.data or []`, which is a raw list (`[...]`).
   However, `NotificationSettings.tsx` checks `if (data?.preferences)`. Since `data` is an array, `data.preferences` is `undefined`. Consequently, `prefs` remains empty `[]`, `displayEventTypes` falls back to default, and toggling an option reverts back to off after `mutate()` completes because `data.preferences` cannot be parsed from the array response.

---

### R6: Campaign Reply Detection UTC Comparison
1. **Reply Detection Implementation**:
   In `campaigns/backend/services/elein_orchestrator.py` lines 532–544:
   ```python
   532:         # --- PHASE 7: REPLY DETECTION (Paranoia Layer) ---
   533:         stop_on_reply = state.get("campaign_metadata", {}).get("stop_on_reply", True)
   534:         if stop_on_reply:
   535:             try:
   536:                 inbound_msg_res = self.supabase.table("messages").select("id").eq("lead_id", state["opportunity_id"]).eq("direction", "inbound").gt("created_at", state["enrollment_created_at"]).limit(1).execute()
   537:                 if inbound_msg_res.data:
   538:                     logger.info(f"Inbound reply detected for lead {state['opportunity_id']}! Pausing campaign execution.")
   539:                     self.update_state(state["id"], current_node_id, "completed", None, lease_token, error_reason="Lead replied (paused)")
   540:                     return
   541:             except Exception as e:
   542:                 capture_error(e, context={"service": "elein_orchestrator"})
   543:                 pass
   ```
2. **State Construction**:
   In `campaigns/backend/services/elein_orchestrator.py` line 452:
   ```python
   "enrollment_created_at": enrollment["created_at"],
   ```
3. **Database Schema of `messages.created_at`**:
   In `backend/supabase_schema.sql` line 488:
   `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),`
4. **Behavioral Testing**:
   PostgREST translates `.gt("created_at", value)` into the query `?created_at=gt.<value>`.
   When `value` is passed as a naive timestamp string (`"2025-01-15T10:30:00"`), PostgreSQL casts it to `TIMESTAMPTZ` using the database session timezone, which will cause timezone drift if the session is not strictly UTC. If `value` is `None` or an unparseable format, the call throws an exception which is silently swallowed by lines 541–543 (`except Exception as e: capture_error(e); pass`), causing reply detection to fail silently.

---

## 2. Logic Chain

### R1 Logic Chain
1. *Observation*: Line 35 of `backend/migrations/029_phase3_account_eligibility.sql` queries `AND a.manual_mode_enabled = FALSE`.
2. *Observation*: The `accounts` table in `backend/supabase_schema.sql` and `backend/migrations/007_manual_send_detection.sql` contains `manual_send_suspected BOOLEAN DEFAULT false`, not `manual_mode_enabled`.
3. *Deduction*: Executing `dequeue_due_leads` at runtime raises PostgreSQL error `column a.manual_mode_enabled does not exist`, causing all campaign lead dequeuing to fail immediately.
4. *Observation*: `elein_orchestrator.py` line 383 calls `self.supabase.rpc("dequeue_due_leads", {"p_batch_size": 50, "p_campaign_ids": active_campaign_ids})`.
5. *Deduction*: The parameter names and types (`p_batch_size`: int, `p_campaign_ids`: list of UUID strings) perfectly match the SQL parameters `p_batch_size integer DEFAULT 50, p_campaign_ids uuid[] DEFAULT NULL`.
6. *Action Required*: Create a migration (`backend/migrations/033_fix_manual_mode_column.sql`) replacing `dequeue_due_leads` where `a.manual_mode_enabled = FALSE` is replaced with `AND COALESCE(a.manual_send_suspected, false) = false` (or `AND a.manual_send_suspected = FALSE`).

### R4 Logic Chain
1. *Observation*: In `NotificationSettings.tsx`, lines 99, 105, 107, 122, and 165 all access `data?.preferences`.
2. *Observation*: In `admin/backend/routers/workspaces.py` line 563, `get_notification_preferences` executes `return res.data or []`.
3. *Deduction*: When `data` is an array (`[{...}]`), `data.preferences` is `undefined`.
4. *Deduction*: `setPrefs(data.preferences)` is never executed. The UI state `prefs` remains `[]`, so all toggle switches render as disabled (or default) regardless of the actual saved preferences in the database. When a toggle is flipped, `mutate()` re-fetches and receives an array without `.preferences`, immediately resetting the toggle back to false.
5. *Deduction*: In `workspaces.py`, `get_notification_preferences` should return `{"preferences": res.data or []}` to match the contract expected by `NotificationSettings.tsx`. In addition, `NotificationSettings.tsx` should support both `Array.isArray(data) ? data : data?.preferences` for defensive layer-1 resiliency.
6. *Observation*: Routes in `main.py` and `workspaces.py` are mounted correctly (`/api/workspaces/{workspace_id}/notification-preferences`), and `user_id` is dynamically extracted via `Depends(get_current_user_id_with_2fa)` without hardcoding.

### R6 Logic Chain
1. *Observation*: In `campaigns/backend/services/elein_orchestrator.py` line 452, `"enrollment_created_at"` is assigned `enrollment["created_at"]` without format validation or timezone conversion.
2. *Observation*: In Phase 7 (line 536), `.gt("created_at", state["enrollment_created_at"])` queries PostgreSQL `messages.created_at` (`TIMESTAMPTZ`).
3. *Deduction*: If `state["enrollment_created_at"]` is naive (`YYYY-MM-DDTHH:MM:SS`), has non-UTC offsets, has different string formats, or is `None`, comparison against `TIMESTAMPTZ` can lead to comparison errors or unhandled exceptions that get swallowed by `except Exception: pass`.
4. *Action Required*: Add a normalization function `_normalize_to_utc_iso` in `elein_orchestrator.py` that parses strings or datetime objects and outputs a normalized, timezone-aware UTC ISO string with explicit `+00:00` suffix (`YYYY-MM-DDTHH:MM:SS+00:00`). Normalize when populating `state["enrollment_created_at"]` (line 452) and before running the `.gt(...)` query in Phase 7 (line 536), with an explicit guard if `norm_created_at` is None.

---

## 3. Caveats
1. **Migration Naming Sequence**: In `backend/migrations/`, `033_timezone_scheduling.sql` already exists and migrations extend through `065_vector_optimization_migration_v2.sql`. However, Requirement R1 in both the original specification and dispatch specifically refers to `backend/migrations/033_fix_manual_mode_column.sql`. The implementer can safely create `backend/migrations/033_fix_manual_mode_column.sql` (or `backend/migrations/066_fix_manual_mode_column.sql` if strict sequential ordering without collision is required; keeping `033_fix_manual_mode_column.sql` satisfies explicit requirements).
2. **Account Status in Dequeue Query**: In `029_phase3_account_eligibility.sql`, line 34 filters `AND a.status = 'ACTIVE'`. Note that `accounts.status` can also be `'MANUAL_MODE'` when the user temporarily pauses automation for manual login. The query `AND a.status = 'ACTIVE'` already filters out accounts in `'MANUAL_MODE'`. Checking `AND COALESCE(a.manual_send_suspected, false) = false` further guarantees that accounts flagged for suspected manual sends are excluded.

---

## 4. Conclusion & Proposed Implementation Specifications

### Proposed Fix for R1: `backend/migrations/033_fix_manual_mode_column.sql`
Create `backend/migrations/033_fix_manual_mode_column.sql` with the following complete content:

```sql
BEGIN;

-- Redefine dequeue_due_leads replacing non-existent column a.manual_mode_enabled with a.manual_send_suspected
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size integer DEFAULT 50,
    p_campaign_ids uuid[] DEFAULT NULL
)
RETURNS SETOF public.campaign_execution_states
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.campaign_execution_states
    SET
        status     = 'processing',
        lease_token = gen_random_uuid(),
        lease_expires_at = now() + interval '5 minutes',
        updated_at = now()
    WHERE id IN (
        SELECT ces.id 
        FROM (
            SELECT DISTINCT workspace_id 
            FROM public.campaigns
            WHERE status = 'ACTIVE' 
              AND (p_campaign_ids IS NULL OR id = ANY(p_campaign_ids))
        ) w
        CROSS JOIN LATERAL (
            SELECT ces.id, ces.next_run_at
            FROM public.campaign_execution_states ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            JOIN public.accounts a ON a.id = ce.account_id
            WHERE ces.workspace_id = w.workspace_id
              AND ces.status IN ('pending', 'running')
              AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
              AND a.status = 'ACTIVE'
              AND COALESCE(a.manual_send_suspected, false) = false
            ORDER BY ces.next_run_at ASC NULLS FIRST
            LIMIT GREATEST(1, p_batch_size / 5)
        ) ces
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

COMMIT;
```

---

### Proposed Fix for R4: Backend & Frontend Alignment

#### 1. In `admin/backend/routers/workspaces.py` (lines 546–568):
Update `get_notification_preferences` to return `{"preferences": res.data or []}`:

```python
@router.get("/{workspace_id}/notification-preferences")
def get_notification_preferences(
    workspace_id: str,
    user_id: str = Depends(get_current_user_id_with_2fa)
):
    try:
        svc = get_service_client()
        # Layer 1: verify workspace exists
        ws_check = svc.table("workspaces").select("id").eq("id", workspace_id).execute()
        if not ws_check.data:
            raise HTTPException(status_code=404, detail="Workspace not found")

        actor = svc.table("workspace_members").select("role").eq("user_id", user_id).eq("workspace_id", workspace_id).execute()
        if not actor.data:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")

        res = svc.table("notification_preferences").select("*").eq("workspace_id", workspace_id).eq("user_id", user_id).execute()
        return {"preferences": res.data or []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service temporarily unavailable: {e}")
```

#### 2. In `core/frontend/pages/settings/NotificationSettings.tsx` (lines 98–122):
Add defensive extraction supporting both wrapped and unwrapped array shapes:

```tsx
  useEffect(() => {
    const rawPrefs = Array.isArray(data) ? data : data?.preferences;
    if (rawPrefs) {
      setPrefs(rawPrefs);
    }
  }, [data]);

  const displayEventTypes = useMemo(() => {
    const rawPrefs = Array.isArray(data) ? data : data?.preferences;
    if (!rawPrefs) return KNOWN_EVENT_TYPES;
    
    const backendTypes = new Set(rawPrefs.map((p: any) => p.event_type));
    const knownIds = new Set(KNOWN_EVENT_TYPES.map(e => e.id));
    
    // Find any unknown types from backend
    const unknownFromBackend = [...backendTypes]
      .filter(id => typeof id === 'string' && !knownIds.has(id))
      .map(id => ({
        id: id as string,
        label: (id as string).replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
        desc: 'Notification from backend',
        group: 'activity' as const,
        recommended: { in_app: false, email: false }
      }));
    
    return [...KNOWN_EVENT_TYPES, ...unknownFromBackend];
  }, [data]);
```

---

### Proposed Fix for R6: `campaigns/backend/services/elein_orchestrator.py`

#### 1. Add `_normalize_to_utc_iso` helper function:
```python
def _normalize_to_utc_iso(dt_val: Any) -> Optional[str]:
    """Normalizes any datetime or ISO string to timezone-aware UTC ISO format (YYYY-MM-DDTHH:MM:SS+00:00)."""
    if not dt_val:
        return None
    if isinstance(dt_val, datetime):
        dt = dt_val
    else:
        s = str(dt_val).strip()
        if s.endswith('Z') or s.endswith('z'):
            s = s[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            try:
                from dateutil.parser import parse
                dt = parse(s)
            except Exception:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()
```

#### 2. At Line 452 in `orchestrate_batch`:
```python
"enrollment_created_at": _normalize_to_utc_iso(enrollment.get("created_at")),
```

#### 3. At Lines 532–544 in Phase 7 (`process_lead`):
```python
        # --- PHASE 7: REPLY DETECTION (Paranoia Layer) ---
        stop_on_reply = state.get("campaign_metadata", {}).get("stop_on_reply", True)
        if stop_on_reply:
            try:
                norm_created_at = _normalize_to_utc_iso(state.get("enrollment_created_at"))
                if norm_created_at:
                    inbound_msg_res = self.supabase.table("messages") \
                        .select("id") \
                        .eq("lead_id", state["opportunity_id"]) \
                        .eq("direction", "inbound") \
                        .gt("created_at", norm_created_at) \
                        .limit(1) \
                        .execute()
                    if inbound_msg_res.data:
                        logger.info(f"Inbound reply detected for lead {state['opportunity_id']}! Pausing campaign execution.")
                        self.update_state(state["id"], current_node_id, "completed", None, lease_token, error_reason="Lead replied (paused)")
                        return
            except Exception as e:
                capture_error(e, context={"service": "elein_orchestrator"})
                pass
```

---

## 5. Verification Method

1. **Compilation Verification**:
   - Run Python bytecode compilation across affected backend targets:
     ```bash
     python3 -m py_compile campaigns/backend/services/elein_orchestrator.py admin/backend/routers/workspaces.py core/backend/main.py
     ```
     Ensure exit code is 0.
   - Run TypeScript verification for frontend:
     ```bash
     npx tsc --noEmit
     ```
     Ensure exit code is 0 with zero errors.

2. **SQL Migration Verification**:
   - Verify SQL syntax of `backend/migrations/033_fix_manual_mode_column.sql`:
     Check that `COALESCE(a.manual_send_suspected, false) = false` replaces `a.manual_mode_enabled = FALSE`.
     Confirm table alias `a` refers to `public.accounts` joined via `campaign_enrollments`.

3. **UTC Normalization Unit Test**:
   Execute the following inline Python test:
   ```bash
   python3 -c "
   from datetime import datetime, timezone
   from campaigns.backend.services.elein_orchestrator import _normalize_to_utc_iso

   assert _normalize_to_utc_iso('2025-01-15T10:30:00Z') == '2025-01-15T10:30:00+00:00'
   assert _normalize_to_utc_iso('2025-01-15T10:30:00') == '2025-01-15T10:30:00+00:00'
   assert _normalize_to_utc_iso('2025-01-15T10:30:00+00:00') == '2025-01-15T10:30:00+00:00'
   assert _normalize_to_utc_iso(None) is None
   print('All UTC normalization tests passed!')
   "
   ```

4. **Invalidation Conditions**:
   - If PostgreSQL reports `column a.manual_send_suspected does not exist`, check `supabase_schema.sql` line 284 to ensure migrations 007 and base schema are in sync.
   - If frontend notification toggle state fails to load, inspect network response payload of `GET /api/workspaces/{id}/notification-preferences` in browser DevTools to verify `{ "preferences": [...] }`.
