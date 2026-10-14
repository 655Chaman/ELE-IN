# Handoff Report: Investigation of Requirements R5, R7, and R8

**Investigator**: Explorer 3 (`teamwork_preview_explorer_survey_3`)  
**Target Project**: Ele-in (`/Users/krdeeksha/Ele-in`)  
**Date**: 2026-10-02  
**Scope**: 
- **R5**: Draft autosave subscription scope leak (`campaigns/frontend/eiTreeStore.ts`, `campaigns/frontend/EleInCreateCampaign.tsx`)
- **R7**: Approval queue frontend-to-backend integration (`inbox/frontend/EleInApprovals.tsx`, `core/frontend/lib/apiClient.ts`, `core/backend/api/routers/approvals.py`, `core/backend/workers/job_processor.py`)
- **R8**: TreeStore state reset bug on campaign edit (`campaigns/frontend/EleInCreateCampaign.tsx`, `campaigns/backend/routers/elein.py`, `core/frontend/App.tsx`)

---

## 1. Observation

### 1.1 Requirement R5: Draft Autosave Subscription Scope Leak
1. **Module-level Unconditional Subscription in `campaigns/frontend/eiTreeStore.ts`**:
   At lines 424–441 of `campaigns/frontend/eiTreeStore.ts`:
   ```ts
   // LAYER 0 + LAYER 1: Paranoia - Draft Autosave with Environmental Failure Protection (QuotaExceeded)
   if (typeof window !== "undefined") {
     useHRTreeStore.subscribe((state) => {
       try {
         const { nodes, edges } = treeToDag(state.rootNodes)
         const draft = {
           nodes,
           edges,
           formState: state.formState,
           step: state.campaignStep,
           timestamp: Date.now()
         }
         localStorage.setItem("elein_unsaved_draft", JSON.stringify(draft))
       } catch (e) {
         console.warn("Failed to autosave campaign draft to localStorage:", e)
       }
     })
   }
   ```
   This subscription runs immediately when `eiTreeStore.ts` is imported by any module in the frontend bundle. It stays active permanently across all pages (Leads, Inbox, Settings, Accounts, Billing). Any state transition in `useHRTreeStore` invokes `localStorage.setItem("elein_unsaved_draft", ...)`.
2. **Draft Overwrite & Post-Save Resurrection in `campaigns/frontend/EleInCreateCampaign.tsx`**:
   At lines 1299–1306 of `campaigns/frontend/EleInCreateCampaign.tsx`:
   ```ts
   // Clear the local draft so the "Unsaved Draft" banner doesn't reappear
   try {
     localStorage.removeItem("elein_unsaved_draft");
   } catch(e) {}
   
   useHRTreeStore.getState().reset();
   mutate("/api/elein/dashboard/stats");
   mutate("/api/elein/campaigns");
   navigate("/elein/campaigns");
   ```
   When `handleSaveDraft` completes, `localStorage.removeItem("elein_unsaved_draft")` is called to delete the draft. Immediately afterwards on line 1303, `useHRTreeStore.getState().reset()` is executed. Calling `reset()` mutates the Zustand store, which synchronously triggers the top-level subscriber. The subscriber immediately executes `localStorage.setItem("elein_unsaved_draft", JSON.stringify(draft))` with the newly emptied state (`nodes: []`, `edges: []`). When `navigate("/elein/campaigns")` mounts `EleInCampaigns.tsx`, an `elein_unsaved_draft` entry is still present in `localStorage`.

---

### 1.2 Requirement R7: Approval Queue Frontend-to-Backend Integration
1. **Frontend Approval Queue Wiring (`inbox/frontend/EleInApprovals.tsx`)**:
   - Line 51–55:
     ```ts
     const { data, error, isLoading, mutate } = useSWR<ApprovalListResponse>(
       '/api/approvals?status=pending&limit=50',
       fetcher,
       { refreshInterval: 30_000 }
     )
     ```
   - Line 81–85:
     ```ts
     const res = await fetchWithAuth(`/api/approvals/${selected.id}/approve`, {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({ edited_message: draftText || null }),
     })
     ```
   - Line 105:
     ```ts
     const res = await fetchWithAuth(`/api/approvals/${selected.id}/reject`, { method: 'POST' })
     ```
2. **Route Mounting in `core/backend/main.py`**:
   At line 71:
   ```python
   app.include_router(approvals.router, prefix="/api", dependencies=[Depends(get_current_workspace)])
   ```
   And `approvals.router` in `core/backend/api/routers/approvals.py` specifies:
   `router = APIRouter(prefix="/approvals", tags=["approvals"])`
   The paths `/api/approvals`, `/api/approvals/{id}/approve`, and `/api/approvals/{id}/reject` properly route to `approvals.py`.
