# Dispatch for teamwork_preview_worker_track_3

## Task
You are Worker 3 implementing Requirement R7 (Approval Queue Frontend-to-Backend Integration) for Ele-in.
Apply real, robust, production-grade implementations to your assigned files.
Run syntax and compilation checks (`python3 -m py_compile ...` and `npx tsc --noEmit`) to verify your changes.
Write a detailed completion report at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_3/handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Authoritative Reference
Read `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Read Explorer 3's detailed findings at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md`.

## Exclusive Write Ownership Boundaries
You ONLY edit/create these files:
1. `core/backend/api/routers/approvals.py`
2. `core/backend/workers/job_processor.py`
3. `core/frontend/lib/apiClient.ts`
DO NOT modify any other files.

## Detailed Requirements & Implementation Guidance
1. **R7: Approval Queue Integration (Approve & Reject flows)**:
   - In `core/backend/api/routers/approvals.py`:
     - In `approve_reply`:
       - Support fetching from both `approval_queue` and `ai_reply_approvals` tables.
       - Resolve `account_id`, `sender_name`, and `final_message`.
       - In `enqueue_job(supabase, 'inbox_action', workspace_id, account_id, payload)`:
         CRITICAL: Ensure `payload` contains `'account_id': account_id` and `'workspace_id': workspace_id` in addition to `'action': 'send_message_to_existing_thread'` and `'payload_data'` (otherwise `job_processor.py` line 84 crashes with `ValueError: Account None not found.`).
       - If `execution_state_id` is present, update `campaign_execution_states` (`status: "pending"`, `next_run_at: now`) so execution resumes.
     - In `reject_reply`:
       - Support fetching from both `approval_queue` (update status to `"skipped"`) and `ai_reply_approvals` (update status to `"rejected"`).
       - CRITICAL: Unblock lead execution state in `campaign_execution_states` (`status: "exited"`, `error_reason: "ai_reply_rejected"`) so the lead does not remain frozen in `"awaiting_approval"`.
   - In `core/backend/workers/job_processor.py`:
     - Line 84: Add fallback: `account_id = payload.get('account_id') or job.get('asset_id')` to ensure resilience against missing payload fields.
   - In `core/frontend/lib/apiClient.ts`:
     - Ensure URL normalization prepends `VITE_API_URL` cleanly when path does not start with http.

## Verification Instructions
- Run: `python3 -m py_compile core/backend/api/routers/approvals.py core/backend/workers/job_processor.py`
- Run: `npx tsc --noEmit`
- Document the commands run and outputs in your handoff report.


## 2026-10-02T08:19:42Z
You are Worker 3 implementing Requirement R7 (Approval Queue Integration) in Ele-in.
Your working directory is `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_3`.
First, read your task dispatch at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_3/DISPATCH.md`.
Read the authoritative user request at `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md`.
Read Explorer 3's detailed handoff at `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md`.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You exclusively own and modify:
1. `core/backend/api/routers/approvals.py`
2. `core/backend/workers/job_processor.py`
3. `core/frontend/lib/apiClient.ts`

Implement all fixes following the Three-Layer Logic Architecture. Run verification:
- `python3 -m py_compile core/backend/api/routers/approvals.py core/backend/workers/job_processor.py`
- `npx tsc --noEmit`
Write your completion report to `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_worker_track_3/handoff.md`.
When done, send a message to parent reporting completion and referencing the handoff path.
