# Known Issues & Post-Mortems

## Persistent API Error 502 / "Failed to fetch" on Save

### Root Cause
The save campaign endpoint produces two distinct failures:

1. **502 Bad Gateway**: Caused by orphaned `uvicorn` Python processes running in the background holding port 8000. When `uvicorn --reload` restarts or a terminal is closed abruptly, the master process may die but leave ghost workers behind. The Vite proxy then routes requests to a dead worker, causing an instant dropped connection and a 502.

2. **"Failed to fetch"**: The backend is completely unreachable — no process is listening on port 8000 at all. This is a pure connectivity failure. The Vite proxy correctly propagates this as a network error to the browser.

A secondary cause was an **agent debugging contamination**: during a debugging session, `workspace_id: str = Depends(get_current_workspace)` was temporarily replaced with `workspace_id: str = "test-workspace"` in `elein.py`. This was left in place across ALL endpoints, causing all authenticated requests to route data into a `"test-workspace"` bucket instead of the actual user's workspace. This meant campaigns appeared to save (no error) but never showed up in the user's campaigns list.

### Resolution
1. All orphaned Python processes on port 8000 were forcefully killed using `lsof -i :8000` and `kill -9`.
2. `workspace_id: str = "test-workspace"` was replaced back to `workspace_id: str = Depends(get_current_workspace)` across all endpoints in `backend/app/api/routers/elein.py`.
3. Created `backend/start.sh` which kills port 8000 occupants before starting uvicorn — prevents ghost processes permanently.
4. Added `onError` handler to `frontend/vite.config.ts` Vite proxy so "Failed to fetch" now returns a clear 503 with an actionable message instead of a silent failure.
5. Updated error handling in `EleInCreateCampaign.tsx` to distinguish "backend not running" from API errors and give the user an actionable message.

### Prevention
- **Always start the backend using `./backend/start.sh`** — never run uvicorn directly. The script automatically clears ghost processes.
- **Never leave debug test values** (like `workspace_id = "test-workspace"`) in production code. If debugging, use a git stash or a test branch — never leave test stubs in files.
- If you ever temporarily change a `Depends(...)` for debugging, always revert it before finishing.

---

## Resume Draft Lands on Campaign Setup Instead of Sequence Step

### Root Cause
The draft autosave stored only the sequence nodes (from the tree store), not the full form state (campaign name, lead list, senders, step index). When "Resume Draft" was clicked, it navigated to `/new?resume=true`, loaded the nodes into the tree store, but the step state initialized to `0` (Campaign Setup), so the user had to manually navigate to the Sequence step again.

### Resolution
1. The draft autosave now writes `{ nodes, formState, step, timestamp }` to `localStorage` on every change.
2. The resume logic now restores: sequence nodes, all form fields (name, lead list, senders, etc.), and the exact step the user was on.
3. The draft is cleared from `localStorage` on successful save so the "Unsaved Draft" banner does not reappear after saving.

### Prevention
When saving any resumable state, always persist the **entire application state** needed to fully restore the UX context — not just the primary data. Include the navigation step, all form fields, and any UI selection state.

---

## Knowledge Base Scraping Hangs Indefinitely

### Root Cause
The URL scraper runs in a background task (`process_url_bg`). It successfully scraped the URL, but crashed while trying to generate embeddings because `get_active_nvidia_keys()` tried to query a missing table `system_api_keys`. Due to the exception, the task attempted to update the database asset status to "failed", but if the backend was running inside an isolated sandbox, the outbound connection to Supabase was blocked, causing the error handler to crash as well. This left the asset permanently marked as "processing", causing the UI to spin forever.

### Resolution
1. Added a `try/except` block inside `get_active_nvidia_keys()` in `elein_ai_service.py` so it gracefully falls back to `.env` variables if the `system_api_keys` table does not exist.
2. Verified that if the embedding step fails (e.g., due to missing LLM keys), the background task now successfully updates the database status to `failed`, and the UI shows the failure instantly.

### Prevention
- Never assume database tables exist without a `try/except` fallback, especially when migrating or setting up new environments.
- Always ensure error handlers in background tasks do not themselves throw unhandled exceptions.


## The "Three-Layer Logic Architecture" (Paranoia Framework)
Every single piece of logic or bug fix must rigorously pass through these three distinct, uncompromising layers before it is considered complete. Do not dilute the quality of any layer; each is a massive architectural step.

### Layer 0: The Foundational Layer
Solve the core issue. This is the basic implementation that everyone knows how to do. Get the fundamental mechanic working.

### Layer 1: Environmental Failure Analysis
Ask exactly this question: *"In what situations or in what environments will this foundational logic fail?"*
- Generate a comprehensive list of edge cases, race conditions, system crashes, network drops, or environmental shifts where the code breaks.
- Find a robust architectural solution for *each and every* identified failure point.
- Integrate these solutions into the codebase.

### Layer 2: Human Paranoia (The Human Error Element)
Ask exactly this question: *"How can a human make a mistake in this section?"*
- Assume the human user will do the stupidest, most extreme thing possible (e.g., clicking 50 times, typing the wrong format, leaving the app open in 10 tabs, misinterpreting the UI, doing exactly what they were told not to do).
- Generate a plethora of answers mapping out these human errors.
- Find a robust, physically preventative solution for *each and every* identified human error.
- Integrate these solutions into the codebase to completely block the user from harming themselves or the system.