3. **CRITICAL DEFECT: `approve_reply` Fails LinkedIn Delivery (`core/backend/api/routers/approvals.py` vs `core/backend/workers/job_processor.py`)**:
   In `core/backend/api/routers/approvals.py` lines 89–103:
   ```python
   enqueue_job(
       supabase, 
       'inbox_action', 
       workspace_id, 
       item["account_id"], 
       {
           'action': 'send_message_to_existing_thread',
           'payload_data': {
               'sender_name': item["sender_name"],
               'message': final_message
           }
       }
   )
   ```
   In `core/backend/services/job_queue.py`:
   `enqueue_job(supabase, job_type, workspace_id, asset_id, payload)` inserts:
   `job_data = { "workspace_id": workspace_id, "asset_id": asset_id, "job_type": job_type, "status": "pending", "payload": payload }`
   `item["account_id"]` is passed as `asset_id` and is stored on the `processing_jobs.asset_id` column.
   However, look at how `core/backend/workers/job_processor.py` processes `inbox_action` at lines 74–90:
   ```python
   elif job_type in ('inbox_sync', 'inbox_action'):
       ...
       account_id = payload.get('account_id')
       ws_id = payload.get('workspace_id', workspace_id)
       
       acc_res = sync_supabase.table("accounts").select("session_cookies_encrypted, proxies(protocol, host, port, username)").eq("id", account_id).execute()
       if not acc_res.data:
           raise ValueError(f"Account {account_id} not found.")
   ```
   Notice: `job_processor.py` reads `payload.get('account_id')`! Because `account_id` was NOT placed in the `payload` dict by `approvals.py`, `account_id` evaluates to `None`. The query `accounts.select(...).eq("id", None)` returns zero rows, and `job_processor.py` throws:
   `ValueError: Account None not found.`!
   As a direct consequence, the LinkedIn message was NEVER dispatched, and the job was marked failed!
4. **CRITICAL DEFECT: `reject_reply` Leaves Lead Stuck in `campaign_execution_states`**:
   In `core/backend/api/routers/approvals.py` lines 126–138:
   ```python
   res = supabase.table("approval_queue").select("id, status").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
   if not res.data:
       raise HTTPException(status_code=404, detail="Approval item not found")
       
   if res.data[0]["status"] != "pending":
       raise HTTPException(status_code=400, detail=f"Cannot reject item in status: {res.data[0]['status']}")
       
   supabase.table("approval_queue").update({
       "status": "skipped",
       "reviewed_at": datetime.utcnow().isoformat()
   }).eq("id", approval_id).execute()
   
   return {"status": "success", "message": "Reply rejected and skipped"}
   ```
   Notice: `reject_reply` ONLY updates the `approval_queue` record to `status: "skipped"`.
   In `campaigns/backend/services/elein_executor.py` lines 1183–1185, when an AI reply requires approval:
   ```python
   self.supabase.table("campaign_execution_states").update({
       "status": "awaiting_approval"
   }).eq("id", execution_state_id).execute()
   ```
   `reject_reply` does NOT touch `campaign_execution_states`. As a result, the lead remains stuck in `"awaiting_approval"` forever (or until the 48-hour reaper in `elein_orchestrator.py` line 337 times out).
5. **Table Discrepancy between `approval_queue` and `ai_reply_approvals`**:
   Migration `049_ai_reply_approvals.sql` created `public.ai_reply_approvals` with columns `(id, workspace_id, lead_id, enrollment_id, execution_state_id, generated_reply, retrieval_score, status)`.
   Meanwhile, `approval_queue` (`backend/supabase_schema.sql` line 495) has columns `(id, workspace_id, account_id, sender_name, thread_messages_json, intent, heat_score, ai_draft, status)`.
   `elein_executor.py` writes to `ai_reply_approvals` (without creating a record in `approval_queue`). `inbox/backend/routers/inbox.py` writes to `approval_queue`.
   `core/backend/api/routers/approvals.py` queries `approval_queue`. If an item is in `ai_reply_approvals`, `approvals.py` returns a 404 unless both tables are reconciled or unified.

---

