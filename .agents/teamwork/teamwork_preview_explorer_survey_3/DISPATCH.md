# Dispatch for teamwork_preview_explorer_survey_3

## Task
You are Explorer 3 investigating the codebase for Requirements R5, R7, and R8.
You are a read-only exploration agent. Do NOT modify source code. Produce a detailed handoff report in your working directory at `handoff.md`.

## Working Directory
`/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3`

## Authoritative Request Reference
Read `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md` (specifically `## Follow-up — 2026-10-02T08:00:47Z`).

## Scope & Instructions
1. **R5: Fix draft autosave subscription scope leak**:
   - Inspect `campaigns/frontend/eiTreeStore.ts`: find the Zustand `subscribe` call that writes `elein_unsaved_draft` to localStorage.
   - Inspect `campaigns/frontend/EleInCreateCampaign.tsx`: analyze its lifecycle, mounting/unmounting, and how subscription can be scoped cleanly (e.g. subscribing on mount in `useEffect`, unsubscribing on unmount, or exposing start/stop/subscribe functions).
   - Ensure the autosave functionality itself is preserved and works during campaign creation/editing, but does not run globally on other pages.
2. **R7: Verify approval queue frontend-to-backend integration**:
   - Inspect `inbox/frontend/EleInApprovals.tsx`: check all API calls (`GET /api/approvals`, `POST /api/approvals/{id}/approve`, `POST /api/approvals/{id}/reject`).
   - Inspect `core/frontend/lib/apiClient.ts`: check `fetchWithAuth` implementation, base URL handling, route prefix resolution.
   - Inspect `core/backend/api/routers/approvals.py`: check `approve` endpoint (does it trigger a LinkedIn `inbox_action` job or how does it trigger delivery?), and check `reject` endpoint (does it reset the item and unblock `campaign_execution_states`?).
   - Identify any missing job triggers, status updates, or routing mismatches.
3. **R8: Treestore state reset bug on campaign edit**:
   - Inspect `campaigns/frontend/EleInCreateCampaign.tsx`: analyze how editing an existing campaign (`/campaigns/{id}/edit` or `id` prop/param) works.
   - Check how campaign data is fetched and loaded into the Zustand store (`eiTreeStore.ts`).
   - Inspect `campaigns/backend/routers/elein.py`: verify the endpoint that fetches campaign details for editing (nodes, edges, settings, metadata).
   - Identify why state might reset to default empty store on edit, and how to ensure sequence tree and metadata fields populate cleanly before user interactions.

## Output
Write your findings and verified evidence chains to `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md`.


## 2026-10-02T08:04:48Z
You are Explorer 3. Your working directory is `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3`.
First, read your task dispatch at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/DISPATCH.md`.
Read the authoritative user request at `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Investigate Requirements R5, R7, and R8 in the Ele-in codebase:
- R5: Draft autosave subscription scope leak in `campaigns/frontend/eiTreeStore.ts` and scoping it in `campaigns/frontend/EleInCreateCampaign.tsx`.
- R7: Approval queue integration in `inbox/frontend/EleInApprovals.tsx`, `core/frontend/lib/apiClient.ts`, and `core/backend/api/routers/approvals.py` (LinkedIn job delivery trigger on approve, unblock lead state on reject).
- R8: Treestore state reset bug on campaign edit in `campaigns/frontend/EleInCreateCampaign.tsx` and `campaigns/backend/routers/elein.py`.
Produce a thorough handoff report at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md` with exact code snippets, line numbers, and precise proposed fix implementations. When done, send a message to parent reporting completion and referencing the handoff path.
