# Dispatch for teamwork_preview_worker_track_4

## Task
You are Worker 4 implementing Requirements R5 and R8 for Ele-in.
Apply real, robust, production-grade implementations to your assigned files.
Run syntax and compilation checks (`python3 -m py_compile ...` and `npx tsc --noEmit`) to verify your changes.
Write a detailed completion report at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_4/handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Authoritative Reference
Read `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Read Explorer 3's detailed findings at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md`.

## Exclusive Write Ownership Boundaries
You ONLY edit/create these files:
1. `campaigns/frontend/eiTreeStore.ts`
2. `campaigns/frontend/EleInCreateCampaign.tsx`
3. `campaigns/backend/routers/elein.py`
4. `core/frontend/App.tsx`
DO NOT modify any other files.

## Detailed Requirements & Implementation Guidance
1. **R5: Fix draft autosave subscription scope leak**:
   - In `campaigns/frontend/eiTreeStore.ts`:
     - Remove the top-level unconditional `useHRTreeStore.subscribe(...)` at lines 424–441 that ran on every state mutation on every page.
     - Optionally export `saveDraftToLocalStorage(state: EITreeStore)` helper.
   - In `campaigns/frontend/EleInCreateCampaign.tsx`:
     - Add `useEffect` inside `EleInCreateCampaignInner` to subscribe to `useHRTreeStore` on mount and unsubscribe on unmount (`return () => unsubscribe()`).
     - Guard subscription with `isSavingRef` so `reset()` on save/launch does NOT resurrect an empty draft in `localStorage` after `removeItem`.
2. **R8: Treestore state reset bug on campaign edit**:
   - In `campaigns/backend/routers/elein.py`:
     - In `create_campaign` (POST `/api/elein/campaigns`): Persist `nodes_json`, `edges_json`, and `sender_account_ids_json` directly to the `campaigns` table row.
     - In `update_campaign` (PUT `/api/elein/campaigns/{campaign_id}`): Update `nodes_json`, `edges_json`, and `sender_account_ids_json` directly on the `campaigns` table row.
     - In `get_campaign_detail` (GET `/api/elein/campaigns/{campaign_id}/detail`):
       - Return both `nodes` and `nodes_json`, `edges` and `edges_json`, `sender_account_ids` and `sender_account_ids_json`.
       - If `nodes` is empty, reconstruct the workflow nodes & edges from `campaign_versions` + `campaign_nodes` + `campaign_edges` so legacy campaigns never load as empty.
   - In `core/frontend/App.tsx`:
     - Add routes for `<Route path="/campaigns/:id/edit" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />` and `<Route path="/elein/campaigns/:id/edit" element={<ProtectedRoute><EleInCreateCampaign /></ProtectedRoute>} />`.
   - In `campaigns/frontend/EleInCreateCampaign.tsx`:
     - Use `useParams` to read `:id`, and check both `params.get("edit") || routeId`.
     - Support both `data.nodes || data.nodes_json`, `data.edges || data.edges_json`, and `data.sender_account_ids || data.sender_account_ids_json`.
     - Call `useHRTreeStore.getState().loadTree(dagToTree(nodes, edges), [])` to load the graph into the store.
     - Add `isLoadingCampaign` loading barrier with spinner so the component does not render with blank store state before the campaign details have finished fetching.

## Verification Instructions
- Run: `python3 -m py_compile campaigns/backend/routers/elein.py`
- Run: `npx tsc --noEmit`
- Document the commands run and outputs in your handoff report.

## 2026-10-02T08:19:42Z
You are Worker 4 implementing Requirements R5 and R8 in Ele-in.
Your working directory is `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_4`.
First, read your task dispatch at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_4/DISPATCH.md`.
Read the authoritative user request at `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Read Explorer 3's detailed handoff at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md`.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You exclusively own and modify:
1. `campaigns/frontend/eiTreeStore.ts`
2. `campaigns/frontend/EleInCreateCampaign.tsx`
3. `campaigns/backend/routers/elein.py`
4. `core/frontend/App.tsx`

Implement all fixes following the Three-Layer Logic Architecture. Run verification:
- `python3 -m py_compile campaigns/backend/routers/elein.py`
- `npx tsc --noEmit`
Write your completion report to `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_4/handoff.md`.
When done, send a message to parent reporting completion and referencing the handoff path.