### 1.3 Requirement R8: TreeStore State Reset Bug on Campaign Edit
1. **Creation & Update Never Store `nodes_json` / `edges_json` in `campaigns` Table (`campaigns/backend/routers/elein.py`)**:
   In `create_campaign` (POST `/api/elein/campaigns`) at lines 1831–1839:
   ```python
   campaign_data = {
       "id": campaign_id,
       "name": name,
       "status": campaign.status or "DRAFT",
       "metadata": meta,
       "workspace_id": workspace_id,
   }
   supabase.table("campaigns").insert(campaign_data).execute()
   ```
   In `update_campaign` (PUT `/api/elein/campaigns/{campaign_id}`) at lines 1960–1977:
   ```python
   update_data = {
       "name": payload.name,
       "status": payload.status,
       "metadata": meta
   }
   client.table("campaigns").update(update_data).eq("id", campaign_id).execute()
   ```
   Although `backend/supabase_schema.sql` lines 380–382 defines:
   `nodes_json JSONB NOT NULL DEFAULT '[]'`
   `edges_json JSONB NOT NULL DEFAULT '[]'`
   `sender_account_ids_json JSONB NOT NULL DEFAULT '[]'`
   neither `create_campaign` nor `update_campaign` ever populates or updates those columns on the `campaigns` row!
2. **`get_campaign_detail` Returns Empty Nodes (`campaigns/backend/routers/elein.py`)**:
   At lines 2306–2320:
   ```python
   camp_res = supabase.table("campaigns").select("*").eq("id", campaign_id).eq("workspace_id", workspace_id).execute()
   campaign = camp_res.data[0]
   campaign["nodes"] = json.loads(campaign.get("nodes_json") or "[]") if isinstance(campaign.get("nodes_json"), str) else (campaign.get("nodes_json") or [])
   campaign["edges"] = json.loads(campaign.get("edges_json") or "[]") if isinstance(campaign.get("edges_json"), str) else (campaign.get("edges_json") or [])
   ```
   Because `nodes_json` on the `campaigns` row is `'[]'`, `campaign["nodes"]` and `campaign["edges"]` are set to `[]`.
   The endpoint does NOT fall back to reconstructing the workflow from `campaign_versions` + `campaign_nodes` + `campaign_edges`!
   Furthermore, the endpoint populates `campaign["nodes"]` and `campaign["edges"]`, but does NOT populate `campaign["nodes_json"]` or `campaign["edges_json"]`.
3. **Frontend Expects `data.nodes_json` Instead of `data.nodes` (`campaigns/frontend/EleInCreateCampaign.tsx`)**:
   At lines 1131–1135:
   ```ts
   const nodes = data.nodes_json ? (typeof data.nodes_json === "string" ? JSON.parse(data.nodes_json) : data.nodes_json) : []
   const edges = data.edges_json ? (typeof data.edges_json === "string" ? JSON.parse(data.edges_json) : data.edges_json) : []
   if (nodes.length > 0) {
     useHRTreeStore.getState().loadTree(dagToTree(nodes, edges), [])
   }
   ```
   `data.nodes_json` is undefined in the response payload. `nodes` evaluates to `[]`. Thus `loadTree` is NEVER called, and the store remains at its default empty state (`rootNodes: []`).
   Similarly:
   `senderIds: data.sender_account_ids_json ? ... : []`
   `get_campaign_detail` returns `campaign["sender_account_ids"]` (line 2317), so `data.sender_account_ids_json` is undefined and `senderIds` is wiped to `[]`.
4. **Missing Route Mapping in `core/frontend/App.tsx`**:
   The authoritative user request specifies: "When a user navigates to `/campaigns/{id}/edit` (editing an existing campaign)..."
   In `core/frontend/App.tsx`:
   Only `/elein/campaigns/new` exists (line 107). There are NO route definitions for `/campaigns/:id/edit` or `/elein/campaigns/:id/edit`.
   Navigating directly to `/campaigns/{id}/edit` triggers the `<NotFound />` component (line 114).
5. **Missing Loading State in `EleInCreateCampaign.tsx`**:
   When entering edit mode, `fetchWithAuth(`/api/elein/campaigns/${editId}/detail`)` is asynchronous. While the network request is in flight, `EleInCreateCampaignInner` immediately renders with the store's default empty state. If the user interacts or if autosave triggers, blank data is written out.

---

## 2. Logic Chain

### 2.1 R5 Logic Chain
1. *Observation 1.1.1* proves that `useHRTreeStore.subscribe` in `eiTreeStore.ts` is executed unconditionally on module evaluation.
2. Therefore, whenever the store updates anywhere in the app (e.g., when visiting campaigns list, switching accounts, or resetting state), `localStorage.setItem("elein_unsaved_draft", ...)` is called.
3. *Observation 1.1.2* shows that saving or launching a campaign calls `reset()`, which triggers the subscriber to immediately re-write an empty draft to `localStorage`, nullifying `removeItem("elein_unsaved_draft")`.
4. **Inference**: Moving the subscription from module level in `eiTreeStore.ts` into a React `useEffect` inside `EleInCreateCampaign` guarantees the listener is active *only* when the campaign builder component is mounted. Adding an `isSavingRef` prevents `reset()` during save/launch from writing an empty draft to `localStorage`.

