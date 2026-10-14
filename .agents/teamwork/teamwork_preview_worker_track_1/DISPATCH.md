# Dispatch for teamwork_preview_worker_track_1

## Task
You are Worker 1 implementing Requirements R1, R4, and R6 for Ele-in.
Apply real, robust, production-grade implementations to your assigned files.
Run syntax and compilation checks (`python3 -m py_compile ...` and `npx tsc --noEmit`) to verify your changes.
Write a detailed completion report at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_1/handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Authoritative Reference
Read `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Read Explorer 1's detailed findings at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_1/handoff.md`.

## Exclusive Write Ownership Boundaries
You ONLY edit/create these files:
1. `backend/migrations/033_fix_manual_mode_column.sql` (create this file)
2. `admin/backend/routers/workspaces.py`
3. `core/frontend/pages/settings/NotificationSettings.tsx`
4. `campaigns/backend/services/elein_orchestrator.py`
DO NOT modify any other files.

## Detailed Requirements & Implementation Guidance
1. **R1: Fix `manual_mode_enabled` column mismatch**:
   - Create `backend/migrations/033_fix_manual_mode_column.sql` replacing `a.manual_mode_enabled = FALSE` with `AND COALESCE(a.manual_send_suspected, false) = false` in `dequeue_due_leads`. See exact SQL in Explorer 1's handoff (lines 235–284).
   - In `campaigns/backend/services/elein_orchestrator.py`, verify line 383 `.rpc("dequeue_due_leads", {"p_batch_size": 50, "p_campaign_ids": active_campaign_ids})` matches the function parameters.
2. **R4: Fix notification settings route and payload mismatch**:
   - In `admin/backend/routers/workspaces.py`: In `get_notification_preferences` (around line 563), return `{"preferences": res.data or []}` instead of raw `res.data or []`.
   - In `core/frontend/pages/settings/NotificationSettings.tsx`: Update `useEffect` (lines 98–102) and `displayEventTypes` (lines 104–122) to defensively parse:
     `const rawPrefs = Array.isArray(data) ? data : data?.preferences;`
3. **R6: Fix campaign reply detection UTC comparison**:
   - In `campaigns/backend/services/elein_orchestrator.py`:
     - Add `_normalize_to_utc_iso(dt_val)` helper function ensuring timezone-aware UTC ISO string with explicit `+00:00` format (`YYYY-MM-DDTHH:MM:SS+00:00`).
     - Line 452: Normalize when setting `"enrollment_created_at": _normalize_to_utc_iso(enrollment.get("created_at"))`.
     - Lines 532–544 (Phase 7): Normalize `state.get("enrollment_created_at")` and ensure null guard before executing `.gt("created_at", norm_created_at)`.

## Verification Instructions
- Run: `python3 -m py_compile campaigns/backend/services/elein_orchestrator.py admin/backend/routers/workspaces.py`
- Run: `npx tsc --noEmit`
- Document the commands run and outputs in your handoff report.


## 2026-10-02T08:19:42Z
[Message] timestamp=2026-10-02T08:19:42Z sender=5d3e6db4-2d32-4498-919a-e452ffd1c2ef priority=MESSAGE_PRIORITY_HIGH content=You are Worker 1 implementing Requirements R1, R4, and R6 in Ele-in.
Your working directory is `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_1`.
First, read your task dispatch at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_1/DISPATCH.md`.
Read the authoritative user request at `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Read Explorer 1's detailed handoff at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_1/handoff.md`.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You exclusively own and modify:
1. `backend/migrations/033_fix_manual_mode_column.sql`
2. `admin/backend/routers/workspaces.py`
3. `core/frontend/pages/settings/NotificationSettings.tsx`
4. `campaigns/backend/services/elein_orchestrator.py`

Implement all fixes following the Three-Layer Logic Architecture. Run verification:
- `python3 -m py_compile campaigns/backend/services/elein_orchestrator.py admin/backend/routers/workspaces.py`
- `npx tsc --noEmit`
Write your completion report to `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_1/handoff.md`.
When done, send a message to parent reporting completion and referencing the handoff path.