### 2.2 R7 Logic Chain
1. *Observation 1.2.3* proves that `approvals.py` calls `enqueue_job('inbox_action', workspace_id, item["account_id"], { 'action': ..., 'payload_data': ... })`.
2. `enqueue_job` places `item["account_id"]` into `processing_jobs.asset_id`, but NOT inside `processing_jobs.payload`.
3. `job_processor.py` line 84 reads `account_id = payload.get('account_id')`, which evaluates to `None`, throws `ValueError: Account None not found.`, and completely fails message delivery.
4. **Inference for Approve**: The payload passed to `enqueue_job` must explicitly include `'account_id': item["account_id"]` and `'workspace_id': workspace_id`. In addition, `job_processor.py` line 84 should fall back to `job.get('asset_id')` if `payload.get('account_id')` is missing.
5. *Observation 1.2.4* proves that `reject_reply` only updates `approval_queue.status = "skipped"`, and leaves `campaign_execution_states` untouched in `"awaiting_approval"`.
6. **Inference for Reject**: `reject_reply` must query for any associated `campaign_execution_states` (via `execution_state_id`, `lead_id`, or matching `sender_name`) and update the execution state to `status = "exited"`, `error_reason = "ai_reply_rejected"` so the lead is unblocked.
7. *Observation 1.2.5* demonstrates that `ai_reply_approvals` and `approval_queue` are separate tables. Supporting both tables in `approvals.py` (`get`, `approve`, `reject`) ensures seamless operation regardless of which subsystem created the pending approval.

### 2.3 R8 Logic Chain
1. *Observation 1.3.1* proves that `create_campaign` and `update_campaign` in `elein.py` never save `nodes_json`, `edges_json`, or `sender_account_ids_json` into `campaigns`.
2. *Observation 1.3.2* proves that `get_campaign_detail` reads `nodes_json` (which is `'[]'`) from `campaigns`, setting `campaign["nodes"] = []` and `campaign["edges"] = []`.
3. *Observation 1.3.3* proves that `EleInCreateCampaign.tsx` checks `data.nodes_json` and `data.sender_account_ids_json`, while `get_campaign_detail` returns `data.nodes` and `data.sender_account_ids`.
4. As a result, `nodes` is parsed as `[]`, `useHRTreeStore.getState().loadTree` is never invoked, and the store remains empty.
5. *Observations 1.3.4 & 1.3.5* show that missing routes in `App.tsx` and absence of an asynchronous loading barrier cause 404s and immediate empty renders on campaign edit.
6. **Inference**:
   - `create_campaign` and `update_campaign` must write `nodes_json`, `edges_json`, and `sender_account_ids_json` directly to `campaigns`.
   - `get_campaign_detail` must return both `nodes` and `nodes_json`, `edges` and `edges_json`, `sender_account_ids` and `sender_account_ids_json`. If `nodes_json` is empty, it must reconstruct the workflow graph from `campaign_versions` + `campaign_nodes` + `campaign_edges`.
   - `EleInCreateCampaign.tsx` must accept `data.nodes || data.nodes_json` and `data.sender_account_ids || data.sender_account_ids_json`.
   - `App.tsx` must register routes for `/campaigns/:id/edit` and `/elein/campaigns/:id/edit`.
   - `EleInCreateCampaign.tsx` must display a loading spinner while `isLoadingCampaign` is true, preventing early renders and user interaction before state is fully hydrated.

---

## 3. Caveats

1. **LinkedIn Worker Execution Environment**: The background LinkedIn worker requires decrypted session cookies and a running browser/network environment. In automated test environments without live LinkedIn accounts, job dispatch is validated via the `processing_jobs` table and worker mocks.
2. **Backward Compatibility with Existing DB Records**: Any campaigns created in the database prior to saving `nodes_json` in the `campaigns` table only have rows in `campaign_nodes` and `campaign_edges`. The proposed fallback reconstruction in `get_campaign_detail` is essential to prevent those legacy campaigns from loading as empty.
3. **Draft Storage Key Namespace**: `elein_unsaved_draft` is shared per browser origin. If a user opens multiple tabs editing different campaigns, the latest edit will overwrite the draft in `localStorage`. The proposed fix addresses the module scope leak and prevents post-save draft resurrection.

---

## 4. Conclusion & Proposed Implementation

### 4.1 Proposed Implementation for R5 (Draft Autosave Scope Leak)

#### File: `campaigns/frontend/eiTreeStore.ts`
Remove lines 424–441 (the top-level `if (typeof window !== "undefined") { useHRTreeStore.subscribe(...) }` block).  
Optionally export a helper `saveDraftToLocalStorage(state: EITreeStore)`:

```ts
// Export helper for scoped autosave
export function saveDraftToLocalStorage(state: EITreeStore) {
  try {
    const { nodes, edges } = treeToDag(state.rootNodes)
    const draft = {
      nodes,
      edges,
      formState: state.formState,
      step: state.campaignStep,
      timestamp: Date.now()
    }
    localStorage.setItem("elein_unsaved_draft", JSON.stringify(draft))
  } catch (e) {
    console.warn("Failed to autosave campaign draft to localStorage:", e)
  }
}
```

#### File: `campaigns/frontend/EleInCreateCampaign.tsx`
Add a scoped `useEffect` with cleanup and `isSavingRef` inside `EleInCreateCampaignInner`:

```tsx
  const isSavingRef = React.useRef(false);

  // Scoped autosave: Active ONLY while EleInCreateCampaign is mounted
  useEffect(() => {
    const unsubscribe = useHRTreeStore.subscribe((state) => {
      // Paranoia Layer 1: Do not overwrite draft if save/launch is currently executing or completed
      if (isSavingRef.current) return;
      
      try {
        const { nodes, edges } = treeToDag(state.rootNodes);
        const draft = {
          nodes,
          edges,
          formState: state.formState,
          step: state.campaignStep,
          timestamp: Date.now()
        };
        localStorage.setItem("elein_unsaved_draft", JSON.stringify(draft));
      } catch (e) {
        console.warn("Failed to autosave campaign draft to localStorage:", e);
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);
```
And inside `handleSaveDraft`:
```tsx
  isSavingRef.current = true;
  setIsSaving(true);
  // ... on success:
  localStorage.removeItem("elein_unsaved_draft");
  useHRTreeStore.getState().reset();
  navigate("/elein/campaigns");
  // ... on error / catch:
  isSavingRef.current = false;
  setIsSaving(false);
```

---

### 4.2 Proposed Implementation for R7 (Approval Queue Integration)

#### File: `core/frontend/lib/apiClient.ts`
Normalize `path` resolution so paths with or without leading slashes and base URLs resolve cleanly:

```ts
const API_BASE = (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL) || "";

export async function fetchWithAuth(path: string, options: AuthRequestInit = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(options.headers || {})
  
  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`)
  }
  
  const activeWorkspace = localStorage.getItem('elein_active_workspace')
  if (activeWorkspace) {
    headers.set('X-Workspace-Id', activeWorkspace)
  }
  
  const resolvedUrl = path.startsWith("http")
    ? path
    : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`

  const res = await fetch(resolvedUrl, { ...options, headers })
  // ... existing 401 and 403 handling ...
```

#### File: `core/backend/api/routers/approvals.py`
Fix both `approve_reply` (payload data for LinkedIn delivery) and `reject_reply` (unblocking `campaign_execution_states`), and support both `approval_queue` and `ai_reply_approvals`:

```python
@router.post("/{approval_id}/approve")
def approve_reply(
    approval_id: str,
    payload: ApprovalActionRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Approve an AI drafted reply. Queues it for actual delivery via LinkedInWorker.
    """
    # 1. Fetch item from approval_queue or ai_reply_approvals
    res = supabase.table("approval_queue").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
    item = None
    is_ai_table = False
    
    if res.data:
        item = res.data[0]
    else:
        res_ai = supabase.table("ai_reply_approvals").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
        if res_ai.data:
            item = res_ai.data[0]
            is_ai_table = True
        else:
            raise HTTPException(status_code=404, detail="Approval item not found")

    if item["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve item in status: {item['status']}")
        
    draft_msg = item.get("ai_draft") or item.get("generated_reply")
    final_message = payload.edited_message.strip() if (payload.edited_message and payload.edited_message.strip()) else draft_msg
    if not final_message:
        raise HTTPException(status_code=400, detail="Message body cannot be empty")
        
    try:
        account_id = item.get("account_id")
        sender_name = item.get("sender_name")
        
        # If item comes from ai_reply_approvals, resolve account and lead
        if is_ai_table:
            lead_id = item.get("lead_id")
            if lead_id:
                lead_res = supabase.table("leads").select("first_name, last_name, linkedin_url").eq("id", lead_id).execute()
                if lead_res.data:
                    lead = lead_res.data[0]
                    sender_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
            
            # Resolve account from campaign enrollment
            if not account_id and item.get("enrollment_id"):
                enr_res = supabase.table("campaign_enrollments").select("campaign_id").eq("id", item["enrollment_id"]).execute()
                if enr_res.data:
                    cid = enr_res.data[0]["campaign_id"]
                    ca_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", cid).limit(1).execute()
                    if ca_res.data:
                        account_id = ca_res.data[0]["account_id"]

        # Fallback to any active account in workspace if account_id is still missing
        if not account_id:
            acc_fallback = supabase.table("accounts").select("id").eq("workspace_id", workspace_id).eq("is_active", True).limit(1).execute()
            if acc_fallback.data:
                account_id = acc_fallback.data[0]["id"]
            else:
                raise HTTPException(status_code=400, detail="No active LinkedIn account found in workspace to deliver message.")

        # 2. Enqueue the send action via the worker with account_id and workspace_id in payload!
        enqueue_job(
            supabase, 
            'inbox_action', 
            workspace_id, 
            account_id, 
            {
                'account_id': account_id,
                'workspace_id': workspace_id,
                'action': 'send_message_to_existing_thread',
                'payload_data': {
                    'sender_name': sender_name,
                    'message': final_message
                }
            }
        )
        
        # 3. Mark as approved in relevant table
        now_iso = datetime.utcnow().isoformat()
        if not is_ai_table:
            supabase.table("approval_queue").update({
                "status": "approved",
                "ai_draft": final_message,
                "reviewed_at": now_iso
            }).eq("id", approval_id).execute()
        else:
            supabase.table("ai_reply_approvals").update({
                "status": "approved",
                "generated_reply": final_message,
                "resolved_at": now_iso
            }).eq("id", approval_id).execute()
            
        # 4. If linked to campaign_execution_states, advance the execution state
        exec_state_id = item.get("execution_state_id")
        if exec_state_id:
            supabase.table("campaign_execution_states").update({
                "status": "pending",
                "next_run_at": now_iso
            }).eq("id", exec_state_id).execute()
        
        return {"status": "success", "message": "Reply approved and queued for delivery"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to approve reply: {str(e)}")


@router.post("/{approval_id}/reject")
def reject_reply(
    approval_id: str,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Reject an AI drafted reply (marks as skipped/rejected, and unblocks lead execution state).
    """
    res = supabase.table("approval_queue").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
    item = None
    is_ai_table = False
    
    if res.data:
        item = res.data[0]
    else:
        res_ai = supabase.table("ai_reply_approvals").select("*").eq("id", approval_id).eq("workspace_id", workspace_id).execute()
        if res_ai.data:
            item = res_ai.data[0]
            is_ai_table = True
        else:
            raise HTTPException(status_code=404, detail="Approval item not found")
        
    if item["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot reject item in status: {item['status']}")
        
    now_iso = datetime.utcnow().isoformat()
    
    # 1. Update approval record status
    if not is_ai_table:
        supabase.table("approval_queue").update({
            "status": "skipped",
            "reviewed_at": now_iso
        }).eq("id", approval_id).execute()
    else:
        supabase.table("ai_reply_approvals").update({
            "status": "rejected",
            "resolved_at": now_iso
        }).eq("id", approval_id).execute()
        
    # 2. Unblock campaign_execution_states so lead is not stuck in 'awaiting_approval'
    exec_state_id = item.get("execution_state_id")
    if exec_state_id:
        supabase.table("campaign_execution_states").update({
            "status": "exited",
            "error_reason": "ai_reply_rejected"
        }).eq("id", exec_state_id).execute()
    else:
        # Resolve lead from sender_name or messages
        sender_name = item.get("sender_name")
        account_id = item.get("account_id")
        if sender_name and account_id:
            msg_res = supabase.table("messages").select("lead_id").eq("account_id", account_id).eq("sender_name", sender_name).not_.is_("lead_id", "null").limit(1).execute()
            if msg_res.data and msg_res.data[0].get("lead_id"):
                lead_id = msg_res.data[0]["lead_id"]
                enr_res = supabase.table("campaign_enrollments").select("id").eq("lead_id", lead_id).execute()
                enr_ids = [e["id"] for e in (enr_res.data or [])]
                if enr_ids:
                    supabase.table("campaign_execution_states").update({
                        "status": "exited",
                        "error_reason": "ai_reply_rejected"
                    }).in_("enrollment_id", enr_ids).eq("status", "awaiting_approval").execute()
    
    return {"status": "success", "message": "Reply rejected and skipped"}
```

#### File: `core/backend/workers/job_processor.py`
Line 84: Add defensive fallback to `job.get('asset_id')`:
```python
account_id = payload.get('account_id') or job.get('asset_id')
```

---

### 4.3 Proposed Implementation for R8 (TreeStore State Reset on Edit)

#### File: `campaigns/backend/routers/elein.py`
1. In `create_campaign` (POST `/api/elein/campaigns`), ensure `nodes_json`, `edges_json`, and `sender_account_ids_json` are stored in `campaign_data`:
   ```python
   campaign_data = {
       "id": campaign_id,
       "name": name,
       "status": campaign.status or "DRAFT",
       "nodes_json": nodes_raw,
       "edges_json": edges_raw,
       "sender_account_ids_json": campaign.senders or [],
       "metadata": meta,
       "workspace_id": workspace_id,
   }
   supabase.table("campaigns").insert(campaign_data).execute()
   ```
2. In `update_campaign` (PUT `/api/elein/campaigns/{campaign_id}`), ensure `nodes_json`, `edges_json`, and `sender_account_ids_json` are updated:
   ```python
   update_data = {
       "name": payload.name,
       "status": payload.status,
       "nodes_json": nodes_raw,
       "edges_json": edges_raw,
       "sender_account_ids_json": payload.senders or [],
       "metadata": meta
   }
   client.table("campaigns").update(update_data).eq("id", campaign_id).execute()
   ```
3. In `get_campaign_detail` (GET `/api/elein/campaigns/{campaign_id}/detail`), ensure nodes/edges are reconstructed if `nodes_json` was empty, and return both key formats (`nodes` & `nodes_json`, `edges` & `edges_json`, `sender_account_ids` & `sender_account_ids_json`):
   ```python
   nodes = json.loads(campaign.get("nodes_json") or "[]") if isinstance(campaign.get("nodes_json"), str) else (campaign.get("nodes_json") or [])
   edges = json.loads(campaign.get("edges_json") or "[]") if isinstance(campaign.get("edges_json"), str) else (campaign.get("edges_json") or [])
   
   # Fallback: If nodes are empty, reconstruct from campaign_versions + campaign_nodes + campaign_edges
   if not nodes:
       ver_res = supabase.table("campaign_versions").select("id").eq("campaign_id", campaign_id).order("version", desc=True).limit(1).execute()
       if ver_res.data:
           vid = ver_res.data[0]["id"]
           n_res = supabase.table("campaign_nodes").select("*").eq("campaign_version_id", vid).execute()
           e_res = supabase.table("campaign_edges").select("*").eq("campaign_version_id", vid).execute()
           
           nodes = [
               {
                   "id": n["id"],
                   "type": n.get("node_type", "unknown"),
                   "data": n.get("config") or {},
                   "position": n.get("ui_position") or {"x": 0, "y": 0}
               }
               for n in (n_res.data or [])
           ]
           edges = [
               {
                   "id": f"e-{e['source_node_id']}-{e['target_node_id']}",
                   "source": e["source_node_id"],
                   "target": e["target_node_id"],
                   "sourceHandle": e.get("condition") or "output"
               }
               for e in (e_res.data or [])
           ]

   campaign["nodes"] = nodes
   campaign["nodes_json"] = nodes
   campaign["edges"] = edges
   campaign["edges_json"] = edges
   
   sender_ids = campaign.get("sender_account_ids") or []
   if not sender_ids:
       acc_res = supabase.table("campaign_accounts").select("account_id").eq("campaign_id", campaign_id).execute()
       sender_ids = [r["account_id"] for r in (acc_res.data or [])]
   campaign["sender_account_ids"] = sender_ids
   campaign["sender_account_ids_json"] = sender_ids
   ```

#### File: `core/frontend/App.tsx`
Add route mappings for editing campaigns:
```tsx
<Route path="/campaigns/:id/edit" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
<Route path="/elein/campaigns/:id/edit" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />
```

#### File: `campaigns/frontend/EleInCreateCampaign.tsx`
1. Import `useParams`:
   ```ts
   import { useNavigate, useSearchParams, useLocation, useParams, Link } from "react-router-dom"
   ```
2. Read both route parameter and search query parameter:
   ```ts
   const { id: routeId } = useParams<{ id?: string }>();
   const params = new URLSearchParams(location.search);
   const editId = params.get("edit") || routeId;
   const [isLoadingCampaign, setIsLoadingCampaign] = useState<boolean>(Boolean(editId));
   ```
3. Parse both `data.nodes` and `data.nodes_json`:
   ```ts
   const rawNodes = data.nodes || data.nodes_json || [];
   const nodes = typeof rawNodes === "string" ? JSON.parse(rawNodes) : rawNodes;
   const rawEdges = data.edges || data.edges_json || [];
   const edges = typeof rawEdges === "string" ? JSON.parse(rawEdges) : rawEdges;
   const senderIds = data.sender_account_ids || data.sender_account_ids_json || [];
   const parsedSenderIds = typeof senderIds === "string" ? JSON.parse(senderIds) : senderIds;

   if (nodes && nodes.length > 0) {
     useHRTreeStore.getState().loadTree(dagToTree(nodes, edges), []);
   }
   setState((prev: any) => ({
     ...prev,
     campaignName: data.name || "Untitled Campaign",
     senderIds: parsedSenderIds,
     timezone: data.metadata?.timezone || data.timezone || "",
     leadListId: data.lead_list_id || data.metadata?.lead_list_id || "",
     searchUrl: data.sales_nav_url || data.metadata?.sales_nav_url || "",
     limit: data.metadata?.limit ?? data.limit ?? 50,
     schedule: data.metadata?.schedule || data.schedule || {},
     stopOnReply: data.metadata?.stop_on_reply ?? true
   }));
   setStep(0);
   setIsLoadingCampaign(false);
   ```
4. Render loading barrier:
   ```tsx
   if (isLoadingCampaign) {
     return (
       <div className="h-[100dvh] bg-background text-foreground flex flex-col items-center justify-center">
         <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
         <p className="text-sm text-muted-foreground font-medium">Loading campaign sequence...</p>
       </div>
     );
   }
   ```

---

## 5. Verification Method

### 5.1 Static Type Checking & Python Compilation
1. **TypeScript Type Check**:
   ```bash
   npx tsc --noEmit
   ```
   *Expected Result*: Exits with code 0.
2. **Python Syntax Compilation**:
   ```bash
   python3 -m py_compile \
     core/backend/api/routers/approvals.py \
     campaigns/backend/routers/elein.py \
     core/backend/workers/job_processor.py \
     campaigns/backend/services/elein_executor.py
   ```
   *Expected Result*: Exits with code 0.

### 5.2 Independent Verification of R5 (Autosave Scoping)
1. Inspect `campaigns/frontend/eiTreeStore.ts`: verify lines 424–441 no longer contain a module-level `useHRTreeStore.subscribe(...)`.
2. Inspect `campaigns/frontend/EleInCreateCampaign.tsx`: verify `useHRTreeStore.subscribe` is invoked only within `useEffect` and cleaned up with `return () => unsubscribe()`.
3. In browser / unit test:
   - Navigate to `/elein/leads`, mutate `useHRTreeStore.getState().reset()` in console: verify `localStorage.getItem("elein_unsaved_draft")` remains untouched.
   - Navigate to `/elein/campaigns/new`, add a node: verify `localStorage.getItem("elein_unsaved_draft")` is saved.
   - Click "Save Draft": verify `localStorage.getItem("elein_unsaved_draft")` is removed and not resurrected by `reset()`.

### 5.3 Independent Verification of R7 (Approval Queue Integration)
1. Verify `approve_reply` in `core/backend/api/routers/approvals.py`:
   - Inspect `enqueue_job` call: confirm `'account_id': item["account_id"]` and `'workspace_id': workspace_id` are included in the payload dict.
   - Inspect `job_processor.py`: confirm `account_id` is successfully retrieved.
2. Verify `reject_reply` in `core/backend/api/routers/approvals.py`:
   - Inspect `reject_reply`: confirm that it executes `supabase.table("campaign_execution_states").update({"status": "exited", "error_reason": "ai_reply_rejected"})` on the relevant execution state.
3. Verify `core/frontend/lib/apiClient.ts`:
   - Confirm URL normalization handles both relative `/api` paths and configured `VITE_API_URL`.

### 5.4 Independent Verification of R8 (TreeStore State Reset on Edit)
1. Inspect `campaigns/backend/routers/elein.py`:
   - Confirm `create_campaign` and `update_campaign` persist `nodes_json`, `edges_json`, and `sender_account_ids_json` to `campaigns`.
   - Confirm `get_campaign_detail` reconstructs nodes/edges from `campaign_nodes`/`campaign_edges` if `nodes_json` is empty, and returns both `nodes` and `nodes_json`.
2. Inspect `core/frontend/App.tsx`:
   - Confirm `<Route path="/campaigns/:id/edit" ...>` and `<Route path="/elein/campaigns/:id/edit" ...>` exist.
3. Inspect `campaigns/frontend/EleInCreateCampaign.tsx`:
   - Confirm `useParams` is used to read `:id`.
   - Confirm `data.nodes || data.nodes_json` is parsed and loaded via `useHRTreeStore.getState().loadTree(...)`.
   - Confirm `isLoadingCampaign` blocks rendering until data is loaded into the store.
